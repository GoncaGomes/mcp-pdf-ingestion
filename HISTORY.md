# MCP PDF ingestion history

This file records this repository's adaptation, checks and observed limitations.
It is not the task specification; use `PLAN.md` and `TODO.md` for planned work.

## 2026-09-24 - Planning baseline

**Inspected source:**
`https://github.com/GoncaGomes/mcp-pdf-ingestion/tree/14390e0a0b863d8b1c02bb51e85f0537b556a130`.

The repository derives from Mário Antunes's `reviewer-mcp`; its project metadata
identifies Gonçalo Gomes and credits the original work. Preserve that attribution.

At inspection, the package was still `reviewer_mcp`, with 11 tools, deterministic
PyMuPDF extraction, SQLite indexes, page/section/search readers and asset crops.
Review-specific behavior remained: venue/form dependencies, inferred manuscript
filtering, persistent consumption state and asset/image quotas. Visual question
answering was not implemented.

The inherited PLAN, TODO and HISTORY described an academic-review workflow and
external personal workspaces. Their historical runs and performance claims are
not validation of this PDF ingestion adaptation. Original versions remain
recoverable at the inspected Git revision. These replacement documents do not
claim that a local archive directory has been created.

**Planning decisions supplied by the owner and planning chat:**

- Keep six tools: overview, pages, sections, search, asset listing and retrieval.
- Bind one PDF per local server process; preserve all-page access and repeatability.
- Remove reviewer quotas and policy. Retain pagination and technical timeouts.
- Add explicit visual questions to `get_asset`, with one auxiliary model call per
  request and inspectable source/response diagnostics.
- The external Architecture Agent uses the OpenAI Agents SDK and controls its own
  evidence acquisition. The coding agent writes code only in this MCP repository.
- Use small assigned tasks, no commits or other Git mutations, and owner review
  between tasks. Documentation preparation is not a coding-agent implementation task.

**Inspection findings to address:** page continuation loses the original range;
section paragraphs may be truncated; asset IDs are only unique within a segment;
rendering does not implement the image cache promised by the inherited PLAN;
multipage assets currently render only their first-page crop.

**Verification performed:** read-only repository/document/code inspection and
confirmation of the baseline revision. No local test suite, remote probe, model
benchmark or consumer integration was executed for this planning handoff.

**Outcome:** PLAN, TODO and AGENTS prepared for owner installation/review.
All implementation tasks remain pending. No repository code, Git state or external
consumer files were changed by this document preparation.

## 2026-09-24 - Thread and commit planning

The owner requested explicit thread/commit boundaries. PLAN now maps each of the
14 implementation tasks to a separate thread and suggested owner-made commit.
AGENTS and TODO describe review, acceptance and continuation. Commit suggestions
do not authorize the coding agent to stage, commit or change Git state.

Validation: checked task order, one commit suggestion per task, and consistency of
the documentation workflow. No code tests or probes were run for this edit. All
implementation tasks remain pending; no implementation commits are claimed.

## 2026-09-24 - MCP-01 - Expose six neutral PDF tools

Status: complete

Changed: `server.py` now registers exactly six tools (`get_paper_overview`,
`read_pages`, `read_section`, `search_paper`, `list_assets`, `get_asset`) and all
reviewer policy was removed from the tool instructions; the five reviewer tools
(`set_manuscript_pages`, `get_author_responses`, `get_review_guideline`,
`submit_report`, `update_report_field`) are no longer exposed.
`papers.overview()` returns a whole-PDF outline with section IDs, whole-PDF asset
counts, optional title and no-text-layer warnings; venue resolution, reviewer
notes, the responses key and the notes budget were removed from `papers.py`.
`config.py` lost the reviewer path constants. Deleted the reviewer-only modules
`forms.py`, `profile.py`, `reports.py`, `responses.py`, `validator.py`, `venues.py`
and their dedicated tests after confirming no remaining imports.
`tests/test_server.py` rewritten for the six-tool contract; `tests/test_fixtures.py`
adapted from profile/venues to `PaperStore` queries; `README.md` updated to describe
the six tools and the intermediate state. Review correction (same day): the
intermediate annotations of the three stateful tools were corrected —
`get_paper_overview` is now `readOnlyHint: False, destructiveHint: True,
idempotentHint: True` (it resets the consumption ledger), `read_pages` is
`readOnlyHint: False, destructiveHint: False, idempotentHint: False` (repeated
requests consume additional pages), and `get_asset` is `readOnlyHint: False,
destructiveHint: False, idempotentHint: False` (it updates the consumption and
image counters); no tool behavior, signatures, quotas or reset logic changed. The
contract test now asserts the exact hint triples for all six tools;
`read_section`, `search_paper` and `list_assets` keep their read-only annotations.
New regression test `TestBareWorkspace.test_overview_without_legacy_reviewer_files`
proves `get_paper_overview` works in an isolated workspace containing only the
synthetic PDF under `papers/` (no `forms/`, `base_review.md` or reviewer notes) and
verifies the page count and the outline. Retained per PLAN as intermediate state:
readers default to the detected manuscript part, and the consumed-page, asset and
image budgets (with their overview resets) remain.

