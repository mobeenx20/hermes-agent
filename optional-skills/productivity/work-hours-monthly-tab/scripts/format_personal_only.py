#!/usr/bin/env python3
"""Apply the September design system to a PERSONAL-ONLY monthly tab.

Some monthly tabs (August26 and earlier) hold only the two personal blocks:
the daily day grid and the WEEKLY SUMMARY. They have no team tables, no
cross-month block, no footnotes and no Column Key. Running build_month_tab.py
against them would CREATE those blocks, which is not wanted.

This script styles only what already exists, using the exact same palette,
fonts, borders, number formats, row heights, column widths and hidden gridlines
as the full September layout, so a personal-only tab reads as one system with it.

It also inserts the "1  MOBEEN ONLY" category band above the Weekly Summary and
shifts that block down one row, matching where build_month_tab.py puts r_sec1
(r_day_last + 2, with a thin spacer row above it).

Values are never rewritten: the band label is the only new content. Every
existing value keeps its text, one row lower. Always --snapshot first, then
--apply, then --verify against that snapshot.

Usage:
  format_personal_only.py --month 8 --year 2026 --snapshot
  format_personal_only.py --month 8 --year 2026 --apply
  format_personal_only.py --month 8 --year 2026 --verify <snapshot.json>
"""
import argparse
import calendar
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Shared palette: one source of truth for the design system.
from build_month_tab import (  # noqa: E402
    auth, SPREADSHEET_ID, tab_name, weeks_of,
    NAVY, STEEL, TOTBG, WEEKEND, WEEKEND_TX, WHITE, WHITE_TX, INK, NOTE_BG,
    LIGHT_B, MID_B, SIGNED, PLAIN0,
)
from googleapiclient.discovery import build  # noqa: E402

