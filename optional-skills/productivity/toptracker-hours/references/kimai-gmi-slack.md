# Kimai (GMI project hours) and Slack presence

Knowledge gathered 2026-08-07 while scoping the GMI hours workflow. The
sync script was NOT built yet (awaiting the user's Kimai API token); this
file is the research base plus the resolved decisions so a future session
does not re-derive them.

## The platform

- `track.plentystaff.com` is a PlentyStaff-hosted **Kimai** instance
  (open-source web time tracker). Login page is Kimai branding; the user's
  GMI project hours live there as timesheet entries.
- PlentyStaff is the HR/contracting provider; the Kimai instance is their
  employee time tracking. The user has NO admin control over it.

## Pulling GMI hours (API path)

- Kimai exposes a JSON REST API with per-user API tokens (created in the
  user profile page: https://track.plentystaff.com/en/profile/). Docs:
  https://www.kimai.org/documentation/rest-api.html (the old
  `/documentation/restapi.html` URL 404s after the docs restructure),
  pagination: https://www.kimai.org/documentation/api-pagination.html
- Instance serves its OpenAPI spec at `/api/doc.json` (useful to confirm
  live endpoint shapes on track.plentystaff.com).
- Relevant endpoints: `/api/timesheets` (filter by project, begin/end,
  user), `/api/projects` (to discover the GMI project ID).
- API auth: `X-AUTH-USER` + `X-AUTH-TOKEN` headers (Kimai convention);
  HTTP basic auth with `username:api_token` also works.
- Planned shape: `kimai_sync.py` mirroring `toptracker_sync.py` (pull
  day/week, land into the worked-hours sheet column H, wire a cron like
  the existing MTMPRO jobs).

## Resolved decisions (2026-08-07, user confirmed)

1. **GMI hours destination: NEW column in the worked-hours sheet = H.**
   August26 tab headers: A Date, B Day, C DIZIO WORKED HOURS, D MTMPRO
   TRACKED, E MTMPRO UNTRACKED, F Other Project, G Others, H GMI (new).
   Data rows start at row 3 (date N = row N+2). Header value proposed:
   "GMI". Hours in decimal form like column D.
2. **Slack fix: user has no control over the Kimai tracker (admin-managed),
   so the ONLY lever is keeping Slack presence active locally.** Chosen
   approach: cliclick + launchd keep-alive (IMPLEMENTED, see below).
3. **Slack-Kimai bot operator: admin side (PlentyStaff); the user cannot
   change the bot's behavior.**

## Slack presence mechanics (verified)

- Away after ~10 minutes of desktop inactivity. There is NO user-facing
  (or standard-plan admin) setting to change the timer.
  [source: slack.com/help/articles/201864558, docs.slack.dev user presence]
- Activity = typing, clicking, scrolling INSIDE Slack. Working in other
  apps, reading, or having Slack open in the background does not reset the
  timer. Manually setting yourself Active does NOT override it.
- `users.setPresence("active")` with a user token does not keep you active;
  per Slack docs a manual "active" just tells the server to use automatic
  detection again.
- Multi-device: any active session (e.g. phone) keeps presence green
  [MEDIUM confidence, slack.green].
- Slack huddles keep you active for the duration of the call.

## Keep-alive: implemented setup (2026-08-07)

- Script: `~/.hermes/scripts/slack_keepalive.sh`. Runs cliclick
  `m:+2,+0 m:-2,+0` (net-zero 2px nudge, two activity events) only inside
  a work window (07:00-23:00 local by default, HOUR_START/HOUR_END vars).
- LaunchAgent: `~/Library/LaunchAgents/com.hermes.slack-keepalive.plist`,
  `StartInterval` 240 (4 min), `RunAtLoad` true.
- Load/verify:
  `launchctl bootstrap gui/$(id -u) <plist>` (ignore "Bootstrap failed: 5"
  if it is already loaded), then
  `launchctl print gui/$(id -u)/com.hermes.slack-keepalive` shows
  `state = running`.
- Requires `brew install cliclick` (already installed at
  /usr/local/bin/cliclick on this Intel Mac) and macOS Accessibility
  permission for the event source; first run showed no error, so events
  post. If it ever stops working, re-grant Accessibility.
- Rationale: Slack reads system idle time; a periodic cursor nudge resets
  the idle timer while the user works in other apps.
- Options evaluated and rejected: native Kimai trackers (user can't change
  how tracking happens), cloud keep-alive services (token risk, policy
  risk), browser extensions (unreliable, one pulled from the store).

## Shortfall verification (Contrive HR dispute, started 2026-08-12)

- Contrive SOP: 8 tracked hours per working day. Shortfall emails come from
  people@contrivesolution.com and workforce@contrivesolution.com. 2025
  chain: Sep-Dec 2025 cumulative 14h30m, Jan-Apr 2025 quarter 12h.
- Active claim (email 2026-07-08): April 2026 shortfall 15h17m, May 2026
  18h22m, combined 33h39m. No June/July 2026 claim found in Gmail.
- Official hours are logged in a Contrive Google Sheet (per HR). Full
  timesheet report requested by email 2026-08-12 (to people@, CC
  hr@contrivesolution.com; the contrivesolutions.com domain bounces).
- Audit tools: kimai_monthly.py (Kimai official totals per month),
  sheet_monthly_totals.py (per-tab totals, header-aware), TopTracker local
  DB (MTMPRO, only from 2026-07-20).
- Framework: month by month, compare HR timesheet vs Kimai GMI + TopTracker
  MTMPRO + own sheet. Key open question: does Kimai GMI tracking count
  toward the SOP (Jul 2025 precedent: GMI hours were not approved as
  compensation).
- Sheet legacy tabs have per-month custom column layouts (K-Factory, PWA
  Design, Other Project); only August26+ has the standard 7-column layout
  with GMI in H.

## Open state (as of 2026-08-10, LIVE)

- LIVE: kimai_sync.py works end-to-end. Project GetMyInvoices id 1; Aug 7 =
  4.97 h, Aug 10 = 4.67 h verified from the API and written to H9/H12.
  Credentials live in ~/.hermes/config/kimai.json (username mahmed). If the
  token leaks, rotate it in Kimai profile and update the config.
- Crons (SUPERSEDED 2026-09-25): the GMI Weekly Sync c25679e94527 (Fri 20:15)
  and GMI Weekly Catch-up 90e71222298f (Mon 00:20) no longer exist. Column H is
  filled daily by the nightly fill_hours.py job (a8090fb09d6c, 23:55).
- Kimai timestamps return offsets like +0500 (no colon); kimai_sync.py
  normalizes before fromisoformat (Python 3.9 limitation).
- Pitfall (legacy): tabs built by the old create_dizio_tab did NOT carry the GMI
  header. Current tabs are built by build_month_tab.py and carry H2 = "GMI";
  if a sync ever reports "has no GMI column in H", set H2 = "GMI" on that tab.
- The Mon 03.08 entry the user rejected is NOT in Kimai; sheet and API agree.
- DONE 2026-08-07: `~/.hermes/scripts/sheet_weekly_summary.py` includes H
  (GMI) in week rows, MONTH TOTAL, and headers. Fixed a format-string bug
  (6 args / 5 placeholders) in the MONTH TOTAL formula that crashed the
  refresh; verified block lands on August26 A34:H44 with GMI column and
  TOTAL column populated.
