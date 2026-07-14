# rag-engine/cache.py
"""Tiny in-memory TTL cache. Repeated/common questions (very common in a
college chatbot -- "what are the fees", "library timings", etc.) get
answered instantly without hitting an LLM API at all."""
import time
import threading
from collections import OrderedDict

from config import CACHE_MAX_ITEMS, CACHE_TTL_SECONDS


class TTLCache:
    def __init__(self, max_items=CACHE_MAX_ITEMS, ttl=CACHE_TTL_SECONDS):
        self.max_items = max_items
        self.ttl = ttl
        self._store = OrderedDict()
        self._lock = threading.Lock()

    def _normalize(self, key):
        return " ".join(key.strip().lower().split())

    def get(self, key):
        key = self._normalize(key)
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            value, expires_at = item
            if time.time() > expires_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key, value):
        key = self._normalize(key)
        with self._lock:
            self._store[key] = (value, time.time() + self.ttl)
            self._store.move_to_end(key)
            while len(self._store) > self.max_items:
                self._store.popitem(last=False)


response_cache = TTLCache()
