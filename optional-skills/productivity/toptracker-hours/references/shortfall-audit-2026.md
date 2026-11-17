# Shortfall audit 2026: management claims vs trackers

Session detail from 2026-08-11/12. The audit is ACTIVE: the full timesheet
was requested from HR and reconciliation runs when it arrives.

## The claim (source: people@contrivesolution.com, 8 Jul 2026, subject
"Mobeen Ahmad_Time Tracking Reports 2026")

- April 2026 shortfall: 15h 17m (weeks: 1-12 Apr 2h51m, 13-19 Apr 15m,
  20-26 Apr 8h43m, 27-30 Apr 3h28m).
- May 2026 shortfall: 18h 22m (5h43m + 3h19m + 3h27m + 5h53m).
- Combined Apr-May 2026: 33h 39m. SOP: 8 tracked hours per working day.
- No disciplinary action; compensation expected; leave deductions if not.

## Older chain (2025, workforce@contrivesolution.com thread)

- Sep 2025: 2h pending; Oct 2025: 7h; total 9h. Nov 2025: +2h = 11h.
  Dec 2025: +3h30m = 14h30m cumulative.
- Jan-Apr 2025 quarter: 12h shortfall; compensation plan existed; 5h spent
  on GMI project without approval, "hours will be treated as deductions,
  not compensated" (Jul 2025). GMI hours did NOT count as compensation then;
  this is the pivotal policy question for the current dispute.

## HR messages (2026-08-12)

- "ap k recorded June26 tak 29 hours and 4 mins mentioned hain meri reports
  main" -> HR's report figure. It matches the sheet's June26 Dizio column
  (29.0h) to the minute, so HR's reports appear to read Dizio-tracked hours
  only.
- Instruction: request the full timesheet report by email, CC
  hr@contrivesolution.com (double-s domain BOUNCES, MX misconfigured; the
  working address is hr@contrivesolution.com, single s).
- Email sent 2026-08-12: to people@contrivesolution.com, CC
  hr@contrivesolution.com, subject "Request for Full Timesheet Report"
  (message id 19ff62dfc81d8824). Draft-first approval rule applies to any
  follow-up.

## Counting rule (user-confirmed 2026-08-12)

- Pre-August 2026: tracked = Kimai (GMI) + sheet logged hours.
- August onward: both trackers live on the sheet (D MTMPRO TRACKED + H GMI).

## Data (2026, hours)

| Month | Kimai GMI | Sheet | Tracked | Expected (8h x workdays) | Delta |
|-------|-----------|-------|---------|--------------------------|-------|
| Jan   | 78.69     | 133.0 | 211.69  | 176                      | +35.69 |
| Feb   | 60.60     | 72.75 | 133.35  | 160                      | -26.65 |
| Mar   | 96.48     | 53.0  | 149.48  | 176                      | -26.52 |
| Apr   | 110.14    | 31.0  | 141.14  | 176                      | -34.86 |
| May   | 84.70     | 33.0  | 117.70  | 168                      | -50.30 |
| Jun   | 62.54     | 66.0  | 128.54  | 176                      | -47.46 |
| Jul   | 51.26     | 46.0  | 97.26   | 184                      | -86.74 |
| Aug 1-11 | (sheet only) | 62.31 | 62.31 | 56                     | +6.31 |

YTD Jan-Aug 11: 1,041.5h tracked vs 1,272h expected (-230.5h).
Jan-Jun: 881.9h tracked vs HR's reported 29h04m.

Sheet per-month detail: Jan sheet = Dizio 19 + K-Factory 114; Feb = 28 + 33
+ 11.75; Mar = 32 + 19 + 2; Apr = Dizio 31 only; May = Dizio 24.5 + 8.5
(unheaded col); Jun = Dizio 29 + Others Hours 37; Jul = Dizio 25 + Others
21; Aug = 1 + 42.7 + 2 + 16.61. Dec 2025 sheet = 62.5h (context).

## Three-way inconsistency (the core finding)

- HR report: 29h04m recorded up to June (Dizio-only read).
- Management claim Apr-May: implies ~310h counted for those months.
- User's own tracked (counting rule): Apr 141.14 + May 117.7 = 258.8h,
  i.e. ~85h shortfall, more than double the 33h39m claim.
- Conclusion: shortfall exists and is larger than claimed; HR's report
  misses ~850h. Strategy: correct the record, then negotiate compensation.

## Caveats / open items

- Expected hours exclude Pakistani holidays (Eid al-Fitr ~Mar 20-22,
  Eid al-Adha ~May 27-29, Aug 14 Independence Day), so deltas are slightly
  pessimistic; apply holidays when the timesheet lands.
- Verify the sheet does not double-count GMI hours already in Kimai
  (e.g. June's 37h "Others Hours") before finalizing per-month deltas.
- TopTracker local DB starts 2026-07-20 only; Apr-May MTMPRO cannot be
  verified locally. The HR timesheet (or a TopTracker server export) is the
  only source for those months.
- Reconciliation script plan when the timesheet arrives: per-day compare
  official vs Kimai + TopTracker + sheet, produce per-month table with
  holidays applied, and a draft reply (draft-first approval before send).

## Tools built

- `~/.hermes/scripts/kimai_monthly.py`: per-month official Kimai totals
  (--from YYYY-MM --to YYYY-MM; running entries count 0).
- `~/.hermes/scripts/sheet_monthly_totals.py`: per-tab totals, header-aware
  (--tab X, --by-month to split two-month tabs).
