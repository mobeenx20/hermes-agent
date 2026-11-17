#!/usr/bin/env python3
"""fill_hours.py - fill one day's tracker hours into the monthly worked-hours tab.

One process does the whole job that used to take a dozen manual steps:
reads TopTracker (column C), reads Kimai (column H), writes both cells in one
batch, then refreshes the weekly summary block's targets.

  fill_hours.py                      # today
  fill_hours.py --date 2026-09-22
  fill_hours.py --date 2026-09-22 --force
  fill_hours.py --date 2026-09-22 --dry-run
  fill_hours.py --summary-only       # just refresh the weekly block
  fill_hours.py --no-summary         # cells only

Column policy (see the work-hours-tracking skill):
  C  MTMPRO TRACKED    <- TopTracker local DB. Written only when blank; an
                          existing value is kept unless --force, and a stale
                          partial is flagged with the closed tracker total.
  H  GMI               <- Kimai API, split at midnight, 2dp. A stale partial
                          lower than the split-aware closed total is auto-
                          repaired and noted; otherwise --force is required.
  D, E, F, G           <- NOT touched. D is untracked MTMPRO, E is the
                          Broadcasting Platform, F is labels/notes, G is other
                          hours. Those are judgement calls that belong to the
                          user, not to a tracker.

A zero reading never clears an existing cell: the TopTracker local DB is a
rolling cache, so "0 today" usually means "purged", not "worked nothing".
"""

import os
import sys
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

# --- interpreter bootstrap -------------------------------------------------
# google-api-python-client lives in the Hermes venv. Cron runs this with a bare
# interpreter, so re-exec into one that actually has the libs.

_REEXEC = "FILL_HOURS_REEXEC"


