"""Lossless deterministic text access, using isolated synthetic PDFs and stores."""

import base64
import json
from unittest import mock

import pymupdf as fitz
from pdf_fixtures import IsolatedTestCase, build_fixture
from test_indexes import paragraph_pdf

from reviewer_mcp import reading
from reviewer_mcp.papers import ReviewError
from reviewer_mcp.store import PaperStore, close_all


def changed_cursor(cursor, **changes):
    state = json.loads(base64.urlsafe_b64decode(cursor))
    state.update(changes)
    return base64.urlsafe_b64encode(json.dumps(state).encode()).decode()


def long_section_pdf(path):
    """An oversized paragraph crosses a page in a hyphenated word, before two subsections."""
    with fitz.open() as doc:
        page = doc.new_page(width=1000, height=3000)
        page.insert_text((72, 100), "1 Introduction", fontsize=14, fontname="tibo")
        for i in range(170):
            page.insert_text(
                (72, 135 + i * 13), f"Evidence line {i} " + "repeatable source text " * 4, fontsize=10, fontname="tiro"
            )
        page.insert_text((72, 135 + 170 * 13), "a word crosses the boundary as contin-", fontsize=10, fontname="tiro")
        page = doc.new_page(width=1000, height=3000)
        page.insert_text((72, 100), "uation with truthful page provenance.", fontsize=10, fontname="tiro")
        for y, text, size, font in (
            (150, "1.1 Details", 12, "tibo"),
            (180, "The first child contains measurements.", 10, "tiro"),
            (220, "1.2 Scope", 12, "tibo"),
            (250, "The second child describes limits.", 10, "tiro"),
            (300, "2 Conclusion", 14, "tibo"),
            (330, "This next section must be excluded.", 10, "tiro"),
        ):
            page.insert_text((72, y), text, fontsize=size, fontname=font)
        doc.save(path)
    return path