COL_W = [135, 215, 175, 175, 160, 115, 130, 118, 160, 180, 180, 180]
# Per-date target overrides. A holiday sets the day's target to 0 and a half day
# to 4, which is what makes "extra" honest: a holiday adds no quota, so any hour
# worked that day is genuinely extra. Keep this in step with the days highlighted
# in highlight_days(); they are the same facts stated twice.
DAY_TARGETS = {"10": 4, "14": 0, "26": 0}
# Public holidays and half days need to be VISIBLE, because they change the
# week's target and therefore what counts as extra. A holiday is green (the
# conventional calendar colour), a half day is amber, so the two read as
# different things at a glance and neither is confused with the cream weekend.
HOLIDAY_BG = {"red": 0.851, "green": 0.917, "blue": 0.827}   # #D9EAD3
HALFDAY_BG = {"red": 1.000, "green": 0.898, "blue": 0.800}   # #FFE5CC
HOLIDAY_TX = {"red": 0.180, "green": 0.400, "blue": 0.200}
BASE_FMT = {
    "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
    "textFormat": {"bold": False, "italic": False, "fontSize": 10,
                   "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}},
    "numberFormat": {"type": "NUMBER", "pattern": "0.00;-0.00;"},
    "horizontalAlignment": "CENTER",
    "verticalAlignment": "MIDDLE",
    "wrapStrategy": "OVERFLOW_CELL",
    "borders": {"top": {"style": "NONE"}, "bottom": {"style": "NONE"},
                "left": {"style": "NONE"}, "right": {"style": "NONE"}},
}
BASE_FIELDS = ("userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,"
               "userEnteredFormat.numberFormat,"
               "userEnteredFormat.horizontalAlignment,"
               "userEnteredFormat.verticalAlignment,"
               "userEnteredFormat.wrapStrategy,"
               "userEnteredFormat.borders")


def geometry(month, year):
    """Row map for a personal-only tab. Mirrors build_month_tab's offsets."""
    wk = weeks_of(month, year)
    ndays = calendar.monthrange(year, month)[1]
    g = {
        "month": month, "year": year, "ndays": ndays, "nweeks": len(wk),
        "tab": tab_name(month, year),
        "r_day_first": 3,
        "r_day_last": 2 + ndays,
    }
    # Band 1 sits one blank spacer row below the grid, exactly as the full
    # layout places it (r_day_last + 2, r_day_last + 1 left blank).
    g["r_sec1"] = g["r_day_last"] + 2
    g["r_wk_title"] = g["r_sec1"] + 1
    g["r_wk_hdr"] = g["r_wk_title"] + 1
    g["r_wk_first"] = g["r_wk_hdr"] + 1
    g["r_wk_last"] = g["r_wk_first"] + len(wk) - 1
    g["r_wk_total"] = g["r_wk_last"] + 1
    return g


def rng(sid, r0, r1, c0, c1):
    return {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1,
            "startColumnIndex": c0, "endColumnIndex": c1}


def cellfmt(sid, r0, r1, c0, c1, bg=None, bold=None, size=None, italic=None,
            fg=None, pat=None, align=None):
    f, fields = {}, []
    if bg is not None:
        f["backgroundColor"] = bg
        fields.append("userEnteredFormat.backgroundColor")
    tf = {}
    for name, val in (("bold", bold), ("fontSize", size),
                      ("italic", italic), ("foregroundColor", fg)):
        if val is not None:
            tf[name] = val
    if tf:
        f["textFormat"] = tf
        fields += ["userEnteredFormat.textFormat." + k for k in tf]
    if pat is not None:
        f["numberFormat"] = {"type": "NUMBER", "pattern": pat}
        fields.append("userEnteredFormat.numberFormat")
    if align is not None:
        f["horizontalAlignment"] = align
        fields.append("userEnteredFormat.horizontalAlignment")
    f["verticalAlignment"] = "MIDDLE"
    f["wrapStrategy"] = "WRAP"
    fields += ["userEnteredFormat.verticalAlignment",
               "userEnteredFormat.wrapStrategy"]
    return {"repeatCell": {"range": rng(sid, r0, r1, c0, c1),
                           "cell": {"userEnteredFormat": f},
                           "fields": ",".join(fields)}}


def borders(sid, r0, r1, c0, c1):
    return {"updateBorders": {"range": rng(sid, r0, r1, c0, c1), "top": MID_B,
                              "bottom": MID_B, "left": MID_B, "right": MID_B,
                              "innerHorizontal": LIGHT_B, "innerVertical": LIGHT_B}}


def height(sid, r, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS",
                  "startIndex": r - 1, "endIndex": r},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def width(sid, c, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "COLUMNS",
                  "startIndex": c, "endIndex": c + 1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def merge(sid, r0, r1, c0, c1):
    return {"mergeCells": {"range": rng(sid, r0, r1, c0, c1),
                           "mergeType": "MERGE_ALL"}}


def datefmt(sid, r0, r1, c0, c1, pattern):
    """Force a DATE number format. Needed for cells Sheets parsed into dates."""
    return {"repeatCell": {
        "range": rng(sid, r0, r1, c0, c1),
        "cell": {"userEnteredFormat": {
            "numberFormat": {"type": "DATE", "pattern": pattern}}},
        "fields": "userEnteredFormat.numberFormat"}}


def week_target(month, year, lo, hi):
    """Weekday target for a week, honouring holiday / half-day overrides.

    A public holiday contributes 0 and a half day 4, so a week that contains one
    is measured against a lower bar. That is what makes extra time countable:
    hours worked on a 0-target day are all extra.
    """
    total = 0
    for d in range(lo, hi + 1):
        if calendar.weekday(year, month, d) >= 5:
            continue
        total += DAY_TARGETS.get(str(d), 8)
    return total


def holiday_rows(month, year):
    """{row: kind} for days that are holidays ('hol') or half days ('half')."""
    out = {}
    for ds, tgt in DAY_TARGETS.items():
        d = int(ds)
        if tgt == 0:
            out[2 + d] = "hol"
        elif tgt < 8:
            out[2 + d] = "half"
    return out


def build_requests(sid, g):
    """The styling pass. Contract: band 30 | title 34 | header 46 | data 21."""
    q = []
    # Row heights (heights are dimension props: always set them explicitly).
    q.append(height(sid, 1, 34))
    q.append(height(sid, 2, 46))
    for r in range(g["r_day_first"], g["r_day_last"] + 1):
        q.append(height(sid, r, 21))
    q.append(height(sid, g["r_day_last"] + 1, 12))       # spacer row
    q.append(height(sid, g["r_sec1"], 30))               # category band
    q.append(height(sid, g["r_wk_title"], 34))
    q.append(height(sid, g["r_wk_hdr"], 46))
    for r in range(g["r_wk_first"], g["r_wk_total"] + 1):
        q.append(height(sid, r, 21))
    # Category band: light grey, navy bold, column A only (not merged), so it
    # stays visually distinct from the navy table titles.
    q.append(cellfmt(sid, g["r_sec1"] - 1, g["r_sec1"], 0, 12, bg=NOTE_BG,
                     bold=True, size=11, fg=NAVY, align="LEFT"))
    # Daily grid.
    q.append(cellfmt(sid, 0, 1, 0, 8, bg=NAVY, bold=True, size=12,
                     fg=WHITE_TX, align="CENTER"))
    q.append(cellfmt(sid, 1, 2, 0, 8, bg=STEEL, bold=True, fg=WHITE_TX,
                     align="CENTER"))
    q.append(cellfmt(sid, 2, g["r_day_last"], 0, 8, bg=WHITE, fg=INK, size=10,
                     align="CENTER"))
    # Weekends: cream and italic.
    for d in range(1, g["ndays"] + 1):
        if calendar.weekday(g["year"], g["month"], d) >= 5:
            row = g["r_day_first"] + d - 2
            q.append(cellfmt(sid, row, row + 1, 0, 8, bg=WEEKEND,
                             fg=WEEKEND_TX, italic=True))
    # Holidays and half days come AFTER weekends so they win on any clash, and
    # carry a bold label so a holiday cannot be mistaken for a normal workday.
    for row, kind in holiday_rows(g["month"], g["year"]).items():
        bg = HOLIDAY_BG if kind == "hol" else HALFDAY_BG
        q.append(cellfmt(sid, row - 1, row, 0, 8, bg=bg, fg=HOLIDAY_TX, bold=True))
    q.append(borders(sid, 0, g["r_day_last"], 0, 8))
    # Weekly Summary. EXTRA/SHORT targets come from week_target(), which accounts
    # for holiday / half-day overrides, so the delta is measured against the real
    # bar for that week rather than a flat 5 x 8h.
    q.append(cellfmt(sid, g["r_wk_title"] - 1, g["r_wk_title"], 0, 9, bg=NAVY,
                     bold=True, size=12, fg=WHITE_TX, align="CENTER"))
    q.append(cellfmt(sid, g["r_wk_hdr"] - 1, g["r_wk_hdr"], 0, 9, bg=STEEL,
                     bold=True, fg=WHITE_TX, align="CENTER"))
    q.append(cellfmt(sid, g["r_wk_first"] - 1, g["r_wk_last"], 0, 9, bg=WHITE,
                     fg=INK, size=10, align="CENTER"))
    q.append(cellfmt(sid, g["r_wk_last"], g["r_wk_total"], 0, 9, bg=TOTBG,
                     bold=True, fg=NAVY, align="CENTER"))
    q.append(cellfmt(sid, g["r_wk_first"] - 1, g["r_wk_total"], 2, 8, pat=PLAIN0))
    q.append(cellfmt(sid, g["r_wk_first"] - 1, g["r_wk_total"], 8, 9, pat=SIGNED))
    # Period cells hold real DATES (a single-day week like "Aug 31" is parsed as
    # a date, not text). The baseline reset above sets a numeric pattern, which
    # makes such a cell render as a serial like 46265.00. Restore the date format
    # explicitly, with a pattern that renders a single-day range as "Aug 31".
    q.append(datefmt(sid, g["r_wk_first"], g["r_wk_total"], 1, 2, "mmm d"))
    q.append(borders(sid, g["r_wk_title"] - 1, g["r_wk_total"], 0, 9))
    q.append(merge(sid, g["r_wk_title"] - 1, g["r_wk_title"], 0, 9))
    # Column widths + hide gridlines, matching the full layout.
    for c, px in enumerate(COL_W):
        q.append(width(sid, c, px))
    q.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {"hideGridlines": True}},
        "fields": "gridProperties.hideGridlines"}})
    return q


