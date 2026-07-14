# rag-engine/db.py
"""
SQLite registry mapping uploaded documents -> their chunks -> their FAISS
vector ids. This is what makes "delete a PDF -> its knowledge disappears"
actually possible, instead of having to rebuild everything from scratch.
"""
import sqlite3
import threading
from datetime import datetime, timezone

from config import DB_FILE

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            num_chunks INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'processing'
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            faiss_id INTEGER NOT NULL UNIQUE,
            text TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
        """
    )
    conn.commit()
    conn.close()


def add_document(original_name, stored_path, file_type):
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO documents (original_name, stored_path, file_type, uploaded_at, status) "
            "VALUES (?, ?, ?, ?, 'processing')",
            (original_name, stored_path, file_type, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        doc_id = cur.lastrowid
        conn.close()
        return doc_id


def add_chunks(doc_id, chunk_texts, faiss_ids):
    with _lock:
        conn = _connect()
        conn.executemany(
            "INSERT INTO chunks (doc_id, faiss_id, text) VALUES (?, ?, ?)",
            [(doc_id, fid, text) for fid, text in zip(faiss_ids, chunk_texts)],
        )
        conn.execute(
            "UPDATE documents SET num_chunks = ?, status = 'ready' WHERE id = ?",
            (len(chunk_texts), doc_id),
        )
        conn.commit()
        conn.close()


def mark_failed(doc_id, reason=""):
    with _lock:
        conn = _connect()
        conn.execute("UPDATE documents SET status = ? WHERE id = ?", (f"failed: {reason}"[:200], doc_id))
        conn.commit()
        conn.close()


def list_documents():
    conn = _connect()
    rows = conn.execute(
        "SELECT id, original_name, file_type, uploaded_at, num_chunks, status "
        "FROM documents ORDER BY uploaded_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_faiss_ids_for_doc(doc_id):
    conn = _connect()
    rows = conn.execute("SELECT faiss_id FROM chunks WHERE doc_id = ?", (doc_id,)).fetchall()
    conn.close()
    return [r["faiss_id"] for r in rows]


def delete_document(doc_id):
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))  # cascades to chunks
        conn.commit()
        conn.close()


def get_all_chunks():
    """Returns list of (faiss_id, text) for every chunk currently registered.
    Used to rebuild the in-memory BM25 keyword index after add/delete."""
    conn = _connect()
    rows = conn.execute("SELECT faiss_id, text FROM chunks").fetchall()
    conn.close()
    return [(r["faiss_id"], r["text"]) for r in rows]


def next_faiss_id():
    """Monotonically increasing id so we never reuse an id FAISS might still
    reference internally after a removal."""
    conn = _connect()
    row = conn.execute("SELECT MAX(faiss_id) as m FROM chunks").fetchone()
    conn.close()
    current_max = row["m"] if row and row["m"] is not None else -1
    return current_max + 1