class TestPageReading(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)
        self.store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))

    def collect(self, **kwargs):
        result = {}
        reply = reading.read_pages(self.store, **kwargs)
        for _ in range(2000):
            for fragment in reply["fragments"]:
                page = fragment["page"]
                result[page] = result.get(page, "") + fragment["text"]
            cursor = reply["next_cursor"]
            if cursor is None:
                return result
            reply = reading.read_pages(self.store, cursor=cursor)
        self.fail("page traversal did not terminate")

    def expected(self, first, last):
        return {p["page"]: p["text"] for p in self.store.pages(first, last)}

    def test_range_defaults_overlap_and_exact_reconstruction(self):
        with mock.patch.object(reading, "READ_BUDGET", 137):
            for args, bounds in (
                ({}, (1, 17)),
                ({"first_page": 4}, (4, 4)),
                ({"last_page": 4}, (1, 4)),
                ({"first_page": 5, "last_page": 7}, (5, 7)),
            ):
                with self.subTest(args=args):
                    self.assertEqual(self.collect(**args), self.expected(*bounds))
            self.assertEqual(self.collect(first_page=6, last_page=8), self.expected(6, 8))
            self.assertEqual(self.collect(first_page=5, last_page=7), self.expected(5, 7))

    def test_invalid_ranges(self):
        for first, last in ((0, 2), (-1, 2), (3, 2), (1, 18), (18, None), (None, 0), (True, 2)):
            with self.subTest(first=first, last=last), self.assertRaises(ReviewError):
                reading.read_pages(self.store, first, last)

    def test_cursor_replay_identity_operation_range_and_position(self):
        with mock.patch.object(reading, "READ_BUDGET", 31):
            cursor = reading.read_pages(self.store, 4, 6)["next_cursor"]
            reply = reading.read_pages(self.store, cursor=cursor)
            self.assertEqual(reply, reading.read_pages(self.store, cursor=cursor))
            self.assertEqual(reply, reading.read_pages(self.store, 4, 6, cursor))
            for first, last in ((5, None), (None, 7)):
                with self.assertRaisesRegex(ReviewError, "conflicts"):
                    reading.read_pages(self.store, first, last, cursor)
            for changes in (
                {"document_id": "other"},
                {"operation": "read_section"},
                {"index": -1},
                {"index": 3},
                {"offset": -1},
                {"offset": 1000000},
                {"index": True},
                {"offset": "0"},
                {"first": None},
                {"last": 18},
            ):
                with self.subTest(changes=changes), self.assertRaises(ReviewError):
                    reading.read_pages(self.store, cursor=changed_cursor(cursor, **changes))
        for bad in ("", "p4@20", "!!!!", "W10=", "e30=", "bnVsbA==", "a" * 4097):
            with self.subTest(cursor=bad), self.assertRaises(ReviewError):
                reading.read_pages(self.store, cursor=bad)

    def test_page_larger_than_default_budget(self):
        path = self.tmp_path / "long.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=1000, height=3000)
            for i in range(190):
                page.insert_text((60, 120 + i * 13), f"Line {i}: " + "long page evidence " * 7, fontsize=8)
            doc.save(path)
        self.store = PaperStore.open(path)
        text = self.store.pages()[0]["text"]
        self.assertGreater(len(text), reading.READ_BUDGET)
        self.assertIsNotNone(reading.read_pages(self.store)["next_cursor"])
        self.assertEqual(self.collect(), {1: text})

    def test_references_outside_inferred_manuscript(self):
        self.store.set_manuscript_pages(4, 10, "Test only: references fall outside this inferred range")
        result = self.collect(first_page=16, last_page=17)
        self.assertEqual(result, self.expected(16, 17))
        self.assertIn("[1]", result[16] + result[17])

    def test_empty_pages_keep_text_and_observed_source(self):
        scanned = PaperStore.open(build_fixture("scanned", self.tmp_path))
        path = self.tmp_path / "blank.pdf"
        with fitz.open() as doc:
            doc.new_page()
            doc.save(path)
        blank = PaperStore.open(path)
        for store, source in ((scanned, "none"), (blank, "blank")):
            reply = reading.read_pages(store)
            self.assertEqual(reply["fragments"], [{"page": 1, "text": ""}])
            self.assertEqual(reply["empty_pages"], [{"page": 1, "source": source}])
            self.assertIsNone(reply["next_cursor"])


