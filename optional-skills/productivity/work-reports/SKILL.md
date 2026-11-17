---
name: work-reports
description: Operate the work-reports MCP (daily reports, ticket lookup, plan/discovery).
---

# Work-Reports MCP skill

Operate the local work-reports MCP server (`~/Dev/work-reports/src/mcp-server.js`) exposed as `mcp__work_reports__*` tools by Hermes. Handles daily structured work reports: one report per day per project, each with a shareable summary plus per-ticket detail.

## When to load

Load whenever the user asks about a work report, ticket status, daily summary, work hours context, or any task involving `mcp__work_reports__*` tools. Also load when the user asks "what did I work on" for a specific date or ticket.

## Architecture

- **MCP server:** `node ~/Dev/work-reports/src/mcp-server.js` (stdio, 12 tools).
- **Data store:** `~/Dev/work-reports/db.json` (LowDB). Sorted newest-first.
- **CLI companion:** `wr` CLI at `~/Dev/work-reports/src/cli.js` (not normally used directly; the MCP is the primary interface).

## Project directory mapping (cache)

The `references/projects.json` file maps project names to their repo paths on disk. This is the single source of truth; load it at the start of any work-reports session. Do NOT hardcode project paths in your responses: always read the cache file.

Two categories of reports exist:

1. **Code projects** - have a repo on disk, tickets with `files[]`/`branch`/`commits`. These go in the cache with their repo path. File and plan resolution applies.
2. **Non-project tasks** - tooling, environment fixes, configuration work that doesn't belong to any code repo. These use a bucket project name (e.g., `dev-environment`), have no tickets, and no repo path. File resolution does not apply.

When a new project appears in `report_stats`, check its reports: if tickets have code artifacts (`files[]`, `branch`, `commits`), it's a code project and needs a cache entry. If reports are summary-only with no tickets, it's a non-project bucket and no cache entry is needed.

### Resolving a file path from a ticket

Reports store file paths relative to the project root (e.g., `src/components/UI/GmiScannerFab.vue`). To open or read such a file:

1. Get the report to extract the `project` field.
2. Look up the project's repo path from `references/projects.json`.
3. Join `<repo-path>/<file-path>` to get the absolute path.
4. Use `read_file` to display it, or `terminal` to open it in the user's editor.

Example: ticket has `project: "mobile-app"`, file `src/components/UI/GmiScannerFab.vue` → `~/Dev/mobile-app/src/components/UI/GmiScannerFab.vue`.

This works for plan files too: a report may reference `.claude/plans/plan-tech-8644-*.md`. Resolve relative to the project root, not the work-reports repo.

## Data model

Each report has:
- `id` (uuid) - primary key for updates/deletes
- `date` (YYYY-MM-DD) - used for lookup via `get_report`/`view_report`
- `project` (string) - maps to a repo path via `references/projects.json`
- `summary` (string) - shareable daily summary
- `tickets[]` - array of ticket objects
- `memoryUpdates` (string) - memory changes from that day
- `openNext` (string) - open items and next steps
- `createdAt` (ISO timestamp)

Each ticket:
- `ticketId` (string) - e.g., `TECH-8644`
- `title` (string)
- `status` (string)
- `branch` (string)
- `commits[]` (string array)
- `implementation` (string) - detailed implementation notes
- `blockers` (string) - any blockers
- `files[]` (string array) - relative paths from the project root
- `verification` (string) - verification results
- `linearUpdates` (string) - Linear/Jira activity
- `sideObservations` (string) - out-of-scope findings. First place to read when the user asks what a side finding means; it often carries the exact server, request path, or line numbers the summary omits.

## MCP tools (all 12)

### Read operations

| Tool | Parameters | Returns |
|------|-----------|---------|
| `list_reports` | `project?`, `from?`, `to?`, `limit?` | Compact summaries array |
| `get_report` | `date` (required), `project?` | Full report JSON |
| `view_report` | `date` (required), `project?` | Formatted plain text |
| `search_reports_by_ticket` | `ticketId` (required) | Reports containing that ticket |
| `report_stats` | `project?` | Aggregate stats, including `projects` array |
| `export_report_to_text` | `date`, `project?` | Writes `.txt` to exports/ |
| `export_range_to_text` | `from`, `to`, `project?`, `filename?` | Combined `.txt` to exports/ |

