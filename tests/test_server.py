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
    "get_paper_overview", "set_manuscript_pages", "read_pages", "read_section", "search_paper",
    "get_author_responses", "list_assets", "get_asset", "get_review_guideline", "submit_report", "update_report_field",
}
READERS = ("get_paper_overview", "read_pages", "read_section", "search_paper", "get_author_responses", "list_assets")
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
        for name in READERS:
            self.assertTrue(tools[name].annotations.read_only_hint, name)

    def test_protocol_negotiated_over_stdio(self):
        async def negotiate(mode):
            transport = StdioTransport(
                command=sys.executable, args=["-c", "from reviewer_mcp.server import main; main()"],
                env=dict(os.environ),
            )
            async with Client(transport, mode=mode) as client:
                return client.protocol_version, len(await client.list_tools())

        # 2026-07-28 is negotiated with server/discover; initialize remains for handshake-era clients
        self.assertEqual(asyncio.run(negotiate("auto")), ("2026-07-28", len(TOOLS)))
        self.assertEqual(asyncio.run(negotiate("legacy"))[0], "2025-11-25")


class TestReading(ServerCase):
    def test_overview_of_a_revision(self):
        paper = self.paper("em_revision")
        (self.workspace / "papers" / f"{paper[:-4]}.notes").write_text("Check the ageing baseline.", encoding="utf-8")
        view = server.get_paper_overview(paper)
        self.assertEqual((view["venue"]["status"], view["venue"]["venue_id"]), ("resolved", "elsevier_jii"))
        self.assertEqual([p["kind"] for p in view["parts"]], ["cover", "manuscript", "responses", "other"])
        self.assertEqual(view["manuscript"]["pages"], "2-37")
        self.assertEqual(view["round"]["status"], "revision")
        self.assertEqual(view["reviewer_notes"], "Check the ageing baseline.")
        self.assertEqual(view["title"], "Mechanism-Guided Framework for Multi-Fault Diagnosis of Battery Systems")
        self.assertTrue(any("Introduction" in heading for heading in view["outline"]))
        self.assertEqual(view["numbered_items"]["figure"], 3)
        self.assertIn("figure:3", view["uncited_items"])
        self.assertNotIn("/", json.dumps(view["parts"]) + str(view["paper"]))

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
        self.assertTrue(again.startswith("Pages 4-17 were already returned in this review."), again)
        self.assertTrue(server.read_pages(paper, first_page=10, last_page=17).startswith("Pages 10-17 were already"))
        everything = server.read_pages(paper, first_page=16, last_page=17, part="all")
        self.assertNotIn(reading.REFERENCES_OMITTED, everything)
        self.assertIn("[1]", everything)
        with self.assertRaisesRegex(ToolError, r"outside this PDF \(17 pages; manuscript = pages 4-17\)"):
            server.read_pages(paper, first_page=40)
        server.get_paper_overview(paper)  # a new review may read everything again
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

    def test_author_responses(self):
        paper = self.paper("em_revision")
        summary = server.get_author_responses(paper)
        self.assertIn("reviewers present: [1, 6, 7, 8]", summary.splitlines()[0])
        six = server.get_author_responses(paper, reviewer=6)
        self.assertIn("Response to Reviewer 6", six)
        self.assertNotIn("Response to Reviewer 7", six)
        self.assertIn("Nothing new to return", server.get_author_responses(paper, reviewer=6))
        comment = server.get_author_responses(paper, query="Comment 2")
        self.assertRegex(comment.splitlines()[0], r"query 'Comment 2': [1-9]\d* matching items")
        with self.assertRaisesRegex(ToolError, "reviewers present"):
            server.get_author_responses(paper, reviewer=2)
        with self.assertRaisesRegex(ToolError, "revisions only"):
            server.get_author_responses(self.paper("ieee_single"))
        server.get_paper_overview(paper)  # a new review may read the letter again
        self.assertIn("Response to Reviewer 6", server.get_author_responses(paper, reviewer=6))

    def test_manual_manuscript_range(self):
        paper = self.paper("scholarone_two_copies")
        view = server.set_manuscript_pages(paper, 24, 43, "pages 4-23 are the highlighted copy")
        self.assertEqual((view["manuscript"]["pages"], view["manuscript"]["source"]), ("24-43", "override"))
        self.assertTrue(server.read_pages(paper).startswith("Pages 24"))


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
            self.assertEqual(reply("figure:1"), "figure:1 was already returned in this review.")
            self.assertEqual(json.loads(reply("table:I"))["id"], "table:I")
            self.assertIn("The budget of 2 items per review is used (figure:1, table:I)", reply("figure:2"))
            server.get_paper_overview(paper)  # a new review restores the budget
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
            server.get_paper_overview(paper)  # a new review restores the budget
            self.assertEqual([type(c).__name__ for c in run(figure).content], ["TextContent", "ImageContent"])


