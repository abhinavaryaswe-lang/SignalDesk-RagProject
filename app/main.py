import csv
import io
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import database
from .config import CHAT_MODEL, DATABASE_URL, EMBEDDING_MODEL, HF_TOKEN, LLM_PROVIDER, MAX_UPLOAD_MB, ROOT, CHUNK_OVERLAP, CHUNK_SIZE
from .rag import answer_question, embed_texts, provider_status

app = FastAPI(title="SignalDesk", description="Market demand intelligence grounded in your research library", version="1.0.0")


@app.on_event("startup")
def startup():
    database.init_db()


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1800)


def split_chunks(text, page=None):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + int(CHUNK_SIZE * 0.65), end)
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            pieces.append((part, page))
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return pieces


def extract_text(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return [(page.extract_text() or "", idx + 1) for idx, page in enumerate(reader.pages)]
    if suffix == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(data))
        return [("\n".join(p.text for p in doc.paragraphs), None)]
    if suffix == ".csv":
        decoded = data.decode("utf-8-sig", errors="replace")
        rows = csv.reader(io.StringIO(decoded))
        return [("\n".join(" | ".join(cell.strip() for cell in row) for row in rows), None)]
    if suffix in {".txt", ".md"}:
        return [(data.decode("utf-8-sig", errors="replace"), None)]
    raise HTTPException(400, "Supported file types are PDF, DOCX, TXT, MD, and CSV.")


@app.get("/api/health")
def health():
    status = provider_status()
    return {"ok": True, "model": CHAT_MODEL, "embedding_model": EMBEDDING_MODEL,
            "provider": LLM_PROVIDER, "provider_ready": status["ready"], "provider_status": status["detail"],
            "hugging_face_configured": bool(HF_TOKEN), "storage": "supabase" if DATABASE_URL else "local"}


@app.get("/api/stats")
def stats():
    docs = database.list_documents()
    status = provider_status()
    return {"documents": len(docs), "chunks": sum(int(d["chunks"]) for d in docs), "model": CHAT_MODEL,
            "embedding_model": EMBEDDING_MODEL, "provider": LLM_PROVIDER,
            "provider_status": status["detail"], "ready": status["ready"]}


@app.get("/api/documents")
def documents():
    return database.list_documents()


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)):
    name = Path(file.filename or "upload").name
    data = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than the {MAX_UPLOAD_MB} MB upload limit.")
    raw_pages = extract_text(name, data)
    chunk_pairs = [chunk for text, page in raw_pages for chunk in split_chunks(text, page)]
    if not chunk_pairs:
        raise HTTPException(422, "No readable text was found. Scanned PDFs need OCR before upload.")
    if len(chunk_pairs) > 250:
        raise HTTPException(413, "This file produced more than 250 text segments. Split it into smaller files and retry.")
    try:
        vectors = embed_texts([text for text, _ in chunk_pairs])
        items = [(text, page, vector) for (text, page), vector in zip(chunk_pairs, vectors)]
        doc_id = str(uuid.uuid4())
        database.add_document(doc_id, name, Path(name).suffix.lower().lstrip("."), len(data), items)
    except Exception as exc:
        raise HTTPException(502, f"Embedding or storage failed: {str(exc)[:300]}") from exc
    return {"id": doc_id, "name": name, "chunks": len(items)}


@app.delete("/api/documents/{doc_id}")
def remove_document(doc_id: str):
    if not database.delete_document(doc_id):
        raise HTTPException(404, "Document not found.")
    return {"deleted": True}


@app.post("/api/chat")
def chat(request: ChatRequest):
    try:
        return answer_question(request.question.strip())
    except Exception as exc:
        raise HTTPException(502, f"Inference request failed: {str(exc)[:350]}") from exc


app.mount("/assets", StaticFiles(directory=ROOT / "frontend" / "assets"), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    path = ROOT / "frontend" / full_path
    if full_path and path.is_file():
        return FileResponse(path)
    return FileResponse(ROOT / "frontend" / "index.html")
