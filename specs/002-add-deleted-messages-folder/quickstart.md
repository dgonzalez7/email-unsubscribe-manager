# Quickstart: Add "Deleted Messages" Folder to IMAP Scanner

**Feature**: 002-add-deleted-messages-folder
**Date**: 2026-05-02

## Prerequisites

- Python 3.11+ installed
- `requests` installed (`pip install requests`)
- Valid `config.json` present at the repository root

## Setup

1. Update `config.json` to add the new folder and window keys:

   ```json
   "folders": {
     "inbox": "INBOX",
     "junk": "Junk",
     "trash": "Trash",
     "deleted": "Deleted Messages"
   },
   "defaults": {
     "since_hours": 24,
     "trash_since_hours": 24,
     "deleted_since_hours": 24
   }
   ```

   Adjust `"deleted"` value to match the exact folder name on your Fidei server
   if it differs from `"Deleted Messages"`. Adjust `deleted_since_hours` to
   control how far back the scanner looks in that folder.

## Running the Scanner

```powershell
python component1_scan.py
```

Diagnostic output goes to stderr; the JSON result goes to stdout and is also
written to `scan_results.json`.

## Verifying the Change

After running, confirm:

1. The stderr output includes a line like:
   ```
   [INFO] 'Deleted Messages': N messages since DD-Mon-YYYY
   ```
2. `scan_results.json` contains entries with `"source_folder": "Deleted Messages"`
   if any qualifying emails were found.
3. The Slack summary lists `Deleted Messages` in the "Folders scanned" line.

If the folder name is wrong or doesn't exist on the server, you will see:
```
[WARN] Could not select 'Deleted Messages': ...
```
Correct the `folders.deleted` value in `config.json` and re-run.
