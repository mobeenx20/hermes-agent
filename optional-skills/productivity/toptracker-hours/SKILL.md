---
name: toptracker-hours
description: Use when filling the worked-hours sheet or auditing tracked hours. One-command day fill (TopTracker column C, Kimai GMI column H), weekly-block targets, and the sync crons.
version: 2.0.2
metadata:
  hermes:
    tags: [toptracker, kimai, time-tracking, sqlite, cron, mtmpro, gmi]
---

# TopTracker Hours

Fill and audit the "Mobeen worked hours" sheet: MTMPRO tracked hours (column C,
from TopTracker) and GMI hours (column H, from Kimai).

## Date verification (MANDATORY, FIRST STEP)

Before responding to ANY query about hours, totals, or week ranges:

1. Confirm the real date with `date`. Trust the system clock over the session
   header and over any date implied by the conversation.
2. Referencing a day by name (Monday, Tuesday...): verify the weekday with
   `date -d YYYY-MM-DD '+%A'`. Never assume.
3. For "this week" or any range, verify the weekday of EVERY date before
   presenting totals.
4. Cross-month weeks (Mon Aug 31 to Fri Sep 4) span two tabs
   (August26 + September26). Totals must pull from BOTH.

HARD RULE. The user said: "make sure you never give me wrong days."

A wrong "today" corrupts every derived number at once. Observed 2026-09-23: the
session context implied Sep 21, the clock said Sep 23, and the Week 4 target was
written as 8h instead of 24h before it surfaced. Earlier failures: Sep 1 2026 is
a Tuesday, not a Monday; on 2026-08-10 a half-day note landed on the wrong row
because the session header said Aug 07.

## The canonical path: one command per day

```bash
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/fill_hours.py --date YYYY-MM-DD
```

One process reads TopTracker (column C), reads Kimai (column H), writes both
cells in one batch, then recomputes the weekly block's targets.

| Flag | Effect |
|------|--------|
| (none) | today |
| `--date YYYY-MM-DD` | a specific day |
| `--dry-run` | report only, no writes |
| `--force` | overwrite cells that already hold a value |
| `--no-summary` | skip the weekly-block refresh |
| `--summary-only` | refresh the block and exit |

Cron wrapper (silent on success, prints only when something needs attention):
`~/.hermes/scripts/fill_hours_nightly.sh`.

The wrapper pipes the fill's stdout to `fill_hours_alert.py`, which alerts on
C stale/zero notes, skipped days, and write-verification failures. A D-only
alert filter is a silent failure; do not reintroduce it.

**Never hand-sum trackers or hand-write block formulas when this script can do
it.** It is idempotent, never clears a cell on a zero reading, and refuses to
write into a merged row. Use raw Sheets writes only for the columns it
deliberately does not own (D, E, F, G).

## Data sources, ranked by reliability

| Source | Gives | Reliability |
|--------|-------|-------------|
| Kimai REST API | any day's GMI total | Authoritative, full history |
| TopTracker local DB `_activity` | per-day MTMPRO sessions | Only per-day source, ROLLING: purges within days |
| TopTracker cloud API | newest activity per project ONLY | No range or list endpoint exists |
| `application.log` | one launch, overwritten each start | That launch only |
| `<email>_work_log` | nothing per-day | UNRELIABLE, do not use |

### The TopTracker API has no history endpoint

Verified by probing: `GET /users/me/activities`, `/activities`,
`/users/me/reports`, `/reports`, `/projects/:id/reports` and
`/projects/:id/activities` all return 404 or 405. `GET /projects/:id` returns
`last_activity` (the single newest activity) and nothing else. Treat the API as
an "is anything new?" probe and a cross-check on the newest row, never as the
source of a day's total.

- Base URL: `https://tracker-api.toptal.com`
- Auth: `remembered-access-token` from `~/.config/TopTracker/settings.ini`,
  passed as `?access_token=TOKEN`. Double-base64 with a hex signature after `--`.
- Wrapper: `~/.hermes/scripts/toptracker_api.py` (`--project 1182888`,
  `--list-projects`, `--json`, `--delete-activity N`).
- `worked_today` lags the web dashboard and only covers desktop-client sessions.
- When the local DB has already purged the days in question, the probe is the
  only per-moment evidence: `worked_today` plus `last_activity` timestamps name
  the newest captured session, so report "the tracker has captured nothing
  since <date>" instead of letting today's C read as a silent zero.
- `POST /projects/:id/activities` creates, it does not list. Internal app-log
  activity IDs differ from API IDs; use API IDs.

## TopTracker DB mechanics

