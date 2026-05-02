<!-- SYNC IMPACT REPORT
  Version change: N/A → 1.0.0 (initial ratification)
  Modified principles: none (initial)
  Added sections: Core Principles, Security Requirements, Development Workflow, Governance
  Removed sections: none
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ no changes needed (Constitution Check section already present)
    - .specify/templates/spec-template.md ✅ no changes needed
    - .specify/templates/tasks-template.md ✅ no changes needed (security hardening task already listed)
  Follow-up TODOs: none
-->

# Email Unsubscribe Manager Constitution

## Core Principles

### I. Strict Component Separation

Each of the four pipeline components (IMAP Scanner, Review Queue Builder, Selection
Processor, Unsubscribe Executor) MUST operate as a fully independent script with no
direct imports or shared in-process state between them. Inter-component communication
MUST occur exclusively through the `scan_results.json` file contract and the Notion
database layer. A component MUST be runnable, testable, and replaceable in isolation
without modifying any other component.

### II. Minimal Dependencies

The dependency surface MUST be kept to the smallest possible footprint. The stdlib
(`imaplib`, `json`, `http.client`, `email`) MUST be preferred over third-party packages
for any capability it provides. Third-party packages MUST only be added when the stdlib
genuinely cannot meet the requirement (e.g., `requests` for HTTP). Every new dependency
MUST be explicitly justified and pinned in `requirements.txt`. No transitive heavy
frameworks (e.g., ORM, web framework, async runtime) shall be introduced.

### III. Credential & Secret Security (NON-NEGOTIABLE)

Secrets (IMAP password, Notion API token, Slack webhook URL) MUST reside exclusively
in `config.json`, which MUST be listed in `.gitignore` and MUST never be committed.
Only `config.json.example` with empty placeholder values is tracked. Code MUST load
credentials at runtime from the config file; credentials MUST NOT be hardcoded,
interpolated into log output, or passed as command-line arguments. Any new credential
field MUST be added to `config.json.example` with an empty value and documented in
the README.

### IV. Reliability & Graceful Failure

Each component MUST handle transient failures (network errors, IMAP timeouts, Notion
API rate limits) with explicit error logging and a non-zero exit code rather than
silent swallowing of exceptions. Components MUST be idempotent where possible — running
a component twice MUST NOT produce duplicate Notion entries or duplicate unsubscribe
requests. The `scan_results.json` intermediate file MUST be treated as a durable
handoff artifact: if a downstream component cannot find it or it is malformed, the
component MUST exit with a clear error message.

### V. Observability & Auditability

Every component MUST write a human-readable summary to stdout upon completion
(consistent with the existing Slack summary pattern). All unsubscribe actions MUST be
logged to the Notion Action Log before the component exits. Log output MUST include the
component name, timestamp, counts of processed/skipped/failed items, and any errors
encountered. Debug-level verbosity MUST be achievable without code changes (e.g.,
via a config flag or environment variable).

## Security Requirements

- `config.json` MUST be `.gitignore`d at all times; CI or pre-commit hooks SHOULD
  verify this if the project gains automated pipelines.
- HTTP unsubscribe requests (Component 4) MUST follow RFC 8058 one-click POST semantics
  and MUST NOT follow open redirects or execute JavaScript.
- The Notion API token MUST be scoped to the minimum required databases (Review Queue,
  Whitelist, Blacklist, Action Log) and MUST NOT be a full workspace integration token
  if avoidable.
- `scan_results.json` MUST NOT contain email body content, only headers and metadata
  necessary for triage.

## Development Workflow

- Changes to the inter-component data contract (`scan_results.json` schema) MUST be
  reflected in all affected components and in the README in the same commit.
- New components or scheduled scripts MUST document their trigger schedule in the
  README scheduling table.
- Each component MUST remain independently executable via `python componentN_*.py`
  with no required arguments beyond the presence of `config.json`.
- Code style follows standard Python (PEP 8); no linter is enforced but consistency
  with the existing codebase is expected.

## Governance

This constitution supersedes all informal conventions. Amendments require updating this
file, bumping the version according to semantic versioning rules (MAJOR: principle
removal/redefinition; MINOR: new principle or section; PATCH: clarification/wording),
and updating the Sync Impact Report comment at the top of this file. All implementation
plans MUST include a Constitution Check section verifying compliance with the principles
above before proceeding to task generation.

**Version**: 1.0.0 | **Ratified**: 2026-05-02 | **Last Amended**: 2026-05-02
