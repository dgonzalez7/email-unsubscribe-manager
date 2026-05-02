# Feature Specification: Add "Deleted Messages" Folder to IMAP Scanner

**Feature Branch**: `002-add-deleted-messages-folder`
**Created**: 2026-05-02
**Status**: Draft
**Input**: Add scanning of the "Deleted Messages" folder on the Fidei IMAP server to the nightly IMAP Scanner run.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scan "Deleted Messages" for Unsubscribe Opportunities (Priority: P1)

When the nightly IMAP Scanner runs, it also scans the "Deleted Messages" folder on
the Fidei server in addition to Inbox, Junk, and Trash. Any mailing list emails that
were deleted without being formally unsubscribed are caught and included in the triage
queue, giving the user a chance to unsubscribe from senders they had simply deleted.

**Why this priority**: This is the entire scope of the feature. Without it the feature
has no value.

**Independent Test**: Can be fully tested by placing a test email with a
`List-Unsubscribe` header into the "Deleted Messages" folder and verifying that the
scanner includes the sender domain in `scan_results.json` after running.

**Acceptance Scenarios**:

1. **Given** the "Deleted Messages" folder contains emails with `List-Unsubscribe`
   headers within the configured look-back window, **When** the scanner runs,
   **Then** those sender domains appear in `scan_results.json` alongside results
   from Inbox, Junk, and Trash.
2. **Given** the same sender domain appears in both "Deleted Messages" and another
   folder, **When** the scanner runs, **Then** only one entry per domain appears in
   `scan_results.json` (the most recent email across all folders).
3. **Given** the "Deleted Messages" folder name is configurable in `config.json`,
   **When** a user sets a custom name for the folder, **Then** the scanner uses that
   custom name rather than the default.
4. **Given** the "Deleted Messages" folder does not exist on the server, **When** the
   scanner runs, **Then** a warning is logged for that folder, scanning continues for
   all other folders, and the component does not exit with an error.
5. **Given** the look-back window for "Deleted Messages" may differ from Inbox/Junk,
   **When** the scanner runs, **Then** the configurable `trash_since_hours` window
   (or a dedicated setting) governs how far back "Deleted Messages" is scanned.

---

### Edge Cases

- What if "Deleted Messages" contains a very large number of emails? → The scanner
  processes each email header-only (no body fetch) and deduplicates by domain, so
  volume affects runtime linearly but does not change correctness.
- What if the folder name on the server uses a different case or namespace prefix?
  → The folder name is taken directly from `config.json`; the user must configure
  it to match the exact server name as reported by the IMAP server.
- What if both "Trash" and "Deleted Messages" exist and overlap? → Deduplication
  by domain across all folders ensures no duplicates in `scan_results.json`
  regardless of folder overlap.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The IMAP Scanner MUST scan a "Deleted Messages" folder in addition to
  Inbox, Junk, and Trash during each run.
- **FR-002**: The "Deleted Messages" folder name MUST be configurable in
  `config.json` under the `folders` key, with a default value of
  `"Deleted Messages"`.
- **FR-003**: The look-back window for "Deleted Messages" MUST be independently
  configurable (defaulting to the same value as `trash_since_hours` if no dedicated
  setting is provided).
- **FR-004**: If the "Deleted Messages" folder is unreachable or does not exist,
  the scanner MUST log a warning and continue scanning the remaining folders without
  exiting.
- **FR-005**: Deduplication by sender domain MUST apply across all five folders
  (Inbox, Junk, Trash, Deleted Messages, and any future additions), retaining only
  the most recent email per domain.
- **FR-006**: The Slack summary posted by the scanner MUST include "Deleted Messages"
  in the list of folders scanned.

### Key Entities

- **Folders configuration**: The `folders` object in `config.json` that maps logical
  folder roles to their actual IMAP folder names on the server.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Mailing list emails present only in "Deleted Messages" are discoverable
  by the nightly scan with no additional manual steps beyond updating `config.json`.
- **SC-002**: No duplicate sender domain entries appear in `scan_results.json` as a
  result of the same sender appearing in both "Deleted Messages" and another folder.
- **SC-003**: The scanner's Slack summary accurately lists "Deleted Messages" as one
  of the scanned folders after the change is applied.
- **SC-004**: Removing or misconfiguring the "Deleted Messages" folder name does not
  cause the scanner to crash or skip the other folders.

## Assumptions

- The Fidei/Roundcube server exposes a folder named "Deleted Messages" (or a
  user-configured equivalent) accessible via IMAP IMAP4rev1 `SELECT`.
- The existing `trash_since_hours` look-back window is an acceptable default for
  "Deleted Messages"; a separate dedicated setting is optional and deferred unless
  the user requests it.
- No changes are needed to Components 2, 3, or 4 — the `source_folder` field in
  `scan_results.json` already records which folder an entry came from, so downstream
  components handle it transparently.
- `config.json.example` must be updated to document the new folder key so new users
  are aware of it.
