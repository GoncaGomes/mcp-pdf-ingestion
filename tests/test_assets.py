import os
import unittest
from pathlib import Path
from unittest import mock

import pymupdf as fitz
from pdf_fixtures import IsolatedTestCase, PaperBuilder, build_fixture, filler

from mcp_pdf_ingestion import assets
from mcp_pdf_ingestion.document import Page
from mcp_pdf_ingestion.heuristics import Metrics
from mcp_pdf_ingestion.store import PaperStore, close_all

REAL_WORKSPACE = os.environ.get("REVIEWER_WORKSPACE", "")
ACCESS = Path(REAL_WORKSPACE) / "papers" / "Access-2026-41373_Proof_hi.pdf"


def ids(store: PaperStore, kind: str) -> list[str]:
    return [asset["id"] for asset in store.assets(kind)]


def exact_asset(store: PaperStore, asset_id: str):
    """These single-copy extraction fixtures have exactly one segment for each requested ID."""
    matches = [a for a in store.assets() if a["id"] == asset_id]
    if not matches:
        return None
    assert len(matches) == 1, f"Fixture must select an explicit segment for {asset_id}"
    return store.asset(matches[0]["segment"], asset_id)


def numbered(values: list[str]) -> list[str]:
    return sorted(values, key=lambda value: int(value.split(":")[1]))


def layout_pdf(path: Path, regions, captions, *, labels=(), text=(), scale=1):
    """Independent raster/vector regions and explicit text flow, without publication-specific content."""
    with fitz.open() as doc:
        page = doc.new_page(width=520 * scale, height=600 * scale)
        for y in (35, 49, 63, 550, 564, 578):
            page.insert_text((55 * scale, y * scale), filler(int(y), 1), fontsize=10 * scale, fontname="tiro")
        for kind, bounds in regions:
            rect = fitz.Rect([v * scale for v in bounds])
            if kind == "image":
                pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), False)
                pix.set_rect(pix.irect, (90, 140, 200))
                page.insert_image(rect, pixmap=pix, keep_proportion=False)
            else:
                page.draw_rect(rect, color=(0, 0, 0), fill=(0.8, 0.9, 0.8))
        for x, y, value in [*captions, *labels]:
            page.insert_text((x * scale, y * scale), value, fontsize=8 * scale, fontname="tiro")
        for x, y, value in text:
            page.insert_text((x * scale, y * scale), value, fontsize=10 * scale, fontname="tiro")
        doc.save(path)
    return path


