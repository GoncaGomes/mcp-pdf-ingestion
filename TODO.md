# MCP PDF ingestion task status

Updated: 2026-09-26. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- Assigned batch: MCP-03 -> MCP-04 -> MCP-05 (explicitly authorized 2026-09-26).
- MCP-03, MCP-04 and MCP-05: `review_pending`; implementation and batch validation complete.
- Batch stopped after MCP-05; owner review/acceptance is next. No MCP-06 work authorized here.
- MCP-01: `done`, consistent with the existing owner-maintained task table.
- MCP-02: `review_pending`; no new owner acceptance recorded.
- MCP-00 is planning, not an implementation task.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
Only explicit owner acceptance permits `done`. This assigned batch may continue
sequentially after focused checks; full checks run once after MCP-05.

## Thread and commit tracking

One task row is a deliverable, usually one owner-made commit. A task can span
several assigned blocks/threads. Intermediate blocks leave the parent `in_progress`;
only the final block can mark it `review_pending`. Owner acceptance permits `done`.
Do not automatically start an unassigned block; the assigned MCP-03–05 batch is authorized.
Use PLAN for scope and commit messages.

Observed 2026-09-26 (read-only Git inspection): branch `feat/pdf-evidence-tool`,
HEAD `4ea837b94f87890951c5b9f54b147bfcd28c0cad` (`fix(config): reject non-PDF and
password-protected documents`); preceding commit `171ef17` implements MCP-02.
The working tree was clean before this batch. Commit presence does not imply acceptance.

## Tasks

| ID | Deliverable | Status |
| --- | --- | --- |
| MCP-01 | Six neutral tools, no reviewer policy | done |
| MCP-02 | One configured PDF and isolated run directory | review_pending |
| MCP-03 | Repeatable, complete page reads | review_pending |
| MCP-04 | Complete section reads by ID | review_pending |
| MCP-05 | Paginated textual search | review_pending |
| MCP-06 | Unambiguous assets without consumption quotas | pending |
| MCP-07 | Paginated, filtered asset catalog | pending |
| MCP-08A | Exact crops and full-page images | pending |
| MCP-08B | Reuse of materialized images | pending |
| MCP-09A | One-call visual helper and diagnostics | pending |
| MCP-09B | Visual questions through get_asset | pending |
| MCP-10 | Package identity and setup alignment | pending |
| MCP-11A | Complete local stdio contract verification | pending |
| MCP-11B | Authorized probes and consumer handoff evidence | pending |

Dependencies follow table order. External SDK integration is deferred for this batch;
the coding agent does not inspect or modify the consumer repository.

## MCP-02 implementation blocks

| Block | Deliverable | Progress |
| --- | --- | --- |
| MCP-02.1 | Configuration loader and focused tests | implemented |
| MCP-02.2 | Startup/store binding and six tool signatures | implemented |
| MCP-02.3 | Process isolation checks and task closure | implemented |

Block progress: `pending`, `in_progress`, `implemented`, `blocked`. `implemented`
means its specified checks passed; it does not mean owner acceptance of the task.

## Blockers and external evidence

- MCP-01 is done per the existing task table; MCP-02 still awaits acceptance.
- Pre-existing Windows issues observed on this machine: chmod 0o700 is not
  enforced (one `test_store` failure) and temporary-file locks during cleanup
  are flaky; corpus/real-PDF tests skip without `REVIEWER_WORKSPACE`.
- MCP-11B requires owner-selected model/configuration, a probe input and explicit
  authorization. Never put credential values in this file.
- Real-paper checks require owner-supplied PDFs. Report unavailable cases as skipped.
- The owner reviews scientific accuracy and runs/authorizes consumer integration.

## Deferred limitations

- Inherited heading, table and equation extraction errors need reproduced cases
  before changes. They are not an instruction to retune the parser now.
- Multipage assets may have partial visual coverage; full pages remain addressable.
- Full-document OCR, new detection families, semantic retrieval, automatic fallback
  and global optimization budgets are outside this plan.

## Resume note

- Batch MCP-03–05 complete for owner review; all three tasks `review_pending`, none marked `done`.
- Page reads are repeatable/lossless; section IDs retain boundaries and source pages; search paginates FTS records.
- Changed source: `src/reviewer_mcp/reading.py`, `server.py`, `store.py`, `papers.py`.
- Changed tests: `tests/test_reading.py` (new), `test_server.py`, `test_indexes.py`, `test_document_binding.py`.
- Changed docs: `README.md`, `TODO.md`, `HISTORY.md`, `PLAN.md`, `AGENTS.md`.
- Focused venv tests (latest runs): reading 15 OK, server 13 OK, indexes 7 run/1 corpus skip, binding 6 OK.
- Full `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -q`: 89 run, 1 failure, 5 skips.
- Sole failure: known Windows chmod assertion `test_store_location_permissions_and_cache` (511 != 448);
  5 corpus tests skipped without `REVIEWER_WORKSPACE`. Full log: `tmp/mcp-03-05-unittest.log` (ignored).
- `.venv/Scripts/ruff.exe check .`, `.venv/Scripts/basedpyright.exe`, `.venv/Scripts/vulture.exe`, `git diff --check`: clean.
- Existing venv is CPython 3.14.3; no dependency/setup changes. Asset/image limitations remain; SDK probes deferred.
- Next: owner review and acceptance; suggested per-task commit messages remain in PLAN. No Git mutations performed.
