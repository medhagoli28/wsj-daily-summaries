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
  python3 wsj_fetch.py                 # print a markdown digest to stdout
  python3 wsj_fetch.py --json out.json # also write structured JSON
  python3 wsj_fetch.py --limit 8       # cap items per section (default 12)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12, help="items per section")
    ap.add_argument("--json", metavar="PATH", help="also write JSON here")
    args = ap.parse_args()

    digest = build(args.limit)
    print(to_markdown(digest))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(digest, f, indent=2)
        print(f"\n[wrote {len(digest)} items -> {args.json}]", file=sys.stderr)


if __name__ == "__main__":
    main()
