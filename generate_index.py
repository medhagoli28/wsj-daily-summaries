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
import shutil

FILENAME_RE = re.compile(r"^digest-(\d{4}-\d{2}-\d{2})\.md$")

SECTION_CLASSES = [("tech", "tech"), ("markets", "markets"), ("personal finance", "finance")]
PILL_LABEL = {"tech": "Tech", "markets": "Markets", "finance": "Finance"}
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

# Recurring "threads" — a digest joins a thread when its text matches any keyword.
# Days that share a thread get cross-linked so readers can follow a story over time.
TOPIC_RULES = [
    ("AI boom", ["artificial intelligence", "hyperscaler", "openai", "anthropic",
                 "nvidia", "claude", "chatgpt", "data center", "capex", "zhipu", "llm"]),
    ("Iran & oil", ["iran", "ceasefire", "hormuz", "israel", "middle east", "crude", "brent"]),
    ("Crypto", ["bitcoin", "btc", "crypto", "microstrategy", "ethereum", "stablecoin"]),
    ("Tariffs & trade", ["tariff", "trade war", "liberation day", "import duty"]),
    ("Fed & rates", ["federal reserve", "interest rate", "treasury yield", "bond yield", "rate cut"]),
    ("IPOs & listings", ["ipo", "nasdaq-100", "market debut", "public offering", "share placement"]),
    ("Chips", ["chip", "semiconductor", "samsung", "sk hynix", "broadcom", "tsmc", "memory"]),
    ("Deals & M&A", ["acquisition", "takeover", "merger", "buyout", "private equity", "commerzbank"]),
]
_TOPIC_RES = [(label, [re.compile(rf"\b{re.escape(k)}\b", re.I) for k in kws])
              for label, kws in TOPIC_RULES]


def digest_topics(md_text):
    """Return the set of thread labels a digest matches, based on its text."""
    return {label for label, pats in _TOPIC_RES if any(p.search(md_text) for p in pats)}

