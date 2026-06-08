#!/bin/bash
# ============================================================
# DDA — Cloud Run Deployment Script (ALL SERVICES + UI)
# Project: the-orchestrators | Region: us-central1
# Run from: ~/dda-project/
# Usage: bash deploy_cloudrun.sh
#
# Deploys:
#   1. dda-ingest-service
#   2. dda-correlate-service
#   3. dda-enrich-service
#   4. dda-query-service
#   5. dda-ui-service  ← React frontend (new)
# ============================================================
set -e

PROJECT_ID="${1:-the-orchestrators}"
REGION="${2:-us-central1}"
REPO="dda"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# ── Infra constants ───────────────────────────────────────────
VS_INDEX_ENDPOINT="${VS_INDEX_ENDPOINT_OVERRIDE:-projects/201529476752/locations/us-central1/indexEndpoints/138655013332320256}"
VS_DEPLOYED_INDEX="dda_deployed_index"
DOC_AI_PROCESSOR="${DOC_AI_PROCESSOR_OVERRIDE:-projects/201529476752/locations/us/processors/c7e0f9cb0fe97115}"
BQ_DATASET="dda_knowledge_graph"

# ── Load API key from .env ────────────────────────────────────
if [ -f "$(dirname "$0")/.env" ]; then
  GEMINI_API_KEY=$(grep GEMINI_API_KEY "$(dirname "$0")/.env" | cut -d'=' -f2 | tr -d '[:space:]')
else
  echo "❌ .env not found at $(dirname "$0")/.env"
  exit 1
fi

if [ -z "$GEMINI_API_KEY" ]; then
  echo "❌ GEMINI_API_KEY is empty in .env"
  exit 1
fi

echo "================================================"
echo "DDA Cloud Run Deployment — $(date)"
echo "Project: $PROJECT_ID | Region: $REGION"
echo "API Key: ${GEMINI_API_KEY:0:8}..."
echo "================================================"

# ── Step 0: Prerequisites ─────────────────────────────────────
echo ""
echo "▶ Step 0: Setting project + enabling APIs..."

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  pubsub.googleapis.com \
  --project=$PROJECT_ID \
  --quiet

gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID \
  --quiet 2>/dev/null || echo "  Repo already exists — OK"

gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# ── Step 1: Pub/Sub topics ────────────────────────────────────
echo ""
echo "▶ Step 1: Creating Pub/Sub topics..."

for TOPIC in dda-ingest-trigger dda-correlate-trigger dda-enrich-trigger dda-query-ready dda-hitl-queue; do
  gcloud pubsub topics create $TOPIC \
    --project=$PROJECT_ID \
    --quiet 2>/dev/null || echo "  Topic $TOPIC already exists — OK"
done

# ── Step 2: Write agent service files + Dockerfiles ──────────
echo ""
echo "▶ Step 2: Writing agent service files + Dockerfiles..."

COMMON_ENV="GCP_PROJECT_ID=${PROJECT_ID},\
GCP_REGION=${REGION},\
BIGQUERY_DATASET=${BQ_DATASET},\
GEMINI_MODEL=gemini-2.5-flash,\
GEMINI_API_KEY=${GEMINI_API_KEY},\
VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT=${VS_INDEX_ENDPOINT},\
VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID=${VS_DEPLOYED_INDEX},\
DOCUMENT_AI_PROCESSOR_ID=${DOC_AI_PROCESSOR},\
CONFIDENCE_THRESHOLD=0.75,\
VECTOR_TOP_K=5"

# ── Step 3: Build + Push agent images ────────────────────────
echo ""
echo "▶ Step 3: Building and pushing agent Docker images..."

for SVC in ingest correlate enrich query upload; do
  echo ""
  echo "  Building: dda-${SVC}-service..."
  docker build --no-cache \
    -t "${REGISTRY}/dda-${SVC}-service:latest" \
    "$(dirname "$0")/agents/${SVC}/" \
    && echo "  ✅ Built" || { echo "  ❌ Build failed: ${SVC}"; exit 1; }
  docker push "${REGISTRY}/dda-${SVC}-service:latest" \
    && echo "  ✅ Pushed" || { echo "  ❌ Push failed: ${SVC}"; exit 1; }
done

# ── Step 4: Deploy agent Cloud Run services ───────────────────
echo ""
echo "▶ Step 4: Deploying agent Cloud Run services..."

