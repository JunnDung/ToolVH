import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolvh.model import Project, FileRecord, Entry, digest
from toolvh.patching import export_patch, install_patch
from toolvh.scanner import scan
from toolvh.addressables import BinaryCatalog
from synthetic_addressables import make_fixture


class CopyExportTests(unittest.TestCase):
    def test_copy_contents_into_game_and_restore_with_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            game = base / 'game'
            target = game / 'Data' / 'en.json'
            target.parent.mkdir(parents=True)
            original = b'{"text":"Start game", "id":12}'
            target.write_bytes(original)
            unrelated = game / 'image.bin'
            unrelated.write_bytes(b'unchanged')
            project = scan(game)
            project.entries[0].translation = 'Bắt đầu chơi'
            destination = base / 'export'
            export_patch(project, destination)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(project.applied_patch, '')
            shutil.copytree(destination / 'files', game, dirs_exist_ok=True)
            self.assertEqual(json.loads(target.read_bytes()), {'text': 'Bắt đầu chơi', 'id': 12})
            self.assertEqual(unrelated.read_bytes(), b'unchanged')
            self.assertFalse((game / 'files').exists())
            self.assertEqual(install_patch(destination, game, restore=True), 1)
            self.assertEqual(target.read_bytes(), original)
            shutil.copytree(destination / 'files', game, dirs_exist_ok=True)
            shutil.copytree(destination / 'backup', game, dirs_exist_ok=True)
            self.assertEqual(target.read_bytes(), original)
            instructions = (destination / 'README.txt').read_text(encoding='utf-8-sig')
            self.assertIn('Data/en.json', instructions)
            self.assertIn('không tự kèm bản vá font', instructions)
            self.assertIn('Không chép chính thư mục files/', instructions)

    def test_copy_export_includes_updated_addressables_catalog_and_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _, relative, original, modified, catalog, _, modified_crc = make_fixture(base / 'fixture')
            game = base / 'game'
            bundle = game / relative
            bundle.parent.mkdir(parents=True)
            bundle.write_bytes(original)
            aa = bundle.parent.parent
            settings = {'m_CatalogLocations': [{'m_InternalId': '{runtime}/catalog.bin', 'm_Dependencies': []}]}
            (aa / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
            catalog_path = aa / 'catalog.bin'
            catalog_path.write_bytes(catalog)
            project = Project(str(game), files=[FileRecord(relative, 'unity', digest(original))],
                              entries=[Entry('entry', relative, {}, 'Start game', '', translation='Bắt đầu')])
            destination = base / 'export'
            with patch('toolvh.patching.rebuild_unity', return_value=modified):
                manifest = export_patch(project, destination)
            self.assertEqual(len(manifest['files']), 2)
            self.assertEqual(bundle.read_bytes(), original)
            self.assertEqual(catalog_path.read_bytes(), catalog)
            shutil.copytree(destination / 'files', game, dirs_exist_ok=True)
            self.assertEqual(bundle.read_bytes(), modified)
            row, = [row for row in BinaryCatalog(catalog_path.read_bytes()).bundles()
                     if row[0].endswith('/' + bundle.name)]
            self.assertEqual(row[2:], (modified_crc, len(modified)))
            self.assertEqual(install_patch(destination, game, restore=True), 2)
            self.assertEqual(bundle.read_bytes(), original)
            self.assertEqual(catalog_path.read_bytes(), catalog)

    def test_export_rejects_stale_source_without_creating_package(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            game = base / 'game'
            game.mkdir()
            source = game / 'en.json'
            source.write_text('{"text":"Start game"}', encoding='utf-8')
            project = scan(game)
            project.entries[0].translation = 'Bắt đầu'
            source.write_text('{"text":"Changed text"}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'thay đổi'):
                export_patch(project, base / 'export')
            self.assertFalse((base / 'export').exists())
            self.assertFalse(list(base.glob('.toolvh-patch-*')))
