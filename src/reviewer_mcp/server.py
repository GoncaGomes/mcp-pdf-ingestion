"""reviewer-mcp: the tools for reading one PDF submission as evidence.

Each PDF is opened once into a deterministic store (text, parts, outline, numbered items). Tools address a paper by its
file name and PDF page numbers, and never expose files, caches or scratch paths. Descriptions and replies are kept
short: they share the agent's context with the paper itself.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from functools import wraps
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from mcp.types import TextContent
from pydantic import Field

from reviewer_mcp import crops, reading
from reviewer_mcp.config import load_section
from reviewer_mcp.papers import (
    ASSETS_KEY,
    IMAGES_KEY,
    ReviewError,
    overview,
    page_span,
    part_range,
    resolve_paper,
)
from reviewer_mcp.runner import run_server
from reviewer_mcp.store import PaperStore

INSTRUCTIONS = """\
Read one PDF submission as evidence. Every tool takes 'paper', the PDF file name in papers/; page numbers are PDF page
numbers; files, caches and extraction are handled internally.
- get_paper_overview: title, page count, full-PDF outline with section ids, numbered-item counts and extraction
  warnings. Call it first.
- read_pages: whole pages in reading order; continue with the next cursor until it is none.
- read_section: one outline section by its heading.
- search_paper: pages and snippets where a term is mentioned.
- list_assets, get_asset: numbered figures, tables, equations, algorithms and references, with content as text and
  citing sentences; get_asset attaches a cropped image when requested and images are enabled.
"""

# Reply budgets, not layout heuristics.
MENTION_ITEMS = 12
MENTION_CONTEXT = 100
CAPTION_PREVIEW = 140

mcp = FastMCP("reviewer", instructions=INSTRUCTIONS)

Paper = Annotated[str, Field(max_length=255, description="PDF file name in papers/, as given in the task.")]
Part = Annotated[
    Literal["manuscript", "responses", "cover", "all"],
    Field(description="Pages to use: a detected part (manuscript, responses or cover) or all."),
]
AssetKind = Literal["figure", "table", "equation", "algorithm", "listing", "statement", "reference"]


def _agent_errors[F: Callable[..., Any]](func: F) -> F:
    """Report problems the caller can fix as tool errors whose message says what to do."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (ReviewError, FileNotFoundError, ValueError) as error:
            raise ToolError(str(error)) from error

    return wrapper  # type: ignore[return-value]


def _open(paper: str) -> tuple[Any, PaperStore]:
    pdf = resolve_paper(paper)
    return pdf, PaperStore.open(pdf)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def get_paper_overview(paper: Paper) -> dict[str, Any]:
    """Call first. Returns the document identity, page count, the extracted title when one is found, the full-PDF
    outline with section ids, numbered-item counts and extraction warnings."""
    pdf, store = _open(paper)
    return overview(store, pdf)


