# rag-engine/ingestion.py
"""
Turns an uploaded file (pdf / docx / txt / md) into clean, overlapping text
chunks ready for embedding. Overlap prevents facts that sit on a chunk
boundary from getting split away from their context.
"""
import os
import re

from config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS


class UnsupportedFileType(Exception):
    pass


def extract_text(file_path, file_type):
    file_type = file_type.lower()
    if file_type == "pdf":
        return _extract_pdf(file_path)
    if file_type == "docx":
        return _extract_docx(file_path)
    if file_type in ("txt", "md"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise UnsupportedFileType(f"Unsupported file type: {file_type}")


def _extract_pdf(file_path):
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {i + 1}]\n{text.strip()}")
    return "\n\n".join(pages)


def _extract_docx(file_path):
    import docx

    doc = docx.Document(file_path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paras)


def _split_sentences(text):
    # lightweight sentence splitter, avoids pulling in a heavy NLP dependency
    return re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)


def create_smart_chunks(text, max_chars=CHUNK_MAX_CHARS, overlap_chars=CHUNK_OVERLAP_CHARS):
    """
    Recursive-style splitter:
    1. Split on blank lines (paragraphs / sections stay together).
    2. If a paragraph itself is too long, fall back to sentence splitting.
    3. Carry a trailing overlap forward into the next chunk so a fact that
       straddles a boundary is still retrievable from either chunk.
    """
    text = text.replace("\r\n", "\n")
    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # Break down any paragraph that's already bigger than max_chars
    units = []
    for para in raw_paragraphs:
        if "====" in para or "----" in para:
            continue
        if len(para) <= max_chars:
            units.append(para)
        else:
            sentences = _split_sentences(para)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) + 1 <= max_chars:
                    buf = f"{buf} {s}".strip()
                else:
                    if buf:
                        units.append(buf)
                    buf = s
            if buf:
                units.append(buf)

    # Pack units into chunks up to max_chars, carrying overlap forward
    chunks = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip() if current else unit
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
                # start next chunk with the tail of the previous one (overlap)
                tail = current[-overlap_chars:] if overlap_chars > 0 else ""
                current = f"{tail}\n\n{unit}".strip()
            else:
                current = unit

    if current:
        chunks.append(current)

    return [c for c in chunks if len(c) > 20]  # drop near-empty fragments


def guess_file_type(filename):
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext
