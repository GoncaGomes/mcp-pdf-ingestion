# reviewer-mcp: History and Evaluation

Milestones of `reviewer-mcp`, its Goose recipe and the `~/Nextcloud/prompts` workspace, and every end-to-end
evaluation run, so that each change can be measured against the runs before it. `TODO.md` holds what is still open.

---

## 1. Evaluation Runs

One row per `make` run of one paper (`goose run --recipe reviewer`, model `qwen3.8-27b` on `custom_skynet`,
`--max-turns 64`). Targets from PLAN §2.5: at most 22 tool calls, no tool errors, at most 5 minutes for a 20-page
paper, at most 2 report submissions, never an invalid report in `reports/`.

| Date | Commit | Paper | Result | Tool calls (MCP + research) | Errors | Wall time | Largest input (tokens) | Submits | Report (chars) |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-09-10 | old pipeline | Access-2026-41373 | published after a manual patch | 28 | 2 | 3 m 34 s | — | 1 + patch | — |
| 2026-09-11 | `c410d33` | Access-2026-40102 | published, valid | 37 (29 + 8) | 0 | 9 m 55 s | 75,759 | 1 | 13,121 |
| 2026-09-12 | `9678328` | Access-2026-40102 | published, valid | 29 (24 + 5) | 0 | 4 m 11 s | 71,606 | 1 | 9,168 |
| 2026-09-12 | `9678328` | Access-2026-40875 | published, valid | 25 (19 + 6) | 0 | 5 m 42 s | 73,123 | 2 + 4 updates | 9,358 |
| 2026-09-12 | `9678328` | Access-2026-41373 | published, valid | 40 (32 + 8) | 0 | 8 m 30 s | 68,629 | 2 + 4 updates | 9,622 |
| 2026-09-12 | `9678328` | IoT-70548-2026 | SKIPPED (no component) | 1 | 0 | 3 m 43 s | 5,629 | 0 | — |
| 2026-09-12 | `9678328` | NEUNET-D-26-04237 | SKIPPED (no component) | 1 | 0 | 3 m 52 s | 5,617 | 0 | — |
| 2026-09-12 | `9678328` | TDSC-2025-09-1631.R1 | published, valid | 36 (30 + 6) | 0 | 84 m 29 s | 110,774 | 1 + 1 update | 9,964 |
| 2026-09-12 | `9678328` | TPDS-2026-08-0833 | SKIPPED (no component) | 1 | 0 | 5 m 16 s | 6,359 | 0 | — |
| 2026-09-12 | `9678328` | oral-4560066 | failed: turn limit reached | 119 (24 + 95) | 0 | 18 m 44 s | 70,652 | 0 | — |
| 2026-09-12 | `decc4ca` | Access-2026-40102 | published, valid | 23 (15 + 8) | 0 | 9 m 38 s | 62,354 | 1 | 7,256 |
| 2026-09-12 | `decc4ca` | Access-2026-40875 | published, valid | 25 (21 + 4) | 0 | 2 m 35 s | 47,086 | 1 + 3 updates | 8,242 |
| 2026-09-12 | `decc4ca` | Access-2026-41373 | published, valid | 34 (26 + 8) | 0 | 14 m 44 s | 50,738 | 1 | 9,253 |
| 2026-09-12 | `decc4ca` | IoT-70548-2026 | SKIPPED (missing venue form) | 1 | 0 | 18 s | 5,041 | 0 | — |
| 2026-09-12 | `decc4ca` | NEUNET-D-26-04237 | SKIPPED (missing venue form) | 1 | 0 | 11 s | 5,030 | 0 | — |
| 2026-09-12 | `decc4ca` | TDSC-2025-09-1631.R1 | failed: model output-token limit | 23 (23 + 0) | 0 | 9 m 49 s | 59,078 | 0 | — |
| 2026-09-12 | `decc4ca` | TPDS-2026-08-0833 | SKIPPED (missing venue form) | 1 | 0 | 25 s | 5,634 | 0 | — |
| 2026-09-12 | `decc4ca` | oral-4560066 | published, valid | 29 (23 + 6) | 0 | 5 m 10 s | 51,226 | 1 + 2 updates | 8,598 |
| 2026-09-12 | `3026202` | TDSC-2025-09-1631.R1 (rerun) | published, valid | 42 (37 + 5) | 0 | 8 m 17 s | 101,308 | 3 + 1 update | 9,267 |
| 2026-09-12 | `a639257` | TDSC-2025-09-1631.R1 (rerun) | published, valid | 58 (52 + 6) | 0 | 8 m 48 s | 117,976 | 1 + 1 update | 9,231 |
| 2026-09-12 | `dc7baa6` | TDSC-2025-09-1631.R1 (rerun) | published, valid | 54 (50 + 4) | 0 | 9 m 29 s | 91,504 | 1 + 3 updates | 8,800 |
| 2026-09-12 | `483ec1b` | Access-2026-41373 (timing rerun) | published | 27 (18 + 9) | 0 | 2 m 50 s | 43,329 | 1 | — |

