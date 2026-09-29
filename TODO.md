# MCP PDF ingestion task status

Updated: 2026-09-29. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- MCP-01: `done`, consistent with the existing owner-maintained task table.
- MCP-02: `done`.
- Assigned batch: MCP-11B.1 direct probes -> MCP-11B.2 SDK/Windows/docs (authorized 2026-09-29); no live requests.
- MCP-03, MCP-04 and MCP-05: `done`; implementation and batch validation complete.
- MCP-06 and MCP-07: `done`; implementation and batch validation complete.
- MCP-08A and MCP-08B: `done`; implementation and batch validation complete.
- MCP-09A and MCP-09B: `done`; implementation and batch validation complete.
- MCP-10 and MCP-11A: `review_pending`; prior HISTORY/resume recorded no owner acceptance.
- MCP-11B: `in_progress`; implementation checks passed, real execution/manual review pending.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
Only explicit owner acceptance permits `done`. This assigned batch may continue
sequentially after focused checks; full checks run once after MCP-11B.2.

## Thread and commit tracking

One task row is a deliverable, usually one owner-made commit. A task can span
several assigned blocks/threads. Intermediate blocks leave the parent `in_progress`;
only the final block can mark it `review_pending`. Owner acceptance permits `done`.
Do not automatically start an unassigned block; MCP-11B.1/11B.2 implementation is authorized, not live requests.
Use PLAN for scope and commit messages.

Observed 2026-09-29: branch `feat/pdf-evidence-tool`; initial local change only
added `.env` to `.gitignore` and is preserved. No Git mutations. MCP-10/MCP-11A
table statuses reconciled with their prior review_pending HISTORY/resume; no new
owner acceptance inferred. Earlier owner-maintained statuses are unchanged.

## Tasks

| ID | Deliverable | Status |
| --- | --- | --- |
| MCP-01 | Six neutral tools, no reviewer policy | done |
| MCP-02 | One configured PDF and isolated run directory | done |
| MCP-03 | Repeatable, complete page reads | done |
| MCP-04 | Complete section reads by ID | done |
| MCP-05 | Paginated textual search | done |
| MCP-06 | Unambiguous assets without consumption quotas | done |
| MCP-07 | Paginated, filtered asset catalog | done |
| MCP-08A | Exact crops and full-page images | done |
| MCP-08B | Reuse of materialized images | done |
| MCP-09A | One-call visual helper and diagnostics | done |
| MCP-09B | Visual questions through get_asset | done |
| MCP-10 | Package identity and setup alignment | review_pending |
| MCP-11A | Complete local stdio contract verification | review_pending |
| MCP-11B | Standalone probes and handoff evidence | in_progress |

Dependencies follow table order. Real endpoint and consumer integration are deferred;
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

- MCP-11B.3 remains pending owner-run real visual/agent commands and manual review.
- Exact input located: `papers/004_microstrip_patch.pdf`; catalog ran without a model.
- Models/endpoint credentials remain owner-selected; never put their values here.
- Earlier Windows chmod test failure is addressed with a POSIX-only mode assertion;
  location/cache/persistence assertions remain on Windows. Full results below.
- Five corpus tests require `REVIEWER_WORKSPACE`; no corpus/remote checks enabled.
- Owner reviews scientific accuracy; later consumer integration remains separate.

## Deferred limitations

- Inherited heading, table and equation extraction errors need reproduced cases
  before changes. They are not an instruction to retune the parser now.
- Multipage asset images cover only the stored first-page region and explicitly report partial coverage.
  Full-page images are available through page:N; no stitching or missing-region inference.
- Full-document OCR, new detection families, semantic retrieval, automatic fallback
  and global optimization budgets are outside this plan.

## Resume note

- MCP-11B.1/11B.2 implementation complete; parent in_progress, live block 11B.3 pending.
- Added scripts/probe_mcp.py: catalog/inspect/agent, local dotenv, explicit models/timeouts, failure records.
- Added optional probes extra/lock, synthetic/mock tests, Windows CI and POSIX-only store-mode assertion.
- Preserved existing .env ignore; ignored probe outputs; no production server/cache/heuristic changes.
- SDK 0.22.3 inspected locally; required websockets adjustment 17.1 -> 16.1.1, no unrelated upgrades.
- Windows CPython 3.14.3: focused test_probe_mcp.py 12 passed; CLI help and real PDF catalog passed (23 assets, 2 pages).
- Fake agent checks cover zero retries/tracing, six tools, visual evidence and cleanup; actual SDK stdio tested without models.
- README/PLAN/AGENTS updated; MCP-10/MCP-11A contradictory done statuses reconciled to review_pending.
- Final full discovery: 135 run, 130 passed, 5 corpus skips; includes 13 probe tests. Ruff/Basedpyright/Vulture/diff passed.
- Exact checks: .venv/Scripts/python.exe -m unittest discover -s tests -p test_*.py -q; .venv/Scripts/{ruff.exe check .,basedpyright.exe,vulture.exe}; git diff --check; logs tmp/mcp-11b-*.log.
- No live requests, consumer work, owner acceptance or Git mutations. Next: owner manual commands for 11B.3 and review; no further implementation block authorized.
