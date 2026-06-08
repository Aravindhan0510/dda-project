#!/bin/bash
# DDA — BigQuery Schema Setup
# Run ONCE before deploying CORRELATE service
# Usage: bash setup_bigquery.sh

PROJECT_ID="the-orchestrators"
DATASET="dda_knowledge_graph"
REGION="US"

echo "▶ Creating BigQuery dataset: ${DATASET}"
bq --location=$REGION mk --dataset --quiet "${PROJECT_ID}:${DATASET}" 2>/dev/null || \
  echo "  Dataset already exists — OK"

echo "▶ Creating table: relationships"
bq mk --table --quiet \
  "${PROJECT_ID}:${DATASET}.relationships" \
  "relationship_id:STRING,source_doc:STRING,target_doc:STRING,relationship_type:STRING,confidence:FLOAT64,narrative:STRING,discovered_at:TIMESTAMP" \
  2>/dev/null || echo "  Table already exists — OK"

echo "▶ Creating table: decisions"
bq mk --table --quiet \
  "${PROJECT_ID}:${DATASET}.decisions" \
  "decision_id:STRING,date:DATE,actor:STRING,rationale:STRING,affected_segment:STRING,impact_estimate:STRING,source_doc:STRING,discovered_at:TIMESTAMP" \
  2>/dev/null || echo "  Table already exists — OK"

echo "▶ Creating table: query_analytics"
bq mk --table --quiet \
  "${PROJECT_ID}:${DATASET}.query_analytics" \
  "trace_id:STRING,user_id:STRING,query:STRING,overall_confidence:FLOAT64,query_latency_ms:INTEGER,queried_at:TIMESTAMP" \
  2>/dev/null || echo "  Table already exists — OK"

echo "✅ BigQuery setup complete"
echo ""
echo "Verify tables:"
bq ls "${PROJECT_ID}:${DATASET}"