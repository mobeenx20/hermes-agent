#!/usr/bin/env python3
"""Build a monthly tab in the "Mobeen worked hours" spreadsheet.

Creates the tab if missing, writes the daily grid, and builds the three summary
blocks (Weekly Summary, Team MTMPRO Hours, Reported Split) plus the Column Key,
all styled with the house palette.

Idempotent: an existing tab keeps its data; blocks are rebuilt around it.
From October 2026 the day grid also carries the Usama watched columns (I-K)
with their own row-1 banner; older months are untouched (USAMA_COLS_FROM).

  build_month_tab.py --month 10 --year 2026
  build_month_tab.py --month 10 --year 2026 --dry-run
  build_month_tab.py --month 9  --year 2026 --report-missing
  build_month_tab.py --month 10 --year 2026 --config /path/overrides.json
  build_month_tab.py --month 11 --year 2026 --apply --spreadsheet <id>   # scratch test

--report-missing prints JSON listing every weekly cell still empty for an
ELAPSED week, so the assistant can ask the user for those figures. It never
invents hours.

Config (all keys optional):
{
  "week_targets":  {"3": 64},                     # instructed target per week
  "team_periods":  {"1": "Aug 31 - Sep 4"},       # client week label per week
  "day_targets":   {"2026-09-10": 4},             # per-date daily target override
  "reported":      {"1": {"mobeen": 35.48, "solat": 17, "danish": 3.5}},
  "team":          {"3": {"mobeen": 49.99, "usama_reported": 25.5,
                          "usama_extra": 0, "solat": 18.5, "danish": 0.5,
                          "reported_total": 64}}
}
"""

import argparse
import calendar
import json
import os
import sys
from datetime import date, datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "REPLACE_SPREADSHEET_ID"
TOKEN_PATH = os.path.expanduser("~/.local/share/google-mcp/tokens.json")
CREDS_PATH = os.path.expanduser("~/.config/google-mcp/credentials.json")

NEW_LAYOUT_FROM = (2026, 8)      # first month using 8 columns + summary blocks
BASE_WEEK_TARGET = 50            # standing weekly team mark (pre-cut)
BASE_WEEK_TARGET_CUT = 40        # standing mark from the Oct 12 2026 client cut
WORKDAY_TARGET = 8               # hours per weekday for the daily-target math
# Client hours cut (Oct 2026): the team's standing mark drops to 40h from Mon
# 2026-10-12. Mobeen's PERSONAL weekly target stays 40h; the 32h is his MTMPRO
# allotment, valid only while Solat does the 8h of testing. Keep in sync with
# fill_hours.py, which recomputes the live weekly block after every fill.
WEEKLY_TARGET_CAP_FROM = date(2026, 10, 12)
WEEKLY_TARGET_CAP = 40
# Usama watched columns (I-K): tracked / productive / difference, one row per
# day, plus their own row-1 banner. Introduced with October 2026; earlier
# months are gated out so a rebuild never adds them retroactively.
USAMA_COLS_FROM = (2026, 10)

# ---------------------------------------------------------------- palette ----
NAVY = {"red": 0.121, "green": 0.220, "blue": 0.392}
STEEL = {"red": 0.180, "green": 0.459, "blue": 0.714}
SUBHDR = {"red": 0.557, "green": 0.667, "blue": 0.859}
TOTBG = {"red": 0.851, "green": 0.886, "blue": 0.953}
WEEKEND = {"red": 1.000, "green": 0.949, "blue": 0.804}
WEEKEND_TX = {"red": 0.502, "green": 0.376, "blue": 0.000}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
WHITE_TX = {"red": 1.0, "green": 1.0, "blue": 1.0}
INK = {"red": 0.129, "green": 0.129, "blue": 0.129}
DIM = {"red": 0.400, "green": 0.400, "blue": 0.400}
NOTE_BG = {"red": 0.976, "green": 0.976, "blue": 0.976}
GREEN_CELL = {"red": 0.851, "green": 0.918, "blue": 0.827}   # #D9EAD3 reported
AMBER_CELL = {"red": 1.000, "green": 0.898, "blue": 0.800}   # #FFE5CC extra
# Usama block banner: theme Accent 1 (#5891AD), distinct from the navy Mobeen
# banner so the two headers read as separate tables.
USAMA_BANNER = {"red": 0.34509805, "green": 0.5686275, "blue": 0.6784314}
LIGHT_B = {"style": "SOLID", "color": {"red": 0.741, "green": 0.843, "blue": 0.933}}
MID_B = {"style": "SOLID", "color": {"red": 0.180, "green": 0.459, "blue": 0.714}}

SIGNED = "+0.00;-0.00;0.00"
PLAIN0 = "0.00;-0.00;"
DAILY_HDRS = ["Date", "Day", "MTMPRO TRACKED", "MTMPRO UNTRACKED",
              "BROADCASTING PLATFORM", "Other Project", "Others", "GMI"]
USAMA_HDRS = ["USAMA TRACKED", "USAMA PRODUCTIVE", "USAMA DIFF"]
WEEKLY_HDRS = ["Week", "Period", "MTMPRO TRACKED", "MTMPRO UNTRACKED",
               "BROADCASTING PLATFORM", "OTHERS", "GMI", "TOTAL", "BASE TARGET",
               "EXTRA/SHORT"]
TEAM_HDRS = ["Week", "Period", "Mobeen", "Usama (reported)", "Usama (extra)",
             "Solat", "Danish", "Other", "Total Hours", "Base Target",
             "Week Target", "Reported to Client", "Extra vs Base",
             "Extra vs Week Target"]
SPLIT_HDRS = ["Week", "Period", "Mobeen (incl. Usama)", "Solat", "Danish", "Total"]
CROSS_HDRS = ["Week", "Other Tab Total", "This Tab: Tracked",
              "This Tab: Untracked", "This Tab: Broadcasting", "This Tab: Others",
              "This Tab: GMI", "Week Total", "Week Target", "Extra vs Target"]
KEY_HDRS = ["Column", "What it measures", "How it is calculated", "Example (Week 3)"]


def tab_name(month, year):
    return "%s%s" % (calendar.month_name[month], str(year)[2:])


