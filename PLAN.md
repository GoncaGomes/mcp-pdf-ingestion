# MCP PDF ingestion implementation plan

Prepared: 2026-09-24. Repository: `GoncaGomes/mcp-pdf-ingestion`.
Inspected baseline: `14390e0a0b863d8b1c02bb51e85f0537b556a130`.

## 1. Purpose and boundaries

Adapt the inherited reviewer server into a six-tool PDF evidence service. An
external agent chooses its own sequence of calls and writes the architecture
report. This repository provides document access and explicit visual question
answering; it does not implement the Architecture Agent or its report validator.

The owner and planning chat prepared these documents. There is no MCP-00 coding
task. The coding agent implements one task below at a time and updates documentation under
`AGENTS.md`. The coding agent must not mutate Git state or create commits; the owner handles Git.

Keep the PyMuPDF extractor, SQLite indexes and useful fixtures. Do not rebuild the
parser, add RAG, impose global query/image quotas, or add full-document OCR.
Per-response pagination and image sizing remain necessary. No performance targets
from reviewer runs become acceptance requirements for this project.

## 2. Verified starting point

- Package/executable: `reviewer_mcp` / `reviewer-mcp`; 11 public tools.
- FastMCP, MCP and PyMuPDF dependencies already exist; SQLite is from the stdlib.
- Tools select a paper by argument and usually restrict access to the inferred
  manuscript. Overview resets persisted consumption state; repeated reads can be
  suppressed. Asset/image quotas are six/four by default.
- Page cursors lose the original end page. Section reading can truncate an
  oversized paragraph without a complete continuation.
- Asset keys are `(segment, id)`; lookup by `id` alone returns the first match.
  Full-document access therefore needs unambiguous public IDs.
- Crops are rendered in memory, not cached as the old PLAN claimed. Multipage
  textual assets currently yield a crop from only their first page.
- Existing CI runs unittest, Ruff, basedpyright and Vulture. External corpus tests
  may skip when PDFs are absent. No tests or institutional calls were run for this
  planning handoff.

## 3. Target contract

This is the final contract, introduced incrementally by the tasks below. Do not
add unused parameters or stubs for later tasks. Intermediate behavior must be
described honestly in README.

### Document and execution

- One local stdio server process serves one configured PDF. Read
  `PDF_INGESTION_PDF` and `PDF_INGESTION_RUN_DIR` at startup; both are required
  from MCP-02 onward. Reject missing/invalid PDF configuration before serving tools.
- The host supplies a distinct run directory for an independent execution.
  Keep indexes, rendered images and later visual diagnostics there; create each
  subdirectory only when needed. No shared user-global scratch or filename search.
- The PDF is fixed for the process lifetime. A changed source requires a new
  process/run; reuse the existing fingerprint/cache validation, not a new scheme.
- Expose a stable `document_id` based on existing document identity. Pages are
  one-based physical PDF pages. The original printed labels remain metadata.
- Search/read/list operate on all PDF pages by default. Inferred segments may
  inform metadata, but cannot hide content or select the scientifically relevant
  antenna. Document text, captions and extracted content are data, not instructions.
- Deterministic rereads return the same content for the same input. No overview
  reset, consumed-page state, consumed-asset state or global image/call quota.

### Tools

| Tool | Target arguments | Essential output |
| --- | --- | --- |
| `get_paper_overview` | none | Document identity, page count, optional extracted title, outline with section IDs, asset counts, extraction warnings |
| `read_pages` | `first_page=None, last_page=None, cursor=None` | Page-labelled text fragments and `next_cursor` |
| `read_section` | `section_id, cursor=None` | Section identity, page-labelled text fragments and `next_cursor` |
| `search_paper` | `query, first_page=None, last_page=None, cursor=None` | Total matches, ordered page/section snippets and `next_cursor` |
| `list_assets` | `kind=None, first_page=None, last_page=None, cursor=None` | Ordered asset metadata, total matches and `next_cursor` |
| `get_asset` | `asset_id, question=None` | Source-linked deterministic content; an additional learned answer only when a question is supplied |

Contract details:

- Use compact dictionaries and MCP text results; preserve table Markdown and
  equation text/MathML. Avoid a hierarchy of response models. Images are materialized
  internally for the visual helper; the principal agent need not receive image bytes.
- Include `document_id` in responses and source page/asset/section identity where
  applicable. Readers return fragments as `{page, text}`. Preserve each fragment's
  page even when a paragraph crosses a page boundary.
- Page range defaults: neither bound means the whole PDF; first only means that
  single page; last only means pages 1 through last. Bounds are inclusive. Invalid
  bounds are errors, not silently clamped values.