### Notes per run
- **2026-09-11, Access-2026-40102 (`c410d33`)**: 14 `get_asset` calls (tables 1-4, figures 2-3, equations 8 and 10,
  references 2, 9, 31, 51, 52); 3 images requested and dropped by Goose (custom provider without vision, see
  aaif-goose/goose#11998). The form section copied the form instructions and `[Reply with Yes or No]`; answers ran to
  3-5 sentences where the form asks for a very short paragraph. The agent reported an inconsistency between Table 4
  and Section IV-C that rested on a low-confidence table extraction. It ended with a 2k-character chat summary. Report
  and log kept outside the workspace (session scratchpad `runs/`).

- **2026-09-12, all 8 papers (`9678328`)**: every published report is valid under the current validator and its form
  section holds only `Label: answer` entries (5.9–6.7k characters). Access-40102 against the baseline: 4 m 11 s
  instead of 9 m 55 s, 29 calls instead of 37, a 30% shorter report, and no Table 4 artefact in the review. The three
  papers without a component stopped after `get_paper_overview` as the recipe says; their index builds take 2–9 s, so
  the 3.7–5.3 minutes are model latency. TDSC (68-page revision): 19 `read_pages` calls, the last request 110.8k input
  tokens, about 2 minutes per turn once the context passed 50k tokens. oral-4560066 (mdpi): the agent called
  `fetch_webpage` 87 times and hit the 64-turn limit without a report. Access-40102 and -41373 used 10 and 11
  `get_asset` calls although the recipe asks for at most 6. Paper index builds (current extractor): 1.3–9.6 s per paper.

- **2026-09-12, all 8 papers (`decc4ca`, extraction `fa6f68d`, page and item budgets)**: 4 valid reports of 5 venues
  with a form (oral-4560066 now published: 6 research calls instead of 95, no `fetch_webpage`). Largest input down
  13–36% on the three Access papers and oral (47–62k tokens instead of 69–73k); reports 7.3–9.3k characters, forms
  4.9–5.9k. Skips of the three papers without a form take 11–25 s instead of 3.7–5.3 minutes. `get_asset` calls: 4,
  3, 6 and 9 (the budget of 6 was not enforced: parallel calls of one turn lost state updates, fixed afterwards with a
  locked update). No `read_pages` request was refused: every agent followed the cursor. TDSC stopped after 20
  `read_pages` calls (manuscript and the whole response letter) with "Response reached the model's output-token
  limit", no report; the request logs of that run were rotated away before inspection. Accuracy spot checks against
  the stores held: oral F1 98.00 against P 95.10 and R 99.03 (97.03), the `[[missing dimensions]]` and
  `[[verify authors]]` placeholders on page 7, page-16 baselines absent from Table 5; Access-40102 equations 1-5, 8
  and 12-14 uncited.

- **2026-09-12, TDSC reruns (`3026202`, `a639257`, `dc7baa6`)**: the first rerun published (8 m 17 s) but needed 3
  submissions because the plain-text rule rejected ordinary math signs (superscript minus, double bar, arrows,
  middle dot, primes), and it read the whole response letter with `read_pages` after `get_author_responses` (the
  truncation footer pointed there), reaching 101k input tokens. With math signs allowed and the footer changed, the
  second rerun submitted once but made 23 `get_author_responses` queries: the letter's `R1.1 — title` comment headings
  were not item boundaries, so each query returned a whole reviewer section (233k characters for a 62.6k-character
  letter) and the context reached 118k tokens. With reviewer-numbered comment headings as item boundaries and each
  letter paragraph returned once per review, the third rerun used 6 queries, peaked at 91.5k input tokens and
  published a valid report in 9 m 29 s. Model output is mostly thinking (up to 35k characters before a single tool
  call; the largest reply 12.3k output tokens, streamed at about 110 tokens/s); whether that caused the output-token
  limit of the failed run is not verified, since its request logs were rotated. In the last ten requests of each
  rerun, whole-context prompt cache misses (72–92k uncached tokens) cost 60–70 s each, and reviewer-mcp tools answer
  in 1–30 ms.

- **2026-09-12, where review time goes (Goose CLI logs of every session that day, `timing_41373` capture)**: tool calls
  of both extensions finish in milliseconds to about a second; the minutes are model turns on the shared skynet
  server, and their length depends on when the run happens more than on the paper. The same one-reply skip
  (`get_paper_overview` then "SKIPPED") took 108–158 s per turn at 00:47, 00:51 and 02:19 and 4–6 s at 11:52; the
  84.5-minute TDSC review of 00:55 had a median turn of 145 s. Access-41373 took 14 m 44 s at 11:37 (eight consecutive
  turns of 44–114 s between 11:39 and 11:47, on a 20–35k-token context, then 2 s turns again) and 2 m 50 s at 18:45
  with a similar number of calls (median turn 3 s, 81% of the time streaming at about 125 tokens/s, no cache miss).
  The only review near 19 minutes, oral-4560066 at 02:25 (18 m 44 s), was the `fetch_webpage` runaway fixed since.

### How a run is measured
```bash
cd ~/Nextcloud/prompts
( time make reports/<stem>_Report.md ) > run.log 2>&1        # one paper, report must not exist yet
grep -c '▸' run.log                                           # tool calls
grep '▸' run.log | awk '{print $2, $3}' | sort | uniq -c    # calls per tool and extension
grep -o '"usage":{[^}]*}' ~/.local/state/goose/logs/llm_request.0.jsonl | tail -1   # last request size
wc -c reports/<stem>_Report.md                                # report size
```

---

## 2. Milestones

- **2026-09-10**: fixtures and test isolation (Phase 0); venue index from component `VENUE:` blocks with lazy guideline
  composition, `prompt.py` and compiled `guidelines/` removed (Phase 3); parts, current copy and review round
  (Phase 4); Makefile reduced to an orchestrator.
- **2026-09-11**: paper store with pages, lines, paragraphs, sections, FTS5 search, assets and mentions (Phase 2);
  layout heuristics derived per document with `config.json`; venue profile read from the store; 11-tool contract on
  the store with the old tools, `bundle.py`, `pdf.py`, `renderer.py`, `scratch.py` and the protocol patch removed
  (Phases 1 and 5); recipe rewritten; `base_review.md` aligned; pre-commit unittest hook uses `venv/bin/python`
  (system Python has fastmcp 3.4.5 / mcp 1.28.1 in `~/.local`).
- **2026-09-11 (later)**: context budget — tool list 11.7k → 9.1k characters, plain-text readers, reference entries
  left out of manuscript reading, guideline without the form or venue summary (10.3k → 6.4k characters); length
  limits removed from components and validator (F6 dropped); `base_review.md` streamlined; Makefile and recipe
  cleaned (backups of the previous Makefile, recipe, `base_review.md` and components in the session scratchpad).
- **2026-09-11 (plain text)**: D3 decided and F13 fixed — everything the agent writes in a report must match one
  allow-list regex (plain text, MathML the only markup); form lines reproduced verbatim are exempt; errors quote the
  offending text; `base_review.md` rule 3 says so.
- **2026-09-11 (forms)**: venue forms rewritten in a field grammar (`forms.py`, documented in
  `~/Nextcloud/prompts/README.md`): `choose`, `choose any`, `scale`, `text` with a size, `help`, `optional`. All 22
  components converted (web-form labels kept, instructions dropped, guidance moved to `help`). The skeleton lists one
  `Label: <to fill: ...>` entry per field and the report holds only `Label: answer`; the validator checks each answer
  against its field (options, range, paragraph count, plain text), text outside fields, repeated fields and labels of
  other venues' forms (replacing the hard-coded foreign markers). `update_report_field` works by label and keeps
  paragraphs. `base_review.md` report rules: 1-2 sentences for the prose sections and matrix cells, answers only.
  `prompts/README.md` rewritten for the MCP pipeline. Image attachments moved to `config.json` and turned off.
- **Store benchmark (2026-09-11)**: SQLite on tmpfs against per-page text and JSON files, median of 200 calls on
  Access-41373 / TDSC-1631: manuscript pages 92 / 134 µs vs 325 / 434 µs; one numbered item 36 / 43 µs vs 181 / 559 µs;
  search 305 / 597 µs vs 1.9 / 12.3 ms; asset list, parts and outline equal; opening a cached store under 1 ms. The
  store stays SQLite.
- **2026-09-12 (numbered items)**, commits `0eba799`, `af94f72`, `fa2bca6` and the statements commit: captions in
  body type and label-only captions with centred titles; section-based and supplementary numbers; tables bounded by
  aligned rules with cells rebuilt from word alignment (column cuts voted per row, stacked rows split, continuation
  rows joined, plain Markdown); vector figures grown with their labels and no longer hidden by plot grids;
  equations rebuilt from character geometry into linear text and MathML; theorem-like statements with proofs;
  plural and range citations. Corpus effect: IoT-J figures 3 → 10 and tables 0 → 11 found; figures and tables
  without a region 45 → 8; equations 181 of 206 at medium confidence; Access-40102 Table 4 read correctly (the
  baseline review's main finding was an extraction artefact). Outline: headings in body type under a numbered
  parent (oral 3.3.1–3.3.4), numbered table rows inside the top-level numbering dropped (Access-40875), running
  heads require numbers constant or following the page (TDSC `TABLE S.x` captions). Recipe: at most 6 `get_asset`
  calls, final reply `PUBLISHED: <report file>`.
- **2026-09-12 (tables and captions)**, commit `59d8035` and the layout commit after it: extraction stays PyMuPDF-only
  (docling and pymupdf4llm were slower, found fewer captions and invented formula LaTeX). TeX extension glyphs mapped
  (delimiters, large operators, radicals, script and double-struck capitals). Table cells from phrases, with the word
  spacing scaled to the table's type and column edges taken from left-aligned text; the header ends at the first
  full-width rule, group labels head the columns under their rule, panels titled between rules get their own header,
  wrapped and sparse rows join their row, and PyMuPDF line cells are kept only when their rules separate every
  column. Zero-height rules are no longer dropped (`Rect.intersects` is false for them); rule pieces join only along
  one line, so plot grids no longer merge with tables; page-wide tables under a one-column caption are matched.
  Captions in small capitals with inline math stay whole; justified lines that MuPDF split at stretched spaces are
  rejoined; pieces of one text row are read left to right and are not taken as table cells; display equations no
  longer absorb inline fractions of the prose row above. Corpus effect: table benchmark (header and one row of eight
  tables) 9/16 → 16/16; table entries without cells 13 → 3 (both TDSC copies counted); IoT-J figures 10 → 11;
  equations unchanged at 124 of 149 medium; `tests/test_corpus.py` records the header and a row of 12 tables.
- **2026-09-18 (numbered items the extraction was losing)**, commits `ea64892` and `071ec7d`, found on a JII
  (Elsevier) manuscript and an IEEE OJ-COMS proof after the 8-paper corpus was replaced. A caption became a label, a
  separator and the caption text, with a label alone on its line taking the line below; a space is not a separator, so
  body sentences (`Table 1 briefly describes ...`) are rejected without any typography test — the previous rule needed
  small type or punctuation, so a manuscript set entirely in one size hid four of its five tables. A caption holds no
  paragraph break, so the next label ends it. Item numbers carry their letter (`5a`, `5b`), which stopped the second
  part of a figure being dropped by the dedupe; a citation of the whole names every part. Numbered items are read past
  the References (floats at the end of a proof, appendices). Tables are limited by their rules rather than by the page.
  A cell of a table is no longer read as document structure: the guard now covers the later lines of a deep cell, which
  stand alone on their row — a wrapped cell reading `abstract and` had been starting a second manuscript part, making a
  single submission look like a revision with two copies at high confidence. Assets carry `last_page`
  (`EXTRACTOR_VERSION` 32) and the server reports a page span. Effect on the two papers: JII tables 1 (43 → 141 rows,
  pages 5 → 5-7), 3 (3 → 18, 15 → 15-16) and 4 (49 → 91, 17 → 17-18), tables 1, 3, 4, 5 and figures 5a, 6a, 6b
  recovered, manuscript 2-25 instead of 2-7 plus 8-25, round unknown instead of a false revision, figure and table
  citations 5 → 26; IEEE figure 10 recovered, its three tables unchanged (they close on their page). Forms: a field
  takes one choice and may carry a `text` size for the explanation after it, with `explain` naming the options that
  must carry one (`explain: No`, `explain: always`) — `ieee_oj-coms.md` had been rejected whole, dropping its venue
  from the index so OJCOMS-07163-2026 could not be reviewed at all. The first cut read the requirement out of a
  `(explain)` aside in the option text; a form says it outright instead, since the aside is prose for a human and
  `help` is never parsed.
- **Protocol**: mcp 2.2 negotiates 2026-07-28 via `server/discover` with modern clients and keeps `initialize`
  (≤ 2025-11-25) for older ones; tested over stdio.
