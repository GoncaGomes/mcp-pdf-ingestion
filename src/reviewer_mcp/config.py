"""Configuration constants and default path settings for reviewer-mcp."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PACKAGED_CONFIG = Path(__file__).with_name("config.json")

# Default relative path in the workspace root
DEFAULT_PAPERS_DIR = Path("papers")


def workspace() -> Path:
    """Workspace root holding papers/.

    Read from REVIEWER_WORKSPACE on every call; defaults to the server's working directory.
    """
    return Path(os.environ.get("REVIEWER_WORKSPACE") or Path.cwd())


def scratch_base() -> Path:
    """Base directory for per-paper scratch data.

    Read from REVIEWER_SCRATCH_BASE on every call; defaults to /tmp/reviewer.
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
