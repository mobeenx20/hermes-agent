---
name: work-hours-tracking
description: Fill the Mobeen worked hours Google Sheet with daily project hours, cross-referencing calendar meetings and Fathom recordings. Handles Dizio sync, MTMPRO client meetings, Impromptu meetings, and any project work.
version: 2.1.0
metadata:
  hermes:
    tags: [google-sheets, time-tracking, calendar, fathom, dizio, mtmpro]
---

# Work Hours Tracking

> **LAYOUT OVERRIDE (2026-10-22):** the tab was restructured by the user: the Dizio column was deleted, Broadcasting Platform inserted at E, and fill_hours.py's TRACKED_COL moved from D to C. Current map: C=MTMPRO TRACKED, D=MTMPRO UNTRACKED, E=BROADCASTING PLATFORM, F=labels, G=others, H=GMI, I=USAMA TRACKED (log), J=USAMA PRODUCTIVE, K=USAMA DIFF (formula). Every column letter in the body below predates that date unless restated: map old-E (untracked) to D, old-D (tracked) to C, and treat old-C (Dizio) as gone.

Track daily working hours in the "Mobeen worked hours" Google Sheet. Covers all project meetings: Dizio sync, MTMPRO client meetings, Impromptu ad-hoc meetings, and any project work. Automation on this machine runs through two scripts, NOT through plugin tools: `fill_hours.py` (columns C + H + weekly block) and `build_month_tab.py` (monthly tab structure). The plugin tool layer this skill was originally written around is NOT installed here (see Automation Engines below). All Google API access (Gmail, Calendar, Sheets, Meet) goes through the `quinnjr/google-mcp` server at `~/Documents/agent-tools/google-mcp/`.

## Key Constants

```
Spreadsheet ID: REPLACE_SPREADSHEET_ID
Sheet name:     Mobeen worked hours
Tab naming:     "September26", "October26" (MonthYear; older tabs vary: "FEb26", "Dec-Jan ")
Hermes venv:    ~/.hermes/hermes-agent/venv/bin/python

Automation:     fill_hours.py      daily C/H fill + weekly block (toptracker-hours skill)
                build_month_tab.py monthly tab structure (work-hours-monthly-tab skill)
                ~/.hermes/plugins/ is ABSENT: none of fill_dizio_today / add_work_entry /
                add_mtmpro_entry / work_status / create_dizio_tab / repair_dizio_colors
                exist on this machine (verified 2026-09-25).

Google MCP:     ~/Documents/agent-tools/google-mcp/ (HTTP service on 127.0.0.1:3015)
MCP creds:      ~/.config/google-mcp/credentials.json + ~/.local/share/google-mcp/tokens.json
```

## Automation Engines (what actually runs here)

The plugin tool layer is NOT installed on this machine (`~/.hermes/plugins/` does not exist; verified 2026-09-25). Replacements for every tool this skill used to name:

| Old tool (does not exist here) | Use instead |
|--------------------------------|-------------|
| `fill_dizio_today`, `fill_dizio_range` | `~/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/fill_hours.py --date YYYY-MM-DD` (fills C + H + weekly block; toptracker-hours skill) |
| `add_work_entry` | Single-cell USER_ENTERED write: label to F, hours to G (`scripts/sheet_write_checked.py` = merge check + write + read-back) |
| `add_mtmpro_entry` | Single-cell USER_ENTERED write into D (MTMPRO UNTRACKED); C only when the user says tracked |
| `work_status`, `dizio_status` | `fill_hours.py --dry-run`, or the work-hours-reporting skill |
| `create_dizio_tab` | `build_month_tab.py --month M --year YYYY` (work-hours-monthly-tab skill) |
| `repair_dizio_colors` | No repair tool; colors come from the builder scripts |

The Dizio column was removed 2026-10-22. Daily columns: C MTMPRO tracked,
D MTMPRO untracked, E Broadcasting Platform, F labels/notes, G others, H GMI.

## MCP Access Patterns

The google-mcp server runs as an HTTP MCP service on `http://127.0.0.1:3015/mcp` (declared under `mcp_servers.google` in `~/.hermes/config.yaml`; it is up whenever Hermes runs). In-session, the `mcp__google__*` tools are the preferred path.