Validation: focused runs `python -m unittest discover -s tests -p "test_server.py"`
(11 ok, including the new bare-workspace regression test) and `-p "test_fixtures.py"`
(6 ok); full suite 52 tests: 46 ok, 1 failure
(pre-existing on this Windows machine: chmod 0o700 not enforced,
`test_store_location_permissions_and_cache`), 5 skips (corpus/real-PDF tests without
`REVIEWER_WORKSPACE`). `ruff check .` clean (the baseline E501 in `server.py` no
longer applies after the rewrite). `basedpyright`: 0 errors, 0 warnings, 0 notes.
`vulture`: clean. `git diff --check`: no whitespace errors. The pre-implementation
baseline was 93 tests with 1 failure, 5 flaky Windows temp-lock errors and 8 skips;
no new failures were introduced.

Limitations: readers still default to the detected manuscript part and budgets
still apply until later tasks; the one configured PDF per server, full-PDF read
defaults and visual questions arrive in later tasks (MCP-02 onward).

Next: owner review and acceptance of the working-tree diff.

## 2026-09-25 - Execution blocks and context guidance

Inspected branch head: `371317499d1df0e57757697a46700ecb471c8216`.
MCP-01 implementation and review corrections are already committed (`a756b7c`,
`3713174`). Earlier working-tree handoff descriptions record their state at the
original handoff; they no longer describe the remote branch. Owner acceptance
remains `review_pending` in the inspected TODO.

PLAN now distinguishes deliverables, implementation blocks and threads. MCP-02
has three specified blocks: configuration; startup/store/tool binding; isolation
checks and closure. The remaining task scopes and commit suggestions are retained
for later refinement against current code. AGENTS uses focused checks per block,
final checks per task, selective reads and short resumable checkpoints. TODO
tracks block progress and preserves reported MCP-01 results without rerunning them.

Validation: checked document consistency, block order, parent-task statuses and
preservation of the six-tool contract and Git restrictions. No implementation,
code tests, endpoint probes, Git mutations or personal configuration edits were
performed for this documentation update.

## 2026-09-25 - MCP-02.1 - Document configuration loader

Status: block MCP-02.1 implemented; parent MCP-02 `in_progress`

Changed: `config.py` gained a frozen `DocumentConfig` dataclass (`pdf_path`,
`run_dir` as `Path`) and `load_document_config()`, which reads
`PDF_INGESTION_PDF` and `PDF_INGESTION_RUN_DIR` (both required), resolves
relative paths against the working directory (spaces preserved), and rejects a
missing or non-file PDF, an unusable PDF (checked with a PyMuPDF context
manager, page count only, no content extraction) and a run-directory path that
is an existing file. A missing run directory is allowed; nothing is created
and no model settings are read. New `tests/test_config.py` covers missing
settings, missing PDF, directory-as-PDF, garbage and empty PDF bytes, run path
pointing to a file, a valid config with spaces and a not-yet-existing run
directory, an existing run directory, and relative paths resolved against a
patched cwd. Existing configuration consumers (`workspace`, `scratch_base`,
`load_section`) and server startup are unchanged; the helper is not advertised
as a server feature yet (bound in block MCP-02.2).

