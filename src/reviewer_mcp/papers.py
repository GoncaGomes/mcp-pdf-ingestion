"""Paper handles for the tools: the PDF named by the agent, its reviewer notes, parts, title and overview.

Tools address a paper by its file name in ``papers/``; a path is accepted but never returned. Page numbers are PDF page
numbers everywhere.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from reviewer_mcp.config import DEFAULT_PAPERS_DIR, workspace
from reviewer_mcp.heuristics import SAME_SIZE
from reviewer_mcp.store import PaperStore

# Reply budgets (characters or items), not layout heuristics.
NOTES_BUDGET = 4000
TITLE_BUDGET = 300
EVIDENCE_ITEMS = 4
IMAGES_KEY = "images_sent"
ASSETS_KEY = "assets_returned"  # item ids get_asset returned in full during the current review
PAGES_READ_KEY = "pages_returned"  # pages read_pages returned whole during the current review
RESPONSES_KEY = "responses_returned"  # response-letter paragraph ids get_author_responses returned in this review


class ReviewError(ValueError):
    """A request the agent can correct; the message says how."""


def paper_stem(paper: str | Path) -> str:
    """File name without the .pdf extension ('Access-2026-41373_Proof_hi.pdf' -> 'Access-2026-41373_Proof_hi')."""
    name = Path(paper).name
    return name[:-4] if name.lower().endswith(".pdf") else Path(name).stem


def resolve_paper(paper: str) -> Path:
    """The PDF named by the agent: a file name in papers/ (a path is also accepted)."""
    papers_dir = workspace() / DEFAULT_PAPERS_DIR
    given = Path(paper.strip())
    for path in (papers_dir / given.name, given if given.is_absolute() else workspace() / given):
        if given.name and path.is_file() and path.suffix.lower() == ".pdf":
            return path.resolve()
    available = sorted(p.name for p in papers_dir.glob("*.pdf")) if papers_dir.is_dir() else []
    raise ReviewError(
        f"Paper {given.name[:120]!r} is not in papers/. Available papers: {available[:20]}. "
        "Pass the PDF file name exactly as given in the task."
    )


def reviewer_notes(pdf: Path) -> str:
    """Reviewer directives from papers/<stem>.notes, if present."""
    notes = pdf.with_name(f"{paper_stem(pdf)}.notes")
    if not notes.is_file():
        return ""
    text = notes.read_text(encoding="utf-8", errors="replace").strip()
    return text if len(text) <= NOTES_BUDGET else text[:NOTES_BUDGET] + " [notes truncated]"


def page_span(first: int, last: int) -> str:
    return str(first) if first == last else f"{first}-{last}"


def part_range(store: PaperStore, part: str) -> tuple[int, int]:
    """First and last PDF page of a part: 'manuscript' (the copy under review), 'responses', 'cover' or 'all'."""
    if part == "all":
        return 1, store.page_count
    if part == "manuscript":
        pages = store.manuscript_pages()
        return int(pages["first"]), int(pages["last"])
    segments = [s for s in store.segments() if s["kind"] == part]
    if not segments:
        parts = ", ".join(f"{s['kind']} {page_span(s['first_page'], s['last_page'])}" for s in store.segments())
        raise ReviewError(
            f"This PDF has no {part} part (parts: {parts or 'none detected'}). Use part='manuscript' or part='all'."
        )
    return min(s["first_page"] for s in segments), max(s["last_page"] for s in segments)


def title(store: PaperStore) -> str:
    """Title of the manuscript under review: the first run of lines in the largest type on its first page."""
    first, _ = part_range(store, "manuscript")
    body_size = float(store.meta().get("body_size") or 0.0)
    lines = [line for line in store.lines(first, ("body",)) if re.search(r"[^\W\d_]{2}", line["text"])]
    if not lines:
        return ""
    tolerance = SAME_SIZE * body_size
    largest = max(line["size"] for line in lines)
    if largest - body_size <= tolerance:
        return ""  # nothing is set larger than the text
    selected: list[str] = []
    for line in lines:
        if largest - line["size"] <= tolerance:
            selected.append(line["text"].strip())
        elif selected:
            break
    return " ".join(selected)[:TITLE_BUDGET]


def overview(store: PaperStore, pdf: Path, venue: dict[str, Any]) -> dict[str, Any]:
    """Everything the agent needs to plan the review, in PDF page numbers."""
    first, last = part_range(store, "manuscript")
    structure = store.structure()
    chosen = store.manuscript_pages()
    manuscript: dict[str, Any] = {"pages": page_span(first, last), "source": chosen["source"]}
    if chosen["source"] == "override":
        manuscript["reason"] = chosen.get("reason", "")
    else:
        manuscript["confidence"] = structure.get("current_confidence", "")
        manuscript["evidence"] = structure.get("current_evidence", [])[:EVIDENCE_ITEMS]
    round_info: dict[str, Any] = {
        "status": structure.get("round") or "unknown",
        "confidence": structure.get("round_confidence", ""),
        "evidence": structure.get("round_evidence", [])[:EVIDENCE_ITEMS],
    }
    if structure.get("round_label"):
        round_info["label"] = structure["round_label"]
    parts = []
    for segment in store.segments():
        entry: dict[str, Any] = {
            "kind": segment["kind"],
            "pages": page_span(segment["first_page"], segment["last_page"]),
        }
        if segment["label"]:
            entry["label"] = segment["label"]
        entry["evidence"] = segment["evidence"][:EVIDENCE_ITEMS]
        parts.append(entry)
    outline = [
        f"{'  ' * (s['level'] - 1)}{s['number'] + ' ' if s['number'] else ''}{s['title']} (p{s['page']})"
        for s in store.outline()
        if first <= s["page"] <= last
    ]
    assets = store.assets(first=first, last=last)
    counts = Counter(a["kind"] for a in assets)
    reply: dict[str, Any] = {
        "paper": pdf.name,
        "pdf_pages": store.page_count,
        "title": title(store),
        "venue": venue,
        "parts": parts,
        "manuscript": manuscript,
        "round": round_info,
        "reviewer_notes": reviewer_notes(pdf),
        "outline": outline,
        "numbered_items": dict(sorted(counts.items())),
        "uncited_items": [a["id"] for a in assets if a["cited"] == 0 and a["kind"] != "reference"],
    }
    unreadable = [p["page"] for p in store.pages() if p["source"] == "none"]
    if unreadable:
        reply["warnings"] = [f"pages {unreadable} have no text layer (e.g. scanned images); their text cannot be read"]
    # a new review starts with the full image and item budgets and may read every page again
    store.set_state(IMAGES_KEY, "0")
    store.set_state(ASSETS_KEY, "")
    store.set_state(PAGES_READ_KEY, "")
    store.set_state(RESPONSES_KEY, "")
    return reply
