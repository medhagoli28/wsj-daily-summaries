# WSJ Section Digest + Auto-Research

A two-stage tool that gives you a detailed daily summary of the WSJ **Tech**, **Markets & Finance**,
and **Personal Finance** sections — **without touching any paywalled article text.**

- **Stage 1 (`wsj_fetch.py`)** pulls the free RSS layer: every article's **headline + link** per section.
- **Stage 2 (`wsj_fetch.py --research`)** takes each headline and **researches the same story across other outlets**
  (Reuters, AP, CNBC, CoinDesk, SEC filings, etc.) to write a deep summary — legally clean, no WSJ body used.

```
 WSJ RSS (headline + dek)  ──►  Claude web research per headline  ──►  Deep section digest
   free / legal                  (other sources, cited)                (what happened + why)
```

## Why it works this way
WSJ articles are paywalled and their terms forbid automated scraping — even for subscribers.
But headlines and deks are published free via RSS, and the *underlying events* (earnings, Fed moves,
deals, market swings) are covered by many non-paywalled outlets. So we use WSJ for **story selection**
and everyone else for **depth**. The only stories this can't deepen are WSJ **exclusives/scoops** that
no one else has covered yet — for those you get just the dek.

## Why I built this
I try follow WSJ regularly but kept losing track of stories across the day — too many headlines, too easy to forget what I meant to read. I wanted one place where the day's important stories were already researched and waiting for me, without having to remember to go looking. So I built this.

## Files
- `wsj_fetch.py` — the whole tool. Stage 1 (fetch) is stdlib-only; Stage 2 (`--research`) uses the Anthropic SDK.
- `tests/` — unit tests for the pure parse/clean helpers (`python3 -m pytest`).
- `dedup.py` — free cross-day de-duplication (difflib similarity, no dependencies) so Stage 2 skips stories already covered.
- `.github/workflows/daily-digest.yml` — cron that publishes the **free** headline digest to GitHub Pages daily.
- `requirements.txt` — the one dependency (`anthropic`), needed only for the optional `--research` mode.
- `digest-<date>.md` — a generated digest (committed daily by the workflow).

