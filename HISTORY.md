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

Status: review_pending

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
