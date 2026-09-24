"""Tool contract and behaviour of the reviewer-mcp server on synthetic submissions."""

import asyncio
import json
import os
import re
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError
from pdf_fixtures import IsolatedTestCase, build_fixture, write_workspace

from reviewer_mcp import reading, server
from reviewer_mcp.papers import ASSETS_KEY
from reviewer_mcp.store import PaperStore, close_all

TOOLS = {
    "get_paper_overview",
    "read_pages",
    "read_section",
    "search_paper",
    "list_assets",
    "get_asset",
}
SCHEMA_BUDGET = 9_200  # characters of the tool list the model receives (names, descriptions, parameters), ~2.5k tokens


def run(coroutine_factory):
    async def session():
        async with Client(server.mcp) as client:
            return await coroutine_factory(client)

    return asyncio.run(session())


class ServerCase(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)
        write_workspace(self.workspace)

    def paper(self, name):
        return build_fixture(name, self.workspace / "papers").name


class TestContract(ServerCase):
    def test_tools_parameters_and_description_budget(self):
        tools = {tool.name: tool for tool in run(lambda client: client.list_tools())}
        self.assertEqual(set(tools), TOOLS)
        for tool in tools.values():
            self.assertTrue(tool.description, tool.name)
            for name, schema in tool.input_schema["properties"].items():
                self.assertTrue(schema.get("description"), f"{tool.name}.{name} has no description")
        listed = [{"name": t.name, "description": t.description, "parameters": t.input_schema} for t in tools.values()]
        self.assertLessEqual(len(json.dumps(listed, ensure_ascii=False)), SCHEMA_BUDGET)
        # read_pages and get_asset record what they return in the retained consumption ledger
        # (not idempotent), and get_paper_overview resets it (destructive but idempotent);
        # none of them can claim read-only.
        def hints(name):
            a = tools[name].annotations
            return (a.read_only_hint, bool(a.destructive_hint), a.idempotent_hint)

        self.assertEqual(hints("get_paper_overview"), (False, True, True))
        self.assertEqual(hints("read_pages"), (False, False, False))
        self.assertEqual(hints("get_asset"), (False, False, False))
        # only the pure reads claim read-only
        for name in ("read_section", "search_paper", "list_assets"):
            self.assertEqual(hints(name), (True, False, True), name)

    def test_protocol_negotiated_over_stdio(self):
        async def negotiate(mode):
            transport = StdioTransport(
                command=sys.executable,
                args=["-c", "from reviewer_mcp.server import main; main()"],
                env=dict(os.environ),
            )
            async with Client(transport, mode=mode) as client:
                return client.protocol_version, len(await client.list_tools())

        # 2026-07-28 is negotiated with server/discover; initialize remains for handshake-era clients
        self.assertEqual(asyncio.run(negotiate("auto")), ("2026-07-28", len(TOOLS)))
        self.assertEqual(asyncio.run(negotiate("legacy"))[0], "2025-11-25")


class TestBareWorkspace(IsolatedTestCase):
    """The overview must not depend on legacy reviewer files (forms/, base_review.md, notes)."""

    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)

    def test_overview_without_legacy_reviewer_files(self):
        paper = build_fixture("ieee_single", self.workspace / "papers").name
        self.assertFalse((self.workspace / "forms").exists())
        self.assertFalse((self.workspace / "base_review.md").exists())
        self.assertFalse(list(self.workspace.glob("papers/*.notes")))
        view = server.get_paper_overview(paper)
        self.assertEqual(view["paper"], paper)
        self.assertEqual(view["pdf_pages"], 17)
        outline = view["outline"]
        self.assertTrue(outline)
        self.assertEqual(len({entry["id"] for entry in outline}), len(outline))
        self.assertTrue(all(set(entry) == {"id", "level", "number", "title", "page"} for entry in outline))
        self.assertTrue(any("RELATED WORK" in entry["title"] for entry in outline))


