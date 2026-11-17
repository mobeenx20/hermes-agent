---
name: work-report-summary
description: Slack-formatted daily/weekly work report summaries.
version: 1.3.1
metadata:
  hermes:
    tags: [work-reports, slack, daily-report, summary]
---

# Work Report Summary

Generate Slack-formatted work report blocks (daily or multi-day) from the user's tickets, git evidence, and teammate day-end reports.

## Format

Always use this exact Slack-ready format:

```
📋 *Work Report - Mon DD (Day)*

*TICKET-ID*: Ticket title
• Bullet point describing work done
• Another bullet
• Verification: test results, build status
• Status: current state (pushed/not pushed, deployed/not deployed)

*TICKET-ID*: Another ticket
• What was done
• Status: current state

*Side findings:* N logged, brief description

***

*Team Member Name (Mon DD EOD):*
• Bullet point of their work
• Another bullet

***

*Next:* Brief next steps
```

## Rules

- Header: 📋 emoji + *bold* date in format `Mon DD (DayName)`
- Each ticket: *TICKET-ID*: Title (bold ticket ID, colon, never an em dash)
- Project-level work with no ticket: *PROJECT*: Label (for example *MTMPRO*: Dev merge); never invent a ticket ID to fit the format.
- Bullet points: use • character, not dashes
- Wrap numbers and identifiers in backticks: build ids (`20260101t120000`), PR refs (`#1234`, `be#1234`, `fe#1234`), SHAs, Jira comment numbers, bug/gap ids (`B-12`, gap `12`)
- Verification line when tests/build were run
- Status line at the end of each ticket block
- Team member EOD: *Name (Mon DD EOD):* in bold, bullets below
- Separators: *** between ticket section, team section, and next steps
- Next steps: *Next:* in bold, 2-3 actions per person, brief, with → for flow. If more are open, keep only the actions that change the next day's outcome and leave dependencies in the ticket's Pending bullet. When the user and a teammate both have items, attribute each group (`Me → ...`, `<Name> → ...`); an unattributed merged list gets corrected.
- A `*Hours:*` line (for example `*Hours:* 4.42 (GMI), half day`) goes after the ticket blocks when the user dictates day hours or the day has special handling (half day, leave); read the figure from Kimai or the sheet, never retype it from memory.
- Plain text, no markdown headers. Slack paste-ready.
- Concise: each bullet is one line, no paragraphs
- When multiple days are requested, output one full report block per day (each block stays individually copy-ready)
- Outcome-first: what was achieved, then what's pending
- A `*Leave:*` line goes after the ticket blocks for a leave day or an upcoming leave; see Leave and follow-ups.

## Revising a report

When the user asks for a change to a report already drafted or stored:

1. Update the record that owns the change: `summary` for narrative, `openNext` for follow-ups, the ticket field for per-ticket detail. Re-read the record after the write.
2. Return the complete paste block, not only the changed section. The user copies one block.
3. Write only what happened. A drafted message is not sent, a queued ticket is not started, and a local setup is not a running system. Do not upgrade the claim to make the report read better.
4. Status is the current phase in one line. Do not chain blockers or prerequisite steps into it; if a blocker changes the next action, put it in Next.
5. Verification is one line with the decisive check. Drop probe-by-probe detail, self-test inventories, and file counts unless the user asks for the full evidence.
6. Before returning an updated block, re-read the live ticket status and the sheet row. A status can move from In Review to Done after the first draft, and a moved booking changes the day total. The first draft is not evidence for the second.

## Side findings

- Write each in plain language: what was found, where, why it matters, and the action. No bare acronyms, finding IDs, or key prefixes.
- Explain a side finding in chat when the user asks what it means. Keep that explanation out of the report unless the user asks to add it.
- Read the report's `sideObservations` field first; it often carries the exact server, request path, or line numbers the summary line omits.

## Leave and follow-ups

- Add a `*Leave:*` line after the ticket blocks for a leave day or an upcoming leave: the date, the fact the user gave, and the follow-up. Keep medical detail to what the user disclosed; never add symptoms, a diagnosis, or a doctor's advice.
- Put the follow-up action in Next under `Me`.
- "Follow up" is ambiguous. In a leave or message context it can mean a message to a person, not a task entry. When the user says "follow up message", draft the message; when they then say to include it in the report, add the leave line and the Next action. Do not substitute a task entry for the message.

## Weeks, leave days, missing days

