"""Unit tests for search.py — indexing, TF-IDF ranking, filters, snippets.

Pure functions and an in-memory corpus, so these run offline and deterministically.
Run with:  python3 -m pytest
"""

import math

import pytest

import search


# A tiny, controlled corpus. Note the term-heavy digest is the OLDEST, so a
# correct ranker must place it first for "apple chips" (relevance, not recency).
DOCS = [
    {"date": "2026-07-10", "text": "Apple to spend billions on chips from Broadcom", "topics": ["Chips"]},
    {"date": "2026-07-09", "text": "Bitcoin falls as Strategy sells crypto holdings", "topics": ["Crypto"]},
    {"date": "2026-07-08", "text": "Apple chips and Apple silicon; chips chips chips", "topics": ["Chips", "AI boom"]},
]


@pytest.fixture
def index():
    return search.build_index(DOCS)


# --- tokenize / idf ----------------------------------------------------------

def test_tokenize_lowercases_splits_and_drops_single_chars():
    assert search.tokenize("Apple's $30B chip!") == ["apple", "30b", "chip"]
    assert search.tokenize("a I x9 to") == ["x9", "to"]   # 'a' and 'i' dropped, 'x9'/'to' kept
    assert search.tokenize("") == []


def test_idf_is_smoothed_and_positive_even_for_ubiquitous_terms():
    assert search.idf(3, 1) == pytest.approx(math.log(4 / 2) + 1)
    # a term in every doc still gets a positive weight (no divide-by-zero / zero collapse)
    assert search.idf(1, 1) > 0


# --- build_index -------------------------------------------------------------

def test_build_index_counts_df_and_postings(index):
    assert index["N"] == 3
    assert index["df"]["apple"] == 2          # docs 0 and 2
    assert index["df"]["bitcoin"] == 1
    # doc 2 has "chips" four times
    chips = dict((doc, tf) for doc, tf in index["postings"]["chips"])
    assert chips[2] == 4 and chips[0] == 1
    assert index["docs"][2]["topics"] == ["AI boom", "Chips"]   # sorted


# --- ranking -----------------------------------------------------------------

def test_search_ranks_by_relevance_not_recency(index):
    results = search.search(index, "apple chips")
    assert [r["date"] for r in results] == ["2026-07-08", "2026-07-10"]  # heavier (older) first
    assert results[0]["score"] > results[1]["score"]


def test_search_no_results_for_absent_term(index):
    assert search.search(index, "zebra kangaroo") == []


def test_empty_query_browses_all_newest_first(index):
    results = search.search(index, "   ")
    assert [r["date"] for r in results] == ["2026-07-10", "2026-07-09", "2026-07-08"]


# --- filters -----------------------------------------------------------------

def test_date_range_filter(index):
    dates = [r["date"] for r in search.search(index, "", date_from="2026-07-09")]
    assert dates == ["2026-07-10", "2026-07-09"]
    dates = [r["date"] for r in search.search(index, "", date_from="2026-07-09", date_to="2026-07-09")]
    assert dates == ["2026-07-09"]


def test_topic_filter_is_union(index):
    assert {r["date"] for r in search.search(index, "", topics=["Crypto"])} == {"2026-07-09"}
    assert {r["date"] for r in search.search(index, "", topics=["Chips"])} == {"2026-07-10", "2026-07-08"}
    assert {r["date"] for r in search.search(index, "", topics=["Chips", "Crypto"])} == \
        {"2026-07-10", "2026-07-09", "2026-07-08"}


def test_keyword_and_filter_combine(index):
    # "apple" matches docs 0 & 2, but the date filter drops the 2026-07-08 one
    dates = [r["date"] for r in search.search(index, "apple", date_from="2026-07-09")]
    assert dates == ["2026-07-10"]


# --- malformed dates ---------------------------------------------------------

def test_parse_date_handles_empty_valid_and_malformed():
    assert search.parse_date("") is None
    assert search.parse_date(None) is None
    assert search.parse_date("2026-07-08").isoformat() == "2026-07-08"
    for bad in ("not-a-date", "2026-13-40", "07/08/2026"):
        with pytest.raises(ValueError):
            search.parse_date(bad)


def test_search_raises_on_malformed_date(index):
    with pytest.raises(ValueError):
        search.search(index, "apple", date_from="garbage")


# --- snippets ----------------------------------------------------------------

def test_snippet_highlights_terms():
    out = search.make_snippet("Apple chips are great", {"chips"})
    assert "<mark>chips</mark>" in out


def test_snippet_is_html_safe():
    out = search.make_snippet("a < b & chips", {"chips"})
    assert "&lt;" in out and "&amp;" in out          # literal HTML escaped
    assert "<mark>chips</mark>" in out               # only the mark tag is raw


def test_snippet_browse_mode_returns_head_without_marks():
    assert search.make_snippet("hello world", set()) == "hello world"


# --- empty corpus ------------------------------------------------------------

def test_empty_corpus():
    empty = search.build_index([])
    assert empty["N"] == 0 and empty["postings"] == {}
    assert search.search(empty, "apple") == []
    assert search.search(empty, "") == []


# --- disk loading + topic reuse (integration) --------------------------------

def test_load_digests_reads_dates_and_reuses_topic_tags(tmp_path):
    (tmp_path / "digest-2026-01-01.md").write_text(
        "# WSJ Deep Digest\nBitcoin surged while Nvidia AI data-center demand grew.",
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text("ignore me", encoding="utf-8")  # non-digest file ignored
    docs = search.load_digests(str(tmp_path))
    assert len(docs) == 1
    assert docs[0]["date"] == "2026-01-01"
    assert "Crypto" in docs[0]["topics"] and "AI boom" in docs[0]["topics"]
    # and the index/search round-trips over it
    results = search.search(search.build_index(docs), "nvidia")
    assert results and results[0]["date"] == "2026-01-01"
