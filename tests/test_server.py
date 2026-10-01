"""Tool contract and behaviour of the mcp-pdf-ingestion server on synthetic submissions."""

import asyncio
import json
import os
import sysconfig
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError
from mcp.client import stdio as sdk_stdio
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, KNOWN_PROTOCOL_VERSIONS
from pdf_fixtures import IsolatedTestCase, build_contract_pdf, build_fixture, write_workspace
from test_reading import changed_cursor
from test_visual_inspection import ENV, FakeClient, completion

from mcp_pdf_ingestion import reading, server, visual_inspection
from mcp_pdf_ingestion.store import PaperStore, close_all

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


def asset(*args, **kwargs):
    return asyncio.run(server.get_asset(*args, **kwargs))


class ServerCase(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)
        write_workspace(self.workspace)
        self.run_dir = self.tmp_path / "run"

    def bind_paper(self, name):
        """Build fixture `name` in the workspace and bind the server process to it; return its file name."""
        paper = build_fixture(name, self.workspace / "papers").name
        env = mock.patch.dict(
            os.environ,
            {
                "PDF_INGESTION_PDF": str(self.workspace / "papers" / paper),
                "PDF_INGESTION_RUN_DIR": str(self.run_dir),
            },
        )
        env.start()
        self.addCleanup(env.stop)
        server.bind_document()
        return paper

    def catalog(self, **kwargs):
        reply = server.list_assets(**kwargs)
        counts, total, items = reply["counts"], reply["total_assets"], []
        for _ in range(1000):
            self.assertEqual(reply["counts"], counts)
            self.assertEqual(reply["total_assets"], total)
            self.assertNotIn("uncited", reply)
            self.assertLessEqual(len(reply["items"]), server.ASSET_PAGE_SIZE)
            items.extend(reply["items"])
            if reply["next_cursor"] is None:
                self.assertEqual(len(items), total)
                return items
            reply = server.list_assets(cursor=reply["next_cursor"])
        self.fail("catalog traversal did not terminate")


class TestContract(ServerCase):
    def test_tools_parameters_and_description_budget(self):
        tools = {tool.name: tool for tool in run(lambda client: client.list_tools())}
        self.assertEqual(set(tools), TOOLS)
        for name, parameters in (
            ("read_pages", {"first_page", "last_page", "cursor"}),
            ("read_section", {"section_id", "cursor"}),
            ("search_paper", {"query", "first_page", "last_page", "cursor"}),
            ("list_assets", {"kind", "first_page", "last_page", "cursor"}),
        ):
            self.assertEqual(set(tools[name].input_schema["properties"]), parameters)
            self.assertGreaterEqual(tools[name].input_schema["properties"]["cursor"]["anyOf"][0]["maxLength"], 4096)
        self.assertEqual(set(tools["get_asset"].input_schema["properties"]), {"asset_id", "question"})
        self.assertIn("page", json.dumps(tools["list_assets"].input_schema["properties"]["kind"]))
        for tool in tools.values():
            self.assertTrue(tool.description, tool.name)
            self.assertNotIn("paper", tool.input_schema["properties"], tool.name)
            for name, schema in tool.input_schema["properties"].items():
                self.assertTrue(schema.get("description"), f"{tool.name}.{name} has no description")
        listed = [{"name": t.name, "description": t.description, "parameters": t.input_schema} for t in tools.values()]
        self.assertLessEqual(len(json.dumps(listed, ensure_ascii=False)), SCHEMA_BUDGET)

        # Only the mixed get_asset tool can infer and persist diagnostics.
        def hints(name):
            a = tools[name].annotations
            return (a.read_only_hint, bool(a.destructive_hint), a.idempotent_hint)

        self.assertEqual(hints("get_paper_overview"), (True, False, True))
        self.assertEqual(hints("read_pages"), (True, False, True))
        self.assertEqual(hints("get_asset"), (False, False, False))
        # only the pure reads claim read-only
        for name in ("read_section", "search_paper", "list_assets"):
            self.assertEqual(hints(name), (True, False, True), name)


class TestStdioContract(IsolatedTestCase):
    def test_installed_console_contract_and_negotiation(self):
        pdf = build_contract_pdf(self.workspace / "contract evidence.pdf")
        run_dir = self.tmp_path / "stdio run"
        self.addCleanup(close_all)
        store = PaperStore.open(pdf, run_dir=self.tmp_path / "expected")
        expected_pages = {p["page"]: p["text"] for p in store.pages()}
        document_id = store.meta()["fingerprint"]
        section_id = next(s["id"] for s in store.outline() if s["title"] == "Evidence")
        expected_section = "\n\n".join(p["text"] for p in store.section_paragraphs(section_id))
        close_all()
        command = Path(sysconfig.get_path("scripts")) / (
            "mcp-pdf-ingestion.exe" if os.name == "nt" else "mcp-pdf-ingestion"
        )
        self.assertTrue(command.is_file(), "install the project in the active environment first")
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() != "PYTHONPATH"
            and not k.startswith(("REVIEWER_", "PDF_INGESTION_", "SKYNET_", "VISUAL_INSPECTION_"))
        }
        env.update(PDF_INGESTION_PDF=str(pdf), PDF_INGESTION_RUN_DIR=str(run_dir))
        processes = []
        create_process = sdk_stdio._create_platform_compatible_process

        async def track_process(*args, **kwargs):
            # Observe process lifetime only; use the SDK's transport and negotiation unchanged.
            process = await create_process(*args, **kwargs)
            processes.append(process)
            return process

        async def scenario():
            for mode in ("legacy", "auto"):
                transport = StdioTransport(
                    command=str(command),
                    args=[],
                    env=env,
                    cwd=str(self.workspace),
                    keep_alive=False,
                    log_file=self.tmp_path / "server.stderr.log",
                )
                async with Client(transport, mode=mode) as client:
                    self.assertIn(client.protocol_version, KNOWN_PROTOCOL_VERSIONS)
                    self.assertEqual(client.server_info.name, "mcp-pdf-ingestion")
                    if mode == "legacy":
                        self.assertIsNotNone(client.initialize_result)
                        self.assertIn(client.protocol_version, HANDSHAKE_PROTOCOL_VERSIONS)
                        self.assertEqual({t.name for t in await client.list_tools()}, TOOLS)
                        continue
                    tools = {t.name: t for t in await client.list_tools()}
                    self.assertEqual(set(tools), TOOLS)
                    for name, tool in tools.items():
                        self.assertNotIn("paper", tool.input_schema["properties"])
                        for field, schema in tool.input_schema["properties"].items():
                            self.assertTrue(schema.get("description"), f"{name}.{field}")
                        hints = tool.annotations
                        self.assertEqual(
                            (hints.read_only_hint, hints.idempotent_hint),
                            (False, False) if name == "get_asset" else (True, True),
                        )
                        self.assertFalse(hints.destructive_hint)
                    question = tools["get_asset"].input_schema["properties"]["question"]
                    self.assertNotIn("question", tools["get_asset"].input_schema.get("required", []))
                    self.assertIn({"type": "null"}, question["anyOf"])
                    self.assertIn("visual", tools["get_asset"].description.lower())

                    async def call(name, **arguments):
                        result = await client.call_tool(name, arguments)
                        self.assertTrue(all(c.type == "text" for c in result.content))
                        value = json.loads(result.content[0].text)
                        self.assertEqual(value["document_id"], document_id)
                        return value

                    async def traverse(name, arguments, key):
                        first = reply = await call(name, **arguments)
                        self.assertIsNotNone(first["next_cursor"], f"{name} must actually paginate")
                        items, cursors, second = [], set(), None
                        for _ in range(100):
                            items.extend(reply[key])
                            cursor = reply["next_cursor"]
                            if cursor is None:
                                break
                            self.assertNotIn(cursor, cursors)
                            cursors.add(cursor)
                            reply = await call(name, **arguments, cursor=cursor)
                            if second is None:
                                second = reply
                        else:
                            self.fail(f"{name} traversal did not terminate")
                        self.assertEqual(await call(name, **arguments, cursor=first["next_cursor"]), second)
                        return first, items

                    view = await call("get_paper_overview")
                    self.assertEqual((view["paper"], view["pdf_pages"]), (pdf.name, 25))
                    self.assertEqual(view["title"], "Synthetic PDF Evidence Contract")
                    self.assertEqual([s["title"] for s in view["outline"]], ["Evidence", "Closing"])
                    self.assertEqual(view["outline"][0]["id"], section_id)
                    first_read, fragments = await traverse("read_pages", {}, "fragments")
                    actual = {}
                    for fragment in fragments:
                        page = fragment["page"]
                        actual[page] = actual.get(page, "") + fragment["text"]
                    self.assertEqual(actual, expected_pages)
                    _, fragments = await traverse("read_section", {"section_id": section_id}, "fragments")
                    self.assertEqual("".join(f["text"] for f in fragments), expected_section)
                    self.assertEqual({f["page"] for f in fragments}, set(range(1, 25)))
                    search, hits = await traverse("search_paper", {"query": "Contractmarker"}, "hits")
                    self.assertEqual(len(hits), search["total_hits"])
                    self.assertEqual(len(hits), 24 * 6)
                    self.assertEqual({h["page"] for h in hits}, set(range(1, 25)))
                    self.assertTrue(all(h["section_id"] == section_id and h["snippet"] for h in hits))
                    first_catalog, items = await traverse("list_assets", {}, "items")
                    self.assertEqual(len(items), first_catalog["total_assets"])
                    self.assertEqual(first_catalog["counts"], {"figure": 24})
                    self.assertEqual(len({a["id"] for a in items}), 24)
                    _, pages = await traverse("list_assets", {"kind": "page"}, "items")
                    self.assertEqual([a["id"] for a in pages], [f"page:{n}" for n in range(1, 26)])
                    retrieved = []
                    for item in items:
                        detail = await call("get_asset", asset_id=item["id"])
                        self.assertEqual((detail["id"], detail["first_page"]), (item["id"], item["first_page"]))
                        self.assertEqual(detail["visual"]["status"], "not_requested")
                        retrieved.append(detail)
                    for page in (1, 25):
                        detail = await call("get_asset", asset_id=f"page:{page}", question=None)
                        self.assertEqual(detail["content"], expected_pages[page])
                        self.assertEqual(detail["visual"]["status"], "not_requested")
                    for _ in range(8):
                        self.assertEqual(await call("get_asset", asset_id=items[0]["id"]), retrieved[0])
                        self.assertEqual(await call("read_pages"), first_read)
                    self.assertEqual(await call("get_paper_overview"), view)
                    self.assertEqual(await call("read_pages"), first_read)
                    self.assertEqual(await call("get_asset", asset_id=items[0]["id"]), retrieved[0])
                    self.assertEqual(await call("list_assets"), first_catalog)
                self.assertIsNone(transport._session)

        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(sdk_stdio, "_create_platform_compatible_process", side_effect=track_process),
            self.assertNoLogs("mcp.client.stdio", level="ERROR"),
        ):
            asyncio.run(asyncio.wait_for(scenario(), 90))
        self.assertEqual(len(processes), 2)
        self.assertTrue(all(p.returncode is not None for p in processes), "stdio subprocess leaked")
        self.assertFalse((run_dir / "images").exists())
        self.assertFalse((run_dir / "inspections").exists())
        self.assertFalse((self.workspace / "forms").exists())
        self.assertFalse((self.workspace / "base_review.md").exists())
        self.assertFalse(list(self.workspace.rglob("*.notes")))


class TestBareWorkspace(IsolatedTestCase):
    """The overview must not depend on legacy reviewer files (forms/, base_review.md, notes)."""

    def setUp(self):
        super().setUp()
        self.addCleanup(close_all)

    def test_overview_without_legacy_reviewer_files(self):
        paper = build_fixture("ieee_single", self.workspace / "papers").name
        env = mock.patch.dict(
            os.environ,
            {
                "PDF_INGESTION_PDF": str(self.workspace / "papers" / paper),
                "PDF_INGESTION_RUN_DIR": str(self.tmp_path / "run"),
            },
        )
        env.start()
        self.addCleanup(env.stop)
        server.bind_document()
        self.assertFalse((self.workspace / "forms").exists())
        self.assertFalse((self.workspace / "base_review.md").exists())
        self.assertFalse(list(self.workspace.glob("papers/*.notes")))
        view = server.get_paper_overview()
        self.assertEqual(view["paper"], paper)
        self.assertEqual(view["pdf_pages"], 17)
        outline = view["outline"]
        self.assertTrue(outline)
        self.assertEqual(len({entry["id"] for entry in outline}), len(outline))
        self.assertTrue(all(set(entry) == {"id", "level", "number", "title", "page"} for entry in outline))
        self.assertTrue(any("RELATED WORK" in entry["title"] for entry in outline))


