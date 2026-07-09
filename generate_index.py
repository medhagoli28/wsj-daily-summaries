#!/usr/bin/env python3
"""Build a GitHub Pages site from the daily digests.

- index.html: a monthly calendar; each day with a digest is a clickable cell.
- digest-<date>.html: a dark "bubble" layout — each article is a cream card with
  a big number, a section-colored pill, the headline, the summary, and sources.

Plain Python + inline CSS — no frameworks, no dependencies.

Usage:
  python3 generate_index.py            # output into ./public
  python3 generate_index.py --out DIR  # choose the output directory
"""

import argparse
import calendar
import datetime
import glob
import html
import os
import re

FILENAME_RE = re.compile(r"^digest-(\d{4}-\d{2}-\d{2})\.md$")

SECTION_CLASSES = [("tech", "tech"), ("markets", "markets"), ("personal finance", "finance")]
PILL_LABEL = {"tech": "Tech", "markets": "Markets", "finance": "Finance"}
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

CSS = """
  :root { color-scheme: light dark;
          --tech: #2563eb; --markets: #059669; --finance: #d97706;
          --card: #fafafa; --border: #ececec; --muted: #6b7280; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         max-width: 740px; margin: 0 auto; padding: 2.5rem 1.1rem 4rem;
         line-height: 1.65; color: #1a1a1a; background: #fff; -webkit-font-smoothing: antialiased; }
  h1 { font-size: 2rem; line-height: 1.15; letter-spacing: -0.02em; margin: 0 0 .4rem; }
  .lead { color: var(--muted); margin: 0 0 1.4rem; font-size: .98rem; }
  a { color: var(--tech); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .back { display: inline-block; margin-bottom: 1.1rem; font-size: .9rem; color: var(--muted); }
  footer { margin-top: 2.5rem; color: #9aa0a6; font-size: .82rem; }

  /* Calendar index */
  table.cal { width: 100%; border-collapse: collapse; margin: 0 0 2.4rem; table-layout: fixed; }
  table.cal caption { caption-side: top; text-align: left; font-size: 1.3rem; font-weight: 700;
                      letter-spacing: -0.01em; margin-bottom: .6rem; }
  table.cal th { padding: .3rem .45rem; text-align: right; font-size: .68rem; font-weight: 600;
                 text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
  table.cal td { border: 1px solid var(--border); height: 84px; vertical-align: top; padding: .35rem .45rem; }
  table.cal td.empty { border-color: transparent; }
  table.cal td .num { font-size: .95rem; color: var(--muted); text-align: right; display: block; }
  table.cal td.has { background: rgba(37, 99, 235, .09); }
  table.cal td.has a { display: flex; flex-direction: column; height: 100%; }
  table.cal td.has .num { color: inherit; font-weight: 800; font-size: 1.15rem; }
  table.cal td.has .tag { margin-top: auto; font-size: .72rem; color: var(--tech); font-weight: 600; }
  @media (max-width: 560px) {
    table.cal td { height: 54px; padding: .25rem; }
    table.cal td.has .tag { display: none; } table.cal th { font-size: .58rem; }
  }

  /* Bubble digest page (dark) */
  body.digest { background: #201d1a; color: #e9e4da; max-width: 960px; }
  body.digest .back { color: #b8b0a4; }
  .mast { background: #efe9dc; color: #26221e; border-radius: 24px; padding: 2rem 2.1rem 1.6rem; margin: 0 0 1.4rem; }
  .mast-month { font-size: 3.2rem; font-weight: 800; letter-spacing: -0.03em; line-height: .9; text-transform: uppercase; }
  .mast-title { font-size: 1.5rem; font-weight: 800; letter-spacing: .02em; text-transform: uppercase; margin-top: .35rem; }
  .mast-sub { color: #6f6658; font-size: .92rem; margin-top: .45rem; font-style: italic; }
  .bubbles { column-count: 2; column-gap: 1.2rem; }
  .bubble { break-inside: avoid; -webkit-column-break-inside: avoid; display: inline-block; width: 100%;
            background: #efe9dc; color: #26221e; border-radius: 22px; padding: 1.4rem 1.5rem; margin: 0 0 1.2rem; }
  .bubble-head { display: flex; justify-content: space-between; align-items: flex-start; gap: .5rem; }
  .bubble-num { font-size: 3.4rem; font-weight: 800; line-height: .85; letter-spacing: -0.03em; }
  .bubble-pill { display: inline-block; background: #26221e; color: #efe9dc; border-radius: 7px;
                 padding: .3rem .7rem; font-size: .68rem; font-weight: 700; letter-spacing: .09em;
                 text-transform: uppercase; margin-top: .5rem; white-space: nowrap; }
  .bubble.tech .bubble-pill { background: var(--tech); }
  .bubble.markets .bubble-pill { background: var(--markets); }
  .bubble.finance .bubble-pill { background: var(--finance); }
  .bubble-kicker { font-style: italic; text-transform: uppercase; font-size: .76rem; letter-spacing: .03em;
                   color: #8a7f6d; margin: .9rem 0 .15rem; }
  .bubble-title { font-size: 1.16rem; font-weight: 800; line-height: 1.25; margin: .15rem 0 .55rem; }
  .bubble-title a { color: inherit; }
  .bubble-body { font-size: .95rem; line-height: 1.55; color: #3a352e; margin: 0; }
  .bubble-sources { font-size: .8rem; color: #8a7f6d; margin: .8rem 0 0; }
  .bubble-sources a { color: #7a663f; }
  @media (max-width: 640px) { .bubbles { column-count: 1; } .mast-month { font-size: 2.4rem; } }

  @media (prefers-color-scheme: dark) {
    :root { --card: #161b22; --border: #24292f; --muted: #9198a1; }
    body { color: #e6e6e6; background: #0d1117; }
    a { color: #6ea8fe; }
    table.cal td.has { background: rgba(110, 168, 254, .14); }
  }
"""