- Cursor continuation preserves the original range, query/filter/section and exact
  position. Use a small JSON cursor encoded with stdlib helpers; validate against
  the bound document and reject conflicting arguments. It is an opaque continuation,
  not a security token; no signatures, cursor database or generic paging framework.
  Keep `READ_BUDGET` as an initial text chunk size and document list page sizes.
- Section IDs may expose the existing section index ID. Public numbered-asset IDs
  must include the stored segment identity, e.g. `segment:2/figure:1`; return them
  from the catalog. Keep `label='Fig. 1'` separate. `page:4` names a full PDF page.
  Do not accept an ambiguous short ID and silently pick a match.
- Lists omit pages by default to avoid noise, include existing numbered kinds,
  including references, and allow `kind='page'`. No new detection families are needed.
- Search remains existing FTS phrase matching with a final-word prefix, not arbitrary
  substring or semantic search. Zero hits do not establish absence from the paper.
- `get_asset` without a question returns caption/content/format, source pages,
  extraction method and visual availability without rendering or inference. A page
  asset returns that page's extracted text and full-page visual availability.
- With a non-empty question, render the selected asset and call the visual model
  once. Return the learned answer separately from extracted content. Keep source
  metadata, status, limitations and an `inspection_id` linking diagnostics.
- Missing crop, invalid ID, model failure and unreadable content are distinct.
  A missing image causes no model call. Do not substitute a full page automatically;
  return page IDs so the principal agent can explicitly request one.
- Multipage assets retain the full source span. If only the first-page crop is
  available, identify `rendered_pages` and `visual_coverage='partial'` in both the
  visual prompt and result. Never imply all pages were inspected.
- Expected invalid arguments use `ToolError`. Recoverable source/model limitations
  carry explicit status and reason. Do not claim idempotence for a tool that can
  perform fresh inference. Keep schema descriptions short and factual.

### Visual execution boundary (MCP-09A/B)

Use an OpenAI-compatible client, with environment-only settings:
`SKYNET_BASE_URL`, `SKYNET_API_KEY`, `VISUAL_INSPECTION_MODEL`, and
`VISUAL_INSPECTION_TIMEOUT_SECONDS` (positive and finite). Text tools must work
without these settings. Read/validate them only when vision is invoked; never
print credentials. The host can supply its existing environment, without a new
dotenv dependency here.

The helper receives one explicit question, the actual image, source identification,
caption and available local asset text. No whole-paper prompt, tools, recursion,
automatic retries or other model fallback. Prompt for local observations and
specific uncertainties, without numerical estimates from image proportions or
unsupported scientific defaults. The principal agent makes global conclusions.

Persist one diagnostic JSON per inspection under the run directory, including the
question, prompt/context, source/render references, model/settings without secrets,
received model response, usage when supplied, duration and outcome. Save received
responses before validation. Do not duplicate base64 images in logs or introduce
a new trace database. Transport failure may have no response. Truncation/empty
answers are failures, with partial output retained only as diagnostics. Return a
compact answer and diagnostic ID to the caller, not the entire raw response.

## 4. Tasks

Execute in order. All source paths below are under `src/reviewer_mcp/` until MCP-10.
Each task includes focused tests and the checks/documentation workflow in AGENTS.
Use existing libraries unless a task explicitly says otherwise.

### Thread and commit workflow

Each numbered task below is one implementation thread and one intended owner-made
commit, including its code, tests and documentation updates. Use the full task
heading as the thread title. MCP-08A/B, MCP-09A/B and MCP-11A/B are separate tasks,
threads and commits. Follow the listed order; do not combine adjacent tasks.

Start a fresh thread for each new task. Keep review corrections in that task's
thread and commit. If context runs low, record a concise TODO resume note and
continue the same task in a fresh thread; this does not create another task or
require an extra commit. Do not expand scope merely to finish in one session.

At handoff, mark `review_pending`, report checks and give the suggested commit
message at the end of the task. The owner reviews, requests corrections if needed,
then explicitly accepts. Only then may the coding agent record `done` and update
the next-task pointer, without starting it. The owner creates the commit before
assigning the next task. Never claim a commit exists without evidence.

Commit messages below are suggestions, not executable instructions. A blocked or
partially verified task is not a completed commit boundary. MCP-11B may contain
only documentation and authorized probe evidence; do not invent code changes.

### MCP-01 - Expose six neutral tools

**Goal:** remove review policy from the public service while keeping extraction.

**Files:** `server.py`, `papers.py`, `tests/test_server.py`; reviewer-only modules
and tests only when their imports are demonstrably disconnected.

