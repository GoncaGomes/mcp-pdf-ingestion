"""On-demand PDF images in the page's displayed orientation.

Stored bounds come from PyMuPDF text/drawing/table extraction: points, top-left
origin of the visible page, x right, y down, before page rotation. They are not
MediaBox coordinates. Intersect in that space, then rotate for get_pixmap's clip.
"""

from __future__ import annotations

import json
import math
import os
import re
import struct
import tempfile
import threading
import zlib
from pathlib import Path
from typing import Any

import pymupdf as fitz
from pymupdf.mupdf import FzErrorBase

from reviewer_mcp.config import load_section

COORDINATE_SYSTEM = "pymupdf_unrotated_visible_page_points"
Bounds = tuple[float, float, float, float]
RENDERER_VERSION = 1
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_METADATA_KEY = b"pdf-ingestion\0"
_LOCKS: dict[Path, Any] = {}
_LOCKS_GUARD = threading.Lock()


class ImagePersistenceError(OSError):
    """The rendered PNG could not be published to the required cache."""


def settings() -> dict[str, int]:
    """The images max_side setting (pixels), read only when rendering is requested."""
    values = load_section("images")
    return {"max_side": int(values["max_side"])}


def image_reference(document_id: str, asset_id: str) -> str:
    """Run-relative cache reference shared by persistence and inspection diagnostics."""
    key = asset_id.replace(":", "-").replace("/", "__") + ".png"
    return f"images/{document_id}/{key}"


def _region(page: Any, bbox: Bounds | None) -> dict[str, Any]:
    visible = page.rect * page.derotation_matrix
    requested = list(bbox) if bbox is not None else list(visible)
    result: dict[str, Any] = {
        "coordinate_system": COORDINATE_SYSTEM,
        # JSON must remain valid even when stored coordinates are non-finite.
        "requested_bounds": [v if math.isfinite(v) else str(v) for v in requested],
        "effective_bounds": None,
        "clipped": False,
        "geometry": {
            "rotation": page.rotation,
            "mediabox": list(page.mediabox),
            "cropbox": list(page.cropbox),
            "visible_bounds": list(visible),
        },
        "available": False,
    }
    if len(requested) != 4 or not all(math.isfinite(v) for v in requested):
        result["reason"] = "Bounds must contain four finite coordinates."
        return result
    rect = fitz.Rect(requested)
    if rect.is_empty or not rect.is_valid:
        result["reason"] = "Bounds must describe a non-empty, non-inverted region."
        return result
    effective = rect & visible
    if effective.is_empty:
        result["reason"] = "The requested region lies fully outside the visible page."
        return result
    result.update(available=True, effective_bounds=list(effective), clipped=rect != effective)
    return result


def _page(doc: Any, page: int) -> Any:
    if type(page) is not int or not 1 <= page <= len(doc):
        raise ValueError(f"Page must be between 1 and {len(doc)}.")
    return doc[page - 1]


def describe_region(pdf: Path, page: int, bbox: Bounds | None) -> dict[str, Any]:
    """Inspect geometry without rendering or decoding an image. None selects a full page."""
    try:
        with fitz.open(str(pdf)) as doc:
            return _region(_page(doc, page), bbox)
    except FzErrorBase as error:
        raise RuntimeError("PDF image geometry could not be read.") from error


def crop_png(pdf: Path, page: int, bbox: Bounds | None, max_side: int) -> bytes:
    """Render the valid intersection, or raise; never substitute a different region."""
    if type(max_side) is not int or max_side <= 0:
        raise ValueError("max_side must be a positive integer.")
    with fitz.open(str(pdf)) as doc:
        pdf_page = _page(doc, page)
        region = _region(pdf_page, bbox)
        if not region["available"]:
            raise ValueError(region["reason"])
        clip = fitz.Rect(region["effective_bounds"]) * pdf_page.rotation_matrix
        zoom = max_side / max(clip.width, clip.height)
        # Align the clip origin with pixel zero to avoid adding a rounding pixel.
        matrix = fitz.Matrix(zoom, zoom).pretranslate(-clip.x0, -clip.y0)
        pixmap = pdf_page.get_pixmap(matrix=matrix, clip=clip, alpha=False, colorspace=fitz.csRGB)
        return pixmap.tobytes("png")


