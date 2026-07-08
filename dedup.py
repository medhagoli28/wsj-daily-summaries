#!/usr/bin/env python3
"""Cross-day headline de-duplication via embeddings.

Mode B researches a fresh batch of WSJ headlines every day, but the same story
often resurfaces across days. To avoid re-researching it, we embed each headline
and skip any that is very similar (cosine similarity above a threshold) to a
headline we already covered in the last few days.

Embeddings use OpenAI's text-embedding-3-small (Anthropic has no embeddings API).
The store is a plain JSON file mapping headline text -> {embedding, date}.
"""

import functools
import json
import math
import os
from datetime import date, timedelta

STORE_PATH = "embeddings_store.json"
EMBED_MODEL = "text-embedding-3-small"


def load_store(path=STORE_PATH):
    """Load the headline->{embedding, date} store, or {} if it doesn't exist."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_store(store, path=STORE_PATH):
    """Write the store back to disk as pretty-printed JSON."""
    with open(path, "w") as f:
        json.dump(store, f, indent=2)


def cosine_similarity(a, b):
    """Cosine similarity between two equal-length vectors (0.0 if either is zero)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@functools.lru_cache(maxsize=None)
def embed(text):
    """Return the embedding vector for `text` via OpenAI.

    Lazily imports the SDK so Mode A and the unit tests don't need `openai` or an
    API key. Cached per-process so embedding the same headline twice in one run
    (once to check for duplicates, once to store it) costs a single API call.
    """
    from openai import OpenAI

    client = OpenAI()  # reads OPENAI_API_KEY from the environment
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def prune_store(store, lookback_days=7):
    """Return a copy of the store without entries older than the lookback window.

    Only headlines from the last `lookback_days` are ever compared, so anything
    older is dead weight — dropping it keeps embeddings_store.json from growing
    without bound.
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    return {
        text: record
        for text, record in store.items()
        if date.fromisoformat(record["date"]) >= cutoff
    }


def is_duplicate(headline, store, threshold=0.85, lookback_days=7):
    """True if `headline` is similar to any headline covered in the last N days.

    Compares the headline's embedding against every stored embedding whose date is
    within `lookback_days`; returns True on the first cosine similarity above
    `threshold`. An empty store is never a duplicate.
    """
    if not store:
        return False

    vector = embed(headline)
    cutoff = date.today() - timedelta(days=lookback_days)
    for record in store.values():
        if date.fromisoformat(record["date"]) < cutoff:
            continue  # too old to count
        if cosine_similarity(vector, record["embedding"]) > threshold:
            return True
    return False
