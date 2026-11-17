---
name: work-hours-reporting
description: Report hours worked to date from the sheet, verified.
version: 1.0.0
metadata:
  hermes:
    tags: [work-hours, reporting, reconciliation, toptracker, google-sheets, shortfall]
---

# Work Hours Reporting

Answer "tell me my hours", "how many hours this week", "am I short this month"
from the worked-hours sheet, verified against the trackers and the work reports.
This is RECONCILIATION work: a raw read of one cell range is not an answer until
the trailing days are proven filled.

Sheet mechanics, Dizio defaults, and TopTracker SQL live in the user-owned
`my-work-hours`, `work-hours-tracking`, and `toptracker-hours` skills. This skill
owns the read-and-report procedure and the shape of the answer.

## Procedure

1. Confirm the real date with `date`. Never trust the conversation header date.
2. Read the current month tab in ONE call over `A1:I95` when the month is long;
   `A1:I45` covers a 31-day grid plus its summary. The day grid and the
   WEEKLY SUMMARY block share that range, so one read returns per-day rows, week
   rows, MONTH TOTAL, and EXTRA/SHORT. If the first Google MCP call returns
   "Not authenticated", run the auth-status check and retry the SAME read before
   concluding the token is broken.
3. Read the previous month tab too when the window opens before the 1st. Month
   totals carry values in from adjacent months (a September MONTH TOTAL included
   an August 31 row), so quote an explicitly stated window, never MONTH TOTAL raw.
4. Compute the total in code: hours = C + D + G + H (the Dizio column is gone
   since 2026-10-22; E Broadcasting counts too when filled). Never add mentally,
   and never quote a sheet total without recomputing it from the per-day cells.
   Then cross-check the computed per-column sums against the tab's own WEEKLY
   SUMMARY and MONTH TOTAL rows: they must match exactly, and a mismatch means
   the column mapping in the script is wrong, not the sheet.
5. Build the elapsed-target from each elapsed date's real day of week: 8h per
   weekday, 0 on weekends. The current day counts as elapsed at 0 until it
   closes, unless the user says otherwise.
6. Verify every trailing elapsed weekday before presenting it. Cross-check the
   tracker for tracked time (column C source) and the work reports for what was
   actually worked.
7. Present: per-day or per-period rows, the total, the shortfall against the 8h
   SOP, the days that are unfilled, the sources used, and one next action. Write
   nothing to the sheet without explicit approval.

## Rules

- **Blank is not zero.** An elapsed weekday with an empty cell means NOT YET
  FILLED. Reporting it as zero understates the total and inflates the shortfall.
  Name it as unfilled and say what the tracker shows for that day.
- **Count weekdays from the tab's own Day column, not from filled rows.**
  Counting only rows that hold hours shrinks the numerator and the target
  together, so the shortfall falsely reads as zero. Iterate every elapsed
  calendar date and classify it weekday or weekend.
- **Attribute sessions by start date.** A timer started after midnight belongs
  to the new day; a timer still running has no end time and is invisible to a
  per-day sum. Never call a trailing day zero hours from tracker silence alone;
  check whether a session is live first. For the sheet's Kimai/GMI day cells,
  split a session that crosses midnight at 00:00 instead; whole-session
  start-date attribution overstates the begin day (see work-hours-tracking
  Pitfall 29).
- **Session-grain only.** A last-activity / last-session record describes one
  session. Use it to confirm a live timer, never to sum a day.
- **State the data window.** Tracker stores roll and purge. Before declaring a
  day empty, check the oldest and newest retained timestamps and say plainly
  when older data is gone rather than implying no work happened.
- **Name an unrefreshed column.** If a source (GMI/Kimai, a tracker reader) is
  unavailable this run, state that the column was not refreshed. Never present
  an unrefreshed cell as zero hours.
- **Cross-source agreement is the finding.** When one source shows work and the
  sheet shows nothing, that gap IS the answer: report it as unfilled days plus
  unsynced tracker time, not as a low total.
- **Separate tracked from untracked.** Tracked (column C) and manually logged
  untracked (column D) hours are different evidence classes. Keep them in
  separate columns in the output; never merge them into one number.
- **Allocation-status windows: use the last completed day.** For a manager or
  client allocation message, sum through the last closed day, label the window
  with explicit dates, and state the current week's total as a plan. Never print
  an in-progress day or week as 0.00: empty cells plus a purged tracker cache
  mean unknown, not zero.
- **No writes on a read request.** "Tell me my hours" is a question. Report,
  then offer the fill as a proposed next action and wait for approval.

## Disputed entries (justify logged hours)

When HR or a manager questions specific logged hours or demands make-up time:

1. List every disputed cell: date, hours, label. Defend entry by entry with its
   own corroborating record; a whole-bucket defense carries no evidence.
2. Corroborate each entry from the wider record set, not just the four sources:
   company/HR emails (equipment issues and migrations, assigned duties),
   Calendar plus Fathom recaps (meetings), work reports plus review artifacts
   and git history (code review, handoffs), session logs (same-day logging
   proves the record is contemporaneous).
3. Present the month total WITH and WITHOUT the disputed entries, each against
   the leave-adjusted target. The "no shortfall" claim must survive both cuts;
   if one cut breaks it, name that cut.
4. Carry the extra-hours evidence with it: days that ran above 8h and their
   overage, and team-vs-base when team hours are in dispute.
5. If a disputed entry could legitimately sit in another column per the column
   rules, offer "reclassify vs hold" as two options stating what moves, what
   stays, and what each total does. Never move the hours without the explicit
   go: a move changes the client-facing figures. On hold, record the hold and
   the reclassification option as a footnote (work-hours-monthly-tab, "Adding a
   footnote to a live tab").
6. Draft the message in `manager-communication` (HR hours disputes); keep the
   evidence pack internal unless the user says otherwise.

## Output shape

Lead with the numbers, not with the method:

| Period | Tracked | Untracked | Broadcasting | Others | GMI | Total |
|---|---|---|---|---|---|---|
| Month to date | .. | .. | .. | .. | .. | **..** |
| Current week | .. | .. | .. | .. | .. | **..** |
| Today | .. | .. | .. | .. | .. | **..** |

For a status/allocation message, use the Month to date row only. Omit Current
week and Today when they are unfilled or in progress; do not print them as 0.00.

Then, in order: the source line naming the sheet tab and the sources actually
consulted; a short list of the gaps found (unfilled days, unsynced tracker
hours, unrefreshed columns); the shortfall against SOP; and one proposed next
action phrased as a decision for the user.

Numbers keep two decimals only where the sheet carries them. State the window
with explicit dates, never "this month" alone.

## Related

- `references/data-sources.md`: the four sources (sheet, tracker, Kimai, work
  reports), which is authoritative for which column, the exact tab layout, the
  reconciliation recipe, and the reporting traps.
- `toptracker-hours` (user-owned): TopTracker API, local DB SQL, sync crons.
- `my-work-hours` (user-owned): sheet layout, Dizio defaults, colors.
- `work-reports` (curator-managed): daily reports, used here to prove a day was
  worked when the sheet is blank.
