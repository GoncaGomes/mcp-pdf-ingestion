"""Submission profile: deterministic identification facts extracted from a PDF.

The profile feeds venue resolution. Only submission-system and publisher traces are collected, all read from the
paper store (``store.py``): file facts, document metadata, running heads and footers (the store's header and footer
regions, i.e. text repeated across pages, see ``document.py``), labelled fields on cover sheets and on the first
page of every other submission part (see ``structure.py``), and DOIs printed in those places. The manuscript body
(title, abstract, sections, references) is never scanned, so words in the paper cannot select a venue.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import pymupdf as fitz

from reviewer_mcp.papers import paper_stem
from reviewer_mcp.store import PaperStore

# Reply budget for the profile (not a layout heuristic).
MAX_STAMP_CHARS = 200
MAX_STAMPS = 40

DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>,;]+")
# Labelled fields. Generic words need a colon, "submitted to" needs its subject and a DOI needs its label,
# so wrapped body sentences that happen to start a line with them do not count.
COVER_LABEL_RE = re.compile(
    r"^(?:(?:manuscript|submission|paper|article)\s+(?:number|id|no\.?|version|type)\b"
    r"|(?:journal(?:\s+name)?|conference|event|track)\s*:"
    r"|for\s+consideration\s+in\b"
    r"|(?:this\s+)?(?:paper|manuscript|article|preprint)\s+(?:has\s+been\s+|was\s+|is\s+)?submitted\s+to\b"
    r"|(?:doi|digital\s+object\s+identifier)\s*:?\s*(?=10\.\d))",
    re.IGNORECASE,
)
EM_BANNER_RE = re.compile(r"--\s*manuscript\s+draft\s*--", re.IGNORECASE)
RUNNING_HEAD_RE = re.compile(r"\bet\s+al\.?\s*:", re.IGNORECASE)
XMP_TAGS = ("prism:publicationName", "prism:doi", "prism:url", "dc:source", "pdfx:doi", "crossmark:DOI")


def _clean(text: str) -> str:
    return " ".join(text.split())


class _Stamps:
    """Collects stamp lines, merging repeats (digits ignored) and recording pages."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    def add(self, text: str, source: str, page: int | None = None) -> None:
        text = _clean(text)
        if len(re.findall(r"[A-Za-z]", text)) < 2 or len(text) > MAX_STAMP_CHARS:
            return
        key = (source, re.sub(r"\d+", "#", text.casefold()))
        entry = self._items.setdefault(key, {"text": text, "source": source, "pages": []})
        if page is not None and page not in entry["pages"]:
            entry["pages"].append(page)

    def items(self) -> list[dict[str, Any]]:
        return list(self._items.values())


def _cover_fields(lines: list[dict[str, Any]], page_no: int, stamps: _Stamps) -> None:
    """Labelled fields with their values (store lines of one page in reading order). Submission forms print the
    value on the label's row; other layouts continue after the label or on the next line."""
    texts = [_clean(line["text"]) for line in lines]
    for i, line in enumerate(lines):
        text = texts[i]
        m = COVER_LABEL_RE.match(text)
        if not m:
            continue
        if not text[m.end() :].strip(" :\t-"):
            row = sorted(
                (
                    other
                    for other in lines
                    if other is not line
                    and other["x0"] >= line["x1"]
                    and line["y0"] <= (other["y0"] + other["y1"]) / 2 <= line["y1"]
                ),
                key=lambda other: other["x0"],
            )
            if row:
                text = " ".join([text, *(_clean(other["text"]) for other in row)])
            elif i + 1 < len(lines):
                text = f"{text} {texts[i + 1]}"
        stamps.add(text, "cover", page_no)
    if texts and any(EM_BANNER_RE.search(text) for text in texts):
        stamps.add(texts[0], "cover", page_no)  # Editorial Manager prints the journal name above the banner


def _xmp_values(xmp: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for tag in XMP_TAGS:
        for m in re.finditer(rf"<{tag}>(.*?)</{tag}>|{tag}=\"([^\"]*)\"", xmp, re.DOTALL):
            value = _clean(re.sub(r"<[^>]+>", " ", m.group(1) or m.group(2) or ""))
            if value:
                values.append((tag, value))
    return values


def build_profile(pdf_path: str | Path) -> dict[str, Any]:
    """Return the submission profile of a PDF, read from its paper store."""
    path = Path(pdf_path).resolve()
    store = PaperStore.open(path)
    st = path.stat()

    stamps = _Stamps()
    for page_no in range(1, store.page_count + 1):
        for line in store.lines(page_no, ("header", "footer")):
            if not RUNNING_HEAD_RE.search(line["text"]):
                stamps.add(line["text"], line["region"], page_no)

    segments = store.segments()
    field_pages = {segment["first_page"] for segment in segments}
    field_pages.update(
        page_no
        for segment in segments
        if segment["kind"] == "cover"
        for page_no in range(segment["first_page"], segment["last_page"] + 1)
    )
    for page_no in sorted(field_pages):
        _cover_fields(store.lines(page_no, ("body",)), page_no, stamps)

    with fitz.open(str(path)) as doc:
        meta = {k: str(v).strip() for k, v in (doc.metadata or {}).items() if v}
        xmp = doc.get_xml_metadata() or ""
    if meta.get("subject"):
        stamps.add(meta["subject"], "metadata")
    for tag, value in _xmp_values(xmp):
        stamps.add(value, f"xmp:{tag}")

    stamp_list = sorted(stamps.items(), key=lambda s: (-len(s["pages"]), s["pages"][:1], s["text"]))[:MAX_STAMPS]
    dois: list[dict[str, str]] = []
    seen: set[str] = set()
    for stamp in stamp_list:
        for m in DOI_RE.finditer(stamp["text"]):
            doi = m.group(0).rstrip(".)")
            if doi.lower() not in seen:
                seen.add(doi.lower())
                dois.append({"doi": doi, "source": stamp["source"]})

    return {
        "file": {
            "name": path.name,
            "stem": paper_stem(path),
            "size_bytes": st.st_size,
            "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
            "sha256": store.meta()["fingerprint"][:16],
        },
        "pdf": {
            "pages": store.page_count,
            "producer": meta.get("producer", ""),
            "creator": meta.get("creator", ""),
            "created": meta.get("creationDate", ""),
            "modified": meta.get("modDate", ""),
        },
        "stamps": stamp_list,
        "dois": dois,
    }
