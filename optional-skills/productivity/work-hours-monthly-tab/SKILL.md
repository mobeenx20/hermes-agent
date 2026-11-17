---
name: work-hours-monthly-tab
description: Build monthly worked-hours tabs and chase gaps.
version: 1.0.0
metadata:
  hermes:
    tags: [google-sheets, work-hours, mtmpro, monthly-tab, reporting]
---

# Work Hours Monthly Tab

Create and maintain a monthly tab in the "Mobeen worked hours" spreadsheet. One
tab per month holds four blocks: the daily grid, the Weekly Summary, the Team
MTMPRO Hours table, the Reported Split, plus a Column Key.

## When to load

Load for any request to create next month's tab, rebuild/refresh a monthly tab,
add the team-hours table to a month, chase missing weekly hours, or when the user
asks "what is missing for this week".

## Constants

```
Spreadsheet ID: REPLACE_SPREADSHEET_ID
Tab naming:     "September26", "October26"  (MonthYear)
Script:         scripts/build_month_tab.py
Interpreter:    ~/.hermes/hermes-agent/venv/bin/python   (scratch python3 lacks googleapiclient)
Auth files:     ~/.local/share/google-mcp/tokens.json + ~/.config/google-mcp/credentials.json
```

## Commands

```bash
PY=~/.hermes/hermes-agent/venv/bin/python
S=~/.hermes/skills/productivity/work-hours-monthly-tab/scripts/build_month_tab.py

$PY $S --month 10 --year 2026                  # create/refresh October26
$PY $S --month 10 --year 2026 --dry-run        # row math only, no writes
$PY $S --month 9  --year 2026 --report-missing # JSON of every empty cell for an elapsed week
$PY $S --month 10 --year 2026 --config /tmp/cfg.json   # seed targets/figures
$PY $S --month 11 --year 2026 --apply --spreadsheet <id>  # scratch-sheet test (never the live sheet)
```

The script is idempotent: verified by running it three times on September26 with
byte-identical results each time. It rebuilds the summary blocks around existing
data and never touches hour cells in the daily grid.

`--spreadsheet <id>` points a run at any other spreadsheet for testing: create
a throwaway sheet, build the CURRENT month there and diff the grid + Usama area
against the live tab, then build NEXT month and run it TWICE (the second run
must report `k_seeded: 0` and `status: built`). Never test a builder change on
the live sheet.

**Before running it on a month with real data, always snapshot first:**

```bash
# read September26!A1:H<last_day> and save to JSON, run the script, then diff.
```

Once the snapshot matches after a rebuild, the script is safe for that month.

## Holidays and half days: highlight AND lower the week target

A public holiday and a half day are two facts in one: a day you did not (fully)
work, and a day that LOWERS the week's bar. Any hour worked on a 0-target day is
entirely extra, so both must be stated in two places that are kept in step:

1. **Highlighting** (`holiday_rows()` + `HOLIDAY_BG`/`HALFDAY_BG`): a holiday is
green `#D9EAD3`, a half day amber `#FFE5CC`, both bold with dark green text so
neither reads as a normal workday. Apply these AFTER the weekend pass so they win
on a clash, and keep them visually distinct from the cream weekend fill.
2. **Target overrides** (`DAY_TARGETS`): holiday `0`, half day `4`, else `8`.
`week_target()` sums those per weekday, and the weekly EXTRA/SHORT formula is
rewritten as `=H<row>-<target>`. Skipping this understates extra hours: August
2026 Week 5 read +6.03 against a flat 40, but the Milad holiday on Wed Aug 26
makes the real bar 32, so the honest figure is +14.03.

`format_personal_only.py --apply` writes both, so a re-run cannot leave the
highlight and the target disagreeing. August 2026 reference values: Aug 10 half
day (4h), Aug 14 national holiday (0), Aug 26 Milad holiday (0); week targets
0/40/28/40/32/8, month 148.

Do NOT highlight a day the user has not named as a holiday or half day, even if
it looks light. A light day is a shortfall, not an entitlement.

### Half days and holidays on the current 8-column layout

The highlight helpers above belong to the old personal-only tabs. On the current
layout a named half day is recorded in three places: the `F` label of that day
row (`Half day`, same slot as `Leave`), the day-hour reduction that fill_hours'
`refresh_summary` reads from that label (`Leave` = 0h, `Half day` = 4h) and
rewrites into the weekly/monthly EXTRA/SHORT formulas (`--summary-only`), and
the build's `day_targets` config when a tab is rebuilt from scratch. The weekly cap can swallow the target change: five days at 8h minus a 4h Friday
sums 36 against a 40h cap, so the delta reads +0.06, not the full 4h; say so
instead of hunting a missing change.
A half day does not change the day's actual hours: hours stay whatever the
sources hold (Kimai, tracker), and a purged tracker day is flagged, not filled.
When the request is ambiguous ("update my hours"), offer the shift span read off
the day's Kimai entries as the alternative before writing anything.

## Personal-only tabs (older months): format_personal_only.py

Older tabs (August26 and earlier) hold ONLY two blocks: the day grid and the
WEEKLY SUMMARY. They have no team table, cross-month block, footnotes, or
Column Key. Running `build_month_tab.py --apply` against them would CREATE those
blocks, which is wrong. Use
`scripts/format_personal_only.py --month M --year YYYY [--snapshot|--apply|--verify PATH]`.

It reuses `build_month_tab`'s palette constants by import, so the two scripts can
never drift apart on colour. The height contract is identical to the full
layout: title 34, header 46, data 21, band 30, spacer 12.

