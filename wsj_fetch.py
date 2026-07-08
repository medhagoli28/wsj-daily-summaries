#!/usr/bin/env python3
"""
wsj_fetch.py — Stage 1 of the WSJ digest tool.

Pulls the free headline+dek layer for three WSJ sections:
  - Tech            (WSJ native RSS)
  - Markets/Finance (WSJ native RSS)
  - Personal Finance(Google News RSS filtered to site:wsj.com — no public WSJ PF feed)

It does NOT fetch article bodies (those are paywalled). Output is a clean JSON list
of {section, title, dek, link, published} that Stage 2 (Claude web research) deepens.

Usage:
  python3 wsj_fetch.py                 # Mode A: print a headline digest to stdout
  python3 wsj_fetch.py --json out.json # Mode A: also write structured JSON
  python3 wsj_fetch.py --limit 8       # cap items per section (default 12)
  python3 wsj_fetch.py --research      # Mode B: deepen each headline via Claude
                                       #   web search, write digest-<date>.md
                                       #   (needs ANTHROPIC_API_KEY in the env)
"""

import argparse
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# type "wsj"   -> native WSJ RSS (has <description> deks, but its CDN can serve stale cache)
# type "gnews" -> Google News RSS search (near-real-time WSJ headlines; recommended default)
#
# NOTE: the native WSJ feeds (feeds.a.dj.com) sometimes freeze on a stale cache, so we default
# to Google News queries scoped to site:wsj.com for reliable freshness. Swap a section back to
# type "wsj" with a feeds.a.dj.com URL if you want WSJ's own deks and the feed is fresh.
def gnews(query: str) -> str:
    import urllib.parse
    return ("https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-US&gl=US&ceid=US:en")

SECTIONS = {
    "Tech": {
        "type": "gnews",
        "url": gnews("site:wsj.com/tech when:4d"),
    },
    "Markets & Finance": {
        "type": "gnews",
        "url": gnews("stock market site:wsj.com when:4d"),
    },
    "Personal Finance": {
        "type": "gnews",
        "url": gnews('"personal finance" site:wsj.com when:7d'),
    },
}

TAG = re.compile(r"<[^>]+>")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def clean(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = TAG.sub("", text)          # strip any embedded HTML
    return re.sub(r"\s+", " ", text).strip()


def parse_items(xml_bytes: bytes, is_gnews: bool, section: str, limit: int):
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        dek = clean(item.findtext("description") or "")
        pub = (item.findtext("pubDate") or "").strip()

        if is_gnews:
            # Google News appends " - WSJ"; drop it and skip non-WSJ noise.
            if "wsj.com" not in (item.findtext("{*}source") and item.find("{*}source").get("url", "") or "").lower() \
               and " - WSJ" not in title:
                # keep only WSJ-sourced results
                pass
            title = re.sub(r"\s*-\s*WSJ\s*$", "", title)
            dek = ""  # Google News description is just a link blob; not useful
        if not title:
            continue
        out.append({
            "section": section,
            "title": title,
            "dek": dek,
            "link": link,
            "published": pub,
        })
        if len(out) >= limit:
            break
    return out


def build(limit: int):
    digest = []
    for section, cfg in SECTIONS.items():
        try:
            raw = fetch(cfg["url"])
            items = parse_items(raw, cfg["type"] == "gnews", section, limit)
            digest.extend(items)
        except Exception as e:  # noqa
            print(f"[warn] {section}: {e}", file=sys.stderr)
    return digest


def to_markdown(digest):
    lines = [f"# WSJ Section Digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
             "",
             "_Headlines + deks from the free RSS layer. Bodies are paywalled and not included._",
             ""]
    current = None
    for it in digest:
        if it["section"] != current:
            current = it["section"]
            lines.append(f"\n## {current}\n")
        lines.append(f"- **{it['title']}**")
        if it["dek"]:
            lines.append(f"  - {it['dek']}")
        if it["link"]:
            lines.append(f"  - <{it['link']}>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mode B — deepen each headline with Claude's web search.
#
# WSJ article bodies are paywalled, so we never read them. Instead we hand Claude
# just the headline and let its server-side web_search tool find the same story on
# other outlets (Reuters, AP, Bloomberg, CNBC, ...) and write a short, sourced
# summary. This keeps us on the free/legal side of the paywall.
# ---------------------------------------------------------------------------

# Opus 4.8 is required for the web_search_20260209 tool (dynamic filtering).
RESEARCH_MODEL = "claude-opus-4-8"

RESEARCH_SYSTEM = (
    "You research a news headline and write a short, factual brief. The headline "
    "comes from The Wall Street Journal, but WSJ is paywalled: do NOT use or quote "
    "WSJ article text. Use the web_search tool to find the same story on OTHER "
    "outlets (Reuters, AP, Bloomberg, CNBC, etc.), then write 3-4 sentences with "
    "concrete numbers and dates.\n\n"
    "End your answer with one line in exactly this form:\n"
    "SOURCES: <url1>, <url2>\n\n"
    "List 1-3 non-WSJ URLs you actually used. Never link wsj.com. If no other "
    "outlet covered the story (a WSJ exclusive or an advice column), say so in one "
    "sentence and give the SOURCES line as 'SOURCES: none'."
)


def split_summary_and_sources(text):
    """Split the model's answer into (summary, [urls]).

    The model is told to end with a 'SOURCES: ...' line; we cut the text there and
    pull the http links out of that line. Anything before it is the summary.
    """
    match = re.search(r"(?im)^\s*sources\s*:\s*(.+)\s*$", text)
    if not match:
        return text.strip(), []
    summary = text[:match.start()].strip()
    urls = re.findall(r"https?://\S+", match.group(1))
    urls = [u.rstrip(".,)") for u in urls if "wsj.com" not in u]  # defensively drop WSJ
    return summary, urls


def research_headline(client, item):
    """Research one headline via Claude + web search.

    Returns the item dict with 'summary' and 'sources' added. On any API/network
    error it returns the item with an 'error' string instead, so a single bad
    headline never aborts the whole run.
    """
    try:
        message = client.messages.create(
            model=RESEARCH_MODEL,
            max_tokens=1024,
            system=RESEARCH_SYSTEM,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}],
            messages=[{
                "role": "user",
                "content": f"Section: {item['section']}\nHeadline: {item['title']}",
            }],
        )
    except Exception as e:  # noqa — record the failure and keep going
        return {**item, "summary": "", "sources": [], "error": str(e)}

    # The final answer is in the 'text' blocks; web-search blocks are ignored here.
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    summary, sources = split_summary_and_sources(text)
    return {**item, "summary": summary, "sources": sources, "error": None}


