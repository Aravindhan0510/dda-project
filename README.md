# Dark Data Archaeologist (DDA)

**Project:** the-orchestrators | **Region:** us-central1

An enterprise pricing intelligence & governance platform that extracts, correlates, and queries pricing decisions, discount approvals, and revenue strategies from unstructured business documents using AI-powered agents deployed on Google Cloud Run.

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐      ┌──────────────┐
│   UPLOAD     │────▶│   INGEST     │────▶│  CORRELATE   │────▶│   ENRICH     │
│  (FastAPI)   │     │  (FastAPI)   │     │  (FastAPI)   │      │  (FastAPI)   │
└──────────────┘     └──────────────┘     └──────────────┘      └──────────────┘
       │                                                               │
       ▼                                                               ▼
┌──────────────┐                                              ┌──────────────┐
│     GCS      │                                              │    QUERY     │
│  Raw Staging │                                              │  (FastAPI)   │
└──────────────┘                                              └──────────────┘
                                                                       │
                                                                       ▼
                                                              ┌──────────────┐
                                                              │   React UI   │
                                                              │   (Nginx)    │
                                                              └──────────────┘
```

### Pipeline Stages

```
UPLOADED → INGESTED → CORRELATED → ENRICHED → QUERY-READY
```

### Event Flow (Pub/Sub)

```
File Upload → dda-ingest-trigger → INGEST → dda-correlate-trigger → CORRELATE → dda-enrich-trigger → ENRICH → dda-query-ready
```

---

## Services

| Service | Path | Function | Memory | CPU | Timeout |
|---------|------|----------|--------|-----|---------|
| Upload | `agents/upload/` | File upload → GCS + Firestore + Pub/Sub trigger | 2 GB | 2 | 120s |
| Ingest | `agents/ingest/` | Text extraction (PDF/DOCX/CSV) via Document AI | 1 GB | 1 | 300s |
| Correlate | `agents/correlate/` | Multi-document relationship extraction via Gemini | 2 GB | 2 | 540s |
| Enrich | `agents/enrich/` | Embedding generation + NER + domain tagging | 1 GB | 1 | 300s |
| Query | `agents/query/` | Natural language Q&A with source citations | 2 GB | 2 | 120s |
| UI | `dda-ui/` | React dashboard served via Nginx | 512 MB | 1 | — |

---

## Data Storage

| Store | Purpose |
|-------|---------|
| **Firestore** (`dda_artifacts`) | Document metadata, pipeline stages, entities, embeddings |
| **Firestore** (`dda_query_log`) | Query traces, sessions, latency |
| **BigQuery** (`dda_knowledge_graph.relationships`) | Cross-document relationships |
| **BigQuery** (`dda_knowledge_graph.decisions`) | Extracted decisions with actors, dates, rationale |
| **BigQuery** (`dda_knowledge_graph.query_analytics`) | Query performance metrics |
| **Vertex AI Vector Search** | Document embeddings for semantic retrieval |
| **GCS** (`dda-raw-staging`) | Raw uploaded files |

---

## Query Service API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/query` | POST | Natural language question answering |
| `/v1/relationships` | GET | Fetch relationships & decisions from BigQuery |
| `/v1/artifacts` | GET | List all processed documents |
| `/v1/artifacts/{id}` | GET | Get specific artifact details |
| `/v1/cache/refresh` | POST | Reload artifact cache from Firestore |
| `/v1/upload` | POST | Upload file (PDF/DOCX/CSV) |
| `/health` | GET | Service health check |

---

## UI

Dark-themed React dashboard (`dda-ui/`) with:
- Natural language query interface with 10 pre-built demo queries
- Answer cards with citations, confidence scores, and latency metrics
- Artifacts browser and relationship explorer
- Analytics dashboard with pipeline progress tracking
- Deployed via Nginx on port 8080 with SPA routing

---

## Deployment

### Pre-Flight

```bash
gcloud config get-value project      # must be: the-orchestrators
echo $GOOGLE_CLOUD_PROJECT           # should be: the-orchestrators
```

### Step 1 — BigQuery Setup (run once)

```bash
bash setup_bigquery.sh
```

### Step 2 — Deploy All Services

```bash
bash deploy_cloudrun.sh
```

This script:
1. Enables required GCP APIs
2. Creates Artifact Registry repo (`dda`)
3. Creates Pub/Sub topics & subscriptions
4. Builds & pushes Docker images for all 5 agents + UI
5. Deploys 6 Cloud Run services with environment variables
6. Wires Pub/Sub push subscriptions
7. Smoke tests all `/health` endpoints
8. Saves all URLs to `.cloudrun_urls`

### Step 3 — Verify

```bash
source ~/dda-project/.cloudrun_urls

curl -s "${QUERY_API_URL}/v1/status" | python3 -m json.tool

curl -s -X POST "${QUERY_API_URL}/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo","session_id":"test","query":"What pricing strategies drove margin decline 2016-2018?"}' \
  | python3 -m json.tool
```

### Stop Services (save billing)

```bash
bash stop_services.sh
```

This preserves Firestore, BigQuery, Vector Search, Docker images, and Pub/Sub topics. Redeploy with `deploy_cloudrun.sh`.

---

## Environment Variables

```bash
GCP_PROJECT_ID=the-orchestrators
GCP_REGION=us-central1
BIGQUERY_DATASET=dda_knowledge_graph
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=<from .env>
VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT=<pre-configured>
DOCUMENT_AI_PROCESSOR_ID=<optional>
CONFIDENCE_THRESHOLD=0.75
VECTOR_TOP_K=5
```

---

## Service URLs (post-deployment)

Saved in `.cloudrun_urls`:
```
https://dda-upload-service-<hash>-uc.a.run.app
https://dda-ingest-service-<hash>-uc.a.run.app
https://dda-correlate-service-<hash>-uc.a.run.app
https://dda-enrich-service-<hash>-uc.a.run.app
https://dda-query-service-<hash>-uc.a.run.app
https://dda-ui-service-<hash>-uc.a.run.app
```

---

## Local Development (POC)

Standalone agent scripts in `poc/` for local testing without Cloud Run:
- `ingest1.py` — Local file ingestion
- `correlate1.py` — Local correlation
- `enrich1.py` — Local enrichment
- `query1.py` — Local query interface

---

## Troubleshooting

| Symptom | Command | Fix |
|---|---|---|
| Build fails: permission denied | `gcloud auth login` | Re-authenticate |
| Push fails: repo not found | Check Artifact Registry in console | Repo creation failed — run step manually |
| Deploy fails: API not enabled | `gcloud services enable run.googleapis.com` | Enable missing API |
| Service unhealthy | `gcloud run logs read dda-query-service --region=us-central1 --limit=50` | Check logs |
| Vector Search error | Set `VS_INDEX_ENDPOINT=""` in deploy script | Skip VS, use Firestore-only retrieval |
| BigQuery write error | `bq show the-orchestrators:dda_knowledge_graph.relationships` | Check table exists |
| Correlate returns 0 relationships | Check Gemini model quota | Retry with smaller batch |