class TestReading(ServerCase):
    def test_overview_is_neutral_and_covers_the_whole_pdf(self):
        paper = self.bind_paper("em_revision")
        (self.workspace / "papers" / f"{paper[:-4]}.notes").write_text("Check the ageing baseline.", encoding="utf-8")
        view = server.get_paper_overview()
        self.assertEqual(view["paper"], paper)
        self.assertRegex(view["document_id"], r"^[0-9a-f]{64}$")
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
        self.bind_paper("scanned")
        view = server.get_paper_overview()
        self.assertEqual(view["pdf_pages"], 1)
        self.assertEqual(view["title"], "")
        self.assertEqual(view["outline"], [])
        self.assertEqual(view["numbered_items"], {})
        self.assertEqual(len(view["warnings"]), 1)

    def test_document_binding_survives_environment_changes(self):
        """An initialized instance keeps its document and run directory when the environment changes."""
        paper = self.bind_paper("ieee_single")
        first = server.get_paper_overview()
        other = build_fixture("em_revision", self.workspace / "papers").name
        other_run = self.tmp_path / "other-run"
        with mock.patch.dict(
            os.environ,
            {
                "PDF_INGESTION_PDF": str(self.workspace / "papers" / other),
                "PDF_INGESTION_RUN_DIR": str(other_run),
            },
        ):
            second = server.get_paper_overview()
        self.assertEqual(second["paper"], paper)
        self.assertEqual(second["document_id"], first["document_id"])
        self.assertFalse(other_run.exists(), "the bound run directory is not re-read from the environment")
        self.assertTrue(any((self.run_dir / "store").glob("*/paper.sqlite")))

    def test_read_pages_are_repeatable_and_complete(self):
        paper = self.bind_paper("ieee_single")
        store = PaperStore.open(self.workspace / "papers" / paper, run_dir=self.run_dir)
        expected = {p["page"]: p["text"] for p in store.pages()}
        actual, cursor = {}, None
        with mock.patch.object(reading, "READ_BUDGET", 1500):
            initial = server.read_pages()
            for _ in range(1000):
                reply = server.read_pages(cursor=cursor)
                self.assertEqual(reply["document_id"], store.meta()["fingerprint"])
                for fragment in reply["fragments"]:
                    number = fragment["page"]
                    actual[number] = actual.get(number, "") + fragment["text"]
                cursor = reply["next_cursor"]
                if cursor is None:
                    break
            else:
                self.fail("page traversal did not terminate")
            self.assertEqual(server.read_pages(), initial)
            server.get_paper_overview()
            self.assertEqual(server.read_pages(), initial)
        self.assertEqual(actual, expected)
        self.assertIn("[1]", actual[16] + actual[17])
        with self.assertRaisesRegex(ToolError, "outside this PDF"):
            server.read_pages(first_page=40)
        with self.assertRaisesRegex(ToolError, "Invalid cursor"):
            server.read_pages(cursor="p4@20")
        self.assertIsNone(store.get_state("pages_returned"))

    def test_sections_and_search(self):
        self.bind_paper("ieee_single")
        section_id = next(s["id"] for s in server.get_paper_overview()["outline"] if s["title"] == "RELATED WORK")
        section = server.read_section(section_id)
        self.assertEqual(section["section"]["title"], "RELATED WORK")
        self.assertTrue(section["fragments"])
        with self.assertRaisesRegex(ToolError, "Unknown section_id.*get_paper_overview"):
            server.read_section(9999)
        with mock.patch.object(reading, "READ_BUDGET", 31):
            cursor = server.read_section(section_id)["next_cursor"]
            with self.assertRaisesRegex(ToolError, "conflicts"):
                server.read_section(section_id + 1, cursor)
            with self.assertRaisesRegex(ToolError, "operation"):
                server.read_pages(cursor=cursor)
        hits = server.search_paper("Fig")
        self.assertGreaterEqual(hits["total_hits"], 3)
        self.assertTrue(all(4 <= hit["page"] <= 17 for hit in hits["hits"]))

    def test_search_protocol_pagination_and_errors(self):
        self.bind_paper("ieee_single")
        result = run(lambda client: client.call_tool("search_paper", {"query": "the"}))
        reply = json.loads(result.content[0].text)
        self.assertGreater(reply["total_hits"], len(reply["hits"]))
        cursor = reply["next_cursor"]
        self.assertTrue(cursor)
        self.assertEqual(server.search_paper("the", cursor=cursor), server.search_paper("the", cursor=cursor))
        with self.assertRaisesRegex(ToolError, "query conflicts"):
            server.search_paper("different", cursor=cursor)
        with self.assertRaisesRegex(ToolError, "last_page conflicts"):
            server.search_paper("the", last_page=2, cursor=cursor)
        with self.assertRaisesRegex(ToolError, "query"):
            server.search_paper(" ")
        with self.assertRaisesRegex(ToolError, "outside this PDF"):
            server.search_paper("the", first_page=99)


