# 🏛️ Dark Data Archaeologist (DDA)

> *GCP-native 5-agent AI pipeline that transforms 20 years of enterprise dark data into a queryable knowledge graph — targeting **$3–5M in recoverable pricing intelligence**.*

Built for the **Gemini CLI Buildathon 2026** · **Project:** `the-orchestrators` · **Region:** `us-central1`

---

## What Is This?

Enterprise organizations accumulate decades of pricing decisions, discount approvals, contract negotiations, and revenue strategies inside unstructured documents — PDFs, emails, DOCX files, audio recordings — that no one can query. This is **dark data**: valuable, inaccessible, and expensive to ignore.

**DDA** deploys a 5-agent orchestration pipeline on Google Cloud Run that ingests this unstructured data, extracts relationships and decisions using Gemini 2.5 Flash, stores them in a hybrid knowledge graph (Vertex AI Vector Search + BigQuery), and exposes a natural language Q&A interface for analysts to recover that buried intelligence.

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   UPLOAD     │────▶│   INGEST     │────▶│  CORRELATE   │────▶│   ENRICH     │
│  (FastAPI)   │     │  (FastAPI)   │     │  (FastAPI)   │     │  (FastAPI)   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
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
File Upload
    └─▶ dda-ingest-trigger
            └─▶ INGEST (text extraction)
                    └─▶ dda-correlate-trigger
                                └─▶ CORRELATE (relationship extraction)
                                        └─▶ dda-enrich-trigger
                                                    └─▶ ENRICH (embeddings + NER)
                                                                └─▶ dda-query-ready
```

---

## Services

| Service | Path | Function | Memory | CPU | Timeout |
|---------|------|----------|--------|-----|---------|
| **Upload** | `agents/upload/` | File upload → GCS + Firestore + Pub/Sub trigger | 2 GB | 2 | 120s |
| **Ingest** | `agents/ingest/` | Text extraction (PDF / DOCX / CSV) via Document AI | 1 GB | 1 | 300s |
| **Correlate** | `agents/correlate/` | Multi-document relationship extraction via Gemini | 2 GB | 2 | 540s |
| **Enrich** | `agents/enrich/` | Embedding generation + NER + domain tagging | 1 GB | 1 | 300s |
| **Query** | `agents/query/` | Natural language Q&A with source citations | 2 GB | 2 | 120s |
| **UI** | `dda-ui/` | React dashboard served via Nginx | 512 MB | 1 | — |

---

## Data Storage

| Store | Purpose |
|-------|---------|
| **Firestore** `dda_artifacts` | Document metadata, pipeline stages, entities, embeddings |
| **Firestore** `dda_query_log` | Query traces, sessions, latency |
| **BigQuery** `dda_knowledge_graph.relationships` | Cross-document relationships |
| **BigQuery** `dda_knowledge_graph.decisions` | Extracted decisions with actors, dates, rationale |
| **BigQuery** `dda_knowledge_graph.query_analytics` | Query performance metrics |
| **Vertex AI Vector Search** | Document embeddings for semantic retrieval |
| **GCS** `dda-raw-staging` | Raw uploaded files |

---

## Key Design Decisions

**Hybrid RAG retrieval** — Vertex AI Vector Search handles semantic recall (similarity-based); BigQuery handles relationship-aware graph traversal. Gemini 2.5 Flash synthesizes the final answer from both.

**Cost-optimisation routing** — A pre-processing layer checks whether a document is directly parseable before invoking Document AI, bypassing unnecessary API calls for clean text files.

**Production-grade reliability** — Confidence scoring thresholds (default: `0.75`), Human-in-the-Loop (HITL) review gates for low-confidence extractions, and immutable audit trails persisted in Cloud Firestore.

---

## Query API

Base URL: `https://dda-query-service-<hash>-uc.a.run.app`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/query` | `POST` | Natural language question answering |
| `/v1/relationships` | `GET` | Fetch relationships & decisions from BigQuery |
| `/v1/artifacts` | `GET` | List all processed documents |
| `/v1/artifacts/{id}` | `GET` | Get specific artifact details |
| `/v1/cache/refresh` | `POST` | Reload artifact cache from Firestore |
| `/v1/upload` | `POST` | Upload file (PDF / DOCX / CSV) |
| `/health` | `GET` | Service health check |

### Example Query

```bash
curl -s -X POST "${QUERY_API_URL}/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo",
    "session_id": "test",
    "query": "What pricing strategies drove margin decline 2016–2018?"
  }' | python3 -m json.tool
```

---

## UI

Dark-themed React dashboard (`dda-ui/`) deployed via Nginx on port 8080:

- Natural language query interface with 10 pre-built demo queries
- Answer cards with citations, confidence scores, and latency metrics
- Artifacts browser and relationship explorer
- Analytics dashboard with pipeline progress tracking
- SPA routing enabled

---

## Deployment

### Prerequisites

