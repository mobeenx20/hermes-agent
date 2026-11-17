#!/usr/bin/env bash
# Nightly worked-hours fill, run at 23:55 local while the TopTracker local DB
# still holds the day's rows (the DB purges older days within days, so a job
# that runs the next morning has nothing left to read).
#
# Watchdog pattern: cron delivers this script's stdout verbatim and an EMPTY
# stdout sends nothing. So success is silent and any output means a problem.
# Wrapper is needed because `no_agent` script jobs cannot carry CLI args, and
# because fill_hours.py prints its full JSON result on every run.

PY=/home/user1011/.hermes/hermes-agent/venv/bin/python
FILL=/home/user1011/.hermes/scripts/fill_hours.py
ALERT=/home/user1011/.hermes/scripts/fill_hours_alert.py

err=$(mktemp) || exit 1
out=$("$PY" "$FILL" "$@" 2>"$err")
rc=$?

if [ "$rc" -ne 0 ]; then
  echo "Nightly hours fill FAILED (exit $rc)"
  echo "$out"
  cat "$err" >&2
  rm -f "$err"
  exit "$rc"
fi
rm -f "$err"

# Success path: report only a genuine problem, otherwise stay silent.
printf '%s' "$out" | "$PY" "$ALERT" 2>/dev/null || echo "Nightly hours fill: alert parser failed"

exit 0
