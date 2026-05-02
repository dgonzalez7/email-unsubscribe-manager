# Implementation Plan: Add "Deleted Messages" Folder to IMAP Scanner

**Branch**: `002-add-deleted-messages-folder` | **Date**: 2026-05-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/002-add-deleted-messages-folder/spec.md`

## Summary

Extend the IMAP Scanner (`component1_scan.py`) to scan a fourth configurable folder,
"Deleted Messages", in addition to Inbox, Junk, and Trash. The folder name and its
look-back window are added to `config.json` under existing `folders` and `defaults`
keys. The scanner's folder loop is refactored to be data-driven (no hardcoded folder
list), making future folder additions a config-only change. `config.json.example` is
updated to document the new keys. No other components are affected.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `requests` (third-party); `imaplib`, `email`, `json`, `os`, `sys`, `re`, `datetime` (stdlib)
**Storage**: `config.json` (runtime config, gitignored); `scan_results.json` (file-based handoff artifact)
**Testing**: Manual end-to-end test against Fidei IMAP server; no automated test framework currently in use
**Target Platform**: Windows 11, Python 3.11+, Windows Task Scheduler
**Project Type**: CLI scheduled automation script
**Performance Goals**: Complete scan of all folders within existing nightly window; no new performance requirement
**Constraints**: Stdlib-first; no new third-party dependencies; single file change (`component1_scan.py`) plus config example update
**Scale/Scope**: Single-user, single-machine; mailbox with up to ~500 mailing list senders

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Strict Component Separation | ✅ PASS | Only `component1_scan.py` is modified; no cross-component imports or shared state introduced |
| II. Minimal Dependencies | ✅ PASS | No new dependencies; uses existing stdlib + `requests` |
| III. Credential & Secret Security | ✅ PASS | No credentials involved; new config keys are folder names only |
| IV. Reliability & Graceful Failure | ✅ PASS | Missing/unreachable folder logs a warning and continues (existing `scan_folder` pattern) |
| V. Observability & Auditability | ✅ PASS | "Deleted Messages" added to `folders_scanned` list in Slack summary |

**Post-design re-check**: ✅ All gates pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/002-add-deleted-messages-folder/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
component1_scan.py       # Primary change: data-driven folder loop + new config keys
config.json.example      # Add "deleted" folder key and "deleted_since_hours" default
```

**Structure Decision**: Flat single-project layout — all scripts live at the repository
root. No `src/` restructuring; this feature touches exactly two files.