def band_present(svc, tab, g):
    """True when the category band label already sits on its row.

    Makes the band insert CONDITIONAL, so --apply is idempotent. Without this a
    second run inserts another row and pushes the Weekly Summary down again.
    """
    v = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!A%d" % (tab, g["r_sec1"]),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])
    return bool(v) and bool(v[0]) and str(v[0][0]).strip() == "1  MOBEEN ONLY"


def apply_style(svc, sid, g):
    """Insert the band row, clean old formatting, label the band, style."""
    if not band_present(svc, g["tab"], g):
        insert = {"requests": [{"insertDimension": {
            "range": {"sheetId": sid, "dimension": "ROWS",
                      "startIndex": g["r_sec1"] - 1, "endIndex": g["r_sec1"]},
            "inheritFromBefore": False}}]}
        svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID,
                                       body=insert).execute()
    # An insert can leave a merge straddling the new boundary, and a stale merge
    # silently redirects writes to its anchor cell. Unmerge the whole area below
    # the grid first.
    unmerge = {"requests": [{"unmergeCells": {"range": rng(
        sid, g["r_day_last"], g["r_wk_total"] + 8, 0, 15)}}]}
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID,
                                   body=unmerge).execute()
    # Baseline reset so formatting residue from an older layout cannot win over
    # the styles applied afterwards.
    reset = {"requests": [{"repeatCell": {
        "range": rng(sid, g["r_day_last"], g["r_wk_total"] + 8, 0, 15),
        "cell": {"userEnteredFormat": BASE_FMT}, "fields": BASE_FIELDS}}]}
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID,
                                   body=reset).execute()
    # The band label is the ONLY new content this script writes.
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range="%s!A%d" % (g["tab"], g["r_sec1"]),
        body={"values": [["1  MOBEEN ONLY"]]},
        valueInputOption="USER_ENTERED").execute()
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID,
                                   body={"requests": build_requests(sid, g)}).execute()
    # Targets last, so the formulas survive the format reset above and pick up
    # the holiday-aware bars.
    return write_targets(svc, g)