Geometry for a 31-day month: grid 1-33, spacer 34, band 35, weekly title 36,
header 37, weeks 38-43, month total 44. Row N of the grid is still day N at
row N+2, so the grid stays pinned to toptracker_sync's convention.

## Personal-only tabs: three pitfalls that cost real time

1. **A date cell becomes a serial number when the baseline reset strips its
   pattern.** The week Period cell for a single-day week ("Aug 31") is a real
   DATE, not text. Resetting formats to a numeric pattern made it render as
   `46265.00`. Always re-apply a DATE format after a baseline reset:
   `datefmt(...)` with pattern `"mmm d"`, which still renders a two-day range
   like "Aug 1 - 2" unchanged because that one is genuinely text.

2. **`insertDimension` is not idempotent.** Inserting the category band row on
   every run shifts the Weekly Summary one more row down each time. Gate the
   insert on the band label actually being absent (`band_present()`), or a second
   `--apply` silently corrupts the layout.

3. **Verify SEMANTICALLY, not byte-for-byte.** The formatter deliberately
   normalizes display to the September contract (zero renders blank, 22.6 renders
   22.60, +2.1 renders +2.05). A raw string comparison reports those as failures
   and buries a real data-loss signal in noise. Compare numeric cells as floats
   with blank == 0, and text/date cells as displayed text.

Prove correctness in three steps: `--snapshot` before, `--apply`, then
`--verify <snapshot.json>`, which must report every pre-existing value present
exactly one row lower and the values numerically identical. Cross-check the
weekly formulas afterwards: row N's EXTRA/SHORT must reference `H<N>`, i.e. its
own row, which is what confirms `insertDimension` shifted the formulas rather
than breaking them.

## ROW HEIGHTS: one plan, one source of truth

Row heights are DIMENSION properties, not cell formats. They survive
`reset_block_area()`, every `values.clear`, and every unmerge. That makes them
the single most drift-prone thing in this sheet: when a block moves down (a new
category band, a 31-day month, a cross-month block appearing) it INHERITS the
height of whatever occupied that row before.

Seen live after the category bands were added: the Team table's Week 5 row was
26px and its MONTH TOTAL was 34px, both leftovers from the previous layout's
footnote and title rows. The Cross-Month table is now correct only because of
the fix below.

**Never scatter `height()` calls through `style_requests`.** Every height must
come from `height_plan(meta)`, which returns the canonical pixel size for EVERY
row from the grid to the Column Key. The plan sweeps the whole summary area to a
12px baseline FIRST, then lays the canonical heights over it, so a row that is
no longer used can never keep a stale height. `style_requests` applies the plan
before any other request, and `verify_heights()` asserts the live sheet matches
the plan after every write, reporting `HEIGHTS DRIFTED` with the offending rows.

### The contract

| Element | Height |
|---|---|
| Category band | 30px |
| Table title | 34px |
| Table header | 46px |
| Table data row | 21px |
| Table summary row (MONTH TOTAL / WEEK TOTAL) | 21px |
| Day grid rows 3-32 | 21px |
| Spacer rows | 12px (all equal) |
| Footnote rows | 26px |
| Column Key data rows | 48px (the ONE exception) |

Every table is IDENTICAL: Weekly Summary, Team MTMPRO, Cross-Month and Reported
Split all read `34 / 46 / 21...`. Only the Column Key differs, because it holds
prose, not hours: its B column is a 62-char description in a 215px column that
wraps to three lines, so 21px would clip it. Document that exception; do not
drift every other table to match it.

Verify with `rowMetadata(pixelSize)`, not values. Read `A1:A<key_bottom>`, group
by block, and assert each block's title/header/data set is `{34, 46, 21}`.

## Footnote count is DATA, never a literal

The Column Key sits below the footnote block, so any change to the footnote
count shifts it. Three places used a hardcoded `3` and silently misaligned the
Key when a 4th note was added: the `r_key_title` offset, the height plan's
footnote range, and the merge loop.

All three now derive from `meta["n_foot"]` / `len(foot)`. When adding or
removing a footnote, change ONLY the `foot = [...]` list; the layout offset
(`r_key_title = r_foot_first + len(foot) - 1 + 2`), heights and merges follow
automatically. Verify with `heights_off_plan: 0` and a merge count equal to
the intended set: grid title + Weekly + Team + one per footnote + Cross-Month +
Split + Column Key.

## Adding a footnote to a live tab (no rebuild)

When a note must land now (an audit trail, a hold decision) and no rebuild is
scheduled, write it in two places in ONE change: the sheet row AND the `foot`
list. The list edit is what keeps the note alive across a later rebuild.

1. Find the footnotes block live (rows below the `3  OTHERS` band). The free
   slot directly below the last footnote is a 12px spacer row; it becomes the
   new footnote row.
2. Write with googleapiclient (Hermes venv python + `tokens.json` /
   `credentials.json`): `values().update` single cell USER_ENTERED into A<row>,
   then one `batchUpdate` with `mergeCells` A:L on that row,
   `updateDimensionProperties` 26px, and `repeatCell` grey `#666666` italic 9pt
   with WRAP + MIDDLE. The google MCP tools write values only; merges, heights
   and text style need this path.
3. Append the SAME text as a new entry to `build_month_tab.py`'s `foot` list.
   Layout offsets and the height plan derive from `len(foot)`, so the list edit
   alone keeps them right; an unlisted footnote is overwritten by the next
   rebuild's block rewrite.
4. Verify: read the cell back, and confirm the A:L merge and the 26px height
   (`includeGridData` rowMetadata). A footnote row left at the spacer's 12px
   clips its text.

The `foot` list is shared by every month the script builds, so a month-specific
note rides along onto later tabs (existing notes already do this). Name the
month inside the note text so it stays self-contained.

