# reviewer-mcp: TODO

Open work for `reviewer-mcp`, its Goose recipe and the `~/Nextcloud/prompts` workspace. Design and decisions are in
`PLAN.md`; evaluation runs, milestones and resolved findings are in `HISTORY.md`. Last updated 2026-09-12.

## 1. Waiting on others

- [ ] **Approve the 11-tool contract** (PLAN §2.8 and the Phase 1 deviations: dictionary replies without output
  schemas; `read_pages` reads to the end of the part and leaves out reference entries; plain-text readers;
  `list_assets` omits references unless asked; a report is published only for the venue whose guideline was loaded).
- [ ] **Images** (D4, vision steps V2–V3 in PLAN §2.5): once Goose passes images to custom providers
  (aaif-goose/goose#11998, PR #12010) and `mmproj-BF16.gguf` is installed, declare vision for `qwen3.8-27b` in
  `custom_skynet.json` and set `images.enabled` in `config.json`.

## 2. Venue forms (`forms/`)

- [ ] Forms for IEEE Internet of Things Journal, Elsevier Neural Networks and IEEE TPDS; their reviews are skipped as a
  missing venue form until then.
- [ ] Identifier gaps listed in PLAN §2.2 (TFS, TDSC, THMS, ComMag, CSUR, TIST, AILET, MDPI, Springer Nature,
  Sparcly, PRIMORIS) and the stamps printed by PRIMORIS, Sparcly and PeerJ PDFs.

## 3. Extraction (validation corpus)

Corpus: `tests/test_corpus.py` records the structure, caption and table facts of 8 PDFs that are no longer in
`~/Nextcloud/prompts/papers` (it holds JII-D-26-01676 and OJCOMS-07163-2026 instead), so those checks skip. Restore
them before changing caption, heading or table heuristics again: the 2026-09-18 commits were validated on two papers.

- [ ] **Tables**: TDSC Table XII of the second copy has no region; in the rule-less text table TDSC Table II the
  italic section labels join the next row and a first-column cell wrapped over two lines shares its rows with the
  neighbouring entries. (A table continuing on the next page is handled since 2026-09-18: rules limit a table, not
  the page.)
- [ ] **Equations**: 25 of 149 at low confidence — multi-row displays and cases (TDSC 7, NEUNET 16), fractions holding
  sums (NEUNET 12–14), numbers whose region catches only a script (Access-40102 3, 4, 6, 8, 10). MathML for matrices,
  cases and aligned systems; nested fractions inside large operators (Access-40875 equation 8).
- [ ] **Headings**: Access-40875 `II.B` (bold italic among bold A, C, D) is missed; `A`–`C` after `III.D.1` (page 9)
  are accepted as level-2 headings without a check against the PDF.
- [ ] **A manuscript section read as a bundle item** (JII-D-26-01676, pages 26-30): `ITEM_LABEL_RE` holds
  `declaration of...` for the Elsevier bundle item, and `_signals` takes the label from the page's first line, so a
  manuscript page that merely opens with the `Declaration of competing interest` section Elsevier requires starts an
  `other` part. The manuscript closes at page 25 and its reference list, pages 26-30, falls outside it: 104 reference
  entries, **0 of them cited** from the manuscript (the IEEE control resolves 34), `list_assets` shows the paper no
  references at all, and `read_pages` stops before the bibliography, all without a signal. A bare `Figures` or
  `Tables` line at the top of a page does the same. The section tree shows the document is unbroken (`10 Conclusion`
  p25 -> `References` p26). Fix tried and held back: an item label does not start a part on a page carrying a heading
  of the section tree (`elif found.label and number not in section_pages:`), which gives manuscript pages 2-30 and
  164 resolved citations, leaving IEEE unchanged; its risk is a genuine bundle item whose first page opens with a
  heading (supplementary material starting `Appendix A`) being absorbed into the part before it. Narrower options:
  suppress only when the heading continues the current part's numbering, or drop `declaration of...` from
  `ITEM_LABEL_RE` and leave `figures?`/`tables?` exposed. Needs a bundle PDF to decide.
- [ ] **Structure**: the TDSC clean-copy choice has low confidence; sparse proof line numbers (oral-4560066, every few
  lines at the right margin) stay in the body; without a cover sheet (NEUNET, oral) the round is unknown and the agent
  must treat it as a first submission.
- Not supported and not seen in the corpus: footnotes, code listings without rules, author–year references and
  citations, sub-equation (`(1a)`) and appendix (`(A.3)`) equation numbers. When a paper shows one, record its facts
  in `tests/test_corpus.py`, add a synthetic fixture for the layout, then implement.

## 4. Review evaluation (`qwen3.8-27b`)

Targets per paper: no tool errors, at most one `submit_report` plus one round of `update_report_field`, never an
invalid file in `reports/`, correct venue, parts and round, and a wall time within 5 minutes for a 20-page paper
when the model server is free.

- [ ] Report quality: integer matrix scores 1–5 for every criterion, answer sizes as the form states, no cross-venue
  labels or filler.
- [ ] Review rigour: unstated assumptions, missing baselines, claims checked against tables and equations, actionable
  comments, confidential notes kept separate.
- [ ] Failure modes (JSON errors, repeated calls, premature exit): fix tool and parameter descriptions before recipe
  prose.
- [ ] Secondary models on skynet once `qwen3.8-27b` meets the targets.

## 5. Heuristic factors (`src/reviewer_mcp/config.json`)

Every layout tolerance is a factor of the document's own body size (em) or line height; the factors are backed only
by the 8 corpus PDFs and the synthetic fixtures at 8, 10 and 12 pt on A4 and Letter (`tests/test_scale.py`).

- [ ] Re-check the factors when a new layout family is added (ACM, Springer LNCS, Elsevier, PeerJ, arXiv preprints).
- [ ] Record the new paper's structure facts in `tests/test_corpus.py` before changing a factor, so a fix for one
  layout cannot silently break another.

## 6. Working rules

- Propose every change (TODO item or new idea, said which) and wait for approval before editing.
- The Makefile only spawns recipe runs; every review decision is the agent's, with the reviewer-mcp tools.
- Venue from metadata only, never from body prose; extraction is deterministic, PyMuPDF only, hidden behind tools.
- No thresholds fitted to one paper: derive them from document statistics or put the factor in `config.json`.
- No unrequested features (OCR was rejected: the PDFs are born-digital).
- Launch MCP servers from their venv binaries, never `uv run`.
- Commit locally at each milestone with pre-commit green; no remote, no push, no attribution lines.
- `~/Nextcloud/prompts` and `~/.config/goose` are not git repositories: back files up before editing.
- Reviews run with high thinking effort.