@mcp.tool(annotations={"destructiveHint": False, "idempotentHint": True})
@_agent_errors
def read_pages(
    paper: Paper,
    first_page: Annotated[int | None, Field(ge=1, description="First PDF page; omit for the part's start.")] = None,
    last_page: Annotated[int | None, Field(ge=1, description="Last PDF page; omit for the part's end.")] = None,
    part: Part = "manuscript",
    cursor: Annotated[
        str | None, Field(max_length=20, description="next cursor of the previous reply; overrides the pages.")
    ] = None,
) -> str:
    """Read whole pages in reading order (about 12,000 characters per call); with part='manuscript' the reference list
    entries are left out (list_assets(kind='reference') lists them). The first line gives the pages returned and the
    next cursor: pass it as cursor until it is none. Pages already returned since the last get_paper_overview are not
    sent again."""
    _, store = _open(paper)
    part_first, part_last = part_range(store, part)
    scope = f"{part} = pages {page_span(part_first, part_last)}"
    offset = 0
    if cursor:
        first, offset = reading.parse_cursor(cursor)
        last = max(part_last, first)
    else:
        first = first_page or part_first
        last = last_page or (part_last if first <= part_last else first)
    last = min(last, store.page_count)
    omission = reading.REFERENCES_OMITTED if part == "manuscript" else ""
    if offset == 0 and 1 <= first <= last:
        returned = reading.pages_returned(store, bool(omission))
        unread = next((page for page in range(first, last + 1) if page not in returned), None)
        if unread is None:
            return (
                f"Pages {page_span(first, last)} were already returned. Use search_paper or "
                "read_section to check a detail and get_asset for a numbered item."
            )
        first = unread
    text, pages = reading.read_pages(store, first, last, offset, scope, omission)
    reading.record_returned(store, pages, bool(omission))
    return text


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def read_section(
    paper: Paper,
    heading: Annotated[
        str,
        Field(
            min_length=1,
            max_length=120,
            description="Outline heading, e.g. 'Introduction', 'IV. Experiments', '3.2'; case and numbering ignored.",
        ),
    ],
) -> str:
    """Read one outline section by its heading, up to the next heading of the same or higher level. If nothing
    matches, the error lists the headings."""
    _, store = _open(paper)
    first, last = part_range(store, "manuscript")
    return reading.read_section(store, heading, first, last)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def search_paper(
    paper: Paper,
    query: Annotated[
        str,
        Field(
            min_length=2,
            max_length=120,
            description="Words matched from their start, case-insensitive: a term, dataset, 'Table 3', a number.",
        ),
    ],
    part: Part = "manuscript",
    max_hits: Annotated[int, Field(ge=1, le=40, description="Maximum hits returned.")] = 15,
) -> dict[str, Any]:
    """Find where something is mentioned: the number of matching paragraphs and, per hit, PDF page, section and
    snippet."""
    _, store = _open(paper)
    first, last = part_range(store, part)
    return reading.search(store, query, first, last, max_hits)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def list_assets(
    paper: Paper,
    kind: Annotated[AssetKind | None, Field(description="Only this kind; omit for all kinds but references.")] = None,
) -> dict[str, Any]:
    """List the numbered items of the part (default: manuscript): id, label, page, caption start and how many
    paragraphs cite it; never-cited ids under 'uncited'. Choose what to inspect with get_asset."""
    _, store = _open(paper)
    first, last = part_range(store, "manuscript")
    everything = store.assets(first=first, last=last)
    shown = [a for a in everything if (a["kind"] == kind if kind else a["kind"] != "reference")]
    items = []
    for item in shown:
        entry: dict[str, Any] = {
            "id": item["id"],
            "label": item["label"],
            "page": page_span(item["page"], item["last_page"]),
            "cited": item["cited"],
        }
        preview = " ".join((item["caption"] or item["content"]).split())
        if preview:
            entry["caption"] = preview[:CAPTION_PREVIEW]
        if item["confidence"] == "low":
            entry["region"] = "not located (caption only)"
        items.append(entry)
    reply: dict[str, Any] = {
        "manuscript_pages": page_span(first, last),
        "counts": dict(sorted(Counter(a["kind"] for a in everything).items())),
        "items": items,
        "uncited": [a["id"] for a in shown if a["cited"] == 0],
    }
    if not kind and any(a["kind"] == "reference" for a in everything):
        reply["hint"] = "References are listed with kind='reference'."
    return reply


