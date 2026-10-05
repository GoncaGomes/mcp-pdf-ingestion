import os
import unittest
from pathlib import Path

import pymupdf as fitz
from pdf_fixtures import IsolatedTestCase, PaperBuilder, build_fixture, filler

from mcp_pdf_ingestion.store import PaperStore, close_all

REAL_WORKSPACE = os.environ.get("REVIEWER_WORKSPACE", "")
ACCESS = Path(REAL_WORKSPACE) / "papers" / "Access-2026-41373_Proof_hi.pdf"


def paragraph_pdf(path: Path) -> Path:
    doc = fitz.open()
    rows = [
        (1, 72, "1 Introduction", 11, "tibo"),
        (1, 72, "The first paragraph starts here and it contin-", 10, "tiro"),
        (1, 72, "ues on the next line of the same paragraph.", 10, "tiro"),
        (1, 84, "Second paragraph begins after a first-line indent.", 10, "tiro"),
        (1, 72, "It also has a second line without an indent.", 10, "tiro"),
        (1, 72, "Figure 1: A caption line in small type.", 8, "tiro"),
        (1, 84, "This sentence goes on", 10, "tiro"),
        (2, 72, "across the page break and ends here.", 10, "tiro"),
    ]
    for page_no in (1, 2):
        # PyMuPDF invalidates page objects when another page is added, so each page is written completely first.
        page = doc.new_page(width=595, height=842)
        y = 100.0
        for row_page, x, text, size, font in rows:
            if row_page != page_no:
                continue
            if text.startswith(("Figure", "This sentence")):
                y += 14
            page.insert_text((x, y), text, fontsize=size, fontname=font)
            y += size * 1.3
    doc.save(str(path))
    doc.close()
    return path


def outline_rows(store: PaperStore) -> list[tuple]:
    return [(s["level"], s["number"], s["title"], s["page"]) for s in store.outline()]


