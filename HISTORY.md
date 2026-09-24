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
