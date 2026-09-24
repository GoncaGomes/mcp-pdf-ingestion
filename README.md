# reviewer-mcp

An MCP (Model Context Protocol) server that lets an AI agent review one academic paper submission: it reads the PDF
deterministically, exposes the manuscript through page, section, search and numbered-item tools, loads the venue
guideline, and publishes a review report only when it passes validation.

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
* **Submission structure**: cover pages, manuscript copies, letters and author responses; the copy under review and
  the review round, each with evidence.
* **Venue from metadata only**: file name, PDF metadata, running heads/footers, labelled cover fields and DOIs; the
  guideline is composed on demand from `base_review.md` and `forms/`. A form field takes one choice (`choose`,
  `choose any`, `scale`) or `text`, and a choice may carry a `text` size for the explanation after it, with `explain`
  naming the options that must carry one (`explain: No`, `explain: always`).
* **Valid reports only**: `submit_report` validates against the venue form and publishes `reports/<stem>_Report.md`
  only when the report passes; `update_report_field` fixes single fields of the draft.
* **No files exposed**: tools take the PDF file name and PDF page numbers; no scratch paths in any reply.
* **MCP protocol `2026-07-28`**, negotiated natively by fastmcp 4.

## Tools (11)

1. `get_paper_overview` — start here: parts, manuscript pages, round, outline, numbered items, venue.
2. `set_manuscript_pages` — correct the manuscript range when the wrong copy was chosen.
3. `read_pages` — whole pages with a continuation cursor (primary reader); pages already returned in the review are
   not sent again.
4. `read_section` — one outline section by heading.
5. `search_paper` — where a term is mentioned (page, section, snippet).
6. `get_author_responses` — reviewers and comment/answer items of the response letter (revisions); each paragraph
   once per review, so repeating a filter continues a truncated reply.
7. `list_assets` — numbered items with pages and citation counts.
8. `get_asset` — one item as text (caption, Markdown table, equation text, algorithm lines, reference) plus citing
   sentences, optionally a cropped image when the `images` settings of `config.json` enable it (off by default); at
   most `replies.asset_budget` (6) items per review, each once.
9. `get_review_guideline` — review criteria, or the report skeleton with the verbatim venue form (`form_only`).
10. `submit_report` — validate and publish only a valid report.
11. `update_report_field` — replace one answer or matrix score in the draft and re-validate.

## Environment

* `REVIEWER_WORKSPACE` — directory with `papers/`, `forms/`, `base_review.md` and `reports/` (default: cwd).
* `REVIEWER_SCRATCH_BASE` — store location (default `/tmp/reviewer`).
* `REVIEWER_CONFIG` — JSON file overriding values of `config.json`: layout factors (`heuristics`), image
  attachments (`images`: `enabled`, `budget`, `max_side`) and reply budgets (`replies`: `asset_budget`). A new
  `get_paper_overview` starts a new review and restores every budget.

## Development

Install dev tools and pre-commit hooks:

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

Real-paper checks run when `REVIEWER_WORKSPACE` points at a workspace with the validation papers.
