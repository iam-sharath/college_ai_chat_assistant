# rag-engine/llm_router.py
"""
Calls out to an ordered chain of LLM providers. Each provider gets a couple
of quick retries (for transient errors / rate limits), and if it's still
failing we move to the next provider in the chain. This is what makes the
assistant resilient instead of just showing "the AI is offline" whenever one
provider hiccups.
"""
import time
import requests

from config import (
    GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
    LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES_PER_PROVIDER,
    SYSTEM_PROMPT,
)


def _call_groq(question, context):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context Information:\n{context}\n\nQuestion: {question}"},
        ],
        "temperature": 0.0,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT_SECONDS)
    if resp.status_code == 429:
        raise _RateLimited("groq")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_gemini_endpoint(question, context, api_key, model, label):
    """Shared Gemini caller -- used for both the primary Gemini slot and the
    'openrouter' slot when that slot is repurposed to hold a second Gemini
    API key (e.g. a separate Google Cloud project for its own quota pool)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\nContext Information:\n{context}\n\nQuestion: {question}"}]}],
        "generationConfig": {"temperature": 0.0},
    }
    resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=LLM_TIMEOUT_SECONDS)
    if resp.status_code == 429:
        raise _RateLimited(label)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_gemini(question, context):
    return _call_gemini_endpoint(question, context, GEMINI_API_KEY, GEMINI_MODEL, "gemini")


def _call_openrouter(question, context):
    # NOTE: this slot still reads from OPENROUTER_API_KEY / OPENROUTER_MODEL
    # (variable names unchanged), but now calls the Gemini endpoint -- put a
    # second Gemini API key here (ideally from a different Google Cloud
    # project) to get an independent quota pool as your 3rd fallback.
    return _call_gemini_endpoint(question, context, OPENROUTER_API_KEY, OPENROUTER_MODEL, "openrouter")


class _RateLimited(Exception):
    def __init__(self, provider):
        self.provider = provider


# Ordered failover chain. Providers with no key configured are skipped.
# Gemini first: best free daily volume (~1,500 req/day) and answer quality.
# Groq second: fastest, good backup for burst traffic when Gemini's lower
# per-minute limit gets hit.
# OpenRouter last: smallest free daily cap (50/day by default), best used
# as a final safety net.
_PROVIDER_CHAIN = [
    ("gemini", GEMINI_API_KEY, _call_gemini),
    ("groq", GROQ_API_KEY, _call_groq),
    ("openrouter", OPENROUTER_API_KEY, _call_openrouter),
]


def _with_retries(name, fn, question, context):
    last_err = None
    for attempt in range(LLM_MAX_RETRIES_PER_PROVIDER):
        try:
            return fn(question, context)
        except _RateLimited:
            wait = 1.5 * (attempt + 1)
            print(f"⚠️  {name} rate-limited, backing off {wait:.1f}s...")
            time.sleep(wait)
            last_err = f"{name} rate limited"
        except requests.exceptions.Timeout:
            print(f"⚠️  {name} timed out (attempt {attempt + 1}).")
            last_err = f"{name} timeout"
        except Exception as e:
            print(f"⚠️  {name} error: {e}")
            last_err = str(e)
            break  # non-retryable error, move to next provider immediately
    return None, last_err


def generate_answer(question, context):
    """
    Tries each configured provider in order. Returns (answer, provider_used)
    on success, or (fallback_message, None) if every provider failed.
    """
    tried = []
    for name, key, fn in _PROVIDER_CHAIN:
        if not key:
            continue
        tried.append(name)
        print(f"💬 Trying provider: {name}...")
        result = _with_retries(name, fn, question, context)
        if isinstance(result, tuple):
            _, err = result
            continue
        if result:
            print(f"✅ Answered using {name}.")
            return result, name

    if not tried:
        return (
            "No LLM provider is configured. Please set at least one of "
            "GROQ_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY in the .env file.",
            None,
        )

    return (
        "The AI assistant is temporarily unable to reach any language model provider "
        "(all configured providers failed or are rate-limited). Please try again shortly. 🎓",
        None,
    )