**Do NOT run `node ~/Documents/agent-tools/google-mcp/dist/index.js` to pipe JSON-RPC into it** — with the service running that crashes with `EADDRINUSE` (verified 2026-09-25; the old "terminal JSON-RPC" fallback is obsolete).

Terminal fallback that works (verified 2026-09-25), over HTTP:

```bash
# 1. initialize; capture the session id from the response headers
SID=$(curl -si -X POST http://127.0.0.1:3015/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"agent","version":"1"}}}' \
  | grep -i '^mcp-session-id' | tr -d '\r' | awk '{print $2}')

# 2. complete the handshake (required before tools/call)
curl -s -X POST http://127.0.0.1:3015/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H "mcp-session-id: $SID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3. call a tool
curl -s -X POST http://127.0.0.1:3015/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -H "mcp-session-id: $SID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"sheets_read","arguments":{"spreadsheetId":"...","range":"September26!A1:H30"}}}'
```

Responses arrive as SSE (`event: message` + `data: {...}` lines).

## Recurring Meeting Automation (Cron Jobs)

For weekly recurring meetings (MTMPRO Thursdays, team standups, etc.), set up a cron job that fills the sheet. The fill runs through `fill_hours.py` plus a single-cell untracked-hours write; the cron invokes that on schedule.

### Cron Reliability: Gateway Required

Cron jobs run inside the Hermes scheduler process. If no Hermes process is running at the scheduled time, the job skips that tick. For reliable execution:

- **Gateway background service (required):** `hermes gateway install && hermes gateway start` keeps a persistent Hermes process running 24/7. Cron jobs tick on schedule regardless of whether a terminal is open.
- **CLI-only (not reliable):** closing the terminal stops the scheduler. Jobs only fire when a `hermes` session is open.

### Setting Up a Recurring Meeting Cron

Use the `cronjob` tool with `action='create'`:

```
cronjob(
  action='create',
  name='MTMPRO Thursday Meeting',
  schedule='0 20 * * 4',              # 8 PM GMT+5 every Thursday
  skills=['toptracker-hours'],
  prompt='Log the weekly meeting for today. Steps:
1. Run: ~/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/fill_hours.py
   (fills column C + H and refreshes the weekly block).
2. Add the untracked meeting hours as a single-cell USER_ENTERED write into
   column D (MTMPRO UNTRACKED) of the current month tab; use C only if the
   user explicitly asks for tracked hours.',
)
```

- **Schedule:** use the user's local timezone (GMT+5 = Asia/Karachi). 5-field cron: `minute hour * * weekday` (0=Sun, 4=Thu). Schedule late in the day (e.g. 8 PM) so manual same-day fills happen first.
- **Prompt:** must be self-contained since cron runs in a fresh session with no conversation context.
- **Skills:** attach `toptracker-hours` so the cron session finds the fill script and column rules.
- **Delivery:** default `local` saves output but doesn't notify. Switch to `deliver='telegram'` or `deliver='all'` if the user wants confirmation pings.

### Pitfall: Manual Fill + Same-Day Cron = Double Count

If you manually fill a meeting entry for today AND the cron job fires later the same day, the untracked-hours write can land twice (doubled column D hours). Mitigations:

1. **Schedule cron late in the day** (e.g. 8 PM) so manual fills happen first and cron is the final word.
2. **Pause the cron** on days you manually fill early: `cronjob(action='pause', job_id='...')`. Unpause after the scheduled time passes.
3. **Check the sheet after first run** to confirm no double-count.

## Non-Dizio Meeting Logging (MTMPRO, Impromptu, etc.)

When the user mentions a meeting with a non-Dizio client (MTMPRO, mobile-app stakeholder, interview), there is no auto-detection. Log it by hand:

### Step-by-step flow

1. **Run the tracker fill** for the date: `~/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/fill_hours.py --date YYYY-MM-DD` (fills C + H + weekly block).

2. **Search Gmail for Fathom recaps** to confirm the meeting and its length: in-session `mcp__google__gmail_search`, or the HTTP curl pattern from MCP Access Patterns.