def _ensure_google_libs():
    try:
        import googleapiclient  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get(_REEXEC):
        sys.exit("error: google-api-python-client not found in any interpreter.")

    import subprocess

    home = os.path.expanduser("~")
    candidates = (
        os.path.join(home, ".hermes", "hermes-agent", "venv", "bin", "python"),
        "/usr/bin/python3",
        "/usr/local/bin/python3",
    )
    for cand in candidates:
        if not os.path.exists(cand):
            continue
        if os.path.realpath(cand) == os.path.realpath(sys.executable):
            continue
        probe = subprocess.run([cand, "-c", "import googleapiclient"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            os.environ[_REEXEC] = "1"
            os.execv(cand, [cand, os.path.abspath(__file__)] + sys.argv[1:])

    sys.exit("error: google-api-python-client not found in any interpreter.")


_ensure_google_libs()

import argparse  # noqa: E402
import calendar  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from datetime import date, datetime, time, timedelta, timezone  # noqa: E402

try:  # noqa: E402
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Karachi")
except Exception:  # pragma: no cover - tzdata missing
    LOCAL_TZ = timezone(timedelta(hours=5))

from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

# --- config ---------------------------------------------------------------

SPREADSHEET_ID = "REPLACE_SPREADSHEET_ID"
TOKEN_PATH = os.path.expanduser("~/.local/share/google-mcp/tokens.json")
CREDS_PATH = os.path.expanduser("~/.config/google-mcp/credentials.json")

TOPTRACKER_DB = os.path.expanduser("~/.local/share/TopTracker/TopTracker.db")
TOPTRACKER_USER = "mobeen.ahmed@contrivesolution.com"
MTMPRO_PROJECT_ID = 1182888

KIMAI_CONFIG = os.path.expanduser("~/.hermes/config/kimai.json")

TRACKED_COL, GMI_COL = "C", "H"
FIRST_DAY_ROW = 3  # date N lives at row N + 2

WORKDAY_TARGET = 8
# date -> target hours, for official holidays and half days. Weekend = 0.
DAY_TARGET_OVERRIDES = {
    "2026-10-16": 4,  # Friday, half day off (told 2026-10-19)
}

# Client hours cut (Oct 2026): from Mon 2026-10-12 Mobeen's week is capped at
# 32h (4 days x 8h). Weeks starting on/after this date are clamped to the cap,
# so the weekly EXTRA/SHORT and the month target follow the reduced budget.
# Keep in sync with build_month_tab.py.
WEEKLY_TARGET_CAP_FROM = date(2026, 10, 12)
# Personal weekly target stays 40h. The 32h figure is Mobeen's MTMPRO
# allotment and applies only while Solat handles the 8h of testing.
WEEKLY_TARGET_CAP = 40

MONTHS = {m: i for i, m in enumerate(calendar.month_abbr) if m}


def today_local() -> date:
    return datetime.now(LOCAL_TZ).date()


def _day_bounds_ms(day: date) -> tuple[int, int]:
    start = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _numbers_equal(got, expected, tol=0.011) -> bool:
    try:
        return abs(float(got) - float(expected)) <= tol
    except (TypeError, ValueError):
        return False


# --- google auth ----------------------------------------------------------


def _get_creds():
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    with open(CREDS_PATH) as f:
        cd = json.load(f)
    info = cd.get("installed", cd.get("web", {}))
    creds = Credentials(
        token=td.get("access_token"),
        refresh_token=td.get("refresh_token"),
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info.get("client_id"),
        client_secret=info.get("client_secret"),
        scopes=td.get("scope", "https://www.googleapis.com/auth/spreadsheets").split(),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        td["access_token"] = creds.token
        td["expiry_date"] = creds.expiry.timestamp() * 1000 if creds.expiry else None
        with open(TOKEN_PATH, "w") as f:
            json.dump(td, f)
    return creds


def _sheets():
    return build("sheets", "v4", credentials=_get_creds())


# --- sources --------------------------------------------------------------


def read_toptracker_hours(day: date):
    """MTMPRO tracked hours for `day`, or None when the rolling DB cannot say.

    Returns None (not 0.0) when the local activity table holds no rows for the
    day at all: the DB purges, so an empty day is "unknown", never "zero".
    """
    if not os.path.exists(TOPTRACKER_DB):
        return None
    activity = '"%s_activity"' % TOPTRACKER_USER
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % TOPTRACKER_DB, uri=True)
    except sqlite3.Error:
        return None
    try:
        start_ms, end_ms = _day_bounds_ms(day)
        where = ("startTime >= ? AND startTime < ? AND projectId = ? "
                 "AND endTime > startTime")
        cur = conn.execute(
            "SELECT COUNT(*) FROM {t} WHERE {w}".format(t=activity, w=where),
            (start_ms, end_ms, MTMPRO_PROJECT_ID),
        )
        if not cur.fetchone()[0]:
            return None
        row = conn.execute(
            "SELECT ROUND(SUM(endTime - startTime) / 1000.0 / 3600.0, 2) "
            "FROM {t} WHERE {w}".format(t=activity, w=where),
            (start_ms, end_ms, MTMPRO_PROJECT_ID),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None or row[0] is None:
        return None
    return float(row[0])


def _kimai_entries(begin_day: date, end_day: date):
    """Raw Kimai entries for the GMI project whose begin falls in the window."""
    with open(KIMAI_CONFIG) as f:
        cfg = json.load(f)
    url = ("%s/api/timesheets?project=%s&begin=%sT00:00:00&end=%sT23:59:59&size=200"
           % (cfg["url"].rstrip("/"), cfg.get("projectId", 1),
              begin_day.isoformat(), end_day.isoformat()))
    req = urllib.request.Request(url, headers={
        "X-AUTH-USER": cfg["username"],
        "X-AUTH-TOKEN": cfg["token"],
        # Cloudflare error 1010 blocks the default Python-urllib signature
        # (began blocking between 2026-10-20 15:08 and 23:55); a browser UA
        # verified HTTP 200 on 2026-10-21 alongside the bare default 403.
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    })
    payload, last_err = None, None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            raise RuntimeError("Kimai HTTP %s: %s" % (e.code, e.read()[:200]))
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 + attempt * 2)
    if payload is None:
        raise RuntimeError("Kimai fetch failed after 3 attempts: %r" % (last_err,))
    entries = payload.get("data", payload) if isinstance(payload, dict) else payload
    return entries or []


def read_kimai(day: date):
    """(hours, entries) for the GMI project on `day`. Hours is the plain sum."""
    entries = _kimai_entries(day, day)
    total = sum(int(e.get("duration") or 0) for e in entries) / 3600.0
    return round(total, 2), entries


def _parse_local(ts):
    """Kimai ISO timestamp -> naive Asia/Karachi datetime."""
    text = str(ts or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=LOCAL_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ).replace(tzinfo=None)


def expected_gmi(day: date):
    """Split-aware GMI hours for `day`, matching Kimai's weekly view.

    Same-day entries count in full. An entry begun on `day` that crosses
    midnight counts only through 24:00; an entry begun the prior day that ends
    on `day` counts only from 00:00. Running entries (end null) are unknown and
    excluded. This is the value H must hold once the day is closed.
    """
    entries = _kimai_entries(day - timedelta(days=1), day)
    total_sec = 0.0
    for e in entries:
        if not e.get("end") or not e.get("duration"):
            continue
        b = _parse_local(e["begin"])
        en = _parse_local(e["end"])
        bdate, edate = b.date(), en.date()
        if bdate == day and edate == day:
            total_sec += int(e["duration"])
        elif bdate == day and edate > day:
            midnight = datetime.combine(day + timedelta(days=1), datetime.min.time())
            total_sec += max(0.0, (midnight - b).total_seconds())
        elif bdate < day and edate == day:
            midnight = datetime.combine(day, datetime.min.time())
            total_sec += max(0.0, (en - midnight).total_seconds())
        elif bdate < day and edate > day:
            total_sec += 86400.0
    return round(total_sec / 3600.0, 2)


# --- weekly summary block -------------------------------------------------


def _find_rows(values):
    """Locate the weekly block: (title_row, header_row, [week_rows], total_row)."""
    title = header = total = None
    weeks = []
    for i, row in enumerate(values):
        a = str(row[0] if row else "").strip()
        if a.upper() == "WEEKLY SUMMARY":
            title = i
        elif title is not None and header is None and i == title + 1:
            header = i
        elif header is not None and total is None and a.upper().startswith("MONTH TOTAL"):
            total = i
        elif header is not None and total is None and re.match(r"^Week\s+\d+", a):
            weeks.append(i)
    return title, header, weeks, total


def _day_target(d: date) -> int:
    if d.isoformat() in DAY_TARGET_OVERRIDES:
        return DAY_TARGET_OVERRIDES[d.isoformat()]
    return 0 if d.weekday() >= 5 else WORKDAY_TARGET


def _week_dates(period: str, year: int):
    """'Sep 21 - Sep 27' -> [date, ...]. Handles a month rollover."""
    m = re.match(r"^\s*([A-Za-z]{3})\w*\s+(\d+)\s*-\s*([A-Za-z]{3})\w*\s+(\d+)\s*$", period or "")
    if not m:
        return []
    m1, d1, m2, d2 = MONTHS.get(m.group(1).title()), int(m.group(2)), MONTHS.get(m.group(3).title()), int(m.group(4))
    if not (m1 and m2):
        return []
    start = date(year, m1, d1)
    end = date(year, m2, d2)
    if end < start:
        end = date(year + 1, m2, d2)
    out, cur = [], start
    while cur <= end and len(out) < 14:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def refresh_summary(svc, tab, month, year, today, dry=False):
    """Recompute every EXTRA/SHORT target in the weekly block.

    Targets are the full leave-adjusted weekly mark: every started week counts
    all its in-month weekdays (8h, F-label "Leave"/"Holiday"/"Off" = 0, "Half day" = 4), and a
    week that has not started keeps a blank cell. Because the in-progress week
    carries its whole target, its EXTRA/SHORT reads negative until the week
    completes (user rule 2026-10-22). The block's SUM formulas are preserved;
    only the trailing target constant and the guard range are rewritten.
    """
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="%s!A1:I90" % tab,
        valueRenderOption="FORMATTED_VALUE").execute()
    values = resp.get("values", [])
    title, header, weeks, total = _find_rows(values)
    if title is None or not weeks or total is None:
        return {"refreshed": False, "reason": "weekly block not found"}

    writes, plan = [], []
    week_first_rows, week_last_rows = [], []
    week_targets = []
    for r in weeks:
        period = str((values[r][1] if len(values[r]) > 1 else "") or "")
        dates = _week_dates(period, year)
        in_month = [d for d in dates if d.month == month and d.year == year]
        if not in_month:
            continue
        week_first_rows.append(in_month[0].day + 2)
        week_last_rows.append(in_month[-1].day + 2)

        if in_month[0] > today:
            plan.append((period, None, "not started"))
            continue

        def day_hours(d):
            # Declared holidays win (DAY_TARGET_OVERRIDES); then the sheet's F
            # labels: "Leave" = 0h, "Half day" = 4h; weekends 0h; else 8h.
            if d.isoformat() in DAY_TARGET_OVERRIDES:
                return DAY_TARGET_OVERRIDES[d.isoformat()]
            if d.weekday() >= 5:
                return 0
            row = values[d.day + 1] if d.day + 1 < len(values) else []
            lbl = str(row[5] if len(row) > 5 else "").lower()
            if "half" in lbl:
                return 4
            if "leave" in lbl or "holiday" in lbl or "off" in lbl:
                return 0
            return 8
        target = sum(day_hours(d) for d in in_month)
        if in_month[0] >= WEEKLY_TARGET_CAP_FROM:
            target = min(target, WEEKLY_TARGET_CAP)
        week_targets.append(target)
        lo, hi = in_month[0].day + 2, in_month[-1].day + 2
        guard = "SUM(C{l}:C{h},D{l}:D{h},E{l}:E{h},G{l}:G{h},H{l}:H{h})".format(l=lo, h=hi)
        # Column I holds the leave-adjusted BASE TARGET; column J holds the live
        # EXTRA/SHORT delta against it (user layout, 2026-10-22).
        writes.append({"range": "%s!I%d" % (tab, r + 1), "values": [[target]]})
        writes.append({"range": "%s!J%d" % (tab, r + 1),
                       "values": [['=IF(%s=0,"",H%d-I%d)' % (guard, r + 1, r + 1)]]})
        plan.append((period, target, "week"))

    if week_first_rows:
        lo, hi = min(week_first_rows), max(week_last_rows)
        # Month base target = live sum of the started weeks' leave-adjusted
        # targets; EXTRA/SHORT = the delta against column I.
        month_target = sum(week_targets)
        guard = "SUM(C{l}:C{h},D{l}:D{h},E{l}:E{h},F{l}:F{h},G{l}:G{h})".format(
            l=min(r + 1 for r in weeks), h=max(r + 1 for r in weeks))
        sum_lo, sum_hi = weeks[0] + 1, weeks[-1] + 1
        writes.append({"range": "%s!I%d" % (tab, total + 1),
                       "values": [["=SUM(I%d:I%d)" % (sum_lo, sum_hi)]]})
        writes.append({"range": "%s!J%d" % (tab, total + 1),
                       "values": [['=IF(%s=0,"",H%d-I%d)' % (guard, total + 1, total + 1)]]})
        plan.append(("MONTH TOTAL", month_target, "month"))

    errors = []
    if not dry and writes:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"valueInputOption": "USER_ENTERED", "data": writes}).execute()
        for w in writes:
            got = svc.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=w["range"],
                valueRenderOption="FORMULA").execute().get("values", [[""]])[0][0]
            expected = w["values"][0][0]
            if isinstance(expected, str) and expected.startswith("="):
                ok = str(got).replace(" ", "") == expected.replace(" ", "")
            else:
                ok = _numbers_equal(got, expected)
            if not ok:
                errors.append("%s: planned %r, read %r" % (w["range"], expected, got))
    return {"refreshed": (not dry and bool(writes)),
            "dry_run": dry,
            "verified": not errors,
            "verification_errors": errors,
            "targets": [{"period": p, "target": t, "kind": k} for p, t, k in plan]}