def auth():
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    with open(CREDS_PATH) as f:
        cd = json.load(f)
    ci = cd.get("installed", cd.get("web", {}))
    scopes = td.get("scope", "").split() or ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials(
        token=td.get("access_token"), refresh_token=td.get("refresh_token"),
        token_uri=ci.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=ci.get("client_id"), client_secret=ci.get("client_secret"),
        scopes=scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        td["access_token"] = creds.token
        with open(TOKEN_PATH, "w") as f:
            json.dump(td, f)
    return creds


def weeks_of(month, year):
    """Mon-Sun weeks clipped to the month: [(lo_day, hi_day, 'Mon D - Mon D')]."""
    _, ndays = calendar.monthrange(year, month)
    m = calendar.month_abbr[month]
    out, d = [], 1
    while d <= ndays:
        wd = calendar.weekday(year, month, d)          # Mon=0
        end = min(d + (6 - wd), ndays)
        lo = 1 if (d + (6 - wd)) > ndays and d == 1 else d
        label = "%s %d - %s %d" % (m, lo, m, end) if lo != end else "%s %d" % (m, lo)
        out.append((lo, end, label))
        d = end + 1
    return out


# --------------------------------------------------------------- builders ----
def cross_month_weeks(month, year):
    """Weeks whose days fall in two monthly tabs.

    A week is a Monday-Sunday span. When the month does not start on a Monday
    the first week starts in the previous month, and when it does not end on a
    Sunday the last week finishes in the next month. Each entry lists the day
    numbers belonging to each side so the blocks can sum both tabs.
    """
    _, ndays = calendar.monthrange(year, month)
    m = calendar.month_abbr[month]
    out = []

    wd1 = calendar.weekday(year, month, 1)                 # Mon=0
    if wd1 != 0:                                           # leading spill
        pm, py = (12, year - 1) if month == 1 else (month - 1, year)
        pnd = calendar.monthrange(py, pm)[1]
        out.append(dict(
            kind="leading",
            ptab=tab_name(pm, py), pyear=py, pmonth=pm,
            tyear=year, tmonth=month,
            pdays=list(range(pnd - wd1 + 1, pnd + 1)),
            tdays=list(range(1, 7 - wd1 + 1)),
            label="%s %d - %s %d" % (calendar.month_abbr[pm], pnd - wd1 + 1,
                                     m, 7 - wd1),
        ))

    wdl = calendar.weekday(year, month, ndays)
    if wdl != 6:                                           # trailing spill
        nm, ny = (1, year + 1) if month == 12 else (month + 1, year)
        out.append(dict(
            kind="trailing",
            ptab=tab_name(nm, ny), pyear=ny, pmonth=nm,
            tyear=year, tmonth=month,
            pdays=list(range(1, 7 - wdl)),
            tdays=list(range(ndays - wdl, ndays + 1)),
            label="%s %d - %s %d" % (m, ndays - wdl,
                                     calendar.month_abbr[nm], 6 - wdl),
        ))
    return out


def week_span_target(x, cfg):
    """Weekday-only target across BOTH sides of a cross-month week."""
    ov = cfg.get("day_targets", {})
    total = 0
    for yr, mo, days in ((x["pyear"], x["pmonth"], x["pdays"]),
                         (x["tyear"], x["tmonth"], x["tdays"])):
        for d in days:
            dt = date(yr, mo, d)
            if dt.weekday() >= 5:
                continue
            total += int(ov.get(dt.isoformat(), WORKDAY_TARGET))
    first = (date(x["pyear"], x["pmonth"], x["pdays"][0]) if x["kind"] == "leading"
             else date(x["tyear"], x["tmonth"], x["tdays"][0]))
    if first >= WEEKLY_TARGET_CAP_FROM:
        total = min(total, WEEKLY_TARGET_CAP)
    return total


def build_rows(month, year, cfg):
    """Return (grid, weekly, team, split, cross, key, meta) row blocks."""
    _, ndays = calendar.monthrange(year, month)
    mname = calendar.month_name[month]
    wk = weeks_of(month, year)
    usama = (year, month) >= USAMA_COLS_FROM

    grid = [[" ", "", "MOBEEN WORKED HOURS"], list(DAILY_HDRS)]
    for day in range(1, ndays + 1):
        grid.append(["%d %s" % (day, mname),
                     calendar.day_name[calendar.weekday(year, month, day)]])
    r_day_first, r_day_last = 3, 2 + ndays
    # Date/Day are written as their own 2-column block. The day rows must NEVER
    # be written as part of `grid`, because padding them to 8 columns sends
    # blank cells over D:H and erases every tracked/untracked/GMI hour.
    day_labels = [row[:2] for row in grid[2:]]

    # ---- CATEGORY BANDS. Three labelled sections group the tables by kind:
    #   1 MOBEEN ONLY (personal) -> 2 MTMPRO (team) -> 3 OTHERS (reference).
    # Band 1 cannot sit above the grid: toptracker_sync.py writes day N to row
    # N+2, so the grid is pinned to rows 1-32. It is a layout invariant.
    r_sec1 = r_day_last + 2
    r_wk_title = r_sec1 + 1
    r_wk_hdr = r_wk_title + 1
    r_wk_first = r_wk_hdr + 1
    r_wk_last = r_wk_first + len(wk) - 1
    r_wk_total = r_wk_last + 1

    weekly = [["WEEKLY SUMMARY"], list(WEEKLY_HDRS)]
    for i, (lo, hi, plabel) in enumerate(wk, start=1):
        tgt = week_target(month, year, lo, hi, cfg)
        dr0, dr1 = r_day_first + lo - 1, r_day_first + hi - 1
        s = lambda col: "=SUM(%s%d:%s%d)" % (col, dr0, col, dr1)
        total_cell = ("=SUM(C{d0}:C{d1},D{d0}:D{d1},E{d0}:E{d1},G{d0}:G{d1},H{d0}:H{d1})"
                      .format(d0=dr0, d1=dr1))
        # EXTRA/SHORT compares against the full leave-adjusted week (user rule
        # 2026-10-22): a week in progress already carries its whole target, so
        # its delta reads negative until the week completes.
        tgt_full = week_target(month, year, lo, hi, cfg)
        started = week_started(month, year, lo)
        orig = cfg.get("weekly_totals", {}).get(str(i))
        # EXTRA/SHORT must blank only when the week has NO hours at all, so the
        # guard spans C,D,E,G,H like the TOTAL cell. Guarding on column H alone
        # blanked every week that had MTMPRO hours but no GMI work, hiding real
        # shortfalls (Sep 2026 Week 3 read blank at -7.51 before this fix).
        any_hours = ("SUM(C{d0}:C{d1},D{d0}:D{d1},E{d0}:E{d1},G{d0}:G{d1},H{d0}:H{d1})=0"
                     .format(d0=dr0, d1=dr1))
        weekly.append([
            "Week %d" % i, plabel,
            s("C"), s("D"), s("E"), s("G"), s("H"),
            total_cell if orig is None else orig,
            # BASE TARGET = the leave-adjusted week mark; EXTRA/SHORT is the
            # live delta against it, blank until the week starts and has hours.
            tgt_full,
            '=IF({g},"",H{r}-I{r})'.format(
                g=any_hours, r=r_wk_first + i - 1) if started else "",
        ])
    rng = lambda col: "=SUM(%s%d:%s%d)" % (col, r_wk_first, col, r_wk_last)
    # MONTH TOTAL must carry EXACTLY one element per header column (A..J), with
    # column B left blank as the Period spacer. Dropping that blank shifts every
    # later value one column left (Others lands in GMI, TOTAL lands in TOTAL's
    # neighbour and the EXTRA formula self-references H42 -> #REF!).
    # Column F (OTHERS) sums the weekly OTHERS cells, NOT column G: the summary
    # header order is F=OTHERS, G=GMI, H=TOTAL, which differs from the day grid.
    weekly.append(["MONTH TOTAL", "", rng("C"), rng("D"), rng("E"), rng("F"),
                   rng("G"), rng("H"),
                   # BASE TARGET = live sum of the started weeks' targets.
                   "=SUM(I%d:I%d)" % (r_wk_first, r_wk_last),
                   # Guard on total hours across the weekly rows, so the month
                   # delta is not blanked just because GMI is empty.
                   "=IF(SUM(C{r0}:C{r1},D{r0}:D{r1},E{r0}:E{r1},F{r0}:F{r1},"
                   "G{r0}:G{r1})=0,\"\",H{t}-I{t})".format(
                       r0=r_wk_first, r1=r_wk_last, t=r_wk_total)])

    # ---- CATEGORY BAND 2: MTMPRO (team tables). Team -> Cross-Month -> Split.
    r_sec2 = r_wk_total + 2
    r_tm_title = r_sec2 + 1
    r_tm_hdr = r_tm_title + 1
    r_tm_first = r_tm_hdr + 1
    r_tm_last = r_tm_first + len(wk) - 1
    r_tm_total = r_tm_last + 1

    team = [["TEAM MTMPRO HOURS"], list(TEAM_HDRS)]
    for i, (lo, hi, _pl) in enumerate(wk, start=1):
        r = r_tm_first + i - 1
        period = cfg.get("team_periods", {}).get(str(i), wk[i - 1][2])
        base = standing_base(month, year, lo)
        tgt = int(cfg.get("week_targets", {}).get(str(i), base))
        seed = cfg.get("team", {}).get(str(i), {})
        team.append([
            "Week %d" % i, period,
            seed.get("mobeen", ""), seed.get("usama_reported", ""),
            seed.get("usama_extra", ""), seed.get("solat", ""),
            seed.get("danish", ""), seed.get("other", ""),
            '=IF(COUNT(C{r}:H{r})=0,"",SUM(C{r}:H{r}))'.format(r=r),
            base,
            target_cell(month, year, hi, tgt, r, lo=lo),
            seed.get("reported_total", ""),
            '=IF(OR(I{r}="",J{r}=""),"",I{r}-J{r})'.format(r=r),
            '=IF(OR(I{r}="",K{r}=""),"",I{r}-K{r})'.format(r=r),
        ])
    r0, r1 = r_tm_first, r_tm_last
    # Phased totals: only weeks that have actually started contribute, so an
    # unstarted month does not report a phantom target, and a week carrying
    # hours but no target is skipped rather than computing against blank.
    live = lambda col: ('=IF(SUMPRODUCT((I{r0}:I{r1}<>"")*({c}{r0}:{c}{r1}<>""))=0,"",'
                        'SUMPRODUCT((I{r0}:I{r1}<>"")*{c}{r0}:{c}{r1}))'
                        .format(r0=r0, r1=r1, c=col))
    team.append(["MONTH TOTAL", ""] +
                ["=SUM(%s%d:%s%d)" % (c, r0, c, r1) for c in "CDEFGH"] +
                ["=IF(COUNT(I%d:I%d)=0,\"\",SUM(I%d:I%d))" % (r0, r1, r0, r1),
                 live("J"), live("K"), live("L"),
                 '=IF(OR(I{t}=\"\",J{t}=\"\"),\"\",I{t}-J{t})'.format(t=r_tm_total),
                 '=IF(OR(I{t}=\"\",K{t}=\"\"),\"\",I{t}-K{t})'.format(t=r_tm_total)])

    # ---- CROSS-MONTH block sits directly under the Team table (same kind) ----
    xwks = cross_month_weeks(month, year)
    r_cx_title = r_tm_total + 2
    cross = []
    if xwks:
        r_cx_hdr = r_cx_title + 1
        r_cx_first = r_cx_hdr + 1
        r_cx_last = r_cx_first + len(xwks) - 1
        r_cx_total = r_cx_last + 1
        cross = [["CROSS-MONTH WEEKS (SPLIT ACROSS TABS)"], list(CROSS_HDRS)]
        for k, x in enumerate(xwks):
            r = r_cx_first + k
            # Row span of the OTHER tab's share: day N lives at row N+2 there too.
            op0 = r_day_first + x["pdays"][0] - 1
            op1 = r_day_first + x["pdays"][-1] - 1
            tp0 = r_day_first + x["tdays"][0] - 1
            tp1 = r_day_first + x["tdays"][-1] - 1
            ts_ = lambda col: "=SUM(%s%d:%s%d)" % (col, tp0, col, tp1)
            other_side = "%s %d" % (calendar.month_abbr[x["pmonth"]],
                                    x["pdays"][0]) if x["kind"] == "leading" else \
                         "%s %d" % (calendar.month_abbr[x["pmonth"]],
                                    x["pdays"][-1])
            this_side = "%s %d" % (calendar.month_abbr[x["tmonth"]],
                                   x["tdays"][0]) if x["kind"] == "leading" else \
                        "%s %d" % (calendar.month_abbr[x["tmonth"]],
                                   x["tdays"][-1])
            # One total for the other tab's half. Blank when the sibling tab does
            # not exist yet: SUM over a missing sheet errors, so IFERROR returns
            # "" rather than the text "n/a", which would poison any arithmetic.
            other_total = ('=IFERROR(SUM(\'{t}\'!C{p0}:H{p1}),"")'
                           .format(t=x["ptab"], p0=op0, p1=op1))
            cross.append([
                x["label"],
                other_total,
                ts_("E"), ts_("C"), ts_("D"), ts_("G"), ts_("H"),
                # H = other-tab total + this tab's five columns. SUM ignores the
                # text "n/a" from a missing sibling tab, where "+" would raise
                # #VALUE!.
                "=SUM(B{r}:G{r})".format(r=r),
                week_span_target(x, cfg),
                # J = H (week total) - I (target). Blank until hours exist, so a
                # quiet week does not read as a full shortfall.
                '=IF(SUM(B{r}:G{r})=0,"",H{r}-I{r})'.format(r=r),
            ])
        rc0, rc1 = r_cx_first, r_cx_last
        # WEEK TOTAL must be exactly 10 cells to match the header width: the
        # label occupies A, then one total per data column B..J.
        cross.append(["WEEK TOTAL"] +
                     ["=SUM(%s%d:%s%d)" % (c, rc0, c, rc1)
                      for c in ("B", "C", "D", "E", "F", "G", "H", "I", "J")])
    else:
        r_cx_hdr = r_cx_first = r_cx_last = r_cx_total = 0

    # ---- GROUPING: personal (grid, weekly) -> team (team, cross, split) ->
    #      reference (footnotes, key). Keep each group contiguous.
    anchor = r_cx_total or r_tm_total
    r_sp_title = anchor + 2              # Reported Split closes the team group
    r_sp_hdr = r_sp_title + 1
    r_sp_first = r_sp_hdr + 1
    r_sp_last = r_sp_first + len(wk) - 1
    # ---- CATEGORY BAND 3: OTHERS (reference). Footnotes and the Column Key.
    r_sec3 = r_sp_last + 2
    r_foot_first = r_sec3 + 1
    # r_key_title is computed AFTER the foot list exists, so its offset is
    # derived from len(foot) instead of a hardcoded count.

    split = [["REPORTED SPLIT (WHAT WAS SHARED)"], list(SPLIT_HDRS)]
    for i in range(1, len(wk) + 1):
        r = r_sp_first + i - 1
        seed = cfg.get("reported", {}).get(str(i), {})
        split.append([
            "Week %d" % i,
            cfg.get("team_periods", {}).get(str(i), wk[i - 1][2]),
            seed.get("mobeen", ""), seed.get("solat", ""), seed.get("danish", ""),
            '=IF(COUNT(C{r}:E{r})=0,"",SUM(C{r}:E{r}))'.format(r=r),
        ])

    # Footnotes close the reported-vs-actual explanation, directly under the
    # split block they refer to. NOTE: any footnote ADDED or REMOVED here must
    # keep len(foot) equal to meta["n_foot"]; the layout offset and the height
    # plan both derive from n_foot, so a mismatch shifts the Column Key.
    foot = [
        ["* Mobeen column = Mobeen's own MTMPRO hours. Usama (reported) = his "
         "hours already included in a report shared with the client; Usama "
         "(extra) = hours worked after that report, banked for the next week's "
         "head start. Usama joined from Week 3 of "
         "September 2026."],
        ["* Base Target = the standing weekly mark (%dh). Week Target = the "
         "instructed target for that week. Total Hours may exceed either."
         % BASE_WEEK_TARGET],
        ["* Reported to Client is the figure actually shared and may be lower "
         "than Total Hours. The Reported Split block holds the per-person split."],
        ["* Week 3 target was initially 64h. The team reached 68h, Rohan confirmed "
         "68h is the figure to share with the client, so 68.00 is reported while "
         "the instructed target stays 64."],
        ["* Week 4 note: Usama's Tue Sep 22 session with Mobeen (4h) was learning "
         "time, excluded from MTMPRO hours. Usama's Week 4: 25:30 counted, 29:30 "
         "including the learning."],
        ["* Oct 2026 client cut (3 churns, 2 downgrades): the MTMPRO team quota "
         "is 40h/week. Mobeen's personal total stays 40h/week across all projects."],
        ["* MTMPRO split: Mobeen (incl. Usama) covers 32h/week while Solat works "
         "his 8h testing; if Solat is out, Mobeen (incl. Usama) takes the full "
         "40h/week."],
        ["* Cell colours: green = Usama's days already included in a report shared "
         "with the client; unhighlighted days are not yet reported (extra work in "
         "progress / banked)."],
        ["* Reclassification note (2026-11-12): the 6h of Usama sessions in Others "
         "(Sep 16/29/30, 2h each) qualify as MTMPRO UNTRACKED per the 2026-09-25 "
         "rule (Usama works MTMPRO). Held in Others as logged, pending the HR/Rohan "
         "decision; if reclassified they move to column E (MTMPRO month 138.16, "
         "month total unchanged 187.17). Sep 8 (2h laptop migration) and Sep 17 "
         "(1.5h mixed meetings) stay in Others."],
    ]

    # Column Key is reference and goes last: it sits 2 rows below the LAST
    # footnote. Derived from len(foot) so adding a note never strands it.
    r_key_title = r_foot_first + len(foot) - 1 + 2

    r_key_hdr = r_key_title + 1
    key = [["COLUMN KEY"], list(KEY_HDRS)]
    key.append(["Extra vs Base",
                "How far the team ran past the standing %dh weekly mark" % BASE_WEEK_TARGET,
                "Total Hours - Base Target", "68.99 - 50 = +18.99"])
    key.append(["Extra vs Week Target",
                "How far the team ran past the target instructed for that week",
                "Total Hours - Week Target", "68.99 - 64 = +4.99"])

    meta = dict(ndays=ndays, nweeks=len(wk), tab=tab_name(month, year),
                usama=usama,
                r_day_first=r_day_first, r_day_last=r_day_last,
                r_sec1=r_sec1, r_sec2=r_sec2, r_sec3=r_sec3,
                r_wk_title=r_wk_title, r_wk_hdr=r_wk_hdr, r_wk_first=r_wk_first,
                r_wk_last=r_wk_last, r_wk_total=r_wk_total,
                r_tm_title=r_tm_title, r_tm_hdr=r_tm_hdr, r_tm_first=r_tm_first,
                r_tm_last=r_tm_last, r_tm_total=r_tm_total,
                r_foot_first=r_foot_first, n_foot=len(foot),
                r_sp_title=r_sp_title, r_sp_hdr=r_sp_hdr, r_sp_first=r_sp_first,
                r_sp_last=r_sp_last,
                r_cx_title=r_cx_title, r_cx_hdr=r_cx_hdr, r_cx_first=r_cx_first,
                r_cx_last=r_cx_last, r_cx_total=r_cx_total, ncross=len(xwks),
                r_key_title=r_key_title, r_key_hdr=r_key_hdr,
                weeks=wk, cross=xwks, month=month, year=year)
    # A1:H1 is MERGED, and a merged range displays only its top-left cell, so the
    # banner text must be written to A1. Writing it to C1 leaves the banner blank.
    title = [["MOBEEN WORKED HOURS "]]
    headers = [list(DAILY_HDRS) + (USAMA_HDRS if usama else [])]
    sections = [
        (r_sec1, "1  MOBEEN ONLY"),
        (r_sec2, "2  MTMPRO"),
        (r_sec3, "3  OTHERS"),
    ]
    return (title, headers, day_labels, weekly, team, split, foot, cross, key,
            sections, meta)


def week_target(month, year, lo, hi, cfg, elapsed_only=False):
    """week_daily_target clamped to the client-cut weekly cap once it applies."""
    t = week_daily_target(month, year, lo, hi, cfg, elapsed_only=elapsed_only)
    if date(year, month, lo) >= WEEKLY_TARGET_CAP_FROM:
        t = min(t, WEEKLY_TARGET_CAP)
    return t


def standing_base(month, year, lo):
    """Standing weekly team mark: 50h, or 40h from the Oct 12 2026 cut week."""
    return (BASE_WEEK_TARGET_CUT if date(year, month, lo) >= WEEKLY_TARGET_CAP_FROM
            else BASE_WEEK_TARGET)


def week_daily_target(month, year, lo, hi, cfg, elapsed_only=False):
    """Weekday-only target for a week, respecting per-date overrides.

    elapsed_only: clamp the end of the range to TODAY. A week in progress must
    be compared against the days that have actually happened, or a Tuesday
    reads as 32h short against the whole week. Finished and future weeks are
    unaffected (their hi is already past or ahead of today). Mirrors the
    elapsed-day clamp that month_day_target already applies.
    """
    ov = cfg.get("day_targets", {})
    hi_eff = hi
    today = date.today()
    if elapsed_only:
        # Only clamp when the week actually straddles today; a finished week
        # keeps its full target, and an unstarted week yields 0.
        lo_d, hi_d = date(year, month, lo), date(year, month, hi)
        if hi_d > today:
            hi_eff = min(hi, today.day) if (year, month) == (today.year, today.month) else 0
        if lo_d > today:
            hi_eff = lo - 1          # entirely in the future: no elapsed days
    total = 0
    for d in range(lo, hi_eff + 1):
        if d < 1:
            continue
        dt = date(year, month, d)
        if dt.weekday() >= 5:
            continue
        total += int(ov.get(dt.isoformat(), WORKDAY_TARGET))
    return total


def week_started(month, year, lo):
    """True once the calendar week containing `lo` has begun.

    The Monday can sit in the previous month (a leading-spill week), so walk
    backwards from `lo` instead of scanning forward inside this month, which
    used to land on the last in-month day and wrongly blank the target.
    """
    y, m, d = year, month, lo
    while calendar.weekday(y, m, d) != 0:            # Mon=0
        d -= 1
        if d < 1:                                    # step into the previous month
            m -= 1
            if m < 1:
                m, y = 12, y - 1
            d = calendar.monthrange(y, m)[1]
    return date(y, m, d) <= date.today()


def target_cell(month, year, hi, tgt, row, lo=None):
    """Blank until the week has begun; the week's in-month target once started."""
    if not week_started(month, year, lo if lo is not None else max(1, hi - 6)):
        return ""
    return tgt


def month_day_target(month, year, cfg):
    """Sum of per-week targets, elapsed weeks only, weekly cap applied.

    The cap must clamp each week on its own: clamping the month total instead
    would wrongly cap a whole month at the single-week limit."""
    return sum(week_target(month, year, lo, hi, cfg, elapsed_only=True)
               for lo, hi, _ in weeks_of(month, year))


# --------------------------------------------------------------- styling -----
def height_plan(meta):
    """Canonical row height for EVERY row from the grid down to the Column Key.

    Row heights are DIMENSION properties, not cell formats, so they survive
    `reset_block_area()` and every value clear. Without an explicit plan a block
    that moves down inherits the height of whatever occupied that row before, and
    the tables drift apart. Live example after the category bands pushed the
    summary blocks down: the Team table's Week 5 row was 26px and its MONTH TOTAL
    was 34px, both leftovers from the previous layout's footnotes and title.

    The plan sweeps the whole summary area to a thin default first, then lays the
    canonical heights over it, so a row that is no longer used can never keep a
    stale height. Values are 1-indexed rows.

    Contract (matched across all tables so they read as one system):
      band 30 | title 34 | header 46 | data 21 | total 21
    The Column Key is a notes table: its data rows carry 3-line wrapped text so
    they need 48, and its note rows 36.
    """
    plan = {}

    def put(r0, r1, px):
        for r in range(r0, r1 + 1):
            plan[r] = px

    # Day grid (pinned to rows 1-32 by toptracker_sync.py).
    put(1, 1, 34)
    put(2, 2, 46)
    put(meta["r_day_first"], meta["r_day_last"], 21)
    # Thin, uniform spacer baseline for the entire summary area.
    put(meta["r_day_last"] + 1, meta["r_key_hdr"] + 4, 12)
    # Bands.
    for r_sec in (meta["r_sec1"], meta["r_sec2"], meta["r_sec3"]):
        put(r_sec, r_sec, 30)
    # Weekly Summary.
    put(meta["r_wk_title"], meta["r_wk_title"], 34)
    put(meta["r_wk_hdr"], meta["r_wk_hdr"], 46)
    put(meta["r_wk_first"], meta["r_wk_total"], 21)
    # Team MTMPRO Hours (the reference table everything else matches).
    put(meta["r_tm_title"], meta["r_tm_title"], 34)
    put(meta["r_tm_hdr"], meta["r_tm_hdr"], 46)
    put(meta["r_tm_first"], meta["r_tm_total"], 21)
    # Cross-Month Weeks (only present when a week is split).
    if meta["ncross"]:
        put(meta["r_cx_title"], meta["r_cx_title"], 34)
        put(meta["r_cx_hdr"], meta["r_cx_hdr"], 46)
        put(meta["r_cx_first"], meta["r_cx_total"], 21)
    # Reported Split.
    put(meta["r_sp_title"], meta["r_sp_title"], 34)
    put(meta["r_sp_hdr"], meta["r_sp_hdr"], 46)
    put(meta["r_sp_first"], meta["r_sp_last"], 21)
    # Footnotes: one row each. Count comes from n_foot so adding a note can
    # never leave a stray row inside the block (or push the Column Key off).
    put(meta["r_foot_first"], meta["r_foot_first"] + meta["n_foot"] - 1, 26)
    # Column Key: the ONE intentional exception, because it holds prose rather
    # than hours. Its cells wrap to three lines (B is a 62-char description in a
    # 215px column), so its two data rows need 48 or the text is clipped by the
    # fixed row height. Header is the standard 46.
    put(meta["r_key_title"], meta["r_key_title"], 34)
    put(meta["r_key_hdr"], meta["r_key_hdr"], 46)
    put(meta["r_key_hdr"] + 1, meta["r_key_hdr"] + 2, 48)
    return plan


def style_requests(sid, meta):
    def R(r0, r1, c0, c1):
        return {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1,
                "startColumnIndex": c0, "endColumnIndex": c1}

    def fmt(r0, r1, c0, c1, **k):
        f, fl = {}, []
        if "bg" in k:
            f["backgroundColor"] = k["bg"]; fl.append("userEnteredFormat.backgroundColor")
        tf = {}
        for key, name in (("bold", "bold"), ("size", "fontSize"),
                          ("italic", "italic"), ("fg", "foregroundColor")):
            if key in k:
                tf[name] = k[key]
        if tf:
            f["textFormat"] = tf
            fl += ["userEnteredFormat.textFormat." + t for t in tf]
        if "pat" in k:
            f["numberFormat"] = {"type": "NUMBER", "pattern": k["pat"]}
            fl.append("userEnteredFormat.numberFormat")
        if "align" in k:
            f["horizontalAlignment"] = k["align"]
            fl.append("userEnteredFormat.horizontalAlignment")
        f["verticalAlignment"] = "MIDDLE"
        f["wrapStrategy"] = "WRAP"
        fl += ["userEnteredFormat.verticalAlignment", "userEnteredFormat.wrapStrategy"]
        return {"repeatCell": {"range": R(r0, r1, c0, c1),
                               "cell": {"userEnteredFormat": f},
                               "fields": ",".join(fl)}}

    def borders(r0, r1, c0, c1):
        return {"updateBorders": {"range": R(r0, r1, c0, c1), "top": MID_B,
                                  "bottom": MID_B, "left": MID_B, "right": MID_B,
                                  "innerHorizontal": LIGHT_B, "innerVertical": LIGHT_B}}

    def height(r0, r1, px):
        return {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS",
                      "startIndex": r0, "endIndex": r1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}}

    def width(c, px):
        return {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}}

    def merge(r0, r1, c0, c1):
        return {"mergeCells": {"range": R(r0, r1, c0, c1), "mergeType": "MERGE_ALL"}}

    q = []
    # Row heights come from ONE authoritative plan (see height_plan). Heights are
    # dimension properties and survive format/value resets, so scattering
    # height() calls through this function let stale heights win and the tables
    # drifted apart. Apply the plan first; nothing below may set a height.
    hp = height_plan(meta)
    for r in sorted(hp):
        q.append(height(r - 1, r, hp[r]))
    # CATEGORY BANDS: a light grey bar with a navy ordinal, one per section.
    # These sit in column A only (not merged) so they are visually distinct from
    # the navy table titles and cannot be confused with a table.
    for r_sec in (meta["r_sec1"], meta["r_sec2"], meta["r_sec3"]):
        q.append(fmt(r_sec - 1, r_sec, 0, 12, bg=NOTE_BG, bold=True, size=11,
                     fg=NAVY, align="LEFT"))
    # daily grid
    q.append(fmt(0, 1, 0, 8, bg=NAVY, bold=True, size=12, fg=WHITE_TX, align="CENTER"))
    q.append(fmt(1, 2, 0, 8, bg=STEEL, bold=True, fg=WHITE_TX, align="CENTER"))
    q.append(fmt(2, meta["r_day_last"], 0, 8, bg=WHITE, fg=INK, size=10, align="CENTER"))
    for d in range(1, meta["ndays"] + 1):
        if date(meta["year"], meta["month"], d).weekday() >= 5:
            row = meta["r_day_first"] + d - 2
            q.append(fmt(row, row + 1, 0, 8, bg=WEEKEND, fg=WEEKEND_TX, italic=True))
    q.append(borders(0, meta["r_day_last"], 0, 8))
    # Day-grid banner (row 1, A-H). clear_merges unmerges it every run, so this
    # merge is deterministic and cannot accumulate.
    q.append(merge(0, 1, 0, 8))
    if meta.get("usama"):
        # Usama watched columns (Oct 2026+): banner, steel header, day formats,
        # weekend pass, and the block's own border box.
        q.append(fmt(0, 1, 8, 11, bg=USAMA_BANNER, bold=True, fg=WHITE_TX, align="CENTER"))
        q.append(merge(0, 1, 8, 11))
        q.append(fmt(1, 2, 8, 11, bg=STEEL, bold=True, fg=WHITE_TX, align="CENTER"))
        q.append(fmt(2, meta["r_day_last"], 8, 11, bg=WHITE, fg=INK, size=10, align="CENTER"))
        q.append(fmt(2, meta["r_day_last"], 8, 10, pat=PLAIN0))
        q.append(fmt(2, meta["r_day_last"], 10, 11, pat=SIGNED))
        for d in range(1, meta["ndays"] + 1):
            if date(meta["year"], meta["month"], d).weekday() >= 5:
                row = meta["r_day_first"] + d - 2
                q.append(fmt(row, row + 1, 8, 11, bg=WEEKEND, fg=WEEKEND_TX, italic=True))
        q.append(borders(1, meta["r_day_last"], 8, 11))
    # weekly summary
    q.append(fmt(meta["r_wk_title"] - 1, meta["r_wk_title"], 0, 10, bg=NAVY, bold=True,
                 size=12, fg=WHITE_TX, align="CENTER"))
    q.append(fmt(meta["r_wk_hdr"] - 1, meta["r_wk_hdr"], 0, 10, bg=STEEL, bold=True,
                 fg=WHITE_TX, align="CENTER"))
    q.append(fmt(meta["r_wk_first"] - 1, meta["r_wk_last"], 0, 10, bg=WHITE, fg=INK,
                 size=10, align="CENTER"))
    q.append(fmt(meta["r_wk_first"] - 1, meta["r_wk_total"], 2, 8, pat=PLAIN0))
    q.append(fmt(meta["r_wk_last"], meta["r_wk_total"], 0, 10, bg=TOTBG, bold=True,
                 fg=NAVY, align="CENTER"))
    q.append(fmt(meta["r_wk_first"] - 1, meta["r_wk_total"], 2, 8, pat=PLAIN0))
    q.append(fmt(meta["r_wk_first"] - 1, meta["r_wk_total"], 8, 9, pat=PLAIN0))
    q.append(fmt(meta["r_wk_first"] - 1, meta["r_wk_total"], 9, 10, pat=SIGNED))
    q.append(borders(meta["r_wk_title"] - 1, meta["r_wk_total"], 0, 10))
    # Banner titles span their table's width, matching the day-grid banner.
    q.append(merge(meta["r_wk_title"] - 1, meta["r_wk_title"], 0, 10))
    # team table
    q.append(fmt(meta["r_tm_title"] - 1, meta["r_tm_title"], 0, 14, bg=NAVY, bold=True,
                 size=12, fg=WHITE_TX, align="CENTER"))
    q.append(fmt(meta["r_tm_hdr"] - 1, meta["r_tm_hdr"], 0, 14, bg=STEEL, bold=True,
                 fg=WHITE_TX, align="CENTER"))
    q.append(fmt(meta["r_tm_first"] - 1, meta["r_tm_last"], 0, 14, bg=WHITE, fg=INK,
                 size=10, align="CENTER"))
    # Numeric block: C..I plain, J..L (targets + reported) plain, M..N signed.
    q.append(fmt(meta["r_tm_first"] - 1, meta["r_tm_last"], 2, 9, pat=PLAIN0))
    q.append(fmt(meta["r_tm_first"] - 1, meta["r_tm_last"], 9, 12, pat=PLAIN0))
    q.append(fmt(meta["r_tm_first"] - 1, meta["r_tm_last"], 12, 14, pat=SIGNED))
    q.append(fmt(meta["r_tm_last"], meta["r_tm_total"], 0, 14, bg=TOTBG, bold=True,
                 fg=NAVY, align="CENTER"))
    q.append(fmt(meta["r_tm_last"], meta["r_tm_total"], 2, 9, pat=PLAIN0))
    q.append(fmt(meta["r_tm_last"], meta["r_tm_total"], 9, 12, pat=PLAIN0))
    q.append(fmt(meta["r_tm_last"], meta["r_tm_total"], 12, 14, pat=SIGNED))
    q.append(borders(meta["r_tm_title"] - 1, meta["r_tm_total"], 0, 14))
    q.append(merge(meta["r_tm_title"] - 1, meta["r_tm_title"], 0, 14))
    # footnotes sit AFTER the split block and BEFORE the Column Key.
    # r_foot_first is 1-indexed, merge/height take 0-indexed rows: use r-1 as the
    # start or the merge lands one row below the text (leaving footnote 1
    # unmerged and a stray merge on the blank row after footnote 3).
    q.append(fmt(meta["r_foot_first"] - 1, meta["r_key_title"] - 1, 0, 12, fg=DIM,
                 italic=True, size=9, align="LEFT"))
    for k in range(meta["n_foot"]):
        q.append(merge(meta["r_foot_first"] - 1 + k, meta["r_foot_first"] + k, 0, 12))
    # reported split. NOTE: 0-indexed rows; r_* values are 1-indexed, so every
    # range uses r-1 as its start. Off-by-one here collapsed the header row.
    q.append(fmt(meta["r_sp_title"] - 1, meta["r_sp_title"], 0, 6, bg=NAVY, bold=True,
                 size=12, fg=WHITE_TX, align="CENTER"))
    q.append(merge(meta["r_sp_title"] - 1, meta["r_sp_title"], 0, 6))
    q.append(fmt(meta["r_sp_hdr"] - 1, meta["r_sp_hdr"], 0, 6, bg=STEEL, bold=True,
                 fg=WHITE_TX, align="CENTER"))
    q.append(fmt(meta["r_sp_first"] - 1, meta["r_sp_last"], 0, 6, bg=WHITE, fg=INK,
                 size=10, align="CENTER"))
    q.append(fmt(meta["r_sp_first"] - 1, meta["r_sp_last"], 2, 6, pat=PLAIN0))
    q.append(borders(meta["r_sp_title"] - 1, meta["r_sp_last"], 0, 6))
    # cross-month block (only when the month has a split week). Width is 11
    # columns (A-K) so it never exceeds the Team table's 13.
    if meta["ncross"]:
        kr = meta["r_cx_title"] - 1
        q.append(fmt(kr, kr + 1, 0, 11, bg=NAVY, bold=True, size=12, fg=WHITE_TX,
                     align="CENTER"))
        # Header 10pt to match the Team table (was inheriting a 9pt residue).
        q.append(fmt(kr + 1, kr + 2, 0, 11, bg=STEEL, bold=True, size=10,
                     fg=WHITE_TX, align="CENTER"))
        # Data rows: not bold, 10pt, matching Team. WEEK TOTAL row (r_cx_total)
        # is the bold summary band.
        q.append(fmt(kr + 2, meta["r_cx_total"], 0, 11, bg=WHITE, fg=INK, size=10,
                     bold=False, align="CENTER"))
        q.append(fmt(kr + 2, meta["r_cx_total"], 1, 11, pat=PLAIN0))
        q.append(fmt(kr + 2, meta["r_cx_total"], 9, 10, pat=SIGNED))
        q.append(fmt(meta["r_cx_total"] - 1, meta["r_cx_total"], 0, 11, bg=TOTBG,
                     bold=True, fg=NAVY, align="CENTER"))
        q.append(borders(kr, meta["r_cx_total"], 0, 11))
        q.append(merge(kr, kr + 1, 0, 11))
    # Column Key: title, header, two data rows. An earlier version also styled and
    # merged two NOTE rows under it, but no text was ever written to them, so they
    # rendered as two grey rows with stray A:D merges on blank cells. The three
    # footnotes above already carry the notes; the empty rows are gone.
    kr = meta["r_key_title"] - 1
    q.append(fmt(kr, kr + 1, 0, 4, bg=NAVY, bold=True, size=12, fg=WHITE_TX, align="CENTER"))
    q.append(fmt(kr + 1, kr + 2, 0, 4, bg=STEEL, bold=True, fg=WHITE_TX, align="CENTER"))
    q.append(fmt(kr + 2, kr + 4, 0, 4, bg=WHITE, fg=INK, size=10, align="LEFT"))
    q.append(borders(kr, kr + 3, 0, 4))
    q.append(merge(kr, kr + 1, 0, 4))
    for c, px in enumerate([135, 215, 175, 175, 160, 150, 120, 130, 118, 160, 165, 180, 175, 175]):
        q.append(width(c, px))
    # COLOUR SCHEME (Usama only): green marks Usama days already included in a
    # report shared with the client. Only the daily I/J rule exists; it carries
    # a DATE cutoff that the report routine refreshes each time a report goes
    # out (days after the cutoff stay unhighlighted = extra work in progress /
    # banked). Built with a past cutoff so a fresh month starts unhighlighted.
    # The team table is NOT coloured (user's explicit rule: no highlight on the
    # Usama (reported) or (extra) columns).
    def cf(r0, r1, c0, c1, formula, color, index):
        return {"addConditionalFormatRule": {
            "rule": {
                "ranges": [R(r0, r1, c0, c1)],
                "booleanRule": {"condition": {"type": "CUSTOM_FORMULA",
                                              "values": [{"userEnteredValue": formula}]},
                                "format": {"backgroundColor": color}}},
            "index": index}}

    q.append(cf(meta["r_day_first"] - 1, meta["r_day_last"], 8, 10,
                '=AND($I%d<>"",$A%d<=DATE(1900,1,1))'
                % (meta["r_day_first"], meta["r_day_first"]), GREEN_CELL, 0))
    # Week-boundary descriptions in column L (quota completed / extra starts)
    # are written by the report routine per week; the builder does not place them.
    q.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {"hideGridlines": True}},
        "fields": "gridProperties.hideGridlines"}})
    return q


