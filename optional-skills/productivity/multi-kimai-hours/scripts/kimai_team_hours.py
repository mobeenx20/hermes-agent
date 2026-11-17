#!/usr/bin/env python3
"""kimai_team_hours.py - read hours from MULTIPLE Kimai accounts and fill
local (CSV) or Google sheets.

Every developer keeps their own Kimai account; one config file lists them
all and one shared sheet holds everyone's hours:

  kimai_team_hours.py read --date 2026-11-16 [--accounts a,b] [--json]
  kimai_team_hours.py read --from 2026-11-10 --to 2026-11-16
  kimai_team_hours.py fill-local  --date 2026-11-16 [--force] [--dry-run]
  kimai_team_hours.py fill-google --date 2026-11-16 [--force] [--dry-run]

Config (JSON), default ~/.hermes/config/kimai-accounts.json:

  {"sheet": {"spreadsheet_id": "...", "tab": "TeamHours", "csv": "..."},
   "accounts": [{"name": "dev-a-gmi", "developer": "Developer A",
                 "url": "...", "username": "...", "token": "...",
                 "projectId": 1, "timezone": "Asia/Karachi"}]}

Sheet layout (both targets): A Date (ISO) | B Day | one column per developer,
header row 1. Rows are keyed by the date in column A; missing rows are
appended in date order.

Book-keeping rules (carried over from the proven single-account pipeline):
  * A cross-midnight entry is SPLIT at 00:00: the pre-midnight part counts on
    the begin day, the post-midnight part on the end day (matches Kimai's
    weekly view; user rule 2026-10-28).
  * A running entry (end null, duration 0) is UNKNOWN, never zero: excluded
    from sums and reported as a flag.
  * Round the SUM at 2dp, never the individual rows.
  * A zero reading never clears a cell that holds a value.
  * Never fill a future day.
  * Every write is read back and verified (exit 2 on verification failure).
  * Kimai calls carry a browser User-Agent (Cloudflare 403s without it) and
    retry transient network errors 3x (2s/4s backoff).

Exit codes: 0 ok, 1 error, 2 verification failure.
"""

import argparse
import calendar
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

DEFAULT_CONFIG = os.path.expanduser("~/.hermes/config/kimai-accounts.json")
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
TOKEN_PATH = os.path.expanduser("~/.local/share/google-mcp/tokens.json")
CREDS_PATH = os.path.expanduser("~/.config/google-mcp/credentials.json")

_REEXEC = "KIMAI_TEAM_HOURS_REEXEC"


# --- helpers ---------------------------------------------------------------

def tz_for(name):
    name = name or "Asia/Karachi"
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return timezone(timedelta(hours=5))  # fallback: PKT fixed offset


def parse_ts(ts, tz):
    """Kimai ISO timestamp -> naive local datetime (same policy as fill_hours)."""
    text = str(ts or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if len(text) >= 25 and (text[-5] in "+-") and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]  # +0500 -> +05:00
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz).replace(tzinfo=None)


def round2(sec):
    return round(sec / 3600.0, 2)


def _window_days(report):
    """Every date in the requested window (data or not), so future days are
    always seen and noted by the fillers."""
    w = report["window"]
    d0, d1 = date.fromisoformat(w["from"]), date.fromisoformat(w["to"])
    out, d = [], d0
    while d <= d1:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def today_local():
    return datetime.now(tz_for("Asia/Karachi")).date()


# --- config ----------------------------------------------------------------

def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    accounts = cfg.get("accounts") or []
    if not accounts:
        raise SystemExit("error: config %s has no accounts[]" % path)
    seen = set()
    for a in accounts:
        for key in ("name", "developer", "url", "username", "token", "projectId"):
            if key not in a:
                raise SystemExit("error: account %r missing %r" % (a.get("name"), key))
        if a["name"] in seen:
            raise SystemExit("error: duplicate account name %r" % a["name"])
        seen.add(a["name"])
    return cfg