3. **Key Fathom search queries:**
   - `fathom "Impromptu Google Meet Meeting"` — ad-hoc MTMPRO/client meetings. The Fathom subject is ALWAYS "Recap for \"Impromptu Google Meet Meeting\"" regardless of what you discussed; identify the meeting from context, not the subject.
   - `fathom "Recap of your meeting with Dizio"` — standard Dizio sync
   - `fathom mtmpro` — any MTMPRO-related Fathom recap
   - `fathom after:YYYY/MM/DD before:YYYY/MM/DD` — date-bounded search

4. **Get the full message to extract duration:** in-session `gmail_get_message(messageId="<id from search>")`. Duration is in the HTML body near "View Meeting": `36 mins&nbsp; <span` or `1 hr 15 mins&nbsp;`

5. **Log the hours** as a single-cell USER_ENTERED write. Default MTMPRO meetings and manual fixes to D (MTMPRO UNTRACKED); write C only when the user explicitly says the entry belongs in tracked hours. Non-MTMPRO work gets an F label and hours in G. Use the duration the user states first, then the Fathom recap, then the calendar block; fall back to 2h only when none of those gives a length. A stated duration wins even when it is shorter than the calendar block or the 2h fallback. Convert minutes to decimal hours at 2dp (30m = 0.50, 50m = 0.83).

6. **Verify** by reading the row back; the weekly block updates through its live formulas.

### Common meeting types and their logging

| Meeting type | Where the hours go |
|-------------|--------------------|
| Dizio sync (calendar or Impromptu Fathom) | no column (Dizio retired 2026-10-22); note to F if it still happens |
| MTMPRO client meeting / Weekly Dev | D (untracked); C when the user says tracked |
| Usama meeting (he works on MTMPRO) | D (untracked); C only on explicit instruction |
| Interview / other project | F label + G hours (Others) |
| Rohan / management meeting | F label + G hours (Others) |

### Multi-meeting days

When a day has both a Dizio meeting and a non-Dizio meeting:
- **Column C**: MTMPRO tracked hours (tracker, or a meeting the user explicitly moved to tracked)
- **Column D**: sum of the untracked MTMPRO hours
- **Column F**: comma-separated labels, e.g. "MTMPRO Weekly Dev, MTMPRO"; **Column G**: other-project hours

- **No automatic Dizio hour**: do not write a 1h default into C on a manual fill (user correction). Log Dizio only from a real meeting or explicit instruction; impromptu calls count at their actual duration.
- **Dizio Sync meetings**: retired; log only on explicit instruction, at the actual duration.
- **Client no-show**: still counts as full meeting hours if the meeting was scheduled.
- **Weekends**: empty (Sat/Sun).
- **Only fill up to the current date** — never pre-fill future days. The user explicitly corrected this.

## Dictated day hours ("add Xh for <date>")

When the user dictates hours for specific days, the number is the day's VALUE,
not an increment: C already holds the tracker's hours, so write the remainder
to D so that C + D reads exactly that number (tracker 3.75 + D 1.25 = 5.00).
Test before writing: if treating the number as an increment produces an
implausible day total, it is a value. Read the day back and refresh the block
with `fill_hours.py --summary-only`.

- A meeting reported afterwards for a day that already carries a dictated value
  is added ON TOP (7.00 + 0.75 = 7.75; D grows by 0.75, label to F).
- "Check the tracker" for a day means read that day's C and report the exact
  number; if the user then gives a time span, the span wins and replaces the
  tracker-derived hours for that day.
- D only accumulates: sum into the cell, never overwrite (Pitfall 24).

## Usama hours (columns I and J)

The user dictates both figures for Usama's day, in h:mm with his own words:
"log" (tracked) is column I, "productive" is column J. Convert each h:mm to
decimal hours at 2dp (8h20 -> 8.33, 7h50 -> 7.83), write I and J as separate
single-cell USER_ENTERED writes, and read both back; K (`I - J`, empty guarded)
computes itself, never write K.

- Both columns are user-dictated only: never fill them from a tracker and never
  treat J as a subset of I. J is the figure that counts toward the MTMPRO team
  quota; I is his raw log that he reconciles against.
- Writing I/J does NOT move the team block: the team week row's member cells
  are static, so also set that week's "Usama (reported)" cell to the sum of J
  for the week and let the row's Total and the MONTH TOTAL formulas recompute
  (toptracker-hours, "Weekly block targets"). Read the week row and the month
  total back and quote both.

## Labeling Conventions (Column F, Row Notes in L, Two-Month Cell Note)