class TestAssets(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)

    def test_invalid_candidates_are_excluded_before_association(self):
        metrics = Metrics("Times", 10, 13)
        valid = (40, 90, 200, 170)
        invalid = [
            (200, 160, 40, 195),
            (40, 195, 200, 160),
            (40, 195, 40, 198),
            (40, 190, float("inf"), 198),
            (40, float("nan"), 200, 198),
            (40, 190, 200),
        ]
        choice = assets._nearest(
            (40, 200, 200, 212), [("caption+image", "high", r) for r in [*invalid, valid]], (40, 200), metrics
        )
        self.assertEqual(choice[2], valid)
        self.assertIsNone(assets._nearest((40, 200, 200, 212), [("image", "high", invalid[0])], (40, 200), metrics))
        outside = (310, 190, 350, 198)
        partial = (-10, 90, 30, 150)
        with fitz.open() as doc:
            pdf_page = doc.new_page(width=300, height=400)
            data = {"blocks": [{"type": 1, "bbox": r} for r in [*invalid, outside, partial, valid]]}
            tables = mock.Mock(tables=[mock.Mock(bbox=r) for r in [*invalid, outside, valid]])
            with (
                mock.patch.object(fitz.Page, "get_text", return_value=data),
                mock.patch.object(fitz.Page, "get_drawings", return_value=[{"rect": r} for r in [*invalid, valid]]),
                mock.patch.object(fitz.Page, "find_tables", return_value=tables),
                mock.patch.object(assets, "_ruled_regions", return_value=[*invalid, outside, valid]),
            ):
                found = assets._geometry(pdf_page, Page(1, 300, 400, "", "text", 2, 0), True, metrics, (0, 400))
        self.assertEqual(found.images, sorted([partial, valid]))
        self.assertEqual(found.tables, [valid])
        self.assertEqual(found.shapes, [valid])
        self.assertEqual(found.ruled, [valid])

    def test_composites_group_rows_columns_and_grids_at_relative_scales(self):
        layouts = [
            [(55, 100, 210, 250), (290, 100, 445, 250)],
            [(55, 100, 170, 230), (185, 100, 300, 230), (315, 100, 430, 230)],
            [(90, 90, 300, 180), (90, 200, 300, 290), (90, 310, 300, 400)],
            [(55, 90, 220, 220), (245, 90, 410, 220), (55, 245, 220, 375), (245, 245, 410, 375)],
        ]
        for index, rects in enumerate(layouts):
            for scale in (0.8, 1.4):
                with self.subTest(layout=index, scale=scale):
                    bottom = max(r[3] for r in rects)
                    labels = [((r[0] + r[2]) / 2, r[3] + 8, f"({chr(97 + i)})") for i, r in enumerate(rects)]
                    pdf = layout_pdf(
                        self.tmp_path / f"group-{index}-{scale}.pdf",
                        [("image" if i % 2 == 0 else "drawing", r) for i, r in enumerate(rects)],
                        [
                            (
                                55,
                                bottom + 26,
                                "Fig. 12. Independent views of the configuration and its measured response.",
                            )
                        ],
                        labels=labels,
                        scale=scale,
                    )
                    store = PaperStore.open(pdf)
                    self.assertEqual(ids(store, "figure"), ["figure:12"])
                    figure = exact_asset(store, "figure:12")
                    self.assertEqual((figure["method"], figure["confidence"]), ("caption+group", "medium"))
                    for r in rects:
                        self.assertLessEqual(figure["x0"], r[0] * scale + 0.02)
                        self.assertLessEqual(figure["y0"], r[1] * scale + 0.02)
                        self.assertGreaterEqual(figure["x1"], r[2] * scale - 0.02)
                        self.assertGreaterEqual(figure["y1"], r[3] * scale - 0.02)
                    self.assertGreater(figure["y1"], bottom * scale)
                    self.assertLess(figure["y1"], (bottom + 26 - 8) * scale)
                    for _, _, label in labels:
                        self.assertIn(label, figure["content"])

    def test_neighboring_figures_with_distinct_captions_remain_separate(self):
        for arrangement, regions, captions in (
            (
                "row",
                [(55, 100, 210, 260), (285, 100, 450, 260)],
                [(55, 280, "Fig. 2. First view."), (285, 280, "Fig. 3. Second view.")],
            ),
            (
                "column",
                [(90, 100, 300, 230), (90, 310, 300, 440)],
                [(90, 250, "Fig. 2. First view."), (90, 460, "Fig. 3. Second view.")],
            ),
            (
                "top-captions",
                [(90, 100, 300, 230), (90, 310, 300, 440)],
                [(90, 80, "Fig. 2. First view."), (90, 290, "Fig. 3. Second view.")],
            ),
        ):
            with self.subTest(arrangement=arrangement):
                store = PaperStore.open(
                    layout_pdf(
                        self.tmp_path / f"neighbors-{arrangement}.pdf", [("image", r) for r in regions], captions
                    )
                )
                self.assertEqual(ids(store, "figure"), ["figure:2", "figure:3"])
                for asset_id, rect in zip(ids(store, "figure"), regions, strict=True):
                    item = exact_asset(store, asset_id)
                    self.assertEqual(tuple(item[k] for k in ("x0", "y0", "x1", "y1")), rect)
                    self.assertEqual(item["confidence"], "medium")

    def test_intervening_prose_stops_a_group(self):
        regions = [(90, 100, 300, 210), (90, 265, 300, 380)]
        pdf = layout_pdf(
            self.tmp_path / "text-boundary.pdf",
            [("image", r) for r in regions],
            [(90, 400, "Fig. 8. The lower configuration.")],
            text=[(90, 245, "These separate results require their own discussion.")],
        )
        item = exact_asset(PaperStore.open(pdf), "figure:8")
        self.assertEqual((item["y0"], item["y1"]), (265, 380))
        self.assertNotIn("separate results", item["content"])

    def test_caption_between_plausible_figures_does_not_choose_the_next_figure(self):
        store = PaperStore.open(
            layout_pdf(
                self.tmp_path / "caption-between-figures.pdf",
                [("image", (90, 100, 300, 250)), ("image", (90, 292, 300, 420))],
                [(90, 282, "Fig. 4. First configuration."), (90, 440, "Fig. 5. Next configuration.")],
            )
        )
        first = exact_asset(store, "figure:4")
        self.assertIsNone(first["x0"])
        self.assertEqual(first["confidence"], "low")
        self.assertEqual(first["page"], 1)
        second = exact_asset(store, "figure:5")
        self.assertIsNone(second["x0"])
        self.assertEqual(second["confidence"], "low")

    def test_disconnected_candidates_preserve_uncertainty_and_caption(self):
        for delta, expected_region in ((20, True), (6, False)):
            with self.subTest(delta=delta):
                bottom = 270 + delta
                pdf = layout_pdf(
                    self.tmp_path / f"uncertain-{delta}.pdf",
                    [("image", (55, 100, 210, 270)), ("image", (300, 120, 455, bottom))],
                    [(55, bottom + 18, "Fig. 9. Independent views of the configuration and its measured response.")],
                )
                item = exact_asset(PaperStore.open(pdf), "figure:9")
                self.assertEqual(item["confidence"], "low")
                self.assertEqual(item["page"], 1)
                self.assertTrue(item["caption"].startswith("Fig. 9."))
                self.assertEqual(item["x0"] is not None, expected_region)

    def test_ieee_fixture_assets(self):
        store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))
        figures = {asset["id"]: asset for asset in store.assets("figure")}
        self.assertEqual(ids(store, "figure"), ["figure:1", "figure:2", "figure:3"])
        self.assertEqual([figures[i]["page"] for i in ids(store, "figure")], [5, 9, 10])
        self.assertTrue(all(a["method"] == "caption+image" and a["confidence"] == "medium" for a in figures.values()))
        self.assertIn("Accuracy (%)", figures["figure:1"]["content"])
        self.assertTrue(figures["figure:1"]["caption"].startswith("Fig. 1."))
        self.assertGreaterEqual(figures["figure:1"]["cited"], 1)
        self.assertGreaterEqual(figures["figure:2"]["cited"], 1)
        self.assertEqual(figures["figure:3"]["cited"], 0)

        table = exact_asset(store, "table:I")
        self.assertIsNotNone(table)
        assert table is not None
        self.assertEqual((table["page"], table["method"], table["content_format"]), (7, "caption+table", "markdown"))
        self.assertIn("| Dataset | Items | Features |\n|---|---|---|\n| A | 1200 | 16 |", table["content"])
        self.assertIn(7, {m["page"] for m in table["mentions"]})

        self.assertEqual(ids(store, "equation"), ["equation:1", "equation:2"])
        equation = exact_asset(store, "equation:1")
        assert equation is not None
        self.assertEqual(equation["page"], 6)
        self.assertEqual(equation["content_format"], "text+mathml")
        text, markup = equation["content"].split("\n")
        self.assertTrue(text.startswith("f(x) = ") and text.endswith("w_ix_i^2"), text)
        self.assertIn("<msubsup><mi>x</mi><mi>i</mi><mn>2</mn></msubsup>", markup)
        self.assertIn("Eq. (1)", {m["text"] for m in equation["mentions"]})

        algorithm = exact_asset(store, "algorithm:1")
        assert algorithm is not None
        self.assertEqual((algorithm["page"], algorithm["method"]), (8, "caption+rules"))
        self.assertIn("1: R <- X", algorithm["content"])
        self.assertIn("4: end while", algorithm["content"])
        self.assertIn(8, {m["page"] for m in algorithm["mentions"]})

        self.assertEqual(numbered(ids(store, "reference")), [f"reference:{k}" for k in range(1, 15)])
        reference = exact_asset(store, "reference:1")
        assert reference is not None
        self.assertIn(4, {m["page"] for m in reference["mentions"]})
        self.assertIsNone(exact_asset(store, "figure:99"))

    def test_caption_paragraphs_need_small_type(self):
        store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))
        captions = [p["text"] for p in store.paragraphs() if p["kind"] == "caption"]
        self.assertFalse(any(text.startswith(("Table I lists", "Algorithm 1 details")) for text in captions))
        self.assertTrue(any(text.startswith("TABLE I") for text in captions))
        references = [p for p in store.paragraphs() if p["kind"] == "reference"]
        self.assertEqual(len(references), 14)
        self.assertTrue(all(p["text"].endswith("2024.") for p in references))

    def test_elsevier_fixture_assets(self):
        store = PaperStore.open(build_fixture("em_revision", self.tmp_path))
        self.assertEqual(ids(store, "figure"), ["figure:1", "figure:2", "figure:3"])
        self.assertEqual([a["page"] for a in store.assets("figure")], [3, 7, 8])
        self.assertEqual(ids(store, "table"), ["table:1"])
        table = exact_asset(store, "table:1")
        assert table is not None
        self.assertEqual(table["method"], "caption+table")
        self.assertGreaterEqual(len(table["mentions"]), 1)
        self.assertEqual(numbered(ids(store, "reference")), [f"reference:{k}" for k in range(1, 36)])

    def test_statements_proofs_and_citation_lists(self):
        builder = PaperBuilder()
        builder.new_page()
        builder.heading("2. Analysis")
        builder.paragraph(filler(3, 2))
        builder.paragraph("Theorem 1 (Bound). For every input the error is at most one half.")
        builder.paragraph("Proof. The claim follows from the triangle inequality.")
        builder.paragraph("Lemma 2. The loss is convex on the feasible set.")
        builder.paragraph("Theorems 1 and 2 are illustrated in Figs. 1-3 and discussed in Tables I-III.")
        store = PaperStore.open(builder.save(self.tmp_path / "statements.pdf"))
        self.assertEqual(ids(store, "statement"), ["theorem:1", "lemma:2"])
        theorem = exact_asset(store, "theorem:1")
        assert theorem is not None
        self.assertEqual(theorem["label"], "Theorem 1 (Bound)")
        self.assertIn("Proof. The claim follows", theorem["content"])
        self.assertEqual(len(theorem["mentions"]), 1)
        lemma = exact_asset(store, "lemma:2")
        assert lemma is not None
        self.assertNotIn("Proof", lemma["content"])

    def test_booktabs_table_with_body_type_caption(self):
        builder = PaperBuilder()
        builder.new_page()
        builder.heading("1. Results")
        builder.paragraph(filler(1, 3))
        builder.paragraph("Table S2 compares the three methods on both datasets.")
        builder.booktabs(
            "TABLE S.2:",
            "Accuracy of the compared methods.",
            [["Method", "Dataset A", "Dataset B"], ["Baseline", "71.2", "64.0"], ["Ours", "78.9", "70.3"]],
        )
        builder.paragraph(filler(2, 3))
        store = PaperStore.open(builder.save(self.tmp_path / "booktabs.pdf"))
        table = exact_asset(store, "table:S2")
        assert table is not None
        self.assertEqual(
            (table["method"], table["confidence"], table["content_format"]), ("caption+rules", "medium", "markdown")
        )
        self.assertEqual(table["content"].splitlines()[0], "| Method | Dataset A | Dataset B |")
        self.assertIn("| Ours | 78.9 | 70.3 |", table["content"])
        self.assertEqual(len(table["mentions"]), 1)
        captions = [p["text"] for p in store.paragraphs() if p["kind"] == "caption"]
        self.assertEqual(captions, ["TABLE S.2: Accuracy of the compared methods."])


