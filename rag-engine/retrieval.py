# rag-engine/retrieval.py
"""
Hybrid retrieval = dense vector search (FAISS) + sparse keyword search (BM25),
fused with Reciprocal Rank Fusion, then re-scored with a cross-encoder
reranker. This combination is what actually fixes "not giving accurate
answers": pure vector search alone misses exact keyword/name/number matches,
and no reranking means irrelevant-but-nearby chunks dilute the context.
"""
import re
import threading

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

import db
from query_rewriter import rewrite_query
from config import (
    EMBEDDING_MODEL,
    RERANKER_MODEL,
    USE_RERANKER,
    INDEX_FILE,
    CANDIDATE_K,
    FINAL_TOP_K,
    MIN_RELEVANCE_SCORE,
)

_lock = threading.Lock()

print(f"⏳ Loading embedding model '{EMBEDDING_MODEL}'...")
embedder = SentenceTransformer(EMBEDDING_MODEL)
EMBED_DIM = embedder.get_sentence_embedding_dimension()
print("✅ Embedding model loaded.")

reranker = None
if USE_RERANKER:
    print(f"⏳ Loading reranker '{RERANKER_MODEL}'...")
    try:
        reranker = CrossEncoder(RERANKER_MODEL)
        print("✅ Reranker loaded.")
    except Exception as e:
        print(f"⚠️  Reranker failed to load, continuing without it: {e}")
        reranker = None


class KnowledgeStore:
    def __init__(self):
        self.index = self._load_or_create_index()
        self._chunk_cache = {}       # faiss_id -> text
        self._bm25 = None
        self._bm25_ids = []
        self._vocabulary = set()     # words seen in the KB, used for typo correction
        self._rebuild_bm25()

    # ---------- FAISS ----------
    def _load_or_create_index(self):
        try:
            idx = faiss.read_index(INDEX_FILE)
            print(f"✅ Loaded existing FAISS index ({idx.ntotal} vectors).")
            return idx
        except Exception:
            print("ℹ️  No existing FAISS index found, creating a new one.")
            flat = faiss.IndexFlatIP(EMBED_DIM)  # inner product on normalized vectors = cosine sim
            return faiss.IndexIDMap2(flat)

    def _save_index(self):
        faiss.write_index(self.index, INDEX_FILE)

    def _embed(self, texts):
        vecs = embedder.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        vecs = vecs.astype("float32")
        faiss.normalize_L2(vecs)
        return vecs

    # ---------- BM25 (keyword search) ----------
    def _rebuild_bm25(self):
        all_chunks = db.get_all_chunks()
        self._bm25_ids = [c[0] for c in all_chunks]
        self._chunk_cache = {fid: text for fid, text in all_chunks}
        corpus = [text.lower().split() for _, text in all_chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

        # Rebuild the vocabulary used for local typo correction. Learning
        # this from your own documents means department names, course
        # codes, and faculty names get recognized automatically as you
        # upload more files -- no generic dictionary needed.
        vocab = set()
        for _, text in all_chunks:
            for word in re.findall(r"[a-z]+", text.lower()):
                if len(word) >= 4:
                    vocab.add(word)
        self._vocabulary = vocab

    # ---------- Mutations ----------
    def add_document_chunks(self, doc_id, chunk_texts):
        with _lock:
            vecs = self._embed(chunk_texts)
            start_id = db.next_faiss_id()
            faiss_ids = list(range(start_id, start_id + len(chunk_texts)))
            self.index.add_with_ids(vecs, np.array(faiss_ids, dtype="int64"))
            db.add_chunks(doc_id, chunk_texts, faiss_ids)
            self._save_index()
            self._rebuild_bm25()
            return faiss_ids

    def remove_document(self, doc_id):
        with _lock:
            faiss_ids = db.get_faiss_ids_for_doc(doc_id)
            if faiss_ids:
                self.index.remove_ids(np.array(faiss_ids, dtype="int64"))
            db.delete_document(doc_id)
            self._save_index()
            self._rebuild_bm25()

    # ---------- Search ----------
    def search(self, question, top_k=FINAL_TOP_K, candidate_k=CANDIDATE_K):
        if self.index.ntotal == 0:
            return []

        candidate_k = min(candidate_k, self.index.ntotal)

        # 0. Local query rewriting: fix typos and expand abbreviations using
        # vocabulary learned from your own documents. The rewritten query is
        # never used *instead of* the original -- both are searched and
        # fused below, so a bad rewrite can only add candidates, never
        # remove good ones the original query would have found.
        rewritten, changed, notes = rewrite_query(question, self._vocabulary)
        queries_to_search = [question]
        if changed:
            print(f"🔤 Query rewrite: \"{question}\" -> \"{rewritten}\" ({', '.join(notes)})")
            queries_to_search.append(rewritten)

        # 1 & 2. Dense vector search + sparse keyword search, for every
        # query variant, each contributing its own ranked list.
        ranked_lists = []
        for q in queries_to_search:
            q_vec = self._embed([q])
            scores, ids = self.index.search(q_vec, candidate_k)
            vector_ranked = [
                int(i) for i, s in sorted(zip(ids[0], scores[0]), key=lambda x: -x[1]) if i != -1
            ]
            ranked_lists.append(vector_ranked)

            if self._bm25 is not None:
                tokenized = q.lower().split()
                bm25_scores = self._bm25.get_scores(tokenized)
                ranked = sorted(
                    zip(self._bm25_ids, bm25_scores), key=lambda x: -x[1]
                )[:candidate_k]
                keyword_ranked = [fid for fid, score in ranked if score > 0]
                ranked_lists.append(keyword_ranked)

        # 3. Reciprocal Rank Fusion to merge every ranked list (vector +
        # keyword, original query + rewritten query)
        fused_scores = {}
        for ranked_list in ranked_lists:
            for rank, fid in enumerate(ranked_list):
                fused_scores[fid] = fused_scores.get(fid, 0) + 1.0 / (60 + rank)

        fused_ranked = sorted(fused_scores.items(), key=lambda x: -x[1])
        candidates = [
            (fid, self._chunk_cache.get(fid, "")) for fid, _ in fused_ranked if fid in self._chunk_cache
        ]

        if not candidates:
            return []

        # 4. Cross-encoder reranking for final precision
        if reranker is not None and len(candidates) > 1:
            pairs = [[question, text] for _, text in candidates]
            rerank_scores = reranker.predict(pairs)
            # squash raw cross-encoder logits to a rough 0-1 scale
            rerank_scores = 1 / (1 + np.exp(-np.array(rerank_scores)))
            scored = list(zip(candidates, rerank_scores))
            scored.sort(key=lambda x: -x[1])
        else:
            # fall back to fusion order with a neutral confidence
            scored = [(c, 0.5) for c in candidates]

        results = [
            {"text": text, "score": float(score)}
            for (fid, text), score in scored
            if score >= MIN_RELEVANCE_SCORE
        ][:top_k]

        return results


store = KnowledgeStore()
