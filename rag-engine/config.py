# rag-engine/config.py
"""
Central configuration. Everything sensitive comes from environment
variables (.env) -- never hardcode API keys in source files.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Server ---
FLASK_PORT = int(os.getenv("FLASK_PORT", 5001))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")  # required to manage knowledge base

# --- Storage paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
INDEX_FILE = os.path.join(STORAGE_DIR, "index.faiss")
DB_FILE = os.path.join(STORAGE_DIR, "knowledge.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)

# --- Embedding / retrieval ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
USE_RERANKER = os.getenv("USE_RERANKER", "true").lower() == "true"

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", 900))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", 150))

# how many candidates to pull from vector + keyword search before reranking
CANDIDATE_K = int(os.getenv("CANDIDATE_K", 20))
# how many chunks to actually hand to the LLM after reranking
FINAL_TOP_K = int(os.getenv("FINAL_TOP_K", 5))
# a reranked chunk below this score is dropped (0-1). Prevents irrelevant
# chunks from diluting the context when the KB has no real answer.
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", 0.15))

# --- LLM providers (ordered failover chain) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", 25))
LLM_MAX_RETRIES_PER_PROVIDER = int(os.getenv("LLM_MAX_RETRIES_PER_PROVIDER", 2))

# --- Response cache (reduces duplicate API calls & speeds up repeats) ---
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_MAX_ITEMS = int(os.getenv("CACHE_MAX_ITEMS", 500))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", 3600))

SYSTEM_PROMPT = """You are an elite, highly accurate AI Assistant for a college. Follow these rules strictly:

1. CONVERSATIONAL ETIQUETTE: If the user sends a simple greeting or thanks you, respond warmly. Do not use the fallback phrase for greetings.
2. STRICT FACTUALITY: For all factual questions, answer ONLY using the facts provided in the Context Information below. NEVER invent information, dates, names, or aliases.
3. NAME COLLISION RULE: If multiple people share a name, treat them as completely separate individuals based on initials/department/other distinguishing details in the context.
4. ENTITY ISOLATION: Only assign a role or title to a person if the context explicitly and directly links them.
5. NATURAL ANSWERS ONLY: Answer in clean, natural language using short paragraphs or simple bullet points. NEVER mention internal document structure, section labels, field names (e.g. "COLLEGE_NAME", "ABOUT_COLLEGE"), page numbers, or filenames in your answer -- the student doesn't know or care how the knowledge base is organized internally. Just state the facts plainly, as if you already knew them.
6. UNKNOWN INFO: If the answer is not contained in the Context Information, reply exactly with: "I'm sorry, I don't have information on that." Do not guess or fabricate.
"""
