#!/usr/bin/env python3
"""Query TopTracker API for tracked hours.

Usage:
    toptracker_api.py                  # today's hours, all projects
    toptracker_api.py --project 1182888  # specific project only
    toptracker_api.py --date 2026-09-10  # check if API supports date queries
    toptracker_api.py --list-projects   # list all projects with IDs

API auth: reads access_token from ~/.config/TopTracker/settings.ini
API base: https://tracker-api.toptal.com
"""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SETTINGS_PATH = Path.home() / ".config" / "TopTracker" / "settings.ini"
API_BASE = "https://tracker-api.toptal.com"
MTMPRO_PROJECT_ID = 1182888


def get_access_token() -> str:
    """Extract access token from TopTracker settings.ini."""
    if not SETTINGS_PATH.exists():
        print(f"ERROR: Settings file not found: {SETTINGS_PATH}", file=sys.stderr)
        sys.exit(1)
    text = SETTINGS_PATH.read_text()
    match = re.search(r'remembered-access-token=(.+)', text)
    if not match:
        print("ERROR: No remembered-access-token in settings.ini", file=sys.stderr)
        sys.exit(1)
    return match.group(1).strip()


def _request(endpoint: str, token: str, method: str = "GET", data: dict = None):
    """TopTracker request via urllib; the token never enters process argv."""
    url = f"{API_BASE}{endpoint}?access_token={urllib.parse.quote(token)}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/120 Safari/537.36")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"TopTracker HTTP {exc.code} for {endpoint}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TopTracker request failed for {endpoint}: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"TopTracker returned non-JSON for {endpoint}") from exc


def api_get(endpoint: str, token: str) -> dict:
    """GET request to TopTracker API."""
    return _request(endpoint, token)


def api_delete(endpoint: str, token: str) -> dict:
    """DELETE request to TopTracker API."""
    return _request(endpoint, token, method="DELETE")


def api_post(endpoint: str, token: str, data: dict) -> dict:
    """POST request to TopTracker API."""
    return _request(endpoint, token, method="POST", data=data)


def list_projects(token: str) -> list:
    """List all projects with worked_today stats."""
    data = api_get("/users/me/projects", token)
    projects = data.get("projects", [])
    results = []
    for p in projects:
        stats = p.get("user_stats", {})
        results.append({
            "id": p["id"],
            "name": p["name"],
            "worked_today": stats.get("worked_today", 0),
            "worked_total": stats.get("worked_total", 0),
        })
    return results


def get_project_hours(project_id: int, token: str) -> dict:
    """Get worked_today and worked_total for a project."""
    data = api_get(f"/projects/{project_id}", token)
    project = data.get("project", {})
    stats = project.get("user_stats", {})
    last = project.get("last_activity", {})
    return {
        "project_name": project.get("name", "Unknown"),
        "project_id": project_id,
        "worked_today": stats.get("worked_today", 0),
        "worked_total": stats.get("worked_total", 0),
        "last_activity": {
            "description": last.get("description"),
            "start_time": last.get("start_time"),
            "end_time": last.get("end_time"),
            "seconds": last.get("seconds"),
        } if last else None,
    }


def format_seconds(s: int) -> str:
    """Format seconds as Xh Ym."""
    h = s // 3600
    m = (s % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Query TopTracker API")
    parser.add_argument("--project", type=int, help="Project ID to query")
    parser.add_argument("--list-projects", action="store_true", help="List all projects")
    parser.add_argument("--delete-activity", type=int, help="Delete an activity by API ID")
    parser.add_argument("--confirm", action="store_true",
                        help="Required with --delete-activity")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.delete_activity and not args.confirm:
        print("ERROR: --delete-activity requires --confirm", file=sys.stderr)
        return 1

    token = get_access_token()

    if args.delete_activity:
        result = api_delete(f"/activities/{args.delete_activity}", token)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            a = result.get("activity", {})
            print(f"Deleted activity {a.get('id')}: {format_seconds(a.get('seconds', 0))}")
        return

    if args.list_projects:
        projects = list_projects(token)
        if args.json:
            print(json.dumps(projects, indent=2))
        else:
            for p in projects:
                today = format_seconds(p["worked_today"])
                total_h = round(p["worked_total"] / 3600, 1)
                marker = " *" if p["worked_today"] > 0 else ""
                print(f"  {p['id']:>8}  {p['name']:<30}  today: {today:<10}  total: {total_h}h{marker}")
        return

    if args.project:
        info = get_project_hours(args.project, token)
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print(f"{info['project_name']} (ID {info['project_id']}):")
            print(f"  Today: {format_seconds(info['worked_today'])} ({info['worked_today']}s)")
            print(f"  Total: {round(info['worked_total']/3600, 1)}h")
            if info["last_activity"]:
                la = info["last_activity"]
                print(f"  Last: {la['description'] or '(no desc)'}, {format_seconds(la['seconds'] or 0)}")
        return

    # Default: all projects with today's hours
    projects = list_projects(token)
    active = [p for p in projects if p["worked_today"] > 0]
    total_today = sum(p["worked_today"] for p in projects)

    if args.json:
        print(json.dumps({"active": active, "total_today": total_today}, indent=2))
    else:
        if not active:
            print(f"No hours tracked today. Total across all projects: {format_seconds(total_today)}")
        else:
            print(f"TopTracker hours today:")
            for p in active:
                print(f"  {p['name']:<30} {format_seconds(p['worked_today'])}")
            if len(active) > 1:
                print(f"  {'TOTAL':<30} {format_seconds(total_today)}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
