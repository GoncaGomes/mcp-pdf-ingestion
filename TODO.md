# MCP PDF ingestion task status

Updated: 2026-09-25. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- Active task: **MCP-02** — `review_pending` (all blocks implemented, owner
  acceptance pending) since 2026-09-25.
- Prior task: **MCP-01** — implemented 2026-09-24, `review_pending`.
- Last implementation block: **MCP-02.3** — implemented 2026-09-25, task-wide
  checks passed (see checkpoint below).
- Implementation started under this plan: yes (MCP-01, MCP-02).
- The owner and planning chat prepared the documents; MCP-00 is not an implementation task.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
The coding agent may set `review_pending` after implementation and checks. Only explicit owner
acceptance permits `done`. Complete one assigned task, update this file/HISTORY,
and stop. Owner acceptance does not authorize Git operations.

## Thread and commit tracking

One task row is a deliverable, usually one owner-made commit. A task can span
several assigned blocks/threads. Intermediate blocks leave the parent `in_progress`;
only the final block can mark it `review_pending`. Owner acceptance permits `done`.
Do not automatically start the next block. Use PLAN for scope and commit messages.

Observed branch: `feat/pdf-evidence-tool`, head
`371317499d1df0e57757697a46700ecb471c8216`. MCP-01 implementation is committed as
`a756b7c`; review fixes are committed as `3713174`. Acceptance remains separate.

## Tasks

| ID | Deliverable | Status |
| --- | --- | --- |
| MCP-01 | Six neutral tools, no reviewer policy | done |
| MCP-02 | One configured PDF and isolated run directory | review_pending |
| MCP-03 | Repeatable, complete page reads | pending |
| MCP-04 | Complete section reads by ID | pending |
| MCP-05 | Paginated textual search | pending |
| MCP-06 | Unambiguous assets without consumption quotas | pending |
| MCP-07 | Paginated, filtered asset catalog | pending |
| MCP-08A | Exact crops and full-page images | pending |
| MCP-08B | Reuse of materialized images | pending |
| MCP-09A | One-call visual helper and diagnostics | pending |
| MCP-09B | Visual questions through get_asset | pending |
| MCP-10 | Package identity and setup alignment | pending |
| MCP-11A | Complete local stdio contract verification | pending |
| MCP-11B | Authorized probes and consumer handoff evidence | pending |

Dependencies follow table order. The owner may perform the external SDK checkpoint
after MCP-03; the coding agent does not modify that consumer repository.

## MCP-02 implementation blocks

| Block | Deliverable | Progress |
| --- | --- | --- |
| MCP-02.1 | Configuration loader and focused tests | implemented |
| MCP-02.2 | Startup/store binding and six tool signatures | implemented |
| MCP-02.3 | Process isolation checks and task closure | implemented |

Block progress: `pending`, `in_progress`, `implemented`, `blocked`. `implemented`
means its specified checks passed; it does not mean owner acceptance of the task.

## Blockers and external evidence

- MCP-01 is implemented and awaiting owner review; no blocker.
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

- Task: MCP-02 (`review_pending`); final block MCP-02.3 implemented 2026-09-25.
- New `tests/test_document_binding.py` (no source changes): two real stdio
  processes serve two same-named synthetic PDFs from separate folders with
  distinct run dirs — each `document_id` matches its own PDF's SHA-256, each
  `read_pages(1..2, part='all')` returns only its own markers, each store
  exists only under its own run dir. Startup rejection (missing settings,
  invalid PDF) exits non-zero with a stderr diagnostic before serving; a
  launch with spaces in the PDF path serves normally. Bounded timeouts, no
  new process infrastructure.
- Checks (repo venv, newly run): focused test_document_binding 4/4 OK; full
  suite 68 run, 1 failure, 0 errors, 5 skipped — failure is the pre-existing
  Windows chmod issue (`test_store_location_permissions_and_cache`, 511 != 448);
  skips are corpus tests without `REVIEWER_WORKSPACE`. `ruff check .` clean,
  `basedpyright` 0/0/0, `vulture` clean, `git diff --check` no whitespace
  errors. README unchanged (binding already documented in MCP-02.2).
- Next: owner review/acceptance of the MCP-02 diff; suggested commit after
  acceptance: `feat(mcp): bind each server to one PDF and run directory`.
