# reviewer-mcp

An MCP (Model Context Protocol) server that serves one academic paper PDF as evidence: it reads the PDF
deterministically and exposes it through six neutral tools — document overview, page and section reads, search, and
numbered-item listing and retrieval. It does not select content, synthesise conclusions or validate scientific claims;
the consuming agent decides what to read and how to use it.

## Key Features

* **Deterministic paper store**: one PyMuPDF pass per PDF into a SQLite store in the server's run directory
  (`$PDF_INGESTION_RUN_DIR/store/<fingerprint>/paper.sqlite`), keyed by the PDF content. Pages, lines, paragraphs,
  sections, full-text search, submission parts and
  numbered items (figures, tables, equations, algorithms, listings, references) with their citations. No LLM involved.
* **Numbered items read the way they are printed**: a caption is a label, a separator and the caption text
  (`Fig. 1. Evolution ...`, `Table 4: Benchmark datasets`), or a label alone on its line whose text is the line below
  (`Table 1` / `Summary of ...`) — a space is not a separator, so `Table 5 compares ...` stays a sentence. The label
  takes a full or short name with or without the period, and the letter of a part belongs to the number, so
  `Fig. 5(a)` and `Fig. 5(b)` are the items `5a` and `5b`, each with its own region. Items set after the References
  count too: floats at the end of a proof, and appendices.
* **Tables limited by their rules, not by the page**: a table ends at its last rule, so when no further rule of its
  own follows and the next page opens with rules with the same ends, it carries on there. Booktabs' three rules and a
  table ruled on every row behave alike. Items report a page span (`"15-16"`).
* **Layout rules relative to each document**: tolerances are factors of the measured body size and line height
  (`src/reviewer_mcp/config.json`, overridable with `REVIEWER_CONFIG`).
* **No files exposed**: tools operate on the server's bound PDF with PDF page numbers; no scratch paths in any reply.
* **MCP protocol `2026-07-28`**, negotiated natively by fastmcp 4.

## Tools (6)

1. `get_paper_overview` — start here: document identity (file name and content fingerprint), page count, extracted title when one is found, the full-PDF
   outline with section ids, numbered-item counts and extraction warnings.
2. `read_pages(first_page=None, last_page=None, cursor=None)` — repeatable page-labelled text, including
   references, with exact continuation within long pages (12,000 text characters per response).
3. `read_section(section_id, cursor=None)` — complete section text by an ID from the overview outline,
   including subsections until the next equal/higher heading, with page provenance and continuation.
4. `search_paper(query, first_page=None, last_page=None, cursor=None)` — paginated textual matches,
   total matching paragraphs, source pages, section IDs/titles and snippets.
5. `list_assets(kind=None, first_page=None, last_page=None, cursor=None)` — paginated numbered items,
   including references, with canonical IDs and source bounds.
6. `get_asset(asset_id, question=None)` - full extracted content and citations for an exact asset or page.
   An explicit non-blank question requests one fresh visual inspection of its precise crop/full-page PNG.
   Learned output is separate from deterministic extraction. No asset/image consumption quotas.

Canonical IDs include segment identity, such as `segment:2/figure:1`, and keep the original printed `label`
separate. Use catalog IDs unchanged: short IDs such as `figure:1` are rejected. Retrieval returns `document_id`,
`id`, `label`, `kind`, numeric `first_page`/`last_page`, `caption`, `content`, `format`, `method`, `confidence`,
`cited_count` and up to 12 `cited_by` contexts. Duplicate labels in different segments remain distinct.

`page:N` selects the one-based physical PDF page, including its stored text (possibly empty) and full visible
page. Missing text does not prevent rendering. Leading zeros, invalid IDs and pages outside the PDF are errors.
`region_available` reports coordinate presence; `visual_available` reports validated geometry.
Without a question (or with `question=null`), the server returns deterministic content and
`visual.status="not_requested"`: zero model calls, no visual credentials loaded, no rendering,
PNG creation or decoded image-cache lookup. Blank/non-string questions are rejected before rendering.
With a question, the existing PNG is rendered/reused and sent to one non-streaming Chat Completions request.
The result remains MCP text only; image bytes are internal. `include_image` and `images.enabled` are retired.

`render` records requested/effective bounds, coordinate system, page geometry, clipping and availability/reason.
Bounds use `pymupdf_unrotated_visible_page_points`: points from the visible page's top-left, x right and y down,
before rotation, matching stored PyMuPDF extraction bounds. They are not raw MediaBox coordinates. The renderer
intersects in unrotated space, then rotates the clip into displayed orientation. Full-page images use the visible
CropBox, including rotation. `images.max_side` controls the longest image side in pixels and must be positive.
Non-finite source coordinates are represented as strings to keep metadata valid JSON. Missing, inverted,
non-finite or fully outside regions return an unavailable reason and preserve text; no replacement crop is chosen.