def find_digests():
    """Return (date, md_filename) pairs for every digest-<date>.md, newest first."""
    found = []
    for path in glob.glob("digest-*.md"):
        name = os.path.basename(path)
        m = FILENAME_RE.match(name)
        if m:
            found.append((datetime.date.fromisoformat(m.group(1)), name))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return found


def pretty_date(d):
    return f"{d:%B} {d.day}, {d.year}"


def _section_class(text):
    low = text.lower()
    for needle, cls in SECTION_CLASSES:
        if needle in low:
            return cls
    return ""


def _strip_emoji(text):
    return re.sub(r"^[^\w]+", "", text).strip()


def _inline(text):
    """Inline Markdown in an already-HTML-escaped string -> HTML."""
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def _page(title, body, body_class=""):
    cls = f' class="{body_class}"' if body_class else ""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{html.escape(title)}</title>\n"
        f"  <style>{CSS}</style>\n</head>\n<body{cls}>\n{body}\n</body>\n</html>\n"
    )


# --- digest page (bubble layout) --------------------------------------------

def _parse_articles(md):
    """Parse a digest's Markdown into a list of article dicts, in order.

    Handles both formats: researched (`**N. Title** *(tag)* — body *Sources: ...*`)
    and free headline days (`- [Title](url)`).
    """
    articles, section, sec_cls = [], "", ""
    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section, sec_cls = _strip_emoji(line[3:]), _section_class(line[3:])
            continue

        m = re.match(r"^\*\*\s*(?:\d+\.\s*)?(.+?)\s*\*\*\s*(.*)$", line)   # researched
        if m:
            title, rest = m.group(1), m.group(2)
            kicker = ""
            t = re.match(r"^\*\(([^)]+)\)\*\s*(.*)$", rest)               # optional *(tag)*
            if t:
                kicker, rest = t.group(1), t.group(2)
            rest = re.sub(r"^[—–\-]\s*", "", rest)             # strip leading dash
            sources, body = [], rest.strip()
            sm = re.search(r"\*Sources:\s*(.+?)\*\s*$", rest)
            if sm:
                sources = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", sm.group(1))
                body = rest[: sm.start()].strip()
            articles.append({"section": section, "cls": sec_cls, "title": title,
                             "url": None, "kicker": kicker, "body": body, "sources": sources})
            continue

        hm = re.match(r"^- \[([^\]]+)\]\((https?://[^)]+)\)", line)        # headline w/ link
        if hm:
            articles.append({"section": section, "cls": sec_cls, "title": hm.group(1),
                             "url": hm.group(2), "kicker": "", "body": "", "sources": []})
            continue
        hm = re.match(r"^- \*\*(.+?)\*\*", line)                           # headline, no link
        if hm:
            articles.append({"section": section, "cls": sec_cls, "title": hm.group(1),
                             "url": None, "kicker": "", "body": "", "sources": []})
    return articles


