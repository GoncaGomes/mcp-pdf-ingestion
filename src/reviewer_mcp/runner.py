"""Server runner: clean stdio transport and prompt shutdown on signals.

The MCP protocol version 2026-07-28 preferred by Goose is negotiated natively by fastmcp>=4.0.3 / mcp>=2.2.
"""

from __future__ import annotations

import atexit
import os
import signal
import sys
from typing import TYPE_CHECKING, Any

import fastmcp

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Keep stdio clean: no banner or rich logging on the JSON-RPC stream.
_settings: Any = getattr(fastmcp, "settings", None)
if _settings is not None:
    _settings.show_server_banner = False
    _settings.enable_rich_logging = False


def run_server(mcp: FastMCP) -> None:
    """Run FastMCP server instance with signal and exit handling."""

    def _on_sigint(_signum: int, _frame: object) -> None:
        sys.exit(0)

    def _on_sigterm_early(_signum: int, _frame: object) -> None:
        os._exit(0)

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigterm_early)

    @atexit.register
    def _flush() -> None:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass

    mcp.run()