`first_page`/`last_page` and `source_page_ids` preserve the complete source span. `rendered_pages` is empty when
no image was prepared for inspection; `visual_coverage` is then `none`. A multipage numbered asset renders only its existing
first-page region, declares `partial` coverage and gives page IDs for explicit follow-up. Clipped images also
declare partial coverage; otherwise coverage is `single_page`. `limitations` explains these cases. There is no
stitching or region inference. These exact coverage fields and limitations reach both the model prompt and
`visual` result. A prepared image does not establish a successful observation; check `visual.status`.
Overview does not reset consumption state; stale counters have no effect. Deterministic access remains repeatable.

Requested deterministic PNGs are created lazily under `PDF_INGESTION_RUN_DIR/images/<document fingerprint>/`.
Each asset has one internal PNG filename with embedded JSON metadata. Reuse requires the existing full document
fingerprint, asset/page identity, requested/effective bounds, rotation/page boxes, render size, RGB/alpha settings,
PyMuPDF version and renderer-format version to match. The PNG container, compressed data and pixels must validate.
Repeated requests and reopening/restarting with the same valid run directory reuse the image with current source provenance.
Each visual question makes a new inspection with a new diagnostic ID, even when the PNG is reused. Different documents and runs remain isolated. Absolute cache
paths are never tool output. Text-only requests and catalog listing create no image files or cache lookups.

PNG pixels and metadata are replaced together using a temporary file in the destination directory, fsync and an
atomic replacement. Per-asset locks coalesce concurrent threads without holding SQLite locks. Concurrent processes
may render redundantly but cannot expose a partially written entry. Incomplete/corrupt/mismatched entries are cache
misses; render/write failures are reported and preserve a previous valid PNG. Each asset retains only the latest
successful render settings. There is no answer cache, cache database or new document hashing scheme.

### Visual results and diagnostics

`visual` contains `status`, an `answer` only on success (otherwise a `reason`), source page IDs,
rendered pages, coverage, bounds and limitations. Model output never replaces extracted `content`.
A missing/invalid region returns `unavailable` with zero model calls; explicitly request one of
`source_page_ids` to inspect a full page. Invalid IDs remain MCP tool errors. Other failures are distinct:
`render_error`, `image_persistence_error`, `configuration_error`, `timeout`, `model_error`,
`empty`, `truncated`, `refused`, `invalid_response` or diagnostic `persistence_error`.
No failure fabricates an observation or triggers a fallback. Missing text and zero search hits do not
establish absence from the paper. The helper asks for visible local evidence and explicit uncertainty,
never proportional dimension estimates, invented materials or whole-antenna conclusions.
Captions, extracted text and image text are source data, not instructions.

`inspection_id` resolves locally to `PDF_INGESTION_RUN_DIR/inspections/<inspection_id>.json`.
Each helper invocation publishes one unique record atomically (temporary file, fsync, replacement).
It includes question, system prompt/source context, run-relative PNG reference, render metadata,
non-secret settings/model, received response, optional usage, duration and outcome. Image base64 and
credentials are omitted/redacted. Endpoint settings record only scheme/host, never URL credentials or queries.
Received responses are saved with outcome `received` before answer validation, then the same record is updated
with its final outcome. A process interruption can leave that intermediate record for diagnosis.
Empty/truncated/refused/tool-call outputs remain diagnostics only. Transport failures have no completion payload.
Required diagnostic write failure returns neither success nor an inspection ID; a previously saved intermediate
record may remain locally. Cancellation propagates and attempts to save a cancelled outcome.

Visual requests serialize within the server process across simultaneous calls and event loops. Cancellation
and failures release the gate. Rendering/file work runs off the event loop; SQLite locks are not held across
network awaits. The client is closed after each invocation. There are no tools, retries, fallback models,
Agents SDK, second completions or answer caching. `get_asset` therefore claims neither read-only nor idempotent
behavior; the other five tools retain their annotations. Validation so far uses synthetic PDFs and fake clients;
real endpoint and consumer integration remain unverified and require separate owner authorization.

The catalog returns up to `ASSET_PAGE_SIZE = 20` items per call, ordered by stored sequence, then segment and
stored ID as a unique tie-breaker. Defaults cover the whole PDF and all numbered kinds: `figure`, `table`,
`equation`, `algorithm`, `listing`, `statement`, `reference`. Explicit `kind="page"` selects only full-page assets
in ascending physical-page order, with the same inclusive range defaults and cursor validation. Page catalog
entries derive from page count/range, omit full text and never render images; pages are excluded by default.

```json
{"document_id":"<fingerprint>","items":[{"id":"segment:2/figure:1","label":"Fig. 1","kind":"figure",
 "first_page":5,"last_page":5,"caption_preview":"Fig. 1. Example caption","cited_count":2,"region_available":true}],
 "total_assets":1,"counts":{"figure":1},"next_cursor":null}
```

`total_assets` and kind `counts` cover the entire filtered result, including items on subsequent response pages.
`caption_preview` is a whitespace-normalized caption truncated to 140 characters; use `get_asset` for full content.
Catalog ranges are inclusive and select overlap (`asset.page <= last_page` and `asset.last_page >= first_page`):
an asset beginning earlier is included if it continues into the requested range. Neither bound selects all pages;
first only selects one page; last only selects pages 1 through last. Invalid ranges are errors.