## Sources (all free)
Headlines come from Google News RSS scoped to `site:wsj.com` (the native `feeds.a.dj.com`
feeds intermittently serve a stale CDN cache, so we don't rely on them):

| Section | Query |
|---|---|
| Tech | `site:wsj.com/tech when:4d` |
| Markets & Finance | `stock market site:wsj.com when:4d` |
| Personal Finance | `"personal finance" site:wsj.com when:7d` |

---

## How to run it

### Mode A — Interactive, inside Claude Code (recommended, no API key)
This is the simplest repeatable workflow and what the demo used.

1. Fetch today's headlines:
   ```bash
   cd ~/Downloads/wsj-digest
   python3 wsj_fetch.py --limit 12 --json digest.json
   ```
2. In Claude Code, say:
   > "Read `digest.json` and for each headline, research the story from non-WSJ sources
   >  and write me a deep summary grouped by section. Skip anything you can't corroborate."
3. Claude uses web search/fetch to deepen each headline and hands you the digest.

You can tune it: "only the top 5 per section," "focus on market-moving items," "add a 3-bullet
'why it matters,'" "flag WSJ exclusives separately," etc.

### Mode B — Fully automated (`--research`, hands-off)
Stage 2 is implemented in `wsj_fetch.py` as the `research_headline()` function: it sends each
headline to Claude (`claude-opus-4-8`) with the server-side **web_search** tool enabled, and Claude
writes a short, sourced summary from non-WSJ outlets. Run it end-to-end with `--research`:

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python3 wsj_fetch.py --research --limit 10   # writes digest-<date>.md
```

How Stage 2 works, in three small functions:
- `research_headline(client, item)` — one API call per headline, web search on, returns summary + sources.
- `split_summary_and_sources(text)` — parses the model's `SOURCES:` line and drops any wsj.com links.
- `research_to_markdown(...)` — groups the results into a dated Markdown digest.

### Automated daily run (GitHub Actions) — free
`.github/workflows/daily-digest.yml` runs on a cron (`0 16 * * *` = noon ET) and is **completely free**:
it fetches today's headlines (Mode A, stdlib only), commits `digest-<date>.md`, and publishes it to
GitHub Pages. It uses only the built-in `GITHUB_TOKEN` — **no API keys, no secrets to add.** You can also
trigger it manually from the Actions tab (`workflow_dispatch`).

The paid deep-research mode (`--research`) is intentionally **not** run by the workflow. Generate deep
summaries on demand instead — run `--research` locally with an `ANTHROPIC_API_KEY`, or ask Claude to
research a fetched headline list for you. De-duplication (`dedup.py`) is free either way (difflib, no API).

---

## Options
```
python3 wsj_fetch.py --limit N        # items per section (default 12)
python3 wsj_fetch.py --json PATH      # Mode A: write structured JSON
python3 wsj_fetch.py --research       # Mode B: deepen each headline via Claude web search
python3 wsj_fetch.py --research --out PATH   # choose the output file
```

## Running the tests
```bash
pip install pytest
python3 -m pytest        # unit tests for clean() / parse_items() / split_summary_and_sources()
```

## Legal note
This tool only reads free RSS metadata and researches events via third-party outlets. It does not
scrape, store, or reproduce WSJ article bodies. Keep it that way: if you later want full WSJ article
text programmatically, use a licensed feed (Dow Jones Newswires / Factiva), not a scraper.

## Prompt for project

```
Build a free, fully-automated "WSJ Deep Digest" — a daily news digest that turns WSJ
headlines into researched summaries and publishes them as a styled static site on
GitHub Pages. Use only plain Python 3 (standard library) + inline CSS. No frameworks,
no third-party packages, no paid APIs. All summary research must come from free web
search over NON-WSJ sources; never reproduce paywalled WSJ text or cite wsj.com.

═══ REPO LAYOUT ═══
- wsj_fetch.py        — fetch today's headlines (stdlib only)
- generate_index.py   — render the static site from the digest markdown files
- seen_headlines.json — JSON dict tracking covered headlines: {title: {"date": "YYYY-MM-DD"}}
- digest-<YYYY-MM-DD>.md — one markdown file per day (the content)
- .github/workflows/daily-digest.yml — daily automation

═══ wsj_fetch.py ═══
Pull WSJ headlines from Google News RSS (free, stdlib: urllib + xml/re). Three sections:
"Tech", "Markets & Finance", "Personal Finance". CLI: `--limit N` (headlines per section)
and `--json PATH` (dump results). Each item: {section, title, dek, link, published}.
Also print a readable markdown list to stdout.

═══ DAILY CONTENT PIPELINE (documented in a workflow + a runbook) ═══
1. `git pull --rebase`.
2. `python3 wsj_fetch.py --limit 7 --json /tmp/hl.json`.
3. Research EVERY headline from non-WSJ outlets (Reuters, Bloomberg, CNBC, etc.) via web
   search. For each, write a 4–5 sentence summary packed with concrete numbers and dates.
   For WSJ advice/opinion columns with no external event, summarize the underlying topic.
4. Write digest-<today>.md (see FORMAT).
5. Update seen_headlines.json: add each covered title -> {"date": "<today>"}.
6. Commit + push. 7. Trigger the site build. 8. Verify the deployed page returns HTTP 200.

═══ DIGEST MARKDOWN FORMAT (exact — the renderer depends on it) ═══
Line 1:  `# WSJ Deep Digest — <YYYY-MM-DD>`
Line 2:  one-line *italic* intro.
Section headers (exact, with emoji): `## 💻 Tech`, `## 📈 Markets & Finance`, `## 💰 Personal Finance`
Each entry EXACTLY:
   `**N. Title** — summary text *Sources: [name](url), [name](url).*`
Advice/analysis/review entries add a tag right after the title:
   `**N. Title** *(advice — underlying topic)* — summary ...`
End the file with an italic provenance line noting research is from non-WSJ sources.

═══ generate_index.py — STATIC SITE ═══
Parse every digest-*.md and emit into an output dir (default ./public):
• index.html — a monthly calendar. Each day that has a digest is a clickable cell linking
  to that day's page. ONLY the current UTC date is visually highlighted (a `today` class);
  past digest days stay clickable but calm. Always render the current month even if it has
  no digest yet. Include a prominent "Read the latest digest →" hero linking to the newest day.
• digest-<date>.html — a dark "bubble" layout. Warm-dark background (#201d1a), cream cards
  (#efe9dc). Each article is a card with: a section-colored pill (Tech=blue #6ea8fe,
  Markets=green, Finance=amber), an optional italic kicker (the *(tag)*), the headline,
  the summary, and a "Sources:" line of links. NO article numbers on cards.
  Card features:
    - Category filter bar at top: buttons All / Tech / Markets / Finance, each showing a
      count. Clicking filters cards (toggle `hidden`). Deep-linkable via URL hash
      (e.g. #tech loads pre-filtered and clicks update location.hash); keep aria-pressed
      in sync; "All" clears the hash.
    - Prev/next-day nav at the bottom ("← Older <date>" / "Newer <date> →").
    - "Recurring threads": cross-link days that share a topic. Detect topics by matching each
      digest's text against a keyword ruleset (e.g. "AI boom", "Iran & oil", "Crypto",
      "Tariffs & trade", "Fed & rates", "IPOs & listings", "Chips", "Deals & M&A"). A day
      joins a thread if it matches; show threads shared by ≥2 days, linking the other dates.
      Rank by how many days share the thread; cap at 5.
• latest.html — a meta-refresh redirect that always points at the newest digest (a stable
  bookmarkable URL).
Whole site uses one unified warm-dark theme, inline CSS, mobile-responsive (calendar shrinks,
bubbles collapse to one column). Pure vanilla JS for the filter; degrades gracefully if JS off.

═══ AUTOMATION (.github/workflows/daily-digest.yml) ═══
Runs on a daily cron + manual dispatch. Renders the markdown digests to HTML via
generate_index.py and deploys the output to GitHub Pages. Include a no-overwrite guard so a
manually-researched digest for a date is never clobbered by an automated headline-only run.
Set git identity to github-actions[bot] when committing.

═══ ACCEPTANCE ═══
- End to end runs for free (web search only, no paid API keys).
- A generated digest page returns HTTP 200 on GitHub Pages, shows 3 sections with researched
  summaries + working non-WSJ source links, and no wsj.com citations.
- Calendar highlights only today; filter works and is shareable by URL; prev/next + latest +
  threads all resolve to real pages.
```
