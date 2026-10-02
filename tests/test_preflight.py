import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolvh.model import FileRecord
from toolvh.patching import preflight
from toolvh.scanner import scan


class PreflightExpansionTests(unittest.TestCase):
    def test_long_unicode_roundtrip_reports_scan_and_preserves_game_and_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'en.json'
            target.write_text('{"text":"Start game", "other":"Quit game"}', encoding='utf-8')
            project = scan(root)
            project.entries[1].enabled = False
            project.entries[0].translation = 'Bắt đầu'
            project.entries[0].error = 'existing review'
            project.files.append(FileRecord('unsupported.ucas', 'ucas', note='IoStore chưa hỗ trợ'))
            project.files.append(FileRecord('settings.json', 'metadata'))
            original = target.read_bytes()
            before = repr(project)
            from toolvh.patching import prepare_changes
            with patch('toolvh.patching.prepare_changes', wraps=prepare_changes) as writer:
                report = preflight(project)
            self.assertEqual(writer.call_count, 2)
            expanded = writer.call_args_list[1].args[1]['en.json'][0]
            self.assertGreater(len(expanded.translation), len(expanded.source))
            self.assertIn('Tiếng Việt', expanded.translation)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(repr(project), before)
            self.assertEqual(list(root.iterdir()), [target])
            self.assertTrue(report['expanded_text_checked'])
            self.assertEqual(report['selected_entries'], 1)
            self.assertEqual(report['scan_summary']['candidate_entries'], 2)
            self.assertEqual(report['scan_summary']['unselected_entries'], 1)
            self.assertEqual(report['scan_summary']['files_with_text'], 1)
            self.assertEqual(report['scan_summary']['files_without_extracted_text'],
                             [{'path': 'unsupported.ucas', 'kind': 'ucas', 'note': 'IoStore chưa hỗ trợ'}])

    def test_expansion_failure_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'en.json'
            target.write_text('{"text":"Start game"}', encoding='utf-8')
            project = scan(root)
            original = target.read_bytes()
            from toolvh.patching import prepare_changes
            def bounded_writer(project, groups, progress):
                if any(len(entry.translation) > len(entry.source) for entries in groups.values() for entry in entries):
                    raise ValueError('Fixture writer rejects expanded text')
                return prepare_changes(project, groups, progress)
            with patch('toolvh.patching.prepare_changes', side_effect=bounded_writer):
                with self.assertRaisesRegex(ValueError, 'expanded text'):
                    preflight(project)
            self.assertEqual(target.read_bytes(), original)

    def test_cancel_before_expanded_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'en.json').write_text('{"text":"Start game"}', encoding='utf-8')
            project = scan(root)
            stop = False
            def progress(message):
                nonlocal stop
                if message.startswith('Đang đóng gói:'):
                    stop = True
            from toolvh.patching import prepare_changes
            with patch('toolvh.patching.prepare_changes', wraps=prepare_changes) as writer:
                with self.assertRaises(InterruptedError):
                    preflight(project, progress, lambda: stop)
            self.assertEqual(writer.call_count, 1)
