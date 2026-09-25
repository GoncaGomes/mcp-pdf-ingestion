# Coding instructions

## Scope and authority

Work only in `mcp-pdf-ingestion`. Follow owner instructions, this file and the
assigned PLAN block. Do not edit the consumer repository or personal agent setup.
Code describes implementation; PLAN describes targets; TODO tracks progress;
HISTORY records results. Legacy reviewer instructions are not active requirements.
Report material conflicts and preserve the agreed acceptance criteria.

## Project context

This repository adapts a scientific-paper reviewer server into a PDF evidence
service for antenna architecture extraction. The target tools are
`get_paper_overview`, `read_pages`, `read_section`, `search_paper`, `list_assets`
and `get_asset`. The external Architecture Agent chooses calls and writes the
report; this repository does not select an antenna or validate scientific claims.
Text access is deterministic. Only an explicit asset question invokes the visual
helper introduced in MCP-09A/B. PLAN distinguishes targets from available behavior.

## Code map

Source paths are under `src/reviewer_mcp/` until MCP-10. Verify current code and
update this map when responsibilities change. Keep shared extraction helpers when
removing reviewer-only features.

| File | Responsibility |
| --- | --- |
| `server.py` | Tool registration, signatures, errors, document binding and entry point. |
| `papers.py` | Overview, title and part helpers for the bound document. |
| `reading.py` | Page/section reads and search responses. |
| `store.py` (`PaperStore`) | SQLite queries, cache and persisted state. |
| `document.py`, `indexes.py`, `structure.py` | Extraction, indexes and document segments. |
| `assets.py`, `crops.py` | Asset detection/metadata and image rendering. |
| `config.py`, `runner.py` | Settings (document configuration, section values) and process execution. |
| `tests/pdf_fixtures.py`, `tests/` | Synthetic PDFs and unittest coverage. |
| Root `pyproject.toml` | Dependencies, package settings and entry point. |

## One assigned block per session

1. Read this file, TODO's active block/resume note, and only the PLAN contract
   sections named by the assigned block. Consult HISTORY only for relevant prior
   decisions or failures. The repository documents must suffice without the chat.
2. Inspect `git status --short --branch` and the relevant diff. Preserve unrelated
   work. Locate named symbols with `rg` before reading their implementation.
3. Briefly state the change and checks, then implement the assigned block. Routine
   implementation and documentation updates are authorized; no approval per edit.
4. Run the block's focused checks and update TODO's checkpoint. Stop at the block
   boundary; do not automatically start another block or task.

A task is a deliverable; a block is an implementation step that can use its own
thread. Intermediate blocks keep the parent `in_progress`. Only the final block
runs the task-wide checks and changes it to `review_pending`. Owner acceptance
permits `done`. Commits belong to the owner, usually one per complete task; review
fixes can be separate commits. Never rewrite history to enforce that convention.

Explain necessary supporting edits. Ask before a material scope expansion or
architecture change. Do not weaken acceptance criteria to obtain passing tests.

## Context and recovery

- Read named functions/callers/tests first; expand for a concrete dependency or
  failure. Avoid repeated whole-file reads, full planning documents, lockfiles,
  generated data and whole-repository diffs.
- Show test summaries and actionable failures. Keep long logs locally, read relevant
  excerpts and preserve exit codes. Never hide failures by truncating output.
- Reuse recorded baseline results unless code, environment or failure symptoms give
  a reason to recheck. Do not repeatedly investigate unchanged Windows/corpus issues.
- After two failed attempts at one problem, record observations, attempted fixes,
  remaining hypothesis and the next discriminating check. Continue with new evidence;
  otherwise report the blocker. Do not expand scope to escape the problem.
- Checkpoint after meaningful progress and before handoff or reported context
  pressure. Do not invent token counts. Resume from TODO and the actual diff;
  compaction summaries do not replace repository state or owner acceptance.

## Git ownership

Never stage, commit, create/switch branches, pull, push, merge, rebase, tag, create
or modify pull requests, reset, restore, clean, or otherwise change Git/GitHub state.
Read-only inspection such as `git status`, `git diff`, `git log`, and `git show` is
allowed. Leave local file edits for the owner. Do not install Git hooks.

## Implementation rules

- Python 3.12, existing FastMCP/MCP, PyMuPDF, SQLite and unittest. Add the
  OpenAI client only in MCP-09A; rename the package only in MCP-10.
- Reuse helpers and ordinary dictionaries/typed boundaries. No generic pipeline,
  plugin framework, universal response schema or speculative adapters.
- Use context managers, parameterized SQL, stable ordering and explicit errors.
  Reserve stdout for MCP transport; send diagnostics to stderr.
- Only an explicit visual question invokes a model. Sequential calls, no automatic
  retries, fallback models, tools or recursive delegation inside the visual helper.
- Preserve evidence, provenance, partial coverage and failures. Never infer antenna
  materials, geometry or scientific absence from a missing extraction/search match.
- Preserve attribution, useful tests and existing fingerprint logic. No new hashing
  subsystem; no heuristic changes without a reproducible fixture.
- English code/docs; European Portuguese handoffs. Never expose credentials. Real
  endpoint probes require specific owner authorization; normal tests use synthetic
  PDFs, temporary directories and fake clients.

## Environment and checks

Use the repository's existing virtual environment, not system-wide packages.
`python` below means that environment's interpreter. If setup is needed, use
`python -m pip install -e ".[dev]"` inside it. Do not upgrade unrelated dependencies.
If pip is unavailable in an existing uv environment, use `uv pip install` targeting
that interpreter rather than creating another environment. Do not migrate tooling.

During a block, run focused tests, for example:

```bash
python -m unittest discover -s tests -p "test_reading.py" -q
```

At the final block of a task, run the existing repository checks once:

```bash
python -m unittest discover -s tests -p "test_*.py" -q
ruff check .
basedpyright
vulture
git diff --check
```

Use environment-local executables and quote paths as required by the actual shell.
Editable installation supplies the source package; do not assume Bash or Unix-only
venv paths on Windows. Record skipped corpus tests, unavailable commands and
pre-existing failures separately. Do not disable checks to claim success. Broaden
testing only for a concrete remaining risk; do not run remote checks implicitly.

## Documentation and handoff

- TODO: track parent status and block progress. Keep one checkpoint of roughly
  8-12 lines: task/block, completed work, changed functions/files, exact checks and
  outcomes, remaining issue, next step. Replace stale resume text; do not append
  a transcript. Only owner acceptance permits the parent task to become `done`.
- HISTORY: append one concise factual entry per task, with block-labelled checks
  when necessary. Update its active entry; retain prior results and distinguish
  newly run checks. Do not invent commits, benchmarks, approvals or endpoint results.
- PLAN: preserve the contract and task IDs. Update only necessary implementation
  notes or owner-approved decisions. Block scope belongs here, not only in prompts.
- README: document behavior/configuration when it becomes available. Keep future
  features distinct. Maintain this file's code map when modules or paths change.

A handoff states observable changes, checks/results, limitations and next step.
Keep it short (normally under 200 words, longer only for an actionable failure).
An intermediate block reports a checkpoint, not a completed task. A final task
handoff includes PLAN's suggested owner commit message. Never execute it.