- "Work report for this week" = one full block per working day, in order; reflect the attendance facts the user gives (who was off, who worked which days).
- Resolve a bare weekday ("friday") against the LIVE clock with `date`: this chat spans weeks, so the conversation's start date is not the target day. A request sent just after midnight means the shift that just ended.
- A leave day still gets a block when the teammate worked: `Mobeen: leave day.` as the body, then `***` and the teammate section. Never turn stray commits on a leave day into work bullets.
- Main body = Mobeen's side (plans, reviews, findings, Jira moves, releases, docs). Team section = the teammate's execution (implementation, testing, pushes). The same ticket legitimately appears in both: Mobeen planned or reviewed it, the teammate built and tested it.
- Check the store first with `list_reports(from=..., to=...)`; a date can hold several project reports (e.g. `mtmpro` plus `mobile-app`/GMI) and one day's block merges them all, grouped by project; `get_report(date)` alone returns only the first project, so fetch each. A day, or one project within a day, with no entry gets rebuilt, and the sources are named in chat per day.
- A tracker row proves time, not ticket-level work. When only a tracker row exists for a project, keep Mobeen's block at the level the row supports and take ticket detail from the teammate's EOD. Never promote a teammate's ticket bullets into Mobeen's main body.
- Jira assignee is ownership, not evidence of the day's worker: a teammate can implement a ticket assigned to Mobeen. When an EOD's owner is ambiguous, the tracker row is the tie-breaker: if Mobeen's MTMPRO cell for that day is blank, the MTMPRO detail belongs in the teammate's section. State the attribution check in chat.
- Usama works *as* Mobeen: he posts to Slack, Jira and the board under Mobeen's identity (user, 2026-11-12). A merge, comment or board move shown under Mobeen's name is NOT evidence Mobeen did it. The teammate's EOD is the tie-breaker; keep the claim in the section of whoever the EOD names, and never book the minutes to Mobeen's untracked column on the strength of a Slack post alone.
- Ask for teammate day-end reports when the week needs their sections; condense their text to single-line bullets, keep their facts.
- If the user dictates per-day hour figures with the request (sometimes "check the tracker" for a day), read that day from TopTracker / column D before using a number, and confirm where the figures should land (sheet vs report).

## Data Sources

- **User's work (Mobeen):** Read from the work-reports MCP (`mcp__work_reports__get_report`). If no entry exists for a date, or for one project on a date (verify with `list_reports`), rebuild from: the meta repo `~/Dev/mtmPro` (plans, findings, Jira records; authored as Mobeen), its dated draft files, `git log` in `mtmproBackend` / `mtmproFrontend`, and the trackers. State in chat which day was reconstructed and from what. Attribution caveat: in the mtmpro code repos Mobeen and Usama BOTH commit as the shared `Mohsin` identity, so commit authors cannot distinguish them; never book one person's implementation or testing from git alone. Full recipe: `references/rebuild-missing-days.md`.
- **GMI ticket lookup:** `TECH-*` IDs are Linear issues; resolve the title and status with `mcp__linear__get_issue`. Do not search the MTMPRO Jira for `TECH-*`.
- **GMI sheet moves:** a manual move can leave the Kimai timestamp on the original day while the sheet carries the hours on the report day. When an `*Hours:*` line is used, take it from the sheet total and name the move in the source note; never present the Kimai day total as the report total.
- **GMI / mobile-app work:** Kimai API (`~/.hermes/config/kimai.json`); day entries carry the full work description (ticket prefix `TECH-`). Hours = sum(duration seconds)/3600. Add as its own `*TECH-…*` block with a `• Logged: X.XXh (Kimai)` bullet when the user asks for GMI details. When sessions were re-booked onto the report day (see the bot-ops booking protocol), the Logged figure uses the re-booked total so report and sheet agree. When the day has Kimai hours but no work-reports entry, the block carries only the Kimai `description` label plus the Logged bullet: never invent implementation bullets from hours alone.
- **Team EOD:** From the teammate's day-end reports relayed by the user in chat; ask for them when a report needs their sections. Condense to single-line bullets and keep their facts. Before calling an EOD missing, run `session_search` newest-first bounded to that day: it often arrives in a different session, especially when the report is requested after midnight. If it is truly absent, omit the section and flag it in chat.
- **Hours:** From the Google Sheet if needed. Read the day row (day N = row N+2) and map columns from the LIVE header row in the same call; the tab has been re-columned more than once, so a remembered letter layout is a wrong answer. A figure read only to verify the day stays in chat: the paste block carries `*Hours:*` only under the rule above.

### Pulling a day's data (verified order)

1. `list_reports(from=D, to=D)` first: it returns every project report for that date, while `get_report(D)` returns only the first match. Then fetch each with `get_report(D, project)`. If a payload is collapsed or too large to read reliably, run the `work-reports` skill's `scripts/extract_reports.py` against `~/Dev/work-reports/db.json`; never reconstruct the contents from memory.
2. Kimai: `GET <url>/api/timesheets?begin=<D>T00:00:00&end=<D+1>T03:00:00&size=200` with `X-AUTH-USER` and `X-AUTH-TOKEN` from `~/.hermes/config/kimai.json`, plus a `User-Agent`. The body is a bare array, `duration` is seconds, and `activity` is an integer ID: the `TECH-` label lives in `description`. A null `end` is a running entry, so that day's total is unknown, never zero.
3. Sheet: day N is row N+2; read the live header row before trusting any column letter.

## Example

```
📋 *Work Report - Sep 11 (Friday)*

*MTMPRO-3111*: Alterations stuck in Draft status
• Fix implemented on both repos (backend + frontend)
• Backend: store-scoped status-id resolver wired into every workflow write path + global-admin repair endpoint
• Frontend: Edit Ticket modal moved onto corrected call
• Verification: 146 tests green, end-to-end probe passes on fix, fails on pre-fix commit
• Status: Not pushed, not deployed

*MTMPRO-3120*: Order number showing bare "2"
• Root cause confirmed: fabric attributes leak into garment number field
• Backend write guard, drawer write-back guard, reader ordering fixes, repair script (dry-run), all implemented
• Pending: false-positive refinement, guard unit tests, Fable review
• Status: Not committed

***

*Usama (Sep 11 EOD):*
• Researched Dizio ticket requirements
• Discussed completed MTMPRO ticket with Mobeen in meeting
• Implementation plan ready, scheduled for Monday

***

*Next:* Finish 3111 local UI walkthrough → cherry-pick to dev. Complete 3120 guard specs + Fable review.
```
