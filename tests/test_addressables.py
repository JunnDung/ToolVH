import json
import base64
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from toolvh.addressables import BinaryCatalog, bundle_crc, update_catalog, update_json_catalog, catalog_updates
from toolvh.patching import install_patch
from toolvh.model import digest
from synthetic_addressables import make_fixture, bundle


class AddressablesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        (cls.patch, cls.relative, cls.original, cls.modified, cls.catalog,
         cls.original_crc, cls.modified_crc) = make_fixture(Path(cls.fixture.name))

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def test_crc_reads_uncompressed_payload(self):
        self.assertEqual(bundle_crc(self.original), self.original_crc)
        self.assertEqual(bundle_crc(self.modified), self.modified_crc)
        import zlib
        payload = b'Independent synthetic compression test.' * 20
        self.assertEqual(bundle_crc(bundle(payload, compressed=True)), zlib.crc32(payload))

    def test_catalog_only_changes_target_crc_and_size(self):
        old = BinaryCatalog(self.catalog).bundles()
        new_data = update_catalog(self.catalog, {self.relative: (self.original, self.modified)})
        new = BinaryCatalog(new_data).bundles()
        self.assertEqual(len(old), 2)
        edited = [(a, b) for a, b in zip(old, new) if a != b]
        self.assertEqual(len(edited), 1)
        a, b = edited[0]
        self.assertEqual(b[2:], (self.modified_crc, len(self.modified)))
        differences = [i for i, (x, y) in enumerate(zip(self.catalog, new_data)) if x != y]
        self.assertTrue(all(a[1] + 8 <= i < a[1] + 16 for i in differences))

    def test_unknown_format_and_wrong_source_rejected(self):
        with self.assertRaises(ValueError):
            BinaryCatalog(b"not a catalog")
        with self.assertRaisesRegex(ValueError, "CRC nguồn"):
            update_catalog(self.catalog, {self.relative: (self.modified, self.original)})

    def test_dynamic_fragment_cycle_is_rejected(self):
        data = bytearray(48)
        struct.pack_into('<II', data, 0, 0x0DE38942, 2)
        struct.pack_into('<II', data, 32, 0x40000020, 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "dynamic"):
            BinaryCatalog(bytes(data)).string(0x40000020, '/')

    def test_local_unity_web_request_cache_is_rejected(self):
        data = bytearray(self.catalog)
        item, = [b for b in BinaryCatalog(data).bundles() if b[0].endswith('/' + Path(self.relative).name)]
        common, = struct.unpack_from('<I', data, item[1] + 16)
        flags, = struct.unpack_from('<I', data, common + 4)
        struct.pack_into('<I', data, common + 4, flags | 8)
        with self.assertRaisesRegex(ValueError, 'UnityWebRequest'):
            update_catalog(bytes(data), {self.relative: (self.original, self.modified)})

    def test_remote_catalog_without_dependencies_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'Sample_Data/StreamingAssets/aa'
            folder.mkdir(parents=True)
            settings = {'m_CatalogLocations': [{'m_InternalId': 'https://example.com/catalog.bin', 'm_Dependencies': []}]}
            (folder / 'settings.json').write_text(json.dumps(settings))
            with self.assertRaisesRegex(ValueError, 'remote'):
                catalog_updates(root, {self.relative: (self.original, self.modified)})

    def test_missing_catalog_patch_rejected_and_fixed_patch_restores(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            game, patch = temp / "game", temp / "patch"
            shutil.copytree(self.patch, patch)
            aa = Path(self.relative).parent.parent
            (game / aa).mkdir(parents=True)
            settings = {"m_CatalogLocations": [{"m_InternalId": "{runtime}/catalog.bin", "m_Dependencies": []}]}
            (game / aa / "settings.json").write_text(json.dumps(settings))
            (game / aa / "catalog.bin").write_bytes(self.catalog)
            (game / self.relative).parent.mkdir(exist_ok=True)
            (game / self.relative).write_bytes(self.original)
            with self.assertRaisesRegex(ValueError, "catalog CRC"):
                install_patch(patch, game)
            self.assertEqual((game / self.relative).read_bytes(), self.original)
            data = update_catalog(self.catalog, {self.relative: (self.original, self.modified)})
            relative = (aa / "catalog.bin").as_posix()
            (patch / "files" / relative).write_bytes(data)
            (patch / "backup" / relative).write_bytes(self.catalog)
            manifest = json.loads((patch / "manifest.json").read_text())
            manifest["files"].append({"path": relative, "original_sha256": digest(self.catalog), "patched_sha256": digest(data)})
            (patch / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(install_patch(patch, game), 2)
            self.assertEqual(install_patch(patch, game), 0)
            self.assertEqual(install_patch(patch, game, restore=True), 2)
            self.assertEqual((game / aa / "catalog.bin").read_bytes(), self.catalog)
            self.assertEqual((game / self.relative).read_bytes(), self.original)


class JsonAddressablesTest(unittest.TestCase):
    def fixture(self, original, uwr=False):
        options = {"m_Crc": bundle_crc(original), "m_BundleSize": len(original),
                   "m_Hash": "0123456789abcdef0123456789abcdef", "m_UseUWRForLocalBundles": uwr}
        assembly = b"Unity.ResourceManager"
        cls = b"UnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions"
        value = json.dumps(options).encode("utf-16-le")
        extra = bytes([7, len(assembly)]) + assembly + bytes([len(cls)]) + cls + struct.pack("<i", len(value)) + value
        entries = struct.pack("<i14i", 2, 0, 0, -1, 0, 0, 0, 0, 1, 1, -1, 0, -1, 0, 0)
        data = {"m_InternalIds": ["{UnityEngine.AddressableAssets.Addressables.RuntimePath}/StandaloneWindows64/english.bundle", "other.asset"],
                "m_ProviderIds": ["UnityEngine.ResourceManagement.ResourceProviders.AssetBundleProvider", "BundledAssetProvider"],
                "m_EntryDataString": base64.b64encode(entries).decode(),
                "m_ExtraDataString": base64.b64encode(extra).decode(), "m_KeyDataString": "unchanged"}
        return json.dumps(data).encode(), options

    def test_json_options_preserve_other_records(self):
        original, modified = bundle(b"English"), bundle("Tiếng Việt".encode())
        data, options = self.fixture(original)
        output = update_json_catalog(data, {"english.bundle": (original, modified)})
        before, after = json.loads(data), json.loads(output)
        oldextra = base64.b64decode(before["m_ExtraDataString"])
        extra = base64.b64decode(after["m_ExtraDataString"])
        self.assertTrue(extra.startswith(oldextra))
        entries = base64.b64decode(after["m_EntryDataString"])
        self.assertEqual(entries[32:], base64.b64decode(before["m_EntryDataString"])[32:])
        replacement = extra[len(oldextra):]
        offset = 2 + replacement[1]
        offset += 1 + replacement[offset]
        length, = struct.unpack_from("<i", replacement, offset)
        value = json.loads(replacement[offset + 4:offset + 4 + length].decode("utf-16-le"))
        self.assertEqual(value, dict(options, m_Crc=bundle_crc(modified), m_BundleSize=len(modified)))
        for key in before.keys() - {"m_ExtraDataString", "m_EntryDataString"}:
            self.assertEqual(before[key], after[key])

    def test_json_rejects_wrong_crc_cache_and_truncated_table(self):
        original, modified = bundle(b"English"), bundle(b"Vietnamese")
        data, _ = self.fixture(original)
        with self.assertRaisesRegex(ValueError, "CRC nguồn"):
            update_json_catalog(data, {"english.bundle": (modified, original)})
        data, _ = self.fixture(original, uwr=True)
        with self.assertRaisesRegex(ValueError, "UnityWebRequest"):
            update_json_catalog(data, {"english.bundle": (original, modified)})
        parsed = json.loads(data)
        parsed["m_EntryDataString"] = base64.b64encode(b"12345").decode()
        with self.assertRaisesRegex(ValueError, "location"):
            update_json_catalog(json.dumps(parsed).encode(), {})

    def test_json_install_retry_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patch, relative, original, modified, *_ = make_fixture(root)
            game = root / "game"
            aa = Path(relative).parent.parent
            (game / Path(relative).parent).mkdir(parents=True)
            (game / relative).write_bytes(original)
            data, _ = self.fixture(original)
            (game / aa / "catalog.json").write_bytes(data)
            settings = {"m_CatalogLocations": [{"m_InternalId": "{runtime}/catalog.json", "m_Dependencies": []}]}
            (game / aa / "settings.json").write_text(json.dumps(settings))
            with self.assertRaisesRegex(ValueError, "catalog CRC"):
                install_patch(patch, game)
            self.assertEqual((game / relative).read_bytes(), original)
            updates = catalog_updates(game, {relative: (original, modified)})
            manifest = json.loads((patch / "manifest.json").read_text())
            for path, (source, translated) in updates.items():
                (patch / "backup" / path).write_bytes(source)
                (patch / "files" / path).write_bytes(translated)
                manifest["files"].append({"path": path, "original_sha256": digest(source), "patched_sha256": digest(translated)})
            (patch / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(install_patch(patch, game), 2)
            self.assertEqual(install_patch(patch, game), 0)
            self.assertEqual(install_patch(patch, game, restore=True), 2)
            self.assertEqual((game / aa / "catalog.json").read_bytes(), data)
            self.assertEqual((game / relative).read_bytes(), original)
