import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from toolvh.model import Entry, Project, FileRecord
from toolvh.translation import APIConfig, Client, GEMINI_BASE_URL, translate
from toolvh.settings import SettingsStore
from toolvh.diagnostics import compatibility_report


def response(data):
    return io.BytesIO(json.dumps(data).encode())


class GeminiTest(unittest.TestCase):
    def config(self, **kwargs):
        return APIConfig(provider="gemini", base_url=GEMINI_BASE_URL, model="gemini-test", api_key="dummy-secret", delay_seconds=0, **kwargs)

    def test_native_request_and_response(self):
        client = Client(self.config())
        reply = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "internal reasoning", "thought": True}, {"text": '{"translation":"Bắt đầu chơi"}'}]}}]}
        with patch.object(client.opener, "open", return_value=response(reply)) as opened:
            result = client.complete([{"role": "system", "content": "Return JSON"}, {"role": "user", "content": "Start game"}], threading.Event())
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, GEMINI_BASE_URL + "/models/gemini-test:generateContent")
        self.assertNotIn("dummy-secret", request.full_url)
        self.assertEqual(dict((k.lower(), v) for k, v in request.header_items())["x-goog-api-key"], "dummy-secret")
        body = json.loads(request.data)
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "Return JSON")
        self.assertEqual(body["contents"][0]["parts"][0]["text"], "Start game")
        self.assertEqual(result["translation"], "Bắt đầu chơi")

    def test_models_pagination_filters_and_deduplicates(self):
        client = Client(replace(self.config(), model=""), require_model=False)
        pages = [{"models": [{"name": "models/gemini-test", "supportedGenerationMethods": ["generateContent"]},
                              {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]}], "nextPageToken": "next/+"},
                 {"models": [{"name": "models/gemini-test", "supportedGenerationMethods": ["generateContent"]},
                              {"name": "models/gemini-test-tts", "supportedGenerationMethods": ["generateContent"]}]}]
        with patch.object(client.opener, "open", side_effect=[response(p) for p in pages]) as opened:
            self.assertEqual(client.list_models(), ["gemini-test"])
        self.assertIn("pageToken=next%2F%2B", opened.call_args.args[0].full_url)

    def test_models_repeating_pagination_stops(self):
        client = Client(self.config())
        with patch.object(client, "_request", return_value={"models": [], "nextPageToken": "same"}):
            with self.assertRaises(ValueError):
                client.list_models()

    def test_model_list_can_correct_a_mistyped_model(self):
        client = Client(replace(self.config(), model="mistyped model name"), require_model=False)
        with patch.object(client, "_request", return_value={"models": []}):
            self.assertEqual(client.list_models(), [])

    def test_requires_key_and_official_endpoint(self):
        for config in [replace(self.config(), api_key=""), replace(self.config(), base_url="https://example.com/v1beta")]:
            with self.assertRaises(ValueError):
                Client(config)

    def test_rejects_truncated_or_blocked_response(self):
        client = Client(self.config())
        for reply in [{"candidates": []}, {"candidates": [{"finishReason": "MAX_TOKENS"}]}]:
            with patch.object(client, "_request", return_value=reply):
                with self.assertRaises(ValueError):
                    client.complete([], threading.Event())

    def test_http_error_does_not_echo_key_or_response(self):
        client = Client(self.config())
        error = urllib.error.HTTPError(GEMINI_BASE_URL, 403, "dummy-secret", {}, io.BytesIO(b"dummy-secret"))
        with patch.object(client.opener, "open", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                client.complete([], threading.Event())
        self.assertIn("403", str(raised.exception))
        self.assertNotIn("dummy-secret", str(raised.exception))

    def test_header_newline_error_is_redacted(self):
        with self.assertRaises(ValueError) as raised:
            Client(replace(self.config(), api_key="dummy-secret\nline"))
        self.assertNotIn("dummy-secret", str(raised.exception))

    def test_payment_required_is_billing_and_never_retried(self):
        for code, body in [(402, b'not JSON dummy-secret'),
                           (429, b'{"error":{"message":"Your prepayment credits are depleted. dummy-secret"}}')]:
            client = Client(self.config())
            error = urllib.error.HTTPError(GEMINI_BASE_URL, code, "dummy-secret", {}, io.BytesIO(body))
            with patch.object(client.opener, "open", side_effect=error) as opened:
                with self.assertRaises(RuntimeError) as raised:
                    client.test_connection()
            self.assertEqual(opened.call_count, 1)
            self.assertIn("Prepay", str(raised.exception))
            self.assertIn("Billing", str(raised.exception))
            self.assertNotIn("dummy-secret", str(raised.exception))

    def test_invalid_key_and_disabled_api_have_specific_hints(self):
        for reason, expected in [("API_KEY_INVALID", "key không hợp lệ"), ("SERVICE_DISABLED", "chưa được bật")]:
            client = Client(self.config())
            body = json.dumps({"error": {"message": "dummy-secret", "details": [{"reason": reason}]}}).encode()
            error = urllib.error.HTTPError(GEMINI_BASE_URL, 400, "bad request", {}, io.BytesIO(body))
            with patch.object(client.opener, "open", side_effect=error):
                with self.assertRaises(RuntimeError) as raised:
                    client.test_connection()
            self.assertIn(expected, str(raised.exception))
            self.assertNotIn("dummy-secret", str(raised.exception))

    def test_connection_test_checks_generation(self):
        client = Client(self.config())
        with patch.object(client, "complete", return_value={"translation": "Bắt đầu"}) as completed:
            self.assertEqual(client.test_connection(), "Bắt đầu")
        self.assertIn("Start game", completed.call_args.args[0][1]["content"])


class MemoryTest(unittest.TestCase):
    def entry(self, id, file="data", translation=""):
        return Entry(id, file, {"type": "TextAsset"}, "Start game", "Localization / menu.start", translation=translation)

    def test_duplicate_unity_entries_use_one_model_item(self):
        project = Project(".", entries=[self.entry("a", "one"), self.entry("b", "two")])
        def complete(client, messages, stop):
            items = json.loads(messages[1]["content"])["items"]
            self.assertEqual(len(items), 1)
            return {"translations": [{"id": items[0]["id"], "text": "Bắt đầu"}]}
        with patch.object(Client, "complete", complete):
            count = translate(project, APIConfig(model="test", delay_seconds=0))
        self.assertEqual(count, 2)
        self.assertEqual([e.translation for e in project.entries], ["Bắt đầu", "Bắt đầu"])

    def test_memory_reuses_previous_and_respects_preview_limit(self):
        project = Project(".", entries=[self.entry("a", translation="Bắt đầu"), self.entry("b"), self.entry("c")])
        with patch.object(Client, "complete") as completed:
            count = translate(project, APIConfig(model="test", delay_seconds=0), limit=1)
        self.assertEqual(count, 1)
        self.assertEqual(project.entries[1].translation, "Bắt đầu")
        self.assertEqual(project.entries[2].translation, "")
        completed.assert_not_called()

    def test_cancel_does_not_apply_memory(self):
        project = Project(".", entries=[self.entry("a", translation="Bắt đầu"), self.entry("b")])
        stop = threading.Event()
        stop.set()
        translate(project, APIConfig(model="test"), stop=stop)
        self.assertEqual(project.entries[1].translation, "")


class SettingsTest(unittest.TestCase):
    def test_unremembered_key_is_never_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            config = APIConfig(api_key="dummy-secret")
            store.save("openai-compatible", {"openai-compatible": (config, False)}, ["project.json"])
            self.assertNotIn("dummy-secret", store.path.read_text())
            loaded = store.load()
            self.assertEqual(loaded["profiles"]["openai-compatible"][0].api_key, "")
            self.assertEqual(loaded["recent"], ["project.json"])

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_dpapi_roundtrip_and_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            config = APIConfig(provider="gemini", base_url=GEMINI_BASE_URL, api_key="dummy-secret")
            store.save("gemini", {"gemini": (config, True)}, [])
            self.assertNotIn("dummy-secret", store.path.read_text())
            self.assertEqual(store.load()["profiles"]["gemini"][0].api_key, "dummy-secret")
            store.save("gemini", {"gemini": (replace(config, api_key=""), False)}, [])
            self.assertEqual(store.load()["profiles"]["gemini"][0].api_key, "")

    def test_support_report_distinguishes_unsupported_and_deferred(self):
        p = Project(".", files=[FileRecord("x", "bundle"), FileRecord("large", "skipped"),
                               FileRecord("bin", "dat", note="Định dạng chưa hỗ trợ ghi lại.")])
        report = compatibility_report(p)
        self.assertEqual(report["bundle_files_not_scanned"], 1)
        self.assertEqual(report["unsupported_files"], 1)
        self.assertEqual(report["oversized_files"], 1)


if __name__ == "__main__":
    unittest.main()
