import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from toolvh.scanner import scan
from toolvh.patching import apply_project, install_patch
from toolvh.export_installed import export_copy
from toolvh.model import digest,atomic_write

class InstalledExportTests(unittest.TestCase):
    def test_export_with_text_and_font_patch_keeps_game_and_uses_original_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);game=root/'Game';game.mkdir()
            text=game/'en.json';text.write_text('{"en":"Hello {0}"}')
            font=game/'menu.ttf';font.write_bytes(b'original-font')
            p=scan(game);p.entries[0].translation='Xin chào {0}'
            apply_project(p,root/'text-patch')
            fontpatch=root/'font-patch';(fontpatch/'files').mkdir(parents=True);(fontpatch/'backup').mkdir()
            (fontpatch/'backup/menu.ttf').write_bytes(b'original-font')
            (fontpatch/'files/menu.ttf').write_bytes(b'patched-font')
            (fontpatch/'manifest.json').write_text(json.dumps({'schema':1,'files':[{'path':'menu.ttf','original_sha256':digest(b'original-font'),'patched_sha256':digest(b'patched-font')}]}))
            install_patch(fontpatch,game);p.font_patches=[str(fontpatch)]
            before=(text.read_bytes(),font.read_bytes(),repr(p))
            p.entries[0].translation='Chào bạn {0}'
            original_project=repr(p)
            with patch('toolvh.export_installed.os.link', side_effect=OSError(17, 'different drives')):
                result=export_copy(p,root/'copy')
            self.assertEqual((text.read_bytes(),font.read_bytes()),before[:2])
            self.assertEqual(repr(p),original_project)
            self.assertEqual(json.loads((root/'copy/files/en.json').read_text(encoding='utf-8')),{'en':'Chào bạn {0}'})
            self.assertEqual((root/'copy/backup/en.json').read_text(encoding='utf-8'),'{"en":"Hello {0}"}')
            self.assertEqual(result['game_root'],str(game.resolve()))
            self.assertFalse((root/'copy/files/menu.ttf').exists())
            font.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'khác phiên bản'):
                export_copy(p,root/'bad')
            self.assertFalse((root/'bad').exists())

    def test_invalid_translation_keeps_english_without_blocking_valid_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);game=root/'Game';game.mkdir()
            (game/'en.json').write_text('{"en":{"one":"Hello {0}","two":"Start game"}}')
            p=scan(game)
            for e in p.entries:e.translation='Sai' if '{0}' in e.source else 'Bắt đầu chơi'
            result=export_copy(p,root/'copy')
            self.assertEqual(len(result['skipped_invalid']),1)
            self.assertEqual(json.loads((root/'copy/files/en.json').read_text(encoding='utf-8')),{'en':{'one':'Hello {0}','two':'Bắt đầu chơi'}})
            self.assertTrue((root/'copy/skipped-invalid.json').exists())
