"""Deterministic text access with exact page/section continuation and paragraph search."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from reviewer_mcp.indexes import _join
from reviewer_mcp.papers import ReviewError, page_span
from reviewer_mcp.store import PaperStore

READ_BUDGET = 12_000  # characters per reply
CURSOR_LIMIT = 4096
SEARCH_PAGE_SIZE = 15  # matching paragraph records per reply, in stable paragraph ID order


def _encode_cursor(state: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(state, separators=(",", ":")).encode()).decode()


def _decode_cursor(cursor: str, document_id: str, operation: str, fields: set[str]) -> dict[str, Any]:
    message = "Invalid cursor: pass next_cursor from the previous reply unchanged, or restart without a cursor."
    try:
        if not cursor or len(cursor) > CURSOR_LIMIT:
            raise ValueError(message)
        state = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
    except (ValueError, UnicodeError, binascii.Error, RecursionError) as error:
        raise ReviewError(message) from error
    if not isinstance(state, dict) or not {"document_id", "operation"} <= set(state):
        raise ReviewError(message)
    if state["document_id"] != document_id or state["operation"] != operation:
        raise ReviewError("Cursor belongs to a different document or operation; restart without a cursor.")
    if set(state) != fields | {"document_id", "operation"}:
        raise ReviewError(message)
    return state


def page_range(total: int, first_page: int | None, last_page: int | None) -> tuple[int, int]:
    first = 1 if first_page is None else first_page
    last = (total if first_page is None else first) if last_page is None else last_page
    for value in (first, last):
        if type(value) is not int or not 1 <= value <= total:
            raise ReviewError(f"Page {value!r} is outside this PDF ({total} pages). Use pages between 1 and {total}.")
    if first > last:
        raise ReviewError(f"first_page {first} is after last_page {last}.")
    return first, last


def _cursor_range(state: dict[str, Any], total: int, first_page: int | None, last_page: int | None) -> tuple[int, int]:
    if type(state["first"]) is not int or type(state["last"]) is not int:
        raise ReviewError("Invalid cursor range; restart without a cursor.")
    first, last = page_range(total, state["first"], state["last"])
    for name, explicit, saved in (("first_page", first_page, first), ("last_page", last_page, last)):
        if explicit is not None and (type(explicit) is not int or explicit != saved):
            raise ReviewError(f"{name} conflicts with the cursor range; omit it or use {saved}.")
    return first, last


def _text_chunk(
    fragments: list[dict[str, Any]], index: int = 0, offset: int = 0
) -> tuple[list[dict[str, Any]], tuple[int, int] | None]:
    """Slice stored text exactly; index and offset always identify the next unreturned character."""
    if (
        type(index) is not int
        or type(offset) is not int
        or not 0 <= index < len(fragments)
        or offset < 0
        or (offset > 0 and offset >= len(fragments[index]["text"]))
    ):
        raise ReviewError("Invalid cursor position; restart without a cursor.")
    result: list[dict[str, Any]] = []
    room = READ_BUDGET
    while index < len(fragments):
        fragment = fragments[index]
        text = fragment["text"]
        if text and room == 0:
            return result, (index, offset)
        end = min(len(text), offset + room)
        result.append({"page": fragment["page"], "text": text[offset:end]})
        room -= end - offset
        if end < len(text):
            return result, (index, end)
        index, offset = index + 1, 0
    return result, None


def read_pages(
    store: PaperStore, first_page: int | None = None, last_page: int | None = None, cursor: str | None = None
) -> dict[str, Any]:
    """Repeatable reads of the selected stored pages, including empty pages and reference entries."""
    document_id = store.meta()["fingerprint"]
    index, offset = 0, 0
    if cursor is not None:
        state = _decode_cursor(cursor, document_id, "read_pages", {"first", "last", "index", "offset"})
        first, last = _cursor_range(state, store.page_count, first_page, last_page)
        index, offset = state["index"], state["offset"]
    else:
        first, last = page_range(store.page_count, first_page, last_page)
    pages = store.pages(first, last)
    fragments, position = _text_chunk(pages, index, offset)
    next_cursor = None
    if position is not None:
        next_cursor = _encode_cursor(
            {
                "document_id": document_id,
                "operation": "read_pages",
                "first": first,
                "last": last,
                "index": position[0],
                "offset": position[1],
            }
        )
    reply = {"document_id": document_id, "fragments": fragments, "next_cursor": next_cursor}
    empty = [
        {"page": p["page"], "source": p["source"]}
        for p in pages
        if not p["text"] and any(f["page"] == p["page"] for f in fragments)
    ]
    if empty:
        reply["empty_pages"] = empty
    return reply


def _paragraph_fragments(store: PaperStore, paragraph: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep the stored paragraph text while attributing cross-page joins to their source lines."""
    if paragraph["page"] == paragraph["last_page"]:
        return [{"page": paragraph["page"], "text": paragraph["text"]}]
    fragments: list[dict[str, Any]] = []
    for line in store.paragraph_lines(paragraph["id"]):
        text = line["text"].strip() if paragraph["kind"] == "heading" else line["text"]
        if not fragments:
            fragments.append({"page": line["page"], "text": text})
        elif fragments[-1]["page"] == line["page"]:
            fragments[-1]["text"] = _join(fragments[-1]["text"], text)
        else:
            # Reuse the extraction join rule: a dehyphenated word may straddle pages.
            previous = fragments[-1]["text"]
            joined = _join(previous, text)
            keep = len(previous) - (1 if previous.endswith("-") and text[:1].islower() else 0)
            fragments[-1]["text"] = previous[:keep]
            fragments.append({"page": line["page"], "text": joined[keep:]})
    if "".join(f["text"] for f in fragments) != paragraph["text"]:
        raise ReviewError(
            f"Cannot map stored paragraph {paragraph['id']} to source pages; "
            f"use read_pages for pages {paragraph['page']} through {paragraph['last_page']}."
        )
    return fragments


