# ResourceInn attendance extraction (Contrive)

Attendance/leave system for the hours shortfall audit. Gathered 2026-08-12.

## The system

- resourceinn.com, Angular SPA, user Mobeen Ahmed CS-01011 (Frontend Dev).
- NO export: a Filters drawer, a Refresh button, and one table.
- Timesheet table columns: Date | Time Slot | Checked In | Checkin Status |
  Checked Out | Checkout Status | Expected Hours (9h shift 11:00-20:00) |
  Worked Hours | Approved Overtime | Break Duration | Shift Worked Hours |
  Actions (View link per row).
- Attendance Score badge on the dashboard (e.g. 65%).

## Status codes (per day, can combine)

- P Present, M Missing, A Absent, S Short Duration, D Day Off, R Rest Days,
  L Full Leave, SL Short Leave, W Work From Home.
- Combinations appear in the Date cell: "W P" = WFH present, "W P SL" = WFH
  present short leave.

## Cross-referencing with notifications

- RINN notification emails come from people@contrivesolution.com with
  subjects "Absent Notification YYYY-MM-DD" / "Unapproved WFH Notification".
  They flag disputed days; verify via work reports (work-reports MCP) before
  acting or replying.
- Proven false positives 2026: Jul 8 (TECH-8555, PR #103 merged), Jul 13
  (TECH-7488 + 6.2.0 release prep), Jan 26 and Feb 16 (corrected after user
  contested with RINN screenshots).
- Compensation evidence = any flagged/leave/WFH/weekend day with tracked
  hours > 0 in Kimai, TopTracker, or the sheet.

## Extraction guidance (what actually worked)

- FASTEST: ask the user to click the table, cmd+A, cmd+C, paste into chat.
  The table renders lazily, so scroll to the bottom first if selection is
  partial.
- Automating with computer_use: bind by pid+window_id to the Chrome window
  titled "Timesheet - Resourceinn" (list_windows shows it), capture in ax
  mode. Open the Filters drawer (Filters button) and use the Attendance
  Status filter to shrink the table to L/SL/A/W days before reading rows.
- Pitfalls seen: typing into the Angular date fields delivered 0 characters
  even in foreground mode; set_value on the date field did not stick; the
  datepicker opens on click and must be closed (CLOSE button) before
  continuing. Full-tree AX captures are huge (1600+ elements); scroll-based
  extraction burns context fast, prefer the status filter or user paste.

## Weekend GMI hours found (Kimai, compensation credits)

Mar 15 2.33h, Apr 12 1.66h, May 3 2.54h, Jun 7 2.10h.