class TestAssets(ServerCase):
    def asset_id(self, stored_id):
        _, store = server._open()
        matches = [a for a in store.assets() if a["id"] == stored_id]
        self.assertEqual(len(matches), 1)
        return f"segment:{matches[0]['segment']}/{stored_id}"

    def test_list_and_inspect_items(self):
        self.bind_paper("ieee_single")
        listing = server.list_assets()
        self.assertEqual(listing["counts"]["figure"], 3)
        self.assertTrue(any(i["kind"] == "reference" for i in listing["items"]))
        table_id = self.asset_id("table:I")
        table = run(lambda client: client.call_tool("get_asset", {"asset_id": table_id}))
        detail = json.loads(table.content[0].text)
        self.assertEqual(detail["id"], table_id)
        self.assertEqual(detail["document_id"], listing["document_id"])
        self.assertTrue(detail["content"].startswith("|"))
        self.assertTrue(detail["cited_by"])
        self.assertEqual(detail["visual"]["status"], "not_requested")
        self.assertEqual((detail["first_page"], detail["last_page"]), (7, 7))
        self.assertEqual(detail["method"], "caption+table")
        self.assertEqual(detail["confidence"], "high")
        for item in self.catalog():
            found = json.loads(asset(item["id"])[0].text)
            self.assertEqual(found["id"], item["id"])
            self.assertEqual(found["label"], item["label"])

    def test_invalid_short_and_unknown_ids(self):
        self.bind_paper("ieee_single")
        for asset_id in (
            "figure:1",
            "page:01",
            "segment:02/figure:1",
            "segment:-1/figure:1",
            "segment:2/figure:",
            "segment:2/figure:1/extra",
            "segment:2/figure:1'",
            "",
        ):
            with self.subTest(asset_id=asset_id), self.assertRaisesRegex(ToolError, "Invalid asset_id.*list_assets"):
                asset(asset_id)
        for asset_id in ("segment:999/figure:1", "segment:2/figure:999"):
            with self.assertRaisesRegex(ToolError, "Unknown asset_id.*list_assets"):
                asset(asset_id)

    def test_repeatability_stale_state_and_more_than_six_assets(self):
        self.bind_paper("ieee_single")
        _, store = server._open()
        stale = {
            "assets_returned": "figure:1,table:I,figure:2,figure:3,equation:1,equation:2",
            "images_sent": "999",
            "pages_returned": "legacy",
        }
        for key, value in stale.items():
            store.set_state(key, value)
        ids = [i["id"] for i in self.catalog()]
        self.assertGreater(len(ids), 6)
        with ThreadPoolExecutor(4) as pool:
            replies = list(pool.map(lambda asset_id: asset(asset_id)[0].text, ids * 2))
        self.assertEqual(replies[: len(ids)], replies[len(ids) :])
        self.assertTrue(all("content" in json.loads(reply) for reply in replies))
        server.get_paper_overview()
        self.assertEqual({k: store.get_state(k) for k in stale}, stale)

    def test_zero_call_path_needs_no_visual_configuration_or_image_settings(self):
        self.bind_paper("ieee_single")
        asset_id = self.asset_id("figure:1")
        self.assertEqual(set(server.crops.settings()), {"max_side"})
        with (
            mock.patch.dict(os.environ, {name: "" for name in ENV}),
            mock.patch.object(server.crops, "settings") as settings,
            mock.patch.object(server.crops, "cached_png") as cached,
            mock.patch.object(visual_inspection, "load_visual_config") as config,
            mock.patch.object(visual_inspection, "AsyncOpenAI") as model,
        ):
            result = run(lambda client: client.call_tool("get_asset", {"asset_id": asset_id}))
            detail = json.loads(result.content[0].text)
            self.assertEqual(detail["visual"]["status"], "not_requested")
            self.assertTrue(detail["visual_available"])
            self.assertTrue(detail["content"] or detail["caption"])
            for operation in (settings, cached, config, model):
                operation.assert_not_called()
            self.assertFalse((self.run_dir / "images").exists())
            self.assertFalse((self.run_dir / "inspections").exists())

    def test_duplicate_ids_resolve_exact_segment_and_mentions(self):
        self.bind_paper("scholarone_two_copies")
        _, store = server._open()
        copies = [a for a in store.assets("figure") if a["id"] == "figure:1"]
        self.assertEqual(len(copies), 2)
        self.assertNotEqual(copies[0]["segment"], copies[1]["segment"])
        for index, item in enumerate(copies):
            marker = f"Unique copy {index}"
            with store.con:
                store.con.execute(
                    "UPDATE assets SET content = ? WHERE segment = ? AND id = ?", (marker, item["segment"], item["id"])
                )
                store.con.execute(
                    "UPDATE paragraphs SET text = ? WHERE id IN "
                    "(SELECT paragraph FROM mentions WHERE segment = ? AND asset = ?)",
                    (marker + " cites Fig. 1.", item["segment"], item["id"]),
                )
        store.set_manuscript_pages(24, 43, "Only the second copy is the inferred manuscript")
        for index, item in enumerate(copies):
            canonical = f"segment:{item['segment']}/{item['id']}"
            detail = json.loads(asset(canonical)[0].text)
            self.assertEqual(detail["content"], f"Unique copy {index}")
            self.assertEqual(detail["first_page"], item["page"])
            self.assertTrue(detail["cited_by"])
            self.assertTrue(all(f"Unique copy {index}" in m["text"] for m in detail["cited_by"]))
            self.assertIn(canonical, [i["id"] for i in self.catalog()])
        self.assertIsNone(store.asset(999, "figure:1"))


