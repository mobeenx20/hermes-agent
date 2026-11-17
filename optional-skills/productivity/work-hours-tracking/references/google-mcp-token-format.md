# Google MCP Token Format

The dizio-work-hours plugin piggybacks on the Google MCP server's OAuth credentials. This means it reads two separate files, which have different formats:

## File 1: `~/.local/share/google-mcp/tokens.json`

Contains the live OAuth tokens. Key fields:

```json
{
  "access_token": "ya29.xxx",
  "refresh_token": "1//xxx",
  "token_type": "Bearer",
  "expiry_date": 1700000000000,
  "scope": "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/drive ..."
}
```

**Critical:** `scope` is singular (not `scopes`) and is a space-separated string, NOT a JSON array. When constructing `google.oauth2.credentials.Credentials`, you must `.split()` it:

```python
# WRONG — wraps the entire string as one malformed scope
scopes=[td.get("scope", "https://.../spreadsheets")]

# CORRECT — splits the space-separated string into individual scopes
scopes=td.get("scope", "https://.../spreadsheets").split()
```

This file does NOT contain `client_id` or `client_secret`.

## File 2: `~/.config/google-mcp/credentials.json`

Contains the OAuth client registration:

```json
{
  "installed": {
    "client_id": "833007106972-xxx.apps.googleusercontent.com",
    "project_id": "...",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_secret": "GOCSPX-xxx",
    "redirect_uris": ["http://localhost"]
  }
}
```

This file contains `client_id`, `client_secret`, and `token_uri` under `installed` (desktop app flow).

## Combined Credential Construction

```python
with open(TOKEN_PATH) as f:
    td = json.load(f)          # tokens.json → access_token, refresh_token, scope
with open(CREDS_PATH) as f:
    cd = json.load(f)          # credentials.json → client_id, client_secret, token_uri
client_info = cd.get("installed", cd.get("web", {}))

creds = Credentials(
    token=td.get("access_token"),
    refresh_token=td.get("refresh_token"),
    token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
    client_id=client_info.get("client_id"),
    client_secret=client_info.get("client_secret"),
    scopes=td.get("scope", "https://www.googleapis.com/auth/spreadsheets").split(),
)
```

## Refresh-Error Root Cause

Before the fix (plugin v1.0.0), `_get_creds()` only read `tokens.json` and expected `client_id`, `client_secret`, and `scopes` (plural, array) to be present. The google-mcp format uses `scope` (singular, string) and puts `client_id`/`client_secret` in a separate file. This caused:

```
RefreshError: The credentials do not contain the necessary fields need to refresh
the access token. You must specify refresh_token, token_uri, client_id, and client_secret.
```

**Diagnosis workflow:**
1. Check if `tokens.json` has `client_id` — it won't
2. Read `credentials.json` — it has `client_id` and `client_secret` under `installed`
3. Check `scope` field — it's singular, space-separated
4. Fix `_get_creds()` to read both files and `.split()` the scope
