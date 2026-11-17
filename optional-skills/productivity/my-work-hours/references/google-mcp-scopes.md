# Google MCP OAuth Scopes — Diagnosis & Fix

## The Error

```
HttpError 403: "Request had insufficient authentication scopes."
```

This fires when the plugin calls Calendar, Sheets, or Drive APIs but the OAuth token in `tokens.json` lacks those scopes.

## Diagnosis

Read `~/.local/share/google-mcp/tokens.json` and inspect the `scope` field (singular, space-separated string):

```bash
python3 -c "import json; t=json.load(open('/home/user1011/.local/share/google-mcp/tokens.json')); print(t.get('scope','MISSING'))"
```

**Bad (only Gmail):**
```
https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.settings.basic
```

**Good (all MCP services):** Must include at minimum:
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/spreadsheets`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/gmail.modify`

Dizio plugin requires calendar + spreadsheets + drive + gmail.modify.

## Full Expected Scope List

The google-mcp server (`pegasusheavy/google-mcp`) requests these 14 scopes in its `SCOPES` array (source: `dist/auth/oauth.js` line 47):

```
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/tasks
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
https://www.googleapis.com/auth/contacts
https://www.googleapis.com/auth/presentations
https://www.googleapis.com/auth/youtube
https://www.googleapis.com/auth/forms.body
https://www.googleapis.com/auth/forms.responses.readonly
https://www.googleapis.com/auth/chat.spaces
https://www.googleapis.com/auth/chat.spaces.create
https://www.googleapis.com/auth/chat.messages
https://www.googleapis.com/auth/chat.messages.create
https://www.googleapis.com/auth/chat.memberships
https://www.googleapis.com/auth/meetings.space.created
https://www.googleapis.com/auth/meetings.space.readonly
```

## Fix: Re-Authenticate with Full Scopes

### Option A: Delete tokens.json and call google_auth

1. Delete `~/.local/share/google-mcp/tokens.json`
2. Call `mcp_google_google_auth` — this opens a browser for OAuth consent
3. Complete the Google OAuth flow in the browser
4. Verify `tokens.json` was written with full scopes

**Known issue (June 2026):** The MCP `google_auth` tool reported success twice but failed to write `tokens.json`. If this happens, the OAuth callback likely completed but the MCP server's file write didn't persist. Fall back to Option B.

### Option B: Manual OAuth via the MCP server directly

Run the MCP server's OAuth module directly from the project directory:

```bash
cd ~/Documents/agent-tools/google-mcp
node -e "
const {GoogleOAuth} = require('./dist/auth/oauth.js');
const oauth = new GoogleOAuth();
oauth.initialize().then(ok => {
  if (!ok) { console.log('No tokens found, starting auth...'); return oauth.authenticate(); }
  console.log('Already authenticated');
}).then(result => console.log('Auth result:', result));
"
```

This runs the same authenticate() flow but in a foreground process where you can see console output and the browser opens directly.

### Option C: Use google_auth + google_auth_code (two-step)

If automatic browser flow fails:
1. Call `mcp_google_google_auth` — if auto-flow fails, it returns a manual auth URL
2. Open the URL in a browser, complete consent
3. Copy the `code` parameter from the redirect URL
4. Call `mcp_google_google_auth_code` with `code=<the code>`

## Verify Fix

After re-auth, confirm scopes:

```bash
python3 -c "import json; t=json.load(open('/home/user1011/.local/share/google-mcp/tokens.json')); scopes=t.get('scope',''); print('calendar' in scopes, 'spreadsheets' in scopes, 'drive' in scopes)"
```

Should print: `True True True`
