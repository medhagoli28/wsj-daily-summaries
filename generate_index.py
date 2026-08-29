#!/usr/bin/env python3
"""Build the GitHub Pages site from the daily digests. Going for a newspaper look.

Two kinds of page:
- index.html          "The Archive": masthead, today's lead + also-inside, a
                      month calendar of past issues, recurring threads.
- digest-<date>.html  "The Issue": dated masthead, category tabs, the day's
                      stories in a two-column layout with a sidebar TOC and threads.

Cream palette, Newsreader serif. Just Python + inline CSS + one tiny filter
script. No frameworks, no build step past this file.

  python3 generate_index.py            # output into ./public
  python3 generate_index.py --out DIR
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
CAT_LABEL = {"tech": "Tech", "markets": "Markets", "finance": "Finance"}
CAT_COLOR = {"tech": "#8a5a2b", "markets": "#2f5d3a", "finance": "#5a4a8a"}
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

# Recurring "threads": a digest joins a thread if its text hits any of the keywords.
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
    """Which thread labels does this digest match?"""
    return {label for label, pats in _TOPIC_RES if any(p.search(md_text) for p in pats)}


CSS = """
  :root { --paper:#f6f1e6; --outer:#e5e1d6; --panel:#efe8d8; --ink:#1c1a15;
          --body:#413d33; --mut:#5a554a; --mut2:#7c7568; --faint:#a49b86;
          --rule:#d8cfbd; --rule2:#d3c9b4; --brown:#8a5a2b; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--outer); color:var(--ink);
         font-family:'Newsreader',Georgia,'Times New Roman',serif; -webkit-font-smoothing:antialiased; }
  a { color:inherit; text-decoration:none; }
  a:hover { text-decoration:underline; }
  ::selection { background:#e9d9bf; }
  .sans { font-family:system-ui,-apple-system,'Segoe UI',sans-serif; }
  .paper { max-width:1000px; margin:0 auto; background:var(--paper); min-height:100vh;
           box-shadow:0 0 40px rgba(0,0,0,.12); }

  /* masthead */
  .mast { padding:26px 44px 20px; text-align:center; border-bottom:2px solid var(--ink); }
  .mast-top { display:flex; justify-content:space-between; align-items:center;
              font:500 10.5px/1 system-ui,sans-serif; letter-spacing:.16em; text-transform:uppercase; color:var(--brown); }
  .mast-title { font-weight:600; font-size:56px; letter-spacing:-.01em; margin:14px 0 9px; }
  .mast-sub { font:400 12px/1.5 system-ui,sans-serif; letter-spacing:.24em; text-transform:uppercase; color:var(--mut); }

  /* nav / search bar */
  .navbar { display:flex; align-items:center; justify-content:space-between; padding:11px 44px;
            border-bottom:1px solid var(--rule); background:var(--panel); gap:12px; flex-wrap:wrap; }
  .navtabs { display:flex; gap:22px; font:500 12px/1 system-ui,sans-serif; }
  .navtabs span { color:var(--mut2); }
  .navtabs .on { color:var(--ink); border-bottom:2px solid var(--ink); padding-bottom:3px; }
  .searchbox { display:flex; align-items:center; gap:8px; border:1px solid #c9bfa8; border-radius:2px;
               padding:6px 11px; background:var(--paper); font:400 12px system-ui,sans-serif; color:#8a8375;
               min-width:210px; }
  .searchbox input { border:0; background:transparent; font:inherit; color:var(--ink); width:100%; outline:none; }

  /* lead + also-inside */
  .lead-grid { display:grid; grid-template-columns:1.55fr 1fr; }
  .lead { padding:30px 38px 32px; border-right:1px solid var(--rule); }
  .kicker { font:600 10.5px/1 system-ui,sans-serif; letter-spacing:.16em; text-transform:uppercase;
            color:var(--brown); margin-bottom:12px; }
  .lead-title { font-weight:700; font-size:40px; line-height:1.04; letter-spacing:-.015em; margin-bottom:14px; }
  .lead-sum { font-size:17px; line-height:1.5; color:var(--body); }
  .lead-btn { display:inline-flex; gap:8px; margin-top:18px; font:600 10px/1 system-ui,sans-serif;
              letter-spacing:.1em; text-transform:uppercase; padding:9px 13px; background:var(--ink); color:var(--paper); }
  .lead-btn:hover { text-decoration:none; opacity:.92; }
  .also { padding:28px 32px; }
  .also-h { font:600 10.5px/1 system-ui,sans-serif; letter-spacing:.16em; text-transform:uppercase;
            color:var(--mut); margin-bottom:14px; }
  .also-item { border-top:1px solid var(--rule); padding-top:11px; margin-bottom:13px; display:block; }
  .also-cat { font:600 9px/1 system-ui,sans-serif; letter-spacing:.08em; text-transform:uppercase; }
  .also-title { font-size:17px; line-height:1.2; font-weight:600; margin-top:3px; }

  /* archive calendar */
  .archive { padding:24px 44px 18px; border-top:2px solid var(--ink); background:var(--panel); }
  .archive + .archive { border-top:1px solid var(--rule); }
  .archive-head { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:14px; }
  .archive-title { font-weight:600; font-size:23px; }
  .archive-meta { font:400 11px system-ui,sans-serif; color:var(--mut2); letter-spacing:.04em; }
  .weekhead { display:grid; grid-template-columns:repeat(7,1fr); gap:2px 8px; text-align:center;
              font:600 10px/1 system-ui,sans-serif; letter-spacing:.1em; text-transform:uppercase;
              color:var(--faint); margin-bottom:7px; }
  .caldays { display:grid; grid-template-columns:repeat(7,1fr); gap:8px; }
  .cell { min-height:60px; padding-top:5px; }
  .cell .cnum { font-size:14px; }
  .cell .chead { font:500 10.5px/1.2 system-ui,sans-serif; color:#4a4638; margin-top:3px; }
  .cell.blank { border-top:1px solid var(--rule2); color:#c3b9a3; }
  .cell.has { border-top:1.5px solid var(--ink); }
  .cell.has .cnum { font-weight:600; }
  .cell.lead { border-top:2.5px solid var(--brown); background:var(--paper); }
  .cell.lead .cnum { font-weight:700; color:var(--brown); }
  .cell.lead .chead { color:var(--ink); font-weight:600; }
  .cell a { display:block; }
  .cell a:hover { text-decoration:none; }
  .cell a:hover .chead { text-decoration:underline; }

  /* recurring threads (landing) */
  .threads { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:16px 0 6px;
             border-top:1px solid var(--rule); margin-top:12px; }
  .threads-label { font:600 10px/1 system-ui,sans-serif; letter-spacing:.12em; text-transform:uppercase;
                   color:var(--mut2); margin-right:4px; }
  .thread { font-style:italic; font-size:15px; border-bottom:1px solid var(--brown); }

  /* issue page */
  .crumb { display:flex; align-items:center; justify-content:space-between; padding:12px 44px;
           border-bottom:1px solid var(--rule); font:500 11px/1 system-ui,sans-serif;
           letter-spacing:.04em; color:var(--mut2); gap:10px; }
  .crumb a { color:var(--brown); }
  .crumb .mid { letter-spacing:.16em; text-transform:uppercase; }
  .issue-mast { padding:34px 44px 22px; text-align:center; border-bottom:2px solid var(--ink); }
  .issue-kicker { font:500 11px/1 system-ui,sans-serif; letter-spacing:.22em; text-transform:uppercase;
                  color:var(--brown); margin-bottom:14px; }
  .issue-date { font-weight:700; font-size:60px; line-height:.98; letter-spacing:-.02em; }
  .issue-sub { font-style:italic; font-size:18px; color:var(--mut); margin-top:12px; }
  .tabbar { display:flex; align-items:center; justify-content:space-between; padding:12px 44px;
            border-bottom:1px solid var(--rule); background:var(--panel); position:sticky; top:0; z-index:5;
            gap:12px; flex-wrap:wrap; }
  .tabs { display:flex; gap:8px; font:500 12px/1 system-ui,sans-serif; }
  .tab { cursor:pointer; padding:6px 12px; border-radius:2px; border:1px solid #c9bfa8; background:transparent; color:var(--ink); }
  .tab.on { background:var(--ink); color:var(--paper); border-color:var(--ink); }
  .issue-grid { display:grid; grid-template-columns:1.7fr 1fr; }
  .articles { padding:30px 38px 34px; border-right:1px solid var(--rule); }
  .article { padding:0 0 22px; margin-bottom:22px; border-bottom:1px solid var(--rule); }
  .article:last-child { border-bottom:0; margin-bottom:0; }
  .art-cat { font:600 10px/1 system-ui,sans-serif; letter-spacing:.14em; text-transform:uppercase; margin-bottom:8px; }
  .art-title { font-weight:700; font-size:25px; line-height:1.1; margin-bottom:9px; }
  .art-title a:hover { text-decoration:underline; }
  .art-sum { font-size:15.5px; line-height:1.56; color:var(--body); }
  .art-kicker { font-style:italic; color:var(--mut); }
  .sidebar { padding:30px; background:var(--panel); }
  .sidebar-sticky { position:sticky; top:72px; }
  .side-h { font:600 10px/1 system-ui,sans-serif; letter-spacing:.14em; text-transform:uppercase;
            color:var(--mut2); margin-bottom:14px; }
  .toc { display:flex; flex-direction:column; gap:9px; margin-bottom:26px; }
  .toc-item { display:flex; gap:9px; align-items:baseline; border-bottom:1px solid var(--rule2); padding-bottom:8px; }
  .toc-n { font:600 10px system-ui,sans-serif; width:14px; flex:none; }
  .toc-t { font-size:14px; line-height:1.25; color:var(--body); flex:1; }
  .side-threads-h { padding-top:20px; border-top:2px solid var(--ink); }
  .thread-row { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:11px; }
  .thread-name { font-style:italic; font-size:16px; border-bottom:1px solid var(--brown); }
  .thread-days { font:400 11px system-ui,sans-serif; color:var(--faint); }
  .issue-foot { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:20px 44px;
                border-top:2px solid var(--ink); background:var(--panel); font:500 12px/1.4 system-ui,sans-serif; }
  .issue-foot .older { color:var(--brown); }
  .issue-foot .home { color:var(--faint); }

  @media (max-width:760px) {
    .mast, .archive { padding-left:20px; padding-right:20px; }
    .navbar, .crumb, .tabbar, .issue-mast, .issue-foot { padding-left:20px; padding-right:20px; }
    .mast-title { font-size:38px; } .issue-date { font-size:40px; }
    .lead-grid, .issue-grid { grid-template-columns:1fr; }
    .lead, .articles { border-right:0; border-bottom:1px solid var(--rule); }
    .cell .chead { display:none; } .cell { min-height:44px; }
    .searchbox { min-width:0; width:100%; }
  }
"""


def find_digests():
    """(date, md_filename) for every digest-<date>.md, newest first."""
    found = []
    for path in glob.glob("digest-*.md"):
        m = FILENAME_RE.match(os.path.basename(path))
        if m:
            found.append((datetime.date.fromisoformat(m.group(1)), os.path.basename(path)))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return found


def pretty_date(d):
    return f"{d:%B} {d.day}, {d.year}"


def _short(d):
    return f"{d:%b} {d.day}"


def _section_class(text):
    low = text.lower()
    for needle, cls in SECTION_CLASSES:
        if needle in low:
            return cls
    return ""


def _strip_emoji(text):
    return re.sub(r"^[^\w]+", "", text).strip()


def _inline(text):
    """Turn inline markdown into HTML (text is already escaped)."""
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def _parse_articles(md):
    """Pull a digest's markdown apart into article dicts (researched or headline-only)."""
    articles, section, sec_cls = [], "", ""
    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section, sec_cls = _strip_emoji(line[3:]), _section_class(line[3:])
            continue
        # A researched entry, in either shape this repo has produced:
        #   "**1. Title** — summary"   (older interactive digests)
        #   "- **Title** — summary"    (research_to_markdown / research_via_claude)
        # The leading "- " used to fall through to the bare-headline branch below,
        # which keeps the title and DISCARDS the summary — so every entry rendered
        # as a naked headline even though the markdown had a full brief.
        m = re.match(r"^(?:-\s+)?\*\*\s*(?:\d+\.\s*)?(.+?)\s*\*\*\s*(.*)$", line)
        if m:
            title, rest = m.group(1), m.group(2)
            kicker = ""
            t = re.match(r"^\*\(([^)]+)\)\*\s*(.*)$", rest)               # maybe a *(tag)* up front
            if t:
                kicker, rest = t.group(1), t.group(2)
            rest = re.sub(r"^[—–\-]\s*", "", rest)
            body = rest.strip()
            # Italics are written with '*' in the older digests and '_' in the ones
            # research_to_markdown emits; accept either or the sources run leaks
            # into the visible body text.
            sm = re.search(r"[*_]Sources:\s*(.+?)[*_]\s*$", rest)
            if sm:
                body = rest[: sm.start()].strip()
            articles.append({"cls": sec_cls, "title": title, "url": None, "kicker": kicker, "body": body})
            continue
        hm = re.match(r"^- \[([^\]]+)\]\((https?://[^)]+)\)", line)        # bare headline, has a link
        if hm:
            articles.append({"cls": sec_cls, "title": hm.group(1), "url": hm.group(2), "kicker": "", "body": ""})
            continue
        hm = re.match(r"^- \*\*(.+?)\*\*", line)                           # bare headline, no link
        if hm:
            articles.append({"cls": sec_cls, "title": hm.group(1), "url": None, "kicker": "", "body": ""})
    return articles


def _cat_label(cls):
    return CAT_LABEL.get(cls, "News")


def _cat_color(cls):
    return CAT_COLOR.get(cls, "#7c7568")


def _read_minutes(articles):
    words = sum(len((a["title"] + " " + a["body"]).split()) for a in articles)
    return max(1, round(words / 220))


def _searchbox(placeholder):
    return (
        '<form class="searchbox" action="search.html" method="get" role="search">'
        '<span>⌕</span>'
        f'<input name="q" placeholder="{html.escape(placeholder)}" aria-label="Search the archive">'
        "</form>"
    )


def _page(title, body):
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{html.escape(title)}</title>\n"
        '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;'
        '0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400;1,6..72,500&display=swap" rel="stylesheet">\n'
        f"  <style>{CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


# --- landing page ("The Archive") -------------------------------------------

def _month_archive(year, month, ctx):
    cal = calendar.Calendar(firstweekday=6)  # weeks start on Sunday
    weeks = cal.monthdayscalendar(year, month)
    n_issues = sum(1 for d, _ in ctx["digests"] if d.year == year and d.month == month)
    head = "".join(f"<span>{d}</span>" for d in WEEKDAYS)
    cells = []
    for week in weeks:
        for day in week:
            if day == 0:
                cells.append('<div class="cell blank"><span class="cnum">&nbsp;</span></div>')
                continue
            iso = f"{year:04d}-{month:02d}-{day:02d}"
            if iso not in ctx["dates"]:
                cells.append(f'<div class="cell blank"><span class="cnum">{day}</span></div>')
                continue
            state = "lead" if iso == ctx["lead_iso"] else "has"
            headline = html.escape(ctx["previews"].get(iso, ""))
            cells.append(
                f'<div class="cell {state}"><a href="digest-{iso}.html">'
                f'<span class="cnum">{day}</span>'
                f'<span class="chead">{headline}</span></a></div>'
            )
    return (
        '  <section class="archive">\n'
        '    <div class="archive-head">'
        f'<div class="archive-title">The Archive — {calendar.month_name[month]} {year}</div>'
        f'<div class="archive-meta">{n_issues} issue{"s" if n_issues != 1 else ""} this month</div></div>\n'
        f'    <div class="weekhead">{head}</div>\n'
        f'    <div class="caldays">{"".join(cells)}</div>\n'
        + _threads_row(ctx) +
        "  </section>\n"
    )


def _threads_row(ctx):
    threads = [lbl for lbl, _ in sorted(ctx["topic_days"].items(), key=lambda kv: -kv[1]) if ctx["topic_days"][lbl]]
    if not threads:
        return ""
    spans = "".join(f'<span class="thread">{html.escape(t)}</span>' for t in threads[:6])
    return f'    <div class="threads"><span class="threads-label">Recurring threads</span>{spans}</div>\n'


def render_index(ctx):
    digests = ctx["digests"]
    latest, latest_name = digests[0]
    arts = ctx["arts"][latest.isoformat()]
    lead = arts[0] if arts else {"title": "", "body": "", "cls": ""}

    also_items = ""
    for a in arts[1:4]:
        also_items += (
            f'    <a class="also-item" href="digest-{latest.isoformat()}.html">'
            f'<span class="also-cat" style="color:{_cat_color(a["cls"])}">{_cat_label(a["cls"]).upper()}</span>'
            f'<div class="also-title">{_inline(html.escape(a["title"]))}</div></a>\n'
        )

    months = sorted({(d.year, d.month) for d, _ in digests}, reverse=True)
    archives = "".join(_month_archive(y, m, ctx) for y, m in months)

    body = (
        '<div class="paper">\n'
        '  <header class="mast">\n'
        '    <div class="mast-top"><span>Shared Daily Digest</span>'
        f'<span>Est. 2026 · No. {len(digests)}</span></div>\n'
        '    <div class="mast-title">The Deep Digest</div>\n'
        f'    <div class="mast-sub">{latest:%A} · {pretty_date(latest)} · Tech, markets &amp; finance</div>\n'
        "  </header>\n"
        '  <nav class="navbar" style="justify-content:flex-end">\n'
        f"    {_searchbox(f'Search {len(digests)} issues…')}\n"
        "  </nav>\n"
        '  <div class="lead-grid">\n'
        f'    <a class="lead" href="digest-{latest.isoformat()}.html">\n'
        '      <div class="kicker">◆ Today’s lead</div>\n'
        f'      <div class="lead-title">{_inline(html.escape(lead["title"]))}</div>\n'
        + (f'      <div class="lead-sum">{_inline(html.escape(lead["body"]))}</div>\n' if lead["body"] else "")
        + '      <span class="lead-btn">Read today’s brief →</span>\n'
        "    </a>\n"
        '    <div class="also">\n'
        f'      <div class="also-h">Also inside · {len(arts)} stories</div>\n'
        f"{also_items}"
        "    </div>\n"
        "  </div>\n"
        f"{archives}"
        "</div>\n"
    )
    return _page("The Deep Digest", body)


# --- the per-day issue page ("The Issue") -----------------------------------

def render_issue(date, ctx):
    iso = date.isoformat()
    arts = ctx["arts"][iso]
    no = ctx["issue_no"][iso]
    minutes = _read_minutes(arts)

    counts = {"all": len(arts)}
    for c in ("tech", "markets", "finance"):
        counts[c] = sum(1 for a in arts if a["cls"] == c)
    tabs = "".join(
        f'<span class="tab{" on" if key == "all" else ""}" data-key="{key}">{lbl} · {counts[key]}</span>'
        for key, lbl in [("all", "All"), ("tech", "Tech"), ("markets", "Markets"), ("finance", "Finance")]
        if key == "all" or counts[key]
    )

    articles_html = ""
    for a in arts:
        title = _inline(html.escape(a["title"]))
        if a["url"]:
            title = f'<a href="{html.escape(a["url"])}">{title}</a>'
        kick = f'<span class="art-kicker">({html.escape(a["kicker"])}) </span>' if a["kicker"] else ""
        summ = f'<div class="art-sum">{kick}{_inline(html.escape(a["body"]))}</div>' if a["body"] else ""
        articles_html += (
            f'      <article class="article" data-cat="{a["cls"] or "news"}">\n'
            f'        <div class="art-cat" style="color:{_cat_color(a["cls"])}">{_cat_label(a["cls"]).upper()}</div>\n'
            f'        <div class="art-title">{title}</div>\n'
            f"        {summ}\n"
            "      </article>\n"
        )

    toc = "".join(
        f'<div class="toc-item"><span class="toc-n" style="color:{_cat_color(a["cls"])}">{i}</span>'
        f'<span class="toc-t">{html.escape(a["title"])}</span></div>'
        for i, a in enumerate(arts, 1)
    )

    threads = sorted(ctx["topics"][iso], key=lambda t: -ctx["topic_days"][t])
    thread_rows = "".join(
        f'<div class="thread-row"><span class="thread-name">{html.escape(t)}</span>'
        f'<span class="thread-days">{ctx["topic_days"][t]} day{"s" if ctx["topic_days"][t] != 1 else ""}</span></div>'
        for t in threads
    )

    older = ctx["older"].get(iso)
    newer = ctx["newer"].get(iso)
    crumb_nav = ""
    if older:
        crumb_nav += f'<a href="digest-{older}.html">‹ {_short(datetime.date.fromisoformat(older))}</a>'
    if newer:
        crumb_nav += f' &nbsp;·&nbsp; <a href="digest-{newer}.html">{_short(datetime.date.fromisoformat(newer))} ›</a>'

    foot_older = ""
    if older:
        od = datetime.date.fromisoformat(older)
        top = ctx["previews"].get(older, "")
        foot_older = f'<a class="older" href="digest-{older}.html">← Older · {pretty_date(od)} · {html.escape(top)}</a>'

    body = (
        '<div class="paper">\n'
        '  <div class="crumb">\n'
        '    <a href="index.html">← The Archive</a>\n'
        '    <span class="mid">The Deep Digest</span>\n'
        f'    <span>{crumb_nav or "&nbsp;"}</span>\n'
        "  </div>\n"
        '  <header class="issue-mast">\n'
        f'    <div class="issue-kicker">{date:%A} Issue · No. {no}</div>\n'
        f'    <div class="issue-date">{pretty_date(date)}</div>\n'
        f'    <div class="issue-sub">{len(arts)} stories across tech, markets &amp; finance — a {minutes}-minute read.</div>\n'
        "  </header>\n"
        f'  <div class="tabbar"><div class="tabs">{tabs}</div>{_searchbox("Search the archive…")}</div>\n'
        '  <div class="issue-grid">\n'
        '    <div class="articles">\n'
        f"{articles_html}"
        "    </div>\n"
        '    <aside class="sidebar"><div class="sidebar-sticky">\n'
        f'      <div class="side-h">In this issue · {len(arts)} stories</div>\n'
        f'      <div class="toc">{toc}</div>\n'
        + (f'      <div class="side-h side-threads-h">Recurring threads</div>\n{thread_rows}\n' if thread_rows else "")
        + "    </div></aside>\n"
        "  </div>\n"
        '  <div class="issue-foot">\n'
        f'    <span>{foot_older or "&nbsp;"}</span>\n'
        '    <a class="home" href="index.html">Back to The Archive</a>\n'
        "  </div>\n"
        "</div>\n"
        "<script>(function(){var tabs=document.querySelectorAll('.tab'),arts=document.querySelectorAll('.article');"
        "tabs.forEach(function(t){t.addEventListener('click',function(){var k=t.dataset.key;"
        "tabs.forEach(function(x){x.classList.toggle('on',x===t)});"
        "arts.forEach(function(a){a.style.display=(k==='all'||a.dataset.cat===k)?'':'none'})})})})();</script>\n"
    )
    return _page(f"The Deep Digest — {pretty_date(date)}", body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="public", help="output directory (default: public)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    digests = find_digests()   # newest first
    if not digests:
        with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
            f.write(_page("The Deep Digest", '<div class="paper"><header class="mast">'
                          '<div class="mast-title">The Deep Digest</div></header></div>'))
        print("[no digests]")
        return

    # read each file once and stash everything the renderers need in one ctx
    arts, topics = {}, {}
    for d, name in digests:
        md = open(name, encoding="utf-8").read()
        arts[d.isoformat()] = _parse_articles(md)
        topics[d.isoformat()] = digest_topics(md)

    topic_days = {}
    for tset in topics.values():
        for t in tset:
            topic_days[t] = topic_days.get(t, 0) + 1

    ordered = sorted(d for d, _ in digests)         # oldest first, for issue numbers
    issue_no = {d.isoformat(): i + 1 for i, d in enumerate(ordered)}
    previews = {d.isoformat(): (arts[d.isoformat()][0]["title"] if arts[d.isoformat()] else "")
                for d, _ in digests}
    # older = previous day, newer = next day (for the prev/next nav)
    older, newer = {}, {}
    for i, (d, _) in enumerate(digests):
        if i < len(digests) - 1:
            older[d.isoformat()] = digests[i + 1][0].isoformat()
        if i > 0:
            newer[d.isoformat()] = digests[i - 1][0].isoformat()

    ctx = {
        "digests": digests, "dates": {d.isoformat() for d, _ in digests},
        "arts": arts, "topics": topics, "topic_days": topic_days,
        "issue_no": issue_no, "previews": previews, "older": older, "newer": newer,
        "lead_iso": digests[0][0].isoformat(),
    }

    for d, _ in digests:
        with open(os.path.join(args.out, f"digest-{d.isoformat()}.html"), "w", encoding="utf-8") as f:
            f.write(render_issue(d, ctx))

    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index(ctx))

    latest_iso = digests[0][0].isoformat()
    with open(os.path.join(args.out, "latest.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><meta charset="utf-8">'
                f'<meta http-equiv="refresh" content="0; url=digest-{latest_iso}.html">'
                f'<link rel="canonical" href="digest-{latest_iso}.html">'
                f'<a href="digest-{latest_iso}.html">Latest issue →</a>')

    print(f"[wrote {args.out}/index.html + latest.html + {len(digests)} issue page(s)]")


if __name__ == "__main__":
    main()
