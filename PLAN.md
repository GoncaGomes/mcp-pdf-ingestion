# reviewer-mcp — Remediation & Streamlining Plan

> 2026-09-12: `components/` was renamed `forms/` and `components.py` merged into `forms.py`; older sections keep the
> former names.

Date: 2026-09-10 · Scope: `reviewer-mcp`, the Goose recipe `~/.config/goose/recipes/reviewer.yaml`,
the `~/Nextcloud/prompts` Makefile/docs, and the Goose model config. **crepe-mcp is out of scope (stable).**

Goal: a lean recipe where the MCP owns every piece of paper manipulation (extraction, caches, files,
structure, figures, forms, validation) and exposes it through a small set of precisely described tools,
so that `qwen3.8-27b` (a capable model for its size) can run a full review without shell access.

---

## 0. Constraints & principles

| Constraint | Consequence for the design |
| :--- | :--- |
| Agent: `qwen3.8-27b` via `custom_skynet` (Open WebUI), Goose 1.50.0, `GOOSE_CONTEXT_LIMIT=65536`, `summarize` strategy, `--max-turns 64` | Compact tool replies, page-boundary reads, a form reload tool before drafting, no bulk dumps. |
| MCP launched from `venv/bin/reviewer-mcp`, **never `uv`** | Dependencies pinned in `pyproject.toml`, installed with `venv/bin/pip install -e .`. |
| MCP protocol `2026-07-28` (Goose PR #11827) | Provided natively by `fastmcp>=4.0.3` / `mcp>=2.2`; no monkeypatching. |
| crepe-mcp stable; only its research sub-server is used | Recipe loads `crepe-research` only (see decision D5 on the name "crepe-academic"). |
| Venue from **metadata only** | No body-prose matching, ever (§2.2). |
| Revision from **page count + repeated structure** | No "revised"/"R2" regex on body text (§2.3). |
| MCP hides caches/files/extractions | No scratch paths, file names or line numbers in any tool input/output (§2.1). |
| **Tool descriptions are critical** | Every tool and parameter described, typed, bounded and cross-referenced (§2.8). |

---

## 1. Evidence baseline

### 1.1 Pipeline run (Access-2026-41373, 17 pages, `make review` in an isolated workspace copy)
3 min 34 s, 28 tool calls, report valid at the end — but ~10 calls were lost to MCP gaps:

| Calls | What happened | Root cause |
| :--- | :--- | :--- |
| `inspect_paper` ×2 | `OSError [Errno 36] File name too long`; the agent recovered metadata from the error text | F1 |
| `inspect_paper_scratch` + 2 × `shell` | `ls /tmp/reviewer`, `head`/`tail raw_paper.txt` | no document map / search tool (F9) |
| `read_paper_page` ×7 | overlapping ranges 4–6, 6–8, 8–10 … | truncation skips text (F4) |
| `render_paper_figures` + 2 × `read_image` | images never reached the model | Goose strips images (F8) |
| `shell` (python heredoc) + `validate_review_report` | agent patched the saved report on disk after a failed validation | invalid report written + no edit tool (F2) |

### 1.2 Findings

| ID | Severity | Finding | Evidence |
| :--- | :--- | :--- | :--- |
| F1 | High — fixed | `resolve_venue` calls `Path(guidelines/<2000-char text>_full.md).exists()` → ENAMETOOLONG | crashed in the run; crashes on all 3 bundles in `prompts/tmp` |
| F2 | High — fixed | Venue matching uses words/substrings of body text | "multiple access"→`ieee_access`, "algorithms"→`ieee_thms`, "statistical"→`acm_tist`; STRICT ABORT practically never fires |
| F3 | High | `save_review_report` writes invalid reports to `reports/`; Makefile only checks `test -f` | `saved: True, valid: False` |
| F4 | High | `read_paper_page` cuts at 12 000 chars mid-page but returns `next_page = last+1` | pages 4–6 = 16.3k chars → rest of page 6 skipped |
| F5 | High | Scratch keyed by lower-cased filename only; extraction skipped if `raw_paper.txt` exists; stale `paper.txt` preferred | replacing a PDF keeps returning the old text; same name in 2 dirs collides |
| F6 | High — dropped 2026-09-11 | Validator only parses `max N characters|words` | 7/22 venues use `(256 words)`/`(128 words)` → unenforced; only `elsevier_jii`, `elsevier_softx` enforced. Resolved by removing every length limit from the forms (the regex reading them was not stable): forms state the size in paragraphs (short sentence, short paragraph, 1-3 paragraphs) and the validator has no length rules |
| F7 | High | `.notes` never influence the review | Makefile does not pass them; recipe only reads `{{ comments }}` |
| F8 | High | Images omitted by Goose: *"This tool result included an image that was omitted as the model does not support vision."* | `llm_request.0.jsonl`; `custom_skynet.json` has no `qwen3.8-27b` entry, `catalog_provider_id: null`, `skip_canonical_filtering: true`; backend also lacks `mmproj-BF16.gguf` (sysadmin notified) |
| F9 | High | Tool schemas carry no parameter descriptions; overlapping tools; file/line concepts leak to the agent | e.g. `split_bundle.boundary_line: string|integer` with no hint |
| F10 | Medium | Named-section lookup matches the first short body line containing the word; section end needs `N. Title` | `section="results"` → body line on page 11 of Access |
| F11 | Medium | Revision regex on body text: IEEE template footnote *"Received XX Month; revised XX Month"*, R² values | TMLCN p4/p24 contain the footnote |
| F12 | Medium | `split_bundle` supports a single tail cut only; real bundles have cover + letters + manuscript copies in varying order | §2.3 table |
| F13 | Medium — fixed 2026-09-11 | Plain-text / bullet / emoji checks run only on length-limited fields | numbered lists in Access "Comments to the Author" pass |
| F14 | Medium | Protocol monkeypatch in `runner.py` is a no-op on mcp 2.2.0; `pyproject` allows `fastmcp>=3.0` where it would advertise an unimplemented protocol | `MODERN_PROTOCOL_VERSIONS == ('2026-07-28',)` already |
| F15 | Low | Tests write `reports/test_paper_Report.md` into cwd (polluted `prompts/reports/`), use real `/tmp/reviewer`, tautological tool-count test, forms test silently skipped without `guidelines/` | |
| F16 | Low | Workspace resolved from server cwd; missing `guidelines/` looks like STRICT ABORT | |
| F17 | Low | `renderer.py` leaks the document on exceptions, `dpi`/`max_figures` uncapped; dead branch in `inspect_paper_scratch`; docstring says "14 tools" | |
| F18 | Low | Docs stale: `prompts/README.md` describes the retired pipeline; TODO Phase 3 model list does not include `qwen3.8-27b` | |

---

## 2. Target design

### 2.1 Paper store and document indexes (hide caches, files, extractions)

Extraction is deterministic, done once per PDF, and locked away from the agent: the agent reasons about the paper's
merits using the assets the MCP returns, never about how text was extracted.

- **Single handle:** every tool takes `paper` = the PDF file name in `papers/` (a path is accepted, but never required or returned).
- **`store.py` / `PaperStore`:**
  - Fingerprint = `sha256(pdf bytes)` (computed once per `(realpath, size, mtime_ns)`); store dir `$REVIEWER_SCRATCH_BASE/<sha256[:16]>/`, mode `0700`.
  - **`paper.sqlite`** (stdlib `sqlite3`, WAL mode): one table per index below plus `meta` (fingerprint,
    `EXTRACTOR_VERSION`, PyMuPDF version, build time), `state` (manuscript override, report draft, attempt count) and
    `crops` (PNG blobs rendered on first request). Queries fetch only what a tool needs (a page range, one section,
    one asset), so nothing large is held in memory between calls.
  - Full-text search uses an **FTS5** table over paragraphs (`unicode61` tokenizer, prefix queries, `highlight()` for
    snippets); SQLite 3.53.4 in the venv provides FTS5 and JSON1 (verified).
  - The database is written to a temporary file and renamed into place, so an interrupted build never leaves a
    half-filled store; concurrent readers are safe.
  - Cache key = fingerprint + `EXTRACTOR_VERSION` + PyMuPDF version; any change rebuilds. Fixes F5.
  - No in-process cache beyond open connections (≤ 8 papers); the store on disk is the single copy.
- **Extraction pass (`document.py`):** one PyMuPDF pass per page with fixed flags: `get_text("dict")` spans (text, font, size, flags, colour, bbox), image blocks, vector drawings, page labels, `find_tables()`. Pages without a text layer (e.g. scanned) are marked `source: none` and reported to the agent; no OCR is performed. Documents are always closed (`with fitz.open(...)`). Fixes F17.
- **Indexes (`indexes.py`)** — every record carries `id`, PDF `page`, `bbox` and reading order:

| Index | Unit | Built from | Serves |
| :--- | :--- | :--- | :--- |
| `pages` | page text in reading order, headers/footers removed | column-sorted blocks | `read_pages` |
| `lines` | line text, bbox, dominant font/size | spans | search, heading and margin detection |
| `paragraphs` | column-aware merged blocks, hyphenation repaired | lines | `search_paper` snippets, mentions |
| `sections` | heading tree: level, number, title, page and paragraph range | typography (size rank, bold, numbering) | outline, `read_section` |
| `margins` | running heads/footers, page counters, proof line numbers | lines repeated across pages (`document.py`, derived) | submission profile (§2.2), removal from reading text |
| `references` | bibliography entries `[k]` / author-year | references section | citation checks, `get_asset("reference:k")` |
| `assets` | numbered items (below) | labels, captions, geometry | `list_assets`, `get_asset` |

- **Asset model (`assets.py`)** — every numbered item is retrievable as text:

| Kind | Detected by | Stored |
| :--- | :--- | :--- |
| `figure` | caption `Fig. N` / `Figure N` linked to the nearest image block or drawing cluster in the column | caption, text inside the region (axis labels, legends), crop image |
| `table` | caption `TABLE N` / `Table N` + `find_tables` region | caption, cells as Markdown, crop image |
| `equation` | display lines with math fonts (CMMI/CMSY/…) or high symbol ratio and a right-aligned `(n)` | linear Unicode text, MathML (decision D7), crop image |
| `algorithm`, `listing` | caption `Algorithm N` / `Listing N`, line numbers, monospace fonts | text with numbering preserved, crop image |
| `theorem` (theorem, lemma, definition, proposition, corollary, remark) | bold/italic label at paragraph start | statement text (and proof span when marked) |
| `footnote` | small-font block at page bottom with a marker | text |
| `reference` | references index | entry text |

  Each asset: `id` (`figure:3`, `table:II`, `equation:5`, `algorithm:1`), `kind`, printed `label`, `number`, `page`,
  `bbox`, `caption`, kind-specific `text`/`markdown`/`mathml`, `mentions` (paragraphs and pages citing it, from
  `Fig. 3`, `Table II`, `Eq. (5)`, `Algorithm 1`, `[12]`), `extraction` (`method`, `confidence`). Unreferenced assets
  and assets cited before they appear are listed as findings for the reviewer.
- **Determinism:** pinned PyMuPDF, fixed extraction flags, stable sort orders, no LLM anywhere; a snapshot test hashes
  the Access index and requires identical output across rebuilds.
- **Measured on Access-2026-41373 (17 pages):** span pass 1.1 s, `find_tables` 2.5 s (7 tables for 7 captions);
  737 blocks, 2 695 lines, 11 880 spans, 34 image blocks, 219 drawings; labelled items: 8 figures, 7 tables,
  2 algorithms, 6 equations. Headers/footers found: `Page # of #` (17 p), `VOLUME #, #` (14 p),
  `For consideration in IEEE Access` (3 p).
- **No agent-visible artefacts:** no `raw_paper.txt`/`paper.txt`/`responses.txt`/`manifest.txt`, no line numbers, no scratch paths. Addressing is by **PDF page number**, section heading, asset id, or continuation cursor.
- **Workspace:** `REVIEWER_WORKSPACE` env (default: cwd) passed by the recipe `envs`; server validates at startup that `papers/`, `components/` and `base_review.md` exist and returns `workspace_error` with the resolved path instead of a fake abort. Fixes F16.
- Scratch lifecycle stays OS-managed (`/tmp`); `make clean` removes `$REVIEWER_SCRATCH_BASE/*`.

### 2.2 Venue resolution from metadata — implemented 2026-09-10

Implemented in `reviewer-mcp` (`profile.py`, `venues.py`, wired into `inspect_paper`, `get_review_guideline`,
`get_form_template`, `validate_review_report`) and `components.py`. The old fuzzy resolver (`guidelines.py`:
`VENUE_PREFIX_MAP`, token overlap, substring stems) is removed, and so are `prompts/prompt.py` and the compiled
`guidelines/` files. Fixes F1 and F2.

**Single source of truth: the component.** Each `components/<venue_id>.md` starts with a `VENUE:` block
(`key: value` lines, lists separated by `|`, `#` in identifiers = a run of digits, no inline comments):
```
VENUE:
name: IEEE Transactions on Automation Science and Engineering
kind: journal
acronym: T-ASE
publisher: IEEE
aliases: IEEE TASE
identifiers: T-ASE-#-#
doi: 10.1109/TASE
CONTEXT: optional extra guidance (may span lines)
---
FORM:
...
```
- `kind` is `journal` (form of one journal), `publisher` (form shared by a publisher's journals) or `platform`
  (review system reused across conferences/journals: PRIMORIS, Sparcly, PeerJ).
- `components.py` validates each component and fails loudly on a missing block, missing `name`/`kind`, unknown or
  repeated keys, bad identifier or DOI syntax, or an empty form; such a component is excluded and reported in
  `index_problems`, together with names/aliases/acronyms, identifiers or DOI prefixes claimed by two venues.
- The venue index holds only VENUE metadata and is rebuilt when `components/` or `base_review.md` change.
- Guidelines are merged **lazily**, from disk, only when a tool asks for one: `base_review.md` with a **generated**
  context sentence (name/kind/acronym/publisher + optional CONTEXT) and the form. Nothing is compiled or cached; the
  result is byte-identical to the former `prompt.py` build for all 22 venues.
- The Makefile only orchestrates: review missing/outdated reports, `make test`, `make clean`.
- Adding a venue = new component; no build step, no MCP change.

**Submission profile** (`profile.py`, decision D1): file name/stem, size, modification time, SHA-256 (16 hex);
PDF producer/creator/dates, `subject`, XMP publication fields; the paper store's header and footer lines (text
repeated across pages, derived per document — no page bands), excluding "et al.:" running heads; labelled fields
with their same-row values on cover parts and on the first page of every other part (`Manuscript Number`,
`Submission ID/Version`, `Journal:`, `Conference:`, `For consideration in`, `Manuscript/Preprint submitted to`,
`DOI`/`Digital Object Identifier` followed by a DOI, first line of an Editorial Manager `--Manuscript Draft--`
page); DOIs found in those stamps. Title, abstract, body and references are never read. A one-page PDF whose
first body line names a journal has no header by any document evidence and stays unresolved. Validation corpus:
unchanged resolution for all 8 real papers (Access ×3 → ieee_access, TDSC → ieee_tdsc, oral → mdpi; IoT-J,
Neural Networks and TPDS have no component and abort); a reference-list DOI no longer leaks in as a footer.

**Evidence and decision** (`venues.py`):

| Evidence | Strength |
| :--- | :--- |
| identifier pattern at file-name start; acronym + separator + digit at file-name start; identifier inside a stamp; venue name/alias inside a stamp (a longer matching name shadows a shorter one); DOI prefix (longest prefix wins) | strong |
| acronym word inside a stamp | medium |

Precedence platform > journal > publisher. One strong venue at the best rank → `resolved/high` (others listed as
conflicts); several → `ambiguous` (abort); medium evidence for exactly one venue → `resolved/medium`; nothing →
`unresolved` (abort); explicit venue id → `resolved/explicit` with contradicting evidence listed. Venue ids are
validated (`^[a-z0-9_-]{2,64}$`) before any lookup.

**Component data (22 venues, sources: web research + local file names):**
- Wrong CONTEXT journal names fixed: `elsevier_softx` → SoftwareX; `ieee_jbhi-ems` → IEEE Journal of Biomedical and
  Health Informatics; `ieee_t-ase` → IEEE Transactions on Automation Science and Engineering.
- `insticc` = PRIMORIS platform (operated by INSTICC); `peerj`, `sparcly` = platforms; `mdpi`, `springer_nature` =
  publishers; the rest journals.
- Identifiers only where confirmed or observed: `Access-#-#`, `JII-D-#-#`, `SOFTX-D-#-#`, `EAAI-#-#`, `TII-#-#`,
  `TMLCN-#-#-#`, `JBHI-#-#`, `T-ASE-#-#`, `VT-#-#`, `TPRS-#-IJPR-#`, `peerj-reviewing-#`.
- DOI prefixes where verifiable; ACM journals share `10.1145` and are left without one.
- Gaps: identifiers for TFS, TDSC, THMS, ComMag, CSUR, TIST, AILET, MDPI, Springer Nature, Sparcly, PRIMORIS
  (acronym-based file-name matching covers the journals); stamps printed by PRIMORIS, Sparcly and PeerJ PDFs.

**Verified:** 22/22 components valid, no problems; Access-2026-41373 → `ieee_access` (high: file-name id and
"For consideration in IEEE Access" on cover and header); JII, TMLCN, JBHI, T-ASE, PeerJ and TVT file names resolve;
body text naming journals does not resolve; 39 tests pass with `REVIEWER_WORKSPACE` set.

### 2.3 Structure, segments and revision detection (page count + repeated structure)

**Per-page features** (cached in the manifest):
`chars`, `image_only`, submission stamps (EM item label on the first line, `Page x of N`, cover fields),
manuscript-start signals (Abstract heading, Keywords/Index Terms, IEEE `Received XX Month … revised …` template block, title repeat from metadata),
references-run signals (References heading + density of `[k] …`/`Author, A. (Year)` entries),
letter signals (salutation, `Response to (the) Reviewers`, `Reviewer #k`, alternating `Comment k`/`Response k`),
mark-up signals (coloured-span ratio, strike/underline/highlight annotations).

**Segmentation:**
1. If submission-system item labels exist (Editorial Manager stamps the upload type on the first line of each item — `Letter`, `Response to reviewers`, `Revised manuscript without author details (unmarked)`, `Highlights` …), split at them.
2. Within items (or the whole PDF for ScholarOne), cut at manuscript-start and letter-start signals; a manuscript block ends at the end of its references run (plus IEEE author bios until the next start signal).
3. Classify blocks: `cover`, `letter`, `responses`, `manuscript`, `other` (highlights, declarations, blank). **Content wins over labels** when they disagree (JII-00489 p15 is labelled "Response to reviewers" but is the manuscript) — the mismatch is reported as evidence.
4. Current manuscript: the single copy; with several copies prefer the `unmarked` label, then the lowest mark-up signal; otherwise the first copy with `confidence: low` so the agent confirms with `set_manuscript_pages`.
5. **Revision decision** (deterministic, explained): revision if a `responses` block exists, or ≥ 2 manuscript copies, or an EM label `Revised manuscript…`, or a metadata round marker (`…R2` manuscript number / file name); first submission if `Submission Version: Initial Submission` and none of the above. Supporting signal: `pdf_pages / manuscript_pages ≥ 1.5` with a letter block. Body-text regexes removed (fixes F11, F12).

**Expected results on the real corpus (verified by page inspection on 2026-09-10):**

| Paper | PDF pages | Expected segments | Round |
| :--- | ---: | :--- | :--- |
| Access-2026-41373_Proof_hi | 17 | cover 1–3 · manuscript 4–17 | first (`Initial Submission`) |
| JII-D-26-00489_R2_reviewer | 93 | EM cover 1 · short items 2–5 (highlights, letter p3) · responses 6–14 (own refs 13–14) · manuscript 15–92 (refs 77–92; "References" on p44–45 are table headers) · blank 93 | revision (R2) |
| JII-D-26-00697_R2_reviewer | 59 | EM cover 1 · manuscript 2–37 (label "unmarked", refs 33–37) · responses 38–58 · blank 59 | revision (R2) |
| TMLCN-03-26-0073.R2_Proof_hi | 56 | ScholarOne cover 1–3 · manuscript copy A 4–23 · manuscript copy B 24–43 · responses 44–55 | revision (R2); which copy is current needs the PDF's colour/annotation signals |

Only `Access-2026-41373_Proof_hi.pdf` exists as a real PDF (`prompts/papers/`). The three bundles survive only as
old `pdftotext` scratch in `prompts/tmp/`, so their rows above are used as **layout specifications for synthetic
fixtures** (same page ranges, item labels, stamps, reference runs, letter blocks), not as real-PDF tests. Signals
that need the PDF itself (span colour, annotations, fonts) are exercised on synthetic PDFs only; the TMLCN copy choice
is therefore specified by the fixture, not verified on the original.

### 2.4 Reading, search and responses

- `read_pages` (pages index): returns **whole pages** up to a budget (default 12 000 chars, bounds 2 000–24 000). If a page does not fit, stop before it; only a single oversized page is split, with a cursor `p6@4000`. Reply always has `next` (cursor or page) that resumes exactly where it stopped. Headers/footers are removed. Fixes F4.
- **Outline from typography** (sections index), not regex: headings = lines with font size above the body median or bold at line start, numbered/unnumbered, level from size rank; References/Appendix/Biographies recognised. Fixes F10.
- `read_section`: match only against section headings (numbering/case ignored, prefix match), section ends at the next heading of same or higher level, stops before References.
- `search_paper` (paragraphs index): case-insensitive literal search over the selected part; per hit `page`, section title and a 160-char snippet; `total_hits`. Replaces shell `grep/head/tail` (used 3–4 times per run so far).
- `get_author_responses`: parses reviewer blocks only at heading-like lines (`Response to Reviewer 4`, `Reviewer #2`), lists reviewers present (JII-00697: 1, 6, 7, 8; TMLCN: 2, 3, 4), supports `reviewer` and `query` filters.

### 2.5 Assets: figures, tables, equations, algorithms

**Why images fail today (two independent causes):**
1. Goose drops image content before sending the request: `supports_vision` is false because `qwen3.8-27b` is absent from `custom_skynet.json` (and the provider has no catalog mapping; Goose's bundled catalog lists `qwen3.8-27b` with `input: text,image` for other providers).
2. The skynet backend lacks `mmproj-BF16.gguf` (sysadmin notified), so even delivered images would not be seen.

**MCP design (works with or without vision):**
- `list_assets(kind)` returns ids, labels, captions and pages from the assets index; `get_asset(id)` returns the
  text fields (caption, Markdown table, MathML + linear text, algorithm lines, statement) and `mentions` **always**,
  plus a cropped `ImageContent` (longest side ≤ 1280 px, ≈ 1–2k visual tokens) when requested and vision is on.
  Verified: fastmcp 4.0.3 returns `TextContent` + `ImageContent` from one tool.
- **MathML (decision D7, recommended deterministic):** rebuilt from span geometry — math fonts identify symbols,
  smaller size plus baseline offset gives sub/superscripts, horizontal rules from drawings give fractions, large
  operator glyphs give sums/integrals with limits. Complex layouts (matrices, cases) get `confidence: low`; the linear
  text and crop image are always present. Flat extraction loses structure today (`max R⊂X, |R|=m SR. (2)`).
- `REVIEWER_VISION=auto|on|off` (recipe `envs`); `off` never attaches images. Image budget (≤ 4 per review) stated in the description.
- No PNG files or paths exposed; crops cached in the store.

**Goose/model side (outside the repo):**
- V1 (sysadmin): install `mmproj-BF16.gguf` for `qwen3.8-27b`; verify with one direct chat-completion request containing a small `image_url`.
- V2: declare vision for `qwen3.8-27b` in Goose (`supports_vision` is `unwrap_or_default()` in `goose-providers/src/openai.rs` and only filled from the bundled catalog; custom provider model entries have no such field in 1.50 — test `catalog_provider_id` pointing at a catalog provider listing `qwen3.8-27b`, otherwise request upstream support).
- V3: verify in `~/.local/state/goose/logs/llm_request.*.jsonl` that the tool result says *"…uploaded in the next message"* and the request contains `image_url`.

### 2.6 Guidelines, forms and reports

- **Structured forms** (`forms.py`): parse each component form into fields
  `{id, label, kind: choice|scale|yesno|number|text, options, limit: {value, unit}, verbatim_lines}`; recognise `max N characters|words`, `(N words)`, `[Reply with Yes or No]`, `[A|B|C]`, `Ans:` scales, `1)`/`i)` numbering. Startup/test check: every component yields ≥ 1 field. Fixes F6.
- **Report skeleton**: `get_review_guideline` returns a Markdown skeleton with the mandated sections, the Metadata table (header row included) pre-filled (manuscript, title, venue, venue id, date, submission status from §2.3, reviewer notes) and the verbatim form. Removes the long template from the recipe.
- **Validator** rules on the structured form: every field present and answered; choice/scale values legal; limits in the stated unit; plain-text rules on **all** free-text fields (F13, see decision D3); quality matrix integer 1–5; Metadata `Venue ID` equals resolved venue; `Submission Status` consistent with §2.3 (warning); foreign-venue leaks computed from the other venues' form labels instead of a hard-coded list.
- **Publishing invariant:** only a valid report is ever written to `reports/<stem>_Report.md` (atomic). Invalid submissions are kept as an internal draft with structured errors `{field, rule, message, measured, limit}`. The Makefile `test -f` gate becomes correct without change. Fixes F3.
- `update_report_field` edits one field/matrix cell of the draft and re-validates, so the agent never resends 12k characters or patches files via shell.
- **Reviewer notes:** `papers/<stem>.notes` returned by `get_paper_overview` and placed in the skeleton; recipe merges them with `{{ comments }}`. Fixes F7.

### 2.7 Dependencies and protocol

- `pyproject.toml`: `fastmcp>=4.0.3,<5`, `mcp>=2.2,<3`, `pymupdf>=1.26`, drop `pyyaml` (no longer used: guidelines have no front-matter).
- Delete the protocol monkeypatch in `runner.py` (keep signal handling). Fixes F14.
- Test: stdio handshake against `venv/bin/reviewer-mcp` asserts negotiated `2026-07-28` (already verified manually for reviewer-mcp and all crepe servers).

### 2.8 Tool contract (critical)

**Rules applied to every tool**
1. Description order: *when to use* → *what it returns* → *what not to use it for / which tool instead* → cost/budget.
2. Every parameter: `Annotated[T, Field(description=…, ge/le…)]`; enums via `Literal`; no `str|int` unions; one name per concept (`paper`, `first_page`, `last_page`).
3. Page numbers are **PDF page numbers** everywhere (the overview shows the manuscript range).
4. `ToolAnnotations`: `readOnlyHint=True` for readers; `idempotentHint=True` where true; submit tools `destructiveHint=False`.
5. Typed return models (pydantic/TypedDict) → FastMCP `output_schema`; compact keys; no paths.
6. Errors via `ToolError` with the fix and the next tool, e.g. *"Page 40 is outside this PDF (17 pages; manuscript = pages 4–17). Call read_pages with first_page between 1 and 17."*
7. Contract test: snapshot of `list_tools()`; every parameter has a description; the tool list the model receives (names, descriptions, parameter schemas) fits ≤ 9,200 characters (~2.5k tokens).

**Tools (11, replacing the current 12):**

| # | Tool | Replaces |
| :--- | :--- | :--- |
| 1 | `get_paper_overview` | `inspect_paper`, `analyze_bundle`, `split_bundle`, `inspect_paper_scratch` |
| 2 | `set_manuscript_pages` | manual `boundary_line` |
| 3 | `read_pages` | `read_paper_page`, page/line modes of `read_paper_section` |
| 4 | `read_section` | named mode of `read_paper_section` |
| 5 | `search_paper` | shell `grep/head/tail` |
| 6 | `get_author_responses` | `get_revision_responses` |
| 7 | `list_assets` | — (numbered figures, tables, equations, algorithms, listings, theorems, footnotes, references) |
| 8 | `get_asset` | `render_paper_figures` + Goose `read_image` |
| 9 | `get_review_guideline` | `get_review_guideline`, `get_form_template` |
| 10 | `submit_report` | `save_review_report`, `validate_review_report` |
| 11 | `update_report_field` | shell patching |

**Draft descriptions**

```python
Paper = Annotated[str, Field(description=
    "PDF file name in papers/, exactly as given in the task (e.g. 'Access-2026-41373_Proof_hi.pdf'). "
    "Use the same value in every call.")]

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def get_paper_overview(paper: Paper) -> Overview:
    """START HERE — call once at the beginning of the review.
    Opens the PDF (text extraction and caching are automatic) and returns what you need to plan the review:
    title, authors, PDF page count, venue resolved from metadata (status/venue_id/evidence), the parts of the
    submission with PDF page ranges (cover, manuscript, author responses, extra manuscript copies), whether this is
    a revision and why, reviewer notes, the manuscript outline (headings with pages) and asset counts per kind
    (list them with list_assets). If venue.status is not 'resolved', stop: no review may be produced.
    Call again only after set_manuscript_pages."""

@mcp.tool()
def set_manuscript_pages(
    paper: Paper,
    first_page: Annotated[int, Field(ge=1, description="First PDF page of the manuscript under review.")],
    last_page: Annotated[int, Field(ge=1, description="Last PDF page of the manuscript, including references.")],
    reason: Annotated[str, Field(max_length=300, description="Why the detected range was wrong (cite the evidence).")],
) -> Overview:
    """Correct the manuscript page range ONLY when get_paper_overview picked the wrong part
    (e.g. the marked-up copy instead of the clean one). All reading tools then use the new range.
    The correction and reason are returned in the overview; report them under 'Extraction Summary & Limitations'."""

Part = Annotated[Literal["manuscript", "responses", "cover", "all"], Field(description=
    "Which part to read: 'manuscript' = the paper under review (default); 'responses' = the authors' response "
    "letter (revisions only); 'cover' = submission-system cover pages; 'all' = every PDF page.")]

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def read_pages(
    paper: Paper,
    first_page: Annotated[int, Field(ge=1, description="First PDF page to read (see get_paper_overview for ranges).")] = 0,
    last_page: Annotated[int | None, Field(ge=1, description="Last PDF page to read, inclusive. Omit to read one page.")] = None,
    part: Part = "manuscript",
    cursor: Annotated[str | None, Field(description="The 'next' value from a previous read_pages reply. When set, first_page/last_page are ignored.")] = None,
) -> PagesText:
    """Read manuscript text page by page — the primary reading tool.
    Returns whole pages, about 12,000 characters per call. If the range does not fit, the reply stops at a page
    boundary and 'next' tells you exactly where to continue; nothing is ever skipped, so never re-read returned pages.
    To locate a topic use search_paper; to read one named section use read_section."""

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def read_section(
    paper: Paper,
    heading: Annotated[str, Field(min_length=2, description="Section heading as in the outline, e.g. 'Introduction', 'IV. Experiments', 'Conclusion'. Numbering and case are ignored.")],
) -> SectionText:
    """Read one manuscript section by heading, up to the next heading of the same or higher level.
    Matches outline headings only (never body text). If no heading matches, the reply lists the available headings.
    Long sections return 'next' for read_pages."""

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def search_paper(
    paper: Paper,
    query: Annotated[str, Field(min_length=2, max_length=120, description="Literal text to find (case-insensitive): a term, dataset, baseline, 'Table 3', a number.")],
    part: Part = "manuscript",
    max_hits: Annotated[int, Field(ge=1, le=40, description="Maximum snippets to return.")] = 15,
) -> SearchHits:
    """Find where something is mentioned. Returns the PDF page and a short snippet per hit plus the total hit count.
    Use read_pages on a returned page to read the full context."""

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def get_author_responses(
    paper: Paper,
    reviewer: Annotated[int | None, Field(ge=1, description="Reviewer number as it appears in the letter (see 'reviewers' in the reply without filters).")] = None,
    query: Annotated[str | None, Field(max_length=120, description="Return only comment/answer pairs containing this text.")] = None,
) -> Responses:
    """Revisions only: read the authors' answers to previous reviews.
    Without filters returns the reviewers present (e.g. [1, 6, 7, 8]) and the letter opening.
    Verify every claimed change in the manuscript with search_paper / read_pages; do not trust the letter alone."""

AssetKind = Literal["figure", "table", "equation", "algorithm", "listing", "theorem", "footnote", "reference"]

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def list_assets(
    paper: Paper,
    kind: Annotated[AssetKind | None, Field(description="Only this kind of numbered item; omit to list every kind.")] = None,
) -> AssetList:
    """List the numbered items of the manuscript: id, printed label, caption or first words, PDF page and how often
    the text cites it. Use it to choose which figures, tables, equations or algorithms to inspect with get_asset.
    Items never cited in the text are flagged."""

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def get_asset(
    paper: Paper,
    asset: Annotated[str, Field(pattern=r"^[a-z]+:[A-Za-z0-9.]+$", description="Asset id from list_assets, e.g. 'figure:3', 'table:II', 'equation:5', 'algorithm:1', 'reference:12'.")],
    include_image: Annotated[bool, Field(description="Attach the cropped image (figures, tables, equations, algorithms) when the model supports images. Budget: at most 4 images per review.")] = False,
) -> list:  # TextContent (+ ImageContent)
    """Inspect one numbered item to verify it against the claims in the text.
    Always returns its caption and content as text — table cells as Markdown, equations as MathML plus linear text,
    algorithm lines, theorem statements, reference entries — and the pages/paragraphs that cite it.
    Check axes, units and that numbers quoted in the text match the table or figure."""

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def get_review_guideline(
    paper: Paper,
    venue: Annotated[str | None, Field(pattern=r"^[a-z0-9_-]{2,64}$", description="Venue id; omit to use the venue resolved from the paper metadata. Pass it only when the task states it explicitly.")] = None,
    form_only: Annotated[bool, Field(description="true = return only the form fields and the report skeleton (call again right before drafting).")] = False,
) -> Guideline:
    """Load the review criteria for this paper's venue: review philosophy and audit checkpoints, the venue form as
    structured fields (label, type, options, length limit and unit) and a report skeleton with all mandated sections
    and the metadata table pre-filled. If status is not 'resolved', stop: never review against another venue's form."""

@mcp.tool(annotations={"destructiveHint": False})
def submit_report(
    paper: Paper,
    report: Annotated[str, Field(min_length=200, description="The complete review report in Markdown, following the skeleton from get_review_guideline.")],
    dry_run: Annotated[bool, Field(description="true = validate only, never publish.")] = False,
) -> Submission:
    """Validate the complete report and publish it to reports/ only if it passes.
    On failure nothing is published: the draft is kept and the reply lists each problem (field, rule, measured vs allowed).
    Fix a few fields with update_report_field; resubmit the whole report only for structural problems.
    The review is finished when this returns published=true."""

@mcp.tool(annotations={"destructiveHint": False})
def update_report_field(
    paper: Paper,
    field: Annotated[str, Field(description="Form field label exactly as in the form (e.g. 'Comments to the Author', 'Question 3'), or 'Quality Matrix: <criterion>'.")],
    answer: Annotated[str, Field(min_length=1, description="The new answer text (or score 1-5 for a matrix criterion).")],
) -> Submission:
    """Replace one answer in the last submitted draft, re-validate, and publish if the whole report now passes.
    Use it to fix length limits or single fields instead of resending the entire report."""
```

**Server instructions** (sent at initialize, ~8 lines): workflow order
`get_paper_overview → get_review_guideline → read_pages/read_section/search_paper (+ get_author_responses for revisions) → list_assets → get_asset (figures, tables, equations, algorithms carrying the main claims; ≤ 4 images) → crepe-research checks → get_review_guideline(form_only) → submit_report → update_report_field until published`.

### 2.9 Recipe (streamlined)

```yaml
version: 1.1.0
title: Academic Paper Reviewer
parameters:
  - {key: paper,    input_type: string, requirement: required, description: "PDF file name in papers/"}
  - {key: venue,    input_type: string, requirement: optional, default: "", description: "Venue id; empty = resolve from metadata"}
  - {key: comments, input_type: string, requirement: optional, default: "", description: "Extra reviewer directives"}
instructions: |
  You are a senior peer reviewer. Review exactly one paper: "{{ paper }}". Verify before asserting; never invent.
  1. get_paper_overview. If venue.status is not "resolved": reply
     "SKIPPED: {{ paper }} — venue unresolved" and stop.
  2. get_review_guideline(venue="{{ venue }}" if given). Follow its philosophy and checkpoints.
     Directives: reviewer notes from the overview plus "{{ comments }}" are priority audit items.
  3. Read the whole manuscript with read_pages following 'next'; use search_paper/read_section to cross-check claims.
     For revisions, check each author response against the manuscript.
  4. list_assets, then get_asset for the figures, tables, equations and algorithms that carry the main claims
     (include_image only for up to 4 figures/tables).
  5. 2–4 external checks with crepe-research (academic_search, arxiv_search; web_search as fallback);
     rate limits go under limitations.
  6. get_review_guideline(form_only=true), fill the skeleton, submit_report; fix errors with update_report_field
     until published=true. Then stop.
extensions:
  - type: stdio
    name: reviewer-mcp
    cmd: /home/mantunes/git/reviewer-mcp/venv/bin/reviewer-mcp
    timeout: 300
    envs: {REVIEWER_WORKSPACE: /home/mantunes/Nextcloud/prompts, REVIEWER_VISION: auto}
  - type: stdio
    name: crepe-research
    cmd: /home/mantunes/git/crepe-mcp/venv/bin/crepe-research
    timeout: 300
    env_keys: [CREPE_TAVILY_API_KEY, CREPE_SEMANTIC_SCHOLAR_API_KEY]
    envs: {CREPE_HEADLESS_BROWSER_PATH: /usr/bin/chromium}
settings: {goose_provider: custom_skynet, goose_model: qwen3.8-27b, goose_mode: auto, temperature: 0.1}
```
- `developer` extension removed (no shell or file writes needed; figures and tables come from `get_asset`).
- `REVIEWER_WORKSPACE` via `envs` instead of relying on cwd (use `$(CURDIR)`-independent absolute path, or make it a recipe parameter if several workspaces exist).
- `base_review.md`: remove "the recipe defines extraction/rendering" references; single source for search counts (2–4); align plain-text rules with decision D3.

### 2.10 Makefile — done 2026-09-10

- Orchestrator only: `all`/`review` (one Goose run per paper without an up-to-date report), `test` (recipe schema +
  reviewer-mcp suite with `REVIEWER_WORKSPACE=$(CURDIR)`), `clean` (reports and scratch).
- No guideline build: the `test -f` gate is correct once only valid reports are published (§2.6).

---

## 3. Phased implementation

Each phase ends green on `ruff`, `basedpyright`, `vulture`, `pytest`, and leaves the pipeline runnable.

### Phase 0 — Safety net (fixtures, isolation) — done 2026-09-10
- Implemented: `tests/pdf_fixtures.py` (builder, 5 fixtures with `FixtureSpec` expectations, minimal workspace, `IsolatedTestCase`), `tests/test_fixtures.py` (7 sanity checks); scratch base read from `REVIEWER_SCRATCH_BASE` at call time; server tests isolated; stray test reports removed.
- Synthetic PDF builders in `tests/fixtures.py` (PyMuPDF, generated at test time; no binary PDFs committed), each mirroring a verified layout from §2.3:
  `ieee_single` ← Access (3 ScholarOne cover pages, 14-page two-column manuscript, empty Info dict, `Initial Submission`);
  `em_long_review` ← JII-00489 (EM cover, short items incl. `Letter`, responses with own references, manuscript item labelled "Response to reviewers", table headers reading "References", long reference run);
  `em_revision` ← JII-00697 (EM cover, `Revised manuscript without author details (unmarked)`, responses, trailing blank page);
  `scholarone_two_copies` ← TMLCN (cover with `For consideration in …` + `Page x of N`, clean copy, highlighted copy with coloured spans, responses to reviewers 2–4);
  `scanned_page` (image-only page).
- Test isolation: `tmp_path` workspace + `REVIEWER_SCRATCH_BASE` per test; remove cwd writes; delete stray `prompts/reports/test_paper_Report.md`.
- Real-PDF test on `prompts/papers/Access-2026-41373_Proof_hi.pdf`, skipped when the file is absent (CI); asserts only structure/venue/figure-index facts, never paper text.
- **Done when:** all current behaviour covered by tests that pass, nothing written outside `tmp_path`.

### Phase 1 — Tool contract (F9) — done 2026-09-11
- The 11 tools of §2.8 are built directly on the paper store (`server.py` with `papers.py`, `reading.py`,
  `responses.py`, `reports.py`, `crops.py`). The old tools and modules (`bundle.py`, `pdf.py`, `renderer.py`,
  `scratch.py`) and the protocol patch in `runner.py` are removed. Parameters carry `Annotated`/`Field` descriptions
  and bounds, parts and kinds are `Literal`s, tools carry annotations, and problems the agent can fix are `ToolError`s
  whose message names the fix.
- Deviations from the §2.8 draft: replies are dictionaries (no pydantic output models yet); `read_pages` reads to the
  end of the part when `last_page` is omitted (fewer calls); `list_assets` omits references unless
  `kind='reference'`; `theorem` and `footnote` kinds are not advertised until they exist; `submit_report` publishes
  only for the venue whose guideline `get_review_guideline` returned, so a report cannot choose its own venue.
- Protocol: mcp 2.2 negotiates 2026-07-28 through `server/discover` (modern era) and keeps `initialize` for
  handshake-era clients (≤ 2025-11-25); the runner patch was never needed.
- Contract tests (`tests/test_server.py`): tool set, every parameter described, description budget ≤ 10,000
  characters, read-only annotations, stdio negotiation of 2026-07-28 (auto) and 2025-11-25 (legacy).
- Dependencies pinned: `fastmcp>=4.0.3,<5`, `mcp>=2.2,<3`, `pymupdf>=1.26`; `pyyaml` dropped.
- Smoke run on the real Access proof: overview 1.9k characters; the whole manuscript in 7 `read_pages` calls
  (68k characters, nothing skipped); tables as Markdown with an optional crop; TDSC responses list reviewers 1–3.
- **Pending:** the user's approval of the tool snapshot.

### Phase 2 — Paper store and document indexes (F5, F16, F17)
- Sub-milestones: **2a** store + pages/lines (regions, proof line numbers, columns, reading order); **2b** paragraphs,
  sections, FTS5 search; **2c** assets, references, mentions.
- Status: 2a done (store, regions, line numbers, reading order); 2b done (paragraphs with indent/gap/size/caption
  rules and hyphen repair; section tree from styled numbered or standard headings; FTS5 phrase search whose last
  word is a prefix). Real Access outline: 6 `I.`-level, 9 `A.`-level, 5 `1)`-level and 2 unnumbered headings,
  all on manuscript pages 4–16, with cover sheets, author line, biographies and math lines rejected.
- 2c done: assets and mentions for figures, tables, equations, algorithms, listings and references (extractor
  version 3). Captions need small type (body sentences such as 'Table 5 compares…' are not captions); regions are
  the nearest image, drawing cluster or `find_tables` table above or below the caption in the same column; tables
  are stored as Markdown; equations come from right-edge `(n)` lines; algorithms from rules around the label;
  references from `[k]` entries joined across hanging indents. Real Access: 8 figures, 7 tables, 6 equations,
  2 algorithms, 20 references; a caption whose region is not found is stored with `confidence: low`.
- Item kinds and numbering variants absent from the example paper (theorems, footnotes, listings, quotes, vector-only
  figures, unruled tables, section/appendix numbering, author–year references, …) are tracked for assessment in
  `TODO.md` → *Extraction*.
- Derived heuristics (extractor version 12, 2026-09-11): no absolute points or page fractions. Tolerances are
  factors of the measured body size / line height in `config.json` (`REVIEWER_CONFIG` overrides; digest in the cache
  key). Running heads repeat on a chain of ≥ `running_min_pages` pages; columns are decided by characters, with
  same-size page majority for first pages whose abstract spans both columns; headings must be alone on their row,
  set apart from body text, and belong to the document's own numbering runs (no caption-size threshold);
  manuscripts start only on pages typeset in the body font; responses need a comment line with a reply or reviewer
  line. Validated on 8 real PDFs (IEEE Access ×3, IoT-J, TDSC, TPDS, Neural Networks, a conference paper) and the
  fixtures at 8/10/12 pt on A4/Letter; open cases and calibration debt are in `TODO.md`.
- Pages without a text layer are detected (`source: none`, images present) and reported; OCR is out of scope
  (not requested: it would feed recognised, possibly wrong text to the review).
- `store.py` (fingerprint, cache key, lazy per-index loading), `document.py` (single extraction pass, pages without a text layer detected),
  `indexes.py` (pages, lines, paragraphs, sections, margins, references), `assets.py` (detection, kind-specific text,
  mentions); `profile.py` reuses the margins index.
- Tests: Access index snapshot (canonical dump of `paper.sqlite` tables) identical across rebuilds; Access counts (8 figures, 7 tables, 2 algorithms, 6
  equations; 3 margin stamps); fixtures cover every asset kind and a page without a text layer; replaced PDF with the same name
  re-extracts; same name in two directories isolated; `EXTRACTOR_VERSION` bump rebuilds; no path in any tool reply.

### Phase 3 — Venue index & metadata resolution (F1, F2) — done 2026-09-10
- See §2.2. Remaining: fill identifier patterns and platform stamps for the listed gaps. The overview carries the
  venue resolution since Phase 1.

### Phase 4 — Structure & revision (F11, F12) — done 2026-09-10 (before Phase 1)
- Implemented in `structure.py` and the store (extractor version 4): parts from cover fields, item labels (content wins),
  Abstract/Keywords or Introduction starts, response headings or reviewer lines, salutations and trailing blank pages;
  current copy from the only copy, an 'unmarked' label or the least mark-up (coloured text + highlight/underline/
  squiggly/strike-out annotations); round from response parts, copies, revised-manuscript labels, R<n> markers in the
  file name or cover fields, and 'Initial Submission'. Assets and citations are now kept per part, and an Abstract
  heading re-opens the outline after an earlier reference list. Manual override: `set_manuscript_pages` (store state).
- Real-data calibration: 'Corresponding author' is a manuscript footnote in IEEE papers, not a cover field; cover
  forms print label and value side by side on one row.
- Results: all five fixtures yield their specified parts, round and current copy; Access-2026-41373 → cover 1–3,
  manuscript 4–17, first submission (high).
- `structure.py`: page features, segmentation, classification, current-copy choice, revision decision with evidence; `set_manuscript_pages` override persisted in the manifest.
- Tests: the four layout fixtures + the real Access PDF.
- **Done when:** Access (real) yields cover 1–3 / manuscript 4–17 / first submission, and the three bundle fixtures yield the §2.3 segments, round and current-copy choice.

### Phase 5 — Reading, outline, search, responses (F4, F10) — done 2026-09-11 (with Phase 1)
- `read_pages` (whole pages, `p<page>@<offset>` cursor only for a page larger than the budget), `read_section`
  (outline headings, case and numbering ignored), `search_paper` (FTS5 within the part), `get_author_responses`
  (reviewer headings, comment/answer items, reviewer and query filters).
- Tests: every page returned once across cursors, headings on IEEE and Elsevier layouts, search within the part,
  reviewers 1, 6, 7, 8 on the EM fixture with reviewer and query filters, first submissions rejected.

### Phase 6 — Assets: figures, tables, equations (F8) — partly done 2026-09-11
- Done: `list_assets` / `get_asset` with caption, content (Markdown tables, equation text, algorithm lines, reference
  entries) and citing sentences always; crops ≤ 1280 px on request, at most 4 per review, `REVIEWER_VISION=off`
  disables them.
- Pending: deterministic MathML builder (D7); unruled (booktabs) tables; Goose/model steps V1–V3 (§2.5) once
  `mmproj-BF16.gguf` is installed.
- Tests: table content and citations, image attached then budget exhausted, vision off; pending MathML cases
  (sub/superscripts, fraction, sum with limits).

### Phase 7 — Forms, validator, publishing (F3, F6, F7, F13) — partly done 2026-09-11
- Done: `reports.py` skeleton (Metadata table pre-filled with manuscript, title, venue, venue id, date, submission
  status and reviewer notes; Quality Matrix rows of `base_review.md`; verbatim form; `<to fill: …>` placeholders that
  block publishing); `submit_report` keeps the draft and publishes `reports/<stem>_Report.md` atomically only when
  valid (F3); `update_report_field` replaces a form answer, an `Ans:` line or a matrix score and re-validates; reviewer
  notes from `papers/<stem>.notes` in the overview and the skeleton (F7).
- Dropped (2026-09-11): length limits (F6). Forms state answer sizes in paragraphs; the validator measures nothing.
- Done (2026-09-11): plain text on everything the agent writes (F13, D3): prose sections, Quality Matrix cells and
  form answers, skipping the form lines reproduced verbatim. One allow-list regex (`validator.PLAIN_TEXT_RE`): letters
  and digits of any script, punctuation, math signs, `_` inside a word, a lone `<`, MathML tags and line breaks, with
  no line opening a list item, a numbered item or a heading; anything else (bold, italic, code, tables, LaTeX, HTML,
  emoji) is an error quoting the text around the first offending character.
- Done (2026-09-18): a field takes one choice (`choose`, `choose any`, `scale`) or `text`, and a choice may carry a
  `text` size for the explanation after it, with `explain` naming the options that must carry one (`explain: No`,
  `explain: always`; a name may leave out an aside a web form prints after an option). Naming an option that does not
  exist, `explain` without a `text` size and `explain` on a text field are form errors. `ieee_oj-coms.md` had been
  rejected whole by the old one-kind-per-field rule, which dropped its venue from the index and made
  OJCOMS-07163-2026 unreviewable; it is the only form of the 23 with combined fields, and the five other choice
  fields whose `help` mentions explaining all send the explanation to a separate field, so they stay as they are.
- Pending: `forms.py` structured fields for all venues; choice/scale values and form-derived foreign labels.
- Pending (D8): whether rating fields should use `explain: always`, measured over several venues rather than one.
- Tests: an unfilled skeleton and an invalid score are not published; field updates publish; a report stating another
  venue is refused; pending fault injection per rule for every venue.

### Phase 8 — Recipe, Makefile, docs (F15, F18) — partly done 2026-09-11
- Token reduction (2026-09-11), measured on Access-2026-41373 and TDSC-2025-09-1631.R1: tool list 11.7k → 9.1k
  characters; server instructions list what each tool does, not the workflow (the recipe is the loop);
  `read_pages`, `read_section` and `get_author_responses` reply in plain text under a status line (no JSON escaping);
  manuscript reading leaves out the reference list entries, which `list_assets(kind='reference')` already returns
  (reading 68k → 62k and 116k → 103k characters); the guideline reply no longer repeats the venue summary nor the form,
  which the skeleton carries (10.3k → 6.4k characters); `base_review.md` keeps philosophy, checkpoints and report rules
  and drops the workflow and length rules.
- Makefile is a pure orchestrator (missing report → one Goose run); every review decision is the agent's. The recipe
  omits empty `venue`/`comments` text with Jinja conditionals.
- Done: recipe rewritten for the 11 tools (developer extension removed; `REVIEWER_WORKSPACE` and `REVIEWER_VISION`
  in `envs`; `goose recipe validate` passes); `base_review.md` no longer refers to recipe-side extraction, rendering
  or shell counting; `reviewer-mcp/README.md` lists the new tools.
- Pending: rewrite `prompts/README.md` for the MCP pipeline; replace the TODO Phase 3 model matrix with `qwen3.8-27b`
  (primary) and the other skynet models as secondary.

### Phase 9 — Evaluation on qwen3.8-27b
Full review runs use the only real paper, `Access-2026-41373_Proof_hi.pdf` (first submission). Revision flows
(responses, two copies, `set_manuscript_pages`) are exercised end-to-end with a short Goose run on the
`scholarone_two_copies` and `em_revision` fixtures written to a temporary workspace (mechanics only: segment choice,
`get_author_responses`, publishing), and on real bundles when they become available. Metrics come from
`~/.local/state/goose/logs/llm_request.*.jsonl`:

| Metric | Baseline (Access: run 1 / run 2 after the venue fix) | Target |
| :--- | :--- | :--- |
| Tool calls | 28 / 31 | ≤ 22 |
| Tool errors | 2 / 0 | 0 |
| Shell calls | 3 / 4 | 0 (extension removed) |
| Overlapping/repeated page reads | 3 | 0 |
| Figures seen | 0 | caption+table always; images once V1–V3 done |
| Submits until published | 1 save + manual patch | ≤ 2 (`submit_report` + ≤ 1 `update_report_field` round) |
| Invalid file ever in `reports/` | yes | never |
| Venue / segments / round correct | venue by luck / by metadata (high); segments not detected | Access real + 3 bundle fixtures: 4/4 |
| Wall time | 3 m 34 s / 3 m 18 s | ≤ 5 min per 20-page paper |

Iterate on descriptions (not recipe prose) when a metric misses.

---

## 4. Decisions needed

| ID | Question | Recommendation |
| :--- | :--- | :--- |
| D1 | What counts as submission metadata? | **Decided:** everything that identifies the submission except manuscript prose — file name/size/date/hash, PDF metadata/XMP, repeated headers/footers, labelled cover fields, DOIs in those places (§2.2). |
| D2 | Where does venue identification data live? | **Decided and implemented:** each component's `VENUE:` block; the MCP validates components and composes guidelines lazily (no registry, no compiled files). |
| D3 | Are numbered paragraphs (`1.`) allowed in long free-text fields? | **Decided 2026-09-11:** no. Everything the agent writes is plain text with MathML as the only markup: no lists, numbered lines, bold, italic, headings, code, tables, emoji or LaTeX. |
| D4 | Where to declare vision for `qwen3.8-27b` in Goose (user config, outside repos). | Add the model entry with `supports_vision: true` to `custom_skynet.json`, verify via llm_request logs (V3). |
| D5 | "crepe-academic" | **Resolved:** typo; the recipe uses `crepe-research`. |
| D6 | Only Access-2026-41373 existed as a real PDF; bundle behaviour relied on synthetic fixtures. | **Resolved 2026-09-11:** the corpus has 8 real PDFs (IEEE Access ×3, IoT-J, TDSC revision with two copies and responses, TPDS, Neural Networks, MDPI); their structure facts and caption counts are in `tests/test_corpus.py`, and synthetic fixtures cover the layouts not in the corpus. |
| D8 | Should a rating field require its reasoning (`explain: always`) even where the web form asks for it only after the negative option? | **Open (2026-09-18).** A choice may carry a `text` size, and `explain` names the options that must use it (`explain: No`, `explain: always`). Measured on two OJCOMS runs of the same commit: with the explanation required only after the negative option, the report lost the two findings that had justified the ratings — the omitted references `arXiv:2504.13589` and `arXiv:2403.02238`, found by the agent's own searches, and the uncited Figures 6 and 9 and Tables 1 and 2. Answers shrank 563 → 65 and 613 → 35 characters and the report 10,396 → 8,617; the recommendation (`Reject-Resubmission Allowed`) and its core argument were unchanged in both. So the conditional form matches the web form but costs supporting evidence, while `explain: always` buys it back at the price of prose after every rating, including an uncontroversial `Yes`. Decide against a few venues, not one: it is a per-field choice in `forms/`, no code change. |
| D7 | Equations: deterministic MathML from span geometry, or a formula-OCR model? | Deterministic (no ML, reproducible, independent of model capability); linear text and crop image always stored; `confidence: low` for matrices/cases. |

## 5. Code removed at the end

`VENUE_PREFIX_MAP`, `tokens()`, overlap scoring and substring matching (`guidelines.py`); line-based `cut_bundle` API and `manifest.txt` (`bundle.py`); body-text revision regex (`pdf.py`); `inspect_paper_scratch`, `validate_review_report`, `get_form_template`, `read_paper_section` line mode (`server.py`); protocol patch (`runner.py`); `cleanup_scratch` public helper; hard-coded `FOREIGN_MARKERS`.