class TestParagraphsAndSections(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)

    def test_wrapped_references_remain_text_in_body_and_smaller_type(self):
        for size in (8, 10):
            with self.subTest(size=size):
                builder = PaperBuilder()
                builder.new_page()
                builder.paragraph(filler(1, 3))
                builder.line("The measured response is shown in", size=size)
                builder.line("Figure 7d.", size=size)
                builder.line("The configuration also appears in", size=size)
                builder.line("Fig. 3(a). Further discussion follows.", size=size)
                builder.y += 20
                builder.paragraph(filler(2, 3))
                store = PaperStore.open(builder.save(self.tmp_path / f"references-{size}.pdf"))
                self.assertEqual(store.assets("figure"), [])
                paragraphs = store.paragraphs()
                for reference in ("Figure 7d.", "Fig. 3(a)."):
                    containing = [p for p in paragraphs if reference in p["text"]]
                    self.assertTrue(containing)
                    self.assertTrue(all(p["kind"] == "text" for p in containing))
                    self.assertIn(reference, store.pages(1, 1)[0]["text"])

    def test_standalone_caption_labels_and_panel_suffixes_remain_supported(self):
        builder = PaperBuilder()
        builder.new_page()
        builder.paragraph(filler(1, 3))
        for label, size in (("Figure 5", 10), ("Fig. 6(b).", 8)):
            builder.y += 24
            builder.line(label, size=size)
            builder.line("Independent view of the configuration.", size=size)
        builder.y += 24
        builder.paragraph(filler(2, 3))
        store = PaperStore.open(builder.save(self.tmp_path / "separate-labels.pdf"))
        self.assertEqual([a["id"] for a in store.assets("figure")], ["figure:5", "figure:6b"])
        self.assertTrue(all("Independent view" in a["caption"] for a in store.assets("figure")))

    def test_panel_annotations_do_not_turn_following_captions_into_prose(self):
        builder = PaperBuilder()
        builder.new_page()
        builder.paragraph(filler(1, 3))
        for size, number in ((8, 1), (10, 2)):
            builder.y += 24
            builder.line("(b)", size=size)
            builder.line(f"Figure {number}. Views of the configuration.", size=size)
        builder.y += 24
        builder.paragraph(filler(2, 3))
        store = PaperStore.open(builder.save(self.tmp_path / "caption-after-panel-label.pdf"))
        self.assertEqual([a["id"] for a in store.assets("figure")], ["figure:1", "figure:2"])

    def test_wrapped_reference_across_a_page_boundary_remains_text(self):
        builder = PaperBuilder()
        builder.new_page()
        builder.paragraph(filler(1, 3))
        builder.line("The measured configuration is shown in")
        builder.new_page()
        builder.line("Figure 4(a). Further details follow.")
        builder.paragraph(filler(2, 3))
        store = PaperStore.open(builder.save(self.tmp_path / "reference-page-break.pdf"))
        self.assertEqual(store.assets("figure"), [])
        self.assertTrue(any("Figure 4(a)." in p["text"] and p["kind"] == "text" for p in store.paragraphs()))

    def test_paragraph_rules(self):
        store = PaperStore.open(paragraph_pdf(self.tmp_path / "paragraphs.pdf"))
        rows = [(p["kind"], p["text"], p["page"], p["last_page"]) for p in store.paragraphs()]
        self.assertEqual(
            rows,
            [
                ("heading", "1 Introduction", 1, 1),
                (
                    "text",
                    "The first paragraph starts here and it continues on the next line of the same paragraph.",
                    1,
                    1,
                ),
                (
                    "text",
                    "Second paragraph begins after a first-line indent. It also has a second line without an indent.",
                    1,
                    1,
                ),
                ("caption", "Figure 1: A caption line in small type.", 1, 1),
                ("text", "This sentence goes on across the page break and ends here.", 1, 2),
            ],
        )
        self.assertEqual(outline_rows(store), [(1, "1", "Introduction", 1)])

    def test_ieee_outline(self):
        store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))
        self.assertEqual(
            outline_rows(store),
            [
                (1, "", "Abstract", 4),
                (1, "I", "INTRODUCTION", 4),
                (1, "II", "RELATED WORK", 7),
                (1, "III", "PROPOSED METHOD", 9),
                (1, "IV", "EXPERIMENTS", 12),
                (1, "V", "CONCLUSION", 14),
                (1, "", "REFERENCES", 16),
            ],
        )

    def test_elsevier_outline_includes_cover_abstract(self):
        store = PaperStore.open(build_fixture("em_revision", self.tmp_path))
        self.assertEqual(
            outline_rows(store),
            [
                (1, "", "Abstract", 1),
                (1, "", "Abstract", 2),
                (1, "1", "Introduction", 2),
                (1, "2", "Related Work", 9),
                (1, "3", "Proposed Method", 15),
                (1, "4", "Experiments", 21),
                (1, "5", "Conclusion", 27),
                (1, "", "References", 33),
            ],
        )

    def test_section_paragraphs(self):
        store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))
        section = next(s for s in store.outline() if s["number"] == "III")
        paragraphs = store.section_paragraphs(section["id"])
        self.assertEqual(paragraphs[0]["kind"], "heading")
        self.assertEqual({p["page"] for p in paragraphs}, {9, 10, 11})
        self.assertEqual(store.section_paragraphs(9999), [])

    def test_search(self):
        store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))
        total, hits = store.search("ablation experiments")
        self.assertGreater(total, 0)
        self.assertTrue(all(4 <= hit["page"] <= 17 for hit in hits))
        self.assertTrue(all(hit["section_title"] for hit in hits))
        self.assertIn("[", hits[0]["snippet"])
        total, hits = store.search("Table I")
        self.assertGreaterEqual(total, 2)
        self.assertEqual({hit["page"] for hit in hits}, {7})
        total, hits = store.search("the", limit=3)
        self.assertEqual(len(hits), 3)
        self.assertGreater(total, 3)
        self.assertEqual(store.search('"; DROP TABLE lines; --')[0], 0)
        self.assertEqual(store.search("..."), (0, []))
        self.assertEqual(store.search("ablation", first=1, last=3), (0, []))

    def test_search_offset_preserves_total_and_record_order(self):
        store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))
        total, all_hits = store.search("the", limit=100000)
        self.assertGreater(total, 15)
        walked = []
        for offset in range(0, total, 7):
            count, hits = store.search("the", limit=7, offset=offset)
            self.assertEqual(count, total)
            walked.extend(hits)
        self.assertEqual(walked, all_hits)
        self.assertEqual(store.search("the", offset=total), (total, []))


@unittest.skipUnless(REAL_WORKSPACE and ACCESS.is_file(), "set REVIEWER_WORKSPACE to a workspace with the Access proof")
class TestRealAccessIndexes(IsolatedTestCase):
    def test_outline_structure(self):
        self.addCleanup(close_all)
        store = PaperStore.open(ACCESS)
        outline = store.outline()
        levels = [(s["level"], bool(s["number"])) for s in outline]
        self.assertEqual(levels.count((1, True)), 6, outline)
        self.assertEqual(levels.count((2, True)), 9, outline)
        self.assertEqual(levels.count((3, True)), 5, outline)
        self.assertEqual(levels.count((1, False)), 2, outline)
        self.assertEqual(
            [s["number"] for s in outline if s["level"] == 1 and s["number"]], ["I", "II", "III", "IV", "V", "VI"]
        )
        self.assertTrue(all(4 <= s["page"] <= 16 for s in outline))
        self.assertGreater(len(store.paragraphs()), 100)
        self.assertGreater(store.search("Fig")[0], 0)


if __name__ == "__main__":
    unittest.main()
