"""Review reports: the skeleton, validation, publishing only valid reports, and single-field updates of the draft."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from reviewer_mcp import forms
from reviewer_mcp.config import DEFAULT_REPORTS_DIR, workspace
from reviewer_mcp.forms import Field
from reviewer_mcp.papers import ReviewError, paper_stem
from reviewer_mcp.store import PaperStore
from reviewer_mcp.validator import PLACEHOLDER_RE, explicit_venue_id_from_report, normalise, validate_report
from reviewer_mcp.venues import VenueIndex

DRAFT_KEY = "report_draft"
PLACEHOLDER = "<to fill"
MATRIX_SECTION = "## Paper Quality Matrix"
FORM_SECTION = "## Venue Review Form Answers"
MATRIX_ROWS = (
    "Novelty (None/Incremental/Novel)", "Technical Soundness", "Evaluation Rigor", "Clarity & Logic", "Impact"
)
MATRIX_FIELD_RE = re.compile(r"^\s*quality\s+matrix\s*:\s*(.+)$", re.IGNORECASE)


def _cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|") or "None"


def skeleton(
    *, paper: str, title: str, venue_name: str, venue_id: str, status: str, notes: str, form: tuple[Field, ...]
) -> str:
    """Markdown report with every mandated section, the Metadata table pre-filled and one entry per form field."""
    rows = (
        ("Manuscript", paper),
        ("Title", title or f"{PLACEHOLDER}: title as printed>"),
        ("Authors", f"{PLACEHOLDER}: authors as printed, or Anonymous>"),
        ("Venue", venue_name),
        ("Venue ID", venue_id),
        ("Date", dt.date.today().isoformat()),
        ("Submission Status", status),
        ("Reviewer Notes", notes or "None"),
    )
    lines = ["# Review Report", "", "## Metadata", "", "| Field | Value |", "| :--- | :--- |"]
    lines += [f"| **{name}** | {_cell(value)} |" for name, value in rows]
    lines += [
        "",
        "## Venue Resolution",
        "",
        f"{PLACEHOLDER}: 1-2 sentences: the venue, the metadata evidence that resolved it, the submission round>",
        "",
        "## Extraction Summary & Limitations",
        "",
        f"{PLACEHOLDER}: 1-2 sentences: pages audited, items inspected, external checks and their limits>",
        "",
        MATRIX_SECTION,
        "",
        "| Criterion | Score (1-5) | Evidence/Reasoning | Validation Status |",
        "| :--- | :--- | :--- | :--- |",
    ]
    lines += [
        f"| {row} | {PLACEHOLDER}: 1-5> | {PLACEHOLDER}: 1-2 sentences of evidence> | "
        f"{PLACEHOLDER}: Validated or Questionable> |"
        for row in MATRIX_ROWS
    ]
    lines += ["", FORM_SECTION, "", forms.skeleton(form), ""]
    return "\n".join(lines)


def report_path(pdf: Path) -> Path:
    return workspace() / DEFAULT_REPORTS_DIR / f"{paper_stem(pdf)}_Report.md"


def check(report: str, index: VenueIndex, venue_id: str) -> dict[str, Any]:
    """Validate against the venue guideline, the resolved venue and the skeleton placeholders."""
    errors: list[str] = []
    stated = explicit_venue_id_from_report(report)
    if not stated:
        errors.append("The Metadata table has no 'Venue ID' row; start from get_review_guideline(form_only=true).")
    elif stated != venue_id:
        errors.append(f"Metadata Venue ID {stated!r} differs from the venue resolved for this paper ({venue_id!r}).")
    unfilled = PLACEHOLDER_RE.findall(report)
    if unfilled:
        errors.append(f"{len(unfilled)} skeleton placeholders are not filled, e.g. {unfilled[0]!r}.")
    result = validate_report(report, index.form_fields(venue_id), index.other_labels(venue_id))
    return {
        "valid": not errors and bool(result["valid"]),
        "errors": errors + list(result["errors"]),
        "warnings": list(result["warnings"]),
    }


def _publish(pdf: Path, report: str) -> None:
    path = report_path(pdf)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(report, encoding="utf-8")
    tmp.replace(path)


def submit(
    store: PaperStore, pdf: Path, report: str, index: VenueIndex, venue_id: str, dry_run: bool
) -> dict[str, Any]:
    """Keep the draft, validate it, and publish it only when it passes."""
    store.set_state(DRAFT_KEY, report)
    outcome = check(report, index, venue_id)
    published = bool(outcome["valid"]) and not dry_run
    if published:
        _publish(pdf, report)
    reply: dict[str, Any] = {"valid": outcome["valid"], "published": published}
    if published:
        reply["report"] = report_path(pdf).name
    if outcome["errors"]:
        reply["errors"] = outcome["errors"]
    if outcome["warnings"]:
        reply["warnings"] = outcome["warnings"]
    if published:
        reply["next"] = "Done: the report is published. Stop."
    elif outcome["valid"]:
        reply["next"] = "Valid (dry run, not published). Call submit_report without dry_run to publish."
    else:
        reply["next"] = ("Nothing was published. Fix single fields with update_report_field; resubmit the whole report "
                         "with submit_report only for structural problems.")
    return reply


def _section_bounds(lines: list[str], heading: str) -> tuple[int, int]:
    start = next((i for i, line in enumerate(lines) if line.strip().lower().startswith(heading.lower())), None)
    if start is None:
        raise ReviewError(f"The draft has no '{heading}' section; resubmit the complete report with submit_report.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("## ", "# "))), len(lines))
    return start + 1, end


def _set_matrix_score(lines: list[str], criterion: str, score: str) -> None:
    if not re.fullmatch(r"[1-5]", score):
        raise ReviewError(f"A Quality Matrix score is a whole number from 1 to 5, not {score[:20]!r}.")
    start, end = _section_bounds(lines, MATRIX_SECTION)
    wanted = normalise(criterion)
    for i in range(start, end):
        cells = lines[i].strip().strip("|").split("|")
        if lines[i].strip().startswith("|") and len(cells) >= 2 and wanted and wanted in normalise(cells[0]):
            cells[1] = f" {score} "
            lines[i] = "|" + "|".join(cells) + "|"
            return
    raise ReviewError(f"No Quality Matrix row matches {criterion[:60]!r}; rows: {list(MATRIX_ROWS)}.")


def _set_answer(lines: list[str], wanted: str, answer: str, fields: tuple[Field, ...]) -> None:
    key = wanted.strip().rstrip(":").casefold()
    field = next((f for f in fields if f.label.casefold() == key), None)
    if field is None:
        starting = [f for f in fields if f.label.casefold().startswith(key)]
        field = starting[0] if len(starting) == 1 else None
    if field is None:
        raise ReviewError(f"No form field is labelled {wanted[:80]!r}. Fields: {[f.label for f in fields]}.")
    start, end = _section_bounds(lines, FORM_SECTION)
    at = next((i for i in range(start, end) if forms.field_at(lines[i], fields) is field), None)
    if at is None:
        raise ReviewError(f"The draft has no {field.label!r} field; resubmit the complete report with submit_report.")
    stop = next((j for j in range(at + 1, end) if forms.field_at(lines[j], fields)), end)
    if field.kind == "text":
        paragraphs = [" ".join(block.split()) for block in re.split(r"\n\s*\n", answer) if block.strip()]
        block = [f"{field.label}:", *[line for paragraph in paragraphs for line in (paragraph, "")]]
    else:
        block = [f"{field.label}: {' '.join(answer.split())}", ""]
    lines[at:stop] = block


def update_field(
    store: PaperStore, pdf: Path, field: str, answer: str, index: VenueIndex, venue_id: str
) -> dict[str, Any]:
    """Replace one answer (or a Quality Matrix score) in the draft, then validate and publish when valid."""
    draft = store.get_state(DRAFT_KEY)
    if not draft:
        raise ReviewError("There is no draft for this paper yet: call submit_report with the complete report first.")
    lines = draft.splitlines()
    matrix = MATRIX_FIELD_RE.match(field)
    if matrix:
        _set_matrix_score(lines, matrix.group(1), " ".join(answer.split()))
    else:
        _set_answer(lines, field, answer, index.form_fields(venue_id))
    report = "\n".join(lines) + ("\n" if draft.endswith("\n") else "")
    return submit(store, pdf, report, index, venue_id, dry_run=False)