- Path `~/.local/share/TopTracker/TopTracker.db`; open read-only via
  `sqlite3.connect("file:<path>?mode=ro", uri=True)` so a running app is undisturbed.
- Account namespace `mobeen.ahmed@contrivesolution.com`. Table names contain
  dots, so they MUST be double-quoted (`"<email>_activity"`).
- MTMPRO project: projectId `1182888`, cached name `AI Resource Management`.
- Timestamps are epoch MILLISECONDS. Duration = `endTime - startTime`; hours =
  that over `/1000/3600`. The `seconds` column is 0 on every row.
- Attribute a session to its START date:
  `date(startTime/1000, 'unixepoch', 'localtime')`. An overnight session
  (23:21 to 00:38) counts toward its start day.
- Only rows with `endTime > startTime` count.

### work_log is never a per-day source

`<email>_work_log` holds `(projectId, lastWorked, workedSeconds)`, a stale
cumulative counter. Measured 2026-09-22: `work_log` reported 2400s = 0.67h for
the same day the activity table reported 5410.7s = 1.50h. The activity table
agreed with the API's `last_activity_time`; `work_log` was simply wrong. An
earlier version of this skill recommended it as a purge fallback and would have
logged 40 minutes for a 1.5-hour day. Do not use it.

### The purge, and why the nightly job exists

The window is rolling and short. Observed: the table held Sep 21 rows read live
on Sep 21, Sep 22 rows the next day, and the Sep 14-18 rows were already gone by
Sep 21. A job that runs even one day late reads nothing.

The purge cannot be prevented from outside the client. The mitigation is to read
each day while it is fresh, which is what the nightly fill does. Confirm the
window before claiming data is missing:

```sql
SELECT MIN(startTime), MAX(startTime), COUNT(*)
FROM "mobeen.ahmed@contrivesolution.com_activity"
WHERE projectId = 1182888 AND endTime > startTime;
```

### Daily query

```sql
SELECT ROUND(SUM(ap.endTime - ap.startTime) / 1000.0 / 3600.0, 2) AS hours
FROM "mobeen.ahmed@contrivesolution.com_activity" ap
WHERE date(ap.startTime / 1000, 'unixepoch', '+5 hours') = '2026-09-22'
  AND ap.endTime > ap.startTime
  AND ap.projectId = 1182888;
```

Round the SUM, never the sum of rounded rows: per-row `ROUND` then adding yields
1.51 where the true total is 1.50.

## Missing-hours diagnosis ("N hrs missing from TopTracker")

1. Compare the sheet's column C against the daily query. If they differ the sync
   was stale, not the data: re-run `fill_hours.py --date ... --force`.
2. If C matches but the user expects more, list every row for the day ordered by
   start to expose untracked windows. A gap between one session's end and the
   next start is a stopped timer, and usually matches the claim:
   `SELECT datetime(startTime/1000,'unixepoch','+5 hours'),
   datetime(endTime/1000,'unixepoch','+5 hours'),
   ROUND((endTime-startTime)/1000.0/3600.0,2) FROM "<email>_activity"
   WHERE date(startTime/1000,'unixepoch','+5 hours') = 'YYYY-MM-DD' ORDER BY startTime;`
3. Check for unsynced sessions: `WHERE offlineType > 0 OR lastSynced IS NULL OR
   lastSynced = 0`. The `<email>_blobs` table holds screenshots only, never
   pending time entries.
4. Untracked work (late-night meetings, windows with the tracker off) goes to
   column D, NEVER column C. Convention confirmed twice: Aug 6 = 8.69 tracked +
   2 untracked; Aug 12 = 7.24 tracked + 2 untracked.
5. If the tracker was simply not running, say that. Do not reconstruct hours.

Full worked example and raw rows: `references/toptracker-gap-diagnosis.md`.

## "Add hours from the trackers" (no Dizio)

When the user asks to update a day and says "add hours from the trackers" or
"no filling for dizio", the day is MTMPRO-only:

1. Do NOT write the 1h Dizio default into column C. If one is already there,
   clear it with a single-cell write of `""`. Never `null`: the API accepts it
   and silently keeps the old value.
2. Run `fill_hours.py --date YYYY-MM-DD` for the tracked and GMI columns.
3. Add any untracked work to column D with a single-cell `USER_ENTERED` write.
4. Read the row back and present it for confirmation.

Pitfall: an existing value in a cell is NOT refreshed without `--force`; the
script reports "already filled" and writes nothing.