Validation: `python -m unittest discover -s tests -p "test_config.py" -q` → 10
tests, all OK (repository venv). `ruff check` on the two changed files: clean.
`basedpyright` on the two changed files: 0 errors, 0 warnings, 0 notes.
`vulture` on `src/reviewer_mcp`: clean. Task-wide checks (full suite,
`git diff --check`) are deferred to block MCP-02.3 per the assigned scope.

Limitations: none observed within the block; remaining MCP-02 blocks pending.

Next: owner review of the diff; assign block MCP-02.2 (startup/store binding
and the six tool signatures).

## 2026-09-25 - MCP-02.2 - Bind startup, store and six tool signatures

Status: block MCP-02.2 implemented; parent MCP-02 `in_progress`

Changed: `server.py` gained `bind_document()`, which loads and validates the
`DocumentConfig` from the environment once and retains it for the process
lifetime; `main()` calls it before `run_server(mcp)`, and in-process tests use
the same path after patching the environment. `_open()` takes no paper
argument and always opens the bound PDF with the bound run directory; `paper`
was removed from all six tool signatures and from the INSTRUCTIONS/module
docstrings, and the `Paper` alias was dropped. `store.py`: `PaperStore.open`
gained a keyword-only `run_dir` parameter; the database still lives at
`<base>/store/<sha256[:16]>/paper.sqlite` under the given run directory, or
under the legacy scratch base when omitted (internal extractor tests keep
working); cache keys and rebuild logic are unchanged. `papers.py`:
`resolve_paper` removed and the overview now adds `document_id` from the
existing store fingerprint (no new hashing). `config.py`: legacy `workspace`
and `DEFAULT_PAPERS_DIR` dropped (no retained callers). `tests/test_server.py`
binds a fixture per test (`bind_paper`), patches the two settings per test,
closes stores before temporary cleanup, passes the new settings to the stdio
launch, asserts that no tool schema exposes `paper`, and adds
`test_document_binding_survives_environment_changes` (environment re-pointed
after initialization does not change the instance's document or run
directory). `tests/test_store.py` adds
`test_explicit_run_dir_places_the_store_inside_it`. README now documents
`PDF_INGESTION_PDF`/`PDF_INGESTION_RUN_DIR` as the launch settings; readers
still default to the manuscript part and budgets still apply.

Validation: `python -m unittest discover -s tests -p "test_server.py" -q` 12
tests OK; `-p "test_store.py" -q` 11 run: 10 OK, 1 failure pre-existing on
this Windows machine (chmod 0o700 not enforced,
`test_store_location_permissions_and_cache`), 1 skip (corpus, no
`REVIEWER_WORKSPACE`); the new placement test passes. `-p "test_config.py" -q`
10 tests OK. `ruff check .` clean; `basedpyright` 0 errors, 0 warnings, 0
notes; `vulture` clean. Task-wide checks (full suite, `git diff --check`) and
two-process isolation tests are deferred to block MCP-02.3.

Limitations: two-process isolation and startup rejection of invalid
configuration are not yet tested end-to-end (block MCP-02.3); the pre-existing
Windows chmod failure and corpus skips remain unchanged.

Next: owner review of the diff; assign block MCP-02.3 (process isolation
checks and task closure).

## 2026-09-25 - MCP-02.3 - Verify process isolation and close MCP-02

Status: block MCP-02.3 implemented; parent MCP-02 `review_pending` (owner
acceptance pending)

Changed: new `tests/test_document_binding.py` (no source changes). It launches
two real stdio server processes (existing `StdioTransport` pattern, bounded
`asyncio.wait_for` timeouts) bound to two synthetic PyMuPDF-built PDFs that
share the filename `same_name.pdf` in separate folders, with distinct run
directories and distinguishable text, and no model settings: each
`get_paper_overview` `document_id` equals the SHA-256 of its own PDF bytes and
each `read_pages(first_page=1, last_page=2, part='all')` returns only its own
marker text; each store exists only under its own run directory at
`<run_dir>/store/<sha256[:16]>/paper.sqlite`. Startup rejection runs the real
entry point via `subprocess.run` (bounded timeout): missing
`PDF_INGESTION_PDF`/`PDF_INGESTION_RUN_DIR` and an invalid (text-file) PDF both
exit non-zero with the diagnostic on stderr, no stdio protocol output and no
store created. A successful stdio launch with spaces in the PDF path
(`papers with spaces/proof hi res.pdf`) serves the overview.