echo "  Deploying: dda-ingest-service"
gcloud run deploy dda-ingest-service \
  --project=$PROJECT_ID \
  --image="${REGISTRY}/dda-ingest-service:latest" \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=1Gi --cpu=1 --timeout=300 \
  --set-env-vars="${COMMON_ENV},\
FIRESTORE_ARTIFACTS=dda_artifacts,\
PUBSUB_INGEST_LISTEN_TOPIC=projects/${PROJECT_ID}/topics/dda-ingest-trigger,\
PUBSUB_INGEST_TO_CORRELATE_TOPIC=projects/${PROJECT_ID}/topics/dda-correlate-trigger" \
  --quiet && echo "  ✅ dda-ingest-service deployed" || echo "  ❌ dda-ingest-service FAILED"

echo "  Deploying: dda-correlate-service"
gcloud run deploy dda-correlate-service \
  --project=$PROJECT_ID \
  --image="${REGISTRY}/dda-correlate-service:latest" \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=2Gi --cpu=2 --timeout=540 \
  --set-env-vars="${COMMON_ENV},\
FIRESTORE_ARTIFACTS=dda_artifacts,\
PUBSUB_CORRELATE_LISTEN_TOPIC=projects/${PROJECT_ID}/topics/dda-correlate-trigger,\
PUBSUB_CORRELATE_TO_ENRICH_TOPIC=projects/${PROJECT_ID}/topics/dda-enrich-trigger" \
  --quiet && echo "  ✅ dda-correlate-service deployed" || echo "  ❌ dda-correlate-service FAILED"

echo "  Deploying: dda-enrich-service"
gcloud run deploy dda-enrich-service \
  --project=$PROJECT_ID \
  --image="${REGISTRY}/dda-enrich-service:latest" \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=1Gi --cpu=1 --timeout=300 \
  --set-env-vars="${COMMON_ENV},\
FIRESTORE_ARTIFACTS=dda_artifacts,\
PUBSUB_ENRICH_LISTEN_TOPIC=projects/${PROJECT_ID}/topics/dda-enrich-trigger,\
PUBSUB_ENRICH_TO_QUERY_READY_TOPIC=projects/${PROJECT_ID}/topics/dda-query-ready" \
  --quiet && echo "  ✅ dda-enrich-service deployed" || echo "  ❌ dda-enrich-service FAILED"

echo "  Deploying: dda-query-service"
gcloud run deploy dda-query-service \
  --project=$PROJECT_ID \
  --image="${REGISTRY}/dda-query-service:latest" \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=2Gi --cpu=2 --timeout=120 \
  --set-env-vars="${COMMON_ENV},\
FIRESTORE_ARTIFACTS=dda_artifacts,\
FIRESTORE_QUERY_LOG=dda_query_log" \
  --quiet && echo "  ✅ dda-query-service deployed" || echo "  ❌ dda-query-service FAILED"

echo "  Deploying: dda-upload-service"
gcloud run deploy dda-upload-service \
  --project=$PROJECT_ID \
  --image="${REGISTRY}/dda-upload-service:latest" \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=2Gi --cpu=2 --timeout=120 \
  --set-env-vars="${COMMON_ENV},\
FIRESTORE_ARTIFACTS=dda_artifacts,\
PUBSUB_UPLOAD_TO_INGEST_TOPIC=projects/${PROJECT_ID}/topics/dda-ingest-trigger" \
  --quiet && echo "  ✅ dda-upload-service deployed" || echo "  ❌ dda-upload-service FAILED"

# ── Step 5: Wire Pub/Sub subscriptions ───────────────────────
echo ""
echo "▶ Step 5: Wiring Pub/Sub push subscriptions..."

CORRELATE_URL=$(gcloud run services describe dda-correlate-service \
  --project=$PROJECT_ID --region=$REGION --format="value(status.url)")
ENRICH_URL=$(gcloud run services describe dda-enrich-service \
  --project=$PROJECT_ID --region=$REGION --format="value(status.url)")
QUERY_URL=$(gcloud run services describe dda-query-service \
  --project=$PROJECT_ID --region=$REGION --format="value(status.url)")
INGEST_URL=$(gcloud run services describe dda-ingest-service \
  --project=$PROJECT_ID --region=$REGION --format="value(status.url)")
UPLOAD_URL=$(gcloud run services describe dda-upload-service \
  --project=$PROJECT_ID --region=$REGION --format="value(status.url)")

gcloud pubsub subscriptions create dda-ingest-trigger-sub \
  --project=$PROJECT_ID \
  --topic=dda-ingest-trigger \
  --push-endpoint="${INGEST_URL}/ingest/trigger" \
  --ack-deadline=600 \
  --quiet 2>/dev/null || \
