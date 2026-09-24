"""Sanity checks: every synthetic fixture really has the structure later phases rely on."""

import unittest

import pymupdf as fitz
from pdf_fixtures import FIXTURES, IsolatedTestCase, build_fixture, write_workspace

from reviewer_mcp.profile import build_profile
from reviewer_mcp.venues import load_index


def page_texts(path):
    with fitz.open(str(path)) as doc:
        return [str(doc[i].get_text()) for i in range(len(doc))]


def first_line(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else ""


class TestFixtures(IsolatedTestCase):
    def test_page_counts_file_names_and_specs(self):
        for name, spec in FIXTURES.items():
            path = build_fixture(name, self.tmp_path)
            self.assertEqual(path.name, spec.filename)
            with fitz.open(str(path)) as doc:
                self.assertEqual(len(doc), spec.pages, name)
            covered = [p for _, first, last in spec.segments for p in range(first, last + 1)]
            self.assertEqual(covered, list(range(1, spec.pages + 1)), f"{name}: segments must tile every page")

    def test_venues_resolve_from_metadata(self):
        write_workspace(self.workspace)
        index = load_index(self.workspace / "forms", self.workspace / "base_review.md")
        self.assertEqual(index.problems, [])
        for name, spec in FIXTURES.items():
            result = index.resolve(build_profile(build_fixture(name, self.tmp_path)))
            expected = ("resolved", spec.venue_id) if spec.venue_id else ("unresolved", "")
            self.assertEqual((result["status"], result["venue_id"]), expected, name)

    def test_running_headers_and_footers(self):
        stamps = build_profile(build_fixture("ieee_single", self.tmp_path))["stamps"]
        by_text = {(s["source"], s["text"]): s["pages"] for s in stamps}
        self.assertEqual(by_text[("header", "For consideration in IEEE Access")], [1, 2, 3])
        self.assertEqual(by_text[("footer", "VOLUME 11, 2023")], list(range(4, 18)))
        self.assertEqual(len(by_text[("header", "Page 1 of 17")]), 17)
        tmlcn = build_profile(build_fixture("scholarone_two_copies", self.tmp_path))["stamps"]
        header = next(s for s in tmlcn if s["source"] == "header")
        self.assertIn("Page 1 of 55", header["text"])
        self.assertEqual(len(header["pages"]), 55)

    def test_submission_item_labels(self):
        long_review = page_texts(build_fixture("em_long_review", self.tmp_path))
        self.assertEqual(first_line(long_review[0]), "Journal of Industrial Information Integration")
        self.assertIn("--Manuscript Draft--", long_review[0])
        self.assertEqual(first_line(long_review[1]), "Highlights")
        self.assertEqual(first_line(long_review[2]), "Letter")
        self.assertEqual(first_line(long_review[5]), "Response to reviewers")
        self.assertEqual(first_line(long_review[14]), "Response to reviewers")
        self.assertIn("Abstract", long_review[14])
        self.assertIn("References", long_review[43])
        revision = page_texts(build_fixture("em_revision", self.tmp_path))
        self.assertEqual(first_line(revision[1]), "Revised manuscript without author details (unmarked)")
        self.assertIn("Response to Reviewer 8", "".join(revision[37:58]))

    def test_numbered_assets_are_present(self):
        path = build_fixture("ieee_single", self.tmp_path)
        texts = page_texts(path)
        manuscript = "".join(texts[3:])
        for label in ("Fig. 1.", "Fig. 2.", "Fig. 3.", "TABLE I", "Algorithm 1", "(1)", "(2)", "[1]", "REFERENCES"):
            self.assertIn(label, manuscript)
        self.assertNotIn("Fig. 3 ", manuscript.replace("Fig. 3.", ""))
        self.assertIn("Received XX Month", texts[3])
        with fitz.open(str(path)) as doc:
            self.assertTrue(doc[4].get_images(), "figure page has an image")
            self.assertIn("Accuracy (%)", doc[4].get_text())
            self.assertGreaterEqual(len(doc[6].find_tables().tables), 1, "table page has a ruled table")
            fonts = {span["font"] for block in doc[5].get_text("dict")["blocks"] for line in block.get("lines", [])
                     for span in line["spans"]}
            self.assertTrue(any("Symbol" in font for font in fonts), fonts)
            sizes = {round(span["size"], 1) for block in doc[5].get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]}
            self.assertIn(7.0, sizes, "sub/superscripts use a smaller size")

    def test_marked_copy_has_colour_and_highlights(self):
        path = build_fixture("scholarone_two_copies", self.tmp_path)
        with fitz.open(str(path)) as doc:
            def red_spans(page_no):
                return sum(
                    1 for block in doc[page_no - 1].get_text("dict")["blocks"] for line in block.get("lines", [])
                    for span in line["spans"] if span["color"] != 0
                )

            def highlights(page_no):
                return len(list(doc[page_no - 1].annots() or []))

            self.assertEqual(sum(red_spans(p) for p in range(4, 24)), 0)
            self.assertEqual(sum(highlights(p) for p in range(4, 24)), 0)
            self.assertGreater(sum(red_spans(p) for p in range(24, 44)), 0)
            self.assertGreater(sum(highlights(p) for p in range(24, 44)), 0)

    def test_blank_and_scanned_pages(self):
        self.assertEqual(page_texts(build_fixture("em_long_review", self.tmp_path))[92].strip(), "")
        path = build_fixture("scanned", self.tmp_path)
        self.assertEqual(page_texts(path)[0].strip(), "")
        with fitz.open(str(path)) as doc:
            self.assertEqual(len(doc[0].get_images()), 1)


if __name__ == "__main__":
    unittest.main()
