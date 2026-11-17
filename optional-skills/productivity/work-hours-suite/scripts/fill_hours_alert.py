#!/usr/bin/env python3
"""Turn fill_hours.py JSON into a compact alert.

Silence means the fill was clean. Anything printed is a problem the user
needs to see. The parser lives here, not inline in the shell wrapper, so the
C-column checks can be unit-tested like the rest of the hours scripts.
"""

import json
import sys
from datetime import date


def collect_problems(d):
    """Return a list of alert strings for one fill result dict."""
    problems = []

    if d.get("skipped"):
        problems.append("skipped: %s" % (d.get("reason") or "unknown"))

    try:
        weekday = date.fromisoformat(d.get("date", "")).weekday() < 5
    except (TypeError, ValueError):
        weekday = True

    if weekday and d.get("toptracker") is None and not d.get("dry_run"):
        problems.append("TopTracker had no closed MTMPRO rows for the day")

    if d.get("verified") is False:
        errors = d.get("verification_errors") or []
        problems.append("write verification failed: %s"
                        % ("; ".join(str(e) for e in errors) or "unknown"))

    for note in d.get("notes") or []:
        if note.startswith("C: tracker reads 0") or note.startswith("C: STALE"):
            problems.append(note)

    summary = d.get("summary") or {}
    if summary.get("verified") is False:
        errors = summary.get("verification_errors") or []
        problems.append("weekly summary verification failed: %s"
                        % ("; ".join(str(e) for e in errors) or "unknown"))
    elif (summary.get("refreshed") is False and summary.get("reason")
          and not summary.get("dry_run")):
        problems.append("weekly summary not refreshed: %s" % summary["reason"])

    return problems


def main():
    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
    except Exception:
        print("Nightly hours fill: output was not JSON:")
        print(raw[:800])
        return 0

    problems = collect_problems(d)
    if not problems:
        return 0

    print("Nightly hours fill %s: %s"
          % (d.get("date", "?"), "; ".join(problems)))
    d.pop("summary", None)
    print(json.dumps(d, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
