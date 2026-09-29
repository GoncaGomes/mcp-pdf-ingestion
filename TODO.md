# MCP PDF ingestion task status

Updated: 2026-09-29. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- Assigned batch: review fixes -> MCP-10 -> MCP-11A (authorized 2026-09-29); stop before MCP-11B.
- MCP-03, MCP-04 and MCP-05: `review_pending`; implementation and batch validation complete.
- MCP-06 and MCP-07: `review_pending`; implementation and batch validation complete.
- MCP-08A and MCP-08B: `review_pending`; implementation and batch validation complete.
- MCP-09A and MCP-09B: `review_pending`; implementation and batch validation complete.
- MCP-10 and MCP-11A: `review_pending`; review fixes and local batch validation complete.
- Stopped before MCP-11B; next step is owner review/acceptance.
- MCP-01: `done`, consistent with the existing owner-maintained task table.
- MCP-02: `review_pending`; no new owner acceptance recorded.
- MCP-00 is planning, not an implementation task.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
Only explicit owner acceptance permits `done`. This assigned batch may continue
sequentially after focused checks; full checks run once after MCP-11A.

## Thread and commit tracking

One task row is a deliverable, usually one owner-made commit. A task can span
several assigned blocks/threads. Intermediate blocks leave the parent `in_progress`;
only the final block can mark it `review_pending`. Owner acceptance permits `done`.
Do not automatically start an unassigned block; the review fixes -> MCP-10 -> MCP-11A batch is authorized.
Use PLAN for scope and commit messages.

Observed 2026-09-29 (read-only Git inspection): branch `feat/pdf-evidence-tool`,
HEAD `9862ae8` (`fix: documentation and visual inspection prompt`). The initial
working-tree diff contained only four README separator fixes, preserved by this batch.
No Git state was mutated. Commit presence does not imply owner acceptance;
earlier task statuses are unchanged.

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
| MCP-09A | One-call visual helper and diagnostics | review_pending |
| MCP-09B | Visual questions through get_asset | review_pending |
| MCP-10 | Package identity and setup alignment | review_pending |
| MCP-11A | Complete local stdio contract verification | review_pending |
| MCP-11B | Authorized probes and consumer handoff evidence | pending |

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

- Batch complete at MCP-11A: MCP-10/MCP-11A review_pending; MCP-11B pending; earlier acceptance unchanged.
- Review fixes: byte-identical prompt reflow, preserved README separators, diagnostic error_type/nullable http_status; public results unchanged.
- Package/command mcp-pdf-ingestion; imports src/mcp_pdf_ingestion; CI/hooks/resources/docs aligned; active legacy env names retained.
- Extraction/store/fingerprints/assets/cursors/cache/config verified unchanged beyond imports; uv lock dependency records identical to HEAD.
- `uv lock --offline`, isolated editable install, `uv build --wheel`, isolated wheel install: passed; final wheel rebuilt/rechecked after diagnostic edit.
- Both installs passed resource/import/entry-point/six-tool stdio smoke checks outside checkout without PYTHONPATH; logs tmp/mcp-10-*.log.
- Focused unittest: visual 10, init 2, crops 11, server 24 passed; focused Ruff passed; fixture/import setup corrections resolved.
- Final `.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -q`: 122 run, 116 passed, 1 known Windows chmod failure (511 != 448), 5 corpus skips; tmp/mcp-10-11a-unittest.log.
- Final `.venv/Scripts/ruff.exe check .`, `.venv/Scripts/basedpyright.exe`, `.venv/Scripts/vulture.exe`, `git diff --check`: passed; tmp/mcp-10-11a-*.log.
- StdIO: real renamed command, native auto/legacy negotiation, six schemas/annotations, actual pagination, repeated IDs/reads, no forms/corpus/visual env, clean protocol and exited processes.
- Windows CPython 3.14.3 verified; Python 3.12/POSIX/live endpoints/consumer not tested. No Git mutations, hooks, new dependencies or real model calls.
- Next: owner review/acceptance and optional commits per PLAN; do not start MCP-11B without its separate authorization/configuration/input.
