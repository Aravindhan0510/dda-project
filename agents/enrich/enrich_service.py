import os, json, base64, logging, re
from datetime import datetime, timezone
from fastapi import FastAPI, Request
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dda-enrich")
app = FastAPI(title="DDA Enrich Service")

PROJECT_ID        = os.environ.get("GCP_PROJECT_ID", "the-orchestrators")
REGION            = os.environ.get("GCP_REGION", "us-central1")
ARTIFACTS_COL     = os.environ.get("FIRESTORE_ARTIFACTS", "dda_artifacts")
PUBSUB_ENRICH_LISTEN_TOPIC       = os.environ.get("PUBSUB_ENRICH_LISTEN_TOPIC", "dda-enrich-trigger")
PUBSUB_ENRICH_TO_QUERY_READY_TOPIC = os.environ.get("PUBSUB_ENRICH_TO_QUERY_READY_TOPIC", "dda-query-ready")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
VS_INDEX_ENDPOINT = os.environ.get("VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT", "")
VS_DEPLOYED_INDEX = os.environ.get("VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID", "dda_deployed_index")

@app.get("/health")
def health():
    return {"status": "ok", "service": "dda-enrich"}

@app.post("/enrich/trigger")
async def enrich_trigger(request: Request):
    """
    Receives Pub/Sub push message containing artifact_id to enrich.
    """
    body = await request.json()
    logger.info(f"Received Pub/Sub message body: {body}")
    try:
        msg_data = base64.b64decode(body["message"]["data"]).decode()
        logger.info(f"Decoded message data: {msg_data}")
        event = json.loads(msg_data)
        logger.info(f"Parsed event: {event}")
        artifact_id = event["artifact_id"]
    except Exception as e:
        logger.error(f"Bad Pub/Sub message: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    return await _run_enrichment_for_artifact(artifact_id)

async def _run_enrichment_for_artifact(triggered_artifact_id: str):
    from google.cloud import firestore, pubsub_v1
    from google.cloud import aiplatform
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    db = firestore.Client(project=PROJECT_ID)
    publisher = pubsub_v1.PublisherClient()
    aiplatform.init(project=PROJECT_ID, location=REGION)

    artifact_ref = db.collection(ARTIFACTS_COL).document(triggered_artifact_id)
    artifact_doc = artifact_ref.get()

    if not artifact_doc.exists:
        logger.error(f"Artifact {triggered_artifact_id} not found in Firestore.")
        raise HTTPException(status_code=404, detail=f"Artifact {triggered_artifact_id} not found.")

    artifact = artifact_doc.to_dict()

    if artifact.get("pipeline_stage") != "CORRELATED":
        logger.warning(f"Artifact {triggered_artifact_id} is not in 'CORRELATED' stage. Current stage: {artifact.get('pipeline_stage')}. Skipping enrichment.")
        return {"status": "skipped", "artifact_id": triggered_artifact_id, "reason": "not_in_correlated_stage"}

    logger.info(f"Starting enrichment for artifact_id: {triggered_artifact_id}")

    raw_text = artifact.get("raw_text", "")
    if not raw_text:
        logger.error(f"Artifact {triggered_artifact_id} has no raw_text to enrich.")
        artifact_ref.update({
            "enrich_error": "No raw_text for enrichment",
            "requires_review": True,
            "pipeline_stage": "ENRICH_FAILED",
            "failed_at": datetime.now(timezone.utc).isoformat()
        })
        raise HTTPException(status_code=500, detail=f"No raw_text for enrichment for {triggered_artifact_id}")

    try:
        # Embedding via google-genai
        embed_response = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=raw_text[:8000]
        )
        embedding = embed_response.embeddings[0].values

        # Vector Search upsert
        if VS_INDEX_ENDPOINT:
            try:
                endpoint = aiplatform.MatchingEngineIndexEndpoint(
                    index_endpoint_name=VS_INDEX_ENDPOINT)
                endpoint.upsert_datapoints(
                    deployed_index_id=VS_DEPLOYED_INDEX,
                    datapoints=[aiplatform.MatchingEngineIndexEndpoint.Datapoint(
                        datapoint_id=triggered_artifact_id, feature_vector=embedding)])
                logger.info(f"Vector upsert OK: {triggered_artifact_id}")
            except Exception as ve:
                logger.warning(f"Vector upsert non-fatal for {triggered_artifact_id}: {ve}")

        # Regex NER
        entities = []
        for m in re.finditer(r'\$[\d,]+(?:\.\d{2})?(?:K|M)?', raw_text):
            entities.append({"text": m.group(), "type": "PRICE", "confidence": 0.95})
        for m in re.finditer(r'\b\d{4}-\d{2}-\d{2}\b', raw_text):
            entities.append({"text": m.group(), "type": "DATE", "confidence": 0.98})
        for m in re.finditer(r'\b\d{1,3}(?:\.\d+)?%', raw_text):
            entities.append({"text": m.group(), "type": "PERCENTAGE", "confidence": 0.90})
        entities = entities[:50]

        # Domain tags
        text_lower  = raw_text.lower()
        domain_tags = [artifact.get("document_type", "unknown")]
        if "discount" in text_lower or "approval" in text_lower:
            domain_tags.append("discount_approval")
        if "price" in text_lower or "pricing" in text_lower:
            domain_tags.append("revenue_intelligence")
        if "compliance" in text_lower or "audit" in text_lower:
            domain_tags.append("compliance")

        artifact_ref.update({
            "entities": entities, "domain_tags": list(set(domain_tags)),
            "embedding_id": f"vs-{triggered_artifact_id}",
            "pipeline_stage": "ENRICHED",
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Enriched: {triggered_artifact_id} ({len(entities)} entities)")

        # Publish to next stage (Query Ready)
        try:
            publisher.publish(PUBSUB_ENRICH_TO_QUERY_READY_TOPIC, json.dumps({"artifact_id": triggered_artifact_id}).encode())
            logger.info(f"Published {triggered_artifact_id} to {PUBSUB_ENRICH_TO_QUERY_READY_TOPIC}")
        except Exception as e:
            logger.error(f"Failed to publish to query ready topic for {triggered_artifact_id}: {e}", exc_info=True)
            artifact_ref.update({
                "query_ready_trigger_error": str(e),
                "requires_review": True,
                "pipeline_stage": "ENRICHED_PUB_FAIL",
                "failed_at": datetime.now(timezone.utc).isoformat()
            })
            raise HTTPException(status_code=500, detail=f"Failed to publish query ready trigger for {triggered_artifact_id}")

        return {"status": "ok", "artifact_id": triggered_artifact_id, "entities_found": len(entities)}

    except Exception as e:
        logger.error(f"Failed to enrich {triggered_artifact_id}: {e}", exc_info=True)
        artifact_ref.update(
            {"enrich_error": str(e), "requires_review": True, "pipeline_stage": "ENRICH_FAILED", "failed_at": datetime.now(timezone.utc).isoformat()})
        raise HTTPException(status_code=500, detail=f"Enrichment failed for {triggered_artifact_id}: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