def verify_heights(svc, sid, meta):
    """Assert every row's live height matches height_plan. Returns diffs.

    Heights are the one property that no value/format reset touches, so they are
    the most likely thing to drift after a layout change. Checking them in the
    build turns a silent visual regression into a reported failure.
    """
    plan = height_plan(meta)
    lo, hi = 1, meta["r_key_hdr"] + 2
    d = svc.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID, includeGridData=True,
        ranges=["%s!A%d:A%d" % (meta["tab"], lo, hi)],
        fields="sheets.data.rowMetadata(pixelSize)").execute()
    live = d["sheets"][0]["data"][0].get("rowMetadata", [])
    diffs = []
    for r, px in sorted(plan.items()):
        if r < lo or r > hi:
            continue
        got = live[r - lo].get("pixelSize") if r - lo < len(live) else None
        if got != px:
            diffs.append({"row": r, "expected": px, "actual": got})
    return diffs, len(plan)


def reset_block_area(svc, sid, meta):
    """Reset ALL formatting in the script-owned area to a clean baseline.

    Formats outlive values, and they also outlive a shrinking layout: an earlier
    15-column Cross-Month block left its text format behind inside A-L, so the
    header rendered 9pt instead of 10pt, data rows stayed bold, and L52 kept a
    12pt bold title fragment. Clearing only fills/borders (or only merges) does
    not touch textFormat, so residue accumulated run after run.

    Every `--apply` now wipes the area to the baseline below and then applies the
    intended styles, which makes the result deterministic and makes the two
    tables match cell for cell.
    """
    first = meta["r_day_last"]                 # 0-indexed, first row after grid
    last = meta["r_key_title"] + 8
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={
        "requests": [{"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": first, "endRowIndex": last,
                      "startColumnIndex": 0, "endColumnIndex": 15},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "textFormat": {"bold": False, "italic": False, "fontSize": 10,
                               "foregroundColor": {"red": 0.0, "green": 0.0,
                                                   "blue": 0.0}},
                "numberFormat": {"type": "NUMBER", "pattern": "0.00;-0.00;"},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "OVERFLOW_CELL",
                "borders": {"top": {"style": "NONE"}, "bottom": {"style": "NONE"},
                            "left": {"style": "NONE"}, "right": {"style": "NONE"}}}},
            "fields": ("userEnteredFormat.backgroundColor,"
                       "userEnteredFormat.textFormat,"
                       "userEnteredFormat.numberFormat,"
                       "userEnteredFormat.horizontalAlignment,"
                       "userEnteredFormat.verticalAlignment,"
                       "userEnteredFormat.wrapStrategy,"
                       "userEnteredFormat.borders")}}]}).execute()
    return {"format_reset_rows": [first + 1, last], "cols": "A-O"}


