# Data Model: Add "Deleted Messages" Folder to IMAP Scanner

**Feature**: 002-add-deleted-messages-folder
**Date**: 2026-05-02

## Config Schema Changes

The only data model change in this feature is an extension of `config.json`.

### `folders` object — new key

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `deleted` | string | `"Deleted Messages"` | IMAP folder name for deleted items on the server. Must match the exact folder name as reported by the server. |

Existing keys (`inbox`, `junk`, `trash`) are unchanged.

### `defaults` object — new key

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `deleted_since_hours` | integer | `24` (falls back to `trash_since_hours` if absent) | Look-back window in hours for the "Deleted Messages" folder scan. |

Existing keys (`since_hours`, `trash_since_hours`) are unchanged.

### Full updated `config.json` shape

```json
{
  "imap": {
    "host": "",
    "port": 993,
    "username": "",
    "password": ""
  },
  "notion": {
    "api_token": ""
  },
  "slack": {
    "webhook_url": ""
  },
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
}
```

## `scan_results.json` schema — unchanged

The `source_folder` field already captures which IMAP folder an entry originated
from. No schema change is required; "Deleted Messages" entries will simply appear
with `"source_folder": "Deleted Messages"` (or the configured name), which
downstream components already handle transparently.

## Validation Rules

- `folders.deleted` MUST be a non-empty string if present; if absent the scanner
  defaults to `"Deleted Messages"`.
- `defaults.deleted_since_hours` MUST be a positive integer if present; if absent
  the scanner falls back to `defaults.trash_since_hours`, then to `24`.
- No uniqueness constraint is enforced on folder names in config — if the user
  configures the same name for two keys, the scanner will scan that folder twice
  and deduplication by domain will collapse any duplicates in the output.