def _png_metadata(data: bytes) -> dict[str, Any] | None:
    """Validate the complete PNG container and pixels, returning our optional tEXt record.

    CRC32 here is the PNG format's required chunk checksum, not a cache identity.
    PyMuPDF alone can accept truncated/repaired PNGs, so validate chunks first.
    """
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("Invalid PNG signature.")
    offset = len(_PNG_SIGNATURE)
    metadata = None
    ended = False
    compressed = []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Incomplete PNG chunk.")
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("Incomplete PNG payload.")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        checksum = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) != checksum:
            raise ValueError("Invalid PNG chunk checksum.")
        if kind == b"IDAT":
            compressed.append(payload)
        if kind == b"tEXt" and payload.startswith(_METADATA_KEY):
            if metadata is not None:
                raise ValueError("Duplicate image metadata.")
            metadata = json.loads(payload[len(_METADATA_KEY):])
            if not isinstance(metadata, dict):
                raise ValueError("Invalid image metadata.")
        if kind == b"IEND":
            if size or end != len(data):
                raise ValueError("Invalid PNG end marker.")
            ended = True
        offset = end
    if not ended:
        raise ValueError("Missing PNG end marker.")
    decoder = zlib.decompressobj()
    try:
        decoder.decompress(b"".join(compressed))
    except zlib.error as error:
        raise ValueError("Invalid PNG pixel stream.") from error
    if not decoder.eof or decoder.unused_data:
        raise ValueError("Incomplete or trailing PNG pixel stream.")
    try:
        pixmap = fitz.Pixmap(data)
    except FzErrorBase as error:
        raise ValueError("Undecodable PNG pixels.") from error
    if pixmap.width <= 0 or pixmap.height <= 0:
        raise ValueError("Empty PNG.")
    return metadata


def _atomic_png(path: Path, data: bytes) -> None:
    """Publish a complete image and its embedded metadata with one atomic replacement."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".image-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def cached_png(
    pdf: Path, page: int, bbox: Bounds | None, max_side: int, *, run_dir: Path,
    document_id: str, asset_id: str, region: dict[str, Any],
) -> bytes:
    """Reuse only a matching, valid PNG under this run; no store/SQLite lock is held.

    One deterministic slot per document/asset; tEXt JSON and pixels live in the same
    atomic PNG. Per-slot locks coalesce threads. Cross-process readers also see a
    whole old or new entry; a mismatching entry is simply a miss.
    """
    if not re.fullmatch(r"[a-f0-9]{64}", document_id):
        raise ValueError("Invalid document identity for image persistence.")
    if not re.fullmatch(r"page:[1-9][0-9]*|segment:[0-9]+/[a-z]+:[A-Za-z0-9.]+", asset_id):
        raise ValueError("Invalid asset identity for image persistence.")
    if type(max_side) is not int or max_side <= 0:
        raise ValueError("max_side must be a positive integer.")
    path = run_dir / image_reference(document_id, asset_id)
    expected = {
        "renderer_version": RENDERER_VERSION, "pymupdf_version": str(fitz.VersionBind),
        "document_id": document_id, "asset_id": asset_id, "page": page,
        "region": region, "max_side": max_side, "colorspace": "RGB", "alpha": False,
    }
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(path, threading.Lock())
    with lock:
        try:
            cached = path.read_bytes()
            if _png_metadata(cached) == expected:
                return cached
        except (OSError, ValueError, RuntimeError):
            # Missing, incomplete, mismatched or undecodable entries are misses.
            pass
        try:
            data = crop_png(pdf, page, bbox, max_side)
        except FzErrorBase as error:
            raise RuntimeError("PDF image rendering failed.") from error
        _png_metadata(data)  # A failed renderer must never publish a successful cache entry.
        payload = _METADATA_KEY + json.dumps(expected, sort_keys=True, allow_nan=False).encode("ascii")
        chunk = b"tEXt" + payload
        record = struct.pack(">I", len(payload)) + chunk + struct.pack(">I", zlib.crc32(chunk))
        data = data[:-12] + record + data[-12:]  # Insert before IEND.
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_png(path, data)
        except OSError as error:
            raise ImagePersistenceError("Required PNG persistence failed.") from error
        return data
