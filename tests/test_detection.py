import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolvh.formats import extract
from toolvh.model import Project
from toolvh.patching import export_patch
from toolvh.scanner import scan, carry_translations
from toolvh.translation import APIConfig, Client, translate
from toolvh.unity import extract_string_table, resolve_table_entries

STRING_TABLE = ("UnityEngine.Localization.Tables", "StringTable")


def table(locale="en"):
    return {"m_Name": "UI_en", "m_LocaleId": {"m_Code": locale}, "m_SharedData": {},
            "m_TableData": [{"m_Id": 123, "m_Localized": "PLAY"},
                            {"m_Id": 456, "m_Localized": "{0} of {1} lobbies shown"},
                            {"m_Id": 789, "m_Localized": "-"},
                            {"m_Id": 999, "m_Localized": ""}]}


class DetectionTest(unittest.TestCase):
    def test_known_runtime_files_never_become_translation_candidates(self):
        data = json.dumps({"text": "Facepunch Transport for Netcode for GameObjects"})
        for file in ["Game_Data/RuntimeInitializeOnLoads.json", "ScriptingAssemblies.json",
                     "StreamingAssets/UnityServicesProjectConfiguration.json", "aa/settings.json"]:
            self.assertEqual(extract(data, "json", file), [])

    def test_assembly_metadata_rejected_even_with_english_filename(self):
        data = {"assemblyName": "Facepunch Transport for Netcode for GameObjects",
                "names": ["Facepunch Transport for Netcode for GameObjects.dll"],
                "text": "Unity.Addressables, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null",
                "m_ResourceType": {"m_AssemblyName": "Unity Localization"}}
        self.assertEqual(extract(json.dumps(data), "json", "en.json"), [])

    def test_english_json_map_and_records_leave_other_languages_untouched(self):
        data = {"menu": {"en-US": "Start", "fr": "Jouer", "ja": "開始"},
                "records": [{"locale": "de", "text": "Spielen"}, {"locale": "en", "text": "Quit"}]}
        entries = extract(json.dumps(data), "json", "language.json")
        self.assertEqual([e.source for e in entries], ["Start", "Quit"])
        self.assertTrue(all(e.enabled for e in entries))

    def test_unknown_language_is_review_only_instead_of_80_percent_guess(self):
        entries = extract('["Start game", "Bonjour tout le monde"]', "json", "content.json")
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(not e.enabled and not e.source_locale for e in entries))

    def test_single_word_english_file_selected(self):
        entries = extract('["PLAY", "Quit"]', "json", "Locales/en-GB.json")
        self.assertTrue(all(e.enabled and e.source_locale == "en-gb" for e in entries))

    def test_non_english_file_and_columns_not_selected(self):
        self.assertEqual(extract('{"text":"Jouer"}', "json", "fr.json"), [])
        self.assertEqual(extract('id,French,German\nmenu,Jouer,Spielen\n', "csv", "localization.csv"), [])

    def test_string_table_uses_locale_and_exact_value_locator(self):
        entries = extract_string_table(table(), "bundle", "cab", 1, STRING_TABLE)
        self.assertEqual([e.source for e in entries], ["PLAY", "{0} of {1} lobbies shown"])
        self.assertTrue(all(e.enabled for e in entries))
        self.assertEqual(entries[0].locator["path"], ["m_TableData", 0, "m_Localized"])
        self.assertIn("ID 123", entries[0].context)

    def test_actual_locale_wins_over_misleading_english_table_name(self):
        self.assertEqual(extract_string_table(table("fr"), "english.bundle", "cab", 1, STRING_TABLE), [])
        self.assertTrue(extract_string_table(table("en_US"), "french.bundle", "cab", 1, STRING_TABLE)[0].enabled)

    def test_asset_table_same_serialized_schema_is_not_text(self):
        t = table()
        t["m_TableData"][0]["m_Localized"] = "7f87ae3d0b693264188361e975644663"
        self.assertEqual(extract_string_table(t, "english.bundle", "cab", 1,
                                            ("UnityEngine.Localization.Tables", "AssetTable")), [])
        unknown = extract_string_table(t, "bundle", "cab", 1)
        self.assertEqual(len(unknown), 1)
        self.assertFalse(unknown[0].enabled)

    def test_script_dependency_can_arrive_after_localization_bundle(self):
        entries = extract_string_table(table(), "bundle", "cab", 1)
        for entry in entries:
            entry._table_script = ("other-cab", 22)
        self.assertTrue(all(not e.enabled for e in entries))
        resolved = resolve_table_entries(entries, {("other-cab", 22): STRING_TABLE})
        self.assertTrue(all(e.enabled for e in resolved))

    def test_wrong_script_class_discards_schema_lookalike(self):
        entries = extract_string_table(table(), "bundle", "cab", 1)
        for entry in entries:
            entry._table_script = ("cab", 22)
        self.assertEqual(resolve_table_entries(entries, {("cab", 22): ("Custom", "AssetTable")}), [])

    def test_rescan_preserves_translations_but_replaces_bad_selection(self):
        old = Project(".", entries=extract('["Start game"]', "json", "unknown.json"))
        old.entries[0].enabled = True
        old.entries[0].translation = "Bắt đầu chơi"
        current = Project(".", entries=extract('["Start game"]', "json", "unknown.json"))
        self.assertEqual(carry_translations(old, current), 1)
        self.assertFalse(current.entries[0].enabled)
        self.assertEqual(current.entries[0].translation, "Bắt đầu chơi")
        changed = copy.deepcopy(current)
        changed.entries[0].source = "Other source"
        self.assertEqual(carry_translations(old, changed), 0)

    def test_old_projects_cannot_send_bad_selection_or_export_patch(self):
        old = Project(".", scan_revision=0)
        with patch.object(Client, "complete") as api:
            with self.assertRaisesRegex(ValueError, "bộ quét cũ"):
                translate(old, APIConfig(model="test"))
            api.assert_not_called()
        with self.assertRaisesRegex(ValueError, "bộ quét cũ"):
            export_patch(old, "unused")

    def test_scanner_reports_runtime_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / "RuntimeInitializeOnLoads.json").write_text('{"text":"Bad runtime text"}')
            (p / "en.json").write_text('{"text":"Start"}')
            project = scan(p)
            self.assertEqual([e.source for e in project.entries], ["Start"])
            self.assertTrue(project.entries[0].enabled)
            self.assertTrue(any(f.kind == "metadata" for f in project.files))


if __name__ == "__main__":
    unittest.main()
