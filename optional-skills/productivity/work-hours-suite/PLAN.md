# Work-hours suite: plan and delivery notes

Goal: get the personal work-report and work-hours skills off this machine and
onto GitHub, exactly as they run today, with credentials stripped to
placeholders. These nine skills plus the runtime scripts are the live
book-keeping stack; until now they existed only in the profile directory,
which is not a git repo.

## What ships here

Nine skills under `optional-skills/productivity/`, copied verbatim from the
active profile:

- `work-hours-tracking`     sheet conventions, meetings, Fathom, Google MCP
- `toptracker-hours`        day fill (TopTracker C + Kimai H), weekly targets
- `work-hours-bot-ops`      routines, FLAG protocol, leave days, audits
- `work-hours-monthly-tab`  monthly tab builder and layout rules
- `work-hours-reporting`    reporting hours from the sheet
- `my-work-hours`           the original worked-hours skill
- `mtmpro-weekly-report`    Slack weekly team report
- `work-reports`            work-reports MCP operations
- `work-report-summary`     daily/weekly report summaries

Runtime scripts under `work-hours-suite/scripts/` (installed to
`~/.hermes/scripts/`): `fill_hours.py`, `fill_hours_alert.py`,
`fill_hours_nightly.sh`, `hours_overnight_scan.py`, `toptracker_api.py`,
`toptracker_weekly_sync.py`, `toptracker_weekly_catchup.sh`, plus
`scripts/tests/test_hours_scripts.py`.

## Sanitization (applied before commit)

- Live Google Spreadsheet ID replaced with `REPLACE_SPREADSHEET_ID`
  (12 files across skills and scripts).
- Credential sweep for OAuth tokens, client secrets, API keys, Slack
  webhooks, and private keys: clean, only code references and documented
  `xxx` placeholders remain.
- No `kimai.json`, `tokens.json`, `credentials.json`, or `settings.ini`
  contents are in this tree; those stay under `~/.config` and
  `~/.hermes/config` on the machine.

## Restore

1. Copy the nine skill dirs to `~/.hermes/profiles/static/skills/productivity/`.
2. Copy `work-hours-suite/scripts/*` to `~/.hermes/scripts/`.
3. Re-inject the real Spreadsheet ID into `REPLACE_SPREADSHEET_ID` slots
   (fill_hours.py, build_month_tab.py, format_worked_hours.py,
   toptracker_sync.py, sheet-colors.md, and the SKILL.md docs).
4. Recreate `~/.hermes/config/kimai.json` from the example in the
   `multi-kimai-hours` branch or from the machine backup.

## Out of scope

- The `multi-kimai-hours` skill lives on branch `skill/multi-kimai-hours`.
- Google MCP setup binary and its credential files.
- Anything outside the nine skills and the hours scripts listed above.
