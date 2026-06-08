import os
from dotenv import load_dotenv
load_dotenv()

PROJECT_ID    = os.getenv("GCP_PROJECT_ID", "the-orchestrators")
REGION        = os.getenv("GCP_REGION", "us-central1")
RAW_DATA_DIR  = os.getenv("RAW_DATA_DIR", "./data/raw")
GEMINI_MODEL  = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")

COL_ARTIFACTS     = "dda_artifacts"
COL_RELATIONSHIPS = "dda_relationships"
COL_DECISIONS     = "dda_decisions"

def get_firestore():
    from google.cloud import firestore
    return firestore.Client(project=PROJECT_ID)

def get_gemini_client():
    from google import genai
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file")
    return genai.Client(api_key=api_key)

def get_chromadb():
    import chromadb
    return chromadb.PersistentClient(path=os.getenv("CHROMA_PATH", "./chroma_store"))

def list_raw_files():
    files = []
    for filename in os.listdir(RAW_DATA_DIR):
        full_path = os.path.join(RAW_DATA_DIR, filename)
        if os.path.isfile(full_path):
            files.append({
                "filename":   filename,
                "full_path":  full_path,
                "extension":  filename.split(".")[-1].lower(),
                "size_bytes": os.path.getsize(full_path)
            })
    return files

def save_artifact(artifact_id, data):
    db  = get_firestore()
    ref = db.collection(COL_ARTIFACTS).document(artifact_id)
    ref.set(data)
    return artifact_id

def get_artifact(artifact_id):
    db  = get_firestore()
    doc = db.collection(COL_ARTIFACTS).document(artifact_id).get()
    return doc.to_dict() if doc.exists else None

def get_all_artifacts():
    db   = get_firestore()
    docs = db.collection(COL_ARTIFACTS).stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

def save_relationship(data):
    db  = get_firestore()
    ref = db.collection(COL_RELATIONSHIPS).document()
    ref.set(data)
    return ref.id

def save_decision(data):
    db  = get_firestore()
    ref = db.collection(COL_DECISIONS).document()
    ref.set(data)
    return ref.id