**Changes:**
1. Remove public registration for `set_manuscript_pages`, `get_author_responses`,
   `get_review_guideline`, `submit_report`, `update_report_field`.
2. Replace server/tool reviewer instructions. Overview no longer resolves venues,
   requires forms, reads reviewer notes or orders the consumer to stop for a venue.
3. Expose full-PDF outline/counts and warnings. Retain optional title extraction as
   metadata, not an access restriction. Include existing section IDs.
4. Remove fully unused reviewer modules/imports and their dedicated tests after
   checking references. Keep `structure.py`: asset indexing still uses segments.
   Do not remove state resets yet if retained readers still depend on them.

**Verify:** exactly six tool names; overview works without forms/base_review/notes;
missing title is allowed; document extraction tests remain useful.
**Stop:** six neutral tools are callable. No signature redesign or parser tuning.

**Suggested owner commit after acceptance:**
`refactor(mcp): expose six neutral PDF tools`

### MCP-02 - Bind one PDF and run directory

**Files:** `config.py`, `papers.py`, `server.py`, `runner.py` if needed;
`tests/pdf_fixtures.py`, `tests/test_server.py`, focused `tests/test_config.py`.

**Changes:** load the two document/run settings at startup; have `_open()` resolve
only that configured file. Remove `paper` from all six public signatures. Root the
existing store in the configured run directory. Remove workspace filename fallback.
Fixtures set isolated configuration; no real workspace or user temp directory.

**Verify:** missing configuration, invalid PDF, names with spaces, and two isolated
processes with different PDFs having the same filename. Source identity and answers
must match. Text tools need no model credentials.
**Stop:** configuration binds each server to one document. No session manager or
consumer-repository changes. Existing reader quotas disappear in later tasks.

**Suggested owner commit after acceptance:**
`feat(mcp): bind each server to one PDF and run directory`

### MCP-03 - Make page reading repeatable and lossless

**Files:** `reading.py`, `server.py`, relevant `store.py` queries;
`tests/test_server.py`, new `tests/test_reading.py` as needed.

**Changes:** remove the public `part` argument for page reading and reference-list
omission. Remove consumed-page checks/writes. Implement page range defaults and
continuation from the contract, including within an oversized page. Return
page-labelled fragments. Reuse existing extraction rather than changing reading
order heuristics. Reject invalid ranges/cursors instead of clamping.

**Verify:** repeated/overlapping requests; a long page; multiple chunks of a strict
subrange; references after the inferred manuscript; invalid/reused-wrong-document
cursor; scanned versus blank page. Concatenated fragments recover the selected
extracted text exactly (apart from response metadata), with no pages beyond last.
**Stop:** all requested page text is recoverable and rereadable.

**Integration checkpoint:** the owner can now test overview/read_pages through the
external Agents SDK client. The coding agent reports readiness and does not edit that project.
Continue later tasks only when assigned; do not invent a successful SDK probe.

**Suggested owner commit after acceptance:**
`fix(reading): make page reads repeatable and lossless`

### MCP-04 - Read complete sections by ID

**Files:** `reading.py`, `server.py`, `papers.py`, `store.py` if necessary;
`tests/test_reading.py`, `tests/test_server.py`.

**Changes:** replace heading matching with `section_id` from overview. Use existing
section boundaries; include subsection content up to the next equal/higher heading.
Paginate paragraphs, including oversized paragraphs, without silently slicing them.
Use stored line/page information for fragments spanning pages. Avoid manuscript
filtering and do not treat absence of an outline as absence of document text.

**Verify:** duplicate heading titles with distinct IDs; long paragraphs; section
continuation staying inside its boundary; unknown ID; missing outline; cross-page
source references. Repeated calls remain independent.
**Stop:** section text has complete continuation and truthful page provenance.

**Suggested owner commit after acceptance:**
`fix(reading): paginate complete sections by ID`

### MCP-05 - Paginate textual search

**Files:** `store.py`, `reading.py`, `server.py`; `tests/test_store.py`,
`tests/test_reading.py`, `tests/test_server.py` as relevant.

**Changes:** preserve existing FTS semantics and parameterized SQL. Replace public
`part`/`max_hits` with the agreed range/cursor interface and an internal documented
result page size. Use stable paragraph order; preserve query/range in continuation.
Return total matches, page, section ID/title where available, and contextual snippet.

**Verify:** more hits than one result page; zero hits; query containing quotes;
range filtering; cursor replay and mismatched query; no duplicates or missing hits.
**Stop:** all matching occurrences can be traversed. No new search library.

