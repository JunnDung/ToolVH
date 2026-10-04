import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolvh.formats import extract, rebuild
from toolvh.model import Project
from toolvh.scanner import scan
from toolvh.terminology import context_map, inferred_names
from toolvh.translation import APIConfig, Client, translate


class TranslationContextTests(unittest.TestCase):
    def test_json_speaker_is_context_not_translatable_text(self):
        source = json.dumps({"lines": [
            {"speaker": "Ada", "scene_id": "room", "text": "What the fuck?"},
            {"speaker": "Ben", "scene_id": "room", "text": "Calm down."},
            {"speaker": "Ada", "scene_id": "hill", "text": "It is cold."}]})
        entries = extract(source, "json", "en.json")
        self.assertEqual([e.source for e in entries], ["What the fuck?", "Calm down.", "It is cold."])
        contexts = context_map(Project(".", entries=entries))
        first, second, third = [contexts[e.id] for e in entries]
        self.assertEqual(first["speaker"], "Ada")
        self.assertEqual(first["next"], "Calm down.")
        self.assertEqual(second["previous"], "What the fuck?")
        self.assertEqual(third["previous_or_next"], [])
        self.assertIn("Ada", inferred_names(Project(".", entries=entries)))
        entries[0].translation = "Cái đéo gì vậy?"
        result = json.loads(rebuild(source, "json", [entries[0]]))
        self.assertEqual(result["lines"][0]["speaker"], "Ada")
        self.assertEqual(result["lines"][0]["scene_id"], "room")
        self.assertEqual(result["lines"][0]["text"], "Cái đéo gì vậy?")

    def test_json_neighbors_never_cross_language_or_text_field(self):
        source = json.dumps({"lines": [
            {"text": {"en": "First", "fr": "Premier"}, "description": {"en": "Description"}},
            {"text": {"en": "Second", "fr": "Deuxième"}}]})
        entries = extract(source, "json", "content.json")
        contexts = context_map(Project(".", entries=entries))
        first = next(e for e in entries if e.source == "First")
        description = next(e for e in entries if e.source == "Description")
        self.assertEqual(contexts[first.id]["next"], "Second")
        self.assertEqual(contexts[description.id]["previous_or_next"], [])

    def test_embedded_json_retains_speaker_and_asset_isolation(self):
        entries = extract('[{"speaker":"Ada","text":"Hello"},{"speaker":"Ben","text":"Hi"}]', "json", "en.json")
        for e in entries:
            e.file = "resources.assets"
            e.locator = {"type": "TextAsset", "format": "json", "object": 1, "inner": e.locator}
        p = Project(".", entries=entries)
        self.assertIn("Ada", inferred_names(p))
        self.assertEqual(context_map(p)[entries[0].id]["next"], "Hi")
        entries[1].locator["object"] = 2
        self.assertEqual(context_map(p)[entries[0].id]["next"], "")

    def test_xml_inherits_locale_and_rebuilds_only_english(self):
        source = '<root><language id="english"><entry id="a"><![CDATA[Quit]]></entry></language><language id="french"><entry id="a">Quitter</entry></language></root>'
        entries = extract(source, "xml", "dialogue.string_table.xml")
        self.assertEqual([e.source for e in entries], ["Quit"])
        self.assertTrue(entries[0].enabled)
        self.assertEqual(entries[0].source_locale, "en")
        entries[0].translation = "Thoát"
        result = rebuild(source, "xml", entries)
        self.assertIn("Quitter", result)
        self.assertEqual([e.source for e in extract(result, "xml", "dialogue.string_table.xml")], ["Thoát"])

    def test_xml_explicit_locale_overrides_filename_and_parent(self):
        source = '<root xml:lang="en"><entry>Start</entry><group locale="fr"><entry>Jouer</entry><entry xml:lang="en">Quit</entry></group></root>'
        entries = extract(source, "xml", "en.xml")
        self.assertEqual([e.source for e in entries], ["Start", "Quit"])
        self.assertTrue(all(e.enabled for e in entries))

    def test_unknown_xml_is_still_review_only(self):
        entries = extract('<root><entry>Bonjour</entry></root>', "xml", "content.xml")
        self.assertFalse(entries[0].enabled)

    def test_unsupported_resources_reported_without_binary_text_guessing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ("dialogue.xnb", "pak01_dir.vpk", "english.loc2", "scripts.zip", "animation.zip"):
                (root / filename).write_bytes(b"not translatable data")
            project = scan(root)
            self.assertEqual(project.entries, [])
            self.assertEqual({f.path for f in project.files}, {"dialogue.xnb", "pak01_dir.vpk", "english.loc2", "scripts.zip"})
            self.assertTrue(all(f.note and f.count == 0 for f in project.files))

    def test_llm_receives_uncensored_contextual_policy_and_names_stay_intact(self):
        p = Project(".", entries=extract('[{"speaker":"Ada","text":"Fuck off, Ada!"}]', "json", "en.json"))
        def complete(client, messages, stop):
            instruction = messages[0]["content"]
            self.assertIn("địt mẹ/đụ má", instruction)
            self.assertIn("Không thêm chửi tục vào câu trung tính", instruction)
            self.assertIn("không gán mọi từ fuck", instruction)
            item = json.loads(messages[1]["content"])["items"][0]
            self.assertEqual(item["speaker"], "Ada")
            return {"translations": [{"id": item["id"], "text": item["text"].replace("Fuck off,", "Cút mẹ đi,")}]}
        with patch.object(Client, "complete", complete):
            translate(p, APIConfig(provider="ollama", base_url="http://localhost:11434", model="test", delay_seconds=0))
        self.assertEqual(p.entries[0].translation, "Cút mẹ đi, Ada!")

    def test_google_web_reports_instruction_limit(self):
        p = Project(".", entries=extract('["Start"]', "json", "en.json"))
        updates = []
        with patch.object(Client, "complete", return_value={"translations": [{"id": p.entries[0].id, "text": "Bắt đầu"}]}):
            translate(p, APIConfig(provider="google-web", base_url="https://translate.googleapis.com", delay_seconds=0), progress=updates.append)
        self.assertTrue(any("không nhận chỉ dẫn" in text for text in updates))
