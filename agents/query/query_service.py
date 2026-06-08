"""
DDA QUERY SERVICE — Minimal, working version
Focused on query/relationships only. Upload endpoint requires separate setup.
"""

import os, json, uuid, logging
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dda-query")

app = FastAPI(title="DDA Query Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PROJECT_ID           = os.environ.get("GCP_PROJECT_ID", "the-orchestrators")
REGION               = os.environ.get("GCP_REGION", "us-central1")
ARTIFACTS_COL        = os.environ.get("FIRESTORE_ARTIFACTS", "dda_artifacts")
QUERY_LOG_COL        = os.environ.get("FIRESTORE_QUERY_LOG", "dda_query_log")
BQ_DATASET           = os.environ.get("BIGQUERY_DATASET", "dda_knowledge_graph")
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.75"))
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL         = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Artifact cache
_ARTIFACT_CACHE = []
_CACHE_LOADED = False

def get_artifact_cache():
    global _ARTIFACT_CACHE, _CACHE_LOADED
    if not _CACHE_LOADED:
        try:
            from google.cloud import firestore
            db = firestore.Client(project=PROJECT_ID)
            _ARTIFACT_CACHE = [
                doc.to_dict() for doc in db.collection(ARTIFACTS_COL).stream()
                if doc.to_dict().get("raw_text")
            ]
            _CACHE_LOADED = True
            logger.info(f"✓ Cache: {len(_ARTIFACT_CACHE)} artifacts")
        except Exception as e:
            logger.error(f"Cache load failed: {e}")
    return _ARTIFACT_CACHE

@app.on_event("startup")
async def warmup():
    import asyncio
    asyncio.create_task(asyncio.to_thread(get_artifact_cache))

class QueryRequest(BaseModel):
    user_id: str = "anonymous"
    session_id: str = ""
    query: str
    filters: Optional[dict] = None

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "dda-query",
        "model": GEMINI_MODEL,
        "cache_loaded": _CACHE_LOADED,
        "cached_artifacts": len(_ARTIFACT_CACHE),
    }

@app.post("/v1/cache/refresh")
async def refresh_cache():
    global _CACHE_LOADED
    _CACHE_LOADED = False
    get_artifact_cache()
    return {"status": "ok", "cached_artifacts": len(_ARTIFACT_CACHE)}

@app.post("/v1/query")
async def handle_query(req: QueryRequest):
    from google.cloud import firestore
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    trace_id = str(uuid.uuid4())[:8]
    start_time = datetime.now(timezone.utc)

    all_artifacts = get_artifact_cache()
    if not all_artifacts:
        db = firestore.Client(project=PROJECT_ID)
        all_artifacts = [
            d.to_dict() for d in db.collection(ARTIFACTS_COL).stream()
            if d.to_dict().get("raw_text")
        ]

    logger.info(f"[{trace_id}] Query: {req.query[:60]}")

    # Compact context
    context = "\n\n---\n\n".join(
        f"[{a['filename']}]\n{a['raw_text'][:800]}"
        for a in all_artifacts[:12]
    )

    prompt = f"""You are an enterprise pricing intelligence analyst.
Answer ONLY from the documents provided. Cite sources like [filename].
If insufficient evidence, say so.

Question: {req.query}

Documents:
{context}

Answer:"""

    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        answer = response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        answer = f"Error generating response: {str(e)[:200]}"

    confidence = 0.5 if "insufficient" in answer.lower() else 0.88
    latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

    citations = [
        {
            "artifact_id": a["artifact_id"],
            "filename": a["filename"],
            "excerpt": a["raw_text"][:300],
            "confidence": a.get("extraction_confidence", 0.9)
        }
        for a in all_artifacts if a["filename"] in answer
    ]
    if not citations and all_artifacts:
        a = all_artifacts[0]
        citations = [{
            "artifact_id": a["artifact_id"],
            "filename": a["filename"],
            "excerpt": a["raw_text"][:300],
            "confidence": 0.9
        }]

    try:
        db = firestore.Client(project=PROJECT_ID)
        db.collection(QUERY_LOG_COL).document(trace_id).set({
            "trace_id": trace_id,
            "user_id": req.user_id,
            "query": req.query,
            "answer": answer[:500],
            "confidence": confidence,
            "latency_ms": latency_ms,
            "queried_at": start_time.isoformat(),
        })
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    logger.info(f"[{trace_id}] ✓ {latency_ms}ms")

    return {
        "answer": answer,
        "citations": citations,
        "overall_confidence": confidence,
        "requires_human_review": confidence < CONFIDENCE_THRESHOLD,
        "query_latency_ms": latency_ms,
        "trace_id": trace_id,
        "artifacts_retrieved": len(all_artifacts),
    }

@app.get("/v1/relationships")
async def get_relationships():
    from google.cloud import bigquery
    bq = bigquery.Client(project=PROJECT_ID)
    try:
        rels = [dict(r) for r in bq.query(
            f"SELECT source_doc, target_doc, relationship_type, "
            f"CAST(confidence AS FLOAT64) as confidence, narrative "
            f"FROM `{PROJECT_ID}.{BQ_DATASET}.relationships`"
        ).result()]
        decs = [dict(d) for d in bq.query(
            f"SELECT CAST(date AS STRING) as date, actor, rationale, "
            f"affected_segment, impact_estimate, source_doc "
            f"FROM `{PROJECT_ID}.{BQ_DATASET}.decisions`"
        ).result()]
        return {"relationships": rels, "decisions": decs}
    except Exception as e:
        logger.error(f"Relationships: {e}")
        return {"relationships": [], "decisions": [], "error": str(e)}

@app.get("/v1/artifacts")
async def list_artifacts():
    artifacts = get_artifact_cache()
    return {
        "artifacts": [{k: v for k, v in a.items() if k != "raw_text"} for a in artifacts],
        "count": len(artifacts),
    }

@app.get("/v1/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT_ID)
    artifact_ref = db.collection(ARTIFACTS_COL).document(artifact_id)
    artifact_doc = artifact_ref.get()

    if not artifact_doc.exists:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found.")

    artifact = artifact_doc.to_dict()
    return {k: v for k, v in artifact.items() if k != "raw_text"}

@app.get("/v1/status")
async def status():
    from google.cloud import firestore, bigquery
    db = firestore.Client(project=PROJECT_ID)
    bq = bigquery.Client(project=PROJECT_ID) # Initialize BigQuery client
    docs = [d.to_dict() for d in db.collection(ARTIFACTS_COL).stream() if d.to_dict().get("raw_text")]
    stages = {}
    for d in docs:
        s = d.get("pipeline_stage", "UNKNOWN")
        stages[s] = stages.get(s, 0) + 1
    try:
        rel = next(bq.query(f"SELECT COUNT(*) c FROM `{PROJECT_ID}.{BQ_DATASET}.relationships`").result()).c
        dec = next(bq.query(f"SELECT COUNT(*) c FROM `{PROJECT_ID}.{BQ_DATASET}.decisions`").result()).c
    except Exception as e: # Catch specific exception for better logging
        logger.error(f"Error fetching BigQuery counts for status: {e}")
        rel = dec = -1
    return {"total_artifacts": len(docs), "pipeline_stages": stages, "relationships": rel, "decisions": dec}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))