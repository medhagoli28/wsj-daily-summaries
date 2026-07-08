# WSJ Section Digest + Auto-Research

A two-stage tool that gives you a detailed daily summary of the WSJ **Tech**, **Markets & Finance**,
and **Personal Finance** sections — **without touching any paywalled article text.**

- **Stage 1 (`wsj_fetch.py`)** pulls the free RSS layer: every article's **headline + dek + link** per section.
- **Stage 2 (Claude)** takes each headline and **researches the same story across other outlets**
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

## Files
- `wsj_fetch.py` — Stage 1 fetcher (zero dependencies, Python 3 stdlib only).
- `digest.json` — last fetched headlines (regenerated each run).
- `README.md` — this file.

## Sources (all free)
| Section | Source | Notes |
|---|---|---|
| Tech | `feeds.a.dj.com/rss/RSSWSJD.xml` | native WSJ feed, includes deks |
| Markets & Finance | `feeds.a.dj.com/rss/RSSMarketsMain.xml` | native WSJ feed, includes deks |
| Personal Finance | Google News RSS filtered to `site:wsj.com` | WSJ blocks its own PF feed (403); this returns WSJ PF headlines |

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

### Mode B — Fully automated (standalone script + API, hands-off)
For a cron job that emails/Slacks you a digest every morning with no human in the loop, replace
Stage 2 with an LLM API call that has web search enabled. Pseudocode:

```python
import json, subprocess
# 1. Stage 1
subprocess.run(["python3", "wsj_fetch.py", "--json", "digest.json"])
items = json.load(open("digest.json"))

# 2. Stage 2 — call an LLM with a web-search tool, once per headline (or batched by section)
#    e.g. Anthropic Messages API with the web_search tool, or the OpenAI/Gemini equivalents.
for it in items:
    prompt = f"Research this news item from sources OTHER THAN wsj.com and write a 4-6 sentence " \
             f"summary with concrete numbers, then a one-line 'why it matters'. " \
             f"Headline: {it['title']}. Dek: {it['dek']}. If no non-WSJ coverage exists, say so."
    # summary = call_llm_with_web_search(prompt)   # <-- your API of choice
    # collect summaries...

# 3. Format into markdown / HTML and deliver (email, Slack webhook, file)
```

Then schedule it:
```bash
# every weekday at 7am
0 7 * * 1-5  cd ~/Downloads/wsj-digest && /usr/bin/python3 daily_digest.py
```
(You'd add an API key in the environment and a delivery step — email/Slack — to `daily_digest.py`.)

---

## Checking feed freshness
The native WSJ feeds are served through a CDN and can occasionally return cached/stale items.
Sanity-check the newest timestamp:
```bash
curl -s -A "Mozilla/5.0" https://feeds.a.dj.com/rss/RSSMarketsMain.xml \
  | grep -o "<pubDate>[^<]*</pubDate>" | head -3
```
If the dates look old, wait and re-fetch, or rely more on the Google-News-sourced sections
(which are near-real-time).

## Options
```
python3 wsj_fetch.py --limit N       # items per section (default 12)
python3 wsj_fetch.py --json PATH      # write structured JSON
```

## Legal note
This tool only reads free RSS metadata and researches events via third-party outlets. It does not
scrape, store, or reproduce WSJ article bodies. Keep it that way: if you later want full WSJ article
text programmatically, use a licensed feed (Dow Jones Newswires / Factiva), not a scraper.
