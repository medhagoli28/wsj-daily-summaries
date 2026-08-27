#!/usr/bin/env python3
"""
research_via_claude.py — free stand-in for `wsj_fetch.py --research`.

Produces exactly the same `# WSJ Deep Digest` output as Mode B, but each headline
is researched by shelling out to the Claude Code CLI (`claude -p`) on a Claude
subscription instead of the metered Anthropic API. No ANTHROPIC_API_KEY, no
per-token bill.

Everything except the one API call is reused from wsj_fetch, so the markdown this
writes is byte-compatible with the digests already in the repo: same headline
fetch, same cross-day de-dup, same renderer, same SOURCES handling.

This is what the daily GitHub Actions run calls, which is why the published site
gets real summaries instead of bare headline links.

  python3 research_via_claude.py                   # writes digest-<date>.md
  python3 research_via_claude.py --limit 10        # headlines per section
  python3 research_via_claude.py --min-entries 5   # exit 1 below this many

Exit codes: 0 = digest written and healthy, 1 = wrote too few real summaries
(the caller should fall back to headlines and make some noise about it).
"""

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import dedup
import wsj_fetch

# The CLI does the paywall-safe research; wsj_fetch owns the prompt so mode B and
# this path can never drift apart.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")

# One headline with a few web searches is well under a minute, but CI runners are
# slow and search can stall — give it room before calling it dead.
TIMEOUT = int(os.environ.get("RESEARCH_TIMEOUT", "300"))

# WebSearch is the only tool it needs. Restricting to it means this subprocess
# can't touch the repo even if the model decides it wants to.
ALLOWED_TOOLS = "WebSearch"


def research_headline(item, attempts=2):
    """Research one headline via `claude -p`, mirroring wsj_fetch.research_headline.

    Returns the item with 'summary'/'sources' filled in, or an 'error' string if
    every attempt failed — one dead headline shouldn't kill the whole run.
    """
    prompt = f"Section: {item['section']}\nHeadline: {item['title']}"
    last_error = "unknown failure"

    for _ in range(attempts):
        # Run in a throwaway cwd: the CLI has no business in the repo here, and an
        # empty dir sidesteps any workspace-trust prompt on a fresh CI container.
        with tempfile.TemporaryDirectory() as sandbox:
            try:
                proc = subprocess.run(
                    [
                        CLAUDE_BIN, "-p", prompt,
                        "--append-system-prompt", wsj_fetch.RESEARCH_SYSTEM,
                        "--allowed-tools", ALLOWED_TOOLS,
                    ],
                    cwd=sandbox,
                    stdin=subprocess.DEVNULL,   # else the CLI waits around for piped input
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                last_error = f"timed out after {TIMEOUT}s"
                continue
            except FileNotFoundError:
                # No CLI at all — retrying won't conjure one up.
                return {**item, "summary": "", "sources": [],
                        "error": f"{CLAUDE_BIN} not found on PATH"}

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            last_error = stderr.splitlines()[-1] if stderr else f"claude exited {proc.returncode}"
            continue

        text = (proc.stdout or "").strip()
        if not text:
            last_error = "empty response"
            continue

        summary, sources = wsj_fetch.split_summary_and_sources(text)
        if not summary:
            last_error = "response had no summary"
            continue

        return {**item, "summary": summary, "sources": sources, "error": None}

    return {**item, "summary": "", "sources": [], "error": last_error}


def research(digest):
    """Run every fetched headline through the CLI, skipping recent near-duplicates.

    Same shape as wsj_fetch.research(), including writing back the de-dup store.
    """
    store = dedup.load_store()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    researched = []
    for i, item in enumerate(digest, 1):
        title = item["title"]
        if dedup.is_duplicate(title, store):
            print(f"[{i}/{len(digest)}] skip (already covered): {title[:60]}", file=sys.stderr)
            continue
        print(f"[{i}/{len(digest)}] {title[:60]}", file=sys.stderr)
        researched.append(research_headline(item))
        store[title] = {"date": today}

    dedup.save_store(dedup.prune_store(store))
    return researched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="items per section")
    ap.add_argument("--out", metavar="PATH",
                    help="output path (default: digest-<date>.md)")
    ap.add_argument("--min-entries", type=int, default=5,
                    help="exit 1 if fewer than this many headlines got a real summary")
    args = ap.parse_args()

    researched = research(wsj_fetch.build(args.limit))
    report = wsj_fetch.research_to_markdown(researched)

    out = args.out or f"digest-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    with open(out, "w") as f:
        f.write(report)

    good = [r for r in researched if not r.get("error")]
    failed = len(researched) - len(good)
    print(f"[wrote {out}: {len(good)} summarized, {failed} failed]", file=sys.stderr)

    # A digest that's mostly "could not research" lines is worse than no digest —
    # say so loudly instead of letting it publish as if the day went fine.
    if len(good) < args.min_entries:
        print(f"[FAIL] only {len(good)} real summaries, need {args.min_entries}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
