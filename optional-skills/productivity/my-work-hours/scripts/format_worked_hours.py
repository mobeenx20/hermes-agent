"""Format a monthly tab in the Mobeen Worked Hours spreadsheet.

Usage: python format_worked_hours.py <tab_name> [month_number] [year]

Examples:
  python format_worked_hours.py "June26" 6 2026
  python format_worked_hours.py "July26" 7 2026

WARNING: This script overwrites ALL data in the tab.
Only run it for brand-new monthly tabs.
"""
import calendar
import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "REPLACE_SPREADSHEET_ID"


def load_creds():
    token_path = os.path.expanduser(
        "~/.local/share/google-mcp/tokens.json"
    )
    with open(token_path) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", []),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_data["access_token"] = creds.token
        with open(token_path, "w") as f:
            json.dump(token_data, f)
    return creds


def month_name(num):
    return calendar.month_name[num]


def create_and_format(service, tab_name, month_num, year):
    sheet_id = None

    # Check if tab already exists
    sheets_data = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in sheets_data["sheets"]:
        if s["properties"]["title"] == tab_name:
            sheet_id = s["properties"]["sheetId"]
            print(f"Tab '{tab_name}' already exists (sheetId={sheet_id})")
            break

    if sheet_id is None:
        # Add the new sheet
        body = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
        result = (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body)
            .execute()
        )
        sheet_id = result["replies"][0]["addSheet"]["properties"]["sheetId"]
        print(f"Created tab '{tab_name}' (sheetId={sheet_id})")

    # Build calendar data
    mname = month_name(month_num)
    _, days_in_month = calendar.monthrange(year, month_num)
    rows = [[" ", "", "MOBEEN WORKED HOURS ", "", "", ""]]
    rows.append(["Date", "Day", "DIZIO WORKED HOURS", "Other Project", "Others", ""])
    for day in range(1, days_in_month + 1):
        dow = calendar.weekday(year, month_num, day)
        day_name = calendar.day_name[dow]
        rows.append([f"{day} {mname}", day_name, "", "", "", ""])

    # Write values
    range_str = f"{tab_name}!A1:F{len(rows)}"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_str,
        body={"values": rows},
        valueInputOption="USER_ENTERED",
    ).execute()
    print(f"Wrote {len(rows)} rows")

    # Apply formatting
    requests = [
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 2,
                    "endColumnIndex": 6,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 2,
                    "endColumnIndex": 6,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": 12},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(textFormat,horizontalAlignment)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": 6,
                },
                "cell": {
                    "userEnteredFormat": {"textFormat": {"bold": True}}
                },
                "fields": "userEnteredFormat.textFormat.bold",
            }
        },
    ]
    body = {"requests": requests}
    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()
    print("Formatting applied (title merge + bold, header bold)")
    print(f"\nDone! Tab '{tab_name}' ready for {mname} {year}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python format_worked_hours.py <tab_name> [month_number] [year]")
        print("Example: python format_worked_hours.py June26 6 2026")
        sys.exit(1)

    tab = sys.argv[1]
    month = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    year = int(sys.argv[3]) if len(sys.argv) > 3 else 2026

    creds = load_creds()
    service = build("sheets", "v4", credentials=creds)
    create_and_format(service, tab, month, year)
