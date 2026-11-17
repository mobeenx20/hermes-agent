# Plan: Multi-Kimai team hours (skill + script)

Goal: maintain ONE sheet holding tracker hours for MULTIPLE developers. Each
developer tracks time the GMI way: their own Kimai account (Kimai REST API,
per-user API token). Later, cron jobs will run the fill for every developer
into a local sheet or a Google Sheet, unattended.

## Research findings (verified 2026-11-16)

- Existing single-account pipeline: `~/.hermes/scripts/fill_hours.py` reads
  `~/.hermes/config/kimai.json` (url, username, token, projectId) and writes
  one developer's hours into one Google Sheet. It is single-account by design;
  this task needs N accounts feeding one shared sheet.
- Kimai REST call:
  `GET {url}/api/timesheets?project={id}&begin=D T00:00:00&end=D T23:59:59&size=200`
  with headers `X-AUTH-USER`, `X-AUTH-TOKEN` AND a browser `User-Agent`
  (without the UA, Cloudflare returns 403 on every request).
- Response is a bare array or `{"data": [...]}`; both shapes occur.
- `activity` is an integer ID, not an object; the ticket label lives in
  `description`. `duration` is seconds.
- A running entry has `end: null, duration: 0` = UNKNOWN hours, never zero.
- Cross-midnight entries are SPLIT at 00:00 (pre-midnight part on the begin
  day, post-midnight part on the end day), matching Kimai's weekly view
  (user rule 2026-10-28).
- Transient TLS/network errors are common on the reference server; retry 3x
  with 2s/4s backoff (pattern proven in fill_hours.py).
- Google writes use the google-mcp credentials
  (`~/.config/google-mcp/credentials.json` + `~/.local/share/google-mcp/tokens.json`),
  single-cell USER_ENTERED writes with read-back verification.
- User requirement (2026-11-16): shared sheet of multiple developers, each
  with a separate Kimai account; future cron runs log everyone automatically.

## Design

1. Config `kimai-accounts.json`: `accounts[]` (name, developer, url, username,
   token, projectId, timezone) plus optional `sheet` defaults
   (spreadsheet_id, tab). Template: `scripts/kimai-accounts.example.json`.
2. One script `scripts/kimai_team_hours.py`, subcommands:
   - `read`        per-account hours for `--date` or `--from/--to` (`--json` for cron)
   - `fill-local`  upsert into a local `.csv` (or `.xlsx` when openpyxl exists)
   - `fill-google` upsert into a Google Sheet tab
   - shared flags: `--config`, `--accounts NAME[,NAME]`, `--dry-run`, `--force`
3. Sheet layout (both targets): `A Date | B Day | <one column per developer>`.
   Rows are keyed by date in column A; missing rows are appended in date order.
4. Book-keeping rules carried over unchanged from the proven single-account
   pipeline: split at midnight, running = unknown, round the SUM at 2dp,
   zero never clears a cell, never fill a future day, verify every write.
5. Cron-ready: `--json` gives pure machine output, exit 0 ok / 1 error /
   2 verification failure. Wrapper: `scripts/run_team_fill.sh`.

## Files

- `PLAN.md`                      this plan
- `SKILL.md`                     the skill
- `scripts/kimai_team_hours.py`  multi-account reader + sheet filler
- `scripts/run_team_fill.sh`     cron wrapper (silent on success)
- `scripts/kimai-accounts.example.json`  config template

## Test plan (results recorded in SKILL.md)

1. Multi-account `read` against the live reference server with two accounts
   (GetMyInvoices project 1 and GMI - Scripts project 69).
2. Cross-midnight split check on 2026-10-26/27/28 (entries 229261, 229565).
3. `fill-local` real write to a scratch CSV plus read-back.
4. `fill-google --dry-run` against the live spreadsheet; live writes wait for
   the user's explicit go.

## Out of scope

- TopTracker and the personal worked-hours sheet (`fill_hours.py` unchanged).
- Creating the shared team spreadsheet itself.
- UI or dashboards.