```bash
gcloud config get-value project     # must return: the-orchestrators
echo $GOOGLE_CLOUD_PROJECT          # must return: the-orchestrators
```

Ensure you have the following APIs enabled (handled automatically by `deploy_cloudrun.sh`):
`run.googleapis.com`, `cloudbuild.googleapis.com`, `pubsub.googleapis.com`,
`firestore.googleapis.com`, `bigquery.googleapis.com`, `aiplatform.googleapis.com`

---

### Step 1 — BigQuery Setup *(run once)*

```bash
bash setup_bigquery.sh
```

Creates the `dda_knowledge_graph` dataset and all required tables.

---

### Step 2 — Deploy All Services

```bash
bash deploy_cloudrun.sh
```

This script handles the full deployment pipeline:

1. Enables required GCP APIs
2. Creates Artifact Registry repo (`dda`)
3. Creates Pub/Sub topics & subscriptions
4. Builds and pushes Docker images for all 5 agents + UI
5. Deploys 6 Cloud Run services with environment variables
6. Wires Pub/Sub push subscriptions
7. Smoke-tests all `/health` endpoints
8. Saves all service URLs to `.cloudrun_urls`

---

### Step 3 — Verify

```bash
source ~/dda-project/.cloudrun_urls

# Check pipeline status
curl -s "${QUERY_API_URL}/v1/status" | python3 -m json.tool

# Run a test query
curl -s -X POST "${QUERY_API_URL}/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo","session_id":"test","query":"What pricing strategies drove margin decline 2016-2018?"}' \
  | python3 -m json.tool
```

---

### Stop Services *(save billing)*

```bash
bash stop_services.sh
```

This tears down Cloud Run instances only. All persistent data is preserved:
Firestore, BigQuery, Vector Search index, Docker images in Artifact Registry, and Pub/Sub topics.

Redeploy at any time with `deploy_cloudrun.sh`.

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

> **Never commit `.env` to version control.** Use `Secret Manager` for production deployments.

---

## Local Development (POC)

Standalone scripts in `poc/` for testing the pipeline locally without Cloud Run:

| Script | Stage |
|--------|-------|
| `poc/ingest1.py` | Local file ingestion |
| `poc/correlate1.py` | Local correlation |
| `poc/enrich1.py` | Local enrichment |
| `poc/query1.py` | Local query interface |

```bash
# Example: run local ingestion on a test PDF
python poc/ingest1.py --file sample_data/contract_2018.pdf
```

---

## Service URLs

After deployment, all URLs are saved to `.cloudrun_urls`:

```
https://dda-upload-service-<hash>-uc.a.run.app
https://dda-ingest-service-<hash>-uc.a.run.app
https://dda-correlate-service-<hash>-uc.a.run.app
https://dda-enrich-service-<hash>-uc.a.run.app
https://dda-query-service-<hash>-uc.a.run.app
https://dda-ui-service-<hash>-uc.a.run.app
```

---

## Troubleshooting

| Symptom | Diagnostic Command | Fix |
|---|---|---|
| Build fails: permission denied | `gcloud auth login` | Re-authenticate |
| Push fails: repo not found | Check Artifact Registry in console | Repo creation failed — run `gcloud artifacts repositories create dda --repository-format=docker --location=us-central1` manually |
| Deploy fails: API not enabled | `gcloud services list --enabled` | Run `gcloud services enable run.googleapis.com` for each missing API |
| Service unhealthy | `gcloud run logs read dda-query-service --region=us-central1 --limit=50` | Check application logs |
| Vector Search error | Set `VS_INDEX_ENDPOINT=""` in deploy script | Skips VS; falls back to Firestore-only retrieval |
| BigQuery write error | `bq show the-orchestrators:dda_knowledge_graph.relationships` | Verify table exists; re-run `setup_bigquery.sh` |
| Correlate returns 0 relationships | Check Gemini quota in Cloud Console | Retry with smaller batch or reduce `VECTOR_TOP_K` |

---

## Tech Stack

![GCP](https://img.shields.io/badge/Google_Cloud-4285F4?style=flat&logo=google-cloud&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat&logo=react&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-8E75B2?style=flat&logo=google&logoColor=white)

**Backend:** Python 3.11, FastAPI, Google Cloud Run, Pub/Sub  
**AI/ML:** Gemini 2.5 Flash, Vertex AI Vector Search, Document AI, Speech-to-Text  
**Storage:** Firestore, BigQuery, Google Cloud Storage  
**Frontend:** React, Nginx  
**DevOps:** Docker, Artifact Registry, Cloud Build  

---

## Built By

**Aravindhan Govindaraj** 
[Portfolio](https://aravindhan0510.github.io/portfolio/) · [LinkedIn](https://www.linkedin.com/in/aravindhan-g0510/) · [GitHub](https://github.com/Aravindhan0510)

*Built for the Gemini CLI Buildathon 2026.*
