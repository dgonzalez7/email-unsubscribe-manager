# Feature Specification: Automated Email Unsubscribe Pipeline

**Feature Branch**: `001-email-unsubscribe-pipeline`
**Created**: 2026-05-02
**Status**: Draft
**Input**: Existing four-component automated pipeline for managing mailing list unsubscribes via IMAP, Notion, and Slack.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nightly Email Discovery (Priority: P1)

The user's inbox, junk, and trash folders are automatically scanned each night for
emails from mailing lists that offer an unsubscribe option. The pipeline identifies
unique sender domains and captures the information needed to act on them later.
The user wakes up each morning knowing that any new mailing list senders from the
previous day have been queued for review — without any manual effort.

**Why this priority**: This is the foundation of the entire pipeline. No downstream
triage, routing, or unsubscribe action is possible without the discovery scan running
first. It delivers immediate value by eliminating the need to manually hunt for
unsubscribe opportunities.

**Independent Test**: Can be fully tested by running the IMAP scanner against a
mailbox containing known mailing list emails and verifying that `scan_results.json`
is produced with the correct sender domains, unsubscribe URLs, and deduplication
applied.

**Acceptance Scenarios**:

1. **Given** the mailbox contains emails with `List-Unsubscribe` headers in Inbox,
   Junk, or Trash, **When** the scanner runs, **Then** each unique sender domain is
   captured with its most recent unsubscribe URL, one-click flag, and source folder.
2. **Given** multiple emails from the same sender domain exist across folders,
   **When** the scanner runs, **Then** only the most recent email per domain appears
   in the output (deduplication by domain).
3. **Given** the IMAP server is unreachable or credentials are invalid, **When** the
   scanner runs, **Then** the component exits with a non-zero code and logs a clear
   error; no partial output file is written.
4. **Given** a folder name in the config does not exist on the server, **When** the
   scanner runs, **Then** a warning is logged and scanning continues for the remaining
   folders.

---

### User Story 2 - New Sender Triage Queueing (Priority: P1)

After the nightly scan, any sender domains not already known to the system are
automatically added to a Notion Review Queue for the user to triage. Senders already
in the Whitelist, Blacklist, or Review Queue are skipped. The user receives a Slack
notification summarising what was added so they can begin triage at their convenience.

**Why this priority**: Without this step, the scan results remain an unstructured
file with no workflow. This step bridges raw discovery into actionable triage items
and prevents duplicates from accumulating across runs.

**Independent Test**: Can be fully tested by providing a `scan_results.json` with a
mix of known and unknown domains (seeded into Notion test databases) and verifying
that only genuinely new domains produce new Notion Review Queue entries.

**Acceptance Scenarios**:

1. **Given** `scan_results.json` contains sender domains not present in any Notion
   database, **When** the Review Queue Builder runs, **Then** a new entry is created
   in the Notion Review Queue for each unknown domain with sender name, domain,
   subject sample, one-click flag, source folder, unsubscribe URL, and date added.
2. **Given** a sender domain already exists in the Review Queue, Whitelist, or
   Blacklist, **When** the Review Queue Builder runs, **Then** no duplicate entry is
   created for that domain.
3. **Given** `scan_results.json` is missing or malformed, **When** the Review Queue
   Builder runs, **Then** the component exits with a non-zero code, logs the error,
   and posts an error notification to Slack.
4. **Given** the Notion API returns a rate-limit response, **When** the Review Queue
   Builder runs, **Then** the component retries with exponential backoff before
   failing permanently.
5. **Given** all domains are already known, **When** the Review Queue Builder runs,
   **Then** no new entries are created and the Slack summary reflects zero additions.

---

### User Story 3 - Manual Triage Decision Processing (Priority: P2)

After the user has triaged entries in Notion (marking each as Keep, Unsubscribe, or
Skip), running the Selection Processor applies those decisions: Keep entries are moved
to the Whitelist, Unsubscribe entries are moved to the Blacklist, and Skip entries are
archived. Each processed entry is removed from the Review Queue. The user receives a
Slack summary of all routing actions taken.