### Write operations

| Tool | Parameters | Notes |
|------|-----------|-------|
| `add_report` | `date` (required), `project` (required), `summary?`, `tickets?`, `memoryUpdates?`, `openNext?` | Creates a new report. If a report for that date+project already exists, use `update_report` instead. Always pass `project` explicitly. |
| `update_report` | `id` (required), plus any fields to change | Pass only the fields that changed. `tickets`, `openNext`, and `summary` are replaced wholesale: to append, re-send the full existing value plus the new item. |
| `delete_report` | `id` (required) | Permanent. |
| `open_report_in_editor` | `date`, `project?` | Exports to JSON, opens in VS Code. |
| `reimport_report` | `filePath` | Reimports after manual editing. |

### Tool behaviors to know

- `get_report` returns the full JSON object. Use this when you need the `id` field for an `update_report` call.
- **Collapsed or oversized payloads:** `get_report` can return more text than stays visible in a long session. Do not re-call it and guess. Run `python3 <skill-dir>/scripts/extract_reports.py --from YYYY-MM-DD --to YYYY-MM-DD [--project NAME] --out <scratch>/reports.md` against the same LowDB store (`~/Dev/work-reports/db.json`). Read that file in chunks. The script is read-only; all writes still go through `add_report` / `update_report`.
- `search_reports_by_ticket` does an exact ticket ID match across all dates AND all projects. If it returns "No reports found", the ticket may be referenced in a plan file in one of the known project repos instead of in the report store. Load the project cache, then check each project's `.claude/plans/` and `.claude/followups/` before concluding the ticket does not exist.
- `update_report` requires the report `id` (uuid), NOT the date. Always call `get_report` first to get the `id` if you don't have it.
- `add_report` creates net-new reports. To add/modify tickets in an existing report, use `update_report`.
- `view_report` produces a formatted plain-text output suitable for direct display to the user.
- `report_stats` returns a `projects` array listing all known project names. Use this to discover projects and validate project names. If a project is missing from the cache, add it.

## Common workflows

### 1. Look up today's report (or a specific date)

```
get_report(date='2026-07-09')
```
If the user didn't specify a project, try without `project` first (returns first match). If the date has reports for multiple projects, pass `project` to disambiguate. If no report exists for that date, `list_reports(limit=5)` to see recent dates across all projects.

### 2. Find all reports for a specific ticket (across all projects)

```
search_reports_by_ticket(ticketId='TECH-8644')
```

This searches all projects, all dates. If empty, load the project cache and search each project's `.claude/` directories for plan files matching the ticket ID. If found, read the plan file and present it. Offer to add/update the report.

### 3. Open a file referenced in a report

When the user says "open the file from the TECH-8644 report":

1. `search_reports_by_ticket(ticketId='TECH-8644')` or `get_report(...)` to get the report.
2. Extract `project` from the report (e.g., `mobile-app`).
3. Read `references/projects.json` from this skill to get the repo path (e.g., `~/Dev/mobile-app`).
4. Extract the file path from the ticket's `files[]` array (these are relative to the project root).
5. Construct the absolute path: `<repo-path>/<relative-file-path>`.
6. `read_file(path='<absolute-path>')` to display it.

For plan files referenced in the `implementation` or `openNext` fields (e.g., `.claude/plans/plan-tech-8644-*.md`), use the same project-root resolution.

### 4. Add a new ticket to an existing report

First get the report to find its `id`:
```
get_report(date='2026-07-09', project='mobile-app')
```
Then update with the full tickets array (existing + new):
```
update_report(id='<uuid>', tickets=[...existing..., ...new...], summary='<merged summary>')
```

Pass the FULL `tickets` array, not just the new one, and a merged `summary` that covers all tickets. The MCP tool replaces, it does not append.

