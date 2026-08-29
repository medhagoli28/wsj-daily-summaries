#!/bin/bash
#
# run-digest.sh — produce and publish the day's researched digest from this Mac.
#
# Driven by the LaunchAgent com.medha.wsj-digest (see tools/com.medha.wsj-digest.plist).
# Uses this machine's own Claude Code login, so it needs no CLAUDE_CODE_OAUTH_TOKEN
# and no ANTHROPIC_API_KEY — that's the whole reason this path exists.
#
# Idempotent on purpose: if today's digest is already researched it exits at once.
# That's what makes catch-up safe — launchd re-runs a missed job when the Mac wakes,
# and the agent also fires at login, so a day can get several attempts for free.
#
# Rendering and deploying still happen in GitHub Actions (workflow_dispatch), so
# there is exactly ONE producer of digest markdown: this script.

set -uo pipefail

# launchd gives a job a near-empty PATH. Absolute paths here or nothing works.
export PATH="/Users/medhagoli/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
CLAUDE_BIN="/Users/medhagoli/.local/bin/claude"
GH="/opt/homebrew/bin/gh"
GIT="/opt/homebrew/bin/git"
PY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

REPO="/Users/medhagoli/Downloads/wsj-daily-summaries"
LOG="$REPO/digest-run.log"
LOCK="/tmp/wsj-digest.lock"

export CLAUDE_BIN            # research_via_claude.py reads this

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# One at a time. A missed-job catch-up can otherwise collide with the timed run,
# and two concurrent pushes to the same file is a guaranteed mess.
exec 9>"$LOCK"
if ! flock -n 9 2>/dev/null; then
  # macOS has no flock(1) by default; fall back to a plain pid check.
  if pgrep -f "research_via_claude.py" > /dev/null; then
    log "another run is already in flight — skipping"
    exit 0
  fi
fi

cd "$REPO" || { log "FATAL: cannot cd to $REPO"; exit 1; }

TODAY="$(date -u +%F)"
FILE="digest-$TODAY.md"

log "=== run start (target $FILE) ==="

# Get in sync first; CI may have published a headline-only fallback overnight.
"$GIT" fetch -q origin && "$GIT" reset -q --hard origin/master
if [ $? -ne 0 ]; then log "FATAL: git sync failed"; exit 1; fi

# Already researched? Nothing to do. This is what makes repeat runs free.
if [ -f "$FILE" ] && head -1 "$FILE" | grep -q "Deep Digest"; then
  log "$FILE is already a researched digest — nothing to do"
  exit 0
fi

if [ -f "$FILE" ]; then
  log "$FILE exists but is headline-only — replacing it with a researched digest"
fi

# --limit 12 (per section) on purpose. Now that seen_headlines.json is warm again,
# de-dup skips most of a day's headlines as already-covered, so fetching a wider
# net is what keeps the digest a reasonable size. The extra headlines are cheap:
# skipped ones never reach the model.
log "researching…"
"$PY" research_via_claude.py --limit 12 --out "$FILE" --min-entries 1 >> "$LOG" 2>&1
RC=$?

if [ $RC -ne 0 ]; then
  # Leave whatever CI published alone rather than committing a broken digest.
  log "FAIL: research exited $RC — not publishing. See the lines above for why."
  "$GIT" checkout -- "$FILE" 2>/dev/null
  exit 1
fi

ENTRIES=$(grep -c '^- \*\*' "$FILE")
log "research OK — $ENTRIES entries"

"$GIT" add "$FILE" seen_headlines.json
if "$GIT" diff --cached --quiet; then
  log "nothing changed — skipping commit"
else
  "$GIT" -c user.name="medhagoli28" -c user.email="mahenderg@yahoo.com" \
      commit -q -m "Researched digest for $TODAY (local run)"
  "$GIT" pull -q --rebase --autostash origin master
  if "$GIT" push -q origin master; then
    log "pushed"
  else
    log "FAIL: push failed"
    exit 1
  fi
fi

# Hand rendering + Pages deploy back to CI. The workflow sees a researched digest
# already exists, skips its own research, and just rebuilds and deploys.
if "$GH" workflow run "Daily WSJ digest" -R medhagoli28/wsj-daily-summaries >> "$LOG" 2>&1; then
  log "deploy dispatched"
else
  log "WARN: could not dispatch the deploy workflow — markdown is pushed, site not yet rebuilt"
fi

log "=== run done ==="