def read_section(store: PaperStore, section_id: int, cursor: str | None = None) -> dict[str, Any]:
    """Read the section's paragraphs, including subsections, with exact text and page provenance."""
    document_id = store.meta()["fingerprint"]
    index, offset = 0, 0
    if type(section_id) is not int:
        raise ReviewError("section_id must be an integer ID from get_paper_overview.")
    if cursor is not None:
        state = _decode_cursor(cursor, document_id, "read_section", {"section_id", "index", "offset"})
        if type(state["section_id"]) is not int or state["section_id"] != section_id:
            raise ReviewError("section_id conflicts with the cursor; use its original section ID or restart.")
        index, offset = state["index"], state["offset"]
    section = next((s for s in store.outline() if s["id"] == section_id), None)
    if section is None:
        raise ReviewError(
            f"Unknown section_id {section_id}; use an ID from get_paper_overview. "
            "If no outline was extracted, use read_pages or search_paper."
        )
    all_fragments: list[dict[str, Any]] = []
    for paragraph in store.section_paragraphs(section_id):
        parts = _paragraph_fragments(store, paragraph)
        if all_fragments:
            parts[0]["text"] = "\n\n" + parts[0]["text"]
        all_fragments.extend(parts)
    fragments, position = _text_chunk(all_fragments, index, offset)
    next_cursor = None
    if position is not None:
        next_cursor = _encode_cursor(
            {
                "document_id": document_id,
                "operation": "read_section",
                "section_id": section_id,
                "index": position[0],
                "offset": position[1],
            }
        )
    return {
        "document_id": document_id,
        "section": {key: section[key] for key in ("id", "number", "title", "level", "page")},
        "fragments": fragments,
        "next_cursor": next_cursor,
    }


def search(
    store: PaperStore,
    query: str,
    first_page: int | None = None,
    last_page: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Paginated FTS phrase hits with a final-word prefix; filters use each paragraph's starting PDF page."""
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ReviewError("query must contain 1–120 characters and cannot be blank.")
    document_id = store.meta()["fingerprint"]
    offset = 0
    if cursor is not None:
        state = _decode_cursor(cursor, document_id, "search_paper", {"query", "first", "last", "offset"})
        if state["query"] != query:
            raise ReviewError("query conflicts with the cursor; repeat the original query or restart without a cursor.")
        first, last = _cursor_range(state, store.page_count, first_page, last_page)
        offset = state["offset"]
        if type(offset) is not int or offset < 0:
            raise ReviewError("Invalid cursor result position; restart without a cursor.")
    else:
        first, last = page_range(store.page_count, first_page, last_page)
    total, hits = store.search(query, SEARCH_PAGE_SIZE, first, last, offset)
    if cursor is not None and offset >= total:
        raise ReviewError("Invalid cursor result position; restart without a cursor.")
    next_cursor = None
    if offset + len(hits) < total:
        next_cursor = _encode_cursor(
            {
                "document_id": document_id,
                "operation": "search_paper",
                "query": query,
                "first": first,
                "last": last,
                "offset": offset + len(hits),
            }
        )
    reply: dict[str, Any] = {
        "document_id": document_id,
        "query": query,
        "pages": page_span(first, last),
        "total_hits": total,
        "hits": [
            {
                "paragraph_id": h["id"],
                "page": h["page"],
                "section_id": h["section"] or None,
                "section_title": h["section_title"] or None,
                "snippet": h["snippet"],
            }
            for h in hits
        ],
        "next_cursor": next_cursor,
    }
    if total == 0:
        reply["hint"] = "No textual matches for this query and range. This does not establish absence from the paper."
    return reply
