# Kimai REST API — Create, Stop, Delete Time Entries

Knowledge gathered 2026-08-25 via live probing against `track.plentystaff.com`
(PlentyStaff-hosted Kimai instance). Complements `kimai-gmi-slack.md` (pull
side) with the push-side mechanics.

## Config

`~/.hermes/config/kimai.json`:
```json
{
  "url": "https://track.plentystaff.com",
  "username": "mahmed",
  "token": "gtg!fcm0pvz4FZM!zwn",
  "project": "GetMyInvoices",
  "timezone": "Asia/Karachi"
}
```

Credentials are shared with `kimai_sync.py`. Never duplicate in code.

## Auth

Two headers on every request:
```
X-AUTH-USER: <username>
X-AUTH-TOKEN: <api_token>
```

HTTP basic auth with `username:api_token` also works per Kimai docs, but the
header approach is what `kimai_sync.py` already uses — stay consistent.

## Endpoints — verified live 2026-08-25

### POST /api/timesheets — CREATE an entry

**Works.** Minimal body:
```json
{"project": 1, "activity": 13, "description": "TECH-1234: fixed login"}
```

- `project` and `activity` are **required** — nothing else is accepted on
  create. Any extra field (`start`, `end`, `begin`, `time`, `duration`) returns
  `{"code":400,"message":"Validation Failed","errors":{"errors":["This form
  should not contain extra fields."],...}}`.
- Kimai sets `begin` to now automatically. `end` is null, `duration` is 0.
- Returns the created entry with its `id`.
- GMI project = ID 1, activity = ID 13 (from live entries; refresh if either
  renumbers).

### GET /api/timesheets — LIST entries

**Works.** Filter by project + date range:
```
/api/timesheets?project=1&begin=2026-08-25T00:00:00&end=2026-08-25T23:59:59&size=100
```

- Returns a bare array (not wrapped in `{"data":...}`). `kimai_sync.py` handles
  both shapes via `_paged()`.
- Each entry has: id, begin, end, duration (seconds), description,
  project, activity, user, tags, rate, internalRate, exported, metaFields.

### GET /api/timesheets/{id} — READ one entry

**Works.** Returns full entry object or 404.

### PATCH /api/timesheets/{id} — STOP an entry

**DOES NOT WORK.** Returns 400 with "This form should not contain extra fields."
The PATCH endpoint only accepts: `project`, `activity`, `description`, `tags`,
`user`. **`end` is not accepted.** You cannot set an end time via the REST API.

Implication: entries created via `POST` have `end: null` and `duration: 0`
permanently, unless the Slack presence bot (admin-controlled by PlentyStaff)
auto-stops them. You cannot manually close an entry from Hermes.

### DELETE /api/timesheets/{id} — DELETE an entry

**Works.** Returns 404 if already deleted or not found (idempotent). No body
needed.

## Script

`~/.hermes/scripts/kimai_create.py` — the working implementation. Subcommands:

| Command | What it does |
|---------|-------------|
| `create "description"` | POST a new entry with now as begin |
| `list [--date YYYY-MM-DD]` | List entries for a day |
| `delete --id N` | DELETE an entry |
| `stop [--id N]` | Reports API limitation (stop not available) |

Run directly: `/usr/bin/python3 ~/.hermes/scripts/kimai_create.py <subcommand>`.

## How it fits the workflow

```
You work → Slack bot auto-tracks in Kimai → kimai_sync.py reads → sheet column H
                                    ↘ kimai_create.py creates/edits entries
```

`kimai_sync.py` (pull, already on cron) is the daily reader. `kimai_create.py`
(push) is for manual backfills when you forgot to track a chunk.

## Pitfall

If PlentyStaff renumbers the GMI project or activity, update the two constants
at the top of `kimai_create.py` (PROJECT_ID, ACTIVITY_ID). Verify by listing
entries and checking the `project`/`activity` values on any existing GMI entry.
