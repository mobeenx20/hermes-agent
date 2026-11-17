# TopTracker missing-hours diagnosis: worked example (2026-08-12)

Context: user asked to fill Aug 12 in the worked-hours sheet, then corrected
mid-turn: "2 hrs are missing from top tracker". Sheet column D had 7.24 after
`sync_toptracker`. DB inspection showed 7.24 was complete; the "missing" time
was never recorded (timer gap), so it was logged as MTMPRO UNTRACKED.

## Source of truth checks, in order

1. Sync result vs DB total. `sync_toptracker` wrote 7.24; direct query:
   ```sql
   SELECT ROUND(SUM(ap.endTime - ap.startTime) / 1000.0 / 3600.0, 2)
   FROM "mobeen.ahmed@contrivesolution.com_activity" ap
   LEFT JOIN "mobeen.ahmed@contrivesolution.com_project_list_cache" p
     ON ap.projectId = p.id
   WHERE date(ap.startTime/1000, 'unixepoch', 'localtime') = '2026-08-12'
     AND ap.endTime > ap.startTime AND ap.projectId = 1182888;
   ```
   → 7.24. Sheet and DB agree; the data itself is short, not the sync.

2. Offline/unsynced rows (none in this case):
   ```sql
   SELECT * FROM "mobeen.ahmed@contrivesolution.com_activity"
   WHERE offlineType > 0 OR lastSynced IS NULL OR lastSynced = 0;
   ```
   Facts: `_blobs` holds screenshots only (schema: id, blob); it never
   queues pending time. `_work_log` (projectId, lastWorked, workedSeconds)
   when populated shows stale cumulative data: lastWorked epoch decodes to
   1970-01-21, workedSeconds 2.42 for project 1182888 — not per-day.

3. Raw rows for the day (the gap finder):
   ```sql
   SELECT p.name, datetime(startTime/1000,'unixepoch','localtime'),
          datetime(endTime/1000,'unixepoch','localtime'),
          ROUND((endTime-startTime)/1000.0/3600.0,2)
   FROM "mobeen.ahmed@contrivesolution.com_activity" ap
   LEFT JOIN "mobeen.ahmed@contrivesolution.com_project_list_cache" p
     ON ap.projectId = p.id
   WHERE date(ap.startTime/1000,'unixepoch','localtime') BETWEEN '2026-08-12' AND '2026-08-13'
   ORDER BY startTime;
   ```
   Result (project 1182888 = AI Resource Management = MTMPRO):
   ```
   14:17:42 -> 20:12:57   5.92
   22:46:02 -> 23:10:38   0.41
   23:10:46 -> 00:05:27   0.91   <- overnight session, start-date attribution:
                                    counts to Aug 12 even though it ends Aug 13
   ```
   Total 7.24. Visible untracked window: 20:12:57 -> 22:45:59 = 2h33m
   (plus a 1-second "Dizo" blip at 22:45:59, a project-switch artifact,
   0.0h, ignore). The gap length matched the user's "2 hrs" claim — the
   timer was stopped/forgotten during that stretch.

## Fix

`add_mtmpro_entry(date="2026-08-12", hours=2)` → column E (MTMPRO
UNTRACKED), E was empty so E = 2. Final row: C=1 (Dizio), D=7.24 (tracked),
E=2 (untracked; pre-restructure, today D), H=6.88 (GMI via kimai_sync.py --date 2026-08-12).
(The tool no longer exists on this machine; the same result today is a
single-cell USER_ENTERED write `E14 = 2`.)

## Rules that held

- Never write manual hours into column C (MTMPRO TRACKED); untracked goes
  to D as a single-cell write (sum into the existing value, never overwrite).
- Precedent pair: Aug 6 = 8.69 tracked + 2 untracked; Aug 12 = 7.24 + 2.
- If the user can locate the time on another device (phone app, web), the
  desktop DB may still lack it; re-sync after the app syncs, or adjust the
  untracked figure with the user's input.
