import csv
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from toolvh.formats import decode_text, encode_text, extract, rebuild
from toolvh.model import Project, safe_child
from toolvh.patching import export_csv, export_patch, import_csv, install_patch, apply_project, restore_project
from toolvh.scanner import scan
from toolvh.translation import APIConfig, Client, mask, translate, unmask, validate


class FormatsTest(unittest.TestCase):
    def test_localization_references_are_not_translatable(self):
        entries = extract('{"text":"Text.TutorialOutro.03","description":"Hello chef!","m_DisplayName":"DialogPlayableAsset"}', "json", "dialogue.json")
        self.assertEqual([e.source for e in entries], ["Hello chef!"])

    def test_slash_separated_control_labels_are_text(self):
        entries = extract('id\tEnglish\ncontrol\tChop/Throw\n', "tsv-raw", "a", "Localization - Shared")
        self.assertEqual(entries[0].source, "Chop/Throw")
        self.assertTrue(entries[0].enabled)

    def test_json_keeps_ids_and_roundtrips_nested_values(self):
        source = '{"id":"quest_12","nested":{"text":"Hello {player}!"},"items":["Start game"],"count":2}'
        entries = extract(source, "json", "dialogue.json")
        self.assertEqual(len(entries), 2)
        entries[0].translation = "Xin chào {player}!"
        result = json.loads(rebuild(source, "json", [entries[0]]))
        self.assertEqual(result["id"], "quest_12")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["nested"]["text"], "Xin chào {player}!")
        self.assertEqual(result["items"], ["Start game"])

    def test_json_duplicate_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            extract('{"text":"One","text":"Two"}', "json", "x.json")

    def test_csv_only_english_and_quoted_newline(self):
        source = 'id,English,French\r\nmenu,"Hello, player\nWelcome",Bonjour\r\n'
        entries = extract(source, "csv", "localization.csv")
        self.assertEqual(len(entries), 1)
        entries[0].translation = "Xin chào, người chơi\nChào mừng"
        rows = list(csv.reader(io.StringIO(rebuild(source, "csv", entries))))
        self.assertEqual(rows[1], ["menu", entries[0].translation, "Bonjour"])

    def test_raw_tsv_preserves_all_other_bytes(self):
        source = '\tEnglish\tFrench\r\nSTART\t"Start now"\tDémarrer\t\r\nEND\r\n'
        entries = extract(source, "tsv-raw", "a", "Localization - Shared")
        entries[0].translation = '"Bắt đầu ngay"'
        self.assertEqual(rebuild(source, "tsv-raw", entries), source.replace('"Start now"', '"Bắt đầu ngay"'))

    def test_utf16_both_endian_preserved(self):
        for encoding in ["utf-16-le-bom", "utf-16-be-bom", "utf-8-sig", "utf-8"]:
            text = "Tiếng Việt\r\nXin chào"
            data = encode_text(text, encoding)
            self.assertEqual(decode_text(data), (text, encoding))

    def test_ini_comments_and_crlf(self):
        source = "; note\r\n[UI]\r\nstart = Start game\r\n"
        entry = extract(source, "ini", "game.ini")[0]
        entry.translation = "Bắt đầu chơi"
        self.assertEqual(rebuild(source, "ini", [entry]), source.replace("Start game", "Bắt đầu chơi"))

    def test_xml_keeps_attributes_and_escapes(self):
        source = '<strings><text id="start">Start game</text><!--keep--></strings>'
        entry = extract(source, "xml", "ui.xml")[0]
        entry.translation = "Bắt đầu & chơi"
        result = rebuild(source, "xml", [entry])
        self.assertIn('id="start"', result)
        self.assertIn("Bắt đầu &amp; chơi", result)
        self.assertIn("<!--keep-->", result)

    def test_srt_timestamps_untouched(self):
        source = "1\n00:00:01,000 --> 00:00:02,000\nHello there!\n\n"
        entries = extract(source, "srt", "scene.srt")
        self.assertEqual(len(entries), 1)
        entries[0].translation = "Xin chào!"
        self.assertEqual(rebuild(source, "srt", entries), source.replace("Hello there!", "Xin chào!"))

    def test_stale_locator_rejected(self):
        e = extract('"Hello there"', "json", "a.json")[0]
        e.translation = "Xin chào"
        with self.assertRaises(ValueError):
            rebuild('"Different text"', "json", [e])


