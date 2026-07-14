# rag-engine/query_rewriter.py
"""
Local, fast query normalization -- no extra LLM call, no added latency,
no extra API-rate-limit usage.

Two techniques, applied before retrieval:
1. Abbreviation / slang expansion ("d" -> "the", "wat" -> "what",
   "kitna" -> "how much") from an editable dictionary.
2. Fuzzy typo correction against a vocabulary built from your OWN ingested
   documents -- so it learns your college's specific terms (department
   names, course codes, faculty names) automatically as documents are
   uploaded, rather than relying on a generic English dictionary.

The rewritten query is never used *instead of* the original -- retrieval.py
searches both and fuses the results, so a bad rewrite can't make things
worse, only potentially better.
"""
import json
import os
import re

from rapidfuzz import process, fuzz

from config import BASE_DIR

ABBREVIATIONS_FILE = os.path.join(BASE_DIR, "data", "abbreviations.json")

# Sensible defaults for common chat shorthand / Hinglish seen in student
# messages. Admins can override/extend this by editing
# rag-engine/data/abbreviations.json (auto-created on first run).
_DEFAULT_ABBREVIATIONS = {
    "d": "the", "u": "you", "ur": "your", "r": "are", "pls": "please",
    "plz": "please", "info": "information", "avail": "available",
    "reg": "registration", "dept": "department", "admn": "admission",
    "addmision": "admission", "admision": "admission", "wat": "what",
    "wats": "what is", "whats": "what is", "hw": "how", "kitna": "how much",
    "kitne": "how many", "kab": "when", "kaha": "where", "kaun": "who",
    "b4": "before", "docs": "documents", "std": "student", "univ": "university",
    "sem": "semester", "yr": "year", "hostel": "hostel", "lib": "library",
    "timming": "timing", "timmings": "timings", "schollarship": "scholarship",
    "scholorship": "scholarship", "prosess": "process", "proccess": "process",
}

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "am", "i", "you", "he",
    "she", "it", "we", "they", "what", "when", "where", "who", "how", "why",
    "do", "does", "did", "can", "could", "will", "would", "should", "to",
    "of", "in", "on", "for", "and", "or", "please", "me", "my", "your",
}


def _load_abbreviations():
    if os.path.exists(ABBREVIATIONS_FILE):
        try:
            with open(ABBREVIATIONS_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
            merged = dict(_DEFAULT_ABBREVIATIONS)
            merged.update(custom)
            return merged
        except Exception as e:
            print(f"⚠️  Could not read abbreviations.json, using defaults: {e}")
            return dict(_DEFAULT_ABBREVIATIONS)
    else:
        os.makedirs(os.path.dirname(ABBREVIATIONS_FILE), exist_ok=True)
        with open(ABBREVIATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)
        return dict(_DEFAULT_ABBREVIATIONS)


_ABBREVIATIONS = _load_abbreviations()

_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+")


def rewrite_query(question, vocabulary, fuzzy_threshold=82):
    """
    Returns (rewritten_query, changed: bool, notes: list[str]).
    `vocabulary` is a set of lowercase words seen across all ingested chunks
    (built and refreshed by retrieval.KnowledgeStore).
    """
    tokens = _TOKEN_RE.findall(question)
    if not tokens:
        return question, False, []

    out_tokens = []
    notes = []
    changed = False

    for tok in tokens:
        lower = tok.lower()

        # 1. Abbreviation / slang expansion
        if lower in _ABBREVIATIONS:
            expansion = _ABBREVIATIONS[lower]
            out_tokens.append(expansion)
            notes.append(f"{tok} -> {expansion}")
            changed = True
            continue

        # 2. Skip correction for stopwords, numbers, and already-known words
        if (
            lower in _STOPWORDS
            or lower.isdigit()
            or len(lower) < 4
            or not vocabulary
            or lower in vocabulary
        ):
            out_tokens.append(tok)
            continue

        # 3. Fuzzy match against the knowledge base's own vocabulary
        match = process.extractOne(lower, vocabulary, scorer=fuzz.ratio, score_cutoff=fuzzy_threshold)
        if match:
            corrected = match[0]
            if corrected != lower:
                out_tokens.append(corrected)
                notes.append(f"{tok} -> {corrected}")
                changed = True
                continue

        out_tokens.append(tok)

    rewritten = " ".join(out_tokens)
    return rewritten, changed, notes