def clear_stale_below(svc, tab, meta):
    """Wipe script-owned summary rows between the day grid and the Column Key.

    Without this, re-running leaves the previous layout's rows in place (a
    31-day month or a newly-appearing cross-month block moves every block down),
    so the tab shows duplicated tables.

    SAFETY: both bounds are absolute layout positions. An earlier version derived
    the end bound from the number of populated rows returned by a read; because a
    partly-filled month returns values only up to its last filled row, that span
    was too short. Never size a clear from counted data.

    Only VALUES are cleared, so a table that once spanned more columns (the
    Cross-Month block was 15 wide, now 11) keeps its old fills and borders out
    to the wider range, which reads as a table overhanging its content. The
    follow-up reset_wide_block_format() clears those trailing formats.
    """
    first = meta["r_day_last"] + 1          # first summary row (after the grid)
    last = meta["r_key_hdr"] + 8            # Column Key bottom, absolute
    svc.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!A%d:O%d" % (tab, first, last),
        body={}).execute()
    return {"cleared_from": first, "cleared_to": last}


def reset_wide_block_format(svc, sid, meta):
    """Strip fills and borders from columns M..O below the day grid.

    Every block now ends by column M (Team = 13 wide) or earlier. When a block
    used to be wider, its old background/border formatting survives in L..O and
    the sheet shows a header-coloured band extending past the last real column.
    Clear that band so each table's width matches its columns exactly.
    """
    first = meta["r_day_last"]                 # 0-indexed first summary row
    last = meta["r_key_hdr"] + 8
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={
        "requests": [
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": first,
                          "endRowIndex": last, "startColumnIndex": 12,
                          "endColumnIndex": 15},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                    "borders": {"top": {"style": "NONE"},
                                "bottom": {"style": "NONE"},
                                "left": {"style": "NONE"},
                                "right": {"style": "NONE"}}}},
                "fields": ("userEnteredFormat.backgroundColor,"
                           "userEnteredFormat.borders")}}]}).execute()
    return {"format_cleared_cols": "M-O", "rows": [first + 1, last]}


