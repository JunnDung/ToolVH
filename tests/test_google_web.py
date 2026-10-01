import io
import json
import threading
import unittest
from unittest.mock import patch

from toolvh.formats import extract
from toolvh.model import Project
from toolvh.translation import APIConfig, Client, GOOGLE_WEB_URL, mask, unmask, translate, validate


class GoogleWebTest(unittest.TestCase):
    def client(self):
        return Client(APIConfig(provider="google-web", base_url=GOOGLE_WEB_URL))

    def test_key_and_custom_endpoint_rejected(self):
        for key, url in [("secret", GOOGLE_WEB_URL), ("", "https://example.org")]:
            with self.assertRaises(ValueError):
                Client(APIConfig(provider="google-web", base_url=url, api_key=key))

    def test_request_is_english_to_vietnamese_without_key(self):
        client = self.client()
        reply = io.BytesIO(json.dumps([[["Bắt đầu", "Start game"]], None, "en"]).encode())
        with patch.object(client.opener, "open", return_value=reply) as opened:
            self.assertEqual(client.test_connection(), "Bắt đầu")
        request = opened.call_args.args[0]
        self.assertIn("sl=en&tl=vi", request.full_url)
        self.assertNotIn("Authorization", request.headers)

    def test_placeholders_tags_and_whitespace_preserved(self):
        source = '<b>Hello {player}</b>\n%02d'
        masked, prefix, tokens = mask(source)
        client = self.client()
        with patch.object(client, "_request", return_value=[[["Xin chào", "Hello"]]]) as called:
            result = unmask(client.google_web_text(masked, threading.Event()), prefix, tokens)
        self.assertEqual(result, '<b>Xin chào {player}</b>\n%02d')
        self.assertEqual(called.call_count, 1)
        self.assertFalse(validate(source, result))
        self.assertNotIn("__VH", called.call_args.args[0])

    def test_changed_response_and_long_text_rejected(self):
        for reply in [{}, [None], [[[]]], [[[None]]]]:
            client = self.client()
            with patch.object(client, "_request", return_value=reply):
                with self.assertRaises(ValueError):
                    client.test_connection()
        with self.assertRaises(ValueError):
            self.client().google_web_text("a" * 4001, threading.Event())

    def test_cancel_before_network(self):
        stop = threading.Event(); stop.set()
        client = self.client()
        with patch.object(client, "_request") as request:
            with self.assertRaises(InterruptedError):
                client.google_web_text("Start game", stop)
            request.assert_not_called()

    def test_each_sentence_checkpoint_survives_later_service_failure(self):
        project = Project(".", entries=extract('["Start game", "Quit game"]', "json", "en.json"))
        saved = []
        replies = [[[["Bắt đầu", "Start game"]]], RuntimeError("blocked")]
        with patch.object(Client, "_request", side_effect=replies), patch.object(threading.Event, "wait", return_value=False):
            with self.assertRaises(RuntimeError):
                translate(project, APIConfig(provider="google-web", base_url=GOOGLE_WEB_URL),
                          save=lambda: saved.append(1))
        self.assertEqual(saved, [1])
        self.assertEqual(project.entries[0].translation, "Bắt đầu")
        self.assertFalse(project.entries[1].translation)
