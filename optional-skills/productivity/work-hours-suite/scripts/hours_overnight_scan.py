#!/usr/bin/env python3
"""hours_overnight_scan.py - morning edge check for the worked-hours sheet.

Covers exactly what the nightly 23:55 fill cannot see:
  * Kimai entries begun yesterday whose end crossed midnight
  * Kimai entries still running (end null; duration 0 = unknown, not zero)
  * yesterday's sheet H vs split-aware Kimai, and C vs TopTracker

Empty stdout means nothing to report (cron delivers stdout verbatim, so
silence is the success signal). Findings are FLAG lines the user acts on;
this script never writes anything. Run with the Hermes venv python.
"""

import argparse
import calendar
import sys
from datetime import date, datetime, timedelta

import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fill_hours as fh  # noqa: E402  (reuses auth + Kimai reader)


def _hm(ts):
    return (ts or "")[11:16]


def _sheet_cell(day, col):
    svc = fh._sheets()
    tab = "%s%s" % (calendar.month_name[day.month], str(day.year)[2:])
    row = day.day + 2
    vals = svc.spreadsheets().values().get(
        spreadsheetId=fh.SPREADSHEET_ID,
        range="%s!%s%d" % (tab, col, row),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [[""]])
    try:
        return str(vals[0][0]).strip()
    except Exception:
        return ""


def _as_hours(text):
    try:
        return round(float(text), 2)
    except (TypeError, ValueError):
        return None


def scan(scan_day, today):
    _, entries = fh.read_kimai(scan_day)
    lines = []
    cross = []
    closed_sec = 0

    for e in entries:
        b = e.get("begin") or ""
        en = e.get("end")
        dur = int(e.get("duration") or 0)
        eid = e.get("id")
        desc = (str(e.get("description") or "").splitlines() or [""])[0][:64]
        if en is None:
            desc_part = (" (%s)" % desc) if desc else ""
            lines.append(
                "FLAG Kimai #%s still RUNNING since %s%s. Duration unknown until it stops; "
                "re-checked next scan." % (eid, _hm(b), desc_part))
            continue
        if en[:10] > b[:10]:
            cross.append((eid, b, en, dur, desc))
        else:
            closed_sec += dur

    for eid, b, en, dur, desc in cross:
        ended = datetime.strptime(en[:10], "%Y-%m-%d").date()
        begun = datetime.strptime(b[:10], "%Y-%m-%d").date()
        hours = dur / 3600.0
        # User convention: split at midnight. Each day gets its own slice.
        midnight = datetime.combine(ended, datetime.min.time())
        end_dt = datetime.strptime(en[:19], "%Y-%m-%dT%H:%M:%S")
        post_h = (end_dt - midnight).total_seconds() / 3600.0
        pre_h = hours - post_h
        row = ended.day + 2
        pre_row = begun.day + 2
        begin_cell = _sheet_cell(begun, "H")
        end_cell = _sheet_cell(ended, "H")
        begin_val = _as_hours(begin_cell) if begin_cell else None
        end_val = _as_hours(end_cell) if end_cell else None
        begin_expected = fh.expected_gmi(begun)
        end_expected = fh.expected_gmi(ended)
        if (begin_val is not None and begin_val >= begin_expected - 0.011 and
                end_val is not None and end_val >= end_expected - 0.011):
            continue  # both midnight slices are already booked
        state = ("Split proposal: +%.2fh on %s (H%d, pre-midnight) and +%.2fh on %s (H%d, post-midnight)."
                 % (pre_h, begun.isoformat(), pre_row, post_h, ended.isoformat(), row))
        lines.append(
            "FLAG Kimai #%s %s -> %s (%.2fh) crossed midnight. %s Awaiting your call."
            % (eid, _hm(b), _hm(en), hours, state))

    # C vs TopTracker: catch the 23:55 partial that never got the closed total.
    tracked = fh.read_toptracker_hours(scan_day)
    sheet_c = _sheet_cell(scan_day, "C")
    if tracked is not None and tracked > 0:
        c_val = _as_hours(sheet_c) if sheet_c else None
        if sheet_c == "":
            lines.append(
                "FLAG TopTracker reads %.2fh for %s but sheet C%d is blank. Was the fill missed?"
                % (tracked, scan_day.isoformat(), scan_day.day + 2))
        elif c_val is not None and tracked > c_val + 0.011:
            lines.append(
                "FLAG TopTracker reads %.2fh for %s but sheet C%d = %s. Missing %.2fh; re-check the row."
                % (tracked, scan_day.isoformat(), scan_day.day + 2, sheet_c, tracked - c_val))

    # H vs Kimai, split-aware: same-day plus this day's midnight slices.
    expected_h = fh.expected_gmi(scan_day)
    sheet_prev = _sheet_cell(scan_day, "H")
    prev_h = _as_hours(sheet_prev) if sheet_prev else None
    if expected_h > 0 and sheet_prev == "":
        lines.append(
            "FLAG Kimai split-aware total is %.2fh for %s but sheet H%d is blank. Was the fill missed?"
            % (expected_h, scan_day.isoformat(), scan_day.day + 2))
    elif prev_h is not None and prev_h < expected_h - 0.011:
        lines.append(
            "FLAG Kimai split-aware total for %s is %.2fh vs sheet H%d = %s. Missing %.2fh; re-check the row."
            % (scan_day.isoformat(), expected_h, scan_day.day + 2, sheet_prev, expected_h - prev_h))

    if lines:
        header = "OVERNIGHT SCAN for %s (window %s)" % (today.isoformat(), scan_day.isoformat())
        trailer = "Reply to book, skip, or adjust."
        print(header)
        print("\n".join(lines))
        print(trailer)


def main():
    ap = argparse.ArgumentParser(description="Report overnight edge cases around the nightly fill.")
    ap.add_argument("--date", help="Window day to scan, YYYY-MM-DD. Defaults to yesterday.")
    args = ap.parse_args()

    today = fh.today_local()
    try:
        scan_day = (datetime.strptime(args.date, "%Y-%m-%d").date()
                    if args.date else today - timedelta(days=1))
        scan(scan_day, today)
    except Exception as exc:
        print("OVERNIGHT SCAN FAILED: %s: %s" % (type(exc).__name__, exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
