#!/bin/bash
# ============================================================
# DDA — Stop Services Script
# Deletes Cloud Run services to stop billing.
# Data is SAFE — Firestore, BigQuery, Vector Search untouched.
# Redeploy anytime: bash deploy_cloudrun.sh
#
# Usage: bash stop_services.sh
# Usage (skip confirmation): bash stop_services.sh --force
# ============================================================

PROJECT_ID="the-orchestrators"
REGION="us-central1"

SERVICES=(
  "dda-ingest-service"
  "dda-correlate-service"
  "dda-enrich-service"
  "dda-query-service"
  "dda-ui-service"
)

PUBSUB_SUBS=(
  "dda-ingest-complete-sub"
  "dda-correlate-complete-sub"
)

echo "================================================"
echo "DDA — Stop Services"
echo "Project: $PROJECT_ID | Region: $REGION"
echo "================================================"
echo ""
echo "This will DELETE the following Cloud Run services:"
for SVC in "${SERVICES[@]}"; do
  echo "  - $SVC"
done
echo ""
echo "Your DATA is safe:"
echo "  ✅ Firestore (dda_artifacts, dda_query_log) — untouched"
echo "  ✅ BigQuery (dda_knowledge_graph) — untouched"
echo "  ✅ Vertex AI Vector Search index — untouched"
echo "  ✅ Docker images in Artifact Registry — untouched"
echo "  ✅ Pub/Sub topics — untouched"
echo ""
echo "Redeploy anytime with: bash deploy_cloudrun.sh"
echo ""

# Confirmation gate
if [[ "$1" != "--force" ]]; then
  read -p "Proceed? (y/n): " CONFIRM
  if [[ "$CONFIRM" != "y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

# ── Delete Cloud Run services ────────────────────────────────
echo ""
echo "▶ Deleting Cloud Run services..."

for SVC in "${SERVICES[@]}"; do
  echo -n "  Deleting $SVC... "
  gcloud run services delete $SVC \
    --project=$PROJECT_ID \
    --region=$REGION \
    --quiet 2>/dev/null \
    && echo "✅ deleted" \
    || echo "⚠ not found (already deleted or never deployed)"
done

# ── Delete Pub/Sub subscriptions ────────────────────────────
echo ""
echo "▶ Deleting Pub/Sub push subscriptions..."

for SUB in "${PUBSUB_SUBS[@]}"; do
  echo -n "  Deleting $SUB... "
  gcloud pubsub subscriptions delete $SUB \
    --project=$PROJECT_ID \
    --quiet 2>/dev/null \
    && echo "✅ deleted" \
    || echo "⚠ not found"
done

# ── What's still running (costs money) ──────────────────────
echo ""
echo "▶ Checking remaining billable resources..."

echo ""
echo "  Artifact Registry images (small storage cost ~cents/month):"
gcloud artifacts docker images list \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/dda" \
  --project=$PROJECT_ID \
  --format="table(IMAGE,DIGEST)" 2>/dev/null | head -10 \
  || echo "  (none or registry empty)"

echo ""
echo "  Vertex AI Vector Search index (check GCP console for cost):"
echo "  projects/201529476752/locations/us-central1/indexEndpoints/138655013332320256"

echo ""
echo "  BigQuery (no ongoing cost — pay per query only)"
echo "  Firestore (minimal cost — ~\$0.06/100K reads)"
echo "  Pub/Sub topics (no cost when idle)"

# ── Clear saved URLs ─────────────────────────────────────────
if [ -f ~/dda-project/.cloudrun_urls ]; then
  rm ~/dda-project/.cloudrun_urls
  echo ""
  echo "  Cleared ~/dda-project/.cloudrun_urls"
fi

echo ""
echo "================================================"
echo "✅ Services stopped"
echo ""
echo "Estimated ongoing costs while stopped:"
echo "  Cloud Run:       \$0.00 (deleted)"
echo "  Firestore:       ~\$0.01/day (idle reads)"
echo "  BigQuery:        \$0.00 (no queries)"
echo "  Vector Search:   check GCP console"
echo "  Artifact Registry: ~\$0.01/day (image storage)"
echo ""
echo "To redeploy: bash ~/dda-project/deploy_cloudrun.sh"
echo "================================================"