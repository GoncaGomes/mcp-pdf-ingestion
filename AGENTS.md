# Coding instructions

## Scope and authority

Work only in `mcp-pdf-ingestion`. You are the coding agent. The production
consumer is an external Architecture Agent using the OpenAI Agents SDK.
Do not edit `antenna-paper-extraction`, personal coding-agent configuration, or another
repository as part of these tasks.

Follow the owner's current instructions, then this file and the selected task in
`PLAN.md`. Code and tests describe implemented behavior; PLAN describes the target.
`TODO.md` tracks progress. `HISTORY.md` records observed changes and checks.
Inherited reviewer documents and any `docs/legacy/` files are historical context,
not active instructions. Report material conflicts rather than silently resolving
them. Do not change the agreed contract or acceptance criteria to make a task pass.

## Project context

These files must be sufficient to work without access to the planning chat or the
consumer repository. The project adapts an existing scientific-paper reviewer MCP
server into a PDF evidence service for antenna architecture extraction.

The target server serves one configured PDF and exposes six tools:
`get_paper_overview`, `read_pages`, `read_section`, `search_paper`, `list_assets`,
and `get_asset`. The external Architecture Agent decides which tools to call,
can revisit evidence, and writes the final architecture report. This repository
does not select the antenna, synthesize the report, or validate scientific claims.

Text access and asset retrieval are deterministic. An explicit question passed to
`get_asset` delegates inspection of that asset to a visual model. The visual helper
answers the local question with source references and limitations; the external
agent remains responsible for conclusions. PLAN defines the exact contract and
when each behavior becomes available. Do not assume the target already exists.

## Code map

Paths below describe the inspected starting layout under `src/reviewer_mcp/`.
Use them to locate the relevant implementation, then verify against current code.
Update this map when a task changes module responsibilities or package paths.

| Location | Responsibility / starting point |
| --- | --- |
| `server.py` | MCP tool registration, public signatures, result and error handling. |
| `papers.py` | Paper resolution and overview; inspect here for document binding changes. |
| `reading.py` | Page/section reads and continuation behavior. |
| `store.py` (`PaperStore`) | SQLite-backed document data, queries and persisted state; inspect alongside readers/search/assets. |
| `document.py`, `indexes.py` | PDF extraction and document indexing support. |
| `assets.py` | Asset catalog/retrieval and source metadata. |
| `crops.py` | PyMuPDF rendering of asset images. |
| `config.py`, `runner.py` | Settings and process startup. |
| Repository `tests/`, especially `tests/pdf_fixtures.py` | Existing unittest coverage and synthetic PDF fixtures. |
| Repository `pyproject.toml` | Dependencies, package metadata and executable entry point. |

The `reviewer_mcp` name is inherited and remains until MCP-10. Reviewer-only
features are legacy behavior, not requirements for the new service. Follow the
selected task before removing code; extraction may still depend on shared helpers.
The visual helper is introduced in MCP-09A; it is not part of this starting map.

## One task per thread

1. Read this file, then TODO's current status/resume note, then PLAN's shared
   contract and the selected task. Read only relevant HISTORY entries when a prior
   decision, failure or incomplete attempt affects that task. Do not load the full
   history or unrelated task/code sections by default.
2. Inspect `git status --short --branch`, relevant code/tests, and applicable local
   instructions. Preserve unrelated edits; do not reset or restore them.
3. Briefly state the behavior to change, affected files, and intended checks.
4. Implement the requested task and its tests. Authorization to implement that
   task includes routine decisions and its documentation updates; do not ask for
   permission after each edit.
5. Validate, inspect the diff, update the documents below, and stop for owner review.
   Do not start the next task automatically.

Use the selected PLAN task heading as the thread title. Each task is one intended
owner-made commit containing code, tests and documentation. Keep review corrections
within that task. If a new session is needed, resume the same task from TODO; do
not start another task or invent an extra commit boundary. After explicit owner
acceptance, update its status to `done` and the next-task pointer, then stop. The
owner handles the commit before assigning the next task.

The listed files are the expected scope. Explain a necessary supporting edit;
ask before a material expansion or architectural change. If blocked, record the
specific blocker and useful completed work. Do not repeatedly attempt the same
failing approach. A new session should resume from the recorded state.

## Git ownership

Never stage, commit, create/switch branches, pull, push, merge, rebase, tag, create
or modify pull requests, reset, restore, clean, or otherwise change Git/GitHub state.
Read-only inspection such as `git status`, `git diff`, `git log`, and `git show` is
allowed. Leave local file edits for the owner. Do not install Git hooks.

## Implementation rules

- Use Python 3.12-compatible code, existing FastMCP/MCP, PyMuPDF, and SQLite.
  Keep the existing unittest style. Add the OpenAI client only for MCP-09A.
- Before MCP-10, source code remains under `src/reviewer_mcp`. Do not combine a
  package rename with functional changes.
- Prefer small functions, explicit arguments and ordinary dictionaries/typed
  boundaries. Reuse existing helpers. Do not build a generic pipeline, plugin
  framework, universal response schema, or speculative adapters.
- Use `pathlib`, context managers, parameterized SQL, stable ordering and explicit
  errors. Keep stdout exclusively for MCP transport; diagnostics go to stderr.
- Default operations are deterministic. Only an explicit visual question invokes
  a model. Model calls are sequential, without automatic retries, fallback models,
  tools or recursive delegation inside the visual helper.
- A missing match is not missing scientific evidence. Never infer materials,
  geometry, values or design selection in Python. Preserve source references,
  extraction limitations, partial results and explicit failures.
- Do not tune extraction heuristics without a reproducible fixture. Preserve
  attribution, existing useful extraction tests, and the current cache fingerprint
  mechanism. Add no new hashing/integrity subsystem.
- Use English for code and documentation. Explain the handoff in European Portuguese.
- Do not read/print credentials, add secrets to logs, or contact institutional
  endpoints unless the owner has authorized that specific probe. Normal tests use
  temporary directories, synthetic PDFs and fake model clients.

## Environment and checks

Use the repository's existing virtual environment, not system-wide packages.
`python` below means that environment's interpreter. If setup is needed, use
`python -m pip install -e ".[dev]"` inside it. Do not upgrade unrelated dependencies.
If pip is unavailable in an existing uv environment, use `uv pip install` targeting
that interpreter rather than creating another environment. Do not migrate tooling.

Run the selected task's focused tests first, for example:

```bash
python -m unittest discover -s tests -p "test_reading.py" -v
```

Before handing off a code task, run the existing repository checks once:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
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

- TODO: mark the selected task `in_progress`, then `review_pending` or `blocked`.
  Only owner acceptance changes it to `done`. Record a short next action.
- HISTORY: keep a change record, not a duplicate project overview or code map.
  Append one concise dated entry with task ID, behavior changed, checks
  actually run and their outcomes, skips, and limitations. No invented commits,
  benchmarks, approvals or endpoint results. Amend an in-progress entry rather than
  adding a transcript of every edit.
- PLAN: update only a necessary implementation note or an owner-approved decision;
  keep task IDs and the agreed acceptance criteria stable.
- README: update usage/configuration when the selected task changes them. Distinguish
  available behavior from later tasks. Update this file when MCP-10 changes paths.

The handoff states what changed, why, files affected, validation results, remaining
limitations and the task status. End with the suggested commit message from PLAN,
clearly labelled as a suggestion for the owner. Do not execute it. Leave a
reviewable working-tree diff and stop.
