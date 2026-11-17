---
name: mtmpro-weekly-report
description: Slack-formatted weekly MTMPRO team hours report.
version: 1.0.0
metadata:
  hermes:
    tags: [mtmpro, slack, weekly-report, hours]
---

# MTMPRO Weekly Hours Report

Generate a Slack-formatted weekly MTMPRO hours report.

## Format

Always use this exact Slack-ready format:

```
📊 *Weekly MTMPRO Hours (Mon DD-Mon DD)*
Mobeen  XX.XX
Solat   XX.XX
Danish  XX.XX
Total (team) XX.XX
```

## Targets: base vs instructed vs actual (three distinct numbers)

Never collapse these into one "target" column. The user corrected this explicitly
(Sep 2026):

| Concept | Meaning | Example |
|---|---|---|
| **Base Target** | Standing weekly mark | 50h |
| **Week Target** | Instructed figure for that week (may be raised) | 64h for Week 3 |
| **Total Hours** | Actual delivered, may EXCEED either | 68.99h |

Two delta columns are required: `Extra vs Base` (Total - Base) and
`Extra vs Week Target` (Total - Week Target). For Week 3 these read +18.99 and
+4.99 respectively: the same week is 18.99 over the standing mark but only
4.99 over what Rohan asked for. Reporting only one of them misrepresents the
week.

Earlier weeks used the 50h standing mark, so their Base and Week targets are
both 50.

## Client hours cut (from Week 3 of October 2026)

The client cut weekly hours (3 churns, 2 downgrades, Oct 2026). From Mon
Oct 12 2026: MTMPRO team quota **40h/week**; **Solat 8h/week**. Mobeen's
personal total stays **40h/week** across all projects. Mobeen (incl. Usama)
covers **32h/week** of MTMPRO while Solat works his testing, and the full
**40h/week** if Solat is out. Consequences for every report from that week on:

- The merged `Mobeen + usama` MTMPRO line is measured against the 32h share
  (40h without Solat); Mobeen's overall week is measured against 40h.
- **Usama's productive hours (column J) are the MTMPRO measure.** Use J, not
  I, for the quota number; the difference I - J is tracked but not productive
  and stays out of the quota (show it separately if needed, never as productive).
- The standing team mark drops from 50h to **40h** (32 + 8).
- A proposed cut is not the quota. A client counter that pairs a balance drawdown with a lower cap (for example 25h/week) does not change the standing mark until the user accepts it in writing. Generate reports at the current quota and flag the proposal separately.
- The month tab's footnotes carry the same note; trust the tab if they ever
  differ.
- After a report is shared: record the figure in `REPORTED SPLIT` (the team
  table has no Reported column; the split block is the source of truth) and
  bump the green cutoff rule for that week's rows (Usama `I/J`) so only the
  reported days stay highlighted. Recipe: read `sheets.conditionalFormats`,
  pick the rule whose range covers the week's rows, replace its `DATE(y,m,d)`
  constant with the last reported day via `updateConditionalFormatRule` (keep
  the rule's ranges and format), then read the rules back. One rule per
  reported week; a week with no rule shows no green at all.

## Reported vs actual (critical distinction)

The figure shared with the client/Rohan is NOT always the week's actual hours.
Keep them as two separate rows/columns and never collapse them:

- **Total Hours** = actual hours worked by the team.
- **Reported to Client** = the figure actually shared.
- **Diff** = Total - Reported. This is the honest ledger cell.

Worked example (Sep 14-20, 2026): actual 68.99 (Mobeen 31.99 + Usama 18 +
Solat 18.5 + Danish 0.5) was reported as 64.00, so Diff = 4.99.

## Team table columns (latest layout)

The live October26+ table is 14 columns:
A Week | B Period | C Mobeen | D Usama (reported) | E Usama (extra) |
F Solat | G Danish | H Other | I Total Hours | J Base Target |
K Week Target | L Reported to Client | M Extra vs Base | N Extra vs Week Target.

**The sheet does not merge Usama into C.** C is Mobeen only; Usama's weekly
figure is D when reported and E when banked for a later report. The SLACK
BLOCK still merges them: its `Mobeen` line = C + D + E. Keep the two shapes
separate or the write double-counts.

Below it, `REPORTED SPLIT (WHAT WAS SHARED)`: A Week | B Period |
C Mobeen (incl. Usama) | D Solat | E Danish | F Total. **C here is the merged
figure, not the sheet's C column.**

## Merging a resource into the lead's line

The merge is a REPORTING rule, not a sheet layout rule. In the Slack block,
attribute Usama's hours to Mobeen in one line and do not list him separately;
in the sheet keep Mobeen in C and Usama in D/E. State the merge in a footnote.

When the reported figure must be REDUCED to hit the target, put the reduced
number in the reported block and keep the full figure in the actual table. Do
not edit the actual figure to make it match the target.

## Team table location (September26 tab)

`TEAM MTMPRO HOURS` is the second category band, below the Weekly Summary.
Live rows in September26: band `2  MTMPRO` row 44, title 45, header 46, weeks
47-51, MONTH TOTAL 52. Columns: A Week, B Period, C Mobeen (incl. Usama),
D Solat, E Danish, F Other, G Total Hours, H Base Target, I Week Target,
J Reported to Client, K Extra vs Base, L Extra vs Week Target.

Below it, `CROSS-MONTH WEEKS (SPLIT ACROSS TABS)` at rows 54-58, then
`REPORTED SPLIT (WHAT WAS SHARED)` at rows 60-66 holding the per-person
reported numbers, then the `3  OTHERS` band row 68 and footnotes 69-71.

Row numbers SHIFT whenever the layout changes (category bands, a 31-day month,
a cross-month block appearing). Read them from the `work-hours-monthly-tab`
script's meta output rather than trusting this list; the block ORDER above is
the stable part.

Total Hours uses `=IF(COUNT(C:F)=0,"",SUM(C:F))` so an unstarted week stays
blank instead of reading as a shortfall. Diff blanks unless both sides exist.

## Rules

- Header: 📊 emoji + *bold* title with date range
- Each person on their own line: name, two spaces, hours with 2 decimal places
- Total line: `Total (team) XX.XX`
- Plain text, no markdown code blocks. Slack paste-ready.
- Hours are decimal (e.g. 36.78, not 36h 47m)
- Mobeen's hours = MTMPRO TRACKED (col C) + MTMPRO UNTRACKED (col D) from the sheet
- Solat and Danish hours are provided by the user; not in the sheet
- **Danish is OFF MTMPRO (user, 2026-11-06):** omit his line from new reports and leave his column/line blank. Past weeks' recorded Danish figures are historical and never rewritten.

## Data Sources

- **Mobeen:** Read from the "Mobeen worked hours" Google Sheet (spreadsheet ID: `REPLACE_SPREADSHEET_ID`). The current month tab. Read the weekly summary block or sum daily rows.
- **Solat/Danish:** User provides these verbally. Ask if not provided. A stated total that contradicts its stated components ("6h + 50min meeting" stated as 6.50: 6h50m is 6.83) is booked as stated, then flagged once with the corrected decimal and an offer to amend; never silently substitute the component math.

## Mid-week "hours left" status (no report shared yet)

Answer "how many MTMPRO hours do we have left this week" from the day grid,
never from the team table (the team row is refreshed by hand and lags the day
cells):

1. Read the week's grid rows: Mobeen = sum of C + D; Usama = sum of J (his
   PRODUCTIVE basis; tracked I stays out of the quota).
