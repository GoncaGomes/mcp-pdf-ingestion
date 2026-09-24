"""reviewer-mcp: the tools a review agent uses to read one submission and publish a valid report.

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

from reviewer_mcp import crops, reading, reports, responses
from reviewer_mcp.config import DEFAULT_BASE_REVIEW_PATH, DEFAULT_FORMS_DIR, load_section, workspace
from reviewer_mcp.papers import (
    ASSETS_KEY,
    IMAGES_KEY,
    ReviewError,
    overview,
    page_span,
    part_range,
    resolve_paper,
    reviewer_notes,
    title,
)
from reviewer_mcp.profile import build_profile
from reviewer_mcp.runner import run_server
from reviewer_mcp.store import PaperStore
from reviewer_mcp.venues import VenueIndex, load_index

INSTRUCTIONS = """\
Read one paper submission and publish a validated review report. Every tool takes 'paper', the PDF file name in
papers/; page numbers are PDF page numbers; files, caches and extraction are handled internally.
- get_paper_overview: title, venue resolved from submission metadata, parts (cover, manuscript copies, author
  responses), manuscript pages, review round, reviewer notes, outline and numbered-item counts. Call it first.
- set_manuscript_pages: correct the manuscript page range when the overview chose the wrong copy.
- read_pages: whole pages in reading order; continue with the next cursor until it is none.
- read_section: one outline section by its heading.
- search_paper: pages and snippets where a term is mentioned.
- get_author_responses: the authors' answers to previous reviews (revisions), by reviewer or text.
- list_assets, get_asset: numbered figures, tables, equations, algorithms and references, with content as text,
  citing sentences and an optional cropped image.
- get_review_guideline: the venue's review criteria; form_only=true returns the report skeleton with the venue form.
- submit_report: validate the complete report; it is published to reports/ only when valid.
- update_report_field: replace one answer of the last draft, validate again and publish when valid.
"""

# Reply budgets, not layout heuristics.
MENTION_ITEMS = 12
MENTION_CONTEXT = 100
CAPTION_PREVIEW = 140
EVIDENCE_ITEMS = 6
REVIEW_VENUE_KEY = "review_venue"  # the venue whose guideline the review follows

mcp = FastMCP("reviewer", instructions=INSTRUCTIONS)

Paper = Annotated[str, Field(max_length=255, description="PDF file name in papers/, as given in the task.")]
Part = Annotated[
    Literal["manuscript", "responses", "cover", "all"],
    Field(description="Pages to use: manuscript (under review), responses (letter), cover or all."),
]
AssetKind = Literal["figure", "table", "equation", "algorithm", "listing", "statement", "reference"]


def _agent_errors[F: Callable[..., Any]](func: F) -> F:
    """Report problems the agent can fix as tool errors whose message says what to do."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (ReviewError, FileNotFoundError, ValueError) as error:
            raise ToolError(str(error)) from error

    return wrapper  # type: ignore[return-value]


def _venue_index() -> VenueIndex:
    root = workspace()
    return load_index(root / DEFAULT_FORMS_DIR, root / DEFAULT_BASE_REVIEW_PATH)


def _venue_summary(resolution: dict[str, Any]) -> dict[str, Any]:
    venue_id = resolution["venue_id"]
    summary = {key: resolution[key] for key in ("status", "venue_id", "name", "kind", "confidence")}
    summary["evidence"] = [
        f"{e['strength']}: {e['detail']} ({e['source']})"
        for e in resolution["evidence"]
        if not venue_id or e["venue_id"] == venue_id
    ][:EVIDENCE_ITEMS]
    for key in ("candidates", "conflicts", "index_problems"):
        if resolution[key]:
            summary[key] = resolution[key]
    return summary


def _abort_reason(resolution: dict[str, Any], explicit: str) -> str:
    if resolution["status"] == "ambiguous":
        return f"the submission metadata matches several venues {[c['venue_id'] for c in resolution['candidates']]}"
    if explicit:
        return f"venue {explicit[:64]!r} cannot be used for this paper"
    return "missing venue form: no form in forms/ matches the submission metadata"


