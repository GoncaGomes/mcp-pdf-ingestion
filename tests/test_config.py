"""Focused checks for the MCP-02.1 document configuration loader (config.py)."""

import os
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from reviewer_mcp.config import DocumentConfig, load_document_config

CONFIG_VARS = ("PDF_INGESTION_PDF", "PDF_INGESTION_RUN_DIR")


def make_pdf(path: Path) -> Path:
    """A minimal one-page PDF written with PyMuPDF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    doc.new_page().insert_text((72, 120), "Synthetic configuration test document.", fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


def apply_env(pdf: str | None, run: str | None) -> None:
    """Set (or clear) the two configuration variables."""
    for name, value in zip(CONFIG_VARS, (pdf, run), strict=True):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class TestLoadDocumentConfig(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        saved = {name: os.environ.get(name) for name in CONFIG_VARS}
        self.addCleanup(self._restore_env, saved)

    @staticmethod
    def _restore_env(saved: dict[str, str | None]) -> None:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_missing_pdf_setting_is_rejected(self):
        apply_env(None, str(self.root / "run"))
        with self.assertRaisesRegex(ValueError, "PDF_INGESTION_PDF"):
            load_document_config()

    def test_missing_run_dir_setting_is_rejected(self):
        pdf = make_pdf(self.root / "paper.pdf")
        apply_env(str(pdf), None)
        with self.assertRaisesRegex(ValueError, "PDF_INGESTION_RUN_DIR"):
            load_document_config()

    def test_missing_pdf_file_is_rejected(self):
        apply_env(str(self.root / "absent paper.pdf"), str(self.root / "run"))
        with self.assertRaises(FileNotFoundError):
            load_document_config()

    def test_pdf_path_pointing_to_directory_is_rejected(self):
        apply_env(str(self.root), str(self.root / "run"))
        with self.assertRaisesRegex(ValueError, "not a file"):
            load_document_config()

    def test_invalid_pdf_content_is_rejected(self):
        pdf = self.root / "broken.pdf"
        pdf.write_bytes(b"not a pdf, just plain text")
        apply_env(str(pdf), str(self.root / "run"))
        with self.assertRaisesRegex(ValueError, "not a usable PDF"):
            load_document_config()

    def test_empty_pdf_file_is_rejected(self):
        pdf = self.root / "empty.pdf"
        pdf.write_bytes(b"")
        apply_env(str(pdf), str(self.root / "run"))
        with self.assertRaisesRegex(ValueError, "not a usable PDF"):
            load_document_config()

    def test_run_dir_pointing_to_file_is_rejected(self):
        pdf = make_pdf(self.root / "paper.pdf")
        blocker = self.root / "not a dir"
        blocker.write_text("a file, not a directory", encoding="utf-8")
        apply_env(str(pdf), str(blocker))
        with self.assertRaisesRegex(ValueError, "run directory path is a file"):
            load_document_config()

    def test_valid_config_with_spaces_and_missing_run_dir(self):
        pdf = make_pdf(self.root / "papers" / "my antenna paper.pdf")
        run = self.root / "runs" / "run dir for paper"
        apply_env(str(pdf), str(run))
        config = load_document_config()
        self.assertIsInstance(config, DocumentConfig)
        self.assertEqual(config.pdf_path, pdf.resolve())
        self.assertEqual(config.run_dir, run.resolve())
        self.assertTrue(config.pdf_path.is_file())
        self.assertFalse(config.run_dir.exists(), "run directory must not be created")

    def test_existing_run_dir_is_allowed(self):
        pdf = make_pdf(self.root / "paper.pdf")
        run = self.root / "run"
        run.mkdir()
        apply_env(str(pdf), str(run))
        self.assertEqual(load_document_config().run_dir, run.resolve())

    def test_relative_paths_resolve_against_cwd(self):
        work = self.root / "work"
        (work / "sub dir").mkdir(parents=True)
        make_pdf(work / "sub dir" / "my paper.pdf")
        previous = os.getcwd()
        os.chdir(work)
        self.addCleanup(os.chdir, previous)
        apply_env("sub dir/my paper.pdf", "run dir")
        config = load_document_config()
        self.assertEqual(config.pdf_path, (work / "sub dir" / "my paper.pdf").resolve())
        self.assertEqual(config.run_dir, (work / "run dir").resolve())
        self.assertTrue(config.pdf_path.is_file())
        self.assertFalse(config.run_dir.exists())


if __name__ == "__main__":
    unittest.main()
