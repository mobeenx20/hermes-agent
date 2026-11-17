#!/bin/sh
# run_team_fill.sh - cron wrapper for kimai_team_hours.py.
#
# Reads every configured Kimai account and fills the shared team sheet.
# Silent on success (watchdog pattern: empty stdout means nothing to report).
# Prints the fill report only when a write failed or verification failed.
#
# Usage:
#   run_team_fill.sh                  # fill today, both targets per config
#   run_team_fill.sh --date 2026-11-16
#   run_team_fill.sh --dry-run
#   run_team_fill.sh fill-local ...   # pass a subcommand to override
#
# Schedule (example, GMT+5), one entry per developer is NOT needed: the
# config lists all accounts, so a single job covers everyone:
#   55 23 * * *  /path/to/run_team_fill.sh --json
set -eu

PY="${HERMES_PY:-$HOME/.hermes/hermes-agent/venv/bin/python}"
SCRIPT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/kimai_team_hours.py"

case "${1:-}" in
  read|fill-local|fill-google) CMD="$1"; shift ;;
  "")                          CMD="fill-local" ;;
  *)                           CMD="fill-local" ;;
esac

# default flags: today, json output, no summary noise
ARGS=""
case "$CMD" in
  fill-*) ARGS="--json" ;;
esac

OUT="$("$PY" "$SCRIPT" "$CMD" $ARGS "$@" 2>&1)" || {
  echo "team-hours fill FAILED:"
  echo "$OUT"
  exit 1
}

# only surface output when something needs attention
if echo "$OUT" | grep -q '"verified": false'; then
  echo "team-hours verification FAILED:"
  echo "$OUT"
  exit 2
fi
if echo "$OUT" | grep -qE 'RUNNING|crosses midnight|STALE|skipped'; then
  echo "$OUT"
fi
exit 0