**Suggested owner commit after acceptance:**
`feat(search): add stable pagination and page filters`

### MCP-06 - Resolve numbered assets without ambiguity or quotas

**Files:** `store.py`, `papers.py`, `server.py`, `config.json`;
`tests/test_store.py`, `tests/test_server.py`, synthetic fixtures.

**Changes:** encode segment and stored ID in the public ID and resolve that exact
pair; preserve printed labels. Update catalog and retrieval together. Use full-PDF
scope. Remove asset/image consumption quotas and overview resets; remove obsolete
consumption keys/helpers once unused. Keep deterministic extraction cache behavior.
Return original content, caption, format, method, source span and availability.

**Verify:** two segments containing `figure:1`; exact retrieval and mentions for
each; ambiguous short ID rejected; repeated retrieval and more than six distinct
assets; stale reviewer consumption state has no effect.
**Stop:** every listed ID resolves to its own asset. Do not flatten segments in the
extractor or rewrite detection rules. Rendering changes belong to MCP-08.

**Suggested owner commit after acceptance:**
`fix(assets): resolve unique IDs and remove consumption quotas`

### MCP-07 - Paginate and filter the catalog

**Files:** `server.py`, `store.py`; `tests/test_store.py`, `tests/test_server.py`.

**Changes:** implement kind/range/cursor filters with stable ordering and counts.
Use range overlap (`page <= last` and `last_page >= first`) for multipage assets.
Differentiate caption preview from full content and region availability from crop
quality. Expose only kinds already supported by the extractor. Pages are added
in MCP-08, not advertised as implemented here.

**Verify:** catalog longer than one response; repeated cursor; kind/range filters;
an asset starting before but continuing into the range; same labels across segments;
every returned numbered-asset ID is resolvable.
**Stop:** complete catalog traversal. No relevance ranking or heuristic tuning.

**Suggested owner commit after acceptance:**
`feat(assets): paginate and filter the asset catalog`

### MCP-08A - Render exact crops and full pages

**Files:** `crops.py`, `server.py`, `config.json`; new `tests/test_crops.py`,
`tests/test_server.py`, relevant fixtures.

**Changes:** add `page:N` and `kind='page'`; render directly from the configured PDF
using PyMuPDF. Preserve page, crop bounds and rendered coverage. Handle clipped,
rotated and invalid regions without inventing a replacement crop. For multipage
assets, declare first-page-only coverage and expose all source page IDs.
Keep the existing optional `include_image` transport temporarily for this task's
MCP image tests; it is removed when MCP-09B establishes the final question interface.

**Verify:** synthetic known page/crop content and dimensions; rotated page; missing
region; invalid page; partial multipage crop; actual MCP image content delivery.
**Stop:** deterministic images and provenance are correct. No VLM invocation.

**Suggested owner commit after acceptance:**
`feat(rendering): support exact crops and full-page assets`

### MCP-08B - Reuse materialized images

**Files:** `crops.py`, a small persistence helper only if needed; `tests/test_crops.py`.

**Changes:** save requested PNGs lazily inside the configured run directory. Reuse
only when document identity, page/bounds and render settings match, using existing
identity plus a simple key/metadata. Write atomically; do not overwrite valid output
with a failed render. Do not cache learned interpretations.

**Verify:** repeated request renders once; changed render settings do not reuse the
wrong image; separate runs are independent; failed write leaves no valid cache hit.
**Stop:** correct images can be referenced and reused. No new cache database/hashes.

**Suggested owner commit after acceptance:**
`feat(rendering): reuse images within each run`

### MCP-09A - Add one-call visual inspection with diagnostics

**Files:** new `visual_inspection.py`, `config.py`, minimal persistence helper;
`pyproject.toml`, `uv.lock`, new `tests/test_visual_inspection.py`.

**Changes:** add `openai>=3.6.0,<4` to match the consumer's existing dependency range;
verify resolution in this environment without upgrading unrelated dependencies.
Build an importable async inspection function using `AsyncOpenAI`, non-streaming
chat completions, an image data URL, explicit timeout and `max_retries=0`. No Agents
SDK is needed inside the helper. Implement the visual boundary and diagnostic JSON
defined above, with a local inspection ID and atomic persistence. Save every received
response before checking empty output or `finish_reason='length'`. Record errors;
if required persistence fails, do not report a successful inspection.

**Verify:** scripted client captures exact question/image/context; one call only;
missing configuration; timeout; server error; empty/truncated reply; raw response
retained on failure; usage optional; no secrets or duplicate image bytes in JSON.
**Stop:** a directly callable, tested helper exists. No public `question` placeholder
or real endpoint call yet. The host supplies the model; do not pick one by assumption.

