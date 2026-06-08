import os, json, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.cloud import firestore, bigquery, pubsub_v1
import vertexai
from vertexai.generative_models import GenerativeModel

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID           = os.getenv("GCP_PROJECT_ID", "the-orchestrators")
REGION               = os.getenv("GCP_REGION", "us-central1")
FIRESTORE_ARTIFACTS  = os.getenv("FIRESTORE_ARTIFACTS", "dda_artifacts")
BIGQUERY_DATASET     = os.getenv("BIGQUERY_DATASET", "dda_knowledge_graph")
PUBSUB_CORRELATE     = os.getenv("PUBSUB_CORRELATE_TOPIC", "dda-correlate-complete")
GEMINI_MODEL         = os.getenv("GEMINI_MODEL", "gemini-1.5-pro-002")

# ── GCP Clients ───────────────────────────────────────────────────────────────
db        = firestore.Client(project=PROJECT_ID)
bq        = bigquery.Client(project=PROJECT_ID)
publisher = pubsub_v1.PublisherClient()
topic_path= publisher.topic_path(PROJECT_ID, PUBSUB_CORRELATE)

vertexai.init(project=PROJECT_ID, location=REGION)
model = GenerativeModel(GEMINI_MODEL)

# ── Load All Artifacts ────────────────────────────────────────────────────────
def load_artifacts() -> list[dict]:
    docs = db.collection(FIRESTORE_ARTIFACTS).stream()
    artifacts = []
    for doc in docs:
        data = doc.to_dict()
        # Skip documents that haven't been fully processed yet (e.g. still in UPLOADED stage)
        if "raw_text" not in data or "filename" not in data:
            continue
            
        artifacts.append({
            "filename":      data["filename"],
            "document_type": data.get("document_type", "unknown"),
            "raw_text":      data["raw_text"][:3000]  # cap per doc to stay within token budget
        })
    return artifacts

# ── Build Gemini Prompt ───────────────────────────────────────────────────────
def build_prompt(artifacts: list[dict]) -> str:
    docs_block = ""
    for i, art in enumerate(artifacts, 1):
        docs_block += f"""
--- DOCUMENT {i}: {art['filename']} (type: {art['document_type']}) ---
{art['raw_text']}
"""

    return f"""You are a pricing intelligence analyst for an enterprise company.
Analyze the following {len(artifacts)} business documents and identify ALL meaningful relationships between them.

{docs_block}

Your task:
1. Find documents referencing the same company or customer
2. Find email threads that approved discounts appearing in contracts
3. Find pricing trends across CSV price lists and contracts
4. Identify decision chains: who approved what, when, and for which customer
5. Find any anomalies: unusual discounts, pricing inconsistencies, margin concerns

Output ONLY valid JSON. No prose, no markdown, no explanation outside the JSON.

{{
  "relationships": [
    {{
      "source_doc": "<exact filename>",
      "target_doc": "<exact filename>",
      "relationship_type": "<one of: discount_approved, price_referenced, same_customer, pricing_trend, compliance_link, anomaly_detected>",
      "confidence": <0.0 to 1.0>,
      "narrative": "<1-2 sentence explanation of this specific relationship>"
    }}
  ],
  "decisions": [
    {{
      "date": "<YYYY-MM-DD or best estimate>",
      "actor": "<person name or role e.g. CFO, VP Sales>",
      "rationale": "<why this decision was made>",
      "affected_segment": "<customer name or segment>",
      "impact_estimate": "<dollar amount or percentage if visible, else qualitative>",
      "source_doc": "<exact filename where this decision is evidenced>"
    }}
  ]
}}"""

# ── Parse Gemini Response ─────────────────────────────────────────────────────
def parse_gemini_response(response_text: str) -> dict:
    text = response_text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    return json.loads(text)

# ── Write to BigQuery ─────────────────────────────────────────────────────────
def write_relationships(relationships: list[dict]):
    if not relationships:
        print("  No relationships to write.")
        return

    table_id = f"{PROJECT_ID}.{BIGQUERY_DATASET}.relationships"
    rows = []
    for r in relationships:
        rows.append({
            "relationship_id":   str(uuid.uuid4()),
            "source_doc":        r.get("source_doc", ""),
            "target_doc":        r.get("target_doc", ""),
            "relationship_type": r.get("relationship_type", "unknown"),
            "confidence":        float(r.get("confidence", 0.0)),
            "narrative":         r.get("narrative", ""),
            "discovered_at":     datetime.now(timezone.utc).isoformat()
        })

    errors = bq.insert_rows_json(table_id, rows)
    if errors:
        print(f"  ❌ BigQuery relationship write errors: {errors}")
    else:
        print(f"  ✅ {len(rows)} relationships written to BigQuery")