@mcp.tool(annotations={"readOnlyHint": True})
@_agent_errors
def get_asset(
    paper: Paper,
    asset: Annotated[
        str,
        Field(
            pattern=r"^[a-z]+:[A-Za-z0-9.]+$",
            description="Item id from list_assets, e.g. 'figure:3', 'table:II', 'theorem:1', 'reference:12'.",
        ),
    ],
    include_image: Annotated[
        bool, Field(description="Attach a cropped image, if images are enabled on this server (a few per paper).")
    ] = False,
) -> list[Any]:
    """Inspect one numbered item: caption and content as text (table cells as Markdown, equations as linear text and
    MathML, algorithm lines, theorem-like statements with their proof, reference entry), how it was located, and the
    sentences citing it. Each item is returned in full once until the next get_paper_overview."""
    pdf, store = _open(paper)
    first, last = part_range(store, "manuscript")
    found = store.asset(asset, first, last)
    if found is None:
        elsewhere = store.asset(asset)
        where = f" It exists on page {elsewhere['page']}, outside the part selected." if elsewhere else ""
        raise ReviewError(
            f"No item {asset!r} in the selected part (pages {page_span(first, last)}).{where} "
            "Call list_assets for valid ids."
        )
    budget = int(load_section("replies")["asset_budget"])
    inspected: list[str] = []

    def claim(value: str | None) -> str:
        # one locked step, so parallel get_asset calls of one turn never exceed the budget
        inspected.extend(item for item in (value or "").split(",") if item)
        if found["id"] in inspected or len(inspected) >= budget:
            return value or ""
        return ",".join([*inspected, found["id"]])

    store.update_state(ASSETS_KEY, claim)
    if found["id"] in inspected and not include_image:
        return [TextContent(type="text", text=f"{found['id']} was already returned.")]
    if found["id"] not in inspected and len(inspected) >= budget:
        return [
            TextContent(
                type="text",
                text=(
                    f"The budget of {budget} items is used ({', '.join(inspected)}). Rely on the list_assets "
                    "captions and search_paper for other items."
                ),
            )
        ]
    mentions = found["mentions"]
    paragraphs: dict[int, str] = {}
    for page_no in sorted({m["page"] for m in mentions[:MENTION_ITEMS]}):
        paragraphs.update({p["id"]: p["text"] for p in store.paragraphs(page_no, page_no)})
    cited_by = []
    for mention in mentions[:MENTION_ITEMS]:
        text = paragraphs.get(mention["paragraph"], "")
        at = max(text.find(mention["text"]), 0)
        context = text[max(0, at - MENTION_CONTEXT) : at + len(mention["text"]) + MENTION_CONTEXT]
        entry = {"page": mention["page"], "text": " ".join(context.split())}
        if mention["strength"] == "weak":
            entry["certainty"] = "weak (bare number)"
        cited_by.append(entry)
    detail: dict[str, Any] = {
        "id": found["id"],
        "label": found["label"],
        "page": page_span(found["page"], found["last_page"]),
        "caption": found["caption"],
        "content": found["content"],
        "format": found["content_format"],
        "located_by": f"{found['method']} ({found['confidence']} confidence)",
        "cited_count": len(mentions),
        "cited_by": cited_by,
    }
    image: Image | None = None
    images = crops.settings()
    if not include_image:
        detail["image"] = "not requested"
    elif not images["enabled"]:
        detail["image"] = "not attached: images are disabled on this server; rely on the caption and content"
    elif found["x0"] is None:
        detail["image"] = "not attached: no region was located for this item"
    else:
        used = int(store.get_state(IMAGES_KEY) or 0)
        if used >= images["budget"]:
            detail["image"] = f"not attached: the budget of {images['budget']} images for this paper is used"
        else:
            bbox = (found["x0"], found["y0"], found["x1"], found["y1"])
            image = Image(data=crops.crop_png(pdf, found["page"], bbox, int(images["max_side"])), format="png")
            store.set_state(IMAGES_KEY, str(used + 1))
            detail["image"] = f"attached ({used + 1} of {images['budget']})"
    text = TextContent(type="text", text=json.dumps(detail, ensure_ascii=False))
    return [text, image] if image is not None else [text]


def main() -> None:
    """Console script entry point for reviewer-mcp."""
    run_server(mcp)


if __name__ == "__main__":
    main()
