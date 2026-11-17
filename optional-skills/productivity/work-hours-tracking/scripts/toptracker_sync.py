#!/usr/bin/env python3
"""
toptracker_sync.py (RETIRED) — legacy TopTracker sync.

This script targets column D and must not be used with the current layout.
Use fill_hours.py instead, which writes column C (MTMPRO tracked) and H (GMI).

Historical description:
Reads the local TopTracker SQLite DB, sums that day's MTMPRO time, and writes
the decimal hours into column D of the month's tab.

  python3 toptracker_sync.py                    # today
  python3 toptracker_sync.py --date 2026-08-03  # a specific day
  python3 toptracker_sync.py --date 2026-08-03 --force

Safety rules (see SKILL.md "Important Rules"):
  - Never overwrites a filled cell unless --force is passed.
  - Never fills future dates.
  - Only writes to tabs using the 7-column layout (August 2026 onward). Older
    tabs have "Other Project" in column D, so writing there would corrupt them.
  - Opens the TopTracker DB read-only so a running TopTracker app is undisturbed.

Exit codes: 0 = wrote or intentionally skipped, 1 = error.
"""

import os
import sys

# ── Interpreter bootstrap ──────────────────────────────────────────────────
# The google-api-python-client libs are installed for the system interpreter
# (/usr/bin/python3), but `python3` on PATH may resolve elsewhere. Re-exec into
# an interpreter that actually has them so the documented command just works.

_REEXEC_FLAG = "TOPTRACKER_SYNC_REEXEC"


