"""
DDA — ENRICH Agent
Reads all artifacts from Firestore, generates vector embeddings
via Gemini embedding model, stores in ChromaDB for semantic search,
and tags entities back to Firestore.
"""

import os
import sys
import json
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gcp_client import get_gemini_client, get_all_artifacts, get_firestore, get_chromadb

GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
EMBEDDING_MODEL   = "models/gemini-embedding-001"
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "dda_embeddings")
COL_ARTIFACTS     = os.getenv("FIRESTORE_ARTIFACTS", "dda_artifacts")


# ── Step 1: Generate embedding for a single text ──────────────────────────────

def generate_embedding(client, text: str) -> list[float]:
    """Call Gemini embedding model; return vector."""
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text
    )
    return result.embeddings[0].values


# ── Step 2: Extract entities via Gemini ───────────────────────────────────────

ENTITY_PROMPT = """
Extract named entities from the following enterprise document text.
Return ONLY a valid JSON object. No prose, no markdown fences.

{{
  "companies": ["<company name>"],
  "people": ["<person name or role>"],
  "prices": ["<price or discount value>"],
  "dates": ["<date string>"],
  "products": ["<product or service name>"]
}}

TEXT:
{text}
"""

def extract_entities(client, text: str) -> dict:
    """Extract structured entities from document text via Gemini."""
    prompt = ENTITY_PROMPT.format(text=text[:2000])  # cap to avoid token waste
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"companies": [], "people": [], "prices": [], "dates": [], "products": []}


# ── Step 3: Upsert to ChromaDB ────────────────────────────────────────────────

def upsert_to_chromadb(collection, artifact_id: str, embedding: list[float],
                        metadata: dict, text: str):
    """Add or update artifact embedding in ChromaDB."""
    collection.upsert(
        ids=[artifact_id],
        embeddings=[embedding],
        documents=[text[:500]],   # store snippet for retrieval preview
        metadatas=[{
            "artifact_id": artifact_id,
            "filename":    metadata.get("filename", ""),
            "doc_type":    metadata.get("document_type", ""),
        }]
    )


# ── Step 4: Write entities back to Firestore ─────────────────────────────────

def update_artifact_entities(artifact_id: str, entities: dict):
    """Write entity tags and ENRICHED status back to Firestore artifact doc."""
    db  = get_firestore()
    ref = db.collection(COL_ARTIFACTS).document(artifact_id)
    ref.update({
        "entities":       entities,
        "pipeline_stage": "ENRICHED",
        "enriched_at":    datetime.now(timezone.utc).isoformat()
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def run_enrich_agent():
    print("=" * 60)
    print("DDA — ENRICH Agent Starting")
    print("=" * 60)

    # Load artifacts
    print("\n[1/4] Loading artifacts from Firestore...")
    artifacts = get_all_artifacts()
    print(f"      Loaded {len(artifacts)} artifacts")

    # Init clients
    print("\n[2/4] Initialising Gemini + ChromaDB clients...")
    gemini_client = get_gemini_client()
    chroma_client = get_chromadb()
    collection    = chroma_client.get_or_create_collection(name=CHROMA_COLLECTION)
    print(f"      ChromaDB collection: {CHROMA_COLLECTION}")

    # Process each artifact
    print("\n[3/4] Generating embeddings + extracting entities...")
    success = 0
    failed  = 0

    for i, artifact in enumerate(artifacts, 1):
        artifact_id = artifact.get("artifact_id") or artifact.get("id")
        filename    = artifact.get("filename", "unknown")
        raw_text    = artifact.get("raw_text", "")

        if not raw_text.strip():
            print(f"      [{i:02d}] SKIP (empty text): {filename}")
            failed += 1
            continue

        try:
            # Embedding
            embedding = generate_embedding(gemini_client, raw_text[:8000])

            # Entity extraction
            entities = extract_entities(gemini_client, raw_text)

            # Upsert to ChromaDB
            upsert_to_chromadb(collection, artifact_id, embedding, artifact, raw_text)

            # Update Firestore
            update_artifact_entities(artifact_id, entities)

            print(f"      [{i:02d}] OK: {filename} | "
                  f"companies={len(entities.get('companies',[]))} "
                  f"prices={len(entities.get('prices',[]))} "
                  f"dates={len(entities.get('dates',[]))}")
            success += 1

        except Exception as e:
            print(f"      [{i:02d}] ERROR: {filename} — {e}")
            failed += 1

    # Summary
    print("\n[4/4] Verifying ChromaDB...")
    count = collection.count()
    print(f"      Vectors in collection: {count}")

    print("\n" + "=" * 60)
    print("ENRICH Agent Complete")
    print(f"  Enriched successfully : {success}")
    print(f"  Failed                : {failed}")
    print(f"  ChromaDB vectors      : {count}")
    print(f"  Firestore updated     : pipeline_stage = ENRICHED")
    print(f"  Next step             : python agents/query.py")
    print("=" * 60)


if __name__ == "__main__":
    run_enrich_agent()