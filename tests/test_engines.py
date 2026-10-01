"""Synthetic engine files only: no commercial assets or extracted game text."""
import hashlib
import gettext
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from toolvh.godot import (extract_pack, extract_resource, read_pack, read_mo,
                          rebuild_pack, rebuild_resource)
from toolvh.unreal import MAGIC, extract_locres, read_locres, rebuild_locres
from toolvh.patching import apply_project, restore_project
from toolvh.scanner import scan
from toolvh.diagnostics import compatibility_report


def string(value, unicode=False):
    raw = value.encode('utf-16-le' if unicode else 'utf-8') + (b'\0\0' if unicode else b'\0')
    return struct.pack('<i', -(len(raw) // 2) if unicode else len(raw)) + raw


def locres(version, modern_legacy=False):
    header = MAGIC + bytes([version]) if version or modern_legacy else b''
    if version:
        header += b'\0' * 8
    body = struct.pack('<i', 2) if version >= 2 else b''
    body += struct.pack('<i', 1)
    if version >= 2:
        body += struct.pack('<I', 0xF1234567)
    body += string('Menu') + struct.pack('<i', 2)
    for key, source_hash in [('Start', 0x12345678), ('Resume', 0x98765432)]:
        if version >= 2:
            body += struct.pack('<I', 0x87654321)
        body += string(key, unicode=True) + struct.pack('<I', source_hash)
        body += struct.pack('<i', 0) if version else string('Start game')
    if version:
        header = header[:17] + struct.pack('<q', len(header) + len(body))
        body += struct.pack('<i', 1) + string('Start game')
        if version >= 2:
            body += struct.pack('<i', 2)
    return header + body


def pack(version, members, flags=0, member_flags=0, directory_at_end=False):
    header = b'GDPC' + struct.pack('<4I', version, 3 if version == 1 else 4, 0, 0)
    base = 0
    if version >= 2:
        base = 16  # exercise file-base relative directory offsets
        header += struct.pack('<IQ', flags, base)
    if version == 3:
        header += struct.pack('<Q', 104)
    header += b'\0' * 64
    directory_size = 4 + sum(4 + len(name.encode()) + (-len(name.encode()) % 4) + 32 + (4 if version >= 2 else 0) for name in members)
    if directory_at_end:
        if version != 3:
            raise ValueError('Only v3 has a directory offset')
        header = header[:32] + struct.pack('<Q', len(header) + sum(map(len, members.values()))) + header[40:]
    cursor = len(header) if directory_at_end else len(header) + directory_size
    directory = bytearray(struct.pack('<I', len(members)))
    payload = bytearray()
    for name, value in members.items():
        raw = name.encode()
        raw += b'\0' * (-len(raw) % 4)
        directory.extend(struct.pack('<I', len(raw)) + raw)
        directory.extend(struct.pack('<QQ', cursor - base, len(value)) + hashlib.md5(value).digest())
        if version >= 2:
            directory.extend(struct.pack('<I', member_flags))
        payload.extend(value)
        cursor += len(value)
    return header + payload + directory if directory_at_end else header + directory + payload


def mo(endian='<'):
    original = ['', 'Menu\x04Start game', 'apple\0apples']
    translated = ['Language: en\nContent-Type: text/plain; charset=UTF-8\n', 'Start game', 'apple\0apples']
    data = bytearray(struct.pack(endian + '7I', 0x950412de, 0, 3, 28, 52, 0, 0) + b'\0' * 48)
    for table, values in enumerate((original, translated)):
        for i, value in enumerate(values):
            raw = value.encode()
            struct.pack_into(endian + '2I', data, 28 + table * 24 + i * 8, len(raw), len(data))
            data.extend(raw + b'\0')
    return bytes(data)


class UnrealTests(unittest.TestCase):
    def test_all_versions_preserve_keys_hashes_and_shared_strings(self):
        for version in range(4):
            with self.subTest(version=version):
                raw = locres(version)
                entries, _ = extract_locres(raw, 'Content/Localization/UI/en/UI.locres')
                self.assertEqual(len(entries), 2)
                self.assertTrue(all(e.enabled and e.source_locale == 'en' for e in entries))
                entries[0].translation = 'Bắt đầu chơi 🎮'
                result = rebuild_locres(raw, entries[:1])
                v, _, _, rows = read_locres(result)
                self.assertEqual(v, version)
                self.assertEqual([r['value'] for r in rows], ['Bắt đầu chơi 🎮', 'Start game'])
                self.assertEqual([r['source_hash'] for r in rows], [0x12345678, 0x98765432])
                self.assertEqual([r['key'] for r in rows], ['Start', 'Resume'])
                if version:
                    table_offset = read_locres(raw)[1]
                    # All metadata/hash bytes unchanged except index for translated key.
                    old_rows = read_locres(raw)[3]
                    patched = bytearray(raw[:table_offset])
                    struct.pack_into('<i', patched, old_rows[0]['start'], 1)
                    self.assertEqual(result[:table_offset], patched)

    def test_modern_legacy_and_noop(self):
        raw = locres(0, True)
        self.assertEqual(read_locres(raw)[0], 0)
        self.assertEqual(rebuild_locres(raw, []), raw)

    def test_language_evidence(self):
        self.assertEqual(extract_locres(locres(1), 'Localization/fr/UI.locres')[0], [])
        entries, _ = extract_locres(locres(1), 'Localization/UI.locres')
        self.assertTrue(entries)
        self.assertTrue(all(not e.enabled for e in entries))

    def test_invalid_locres_and_changed_source_are_rejected(self):
        raw = locres(2)
        bad_offset = bytearray(raw)
        struct.pack_into('<q', bad_offset, 17, 0)
        bad_index = bytearray(raw)
        struct.pack_into('<i', bad_index, read_locres(raw)[3][0]['start'], 99)
        for bad in (raw[:-1], bytes(bad_offset), bytes(bad_index), MAGIC + b'\xff', raw + b'x'):
            with self.assertRaises(ValueError):
                read_locres(bad)
        entries, _ = extract_locres(raw, 'en/a.locres')
        entries[0].source = 'Wrong source'
        entries[0].translation = 'Bắt đầu'
        with self.assertRaises(ValueError):
            rebuild_locres(raw, entries[:1])


class GodotTests(unittest.TestCase):
    def test_pack_versions_scan_patch_restore_and_keep_binary_assets(self):
        for version in (1, 2, 3):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'game'
                root.mkdir()
                members = {'res://locale.csv': b'keys,en,fr\nstart,Start game,Jouer\n',
                           'res://texture.bin': b'\0\xffDo not translate binary!\0'}
                raw = pack(version, members)
                (root / 'game.pck').write_bytes(raw)
                quick = scan(root)
                self.assertEqual(quick.entries, [])
                self.assertEqual(compatibility_report(quick)['bundle_files_not_scanned'], 1)
                project = scan(root, deep=True)
                self.assertIn('Godot', project.engines)
                self.assertEqual([e.source for e in project.entries], ['Start game'])
                project.entries[0].translation = 'Bắt đầu chơi'
                apply_project(project, Path(tmp) / 'patch')
                patched = (root / 'game.pck').read_bytes()
                _, old_rows = read_pack(raw)
                _, rows = read_pack(patched)
                untouched = rows[1]
                self.assertEqual(patched[untouched['offset']:untouched['offset'] + untouched['size']], members['res://texture.bin'])
                self.assertEqual(untouched, old_rows[1])
                self.assertEqual(extract_pack(patched, 'game.pck')[0][0].source, 'Bắt đầu chơi')
                restore_project(project)
                self.assertEqual((root / 'game.pck').read_bytes(), raw)

    def test_encrypted_and_remapped_members_do_not_produce_false_translations(self):
        source = {'res://locale.csv': b'keys,en\nstart,Start game\n', 'res://locale.csv.import': b'remap',
                  'res://locale.en.translation': b'RSCC\0\xff'}
        entries, note = extract_pack(pack(2, source), 'game.pck')
        self.assertEqual(entries, [])
        self.assertIn('locale.en.translation', note)
        entries, _ = extract_pack(pack(2, {'res://en.json': b'{"text":"Start game"}'}, member_flags=1), 'game.pck')
        self.assertEqual(entries, [])
        with self.assertRaises(ValueError):
            read_pack(pack(2, {}, flags=1))

    def test_bad_pack_paths_offsets_hash_and_version(self):
        for bad in (pack(2, {'res://../en.json': b'{}'}), pack(2, {})[:-2], b'GDPC' + struct.pack('<I', 4)):
            with self.assertRaises(ValueError):
                read_pack(bad)
        raw = pack(2, {'res://en.json': b'{"text":"Start game"}'})
        corrupted = bytearray(raw)
        row = read_pack(raw)[1][0]
        corrupted[row['offset']] = 0
        entries, note = extract_pack(corrupted, 'game.pck')
        self.assertFalse(entries)
        self.assertIn('MD5', note)
        invalid = bytearray(raw)
        struct.pack_into('<Q', invalid, row['metadata'], 999999999)
        with self.assertRaises(ValueError):
            read_pack(invalid)

    def test_cancel_pack(self):
        with self.assertRaises(InterruptedError):
            extract_pack(pack(1, {'res://en.json': b'{}'}), 'game.pck', lambda: True)

    def test_v3_directory_at_end_and_rebuilt_md5(self):
        raw = pack(3, {'res://en.json': b'{"text":"Start game"}'}, directory_at_end=True)
        entries, _ = extract_pack(raw, 'game.pck')
        entries[0].translation = 'Bắt đầu chơi'
        modified = rebuild_pack(raw, entries)
        row = read_pack(modified)[1][0]
        payload = modified[row['offset']:row['offset'] + row['size']]
        self.assertEqual(row['md5'], hashlib.md5(payload).digest())
        self.assertEqual(json.loads(payload)['text'], 'Bắt đầu chơi')

    def test_loose_import_remap_and_unsupported_containers_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'en.csv').write_bytes(b'keys,en\nstart,Start game\n')
            (root / 'en.csv.import').write_text('remap')
            (root / 'game.utoc').write_bytes(b'IoStore sample')
            (root / 'en.translation').write_bytes(b'RSCC\0')
            project = scan(root, deep=True)
            self.assertEqual(project.entries, [])
            report = compatibility_report(project)
            self.assertGreaterEqual(report['unsupported_files'], 2)
            self.assertTrue(any('cần đọc tài nguyên đích' in f.note for f in project.files))

    def test_invalid_mo_and_changed_resource_source(self):
        raw = bytearray(mo())
        struct.pack_into('<I', raw, 12, 99999999)
        with self.assertRaises(ValueError):
            read_mo(raw)
        source = b'[gd_scene format=3]\ntext = "Start game"\n'
        entries, _ = extract_resource(source, 'tscn', 'en/menu.tscn')
        entries[0].source = 'Different source'
        entries[0].translation = 'Bắt đầu chơi'
        with self.assertRaises(ValueError):
            rebuild_resource(source, 'tscn', entries)

    def test_scene_changes_only_visible_properties_and_unknown_locale_needs_review(self):
        raw = b'[gd_scene format=3]\n[node name="Start game" type="Label"]\ntext = "Start game"\ntexture = "res://Start.png"\n'
        entries, _ = extract_resource(raw, 'tscn', 'menu.tscn')
        self.assertEqual([e.source for e in entries], ['Start game'])
        self.assertFalse(entries[0].enabled)
        entries[0].translation = 'Bắt đầu chơi'
        result = rebuild_resource(raw, 'tscn', entries)
        self.assertIn(b'name="Start game"', result)
        self.assertIn('text = "Bắt đầu chơi"'.encode(), result)

    def test_translation_resource_uses_locale_keeps_keys_and_non_english(self):
        raw = b'[gd_resource type="Translation" format=3]\n[resource]\nlocale = "en"\nmessages = {\n"MENU_START": "Start game",\n"MENU_BACK": "Go back"\n}\n'
        entries, _ = extract_resource(raw, 'tres', 'ui.tres')
        self.assertTrue(all(e.enabled for e in entries))
        entries[0].translation = 'Bắt đầu chơi'
        result = rebuild_resource(raw, 'tres', entries[:1])
        self.assertIn(b'"MENU_START":', result)
        self.assertIn(b'"MENU_BACK": "Go back"', result)
        self.assertEqual(extract_resource(raw.replace(b'"en"', b'"fr"'), 'tres', 'ui.tres')[0], [])

    def test_godot4_stringname_dictionary_preserves_type_and_inline_layout(self):
        raw = b'[gd_resource type="Translation" format=3]\nlocale = "en"\nmessages = {&"MENU_START": &"Start game", &"MENU_BACK": &"Go back"}\n'
        entries, _ = extract_resource(raw, 'translation', 'ui.translation')
        self.assertEqual([e.source for e in entries], ['Start game', 'Go back'])
        entries[0].translation = 'Bắt đầu chơi'
        result = rebuild_resource(raw, 'translation', entries[:1])
        self.assertIn('&"MENU_START": &"Bắt đầu chơi"'.encode(), result)
        self.assertIn(b'&"MENU_BACK": &"Go back"', result)

    def test_po_header_context_continuation_fuzzy_plural_and_obsolete(self):
        text = ('msgid ""\nmsgstr ""\n"Language: en\\n"\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
                '# context comment\nmsgctxt "Menu"\nmsgid "Start "\n"game"\nmsgstr ""\n\n'
                '#, fuzzy\nmsgid "Do not change"\nmsgstr ""\n\n'
                'msgid "apple"\nmsgid_plural "apples"\nmsgstr[0] "apple"\nmsgstr[1] "apples"\n\n'
                '#~ msgid "Removed"\n#~ msgstr "Removed"\n')
        entries, _ = extract_resource(text.encode(), 'po', 'messages.po')
        self.assertEqual([e.source for e in entries], ['Start game'])
        self.assertTrue(entries[0].enabled)
        entries[0].translation = 'Bắt đầu chơi'
        result = rebuild_resource(text.encode(), 'po', entries).decode()
        self.assertIn('msgstr "Bắt đầu chơi"', result)
        self.assertIn('msgid "Start "\n"game"', result)
        self.assertEqual(result.split('#, fuzzy')[1], text.split('#, fuzzy')[1])
        self.assertIn('Language: en', result)

    def test_mo_endian_unicode_and_plural_preserved(self):
        for endian in ('<', '>'):
            raw = mo(endian)
            entries, _ = extract_resource(raw, 'mo', 'messages.mo')
            self.assertEqual([e.source for e in entries], ['Start game'])
            entries[0].translation = 'Bắt đầu chơi 🎮'
            result = rebuild_resource(raw, 'mo', entries)
            new_endian, originals, translated = read_mo(result)
            self.assertEqual(new_endian, endian)
            self.assertEqual(originals, read_mo(raw)[1])
            self.assertEqual(translated[2], 'apple\0apples')
            self.assertEqual(translated[1], 'Bắt đầu chơi 🎮')
            # Validate output with the independent standard-library MO reader.
            runtime = gettext.GNUTranslations(io.BytesIO(result))
            self.assertEqual(runtime.pgettext('Menu', 'Start game'), 'Bắt đầu chơi 🎮')
            self.assertEqual(runtime.ngettext('apple', 'apples', 2), 'apples')

    def test_loose_locres_and_po_apply_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'game'
            (root / 'Localization' / 'en').mkdir(parents=True)
            original = locres(3)
            target = root / 'Localization/en/UI.locres'
            target.write_bytes(original)
            po = b'msgid ""\nmsgstr "Language: en\\n"\n\nmsgid "Go back"\nmsgstr ""\n'
            (root / 'en.po').write_bytes(po)
            (root / 'project.godot').write_text('config/name="Never translate config"')
            project = scan(root)
            self.assertIn('Godot', project.engines)
            self.assertIn('Unreal Engine', project.engines)
            self.assertEqual(len(project.entries), 3)
            for entry in project.entries:
                entry.translation = 'Bắt đầu chơi' if entry.source == 'Start game' else 'Quay lại'
            apply_project(project, Path(tmp) / 'patch')
            self.assertEqual(read_locres(target.read_bytes())[3][0]['value'], 'Bắt đầu chơi')
            self.assertIn('Quay lại'.encode(), (root / 'en.po').read_bytes())
            restore_project(project)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual((root / 'en.po').read_bytes(), po)


if __name__ == '__main__':
    unittest.main()