class TestSectionReading(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)

    def collect(self, store, section_id):
        fragments, cursor = [], None
        for _ in range(2000):
            reply = reading.read_section(store, section_id, cursor)
            fragments.extend(reply["fragments"])
            cursor = reply["next_cursor"]
            if cursor is None:
                return fragments
        self.fail("section traversal did not terminate")

    def test_cross_page_paragraph_and_exact_section_text(self):
        store = PaperStore.open(paragraph_pdf(self.tmp_path / "paragraphs.pdf"))
        section_id = store.outline()[0]["id"]
        expected = "\n\n".join(p["text"] for p in store.section_paragraphs(section_id))
        with mock.patch.object(reading, "READ_BUDGET", 17):
            fragments = self.collect(store, section_id)
            self.assertEqual(self.collect(store, section_id), fragments)
        self.assertEqual("".join(f["text"] for f in fragments), expected)
        by_page = {page: "".join(f["text"] for f in fragments if f["page"] == page) for page in (1, 2)}
        self.assertTrue(by_page[1].endswith("This sentence goes on"))
        self.assertEqual(by_page[2], " across the page break and ends here.")

    def test_duplicate_titles_and_sections_outside_manuscript(self):
        store = PaperStore.open(build_fixture("em_revision", self.tmp_path))
        duplicates = [s for s in store.outline() if s["title"] == "Abstract"]
        self.assertEqual(len(duplicates), 2)
        self.assertNotEqual(duplicates[0]["id"], duplicates[1]["id"])
        for section in duplicates:
            result = reading.read_section(store, section["id"])
            self.assertEqual(result["section"]["id"], section["id"])
            self.assertEqual(result["fragments"][0]["page"], section["page"])
            expected = "\n\n".join(p["text"] for p in store.section_paragraphs(section["id"]))
            self.assertEqual("".join(f["text"] for f in self.collect(store, section["id"])), expected)

    def test_missing_outline_does_not_block_page_reads(self):
        store = PaperStore.open(build_fixture("scanned", self.tmp_path))
        self.assertEqual(store.outline(), [])
        with self.assertRaisesRegex(ReviewError, "Unknown section_id.*read_pages"):
            reading.read_section(store, 1)
        self.assertEqual(reading.read_pages(store)["fragments"], [{"page": 1, "text": ""}])

    def test_cursor_replay_conflicts_and_malformed_positions(self):
        store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))
        section_id = store.outline()[0]["id"]
        with mock.patch.object(reading, "READ_BUDGET", 13):
            cursor = reading.read_section(store, section_id)["next_cursor"]
            reply = reading.read_section(store, section_id, cursor)
            self.assertEqual(reply, reading.read_section(store, section_id, cursor))
            for changes in (
                {"section_id": section_id + 1},
                {"section_id": True},
                {"document_id": "other"},
                {"operation": "read_pages"},
                {"index": -1},
                {"offset": 1000000},
            ):
                with self.subTest(changes=changes), self.assertRaises(ReviewError):
                    reading.read_section(store, section_id, changed_cursor(cursor, **changes))
            with self.assertRaisesRegex(ReviewError, "conflicts"):
                reading.read_section(store, section_id + 1, cursor)
        with self.assertRaisesRegex(ReviewError, "Unknown section_id"):
            reading.read_section(store, 9999)

    def test_long_paragraph_subsections_hyphenation_and_exact_boundary(self):
        store = PaperStore.open(long_section_pdf(self.tmp_path / "long-section.pdf"))
        outline = store.outline()
        self.assertEqual([(s["number"], s["level"]) for s in outline], [("1", 1), ("1.1", 2), ("1.2", 2), ("2", 1)])
        section_id = outline[0]["id"]
        paragraphs = store.section_paragraphs(section_id)
        self.assertGreater(max(len(p["text"]) for p in paragraphs), reading.READ_BUDGET)
        cross_page = [p for p in paragraphs if p["last_page"] > p["page"]]
        self.assertEqual(len(cross_page), 1)
        self.assertIn("continuation", cross_page[0]["text"])
        self.assertIsNotNone(reading.read_section(store, section_id)["next_cursor"])
        fragments = self.collect(store, section_id)
        text = "".join(f["text"] for f in fragments)
        self.assertEqual(text, "\n\n".join(p["text"] for p in paragraphs))
        self.assertIn("1.1 Details", text)
        self.assertIn("1.2 Scope", text)
        self.assertNotIn("2 Conclusion", text)
        page_one = "".join(f["text"] for f in fragments if f["page"] == 1)
        page_two = "".join(f["text"] for f in fragments if f["page"] == 2)
        self.assertTrue(page_one.endswith("contin"))
        self.assertTrue(page_two.startswith("uation with truthful page provenance."))
        child = "".join(f["text"] for f in self.collect(store, outline[1]["id"]))
        self.assertIn("first child", child)
        self.assertNotIn("1.2 Scope", child)


