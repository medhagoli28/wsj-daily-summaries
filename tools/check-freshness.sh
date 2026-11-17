#!/bin/bash
#
# check-freshness.sh — tell Medha when the digest has gone stale.
#
# Deliberately NOT part of run-digest.sh. Every outage so far was invisible
# because the thing that was supposed to report it was the thing that was broken:
# the agent kept firing on schedule, kept failing, and kept saying nothing. The
# 2026-10-27 OAuth expiry ran 19 days that way. A watchdog that shares a process,
# a code path or an auth token with the pipeline it watches is not a watchdog.
#
# So this is its own LaunchAgent, it reads only the filesystem, and it needs no
# network, no Claude login and no GitHub access. The only thing it can't survive
# is the Mac being off — and then nothing is producing digests anyway.
#
# Exit codes: 0 = fresh, 1 = stale (notified), 2 = can't tell.

set -uo pipefail

# Overridable so the stale path can actually be tested against a fixture dir.
# Testing it only by lowering STALE_HOURS doesn't work: the newest digest is
# named for the UTC date, so its age clamps to 0 and no threshold can trip it.
REPO="${WSJ_REPO:-/Users/medhagoli/wsj-daily-summaries}"
LOG="$REPO/freshness.log"

# Hours before the digest counts as stale. A day is missed all the time for
# ordinary reasons (asleep at every slot, offline weekend), so one missed day
# shouldn't nag. Two in a row is a real signal.
STALE_HOURS="${STALE_HOURS:-40}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

notify() {
  local title="$1" msg="$2"
  # Escape double quotes for AppleScript.
  msg=${msg//\"/\\\"}
  title=${title//\"/\\\"}
  /usr/bin/osascript -e "display notification \"$msg\" with title \"$title\" sound name \"Basso\"" 2>/dev/null
}

cd "$REPO" 2>/dev/null || { log "FATAL: no repo at $REPO"; exit 2; }

# Newest digest by the DATE IN ITS NAME, not mtime — a backfill rewrites old
# files with today's mtime, which would make a stale archive look fresh.
newest=$(ls -1 digest-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md 2>/dev/null \
         | sed 's/^digest-//; s/\.md$//' | sort | tail -1)

if [ -z "$newest" ]; then
  log "FATAL: no digests found at all"
  notify "WSJ digest" "No digests found in the repo at all."
  exit 2
fi

newest_epoch=$(date -j -f "%Y-%m-%d %H:%M:%S" "$newest 12:00:00" +%s 2>/dev/null)
if [ -z "$newest_epoch" ]; then
  log "FATAL: could not parse date '$newest'"
  exit 2
fi

age_hours=$(( ( $(date +%s) - newest_epoch ) / 3600 ))
# Digests are named by UTC date, so late in the US evening today's file is
# already "tomorrow" and the age comes out negative. That's fresh, not broken.
[ "$age_hours" -lt 0 ] && age_hours=0

# A file existing isn't success — a headline-only or mostly-failed digest is a
# failure wearing the right filename. Check the newest one is actually real.
f="digest-$newest.md"
# `grep -c` prints its count AND exits 1 when the count is zero, so a trailing
# `|| echo 0` appends a SECOND zero and the arithmetic below dies on "0\n0".
count() { grep -c "$1" "$2" 2>/dev/null || true; }

entries=$(count '^- \*\*' "$f")
failures=$(count 'could not research' "$f")
deep=$(head -1 "$f" | grep -c 'Deep Digest' || true)
entries=${entries:-0}; failures=${failures:-0}; deep=${deep:-0}

if [ "$age_hours" -gt "$STALE_HOURS" ]; then
  days=$(( age_hours / 24 ))
  log "STALE: newest digest is $newest (${days}d old, ${age_hours}h)"
  notify "WSJ digest is stale" \
         "Newest is $newest — ${days} days old. Check: tail digest-run.log"
  exit 1
fi

if [ "$deep" -eq 0 ] || [ "$entries" -eq 0 ] || [ $(( failures * 2 )) -ge "$entries" ]; then
  log "DEGRADED: $f exists but isn't a healthy digest (entries=$entries failures=$failures deep=$deep)"
  notify "WSJ digest looks broken" \
         "$newest published but has $entries entries / $failures failures."
  exit 1
fi

log "ok: newest $newest (${age_hours}h, $entries entries, $failures failures)"
exit 0