def research_to_markdown(researched):
    """Render researched items as a dated Markdown digest, grouped by section."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# WSJ Deep Digest — {date}", "",
             "_Headlines selected by WSJ; summaries researched from non-WSJ sources._", ""]
    current = None
    for it in researched:
        if it["section"] != current:
            current = it["section"]
            lines.append(f"\n## {current}\n")
        if it.get("error"):
            lines.append(f"- **{it['title']}** — _(could not research: {it['error']})_")
            continue
        srcs = ""
        if it["sources"]:
            srcs = " _Sources: " + ", ".join(f"<{u}>" for u in it["sources"]) + "_"
        lines.append(f"- **{it['title']}** — {it['summary']}{srcs}")
    return "\n".join(lines)


def research(digest):
    """Run Mode B over every fetched headline and return the Markdown report.

    Cross-day de-dup: before researching a headline we skip it if a very similar
    headline was already covered in the last few days (see dedup.py). Headlines
    that pass the filter are researched and added to the store for next time.
    """
    import anthropic  # imported lazily so Mode A works without the SDK installed
    import dedup

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    store = dedup.load_store()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    researched = []
    for i, item in enumerate(digest, 1):
        title = item["title"]
        if dedup.is_duplicate(title, store):
            print(f"[{i}/{len(digest)}] skip (already covered): {title[:60]}", file=sys.stderr)
            continue
        print(f"[{i}/{len(digest)}] {title[:60]}", file=sys.stderr)
        researched.append(research_headline(client, item))
        store[title] = {"date": today}

    dedup.save_store(dedup.prune_store(store))  # drop entries past the lookback window
    return research_to_markdown(researched)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12, help="items per section")
    ap.add_argument("--json", metavar="PATH", help="also write JSON here")
    ap.add_argument("--research", action="store_true",
                    help="Mode B: deepen each headline via Claude web search")
    ap.add_argument("--out", metavar="PATH",
                    help="path for the Mode B digest (default: digest-<date>.md)")
    args = ap.parse_args()

    digest = build(args.limit)

    if args.research:
        report = research(digest)
        out = args.out or f"digest-{datetime.now(timezone.utc):%Y-%m-%d}.md"
        with open(out, "w") as f:
            f.write(report)
        print(f"[wrote {out}]", file=sys.stderr)
        return

    print(to_markdown(digest))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(digest, f, indent=2)
        print(f"\n[wrote {len(digest)} items -> {args.json}]", file=sys.stderr)


if __name__ == "__main__":
    main()
