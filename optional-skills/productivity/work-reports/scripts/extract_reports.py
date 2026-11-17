#!/usr/bin/env python3
"""Extract a date range from the work-reports LowDB store to a compact file.

Read-only. Use when an MCP report payload is too large to read reliably in
context. The MCP writes the same store; this script never mutates it.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

DEFAULT_DB = Path.home() / "Dev" / "work-reports" / "db.json"
FIELDS = (
    "status",
    "branch",
    "commits",
    "implementation",
    "blockers",
    "files",
    "verification",
    "linearUpdates",
    "sideObservations",
)


def load_reports(db_path: Path) -> list:
    data = json.loads(db_path.read_text(encoding="utf-8"))
    reports = data.get("reports") if isinstance(data, dict) else data
    if not isinstance(reports, list):
        raise SystemExit(f"Unexpected report store shape in {db_path}")
    return reports


def as_text(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def render(reports: list, start: str, end: str, project: str | None) -> tuple[str, int]:
    selected = [
        report
        for report in reports
        if start <= str(report.get("date") or "") <= end
        and (not project or report.get("project") == project)
    ]
    selected.sort(
        key=lambda report: (
            str(report.get("date") or ""),
            str(report.get("project") or ""),
        )
    )
    lines = []
    for report in selected:
        lines.append(
            f"# {report.get('date')} | {report.get('project')} | id {report.get('id')}\n"
        )
        lines.append(f"SUMMARY:\n{report.get('summary', '')}\n")
        for ticket in report.get("tickets") or []:
            lines.append(f"\n## {ticket.get('ticketId')}: {ticket.get('title')}\n")
            for field in FIELDS:
                value = ticket.get(field)
                if value:
                    lines.append(f"{field}: {as_text(value)}\n")
        lines.append(f"\nOPEN NEXT:\n{report.get('openNext', '')}\n")
        lines.append(f"\nMEMORY UPDATES:\n{report.get('memoryUpdates', '')}\n")
        lines.append("\n" + "=" * 80 + "\n")
    if not selected:
        scope = f" in {project}" if project else ""
        lines.append(f"No reports found for {start} through {end}{scope}.\n")
    return "".join(lines), len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", required=True, help="first date, YYYY-MM-DD")
    parser.add_argument("--to", dest="end", required=True, help="last date, YYYY-MM-DD")
    parser.add_argument("--project", help="exact project name")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("WORK_REPORTS_DB", str(DEFAULT_DB))),
        help="work-reports db.json path",
    )
    parser.add_argument("--out", type=Path, required=True, help="Markdown output path")
    args = parser.parse_args()

    for label, value in (("--from", args.start), ("--to", args.end)):
        try:
            date.fromisoformat(value)
        except ValueError:
            parser.error(f"{label} must be YYYY-MM-DD: {value}")
    if args.start > args.end:
        parser.error("--from must be on or before --to")

    reports = load_reports(args.db)
    text, count = render(reports, args.start, args.end, args.project)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{count} report(s) -> {args.out} ({len(text)} chars)")


if __name__ == "__main__":
    main()
