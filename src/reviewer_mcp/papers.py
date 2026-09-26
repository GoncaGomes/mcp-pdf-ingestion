"""Parts, title and overview of the document bound to the server process.

The server binds one configured PDF per process (see ``config.DocumentConfig``); page numbers are PDF page
numbers everywhere.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from reviewer_mcp.heuristics import SAME_SIZE
from reviewer_mcp.store import PaperStore

# Reply budgets (characters or items), not layout heuristics.
TITLE_BUDGET = 300
IMAGES_KEY = "images_sent"
ASSETS_KEY = "assets_returned"  # item ids get_asset returned in full during the current review


class ReviewError(ValueError):
    """A request the agent can correct; the message says how."""


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


def overview(store: PaperStore, pdf: Path) -> dict[str, Any]:
    """Everything needed to plan the reading of the document, over the whole PDF, in PDF page numbers."""
    outline = [
        {"id": s["id"], "level": s["level"], "number": s["number"], "title": s["title"], "page": s["page"]}
        for s in store.outline()
    ]
    assets = store.assets()
    reply: dict[str, Any] = {
        "paper": pdf.name,
        "document_id": store.meta()["fingerprint"],
        "pdf_pages": store.page_count,
        "title": title(store),
        "outline": outline,
        "numbered_items": dict(sorted(Counter(a["kind"] for a in assets).items())),
    }
    unreadable = [p["page"] for p in store.pages() if p["source"] == "none"]
    if unreadable:
        reply["warnings"] = [f"pages {unreadable} have no text layer (e.g. scanned images); their text cannot be read"]
    # Overview still resets the image and item budgets until MCP-06.
    store.set_state(IMAGES_KEY, "0")
    store.set_state(ASSETS_KEY, "")
    return reply
