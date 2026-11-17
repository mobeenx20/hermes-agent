---
name: multi-kimai-hours
description: Use when filling a shared team sheet from multiple Kimai tracker accounts. Reads every developer's Kimai hours and fills local CSV or Google Sheets.
version: 1.0.0
metadata:
  hermes:
    tags: [kimai, team, hours, google-sheets, csv, multi-account]
---

# Multi-Kimai Team Hours

Read tracker hours from MULTIPLE Kimai accounts (one per developer) and fill
one shared sheet: local CSV or Google Sheets. This is the team-scale sibling
of the single-account `fill_hours.py` pipeline (toptracker-hours skill); that
pipeline is untouched by this skill.

## When to use

- "Fill the team sheet", "log everyone's Kimai hours", "add X's hours".
- Setting up the recurring (cron) fill for the whole team.
- Auditing what any Kimai account recorded for a day or range.

## Layout

```
A Date (ISO) | B Day | C..  one column per developer, header row 1
```

Rows are keyed by the date in column A; missing rows are appended in date
order. Developer columns come from the config's `developer` fields, in config
order.

## Config

`~/.hermes/config/kimai-accounts.json` (template:
`scripts/kimai-accounts.example.json`):

```json
{
  "sheet": {
    "spreadsheet_id": "REPLACE_WITH_TEAM_SHEET_ID",
    "tab": "TeamHours",
    "csv": "~/team-hours.csv"
  },
  "accounts": [
    {"name": "dev-a-gmi", "developer": "Developer A",
     "url": "https://kimai.example.com", "username": "dev-a",
     "token": "...", "projectId": 1, "timezone": "Asia/Karachi"}
  ]
}
```

- One account per developer: their own Kimai username + API token.
- `name` is the CLI key (`--accounts dev-a-gmi`), `developer` is the sheet
  column header. `projectId` filters to that developer's project.
- Credentials live ONLY in the config file. Never commit it.

## Commands

```bash
PY=~/.hermes/hermes-agent/venv/bin/python
S=~/.hermes/skills/productivity/multi-kimai-hours/scripts/kimai_team_hours.py

$PY $S read --date 2026-11-16                 # today, all accounts
$PY $S read --from 2026-11-10 --to 2026-11-16 # a range
$PY $S read --accounts dev-a-gmi --json       # one account, machine output
$PY $S fill-local  --date 2026-11-16          # write the CSV
$PY $S fill-google --date 2026-11-16          # write the Google tab
$PY $S fill-local --date 2026-11-16 --dry-run # report only, write nothing
```

Shared flags: `--config`, `--accounts NAME[,NAME]`, `--date` / `--from`+`--to`,
`--force`, `--dry-run`, `--json`. Exit codes: 0 ok, 1 error, 2 verify failure.

Cron wrapper `scripts/run_team_fill.sh`: silent on success (empty stdout),
prints only when attention is needed; safe for `no_agent` cron jobs.

## Book-keeping rules (non-negotiable)

- **Midnight split:** a cross-midnight entry is split at 00:00; the
  pre-midnight part counts on the begin day, the post-midnight part on the
  end day (matches Kimai's weekly view; user rule 2026-10-28).
- **Running = unknown:** an entry with `end: null, duration: 0` is excluded
  from sums and flagged. Never treat it as zero.
- **Round the SUM at 2dp**, never the individual rows.
- **Zero never clears:** a 0.00 reading never erases a cell that holds value.
- **No future days:** a date after today is skipped and noted.
- **Verify every write:** read back after writing; exit 2 on mismatch.
- **No silent overwrite:** a cell holding a DIFFERENT non-zero value is kept
  and noted (STALE below the reading auto-repairs; above needs `--force`).

## Kimai API facts (proven)

- `GET {url}/api/timesheets?project=ID&begin=D T00:00:00&end=D T23:59:59&size=200&page=N`
  with `X-AUTH-USER` + `X-AUTH-TOKEN`.
- A browser `User-Agent` header is REQUIRED: without it Cloudflare 403s every
  call (looks like a rotated token; it is not).
- Response is a bare array OR `{"data": [...]}`. Handle both.
- `activity` is an integer ID, not an object; the ticket label lives in
  `description` (shape `TECH-<n>/<epic-slug>`).
- `duration` is seconds; entries paginate at 200/page.
- Transient TLS/network errors are common: retry 3x with 2s/4s backoff
  (already built into the script).

## Cross-target consistency

`fill-local` and `fill-google` apply identical cell rules, so the CSV and the
Google tab converge to the same numbers. The Google tab is keyed by date
serials when read back (`UNFORMATTED_VALUE`), so the date match handles both
serial numbers and ISO text.

## Pitfalls

1. **Google auth is the google-mcp token pair** (`~/.config/google-mcp/credentials.json`
   + `~/.local/share/google-mcp/tokens.json`). If fill-google exits with an
   auth error, refresh with `scripts/google_token_refresh.py` (work-hours-tracking
   skill) and retry. `fill-google` re-execs into the Hermes venv for
   `google-api-python-client` automatically.
2. **Header drift:** if a developer is added to the config, their column must
   exist in the tab header row. The script refuses to guess a column and
   errors listing what is missing; add the header cell first.
3. **Do not hand-edit the CSV and the Google tab differently**; rerun
   `fill-local`/`fill-google` to converge, or fix one side and let the fill
   repair the other (STALE auto-repair handles growth).
4. **Account names are keys**, developer names are labels. Renaming
   `developer` renames the column and orphans old data; treat both as stable
   once used.
5. **A wholesale mismatch** (totals entirely different from expectation) means
   projectId or token changed: do not write, re-check the config first.

## Validation snapshot (2026-11-16, reference server)

Two accounts read live (GetMyInvoices project 1, GMI - Scripts project 69):
- 2026-11-16 project 1: 3 closed entries = 8.53h (12840+10500+7380 sec).
- Cross-midnight checks 2026-10-26/27 (entries 229261, 229565) reproduce the
  established split figures (see work-hours-bot-ops, Oct 26-28 note).
- `fill-local` wrote and verified a scratch CSV; `fill-google --dry-run`
  produced a plan without touching the sheet.

## Related

- Personal single-account pipeline: `toptracker-hours` skill,
  `~/.hermes/scripts/fill_hours.py` (column C/H of the personal sheet).
- Sheet conventions and Google auth repair: `work-hours-tracking` skill.
- Operating routines around hours: `work-hours-bot-ops` skill.
