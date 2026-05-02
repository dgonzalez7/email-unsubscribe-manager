# Research: Add "Deleted Messages" Folder to IMAP Scanner

**Feature**: 002-add-deleted-messages-folder
**Date**: 2026-05-02

## Decision 1: Config key name for the new folder

- **Decision**: Use `"deleted"` as the key under `folders` in `config.json`, with a
  default value of `"Deleted Messages"`.
- **Rationale**: Consistent with existing keys (`inbox`, `junk`, `trash`) — short
  lowercase role name as key, actual server folder name as value. Follows the
  established pattern exactly.
- **Alternatives considered**: `"deleted_messages"` (too verbose given the pattern),
  `"deleted_items"` (Outlook-specific terminology, not appropriate for Roundcube).

## Decision 2: Look-back window for "Deleted Messages"

- **Decision**: Add `"deleted_since_hours"` under `defaults` in `config.json`,
  defaulting to the same value as `trash_since_hours` (24 hours) if not set.
- **Rationale**: "Deleted Messages" behaves analogously to Trash — items land there
  after deletion and may persist for days. Sharing the same default as `trash_since_hours`
  is a sensible starting point. Making it independently configurable (rather than
  hard-linking to `trash_since_hours`) allows the user to set a longer window for
  deleted items without affecting the trash scan.
- **Alternatives considered**: Reuse `trash_since_hours` directly (no new key) — rejected
  because it removes independent control; hardcode 48 hours — rejected as arbitrary.

## Decision 3: Refactor folder loop to be data-driven

- **Decision**: Replace the hardcoded three-folder loop in `main()` with a list built
  from the config's `folders` dict, each paired with its corresponding `since_hours`
  value. The existing `scan_folder()` function is unchanged.
- **Rationale**: Adding a fourth folder via a hardcoded call (`scan_folder(imap, deleted_folder, deleted_since_hours)`) would work but creates a growing list of discrete calls. A data-driven approach maps each folder key to its window and loops once, making future folder additions config-only with no code change.
- **Alternatives considered**: Simple fourth hardcoded call — works but doesn't scale;
  fully generic "scan all IMAP folders" approach — over-engineered, the user wants explicit opt-in control via config.

## Decision 4: No contracts directory needed

- **Decision**: Skip the `contracts/` Phase 1 artifact for this feature.
- **Rationale**: This project has no external API, CLI argument interface, or
  inter-process contract that changes. The only interface change is within
  `config.json`, which is fully documented in `data-model.md` and `config.json.example`.
- **Alternatives considered**: Document `scan_results.json` schema as a contract —
  the schema is unchanged by this feature, so no contract update is warranted.