- **Project labels live in F** (excluded from sums): meeting names like "MTMPRO", "Dizio Sync".
- **Row-level quota and reallocation notes live in L**, the daily grid note column. The **two-month net is a cell note**, not visible L text: attach it to the last weekday's A cell of the second month in the fixed pair (Oct 2026: A32, 30 Oct). Pairs are Sep-Oct, Nov-Dec, Jan-Feb; do not roll one month forward (after Sep-Oct comes Nov-Dec). Do not put general notes in F; F is parsed for `Leave` and `Half day`, so a free-form note there can silently change the week target.
- **Hours never go into F or L.** MTMPRO untracked hours -> D; explicitly tracked MTMPRO -> C; other-project hours -> G; GMI -> H. There is no Dizio column.
- **Days with no actual work**: clear the day's cells only when the user says so.
- **After any fill run:** present the result and confirm labels/hours with the user; never assume the fill is final.

## Sheet Structure (current tabs: August 2026 onward)

```
A: Date   B: Day   C: MTMPRO TRACKED   D: MTMPRO UNTRACKED   E: BROADCASTING PLATFORM
F: Other Project (labels)   G: Others (hours)   H: GMI
I: USAMA TRACKED (log)   J: USAMA PRODUCTIVE   K: USAMA DIFF (live I-J formula, never written)
L: daily row notes (not summed)
```

- Row 1: titles ("MOBEEN WORKED HOURS" merged A-H, "USAMA WORKED HOURS" at I); Row 2: headers; date N = row N+2.
- RESTRUCTURED 2026-10-22 (user): the Dizio column was deleted and Broadcasting Platform inserted at E; fill_hours.py's TRACKED_COL moved D to C in the same edit. Deleting a column slides existing values with it (a value written to old-D arrives at C).
- Column C: TopTracker territory, normally written by `fill_hours.py` (was D before 2026-10-22). A user-confirmed tracked meeting is a single-cell manual write; record the reason in F.
- Column D: untracked MTMPRO (meetings incl. Usama, fixes when the tracker was off). Column E: Broadcasting Platform.
- Column F: project labels, EXCLUDED from sums. Column L: daily row notes, EXCLUDED from sums. Column G: hours for non-MTMPRO work (Others).
- Column H: GMI (Kimai), written by `fill_hours.py`. Columns I and J: Usama's day, both user-dictated (see Usama hours below); K is a live `I-J` formula with an empty guard, so never write K.
- Legacy tabs BEFORE August 2026 use the old 6-column layout (D = Other Project, E = Others): never write the MTMPRO columns into them.
- **Never remove existing data.** Append/sum into existing cells per the column rules above.

## Color Fill Conventions

Current tabs (August 2026 onward) get their colors from `build_month_tab.py` at build time (navy/steel/cream family); do not hand-apply colors, and there is no repair tool on this machine.

The orange/green/yellow scheme below describes the LEGACY pre-August layout only; never apply it to new tabs:

| Row(s) | Color | RGB | Purpose |
|--------|-------|-----|---------|
| 1 | Orange | `(0.902, 0.569, 0.220)` | Title bar (legacy) |
| 2 | Green | `(0.576, 0.769, 0.490)` | Column headers (legacy) |
| Sat/Sun rows | Yellow | `(1, 0.851, 0.4)` | Weekend marker (legacy) |

The legacy API pattern (batchUpdate repeatCell) is in `references/sheet-colors.md`.

## Workflow: Direct Google API Access (Manual)

Prefer the in-session `mcp__google__*` tools. When they are unavailable, use the
HTTP curl pattern from MCP Access Patterns (there is no other fallback any
more). Useful calls: `google_auth_status` (must return "authenticated": true),
`gmail_search` (e.g. query='fathom', maxResults=10), `gmail_get_message`,
`sheets_read`, `sheets_update`.

Clearing cells: `sheets_update` with `values: [[""]]` — `null` is silently
ignored (Pitfall 5). Never clear more than the exact wrong cells. A single-cell
`sheets_update` can return success and still leave the cell empty (F4,
2026-11-03); read back, and if unchanged, repeat with a direct
googleapiclient `values().update` USER_ENTERED call.

## Fathom Email Parsing