def clear_merges(svc, sid, meta):
    """Unmerge the whole script-owned area, banner row included, before re-merging.

    Merges accumulate: each run added its own merges while the previous run's
    stayed, because a merge is keyed by ROW RANGE and the blocks move down as
    layouts change. Leftovers landed on top of live tables, hiding cells (a stale
    A:D merge hid the Mobeen/Solat columns in the Reported Split). Always unmerge
    the script-owned area first so only the current layout's merges exist.
    """
    first = 0    # include the banner row; style_requests re-merges it every run
    last = meta["r_key_hdr"] + 12
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={
        "requests": [{"unmergeCells": {"range": {
            "sheetId": sid, "startRowIndex": first, "endRowIndex": last,
            "startColumnIndex": 0, "endColumnIndex": 15}}}]}).execute()
    return {"unmerged_from_row": first + 1, "unmerged_to_row": last}


def snapshot_grid(svc, tab, meta):
    """Read the day grid (A1:Hlast-day) as the write-safety baseline."""
    return svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!A1:H%d" % (tab, meta["r_day_last"]),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])


def verify_grid(svc, tab, meta, before):
    """True when the day grid is unchanged. Guards against writes reaching D:H.

    A rebuild must never alter the grid; if any cell differs, the caller aborts
    and the operator restores from the snapshot. This is the check that would
    have caught the incident that blanked D:H.
    """
    after = snapshot_grid(svc, tab, meta)
    n = max(len(before), len(after))
    diffs = []
    for i in range(n):
        b = list(before[i]) if i < len(before) else []
        a = list(after[i]) if i < len(after) else []
        for c in range(8):
            bv = b[c] if c < len(b) else ""
            av = a[c] if c < len(a) else ""
            if str(bv) != str(av):
                diffs.append({"row": i + 1, "col": chr(65 + c),
                              "before": bv, "after": av})
    return (not diffs), diffs


