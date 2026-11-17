#!/usr/bin/env python3
"""Merge-checked, read-back-verified single-cell writes to the worked-hours sheet.

    ~/.hermes/hermes-agent/venv/bin/python scripts/sheet_write_checked.py \
        [--dry-run] 'November26!C14' 1 'November26!F14' 'MTMPRO label'

CELL VALUE pairs are written one single cell at a time, USER_ENTERED (pitfall 8:
never write a row range). Before anything is written it refuses any target row
covered by a merge, because a merged row silently redirects the value to the
merge anchor (pitfall 27). After each write it reads the cell back and exits 1
if what is stored does not match what was sent, so a silent no-op write never
reports as success. --dry-run does the merge check and prints the plan only.
Run it with the Hermes venv python (only interpreter with google-api-python-client).
"""
import json
import pathlib
import re
import sys

import googleapiclient.discovery
from google.oauth2.credentials import Credentials

SPREADSHEET_ID = "REPLACE_SPREADSHEET_ID"
HOME = pathlib.Path.home()
CRED_PATH = HOME / ".config/google-mcp/credentials.json"
TOK_PATH = HOME / ".local/share/google-mcp/tokens.json"


def credentials():
    cred = json.loads(CRED_PATH.read_text())
    cred = cred.get("installed") or cred.get("web") or cred
    tok = json.loads(TOK_PATH.read_text())
    return Credentials(
        tok.get("access_token"),
        refresh_token=tok.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cred.get("client_id"),
        client_secret=cred.get("client_secret"),
    )


def row_of(a1):
    hit = re.search(r"(\d+)$", a1)
    if not hit:
        sys.exit("no row number in %r - use Tab!Cell form" % a1)
    return int(hit.group(1))


def same(stored, written):
    try:
        return abs(float(stored) - float(written)) < 1e-9
    except (TypeError, ValueError):
        return str(stored) == str(written)


def main():
    dry = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if not args or len(args) % 2:
        sys.exit(__doc__)
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]

    for ref, _ in pairs:
        if "!" not in ref:
            sys.exit("use Tab!Cell form: %r" % ref)

    sh = googleapiclient.discovery.build(
        "sheets", "v4", credentials=credentials(), cache_discovery=False)

    wanted = {}
    for ref, _ in pairs:
        tab, a1 = ref.split("!", 1)
        wanted.setdefault(tab, set()).add(row_of(a1))

    meta = sh.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields="sheets(properties(title),merges)").execute()
    merges_by_tab = {s["properties"]["title"]: s.get("merges", [])
                     for s in meta["sheets"]}
    for tab, rows in wanted.items():
        if tab not in merges_by_tab:
            sys.exit("no tab named %r" % tab)
        for row in sorted(rows):
            for merge in merges_by_tab[tab]:
                # sheet row R (1-based) is index R-1, half-open merge range
                if merge["startRowIndex"] < row <= merge["endRowIndex"]:
                    sys.exit("row %d of %s is merged %s; unmerge before writing"
                             % (row, tab, merge))

    if dry:
        for ref, val in pairs:
            print("dry run, would write", ref, "=", repr(val))
        return

    for ref, val in pairs:
        sh.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=ref,
            valueInputOption="USER_ENTERED", body={"values": [[val]]}).execute()
        values = sh.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=ref,
            valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [])
        stored = values[0][0] if values and values[0] else ""
        print("wrote", ref, "stored:", repr(stored))
        if not same(stored, val):
            sys.exit("read-back mismatch at %s: stored %r, wanted %r"
                     % (ref, stored, val))


if __name__ == "__main__":
    main()