An early fill sticks in C: once a C cell holds a value, the 23:55 nightly skips
it (C is never auto-repaired; H auto-repairs when Kimai closes new entries).
Obey a mid-day request for current hours ("just add my current hours") by
running the day fill and reading it back, then say plainly that tonight's run
will skip C and a later `--force` refresh picks up whatever comes after. Never
fill a partial day unasked.

Late-night meeting identification: the Fathom recap `date` header is UTC; add 5h
for GMT+5 local. The recap is sent when the meeting ends, so it pins the time.
A recap dated Mon 17 Aug 2026 18:16:15 +0000 is 23:16 local.

## Sheet layout and column ownership

```
A Date | B Day | C MTMPRO TRACKED | D MTMPRO UNTRACKED | E BROADCASTING PLATFORM
F Other Project (labels/notes) | G Others | H GMI
```

- **Column C is TopTracker territory** (MTMPRO project `1182888` only). Manual
  corrections go to D, never hand-written into C unannounced.
- **Columns migrated 2026-10-22:** the old C (Dizio) column was removed; C now
  holds MTMPRO tracked (formerly D), D holds MTMPRO untracked (formerly E), E is
  the Broadcasting Platform project (Rohan-assigned, from Oct 2026), and G holds
  Others. `fill_hours.py` writes C + H only.
- **TopTracker project `1183966` "Chris" = the Broadcasting Platform project**
  (user, 2026-10-22). Its sessions go to column E, never G.
- Older paragraphs in this skill that say D = tracked, E = untracked or C =
  Dizio describe the pre-migration layout; map them onto C/D/E as above.
- **Column D** is untracked MTMPRO: meetings, fixes done with the tracker off.
- **Usama meeting hours go to D, not F/G.** Usama works on MTMPRO, so his
  meeting hours are MTMPRO untracked (user correction 2026-09-25). The Sep 16/17
  Usama entries in F/G predate that rule; the Sep 24 entry was moved from G to E
  under the old layout (D now).
- **Column F** holds project names and day notes, and is excluded from sums.
- **Column H is the split-aware Kimai sum.** A cross-midnight entry is split at
  00:00: the pre-midnight part lands on the start day, the post-midnight part on
  the end day, 2dp. No untracked counterpart.
- Day N lives at row N + 2. Weekend rows stay empty.
- Legacy pre-August 2026 tabs use a 6-column layout (D = Other Project) and are
  intentionally NOT migrated: user decision. Never add summary blocks to them
  and never write MTMPRO columns into them.

Monthly tabs keep same-kind blocks contiguous, top to bottom: daily grid,
Weekly Summary, Team MTMPRO Hours, Cross-Month Weeks, Reported Split,
Footnotes, Column Key. Build personal, then team, then reference. Do not put
footnotes between two team tables.

### Weekly block targets

Columns after TOTAL (user layout, 2026-10-22): I `BASE TARGET` = the
leave-adjusted week target (leaves deducted, blank until the week starts);
J `EXTRA/SHORT` = the live `H - I` delta.

- Every STARTED week counts all its in-month weekdays, so the week in progress
  already carries its whole target and reads negative until it completes. That
  negative is the real remaining hours for the week, by design.
- Leaves and declared holidays reduce the base target: F label "Leave" = 0h
  that day, "Half day" = 4h, "Holiday"/"Off" = 0h (fill_hours.py `day_hours`
  matches half first, then leave/holiday/off; added 2026-11-10 when "Holiday"
  alone left a company-off day counted as 8h); `DAY_TARGET_OVERRIDES` wins over
  the labels.
- A week that has not started keeps BLANK base and delta cells.
- MONTH TOTAL: base = `=SUM` of the week base cells; delta = `H - I`.
- The TEAM MTMPRO and REPORTED SPLIT blocks are static values: after any
  day-cell change update the team week row by hand. Only the week row's MEMBER
  cells are static (Mobeen = that week's C+D; Usama (reported) = that week's
  sum of column J, productive basis; Solat/Danish/Other as dictated; K Week
  Target = 32 share while Solat works, 40 if out). The row's
  Total Hours cell and every MONTH TOTAL cell are live `IF/COUNT` + `SUM`
  formulas: never hand-write them, just read them back after the member writes
  and quote both. After a share, record it in REPORTED SPLIT.
- A team week row's Total formula can be CLOBBERED: November26 Week 3 was found
  2026-11-13 with I50 empty while C50/D50/F50 held values, so the week read a
  blank total against real hours. Read the row in FORMULA mode whenever a Total
  comes back blank with member cells filled, and restore
  `=IF(COUNT(C50:H50)=0,"",SUM(C50:H50))`.

