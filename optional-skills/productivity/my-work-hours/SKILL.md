---
name: my-work-hours
description: Track all work hours in the Mobeen worked hours Google Sheet — Dizio (auto-filled via calendar + Fathom), MTMPRO, Claude-repo, designer-agent, and other projects.
version: 2.0.0
metadata:
  hermes:
    tags: [google-sheets, dizio, time-tracking, calendar, fathom, work-hours]
---

# My Work Hours

**SUPERSEDED 2026-09-25. The plugin this skill describes does NOT exist on this machine** (`~/.hermes/plugins/` is absent; none of the tools listed below exist, and the `null`-clearing advice in the pitfalls is wrong). Do not follow this skill for automation. Use instead: `toptracker-hours` (daily fill, columns D/H, crons), `work-hours-tracking` (Dizio/Fathom/calendar reference), `work-hours-monthly-tab` (tab building), `work-hours-reporting` (readouts).

Track all work hours in the "Mobeen worked hours" Google Sheet: Dizio hours (calendar + Fathom), MTMPRO (tracked + untracked), GMI, and other projects. Kept for historical reference only.

## Key Constants

```
Spreadsheet ID: REPLACE_SPREADSHEET_ID
Sheet name:     Mobeen worked hours
Tab naming:     "June26", "July26", etc (MonthYear, mixed case like "FEb26", "March26")
Plugin dir:     ~/.hermes/plugins/my-work-hours/
Hermes venv:    ~/.hermes/hermes-agent/venv/bin/python
```

## Plugin (Preferred Method)

The plugin at `~/.hermes/plugins/my-work-hours/` provides dedicated tools:

| Tool | Description |
|------|-------------|
| `fill_dizio_today` | Fill today's hours — auto-checks calendar + Fathom, applies defaults, never fills future dates |
| `fill_dizio_range` | Fill a date range with the same logic |
| `create_dizio_tab` | Create a new monthly tab with full calendar + color formatting |
| `dizio_status` | Show monthly summary — total hours, days filled, per-day breakdown |
| `add_work_entry` | Log non-Dizio project hours — appends to D column, sums in E column |
| `repair_dizio_colors` | Fix/reset background colors on any monthly tab |
| `work_status` | Full monthly breakdown: Dizio + Other hours with per-day notes |

**Slash commands:** `/work-today`, `/work-status`, `/work-repair`

**When to use:** Prefer `fill_dizio_today` for single-day filling. The plugin encodes all rules so you never string together manual MCP calls. Restart Hermes after enabling or editing the plugin.

## Daily Defaults

- **Weekdays**: 1 hour default (code review, general Dizio dev work)
- **Dizio Sync meetings**: 2 hours by default, 3 hours if the calendar event or Fathom recording duration exceeds 1 hour 30 minutes
- **Client no-show**: Still counts as full meeting hours if scheduled
- **Weekends**: Empty (Sat/Sun)
- **Only fill up to the current date** — never pre-fill future days. The user explicitly corrected this.
- **No descriptions in Others column** — hours only in column C. The user explicitly asked to remove descriptions.

## Sheet Structure

```
A: Date         B: Day          C: DIZIO WORKED HOURS
D: Other Project   E: Others   F: (extra hours)
```

- Row 1: Title — "MOBEEN WORKED HOURS" (merged C-F, bold, centered)
- Row 2: Headers — bold
- Row 3+: Calendar days
- Row index formula: date N = row N+2
- **Meeting notes (Dizio Sync, Impromptu, etc.) go in column D (Other Project), not column E (Others).** Column E is reserved for additional hours only. Column C is for Dizio hours only.
- **Never remove existing data.** When adding to a cell that already has content (appending a meeting name to column D, or increasing hours in column E), always preserve what's there. Column D entries are comma-separated. Column E is a running total of non-Dizio hours for the day. Example: D4="Dizio Sync" + MTMPRO meeting → D4="Dizio Sync, MTMPRO Weekly Dev", E4=3 + 1h → E4=4.
- **When logging non-Dizio work, use the `add_work_entry` tool, not manual sheet edits.** It appends the project name to column D and sums the hours into column E — never removing or overwriting existing data.

