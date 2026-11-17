# Rebuilding a missing day for the work report

Use when a day, or one project within a day, has no entry in the store: `list_reports(from, to)` returns nothing for that scope. Rebuild from evidence, name the sources in chat, invent nothing.

## Source checklist, in order

1. **Store first.** `list_reports(from='YYYY-MM-DD', to='YYYY-MM-DD')` across all projects; `get_report` / `view_report` for the hits. Only the store is the canonical record; everything below is reconstruction evidence.

2. **Meta repo** `~/Dev/mtmPro` (authored as Mobeen; Usama does not commit as Mobeen). Carries the plan / review / finding / Jira trail:
   - `git log --all --since=... --until=... --pretty=format:'%ad %h %s' --date=format:'%a %m-%d %H:%M'`
   - A plan that lives on another branch: `git show <branch>:.claude/plans/<TICKET>.md`
   - Subjects read like a work log: "plan: implemented...", "log findings B-...", "Jira comment NNNNN posted", "browser verified".

3. **Dated draft files** at the meta repo top level (Jira comments, PR notes, release docs, client summaries). Find by mtime:
   `find ~/Dev/mtmPro -maxdepth 1 -newermt 'DAY1 00:00' ! -newermt 'DAY2 00:00' -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort`
   - Release day: read `prod-release-<date>-notice.md` first. It carries the Jira comment, PR list, verification numbers, and rollback, so the release block is built from one file instead of re-derived from git.

4. **Code repos** `mtmproBackend` / `mtmproFrontend`: same `git log --all` pattern.
   CAVEAT: Mobeen and Usama both commit as the shared `Mohsin` identity there, so authors cannot attribute. These logs say WHAT happened; day-end reports say WHO did it. Never book a person's implementation or testing from these logs alone.

5. **Trackers:** the sheet (current-month tab; day N sits at row N+2) for tracked / GMI cells; TopTracker sqlite for per-day tracked hours; Kimai for GMI entries (usually none on MTMPRO-only days).
   - Ticket titles: GMI `TECH-*` from Linear (`mcp__linear__get_issue`); MTMPRO `MTMPRO-*` from Jira. The MTMPRO Jira does not hold `TECH-*`.

6. **Calendar / Fathom:** `calendar_list_events` around the day for meetings; Gmail Fathom recaps for meeting titles and durations.

7. **Teammate day-end reports:** ask the user to send them for the days being rebuilt; condense into that teammate's section bullets.

## Partial gaps (a project is missing, not the day)

- A `mobile-app` report does not cover MTMPRO. Run `list_reports` for the missing project before treating the day as empty.
- A tracker row proves time and a project label, not ticket-level work. Keep Mobeen's block at the level the row supports ("Dev merge", "Deployment") and put ticket detail in the teammate's section. Never copy the teammate's implementation bullets into Mobeen's main body.
- If the only evidence is a tracker row, say so in the source note; do not invent tickets, outcomes, or verification.

## Writing rules

- State per day which sources the rebuild used.
- A rebuilt day stays a draft until the user approves it; then write each project record with `add_report` and read it back. One day can need more than one project record.
- Keep the user's own framing when given, but carry ticket-level detail from the evidence; drop anything not evidenced.
- Off days stay off: a leave day reads `Mobeen: leave day.`, never stray-commit bullets.
- Reconstruct one day per pass, then present all blocks in order; verify every number against its source before it goes out.