def _open(paper: str) -> tuple[Any, PaperStore]:
    pdf = resolve_paper(paper)
    return pdf, PaperStore.open(pdf)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def get_paper_overview(paper: Paper) -> dict[str, Any]:
    """Call first. Returns title, page count, venue resolved from submission metadata, submission parts with page
    ranges, the manuscript pages under review and why, review round, reviewer notes, outline with pages and
    numbered-item counts. If venue.status is not 'resolved', stop unless the task names the venue."""
    pdf, store = _open(paper)
    venue = _venue_summary(_venue_index().resolve(build_profile(pdf)))
    return overview(store, pdf, venue)


@mcp.tool(annotations={"destructiveHint": False, "idempotentHint": True})
@_agent_errors
def set_manuscript_pages(
    paper: Paper,
    first_page: Annotated[int, Field(ge=1, description="First PDF page of the manuscript.")],
    last_page: Annotated[int, Field(ge=1, description="Last PDF page, including references.")],
    reason: Annotated[
        str, Field(min_length=5, max_length=300, description="Evidence that the detected range is wrong.")
    ],
) -> dict[str, Any]:
    """Correct the manuscript page range only when the overview chose the wrong part (e.g. the marked-up copy).
    All reading tools then use it. Returns the updated overview; mention the correction under limitations."""
    pdf, store = _open(paper)
    store.set_manuscript_pages(first_page, last_page, reason)
    return overview(store, pdf, _venue_summary(_venue_index().resolve(build_profile(pdf))))


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
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
    """Read whole pages in reading order (about 12,000 characters per call); the manuscript leaves out the reference
    list entries (see list_assets). The first line gives the pages returned and the next cursor: pass it as cursor
    until it is none. Nothing is skipped, and pages already returned in this review are not sent again."""
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
                f"Pages {page_span(first, last)} were already returned in this review. Use search_paper or "
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
    """Read one manuscript section by its outline heading, up to the next heading of the same or higher level. If
    nothing matches, the error lists the headings."""
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
def get_author_responses(
    paper: Paper,
    reviewer: Annotated[int | None, Field(ge=1, le=99, description="Reviewer number from 'reviewers present'.")] = None,
    query: Annotated[
        str | None, Field(min_length=2, max_length=120, description="Only comment/answer items with this text.")
    ] = None,
) -> str:
    """Revisions only: the authors' response letter. Without filters returns the reviewers present and the letter
    opening. Each paragraph is returned once per review. Verify every claimed change in the manuscript; do not trust
    the letter alone."""
    _, store = _open(paper)
    return responses.author_responses(store, reviewer, query)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def list_assets(
    paper: Paper,
    kind: Annotated[AssetKind | None, Field(description="Only this kind; omit for all kinds but references.")] = None,
) -> dict[str, Any]:
    """List the numbered items of the manuscript: id, label, page, caption start and how many paragraphs cite it;
    never-cited ids under 'uncited'. Choose what to inspect with get_asset."""
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
    """Inspect one numbered item: caption and content as text (table cells as Markdown, equations as linear text
    and MathML, algorithm lines, theorem-like statements with their proof, reference entry), how it was located,
    and the sentences citing it. Check that numbers quoted in the text match it. A review inspects a limited number
    of items, each once."""
    pdf, store = _open(paper)
    first, last = part_range(store, "manuscript")
    found = store.asset(asset, first, last)
    if found is None:
        elsewhere = store.asset(asset)
        where = f" It exists on page {elsewhere['page']}, outside the manuscript under review." if elsewhere else ""
        raise ReviewError(
            f"No item {asset!r} in the manuscript (pages {page_span(first, last)}).{where} "
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
        return [TextContent(type="text", text=f"{found['id']} was already returned in this review.")]
    if found["id"] not in inspected and len(inspected) >= budget:
        return [
            TextContent(
                type="text",
                text=(
                    f"The budget of {budget} items per review is used ({', '.join(inspected)}). Rely on the list_assets "
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


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
@_agent_errors
def get_review_guideline(
    paper: Paper,
    venue: Annotated[
        str | None,
        Field(
            pattern=r"^$|^[a-z0-9][a-z0-9_-]{1,63}$",
            description="Venue id only when the task names it; omit to use the venue resolved from metadata.",
        ),
    ] = None,
    form_only: Annotated[
        bool, Field(description="true = only the report skeleton with the venue form (call right before drafting).")
    ] = False,
) -> dict[str, Any]:
    """The venue's review criteria: philosophy, audit checkpoints and report rules. form_only=true returns the report
    skeleton instead: mandated sections, pre-filled Metadata, Quality Matrix rows and one 'Label: <to fill: ...>'
    entry per venue form field. If status is not 'resolved', stop."""
    pdf, store = _open(paper)
    index = _venue_index()
    explicit = (venue or "").strip()
    resolution = index.resolve(build_profile(pdf), explicit=explicit or None)
    if resolution["status"] != "resolved":
        return {
            "status": resolution["status"],
            "venue": _venue_summary(resolution),
            "error": f"STRICT ABORT: {_abort_reason(resolution, explicit)}. Do not produce a review.",
        }
    venue_id = resolution["venue_id"]
    store.set_state(REVIEW_VENUE_KEY, venue_id)
    if not form_only:
        return {
            "status": "resolved",
            "venue_id": venue_id,
            "guideline": index.guideline(venue_id),
            "next": "Read the paper; right before drafting call get_review_guideline(form_only=true).",
        }
    structure = store.structure()
    round_status = structure.get("round") or ""
    label = structure.get("round_label") or ""
    status = {"revision": f"Revision{f' ({label})' if label else ''}", "first": "First submission"}.get(
        round_status, "First submission (no revision evidence found)"
    )
    return {
        "status": "resolved",
        "venue_id": venue_id,
        "skeleton": reports.skeleton(
            paper=pdf.name,
            title=title(store),
            venue_name=resolution["name"],
            venue_id=venue_id,
            status=status,
            notes=reviewer_notes(pdf),
            form=index.form_fields(venue_id),
        ),
        "next": "Replace every '<to fill: ...>' placeholder with the answer only (no options or help text), then "
        "submit_report.",
    }


def _review_venue(index: VenueIndex, pdf: Any, store: PaperStore) -> str:
    """The venue a report may be published for: the one whose guideline get_review_guideline returned (an explicit
    venue named by the task, else the venue resolved from metadata). A report cannot choose its own venue."""
    recorded = store.get_state(REVIEW_VENUE_KEY)
    if recorded and index.get(recorded) is not None:
        return recorded
    resolution = index.resolve(build_profile(pdf))
    if resolution["status"] != "resolved":
        raise ReviewError(f"STRICT ABORT: {_abort_reason(resolution, '')}. The report cannot be published.")
    return str(resolution["venue_id"])


@mcp.tool(annotations={"destructiveHint": False})
@_agent_errors
def submit_report(
    paper: Paper,
    report: Annotated[
        str,
        Field(min_length=200, max_length=100_000, description="The complete report in Markdown, from the skeleton."),
    ],
    dry_run: Annotated[bool, Field(description="true = validate only.")] = False,
) -> dict[str, Any]:
    """Validate the complete report and publish it to reports/ only if it passes. Otherwise the draft is kept and
    every problem is listed: fix single fields with update_report_field. The review is done when published is true."""
    pdf, store = _open(paper)
    index = _venue_index()
    return reports.submit(store, pdf, report, index, _review_venue(index, pdf, store), dry_run)


@mcp.tool(annotations={"destructiveHint": False})
@_agent_errors
def update_report_field(
    paper: Paper,
    field: Annotated[
        str,
        Field(
            min_length=2,
            max_length=200,
            description="Form field label as in the skeleton, or 'Quality Matrix: <criterion>'.",
        ),
    ],
    answer: Annotated[
        str, Field(min_length=1, max_length=20_000, description="New answer text, or a matrix score 1-5.")
    ],
) -> dict[str, Any]:
    """Replace one answer of the last submitted draft, validate again and publish if the whole report now passes."""
    pdf, store = _open(paper)
    index = _venue_index()
    if not store.get_state(reports.DRAFT_KEY):
        raise ReviewError("There is no draft for this paper yet: call submit_report with the complete report first.")
    return reports.update_field(store, pdf, field, answer, index, _review_venue(index, pdf, store))


def main() -> None:
    """Console script entry point for reviewer-mcp."""
    run_server(mcp)


if __name__ == "__main__":
    main()
