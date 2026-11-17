---
name: work-hours-bot-ops
description: "Use when running Static's hours routines and fills."
version: 1.1.1
author: TUTU
license: MIT
metadata:
  hermes:
    tags: [work-hours, sheet, kimai, toptracker, routines]
    related_skills: [work-hours-tracking, toptracker-hours, work-hours-monthly-tab, mtmpro-weekly-report]
---

# Work Hours Bot Ops (Static, the glitch cat)

## When to Use
Triggers: any work-hours sheet write or check, a routine run (nightly fill, overnight reconcile, meeting sweep, weekly close), a FLAG message about cross-midnight or running Kimai entries, or the user asking about their logged hours.

The bot's operating loop around the worked-hours sheet. Mechanics live in the sibling skills (work-hours-tracking, toptracker-hours, work-hours-monthly-tab, mtmpro-weekly-report); this one is the procedure plus the earned pitfalls. Load the matching sibling before any live action.

## Ground truth
- Sheet: the worked-hours spreadsheet; tab `<Month><YY>` (September26 = Sep 2026). Day N = row N + 2. Columns: C MTMPRO tracked, D untracked MTMPRO, E Broadcasting Platform, F project labels, G others, H GMI, I Usama tracked (log), J Usama productive, K Usama diff (formula), L daily row notes. No Dizio column since 2026-10-22. Team table has the Usama (reported)/(extra) split.
- fill_hours.py (`/home/user1011/.hermes/scripts/`, run with the Hermes venv python): fills C (TopTracker local DB, start-date attribution) and H (Kimai sum, 2dp), then refreshes weekly targets. Flags: `--date`, `--force`, `--dry-run`, `--summary-only`, `--no-summary`.
- Client hours cut from Mon 2026-10-12: MTMPRO team quota 40h/week; Solat 8h/week. Danish is off MTMPRO (user, 2026-11-06): the quota team is Mobeen + Usama + Solat; his G column stays blank going forward, past figures untouched. Mobeen's personal total stays 40h/week across all projects; Mobeen (incl. Usama) covers 32h/week of MTMPRO while Solat works, 40h/week if Solat is out. The personal cap (40h) and the 40h standing mark live as `WEEKLY_TARGET_CAP_FROM` / `WEEKLY_TARGET_CAP` (`BASE_WEEK_TARGET_CUT`) in fill_hours.py and build_month_tab.py; keep the two copies in sync.
- A client-proposed cap is not a quota change. A counter that pairs a balance drawdown with a lower weekly cap (for example 25h/week) does not touch `WEEKLY_TARGET_CAP` or the 40h standing mark until the user accepts it in writing. Keep filling and reporting at 40h and flag the proposal separately.
- Regime (Rohan, from 2026-10-13): fixed 2:30pm-11:30pm; daily day-end + next-day plan in the report group by shift close; MTMPRO: Usama primary, user supports/reviews only, max 2-3h/day.
- hours_overnight_scan.py: the morning edge check (see Flags below). Never writes.
- Kimai: config `~/.hermes/config/kimai.json`, project 1 = GMI. Day filter is by BEGIN date, so an entry crossing midnight never appears in the next day's window, and running entries show duration 0 until they stop.
- Google Calendar and Fathom recaps (Gmail, from fathom.video) via the google MCP.
- Team sheet (multiple developers' Kimai hours, one shared sheet): `kimai_team_hours.py` from the `multi-kimai-hours` deliverable on branch `skill/multi-kimai-hours` of `mobeenx20/hermes-agent`; operating notes under "Team sheet: multi-account Kimai" in toptracker-hours.

## Routines
| Routine | When | Kind |
|---|---|---|
| Nightly hours fill | 23:55 daily | no-agent script `nightly_fill.sh`; owned by this profile (moved from the default profile 2026-09-25; the default copy is paused as a spare) |
| Overnight reconcile | 09:00 daily | no-agent script `overnight_scan.sh`; only flags post |
| Meeting sweep | 20:00 daily | agent; proposes unlogged meetings, else [SILENT] |
| Weekly close | Sun 19:00 | agent; always posts the week digest |

## Acting on a FLAG
1. Write nothing yet. Restate the finding with the exact write you would make (cell + value) and the proposed placement. Kimai default: the day the entry ENDS. TopTracker: the day it starts.
2. Wait for the user reply: "book", a day override, or "skip".
3. On approval: write the single cell (USER_ENTERED), read it back, then run `fill_hours.py --summary-only` to refresh the block.
4. If the target cell already equals the value, say so and write nothing.

Make every approval ask a poll (clarify) whose options ARE the candidate writes, recommended option first, and batch independent writes into one poll. Chat delivery conventions (polls for confirmations, raw-MXID mention at completion) live in the matrix-communication skill.

When explaining a choice before the poll, keep it plain: one line per option (what moves, what stays, what the totals do), the recommendation, and the short reply that enacts it. Column letters and ledger jargon only appear beside their plain words; dense option analyses get bounced back for a simpler version.

This protocol also covers direct instructions that move a day's or a column's attribution, not just routine flags. Three earned extensions:

5. If the instruction names hours that do not exist on the named day (the named day reads 0.00h), do not guess and do not silently no-op: list the candidate sessions with exact values and ask once, covering both the value and the placement; phrase every option as the complete write (destination cell + final value + what gets cleared).
6. Moving hours between days is a MOVE, not a copy: write the destination, clear the source with `""`, read both rows back, refresh the block. Never leave the same hours booked on both days. Do not add booking notes to sheet cells; record the move in chat only. For a tracker-backed move, derive the destination from the authoritative tracker sum, not the old cell plus a delta. For a Kimai/GMI move, the API cannot re-date an entry, so the move is sheet-only: destination H = its verified current H + the source H, source H cleared, and no fill on either day afterward (a fill re-reads Kimai by begin date and restores the source while overwriting the destination). Use `--summary-only` to refresh summaries. A cross-month move needs both month summaries; report both month deltas and the affected calendar-week total.
7. Moving between tracked and untracked is a column MOVE: write the destination (C for tracked, D for untracked), reduce or clear the source, rewrite F with the actual duration and the "tracked" qualifier, read both cells back, refresh the block. Never leave the same meeting in both columns.

## Leave days
- A leave day is a TARGET override, not a zero-hour workday: the day's target drops by the leave fraction (8h for a full day, 4h for a half day), and the week and month targets fall by the same amount.
- Label F with the leave type the user gives ("Sick leave", "Annual leave"). Keep medical detail out of the sheet; the label is the record.
- Propose the exact writes (F label plus the target override) and wait for the user's go. Never zero a day or add a leave label on your own.
- After the write, refresh the block with `fill_hours.py --summary-only`, then re-read the day row and the weekly target. A leave day is not a worked day: it must not add hours, and it must not leave the target at 8h.

## Meeting sweep
- Sources: today Calendar events plus Fathom recap emails (`from:fathom.video newer_than:1d`).
- Anything not evidently logged in today row: propose it. MTMPRO meetings default to column D (the untracked MTMPRO column since the 2026-10-22 restructure; E is now Broadcasting Platform) with a short F label ("MTMPRO meetings"); use the user's stated duration first, then the calendar/Fathom length, never a standard block; truncate to 2dp, 30 min = 0.5. If the user says a meeting belongs in tracked hours, propose C instead and reduce or clear its D entry; never leave it in both. Approval required; propose only.
- All accounted for = end with [SILENT].

## Weekly close (Sunday)
1. Read the month tab; compute the week totals per column from the day cells (read them, never retype).
2. MTMPRO team numbers: Mobeen (C + D; no Dizio column any more) plus Usama's productive hours (column J), honoring documented exclusions (non-productive tracked time stays OUT of the quota but IN a note). Cross-check against mtmpro-weekly-report.
3. Month invariant: MONTH TOTAL extra must equal TOTAL minus the month target (8h per elapsed workday, each week capped at the personal limit: 40h); flag any guard SUM that is empty over written cells.
4. Post the digest: week totals, delta vs target, team breakdown, month standing, anomalies. This routine always posts.

## Monthly audit (read-only) before trusting a tab

Run this before reporting figures from the month tab. Report findings; never fix them silently.

- User edits: to isolate what changed, list Drive revisions, export the prior
  revision as XLSX, and diff the month grid against current formulas/values.
  Date serials are noise; numeric and text changes are the signal.

- TEAM MTMPRO vs daily grid: Mobeen = that week's C+D; row total = sum of
  components. A blank week row or a Total that does not reconcile is a finding.
- REPORTED SPLIT = what was actually shared; it will diverge from the team
  table whenever the week ran extra (that is correct) but a missing Week 1 row
  or a stale figure is not.
- Cross-month blocks after ANY column migration or month move: the Sep 28-Oct 4
  row kept the pre-Oct-22 mapping (Tracked 0 / Untracked 4.31 / Broadcasting
  6.48), and a trailing split row can carry a target from another week (32
  against the correct 40). Recompute the row from the day cells before quoting.
- Footnotes must belong to THIS month: September's "64h Week 3" and "Sep 22"
  notes sat in the October tab.
- Green CF coverage: one rule per reported week with that week's DATE cutoff.
  A week with Usama daily hours but no rule shows no green (Week 2, rows 7-13).
- Kimai per-day: sum each day's timesheets and compare column H; a running
  entry is unknown, never zero.
- Any base/target that does not reconcile with its own components (month base
  130 vs week bases 220) is stale: report it, do not rewrite it.

## Pitfalls (earned)
- Kimai cross-midnight: scan the PRIOR day for entries whose end date crosses midnight, then SPLIT at 00:00 (pre-midnight part on the begin day, post-midnight part on the end day), matching Kimai's weekly view. Never whole-entry end-day. A range fill overwrites the split; refresh split days manually from the entry's clock times. Running entries are duration 0 until they stop.
- Partial-value freeze: a non-empty H or C is not final. A 23:55 partial or mid-day split blocks the next fill via `existing and not force`. fill_hours auto-repairs H under-reads from split-aware Kimai and flags C under-reads; the morning scan checks both. Never trust "already filled" alone.
- TopTracker DB purges within days: the 23:55 fill is the reliable read; a next-morning re-read can legitimately see nothing. A later read can also come back HIGHER (sessions synced after the fill): when the user asks to update the day, refresh with `--force` and state the delta (`4.35 -> 4.4`); never leave the capture stale.
- Zero never clears a cell. Future days never get filled. Merged rows silently redirect single-cell writes; fill_hours checks merges, so manual writes must too: one command covers the manual side (`work-hours-tracking/scripts/sheet_write_checked.py` = merge check, single-cell USER_ENTERED write, read-back that fails loudly on a no-op).
- The user hand-edits the tab himself; when he says "i updated the sheet", re-read the whole row and the summary blocks before quoting numbers. His row edits can wipe neighbouring cells (2026-10-22: G24 disappeared when he set C24). Restore a wiped cell only when an earlier explicit instruction had put it there, and say that you restored it.
- Sheet discipline: USER_ENTERED, decimal hours at 2dp, read-back after every write. Block cells are live formulas; never overwrite them, refresh via --summary-only. --summary-only targets the CURRENT month; to refresh a past month, pass --date <last day> --summary-only (e.g. --date 2026-10-31 for October).
- Notes upkeep: exception notes live as cell notes plus footnote rows; when adding, keep build_month_tab.py in sync (see work-hours-monthly-tab). At each two-month pair close (Sep-Oct, Nov-Dec, Jan-Feb), add the pair net twice: as a cell note on the second month's last weekday A cell (Oct 2026: A32, 30 Oct) AND as visible text in K43, worded plainly ("333.54h worked vs 332h target, 1.54h over"). K43 sits outside the A:J table by design; the user reads it directly, so never clear it as a duplicate. Do not roll one month forward.
- Weeks: periods come from the block's own strings ("Sep 21 - Sep 27"); never assume.
- Resolve "today", "yesterday" and bare weekdays against the LIVE clock (`date`), never the chat's start date: this chat spans weeks, and anchoring on the old date pulls another day's data. Just past midnight the user's "today" is the shift that just ended; fill it with `--date <that day>`. A request arriving after 23:55 may already be done by the nightly run (the fill answers `already X - pass --force`).
- Moved bookings leave the source day's H blank: a later range fill over that day would re-write it (double count). Never range-fill a moved day. The user wants no booking notes in sheet cells (Oct 15: F16/F17 cleared on request); keep the audit here instead. Live moved items: Oct 11 to 9 (2.18h); TopTracker tail 0.27h (the Oct 15 01:25 row of the Oct 14 night session) merged into Oct 14 as E16 (user request); subtract 0.27 from any Oct 15 tracker refresh until the row purges (applied 2026-10-15: D17 = 0.88 = raw 1.15 minus 0.27; as of 23:25 that night, no hours after the 22:16 entry had closed, so the Oct 15 stretch after 22:16 may need a re-pull once sessions/entries land - the nightly skips filled days). Week 3 team row (Oct 12-18): Mobeen 5.99 | Usama 29.00 | Solat 5.00; total 39.99 (-0.01 vs the 40 target). Team table gained a separate Usama column (D) 2026-10-15; C is Mobeen-only from then; the earlier merged C was split arithmetically (W2 21.68/26.00, derived, flagged; W1 left blank). Usama basis switched to PRODUCTIVE on 2026-10-16 (D50 33.81 -> 29.00; tracked figures stay in the I-K day columns). W2's 26.00 remains the old residual (tracked/lump basis); his W2 productive figure is pending from the user. Danish / Other / Reported to Client still open; month row C 27.67 / D 55.00 / E 20 / total 102.67. Kimai #226665 (2.43h) was rebooked back to Oct 14, its natural begin day (Oct 14 sums 6.93 on its own); no guard needed. If the nightly missed (app closed at 23:55, check `hermes cron list` for overdue state), fill the missed day manually with `--date`. Nov 2 2026 H reads 6.60 by user decision (split-rule expectation 6.47; the 0.13h already sits in Nov 3's 4.95), so do not re-flag it.
