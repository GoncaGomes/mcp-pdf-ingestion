"""Validation of review reports: mandated structure, Quality Matrix, plain text and the venue form answers."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from reviewer_mcp.forms import Field, answer_problems, labels_elsewhere, split_answers

MANDATED_SECTIONS = [
    "# Review Report",
    "## Venue Resolution",
    "## Extraction Summary & Limitations",
    "## Paper Quality Matrix",
    "## Venue Review Form Answers",
]

OPTIONAL_SECTIONS = ["## Metadata"]

PROSE_SECTIONS = ["## Venue Resolution", "## Extraction Summary & Limitations"]

QUALITY_CRITERIA = [
    "novelty",
    "technical soundness",
    "evaluation rigor",
    "clarity",
    "impact",
]

UNICODE_FOLD = {
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "…": "...",
    " ": " ",
}
_FOLD_RE = re.compile("|".join(map(re.escape, UNICODE_FOLD)))

# Agent-written text is plain text, with MathML as the only markup: letters and digits of any script, punctuation,
# math signs, '_' inside a word (identifiers, file names), a lone '<', MathML tags and line breaks, where no line opens
# a list item, a numbered item or a heading.
LIST_OR_HEADING = r"[ \t]*(?:\d+[.)]|[-+•]|#{1,6})[ \t]"
MATHML_TAG = (
    r"</?(?:math|semantics|annotation|m(?:i|n|o|s|text|row|sub|sup|subsup|frac|sqrt|root|over|under|underover"
    r"|table|tr|td|space|style))\b[^<>]*>"
)
_PLAIN = (
    r"(?:[^\W_]|[ \t\r\u00a0.,;:!?'\"()\[\]{}%/&@#§+=>≤≥–—‘’“”…°±×µ·‖′″‴\u2070-\u209f\u2190-\u21ff\u2200-\u22ff"
    r"\u2308-\u230b\u27e8\u27e9\u2a00-\u2aff-]"
    rf"|(?<=[^\W_])_(?=[^\W_])|<(?![/A-Za-z])|{MATHML_TAG}|\n(?!{LIST_OR_HEADING}))*"
)
PLAIN_TEXT_RE = re.compile(rf"(?!{LIST_OR_HEADING}){_PLAIN}")
PLACEHOLDER_RE = re.compile(r"<to fill[^>]*>")  # skeleton placeholders, reported separately
QUOTE_CONTEXT = 30  # characters quoted before the first non-plain character
PLAIN_TEXT_HINT = (
    "Write plain sentences and paragraphs only (no lists, numbering, bold, italic, headings, emoji or markup; "
    "formulas as Unicode signs or MathML)."
)

def explicit_venue_id_from_report(report_text: str) -> str:
    """Extract the explicit 'Venue ID' value from the report metadata table."""
    m = re.search(r"venue\s*id\s*\**\s*[|:]\s*\**\s*([a-z0-9_\-]+)", report_text, re.I)
    return m.group(1).strip().lower() if m else ""


def normalise(line: str) -> str:
    """Normalize line removing formatting, whitespace runs, and folding dashes."""
    s = unicodedata.normalize("NFKC", line)
    s = _FOLD_RE.sub(lambda m: UNICODE_FOLD[m.group()], s)
    s = re.sub(r"[*_`]+", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip().strip("-").strip()
    s = s.rstrip(":.").strip()
    return s.lower()


def extract_section(text: str, heading: str, stop_level: str = "## ") -> str:
    """Extract the body under heading up to the next heading of stop_level."""
    lines = text.splitlines()
    want = heading.strip().lower()

    def body_from(idx: int) -> str:
        out: list[str] = []
        for line in lines[idx + 1 :]:
            if line.startswith(stop_level) or line.startswith("# "):
                break
            out.append(line)
        return "\n".join(out)

    prefix_hit = -1
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if s == want:
            return body_from(i)
        if prefix_hit < 0 and s.startswith(want):
            prefix_hit = i
    return body_from(prefix_hit) if prefix_hit >= 0 else ""


def plain_text_problem(text: str) -> str:
    """'' when text is plain text (MathML allowed), else the text where it stops being plain."""
    text = PLACEHOLDER_RE.sub("", text)
    match = PLAIN_TEXT_RE.match(text)
    end = match.end() if match else 0
    if end == len(text):
        return ""
    if text[end] == "\n":
        end += 1  # the next line opens a list item, a numbered item or a heading
    start = max(text.rfind("\n", 0, end) + 1, end - QUOTE_CONTEXT)
    return text[start:].split("\n", 1)[0][: 2 * QUOTE_CONTEXT].strip()


def validate_report(
    report_text: str, fields: tuple[Field, ...], other_labels: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Validate a report against the venue form fields; other_labels are the field labels of the other venues."""
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Structure
    for sec in MANDATED_SECTIONS:
        if sec.lower() not in report_text.lower():
            errors.append(f"Missing mandated section: {sec}")

    present_headers = [line_hdr.strip() for line_hdr in report_text.splitlines() if line_hdr.startswith("## ")]
    allowed = {s.lower() for s in MANDATED_SECTIONS + OPTIONAL_SECTIONS}
    for h in present_headers:
        if h.lower() not in allowed:
            warnings.append(f"Section not in mandated structure: {h}")

    # 2. Quality Matrix
    matrix = extract_section(report_text, "## Paper Quality Matrix")
    if not matrix.strip():
        errors.append("Paper Quality Matrix section is empty")
    else:
        for crit in QUALITY_CRITERIA:
            row: list[str] | None = None
            for line in matrix.splitlines():
                if not line.strip().startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 2:
                    continue
                name = re.sub(r"[*_]+", "", cells[0]).strip().lower()
                if name.startswith("criterion") or set(name) <= set(": -"):
                    continue
                if crit in name:
                    row = cells
                    break
            if row is None:
                errors.append(f"Paper Quality Matrix missing criterion row: {crit}")
                continue
            for cell in row[1:]:
                if problem := plain_text_problem(cell):
                    errors.append(f"Not plain text in the Quality Matrix row {crit!r}: {problem!r}. {PLAIN_TEXT_HINT}")
            score = re.sub(r"[*_\s]+", "", row[1])
            if not re.fullmatch(r"[1-5]", score):
                errors.append(
                    f"Paper Quality Matrix score for {crit!r} is {row[1].strip()!r}; expected a whole number 1-5"
                )

    # 3. Prose sections
    for section in PROSE_SECTIONS:
        if problem := plain_text_problem(extract_section(report_text, section)):
            errors.append(f"Not plain text in {section[3:]}: {problem!r}. {PLAIN_TEXT_HINT}")

    # 4. Form answers: every field once, valid for its kind, plain text, nothing else
    answers = extract_section(report_text, "## Venue Review Form Answers")
    if not answers.strip():
        errors.append("Report has no '## Venue Review Form Answers' content")
        return {"valid": False, "errors": errors, "warnings": warnings}
    values, layout = split_answers(answers, fields)
    errors.extend(layout)
    for field in fields:
        if field.label not in values:
            if not field.optional:
                errors.append(f"The field {field.label!r} is missing; answer it as '{field.label}: ...'.")
            continue
        answer = values[field.label]
        if PLACEHOLDER_RE.search(answer):
            continue  # reported as an unfilled placeholder
        errors.extend(answer_problems(field, answer))
        if problem := plain_text_problem(answer):
            errors.append(f"Not plain text in the answer to {field.label!r}: {problem!r}. {PLAIN_TEXT_HINT}")
    errors.extend(labels_elsewhere(answers, fields, set(other_labels)))

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
