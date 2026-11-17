# Google Workspace MCP Server Setup

## Server

**Repository:** `quinnjr/google-mcp` (MIT license)
**Location:** `~/Documents/agent-tools/google-mcp/`
**Entry point:** `~/Documents/agent-tools/google-mcp/dist/index.js`
**Run command:** `node ~/Documents/agent-tools/google-mcp/dist/index.js`

## Hermes Config

```yaml
mcp_servers:
  google:
    command: "node"
    args: ["/home/user1011/Documents/agent-tools/google-mcp/dist/index.js"]
```

Set via: `hermes config set mcp_servers '{"google": {"command": "node", "args": ["/home/user1011/Documents/agent-tools/google-mcp/dist/index.js"]}}'`

## OAuth Credentials

Credentials file location (macOS):
```
~/.config/google-mcp/credentials.json
```

Token auto-stored at:
```
~/.local/share/google-mcp/tokens.json
```

## Setup Steps

1. Create Google Cloud project + OAuth Desktop client at https://console.cloud.google.com/apis/credentials
2. Enable APIs: Gmail, Calendar, Drive, Sheets, Docs, People, YouTube Data, Tasks, Forms
3. Download OAuth client JSON, rename to `credentials.json`, place in `~/.config/google-mcp/`
4. Restart Hermes — MCP server loads at startup
5. Call `google_auth` tool on first use to complete OAuth flow

## MCP Tools Available

70+ tools across: Calendar (11), Gmail (12), Contacts (6), Drive (10), Docs (6), Sheets (9), Slides (9), YouTube (10), Tasks (8), Forms (8), Chat (7), Meet (14)

All namespaced as `mcp_google_<service>_<action>` (e.g., `mcp_google_gmail_search`, `mcp_google_calendar_list_events`, `mcp_google_sheets_update`).

## Build

```bash
cd ~/Documents/agent-tools/google-mcp
npm install
npm run build
```

## Known Limitation

The `mcp` Python SDK requires Python 3.10+. The system Python (3.9.6 from Xcode) can't load it, but Hermes' own venv at `~/.hermes/hermes-agent/venv/` runs Python 3.11 and has `mcp` installed.
