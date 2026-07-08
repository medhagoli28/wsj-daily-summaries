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