class TestReading(ServerCase):
    def test_overview_is_neutral_and_covers_the_whole_pdf(self):
        paper = self.paper("em_revision")
        (self.workspace / "papers" / f"{paper[:-4]}.notes").write_text("Check the ageing baseline.", encoding="utf-8")
        view = server.get_paper_overview(paper)
        self.assertEqual(view["paper"], paper)
        self.assertEqual(view["pdf_pages"], 59)
        self.assertEqual(view["title"], "Mechanism-Guided Framework for Multi-Fault Diagnosis of Battery Systems")
        for key in ("venue", "reviewer_notes", "parts", "manuscript", "round"):
            self.assertNotIn(key, view)
        self.assertNotIn("ageing", json.dumps(view))  # a .notes file next to the PDF is not read
        outline = view["outline"]
        self.assertTrue(outline)
        self.assertEqual(len({entry["id"] for entry in outline}), len(outline))
        self.assertTrue(all(set(entry) == {"id", "level", "number", "title", "page"} for entry in outline))
        self.assertTrue(any("Introduction" in entry["title"] for entry in outline))
        self.assertEqual(view["numbered_items"]["figure"], 3)
        self.assertNotIn("/", str(view["paper"]))

    def test_overview_allows_a_missing_title_and_reports_warnings(self):
        view = server.get_paper_overview(self.paper("scanned"))
        self.assertEqual(view["pdf_pages"], 1)
        self.assertEqual(view["title"], "")
        self.assertEqual(view["outline"], [])
        self.assertEqual(view["numbered_items"], {})
        self.assertEqual(len(view["warnings"]), 1)

    def test_read_pages_returns_every_page_once(self):
        paper = self.paper("ieee_single")
        texts, cursor, calls = [], None, 0
        with mock.patch.object(reading, "READ_BUDGET", 1500):
            while True:
                reply = server.read_pages(paper, cursor=cursor)
                texts.append(reply)
                calls += 1
                cursor = re.match(r"Pages \S+ \(manuscript = pages 4-17\)\. next: (\S+)", reply).group(1)
                if cursor == "none":
                    break
        joined = "\n".join(texts)
        self.assertGreater(calls, 2)
        self.assertEqual(sorted({int(n) for n in re.findall(r"=== Page (\d+) ===", joined)}), list(range(4, 18)))
        store = PaperStore.open(self.workspace / "papers" / paper)
        reference_lines = {
            line
            for entry in store.paragraphs(4, 17)
            if entry["kind"] == "reference"
            for line in range(entry["first_line"], entry["last_line"] + 1)
        }
        self.assertTrue(reference_lines)
        for page in store.pages(4, 17):
            for line in store.lines(page["page"], ("body",)):
                if line["id"] in reference_lines:
                    self.assertNotIn(line["text"], joined)
                else:
                    self.assertIn(line["text"], joined)
        self.assertIn(reading.REFERENCES_OMITTED, joined)
        again = server.read_pages(paper)
        self.assertTrue(again.startswith("Pages 4-17 were already returned."), again)
        self.assertTrue(server.read_pages(paper, first_page=10, last_page=17).startswith("Pages 10-17 were already"))
        everything = server.read_pages(paper, first_page=16, last_page=17, part="all")
        self.assertNotIn(reading.REFERENCES_OMITTED, everything)
        self.assertIn("[1]", everything)
        with self.assertRaisesRegex(ToolError, r"outside this PDF \(17 pages; manuscript = pages 4-17\)"):
            server.read_pages(paper, first_page=40)
        server.get_paper_overview(paper)  # a new reading session may read everything again
        self.assertTrue(server.read_pages(paper).startswith("Pages 4-"))

    def test_sections_and_search(self):
        paper = self.paper("ieee_single")
        section = server.read_section(paper, "ii. related work")
        status, _, text = section.partition("\n\n")
        self.assertTrue(status.startswith("Section II RELATED WORK (level 1, pages "), status)
        self.assertTrue(text)
        with self.assertRaisesRegex(ToolError, "INTRODUCTION"):
            server.read_section(paper, "Discussion of results")
        hits = server.search_paper(paper, "Fig")
        self.assertGreaterEqual(hits["total_hits"], 3)
        self.assertTrue(all(4 <= hit["page"] <= 17 for hit in hits["hits"]))


