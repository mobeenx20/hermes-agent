#!/usr/bin/env bash
# Monday catch-up: force-sync the PREVIOUS week (Mon-Sun) so Friday's partial
# write is replaced with the complete week. Cron has no args, so the flags live
# here; "$@" lets a manual run add --dry-run.
set -euo pipefail
PY="${HOME}/.hermes/hermes-agent/venv/bin/python"
exec "$PY" "${HOME}/.hermes/scripts/toptracker_weekly_sync.py" --last --force "$@"