def write_decisions(decisions: list[dict]):
    if not decisions:
        print("  No decisions to write.")
        return

    table_id = f"{PROJECT_ID}.{BIGQUERY_DATASET}.decisions"
    rows = []
    for d in decisions:
        rows.append({
            "decision_id":       str(uuid.uuid4()),
            "date":              d.get("date") or None,
            "actor":             d.get("actor", ""),
            "rationale":         d.get("rationale", ""),
            "affected_segment":  d.get("affected_segment", ""),
            "impact_estimate":   d.get("impact_estimate", ""),
            "source_doc":        d.get("source_doc", ""),
            "discovered_at":     datetime.now(timezone.utc).isoformat()
        })

    errors = bq.insert_rows_json(table_id, rows)
    if errors:
        print(f"  ❌ BigQuery decision write errors: {errors}")
    else:
        print(f"  ✅ {len(rows)} decisions written to BigQuery")

# ── Update Firestore Pipeline Stage ──────────────────────────────────────────
def update_pipeline_stage(filename: str):
    docs = db.collection(FIRESTORE_ARTIFACTS)\
              .where("filename", "==", filename)\
              .limit(1).get()
    for doc in docs:
        doc.reference.update({"pipeline_stage": "CORRELATED"})

# ── Publish Completion ────────────────────────────────────────────────────────
def publish_completion(relationship_count: int, decision_count: int):
    payload = json.dumps({
        "pipeline_stage":    "CORRELATED",
        "relationship_count": relationship_count,
        "decision_count":     decision_count,
        "timestamp":          datetime.now(timezone.utc).isoformat()
    }).encode()
    publisher.publish(topic_path, payload)
    print(f"  ✅ Published completion event to {PUBSUB_CORRELATE}")

# ── Main ──────────────────────────────────────────────────────────────────────
def correlate():
    print(f"\n{'='*60}")
    print(f"  DDA CORRELATE AGENT — Enterprise Build")
    print(f"  Model: {GEMINI_MODEL}")
    print(f"{'='*60}\n")

    # Load
    print("Step 1: Loading artifacts from Firestore...")
    artifacts = load_artifacts()
    print(f"  ✅ Loaded {len(artifacts)} artifacts\n")

    # Prompt
    print("Step 2: Building Gemini prompt...")
    prompt = build_prompt(artifacts)
    print(f"  ✅ Prompt built ({len(prompt)} chars | ~{len(prompt)//4} tokens)\n")

    # Gemini call
    print(f"Step 3: Calling {GEMINI_MODEL} for cross-document correlation...")
    response = model.generate_content(prompt)
    raw_text = response.text
    print(f"  ✅ Response received ({len(raw_text)} chars)\n")

    # Parse
    print("Step 4: Parsing Gemini response...")
    try:
        parsed = parse_gemini_response(raw_text)
        relationships = parsed.get("relationships", [])
        decisions     = parsed.get("decisions", [])
        print(f"  ✅ Parsed: {len(relationships)} relationships, {len(decisions)} decisions\n")
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse failed: {e}")
        print(f"  Raw response:\n{raw_text[:500]}")
        return

    # Preview
    print("Step 5: Relationship preview:")
    for r in relationships[:3]:
        print(f"  [{r.get('relationship_type')}] {r.get('source_doc')} ↔ {r.get('target_doc')} (confidence: {r.get('confidence')})")
        print(f"    {r.get('narrative')}")
    if len(relationships) > 3:
        print(f"  ... and {len(relationships)-3} more\n")

    print("\nStep 6: Writing to BigQuery...")
    write_relationships(relationships)
    write_decisions(decisions)

    # Update Firestore
    print("\nStep 7: Updating pipeline stage in Firestore...")
    for art in artifacts:
        update_pipeline_stage(art["filename"])
    print(f"  ✅ {len(artifacts)} artifacts marked CORRELATED\n")

    # Publish
    print("Step 8: Publishing completion event...")
    publish_completion(len(relationships), len(decisions))

    print(f"\n{'='*60}")
    print(f"  CORRELATE COMPLETE")
    print(f"  Relationships discovered: {len(relationships)}")
    print(f"  Decisions extracted:      {len(decisions)}")
    print(f"{'='*60}\n")

    return {"relationships": relationships, "decisions": decisions}

if __name__ == "__main__":
    correlate()