Fathom emails come from `no-reply@fathom.video`. The actual HTML structure (discovered via debugging):

```
<span style="color:#D3D3D3;">&bull;</span>&nbsp; 40 mins&nbsp; <span style="color:#D3D3D3;">&bull;</span>&nbsp;
<a href="https://fathom.video/calls/702982922?tab=summary">View Meeting</a>
```

**Parsing approach that works:**
1. Find "View Meeting" in the HTML body.
2. Look backwards up to 350 characters for the duration pattern.
3. Capture `(\d+)\s*(h)?\s*(\d+)?\s*m(?:ins?)?` — handles "40 mins", "1h 23m", "1h23m".
4. If the capture group contains "h", first number = hours; otherwise first number = total minutes.

**Critical email body extraction gotcha:** Fathom emails are single-part `text/html` — the body is directly in `payload["body"]["data"]`, NOT in `payload["parts"][0]["body"]["data"]`. Always check `payload.body.data` first, fall back to iterating `parts`.

**Fathom email subjects:**
- "Recap of your meeting with Dizio" — standard Dizio sync. Dizio is retired; no hours column. Note to F only if the user still wants it recorded.
- "Recap for 'Impromptu Google Meet Meeting'" — impromptu/ad-hoc meetings (MTMPRO client calls, team syncs, interviews, etc.). These are **always counted** as meeting hours. Identify the meeting type from context (user says "MTMPRO client meeting" → log as MTMPRO in D, or C when the user says tracked). When both a calendar Dizio meeting and an impromptu Fathom recap land on the same day, column F reads "Dizio Sync, MTMPRO" etc.; the non-Dizio hours go to D (MTMPRO) or G (Others).
- "Recap of your meeting with Contrive Solutions" — MTMPRO Weekly Dev or other Contrive internal meetings. Log to D, or C when the user says tracked, or F/G per the table above.
- "Reminder: Your AI notetaker will join..." — pre-meeting reminder, NOT a recap. Ignore these.

**Scan results (72 emails, June 2026):** 71 parsed, 1 unparseable (the reminder email). Longest Dizio meeting: 31 minutes (Oct 31, 2025). Use the parsed duration, not a standard block; the old 2h/3h meeting convention is retired. Full scan data in `references/fathom-scan.md`.

## Calendar Cross-Reference

Dizio meetings on calendar:
- Title: "Dizio Sync"
- Attendees: info@dizio.app, mobeen.ahmed@contrivesolution.com
- Duration: use the actual calendar or recording length; Dizio is retired, so log only on explicit instruction.
- **Client timezone (meeting is scheduled in):** America/New_York (EST/EDT)
- **User's timezone:** Asia/Karachi (GMT+5)
- 7:15 AM EDT = 4:15 PM GMT+5 (for the user)

## Workflow: Scheduling a Dizio Sync Meeting

Use `mcp_google_meet_schedule` with these parameters:

```
summary: "Dizio Sync"
startTime: ISO 8601 in America/New_York timezone (e.g. "2026-06-29T07:15:00-04:00")
endTime: ISO 8601, 1 hour after start (e.g. "2026-06-29T08:15:00-04:00")
timeZone: "America/New_York"
attendees: ["info@dizio.app", "mobeen.ahmed@contrivesolution.com"]
sendUpdates: "all"    ← REQUIRED — without this, no invitation email is sent
```

**Verification:** After scheduling, call `mcp_google_calendar_get_event` and confirm `info@dizio.app` shows `responseStatus: "needsAction"`. Calendar invites do NOT appear in Gmail sent folder — they are sent by Google's calendar system directly. The `needsAction` status is the proof the invitation was delivered.

## Workflow: New Month Setup

Use the current builder (work-hours-monthly-tab skill):
```bash
~/.hermes/hermes-agent/venv/bin/python \
  ~/.hermes/skills/productivity/work-hours-monthly-tab/scripts/build_month_tab.py \
  --month 10 --year 2026
```
Do NOT use `create_dizio_tab` (not installed) or `format_worked_hours.py` (writes the legacy 6-column layout and overwrites all data).

## Common Pitfalls

NOTE (2026-09-25): items below that name plugin tools (`fill_dizio_today`, `fill_dizio_range`, `add_work_entry`, `add_mtmpro_entry`, `work_status`, `create_dizio_tab`, `repair_dizio_colors`) describe tools that are NOT installed here; the replacement is a `fill_hours.py` run and/or a single-cell USER_ENTERED write (see Automation Engines).