class TestCatalog(ServerCase):
    def test_page_catalog_is_lazy_paginated_and_filtered(self):
        self.bind_paper("ieee_single")
        with (
            mock.patch.object(server.crops, "crop_png") as crop,
            mock.patch.object(server.crops, "describe_region") as describe,
            mock.patch.object(server, "ASSET_PAGE_SIZE", 3),
        ):
            items = self.catalog(kind="page")
            self.assertEqual([item["id"] for item in items], [f"page:{p}" for p in range(1, 18)])
            self.assertTrue(all("content" not in item and "text" not in item for item in items))
            self.assertEqual(server.list_assets(kind="page")["counts"], {"page": 17})
            self.assertFalse(any(i["kind"] == "page" for i in self.catalog()))
            for args, expected in (
                ({"first_page": 5}, [5]),
                ({"last_page": 4}, [1, 2, 3, 4]),
                ({"first_page": 4, "last_page": 8}, list(range(4, 9))),
            ):
                self.assertEqual([i["first_page"] for i in self.catalog(kind="page", **args)], expected)
            cursor = server.list_assets(kind="page")["next_cursor"]
            self.assertEqual(server.list_assets(cursor=cursor), server.list_assets(cursor=cursor, kind="page"))
            with self.assertRaisesRegex(ToolError, "conflicts"):
                server.list_assets(cursor=cursor, kind="figure")
            for changes in ({"offset": 17}, {"last": 99}, {"document_id": "wrong"}, {"operation": "read_pages"}):
                with self.assertRaises(ToolError):
                    server.list_assets(cursor=changed_cursor(cursor, **changes))
            crop.assert_not_called()
            describe.assert_not_called()

    def test_traversal_tie_breaker_duplicates_and_exact_retrieval(self):
        self.bind_paper("scholarone_two_copies")
        _, store = server._open()
        # Force sequence ties to prove that the segment/ID tie-breaker is sufficient.
        with store.con:
            store.con.execute("UPDATE assets SET seq = 1")
        expected = sorted(store.assets(), key=lambda a: (a["segment"], a["id"]))
        self.assertGreater(len(expected), server.ASSET_PAGE_SIZE)
        initial = server.list_assets()
        actual = self.catalog()
        ids = [item["id"] for item in actual]
        self.assertEqual(ids, [f"segment:{a['segment']}/{a['id']}" for a in expected])
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(server.list_assets(), initial)
        self.assertEqual(self.catalog(), actual)
        for item, source in zip(actual, expected, strict=True):
            detail = json.loads(asset(item["id"])[0].text)
            self.assertEqual(detail["content"], source["content"])
            self.assertEqual((item["first_page"], item["last_page"]), (source["page"], source["last_page"]))
            self.assertEqual(item["cited_count"], len(store.asset(source["segment"], source["id"])["mentions"]))
            self.assertLessEqual(len(item["caption_preview"]), server.CAPTION_PREVIEW)
            self.assertEqual(item["region_available"], source["x0"] is not None)
        duplicates = [i for i in actual if i["id"].endswith("/figure:1")]
        self.assertEqual(len(duplicates), 2)
        self.assertEqual(duplicates[0]["label"], duplicates[1]["label"])
        self.assertNotEqual(duplicates[0]["id"], duplicates[1]["id"])

    def test_kind_range_defaults_overlap_and_empty_results(self):
        self.bind_paper("ieee_single")
        _, store = server._open()
        with store.con:
            store.con.execute("UPDATE assets SET last_page = 9 WHERE id = ?", ("table:I",))
        all_assets = store.assets()
        with mock.patch.object(server, "ASSET_PAGE_SIZE", 2):
            for args, low, high in (
                ({}, 1, 17),
                ({"first_page": 8}, 8, 8),
                ({"last_page": 8}, 1, 8),
                ({"first_page": 8, "last_page": 10}, 8, 10),
            ):
                for kind in (None, "figure", "reference", "table", "statement"):
                    with self.subTest(args=args, kind=kind):
                        actual = self.catalog(kind=kind, **args)
                        expected = [
                            a
                            for a in all_assets
                            if a["page"] <= high and a["last_page"] >= low and (kind is None or a["kind"] == kind)
                        ]
                        self.assertEqual(
                            [i["id"] for i in actual], [f"segment:{a['segment']}/{a['id']}" for a in expected]
                        )
                        self.assertEqual(
                            server.list_assets(kind=kind, **args)["counts"],
                            {k: sum(a["kind"] == k for a in expected) for k in {a["kind"] for a in expected}},
                        )
        overlap = server.list_assets(kind="table", first_page=8)["items"]
        self.assertEqual([(i["first_page"], i["last_page"]) for i in overlap], [(7, 9)])
        self.assertEqual(json.loads(asset(overlap[0]["id"])[0].text)["last_page"], 9)
        zero = server.list_assets(kind="statement")
        self.assertEqual((zero["total_assets"], zero["items"], zero["counts"], zero["next_cursor"]), (0, [], {}, None))
        self.assertTrue(any(i["kind"] == "reference" for i in self.catalog()))
        for first, last in ((0, 1), (3, 2), (1, 18), (18, None), (None, 0)):
            with self.assertRaises(ToolError):
                server.list_assets(first_page=first, last_page=last)
        with self.assertRaisesRegex(ToolError, "Invalid kind"):
            server.list_assets(kind="unknown")

    def test_cursor_replay_and_rejected_conflicts(self):
        self.bind_paper("ieee_single")
        with mock.patch.object(server, "ASSET_PAGE_SIZE", 2):
            cursor = server.list_assets(kind="reference", first_page=15, last_page=17)["next_cursor"]
            self.assertTrue(cursor)
            reply = server.list_assets(cursor=cursor)
            self.assertEqual(reply, server.list_assets(cursor=cursor))
            self.assertEqual(reply, server.list_assets(kind="reference", first_page=15, last_page=17, cursor=cursor))
            for kwargs in ({"kind": "figure"}, {"first_page": 16}, {"last_page": 16}):
                with self.assertRaisesRegex(ToolError, "conflicts"):
                    server.list_assets(cursor=cursor, **kwargs)
            for changes in (
                {"document_id": "other"},
                {"operation": "read_pages"},
                {"kind": "unknown"},
                {"first": None},
                {"last": 99},
                {"offset": -1},
                {"offset": True},
                {"offset": "2"},
                {"offset": 999999},
            ):
                with self.subTest(changes=changes), self.assertRaises(ToolError):
                    server.list_assets(cursor=changed_cursor(cursor, **changes))
            with self.assertRaisesRegex(ToolError, "operation"):
                server.read_pages(cursor=cursor)
        for cursor in ("", "bad cursor", "e30=", "W10=", "a" * 4097):
            with self.assertRaisesRegex(ToolError, "Invalid cursor"):
                server.list_assets(cursor=cursor)


