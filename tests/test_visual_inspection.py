"""Synthetic one-request inspections; no endpoint or credentials are used."""

import asyncio
import base64
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx2
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletion
from openai.types.completion_usage import CompletionUsage

from reviewer_mcp import visual_inspection as visual
from reviewer_mcp.config import load_visual_config

ENV = {"SKYNET_BASE_URL": "https://example.invalid/v1", "SKYNET_API_KEY": "fake-secret-key",
       "VISUAL_INSPECTION_MODEL": "fake-visual-model", "VISUAL_INSPECTION_TIMEOUT_SECONDS": "5"}


def completion(content="Visible label A.", finish="stop", **message):
    return ChatCompletion.model_validate({
        "id": "fake-completion", "created": 0, "object": "chat.completion", "model": "fake-visual-model",
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": content, **message}}],
    })


class FakeClient:
    def __init__(self, response=None, effect=None):
        self.create = mock.AsyncMock(return_value=response or completion(), side_effect=effect)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True


class TestInspection(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = mock.patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        self.fake = FakeClient()
        patch = mock.patch.object(visual, "AsyncOpenAI", return_value=self.fake)
        self.factory = patch.start()
        self.addCleanup(patch.stop)
        self.png = b"synthetic-image-bytes-for-request-test"
        self.context = {"document_id": "doc", "id": "segment:0/figure:1", "first_page": 2,
                        "last_page": 4, "caption": "Fig. 1", "content": "Local text",
                        "rendered_pages": [2], "visual_coverage": "partial",
                        "render": {"clipped": True, "effective_bounds": [0, 0, 100, 50]},
                        "limitations": ["Only page 2's clipped first region is available."]}

    def invoke(self):
        return asyncio.run(visual.inspect_image(png=self.png, question="  What label is visible?\n",
                           context=self.context, image_reference="images/doc/region.png", run_dir=self.root))

    def diagnostic(self, result):
        path = self.root / "inspections" / (result["inspection_id"] + ".json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_exact_request_one_call_no_retries_and_optional_usage(self):
        result = self.invoke()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["answer"], "Visible label A.")
        self.fake.create.assert_awaited_once()
        self.factory.assert_called_once_with(base_url=ENV["SKYNET_BASE_URL"], api_key=ENV["SKYNET_API_KEY"],
                                             timeout=5, max_retries=0)
        request = self.fake.create.call_args.kwargs
        self.assertEqual(set(request), {"model", "stream", "timeout", "messages"})
        self.assertFalse(request["stream"])
        content = request["messages"][1]["content"]
        self.assertEqual(content[0]["text"], "  What label is visible?\n")
        self.assertEqual(json.loads(content[1]["text"].split("\n", 1)[1]), self.context)
        self.assertEqual(base64.b64decode(content[2]["image_url"]["url"].split(",")[1]), self.png)
        record = self.diagnostic(result)
        self.assertEqual(record["prompt"]["context"], self.context)
        self.assertEqual(record["image_reference"], "images/doc/region.png")
        self.assertNotIn("usage", record)
        self.assertGreaterEqual(record["duration_seconds"], 0)
        self.assertTrue(self.fake.closed)
        raw = json.dumps(record)
        for secret in (ENV["SKYNET_API_KEY"], base64.b64encode(self.png).decode(), "data:image"):
            self.assertNotIn(secret, raw)

    def test_response_is_on_disk_before_validation_for_every_outcome(self):
        original = visual._answer

        def validate(payload):
            records = [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("inspections/*.json")]
            received = [r for r in records if r["outcome"]["status"] == "received"]
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["response"], payload)
            return original(payload)

        for response, status in (
            (completion(), "success"), (completion("  "), "empty"), (completion("partial", "length"), "truncated"),
            (completion(None, refusal="No."), "refused"),
            (completion(None, "tool_calls", tool_calls=[{"id": "x", "type": "function",
              "function": {"name": "bad", "arguments": "{}"}}]), "invalid_response"),
        ):
            with self.subTest(status=status), mock.patch.object(visual, "_answer", side_effect=validate):
                self.fake.create.return_value = response
                result = self.invoke()
                self.assertEqual(result["status"], status)
                self.assertEqual(self.diagnostic(result)["response"], response.model_dump(mode="json"))
                if status != "success":
                    self.assertNotIn("answer", result)

    def test_missing_settings_and_bad_timeout_are_lazy_and_recorded(self):
        for name in ENV:
            with self.subTest(missing=name), mock.patch.dict(os.environ, {name: ""}):
                result = self.invoke()
                self.assertEqual(result["status"], "configuration_error")
                self.assertIn(name, result["reason"])
                self.assertIsNone(self.diagnostic(result)["response"])
        for timeout in ("0", "-1", "nan", "inf", "-inf", "garbage"):
            with self.subTest(timeout=timeout), mock.patch.dict(os.environ,
                                                              {"VISUAL_INSPECTION_TIMEOUT_SECONDS": timeout}):
                self.assertEqual(self.invoke()["status"], "configuration_error")
        self.factory.assert_not_called()
        with mock.patch.dict(os.environ, {"SKYNET_BASE_URL": "not a URL"}):
            with self.assertRaisesRegex(ValueError, "absolute HTTP"):
                load_visual_config()
        self.assertNotIn(ENV["SKYNET_API_KEY"], repr(load_visual_config()))

    def test_transport_api_timeout_failures_have_no_exception_secrets(self):
        request = httpx2.Request("POST", ENV["SKYNET_BASE_URL"], headers={"Authorization": ENV["SKYNET_API_KEY"]})
        for error, status in (
            (APITimeoutError(request=request), "timeout"),
            (APIConnectionError(request=request, message=ENV["SKYNET_API_KEY"]), "model_error"),
            (APIStatusError(ENV["SKYNET_API_KEY"], response=httpx2.Response(500, request=request), body={}),
             "model_error"),
        ):
            with self.subTest(status=status):
                self.fake.create.reset_mock(side_effect=True)
                self.fake.create.side_effect = error
                result = self.invoke()
                self.assertEqual(result["status"], status)
                self.fake.create.assert_awaited_once()
                raw = json.dumps(self.diagnostic(result))
                self.assertNotIn(ENV["SKYNET_API_KEY"], raw)
                self.assertNotIn("Authorization", raw)
                self.assertTrue(self.fake.closed)

    def test_required_write_failure_never_returns_success_or_id(self):
        for fail_at in (1, 2):
            original = visual._atomic_diagnostic
            count = 0

            def save(path, record, fail_at=fail_at, original=original):
                nonlocal count
                count += 1
                if count == fail_at:
                    raise OSError("disk failed")
                original(path, record)

            with self.subTest(fail_at=fail_at), mock.patch.object(visual, "_atomic_diagnostic", side_effect=save):
                result = self.invoke()
                self.assertEqual(result["status"], "persistence_error")
                self.assertNotIn("answer", result)
                self.assertNotIn("inspection_id", result)

    def test_failed_atomic_replacement_preserves_received_record(self):
        original = visual.os.replace
        replacements = 0

        def replace(source, destination):
            nonlocal replacements
            replacements += 1
            incoming = json.loads(source.read_text(encoding="utf-8"))
            if replacements == 2:
                self.assertEqual(incoming["outcome"]["status"], "success")
                self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["outcome"]["status"],
                                 "received")
                raise OSError("disk failed")
            original(source, destination)

        with mock.patch.object(visual.os, "replace", side_effect=replace):
            result = self.invoke()
        self.assertEqual(result["status"], "persistence_error")
        self.assertNotIn("inspection_id", result)
        records = list(self.root.glob("inspections/*.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text(encoding="utf-8"))["outcome"]["status"], "received")
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_installed_sdk_with_mock_http_transport_makes_one_request(self):
        captured = []

        def respond(request):
            captured.append(json.loads(request.content))
            return httpx2.Response(200, json=completion().model_dump(mode="json"))

        def factory(**kwargs):
            return AsyncOpenAI(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond)))

        self.factory.side_effect = factory
        self.assertEqual(self.invoke()["status"], "success")
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["messages"][1]["content"][0]["text"], "  What label is visible?\n")
        self.assertFalse(captured[0]["stream"])

    def test_usage_and_redaction_of_echoed_secrets_and_image(self):
        response = completion(ENV["SKYNET_API_KEY"] + " data:image/png;base64," + base64.b64encode(self.png).decode())
        response.usage = CompletionUsage(total_tokens=3, prompt_tokens=2, completion_tokens=1)
        self.fake.create.return_value = response
        result = self.invoke()
        raw = json.dumps(self.diagnostic(result))
        self.assertNotIn(ENV["SKYNET_API_KEY"], raw)
        self.assertNotIn(base64.b64encode(self.png).decode(), raw)
        self.assertIn("usage", self.diagnostic(result))

    def test_cancellation_releases_gate_for_active_and_waiting_inspections(self):
        async def scenario():
            entered = asyncio.Event()

            async def blocked(**kwargs):
                entered.set()
                await asyncio.Event().wait()

            self.fake.create.side_effect = blocked

            async def inspect():
                return await visual.inspect_image(png=self.png, question="test", context=self.context,
                                                  image_reference="images/test.png", run_dir=self.root)

            active = asyncio.create_task(inspect())
            await asyncio.wait_for(entered.wait(), 2)
            waiting = asyncio.create_task(inspect())
            await asyncio.sleep(0.02)
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting
            self.fake.create.assert_awaited_once()
            active.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await active
            self.assertTrue(self.fake.closed)
            self.fake.create.side_effect = None
            self.assertEqual((await asyncio.wait_for(inspect(), 2))["status"], "success")

        asyncio.run(scenario())
        records = [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("inspections/*.json")]
        self.assertEqual(sorted(r["outcome"]["status"] for r in records), ["cancelled", "cancelled", "success"])

    def test_process_serialization_survives_concurrent_event_loops(self):
        guard = threading.Lock()
        active = maximum = 0

        async def respond(**kwargs):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            try:
                await asyncio.sleep(0.03)
                return completion()
            finally:
                with guard:
                    active -= 1

        self.fake.create.side_effect = respond
        with ThreadPoolExecutor(3) as pool:
            results = list(pool.map(lambda _: self.invoke(), range(6)))
        self.assertTrue(all(r["status"] == "success" for r in results))
        self.assertEqual((maximum, active), (1, 0))
        self.assertEqual(len({r["inspection_id"] for r in results}), 6)


if __name__ == "__main__":
    unittest.main()
