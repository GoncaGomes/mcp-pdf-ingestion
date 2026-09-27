# MCP PDF ingestion task status

Updated: 2026-09-27. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- Assigned batch: MCP-06 -> MCP-07 (explicitly authorized 2026-09-27).
- MCP-03, MCP-04 and MCP-05: `review_pending`; implementation and batch validation complete.
- MCP-06 and MCP-07: `review_pending`; implementation and batch validation complete.
- Stopped after MCP-07; next step is owner review/acceptance.
- MCP-01: `done`, consistent with the existing owner-maintained task table.
- MCP-02: `review_pending`; no new owner acceptance recorded.
- MCP-00 is planning, not an implementation task.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
Only explicit owner acceptance permits `done`. This assigned batch may continue
sequentially after focused checks; full checks run once after MCP-07.

## Thread and commit tracking

One task row is a deliverable, usually one owner-made commit. A task can span
several assigned blocks/threads. Intermediate blocks leave the parent `in_progress`;
only the final block can mark it `review_pending`. Owner acceptance permits `done`.
Do not automatically start an unassigned block; the assigned MCP-06–07 batch is authorized.
Use PLAN for scope and commit messages.

Observed 2026-09-27 (read-only Git inspection): branch `feat/pdf-evidence-tool`,
HEAD `b6d73b5ffd7612a1c08e1268360eaf0fe31dd22a` (`feat(reading): add complete
repeatable reads and paginated search`). Working tree was clean before MCP-06/07.
Commit presence does not imply owner acceptance; MCP-02–05 statuses are unchanged.

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
- Multipage asset images may cover only the first page. Full-page assets await MCP-08;
  page text remains accessible through read_pages.
- Full-document OCR, new detection families, semantic retrieval, automatic fallback
  and global optimization budgets are outside this plan.

## Resume note

- MCP-06/MCP-07 batch implemented; both `review_pending`, no earlier task acceptance inferred.
- Exact canonical asset IDs/mentions, whole-PDF access and no consumption quotas or overview resets.
- Catalog: 20-item SQL pages, overlap filters, stable ordering, full filtered counts and validated cursors.
- Changed source: server.py, store.py, papers.py, crops.py, config.json under src/reviewer_mcp.
- Changed tests: test_server.py, test_assets.py, test_structure.py, test_corpus.py; docs: README/PLAN/TODO/HISTORY.
- Focused venv checks: assets 6 run/1 skip, structure 8 run/1 skip, server 14 OK (MCP-06), 17 OK (MCP-07);
  store 11 run/1 known chmod failure/1 corpus skip. No new unresolved failures.
- Full `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -q`: 93 run, 87 passed, 1 failure, 5 skips.
- Only failure: known Windows chmod assertion (511 != 448); corpus skips require REVIEWER_WORKSPACE.
  Full local log: tmp/mcp-06-07-unittest.log (ignored). Existing venv CPython 3.14.3 reused unchanged.
- `.venv/Scripts/ruff.exe check .`, `.venv/Scripts/basedpyright.exe`, `.venv/Scripts/vulture.exe`, `git diff --check`: clean.
- Next: owner review; stop after MCP-07. Rendering/vision/full-page assets deferred. No Git mutations or model calls.
