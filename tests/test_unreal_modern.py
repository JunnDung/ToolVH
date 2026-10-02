import hashlib
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from toolvh import pak, pak_modern
from toolvh.scanner import scan
from toolvh.patching import preflight, export_patch, install_patch
from toolvh.formats import context_locale
from toolvh.unreal import fstring, read_locres
from test_engines import locres


def fixture(version=12, method='', engine=False):
    output, encoded, locations = bytearray(), bytearray(), []
    names = ['Game/Content/Localization/UI/en-001/UI.locres', 'Game/Content/image.bin']
    if engine:
        names[0] = 'Engine/Content/Localization/UI/en/UI.locres'
    for name, raw in zip(names, [locres(3), b'unchanged binary']):
        offset = len(output)
        compressed = bool(method and name.endswith('.locres'))
        blocks = [zlib.compress(raw[:len(raw)//2]), zlib.compress(raw[len(raw)//2:])] if compressed else []
        if method == 'OodleLiteral' and compressed:
            blocks = [b'\x4c\x06' + raw]
        if method == 'Gzip':
            blocks = []
            for part in [raw[:len(raw)//2], raw[len(raw)//2:]]:
                encoder = zlib.compressobj(wbits=31)
                blocks.append(encoder.compress(part) + encoder.flush())
        stored = b''.join(blocks) if compressed else raw
        header = struct.pack('<qqqI', 0, len(stored), len(raw), int(compressed)) + hashlib.sha1(stored).digest()
        if compressed:
            start = 57 + 16 * len(blocks)
            header += struct.pack('<i', len(blocks))
            for block in blocks:
                header += struct.pack('<qq', start, start + len(block))
                start += len(block)
        header += struct.pack('<BI', 0, 65536 if compressed else 0)
        output.extend(header + stored)
        locations.append(len(encoded))
        flags = 0xe0000000 | ((1 << 23) | (len(blocks) << 6) | 32 if compressed else 0)
        encoded.extend(struct.pack('<III', flags, offset, len(raw)))
        if compressed:
            encoded.extend(struct.pack('<I', len(stored)))
            if len(blocks) > 1:
                encoded.extend(b''.join(struct.pack('<I', len(block)) for block in blocks))
    directories = struct.pack('<i', 2)
    for name, location in zip(names, locations):
        parent, leaf = name.rsplit('/', 1)
        leaf_bytes = leaf.encode()
        filename = struct.pack('<i', len(leaf_bytes)) + leaf_bytes if version == 12 else fstring(leaf)
        directories += fstring(parent + '/') + struct.pack('<i', 1) + filename + struct.pack('<i', location)
    hashes = struct.pack('<i', 2) + b''.join(struct.pack('<Qi', i, l) for i, l in enumerate(locations)) + directories
    index = fstring('../../../') + struct.pack('<iQ', 2, 123)
    for secondary in [hashes, directories]:
        index += struct.pack('<iqq', 1, len(output), len(secondary)) + hashlib.sha1(secondary).digest()
        output.extend(secondary)
    index += struct.pack('<i', len(encoded)) + encoded + struct.pack('<i', 0)
    footer = bytes(17) + struct.pack('<Iiqq', pak.MAGIC, version, len(output), len(index)) + hashlib.sha1(index).digest()
    footer += ('Oodle' if method == 'OodleLiteral' else method).encode().ljust(32, b'\0') + bytes(128)
    return bytes(output + index + footer)


class ModernUnrealTests(unittest.TestCase):
    def test_modern_roundtrip_compressed_and_utf8_directory(self):
        for version in (10, 11, 12):
            for method in ('', 'Zlib', 'Gzip', 'OodleLiteral'):
                with self.subTest(version=version, method=method):
                    raw = fixture(version, method)
                    entries, note = pak.extract(raw, 'game.pak')
                    self.assertTrue(entries[0].enabled)
                    entries[0].translation = 'Bắt đầu chơi — tiếng Việt dài hơn nguồn'
                    result = pak.rebuild(raw, entries[:1])
                    a = pak_modern.read(result)
                    self.assertEqual(read_locres(pak_modern.payload(result, a['rows'][0], a))[3][0]['value'], entries[0].translation)
                    self.assertEqual(pak_modern.payload(result, a['rows'][1], a), b'unchanged binary')
                    self.assertTrue(result.startswith(raw[:-221]))
                    hash_data = a['references'][0][1]
                    self.assertEqual(struct.unpack_from('<i', hash_data, 12)[0], a['rows'][0]['location'])
                    self.assertEqual(pak.rebuild(raw, []), raw)

    def test_corrupt_indexes_payload_encryption_oodle_and_engine_filtered(self):
        raw = fixture(method='Oodle')
        entries, note = pak.extract(raw, 'game.pak')
        self.assertEqual(entries, [])
        self.assertIn('Oodle', note)
        self.assertEqual(pak.extract(fixture(engine=True), 'game.pak')[0], [])
        for index in (-170, 55):
            damaged = bytearray(fixture())
            damaged[index] ^= 1
            if index < 0:
                with self.assertRaisesRegex(ValueError, 'SHA1'):
                    pak.read(bytes(damaged))
            else:
                self.assertIn('SHA1', pak.extract(bytes(damaged), 'game.pak')[1])
        encrypted = bytearray(fixture())
        encrypted[-205] = 1
        with self.assertRaisesRegex(ValueError, 'mã hóa'):
            pak.read(bytes(encrypted))

    def test_scan_install_restore_and_external_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'game'
            root.mkdir()
            target = root / 'content.pak'
            raw = fixture(method='Zlib')
            target.write_bytes(raw)
            external = root / 'launcher-GSE'
            external.mkdir()
            (external / 'achievements.json').write_text('{"description":{"english":"External achievement"}}')
            toc = bytearray(144)
            toc[:16] = b'-==--==--==--==-'
            toc[16] = 8
            struct.pack_into('<III', toc, 20, 144, 1234, 5678)
            toc[80] = 9
            (root / 'game.utoc').write_bytes(toc)
            (root / 'game.ucas').write_bytes(b'not text')
            project = scan(root, deep=True, max_mb=1)
            self.assertEqual(project.engines, ['Unreal Engine'])
            self.assertTrue(all(e.file == 'content.pak' for e in project.entries))
            self.assertIn('1,234 chunk', next(f.note for f in project.files if f.kind == 'utoc'))
            preflight(project)
            project.entries[0].translation = 'Bắt đầu chơi'
            export_patch(project, base / 'patch')
            install_patch(base / 'patch', root)
            install_patch(base / 'patch', root, restore=True)
            self.assertEqual(target.read_bytes(), raw)
        self.assertEqual(context_locale('Game/en-001/UI.locres'), 'en-001')