class TestSearch(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)
        self.store = PaperStore.open(build_fixture("ieee_single", self.tmp_path))

    def collect(self, query, **kwargs):
        reply = reading.search(self.store, query, **kwargs)
        total = reply["total_hits"]
        hits = []
        for _ in range(1000):
            self.assertEqual(reply["total_hits"], total)
            self.assertEqual(reply["document_id"], self.store.meta()["fingerprint"])
            self.assertLessEqual(len(reply["hits"]), reading.SEARCH_PAGE_SIZE)
            hits.extend(reply["hits"])
            cursor = reply["next_cursor"]
            if cursor is None:
                self.assertEqual(len(hits), total)
                return hits
            reply = reading.search(self.store, query, cursor=cursor)
        self.fail("search traversal did not terminate")

    def test_traversal_stable_order_and_section_identity(self):
        total, expected = self.store.search("the", limit=100000)
        self.assertGreater(total, reading.SEARCH_PAGE_SIZE)
        initial = reading.search(self.store, "the")
        hits = self.collect("the")
        ids = [h["paragraph_id"] for h in hits]
        self.assertEqual(ids, [h["id"] for h in expected])
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(reading.search(self.store, "the"), initial)
        sections = {s["id"]: s["title"] for s in self.store.outline()}
        for hit in hits:
            self.assertEqual(hit["section_title"], sections.get(hit["section_id"]))
            self.assertTrue(hit["snippet"])

    def test_range_defaults_and_continuation(self):
        with mock.patch.object(reading, "SEARCH_PAGE_SIZE", 2):
            for kwargs, bounds in (
                ({}, (1, 17)),
                ({"first_page": 7}, (7, 7)),
                ({"last_page": 7}, (1, 7)),
                ({"first_page": 7, "last_page": 10}, (7, 10)),
            ):
                with self.subTest(kwargs=kwargs):
                    _, expected = self.store.search("the", limit=100000, first=bounds[0], last=bounds[1])
                    hits = self.collect("the", **kwargs)
                    self.assertEqual([h["paragraph_id"] for h in hits], [h["id"] for h in expected])
                    self.assertTrue(all(bounds[0] <= h["page"] <= bounds[1] for h in hits))

    def test_phrase_final_prefix_quotes_and_zero_hits(self):
        for query in ('"proposed method"', "proposed meth", '"; DROP TABLE lines; --', "zzzznotextracted", "..."):
            with self.subTest(query=query):
                total, expected = self.store.search(query, limit=100000)
                hits = self.collect(query)
                self.assertEqual(len(hits), total)
                self.assertEqual([h["paragraph_id"] for h in hits], [h["id"] for h in expected])
        self.assertGreater(reading.search(self.store, '"proposed method"')["total_hits"], 0)
        self.assertEqual(
            reading.search(self.store, "proposed meth")["total_hits"],
            reading.search(self.store, "proposed method")["total_hits"],
        )
        zero = reading.search(self.store, "zzzznotextracted")
        self.assertEqual(zero["total_hits"], 0)
        self.assertEqual(zero["hits"], [])
        self.assertIsNone(zero["next_cursor"])
        self.assertIn("does not establish absence", zero["hint"])

    def test_cursor_replay_query_range_identity_operation_and_position(self):
        with mock.patch.object(reading, "SEARCH_PAGE_SIZE", 2):
            cursor = reading.search(self.store, "the", 4, 10)["next_cursor"]
            reply = reading.search(self.store, "the", cursor=cursor)
            self.assertEqual(reply, reading.search(self.store, "the", 4, 10, cursor))
            self.assertEqual(reply, reading.search(self.store, "the", cursor=cursor))
            for query, first, last in (("The", None, None), ("method", 4, 10), ("the", 5, 10), ("the", 4, 11)):
                with self.subTest(query=query, first=first), self.assertRaisesRegex(ReviewError, "conflicts"):
                    reading.search(self.store, query, first, last, cursor)
            for changes in (
                {"document_id": "other"},
                {"operation": "read_pages"},
                {"offset": -1},
                {"offset": True},
                {"offset": "2"},
                {"offset": 100000},
                {"last": None},
            ):
                with self.subTest(changes=changes), self.assertRaises(ReviewError):
                    reading.search(self.store, "the", cursor=changed_cursor(cursor, **changes))
        for query in ("", "  ", "\n", "a" * 121):
            with self.subTest(query=query), self.assertRaisesRegex(ReviewError, "query"):
                reading.search(self.store, query)
        for first, last in ((0, 1), (3, 2), (1, 18)):
            with self.assertRaises(ReviewError):
                reading.search(self.store, "the", first, last)
        with self.assertRaisesRegex(ReviewError, "Invalid cursor"):
            reading.search(self.store, "the", cursor="old-cursor")