## Instructed target vs reported figure (they can diverge by design)

When a week BEATS its instructed target and the manager then confirms the higher
actual as the client figure, do NOT rewrite `week_targets`. The instructed
target is a historical fact: it records what was asked for. Push the confirmed
figure into `team[N].reported_total` and the `reported[N]` split instead, then
add a footnote stating the target, the actual, and who confirmed the change.

Rewriting the target destroys the over-delivery signal: `Extra vs Week Target`
collapses to +0.99 instead of showing +4.99 over what was instructed. Worked
case (Sep 2026 Week 3): target stays 64, reported 68, Extra vs Week Target
+4.99, with a footnote recording Rohan's 68h confirmation.

## CATEGORY BANDS

The summary area is grouped into three labelled sections, in this order:

1. **1  MOBEEN ONLY** (personal): Weekly Summary
2. **2  MTMPRO** (team): Team MTMPRO Hours, Cross-Month Weeks, Reported Split
3. **3  OTHERS** (reference): footnotes, Column Key

A band is a light-grey row (`NOTE_BG`), navy bold 11pt, LEFT aligned, 30px tall.
It is deliberately NOT merged: merged bars read as table titles, and the point is
that a band is visibly not a table.

**The day grid is pinned to rows 1-32 and no band may go above it.**
`toptracker_sync.py` writes day N to row `N+2`, so rows 1-32 are a fixed contract
shared with that script. Any block inserted ABOVE the grid silently corrupts the
sync. Bands start at `r_day_last + 2` and push the summary blocks down. Verify a
layout change by re-reading the grid: day 1 must be at row 3, date intact.

Adding a band means adding `r_secN = <previous block last row> + 2` and deriving
the block below it from `r_secN + 1`. Every block start is derived from the one
above, so the map self-adjusts; never hard-code a row position.

## STALE FORMAT OUTLIVES VALUES

`values.clear` removes VALUES only. Formats survive, so a shrinking block leaves
older styling behind. Two separate residues hit the Cross-Month table, and only
fixing the second made the tables match:

1. **Greyscale/fill residue outside the block** (columns M..O from the old
   15-wide version) made the table LOOK wider than its content.
   `reset_wide_block_format()` clears fills and borders in M..O (moved from
   L..O when the Team table grew to 13 columns, Oct 2026).
2. **Text-format residue INSIDE the block** (still within A-L) made the header
   render 9pt instead of 10pt, kept data rows bold, and left a 12pt bold title
   fragment in L52. Clearing fills/borders or merges does NOT touch textFormat.
   `reset_block_area()` resets the whole area to a clean baseline.

Run order on every `--apply` is fixed and matters:

```
values.clear (blocks)  ->  clear_merges  ->  reset_block_area
  ->  reset_wide_block_format  ->  write blocks  ->  style_requests
  ->  verify_grid
```

`reset_block_area` runs BEFORE `style_requests`, never after, or it would wipe
the intended styling it is meant to precede.

### Matching two tables exactly

When the user says one table must "be the same as" another, match ALL of these,
not just width: row heights, header font size, data-row bold, alignment,
number formats, fill colours, and borders.

The reference pair (Team vs Cross-Month) is:

| Aspect | Required value |
|---|---|
| Title row height | 34px, navy fill, white bold 12pt, merged across the table |
| Header row height | 46px, steel fill, white bold 10pt, centred, wrapped |
| Data row height | 21px, white fill, black 10pt, NOT bold, centred |
| Summary row height | 21px, `#D9E2F3` fill, navy bold 10pt |
| Hour columns | `0.00;-0.00;` |
| Delta column | `+0.00;-0.00;0.00` |
| Width | Team 14 (A-N); Cross-Month 11 (A-K), never wider than Team |

Verify with effectiveFormat, not values: read the range with `includeGridData`
and compare the per-cell signature (bg, bold, fontSize, alignment, numberFormat)
of both tables. A values-only check passes while the tables still look different.
Also confirm the row height list, e.g. `[34, 46, 21, 21, ...]` for both blocks.

## MERGES: unmerge before you merge

Merges accumulate because a merge is keyed by ROW RANGE, and the blocks move
down whenever the layout changes (a 31-day month, a cross-month block appearing,
a new footnote row). Each run added its own merges while the previous run's
stayed, so stale ones landed on top of live tables and collapsed real data cells:
a leftover `A:D` merge hid the Mobeen and Solat columns in the Reported Split, and
leftover `A:L` merges sat on the Cross-Month table. Symptom the user reported:
"tables are broken and overlapping".

Rules:

- `--apply` calls `clear_merges()` FIRST, which unmerges the whole script-owned
  area (from the banner row through the Column Key) before writing and re-merging.
  Banner merges included, so they are re-created deterministically every run.
  Never remove that call.
- Cache merges for an `unmergeCells` request: the data API caches values, so drop
  the `fields` filter on the final `spreadsheets().get()`; otherwise it can
  return an empty merges list and hide the problem.
- Every merge range is 0-indexed while `meta["r_*"]` values are 1-indexed. Use
  `r - 1` as the start. Getting this wrong puts the merge one row BELOW its text,
  which is what left footnote 1 unmerged with a stray merge on the blank row
  after footnote 3, and what collapsed the Reported Split header row.

Expected merge set: the two banners + one per table title + one per footnote.
October 2026 (split weeks, 7 footnotes) verified live and on a scratch build at
14 total:

