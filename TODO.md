# MCP PDF ingestion task status

Updated: 2026-10-05. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- MCP-01: `done`, consistent with the existing owner-maintained task table.
- MCP-02: `done`.
- Assigned block: visual evidence acquisition review (authorized 2026-10-05), two sequential steps; no live requests.
- Visual evidence review: `review_pending`; steps 1 and 2 `implemented`; owner acceptance pending.
- MCP-03, MCP-04 and MCP-05: `done`; implementation and batch validation complete.
- MCP-06 and MCP-07: `done`; implementation and batch validation complete.
- MCP-08A and MCP-08B: `done`; implementation and batch validation complete.
- MCP-09A and MCP-09B: `done`; implementation and batch validation complete.
- MCP-10 and MCP-11A: `done`; prior HISTORY/resume recorded no owner acceptance.
- MCP-11B: `done`; implementation checks passed, real execution/manual review pending.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
Only explicit owner acceptance permits `done`. The current visual evidence review
runs focused assets/indexes/server/crop checks and the repository checks at its final boundary.

## Thread and commit tracking

One task row is a deliverable, usually one owner-made commit. A task can span
several assigned blocks/threads. Intermediate blocks leave the parent `in_progress`;
only the final block can mark it `review_pending`. Owner acceptance permits `done`.
Do not automatically start an unassigned block; targeted review fixes are authorized, not live requests.
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
| MCP-10 | Package identity and setup alignment | done |
| MCP-11A | Complete local stdio contract verification | done |
| MCP-11B | Standalone probes and handoff evidence | done |

Dependencies follow table order. Real endpoint and consumer integration are deferred;
the coding agent does not inspect or modify the consumer repository.


Block progress: `pending`, `in_progress`, `implemented`, `blocked`. `implemented`
means its specified checks passed; it does not mean owner acceptance of the task.

## Blockers and external evidence

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
- Full-page images are available through page:N; no stitching or missing-region inference.
- Full-document OCR, new detection families, semantic retrieval, automatic fallback
  and global optimization budgets are outside this plan.

## Resume note

- Visual evidence review: `review_pending`; both authorized steps implemented (2026-10-05), no owner acceptance.
- Inspected clean main at 90f2e6112d6cee921b4d11e1399a27bcfb1a7143; no Git mutations.
- Changed assets/crops/indexes/server/store.py; tests/test_assets.py, test_indexes.py, test_server.py; README/PLAN/HISTORY/TODO.
- Valid candidates/availability share geometry checks; prose flow, bounded grouping and source-page uncertainty retained.
- EXTRACTOR_VERSION 32 -> 34 rebuilds SQLite; existing PNG bounds metadata rejects incompatible crops.
- Step 1 focused unittest: assets 7 run/1 skip, crops 12 passed, server 25 passed; exact commands in HISTORY.
- Step 2 focused unittest: assets 12 run/1 skip, indexes 11 run/1 skip, server 26 passed, crops 12 passed.
- Final .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -q: 156 run, 151 passed, 5 corpus skips.
- Ruff, Basedpyright, Vulture, changed-file formatting and git diff --check passed; logs under tmp/visual-evidence-review/.
- Reviewed 17 source pages from six read-only PDFs; 74 figure entries, 55 usable regions; availability is not complete coverage.
- Remaining: missing vector/photo regions, incomplete labels/panels, inherited caption boundaries; explicit page:N requests required.
- Stop here for owner review; no live calls, dependency/consumer/review-run edits; Windows 3.14.3 tested, Python 3.12/Linux unverified.