Weekdays are 8h, weekends 0. `DAY_TARGET_OVERRIDES` in `fill_hours.py` holds
per-date exceptions (declared holidays; wins over the F labels) and only
affects the current month's refresh (the script refreshes only the tab of
`--date`'s month). August 2026 needed `2026-08-10` = 4 (official half day),
`2026-08-14` = 0 and `2026-08-26` = 0 (national holidays). Add the next
declared holiday when it comes, so the recompute stays honest.

Personal leave and half days DO lower the target (user, 2026-10-22):
`refresh_summary` reads each day's F label on every run, Leave = 0h and Half day
= 4h, so write the label first and then refresh. The weekly cap
(`WEEKLY_TARGET_CAP`, 40h from 2026-10-12) is Mobeen's PERSONAL total target
across all projects; the team's 40h/week MTMPRO quota and his 32h MTMPRO share
(while Solat tests) live in the team block, never in the daily target.

All block values are live SUM formulas, so changing day cells is enough. Do NOT
hand-edit a target: a stale one is how the month once reported a fake +24.41
surplus (a 112h target frozen at Sep 18 instead of 136h through Sep 23). Run
`fill_hours.py --summary-only` to recompute them; it is idempotent.

Column J (EXTRA/SHORT) carries the number format `+0.00;-0.00;0.00`; column I
(BASE TARGET) is plain `0.00`. Bold the title, header and total rows, and write
values `USER_ENTERED`.

### The month delta binds to the FIRST MONTH TOTAL row

Both summary blocks end in a MONTH TOTAL row (September26: personal row 42,
team row 52). `_find_rows` in `fill_hours.py` must take the FIRST match only.
Before 2026-09-25 it kept overwriting `total` with the team row, so refreshes
scribbled the personal month delta into the team block's Week Target cell (I52)
while the personal month target froze at an old value and displayed a fake
surplus (+19.92 against a stale 136 target instead of +4.92 against 152). Fixed
with a `total is None` guard on the MONTH TOTAL branch. Verify after any
refresh: I42 in FORMULA mode reads `H42-<elapsed weekdays x 8>`, and I52 still
holds its `SUMPRODUCT` week-target formula (restored to
`=IF(SUMPRODUCT((G47:G51<>"")*(I47:I51<>"") )=0,"",SUMPRODUCT((G47:G51<>"")*I47:I51))`
if it was clobbered).

## Crons

| Job | ID | Schedule (GMT+5) | State |
|-----|----|------------------|-------|
| Work Hours Nightly Fill | `a8090fb09d6c` | `55 23 * * *` daily | ACTIVE |
| TopTracker Weekly Sync | `1a9ca9bc705e` | `0 20 * * 5` Fri | REMOVED 2026-09-25 |
| TopTracker Weekend Catch-up | `ac26b62ec9f0` | `5 0 * * 1` Mon | REMOVED 2026-09-25 |

The nightly job runs at 23:55 while the DB still holds the day. It is why the
two weekly jobs were paused and later removed (2026-09-25): the Friday job scanned a whole week and skipped
filled cells, and the Monday catch-up re-read a week the DB had already purged
(on 2026-09-21 it reported Sep 14-16 as "no tracked hours" purely from the
purge, and it ran with `--force`).

Operational rules:

- Cron `script` paths MUST be relative to `~/.hermes/scripts/`.
- `no_agent` script jobs cannot carry CLI args; use a `.sh` wrapper that execs
  python with the flags and appends `"$@"` so a manual run can add `--dry-run`.
- Empty stdout sends nothing (watchdog pattern): a quiet job means success.
- Test without waiting: `cronjob(action='run', job_id=...)`. Output is saved to
  `~/.hermes/cron/output/<job_id>/YYYY-MM-DD_HH-MM-SS.md`.
- The month's tab must exist before any write. Create it first if missing.
- Script interpreter: the Hermes venv
  (`~/.hermes/hermes-agent/venv/bin/python`) is the only one on this box with
  `google-api-python-client`. `fill_hours.py` re-execs into it; if a script
  reports the libs missing, check the candidate list before believing it,
  because a wrong candidate list once made every cron silently no-op.
- `toptracker_sync.py` is retired and refuses to run. It targets the legacy D
  column. Use `fill_hours.py --date YYYY-MM-DD`, which writes C and H.

## GMI hours (column H) from Kimai

Config: `~/.hermes/config/kimai.json` (`url`, `username`, `token`, `projectId`).
It was lost in the CachyOS migration and restored 2026-09-23. Recreate it rather
than inventing credentials if it goes missing.