def snapshot_usama(svc, tab, meta):
    "Read the Usama fed data cells (I3:J lastday) as the write-safety baseline."
    return svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!I%d:J%d" % (tab, meta["r_day_first"], meta["r_day_last"]),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])


def verify_usama(svc, tab, meta, before):
    "True when the Usama fed cells are unchanged. Mirrors verify_grid."
    after = snapshot_usama(svc, tab, meta)
    n = max(len(before), len(after))
    diffs = []
    for i in range(n):
        b = list(before[i]) if i < len(before) else []
        a = list(after[i]) if i < len(after) else []
        for c in range(2):
            bv = b[c] if c < len(b) else ""
            av = a[c] if c < len(a) else ""
            if str(bv) != str(av):
                diffs.append({"row": meta["r_day_first"] + i, "col": chr(ord("I") + c),
                              "before": bv, "after": av})
    return (not diffs), diffs


def seed_usama_diff(svc, tab, meta):
    "Seed the USAMA DIFF formulas in column K; never clobber existing cells."
    r0, r1 = meta["r_day_first"], meta["r_day_last"]
    cur = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="%s!K%d:K%d" % (tab, r0, r1),
        valueRenderOption="FORMULA").execute().get("values", [])
    col, seeded = [], 0
    for i, r in enumerate(range(r0, r1 + 1)):
        val = cur[i][0] if i < len(cur) and cur[i] else ""
        if val == "":
            val = '=IF(OR(I{r}="",J{r}=""),"",I{r}-J{r})'.format(r=r)
            seeded += 1
        col.append([val])
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range="%s!K%d:K%d" % (tab, r0, r1),
        body={"values": col}, valueInputOption="USER_ENTERED").execute()
    return {"k_seeded": seeded, "k_rows": [r0, r1]}


