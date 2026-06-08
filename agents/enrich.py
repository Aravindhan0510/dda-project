import os, json, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.cloud import firestore, pubsub_v1
from google.cloud.aiplatform_v1 import IndexServiceClient
from google.cloud.aiplatform_v1.types import IndexDatapoint
import vertexai
from vertexai.language_models import TextEmbeddingModel

load_dotenv()
# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID           = os.getenv("GCP_PROJECT_ID", "the-orchestrators")
REGION               = os.getenv("GCP_REGION", "us-central1")
FIRESTORE_ARTIFACTS  = os.getenv("FIRESTORE_ARTIFACTS", "dda_artifacts")
PUBSUB_ENRICH        = os.getenv("PUBSUB_ENRICH_TOPIC", "dda-enrich-complete")
INDEX_ENDPOINT       = os.getenv("VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT")
DEPLOYED_INDEX_ID    = os.getenv("VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID", "dda_deployed_index")
INDEX_RESOURCE       = os.getenv("VERTEX_VECTOR_SEARCH_INDEX_ID")
ENRICH_BATCH_SIZE    = int(os.getenv("ENRICH_BATCH_SIZE", "5"))

# ── GCP Clients ───────────────────────────────────────────────────────────────
db        = firestore.Client(project=PROJECT_ID)
publisher = pubsub_v1.PublisherClient()
topic_path= publisher.topic_path(PROJECT_ID, PUBSUB_ENRICH)

vertexai.init(project=PROJECT_ID, location=REGION)
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")

# ── Load Correlated Artifacts ─────────────────────────────────────────────────
def load_artifacts() -> list[dict]:
    docs = db.collection(FIRESTORE_ARTIFACTS)\
            .where("pipeline_stage", "==", "CORRELATED")\
            .stream()
    return [doc.to_dict() for doc in docs]

# ── Generate Embeddings ───────────────────────────────────────────────────────
def generate_embedding(text: str) -> list[float]:
    # Truncate to ~8000 chars — well within text-embedding-004 token limit
    truncated = text[:8000]
    embeddings = embedding_model.get_embeddings([truncated])
    return embeddings[0].values

# ── NER: Extract Entities from raw_text via simple heuristics + Gemini ────────
def extract_entities(artifact: dict) -> list[dict]:
    """
    Lightweight entity extraction using keyword patterns.
    Gemini-based NER runs in QUERY agent for on-demand enrichment.
    """
    import re
    text     = artifact.get("raw_text", "")
    filename = artifact.get("filename", "")
    entities = []

    # Prices — match $X,XXX or $X.XX patterns
    prices = re.findall(r'\$[\d,]+(?:\.\d{2})?', text)
    for p in set(prices):
        entities.append({"text": p, "type": "PRICE", "confidence": 0.97})

    # Dates — YYYY-MM-DD or Month DD, YYYY
    dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', text)
    for d in set(dates):
        entities.append({"text": d, "type": "DATE", "confidence": 1.0})

    # Percentages
    percents = re.findall(r'\b\d{1,3}(?:\.\d+)?%', text)
    for p in set(percents):
        entities.append({"text": p, "type": "DISCOUNT_RATE", "confidence": 0.95})

    # Company names from filename
    company_map = {
        "Acme_Corp":          "Acme Corp",
        "BlueStar_Ltd":       "BlueStar Ltd",
        "NovaTech_Inc":       "NovaTech Inc",
        "PrimeEdge_Solutions":"PrimeEdge Solutions",
        "Quantum_Dynamics":   "Quantum Dynamics"
    }
    for key, name in company_map.items():
        if key in filename or name in text:
            entities.append({"text": name, "type": "COMPANY", "confidence": 0.99})

    # People / roles
    roles = re.findall(r'\b(?:CFO|VP Sales|Finance Director|CEO|Director)\b', text)
    for r in set(roles):
        entities.append({"text": r, "type": "ROLE", "confidence": 0.95})

    names = re.findall(r'\b(?:Mark Lawson|Rita Gomez|Tom Blake)\b', text)
    for n in set(names):
        entities.append({"text": n, "type": "PERSON", "confidence": 0.98})

    return entities

# ── Classify Domain Tags ──────────────────────────────────────────────────────
def classify_domain_tags(artifact: dict) -> list[str]:
    doc_type = artifact.get("document_type", "")
    text     = artifact.get("raw_text", "").lower()
    tags     = [doc_type]

    if any(w in text for w in ["discount", "approval", "approved"]):
        tags.append("discount_approval")
    if any(w in text for w in ["margin", "revenue", "pricing"]):
        tags.append("revenue_intelligence")
    if any(w in text for w in ["compliance", "audit", "regulatory"]):
        tags.append("compliance")
    if any(w in text for w in ["enterprise", "smb", "mid-market"]):
        tags.append("segment_tagged")

    return list(set(tags))

