"""
DDA UPLOAD SERVICE — Standalone
Separate microservice just for file uploads.
Deploy as: gcloud run deploy dda-upload-service --source .
"""

import os, json, uuid, logging, hashlib
from datetime import datetime, timezone
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from gcp_client import COL_ARTIFACTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dda-upload")

app = FastAPI(title="DDA Upload Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "the-orchestrators")
GCS_BUCKET = os.environ.get("GCS_STAGING_BUCKET", "dda-raw-staging")
PUBSUB_UPLOAD_TO_INGEST_TOPIC_FULL = os.environ.get("PUBSUB_UPLOAD_TO_INGEST_TOPIC", "dda-ingest-trigger")
PUBSUB_UPLOAD_TO_INGEST_TOPIC_ID = PUBSUB_UPLOAD_TO_INGEST_TOPIC_FULL.split('/')[-1]

ALLOWED_EXT = {".pdf", ".docx", ".csv"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "dda-upload", "bucket": GCS_BUCKET}

@app.post("/v1/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload file to GCS and trigger INGEST pipeline.

    Error codes:
    - 400: Invalid file type or empty file
    - 500: GCS write failed (check permissions)
    - 503: Pub/Sub failed (check topic exists)
    """
    from google.cloud import storage, pubsub_v1, firestore

    # Validate extension
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Use: {', '.join(ALLOWED_EXT)}"
        )

    # Read and validate content
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    content_hash = hashlib.md5(content).hexdigest()
    artifact_id = f"{file.filename.replace('.', '_')}_{content_hash[:8]}"
    gcs_path = f"uploads/{datetime.now().strftime('%Y%m%d')}/{file.filename}"
    gcs_uri = f"gs://{GCS_BUCKET}/{gcs_path}"

    # ── Write to GCS ──────────────────────────────────────────────────────
    try:
        gcs_client = storage.Client(project=PROJECT_ID)
        bucket = gcs_client.bucket(GCS_BUCKET)
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(
            content,
            content_type=file.content_type or "application/octet-stream"
        )
        logger.info(f"✓ GCS: {gcs_uri} ({len(content)} bytes)")
    except Exception as e:
        logger.error(f"✗ GCS write: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload to GCS: {str(e)[:150]}"
        )

    # ── Create initial Firestore artifact record ──────────────────────────
    try:
        db = firestore.Client(project=PROJECT_ID)
        initial_artifact = {
            "artifact_id":   artifact_id,
            "filename":      file.filename,
            "gcs_uri":       gcs_uri,
            "mime_type":     file.content_type or "application/octet-stream",
            "pipeline_stage":"UPLOADED",
            "uploaded_at":   datetime.now(timezone.utc).isoformat(),
            "content_hash":  content_hash,
            "size":          len(content),
        }
        db.collection(COL_ARTIFACTS).document(artifact_id).set(initial_artifact)
        logger.info(f"✓ Firestore: initial artifact {artifact_id} created with UPLOADED stage")
    except Exception as e:
        logger.error(f"✗ Firestore write failed for initial artifact: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create initial artifact record in Firestore: {str(e)[:150]}"
        )

    # ── Publish Pub/Sub trigger ───────────────────────────────────────────
    pub_triggered = False
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_UPLOAD_TO_INGEST_TOPIC_ID)
        payload_data = {
            "artifact_id": artifact_id,
            "gcs_uri": gcs_uri,
            "filename": file.filename,
            "mime_type": file.content_type or "application/octet-stream",
            "size": len(content),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = json.dumps(payload_data).encode()

        logger.info(f"Pub/Sub payload data before encoding: {payload_data}")
        logger.info(f"Pub/Sub payload type: {type(payload)}, length: {len(payload)}")

        publisher.publish(topic_path, payload).result() # .result() will block until the publish call returns a response from the Pub/Sub service
        logger.info(f"✓ Pub/Sub: Ingest trigger for {artifact_id}")
        pub_triggered = True
    except google.api_core.exceptions.GoogleAPICallError as e:
        logger.error(f"✗ Pub/Sub: Ingest trigger failed for {artifact_id} due to API call error: {e}", exc_info=True)
        # Update Firestore with the specific Pub/Sub API error
        db = firestore.Client(project=PROJECT_ID)
        db.collection(COL_ARTIFACTS).document(artifact_id).update({
            "ingest_trigger_error": f"Pub/Sub API Error: {str(e)[:150]}",
            "requires_review": True,
        })
        logger.info(f"✓ Firestore: Updated {artifact_id} with ingest_trigger_error due to API call error")
        pub_triggered = False
    except Exception as e:
        logger.error(f"✗ Pub/Sub: Ingest trigger failed for {artifact_id} due to unexpected error: {e}", exc_info=True)
        db = firestore.Client(project=PROJECT_ID)
        db.collection(COL_ARTIFACTS).document(artifact_id).update({
            "ingest_trigger_error": f"Unexpected Pub/Sub Error: {str(e)[:150]}",
            "requires_review": True,
        })
        logger.info(f"✓ Firestore: Updated {artifact_id} with ingest_trigger_error due to unexpected error")
        pub_triggered = False

    response = {
        "status": "ok" if pub_triggered else "partial",
        "artifact_id": artifact_id,
        "gcs_uri": gcs_uri,
        "filename": file.filename,
        "size": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    if pub_triggered:
        response["message"] = "✓ File uploaded and INGEST pipeline triggered. Processing will begin shortly."
    else:
        response["message"] = "⚠ File uploaded to GCS but INGEST trigger failed. Check logs for details. It will be processed manually."

    return response

@app.post("/v1/upload/batch")
async def upload_batch(files: list[UploadFile] = File(...)):
    """Upload multiple files at once."""
    results = []
    for file in files:
        try:
            result = await upload_file(file)
            results.append({"filename": file.filename, "status": "ok", "data": result})
        except HTTPException as e:
            results.append({"filename": file.filename, "status": "error", "detail": e.detail})
        except Exception as e:
            results.append({"filename": file.filename, "status": "error", "detail": str(e)})
    return {"uploaded": len([r for r in results if r["status"]=="ok"]), "results": results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))