1. **Never pre-fill future dates** — user corrected this. Only fill up to today.
2. **No descriptions in Others column** — hours only; labels go to F, never into hour columns.
3. **Email body extraction** — Fathom emails store the body in `payload.body.data` directly, NOT in `parts[0].body.data`. Always check both.
4. **Merged cell titles get lost** on bulk writes — restore with: `sheets_update(range="Tab!C1", values=[["MOBEEN WORKED HOURS"]])`.
5. **Clearing cells via direct MCP: use `""`, not `null`** — `mcp__google__sheets_update` with `values: [[null]]` succeeds but is silently IGNORED by the API; the cell keeps its value. Use `values: [[""]]` to actually clear a cell (verified Aug 2026).
6. **Fathom duration `&bull;` vs `•`** — the HTML uses `&bull;` entity, not the Unicode `•` character. Use `&bull;` in regex searches.
7. **Legacy creation/format scripts wipe data** — `format_worked_hours.py` writes the old 6-column layout and overwrites everything. For any month from 2026-08 onward use `build_month_tab.py` (work-hours-monthly-tab skill).
8. **Row math: target single cells, never ranges** — date N lives at row N+2. For manual writes use a single-cell range like `"September26!E26"`, never a batch range like `"September26!E25:E26"`. A range shifts every cell by one row from intent and silently overwrites adjacent rows, including weekends. `fill_hours.py` handles row math correctly for C/H.
9b. **"Not authenticated" despite valid files: refresh the token, then call `google_auth` (do NOT restart the service).** The google-mcp server is the systemd user unit `google-mcp.service` (dist/index.js, pooled long-lived process). If it boots while `tokens.json` is expired and its boot refresh fails, `oauth.isAuthenticated` stays false forever: every tool returns "Not authenticated" even though both credential files exist and are valid. `ensureAuthenticated` checks `isReady()` before it ever attempts a refresh, so an expired access token alone does not heal itself. Fix, in order:
   1. Refresh manually: run `scripts/google_token_refresh.py` (this skill, Hermes venv), or POST `https://oauth2.googleapis.com/token` with `grant_type=refresh_token` plus `client_id`/`client_secret` from `~/.config/google-mcp/credentials.json` and `refresh_token` from `~/.local/share/google-mcp/tokens.json`; write back `access_token` and `expiry_date` (ms). The client fields are NESTED under an `installed` key in the downloaded file, so a top-level `cred["client_id"]` raises KeyError; use `cred["installed"]["client_id"]`.
   2. Call the `google_auth` tool. It runs `oauth.initialize()` in-process, sees the fresh token, sets authenticated, and answers "Already authenticated with Google!". No restart needed.
   3. In cron, call `google_auth` and ALL subsequent tools over the HTTP curl pattern (MCP Access Patterns), not the in-session `mcp__google__*` layer: the layer's failure-pause counter keeps rejecting calls ("paused for ~Ns") even after the server itself authenticates, which burns the whole run. Verified 2026-10-02: HTTP `google_auth` returned "Already authenticated" while in-session tools stayed rejected.
   3. `systemctl --user restart google-mcp.service` is BLOCKED for cron runs (security scan flags service restarts). The google_auth path is the cron-safe workaround (verified 2026-09-28).
   After fixing, sanity-check with a must-match query (`newer_than:7d`) before trusting an empty search result: a silent `[]` from a broken auth path looks identical to a real zero-result sweep.
