# Contrive tracked-hours shortfall audit

Recurring task (gathered 2026-08-11): Contrive people ops / workforce
analytics email shortfall reports; the user must verify the claimed missing
hours month by month against their trackers (Kimai GMI + TopTracker MTMPRO +
the worked-hours sheet) and reply with evidence. The user requested the
official timesheet from HR as the baseline.

## The policy and the claim history

- Contrive SOP: 8 TRACKED hours per working day. Uncompensated shortfall may
  be deducted from leave. Source: people@contrivesolution.com, subject
  "Mobeen Ahmad_Time Tracking Reports 2026", 8 Jul 2026.
- LIVE claim (the active one): April-May 2026 combined shortfall 33h 39m.
  - Apr 2026: 1-12 Apr 2h51m; 13-19 Apr 15m; 20-26 Apr 8h43m; 27-30 Apr
    3h28m. Total 15h 17m.
  - May 2026: 1-10 May 5h43m; 11-17 May 3h19m; 18-24 May 3h27m; 25-31 May
    5h53m. Total 18h 22m.
- Older 2025 chain (workforce@contrivesolution.com, thread "Re: Time
  Tracking Report FTM May 2025", full quoted history inside bodies): Sep
  2h + Oct 7h = 9h; Nov +2h = 11h; Dec +3h30m = 14h30m cumulative. Jan-Apr
  2025 quarter: 12h; the compensation saga shows GMI hours spent on it were
  NOT approved ("shortfall hours will be treated as deductions, not
  compensated") - precedent that GMI hours may not count toward the SOP.
- Gmail recipes: search "shortfall" finds the report emails.
  from:people@contrivesolution.com after:YYYY/MM/DD is mostly announcements
  (holidays, anniversaries); filter by subject. The 2025 chain is one long
  thread, newer messages carry the whole history quoted.

## Verification sources and limits (2026-08-11 state)

| Source | Coverage | Notes |
|---|---|---|
| Kimai track.plentystaff.com, project GetMyInvoices id 1 | Jan 2026+ full | Official PlentyStaff tracker; monthly totals via kimai_monthly.py |
| TopTracker local DB | only from ~2026-07-20 | Earlier months need HR timesheet or TopTracker server export; cannot verify locally |
| Google sheet tabs | all months | Manual record; sparse for Apr-May (64h across both) and column layout shifts per month |

## Tools built for the audit

- ~/.hermes/scripts/kimai_monthly.py: official Kimai monthly totals (hours,
  entries, active_running). Run with /usr/bin/python3, reads
  ~/.hermes/config/kimai.json. Flags --from YYYY-MM --to YYYY-MM. Running
  entries report duration 0 until stopped.
- ~/.hermes/scripts/sheet_monthly_totals.py: per-tab totals, header-aware
  (prints headers + per-column sums + total). Legacy tabs shift column
  meaning by month:
  - Dec-Jan: C DIZIO, D K-Factory, E MEETINGS
  - FEb26: C DIZIO, D K-Factory, E Others
  - March26: C DIZIO, D PWA Design, E Others
  - April26-May26: C DIZIO, D Other Project, E Others (some values in
    unheaded F)
  - June26: C DIZIO, D Others, E Others Hours, F Notes
  - July26: C DIZIO, D Other Project, E Others
  - August26+: 7-column layout plus GMI (H)
- Pitfall: direct googleapiclient spreadsheet().get() returns rowCount under
  properties.gridProperties.rowCount (the google-mcp tool flattens it); do
  not read properties.rowCount.

## Findings as of 2026-08-11

- Kimai GMI official monthly: Jan 78.69, Feb 60.60, Mar 96.48, Apr 110.14,
  May 84.70, Jun 62.54, Jul 51.26, Aug 16.60 (1 running).
- Apr+May GMI = 194.84h. If GMI hours count toward the SOP, the 33h39m claim
  is very likely wrong. This is the CRUX question to put to HR (2025
  precedent says no without approval).
- The sheet cannot prove extra work for Apr-May (only 64h recorded, mostly
  Dizio).
- [INFERENCE] If the claim is accurate and TopTracker is the counted system:
  implied TopTracker Apr ~50.6h, May ~64.9h (expected 8h x workdays minus
  claimed shortfall minus Kimai hours).

## Counting rule (user-confirmed 2026-08-12)

- Pre-August 2026 months: tracked = Kimai (GMI) + sheet logged hours.
- August 2026 onward: both trackers live on the sheet (D MTMPRO TRACKED +
  H GMI; C/E also count as logged).
- HR's own figure "29h04m recorded up to June" matches the June26 Dizio
  column (29.0h) to the minute: HR reports appear to read Dizio only.

## Per-month recomputation (counting rule applied)

| Month | Kimai | Sheet | Tracked | Expected (8h x workdays) | Delta |
|-------|-------|-------|---------|--------------------------|-------|
| Jan   | 78.69 | 133.0 | 211.69  | 176                      | +35.69 |
| Feb   | 60.60 | 72.75 | 133.35  | 160                      | -26.65 |
| Mar   | 96.48 | 53.0  | 149.48  | 176                      | -26.52 |
| Apr   | 110.14| 31.0  | 141.14  | 176                      | -34.86 |
| May   | 84.70 | 33.0  | 117.70  | 168                      | -50.30 |
| Jun   | 62.54 | 66.0  | 128.54  | 176                      | -47.46 |
| Jul   | 51.26 | 46.0  | 97.26   | 184                      | -86.74 |
| Aug 1-11 | (sheet only) | 62.31 | 62.31 | 56                     | +6.31 |

Sheet per-month splits (sheet_monthly_totals.py --by-month): Jan = Dizio 19
+ K-Factory 114; Feb = 28 + 33 + 11.75; Mar = 32 + 19 + 2; Apr = Dizio 31;
May = Dizio 24.5 + 8.5 (unheaded col); Jun = Dizio 29 + Others Hours 37;
Jul = Dizio 25 + Others 21; Aug = 1 + 42.7 + 2 + 16.61. Dec 2025 sheet = 62.5.

## Findings after the counting rule (2026-08-12)

- Three-way inconsistency: HR reports 29h04m up to June; the 33h39m claim
  implies ~310h counted for Apr-May; the user's own tracked (rule) is
  258.8h for Apr-May (141.14 + 117.7), i.e. ~85h shortfall, MORE than double
  the claim. Jan-Jun tracked = 881.9h vs HR's 29h04m, an ~850h gap.
- Conclusion: the shortfall is real and larger than claimed (Jun -47h,
  Jul -87h are worse than the flagged months). Strategy: correct the record
  (HR's figure is wrong by ~850h), negotiate compensation, do NOT dispute
  existence when the user's own data confirms it.
- Caveats: expected excludes Pakistani holidays (Eid al-Fitr ~Mar 20-22,
  Eid al-Adha ~May 27-29, Aug 14 Independence), deltas slightly pessimistic;
  confirm the sheet does not double-count GMI already in Kimai (e.g. Jun 37h
  "Others Hours") before finalizing.

## Open state / next steps (2026-08-12)

- Full timesheet REPORT REQUESTED by email 2026-08-12: to
  people@contrivesolution.com, CC hr@contrivesolution.com (the double-s
  contrivesolutions.com domain bounces; correct domain is single-s), subject
  "Request for Full Timesheet Report", message id 19ff62dfc81d8824.
- Still open: (1) whether Kimai GMI counts toward the SOP (2025 precedent
  says no without approval), (2) which months management will claim next
  (check Gmail for newer shortfall emails before concluding scope).
- When the timesheet lands: reconcile per day (official vs Kimai + TopTracker
  + sheet), apply holiday-adjusted expected hours, produce the evidence pack
  and a draft reply (draft-first approval before send).
