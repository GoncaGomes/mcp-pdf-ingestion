# MCP PDF ingestion task status

Updated: 2026-09-30. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- MCP-01: `done`, consistent with the existing owner-maintained task table.
- MCP-02: `done`.
- Assigned block: MCP-11B targeted review fixes (authorized 2026-09-30); no live requests.
- MCP-03, MCP-04 and MCP-05: `done`; implementation and batch validation complete.
- MCP-06 and MCP-07: `done`; implementation and batch validation complete.
- MCP-08A and MCP-08B: `done`; implementation and batch validation complete.
- MCP-09A and MCP-09B: `done`; implementation and batch validation complete.
- MCP-10 and MCP-11A: `done`; prior HISTORY/resume recorded no owner acceptance.
- MCP-11B: `done`; implementation checks passed, real execution/manual review pending.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
Only explicit owner acceptance permits `done`. The current targeted review block
runs focused crop/probe checks and all repository checks once at its final boundary.

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

- crops._region uses visible.contains(rect) before intersection; bounds/rotation/errors/cache validation retained.
- scripts/probe_mcp.py requires final text plus visual success; unavailable recovery remains fully recorded.
- Geometry instructions choose one figure/variant, explicitly request its source page if needed and finish with uncertainties.
- Probe default/help already 600; tests/README/PLAN now match; +60 MCP margin and eight-turn default retained.
- Focused: .venv/Scripts/python.exe -m unittest discover -s tests -p test_crops.py -q: 12 passed; same with test_probe_mcp.py: 21 passed.
- Final: .venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -q: 144 run, 139 passed, 5 corpus skips.
- .venv/Scripts/ruff.exe check ., basedpyright.exe, vulture.exe and git diff --check passed. Logs: tmp/mcp-11b-review-fixes-*.log.
- Windows checks passed; corpus needs REVIEWER_WORKSPACE; Linux/Python 3.12 unverified. CLI help/editable import/probe installation verified.
- README documents unused shared probe-runs/microstrip-review-fixes and review outputs; earlier evidence retained.
- Preserved unrelated .gitignore change; no dependency changes, live requests, consumer edits, Git mutations or owner acceptance.
- Next: owner reruns the documented 600-second commands and returns JSON/PNG evidence for review; no further block authorized.