9. **Tool auth depends on both google-mcp files** — tools read `tokens.json` for access/refresh tokens and `credentials.json` for OAuth client_id/client_secret. If tools report credential refresh errors, check both files at `~/.config/google-mcp/` (credentials.json) and `~/.local/share/google-mcp/` (tokens.json). The `scope` field is singular and space-separated, it must be `.split()`. Full details in `references/google-mcp-token-format.md`.
10. **sendUpdates is REQUIRED when scheduling meetings** — `mcp_google_meet_schedule` defaults to no notifications. Always pass `sendUpdates="all"`. Calendar invites do NOT appear in Gmail sent folder — verify delivery by checking `responseStatus: "needsAction"` on the attendee via `mcp_google_calendar_get_event`.
11. **Never override the user's specified date** — if the user says "today," schedule today. Don't assume it already passed. If unsure whether the time has passed, ask once, but do NOT silently change the date.
12. **Dual timezone: meetings = client's time, not user's** — Dizio Sync meetings are always scheduled in America/New_York (EST/EDT), the client's timezone. The user is in Asia/Karachi (GMT+5). When the user says "schedule at 7:15 AM EST," that means the client's 7:15 AM, not the user's. 7:15 AM EDT = 4:15 PM GMT+5.
13. **Column C is TopTracker MTMPRO TRACKED; D is MTMPRO UNTRACKED, not a notes column.** Meeting labels go to F; row notes go to L. If a manual entry sits in C where the fill wants to write, check before overwriting; the user has forbidden silent data loss. A meeting the user moves to tracked goes to C, and its prior D entry is reduced or cleared in the same correction.
14. **403 "insufficient authentication scopes"** — if a Google tool fails with 403 and "insufficientPermissions", the OAuth token in `tokens.json` only has Gmail scopes and is missing Calendar, Sheets, or Drive. Check the `scope` field in `tokens.json` — it must include `calendar`, `spreadsheets`, and `drive` (not just `gmail.modify`). Fix: delete `tokens.json` and re-authenticate via `mcp_google_google_auth` to obtain the full 14-scope token. If the auto-flow fails to write the file (known issue), fall back to manual auth via `google_auth_code`. Full scope list in `references/google-mcp-scopes.md`.
15. **New tabs**: built by `build_month_tab.py` (colors applied at build time). The legacy orange/green/yellow scheme applies only to pre-August tabs.
16. **Never remove or overwrite existing data.** Sum new hours into the target cell (D or G); append labels to F comma-separated. The user explicitly forbids removing data that has already been added.
17. **The tracker fill only auto-detects TopTracker + Kimai.** Internal meetings (MTMPRO, mobile-app standups) are NOT auto-detected. The user will tell you about these meetings — ask if the week looks light, and always confirm after filling that all meetings are captured.
18. **After filling, always present the result and ask the user to confirm labels and hours.** The user frequently adjusts both. Never assume the initial fill is final.

19. **MTMPRO/Impromptu meetings are not auto-detected.** Only TopTracker (C) and Kimai (H) fill automatically. Ad-hoc meetings recorded by Fathom under "Recap for \"Impromptu Google Meet Meeting\"" require manual Gmail search and a manual D write (C when the user says tracked). Always search Gmail for Fathom recaps whenever the user mentions a non-Dizio meeting.

20. **A wrong log is corrected with direct `sheets_update` writes**, clearing the exact wrong cells with `""` (see Pitfall 5). Never leave both the wrong and right entries.

21. **When `mcp__google__*` tools aren't exposed in-session**, use the HTTP curl pattern from MCP Access Patterns. Verify credentials first via `google_auth_status` (must return "authenticated": true).

22. **Fathom Impromptu meeting subjects are generic.** The subject is always "Recap for \"Impromptu Google Meet Meeting\"" regardless of meeting content. Identify the meeting type from context (who the user says they met with), not from the Fathom subject line. Duration is always extractable from the HTML body near the "View Meeting" link.

23. **Don't log a meeting twice.** If the user says "log the MTMPRO meeting", put the hours in D exactly once (C when the user says tracked). Clear the other column only per the user's instruction; never leave the same meeting in both C and D.

24. **Manual hour writes sum into the target cell, never overwrite.** If column D already has 2 and the new entry is 2, D becomes 4. Labels append comma-separated in F: "Project A, Project B".

25. **MTMPRO untracked hours go to column D, NOT E/F/G (since the 2026-10-22 restructure).** Layout (2026-10-22+): C=MTMPRO TRACKED (TopTracker, fill_hours TRACKED_COL), D=MTMPRO UNTRACKED, E=BROADCASTING PLATFORM, F=Other Project (labels), G=Others (hours), H=GMI, I=USAMA TRACKED. The pre-restructure map (August 2026 to 2026-10-22: C=DIZIO, D=TRACKED, E=UNTRACKED) is dead for current tabs; every "column E" reference written before that date means column D now. Writing MTMPRO hours into E books them to Broadcasting Platform.