def _ensure_google_libs():
    try:
        import googleapiclient  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get(_REEXEC_FLAG):
        sys.exit(
            "error: google-api-python-client is not installed for any known "
            "interpreter.\n       Install with: "
            "/usr/bin/python3 -m pip install --user google-api-python-client "
            "google-auth"
        )

    import subprocess

    # Candidate interpreters, in order. The Hermes venv is FIRST because it is
    # the only interpreter on this machine that ships google-api-python-client.
    # The original list omitted it, so the re-exec always failed with
    # "google-api-python-client is not installed" and every sync silently broke.
    home = os.path.expanduser("~")
    candidates = (
        os.path.join(home, ".hermes", "hermes-agent", "venv", "bin", "python"),
        "/usr/bin/python3",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
    )
    for cand in candidates:
        if not os.path.exists(cand) or os.path.realpath(cand) == os.path.realpath(sys.executable):
            continue
        probe = subprocess.run(
            [cand, "-c", "import googleapiclient"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            os.environ[_REEXEC_FLAG] = "1"
            os.execv(cand, [cand, os.path.abspath(__file__)] + sys.argv[1:])

    sys.exit(
        "error: google-api-python-client is not installed for any known "
        "interpreter.\n       Checked: %s\n       Install with: "
        "/usr/bin/python3 -m pip install --user google-api-python-client "
        "google-auth" % ", ".join(candidates)
    )


_ensure_google_libs()

# Quiet the end-of-life / LibreSSL notices the 3.9 system interpreter emits on
# import. They are advisory and would otherwise dominate this script's output.
import warnings  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*OpenSSL.*")

import argparse  # noqa: E402
import calendar  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
from datetime import datetime  # noqa: E402

from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

# ── Config ─────────────────────────────────────────────────────────────────

SPREADSHEET_ID = "REPLACE_SPREADSHEET_ID"
TOKEN_PATH = os.path.expanduser("~/.local/share/google-mcp/tokens.json")
CREDS_PATH = os.path.expanduser("~/.config/google-mcp/credentials.json")

TOPTRACKER_DB = os.path.expanduser(
    "~/.local/share/TopTracker/TopTracker.db"
)
TOPTRACKER_USER = "mobeen.ahmed@contrivesolution.com"
MTMPRO_PROJECT_ID = 1182888
MTMPRO_PROJECT_NAME = "AI Resource Management"

# First month using the 7-column layout (MTMPRO TRACKED / MTMPRO UNTRACKED at
# D/E, pushing Other Project + Others to F/G). Mirrors NEW_LAYOUT_FROM in the
# my-work-hours plugin — keep the two in sync.
NEW_LAYOUT_FROM = (2026, 8)
TRACKED_COLUMN = "D"
TRACKED_HEADER = "MTMPRO TRACKED"

# ── Google Sheets auth (same pattern as the my-work-hours plugin) ──────────


def _get_creds():
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    with open(CREDS_PATH) as f:
        cd = json.load(f)
    client_info = cd.get("installed", cd.get("web", {}))
    creds = Credentials(
        token=td.get("access_token"),
        refresh_token=td.get("refresh_token"),
        token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_info.get("client_id"),
        client_secret=client_info.get("client_secret"),
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


# ── TopTracker ─────────────────────────────────────────────────────────────


def read_toptracker_hours(date_obj):
    """Total MTMPRO hours tracked on `date_obj`, as a decimal. 0 if none."""
    if not os.path.exists(TOPTRACKER_DB):
        raise FileNotFoundError("TopTracker DB not found at %s" % TOPTRACKER_DB)

    # Table names are namespaced by account email and contain dots, so they must
    # be double-quoted or SQLite parses them as schema.table.
    activity = '"%s_activity"' % TOPTRACKER_USER
    projects = '"%s_project_list_cache"' % TOPTRACKER_USER
    day_str = date_obj.strftime("%Y-%m-%d")

    conn = sqlite3.connect("file:%s?mode=ro" % TOPTRACKER_DB, uri=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(p.name, 'Unknown') AS project,
                ROUND(SUM(ap.endTime - ap.startTime) / 1000.0 / 3600.0, 2) AS total_hours
            FROM {activity} ap
            LEFT JOIN {projects} p ON ap.projectId = p.id
            WHERE date(ap.startTime/1000, 'unixepoch', 'localtime') = ?
              AND ap.endTime > ap.startTime
              AND ap.projectId = ?
            GROUP BY p.name
            """.format(activity=activity, projects=projects),
            (day_str, MTMPRO_PROJECT_ID),
        )
        by_project = {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()

    # Keyed on the cached project name, but fall back to the sum in case the
    # project_list_cache has not synced the name yet (LEFT JOIN -> 'Unknown').
    if MTMPRO_PROJECT_NAME in by_project:
        return by_project[MTMPRO_PROJECT_NAME] or 0
    return round(sum(v for v in by_project.values() if v), 2)


# ── Sheet helpers ──────────────────────────────────────────────────────────


def tab_name_for(date_obj):
    """'August26' for August 2026 — matches the plugin's naming convention."""
    return "%s%s" % (calendar.month_name[date_obj.month], str(date_obj.year)[2:])


def find_tab(svc, tab_name):
    """Return the tab's sheetId, or None if the tab does not exist."""
    ss = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in ss["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    return None


def has_new_layout(svc, tab_name, date_obj):
    """True when this tab really has MTMPRO TRACKED in column D.

    Checks the live header row rather than trusting the date alone, so an
    old-layout tab is never written to even if its month is >= NEW_LAYOUT_FROM.
    """
    if (date_obj.year, date_obj.month) < NEW_LAYOUT_FROM:
        return False
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="%s!A2:G2" % tab_name,
    ).execute()
    header = (resp.get("values") or [[]])[0]
    if len(header) < 4:
        return False
    return header[3].strip().upper() == TRACKED_HEADER


def read_cell(svc, tab_name, cell):
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="%s!%s" % (tab_name, cell),
    ).execute()
    values = resp.get("values")
    if not values or not values[0]:
        return ""
    return values[0][0]


def write_cell(svc, tab_name, cell, value):
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!%s" % (tab_name, cell),
        body={"values": [[value]]},
        valueInputOption="USER_ENTERED",
    ).execute()


# ── Main ───────────────────────────────────────────────────────────────────


def sync(date_obj, force=False):
    """Sync one day. Returns a result dict (also printed as JSON)."""
    raise RuntimeError(
        "toptracker_sync.py is retired: use fill_hours.py, which writes "
        "column C. This script targets the legacy D column."
    )
    date_str = date_obj.strftime("%Y-%m-%d")
    tab = tab_name_for(date_obj)
    row = date_obj.day + 2  # row 3 = day 1
    cell = "%s%d" % (TRACKED_COLUMN, row)
    base = {"date": date_str, "tab": tab, "cell": cell}

    if date_obj.date() > datetime.now().date():
        base.update(hours=0, written=False, skipped=True,
                    reason="date is in the future")
        return base

    hours = read_toptracker_hours(date_obj)
    base["hours"] = hours

    if hours <= 0:
        base.update(written=False, skipped=True, reason="no tracked hours")
        return base

    svc = _sheets()

    if find_tab(svc, tab) is None:
        base.update(written=False, skipped=True,
                    reason="tab '%s' does not exist — create it first with "
                           "build_month_tab.py (work-hours-monthly-tab skill)" % tab)
        return base

    if not has_new_layout(svc, tab, date_obj):
        base.update(written=False, skipped=True,
                    reason="tab '%s' uses the legacy 6-column layout "
                           "(column D is 'Other Project'), so MTMPRO TRACKED "
                           "has nowhere to go" % tab)
        return base

    existing = read_cell(svc, tab, cell)
    if existing and not force:
        base.update(written=False, skipped=True, existing=existing,
                    reason="already filled — pass --force to overwrite")
        return base

    write_cell(svc, tab, cell, hours)
    base.update(written=True, skipped=False)
    if existing:
        base["overwrote"] = existing
    return base


def main():
    ap = argparse.ArgumentParser(
        description="Sync TopTracker MTMPRO hours into column D "
                    "(MTMPRO TRACKED) of the month's tab.",
    )
    ap.add_argument("--date", help="Date to sync, YYYY-MM-DD. Defaults to today.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite the cell even if it already has a value.")
    args = ap.parse_args()

    if args.date:
        try:
            date_obj = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print("error: --date must be YYYY-MM-DD, got %r" % args.date,
                  file=sys.stderr)
            return 1
    else:
        date_obj = datetime.now()

    try:
        result = sync(date_obj, force=args.force)
    except FileNotFoundError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except sqlite3.Error as e:
        print("error: TopTracker DB read failed: %s" % e, file=sys.stderr)
        return 1
    except Exception as e:  # network / auth / API failures
        print("error: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result.get("written"):
        print("\n%s  ->  %s!%s = %sh" %
              (result["date"], result["tab"], result["cell"], result["hours"]),
              file=sys.stderr)
    else:
        print("\n%s  ->  skipped: %s" % (result["date"], result["reason"]),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