2. Remaining = 32.00 minus the merged figure (40.00 when Solat is out). Today
   counts as open at 0 until its cells close; a running Kimai entry is unknown,
   never zero.
3. Report the full-team actual (merged + Solat's fed figure) against the 40h
   standing mark separately, and name an unfed J day as a gap carrying its
   tracked I value, never as a zero.
4. Growing a previously fed Usama weekly figure: the week's REPORTED SPLIT row
   decides the placement. Empty split row = nothing was shared yet, so fold the
   new productive hours into D; a filled split row means D is frozen at the
   shared figure and new hours bank into E. Recompute the row's static I by
   hand after any move.

## Rohan approval message (the canonical ask)

When weekly hours need sign-off before going to the client, send this shape.
It is the format the user actually sent and approved (Sep 2026). Do not invent a
different structure, and do not collapse it into prose.

```
📊 *Weekly MTMPRO Hours (Mon DD-DD)*
Mobeen  XX.XX
Solat   XX.XX
Danish  XX.XX
Total (team) XX.XX

<Rohan's name> This is the hours I'm thinking of sending to the client: XX.XXh. Confirm which set goes.


 these are our actual internal hours:
Mobeen + usama  XX.XX
Solat   XX.XX
Danish  XX.XX
Total XX.XX
```

Rules that make it work:

1. **Two blocks, client-facing first.** The `📊` block carries the REPORTED
   figures (what goes to the client). The plain second block carries the ACTUAL
   internal figures. Never merge them into one list.
2. **The ask is one sentence, in the middle**, naming the exact figure:
   "This is the hours I'm thinking of sending to the client: XX.XXh. Confirm
   which set goes."
3. **Name the label "Mobeen + usama"** in the internal block so the merged
   resource is visible, matching how the hours are attributed.
4. **State the delta in ONE line after the ask** when the sets differ, e.g.
   "Only difference is Mobeen, +4.99h; Solat and Danish match." That gives Rohan
   a single decision instead of a table to diff.
5. **Plain text, no code fences, no markdown.** Slack paste-ready. Two spaces
   between name and hours keeps the column alignment.
6. Hours are decimal (45.00, not 45h).

Worked example (Sep 14-20, 2026): reported 64.00 vs actual 68.99, a +4.99 gap
entirely in Mobeen's line. Solat 18.50 and Danish 0.50 were identical in both,
which is what made the decision one cell instead of a table.

Read the figures from the tab's `TEAM MTMPRO HOURS` block (columns J Reported to
Client for the client-facing set, G Total Hours for actual) and
`REPORTED SPLIT (WHAT WAS SHARED)` for the per-person reported split.

## Example Output

```
📊 *Weekly MTMPRO Hours (Sep 7-13)*
Mobeen  36.78
Solat   13.00
Danish  0.67
Total (team) 50.45
```
