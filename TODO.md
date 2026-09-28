# MCP PDF ingestion task status

Updated: 2026-09-28. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- Assigned batch: MCP-08A -> MCP-08B (explicitly authorized 2026-09-28).
- MCP-03, MCP-04 and MCP-05: `review_pending`; implementation and batch validation complete.
- MCP-06 and MCP-07: `review_pending`; implementation and batch validation complete.
- MCP-08A and MCP-08B: `review_pending`; implementation and batch validation complete.
- Stopped after MCP-08B; next step is owner review/acceptance.
- MCP-01: `done`, consistent with the existing owner-maintained task table.
- MCP-02: `review_pending`; no new owner acceptance recorded.
- MCP-00 is planning, not an implementation task.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
Only explicit owner acceptance permits `done`. This assigned batch may continue
sequentially after focused checks; full checks run once after MCP-08B.

## Thread and commit tracking

One task row is a deliverable, usually one owner-made commit. A task can span
several assigned blocks/threads. Intermediate blocks leave the parent `in_progress`;
only the final block can mark it `review_pending`. Owner acceptance permits `done`.
Do not automatically start an unassigned block; the assigned MCP-08A–08B batch is authorized.
Use PLAN for scope and commit messages.

Observed 2026-09-28 (read-only Git inspection): branch `feat/pdf-evidence-tool`,
HEAD `6d16490` (`feat(assets): add unique IDs and paginated access without quotas`).
Working tree was clean before MCP-08A/08B. Commit presence does not imply owner
acceptance; earlier task statuses are unchanged.

## Tasks

| ID | Deliverable | Status |
| --- | --- | --- |
| MCP-01 | Six neutral tools, no reviewer policy | done |
| MCP-02 | One configured PDF and isolated run directory | review_pending |
| MCP-03 | Repeatable, complete page reads | review_pending |
| MCP-04 | Complete section reads by ID | review_pending |
| MCP-05 | Paginated textual search | review_pending |
| MCP-06 | Unambiguous assets without consumption quotas | review_pending |
| MCP-07 | Paginated, filtered asset catalog | review_pending |
| MCP-08A | Exact crops and full-page images | review_pending |
| MCP-08B | Reuse of materialized images | review_pending |
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
- Multipage asset images cover only the stored first-page region and explicitly report partial coverage.
  Full-page images are available through page:N; no stitching or missing-region inference.
- Full-document OCR, new detection families, semantic retrieval, automatic fallback
  and global optimization budgets are outside this plan.

## Resume note

- MCP-08A/MCP-08B implemented; both `review_pending`. Earlier task acceptance is unchanged.
- Added exact rotated crops/full pages, page catalog/text, source page IDs and explicit clipping/coverage.
- Lazy atomic PNGs embed geometry/settings/identity metadata; repeat/reopen/restart reuse verified.
- Source: crops.py/server.py/config.json; tests: test_crops.py/test_server.py/pdf_fixtures.py.
- Docs updated: README, PLAN, HISTORY and AGENTS code map; no model/dependency/schema/heuristic changes.
- MCP-08A focused unittest: crops 3 OK, server 20 OK; Ruff/Basedpyright/diff clean.
- MCP-08B focused unittest: crops 11 OK, server 21 OK; crops 11 OK again after exception-import correction.
- Full `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -q`: 108 run, 102 passed, 1 failure, 5 skips.
- Sole failure: known Windows chmod assertion (511 != 448); corpus skips lack REVIEWER_WORKSPACE PDFs.
- Full Ruff/Basedpyright found a long line/private import; corrected, focused Ruff and full Basedpyright clean.
- Full Vulture/diff checks clean. Log: tmp/mcp-08-unittest.log; existing venv CPython 3.14.3 reused.
- Next: owner review/acceptance. Stop after MCP-08B; no Git mutations, consumer work, remote probes or model calls.