class TestGuidelineAndReports(ServerCase):
    def test_only_valid_reports_are_published(self):
        paper = self.paper("ieee_single")
        guideline = server.get_review_guideline(paper)
        self.assertEqual((guideline["status"], guideline["venue_id"]), ("resolved", "ieee_access"))
        skeleton = server.get_review_guideline(paper, form_only=True)["skeleton"]
        self.assertIn("| **Venue ID** | ieee_access |", skeleton)
        self.assertIn("Recommendation: <to fill: one of: Accept | Reject>", skeleton)
        self.assertIn("Comments to the Author:\n<to fill: 1-3 paragraphs; main issues>", skeleton)
        published = self.workspace / "reports" / "Access-2026-00001_Proof_hi_Report.md"

        first = server.submit_report(paper, skeleton)
        self.assertFalse(first["published"])
        self.assertFalse(published.exists())

        draft = skeleton.replace("<to fill: 1-5>", "3", 4).replace("<to fill: 1-5>", "high")
        draft = draft.replace("<to fill: one of: Accept | Reject>", "Accept")
        draft = draft.replace("<to fill: a whole number from 1 to 10>", "7")
        draft = re.sub(r"<to fill[^>]*>", "Checked against the manuscript.", draft)
        second = server.submit_report(paper, draft)
        self.assertFalse(second["published"])
        self.assertTrue(any("impact" in error for error in second["errors"]))

        third = server.update_report_field(paper, "Quality Matrix: Impact", "4")
        self.assertTrue(third["published"], third)
        fourth = server.update_report_field(paper, "Recommendation", "Reject")
        self.assertTrue(fourth["published"], fourth)
        fifth = server.update_report_field(paper, "comments to the author", "First point.\n\nSecond point.")
        self.assertTrue(fifth["published"], fifth)
        text = published.read_text(encoding="utf-8")
        self.assertIn("Recommendation: Reject", text)
        self.assertIn("Comments to the Author:\nFirst point.\n\nSecond point.", text)
        invalid = server.update_report_field(paper, "Overall Rating", "11")
        self.assertFalse(invalid["published"])
        self.assertTrue(any("whole number from 1 to 10" in error for error in invalid["errors"]))
        with self.assertRaisesRegex(ToolError, "No form field is labelled"):
            server.update_report_field(paper, "Confidential Notes", "5")

        # a report cannot pick another venue than the guideline it was written against
        published.unlink()
        wrong = draft.replace("| **Venue ID** | ieee_access |", "| **Venue ID** | elsevier_jii |")
        result = server.submit_report(paper, wrong)
        self.assertFalse(result["published"])
        self.assertTrue(any("differs from the venue resolved" in error for error in result["errors"]))
        self.assertFalse(published.exists())

    def test_update_needs_a_draft_and_unresolved_venues_abort(self):
        paper = self.paper("em_revision")
        with self.assertRaisesRegex(ToolError, "no draft"):
            server.update_report_field(paper, "Recommendation", "Accept")
        (self.workspace / "forms" / "elsevier_jii.md").unlink()
        self.assertIn("STRICT ABORT", server.get_review_guideline(paper)["error"])
        with self.assertRaisesRegex(ToolError, "is not in papers/"):
            server.get_paper_overview("missing.pdf")


if __name__ == "__main__":
    unittest.main()
