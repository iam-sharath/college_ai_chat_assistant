# College AI Assistant — v2

A RAG-powered chatbot (website + WhatsApp) with an admin panel for managing
the knowledge base, hybrid retrieval, and multi-provider LLM failover.

## ⚠️ Security first

This rebuild removes hardcoded API keys from source code. **If you're
migrating from the old version, your old Groq/Gemini keys were exposed in
`query.py` and `.env` and were likely committed to git — revoke/regenerate
both keys before doing anything else**, then fill in the new ones only in
`.env` files (never in code, never committed).

## What changed vs the original version

- **Hybrid retrieval**: vector search (FAISS) + keyword search (BM25),
  fused with Reciprocal Rank Fusion, then re-ranked with a cross-encoder.
  This fixes most "wrong/irrelevant answer" issues — pure vector search
  alone often misses exact names/numbers, and un-reranked top-25 chunks
  drown the LLM in noise.
- **Relevance threshold**: low-confidence chunks are dropped instead of
  being forced into context, so the bot says "I don't know" instead of
  guessing from irrelevant material.
- **Admin panel** (`/admin`): upload PDF/DOCX/TXT/MD files; each file is
  chunked+embedded and tracked in SQLite. Deleting a file removes its
  vectors from FAISS **and** its chunk rows — its knowledge is fully gone,
  not just orphaned.
- **3-provider LLM failover**: Gemini → Groq → OpenRouter, each with retry
  + backoff before moving to the next, so a single provider's rate limit
  doesn't take the whole assistant down. Gemini goes first for its higher
  free daily volume and answer quality; Groq is the fast backup; OpenRouter
  is the last-resort safety net.
- **Response cache**: repeated questions get instant, consistent answers
  without hitting an LLM API again.
- **Query rewriting (typo correction + abbreviation expansion)**: messy
  queries like "wat is d libary timmings" get corrected to "what is the
  library timings" *before* retrieval, using a vocabulary learned
  automatically from your own uploaded documents (no extra LLM call, no
  added rate-limit usage). Both the original and corrected query are
  searched and merged, so a bad correction can only add candidates, never
  remove ones the original would have found. Edit
  `rag-engine/data/abbreviations.json` (auto-created on first run) to add
  your own college-specific shorthand.
- Removed: `venv/`, `node_modules/` (335MB → a few MB) from the shipped
  project — reinstall with `pip install` / `npm install` below.

## Project structure

```
backend/          Node/Express API (serves frontend, proxies to rag-engine)
frontend/         Chat widget (index.html) + Admin panel (admin.html)
rag-engine/       Python/Flask RAG engine (retrieval + LLM routing + admin API)
```

## Setup

### 1. RAG engine (Python)

```bash
cd rag-engine
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set ADMIN_API_KEY and at least one of GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY
python app.py
```

First run downloads the embedding model (`all-MiniLM-L6-v2`) and, if enabled,
the reranker model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) — needs internet
once, then they're cached locally.

### 2. Backend (Node)

```bash
cd backend
npm install
cp .env.example .env
# edit .env: set the SAME ADMIN_API_KEY as rag-engine/.env
npm start
```

### 3. Use it

- Chatbot: http://localhost:3000
- Admin panel: http://localhost:3000/admin — enter your `ADMIN_API_KEY` to unlock, then upload PDFs/DOCX/TXT.

There is no seed knowledge base — upload your college's documents (PDFs of
handbooks, FAQs, course catalogs, etc.) via the admin panel to get started.

### 4. WhatsApp (optional)

Point your Twilio WhatsApp sandbox webhook to:
`https://<your-domain>/api/whatsapp/webhook`

## Tuning retrieval accuracy

All knobs are in `rag-engine/.env`:
- `FINAL_TOP_K` — how many chunks get sent to the LLM (default 5)
- `MIN_RELEVANCE_SCORE` — raise this (e.g. 0.25) if the bot still answers
  from loosely-related chunks; lower it if it says "I don't know" too often
- `USE_RERANKER=false` — disable the cross-encoder if your server is very
  low-spec (retrieval will be faster but less precise)
