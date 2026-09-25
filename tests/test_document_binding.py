"""Process-level document binding (MCP-02.3): each stdio server process serves only its configured PDF.

Two real server processes over stdio (same pattern as tests/test_server.py) bind to two synthetic PDFs
that share the same filename but live in separate folders, with distinct run directories and
distinguishable text. No model settings or credentials are configured in any process. Startup rejection
(missing configuration, invalid PDF) and a successful launch with spaces in the PDF path are checked
with bounded timeouts; the StdioTransport context manager and subprocess.run keep the processes clean.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import pymupdf as fitz
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pdf_fixtures import IsolatedTestCase

SERVER_CODE = "from reviewer_mcp.server import main; main()"
TIMEOUT = 90  # seconds, per stdio probe or subprocess launch


def _build_pdf(path: Path, marker: str, pages: int = 2) -> Path:
    """Minimal synthetic PDF (generated, never committed) with distinguishable text on each page."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_text((72, 100), f"{marker} page {i + 1}", fontsize=12)
        page.insert_text((72, 130), f"Distinguishable filler sentence {i + 1} for {marker}.", fontsize=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _env(**overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(overrides)
    return env


async def _serve(pdf: Path, run_dir: Path) -> tuple[dict, str]:
    """Start one stdio server bound to ``pdf``/``run_dir``; return its overview and an explicit read."""
    transport = StdioTransport(
        command=sys.executable,
        args=["-c", SERVER_CODE],
        env=_env(PDF_INGESTION_PDF=str(pdf), PDF_INGESTION_RUN_DIR=str(run_dir)),
    )
    async with Client(transport) as client:
        overview = json.loads((await client.call_tool("get_paper_overview", {})).content[0].text)
        # Explicit page range and part='all': no manuscript heuristics in this isolation check.
        pages = (await client.call_tool("read_pages", {"first_page": 1, "last_page": 2, "part": "all"})).content[
            0
        ].text
    return overview, pages


class ProcessIsolationTestCase(IsolatedTestCase):
    def test_two_processes_serve_their_own_configured_pdf(self):
        pdf_a = _build_pdf(self.tmp_path / "submission_a" / "same_name.pdf", "ZULU-ALPHA")
        pdf_b = _build_pdf(self.tmp_path / "submission_b" / "same_name.pdf", "ZULU-BRAVO")
        run_a, run_b = self.tmp_path / "run_a", self.tmp_path / "run_b"
        self.assertEqual(pdf_a.name, pdf_b.name)
        sha_a, sha_b = _sha256(pdf_a), _sha256(pdf_b)
        self.assertNotEqual(sha_a, sha_b)

        overview_a, pages_a = asyncio.run(asyncio.wait_for(_serve(pdf_a, run_a), TIMEOUT))
        overview_b, pages_b = asyncio.run(asyncio.wait_for(_serve(pdf_b, run_b), TIMEOUT))

        # Each overview identifies its own PDF: the fingerprint is the SHA-256 of its configured bytes.
        self.assertEqual(overview_a["paper"], "same_name.pdf")
        self.assertEqual(overview_a["document_id"], sha_a)
        self.assertEqual(overview_a["pdf_pages"], 2)
        self.assertEqual(overview_b["paper"], "same_name.pdf")
        self.assertEqual(overview_b["document_id"], sha_b)
        self.assertEqual(overview_b["pdf_pages"], 2)

        # Each read_pages returns exactly the text of its own PDF, for the explicitly requested pages.
        self.assertTrue(pages_a.startswith("Pages 1-2"))
        self.assertIn("ZULU-ALPHA page 1", pages_a)
        self.assertIn("ZULU-ALPHA page 2", pages_a)
        self.assertNotIn("ZULU-BRAVO", pages_a)
        self.assertTrue(pages_b.startswith("Pages 1-2"))
        self.assertIn("ZULU-BRAVO page 1", pages_b)
        self.assertIn("ZULU-BRAVO page 2", pages_b)
        self.assertNotIn("ZULU-ALPHA", pages_b)

        # Each store is created under its own run directory, keyed by its own fingerprint.
        stores_a = sorted(p.parent.name for p in (run_a / "store").glob("*/paper.sqlite"))
        stores_b = sorted(p.parent.name for p in (run_b / "store").glob("*/paper.sqlite"))
        self.assertEqual(stores_a, [sha_a[:16]])
        self.assertEqual(stores_b, [sha_b[:16]])


class StartupRejectionTestCase(IsolatedTestCase):
    def _launch(self, **overrides: str) -> subprocess.CompletedProcess:
        """Run the real entry point with the given document settings; everything else is inherited."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("PDF_INGESTION_")}
        env.update(overrides)
        return subprocess.run(
            [sys.executable, "-c", SERVER_CODE],
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

    def test_missing_configuration_is_rejected_before_serving(self):
        result = self._launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")  # no protocol output: the server never started
        self.assertIn("PDF_INGESTION_PDF must be set", result.stderr)

    def test_invalid_pdf_is_rejected_before_serving(self):
        bad = self.tmp_path / "not_a_pdf.pdf"
        bad.write_text("not a PDF, just text", encoding="utf-8")
        result = self._launch(
            PDF_INGESTION_PDF=str(bad),
            PDF_INGESTION_RUN_DIR=str(self.tmp_path / "run"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("not a usable PDF", result.stderr)
        self.assertFalse((self.tmp_path / "run").exists())  # nothing is created for a rejected document


class StartupSuccessTestCase(IsolatedTestCase):
    def test_launch_succeeds_with_spaces_in_the_pdf_path(self):
        pdf = _build_pdf(self.tmp_path / "papers with spaces" / "proof hi res.pdf", "ZULU-CHARLIE")
        run_dir = self.tmp_path / "run spaced"

        async def probe() -> dict:
            transport = StdioTransport(
                command=sys.executable,
                args=["-c", SERVER_CODE],
                env=_env(PDF_INGESTION_PDF=str(pdf), PDF_INGESTION_RUN_DIR=str(run_dir)),
            )
            async with Client(transport) as client:
                return json.loads((await client.call_tool("get_paper_overview", {})).content[0].text)

        overview = asyncio.run(asyncio.wait_for(probe(), TIMEOUT))
        self.assertEqual(overview["paper"], "proof hi res.pdf")
        self.assertEqual(overview["document_id"], _sha256(pdf))


if __name__ == "__main__":
    unittest.main()
