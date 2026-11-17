#!/usr/bin/env python3
"""Weekly TopTracker -> sheet sync wrapper.

Runs fill_hours.py for every day of a week. fill_hours.py is the single writer
for column C (MTMPRO tracked) and column H (GMI). The legacy
toptracker_sync.py is retired because it targets column D.

  toptracker_weekly_sync.py            # current week (Mon-Fri), no force
  toptracker_weekly_sync.py --last     # previous week (Mon-Sun)
  toptracker_weekly_sync.py --force    # overwrite already-filled cells
  toptracker_weekly_sync.py --dry-run  # report only, no writes

Exit 1 when any day errors or a write verification fails.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Karachi")
except Exception:  # pragma: no cover - tzdata missing
    from datetime import timezone
    TZ = timezone(timedelta(hours=5))

FILL = os.path.expanduser("~/.hermes/scripts/fill_hours.py")
PY = os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python")


def week_dates(last=False):
    today = datetime.now(TZ).date()
    monday = today - timedelta(days=today.weekday())
    if last:
        monday -= timedelta(days=7)
    # Mon-Sun for the catch-up; Mon-Fri for the in-week run.
    span = range(7) if last else range(5)
    return [monday + timedelta(days=i) for i in span]


def run_day(d, force=False, dry=False):
    cmd = [PY, FILL, "--date", d.isoformat(), "--no-summary"]
    if force:
        cmd.append("--force")
    if dry:
        cmd.append("--dry-run")
        return {"date": d.isoformat(), "dry_run": True, "cmd": " ".join(cmd)}
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {"date": d.isoformat(), "exit": 1, "stderr": "timeout"}
    out = (p.stdout or "").strip()
    info = {}
    lines = out.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("{"):
            try:
                info = json.loads("\n".join(lines[i:]))
            except Exception:
                info = {}
            break
    info["exit"] = p.returncode
    info["written"] = bool(info.get("planned_writes")) and not info.get("dry_run")
    info["hours"] = info.get("toptracker")
    if p.returncode != 0:
        info["stderr"] = (p.stderr or "").strip()[:300]
    return info


def refresh_summaries(days):
    months = sorted({(d.year, d.month) for d in days})
    for year, month in months:
        last = max(d for d in days if d.year == year and d.month == month)
        cmd = [PY, FILL, "--summary-only", "--date", last.isoformat()]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            print("summary refresh timed out for %04d-%02d" % (year, month))
            return False
        if p.returncode != 0:
            print("summary refresh failed for %04d-%02d:" % (year, month))
            print((p.stderr or p.stdout or "").strip()[:800])
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", action="store_true", help="previous week, Mon-Sun")
    ap.add_argument("--force", action="store_true", help="overwrite filled cells")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    days = week_dates(last=a.last)
    print("TopTracker sync: %s to %s%s" % (
        days[0].isoformat(), days[-1].isoformat(),
        " (forced)" if a.force else ""))
    results = [run_day(d, force=a.force, dry=a.dry_run) for d in days]

    wrote = [r for r in results if r.get("written")]
    skipped = [r for r in results if r.get("skipped")]
    failed = [r for r in results if r.get("exit") not in (0, None)
              or r.get("verified") is False]
    no_change = [r for r in results if not r.get("dry_run")
                 and not r.get("written") and not r.get("skipped")
                 and r.get("exit") in (0, None) and r.get("verified") is not False]

    for r in results:
        if r.get("dry_run"):
            state = "would run"
        elif r.get("written"):
            state = "wrote %sh" % r.get("hours")
        elif r.get("skipped"):
            state = "skipped: %s" % r.get("reason", "unknown")
        elif r.get("exit") not in (0, None) or r.get("verified") is False:
            state = "FAILED: %s" % (r.get("stderr") or "exit %s" % r.get("exit"))
        else:
            notes = r.get("notes") or []
            state = "no change" + (": " + notes[0] if notes else "")
        print("  %s  %s" % (r.get("date"), state))

    if not a.dry_run and not failed:
        if not refresh_summaries(days):
            failed.append({"date": "summary", "exit": 1})

    print("\nwrote %d, no change %d, skipped %d, failed %d"
          % (len(wrote), len(no_change), len(skipped), len(failed)))
    if failed:
        print(json.dumps(failed, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
