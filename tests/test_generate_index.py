"""Rendering tests for generate_index._parse_articles.

These exist because of a bug that was invisible for days: the digests had full
researched summaries in markdown, but every entry rendered on the site as a naked
headline. `research_to_markdown` writes "- **Title** — summary", and the parser
only treated "**Title** — summary" as researched — the "- " form fell through to
the bare-headline branch, which keeps the title and silently discards the body.

Nothing caught it because the pages looked structurally fine. So: pin both entry
shapes, and pin that the sources run never leaks into the visible body.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_index import _parse_articles


def test_dash_bullet_entry_keeps_its_summary():
    """The shape research_to_markdown actually emits. This is the regression."""
    md = "## Tech\n\n- **An AI Oracle's Rise and Fall** — Oracle became the bellwether.\n"
    articles = _parse_articles(md)
    assert len(articles) == 1
    assert articles[0]["title"] == "An AI Oracle's Rise and Fall"
    assert articles[0]["body"] == "Oracle became the bellwether."


def test_numbered_entry_still_parses():
    """The older interactive-digest shape must keep working."""
    md = "## Tech\n\n**1. Apple to Spend $30 Billion** — Apple announced the deal.\n"
    articles = _parse_articles(md)
    assert len(articles) == 1
    assert articles[0]["title"] == "Apple to Spend $30 Billion"
    assert articles[0]["body"] == "Apple announced the deal."


def test_sources_stripped_from_body_both_italic_styles():
    """Older digests italicise with '*', newer ones with '_'. Neither may leak."""
    for open_c, close_c in (("*", "*"), ("_", "_")):
        md = (f"## Tech\n\n- **T** — Body text here. "
              f"{open_c}Sources: <https://example.com/a>{close_c}\n")
        articles = _parse_articles(md)
        assert articles[0]["body"] == "Body text here.", (open_c, articles[0]["body"])
        assert "Sources" not in articles[0]["body"]


def test_bare_headline_has_no_body():
    """A headline-only entry should stay bodiless rather than invent one."""
    articles = _parse_articles("## Tech\n\n- **Just A Headline**\n")
    assert len(articles) == 1
    assert articles[0]["body"] == ""


def test_linked_headline_keeps_its_url():
    """The headline-only digest form carries a link instead of a summary."""
    articles = _parse_articles("## Tech\n\n- [Linked Headline](https://example.com/c)\n")
    assert len(articles) == 1
    assert articles[0]["url"] == "https://example.com/c"
    assert articles[0]["title"] == "Linked Headline"
