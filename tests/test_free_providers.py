import io
import json
import os
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from toolvh.translation import APIConfig, Client, PROVIDERS, environment_key


class FreeProvidersTest(unittest.TestCase):
    def config(self, provider):
        return APIConfig(provider=provider, base_url=PROVIDERS[provider][1], api_key="dummy-secret",
                         model="vendor/model:free" if provider == "openrouter-free" else "chat-model")

    def test_both_presets_use_official_url_key_header_and_json(self):
        for provider in ("groq", "openrouter-free"):
            client = Client(self.config(provider))
            body = {"choices": [{"message": {"content": '{"translation":"Bắt đầu"}'}, "finish_reason": "stop"}]}
            with patch.object(client.opener, "open", return_value=io.BytesIO(json.dumps(body).encode())) as opened:
                self.assertEqual(client.test_connection(), "Bắt đầu")
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, PROVIDERS[provider][1] + "/chat/completions")
            self.assertNotIn("dummy-secret", request.full_url)
            self.assertEqual(request.get_header("Authorization"), "Bearer dummy-secret")
            payload = json.loads(request.data)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            if provider == "openrouter-free":
                self.assertEqual(payload["provider"], {"require_parameters": True})
                self.assertNotIn("models", payload)

    def test_openrouter_filters_paid_missing_prices_and_audio(self):
        client = Client(self.config("openrouter-free"))
        def model(name, p="0", c="0", output=None):
            return {"id": name, "pricing": {"prompt": p, "completion": c},
                    "architecture": {"output_modalities": output or ["text"]}}
        models = [model("a/model:free"), model("paid/model"), model("fake:free", "0", "0.001"),
                  model("invalid:free", "oops"), model("audio:free", output=["audio"]),
                  {"id": "missing:free"}, model("openrouter/free"), model("a/model:free")]
        with patch.object(client, "_request", return_value={"data": models}):
            self.assertEqual(client.list_models(), ["a/model:free", "openrouter/free"])

    def test_openrouter_paid_model_rejected_before_network(self):
        config = self.config("openrouter-free")
        for model in ("vendor/paid", "openrouter/auto", "vendor/free-model"):
            with self.assertRaisesRegex(ValueError, ":free"):
                Client(replace(config, model=model))
        Client(replace(config, model=""), require_model=False)

    def test_no_key_or_wrong_host_rejected(self):
        for provider in ("groq", "openrouter-free"):
            for config in (replace(self.config(provider), api_key=""),
                           replace(self.config(provider), base_url="https://example.com/v1")):
                with self.assertRaises(ValueError):
                    Client(config)

    def test_groq_filters_inactive_audio_and_guards(self):
        client = Client(self.config("groq"))
        ids = [{"id": "chat-model"}, {"id": "old-chat", "active": False}, {"id": "whisper-large"},
               {"id": "llama-prompt-guard"}, {"id": "orpheus-v1"}]
        with patch.object(client, "_request", return_value={"data": ids}):
            self.assertEqual(client.list_models(), ["chat-model"])

    def test_http_success_with_error_body_does_not_echo_secret(self):
        for provider in ("groq", "openrouter-free"):
            with patch.object(Client, "_request", return_value={"error": {"message": "dummy-secret"}}):
                with self.assertRaises(ValueError) as raised:
                    Client(self.config(provider)).test_connection()
            self.assertNotIn("dummy-secret", str(raised.exception))

    def test_provider_environment_keys_are_isolated(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "groq-secret", "OPENROUTER_API_KEY": "router-secret",
                                     "TOOLVH_API_KEY": "other-secret"}, clear=True):
            self.assertEqual(environment_key("groq"), "groq-secret")
            self.assertEqual(environment_key("openrouter-free"), "router-secret")
            self.assertEqual(environment_key("google-web"), "")
            self.assertEqual(environment_key("ollama"), "")


if __name__ == "__main__":
    unittest.main()