```
GET <url>/api/timesheets
    ?project=1&begin=YYYY-MM-DDT00:00:00&end=YYYY-MM-DDT23:59:59&size=200
Headers: X-AUTH-USER: <username> | X-AUTH-TOKEN: <token>
```

- Send a `User-Agent` header (any browser UA) on every Kimai call. Without it
  the API returns **403 Forbidden** for every day, which reads like a rotated
  token but is not; the same request passes with the header (verified
  2026-10-22).
- Returns a BARE ARRAY, not `{"data": ...}`. Handle both shapes.
- `activity` is an integer ID, not an object, so `entry['activity']['name']` raises AttributeError; the ticket label lives in `description` (shape `TECH-<n>/<epic-slug>`).
- Sum `duration` (seconds) over the entries and divide by 3600. Never round per
  entry.
- **Validate before writing.** Query days already in the sheet and confirm the
  API reproduces them exactly. Held Sep 2026: Sep 1 = 6.62, Sep 3 = 2.15,
  Sep 7 = 4.02, Sep 18 = 7.02, Sep 21 = 1.23, Sep 22 = 5.18, Sep 23 = 5.38,
  Sep 24 = 2.51 (all reproduced exactly on 2026-09-25). A wholesale mismatch
  (different totals entirely) means the project renumbered or the token
  rotated: do not write. A small drift (minutes) is a stale cell: the day was
  filled before an entry was edited or closed, and the API sum is
  authoritative. When you touch that day anyway, derive the new value from the
  API sum plus any booked addition and write that, stating the reason; never
  add the addition onto the drifted cell value.
- A running entry has `end: null` and `duration: 0`, so a day whose only entry is
  live sums to 0. That is not a real zero. Wait for it to close.
- **An entry created through the API can never be closed from Hermes**: PATCH
  rejects `end`. Only the admin-side Slack presence bot auto-stops entries, so a
  running entry closes on its own schedule, not on request.
- A long GMI day with a blank MTMPRO column is normal: Kimai and TopTracker
  track different projects.

## Team sheet: multi-account Kimai (kimai_team_hours.py)

Logging MULTIPLE developers' Kimai hours into one shared sheet is NOT
fill_hours.py (that one is single-account and personal). Use the multi-account
tooling; its SKILL.md on the branch is the full operating manual.

- Home: branch `skill/multi-kimai-hours` on `mobeenx20/hermes-agent` (fork of
  `NousResearch/hermes-agent`), path
  `optional-skills/productivity/multi-kimai-hours/` (PLAN.md, SKILL.md,
  scripts/). Fetch the branch to get the scripts; scratch clones prune on
  idle, so never treat one as the home.
- Config: `~/.hermes/config/kimai-accounts.json`, `accounts[]` (name,
  developer, url, username, token, projectId, timezone) plus `sheet`
  (spreadsheet_id, tab, csv). One account per developer; template ships in
  the branch. Credentials live only in this file.
- Run (Hermes venv python): `kimai_team_hours.py read|fill-local|fill-google`
  with `--date` or `--from/--to`, `--accounts NAME[,NAME]`, `--force`,
  `--dry-run`, `--json`. `run_team_fill.sh` is the cron wrapper (silent on
  success). Exit 2 = write verification failed.
- Layout differs from the personal tab: `A Date | B Day | one column per
  developer` (header row 1), rows keyed by the date in column A. When reading
  keyed rows back with UNFORMATTED_VALUE, date cells return serials (base
  1899-12-30): normalize to ISO before comparing.
- Same non-negotiables as the personal fill (midnight split, running =
  unknown, round the SUM at 2dp, zero never clears, no future days, read-back
  verify). Differences: a cell holding a DIFFERENT non-zero value is kept
  (a reading above it auto-repairs as STALE; below it needs `--force`), and
  rows appear lazily only when a write actually happens.

## Related

- Sheet conventions (Dizio defaults, labels, colours): the `work-hours-tracking`
  skill. Its plugin tools (`fill_dizio_today`, `add_mtmpro_entry`,
  `work_status`) are NOT installed on this machine (`~/.hermes/plugins/` is
  absent), which is why `fill_hours.py` exists. Never assume they are callable.
- Whole-tab formatting: `format_personal_only.py` and `build_month_tab.py` in
  the `work-hours-monthly-tab` skill.
- Kimai push side (create/delete entries): `references/kimai-api.md`.
- Kimai Slack presence keep-alive: `references/kimai-gmi-slack.md`.
- Shortfall claims audit (Contrive SOP 8h/day, per-month verification, Gmail
  recipes): `references/shortfall-audit.md`.
- ResourceInn attendance extraction: `references/resourceinn-attendance.md`.