def select_accounts(cfg, only):
    accounts = cfg["accounts"]
    if not only:
        return accounts
    wanted = [w.strip() for w in only.split(",") if w.strip()]
    picked = [a for a in accounts if a["name"] in wanted]
    missing = set(wanted) - {a["name"] for a in picked}
    if missing:
        raise SystemExit("error: unknown account(s): %s" % ", ".join(sorted(missing)))
    return picked


# --- Kimai API -------------------------------------------------------------

def fetch_entries(account, begin_day, end_day):
    """Raw entries whose BEGIN falls in [begin_day, end_day], paginated."""
    base = account["url"].rstrip("/")
    entries, page = [], 1
    while True:
        url = ("%s/api/timesheets?project=%s&begin=%sT00:00:00&end=%sT23:59:59"
               "&size=200&page=%d"
               % (base, account["projectId"], begin_day.isoformat(),
                  end_day.isoformat(), page))
        req = urllib.request.Request(url, headers={
            "X-AUTH-USER": account["username"],
            "X-AUTH-TOKEN": account["token"],
            "User-Agent": USER_AGENT,
        })
        payload, last_err = None, None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.load(resp)
                break
            except urllib.error.HTTPError as e:
                raise RuntimeError("Kimai HTTP %s for %s: %s"
                                   % (e.code, account["name"], e.read()[:200]))
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2 + attempt * 2)
        if payload is None:
            raise RuntimeError("Kimai fetch failed for %s after 3 attempts: %r"
                               % (account["name"], last_err))
        batch = payload.get("data", payload) if isinstance(payload, dict) else payload
        batch = batch or []
        entries.extend(batch)
        if len(batch) < 200:
            return entries
        page += 1
        if page > 20:
            raise RuntimeError("Kimai pagination ran away for %s" % account["name"])


# --- split-aware day math ---------------------------------------------------

def day_breakdown(entries, day, tz):
    """Split-aware book-keeping for one day.

    Returns dict: split_sec (midnight-split total, running excluded),
    begin_sec (plain begin-date sum), running ids, cross-midnight details.
    """
    split_sec = 0.0
    begin_sec = 0
    running = []
    cross = []
    for e in entries:
        eid = e.get("id")
        if not e.get("end") or not e.get("duration"):
            running.append({"id": eid, "begin": e.get("begin"),
                            "description": str(e.get("description") or "").splitlines()[0][:64]
                            if e.get("description") else ""})
            continue
        b = parse_ts(e["begin"], tz)
        en = parse_ts(e["end"], tz)
        bdate, edate = b.date(), en.date()
        if bdate == day:
            begin_sec += int(e["duration"])
        if bdate == day and edate == day:
            split_sec += int(e["duration"])
        elif bdate == day and edate > day:
            midnight = datetime.combine(day + timedelta(days=1), dtime.min)
            split_sec += max(0.0, (midnight - b).total_seconds())
            cross.append({"id": eid, "begin": e["begin"], "end": e["end"]})
        elif bdate < day and edate == day:
            midnight = datetime.combine(day, dtime.min)
            split_sec += max(0.0, (en - midnight).total_seconds())
            cross.append({"id": eid, "begin": e["begin"], "end": e["end"]})
        elif bdate < day and edate > day:
            split_sec += 86400.0
            cross.append({"id": eid, "begin": e["begin"], "end": e["end"]})
    return {"split_sec": split_sec, "begin_sec": begin_sec,
            "running": running, "cross_midnight": cross}


