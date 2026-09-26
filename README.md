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
5. `list_assets` — numbered items with pages and citation counts.
6. `get_asset` — one item as text (caption, Markdown table, equation text, algorithm lines, reference) plus citing
   sentences, optionally a cropped image when the `images` settings of `config.json` enable it (off by default); at
   most `replies.asset_budget` (6) items per overview, each once.

Page reads and search now cover the whole PDF by default; section reads use the complete extracted outline.
Asset/image budgets still apply; unambiguous asset IDs and explicit visual questions remain future work (MCP-06 onward).

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
absence. Text reads/search invoke no model. OCR, visual questions, asset quota removal and catalog/rendering
improvements remain outside these implemented text tools. External Agents SDK verification is deferred.

## Environment

* `PDF_INGESTION_PDF` — the PDF bound to the server process; required, must exist as a usable PDF (relative paths
  are resolved against the startup working directory, spaces preserved).
* `PDF_INGESTION_RUN_DIR` — isolated run directory for derived data; required, may not exist yet (persistence creates
  it on demand) and must not point to an existing file.
* `REVIEWER_CONFIG` — JSON file overriding values of `config.json`: layout factors (`heuristics`), image
  attachments (`images`: `enabled`, `budget`, `max_side`) and reply budgets (`replies`: `asset_budget`). A new
  `get_paper_overview` restores the remaining asset/image budgets; text reads have no consumption budget.
* `REVIEWER_SCRATCH_BASE` — legacy store base (default `/tmp/reviewer`) used only when a store is opened without an
  explicit run directory (internal extractor tests); the server always uses its bound run directory.

## Development

Install dev tools and pre-commit hooks:

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

Real-paper checks run when `REVIEWER_WORKSPACE` points at a workspace with the validation papers.