### 5. Create a brand-new report for a date

```
add_report(date='2026-07-10', project='mobile-app', summary='...', tickets=[...], openNext='...')
```

Always pass `project` explicitly. Never assume a default.

### 6. Find what the user worked on in a date range

```
list_reports(from='2026-07-01', to='2026-07-09')
```
To scope to one project, add `project='mobile-app'`. For weekly summaries, follow with:
```
export_range_to_text(from='2026-07-01', to='2026-07-07')
```

### 7. Discover which project a ticket belongs to

When the user says "tell me about ticket X" without naming the project:
1. `search_reports_by_ticket(ticketId='X')` - searches all projects
2. If empty, load the project cache, search each non-null project's `.claude/plans/` for matching files
3. If still nothing, ask the user which project the ticket belongs to

### 8. List all projects and recent activity

```
report_stats()
```
Returns total reports, tickets, blocked count, date range, and the full `projects` array. Cross-reference with `references/projects.json`; if any project appears in stats but not in the cache, ask the user for its repo path and update the cache.

### 9. Verify work activity on a specific date

When the user asks whether they worked on a given date (e.g. to cross-reference an absent notification from HR or attendance):

1. Call `get_report(date='YYYY-MM-DD', project='mobile-app')`. If no report is returned, try without `project` first, or call `list_reports(from='YYYY-MM-DD', to='YYYY-MM-DD')` to find all reports across any project for that date.
2. If a report exists, read the `summary` and `tickets` array. Tickets with commits, PRs, merged branches, or releases confirm active work.
3. Present the findings clearly. If the report shows work, the absent notification is a false positive and no RINN (Remote In/Out Notification) is needed.
4. Only advise submitting a RINN if no report exists or the report confirms no activity for that day.

This pairs with the absent notification verification section in the `google-workspace-mcp` skill's attendance workflow.

## Pitfalls

1. **No default project.** Always pass `project` explicitly in `add_report` and prefer to pass it in queries. If the user doesn't name a project, try `get_report(date)` without project first, then use `report_stats` to discover options.

2. **`update_report` replaces, does not merge.** Passing a `tickets` array replaces the entire array; `openNext` and `summary` are replaced wholesale too. To add one follow-up, re-send the full existing `openNext` list plus the new line, or the rest is lost. Always include existing tickets you want to keep.

3. **`update_report` uses `id`, not `date`.** Always call `get_report` first to get the `id` uuid.

4. **Ticket search can miss real work.** `search_reports_by_ticket` only searches the report store `db.json`. If work was planned/spec'd but the report wasn't yet written, the ticket exists only in the project's `.claude/plans/` directory. Always fall back to a project plan search (using the project cache for paths) before reporting "not found."

5. **File paths in tickets are relative to the project root, not the work-reports root.** Always resolve them via `references/projects.json`: `<repo-path>/<file-path>`. Plan file references (`.claude/plans/...`) follow the same rule.

6. **`view_report` vs `get_report`:** use `view_report` when presenting to the user (formatted text). Use `get_report` when you need the machine-readable JSON.

7. **Don't overwrite the summary blindly.** When adding a ticket to an existing report, merge summaries. Use `get_report` first, then construct a combined summary for `update_report`.

8. **Multi-project awareness.** A single date can have reports for multiple projects. When searching by date alone, be prepared for `get_report` to return the first match from any project.

9. **Cache staleness.** `references/projects.json` is durable but not self-updating. When `report_stats` shows a project not in the cache, auto-discover its path before asking the user:

    a. Check `~/Dev/<project-name>/` first (the convention for most projects).
    b. If not found, search `~/Dev/`, `~/Documents/`, `~/Projects/` for directories matching the project name.
    c. If found, update `references/projects.json` with the discovered path and continue.
    d. Only if discovery fails, ask the user where the project lives.

    Same process when a `null` value exists in the cache: try discovery once per session, then ask if it keeps failing. Always `skill_manage(action='write_file', ...)` to persist the updated cache immediately.