def save_snapshot(meta, grid, path=None):
    tab = meta["tab"]
    path = path or os.path.expanduser("~/.hermes/cache/sheets/%s_grid.json" % tab)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"tab": tab, "rows": grid}, f, indent=1)
    return path


# ---------------------------------------------------------------- writing ----
def write_block(svc, tab, start_row, block, protect_cols=None, start_col=1):
    """Write a row block. Every element must already be a list of cells.

    protect_cols: 1-indexed columns that this block must not touch. Used to keep
    any day-row write away from D:H, where the hour data lives. A block that
    would span a protected column is truncated to the column before it, so a
    mis-shaped row can never blank out an hour cell.
    start_col: first column of the write (1 = A). The Usama banner is written
    with start_col=9 (column I) so it can never touch the Mobeen banner cells.
    """
    if not block:
        return
    if any(isinstance(r, str) for r in block):
        raise TypeError("write_block expects list-of-lists rows, got a bare string")
    ncols = max(len(r) for r in block)
    if protect_cols:
        lowest = min(protect_cols)
        if ncols >= lowest:
            ncols = lowest - 1
            if ncols <= 0:
                raise ValueError("block width would reach protected column %d" % lowest)
            block = [list(r)[:ncols] for r in block]
    block = [list(r) + [""] * (ncols - len(r)) for r in block]
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="%s!%s%d:%s%d" % (tab, chr(ord("A") + start_col - 1), start_row,
                                chr(ord("A") + start_col - 1 + ncols - 1),
                                start_row + len(block) - 1),
        body={"values": block}, valueInputOption="USER_ENTERED").execute()


def ensure_tab(svc, tab):
    info = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in info["sheets"]:
        if s["properties"]["title"] == tab:
            return s["properties"]["sheetId"], False
    res = svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={
        "requests": [{"addSheet": {"properties": {"title": tab}}}]}).execute()
    return res["replies"][0]["addSheet"]["properties"]["sheetId"], True


def report_missing(svc, tab, meta, cfg):
    """Every weekly/team cell still empty for an ELAPSED week. JSON out.

    Reads the tab live (never a hard-coded sheet layout) so the answer stays
    correct when rows shift, e.g. when a 31-day month or a cross-month block
    moves the tables down.
    """
    tab_data = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="%s!A1:O%d" % (tab, meta["r_key_hdr"]),
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])

    def cell(row, col):                                # row/col are 1-indexed
        if row - 1 >= len(tab_data):
            return ""
        r = tab_data[row - 1]
        return r[col - 1] if col - 1 < len(r) else ""

    def team_row_of(label):
        """Locate a team-table row by its Week cell, not by an assumed offset."""
        for i in range(meta["r_tm_first"], meta["r_tm_last"] + 1):
            if str(cell(i, 1)).strip() == label:
                return i
        return None

    today = date.today()
    missing = []
    for i, (lo, hi, lbl) in enumerate(meta["weeks"], start=1):
        if not week_started(meta["month"], meta["year"], lo):
            continue                                   # week has not started
        label = "Week %d" % i
        r = team_row_of(label)
        if r:
            # Only actually-tracked people. "Other" is optional and never
            # flagged, or the list is noise every single week.
            for col, name in ((3, "Mobeen"), (4, "Usama (reported)"),
                              (6, "Solat"), (7, "Danish")):
                if not cell(r, col):
                    missing.append({"block": "team", "week": i, "period": lbl,
                                    "person": name,
                                    "cell": "%s%d" % (chr(64 + col), r)})
            if not cell(r, 12):
                missing.append({"block": "team", "week": i, "period": lbl,
                                "person": "Reported to Client",
                                "cell": "L%d" % r})
        rs = meta["r_sp_first"] + i - 1
        for col, name in ((3, "Mobeen"), (4, "Solat"), (5, "Danish")):
            if not cell(rs, col):
                missing.append({"block": "reported_split", "week": i,
                                "period": lbl, "person": name,
                                "cell": "%s%d" % (chr(64 + col), rs)})
        # daily gaps inside an elapsed week
        for d in range(lo, hi + 1):
            dt = date(meta["year"], meta["month"], d)
            if dt > today or dt.weekday() >= 5:
                continue
            dr = meta["r_day_first"] + d - 1
            if not cell(dr, 4) and not cell(dr, 5) and not cell(dr, 8):
                missing.append({"block": "daily", "date": dt.isoformat(),
                                "day": calendar.day_name[dt.weekday()],
                                "cell": "D%d/E%d/H%d" % (dr, dr, dr)})
    # cross-month rows: flag only when the sibling tab is reachable but its
    # half is empty AND this tab has no hours either (nothing to report yet).
    for k in range(meta["ncross"]):
        r = meta["r_cx_first"] + k
        if not cell(r, 1):
            continue
        if str(cell(r, 13)).strip() in ("", "n/a") and not any(
                str(cell(r, c)).strip() for c in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)):
            missing.append({"block": "cross_month", "week": cell(r, 1),
                            "person": "both halves",
                            "cell": "C%d:L%d" % (r, r)})
    return {"tab": tab, "today": today.isoformat(), "missing": missing,
            "count": len(missing)}


