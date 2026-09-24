# MCP PDF ingestion task status

Updated: 2026-09-24. Scope: this repository only.
Read `AGENTS.md` and the selected task in `PLAN.md` before editing.

## Current work

- Active task: **MCP-01** — implemented 2026-09-24, `review_pending`.
- Next task after acceptance: **MCP-02**.
- Implementation started under this plan: yes (MCP-01).
- The owner and planning chat prepared the documents; MCP-00 is not an implementation task.

Statuses: `pending`, `in_progress`, `review_pending`, `done`, `blocked`.
The coding agent may set `review_pending` after implementation and checks. Only explicit owner
acceptance permits `done`. Complete one assigned task, update this file/HISTORY,
and stop. Owner acceptance does not authorize Git operations.

## Thread and commit tracking

One task row = one fresh implementation thread = one intended owner-made commit.
Use the corresponding PLAN heading as the thread title; the suggested commit
message appears at the end of that task. Keep corrections with the same task.
After explicit owner acceptance, record `done` and the next pending task, then
stop. The owner commits before assigning the next thread. Do not infer acceptance
from tests passing or from the presence of a commit. No implementation commits have
been recorded under this plan.

## Tasks

| ID | Deliverable | Status |
| --- | --- | --- |
| MCP-01 | Six neutral tools, no reviewer policy | review_pending |
| MCP-02 | One configured PDF and isolated run directory | pending |
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

MCP-01 is implemented and `review_pending` (2026-09-24). Files:
`src/reviewer_mcp/server.py`, `papers.py`, `config.py`; deleted reviewer-only
`forms.py`, `profile.py`, `reports.py`, `responses.py`, `validator.py`, `venues.py`;
rewrote `tests/test_server.py`, adapted `tests/test_fixtures.py`; deleted
`tests/test_venues.py` and `tests/test_guidelines_validator.py`; updated
`README.md`. Checks: full suite 51 tests (45 ok, 1 pre-existing Windows chmod
failure, 5 corpus skips), ruff clean, basedpyright 0, vulture clean,
`git diff --check` clean. Next: owner review of the working-tree diff and
acceptance; the coding agent performs no Git operations.