CSS = """
  @font-face { font-family: "Lumiare"; src: url("fonts/Lumiare.otf") format("opentype"); font-display: swap; }
  @font-face { font-family: "Dealerplate California"; src: url("fonts/DealerplateCalifornia.otf") format("opentype"); font-display: swap; }
  :root { color-scheme: dark;
          --tech: #6ea8fe; --markets: #34d399; --finance: #fbbf24;
          --accent: #6ea8fe; --border: #35302a; --muted: #9b9187; }
  * { box-sizing: border-box; }
  body { font-family: "Dealerplate California", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         max-width: 740px; margin: 0 auto; padding: 2.5rem 1.1rem 4rem;
         line-height: 1.65; color: #e9e4da; background: #201d1a; -webkit-font-smoothing: antialiased; }
  h1, h2, h3, table.cal caption, .mast-month, .mast-title, .bubble-title {
    font-family: "Lumiare", Georgia, "Times New Roman", serif; }
  h1 { font-size: 2rem; line-height: 1.15; letter-spacing: -0.02em; margin: 0 0 .4rem; }
  .lead { color: var(--muted); margin: 0 0 1.4rem; font-size: .98rem; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .back { display: inline-block; margin-bottom: 1.1rem; font-size: .9rem; color: var(--muted); }
  footer { margin-top: 2.5rem; color: #6f6658; font-size: .82rem; }

  /* Top-right search bar on the index */
  .topbar { display: flex; justify-content: space-between; align-items: center; gap: 1rem;
            flex-wrap: wrap; margin: 0 0 .5rem; }
  .topbar h1 { margin: 0; }
  .topsearch input { font: inherit; color: #e9e4da; background: #2a2521; border: 1px solid #4a453e;
                     border-radius: 999px; padding: .5rem 1rem; min-width: 210px; }
  .topsearch input:focus { outline: none; border-color: var(--accent); }
  @media (max-width: 520px) { .topsearch, .topsearch input { width: 100%; } }

  /* "Read the latest" hero on the index */
  .hero-latest { display: inline-flex; align-items: baseline; gap: .55rem; margin: 0 0 2rem;
                 background: #efe9dc; color: #26221e; border-radius: 14px; padding: .85rem 1.25rem;
                 font-weight: 700; font-size: 1.02rem; }
  .hero-latest:hover { text-decoration: none; opacity: .93; }
  .hero-latest .hero-date { color: #6f6658; font-weight: 600; font-size: .9rem; }

  /* Calendar index */
  table.cal { width: 100%; border-collapse: collapse; margin: 0 0 2.4rem; table-layout: fixed; }
  table.cal caption { caption-side: top; text-align: left; font-size: 1.3rem; font-weight: 700;
                      letter-spacing: -0.01em; margin-bottom: .6rem; }
  table.cal th { padding: .3rem .45rem; text-align: right; font-size: .68rem; font-weight: 600;
                 text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
  table.cal td { border: 1px solid var(--border); height: 84px; vertical-align: top; padding: .35rem .45rem; }
  table.cal td.empty { border-color: transparent; }
  table.cal td .num { font-size: .95rem; color: var(--muted); text-align: right; display: block; }
  /* days with a digest stay clickable, but are not "highlighted" */
  table.cal td.has a { display: flex; flex-direction: column; height: 100%; }
  table.cal td.has .num { color: var(--accent); font-weight: 700; }
  table.cal td.has .tag { margin-top: auto; font-size: .72rem; color: var(--accent); font-weight: 600; }
  /* only the current date is highlighted */
  table.cal td.today { background: rgba(110, 168, 254, .14); }
  table.cal td.today .num { font-weight: 800; font-size: 1.15rem; }
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
  .filters { display: flex; flex-wrap: wrap; gap: .5rem; margin: 0 0 1.4rem; }
  .filter-btn { font: inherit; cursor: pointer; -webkit-appearance: none; border: 1px solid #4a453e;
                background: transparent; color: #d9d2c6; border-radius: 999px; padding: .4rem .95rem;
                font-size: .82rem; font-weight: 600; letter-spacing: .02em; }
  .filter-btn:hover { border-color: #7a7266; }
  .filter-btn.is-active { background: #efe9dc; color: #26221e; border-color: #efe9dc; }
  .bubble[hidden] { display: none; }
  .bubbles { column-count: 2; column-gap: 1.2rem; }
  .bubble { break-inside: avoid; -webkit-column-break-inside: avoid; display: inline-block; width: 100%;
            background: #efe9dc; color: #26221e; border-radius: 22px; padding: 1.4rem 1.5rem; margin: 0 0 1.2rem; }
  .bubble-head { display: flex; justify-content: flex-start; align-items: flex-start; gap: .5rem; }
  .bubble-pill { display: inline-block; background: #26221e; color: #efe9dc; border-radius: 7px;
                 padding: .3rem .7rem; font-size: .68rem; font-weight: 700; letter-spacing: .09em;
                 text-transform: uppercase; white-space: nowrap; }
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

  /* prev / next-day navigation */
  .daynav { display: flex; justify-content: space-between; gap: .75rem; margin: 2.2rem 0 0; }
  .daynav a { flex: 1; background: #2b2723; border: 1px solid #3a352e; border-radius: 14px;
              padding: .75rem 1rem; color: #e9e4da; }
  .daynav a:hover { text-decoration: none; border-color: #6f6658; }
  .daynav .dn-next { text-align: right; }
  .daynav .dn-label { display: block; font-size: .7rem; text-transform: uppercase; letter-spacing: .08em;
                      color: #8a7f6d; }
  .daynav .dn-date { font-weight: 700; }
  .daynav .dn-spacer { flex: 1; }
  /* recurring "threads" cross-links */
  .threads { margin: 2rem 0 0; }
  .threads-h { font-size: .72rem; text-transform: uppercase; letter-spacing: .09em; color: #8a7f6d;
               margin: 0 0 .7rem; }
  .thread { background: #2b2723; border: 1px solid #3a352e; border-radius: 12px; padding: .7rem .95rem;
            margin: 0 0 .6rem; font-size: .9rem; }
  .thread-label { font-weight: 700; color: #efe9dc; margin-right: .5rem; }
  .thread a { margin-right: .7rem; white-space: nowrap; }
  .filter-btn .fc { opacity: .6; font-weight: 600; margin-left: .35rem; }
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
        f'<div class="bubble {a["cls"]}" data-cat="{a["cls"] or "other"}">'
        f'<div class="bubble-head"><span class="bubble-pill">{html.escape(pill)}</span></div>'
        f"{kicker}<div class=\"bubble-title\">{title}</div>{body}{src}</div>"
    )


def _filter_bar(articles):
    """Filter buttons (with counts) for the categories actually present."""
    counts = {}
    for a in articles:
        counts[a["cls"]] = counts.get(a["cls"], 0) + 1
    total = len(articles)
    buttons = ['<button class="filter-btn is-active" data-filter="all" aria-pressed="true">'
               f'All<span class="fc">{total}</span></button>']
    for _, cls in SECTION_CLASSES:
        if counts.get(cls):
            buttons.append(f'<button class="filter-btn" data-filter="{cls}" aria-pressed="false">'
                           f'{PILL_LABEL[cls]}<span class="fc">{counts[cls]}</span></button>')
    if len(buttons) < 3:            # nothing meaningful to filter by
        return ""
    return ('<div class="filters" role="group" aria-label="Filter by category">'
            + "".join(buttons) + "</div>")


FILTER_JS = """
(function () {
  var bar = document.querySelector('.filters');
  if (!bar) return;
  var cards = document.querySelectorAll('.bubble');
  var buttons = bar.querySelectorAll('.filter-btn');
  function apply(f, push) {
    var matched = false;
    buttons.forEach(function (b) {
      var on = b.getAttribute('data-filter') === f;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on) matched = true;
    });
    if (!matched) { f = 'all'; buttons[0].classList.add('is-active');
                    buttons[0].setAttribute('aria-pressed', 'true'); }
    cards.forEach(function (c) {
      c.hidden = !(f === 'all' || c.getAttribute('data-cat') === f);
    });
    if (push) {
      var h = f === 'all' ? ' ' : '#' + f;
      history.replaceState(null, '', h === ' ' ? location.pathname + location.search : h);
    }
  }
  bar.addEventListener('click', function (e) {
    var btn = e.target.closest('.filter-btn');
    if (btn) apply(btn.getAttribute('data-filter'), true);
  });
  apply((location.hash || '').replace('#', '') || 'all', false);
  window.addEventListener('hashchange', function () {
    apply((location.hash || '').replace('#', '') || 'all', false);
  });
})();
"""


def _daynav(older, newer):
    """Prev/next links between digest days (older on the left, newer on the right)."""
    if not older and not newer:
        return ""
    if older:
        left = (f'<a class="dn-prev" href="digest-{older.isoformat()}.html">'
                f'<span class="dn-label">← Older</span>'
                f'<span class="dn-date">{older:%b} {older.day}</span></a>')
    else:
        left = '<span class="dn-spacer"></span>'
    if newer:
        right = (f'<a class="dn-next" href="digest-{newer.isoformat()}.html">'
                 f'<span class="dn-label">Newer →</span>'
                 f'<span class="dn-date">{newer:%b} {newer.day}</span></a>')
    else:
        right = '<span class="dn-spacer"></span>'
    return f'<nav class="daynav">{left}{right}</nav>'


def _threads_block(threads):
    """threads: list of (label, [other dates]) sharing a recurring topic with this day."""
    if not threads:
        return ""
    rows = []
    for label, dates in threads:
        links = "".join(f'<a href="digest-{d.isoformat()}.html">{d:%b %-d}</a>'
                        for d in sorted(dates, reverse=True))
        rows.append(f'<div class="thread"><span class="thread-label">{html.escape(label)}</span>'
                    f'<span class="thread-days">also on {links}</span></div>')
    return ('<section class="threads"><h2 class="threads-h">Recurring threads</h2>'
            + "".join(rows) + "</section>")


def render_digest_page(md_text, date, older=None, newer=None, threads=None):
    articles = _parse_articles(md_text)
    cards = "\n".join(_bubble(i, a) for i, a in enumerate(articles, 1))
    mast = (
        f'<header class="mast"><div class="mast-month">{date:%B} {date.day}</div>'
        f'<div class="mast-title">WSJ Digest</div>'
        f'<div class="mast-sub">{date.year} — researched from non-WSJ sources</div></header>'
    )
    filters = _filter_bar(articles)
    body = (f'<a class="back" href="index.html">← calendar</a>\n{mast}\n{filters}\n'
            f'<div class="bubbles">\n{cards}\n</div>\n'
            f'{_threads_block(threads)}\n{_daynav(older, newer)}\n<script>{FILTER_JS}</script>')
    return _page(f"WSJ Digest — {pretty_date(date)}", body, body_class="digest")


# --- index page (calendar) --------------------------------------------------

def _month_calendar(year, month, digest_dates, today=None):
    cal = calendar.Calendar(firstweekday=6)  # Sunday-first
    head = "".join(f"<th>{d}</th>" for d in WEEKDAYS)
    today_iso = today.isoformat() if today else None
    rows = []
    for week in cal.monthdayscalendar(year, month):
        cells = []
        for day in week:
            if day == 0:
                cells.append('<td class="empty"></td>')
                continue
            iso = f"{year:04d}-{month:02d}-{day:02d}"
            classes = []
            if iso in digest_dates:
                classes.append("has")
            if iso == today_iso:
                classes.append("today")
            cls = f' class="{" ".join(classes)}"' if classes else ""
            if iso in digest_dates:
                cells.append(
                    f'<td{cls}><a href="digest-{iso}.html">'
                    f'<span class="num">{day}</span><span class="tag">Digest →</span></a></td>'
                )
            else:
                cells.append(f'<td{cls}><span class="num">{day}</span></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    caption = f"{calendar.month_name[month]} {year}"
    return (
        f'<table class="cal"><caption>{caption}</caption>\n'
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody></table>"
    )


def render_index(digests):
    digest_dates = {d.isoformat() for d, _ in digests}
    today = datetime.datetime.now(datetime.timezone.utc).date()
    months = sorted({(d.year, d.month) for d, _ in digests} | {(today.year, today.month)}, reverse=True)
    cals = "\n".join(_month_calendar(y, m, digest_dates, today) for y, m in months) if months \
        else "<p class='lead'>No digests yet.</p>"
    hero = ""
    if digests:
        latest = digests[0][0]
        hero = (f'  <a class="hero-latest" href="digest-{latest.isoformat()}.html">'
                f'Read the latest digest → <span class="hero-date">{pretty_date(latest)}</span></a>\n')
    body = (
        '  <div class="topbar"><h1>WSJ Deep Digest</h1>\n'
        '    <form class="topsearch" action="search.html" method="get" role="search">\n'
        '      <input type="search" name="q" placeholder="Search the archive…" aria-label="Search the archive">\n'
        "    </form></div>\n"
        '  <p class="lead">Daily summaries — headlines from WSJ, depth researched from other outlets. '
        "Pick a highlighted day.</p>\n"
        f"{hero}{cals}\n"
        "  <footer>Generated automatically. No paywalled WSJ text is reproduced.</footer>"
    )
    return _page("WSJ Deep Digest", body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="public", help="output directory (default: public)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # publish the custom fonts alongside the pages (referenced by @font-face)
    fonts_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    if os.path.isdir(fonts_src):
        shutil.copytree(fonts_src, os.path.join(args.out, "fonts"), dirs_exist_ok=True)

    digests = find_digests()   # newest first

    # First pass: read text + derive each day's recurring-topic labels.
    texts = {date: open(name, encoding="utf-8").read() for date, name in digests}
    topics = {date: digest_topics(texts[date]) for date, _ in digests}
    topic_days = {}
    for date, labels in topics.items():
        for label in labels:
            topic_days.setdefault(label, set()).add(date)

    for i, (date, _) in enumerate(digests):
        newer = digests[i - 1][0] if i > 0 else None
        older = digests[i + 1][0] if i < len(digests) - 1 else None
        threads = []
        for label in topics[date]:
            others = topic_days[label] - {date}
            if others:
                threads.append((label, others))
        # strongest threads first (shared by the most days), then alphabetical; keep it tidy
        threads.sort(key=lambda t: (-len(t[1]), t[0]))
        threads = threads[:5]
        with open(os.path.join(args.out, f"digest-{date.isoformat()}.html"), "w", encoding="utf-8") as f:
            f.write(render_digest_page(texts[date], date, older=older, newer=newer, threads=threads))

    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(digests))

    # Stable bookmarkable URL that always points at the newest digest.
    if digests:
        latest_iso = digests[0][0].isoformat()
        redirect = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url=digest-{latest_iso}.html">'
            f'<link rel="canonical" href="digest-{latest_iso}.html">'
            '<title>Latest WSJ Deep Digest</title></head>'
            f'<body><a href="digest-{latest_iso}.html">Latest digest →</a></body></html>\n'
        )
        with open(os.path.join(args.out, "latest.html"), "w", encoding="utf-8") as f:
            f.write(redirect)

    print(f"[wrote {args.out}/index.html + latest.html + {len(digests)} digest page(s)]")


if __name__ == "__main__":
    main()
