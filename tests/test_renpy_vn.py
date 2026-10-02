import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toolvh import renpy
from toolvh.patching import export_patch, install_patch, preflight
from toolvh.scanner import scan
from toolvh.translation import validate


class RenpyVisualNovelTests(unittest.TestCase):
    def test_attributes_named_speakers_extend_and_arguments_keep_code(self):
        source = '''label meeting:
    e happy @ blush "Hello [player!t]!" nointeract
    extend " Welcome back." with dissolve
    character.lucy -sad "Good morning." (what_color="#8c8", interact=False)
    "Lucy" "A lovely day." # speaker name
    if "internal flag":
        jump done
    menu:
        "Go west" if has_key:
            jump west
'''
        entries, _ = renpy.extract(source, 'game/en/story.rpy')
        self.assertEqual([entry.source for entry in entries], ['Hello [player!t]!', ' Welcome back.', 'Good morning.', 'A lovely day.', 'Go west'])
        self.assertTrue(all(entry.enabled for entry in entries))
        self.assertIn('meeting / e happy @ blush', entries[0].context)
        entries[0].translation = 'Chào [player!t]!'
        entries[2].translation = 'Chào buổi sáng.'
        changed = renpy.rebuild(source, [entries[0], entries[2]])
        self.assertIn('e happy @ blush "Chào [player!t]!" nointeract', changed)
        self.assertIn('character.lucy -sad "Chào buổi sáng." (what_color="#8c8", interact=False)', changed)
        self.assertIn('"Lucy" "A lovely day." # speaker name', changed)
        self.assertIn('"Go west" if has_key:', changed)
        self.assertEqual(renpy.extract(changed, 'game/en/story.rpy')[0][0].source, entries[0].translation)

    def test_physical_multiline_keeps_explicit_newline_and_tags(self):
        source = 'label start:\r\n    e "Hello\r\n        [player!t], {b}welcome{/b}!\\nNext line."\r\n    jump done\r\n'
        entries, _ = renpy.extract(source, 'en/story.rpy')
        self.assertEqual(entries[0].source, 'Hello [player!t], {b}welcome{/b}!\nNext line.')
        entries[0].translation = 'Chào [player!t], {b}mừng bạn{/b}!\nDòng tiếp.'
        self.assertEqual(validate(entries[0].source, entries[0].translation), [])
        changed = renpy.rebuild(source, entries)
        self.assertIn('    jump done\r\n', changed)
        self.assertEqual(renpy.extract(changed, 'en/story.rpy')[0][0].source, entries[0].translation)

    def test_monologue_blocks_preserve_boundaries_and_other_blocks(self):
        for quote in ('"""', "'''"):
            with self.subTest(quote=quote):
                source = 'label start:\n    e happy ' + quote + '\n    First paragraph wraps\n    across lines.\n\n    Second paragraph.\n\n    Third paragraph.\n    ' + quote + '\n    jump end\n'
                entries, _ = renpy.extract(source, 'en/story.rpy')
                self.assertEqual([entry.source for entry in entries], ['First paragraph wraps across lines.', 'Second paragraph.', 'Third paragraph.'])
                entries[1].translation = 'Lời "chào" của Lucy\'s.'
                changed = renpy.rebuild(source, [entries[1]])
                reopened = renpy.extract(changed, 'en/story.rpy')[0]
                self.assertEqual([entry.source for entry in reopened], [entries[0].source, entries[1].translation, entries[2].source])
                self.assertIn('First paragraph wraps\n    across lines.', changed)
                self.assertEqual(changed.count('\n\n'), source.count('\n\n'))
                self.assertTrue(changed.endswith('    jump end\n'))

    def test_python_screens_foreign_templates_and_assets_not_extracted(self):
        source = '''init python:
    data = """
    e "Fake dialogue"
    """
screen main_menu:
    text "Not source dialogue"
translate french scene:
    e "Bonjour"
label start:
    play music "audio/theme.ogg"
    scene bg room
    e "Real dialogue" # an unmatched quote " in a comment
'''
        entries, _ = renpy.extract(source, 'game/story.rpy')
        self.assertEqual([entry.source for entry in entries], ['Real dialogue'])
        self.assertFalse(entries[0].enabled)
        self.assertEqual(renpy.extract(source, 'game/tl/fr/story.rpy')[0], [])

    def test_unclosed_literals_fail_instead_of_extracting_inside_them(self):
        with self.assertRaisesRegex(ValueError, 'chưa đóng'):
            renpy.extract('e "Unclosed\n e "Fake"\n', 'en/story.rpy')

    def test_monologue_none_is_reported_and_skipped(self):
        entries, note = renpy.extract('rpy monologue none\ne """Keep\nline breaks"""\ne "Next dialogue"\n', 'en/story.rpy')
        self.assertEqual([entry.source for entry in entries], ['Next dialogue'])
        self.assertIn('Bỏ qua 1', note)

    def test_multiline_template_keeps_old_literal(self):
        source = 'translate english strings:\n    old "Start\n        game"\n    new ""\n'
        entries, _ = renpy.extract(source, 'game/tl/en/strings.rpy')
        self.assertEqual(entries[0].source, 'Start game')
        entries[0].translation = 'Bắt đầu chơi'
        changed = renpy.rebuild(source, entries)
        self.assertIn('old "Start\n        game"', changed)
        self.assertIn('new "Bắt đầu chơi"', changed)

    def test_multiline_scan_export_copy_restore_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            game = base / 'game'
            story = game / 'en/story.rpy'
            story.parent.mkdir(parents=True)
            original = b'label start:\n    e happy "Hello\n        player!"\n    e """First part.\n\nSecond part."""\n'
            story.write_bytes(original)
            project = scan(game)
            self.assertEqual(len(project.entries), 3)
            for entry in project.entries:
                entry.translation = 'Chào người chơi!'
            preflight(project)
            export_patch(project, base / 'patch')
            self.assertEqual(story.read_bytes(), original)
            shutil.copytree(base / 'patch/files', game, dirs_exist_ok=True)
            self.assertEqual([entry.source for entry in renpy.extract(story.read_text(encoding='utf-8'), 'en/story.rpy')[0]], ['Chào người chơi!'] * 3)
            install_patch(base / 'patch', game, restore=True)
            self.assertEqual(story.read_bytes(), original)

    def test_stale_monologue_and_duplicate_locator_are_rejected(self):
        source = 'e """First part.\n\nSecond part."""\n'
        entries, _ = renpy.extract(source, 'en/story.rpy')
        entries[0].translation = 'Đoạn đầu.'
        with self.assertRaises(ValueError):
            renpy.rebuild(source.replace('First', 'Changed'), entries[:1])
        with self.assertRaises(ValueError):
            renpy.rebuild(source, [entries[0], entries[0]])

    def test_cli_scan_on_windows_legacy_code_page_saves_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / 'game/en'
            game.mkdir(parents=True)
            (game / 'story.rpy').write_text('e "Hello player!"\n', encoding='utf-8')
            destination = root / 'project.toolvh.json'
            env = dict(os.environ, PYTHONIOENCODING='cp1252')
            result = subprocess.run([sys.executable, '-m', 'toolvh', 'scan', str(game.parent), '--out', str(destination)],
                                    capture_output=True, env=env, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertIn('đoạn text', result.stdout.decode('utf-8'))
            self.assertTrue(destination.exists())
