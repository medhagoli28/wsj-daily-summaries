#!/usr/bin/env python3
"""Cross-day headline de-duplication — free, no external services.

Mode B researches a fresh batch of WSJ headlines, but the same story often
resurfaces across days. To avoid re-researching it, we compare each new headline
against headlines we already covered in the last few days and skip near-matches.

Similarity uses Python's built-in difflib — no API, no dependencies, no cost.
The store is a JSON file mapping headline text -> {date it was covered}.
"""

import difflib
import json
import os
from datetime import date, timedelta

STORE_PATH = "seen_headlines.json"


def load_store(path=STORE_PATH):
    """Load the headline->{date} store, or {} if the file doesn't exist yet."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_store(store, path=STORE_PATH):
    """Write the store back to disk as pretty-printed JSON."""
    with open(path, "w") as f:
        json.dump(store, f, indent=2)


def similarity(a, b):
    """Return how similar two headlines are, as a ratio in [0, 1] (difflib)."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def prune_store(store, lookback_days=7):
    """Return a copy of the store without entries older than the lookback window.

    Only headlines from the last `lookback_days` are ever compared, so anything
    older is dead weight — dropping it keeps the store file from growing forever.
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    return {
        text: record
        for text, record in store.items()
        if date.fromisoformat(record["date"]) >= cutoff
    }


def is_duplicate(headline, store, threshold=0.85, lookback_days=7):
    """True if `headline` is similar to any headline covered in the last N days.

    Compares the headline against every stored headline whose date is within
    `lookback_days`; returns True on the first similarity above `threshold`. An
    empty store is never a duplicate.
    """
    if not store:
        return False

    cutoff = date.today() - timedelta(days=lookback_days)
    for text, record in store.items():
        if date.fromisoformat(record["date"]) < cutoff:
            continue  # too old to count
        if similarity(headline, text) > threshold:
            return True
    return False
