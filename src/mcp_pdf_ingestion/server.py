"""mcp-pdf-ingestion: the tools for reading one configured PDF submission as evidence.

Each server process binds to one configured PDF (``PDF_INGESTION_PDF``) with its derived data in an isolated run
directory (``PDF_INGESTION_RUN_DIR``), loaded once at startup. The PDF is opened once into a deterministic store (text,
parts, outline, numbered items). Tools use PDF page numbers and never expose files, caches or scratch paths.
Descriptions and replies are kept short: they share the agent's context with the paper itself.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Literal, get_args

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import TextContent
from pydantic import Field

from mcp_pdf_ingestion import crops, reading, visual_inspection
from mcp_pdf_ingestion.config import DocumentConfig, load_document_config
from mcp_pdf_ingestion.papers import ReviewError, overview
from mcp_pdf_ingestion.runner import run_server
from mcp_pdf_ingestion.store import PaperStore

INSTRUCTIONS = """\
Read one PDF submission as evidence. The server is bound to one configured PDF; page numbers are PDF page numbers;
files, caches and extraction are handled internally.
- get_paper_overview: title, page count, full-PDF outline with section ids, numbered-item counts and extraction
  warnings. Call it first.
- read_pages: repeatable page-labelled text; continue with next_cursor until null.
- read_section: an outline section by ID, with complete continuation and page provenance.
- search_paper: paginated textual matches with pages, section IDs and snippets.
- list_assets: paginated numbered assets by default; kind=page selects physical pages, with range filters.
- get_asset: exact extracted content or page text; an explicit question requests one visual inspection.
"""

# Reply budgets, not layout heuristics.
MENTION_ITEMS = 12
MENTION_CONTEXT = 100
CAPTION_PREVIEW = 140
ASSET_PAGE_SIZE = 20  # assets per catalog response

mcp = FastMCP("mcp-pdf-ingestion", instructions=INSTRUCTIONS)

# The document bound to this process: set once at startup (main) or once per in-process test; never reread.
_DOCUMENT: DocumentConfig | None = None

AssetKind = Literal["figure", "table", "equation", "algorithm", "listing", "statement", "reference", "page"]


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

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except (ReviewError, FileNotFoundError, ValueError) as error:
                raise ToolError(str(error)) from error

        return async_wrapper  # type: ignore[return-value]

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


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
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


def _public_asset_id(item: dict[str, Any]) -> str:
    return f"segment:{item['segment']}/{item['id']}"


def _region_available(item: dict[str, Any]) -> bool:
    return all(item[key] is not None for key in ("x0", "y0", "x1", "y1"))


def _asset_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _public_asset_id(item),
        "label": item["label"],
        "kind": item["kind"],
        "first_page": item["page"],
        "last_page": item["last_page"],
        "caption_preview": " ".join(item["caption"].split())[:CAPTION_PREVIEW],
        "cited_count": item["cited"],
        "region_available": _region_available(item),
    }


def _page_entry(page: int) -> dict[str, Any]:
    return {
        "id": f"page:{page}",
        "label": f"Page {page}",
        "kind": "page",
        "first_page": page,
        "last_page": page,
        "region_available": True,
    }


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def list_assets(
    kind: Annotated[
        AssetKind | None, Field(description="Numbered kind, or page for full pages; omit for numbered assets.")
    ] = None,
    first_page: Annotated[int | None, Field(ge=1, description="First PDF page; alone selects one page.")] = None,
    last_page: Annotated[int | None, Field(ge=1, description="Last PDF page; alone starts at page 1.")] = None,
    cursor: Annotated[
        str | None, Field(max_length=reading.CURSOR_LIMIT, description="Opaque next_cursor; pass unchanged.")
    ] = None,
) -> dict[str, Any]:
    """List up to 20 assets with IDs and source spans. Default: numbered assets including references; page selects
    only full pages in ascending order. Inclusive ranges select overlap. Counts cover the full filtered result.
    Continue with next_cursor until null. Catalogs never render images or include full text."""
    _, store = _open()
    document_id = store.meta()["fingerprint"]
    offset = 0
    if cursor is not None:
        state = reading._decode_cursor(cursor, document_id, "list_assets", {"kind", "first", "last", "offset"})
        if kind is not None and kind != state["kind"]:
            raise ReviewError("kind conflicts with the cursor; omit it or repeat the original filter.")
        kind = state["kind"]
        first, last = reading._cursor_range(state, store.page_count, first_page, last_page)
        offset = state["offset"]
        if type(offset) is not int or offset < 0:
            raise ReviewError("Invalid cursor result position; restart without a cursor.")
    else:
        first, last = reading.page_range(store.page_count, first_page, last_page)
    if kind is not None and kind not in get_args(AssetKind):
        raise ReviewError(f"Invalid kind; use one of {get_args(AssetKind)} or omit it for all numbered assets.")
    counts = {"page": last - first + 1} if kind == "page" else store.asset_counts(kind, first, last)
    total = sum(counts.values())
    if cursor is not None and offset >= total:
        raise ReviewError("Invalid cursor result position; restart without a cursor.")
    if kind == "page":
        shown = [_page_entry(page) for page in range(first + offset, min(last + 1, first + offset + ASSET_PAGE_SIZE))]
    else:
        shown = [_asset_entry(item) for item in store.assets(kind, first, last, limit=ASSET_PAGE_SIZE, offset=offset)]
    next_cursor = None
    if offset + len(shown) < total:
        next_cursor = reading._encode_cursor(
            {
                "document_id": document_id,
                "operation": "list_assets",
                "kind": kind,
                "first": first,
                "last": last,
                "offset": offset + len(shown),
            }
        )
    return {
        "document_id": document_id,
        "items": shown,
        "total_assets": total,
        "counts": counts,
        "next_cursor": next_cursor,
    }


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "destructiveHint": False})
@_agent_errors
async def get_asset(
    asset_id: Annotated[
        str, Field(max_length=512, description="Canonical ID: segment:2/figure:1 or page:4 (physical PDF page).")
    ],
    question: Annotated[str | None, Field(description="Explicit non-blank question about the selected image.")] = None,
) -> list[TextContent]:
    """Return extracted content and source metadata. A question requests one fresh visual inspection with
    separate observations and diagnostics. Missing regions never fall back to a full page automatically."""
    if question is not None and (not isinstance(question, str) or not question.strip()):
        raise ReviewError("question must be a non-blank string, or omitted for deterministic content.")
    config = _DOCUMENT
    if config is None:
        raise RuntimeError("No document bound.")
    pdf, detail, bbox = await asyncio.to_thread(_resolve_asset, asset_id)
    return await _asset_response(pdf, detail, bbox, question, config.run_dir)


def _resolve_asset(asset_id: str) -> tuple[Path, dict[str, Any], crops.Bounds | None]:
    """Complete synchronous store reads before any model/network await."""
    page_match = re.fullmatch(r"page:([1-9][0-9]{0,17})", asset_id)
    match = re.fullmatch(r"segment:(0|[1-9][0-9]{0,17})/([a-z]+:[A-Za-z0-9.]+)", asset_id)
    if match is None and page_match is None:
        raise ReviewError("Invalid asset_id: use list_assets IDs, e.g. segment:2/figure:1 or page:4.")
    pdf, store = _open()
    if page_match is not None:
        page = int(page_match[1])
        reading.page_range(store.page_count, page, page)
        stored_page = store.pages(page, page)[0]
        detail = {
            **_page_entry(page),
            "document_id": store.meta()["fingerprint"],
            "content": stored_page["text"],
            "format": "text",
            "method": "page_text",
            "text_source": stored_page["source"],
            "page_label": stored_page["label"],
        }
        return pdf, detail, None
    assert match is not None
    found = store.asset(int(match[1]), match[2])
    if found is None:
        raise ReviewError(f"Unknown asset_id {asset_id!r}; call list_assets for valid IDs in this document.")
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
        "document_id": store.meta()["fingerprint"],
        "id": _public_asset_id(found),
        "kind": found["kind"],
        "label": found["label"],
        "first_page": found["page"],
        "last_page": found["last_page"],
        "caption": found["caption"],
        "content": found["content"],
        "format": found["content_format"],
        "method": found["method"],
        "confidence": found["confidence"],
        "cited_count": len(mentions),
        "cited_by": cited_by,
    }
    bbox = (found["x0"], found["y0"], found["x1"], found["y1"]) if _region_available(found) else None
    detail["region_available"] = _region_available(found)
    return pdf, detail, bbox


def _describe_asset(pdf: Path, detail: dict[str, Any], bbox: crops.Bounds | None) -> None:
    first, last = detail["first_page"], detail["last_page"]
    detail["source_page_ids"] = [f"page:{page}" for page in range(first, last + 1)]
    detail["rendered_pages"] = []
    detail["visual_coverage"] = "none"
    detail["limitations"] = (
        ["Only the first-page region is available for this multipage asset."] if last > first else []
    )
    if detail["region_available"]:
        region = crops.describe_region(pdf, first, bbox)
    else:
        region = {
            "available": False,
            "reason": "No stored region is available.",
            "coordinate_system": crops.COORDINATE_SYSTEM,
            "requested_bounds": None,
            "effective_bounds": None,
            "clipped": False,
        }
    detail["render"] = region
    detail["visual_available"] = region["available"]
    if region["clipped"]:
        detail["limitations"].append("The region was clipped to the visible page.")


async def _asset_response(
    pdf: Path,
    detail: dict[str, Any],
    bbox: crops.Bounds | None,
    question: str | None,
    run_dir: Path,
) -> list[TextContent]:
    try:
        await asyncio.to_thread(_describe_asset, pdf, detail, bbox)
    except (OSError, RuntimeError, ValueError):
        detail["visual_available"] = False
        detail["render"] = {"available": False, "reason": "Source geometry could not be read."}
    result: dict[str, Any] = {"status": "not_requested"}
    if question is not None:
        if not detail["visual_available"]:
            result = {"status": "unavailable", "reason": detail["render"]["reason"]}
        else:

            def render() -> bytes:
                max_side = crops.settings()["max_side"]
                detail["render_settings"] = {
                    "max_side": max_side,
                    "renderer_version": crops.RENDERER_VERSION,
                    "colorspace": "RGB",
                    "alpha": False,
                }
                return crops.cached_png(
                    pdf,
                    detail["first_page"],
                    bbox,
                    max_side,
                    run_dir=run_dir,
                    document_id=detail["document_id"],
                    asset_id=detail["id"],
                    region=detail["render"],
                )

            try:
                data = await asyncio.to_thread(render)
            except crops.ImagePersistenceError:
                result = {"status": "image_persistence_error", "reason": "Required PNG persistence failed."}
            except (OSError, RuntimeError, ValueError):
                result = {"status": "render_error", "reason": "Selected image rendering failed."}
            else:
                detail["rendered_pages"] = [detail["first_page"]]
                detail["visual_coverage"] = (
                    "partial"
                    if detail["last_page"] > detail["first_page"] or detail["render"]["clipped"]
                    else "single_page"
                )
                result = await visual_inspection.inspect_image(
                    png=data,
                    question=question,
                    context=detail,
                    image_reference=crops.image_reference(detail["document_id"], detail["id"]),
                    run_dir=run_dir,
                )
    detail["visual"] = {
        **result,
        "source_page_ids": detail["source_page_ids"],
        "rendered_pages": detail["rendered_pages"],
        "visual_coverage": detail["visual_coverage"],
        "render": detail["render"],
        "limitations": detail["limitations"],
    }
    return [TextContent(type="text", text=json.dumps(detail, ensure_ascii=False))]


def main() -> None:
    """Console script entry point for mcp-pdf-ingestion: bind the configured document, then serve."""
    bind_document()
    run_server(mcp)


if __name__ == "__main__":
    main()
