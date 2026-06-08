import os, json, base64, logging, uuid
from datetime import datetime, timezone
import re
from fastapi import FastAPI, Request, HTTPException
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dda-correlate")
app = FastAPI(title="DDA Correlate Service")

PROJECT_ID    = os.environ.get("GCP_PROJECT_ID", "the-orchestrators")
ARTIFACTS_COL = os.environ.get("FIRESTORE_ARTIFACTS", "dda_artifacts")
BQ_DATASET    = os.environ.get("BIGQUERY_DATASET", "dda_knowledge_graph")
PUBSUB_CORRELATE_LISTEN_TOPIC    = os.environ.get("PUBSUB_CORRELATE_LISTEN_TOPIC", "dda-correlate-trigger")
PUBSUB_CORRELATE_TO_ENRICH_TOPIC_FULL = os.environ.get("PUBSUB_CORRELATE_TO_ENRICH_TOPIC", "dda-enrich-trigger")
PUBSUB_CORRELATE_TO_ENRICH_TOPIC_ID = PUBSUB_CORRELATE_TO_ENRICH_TOPIC_FULL.split('/')[-1]

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_ARTIFACTS_FOR_CORRELATION = int(os.environ.get("MAX_ARTIFACTS_FOR_CORRELATION", "10"))

def _parse_date(date_val: any) -> str | None:
    if not date_val: # Handle None or empty string/value
        return None
    date_str = str(date_val) # Ensure it's a string
    try:
        # Try parsing as YYYY-MM-DD
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        # Try parsing as YYYY-QX and convert to YYYY-MM-DD (e.g., 2016-Q1 -> 2016-01-01)
        if re.match(r"^\d{4}-Q[1-4]$", date_str):
            year, quarter_str = date_str.split('-')
            quarter = int(quarter_str[1])
            month = (quarter - 1) * 3 + 1
            return datetime(int(year), month, 1).strftime("%Y-%m-%d")
        raise ValueError("Not in YYYY-QX format") # Raise if format doesn't match
    except Exception as e:
        logger.warning(f"Could not parse date string '{date_str}': {e}")
        return None

@app.get("/health")
def health():
    return {"status": "ok", "service": "dda-correlate", "model": GEMINI_MODEL}

async def _perform_global_correlation_and_extract_results(client, db, bq, artifacts: list[dict]) -> tuple[list, list]:

    if not artifacts:
        logger.info("No artifacts with raw_text found for global correlation.")
        return [], []

    logger.info(f"Correlating {len(artifacts)} artifacts with {GEMINI_MODEL}")

    doc_block = "\n\n".join(
        f"--- {a.get('filename', 'unknown')} ({a.get('document_type', 'unknown')}) ---\n{a['raw_text'][:8000]}"
        for a in artifacts
    )

    prompt = f"""Analyze these {len(artifacts)} enterprise documents. Find cross-document relationships.

{doc_block}

Output ONLY valid JSON, no markdown fences:
{{
  "relationships": [it
    {{"source_doc": "filename", "target_doc": "filename",arti
      "relationship_type": "discount_approved|price_referenced|company_shared|decision_chain",
      "confidence": 0.9, "narrative": "explanation"}}
  ],
  "decisions": [
    {{"date": "YYYY-MM-DD", "actor": "role", "rationale": "why",
      "affected_segment": "Enterprise", "impact_estimate": "$X", "source_doc": "filename"}}
  ]
}}"""

    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    raw = response.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

    try:
        result = json.loads(raw)
    except Exception as e:
        logger.error(f"JSON parse error: {e} | raw: {raw}")
        raise ValueError(f"Failed to parse Gemini response: {e}")

    relationships = result.get("relationships", [])
    decisions     = result.get("decisions", [])
    now           = datetime.now(timezone.utc).isoformat()

    if relationships:
        try:
            bq.insert_rows_json(f"{PROJECT_ID}.{BQ_DATASET}.relationships", [
                {"relationship_id": str(uuid.uuid4()),
                 "source_doc": r.get("source_doc",""), "target_doc": r.get("target_doc",""),
                 "relationship_type": r.get("relationship_type",""),
                 "confidence": float(r.get("confidence", 0)),
                 "narrative": r.get("narrative",""), "discovered_at": now}
                for r in relationships
            ])
        except Exception as e:
            logger.error(f"BigQuery relationships insertion error: {e}", exc_info=True)
            raise ValueError(f"BigQuery relationships insertion failed: {e}")

    if decisions:
        try:
            bq.insert_rows_json(f"{PROJECT_ID}.{BQ_DATASET}.decisions", [
                {"decision_id": str(uuid.uuid4()),
                 # Apply _parse_date to ensure correct format for BigQuery
                 "date": _parse_date(d.get("date")),
             "actor": d.get("actor",""), "rationale": d.get("rationale",""),
             "affected_segment": d.get("affected_segment",""),
             "impact_estimate": d.get("impact_estimate",""),
                 "source_doc": d.get("source_doc",""), "discovered_at": now}
                for d in decisions # Corrected loop variable from 'r' to 'd'
            ])
        except Exception as e:
            logger.error(f"BigQuery decisions insertion error: {e}", exc_info=True)
            raise ValueError(f"BigQuery decisions insertion failed: {e}")
    
    logger.info(f"Global correlation completed: {len(relationships)} relationships, {len(decisions)} decisions")
    return relationships, decisions