class TestVisualAssets(ServerCase):
    def setUp(self):
        super().setUp()
        self.bind_paper("ieee_single")
        env = mock.patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        self.fake = FakeClient()
        patch = mock.patch.object(visual_inspection, "AsyncOpenAI", return_value=self.fake)
        self.factory = patch.start()
        self.addCleanup(patch.stop)
        settings = mock.patch.object(server.crops, "settings", return_value={"max_side": 200})
        settings.start()
        self.addCleanup(settings.stop)

    def call(self, asset_id, question="What is visible?"):
        result = run(lambda client: client.call_tool("get_asset", {"asset_id": asset_id, "question": question}))
        self.assertEqual([type(c).__name__ for c in result.content], ["TextContent"])
        return json.loads(result.content[0].text)

    def diagnostic(self, detail):
        path = self.run_dir / "inspections" / (detail["visual"]["inspection_id"] + ".json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_selected_crop_exact_bytes_and_fresh_inspections_reuse_png_after_reopen(self):
        import base64

        _, store = server._open()
        item = store.assets("figure")[0]
        asset_id = f"segment:{item['segment']}/{item['id']}"
        original = server.crops.crop_png

        def render_without_sqlite_lock(*args, **kwargs):
            with ThreadPoolExecutor(1) as pool:
                self.assertTrue(pool.submit(store.pages, 1, 1).result(timeout=5))
            return original(*args, **kwargs)

        with mock.patch.object(server.crops, "crop_png", side_effect=render_without_sqlite_lock) as render:
            first = self.call(asset_id, "  Exact question?  ")
            close_all()
            server.bind_document()
            second = self.call(asset_id)
            self.assertEqual(render.call_count, 1)
        self.assertEqual(self.fake.create.await_count, 2)
        self.assertNotEqual(first["visual"]["inspection_id"], second["visual"]["inspection_id"])
        self.assertEqual(first["content"], second["content"])
        record = self.diagnostic(first)
        self.assertEqual(record["question"], "  Exact question?  ")
        self.assertEqual(record["prompt"]["context"]["id"], asset_id)
        selected_png = (self.run_dir / record["image_reference"]).read_bytes()
        request = self.fake.create.call_args_list[0].kwargs
        image = request["messages"][1]["content"][2]["image_url"]["url"]
        self.assertEqual(base64.b64decode(image.split(",")[1]), selected_png)
        self.assertEqual(
            record["prompt"]["context"]["render"]["requested_bounds"], [item[k] for k in ("x0", "y0", "x1", "y1")]
        )

    def test_full_page_empty_text_and_invalid_ids_or_question(self):
        _, store = server._open()
        with store.con:
            store.con.execute("UPDATE pages SET text = '' WHERE page = 1")
        detail = self.call("page:1")
        self.assertEqual(detail["content"], "")
        self.assertEqual(detail["visual"]["status"], "success")
        self.assertEqual(detail["visual"]["rendered_pages"], [1])
        self.assertEqual(detail["visual"]["visual_coverage"], "single_page")
        self.assertEqual(self.diagnostic(detail)["prompt"]["context"]["id"], "page:1")
        for asset_id in ("page:0", "page:-1", "page:01", "page:x", "page:1/extra", "page:1.0", "page:", "page:18"):
            with self.subTest(asset_id=asset_id), self.assertRaises(ToolError):
                asset(asset_id)
        with mock.patch.object(server.crops, "cached_png") as cached:
            for question in ("", "  ", "\n\t", 4):
                with self.subTest(question=question):
                    response = run(
                        lambda c, question=question: c.call_tool(
                            "get_asset", {"asset_id": "page:1", "question": question}, raise_on_error=False
                        )
                    )
                    self.assertTrue(response.is_error)
            cached.assert_not_called()
        self.assertEqual(self.fake.create.await_count, 1)

    def test_multipage_clipping_and_missing_regions_have_no_fallback(self):
        _, store = server._open()
        item = store.assets("figure")[0]
        asset_id = f"segment:{item['segment']}/{item['id']}"
        first = item["page"]
        with store.con:
            store.con.execute(
                "UPDATE assets SET last_page = ? WHERE segment = ? AND id = ?", (first + 2, item["segment"], item["id"])
            )
        for bounds in (
            (-10, -5, 80, 40),
            (9000, 9000, 9100, 9100),
            (30, 30, 10, 10),
            (0, 0, float("inf"), 30),
            (None, 0, 30, 30),
        ):
            with store.con:
                store.con.execute(
                    "UPDATE assets SET x0=?, y0=?, x1=?, y1=? WHERE segment=? AND id=?",
                    (*bounds, item["segment"], item["id"]),
                )
            detail = self.call(asset_id)
            self.assertEqual(detail["content"], item["content"])
            self.assertEqual(detail["source_page_ids"], [f"page:{p}" for p in range(first, first + 3)])
            if bounds[0] == -10:
                visual = detail["visual"]
                self.assertEqual(visual["status"], "success")
                self.assertEqual(visual["render"]["effective_bounds"], [0, 0, 80, 40])
                self.assertEqual(visual["visual_coverage"], "partial")
                context = self.diagnostic(detail)["prompt"]["context"]
                for key in ("render", "rendered_pages", "visual_coverage", "source_page_ids", "limitations"):
                    self.assertEqual(context[key], visual[key])
                request_context = self.fake.create.call_args.kwargs["messages"][1]["content"][1]["text"]
                self.assertEqual(json.loads(request_context.split("\n", 1)[1]), context)
            else:
                self.assertEqual(detail["visual"]["status"], "unavailable")
                self.assertTrue(detail["visual"]["reason"])
                self.assertEqual(detail["rendered_pages"], [])
        self.fake.create.assert_awaited_once()

    def test_failures_preserve_content_and_are_distinguishable(self):
        for error, status in (
            (OSError("private path"), "render_error"),
            (server.crops.ImagePersistenceError("private path"), "image_persistence_error"),
        ):
            with mock.patch.object(server.crops, "cached_png", side_effect=error):
                detail = self.call("page:1")
                self.assertEqual(detail["visual"]["status"], status)
                self.assertTrue(detail["content"])
                self.assertNotIn("private path", json.dumps(detail))
        self.factory.assert_not_called()
        with mock.patch.dict(os.environ, {"SKYNET_API_KEY": ""}):
            detail = self.call("page:1")
            self.assertEqual(detail["visual"]["status"], "configuration_error")
            self.diagnostic(detail)
        with mock.patch.object(visual_inspection, "_atomic_diagnostic", side_effect=OSError("disk full")):
            detail = self.call("page:1")
            self.assertEqual(detail["visual"]["status"], "persistence_error")
            self.assertNotIn("inspection_id", detail["visual"])
        self.assertEqual(self.call("page:1")["visual"]["status"], "success")

    def test_errors_after_await_are_tool_errors(self):
        async def fail(**kwargs):
            await asyncio.sleep(0)
            raise server.ReviewError("Synthetic awaited failure.")

        with mock.patch.object(visual_inspection, "inspect_image", side_effect=fail):
            with self.assertRaisesRegex(ToolError, "Synthetic awaited failure"):
                asset("page:1", question="Test")
            result = run(
                lambda c: c.call_tool("get_asset", {"asset_id": "page:1", "question": "Test"}, raise_on_error=False)
            )
            self.assertTrue(result.is_error)
            self.assertIn("Synthetic awaited failure", result.content[0].text)

    def test_concurrent_mcp_requests_are_serial_and_recover_after_failure(self):
        active = maximum = count = 0
        _, store = server._open()

        async def respond(**kwargs):
            nonlocal active, maximum, count
            active += 1
            maximum = max(maximum, active)
            count += 1
            try:
                # Network await cannot own SQLite's lock or block the event loop.
                self.assertTrue(await asyncio.to_thread(store.pages, 1, 1))
                await asyncio.sleep(0.025)
                if count == 1:
                    raise TimeoutError("fake timeout")
                return completion()
            finally:
                active -= 1

        self.fake.create.side_effect = respond

        async def requests(client):
            return await asyncio.gather(
                *(client.call_tool("get_asset", {"asset_id": "page:1", "question": str(i)}) for i in range(4))
            )

        replies = run(requests)
        statuses = [json.loads(r.content[0].text)["visual"]["status"] for r in replies]
        self.assertEqual(statuses.count("timeout"), 1)
        self.assertEqual(statuses.count("success"), 3)
        self.assertEqual((maximum, active, count), (1, 0, 4))
        self.assertEqual(self.call("page:1")["visual"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