def write_targets(svc, g):
    """Rewrite the weekly EXTRA/SHORT formulas against holiday-aware targets.

    This is the ONE content change this script makes beyond the band label, and
    it is deliberate: a holiday (0h) and a half day (4h) lower that week's bar, so
    measuring the week against a flat 5 x 8h would understate the extra hours
    worked. Rewriting the formula's target constant is what "any extra hour counts
    as extra" means in the sheet. Values in C..H are never touched.

    Idempotent: the same targets are produced on every run, so the cell text is
    stable and a second --apply is a no-op.
    """
    wk = weeks_of(g["month"], g["year"])
    data = []
    month_tgt = 0
    for i, (lo, hi, _lbl) in enumerate(wk, start=1):
        t = week_target(g["month"], g["year"], lo, hi)
        month_tgt += t
        r = g["r_wk_first"] + i - 1
        data.append({"range": "%s!I%d" % (g["tab"], r),
                     "values": [["=H%d-%d" % (r, t)]]})
    t = month_tgt
    data.append({"range": "%s!I%d" % (g["tab"], g["r_wk_total"]),
                 "values": [["=H%d-%d" % (g["r_wk_total"], t)]]})
    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data}).execute()
    return {"week_targets": [week_target(g["month"], g["year"], lo, hi)
                             for lo, hi, _ in wk],
            "month_target": t}