## Color Fill Conventions

Background colors applied per row (columns A-E):

| Row(s) | Color | RGB | Purpose |
|--------|-------|-----|---------|
| 1 | Orange | `(0.902, 0.569, 0.220)` | Title bar |
| 2 | Green | `(0.576, 0.769, 0.490)` | Column headers |
| Sat/Sun rows | Yellow | `(1, 0.851, 0.4)` | Weekend marker |
| Mon-Fri rows | White/default | — | Weekdays |

The color fill is applied via Google Sheets `batchUpdate` with `repeatCell` requests. Full API pattern documented in `references/sheet-colors.md`.

**New tabs get colors automatically.** `create_dizio_tab` / `_populate_calendar` now calls the `_apply_colors` helper, so a freshly created tab already has the orange title, green headers, and yellow weekends — no manual repair pass needed. If colors later drift from manual edits, run the `repair_dizio_colors` plugin tool (or `/work-repair`) to reset the scheme without touching any cell data.

## Workflow: Daily Hour Filling (Manual)

When using MCP tools instead of the plugin:

1. **Check Google Calendar** for Dizio meetings:
   ```
   mcp_google_calendar_list_events with q="dizio" for the month range
   ```
   - Read start/end times, calculate duration. If > 90 minutes → 3h; otherwise → 2h.
   - Update sheet column C for hours, column D for meeting label (e.g. "Dizio Sync").

2. **Check Fathom emails** for verification and ad-hoc meetings:
   ```
   mcp_google_gmail_search with query='from:no-reply@fathom.video after:YYYY/MM/DD before:YYYY/MM/DD'
   ```
   - If a calendar event exists but no Fathom email → client may have no-showed (still count hours).
   - If no calendar event but Fathom email exists → ad-hoc meeting. Parse duration from HTML body to determine 2h vs 3h.

3. **Fill default 1h** for non-meeting weekdays. Use `mcp_google_sheets_update` with `null` for weekends.

4. **Never fill future dates.**

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
- "Recap of your meeting with Dizio" — standard Dizio sync (majority of emails)
- "Recap for 'Impromptu Google Meet Meeting'" — impromptu/ad-hoc meetings. These are **always counted** as Dizio meeting hours (2h default, 3h if duration > 90 min). They are checked alongside calendar meetings and take effect when no calendar "Dizio Sync" exists for the same date. When both a calendar meeting and an impromptu Fathom recap land on the same day, the note reads "Dizio Sync + Impromptu" and the calendar meeting hours apply.
- "Reminder: Your AI notetaker will join..." — pre-meeting reminder, NOT a recap. Ignore these.

**Scan results (72 emails, June 2026):** 71 parsed, 1 unparseable (the reminder email). Longest Dizio meeting: 31 minutes (Oct 31, 2025). The 1h30m threshold for 3h has never been hit by Fathom duration alone — it only triggers from longer calendar-scheduled events. Full scan data in `references/fathom-scan.md`.

## Calendar Cross-Reference

Dizio meetings on calendar:
- Title: "Dizio Sync"
- Attendees: info@dizio.app, mobeen.ahmed@contrivesolution.com
- Duration: typically 1 hour (logged as 2h unless > 90 min → 3h)
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

Use the plugin's `create_dizio_tab` tool, or manually:
```bash
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/skills/productivity/my-work-hours/scripts/format_worked_hours.py "July26" 7 2026
```

## Common Pitfalls