@unittest.skipUnless(REAL_WORKSPACE and ACCESS.is_file(), "set REVIEWER_WORKSPACE to a workspace with the Access proof")
class TestRealAccessAssets(IsolatedTestCase):
    def test_asset_counts_and_regions(self):
        self.addCleanup(close_all)
        store = PaperStore.open(ACCESS)
        self.assertEqual(numbered(ids(store, "figure")), [f"figure:{k}" for k in range(1, 9)])
        self.assertEqual(numbered(ids(store, "table")), [f"table:{k}" for k in range(1, 8)])
        self.assertEqual(numbered(ids(store, "equation")), [f"equation:{k}" for k in range(1, 7)])
        self.assertEqual(ids(store, "algorithm"), ["algorithm:1", "algorithm:2"])
        self.assertEqual(numbered(ids(store, "reference")), [f"reference:{k}" for k in range(1, 21)])
        figures = store.assets("figure")
        self.assertGreaterEqual(sum(1 for a in figures if a["method"] == "caption+image"), 7)
        tables = store.assets("table")
        self.assertTrue(all(a["method"] == "caption+table" and a["content"].startswith("| ") for a in tables))
        first = exact_asset(store, "table:1")
        assert first is not None
        self.assertEqual(
            first["content"].splitlines()[:3],
            ["| λ | SR | Comput. time (h) |", "|---|---|---|", "| 2 | -21775 | 6.47 |"],
        )
        for algorithm_id in ("algorithm:1", "algorithm:2"):
            algorithm = exact_asset(store, algorithm_id)
            assert algorithm is not None
            self.assertGreaterEqual(algorithm["content"].count("\n"), 5)
        self.assertGreaterEqual(sum(1 for a in tables if a["cited"]), 5)
        self.assertGreaterEqual(sum(1 for a in store.assets("reference") if a["cited"]), 15)


if __name__ == "__main__":
    unittest.main()