Validation (repository venv, newly executed): focused
`python -m unittest discover -s tests -p "test_document_binding.py" -q` — 4
tests, all OK. Task-wide checks once: full suite
`python -m unittest discover -s tests -p "test_*.py" -q` — **68 run, 1 failure,
0 errors, 5 skipped** (actual output; replaces the earlier inconsistent
test_store summary). The single failure is the pre-existing Windows issue
`test_store.TestPaperStore.test_store_location_permissions_and_cache`
(0o700 not enforced, `511 != 448`), unchanged by this task; the 5 skips are the
corpus/real-PDF tests that require `REVIEWER_WORKSPACE` with the real PDFs
(absent on this machine). `ruff check .` clean; `basedpyright` 0 errors, 0
warnings, 0 notes; `vulture` clean; `git diff --check` no whitespace errors
(only pre-existing LF/CRLF line-ending warnings).

Limitations: the Windows chmod failure and corpus skips are baseline and
reported separately per the block scope; not fixed here. No consumer-repository
edits, no reader/quota/vision changes.

Next: owner review and acceptance of the MCP-02 diff; suggested owner commit
after acceptance: `feat(mcp): bind each server to one PDF and run directory`.

## 2026-09-25 - MCP-02 - Review fix: reject non-PDF and password-protected PDFs

Status: review fix implemented; parent MCP-02 stays `review_pending` (owner
acceptance pending)

Changed: `src/reviewer_mcp/config.py` (`load_document_config`): inside the
existing PyMuPDF context manager and before the page-count check, documents
with `doc.is_pdf` false are rejected with "not a PDF document (file is not in
PDF format)" and documents with `doc.needs_pass` with "PDF is
password-protected"; both raise ValueError identifying the reason and the
path. The page-count check and the "not a usable PDF" wrapper for open
failures are unchanged. `tests/test_config.py`: two new loader cases — PNG
bytes rendered with a PyMuPDF pixmap and saved under a `.pdf` name, and a
one-page AES-128 PDF saved with a non-empty user password — both rejected
with the expected reason. `tests/test_document_binding.py`: two new
`StartupRejectionTestCase` cases with module-level generators for the same
two file kinds, each verifying a non-zero exit, the reason on stderr, empty
stdout (no protocol output) and no run directory created; the existing
bounded `subprocess.run` timeout and env helpers are reused. No password
support, no new dependencies, and no changes to startup, store/cache behavior
or tool signatures.

Validation (repository venv, newly executed): focused
`python -m unittest discover -s tests -p "test_config.py" -q` — 12 tests, all
OK. Focused `python -m unittest discover -s tests -p "test_document_binding.py"
-q` — 6 tests, all OK. Task-wide checks once: full suite
`python -m unittest discover -s tests -p "test_*.py" -q` — **72 run, 1 failure,
0 errors, 5 skipped** (suite was 68 before this fix). The single failure is
the pre-existing Windows issue `test_store.TestPaperStore.test_store_location_permissions_and_cache`
(0o700 not enforced, `511 != 448`), unchanged by this fix; the 5 skips are the
corpus/real-PDF tests requiring `REVIEWER_WORKSPACE` with real PDFs (absent on
this machine). `ruff check .` clean; `basedpyright` 0 errors, 0 warnings, 0
notes; `vulture` clean; `git diff --check` no whitespace errors (only
pre-existing LF/CRLF line-ending warnings).

Limitations: password-protected PDFs are rejected, not opened (no password
support added); the Windows chmod failure and corpus skips are baseline and
reported separately, not fixed here.

Next: owner review and acceptance of the MCP-02 diff; suggested owner commit
after acceptance: `feat(mcp): bind each server to one PDF and run directory`.

## Entry format for future work

Append one short entry per task attempt, using the actual date:

```text
YYYY-MM-DD - MCP-XX - Short outcome
Status: review_pending | blocked | done (owner accepted)
Changed: observable behavior and key files.
Validation: exact commands and actual outcomes; skipped/unavailable checks.
Limitations: remaining issue or explicit none observed within the task scope.
Next: owner review or concrete blocked step.
```

Do not invent commit IDs, approval, test counts or scientific conclusions. Mark
external results as owner-reported when they were not directly observed. Keep
credentials, raw model payloads and lengthy logs out of this document.
