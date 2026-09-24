"""Author responses of a revision: reviewer blocks and comment/answer items of the response letter."""

from __future__ import annotations

import json
import re
from typing import Any

from reviewer_mcp.papers import RESPONSES_KEY, ReviewError, page_span
from reviewer_mcp.reading import READ_BUDGET
from reviewer_mcp.store import PaperStore
from reviewer_mcp.structure import COMMENT_LINE_RE

# A reviewer heading is a paragraph of its own, not a sentence ("Response to Reviewer 2", "Reviewer #1:").
REVIEWER_HEADING_RE = re.compile(
    r"^(?:(?:responses?|repl(?:y|ies)|answers?)\s+to\s+|comments?\s+(?:from|of|by)\s+)?(?:the\s+)?"
    r"(?:reviewer|referee)\s*#?\s*(\d{1,2})\b[^.?!]*$",
    re.IGNORECASE,
)
# A reviewer-numbered comment heading ("R1.2 — Notation table", "Reviewer 2.3") opens a comment/answer item.
COMMENT_NUMBER_RE = re.compile(r"^(?:R|reviewer\s*)\d{1,2}\s*[.-]\s*\d{1,3}\b", re.IGNORECASE)
OPENING_BUDGET = 3000  # characters of the letter opening


def _text(paragraphs: list[dict[str, Any]], budget: int) -> tuple[str, int | None, int]:
    """Paragraphs with page markers up to the budget, the page where the rest continues and how many paragraphs
    were included."""
    parts: list[str] = []
    used = 0
    page = 0
    for paragraph in paragraphs:
        chunk = paragraph["text"]
        if paragraph["page"] != page:
            page = paragraph["page"]
            chunk = f"(page {page}) {chunk}"
        if parts and used + len(chunk) > budget:
            return "\n\n".join(parts), paragraph["page"], len(parts)
        parts.append(chunk[:budget])
        used += len(parts[-1]) + 2
    return "\n\n".join(parts), None, len(parts)


def _items(paragraphs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Comment/answer items: each starts at a numbered comment line, a reviewer-numbered comment heading or a
    reviewer heading."""
    items: list[list[dict[str, Any]]] = []
    for paragraph in paragraphs:
        text = paragraph["text"].strip()
        if not items or COMMENT_LINE_RE.match(text) or COMMENT_NUMBER_RE.match(text) or REVIEWER_HEADING_RE.match(text):
            items.append([paragraph])
        else:
            items[-1].append(paragraph)
    return items


def author_responses(store: PaperStore, reviewer: int | None, query: str | None) -> str:
    """The response letter as plain text under a status line: its opening without filters, else the selected
    reviewer blocks or comment/answer items. Paragraphs already returned during this review are left out, so
    repeating a filter continues a truncated reply."""
    segments = [s for s in store.segments() if s["kind"] == "responses"]
    if not segments:
        round_status = store.structure().get("round") or "unknown"
        raise ReviewError(
            f"This PDF has no author response letter (review round: {round_status}). "
            "get_author_responses applies to revisions only."
        )
    first, last = min(s["first_page"] for s in segments), max(s["last_page"] for s in segments)
    paragraphs = store.paragraphs(first, last)
    marks = [
        (index, int(match.group(1)))
        for index, paragraph in enumerate(paragraphs)
        if (match := REVIEWER_HEADING_RE.match(paragraph["text"].strip()))
    ]
    reviewers = list(dict.fromkeys(number for _, number in marks))
    status = f"Author responses, pages {page_span(first, last)}; reviewers present: {reviewers}"
    if reviewer is None and not query:
        opening, _, _ = _text(paragraphs[: marks[0][0] if marks else len(paragraphs)], OPENING_BUDGET)
        guide = (
            "Letter opening below; filter with reviewer=<number> or query=<text> instead of reading the letter "
            "pages. Verify every claimed change in the manuscript with search_paper or read_section; do not trust "
            "the letter alone."
        )
        return f"{status}. {guide}\n\n{opening}"

    selected = paragraphs
    if reviewer is not None:
        if reviewer not in reviewers:
            raise ReviewError(
                f"Reviewer {reviewer} does not appear in the response letter; reviewers present: {reviewers}."
            )
        bounds = [*marks, (len(paragraphs), 0)]
        selected = [
            paragraph
            for (start, number), (end, _) in zip(bounds, bounds[1:], strict=False)
            if number == reviewer
            for paragraph in paragraphs[start:end]
        ]
        status += f"; reviewer {reviewer}"
    if query:
        needle = query.casefold()
        matching = [item for item in _items(selected) if any(needle in p["text"].casefold() for p in item)]
        selected = [paragraph for item in matching for paragraph in item]
        status += f"; query {query!r}: {len(matching)} matching items"
    returned = set(json.loads(store.get_state(RESPONSES_KEY) or "[]"))
    fresh = [paragraph for paragraph in selected if paragraph["id"] not in returned]
    if len(fresh) < len(selected):
        status += f"; {len(selected) - len(fresh)} paragraphs already returned in this review are left out"
    if not fresh:
        return f"{status}. Nothing new to return."
    text, next_page, count = _text(fresh, READ_BUDGET)
    sent = {paragraph["id"] for paragraph in fresh[:count]}
    store.update_state(RESPONSES_KEY, lambda value: json.dumps(sorted(set(json.loads(value or "[]")) | sent)))
    footer = f"\n\n[truncated at page {next_page}: call again with the same filter for the rest]" if next_page else ""
    return f"{status}\n\n{text}{footer}"
