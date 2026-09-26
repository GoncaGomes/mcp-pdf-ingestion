"""reviewer-mcp: the tools for reading one configured PDF submission as evidence.

Each server process binds to one configured PDF (``PDF_INGESTION_PDF``) with its derived data in an isolated run
directory (``PDF_INGESTION_RUN_DIR``), loaded once at startup. The PDF is opened once into a deterministic store (text,
parts, outline, numbered items). Tools use PDF page numbers and never expose files, caches or scratch paths.
Descriptions and replies are kept short: they share the agent's context with the paper itself.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from mcp.types import TextContent
from pydantic import Field

from reviewer_mcp import crops, reading
from reviewer_mcp.config import DocumentConfig, load_document_config, load_section
from reviewer_mcp.papers import (
    ASSETS_KEY,
    IMAGES_KEY,
    ReviewError,
    overview,
    page_span,
    part_range,
)
from reviewer_mcp.runner import run_server
from reviewer_mcp.store import PaperStore

INSTRUCTIONS = """\
Read one PDF submission as evidence. The server is bound to one configured PDF; page numbers are PDF page numbers;
files, caches and extraction are handled internally.
- get_paper_overview: title, page count, full-PDF outline with section ids, numbered-item counts and extraction
  warnings. Call it first.
- read_pages: repeatable page-labelled text; continue with next_cursor until null.
- read_section: an outline section by ID, with complete continuation and page provenance.
- search_paper: paginated textual matches with pages, section IDs and snippets.
- list_assets, get_asset: numbered figures, tables, equations, algorithms and references, with content as text and
  citing sentences; get_asset attaches a cropped image when requested and images are enabled.
"""

# Reply budgets, not layout heuristics.
MENTION_ITEMS = 12
MENTION_CONTEXT = 100
CAPTION_PREVIEW = 140

mcp = FastMCP("reviewer", instructions=INSTRUCTIONS)

# The document bound to this process: set once at startup (main) or once per in-process test; never reread.
_DOCUMENT: DocumentConfig | None = None

AssetKind = Literal["figure", "table", "equation", "algorithm", "listing", "statement", "reference"]


def bind_document() -> DocumentConfig:
    """Bind this process to the configured document (PDF and run directory) and return the retained configuration.

    Called once by the entry point before serving, and once per in-process test after it patches the environment.
    Tool calls use the retained configuration and never reread the document settings.
    """
    global _DOCUMENT
    _DOCUMENT = load_document_config()
    return _DOCUMENT


def _agent_errors[F: Callable[..., Any]](func: F) -> F:
    """Report problems the caller can fix as tool errors whose message says what to do."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (ReviewError, FileNotFoundError, ValueError) as error:
            raise ToolError(str(error)) from error

    return wrapper  # type: ignore[return-value]


def _open() -> tuple[Path, PaperStore]:
    """The bound document's PDF and its store, built under the bound run directory on first use."""
    config = _DOCUMENT
    if config is None:
        raise RuntimeError("no document bound: start the server with PDF_INGESTION_PDF and PDF_INGESTION_RUN_DIR")
    return config.pdf_path, PaperStore.open(config.pdf_path, run_dir=config.run_dir)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True})
@_agent_errors
def get_paper_overview() -> dict[str, Any]:
    """Call first. Returns the document identity, page count, the extracted title when one is found, the full-PDF
    outline with section ids, numbered-item counts and extraction warnings."""
    pdf, store = _open()
    return overview(store, pdf)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def read_pages(
    first_page: Annotated[int | None, Field(ge=1, description="First PDF page; alone selects one page.")] = None,
    last_page: Annotated[int | None, Field(ge=1, description="Last PDF page; alone starts at page 1.")] = None,
    cursor: Annotated[
        str | None, Field(max_length=reading.CURSOR_LIMIT, description="Opaque next_cursor; pass unchanged.")
    ] = None,
) -> dict[str, Any]:
    """Read page-labelled text, including references (12,000 characters per call). Omit bounds for the whole PDF.
    Reads are repeatable. Continue with next_cursor until null; explicit bounds must agree with its original range."""
    _, store = _open()
    return reading.read_pages(store, first_page, last_page, cursor)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def read_section(
    section_id: Annotated[int, Field(ge=1, description="Section ID from get_paper_overview's outline.")],
    cursor: Annotated[
        str | None, Field(max_length=reading.CURSOR_LIMIT, description="Opaque next_cursor; pass unchanged.")
    ] = None,
) -> dict[str, Any]:
    """Read a section by ID, including subsections until the next equal/higher heading. Returns page-labelled
    fragments, section identity and next_cursor. Repeat the same section_id when continuing until null."""
    _, store = _open()
    return reading.read_section(store, section_id, cursor)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def search_paper(
    query: Annotated[
        str, Field(min_length=1, max_length=120, description="Case-insensitive FTS phrase; the final word is a prefix.")
    ],
    first_page: Annotated[int | None, Field(ge=1, description="First PDF page; alone selects one page.")] = None,
    last_page: Annotated[int | None, Field(ge=1, description="Last PDF page; alone starts at page 1.")] = None,
    cursor: Annotated[
        str | None, Field(max_length=reading.CURSOR_LIMIT, description="Opaque next_cursor; repeat the original query.")
    ] = None,
) -> dict[str, Any]:
    """Search all PDF text by default. Returns total matching paragraphs and up to 15 ordered snippets with page
    and section identity. Range filters use paragraph start pages. Continue with next_cursor until null;
    zero matches do not establish absence from the paper."""
    _, store = _open()
    return reading.search(store, query, first_page, last_page, cursor)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def list_assets(
    kind: Annotated[AssetKind | None, Field(description="Only this kind; omit for all kinds but references.")] = None,
) -> dict[str, Any]:
    """List the numbered items of the part (default: manuscript): id, label, page, caption start and how many
    paragraphs cite it; never-cited ids under 'uncited'. Choose what to inspect with get_asset."""
    _, store = _open()
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


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
@_agent_errors
def get_asset(
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
    pdf, store = _open()
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
    """Console script entry point for reviewer-mcp: bind the configured document, then serve."""
    bind_document()
    run_server(mcp)


if __name__ == "__main__":
    main()
