# Data sources for hours reporting

Four sources feed a work-hours answer. Know which one is authoritative for
which column before presenting a total.

| Source | Covers | Authority |
|---|---|---|
| Worked-hours sheet (current + previous month tabs) | All columns as recorded | Authoritative for what was REPORTED |
| TopTracker (local DB + cloud API) | Column D, MTMPRO tracked | Authoritative for what was TRACKED, session-grain |
| Kimai | Column H, GMI | Authoritative for GMI time entries |
| Work reports | What was actually worked, per ticket | Proof a blank day was a real working day |

## Sheet shape

7-column layout on tabs from August 2026 onward: A Date, B Day, C Dizio,
D MTMPRO TRACKED, E MTMPRO UNTRACKED, F Other Project / day notes, G Others,
H GMI.

- Pre-August tabs are 6-column legacy. Read them, never write summary blocks into them.
- Day grid is date N at row N+2. Header at row 2, title at row 1.
- The Weekly Summary block sits one blank row below the last day, so a month tab
  is fully covered by `A1:I45`.
- Column F is notes and is EXCLUDED from totals. Sum D + E + G + H (+ C for Dizio).

Read both the current and previous month tabs when the reporting window crosses
a month boundary. A MONTH TOTAL is not a window total: it can include days from
the adjacent month.

## TopTracker notes that change the answer

- Sessions are a start timestamp and an end timestamp in milliseconds. A timer
  that is still running has no end timestamp yet, so it does not appear in any
  per-day sum. Confirm a live session separately before reporting a trailing day
  as zero.
- Sessions are attributed to the day they START. A session begun at 00:52
  belongs to the next calendar day, which can move the previous evening's work
  to a different row than the user expects.
- A last-activity or last-session field, whether from the API or the app log,
  describes ONE session. It is a liveness check, never a daily total.
- The local store is session-grain and rolls: run a count and min/max timestamp
  over it before asserting a day is empty, and say when old data was purged.
- Pull tracked totals from per-day activity rows, not from the tracker's own
  "worked today" statistic, which can lag or cover only client-tracked sessions.
- When the sheet's tracked cell already holds a value, a re-sync may skip it. To
  refresh a tracked cell, clear it first, then re-sync.

## Reconciliation recipe

1. `date` and derive the day of week for every date in the window.
2. Read `Tab!A1:I45` for the current month and for the previous month when needed.
3. Sum D + E + G + H per day and for the window, in code.
4. Build the elapsed target from real weekdays: 8h each, 0 on weekends, current
   day at 0 until it closes. Holidays and half-days are overrides the summary
   script carries; check them before reporting a shortfall.
5. For each elapsed weekday with a blank or suspiciously low cell, query the
   tracker for that day and check the work reports for that date.
6. Report total, shortfall, unfilled days, sources, and one next action. Write
   nothing until the user approves.

## Reporting traps

- A total that omits a not-yet-filled trailing day reads as an underworked
  week. Present unfilled days as a category of their own.
- A target built only from filled rows always matches the numerator, producing a
  false zero shortfall. Enumerate elapsed dates instead.
- An unrefreshable column is "not refreshed", not zero.
- Confirmed-but-missing work belongs in the untracked column, never in the
  tracked column. A tracked column is reserved for what the tracker recorded.