# --- main -----------------------------------------------------------------


def fill(day, force=False, dry=False, summary=True):
    tab = "%s%s" % (calendar.month_name[day.month], str(day.year)[2:])
    row = day.day + 2
    result = {"date": day.isoformat(), "tab": tab, "row": row}

    if day > today_local():
        result.update(skipped=True, reason="date is in the future")
        return result

    tracked = read_toptracker_hours(day)
    gmi, entries = read_kimai(day)
    result["toptracker"] = tracked
    result["kimai_hours"] = gmi
    result["kimai_entries"] = len(entries)

    svc = _sheets()

    # refuse to write into a merged day row (a merge redirects the write silently)
    md = svc.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields="sheets(properties(title),merges)").execute()
    for sh in md["sheets"]:
        if sh["properties"]["title"] != tab:
            continue
        for m in sh.get("merges", []):
            if m["startRowIndex"] + 1 <= row <= m["endRowIndex"]:
                result.update(skipped=True, reason="row %d is merged (cols %d-%d)"
                              % (row, m["startColumnIndex"], m["endColumnIndex"]))
                return result

    before = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="%s!A%d:I%d" % (tab, row, row),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [[]])
    before = (before[0] if before else []) + [""] * 9
    existing_d = str(before[2]).strip()
    existing_h = str(before[7]).strip()

    writes, notes, planned = [], [], {}
    if tracked is None:
        notes.append("C: no closed MTMPRO rows for this day (purged, running, or none) - left as is")
    elif tracked == 0 and existing_d:
        notes.append("C: tracker reads 0 but cell holds %s - kept (never clear on a zero read)" % existing_d)
    elif existing_d and not force:
        try:
            existing_c_val = float(existing_d)
        except (TypeError, ValueError):
            existing_c_val = None
        if existing_c_val is not None and tracked > existing_c_val + 0.011:
            notes.append("C: STALE %s vs tracker %.2f (%.2fh missing) - pass --force or confirm"
                         % (existing_d, tracked, tracked - existing_c_val))
        else:
            notes.append("C: already %s - pass --force to overwrite" % existing_d)
    else:
        writes.append({"range": "%s!%s%d" % (tab, TRACKED_COL, row), "values": [[tracked]]})
        planned["C"] = tracked
        notes.append("C: %s -> %s%s" % (existing_d or "(blank)", tracked,
                                        " (forced)" if existing_d else ""))

    expected_h = expected_gmi(day)
    if expected_h == 0 and not entries:
        notes.append("H: no Kimai entries for this day")
    elif expected_h == 0:
        notes.append("H: %d entry/entries but all still running (duration 0) - not written" % len(entries))
    elif existing_h and not force:
        try:
            existing_val = float(existing_h)
        except (TypeError, ValueError):
            existing_val = None
        if existing_val is not None and expected_h > existing_val + 0.011:
            writes.append({"range": "%s!%s%d" % (tab, GMI_COL, row), "values": [[expected_h]]})
            planned["H"] = expected_h
            notes.append("H: STALE %s -> %.2f (closed Kimai entries added; %.2fh missing)"
                         % (existing_h, expected_h, expected_h - existing_val))
        else:
            notes.append("H: already %s (expected %.2f) - pass --force to overwrite"
                         % (existing_h, expected_h))
    else:
        writes.append({"range": "%s!%s%d" % (tab, GMI_COL, row), "values": [[expected_h]]})
        planned["H"] = expected_h
        notes.append("H: %s -> %.2f%s" % (existing_h or "(blank)", expected_h,
                                          " (forced)" if existing_h else ""))

    result["notes"] = notes
    result["planned_writes"] = [w["range"] for w in writes]
    result["planned_values"] = planned

    if dry:
        result["dry_run"] = True
        if summary:
            result["summary"] = {"refreshed": None, "reason": "dry run"}
        return result

    if writes:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"valueInputOption": "USER_ENTERED", "data": writes}).execute()

    after = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="%s!A%d:I%d" % (tab, row, row),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [[]])
    after = (after[0] if after else []) + [""] * 9
    result["after"] = {"date": after[0], "C": after[2], "D": after[3], "E": after[4], "H": after[7]}
    after_map = {"C": after[2], "H": after[7]}
    errors = []
    for col, expected in planned.items():
        if not _numbers_equal(after_map.get(col), expected):
            errors.append("%s: planned %s, read back %s"
                          % (col, expected, after_map.get(col) or "(blank)"))
    result["verified"] = not errors
    if errors:
        result["verification_errors"] = errors

    if summary:
        result["summary"] = refresh_summary(svc, tab, day.month, day.year, today_local())
    return result


