#!/usr/bin/env python3
"""Build a GitHub Pages site listing the daily digests.

Scans the repo root for ``digest-<date>.md`` files, copies each into the output
directory, and writes an ``index.html`` that links to them newest-first with the
date formatted for humans (e.g. "July 8, 2026").

Usage:
  python3 generate_index.py            # output into ./public
  python3 generate_index.py --out DIR  # choose the output directory
"""

import argparse
import datetime
import glob
import html
import os
import re
import shutil

# Matches digest-YYYY-MM-DD.md and captures the date part.
FILENAME_RE = re.compile(r"^digest-(\d{4}-\d{2}-\d{2})\.md$")


def find_digests():
    """Return (date, filename) pairs for every digest-<date>.md, newest first."""
    found = []
    for path in glob.glob("digest-*.md"):
        name = os.path.basename(path)
        match = FILENAME_RE.match(name)
        if not match:
            continue  # skip anything that isn't a dated digest
        date = datetime.date.fromisoformat(match.group(1))
        found.append((date, name))
    found.sort(key=lambda pair: pair[0], reverse=True)  # newest first
    return found


def pretty_date(d: datetime.date) -> str:
    """Format a date like 'July 8, 2026' (no leading zero on the day)."""
    return f"{d:%B} {d.day}, {d.year}"


def render_html(digests) -> str:
    """Build the index.html page as a plain HTML string with inline CSS."""
    if digests:
        rows = "\n".join(
            f'      <li><a href="{html.escape(name)}">{html.escape(pretty_date(date))}</a></li>'
            for date, name in digests
        )
    else:
        rows = "      <li>No digests yet.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WSJ Deep Digest</title>
  <style>
    body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
           max-width: 640px; margin: 3rem auto; padding: 0 1rem; color: #1a1a1a; }}
    h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
    p.sub {{ color: #666; margin-top: 0; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ padding: 0.6rem 0; border-bottom: 1px solid #eee; font-size: 1.1rem; }}
    a {{ color: #0645ad; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    footer {{ margin-top: 2rem; color: #999; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1>WSJ Deep Digest</h1>
  <p class="sub">Daily summaries — headlines from WSJ, depth researched from other outlets.</p>
  <ul>
{rows}
  </ul>
  <footer>Generated automatically. No paywalled WSJ text is reproduced.</footer>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="public", help="output directory (default: public)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    digests = find_digests()

    # Copy each digest into the output so the links resolve on the published site.
    for _, name in digests:
        shutil.copyfile(name, os.path.join(args.out, name))

    with open(os.path.join(args.out, "index.html"), "w") as f:
        f.write(render_html(digests))

    print(f"[wrote {args.out}/index.html with {len(digests)} digest(s)]")


if __name__ == "__main__":
    main()