def read_range(accounts, start, end):
    report = {"window": {"from": start.isoformat(), "to": end.isoformat()},
              "accounts": {}, "flags": []}
    for acct in accounts:
        tz = tz_for(acct.get("timezone"))
        # pull one extra day back so prior-day cross-midnight entries are seen
        entries = fetch_entries(acct, start - timedelta(days=1), end)
        days = {}
        total_split_sec = 0.0
        d = start
        while d <= end:
            bd = day_breakdown(entries, d, tz)
            total_split_sec += bd["split_sec"]
            if bd["running"] or bd["cross_midnight"] or bd["split_sec"] or bd["begin_sec"]:
                days[d.isoformat()] = {
                    "split_hours": round2(bd["split_sec"]),
                    "begin_hours": round2(bd["begin_sec"]),
                    "running": bd["running"],
                    "cross_midnight": bd["cross_midnight"],
                }
                for r in bd["running"]:
                    report["flags"].append(
                        "%s %s: entry #%s RUNNING since %s - duration unknown"
                        % (acct["name"], d.isoformat(), r["id"], (r["begin"] or "")[11:16]))
                for c in bd["cross_midnight"]:
                    report["flags"].append(
                        "%s %s: entry #%s crosses midnight (%s -> %s), split applied"
                        % (acct["name"], d.isoformat(), c["id"],
                           (c["begin"] or "")[11:16], (c["end"] or "")[11:16]))
            d += timedelta(days=1)
        report["accounts"][acct["name"]] = {
            "developer": acct["developer"],
            "url": acct["url"],
            "projectId": acct["projectId"],
            "entries_seen": len(entries),
            "days": days,
            "total_split_hours": round2(total_split_sec),
        }
    return report


# --- local CSV fill --------------------------------------------------------

def _cell_rule(existing, value):
    """Return (action, note) for one cell. Never clears; zero never writes."""
    existing = (existing or "").strip()
    if value == 0:
        return ("keep", "zero reading, cell untouched" if existing else "no hours, nothing to write")
    if not existing:
        return ("write", "(blank) -> %.2f" % value)
    try:
        old = float(existing)
    except ValueError:
        return ("skip", "cell holds %r (non-numeric); --force to overwrite" % existing)
    if abs(old - value) <= 0.011:
        return ("skip", "already %.2f" % old)
    if value > old + 0.011:
        return ("write", "STALE %.2f -> %.2f (%.2fh missing)" % (old, value, value - old))
    return ("skip", "cell %.2f > read %.2f; --force to overwrite" % (old, value))


def fill_local(report, cfg, force, dry):
    path = (cfg.get("sheet") or {}).get("csv") or "team-hours.csv"
    path = os.path.expanduser(path)
    developers = [report["accounts"][n]["developer"] for n in report["accounts"]]
    header = ["Date", "Day"] + developers

    rows = {}   # date -> {developer: value}
    if os.path.exists(path):
        with open(path, newline="") as f:
            reader = csv.reader(f)
            existing_header = next(reader, None)
            if existing_header and existing_header[:2] != ["Date", "Day"]:
                raise SystemExit("error: %s does not look like a team-hours CSV" % path)
            col_of = {name: i for i, name in enumerate(existing_header or [])}
            for row in reader:
                if not row or not row[0]:
                    continue
                rows[row[0]] = {name: (row[i] if i < len(row) else "")
                                for name, i in col_of.items() if i >= 2}

    planned, notes = [], []
    win_days = _window_days(report)
    for iso in win_days:
        day = date.fromisoformat(iso)
        if day > today_local():
            notes.append("%s: skipped, future day" % iso)
            continue
        for name, acc in report["accounts"].items():
            dev = acc["developer"]
            value = acc["days"].get(iso, {}).get("split_hours", 0)
            action, note = _cell_rule(rows.get(iso, {}).get(dev, ""), value)
            if force and action == "skip" and value and "already" not in note:
                action, note = "write", note + " (forced)"
            label = "%s %s [%s]" % (iso, dev, name)
            if action == "write":
                planned.append((iso, dev, value))
                rows.setdefault(iso, {d: "" for d in developers})[dev] = "%.2f" % value
                notes.append("%s: %s" % (label, note))
            else:
                notes.append("%s: kept - %s" % (label, note))
    result = {"target": "local", "path": path, "planned_writes":
              [{"date": d, "developer": dev, "value": v} for d, dev, v in planned],
              "notes": notes, "dry_run": dry}
    if dry:
        return result

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for iso in sorted(rows):
            writer.writerow([iso, calendar.day_name[date.fromisoformat(iso).weekday()]]
                            + [rows[iso].get(dev, "") for dev in developers])

    # read back and verify every planned write
    errors = []
    with open(path, newline="") as f:
        got = {r[0]: r for r in csv.reader(f) if r and r[0] != "Date"}
    for iso, dev, value in planned:
        row = got.get(iso)
        idx = header.index(dev)
        cell = row[idx] if row and idx < len(row) else ""
        if not cell or abs(float(cell) - value) > 0.011:
            errors.append("%s %s: planned %.2f, read %r" % (iso, dev, value, cell))
    result["verified"] = not errors
    if errors:
        result["verification_errors"] = errors
    return result


