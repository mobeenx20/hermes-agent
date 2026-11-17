#!/bin/sh
# run_team_fill.sh - cron wrapper for kimai_team_hours.py.
#
# Reads every configured Kimai account and fills the shared team sheet.
# Silent on success (watchdog pattern: empty stdout means nothing to report).
# Prints the fill report only when a write failed or verification failed.
#
# Usage:
#   run_team_fill.sh fill-local  [--date YYYY-MM-DD] [...]   # CSV target
#   run_team_fill.sh fill-google [--date YYYY-MM-DD] [...]   # Google tab
#
# The target is NEVER guessed (user rule: ask first which target to use).
# Interactive runs ask via poll; for cron, decide the target ONCE when the
# job is created and pass it explicitly here. An omitted or unknown target
# is an error (exit 64), not a default.
#
# Schedule (example, GMT+5) - the config lists all accounts, so one job
# covers every developer:
#   55 23 * * *  /path/to/run_team_fill.sh fill-google
set -eu

PY="${HERMES_PY:-$HOME/.hermes/hermes-agent/venv/bin/python}"
SCRIPT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/kimai_team_hours.py"

case "${1:-}" in
  fill-local|fill-google) CMD="$1"; shift ;;
  *)
    echo "run_team_fill.sh: target required (fill-local | fill-google)." >&2
    echo "Ask the user which target to use; do not guess." >&2
    exit 64
    ;;
esac

OUT="$("$PY" "$SCRIPT" "$CMD" --json "$@" 2>&1)" || {
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