def _bubble(n, a):
    pill = PILL_LABEL.get(a["cls"]) or a["section"] or "WSJ"
    title = _inline(html.escape(a["title"]))
    if a["url"]:
        title = f'<a href="{html.escape(a["url"])}">{title}</a>'
    kicker = f'<div class="bubble-kicker">{html.escape(a["kicker"])}</div>' if a["kicker"] else ""
    body = f'<p class="bubble-body">{_inline(html.escape(a["body"]))}</p>' if a["body"] else ""
    src = ""
    if a["sources"]:
        links = ", ".join(f'<a href="{html.escape(u)}">{html.escape(name)}</a>' for name, u in a["sources"])
        src = f'<p class="bubble-sources">Sources: {links}</p>'
    return (
        f'<div class="bubble {a["cls"]}">'
        f'<div class="bubble-head"><span class="bubble-num">{n}</span>'
        f'<span class="bubble-pill">{html.escape(pill)}</span></div>'
        f"{kicker}<div class=\"bubble-title\">{title}</div>{body}{src}</div>"
    )


def render_digest_page(md_text, date):
    articles = _parse_articles(md_text)
    cards = "\n".join(_bubble(i, a) for i, a in enumerate(articles, 1))
    mast = (
        f'<header class="mast"><div class="mast-month">{date:%B} {date.day}</div>'
        f'<div class="mast-title">WSJ Digest</div>'
        f'<div class="mast-sub">{date.year} — researched from non-WSJ sources</div></header>'
    )
    body = f'<a class="back" href="index.html">← calendar</a>\n{mast}\n<div class="bubbles">\n{cards}\n</div>'
    return _page(f"WSJ Digest — {pretty_date(date)}", body, body_class="digest")


# --- index page (calendar) --------------------------------------------------

def _month_calendar(year, month, digest_dates):
    cal = calendar.Calendar(firstweekday=6)  # Sunday-first
    head = "".join(f"<th>{d}</th>" for d in WEEKDAYS)
    rows = []
    for week in cal.monthdayscalendar(year, month):
        cells = []
        for day in week:
            if day == 0:
                cells.append('<td class="empty"></td>')
                continue
            iso = f"{year:04d}-{month:02d}-{day:02d}"
            if iso in digest_dates:
                cells.append(
                    f'<td class="has"><a href="digest-{iso}.html">'
                    f'<span class="num">{day}</span><span class="tag">Digest →</span></a></td>'
                )
            else:
                cells.append(f'<td><span class="num">{day}</span></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    caption = f"{calendar.month_name[month]} {year}"
    return (
        f'<table class="cal"><caption>{caption}</caption>\n'
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody></table>"
    )


def render_index(digests):
    digest_dates = {d.isoformat() for d, _ in digests}
    months = sorted({(d.year, d.month) for d, _ in digests}, reverse=True)
    cals = "\n".join(_month_calendar(y, m, digest_dates) for y, m in months) if months \
        else "<p class='lead'>No digests yet.</p>"
    body = (
        "  <h1>WSJ Deep Digest</h1>\n"
        '  <p class="lead">Daily summaries — headlines from WSJ, depth researched from other outlets. '
        "Pick a highlighted day.</p>\n"
        f"{cals}\n"
        "  <footer>Generated automatically. No paywalled WSJ text is reproduced.</footer>"
    )
    return _page("WSJ Deep Digest", body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="public", help="output directory (default: public)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    digests = find_digests()

    for date, name in digests:
        md_text = open(name, encoding="utf-8").read()
        with open(os.path.join(args.out, f"digest-{date.isoformat()}.html"), "w", encoding="utf-8") as f:
            f.write(render_digest_page(md_text, date))

    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(digests))

    print(f"[wrote {args.out}/index.html + {len(digests)} digest page(s)]")


if __name__ == "__main__":
    main()