class TestAssets(ServerCase):
    def test_list_and_inspect_items(self):
        paper = self.paper("ieee_single")
        listing = server.list_assets(paper)
        self.assertEqual(listing["counts"]["figure"], 3)
        self.assertIn("figure:3", listing["uncited"])
        self.assertTrue(all(item["id"].split(":")[0] != "reference" for item in listing["items"]))
        table = run(lambda client: client.call_tool("get_asset", {"paper": paper, "asset": "table:I"}))
        detail = json.loads(table.content[0].text)
        self.assertTrue(detail["content"].startswith("|"))
        self.assertTrue(detail["cited_by"])
        self.assertEqual(detail["image"], "not requested")
        with self.assertRaisesRegex(ToolError, "list_assets"):
            server.get_asset(paper, "figure:99")

    def test_items_are_returned_once_within_the_budget(self):
        paper = self.paper("ieee_single")
        server.get_paper_overview(paper)
        override = self.tmp_path / "two_items.json"
        override.write_text(json.dumps({"replies": {"asset_budget": 2}}), encoding="utf-8")

        def reply(asset):
            return server.get_asset(paper, asset)[0].text

        with mock.patch.dict(os.environ, {"REVIEWER_CONFIG": str(override)}):
            self.assertEqual(json.loads(reply("figure:1"))["id"], "figure:1")
            self.assertEqual(reply("figure:1"), "figure:1 was already returned.")
            self.assertEqual(json.loads(reply("table:I"))["id"], "table:I")
            self.assertIn("The budget of 2 items is used (figure:1, table:I)", reply("figure:2"))
            server.get_paper_overview(paper)  # a new reading session restores the budget
            self.assertEqual(json.loads(reply("figure:2"))["id"], "figure:2")

    def test_budget_holds_for_parallel_calls(self):
        paper = self.paper("ieee_single")
        server.get_paper_overview(paper)
        override = self.tmp_path / "two_items.json"
        override.write_text(json.dumps({"replies": {"asset_budget": 2}}), encoding="utf-8")
        ids = ["figure:1", "figure:2", "figure:3", "table:I"] * 3
        with mock.patch.dict(os.environ, {"REVIEWER_CONFIG": str(override)}), ThreadPoolExecutor(len(ids)) as pool:
            replies = list(pool.map(lambda asset: server.get_asset(paper, asset)[0].text, ids))
        self.assertEqual(sum(reply.startswith("{") for reply in replies), 2)
        stored = PaperStore.open(self.workspace / "papers" / paper).get_state(ASSETS_KEY) or ""
        self.assertEqual(len(stored.split(",")), 2)

    def test_images_follow_vision_mode_and_budget(self):
        paper = self.paper("ieee_single")
        server.get_paper_overview(paper)

        def figure(client):
            return client.call_tool("get_asset", {"paper": paper, "asset": "figure:1", "include_image": True})

        disabled = run(figure)  # images are off in the packaged config
        self.assertEqual([type(c).__name__ for c in disabled.content], ["TextContent"])
        self.assertIn("images are disabled", json.loads(disabled.content[0].text)["image"])
        override = self.tmp_path / "images_on.json"
        override.write_text(json.dumps({"images": {"enabled": True}}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"REVIEWER_CONFIG": str(override)}):
            kinds = [[type(c).__name__ for c in run(figure).content] for _ in range(5)]
            self.assertEqual(kinds[0], ["TextContent", "ImageContent"])
            self.assertEqual(kinds[4], ["TextContent"])
            server.get_paper_overview(paper)  # a new reading session restores the budget
            self.assertEqual([type(c).__name__ for c in run(figure).content], ["TextContent", "ImageContent"])


if __name__ == "__main__":
    unittest.main()