def main():
    ap = argparse.ArgumentParser(description="Fill one day's tracker hours into the monthly tab.")
    ap.add_argument("--date", help="YYYY-MM-DD. Defaults to today.")
    ap.add_argument("--force", action="store_true", help="Overwrite cells that already hold a value.")
    ap.add_argument("--dry-run", action="store_true", help="Report only, write nothing.")
    ap.add_argument("--no-summary", action="store_true", help="Skip the weekly block refresh.")
    ap.add_argument("--summary-only", action="store_true", help="Refresh the weekly block and exit.")
    args = ap.parse_args()

    try:
        day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else today_local()
    except ValueError:
        print("error: --date must be YYYY-MM-DD, got %r" % args.date, file=sys.stderr)
        return 1

    try:
        if args.summary_only:
            svc = _sheets()
            tab = "%s%s" % (calendar.month_name[day.month], str(day.year)[2:])
            out = {"date": day.isoformat(), "tab": tab,
                   "summary": refresh_summary(svc, tab, day.month, day.year,
                                              today_local(), dry=args.dry_run)}
        else:
            out = fill(day, force=args.force, dry=args.dry_run,
                       summary=not args.no_summary)
    except Exception as e:
        print("error: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 1

    print(json.dumps(out, indent=2))
    if out.get("verified") is False:
        return 1
    if (out.get("summary") or {}).get("verified") is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