@app.post("/correlate/trigger")
async def correlate_trigger(request: Request):
    """
    Receives Pub/Sub push message containing artifact_id to correlate.
    Triggers a global correlation, then updates the specific artifact's stage.
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
        logger.error(f"Bad Pub/Sub message format: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    return await _run_correlation_for_artifact(artifact_id)

async def _run_correlation_for_artifact(triggered_artifact_id: str):
    from google.cloud import firestore, bigquery, pubsub_v1
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    db = firestore.Client(project=PROJECT_ID)
    bq = bigquery.Client(project=PROJECT_ID)
    publisher = pubsub_v1.PublisherClient()

    artifact_ref = db.collection(ARTIFACTS_COL).document(triggered_artifact_id)
    artifact_doc = artifact_ref.get()

    if not artifact_doc.exists:
        logger.error(f"Artifact {triggered_artifact_id} not found in Firestore.")
        raise HTTPException(status_code=404, detail=f"Artifact {triggered_artifact_id} not found.")

    artifact = artifact_doc.to_dict()

    if artifact.get("pipeline_stage") != "INGESTED":
        logger.warning(f"Artifact {triggered_artifact_id} is not in 'INGESTED' stage. Current stage: {artifact.get('pipeline_stage')}. Skipping correlation.")
        return {"status": "skipped", "artifact_id": triggered_artifact_id, "reason": "not_in_ingested_stage"}

    logger.info(f"Starting correlation for artifact_id: {triggered_artifact_id}")

    # Fetch relevant artifacts for correlation
    # Always include the triggered artifact
    artifacts_to_correlate = [artifact]

    # Fetch other recent artifacts, excluding the triggered one
    # Query for the most recent artifacts that are either INGESTED or CORRELATED
    recent_docs_query = db.collection(ARTIFACTS_COL)\
                            .where("pipeline_stage", "in", ["INGESTED", "CORRELATED"])\
                            .order_by("correlated_at", direction=firestore.Query.DESCENDING)\
                            .order_by("ingested_at", direction=firestore.Query.DESCENDING)\
                            .limit(MAX_ARTIFACTS_FOR_CORRELATION - 1)
    
    recent_artifacts = [
        d.to_dict() for d in recent_docs_query.stream() 
        if d.id != triggered_artifact_id and d.to_dict().get("raw_text")
    ]
    artifacts_to_correlate.extend(recent_artifacts)

    # Remove duplicates if any (e.g., if triggered was also in recent)
    seen_filenames = set()
    unique_artifacts = []
    for art in artifacts_to_correlate:
        if art.get("filename") not in seen_filenames:
            unique_artifacts.append(art)
            seen_filenames.add(art.get("filename"))
    
    logger.info(f"Correlating {len(unique_artifacts)} artifacts with {GEMINI_MODEL}")

    # Perform correlation with the selected artifacts
    relationships, decisions = await _perform_global_correlation_and_extract_results(client, db, bq, unique_artifacts)

    # Update only the triggered artifact's pipeline stage
    try:
        artifact_ref.update({
            "pipeline_stage": "CORRELATED",
            "correlated_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Artifact {triggered_artifact_id} pipeline stage updated to CORRELATED.")
    except Exception as e:
        logger.error(f"Failed to update pipeline_stage for {triggered_artifact_id}: {e}", exc_info=True)
        artifact_ref.update({
            "correlate_error": str(e),
            "requires_review": True,
            "pipeline_stage": "CORRELATE_FAILED",
            "failed_at": datetime.now(timezone.utc).isoformat()
        })
        raise HTTPException(status_code=500, detail=f"Failed to update pipeline stage for {triggered_artifact_id}")

    # Publish to next stage
    try:
        publisher.publish(publisher.topic_path(PROJECT_ID, PUBSUB_CORRELATE_TO_ENRICH_TOPIC_ID), json.dumps({"artifact_id": triggered_artifact_id}).encode()).result()
        logger.info(f"Published {triggered_artifact_id} to {PUBSUB_CORRELATE_TO_ENRICH_TOPIC_ID}")
    except Exception as e:
        logger.error(f"Failed to publish to enrich topic for {triggered_artifact_id}: {e}", exc_info=True)
        artifact_ref.update({
            "enrich_trigger_error": str(e),
            "requires_review": True,
            "pipeline_stage": "CORRELATED_PUB_FAIL", # Or a new failure stage
            "failed_at": datetime.now(timezone.utc).isoformat()
        })
        raise HTTPException(status_code=500, detail=f"Failed to publish enrich trigger for {triggered_artifact_id}")

    return {"status": "ok", "artifact_id": triggered_artifact_id, "relationships_found": len(relationships), "decisions_found": len(decisions)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