# --- Google Sheets fill ----------------------------------------------------

def _reexec_into_venv():
    if os.environ.get(_REEXEC):
        sys.exit("error: google-api-python-client not found in any interpreter.")
    home = os.path.expanduser("~")
    for cand in (os.path.join(home, ".hermes", "hermes-agent", "venv", "bin", "python"),
                 "/usr/bin/python3", "/usr/local/bin/python3"):
        if not os.path.exists(cand):
            continue
        if os.path.realpath(cand) == os.path.realpath(sys.executable):
            continue
        import subprocess
        probe = subprocess.run([cand, "-c", "import googleapiclient"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            os.environ[_REEXEC] = "1"
            os.execv(cand, [cand, os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit("error: google-api-python-client not found in any interpreter.")


def _sheets_service():
    try:
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        _reexec_into_venv()
        raise  # unreachable: re-exec replaces the process
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    with open(CREDS_PATH) as f:
        cd = json.load(f)
    info = cd.get("installed", cd.get("web", {}))
    creds = Credentials(
        token=td.get("access_token"), refresh_token=td.get("refresh_token"),
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info.get("client_id"), client_secret=info.get("client_secret"),
        scopes=td.get("scope", "https://www.googleapis.com/auth/spreadsheets").split())
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        td["access_token"] = creds.token
        td["expiry_date"] = creds.expiry.timestamp() * 1000 if creds.expiry else None
        with open(TOKEN_PATH, "w") as f:
            json.dump(td, f)
    return build("sheets", "v4", credentials=creds)


def _serial_to_iso(v):
    """Sheets date serial (UNFORMATTED_VALUE) -> ISO date string."""
    if isinstance(v, (int, float)) and v > 1000:
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    text = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def fill_google(report, cfg, force, dry):
    sheet_cfg = cfg.get("sheet") or {}
    spreadsheet_id = sheet_cfg.get("spreadsheet_id")
    tab = sheet_cfg.get("tab") or "TeamHours"
    if not spreadsheet_id or spreadsheet_id.startswith("REPLACE"):
        raise SystemExit("error: config sheet.spreadsheet_id is not set")
    svc = _sheets_service()
    rng = "%s!A1:Z400" % tab

    devs = [report["accounts"][n]["developer"] for n in report["accounts"]]
    try:
        grid = svc.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=rng,
            valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [])
    except Exception as e:
        raise SystemExit("error: cannot read %s!%s: %s" % (spreadsheet_id, rng, e))

    # header: row 1. create it when the tab is empty.
    writes, notes = [], []
    if not grid or not grid[0] or not grid[0][0]:
        notes.append("header: creating %s" % (["Date", "Day"] + devs))
        writes.append({"range": "%s!A1" % tab,
                       "values": [["Date", "Day"] + devs]})
        grid = [["Date", "Day"] + devs]
    header = [str(c or "") for c in grid[0]]
    missing = [d for d in devs if d not in header[2:]]
    if missing:
        raise SystemExit("error: tab %r header lacks column(s): %s (found: %s)"
                         % (tab, ", ".join(missing), ", ".join(header)))

    row_by_date = {}
    for i, row in enumerate(grid):
        if i == 0 or not row or not row[0]:
            continue
        iso = _serial_to_iso(row[0])
        if iso:
            row_by_date[iso] = i + 1  # 1-based sheet row

    planned = []
    win_days = _window_days(report)
    for iso in win_days:
        day = date.fromisoformat(iso)
        if day > today_local():
            notes.append("%s: skipped, future day" % iso)
            continue
        row = row_by_date.get(iso)
        for name, acc in report["accounts"].items():
            dev = acc["developer"]
            value = acc["days"].get(iso, {}).get("split_hours", 0)
            col_idx = header.index(dev)
            existing = ""
            grow = grid[row - 1] if row and row - 1 < len(grid) else []
            if col_idx < len(grow):
                existing = grow[col_idx]
            if isinstance(existing, (int, float)):
                existing = ("%.2f" % existing).rstrip("0").rstrip(".") or "0"
            action, note = _cell_rule(str(existing), value)
            if force and action == "skip" and value and "already" not in note:
                action, note = "write", note + " (forced)"
            label = "%s %s [%s]" % (iso, dev, name)
            if action == "write":
                if not row:  # lazy row: only when a write actually happens
                    row = len(grid) + 1
                    while row in row_by_date.values():
                        row += 1
                    row_by_date[iso] = row
                    grid.append([iso, calendar.day_name[day.weekday()]] + [""] * len(devs))
                    writes.append({"range": "%s!A%d:B%d" % (tab, row, row),
                                   "values": [[iso, calendar.day_name[day.weekday()]]]})
                    notes.append("%s: new row %d" % (iso, row))
                col_letter = chr(ord("A") + col_idx)
                writes.append({"range": "%s!%s%d" % (tab, col_letter, row),
                               "values": [[value]]})
                planned.append((col_letter, row, dev, value))
                notes.append("%s: %s" % (label, note))
                while len(grid) < row:
                    grid.append([])
                while len(grid[row - 1]) <= col_idx:
                    grid[row - 1].append("")
                grid[row - 1][col_idx] = value
            else:
                notes.append("%s: kept - %s" % (label, note))

    result = {"target": "google", "spreadsheet_id": spreadsheet_id, "tab": tab,
              "planned_writes": [{"cell": "%s!%s%d" % (tab, c, r), "developer": dev,
                                  "value": v} for c, r, dev, v in planned],
              "notes": notes, "dry_run": dry}
    if dry or not writes:
        return result

    body = {"valueInputOption": "USER_ENTERED", "data": writes}
    svc.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

    errors = []
    for col_letter, row, dev, value in planned:
        got = svc.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="%s!%s%d" % (tab, col_letter, row),
            valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [[""]])
        cell = got[0][0] if got and got[0] else ""
        try:
            ok = abs(float(cell) - value) <= 0.011
        except (TypeError, ValueError):
            ok = False
        if not ok:
            errors.append("%s!%s%d [%s]: planned %.2f, read %r"
                          % (tab, col_letter, row, dev, value, cell))
    result["verified"] = not errors
    if errors:
        result["verification_errors"] = errors
    return result


# --- CLI -------------------------------------------------------------------

def parse_day(text, flag):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit("error: %s must be YYYY-MM-DD, got %r" % (flag, text))


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("command", choices=["read", "fill-local", "fill-google"])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--accounts", help="comma-separated account names (default: all)")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--from", dest="from_", help="range start YYYY-MM-DD")
    ap.add_argument("--to", help="range end YYYY-MM-DD")
    ap.add_argument("--force", action="store_true",
                    help="overwrite cells that already hold a value")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    cfg = load_config(args.config)
    accounts = select_accounts(cfg, args.accounts)

    if args.from_ or args.to:
        if not (args.from_ and args.to):
            raise SystemExit("error: --from and --to must be used together")
        start = parse_day(args.from_, "--from")
        end = parse_day(args.to, "--to")
    else:
        start = end = parse_day(args.date, "--date") if args.date else today_local()
    if end < start:
        raise SystemExit("error: --to before --from")

    report = read_range(accounts, start, end)

    if args.command == "read":
        out = report
    elif args.command == "fill-local":
        out = fill_local(report, cfg, args.force, args.dry_run)
    else:
        out = fill_google(report, cfg, args.force, args.dry_run)

    print(json.dumps(out, indent=2))
    if out.get("verified") is False:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(1)