**Why this priority**: Triage decisions in Notion have no effect until this component
runs. It is the bridge between human judgment and automated action.

**Independent Test**: Can be fully tested by seeding the Notion Review Queue with
entries carrying known Status values (Keep/Unsubscribe/Skip) and verifying correct
routing and archival, independent of the scan or unsubscribe steps.

**Acceptance Scenarios**:

1. **Given** a Review Queue entry has Status = "Keep", **When** the Selection
   Processor runs, **Then** a corresponding entry is created in the Whitelist and
   the Review Queue entry is archived.
2. **Given** a Review Queue entry has Status = "Unsubscribe", **When** the Selection
   Processor runs, **Then** a corresponding entry is created in the Blacklist
   (with `Unsubscribed = false`) and the Review Queue entry is archived.
3. **Given** a Review Queue entry has Status = "Skip", **When** the Selection
   Processor runs, **Then** the Review Queue entry is archived with no routing to
   Whitelist or Blacklist.
4. **Given** routing to Whitelist or Blacklist fails, **When** the Selection Processor
   runs, **Then** the Review Queue entry is NOT archived (data is preserved for retry)
   and the failure count is reflected in the Slack summary.
5. **Given** there are no triaged entries in the Review Queue, **When** the Selection
   Processor runs, **Then** the component exits cleanly and posts a Slack message
   confirming nothing to process.

---

### User Story 4 - Automated Weekly Unsubscribe Execution (Priority: P2)

Once a week, the pipeline automatically submits one-click unsubscribe POST requests
for all Blacklist entries that have not yet been unsubscribed. Successful unsubscribes
are marked in Notion. Failed attempts are retried on subsequent weekly runs up to a
maximum retry limit. Entries without a one-click URL or that have exceeded the retry
limit are flagged for manual attention. The user receives a Slack summary of all
outcomes.

**Why this priority**: This is the final delivery of the pipeline's core promise —
actually stopping unwanted emails. It depends on the Blacklist being populated by
Story 3.

**Independent Test**: Can be fully tested by seeding the Notion Blacklist with entries
in various states (one-click URL present, no URL, retry count at limit, already
unsubscribed) and verifying correct handling of each case, using a mock HTTP endpoint
for the POST requests.

**Acceptance Scenarios**:

1. **Given** a Blacklist entry has `Unsubscribed = false`, a valid unsubscribe URL,
   and `One-Click = true`, **When** the Unsubscribe Executor runs, **Then** a POST
   request is sent to the URL and on success `Unsubscribed` is set to `true` in Notion.
2. **Given** the POST request returns an HTTP error or times out, **When** the
   Unsubscribe Executor runs, **Then** the `Retry Count` is incremented in Notion and
   the entry remains pending for the next run.
3. **Given** a Blacklist entry has `Retry Count >= 3`, **When** the Unsubscribe
   Executor runs, **Then** the entry is skipped and flagged as abandoned in the Slack
   summary.
4. **Given** a Blacklist entry has `One-Click = false` or no unsubscribe URL,
   **When** the Unsubscribe Executor runs, **Then** the entry is flagged for manual
   unsubscribe in the Slack summary and is not modified in Notion.
5. **Given** a Blacklist entry already has `Unsubscribed = true`, **When** the
   Unsubscribe Executor runs, **Then** the entry is not processed (filtered out by
   the query).

---

### Edge Cases

- What happens when the IMAP folder names in `config.json` differ from the actual
  server folder names? → Scanner logs a warning per folder and continues.
- How does the system handle MIME-encoded (QP/Base64) `List-Unsubscribe` headers?
  → Headers are fully decoded before URL extraction.
- What if a sender domain contains Unicode or unusual characters? → Domain is
  normalised to lowercase; any encoding issues are logged and the entry is skipped.
- What if the Notion API is completely unavailable during execution? → Component
  exits with a non-zero code after exhausting retries; error is posted to Slack.
- What if the Slack webhook is not configured? → Warning is logged; component
  continues and exits normally (Slack notification is non-blocking).