def _num(s):
    """Parse a displayed cell to a float. Blank and '0' both mean zero."""
    s = str(s).strip().replace("+", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return "TEXT"


def verify(svc, tab, g, snap_path):
    """Prove every pre-existing value survived, shifted down exactly one row.

    Comparison is SEMANTIC, not byte-for-byte, because this script deliberately
    normalizes the display to the September format contract: a zero renders as
    blank (zero-suppression), 22.6 renders as 22.60, and +2.1 renders as +2.05.
    Those are formatting changes, not data changes. So:
      - numeric cells (C..I) compare NUMERICALLY, with blank == 0
      - date/text cells (A, B) compare as displayed text, since a date's serial
        number is meaningless without its pattern
    """
    before = json.load(open(snap_path))["values"]
    after = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!A1:O%d" % (tab, g["r_wk_total"] + 6),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])

    def pad(r, n=15):
        r = list(r) if r else []
        return [str(x) for x in r + [""] * (n - len(r))]

    def row_diff(b, a):
        """Column indices whose meaning differs."""
        bad = []
        for j in range(15):
            bv, av = b[j], a[j]
            bn, an = _num(bv), _num(av)
            # Numeric on at least one side and parseable on both.
            if (bn is not None and bn != "TEXT") or (an is not None and an != "TEXT"):
                b0 = 0.0 if bn is None or bn == "TEXT" else bn
                a0 = 0.0 if an is None or an == "TEXT" else an
                if abs(b0 - a0) > 1e-9:
                    bad.append(j)
                continue
            if bv.strip() != av.strip():
                bad.append(j)
        return bad

    problems, checked = [], 0
    for i in range(len(before)):
        b = pad(before[i])
        if i < g["r_day_last"]:
            a = pad(after[i]) if i < len(after) else [""] * 15
            target = i + 1
        else:
            a = pad(after[i + 1]) if i + 1 < len(after) else [""] * 15
            target = i + 2
        if not any(b):
            continue
        bad = row_diff(b, a)
        if bad:
            problems.append({
                "snapshot_row": i + 1, "now_at_row": target,
                "cols": [chr(65 + j) for j in bad],
                "before": [b[j] for j in bad],
                "after": [a[j] for j in bad]})
        checked += 1
    band_row = pad(after[g["r_sec1"] - 1]) if g["r_sec1"] - 1 < len(after) else [""] * 15
    if band_row[0].strip() != "1  MOBEEN ONLY":
        problems.append({"row": g["r_sec1"], "band_missing": band_row[0]})
    return problems, checked, len(before)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--verify")
    a = ap.parse_args()

    g = geometry(a.month, a.year)
    svc = build("sheets", "v4", credentials=auth(), cache_discovery=False)

    if a.verify:
        problems, checked, total = verify(svc, g["tab"], g, a.verify)
        print(json.dumps({
            "tab": g["tab"],
            "status": "verified" if not problems else "MISMATCH",
            "rows_checked": checked, "snapshot_rows": total,
            "problem_count": len(problems), "problems": problems[:12]},
            indent=2))
        return 1 if problems else 0

    if a.snapshot:
        v = svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="%s!A1:O%d" % (g["tab"], g["r_wk_total"] + 6),
            valueRenderOption="FORMATTED_VALUE").execute().get("values", [])
        p = os.path.expanduser("~/.hermes/cache/sheets/%s_snapshot.json" % g["tab"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            json.dump({"tab": g["tab"], "values": v}, fh, indent=1)
        print(json.dumps({"tab": g["tab"], "snapshot": p,
                          "rows": len(v), "status": "saved"}, indent=2))
        return 0

    if not a.apply:
        print(json.dumps({"tab": g["tab"], "status": "refused",
                          "reason": "writing requires --apply",
                          "geometry": g}, indent=2))
        return 1

    sid = None
    info = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sh in info["sheets"]:
        if sh["properties"]["title"] == g["tab"]:
            sid = sh["properties"]["sheetId"]
    if sid is None:
        print(json.dumps({"error": "tab does not exist", "tab": g["tab"]}, indent=2))
        return 1

    apply_style(svc, sid, g)
    v = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!A%d:I%d" % (g["tab"], g["r_sec1"] - 1, g["r_wk_total"]),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])
    print(json.dumps({"tab": g["tab"], "status": "styled",
                      "band_row": g["r_sec1"],
                      "weekly_title_row": g["r_wk_title"],
                      "month_total_row": g["r_wk_total"],
                      "block": v}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