| Row | Cols | Purpose |
|---|---|---|
| 1 | A-H | day-grid banner (Mobeen) |
| 1 | I-K | day-grid banner (Usama; Oct 2026+ only) |
| r_wk_title | A-I | Weekly Summary title |
| r_tm_title | A-N | Team title (14 cols) |
| r_cx_title | A-K | Cross-Month title (11 cols, never wider than Team) |
| r_sp_title | A-F | Reported Split title |
| r_foot_first.. | A-L | one per footnote (len(foot)) |
| r_key_title | A-D | Column Key title |

Nothing below the Column Key is merged (the old key note rows are gone). If the
count exceeds the table above, stale merges survived: re-check that
`clear_merges` runs before `style_requests` and that no title merge is missing.

## DATA SAFETY (read before editing the script)

A rebuild wiped every hour value in columns D:H on September26. Two causes, both
fixed, both worth re-checking after ANY change:

1. **Never write a day row wider than column B.** Day rows were written from the
   same padded block as the title, so `["1 September","Tuesday"]` was padded to 8
   columns and blanks landed on D:H, erasing tracked, untracked, Other and GMI
   hours. Day rows are now written with `protect_cols=(3,)`, which truncates the
   block to 2 columns. Keep that guard in place.
2. **Never size a clear from counted data.** `clear_stale_below` computed its end
   row as `first + len(existing) + 8`; a partly-filled month returns populated
   values only up to its last filled row, so the span was short and the clear
   started inside the grid. Both bounds are now absolute layout positions.

Rules:

- The daily grid (A1:H`2+days`) is DATA. The script writes only A, B and the two
  header rows there; every other cell in the grid is user-owned.
- The Usama block follows the same rule: I3:J`2+days` are DATA (chat-fed) and
  are never written; K cells are seeded only when empty. `verify_usama()` fails
  the build on any I/J change.
- `clear_stale_below` runs between the summaries and the Column Key only.
- After any script change, run this proof before trusting it: snapshot
  A1:H`last_day` (and I3:J`last_day`) to JSON, rebuild, then diff cell by cell.
  Expected result is ZERO diffs. A single diff means the grid is being written.
  For extra safety prove the run on a scratch sheet first (`--spreadsheet`).
- Also inject a value (e.g. D20=3), rebuild, confirm it survived, then clear it.
  Do this on a throwaway tab first.

## Weekly report tab grouping

Three labelled category bands group the tables by kind:

| Band | Blocks | Audience |
|---|---|---|
| 1 MOBEEN ONLY | Daily grid, Weekly Summary | personal |
| 2 MTMPRO | Team MTMPRO Hours, Cross-Month Weeks, Reported Split | team |
| 3 OTHERS | Footnotes, Column Key | reference |

Build band 1, then band 2, then band 3. Never put footnotes between two team
tables: that splits the group and the reader loses the connection between the
team table and its reported split.

## Cross-month weeks (a Mon-Sun week split across two tabs)

