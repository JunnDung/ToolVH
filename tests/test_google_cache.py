import json
import tempfile
import threading
import unittest
import urllib.parse
import urllib.error
from pathlib import Path
from unittest.mock import patch

from toolvh.formats import extract
from toolvh.model import Project, digest
from toolvh.scanner import carry_translations
from toolvh.translation import APIConfig, Client, GOOGLE_WEB_URL, google_chunks, mask, translate, unmask


class GoogleCacheTests(unittest.TestCase):
    def config(self):
        return APIConfig(provider='google-web', base_url=GOOGLE_WEB_URL, delay_seconds=2)

    def project(self):
        entries = extract('"Start game"', 'json', 'en/a.json') + extract('"Start game"', 'json', 'en/b.json')
        return Project('.', entries=entries)

    def test_repeated_segments_send_once_without_double_wait(self):
        project = self.project()
        with patch.object(Client, '_request', return_value=[[["Bắt đầu", "Start game"]]]) as request, \
                patch.object(threading.Event, 'wait', return_value=False) as wait:
            self.assertEqual(translate(project, self.config()), 2)
        self.assertEqual(request.call_count, 1)
        wait.assert_not_called()
        self.assertEqual(len(project.google_web_cache), 1)
        self.assertTrue(all(entry.translation == 'Bắt đầu' for entry in project.entries))

    def test_distinct_requests_only_wait_once_between_them(self):
        project = Project('.', entries=extract('["Start game", "Quit game"]', 'json', 'en.json'))
        with patch.object(Client, '_request', side_effect=[[[["Bắt đầu"]]], [[["Thoát"]]]]), \
                patch.object(threading.Event, 'wait', return_value=False) as wait:
            self.assertEqual(translate(project, self.config()), 2)
        wait.assert_called_once_with(2)

    def test_saved_cache_survives_restart_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'project.json'
            project = self.project()
            project.root = directory
            with patch.object(Client, '_request', return_value=[[["Bắt đầu"]]]):
                translate(project, self.config(), save=lambda: project.save(file))
            loaded = Project.load(file)
            for entry in loaded.entries:
                entry.translation = ''
            with patch.object(Client, '_request') as request:
                self.assertEqual(translate(loaded, self.config()), 2)
            request.assert_not_called()
            old_data = json.loads(file.read_text(encoding='utf-8'))
            old_data.pop('google_web_cache')
            file.write_text(json.dumps(old_data), encoding='utf-8')
            self.assertEqual(Project.load(file).google_web_cache, {})

    def test_retranslate_bypasses_and_refreshes_cache(self):
        project = self.project()
        with patch.object(Client, '_request', return_value=[[["Bắt đầu"]]]):
            translate(project, self.config())
        with patch.object(Client, '_request', return_value=[[["Khởi động"]]]) as request, \
                patch.object(threading.Event, 'wait', return_value=False):
            translate(project, self.config(), overwrite=True)
        self.assertEqual(request.call_count, 2)
        self.assertTrue(all(entry.translation == 'Khởi động' for entry in project.entries))
        self.assertEqual(list(project.google_web_cache.values()), ['Khởi động'])

    def test_invalid_cache_value_is_not_reused(self):
        client = Client(self.config())
        key = 'en-vi:v1:' + digest(b'Start game')
        for bad in ('', 'Wrong {variable}', None, 12):
            client.google_cache[key] = bad
            with patch.object(Client, '_request', return_value=[[["Bắt đầu"]]]) as request, \
                    patch.object(threading.Event, 'wait', return_value=False):
                self.assertEqual(client.google_web_text('Start game', threading.Event()), 'Bắt đầu')
            request.assert_called_once()

    def test_chunks_keep_boundaries_and_never_send_protected_tokens(self):
        source = '<b>' + ('A long sentence. ' * 400) + '</b>\nHello {player}!'
        masked, prefix, tokens = mask(source)
        client = Client(self.config())
        sent = []
        def request(url, payload, stop):
            value = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['q'][0]
            sent.append(value)
            return [[[value]]]
        with patch.object(Client, '_request', side_effect=request), patch.object(threading.Event, 'wait', return_value=False):
            result = unmask(client.google_web_text(masked, threading.Event()), prefix, tokens)
        self.assertEqual(result, source)
        self.assertTrue(all(len(value) <= 4000 and '__VH' not in value for value in sent))
        text = 'One sentence. ' * 600
        chunks = google_chunks(text)
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(chunk.strip()) <= 4000 for chunk in chunks))

    def test_rescan_cache_stays_in_same_game_only(self):
        old = Project('.', google_web_cache={'entry': 'Bản dịch'})
        new = Project('.')
        carry_translations(old, new)
        self.assertEqual(new.google_web_cache, old.google_web_cache)
        new.google_web_cache.clear()
        self.assertTrue(old.google_web_cache)
        other = Project('other-game')
        carry_translations(old, other)
        self.assertEqual(other.google_web_cache, {})

    def test_cancel_cached_result_never_updates_entry(self):
        project = self.project()
        stop = threading.Event()
        stop.set()
        with patch.object(Client, '_request') as request:
            self.assertEqual(translate(project, self.config(), stop=stop), 0)
        request.assert_not_called()
        self.assertFalse(any(entry.translation for entry in project.entries))

    def test_invalid_cache_container_rejected_when_loading_project(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'project.json'
            project = Project(directory)
            project.save(file)
            data = json.loads(file.read_text(encoding='utf-8'))
            data['google_web_cache'] = []
            file.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Cache Google'):
                Project.load(file)

    def test_web_rate_limit_hint_does_not_require_key_or_billing(self):
        from toolvh.translation import api_error_hint
        for code in (403, 429):
            error = urllib.error.HTTPError(GOOGLE_WEB_URL, code, 'blocked', {}, None)
            hint, retry = api_error_hint(error, 'google-web')
            self.assertIn('Không liên quan API key', hint)
            self.assertIn('Ollama local', hint)
            self.assertEqual(retry, code == 429)
