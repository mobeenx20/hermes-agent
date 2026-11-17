#!/usr/bin/env python3
"""Refresh the google-mcp OAuth access token in place (pitfall 9b).

Run with the Hermes venv python, then call the google_auth tool:
    ~/.hermes/hermes-agent/venv/bin/python scripts/google_token_refresh.py
Never restart google-mcp.service for this: the pooled service can sit at
"Not authenticated" forever while both credential files are valid, because it
checks readiness before it ever attempts a refresh of an expired access token.
The downloaded credentials.json nests the client fields under an "installed"
key, so a top-level client_id lookup raises KeyError; this handles both shapes.
"""
import json
import pathlib
import time
import urllib.parse
import urllib.request

HOME = pathlib.Path.home()
CRED_PATH = HOME / ".config/google-mcp/credentials.json"
TOK_PATH = HOME / ".local/share/google-mcp/tokens.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def main():
    cred = json.loads(CRED_PATH.read_text())
    cred = cred.get("installed") or cred.get("web") or cred
    for key in ("client_id", "client_secret"):
        if not cred.get(key):
            raise SystemExit("credentials.json has no %s under installed/web" % key)
    tok = json.loads(TOK_PATH.read_text())
    if not tok.get("refresh_token"):
        raise SystemExit("tokens.json has no refresh_token; re-authenticate instead")

    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": cred["client_id"],
        "client_secret": cred["client_secret"],
        "refresh_token": tok["refresh_token"],
    }).encode()
    resp = json.load(urllib.request.urlopen(
        urllib.request.Request(TOKEN_URL, data=body), timeout=30))

    tok["access_token"] = resp["access_token"]
    tok["expiry_date"] = int(time.time() * 1000) + int(resp.get("expires_in", 3590)) * 1000
    # full-file rewrite keeps scope, refresh_token and token_type untouched
    TOK_PATH.write_text(json.dumps(tok))
    print("refreshed; expires_in", resp.get("expires_in"))


if __name__ == "__main__":
    main()