A week is Monday-Sunday, so any month that does not start on a Monday or end on
a Sunday has a week spanning two tabs. Reported weeks are therefore sometimes
`Aug 31 - Sep 4` (real example: September26's Week 1).

The script auto-detects both shapes and emits a `CROSS-MONTH WEEKS (SPLIT
ACROSS TABS)` block when either exists:

- **leading spill**: week starts in the previous month (Oct 1 2026 = Thursday,
  so Sep 28 - Oct 4).
- **trailing spill**: week ends in the next month (Oct 31 2026 = Saturday, so
  Oct 26 - Nov 1).

Columns (10, A-K, narrower than the Team table's 14 so it never overhangs):
Week | Other Tab Total | This Tab: Tracked | This Tab: Untracked | This Tab:
Broadcasting | This Tab: Others | This Tab: GMI | Week Total |
Week Target | Extra vs Target.

The other tab's half is ONE combined total, not five per-column splits. That is
what keeps the width down; the user asked for it explicitly ("too wide, should be
less or equal to team hours table"). The sibling side is read live with
`IFERROR(SUM('<Tab>'!C3:H32),"")` (day N sits at row N+2 in every tab).

Always return EMPTY STRING from that IFERROR, never the text "n/a": a text value
in the total column poisons `=B+C+...` into `#VALUE!`. Two related traps:

- Total the row with `SUM(B:G)`, not `B+C+D+...`; SUM ignores text, `+` errors.
- The WEEK TOTAL row must carry exactly as many cells as the header. A short row
  is left-padded by the writer, which shifts every total one column right (the
  WEEK TOTAL row showed `40.00` under Extra vs Target before this was fixed).

Never nest a formula inside SUM: `SUM(IFERROR(...),IFERROR(...))` is a syntax
error (`#ERROR!`). Build separate cell formulas instead.

**Reporting a cross-month week:** use this block for the combined total, not
either tab's Weekly Summary, because summing one tab drops the other half.
Verify the block's Week Target and per-column placement against the day cells
before quoting: a stale block can carry the wrong target or a shifted total.
If the block disagrees with the Weekly Summary, recompute from the day cells,
report the block as a finding, and fix the block separately.

## USAMA day columns (I-K, standard build from October 2026)

Usama's hours are tracked as three columns BESIDE the daily grid (no new table):
I = 'USAMA TRACKED', J = 'USAMA PRODUCTIVE', K = 'USAMA DIFF', one row per day
(day N = row N+2, rows 3-33). Header row 2 styled like the grid header (steel,
white bold, centred); data rows white 10pt centred; I/J use PLAIN0, K uses
SIGNED. K{r} = `=IF(OR(I{r}="",J{r}=""),"",I{r}-J{r})` (tracked minus
productive; the gap gets shared with Usama for explanation).
Weekend rows carry the same WEEKEND fill/italic as the grid. Borders extended
over I:K rows 2-33 (MID_B outer, LIGHT_B inner). Values arrive as chat feeds;
cells stay empty until fed. Note: below row 34, column I is also the weekly
block's EXTRA/SHORT column; days and weeks never overlap. A first draft built a
week-based table below the Column Key; it was reverted in favor of these columns
on user request, so keep that area clear. Now part of the standard build (`USAMA_COLS_FROM = (2026, 10)` in
build_month_tab.py); older months are gated out so a rebuild never adds the
columns retroactively.

- Row 1 carries a second banner: 'USAMA WORKED HOURS ' in I1, merged I1:K1,
  theme-Accent-1 blue #5891AD, white bold centred. A1:H1 stays the Mobeen
  banner. `style_requests` merges BOTH banners every run (earlier builds relied
  on a pre-existing banner merge and never created one, so a fresh tab had an
  unmerged, wrapping banner).
- Header row 2 extends to K (same steel style as A-H). The block carries its
  own border box: I2:K last-day, MID_B outer, LIGHT_B inner.
- Data rows mirror the grid (white 10pt centred); I/J use PLAIN0, K uses
  SIGNED; weekend rows carry the same WEEKEND fill and italic. Holiday /
  half-day highlights and 'Leave' labels cover columns A-H only (Mobeen's
  calendar, not Usama's; October 2026 left I-K plain on his Oct 5 leave).
- K is script-owned: `seed_usama_diff()` fills EMPTY K cells with
  `=IF(OR(I{r}="",J{r}=""),"",I{r}-J{r})` and preserves anything already in a
  K cell, so a rebuild can never clobber content. I/J are fed from chat and are
  NEVER written by the script; `verify_usama()` compares I3:J last-day before
  and after every build and fails the run with 'USAMA DATA CHANGED' on any
  difference.
- A fresh-tab create runs clean: the grid verify allows the script's own writes
  (banner, header row, Date/Day labels) only when the tab was just created;
  anything else, especially D:H, still fails the run.
- Verified cell-for-cell against Mobeen's hand-formatted October26 on a scratch
  sheet (formats, merges, heights, K formulas). The one known cosmetic delta:
  his I1 lacks an explicit wrapStrategy and the build writes WRAP; renders
  identically.

## Block layout (rows are computed, never hard-coded)

For a 30-day month (September26, verified live). The day grid is PINNED to rows
1-32 because `toptracker_sync.py` writes day N to row N+2:

| Rows | Block |
|---|---|
| 1-2 | Title + daily headers |
| 3-32 | Daily grid (day N = row N+2) |
| 34 | Band 1 MOBEEN ONLY |
| 35-42 | Weekly Summary (title, header, W1-5, MONTH TOTAL) |
| 44 | Band 2 MTMPRO |
| 45-52 | Team MTMPRO Hours |
| 54-58 | Cross-Month Weeks (only when a split week exists) |
| 60-66 | Reported Split |
| 68 | Band 3 OTHERS |
| 69-71 | Footnotes |
| 74-77 | Column Key (title, header, 2 data rows) |

Row heights on that map: band 30, title 34, header 46, data 21, footnote 26,
spacer 12, Column Key data 48. See ROW HEIGHTS above; all of it comes from
`height_plan(meta)`.

A 31-day month shifts everything below the grid +1. Always read the `meta` keys
the script prints (r_sec1/2/3, r_wk_*, r_tm_*, r_cx_*, r_sp_*, r_foot_first,
r_key_*) rather than assuming a row number.

## Team table columns

A Week | B Period | C Mobeen | D Usama (reported) | E Usama (extra) |
F Solat | G Danish | H Other | I Total Hours | J Base Target |
K Week Target | L Reported to Client | M Extra vs Base | N Extra vs Week Target

14 columns from 2026-10-22: D freezes Usama's figure at the last report, E
accumulates the hours he works after it (the banked head start). **The week
row's C-H and I are STATIC values; only M (`=I-J`) and N (`=I-K`) are
formulas.** Writing C-H does not move I: after any component change, write
I = SUM(C:H) by hand, then confirm M/N recalculated. The MONTH row is
different: C-H are SUM formulas, I is a count-sum, J/K/L use SUMPRODUCT, and
M/N are deltas, so it follows the week rows automatically. Title merge,
borders, header and widths span A-N; footnote merges stay A-L (decor). At
each report: move Usama's current weekly figure from E into D and reset E.

## Weekly figures arrive as chat feeds

Team numbers come from the user in chat, in any order, sometimes mid-week.
Record each as it lands (single-cell USER_ENTERED write + read-back):

- Per-person actuals: Usama (reported) to D of the week row, Usama (extra) to
  E, Solat to F, Danish to G, Other to H. Usama also feeds DAILY pairs (`10:25
  log`, `9:30 productive`): they go into his day cells (`I` = tracked/log, `J` =
  productive, `K` derives), one row per day, each as it arrives. The sheet
  itself is the ledger; do not keep a side file for these. His basis is settled
  (productive); do not re-ask.
- Daily pairs also move the team row when they fall after Usama's quota is
  complete. Sum the PRODUCTIVE `J` values from the day after the week's cutoff
  through Sunday into E (the cutoff is named in the week's L note, `40h quota
  completed <day> ...`); pre-cutoff productive hours are already inside D. Then
  rewrite the week's static I to the new C-H total. Two post-quota days at 7.0
  and 6.5 productive add 13.5 to E, not 0.
- When the user re-labels a feed ("record it in Tuesday"): move the entry to the
  named day, never keep it on both days.
- `C = the week's Mobeen day rows summed (Tracked + Untracked)`; Usama's
  weekly figure goes to D (reported) when a report is shared and E (extra) for
  hours after it, on his PRODUCTIVE basis (tracked/counted figures stay in the
  I-K day columns). Update C/D/E whenever a side moves.
- A figure the user revises later supersedes the earlier one: overwrite the
  cell and say what it replaced in chat; never leave two versions standing.
- Writing a team row mid-week is allowed on explicit instruction; the row is
  not locked until the close and must be refreshed when a side changes.
- A set the user reports as SENT to the client: L = total on the week row and
  per-person values in the Reported Split row (C:F). Never write reported
  values into the week's actual columns C-G; if actuals are unknown they stay
  blank and say so. Boundary weeks are recorded on the live tab's boundary
  row; the client span ("Sep 28 - Oct 2") differs from its calendar label and
  belongs in `team_periods`; flag the mismatch, never hand-edit the cell.
- "What else needs updating" sweeps: walk the blocks and list per block: team
  weeks (C-G actuals, K Week Target, L Reported), Reported Split rows,
  cross-month rows, day rows (today's fill, dictated E values), labels.
  Check the previous month's tab too: fill_hours refreshes only the tab of the
  date it runs for, so its spill figures can still need entries.

## Three numbers that must never be collapsed

| Concept | Meaning | Example |
|---|---|---|
| Base Target | the standing weekly mark (50h; drops to 40h from Week 3 of Oct 2026) | 50h |
| Week Target | instructed figure for THAT week, may be raised | 64h (Week 3, Rohan) |
| Total Hours | actual delivered, may exceed either | 68.99h |

Two deltas are required: `Extra vs Base` (I-J) and `Extra vs Week Target` (I-K).
Week 3 read +18.99 and +4.99 for the SAME 68.99h; reporting one figure
misrepresents the week. The Column Key block explains this in-sheet.

## Reported vs actual

`Reported to Client` (col L) is the figure actually shared, which may be below
Total Hours. The Reported Split block holds the per-person version of what was
shared. Keep reported and actual in separate blocks; never overwrite actual
hours to match a reported figure.

## Config file

```json
{
  "week_targets": {"3": 64},
  "team_periods": {"1": "Aug 31 - Sep 4"},
  "day_targets":  {"2026-09-10": 4},
  "team":     {"3": {"mobeen": 49.99, "usama_reported": 25.5,
                     "usama_extra": 0, "solat": 18.5, "danish": 0.5,
                     "reported_total": 64}},
  "reported": {"1": {"mobeen": 35.48, "solat": 17, "danish": 3.5}}
}
```

All keys optional. `team_periods` overrides a week label when the client week
differs from the calendar week (e.g. "Aug 31 - Sep 4" instead of "Sep 1 - 6").
`day_targets` sets a per-date weekday target (half days, holidays).

## Missing-data workflow (ask before assuming)

Never invent hours. Sequence:

1. `--report-missing` and read the JSON `missing` array.
2. Group by block and week, then ask the user in ONE message, e.g.
   "Week 3 (Sep 14-20) needs Solat and Danish hours, and the Reported to Client
   figure. What are they?"
3. Write the answers into the team table (C:H, L) and the Reported Split (C:F).
4. Re-run the script so MONTH TOTAL formulas pick the values up, then re-read
   the block to confirm.

Rules the reporter encodes:

- Only weeks whose Monday has already arrived are checked. A future week is
  never reported as missing.
- `Other` is optional and never flagged, or the list is noise every week.
- A weekday is flagged as a daily gap only when D (tracked), E (untracked) AND
  H (GMI) are all empty for that date.
- Blocks: `team`, `reported_split`, `daily`. Each entry carries the exact cell
  reference so the fix is unambiguous.

## Target semantics (learned the hard way)

- Week targets are entered in the sheet at build time: the week's Monday-to-
  Sunday span, weekdays only, 8h each, minus holidays/half days (`day_targets`
  at build; fill_hours reads the `Leave`/`Half day` F labels on every refresh),
  then clamped to the personal weekly cap once it applies.
- Client hours cut (Oct 2026, effective Mon 2026-10-12): MTMPRO team quota
  40h/week. Mobeen's personal total stays 40h/week across all projects; his
  (incl. Usama) MTMPRO share = 32h/week while Solat works (8h testing), and
  40h/week if Solat is out. Team standing mark 50h -> 40h. The personal cap
  lives as `WEEKLY_TARGET_CAP_FROM` / `WEEKLY_TARGET_CAP` (40) in this skill's
  build_month_tab.py AND in fill_hours.py (which recomputes the live weekly
  block after every fill); `standing_base()` picks 50 vs 40 per week. Keep the
  two copies in sync, and clamp the cap PER WEEK: clamping a month total would
  cap a whole month at the single-week limit.
- WEEKLY SUMMARY columns after TOTAL (user layout 2026-10-22): I `BASE TARGET`
  = the leave-adjusted week target (every STARTED week counts all its in-month
  weekday targets; any F label CONTAINING `leave` = 0, `Half day` = 4, so
  `Sick leave` and `Annual leave` both zero the day), J `EXTRA/SHORT` = the
  live `H - I` formula. A week in progress therefore reads negative until it
  completes: that negative IS the hours still owed for the week. Unstarted
  weeks keep both cells blank; MONTH TOTAL is `=SUM(I...)` and `H - I`.
- The MONTH TOTAL target must never count unstarted weeks. Comparing against
  the whole month produced a phantom -168 on a fresh tab. The builder writes
  every week's base as a static value at build time and `refresh_summary` skips
  weeks that have not started, so those statics survive and the month row keeps
  lying mid-month. Blank each unstarted week's BASE TARGET cell with a
  single-cell `""` write (never a range) after the user's go; the MONTH TOTAL
  `=SUM` and its delta recompute to the elapsed-weeks value on the next read.
- Both scripts own this block: `fill_hours.refresh_summary` writes I = target
  and J = `=IF(guard,"",H-I)`; `build_month_tab.py` writes the same shape.
  Change one, change the other, then re-verify the live tab.
- The TEAM MTMPRO and REPORTED SPLIT blocks are STATIC values, not formulas:
  after any day-cell change update the team week row by hand (Mobeen = that
  week's C+D; Total = sum of components); after a share record the figure in
  REPORTED SPLIT.
- Base/Week Target and Reported totals in the Team table use
  `SUMPRODUCT((H<>"")*col)` so unstarted weeks contribute nothing. A plain SUM
  gave 300h of target for a month with no hours.
- Blank guards test the SUM (`IF(SUM(range)=0,"",...)`), never the displayed
  cell: a zero-suppressed 0 still reads as numeric and defeats `IF(x="")`.

## Colour scheme: Usama reported vs extra

Green (`#D9EAD3`) marks **Usama hours actually included in the shared report**,
nothing else (user rule; never colour the team table or other people's columns).

- Reporting convention: a week fills its quota (40h since Oct 12) from the
  team's hours first, topping up with Usama's hours. Only that consumed portion
  is "reported"; any of his hours beyond the quota were NOT reported and are
  banked. Example: Week 3 (Oct 12-18): Mobeen 5.99 + Solat 5.00 needed 29 of
  Usama's 35 productive hours, so Friday's remaining 6h went to Usama (extra).
- Daily grid: Usama's `I/J` cells are green only for the days whose productive
  hours fit inside the reported figure (attribute day by day from the week's
  first day). Use one rule per reported week with that week's cutoff date:
  `=AND($I<firstrow><>"",$A<firstrow><=DATE(y,m,d))` over that week's rows.
- Team table: never colour it. The reported figure sits in Usama (reported);
  the unreported remainder goes in Usama (extra) as the banked head start.
- A rebuild resets rules to a past cutoff (`1900-01-01`, nothing green); after
  every report re-add the per-week cutoff rules.
- Column L, daily grid: row-level notes go here, not F. At the first extra day
  of each week (the row where the weekly quota was completed), write a short
  italic quota note, e.g. "* 40h quota completed <day> (<hours> Usama hours
  reported). Extra hours from here are not reported; they bank."
- Two-month net note: a CELL NOTE, not visible L text. Pairs are fixed two-month
  blocks: Sep-Oct, Nov-Dec, Jan-Feb. Attach the note to the last weekday's A
  cell of the SECOND month (Oct 2026: A32, 30 Oct). Text: "* <Month A>-<Month
  B> total net +X.XXh (<A> +a, <B> -b; actual vs target)." Add it at each pair
  close, not every month; the next pair after Sep-Oct is Nov-Dec. The builder
  does not place it. This is separate from the L quota notes. Never put it in
  the team table or F. (User rule, 2026-11-03.)
- The legend footnote explains the colours in-sheet; do not colour Mobeen's or
  anyone else's columns.

## Styling rules (do not regress)

Palette (must stay consistent across all blocks):

| Element | Color |
|---|---|
| Category band rows | `#F9F9F9`, navy bold 11pt, LEFT, NOT merged |
| Title bars | navy `#1F3864`, white bold 12pt, wrapped, centred |
| Usama banner (Oct 2026+) | theme Accent 1 `#5891AD`, white bold, centred |
| Header rows | steel `#2E75B6`, white bold 10pt, centred, wrapped, 46px tall |
| MONTH TOTAL rows | `#D9E2F3`, navy bold |
| Weekends | `#FFF2CC`, brown italic |
| Borders | steel outer, `#BDD7EE` inner |
| Footnotes / notes | grey `#666666` italic 9pt |

Every table title is the SAME navy bar (the Reported Split title was `#8EAADB`
and read as a different, lesser table; all five titles are now navy 12pt white).

Hard-won formatting rules:

- `wrapStrategy: WRAP` + `verticalAlignment: MIDDLE` on every cell in every
  block, or long headers truncate.
- Long single-cell notes MUST be merged across the block's full width (A:D for
  the key). A 164-char note confined to column A truncates after ~20%.
- Set explicit row heights: 34px titles, 40-46px headers, 48px for rows holding
  a 3-line wrapped description, 36px for note rows. Releasing height to "auto"
  collapsed the rows to 1-2px because the surrounding grid is locked at 21px.
- Column widths: A 135, B 215 (long key descriptions live here, which also
  widens the daily Day column), C 175, D 175 (Usama reported), E 160 (Usama
  extra), F 150, G 120, H 130, I 118, J 160, K 165, L 180, M-N 175.
- Signed format `+0.00;-0.00;0.00` on every delta column. Plain `0.00` silently
  drops the plus sign and makes +5.98 read as 5.98.
- Zero-suppress hour columns with `0.00;-0.00;` so untouched cells read blank
  rather than a wall of 0.00.
- `hideGridlines: true` on the tab so the explicit borders define the layout.

### When a block gains or moves a column (chrome checklist)

- Title bars: the navy fill paints only through the merged range. Unmerge the
  old range and merge the new full width (weekly summary: A..J), or the band
  stops one column short (seen 2026-10-22).
- Total rows: fill and borders must END at the block's last column. A fill that
  ran to column P produced a full-width bar across the sheet; clear leftover
  formats with `updateCells` + `fields: userEnteredFormat` on the columns to
  the right of the block.
- Borders are per-cell: every new column needs its own top/bottom/left/right.
  Interior lines `#BDD7EE`, the block's RIGHT edge `#2D75B6` (dark navy). The
  total row is where the two most often get swapped.
- Number formats: plain `0.00` for bases, signed `+0.00;-0.00;0.00` for deltas.
- Verify by reading FORMATS back per column and mapping the letters explicitly
  (startColumnIndex + j). An off-by-one mapping once "confirmed" borders on J
  while the J cells were bare; read the header value in the same call to anchor
  the letters.

## Post-build verification (mandatory)

Reading values back is not enough; a stale read can show an old `#REF!`.

1. Read `A<wk_hdr>:I<wk_total>` in FORMULA mode and confirm the month-total row
   has a cell for EVERY column C-I (a missing blank for column F shifts every
   later formula one column right and self-references H, producing `#REF!`).
2. Read FORMATTED_VALUE and confirm no `#REF!`, `#VALUE!` or `#NAME?` anywhere.
3. Format audit of the summary block: title merge endColumnIndex equals the
   header width; no fills or borders past the last block column; every block
   cell (including new columns) has a border; delta columns carry the signed
   format.
4. Inject a throwaway value into one day row and one team row, confirm the
   month totals move, then CLEAR the injected cells.
5. When a total does not move after a component write, verify whether the cell
   is static before assuming a broken dependency: read it with googleapiclient
   (`Credentials` from `tokens.json` plus the `installed` block of
   `credentials.json`, then `values().get(..., valueRenderOption='FORMULA')`).
   A returned number means the cell is static and must be written by hand;
   `=...` means it is a formula and the dependency is elsewhere. The MCP
   `sheets_read` can return the computed value even when `FORMULA` is
   requested, so it cannot settle this question alone.

## Pitfalls

1. **Header rows must be flat lists.** `[["A","B"]]` is correct;
   `[[lbl] for lbl in ["TITLE", HDRS]]` nests a list and Sheets rejects it with
   `Invalid values[N][0]: list_value`.
2. **`updateDimensionProperties` needs a DimensionRange**, not a GridRange:
   `{"sheetId":n,"dimension":"ROWS","startIndex":a,"endIndex":b}`. Passing
   `startRowIndex` yields `Unknown name "startRowIndex"`.
3. **The Weekly Summary MONTH TOTAL row must carry 9 cells.** Emitting only the
   non-empty columns shifts the totals right; column F is deliberately blank
   because F is the "Other Project" label in the day grid.
4. **Never write into a legacy tab.** Months before 2026-08 use a 6-column
   layout; the script refuses them by design.
5. **Do not run on the current month without a config.** Rebasing an existing
   tab is safe for the summary blocks, but the team table seeds are empty, so
   pass `--config` with the known week figures or expect the missing-data list
   to be long.
6. **`create_dizio_tab` / `format_worked_hours.py` in `my-work-hours` write the
   OLD 6-column layout and DESTROY data.** Use this skill's script for any month
   from 2026-08 onward.
7. **A cross-month block must reference only its own spill days.** Pointing the
   other-tab SUM at the whole day grid (C3:C32) pulls a full month's hours into
   a single week. Compute the row span from that side's day list:
   `row = 3 + first_day - 1` through `3 + last_day - 1`.
8. **The Note text must name the right sides.** For a leading spill the other
   side is the previous month's last days (Sep 28) and this side is the 1st
   (Oct 1); for a trailing spill it is this month's last day and next month's
   1st. Deriving it by splitting the label string gets this backwards.
9. **Weekly Summary EXTRA/SHORT is a DELTA, not the target.** It must read
   `total - weekday_target` (Week 1 = 36.97 - 32 = +4.97). An earlier version
   wrote the bare target there, so weeks showed +32.00/+40.00. Guard it with
   `IF(SUM(Hfirst:Hlast)=0,"",...)` and never `IF(OR(SUM(..)=0,""),...)`, which
   concatenates a blank into the subtraction and yields `#VALUE!`.
10. **Column C1 of the day grid aliases the previous month's last day.** A
    leading-spill week (1st not a Monday) makes the day-1 row read C1:C`n`,
    which overlaps the previous tab's C(1+last-day):C31. September26 C1:C6
    duplicates August 31 fully. Use the CROSS-MONTH block for those weeks and
    never sum two tabs' Weekly Summary rows together for one split week.
11. **A1:H1 is merged, so the banner text belongs in A1.** Writing it to C1
    renders a blank banner: a merged range displays only its top-left cell.
12. **Never add a project column with `insertDimension`.** Column inserts are
    sheet-wide: a grid column shifts every block below and the I-K Usama block
    at once. Migrate the day values with ONE matrix `values.update` into the
    new column letters, update the header lists, team-table build, styles and
    widths, then rebuild with `--apply` and a config carrying every current
    seed (team rows incl. `usama_reported`/`usama_extra`, reported splits, week
    targets). Read the grid back cell by cell afterwards.
13. **Anchor a team-row write to the row's own Week label, never to a
    hand-counted position in a values read.** In a values response the A1 row =
    the range's start row + the entry's index, and hand-counting that index over
    a 55-entry array is off-by-one-prone: the write lands on the neighbouring
    week, and a mid-month feed then books team figures into a FUTURE week.
    Locate the row by matching its unique `Week N` + period string (compute the
    index in code, or read the block header together with the row), and after
    every team-row write read back columns A:B of that row: the Week/Period
    label is the only proof the write landed where intended; reading back only
    the written cells confirms a wrong-row write just as happily. If figures
    land on a week that has not started, clear those exact cells at once; a
    future week never carries team figures.

## Related

- `toptracker-hours` — column C (MTMPRO TRACKED) values and the weekly crons.
- `my-work-hours` — Dizio defaults, calendar/Fathom cross-reference, colour rules.
- `mtmpro-weekly-report` — the Slack-formatted weekly message and its format.
