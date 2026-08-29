#!/usr/bin/env python3
"""
wsj_fetch.py — stage 1 of the digest tool.

Grabs the free headline/dek layer for three WSJ sections (Tech, Markets/Finance,
Personal Finance). PF doesn't have a public WSJ feed so I go through Google News
scoped to site:wsj.com.

No article bodies here (those are paywalled). Output is just a JSON list of
{section, title, dek, link, published} that stage 2 fills in.

  python3 wsj_fetch.py                 # print headline digest to stdout
  python3 wsj_fetch.py --json out.json # also dump structured JSON
  python3 wsj_fetch.py --limit 8       # cap per section (default 12)
  python3 wsj_fetch.py --research      # mode B: deepen via Claude web search,
                                       # writes digest-<date>.md (needs ANTHROPIC_API_KEY)
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

# Two feed types:
#   "wsj"   -> native WSJ RSS. has real deks but the CDN loves serving stale cache.
#   "gnews" -> Google News search. basically real-time, so this is my default.
# The dj.com feeds kept freezing on me, hence gnews everywhere below. If you want
# WSJ's own deks back, point a section at a feeds.a.dj.com url with type "wsj".
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
    text = TAG.sub("", text)          # kill any leftover html tags
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
            # gnews tacks " - WSJ" onto every title. strip it, ignore non-WSJ stuff.
            if "wsj.com" not in (item.findtext("{*}source") and item.find("{*}source").get("url", "") or "").lower() \
               and " - WSJ" not in title:
                # keep only WSJ-sourced results
                pass
            title = re.sub(r"\s*-\s*WSJ\s*$", "", title)
            dek = ""  # gnews description is just a link blob, useless
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
        # link the title itself so the page doesn't show raw urls
        if it["link"]:
            lines.append(f"- [{it['title']}]({it['link']})")
        else:
            lines.append(f"- **{it['title']}**")
        if it["dek"]:
            lines.append(f"  - {it['dek']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mode B: deepen each headline with Claude web search.
#
# WSJ bodies are paywalled so I never touch them. I just hand Claude the headline
# and let its web_search tool find the same story elsewhere (Reuters, AP,
# Bloomberg, CNBC...) and write a short sourced summary. Keeps everything on the
# legal side of the paywall.
# ---------------------------------------------------------------------------

# needs Opus 4.8 for the web_search_20260209 tool
RESEARCH_MODEL = "claude-opus-4-8"

RESEARCH_SYSTEM = (
    "You research a news headline and write a short, factual brief. The headline "
    "comes from The Wall Street Journal, but WSJ is paywalled: do NOT use or quote "
    "WSJ article text. Use the web_search tool to find the same story on OTHER "
    "outlets (Reuters, AP, Bloomberg, CNBC, etc.), then write 3-4 sentences with "
    "concrete numbers and dates.\n\n"
    "Reply with ONLY the brief itself, as a SINGLE paragraph on one line. Do not "
    "write a preamble, do not label it ('Brief:', 'Summary:'), and do not narrate "
    "your search process ('I have enough to write the brief', 'This confirms...', "
    "'Based on multiple outlets...'). Start directly with the first fact.\n\n"
    "End your answer with one line in exactly this form:\n"
    "SOURCES: <url1>, <url2>\n\n"
    "List 1-3 non-WSJ URLs you actually used. Never link wsj.com. If no other "
    "outlet covered the story (a WSJ exclusive or an advice column), say so in one "
    "sentence and give the SOURCES line as 'SOURCES: none'."
)


def split_summary_and_sources(text):
    """Cut the model's answer into (summary, [urls]).

    It's told to end with a 'SOURCES: ...' line, so I split there and pull the
    http links out of that line. Everything before it is the summary.
    """
    match = re.search(r"(?im)^\s*sources\s*:\s*(.+)\s*$", text)
    if not match:
        return text.strip(), []
    summary = text[:match.start()].strip()
    urls = re.findall(r"https?://\S+", match.group(1))
    urls = [u.rstrip(".,)") for u in urls if "wsj.com" not in u]  # drop wsj just in case
    return summary, urls


def research_headline(client, item):
    """Research one headline via Claude + web search.

    Returns the item with 'summary' and 'sources' filled in. If the API/network
    blows up it comes back with an 'error' string instead so one bad headline
    can't kill the whole run.
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
    except Exception as e:  # noqa — log it and move on
        return {**item, "summary": "", "sources": [], "error": str(e)}

    # answer lives in the text blocks; ignore the web-search blocks
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    summary, sources = split_summary_and_sources(text)
    return {**item, "summary": summary, "sources": sources, "error": None}


def research_to_markdown(researched):
    """Render the researched items as a dated markdown digest, grouped by section."""
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
    """Run mode B over every fetched headline, return the markdown.

    Skips a headline if something very similar was already covered in the last few
    days (see dedup.py). Ones that survive get researched and added to the store.
    """
    import anthropic  # lazy import so mode A works without the SDK installed
    import dedup

    client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY from the env
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

    dedup.save_store(dedup.prune_store(store))  # drop anything past the lookback window
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
