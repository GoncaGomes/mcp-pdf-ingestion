# reviewer-mcp

An MCP (Model Context Protocol) server that serves one academic paper PDF as evidence: it reads the PDF
deterministically and exposes it through six neutral tools — document overview, page and section reads, search, and
numbered-item listing and retrieval. It does not select content, synthesise conclusions or validate scientific claims;
the consuming agent decides what to read and how to use it.

## Key Features

* **Deterministic paper store**: one PyMuPDF pass per PDF into a SQLite store in `$REVIEWER_SCRATCH_BASE` (default
  `/tmp/reviewer`), keyed by the PDF content. Pages, lines, paragraphs, sections, full-text search, submission parts and
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
* **No files exposed**: tools take the PDF file name and PDF page numbers; no scratch paths in any reply.
* **MCP protocol `2026-07-28`**, negotiated natively by fastmcp 4.

## Tools (6)

1. `get_paper_overview` — start here: document identity, page count, extracted title when one is found, the full-PDF
   outline with section ids, numbered-item counts and extraction warnings.
2. `read_pages` — whole pages with a continuation cursor (primary reader); pages already returned since the last
   `get_paper_overview` are not sent again.
3. `read_section` — one outline section by heading.
4. `search_paper` — where a term is mentioned (page, section, snippet).
5. `list_assets` — numbered items with pages and citation counts.
6. `get_asset` — one item as text (caption, Markdown table, equation text, algorithm lines, reference) plus citing
   sentences, optionally a cropped image when the `images` settings of `config.json` enable it (off by default); at
   most `replies.asset_budget` (6) items per overview, each once.

This is the current behaviour. The readers still default to the detected manuscript part, and the asset/image budgets
still apply. Binding one configured PDF and run directory per server, whole-PDF reads by default, unambiguous asset
ids and explicit visual questions in `get_asset` come in the later tasks of `PLAN.md` (MCP-02 onward); the intermediate
states are described there, not assumed here.

## Environment

* `REVIEWER_WORKSPACE` — directory with `papers/` (default: cwd).
* `REVIEWER_SCRATCH_BASE` — store location (default `/tmp/reviewer`).
* `REVIEWER_CONFIG` — JSON file overriding values of `config.json`: layout factors (`heuristics`), image
  attachments (`images`: `enabled`, `budget`, `max_side`) and reply budgets (`replies`: `asset_budget`). A new
  `get_paper_overview` starts a new reading session and restores every budget.

## Development

Install dev tools and pre-commit hooks:

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

Real-paper checks run when `REVIEWER_WORKSPACE` points at a workspace with the validation papers.
