"""
DDA — QUERY Agent
Takes a natural language question, retrieves relevant artifacts
from ChromaDB (semantic) + Firestore relationships (graph),
synthesises a cited answer via Gemini.
"""

import os
import sys
import json
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gcp_client import get_gemini_client, get_firestore, get_chromadb, get_all_artifacts

GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
EMBEDDING_MODEL   = "models/gemini-embedding-001"
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "dda_embeddings")
COL_ARTIFACTS     = os.getenv("FIRESTORE_ARTIFACTS", "dda_artifacts")
COL_RELATIONSHIPS = os.getenv("FIRESTORE_RELATIONSHIPS", "dda_relationships")
TOP_K             = 5
CONFIDENCE_FLOOR  = 0.75


# ── Step 1: Embed the query ───────────────────────────────────────────────────

def embed_query(client, question: str) -> list[float]:
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=question
    )
    return result.embeddings[0].values


# ── Step 2: Semantic retrieval from ChromaDB ──────────────────────────────────

def semantic_search(collection, query_embedding: list[float], top_k: int) -> list[dict]:
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    hits = []
    for i in range(len(results["ids"][0])):
        hits.append({
            "artifact_id": results["metadatas"][0][i]["artifact_id"],
            "filename":    results["metadatas"][0][i]["filename"],
            "snippet":     results["documents"][0][i],
            "distance":    results["distances"][0][i],
        })
    return hits


# ── Step 3: Graph retrieval from Firestore relationships ──────────────────────

def graph_search(semantic_hits: list[dict]) -> list[dict]:
    """Pull relationships where any semantic hit is source or target."""
    db = get_firestore()
    filenames = {h["filename"] for h in semantic_hits}
    relationships = []

    docs = db.collection(COL_RELATIONSHIPS).stream()
    for doc in docs:
        rel = doc.to_dict()
        if rel.get("source_doc") in filenames or rel.get("target_doc") in filenames:
            relationships.append(rel)

    return relationships[:10]  # cap to avoid context bloat


# ── Step 4: Hydrate full text for top hits ────────────────────────────────────

def hydrate_artifacts(artifact_ids: list[str]) -> list[dict]:
    """Fetch full raw_text for top retrieved artifact IDs."""
    db   = get_firestore()
    docs = db.collection(COL_ARTIFACTS).stream()
    lookup = {d.to_dict().get("artifact_id"): d.to_dict() for d in docs}
    return [lookup[aid] for aid in artifact_ids if aid in lookup]


# ── Step 5: Synthesise answer via Gemini ─────────────────────────────────────

QUERY_PROMPT = """
You are an enterprise pricing intelligence analyst. Answer the user's question
using ONLY the document excerpts and relationships provided below.
Never answer from general knowledge. If evidence is insufficient, say so explicitly.

For every factual claim in your answer, cite the source document filename in brackets like [filename].
End your answer with a JSON block in this exact format:

```json
{{
  "answer_summary": "<2-3 sentence summary>",
  "citations": [
    {{"filename": "<filename>", "relevance": "<why this doc supports the answer>"}}
  ],
  "confidence": <float 0.0-1.0>,
  "requires_human_review": <true|false>
}}
```

USER QUESTION:
{question}

RETRIEVED DOCUMENTS:
{documents}

RELATED RELATIONSHIPS:
{relationships}
"""

def synthesise_answer(client, question: str, artifacts: list[dict],
                       relationships: list[dict]) -> dict:
    # Build document context
    doc_context = ""
    for a in artifacts:
        doc_context += (
            f"\n--- {a.get('filename')} ({a.get('document_type')}) ---\n"
            f"{a.get('raw_text', '')[:2000]}\n"
        )

    # Build relationship context
    rel_context = ""
    for r in relationships:
        rel_context += (
            f"• {r.get('source_doc')} → {r.get('target_doc')} "
            f"[{r.get('relationship_type')}] "
            f"(confidence: {r.get('confidence', '?')}) — {r.get('narrative', '')}\n"
        )

    prompt = QUERY_PROMPT.format(
        question=question,
        documents=doc_context or "No documents retrieved.",
        relationships=rel_context or "No relationships found."
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )
    return response.text


# ── Step 6: Parse structured JSON from response ───────────────────────────────

def parse_response(raw: str) -> tuple[str, dict]:
    """Split narrative answer from trailing JSON block."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        narrative = raw[:match.start()].strip()
        try:
            structured = json.loads(match.group(1))
        except json.JSONDecodeError:
            structured = {"confidence": 0.5, "requires_human_review": True}
    else:
        narrative  = raw.strip()
        structured = {"confidence": 0.5, "requires_human_review": True}
    return narrative, structured


# ── Main ──────────────────────────────────────────────────────────────────────

def run_query_agent(question: str):
    print("=" * 60)
    print("DDA — QUERY Agent")
    print(f"Question: {question}")
    print("=" * 60)

    gemini_client = get_gemini_client()
    chroma_client = get_chromadb()
    collection    = chroma_client.get_or_create_collection(name=CHROMA_COLLECTION)

    # Step 1: Embed query
    print("\n[1/4] Embedding query...")
    query_vec = embed_query(gemini_client, question)

    # Step 2: Semantic search
    print("[2/4] Semantic search (ChromaDB)...")
    semantic_hits = semantic_search(collection, query_vec, TOP_K)
    print(f"      Top {len(semantic_hits)} hits:")
    for h in semantic_hits:
        print(f"        • {h['filename']} (distance: {h['distance']:.4f})")

    # Step 3: Graph search
    print("[3/4] Graph search (Firestore relationships)...")
    relationships = graph_search(semantic_hits)
    print(f"      Related relationships found: {len(relationships)}")

    # Step 4: Hydrate + synthesise
    print("[4/4] Synthesising answer via Gemini...")
    artifact_ids = [h["artifact_id"] for h in semantic_hits]
    artifacts    = hydrate_artifacts(artifact_ids)
    raw_response = synthesise_answer(gemini_client, question, artifacts, relationships)

    # Step 5: Parse + display
    narrative, structured = parse_response(raw_response)

    print("\n" + "=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(narrative)
    print("\n" + "─" * 60)
    print(f"Confidence     : {structured.get('confidence', 'N/A')}")
    print(f"Human Review   : {structured.get('requires_human_review', 'N/A')}")
    print(f"Citations      : {len(structured.get('citations', []))}")
    if structured.get("citations"):
        for c in structured["citations"]:
            print(f"  • {c.get('filename')} — {c.get('relevance', '')}")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default demo query if none provided
        question = "Which customers received the largest discounts and why?"
    else:
        question = " ".join(sys.argv[1:])

    run_query_agent(question)