1. **Never pre-fill future dates** — user corrected this. Only fill up to today. The plugin enforces this.
2. **No descriptions in Others column** — user explicitly asked to remove. Hours only in column C.
3. **Email body extraction** — Fathom emails store the body in `payload.body.data` directly, NOT in `parts[0].body.data`. Always check both.
4. **Merged cell titles get lost** on bulk writes — restore with: `sheets_update(range="Tab!C1", values=[["MOBEEN WORKED HOURS"]])`.
5. **To clear a cell via the direct Sheets API, write `""`, never `null`.** `null` is silently ignored and the cell keeps its value (verified Aug 2026). This pitfall previously stated the opposite.
6. **Fathom duration `&bull;` vs `•`** — the HTML uses `&bull;` entity, not the Unicode `•` character. Use `&bull;` in regex searches.
7. **Format script wipes data** — only run `format_worked_hours.py` for brand-new tabs. Use `mcp_google_sheets_update` for everything else.
8. **Row math: target single cells, never ranges** — date N lives at row N+2. When filling via manual MCP calls, use a single-cell range like `"June26!C13"`, never a batch range like `"June26!C14:C15"`. A range shifts every cell by one row from intent and silently overwrites adjacent rows, including weekends. The plugin tools (`fill_dizio_today`, `fill_dizio_range`) handle row math correctly — use them instead of manual MCP calls whenever possible.
9. **Plugin auth depends on both google-mcp files** — the plugin reads `tokens.json` for access/refresh tokens and `credentials.json` for OAuth client_id/client_secret. These are separate files with different formats. If the plugin reports credential refresh errors, check both files at `~/.config/google-mcp/` (credentials.json) and `~/.local/share/google-mcp/` (tokens.json). The `scope` field is singular and space-separated — must be `.split()`. Full details in `references/google-mcp-token-format.md`.
10. **sendUpdates is REQUIRED when scheduling meetings** — `mcp_google_meet_schedule` defaults to no notifications. Always pass `sendUpdates="all"`. Calendar invites do NOT appear in Gmail sent folder — verify delivery by checking `responseStatus: "needsAction"` on the attendee via `mcp_google_calendar_get_event`.
11. **Never override the user's specified date** — if the user says "today," schedule today. Don't assume it already passed. If unsure whether the time has passed, ask once, but do NOT silently change the date.
12. **Dual timezone: meetings = client's time, not user's** — Dizio Sync meetings are always scheduled in America/New_York (EST/EDT), the client's timezone. The user is in Asia/Karachi (GMT+5). When the user says "schedule at 7:15 AM EST," that means the client's 7:15 AM, not the user's. 7:15 AM EDT = 4:15 PM GMT+5.
13. **Column D is the meeting notes column** — the plugin (v1.3.0+) writes meeting labels ("Dizio Sync", "Impromptu Meeting", etc.) to column D. If column D already contains a manual entry, the plugin overwrites it. After filling, check and re-append any displaced entries (comma-separated).
14. **403 "insufficient authentication scopes"** — if `/work-today` fails with a 403 and "insufficientPermissions", the OAuth token in `tokens.json` only has Gmail scopes and is missing Calendar, Sheets, or Drive. Check the `scope` field in `tokens.json` — it must include `calendar`, `spreadsheets`, and `drive` (not just `gmail.modify`). Fix: delete `tokens.json` and re-authenticate via `mcp_google_google_auth` to obtain the full 14-scope token from the google-mcp server. The `google_auth` tool opens a browser for OAuth consent; if the auto-flow fails to write the file (known issue), fall back to manual auth via `google_auth_code` or run the MCP server's OAuth module directly. Full scope list and all fix options in `references/google-mcp-scopes.md`.
15. **Color drift** — `create_dizio_tab` / `_populate_calendar` now applies the full color scheme automatically via `_apply_colors`, so new tabs are already colored. But manual edits can still shift or clear weekend coloring over time. Run `repair_dizio_colors` (or `/work-repair`) to reset the orange/green/yellow scheme without touching data.
16. **Never remove or overwrite existing data in columns D or E** — when adding a new meeting or project entry, append to the existing D value (comma-separated) and sum into the existing E value. The user explicitly forbids removing data that has already been added.
17. **Adding non-Dizio entries** — use the `add_work_entry` tool, not manual sheet edits. It appends the project name to column D and sums the hours into column E, so existing entries are preserved.

## Google MCP Setup

The Google Workspace MCP server (`quinnjr/google-mcp`) is configured at `~/Documents/agent-tools/google-mcp/`. Credentials at `~/.config/google-mcp/` (credentials.json) and `~/.local/share/google-mcp/` (tokens.json). Full setup guide in `references/google-mcp-setup.md`.