- What if `scan_results.json` contains more entries than Notion can handle in one
  run? → Each entry is processed sequentially with rate-limit backoff; no entries
  are silently dropped.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST scan IMAP Inbox, Junk, and Trash folders for emails
  containing `List-Unsubscribe` headers within a configurable look-back window.
- **FR-002**: The system MUST deduplicate scan results by sender domain, retaining
  only the most recent email per domain.
- **FR-003**: The system MUST write scan results to `scan_results.json` as the
  sole handoff artifact between Component 1 and Component 2.
- **FR-004**: The system MUST check each discovered sender domain against all three
  Notion databases (Review Queue, Whitelist, Blacklist) before creating a new entry.
- **FR-005**: The system MUST create Notion Review Queue entries for previously
  unknown sender domains with: sender name, domain, email address, subject sample,
  one-click flag, source folder, unsubscribe URL, and date added.
- **FR-006**: The system MUST route triaged Review Queue entries to the correct
  Notion database (Keep → Whitelist, Unsubscribe → Blacklist) and archive the
  originating Review Queue entry upon successful routing.
- **FR-007**: The system MUST execute RFC 8058 one-click unsubscribe POST requests
  for Blacklist entries where `One-Click = true` and `Unsubscribed = false`.
- **FR-008**: The system MUST mark successfully unsubscribed Blacklist entries with
  `Unsubscribed = true` in Notion.
- **FR-009**: The system MUST increment a `Retry Count` field for failed unsubscribe
  attempts and abandon entries that reach or exceed 3 failed attempts.
- **FR-010**: Every component MUST post a Slack summary upon completion (success or
  failure) detailing counts of items processed, skipped, failed, and any errors.
- **FR-011**: Every component MUST exit with a non-zero code on fatal errors and log
  a descriptive message to stderr.
- **FR-012**: All credentials MUST be loaded from `config.json` at runtime; no
  credential may be hardcoded or appear in any log output.

### Key Entities

- **Sender Domain**: The deduplicated unit of identity throughout the pipeline;
  represents a mailing list source identified by its email domain.
- **Review Queue Entry**: A Notion page holding a pending triage decision for a
  newly discovered sender domain.
- **Whitelist Entry**: A Notion page representing a sender domain the user has
  chosen to keep receiving email from.
- **Blacklist Entry**: A Notion page representing a sender domain the user wants
  to unsubscribe from, with unsubscribe state and retry tracking.
- **scan_results.json**: The file-based handoff contract between the IMAP Scanner
  and the Review Queue Builder; contains an array of sender domain records.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All mailing list senders active in the past 24 hours are discoverable
  by the nightly scan with zero manual intervention required.
- **SC-002**: No sender domain appears more than once across the Review Queue,
  Whitelist, and Blacklist after any pipeline run.
- **SC-003**: 100% of one-click unsubscribe attempts that receive an HTTP 2xx
  response are marked as unsubscribed in Notion within the same weekly run.
- **SC-004**: Each component completes its execution and posts a Slack summary
  regardless of whether individual items succeed or fail (no silent failures).
- **SC-005**: A sender domain that has been triaged and unsubscribed does not
  reappear in the Review Queue on subsequent runs.
- **SC-006**: Each component is independently runnable in under 5 minutes for a
  mailbox with up to 500 mailing list senders.

## Assumptions

- The IMAP server supports IMAP4rev1 with SSL on port 993 and the standard
  `SINCE` search command.
- The user has a Notion workspace with four databases already created (Review Queue,
  Whitelist, Blacklist, Action Log) and a Notion integration token with write access.
- The Slack webhook URL is pre-configured and functional; Slack notification
  delivery is best-effort and not required for pipeline correctness.
- The system runs on a single Windows machine via Windows Task Scheduler; no
  containerisation, concurrency, or distributed execution is required.
- A single user performs all triage decisions in Notion; no multi-user access
  control is needed.
- Mailing list senders that do not include a `List-Unsubscribe` header are out of
  scope and will not be processed.
- Senders requiring manual (non-one-click) unsubscribe steps are flagged but not
  automatically actioned.
