import os, json, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.cloud import firestore, bigquery, pubsub_v1
from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel
from vertexai.language_models import TextEmbeddingModel

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID        = os.getenv("GCP_PROJECT_ID", "the-orchestrators")
REGION            = os.getenv("GCP_REGION", "us-central1")
FIRESTORE_ARTIFACTS = os.getenv("FIRESTORE_ARTIFACTS", "dda_artifacts")
BIGQUERY_DATASET  = os.getenv("BIGQUERY_DATASET", "dda_knowledge_graph")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
INDEX_ENDPOINT    = os.getenv("VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT")
DEPLOYED_INDEX_ID = os.getenv("VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID", "dda_deployed_index")
VECTOR_TOP_K      = int(os.getenv("VECTOR_TOP_K", "5"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
HITL_TOPIC        = os.getenv("PUBSUB_HITL_TOPIC", "dda-hitl-queue")

# ── GCP Clients ───────────────────────────────────────────────────────────────
db        = firestore.Client(project=PROJECT_ID)
bq        = bigquery.Client(project=PROJECT_ID)
publisher = pubsub_v1.PublisherClient()
hitl_path = publisher.topic_path(PROJECT_ID, HITL_TOPIC)

vertexai.init(project=PROJECT_ID, location=REGION)
aiplatform.init(project=PROJECT_ID, location=REGION)
gemini          = GenerativeModel(GEMINI_MODEL)
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")

# ── Step 1: Embed the Query ───────────────────────────────────────────────────
def embed_query(query: str) -> list[float]:
    result = embedding_model.get_embeddings([query])
    return result[0].values

# ── Step 2A: Vector Search Retrieval ─────────────────────────────────────────
def vector_search(query_embedding: list[float]) -> list[dict]:
    endpoint = aiplatform.MatchingEngineIndexEndpoint(
        index_endpoint_name=INDEX_ENDPOINT
    )

    response = endpoint.find_neighbors(
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[query_embedding],
        num_neighbors=VECTOR_TOP_K
    )

    results = []
    for neighbor in response[0]:
        results.append({
            "artifact_id": neighbor.id,
            "distance":    neighbor.distance
        })
    return results

# ── Step 2B: Fetch Artifact Text from Firestore ───────────────────────────────
def fetch_artifact(artifact_id: str) -> dict | None:
    doc = db.collection(FIRESTORE_ARTIFACTS).document(artifact_id).get()
    return doc.to_dict() if doc.exists else None

# ── Step 2C: BigQuery Graph Retrieval ────────────────────────────────────────
def graph_search(query: str) -> list[dict]:
    """Fetch relationships and decisions from BigQuery relevant to the query."""
    # Pull all relationships + decisions — small dataset, full scan is fine
    relationships = list(bq.query("""
        SELECT source_doc, target_doc, relationship_type, confidence, narrative
        FROM dda_knowledge_graph.relationships
        ORDER BY confidence DESC
    """).result())

    decisions = list(bq.query("""
        SELECT date, actor, rationale, affected_segment, impact_estimate, source_doc
        FROM dda_knowledge_graph.decisions
        ORDER BY date
    """).result())

    return {
        "relationships": [dict(r) for r in relationships],
        "decisions":     [dict(d) for d in decisions]
    }

# ── Step 3: Build Synthesis Prompt ───────────────────────────────────────────
def build_synthesis_prompt(query: str, artifacts: list[dict], graph_data: dict) -> str:
    # Build context from retrieved artifacts
    artifact_context = ""
    for art in artifacts:
        artifact_context += f"""
--- {art['filename']} ({art['document_type']}) ---
{art.get('raw_text', '')[:2000]}
"""

    # Build graph context
    rel_context = ""
    for r in graph_data["relationships"][:10]:
        rel_context += f"  [{r['relationship_type']}] {r['source_doc']} ↔ {r['target_doc']} (confidence: {r['confidence']}): {r['narrative']}\n"

    dec_context = ""
    for d in graph_data["decisions"]:
        dec_context += f"  [{d['date']}] {d['actor']} | {d['affected_segment']} | {d['impact_estimate']} | source: {d['source_doc']}\n"

    return f"""You are an enterprise pricing intelligence analyst.
Answer the following question using ONLY the provided document context, relationships, and decisions.
Never answer from general knowledge. If evidence is insufficient, say so explicitly.
Every factual claim MUST cite the source document filename.

QUESTION: {query}

RETRIEVED DOCUMENTS:
{artifact_context}

KNOWN RELATIONSHIPS:
{rel_context}

PRICING DECISIONS:
{dec_context}

Instructions:
1. Answer the question directly and specifically using the evidence above
2. Cite source documents for every claim using [filename] notation
3. Highlight any anomalies, trends, or patterns relevant to the question
4. Assign an overall confidence score (0.0-1.0) based on evidence quality
5. State if human review is recommended

Output ONLY valid JSON:
{{
  "answer": "<detailed narrative answer with [filename] citations>",
  "key_findings": ["<finding 1>", "<finding 2>", "<finding 3>"],
  "citations": [
    {{
      "filename": "<source filename>",
      "excerpt": "<relevant excerpt max 100 chars>",
      "confidence": <0.0-1.0>
    }}
  ],
  "overall_confidence": <0.0-1.0>,
  "requires_human_review": <true|false>,
  "anomalies_detected": ["<anomaly if any>"]
}}"""

# ── Step 4: Parse Response ────────────────────────────────────────────────────
def parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())

# ── Step 5: Log to Firestore ──────────────────────────────────────────────────
def log_query(query: str, answer: dict, trace_id: str):
    db.collection("dda_query_log").document(trace_id).set({
        "trace_id":         trace_id,
        "query":            query,
        "answer":           answer.get("answer", ""),
        "overall_confidence": answer.get("overall_confidence", 0),
        "requires_human_review": answer.get("requires_human_review", False),
        "queried_at":       datetime.now(timezone.utc).isoformat()
    })

# ── Step 6: HITL Gate ────────────────────────────────────────────────────────
def route_to_hitl(trace_id: str, query: str, answer: dict):
    payload = json.dumps({
        "trace_id": trace_id,
        "query":    query,
        "reason":   "confidence_below_threshold",
        "confidence": answer.get("overall_confidence"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }).encode()
    publisher.publish(hitl_path, payload)
    print(f"  ⚠  Low confidence — routed to HITL queue")

# ── Main Query Function ───────────────────────────────────────────────────────
def query_dda(question: str) -> dict:
    trace_id = str(uuid.uuid4())[:8]
    print(f"\n{'='*60}")
    print(f"  QUERY: {question}")
    print(f"  trace_id: {trace_id}")
    print(f"{'='*60}\n")

    # Embed query
    print("Step 1: Embedding query...")
    query_embedding = embed_query(question)
    print(f"  ✅ Query embedded ({len(query_embedding)} dims)\n")

    # Vector search
    print("Step 2A: Vector Search retrieval...")
    vector_results = vector_search(query_embedding)
    print(f"  ✅ {len(vector_results)} nearest neighbors found")
    for v in vector_results:
        print(f"    artifact_id: {v['artifact_id']} | distance: {v['distance']:.4f}")

    # Fetch artifact texts
    print("\nStep 2B: Fetching artifact content from Firestore...")
    artifacts = []
    for v in vector_results:
        art = fetch_artifact(v["artifact_id"])
        if art:
            artifacts.append(art)
            print(f"  ✅ {art['filename']}")

    # Graph retrieval
    print("\nStep 2C: Graph retrieval from BigQuery...")
    graph_data = graph_search(question)
    print(f"  ✅ {len(graph_data['relationships'])} relationships | {len(graph_data['decisions'])} decisions\n")

    # Synthesize
    print(f"Step 3: Synthesizing answer with {GEMINI_MODEL}...")
    prompt   = build_synthesis_prompt(question, artifacts, graph_data)
    response = gemini.generate_content(prompt)
    print(f"  ✅ Response received ({len(response.text)} chars)\n")

    # Parse
    print("Step 4: Parsing structured response...")
    try:
        parsed = parse_response(response.text)
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse failed: {e}")
        print(f"  Raw: {response.text[:300]}")
        return {"error": str(e)}

    # HITL gate
    confidence = parsed.get("overall_confidence", 0)
    if confidence < CONFIDENCE_THRESHOLD:
        route_to_hitl(trace_id, question, parsed)
    else:
        print(f"  ✅ Confidence: {confidence} — cleared for delivery\n")

    # Log
    log_query(question, parsed, trace_id)

    # Print answer
    print(f"{'='*60}")
    print(f"  ANSWER:")
    print(f"{'='*60}")
    print(f"\n{parsed.get('answer', 'No answer generated')}\n")

    print(f"KEY FINDINGS:")
    for i, finding in enumerate(parsed.get("key_findings", []), 1):
        print(f"  {i}. {finding}")

    print(f"\nCITATIONS:")
    for c in parsed.get("citations", []):
        print(f"  [{c['confidence']}] {c['filename']}: {c['excerpt'][:80]}")

    print(f"\nANOMALIES:")
    for a in parsed.get("anomalies_detected", []):
        print(f"  ⚠  {a}")

    print(f"\nOVERALL CONFIDENCE: {confidence}")
    print(f"REQUIRES HUMAN REVIEW: {parsed.get('requires_human_review')}")
    print(f"TRACE ID: {trace_id}")
    print(f"{'='*60}\n")

    return parsed

# ── Demo Queries ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    demo_queries = [
        "Which customers received the largest discounts and why?",
        "What was the approval process for discounts above 15%?",
    ]

    for q in demo_queries:
        result = query_dda(q)
        print("\n" + "~"*60 + "\n")