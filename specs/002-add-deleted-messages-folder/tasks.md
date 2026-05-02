---
description: "Task list for Add Deleted Messages Folder to IMAP Scanner"
---

# Tasks: Add "Deleted Messages" Folder to IMAP Scanner

**Input**: Design documents from `specs/002-add-deleted-messages-folder/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, research.md ✅

**Tests**: Not requested — no test tasks generated.

**Organization**: Single user story (US1); setup and foundational phases are minimal
given the narrow scope of this change.

---

## Phase 1: Setup

**Purpose**: No new project initialization needed. This phase covers the config
example update that establishes the data contract before code changes.

- [ ] T001 Add `"deleted": "Deleted Messages"` key to `folders` object in `config.json.example`
- [ ] T002 [P] Add `"deleted_since_hours": 24` key to `defaults` object in `config.json.example`

---

## Phase 2: Foundational

**Purpose**: Read the new config keys in `component1_scan.py` so they are available
to the folder loop. This is a prerequisite for the US1 implementation tasks.

- [ ] T003 In `component1_scan.py` `main()`, read `folders_cfg.get("deleted", "Deleted Messages")` into `deleted_folder` variable
- [ ] T004 In `component1_scan.py` `main()`, read `int(defaults.get("deleted_since_hours", trash_since_hours))` into `deleted_since_hours` variable (must run after T003 since `trash_since_hours` must already be resolved)

**Checkpoint**: New config keys are read and available — US1 implementation can begin.

---

## Phase 3: User Story 1 — Scan "Deleted Messages" for Unsubscribe Opportunities (Priority: P1) 🎯 MVP

**Goal**: The IMAP Scanner scans "Deleted Messages" on every run, includes results in
`scan_results.json`, and lists the folder in the Slack summary. Deduplication applies
across all folders including this one.

**Independent Test**: Update `config.json` with `"deleted": "Deleted Messages"` and
`"deleted_since_hours": 24`, place a test email with a `List-Unsubscribe` header in
the "Deleted Messages" folder on the Fidei server, run `python component1_scan.py`,
and verify: (1) stderr shows `[INFO] 'Deleted Messages': N messages since ...`,
(2) `scan_results.json` contains an entry with `"source_folder": "Deleted Messages"`,
(3) Slack summary lists "Deleted Messages" in folders scanned.

### Implementation for User Story 1

- [ ] T005 [US1] Refactor the hardcoded folder loop in `component1_scan.py` `main()` — replace the three discrete `scan_folder` calls for inbox/junk and trash with a data-driven list of `(folder_name, since_hours)` tuples built from config, then iterate once with `scan_folder`; ensure `folders_scanned` list is populated from the same loop in `component1_scan.py`
- [ ] T006 [US1] Add the `deleted_folder` / `deleted_since_hours` pair to the data-driven folder list in `component1_scan.py` `main()` (depends on T005)
- [ ] T007 [US1] Verify the `send_slack_notification` call in `component1_scan.py` passes the full `folders_scanned` list (now populated from the loop) so "Deleted Messages" appears in the Slack summary (depends on T006)

**Checkpoint**: User Story 1 is fully functional. Run the independent test above to
validate before proceeding.

---

## Phase 4: Polish & Cross-Cutting Concerns

- [ ] T008 [P] Update `README.md` scheduling table or setup section to mention the `folders.deleted` and `defaults.deleted_since_hours` config keys
- [ ] T009 [P] Manually verify `config.json` (gitignored, local) is updated with the new keys before the next scheduled Task Scheduler run

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately; T001 and T002 are parallel
- **Foundational (Phase 2)**: Depends on Phase 1 completion; T004 depends on T003
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion; T005 → T006 → T007 sequential
- **Polish (Phase 4)**: Depends on Phase 3 completion; T008 and T009 are parallel

### Within User Story 1

- T005 (refactor loop) MUST complete before T006 (add deleted folder to loop)
- T006 MUST complete before T007 (verify Slack summary)
- T005 is the highest-risk task — review the existing `main()` loop carefully before refactoring

### Parallel Opportunities

- T001 and T002 (config.json.example updates) can be done simultaneously
- T008 and T009 (polish) can be done simultaneously after T007

---

## Implementation Strategy

### MVP (all tasks — feature is small)

1. Complete Phase 1: Update `config.json.example` (T001, T002)
2. Complete Phase 2: Read new config keys in `main()` (T003, T004)
3. Complete Phase 3: Refactor loop + add folder + verify Slack (T005, T006, T007)
4. **STOP and VALIDATE**: Run independent test against Fidei server
5. Complete Phase 4: README update + local config update (T008, T009)

---

## Notes

- [P] tasks = different files or no dependencies on incomplete tasks
- [US1] label maps each task to User Story 1 for traceability
- T005 is the most structural change — the refactor must preserve exact existing
  behaviour for Inbox, Junk, and Trash before adding the new folder
- The existing `scan_folder()` function requires **no changes** — it already handles
  missing/unreachable folders with a warning (FR-004 is already satisfied)
- Deduplication (`deduplicate_by_domain`) requires **no changes** — it operates on
  the combined results list regardless of how many folders were scanned (FR-005
  already satisfied)
- After completing all tasks, open a pull request from `002-add-deleted-messages-folder`
  into `master` on GitHub