gcloud pubsub subscriptions modify-push-config dda-ingest-trigger-sub \
  --project=$PROJECT_ID \
  --push-endpoint="${INGEST_URL}/ingest/trigger" --quiet
echo "  ✅ upload → ingest wired"

gcloud pubsub subscriptions create dda-correlate-trigger-sub \
  --project=$PROJECT_ID \
  --topic=dda-correlate-trigger \
  --push-endpoint="${CORRELATE_URL}/correlate/trigger" \
  --ack-deadline=600 \
  --quiet 2>/dev/null || \
gcloud pubsub subscriptions modify-push-config dda-correlate-trigger-sub \
  --project=$PROJECT_ID \
  --push-endpoint="${CORRELATE_URL}/correlate/trigger" --quiet
echo "  ✅ ingest → correlate wired"

gcloud pubsub subscriptions create dda-enrich-trigger-sub \
  --project=$PROJECT_ID \
  --topic=dda-enrich-trigger \
  --push-endpoint="${ENRICH_URL}/enrich/trigger" \
  --ack-deadline=600 \
  --quiet 2>/dev/null || \
gcloud pubsub subscriptions modify-push-config dda-enrich-trigger-sub \
  --project=$PROJECT_ID \
  --push-endpoint="${ENRICH_URL}/enrich/trigger" --quiet
echo "  ✅ correlate → enrich wired"

# ═══════════════════════════════════════════════════════════════
# ── Step 6: Deploy DDA UI (React → Docker → Cloud Run)
# ═══════════════════════════════════════════════════════════════
echo ""
echo "▶ Step 6: Building DDA UI React application..."

UI_DIR="$(dirname "$0")/dda-ui"

# ── 6a: Docker build + push ───────────────────────────────────
echo ""
echo "  Building UI Docker image (React build takes ~2 min)..."
docker build --no-cache -t dda-ui \
  -t "${REGISTRY}/dda-ui-service:latest" \
  "${UI_DIR}/" \
  && echo "  ✅ UI image built" || { echo "  ❌ UI build failed"; exit 1; }

docker push "${REGISTRY}/dda-ui-service:latest" \
  && echo "  ✅ UI image pushed" || { echo "  ❌ UI push failed"; exit 1; }

# ── 6b: Deploy UI to Cloud Run ────────────────────────────────
echo ""
echo "  Deploying: dda-ui-service..."
gcloud run deploy dda-ui-service \
  --project=$PROJECT_ID \
  --image="${REGISTRY}/dda-ui-service:latest" \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --port=8080 \
  --quiet && echo "  ✅ dda-ui-service deployed" || echo "  ❌ dda-ui-service FAILED"

UI_URL=$(gcloud run services describe dda-ui-service \
  --project=$PROJECT_ID --region=$REGION \
  --format="value(status.url)" 2>/dev/null)

# ── 6c: Smoke test UI ─────────────────────────────────────────
echo ""
echo "  Smoke testing UI..."
HTTP_STATUS=$(curl -o /dev/null -sf -w "%{http_code}" "${UI_URL}" 2>/dev/null || echo "000")
if [ "$HTTP_STATUS" = "200" ]; then
  echo "  ✅ UI reachable — HTTP $HTTP_STATUS"
else
  echo "  ⚠ UI returned HTTP $HTTP_STATUS — check Cloud Run logs"
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "================================================"
echo "✅ DDA Full Deployment Complete"
echo "================================================"
echo ""
echo "Agent Service URLs:"
echo "  INGEST:    ${INGEST_URL}"
echo "  CORRELATE: ${CORRELATE_URL}"
echo "  ENRICH:    ${ENRICH_URL}"
echo "  QUERY API: ${QUERY_URL}"
echo "  UPLOAD:    ${UPLOAD_URL}"
echo ""
echo "UI:"
echo "  🌐 ${UI_URL}"
echo ""
echo "API endpoints:"
echo "  POST ${QUERY_URL}/v1/query"
echo "  GET  ${QUERY_URL}/v1/status"
echo "  GET  ${QUERY_URL}/v1/artifacts"
echo ""
echo "To stop all services (save billing):"
echo "  bash ~/dda-project/stop_services.sh"
echo ""

# Save all URLs
cat > ~/dda-project/.cloudrun_urls << URLEOF
QUERY_API_URL=${QUERY_URL}
CORRELATE_URL=${CORRELATE_URL}
ENRICH_URL=${ENRICH_URL}
INGEST_URL=${INGEST_URL}
UPLOAD_URL=${UPLOAD_URL}
UI_URL=${UI_URL}
URLEOF
echo "URLs saved to ~/dda-project/.cloudrun_urls"
echo "================================================"