def main():
    global SPREADSHEET_ID

    ap = argparse.ArgumentParser()
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--config")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-missing", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="Required to write. Without it the run is read-only.")
    ap.add_argument("--snapshot", action="store_true",
                    help="Save the day grid to ~/.hermes/cache/sheets/ and exit.")
    ap.add_argument("--force", action="store_true",
                    help="Write even if the grid differs from the snapshot.")
    ap.add_argument("--spreadsheet", default=None,
                    help="Override the target spreadsheet id (scratch-sheet testing).")
    a = ap.parse_args()

    if a.spreadsheet:
        SPREADSHEET_ID = a.spreadsheet

    cfg = json.load(open(a.config)) if a.config else {}
    tab = tab_name(a.month, a.year)

    if (a.year, a.month) < NEW_LAYOUT_FROM:
        print(json.dumps({"error": "month predates the summary-block layout",
                          "tab": tab}, indent=2))
        return 1

    title, headers, day_labels, weekly, team, split, foot, cross, key, sections, meta = \
        build_rows(a.month, a.year, cfg)
    if a.dry_run:
        print(json.dumps({"tab": tab, "meta": {k: v for k, v in meta.items()
                                               if k != "weeks"}, "blocks": {
            "day_rows": len(day_labels), "weekly_rows": len(weekly),
            "team_rows": len(team), "split_rows": len(split),
            "cross_rows": len(cross), "key_rows": len(key)}}, indent=2))
        return 0

    svc = build("sheets", "v4", credentials=auth())

    if a.snapshot:
        svc_info = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        if not any(s["properties"]["title"] == tab for s in svc_info["sheets"]):
            print(json.dumps({"error": "tab does not exist", "tab": tab}, indent=2))
            return 1
        path = save_snapshot(meta, snapshot_grid(svc, tab, meta))
        print(json.dumps({"tab": tab, "snapshot": path, "status": "saved"},
                         indent=2))
        return 0

    if a.report_missing:
        print(json.dumps(report_missing(svc, tab, meta, cfg), indent=2))
        return 0

    if not a.apply:
        print(json.dumps({
            "tab": tab, "status": "refused",
            "reason": "writing requires --apply (read-only by default)",
            "hint": "run with --snapshot first, then --apply"},
            indent=2))
        return 1

    sid, created = ensure_tab(svc, tab)
    # Safety: capture the grid, write, then prove the grid is untouched. Any
    # difference means a write reached the hour columns; restore from the
    # snapshot path printed below and fix the script before retrying.
    before = snapshot_grid(svc, tab, meta)
    ubefore = snapshot_usama(svc, tab, meta) if meta.get("usama") else None
    snap_path = save_snapshot(meta, before)

    # A1 is the banner row (merged C1:H1 styling lives there); write only the
    # three real title cells, never a padded row, or the banner blanks out.
    write_block(svc, tab, 1, title)
    if meta.get("usama"):
        # Usama banner in I1 (its own merged span); A1:H1 stays Mobeen's.
        write_block(svc, tab, 1, [["USAMA WORKED HOURS "]], start_col=9)
    write_block(svc, tab, 2, headers)
    # Day rows: Date and Day ONLY. Pass protect_cols so no future shape change
    # can send blanks over D:H and erase tracked/untracked/GMI hours.
    write_block(svc, tab, meta["r_day_first"], day_labels, protect_cols=(3,))
    # Seed (never clobber) the Usama DIFF formulas; I and J are fed from chat.
    usama_seed = seed_usama_diff(svc, tab, meta) if meta.get("usama") else None
    cleared = clear_stale_below(svc, tab, meta)
    # Unmerge the script-owned area BEFORE writing and re-merging, or stale
    # merges from earlier layouts collapse live cells in the current tables.
    unmerged = clear_merges(svc, sid, meta)
    # Reset formats to a clean baseline BEFORE styling: stale text formats from
    # earlier, wider layouts survive value clears and would otherwise mismatch
    # the two tables (9pt/bold residue in the Cross-Month block).
    baseline_reset = reset_block_area(svc, sid, meta)
    wide_reset = reset_wide_block_format(svc, sid, meta)
    # Category band labels, written before the tables they introduce.
    for r_sec, label in sections:
        write_block(svc, tab, r_sec, [[label]])
    write_block(svc, tab, meta["r_wk_title"], weekly)
    # Same-kind blocks stay contiguous: Team -> Cross-Month -> Reported Split.
    write_block(svc, tab, meta["r_tm_title"], team)
    if cross:
        write_block(svc, tab, meta["r_cx_title"], cross)
    write_block(svc, tab, meta["r_sp_title"], split)
    write_block(svc, tab, meta["r_foot_first"], foot)
    write_block(svc, tab, meta["r_key_title"], key)
    # Replace the sheet's conditional formats wholesale so re-runs never stack
    # duplicate colour rules.
    cf_meta = svc.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields="sheets(properties(sheetId),conditionalFormats)").execute()
    cf_n = 0
    for s_ in cf_meta["sheets"]:
        if s_["properties"]["sheetId"] == sid:
            cf_n = len(s_.get("conditionalFormats", []))
    style = [{"deleteConditionalFormatRule": {"sheetId": sid, "index": i}}
             for i in range(cf_n - 1, -1, -1)]
    style += style_requests(sid, meta)
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID,
                                   body={"requests": style}).execute()

    # POST-WRITE PROOF: the day grid must be byte-identical to the snapshot.
    ok, diffs = verify_grid(svc, tab, meta, before)
    if created:
        # A fresh tab starts empty, so the script's own writes (banner, header
        # row, Date/Day labels) legitimately appear as diffs. Allow exactly
        # those; any other cell, most importantly the D:H hour columns, must
        # still fail the build.
        allowed = lambda d: ((d["row"] <= 2 and "A" <= d["col"] <= "H") or
                             (d["row"] >= 3 and d["col"] in ("A", "B")))
        diffs = [d for d in diffs if not allowed(d)]
        ok = not diffs
    h_diffs, h_checked = verify_heights(svc, sid, meta)
    uok, udiffs = (verify_usama(svc, tab, meta, ubefore)
                   if meta.get("usama") else (True, []))
    status = "built"
    if not ok:
        status = "GRID CHANGED"
    elif h_diffs:
        status = "HEIGHTS DRIFTED"
    elif not uok:
        status = "USAMA DATA CHANGED"
    result = {"tab": tab, "sheetId": sid, "created": created,
              "days": meta["ndays"], "weeks": meta["nweeks"],
              "cross_month_weeks": meta["ncross"],
              "team_rows": [meta["r_tm_first"], meta["r_tm_last"]],
              "key_row": meta["r_key_title"],
              "cleared": cleared,
              "wide_format_reset": wide_reset,
              "grid_snapshot": snap_path,
              "grid_unchanged": ok,
              "heights_checked": h_checked,
              "heights_off_plan": len(h_diffs),
              "usama_columns": bool(meta.get("usama")),
              "usama_seed": usama_seed,
              "usama_unchanged": uok,
              "status": status}
    if h_diffs:
        result["height_diffs"] = h_diffs[:20]
    if udiffs:
        result["usama_diffs"] = udiffs[:20]
    if not ok:
        result["grid_diffs"] = diffs[:20]
        result["restore"] = ("grid differs from the snapshot in %s; restore from "
                             "%s before doing anything else" % (tab, snap_path))
        print(json.dumps(result, indent=2))
        return 1
    if not uok:
        print(json.dumps(result, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
