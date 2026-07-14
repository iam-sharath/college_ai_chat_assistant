# rag-engine/app.py
"""
Main RAG engine server.

Endpoints:
  POST /query                 -> chatbot answer (used by website + WhatsApp bridge)
  POST /whatsapp               -> direct Twilio webhook (TwiML response)
  GET  /health                  -> health check
  POST /admin/documents         -> upload a new PDF/DOCX/TXT into the knowledge base
  GET  /admin/documents         -> list knowledge base documents
  DELETE /admin/documents/<id>  -> remove a document AND its chunks from the knowledge base
All /admin/* routes require header: X-Admin-Key: <ADMIN_API_KEY>
"""
import os
import uuid
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from werkzeug.utils import secure_filename

import db
db.init_db()  # must run before importing retrieval, which queries the DB at import time

import ingestion
from retrieval import store
from llm_router import generate_answer
from cache import response_cache
from config import FLASK_PORT, ADMIN_API_KEY, UPLOAD_DIR

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md"}

app = Flask(__name__)
CORS(app)


# ---------------------------------------------------------------------------
# Admin auth
# ---------------------------------------------------------------------------
def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not ADMIN_API_KEY:
            return jsonify({"error": "Server misconfigured: ADMIN_API_KEY not set."}), 500
        provided = request.headers.get("X-Admin-Key", "")
        if provided != ADMIN_API_KEY:
            return jsonify({"error": "Unauthorized. Invalid or missing admin key."}), 401
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Core answer pipeline (shared by /query and /whatsapp)
# ---------------------------------------------------------------------------
def answer_question(question):
    cached = response_cache.get(question)
    if cached:
        return {**cached, "cached": True}

    results = store.search(question)

    if results:
        context = "\n\n---\n\n".join(r["text"] for r in results)
        confidence = round(results[0]["score"], 3)
    else:
        context = "(No relevant information was found in the knowledge base for this question.)"
        confidence = 0.0

    answer, provider = generate_answer(question, context)

    payload = {
        "answer": answer,
        "sources": [r["text"] for r in results],
        "confidence": confidence,
        "provider": provider,
    }
    # only cache genuinely successful, provider-backed answers
    if provider:
        response_cache.set(question, payload)
    return {**payload, "cached": False}


# ---------------------------------------------------------------------------
# Public chatbot endpoints
# ---------------------------------------------------------------------------
@app.route("/query", methods=["POST"])
def query_rag():
    data = request.json or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    result = answer_question(question)
    return jsonify(result)


@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    incoming_msg = request.values.get("Body", "").strip()
    resp = MessagingResponse()
    if not incoming_msg:
        return str(resp)

    print(f"\n📱 WhatsApp message: {incoming_msg}")
    result = answer_question(incoming_msg)
    resp.message(result["answer"])
    return str(resp)


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "running",
        "vectors_indexed": store.index.ntotal,
        "documents": len(db.list_documents()),
    })


# ---------------------------------------------------------------------------
# Admin endpoints: manage the knowledge base
# ---------------------------------------------------------------------------
@app.route("/admin/documents", methods=["GET"])
@require_admin
def list_documents():
    return jsonify({"documents": db.list_documents()})


@app.route("/admin/documents", methods=["POST"])
@require_admin
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file provided (expected multipart field 'file')."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename."}), 400

    ext = ingestion.guess_file_type(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type '.{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}"}), 400

    safe_name = secure_filename(file.filename)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    file.save(stored_path)

    doc_id = db.add_document(original_name=safe_name, stored_path=stored_path, file_type=ext)

    try:
        raw_text = ingestion.extract_text(stored_path, ext)
        if not raw_text or not raw_text.strip():
            raise ValueError("No extractable text found in file (is it a scanned/image PDF?).")

        chunks = ingestion.create_smart_chunks(raw_text)
        if not chunks:
            raise ValueError("Document produced no usable chunks.")

        store.add_document_chunks(doc_id, chunks)
        return jsonify({
            "success": True,
            "document_id": doc_id,
            "original_name": safe_name,
            "chunks_created": len(chunks),
        })
    except Exception as e:
        db.mark_failed(doc_id, str(e))
        return jsonify({"success": False, "error": f"Ingestion failed: {e}", "document_id": doc_id}), 500


@app.route("/admin/documents/<int:doc_id>", methods=["DELETE"])
@require_admin
def delete_document(doc_id):
    document = db.get_document(doc_id)
    if not document:
        return jsonify({"error": "Document not found."}), 404

    store.remove_document(doc_id)  # removes vectors from FAISS + rows from SQLite

    try:
        if os.path.exists(document["stored_path"]):
            os.remove(document["stored_path"])
    except Exception as e:
        print(f"⚠️  Could not delete file from disk: {e}")

    return jsonify({"success": True, "message": f"Document '{document['original_name']}' and its knowledge removed."})


if __name__ == "__main__":
    print(f"🚀 RAG Engine (hybrid search + reranking + multi-provider failover) is LIVE on port {FLASK_PORT}")
    app.run(port=FLASK_PORT, debug=False)
