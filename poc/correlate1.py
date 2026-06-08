"""
DDA — CORRELATE Agent
Reads all artifacts from Firestore, feeds to Gemini in one batch,
extracts cross-document relationships and pricing decisions,
persists to dda_relationships and dda_decisions collections.
"""

import os
import json
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# Use the established gcp_client pattern
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gcp_client import get_gemini_client, get_all_artifacts, save_relationship, save_decision

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")


# ── Step 1: Build context bundle ─────────────────────────────────────────────

def build_context_bundle(artifacts: list[dict]) -> str:
    """Compact representation of all artifacts for Gemini context."""
    lines = []
    for a in artifacts:
        lines.append(
            f"=== DOCUMENT ===\n"
            f"ID: {a['artifact_id']}\n"
            f"File: {a['filename']}\n"
            f"Type: {a['document_type']}\n"
            f"Text:\n{a['raw_text'][:3000]}\n"  # cap per doc; 12 docs * 3K = 36K tokens — well within limit
        )
    return "\n".join(lines)


# ── Step 2: Construct the CORRELATE prompt ───────────────────────────────────

CORRELATE_PROMPT_TEMPLATE = """
You are a cross-document relationship extraction engine for enterprise pricing intelligence.

Below are {doc_count} enterprise documents. Analyze them and extract:
1. Relationships between documents (which docs reference the same companies, contracts, discounts, or pricing decisions)
2. Pricing decision events (who decided what discount/price, when, for which customer/segment, and what was the financial impact)

OUTPUT FORMAT: Return ONLY a valid JSON object. No prose, no markdown, no code fences.

{{
  "relationships": [
    {{
      "source_doc": "<filename of source document>",
      "target_doc": "<filename of related document>",
      "relationship_type": "<one of: discount_approved | contract_references_email | pricing_trend | company_mention | approval_chain | competitive_reference>",
      "confidence": <float 0.0–1.0>,
      "narrative": "<1–2 sentence explanation of why these documents are related>"
    }}
  ],
  "decisions": [
    {{
      "decision_id": "<source_doc>_decision_<sequence>",
      "source_doc": "<filename>",
      "actor": "<person or role who made the decision, e.g. CFO, Sales Director>",
      "decision_date": "<date string if extractable, else null>",
      "customer_segment": "<customer name or segment if identifiable>",
      "decision_type": "<one of: discount_granted | price_set | price_change | approval_given | policy_exception>",
      "discount_percent": <float or null>,
      "rationale": "<why was this decision made>",
      "revenue_impact": "<estimated financial impact if mentioned, else null>"
    }}
  ]
}}

DOCUMENTS:
{context_bundle}
"""


# ── Step 3: Parse Gemini response ────────────────────────────────────────────

def extract_json(raw_response: str) -> dict:
    """Strip markdown fences if Gemini adds them, then parse JSON."""
    text = raw_response.strip()
    # Remove ```json ... ``` or ``` ... ``` wrappers
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ── Step 4: Persist to Firestore ─────────────────────────────────────────────

def persist_relationships(relationships: list[dict]) -> int:
    count = 0
    for rel in relationships:
        rel["discovered_at"] = datetime.now(timezone.utc).isoformat()
        rel["pipeline_stage"] = "CORRELATED"
        save_relationship(rel)
        count += 1
    return count


def persist_decisions(decisions: list[dict]) -> int:
    count = 0
    for dec in decisions:
        dec["discovered_at"] = datetime.now(timezone.utc).isoformat()
        dec["pipeline_stage"] = "CORRELATED"
        save_decision(dec)
        count += 1
    return count


# ── Main ─────────────────────────────────────────────────────────────────────

def run_correlate_agent():
    print("=" * 60)
    print("DDA — CORRELATE Agent Starting")
    print("=" * 60)

    # Step 1: Load artifacts
    print("\n[1/4] Loading artifacts from Firestore...")
    artifacts = get_all_artifacts()
    print(f"      Loaded {len(artifacts)} artifacts")
    if not artifacts:
        print("ERROR: No artifacts found. Run ingest.py first.")
        return

    # Step 2: Build context + prompt
    print("\n[2/4] Building Gemini context bundle...")
    context_bundle = build_context_bundle(artifacts)
    prompt = CORRELATE_PROMPT_TEMPLATE.format(
        doc_count=len(artifacts),
        context_bundle=context_bundle
    )
    print(f"      Context size: ~{len(prompt.split()):,} words")

    # Step 3: Call Gemini
    print("\n[3/4] Calling Gemini for cross-document correlation...")
    client = get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )
    raw_text = response.text
    print(f"      Response received ({len(raw_text)} chars)")

    # Parse
    try:
        result = extract_json(raw_text)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON parse failed — {e}")
        print("Raw response (first 500 chars):", raw_text[:500])
        return

    relationships = result.get("relationships", [])
    decisions = result.get("decisions", [])
    print(f"      Extracted {len(relationships)} relationships, {len(decisions)} decisions")

    # Step 4: Persist
    print("\n[4/4] Persisting to Firestore...")
    rel_count = persist_relationships(relationships)
    dec_count = persist_decisions(decisions)

    # Summary
    print("\n" + "=" * 60)
    print("CORRELATE Agent Complete")
    print(f"  Relationships saved : {rel_count}")
    print(f"  Decisions saved     : {dec_count}")
    print("  Collections updated : dda_relationships, dda_decisions")
    print("  Next step           : python agents/enrich.py")
    print("=" * 60)


if __name__ == "__main__":
    run_correlate_agent()