# ── Upsert to Vertex AI Vector Search ────────────────────────────────────────
def upsert_to_vector_search(datapoints: list):
    from google.cloud import aiplatform_v1

    client = aiplatform_v1.IndexServiceClient(
        client_options={"api_endpoint": f"{REGION}-aiplatform.googleapis.com"}
    )
    request = aiplatform_v1.UpsertDatapointsRequest(
        index=INDEX_RESOURCE,
        datapoints=datapoints
    )

    client.upsert_datapoints(request=request)

# ── Update Firestore ──────────────────────────────────────────────────────────
def update_artifact_enrichment_batch(batch_updates: dict):
    batch = db.batch()
    for artifact_id, enrichment_data in batch_updates.items():
        doc_ref = db.collection(FIRESTORE_ARTIFACTS).document(artifact_id)
        batch.update(doc_ref, enrichment_data)
    batch.commit()

# ── Publish Completion ────────────────────────────────────────────────────────
def publish_completion(count: int):
    payload = json.dumps({
        "pipeline_stage": "ENRICHED",
        "artifacts_enriched": count,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }).encode()
    publisher.publish(topic_path, payload)
    print(f"  ✅ Published completion event to {PUBSUB_ENRICH}")

# ── Main ──────────────────────────────────────────────────────────────────────
def enrich():
    print(f"\n{'='*60}")
    print(f"  DDA ENRICH AGENT — Enterprise Build")
    print(f"  Embedding model: text-embedding-004")
    print(f"{'='*60}\n")

    # Load
    print("Step 1: Loading CORRELATED artifacts from Firestore...")
    artifacts = load_artifacts()
    print(f"  ✅ Loaded {len(artifacts)} artifacts\n")

    if not artifacts:
        print("  ⚠ No CORRELATED artifacts found. Run correlate.py first.")
        return

    enriched_count = 0

    # Process artifacts in batches
    for i in range(0, len(artifacts), ENRICH_BATCH_SIZE):
        batch_artifacts = artifacts[i:i + ENRICH_BATCH_SIZE]
        batch_raw_texts = [artifact.get("raw_text", "") for artifact in batch_artifacts]
        batch_artifact_ids = [artifact["artifact_id"] for artifact in batch_artifacts]

        print(f"Processing batch {i//ENRICH_BATCH_SIZE + 1}/{(len(artifacts) + ENRICH_BATCH_SIZE - 1)//ENRICH_BATCH_SIZE} ({len(batch_artifacts)} artifacts)")

        try:
            # Generate embeddings for the batch
            print(f"    → Generating embeddings for {len(batch_artifacts)} artifacts...")
            batch_embeddings_response = embedding_model.get_embeddings(batch_raw_texts)
            batch_embeddings = [e.values for e in batch_embeddings_response]
            print(f"    → Embeddings generated ✅")

            # Prepare datapoints for Vector Search upsert
            datapoints = []
            for j, embedding in enumerate(batch_embeddings):
                datapoints.append(IndexDatapoint(
                    datapoint_id=batch_artifact_ids[j],
                    feature_vector=embedding
                ))
            
            # Upsert to Vector Search for the batch
            print(f"    → Upserting {len(datapoints)} to Vertex AI Vector Search...")
            upsert_to_vector_search(datapoints)
            print(f"    → Vector Search upsert ✅")

            # Prepare Firestore batch update and process entities/tags
            firestore_batch_updates = {}
            for j, artifact in enumerate(batch_artifacts):
                artifact_id = artifact["artifact_id"]
                filename    = artifact["filename"]
                
                # Extract entities
                entities = extract_entities(artifact)
                domain_tags = classify_domain_tags(artifact)

                enrichment = {
                    "entities":       entities,
                    "domain_tags":    domain_tags,
                    "embedding_id":   artifact_id, # Assuming embedding_id is the artifact_id
                    "pipeline_stage": "ENRICHED",
                    "enriched_at":    datetime.now(timezone.utc).isoformat()
                }
                firestore_batch_updates[artifact_id] = enrichment
                print(f"      [{filename}] Entities: {len(entities)} | Tags: {domain_tags} ✅")
            
            # Update Firestore in a batch
            print(f"    → Updating Firestore for {len(firestore_batch_updates)} artifacts...")
            update_artifact_enrichment_batch(firestore_batch_updates)
            print(f"    → Firestore batch update ✅")

            enriched_count += len(batch_artifacts)

        except Exception as e:
            print(f"    → ❌ BATCH FAILED: {e}\n")
            # For a batch failure, individual artifact status might need more granular handling
            # For now, we'll just log and continue, but in a real system, failed artifacts
            # might be marked with a specific status or retried individually.

    # Publish
    print("Final Step: Publishing completion event...")
    publish_completion(enriched_count)

    print(f"\n{'='*60}")
    print(f"  ENRICH COMPLETE")
    print(f"  Artifacts enriched:  {enriched_count}/{len(artifacts)}")
    print(f"  Vector Search index: updated")
    print(f"  Firestore:           updated with entities + tags")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    enrich()