class TranslationTest(unittest.TestCase):
    def test_tokens_protected(self):
        source = '<color=red>Hello {player}, %02d [name] \\V[3]\\n</color>\r\n'
        masked, prefix, values = mask(source)
        result = unmask(masked.replace("Hello", "Xin chào"), prefix, values)
        self.assertFalse(validate(source, result))
        self.assertTrue(validate(source, result.replace("{player}", "{người chơi}")))
        with self.assertRaises(ValueError):
            unmask(masked + prefix + "0__", prefix, values)

    def test_tag_reordering_rejected(self):
        self.assertTrue(validate("<b><i>Hi</i></b>", "<i><b>Chào</b></i>"))

    def test_api_batches_resume_and_checkpoint(self):
        project = Project(".", entries=extract('["Hello {player}","Start game","Quit game"]', "json", "en.json"))
        project.entries[0].translation = "Xin chào {player}"
        saves, calls = [], []
        def complete(client, messages, stop):
            items = json.loads(messages[1]["content"])["items"]
            calls.append(items)
            return {"translations": [{"id": i["id"], "text": "Dịch " + i["text"]} for i in items]}
        with patch.object(Client, "complete", complete):
            count = translate(project, APIConfig(model="test", batch_size=1), save=lambda: saves.append(1))
        self.assertEqual(count, 2)
        self.assertEqual(len(saves), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(project.entries[0].translation, "Xin chào {player}")

    def test_invalid_batch_ids_not_committed(self):
        project = Project(".", entries=extract('["Start game"]', "json", "en.json"))
        with patch.object(Client, "complete", return_value={"translations": [{"id": "bad", "text": "Bắt đầu"}]}):
            with self.assertRaises(ValueError):
                translate(project, APIConfig(model="test"))
        self.assertFalse(project.entries[0].translation)

    def test_bad_placeholder_recorded_without_translation(self):
        project = Project(".", entries=extract('["Hello {name}"]', "json", "en.json"))
        with patch.object(Client, "complete", return_value={"translations": [{"id": project.entries[0].id, "text": "Xin chào"}]}):
            translate(project, APIConfig(model="test"))
        self.assertTrue(project.entries[0].error)
        self.assertFalse(project.entries[0].translation)

    def test_http_remote_key_not_allowed(self):
        with self.assertRaises(ValueError):
            Client(APIConfig(base_url="http://example.com/v1", model="test", api_key="secret"))

    def test_cancelled_before_network(self):
        project = Project(".", entries=extract('["Start game"]', "json", "en.json"))
        stop = threading.Event()
        stop.set()
        with patch.object(Client, "complete") as mock:
            self.assertEqual(translate(project, APIConfig(model="test"), stop=stop), 0)
        mock.assert_not_called()

    def test_wire_contract_both_providers(self):
        for provider in ["ollama", "openai-compatible"]:
            client = Client(APIConfig(provider, "http://localhost:11434", "test-model"))
            body = json.dumps({'translations':[{'id':'0' if provider == 'ollama' else 'original-id','text':'Bắt đầu chơi'}]})
            payload = {"message": {"content": body}} if provider == "ollama" else {"choices": [{"message": {"content": body}, "finish_reason": "stop"}]}
            response = io.BytesIO(json.dumps(payload).encode())
            with patch.object(client.opener, "open", return_value=response) as request:
                messages = [{'role':'user','content':json.dumps({'items':[{'id':'original-id','text':'Start game','context':'Menu'}]})}]
                self.assertEqual(client.complete(messages, threading.Event()), {'translations':[{'id':'original-id','text':'Bắt đầu chơi'}]})
                req = request.call_args.args[0]
                sent = json.loads(req.data)
                self.assertEqual(sent["model"], "test-model")
                self.assertFalse(sent["stream"])
                self.assertTrue(req.full_url.endswith("/api/chat" if provider == "ollama" else "/chat/completions"))


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.game = self.base / "game"
        self.game.mkdir()
        self.source = self.game / "localization.en.json"
        self.source.write_text('{"id":"menu","text":"Start game"}', encoding="utf-8")
        self.original = self.source.read_bytes()
        self.project = scan(self.game)
        self.project.entries[0].translation = "Bắt đầu chơi"

    def tearDown(self):
        self.temp.cleanup()

    def test_export_apply_restore_preserves_original(self):
        destination = self.base / "patch"
        manifest = export_patch(self.project, destination)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(manifest["translated"], 1)
        install_patch(destination, self.game)
        self.assertEqual(json.loads(self.source.read_text(encoding="utf-8"))["text"], "Bắt đầu chơi")
        install_patch(destination, self.game, restore=True)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_stale_source_cannot_export(self):
        self.source.write_text("changed")
        with self.assertRaises(ValueError):
            export_patch(self.project, self.base / "patch")
        self.assertFalse((self.base / "patch").exists())

    def test_direct_apply_persists_recovery_before_writing_and_restores(self):
        snapshots = []
        def save():
            snapshots.append((self.project.applied_patch, self.source.read_bytes()))
        result = apply_project(self.project, self.base / "direct", save=save)
        self.assertEqual(result["files"], 1)
        self.assertEqual(snapshots[0][1], self.original)
        self.assertTrue(Path(snapshots[0][0]).is_dir())
        with self.assertRaises(ValueError):
            apply_project(self.project, self.base / "second")
        self.assertEqual(restore_project(self.project, save=save), 1)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.project.applied_patch, "")

    def test_checkpoint_failure_never_writes_game(self):
        with self.assertRaises(OSError):
            apply_project(self.project, self.base / "direct", save=lambda: (_ for _ in ()).throw(OSError("disk full")))
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(restore_project(self.project), 0)

    def test_install_and_restore_can_be_retried(self):
        destination = self.base / "retry"
        export_patch(self.project, destination)
        self.assertEqual(install_patch(destination, self.game), 1)
        self.assertEqual(install_patch(destination, self.game), 0)
        self.assertEqual(install_patch(destination, self.game, restore=True), 1)
        self.assertEqual(install_patch(destination, self.game, restore=True), 0)

    def test_export_into_game_rejected(self):
        with self.assertRaises(ValueError):
            export_patch(self.project, self.game / "patch")

    def test_modified_backup_blocks_install(self):
        destination = self.base / "patch"
        export_patch(self.project, destination)
        (destination / "backup" / "localization.en.json").write_text("broken")
        with self.assertRaises(ValueError):
            install_patch(destination, self.game)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_paths_cannot_escape_root(self):
        for relative in ["../escape", "C:/escape", "a:stream", "/escape"]:
            with self.assertRaises(ValueError):
                safe_child(self.game, relative)

    def test_csv_import_is_atomic_and_source_checked(self):
        path = self.base / "translations.csv"
        export_csv(self.project, path)
        project = scan(self.game)
        self.assertEqual(import_csv(project, path), 1)
        self.assertEqual(project.entries[0].translation, "Bắt đầu chơi")
        path.write_text(path.read_text(encoding="utf-8-sig").replace("Start game", "Wrong source"), encoding="utf-8-sig")
        with self.assertRaises(ValueError):
            import_csv(project, path)

    def test_project_roundtrip_and_no_api_key(self):
        path = self.base / "game.toolvh.json"
        self.project.save(path)
        loaded = Project.load(path)
        self.assertEqual(loaded.entries, self.project.entries)
        self.assertNotIn("api_key", path.read_text(encoding="utf-8"))

    def test_skipped_large_file_has_report(self):
        (self.game / "big.json").write_bytes(b" " * 1024 * 1024 + b"{}")
        project = scan(self.game, max_mb=1)
        self.assertTrue(any(f.path == "big.json" and f.kind == "skipped" for f in project.files))


if __name__ == "__main__":
    unittest.main()