**Suggested owner commit after acceptance:**
`feat(vision): add single-call inspection and diagnostics`

### MCP-09B - Connect visual questions to get_asset

**Files:** `server.py`, `visual_inspection.py`; `tests/test_server.py`,
`tests/test_visual_inspection.py`.

**Changes:** replace `include_image` with `question=None` in the final public tool.
No question means deterministic content with zero inference. A supplied question
must be non-blank. Render/reuse the exact image, await one helper call, then return
extracted content and a separate visual result with status, answer, limitations,
source/render coverage and inspection ID. Missing imagery means no inference.
Update `_agent_errors` for awaited exceptions if used on async functions. Ensure
visual calls serialize even if a client submits simultaneous requests; do not hold
the SQLite lock across a network await. Do not mark this mixed tool idempotent.

**Verify:** actual MCP invocation with a fake model; zero versus one model request;
full-page question; partial crop warning; missing crop; async failure; sequential
model requests; diagnostic ID resolves under the run directory.
**Stop:** all six tools meet the final contract. No automatic page/model fallback.

**Suggested owner commit after acceptance:**
`feat(mcp): support visual questions in get_asset`

### MCP-10 - Align package identity and local setup

**Files:** `pyproject.toml`, `uv.lock`, package/import paths, `tests/test_init.py`,
CI, hooks, README and AGENTS wherever paths are affected.

**Changes:** rename distribution/executable to `mcp-pdf-ingestion` and import package
to `mcp_pdf_ingestion`. Update build configuration, imports, type/dead-code settings
and obsolete reviewer-only configuration. Preserve original-work attribution.
Document setup and the final configuration without personal paths. Keep existing
test/lint tools; make changed launch examples shell-appropriate. Do not install hooks.

**Verify:** clean editable install, package import, real stdio launch, full suite and
checks. Search for unintended old paths; historical references are allowed.
**Stop:** naming/setup agree with the code. No extraction behavior changes here.

**Suggested owner commit after acceptance:**
`refactor(package): rename reviewer MCP to PDF ingestion`

### MCP-11A - Verify the complete local MCP contract

**Files:** `tests/test_server.py`, small focused protocol tests if necessary, README,
TODO and HISTORY. Do not add the external agent to this repository.

**Changes:** exercise a real stdio process with a synthetic PDF: discover six tools,
overview, paginated reads/search/catalog, repeated retrieval and page assets. Verify
no forms, reviewer state or external workspace is required. Cover vision through
the fake-client integration from MCP-09B. Use negotiated protocol behavior supported
by the installed libraries; do not add protocol patches or upgrade for a date string.

**Verify:** full local checks, isolated runs, useful parameter descriptions, truthful
tool annotations and no stdout contamination. Report corpus skips explicitly.
**Stop:** local contract is verified; remote and scientific acceptance remain separate.

**Suggested owner commit after acceptance:**
`test(mcp): verify the complete stdio tool contract`

### MCP-11B - Run owner-authorized probes and record handoff

**Files:** optional `scripts/probe_visual.py`, its tests if substantive, README,
TODO and HISTORY. No edits to the antenna repository or personal coding-agent settings.

**Changes:** first present the proposed PDF/image, question, endpoint/model setting
names and expected calls. After owner authorization, run sequential text/visual
probes with explicit outcomes and retained diagnostics. An opt-in script may call
the MCP or helper; it must not run during normal tests or print secrets.

**Verify:** real image/question reaches the VLM; reply/usage/failures are inspectable.
The owner runs the external Agents SDK integration and provides results. Record
that evidence as owner-reported unless directly observed; do not infer success.
**Stop:** MCP handoff and known limitations documented. Missing endpoint/access is
a specific blocker for this task, not a reason to redo the local implementation.

**Suggested owner commit after acceptance:**
`docs(mcp): record authorized probes and integration handoff`

## 5. Completion and deferred work

MCP work is complete after owner review when the six-tool contract, isolated PDF
binding, recoverable pagination, unambiguous assets, explicit visual delegation,
diagnostics, local checks and authorized probes have evidence. A technically
successful call is not scientific validation of an extracted claim.

The antenna repository owns its SDK agent loop, A/B selection, lifecycle, report
format and manual scientific comparison. Do not implement those here.

Keep known limitations visible: heading/table/equation extraction can be wrong;
some crops are unavailable or partial; external corpus PDFs are not bundled.
Do not repair every inherited heuristic, build perfect multipage crops, add new
asset kinds, full-document OCR, semantic search, automatic fallback, global call
quotas, or a generalized session service to finish this plan.