Pass `next_cursor` unchanged until null. Omitted kind/bounds retain the cursor's filters; conflicting explicit
filters are errors. To change or clear a kind filter, start without a cursor. Document, operation, kind, range
and result position are preserved; cursor replay is deterministic. Empty results contain `items: []`,
`total_assets: 0`, `counts: {}` and null continuation. No unpaginated auxiliary ID list is returned.

For page reads and search, bounds are inclusive: neither bound selects the whole PDF; first only selects that page;
last only selects pages 1 through last. Invalid ranges are errors. Pass `next_cursor` unchanged until it is null;
a cursor retains the original document and range, and conflicting explicit bounds are errors. Reads can be
repeated or overlapped without an overview reset. Concatenating fragments per page recovers stored text exactly.

```json
{"document_id":"<fingerprint>","fragments":[{"page":1,"text":"Extracted text"}],"next_cursor":null}
```

Empty pages retain `{ "page": 1, "text": "" }` and an `empty_pages` entry with the stored `source`:
`blank`, `none` (no text layer, e.g. image-only), or `text` (text was extracted but no body text remains).
No OCR or inferred content is added.

Section reads return the same `document_id`, `fragments` and `next_cursor` fields plus section identity:

```json
{"document_id":"<fingerprint>","section":{"id":2,"number":"1","title":"Introduction","level":1,"page":3},
 "fragments":[{"page":3,"text":"1 Introduction\n\nSection text"}],"next_cursor":null}
```

Repeat `section_id` with the returned cursor. IDs disambiguate repeated heading titles. Concatenating fragment
text in response order reconstructs the stored paragraphs separated by two newlines, including long paragraphs.
Cross-page paragraphs retain each source page and the extractor's existing dehyphenation. An unknown ID is an
error; if no outline was extracted, use page reads. Inferred manuscript boundaries do not restrict section reads.

Search uses SQLite FTS phrase matching with a final-word prefix, case-insensitively: `proposed meth` finds
`proposed method`. It is neither arbitrary substring matching nor semantic retrieval. `query` is required,
non-blank and at most 120 characters. The internal `SEARCH_PAGE_SIZE` is 15 matching paragraph records per
response, ordered by unique stored paragraph ID. Range filters use the paragraph's starting physical page;
a paragraph may continue onto later pages. Total hits count matching records, not individual word occurrences.

```json
{"document_id":"<fingerprint>","query":"proposed meth","pages":"1-17","total_hits":1,
 "hits":[{"paragraph_id":9,"page":4,"section_id":2,"section_title":"Introduction","snippet":"The [proposed method] ..."}],
 "next_cursor":null}
```

Section fields are null when no section is available. Repeat the exact query with `next_cursor`; omitted bounds
retain its range, while conflicting query/bounds are errors. Cursors are opaque JSON encoded with base64,
limited to 4,096 characters, and bound to document identity and operation. They can be replayed unchanged;
legacy page-number cursors are rejected. No cursor signing or server-side cursor state is used.
Zero matches return `total_hits: 0`, an empty `hits` list and null continuation; they do not establish scientific
absence. Text tools and question-free assets invoke no model. Full-document OCR remains future work;
external consumer integration is deferred.

## Environment

* `PDF_INGESTION_PDF` — the PDF bound to the server process; required, must exist as a usable PDF (relative paths
  are resolved against the startup working directory, spaces preserved).
* `PDF_INGESTION_RUN_DIR` — isolated run directory for derived data; required, may not exist yet (persistence creates
  it on demand) and must not point to an existing file.
* `REVIEWER_CONFIG` — JSON file overriding values of `config.json`: layout factors (`heuristics`), image
  rendering (`images`: `max_side`). Remove obsolete `images.enabled`, `images.budget` and
  `replies.asset_budget` overrides; unknown image settings are rejected when rendering is requested.
  A question is the only visual trigger; there is no second enable switch or consumption quota.
* `REVIEWER_SCRATCH_BASE` — legacy store base (default `/tmp/reviewer`) used only when a store is opened without an
  explicit run directory (internal extractor tests); the server always uses its bound run directory.

The following environment settings are required **only for an explicit visual inspection**. Startup,
text tools and question-free assets work without them. No dotenv loader or default model is supplied:

* `SKYNET_BASE_URL` � absolute HTTP(S) URL of the OpenAI-compatible service.
* `SKYNET_API_KEY` � service credential, never included in diagnostics.
* `VISUAL_INSPECTION_MODEL` � host-selected model identifier; no fallback.
* `VISUAL_INSPECTION_TIMEOUT_SECONDS` � required positive finite seconds, passed explicitly to the client/request.

The async OpenAI SDK uses `max_retries=0`. Missing or invalid settings produce a diagnostic
`configuration_error` without initializing a client or sending a request.

## Development

Install dev tools and pre-commit hooks:

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

Real-paper checks run when `REVIEWER_WORKSPACE` points at a workspace with the validation papers.
