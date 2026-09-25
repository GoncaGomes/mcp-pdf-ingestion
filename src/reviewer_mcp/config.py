"""Configuration constants and default path settings for reviewer-mcp."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf as fitz

PACKAGED_CONFIG = Path(__file__).with_name("config.json")


def scratch_base() -> Path:
    """Base directory for per-paper scratch data.

    Read from REVIEWER_SCRATCH_BASE on every call; defaults to /tmp/reviewer. Used as the store base only when a
    store is opened without an explicit run directory (internal tests); the server always passes its bound run
    directory.
    """
    return Path(os.environ.get("REVIEWER_SCRATCH_BASE") or "/tmp/reviewer")


def load_section(section: str) -> dict[str, Any]:
    """Values of one section of the packaged config.json, overridden by the REVIEWER_CONFIG file when set."""
    entries: dict[str, Any] = json.loads(PACKAGED_CONFIG.read_text(encoding="utf-8"))[section]
    values = {name: entry["value"] for name, entry in entries.items()}
    override_path = os.environ.get("REVIEWER_CONFIG")
    if override_path:
        overrides: dict[str, Any] = json.loads(Path(override_path).read_text(encoding="utf-8")).get(section, {})
        unknown = sorted(set(overrides) - set(values))
        if unknown:
            raise ValueError(f"{override_path}: unknown {section} settings {unknown}; known: {sorted(values)}")
        for name, entry in overrides.items():
            values[name] = entry["value"] if isinstance(entry, dict) else entry
    return values


@dataclass(frozen=True)
class DocumentConfig:
    """The document bound to one server process: its configured PDF and run directory."""

    pdf_path: Path
    run_dir: Path


def load_document_config() -> DocumentConfig:
    """Load and validate the document settings from the environment.

    Reads ``PDF_INGESTION_PDF`` and ``PDF_INGESTION_RUN_DIR``; both are required. Relative paths are
    resolved against the current working directory, preserving spaces in names. The PDF must exist as a
    regular file and open in a PyMuPDF context manager as a usable document: it must be a real PDF
    (not another image or file format), must not require a password, and must have at least one page.
    No content is extracted. The run directory may not exist yet, but must not already be a file. Nothing
    is created and no model settings are read.
    """
    pdf_raw = os.environ.get("PDF_INGESTION_PDF")
    run_raw = os.environ.get("PDF_INGESTION_RUN_DIR")
    if not pdf_raw:
        raise ValueError("PDF_INGESTION_PDF must be set to the path of the configured PDF")
    if not run_raw:
        raise ValueError("PDF_INGESTION_RUN_DIR must be set to the run directory for derived data")

    pdf_path = Path(pdf_raw).resolve()
    run_dir = Path(run_raw).resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not pdf_path.is_file():
        raise ValueError(f"PDF path is not a file: {pdf_path}")
    if run_dir.is_file():
        raise ValueError(f"run directory path is a file: {run_dir}")

    try:
        with fitz.open(str(pdf_path)) as doc:
            if not doc.is_pdf:
                raise ValueError(f"not a PDF document (file is not in PDF format): {pdf_path}")
            if doc.needs_pass:
                raise ValueError(f"PDF is password-protected: {pdf_path}")
            if doc.page_count < 1:
                raise ValueError(f"PDF has no pages: {pdf_path}")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"not a usable PDF: {pdf_path}: {error}") from error

    return DocumentConfig(pdf_path=pdf_path, run_dir=run_dir)
