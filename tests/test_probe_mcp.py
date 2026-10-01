"""Probe CLI and fake clients: no live endpoints, credentials or corpus needed."""

import asyncio
import contextlib
import importlib.util
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pymupdf

if importlib.util.find_spec("dotenv") is None:
    raise unittest.SkipTest("Install .[probes] to run optional probe tests.")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_mcp.py"
SPEC = importlib.util.spec_from_file_location("probe_mcp", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def response(data):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(data))], isError=False)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="probe with spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / "source paper.pdf"
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), "Synthetic antenna geometry")
            doc.save(self.pdf)
        self.run_dir = self.root / "run directory"
        self.env_file = self.root / "local.env"
        self.common = ["--pdf", str(self.pdf), "--run-dir", str(self.run_dir), "--env-file", str(self.env_file)]
        self.addCleanup(logging.disable, logging.NOTSET)

    def args(self, command="catalog", *extra):
        return probe.parser().parse_args([command, *self.common, *extra])

    def test_environment_precedence_alias_and_forwarding(self):
        self.env_file.write_text(
            "SKYNET_API_KEY=file-key\nSKYNET_BASE_URL=https://example.invalid/v1\nIMAGE_ANALYSIS_MODEL=file-image\n",
            encoding="utf-8",
        )
        with mock.patch.dict(
            os.environ, {"SKYNET_API_KEY": "process-key", "IMAGE_ANALYSIS_MODEL": "process-image"}, clear=True
        ):
            env = probe.environment(self.args())
            self.assertEqual(env["SKYNET_API_KEY"], "process-key")
            self.assertEqual(env["SKYNET_BASE_URL"], "https://example.invalid/v1")
            self.assertEqual(env["VISUAL_INSPECTION_MODEL"], "process-image")
            self.assertEqual(env["VISUAL_INSPECTION_TIMEOUT_SECONDS"], "600")
            self.assertEqual(env["PDF_INGESTION_PDF"], str(self.pdf))
            self.assertEqual(env["PDF_INGESTION_RUN_DIR"], str(self.run_dir))
            self.assertNotIn("VISUAL_INSPECTION_MODEL", os.environ)
        with mock.patch.dict(os.environ, {"VISUAL_INSPECTION_MODEL": "explicit"}, clear=True):
            self.assertEqual(probe.environment(self.args())["VISUAL_INSPECTION_MODEL"], "explicit")
        with self.env_file.open("a", encoding="utf-8") as file:
            file.write("VISUAL_INSPECTION_MODEL=file-visual\n")
        with mock.patch.dict(os.environ, {"IMAGE_ANALYSIS_MODEL": "alias"}, clear=True):
            self.assertEqual(probe.environment(self.args())["VISUAL_INSPECTION_MODEL"], "file-visual")

    def test_timeout_and_turn_overrides(self):
        args = self.args("agent", "--agent-model", "chosen", "--visual-timeout", "700", "--max-turns", "3")
        self.assertEqual(args.visual_timeout, 700)
        self.assertEqual(probe.environment(args)["VISUAL_INSPECTION_TIMEOUT_SECONDS"], "700.0")
        self.assertEqual(args.max_turns, 3)

    def test_required_and_invalid_arguments(self):
        cases = [
            ["catalog"],
            ["catalog", "--pdf", str(self.pdf)],
            ["catalog", "--run-dir", str(self.root)],
            ["inspect", *self.common],
            ["agent", *self.common],
            ["agent", *self.common, "--agent-model", " "],
            ["catalog", *self.common, "--visual-timeout", "nan"],
            ["inspect", *self.common, "--asset-id", "page:1", "--question", "Q", "--repeat", "0"],
        ]
        for argv in cases:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                probe.parser().parse_args(argv)
        self.assertEqual(self.args("agent", "--agent-model", "chosen").max_turns, 8)

    def test_installed_executable_resolution(self):
        self.assertEqual(Path(probe.executable()).parent, Path(sys.executable).parent)
        self.assertTrue(Path(probe.executable()).is_file())

    def test_cli_help_and_synthetic_catalog_subprocess(self):
        for argv in (["--help"], ["inspect", "--help"], ["catalog", *self.common]):
            result = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            if argv == ["inspect", "--help"]:
                self.assertIn("default: 600", result.stdout)
        report = json.loads(next(self.run_dir.glob("probe-catalog-*.json")).read_text(encoding="utf-8"))
        self.assertTrue(report["operational_success"])
        self.assertEqual([c["tool"] for c in report["calls"]], ["get_paper_overview", "list_assets"])
        self.assertFalse(list(self.run_dir.rglob("*.png")))
        self.assertFalse((self.run_dir / "inspections").exists())

    def test_catalog_pagination(self):
        fake = mock.MagicMock()
        fake.__aenter__ = mock.AsyncMock(return_value=fake)
        fake.__aexit__ = mock.AsyncMock(return_value=False)
        fake.call_tool = mock.AsyncMock(
            side_effect=[
                response({}),
                response({"items": [], "next_cursor": "opaque"}),
                response({"items": [], "next_cursor": None}),
            ]
        )
        with mock.patch.object(probe, "Client", return_value=fake) as client, contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(asyncio.run(probe.direct(self.args(), {}, {"calls": []})))
        self.assertEqual(client.call_args.kwargs["timeout"], 660)
        fake.call_tool.assert_awaited_with("list_assets", {"cursor": "opaque"})
        fake.__aexit__.assert_awaited_once()

    def inspection(self, fail=False, duplicate=False, mutate=False, status=None):
        args = self.args("inspect", "--asset-id", "page:1", "--question", " exact question \n", "--repeat", "2")
        image = self.run_dir / probe.image_reference("document", "page:1")
        image.parent.mkdir(parents=True)
        image.write_bytes(b"png")
        counter = 0

        async def call(_name, arguments):
            nonlocal counter
            if "question" not in arguments:
                return response({"visual": {"status": "not_requested"}})
            counter += 1
            self.assertEqual(arguments["question"], args.question)
            if mutate and counter == 2:
                image.write_bytes(b"changed")
            return response(
                {
                    "id": "page:1",
                    "document_id": "document",
                    "rendered_pages": [1],
                    "visual": {
                        "status": status or ("timeout" if fail else "success"),
                        "inspection_id": "same" if duplicate else str(counter),
                        "answer": "visible component",
                        "visual_coverage": "single_page",
                    },
                }
            )

        fake = mock.MagicMock()
        fake.__aenter__ = mock.AsyncMock(return_value=fake)
        fake.__aexit__ = mock.AsyncMock(return_value=False)
        fake.call_tool = mock.AsyncMock(side_effect=call)
        report = {"calls": []}
        with mock.patch.object(probe, "Client", return_value=fake), contextlib.redirect_stdout(io.StringIO()):
            result = asyncio.run(probe.direct(args, {}, report))
        self.assertEqual(fake.call_tool.await_count, 3)
        fake.__aexit__.assert_awaited_once()
        return result, report

    def test_repeat_success(self):
        result, report = self.inspection()
        self.assertTrue(result)
        self.assertTrue(report["repeat_check"]["successful_cache_and_vision_check"])

    def test_failed_vision_is_not_cache_success(self):
        result, report = self.inspection(fail=True)
        self.assertFalse(result)
        self.assertTrue(report["repeat_check"]["png_content_and_mtime_unchanged"])
        self.assertFalse(report["repeat_check"]["successful_cache_and_vision_check"])

    def test_direct_unavailable_inspection_is_failure(self):
        result, report = self.inspection(status="unavailable")
        self.assertFalse(result)
        self.assertFalse(report["visual_succeeded"])
        self.assertEqual(report["calls"][1]["result"]["visual"]["status"], "unavailable")

    def test_duplicate_diagnostics_fail(self):
        self.assertFalse(self.inspection(duplicate=True)[0])

    def test_changed_png_fails(self):
        self.assertFalse(self.inspection(mutate=True)[0])

    def test_failure_artifact_and_redaction(self):
        async def failing(_args, _env, report):
            report["calls"].append({"answer": "key-secret https://endpoint.invalid data:image/png;base64,AAAA"})
            raise RuntimeError("key-secret")

        output = io.StringIO()
        with (
            mock.patch.object(probe, "direct", side_effect=failing),
            mock.patch.dict(
                os.environ, {"SKYNET_API_KEY": "key-secret", "SKYNET_BASE_URL": "https://endpoint.invalid"}
            ),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(probe.main(["catalog", *self.common]), 1)
        saved = next(self.run_dir.glob("probe-*.json")).read_text(encoding="utf-8")
        for forbidden in ("key-secret", "https://endpoint.invalid", "AAAA"):
            self.assertNotIn(forbidden, saved + output.getvalue())
        self.assertEqual(json.loads(saved)["error_type"], "RuntimeError")

    def test_unsuccessful_inspection_exit_status(self):
        with (
            mock.patch.object(probe, "direct", new_callable=mock.AsyncMock, return_value=False),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = probe.main(["inspect", *self.common, "--asset-id", "page:1", "--question", "Geometry?"])
        self.assertEqual(code, 1)
        record = json.loads(next(self.run_dir.glob("probe-inspect-*.json")).read_text(encoding="utf-8"))
        self.assertFalse(record["operational_success"])

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_agent_configuration_recording_and_cleanup(self):
        from agents import Runner
        from agents.mcp import MCPServerStdio

        async def run(agent, question, **kwargs):
            self.assertEqual(agent.model.model, "explicit-agent")
            self.assertEqual(agent.model._client.max_retries, 0)
            self.assertEqual(agent.model._client.timeout, args.visual_timeout)
            self.assertFalse(agent.model_settings.parallel_tool_calls)
            self.assertTrue(kwargs["run_config"].tracing_disabled)
            self.assertEqual(kwargs["max_turns"], 8)
            self.assertEqual(question, probe.QUESTION)
            server = agent.mcp_servers[0]
            self.assertEqual(server.max_retry_attempts, 0)
            self.assertEqual(server.client_session_timeout_seconds, args.visual_timeout + 60)
            self.assertEqual(server.params.env["VISUAL_INSPECTION_MODEL"], "explicit-visual")
            await server.call_tool("get_asset", {"asset_id": "page:1", "question": "geometry?"})
            return SimpleNamespace(final_output="Visible antenna.")

        args = self.args("agent", "--agent-model", "explicit-agent")
        env = {
            "SKYNET_API_KEY": "fake",
            "SKYNET_BASE_URL": "https://example.invalid/v1",
            "VISUAL_INSPECTION_MODEL": "explicit-visual",
        }
        for effect in (run, RuntimeError("failure"), asyncio.CancelledError()):
            report = {"calls": [], "visual_succeeded": False}
            with (
                mock.patch.object(MCPServerStdio, "connect", new_callable=mock.AsyncMock),
                mock.patch.object(MCPServerStdio, "cleanup", new_callable=mock.AsyncMock) as cleanup,
                mock.patch.object(
                    MCPServerStdio,
                    "list_tools",
                    new_callable=mock.AsyncMock,
                    return_value=[SimpleNamespace(name=n) for n in probe.TOOLS],
                ),
                mock.patch.object(
                    MCPServerStdio,
                    "call_tool",
                    new_callable=mock.AsyncMock,
                    return_value=response({"visual": {"status": "success", "inspection_id": "unique"}}),
                ),
                mock.patch.object(Runner, "run", side_effect=effect),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                if callable(effect):
                    self.assertTrue(asyncio.run(probe.agent(args, env, report)))
                    self.assertEqual(report["calls"][0]["visual"]["inspection_id"], "unique")
                else:
                    with self.assertRaises(type(effect)):
                        asyncio.run(probe.agent(args, env, report))
                cleanup.assert_awaited_once()

    def agent_scenario(
        self, statuses, *, final_answer="Visible geometry; unresolved dimensions remain uncertain.", error=None
    ):
        from agents import Runner
        from agents.mcp import MCPServerStdio

        results = [
            status
            if isinstance(status, Exception)
            else response(
                {"visual": {"status": status, "reason": f"attempt-{i}", "inspection_id": f"inspection-{i}"}}
            )
            for i, status in enumerate(statuses)
        ]

        async def run(agent, *_args, **kwargs):
            self.assertEqual(kwargs["max_turns"], 3)
            server = agent.mcp_servers[0]
            for i, status in enumerate(statuses):
                arguments = {"asset_id": "segment:1/figure:7" if i == 0 else "page:1", "question": "Geometry?"}
                if isinstance(status, Exception):
                    with self.assertRaises(type(status)):
                        await server.call_tool("get_asset", arguments)
                else:
                    await server.call_tool("get_asset", arguments)
            if error is not None:
                raise error
            return SimpleNamespace(final_output=final_answer)

        with (
            mock.patch.dict(os.environ, {"SKYNET_API_KEY": "fake", "SKYNET_BASE_URL": "https://example.invalid/v1"}),
            mock.patch.object(MCPServerStdio, "connect", new_callable=mock.AsyncMock),
            mock.patch.object(MCPServerStdio, "cleanup", new_callable=mock.AsyncMock) as cleanup,
            mock.patch.object(
                MCPServerStdio, "list_tools", new_callable=mock.AsyncMock,
                return_value=[SimpleNamespace(name=n) for n in probe.TOOLS],
            ),
            mock.patch.object(MCPServerStdio, "call_tool", new_callable=mock.AsyncMock, side_effect=results) as call,
            mock.patch.object(Runner, "run", side_effect=run),
            mock.patch.object(probe.uuid, "uuid4", return_value=SimpleNamespace(hex="scenario")),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = probe.main(["agent", *self.common, "--agent-model", "fake-agent", "--max-turns", "3"])
        cleanup.assert_awaited_once()
        self.assertEqual(call.await_count, len(statuses))
        return code, json.loads((self.run_dir / "probe-agent-scenario.json").read_text(encoding="utf-8"))

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_agent_unavailable_crop_then_successful_page_is_recovery(self):
        code, report = self.agent_scenario(["unavailable", "success"])
        self.assertEqual(code, 0)
        self.assertTrue(report["operational_success"])
        self.assertTrue(report["visual_succeeded"])
        self.assertTrue(report["final_answer"].strip())
        self.assertEqual(len(report["calls"]), 2)
        for i, status in enumerate(("unavailable", "success")):
            entry = report["calls"][i]
            self.assertEqual(entry["outcome"], "returned")
            self.assertEqual(entry["visual"]["status"], status)
            self.assertEqual(entry["visual"]["reason"], f"attempt-{i}")
            self.assertEqual(
                entry["artifacts"]["diagnostic"], str(self.run_dir / "inspections" / f"inspection-{i}.json")
            )
        self.assertEqual(report["calls"][0]["arguments"]["asset_id"], "segment:1/figure:7")
        self.assertEqual(report["calls"][1]["arguments"]["asset_id"], "page:1")

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_agent_unavailable_only_is_failure(self):
        code, report = self.agent_scenario(["unavailable"])
        self.assertEqual(code, 1)
        self.assertFalse(report["operational_success"])
        self.assertFalse(report["visual_succeeded"])
        self.assertEqual(report["calls"][0]["visual"]["status"], "unavailable")

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_agent_success_then_max_turns_is_failure(self):
        from agents.exceptions import MaxTurnsExceeded

        code, report = self.agent_scenario(["success"], error=MaxTurnsExceeded("Narrow task did not finish."))
        self.assertEqual(code, 1)
        self.assertTrue(report["visual_succeeded"])
        self.assertFalse(report["operational_success"])
        self.assertEqual(report["error_type"], "MaxTurnsExceeded")
        self.assertEqual(report["calls"][0]["visual"]["status"], "success")

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_agent_visual_failure_is_failure_even_with_success(self):
        for status in ("timeout", "model_error", "render_error"):
            with self.subTest(status=status):
                code, report = self.agent_scenario([status, "success"])
                self.assertEqual(code, 1)
                self.assertTrue(report["visual_succeeded"])
                self.assertFalse(report["operational_success"])
                self.assertEqual(report["calls"][0]["visual"]["status"], status)

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_agent_tool_exception_is_failure_even_with_success(self):
        code, report = self.agent_scenario([RuntimeError("Tool failed."), "success"])
        self.assertEqual(code, 1)
        self.assertTrue(report["visual_succeeded"])
        self.assertFalse(report["operational_success"])
        self.assertEqual(report["calls"][0]["outcome"], "error")
        self.assertEqual(report["calls"][0]["error_type"], "RuntimeError")

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_agent_success_without_final_answer_is_failure(self):
        for answer in (None, "", " \n "):
            with self.subTest(answer=answer):
                code, report = self.agent_scenario(["success"], final_answer=answer)
                self.assertEqual(code, 1)
                self.assertTrue(report["visual_succeeded"])
                self.assertFalse(report["operational_success"])

    @unittest.skipUnless(importlib.util.find_spec("agents"), "Install .[probes] for SDK tests.")
    def test_text_only_agent_is_not_visual_success(self):
        from agents import Runner

        # Real SDK stdio connection to the installed server, mocked model loop.
        args = self.args("agent", "--agent-model", "unused")
        env = probe.environment(args)
        env.update(SKYNET_API_KEY="fake", SKYNET_BASE_URL="https://example.invalid/v1")
        report = {"calls": [], "visual_succeeded": False}

        async def text_only(agent, *_args, **_kwargs):
            await agent.mcp_servers[0].call_tool("get_asset", {"asset_id": "page:1"})
            return SimpleNamespace(final_output="Only text; vision untested.")

        with mock.patch.object(Runner, "run", side_effect=text_only), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(asyncio.run(probe.agent(args, env, report)))
        self.assertEqual(report["calls"][0]["visual"]["status"], "not_requested")
        self.assertFalse(list(self.run_dir.rglob("*.png")))
