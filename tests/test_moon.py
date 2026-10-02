"""Original synthetic Moon-schema data, never game assets."""
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from toolvh.formats import extract
from toolvh.moon import LOCALES, PROPERTIES_HASH, extract_provider, parse_provider, rebuild_provider, script_matches
from toolvh.scanner import scan
from toolvh.unity import script_reference


def string(value):
    raw = value.encode('utf-8')
    return struct.pack('<i', len(raw)) + raw + b'\0' * (-len(raw) % 4)


def provider(messages=('Start game', 'Go back')):
    header = b'\0' * 12 + struct.pack('<iiq', 1, 1, 100)
    data = header + string('SyntheticMessageProvider') + struct.pack('<i', len(messages))
    for i, text in enumerate(messages):
        data += string(text)
        for locale in LOCALES[1:]:
            data += string('Other-language-' + locale)
        data += struct.pack('<4i', i, 2, 3, 4) + struct.pack('<i', 16) + bytes([i + 1]) * 16 + struct.pack('<i', 1)
    return data


class MoonTests(unittest.TestCase):
    def test_only_english_fields_are_selected(self):
        entries = extract_provider(provider(), 'Game_Data/resources.assets', '__root__', 10)
        self.assertEqual([e.source for e in entries], ['Start game', 'Go back'])
        self.assertTrue(all(e.enabled and e.source_locale == 'en' for e in entries))
        self.assertIn('message 2', entries[1].context)

    def test_rebuild_preserves_all_non_english_bytes_metadata_and_header(self):
        data = provider()
        entries = extract_provider(data, 'a', '__root__', 10)
        entries[0].translation = 'Bắt đầu chơi 🎮'
        result = rebuild_provider(data, entries[:1])
        old, new = parse_provider(data), parse_provider(result)
        self.assertEqual(new['rows'][0][0]['value'], 'Bắt đầu chơi 🎮')
        self.assertEqual(new['rows'][1][0]['value'], 'Go back')
        old_field, new_field = old['rows'][0][0], new['rows'][0][0]
        self.assertEqual(data[:old_field['start']], result[:new_field['start']])
        self.assertEqual(data[old_field['end']:], result[new_field['end']:])
        self.assertEqual(rebuild_provider(data, []), data)

    def test_malformed_schema_and_unsafe_locator_are_blocked(self):
        data = provider()
        parsed = parse_provider(data)
        bad_guid = bytearray(data)
        meta = parsed['rows'][0][-1]['end']
        struct.pack_into('<i', bad_guid, meta + 16, 15)
        for bad in (data[:12], data[:-1], data + b'\0\0\0\0', bytes(bad_guid)):
            with self.assertRaises(ValueError):
                parse_provider(bad)
        for field, value in [('schema', 'unknown'), ('script_id', 999), ('row', -1), ('name', 'Different')]:
            entries = extract_provider(data, 'a', '__root__', 10)
            entries[0].translation = 'Bắt đầu'
            entries[0].locator[field] = value
            with self.assertRaises(ValueError):
                rebuild_provider(data, entries[:1])
        entries = extract_provider(data, 'a', '__root__', 10)
        entries[0].translation = 'Bắt đầu'
        with self.assertRaises(ValueError):
            rebuild_provider(data, entries[:1] * 2)

    def test_fingerprint_and_assembly_required(self):
        tree = {'m_Namespace': '', 'm_ClassName': 'TranslatedMessageProvider', 'm_AssemblyName': '__mainWisp.dll',
                'm_PropertiesHash': {f'bytes[{i}]': v for i, v in enumerate(PROPERTIES_HASH)}}
        self.assertTrue(script_matches(tree))
        self.assertFalse(script_matches(dict(tree, m_AssemblyName='Other.dll')))
        self.assertFalse(script_matches(dict(tree, m_PropertiesHash={})))

    def test_external_script_stays_relative_to_asset_directory(self):
        obj = SimpleNamespace(assets_file=SimpleNamespace(name='__root__', externals=[SimpleNamespace(path='globalgamemanagers.assets')]))
        tree = {'m_Script': {'m_FileID': 1, 'm_PathID': 100}}
        self.assertEqual(script_reference(obj, tree, 'Game_Data/resources.assets'), ('Game_Data/globalgamemanagers.assets', 100))

    def test_audio_and_notices_are_metadata_even_if_named_english(self):
        for name in ('Game_Data/StreamingAssets/Audio/GeneratedSoundBanks/Windows/English.txt',
                     'Game_Data/Plugins/ThirdPartyNotices.txt', 'nameDatabase', 'runtimeBuildInformation'):
            self.assertEqual(extract('Start game\nGo back', 'txt', name), [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'GeneratedSoundBanks').mkdir()
            (root / 'GeneratedSoundBanks/en.txt').write_text('Fake audio event')
            (root / 'en.json').write_text('{"text":"Start game"}')
            project = scan(root)
            self.assertEqual([e.source for e in project.entries], ['Start game'])


if __name__ == '__main__':
    unittest.main()