26. **Moving misplaced entries is safe when correcting the same session's mistake.** If hours land in the wrong column, move them: write the correct cell, clear the wrong cells via direct `sheets_update` with `""` (single-cell or narrow range like `September26!F16:G16`), then read the row back to verify.

27. **Merged cells silently redirect writes (August26, row 16).** August26 has a merged range C16:H16 (sheet row 16 = Aug 14) and a merged row 35 (weekly summary block). Writes to any non-anchor cell inside a merge land in the anchor (C16), so a "National holiday" note written to F16 appeared in C16 and D16 refused values entirely. Before writing to any row, check merges: `spreadsheets().get(spreadsheetId=..., fields="sheets(properties(title,sheetId),merges)")`. If a day row is merged, unmerge first via `batchUpdate` with `unmergeCells`, then write, then read back. Always read back after writes that behave oddly (see fix_row16 pattern: direct googleapiclient with tokens.json/credentials.json from `~/.config/google-mcp/` (credentials.json) and `~/.local/share/google-mcp/` (tokens.json)). One command does the merge check, the single-cell USER_ENTERED write and the read-back: `scripts/sheet_write_checked.py` (this skill; `--dry-run` checks merges only).

28. **Cross-midnight H freeze: never --force H on a day whose overnight portion is booked on the other day.** The begin-day fill ran while the overnight entry was still open, so it summed as 0 and the cell held only same-day hours (verified 2026-10-15: the 21:53->00:19 entry left H16 = 4.50 = the same-day 4.50h entry alone). A later `fill --date <begin day> --force` re-reads the now-closed entry and would overwrite the cell with the whole entry, double-counting the portion booked on the other day. **This supersedes the old whole-entry end-day method.** Current GMI rule: the midnight split in Pitfall 29. Under the split, BOTH days hold part of the entry, so a range fill over either day is a whole-entry overwrite. Refresh split days manually from the entry's clock times; never use a range fill on a split day.

29. **GMI cross-midnight allocation: split at midnight, matching Kimai's weekly view (user rule, 2026-10-28).** The user reconciles GMI to Kimai's weekly timesheet, which splits an overnight entry at 00:00: the pre-midnight part belongs to the BEGIN day, the post-midnight part to the END day. Never book the whole entry to either day. Example Oct 26-28: Mon 21:52->Tue 00:04 (2:12) = 2:08 Mon + 0:04 Tue; Tue 23:20->Wed 00:44 (1:24) = 0:40 Tue + 0:44 Wed, so H28=5.47, H29=6.77, H30=0.73. The week total is unchanged. A begin-day `--force` fill sees the whole closed entry and would put 2:12 on Monday; an end-day booking would put it all on Tuesday; both are wrong. Refresh a split day manually from the entry's start/end clock times, never with a range fill. If the user supplies a Kimai screenshot, its daily h:mm values are authoritative.

30. **Partial-value freeze: a non-empty H or C is not proof of completeness.** A 23:55 fill or a mid-day split can write a partial (0.42 of a running TopTracker session; 0.73 of a split Kimai day) while the rest is still open. When the remainder closes, the next fill's `existing and not force` guard skips the cell, freezing the undercount. `fill_hours.py` now computes `expected_gmi(day)` on the midnight split and auto-repairs an H under-read with a `STALE` note; it flags a C under-read but does not overwrite C without the user's go. `hours_overnight_scan.py` compares C to TopTracker and H to split-aware Kimai every morning, and suppresses a split proposal once both slices are booked. Never treat "already filled" as final; compare to the closed tracker total. The nightly alert parser is `fill_hours_alert.py`; it must match `C: STALE`, `C: tracker reads 0`, skipped days, and the `verified` flag. A wrapper that filters only `D:` notes is blind to the current layout and stays silent while C is short. `fill_hours_nightly.sh` pipes the fill JSON to that parser and keeps stderr separate so a warning cannot corrupt the JSON.

## Google MCP Setup

The Google Workspace MCP server (`quinnjr/google-mcp`) is configured at `~/Documents/agent-tools/google-mcp/`. Credentials at `~/.config/google-mcp/` (credentials.json) and `~/.local/share/google-mcp/` (tokens.json). Full setup guide in `references/google-mcp-setup.md`.
