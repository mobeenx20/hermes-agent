# Sheet Color Fill Reference

Background color conventions and the Google Sheets API pattern for applying/repairing them.

## Color Palette

| Use | RGB (API format) | Hex |
|-----|-----------------|-----|
| Title (row 1) | `{"red": 0.9019608, "green": 0.5686275, "blue": 0.21960784}` | #E69138 |
| Headers (row 2) | `{"red": 0.5764706, "green": 0.76862746, "blue": 0.49019608}` | #93C47D |
| Weekends | `{"red": 1, "green": 0.8509804, "blue": 0.4}` | #FFD966 |
| White/default | `{"red": 1, "green": 1, "blue": 1}` | #FFFFFF |

## Full Repair via batchUpdate

Use this pattern to reset all colors on a tab. Replace `SHEET_ID` and adjust the weekend row ranges.

```python
import json, urllib.request

spreadsheet_id = "REPLACE_SPREADSHEET_ID"
sheet_id = 1951708847  # July26 — replace with target sheet ID
access_token = "..."   # from tokens.json

ORANGE = {"red": 0.9019608, "green": 0.5686275, "blue": 0.21960784}
GREEN = {"red": 0.5764706, "green": 0.76862746, "blue": 0.49019608}
YELLOW = {"red": 1, "green": 0.8509804, "blue": 0.4}
WHITE = {"red": 1, "green": 1, "blue": 1}

days_in_month = 31  # varies per month

requests = []

# Step 1: Clear all backgrounds to white
requests.append({
    "repeatCell": {
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 0,
            "endRowIndex": 2 + days_in_month,
            "startColumnIndex": 0,
            "endColumnIndex": 5
        },
        "cell": {"userEnteredFormat": {"backgroundColor": WHITE}},
        "fields": "userEnteredFormat.backgroundColor"
    }
})

# Step 2: Title row (row 1 = index 0)
requests.append({
    "repeatCell": {
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 0, "endRowIndex": 1,
            "startColumnIndex": 0, "endColumnIndex": 5
        },
        "cell": {"userEnteredFormat": {"backgroundColor": ORANGE}},
        "fields": "userEnteredFormat.backgroundColor"
    }
})

# Step 3: Header row (row 2 = index 1)
requests.append({
    "repeatCell": {
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 1, "endRowIndex": 2,
            "startColumnIndex": 0, "endColumnIndex": 5
        },
        "cell": {"userEnteredFormat": {"backgroundColor": GREEN}},
        "fields": "userEnteredFormat.backgroundColor"
    }
})

# Step 4: Weekend rows (compute from calendar.monthrange)
# Each weekend pair: (sat_index, sun_index) where row_index = date + 1
# Example for July 2026 (starts Wednesday):
#   Jul 4 Sat = row 5, Jul 5 Sun = row 6
#   Jul 11 Sat = row 12, Jul 12 Sun = row 13
#   etc.
for sat_row in [5, 12, 19, 26]:  # 0-indexed row of each Saturday
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": sat_row,
                "endRowIndex": sat_row + 2,  # Sat + Sun
                "startColumnIndex": 0,
                "endColumnIndex": 5
            },
            "cell": {"userEnteredFormat": {"backgroundColor": YELLOW}},
            "fields": "userEnteredFormat.backgroundColor"
        }
    })

batch_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
req = urllib.request.Request(
    batch_url,
    data=json.dumps({"requests": requests}).encode(),
    headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    },
    method="POST"
)
urllib.request.urlopen(req)
```

## Getting the Sheet ID

```python
ss = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
for s in ss["sheets"]:
    if s["properties"]["title"] == "July26":
        sheet_id = s["properties"]["sheetId"]
```

## Computing Weekend Rows

```python
import calendar
year, month = 2026, 7
_, days = calendar.monthrange(year, month)
weekends = []
for d in range(1, days + 1):
    dow = calendar.weekday(year, month, d)
    if dow == 5:  # Saturday
        row = d + 1  # 0-indexed: date 1 = row index 2, but our row calc is d+1
        weekends.append(row)
# Each value in weekends is the 0-indexed row of a Saturday
```
