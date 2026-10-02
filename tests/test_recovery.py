import json
import http.client
import threading
import unittest
from unittest.mock import patch

from toolvh.formats import extract
from toolvh.model import Project
from toolvh.translation import APIConfig, Client, translate
from toolvh.terminology import context_map, inferred_names, repair_protected_names, validate_entry


class RecoveryTest(unittest.TestCase):
    def config(self):
        return APIConfig(provider='ollama', base_url='http://localhost:11434', model='test', delay_seconds=0)

    def project(self, sources):
        return Project('.', entries=extract(json.dumps(sources), 'json', 'en.json'))

    def test_missing_token_retried_as_single_sentence(self):
        project = self.project(['Hello{comma} player.', 'Start game'])
        sizes = []
        def complete(client, messages, stop):
            items = json.loads(messages[-1]['content'])['items']
            sizes.append(len(items))
            return {'translations': [{'id': item['id'], 'text': 'Sai' if len(items) > 1 and '{' not in item['text'] and '__VH' in item['text'] else item['text'].replace('Hello', 'Xin chào')} for item in items]}
        with patch.object(Client, 'complete', complete):
            self.assertEqual(translate(project, self.config()), 2)
        self.assertEqual(sizes, [2, 1])
        self.assertEqual(project.entries[0].translation, 'Xin chào{comma} player.')
        self.assertFalse(project.entries[0].error)

    def test_literal_recovery_keeps_comma_name_and_format_order(self):
        project = self.project(['<b>Go{comma} Lucy!</b>'])
        project.protected_names = ['Lucy']
        seen = []
        def complete(client, messages, stop):
            item = json.loads(messages[-1]['content'])['items'][0]
            seen.append(item)
            target = 'Sai' if '__VH' in item['text'] else 'Đi'
            return {'translations': [{'id': item['id'], 'text': target}]}
        with patch.object(Client, 'complete', complete):
            self.assertEqual(translate(project, self.config()), 1)
        self.assertEqual(project.entries[0].translation, '<b>Đi{comma} Lucy!</b>')
        self.assertEqual(len(seen), 3)
        self.assertIn('full_sentence_context', seen[-1])
        self.assertNotIn('Lucy', seen[-1]['text'])

    def test_bad_batch_is_isolated_and_other_sentences_continue(self):
        project = self.project(['Hello{comma} friend.', 'Quit game'])
        calls = []
        def complete(client, messages, stop):
            items = json.loads(messages[-1]['content'])['items']; calls.append(len(items))
            if len(items) > 1:
                raise ValueError('Malformed JSON')
            return {'translations': [{'id': items[0]['id'], 'text': items[0]['text'].replace('Hello', 'Chào').replace('Quit game', 'Thoát')}]}
        with patch.object(Client, 'complete', complete):
            self.assertEqual(translate(project, self.config()), 2)
        self.assertEqual(calls, [2, 1, 1])

    def test_recovery_stays_bounded_and_old_translation_survives(self):
        project = self.project(['Hello{comma} friend.'])
        project.entries[0].translation = 'Bản dịch cũ'
        with patch.object(Client, 'complete', return_value={'translations': []}) as called:
            self.assertEqual(translate(project, self.config(), overwrite=True), 0)
        self.assertEqual(called.call_count, 4)
        self.assertEqual(project.entries[0].translation, 'Bản dịch cũ')
        self.assertTrue(project.entries[0].error)

    def test_bad_configuration_does_not_trigger_recovery(self):
        project = self.project(['Hello{comma} friend.'])
        config = self.config()
        config.base_url = 'http://remote.example/v1'
        with patch.object(Client, 'complete') as called:
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                translate(project, config)
        called.assert_not_called()

    def test_local_disconnection_is_a_readable_resumable_error(self):
        client = Client(self.config())
        with patch.object(client.opener, 'open', side_effect=http.client.RemoteDisconnected('closed')):
            with self.assertRaisesRegex(RuntimeError, 'Ollama'):
                client._request('http://localhost:11434/api/chat', {}, threading.Event())

    def test_cloud_does_not_automatically_retry(self):
        project = self.project(['Hello{comma} friend.'])
        with patch.object(Client, 'complete', return_value={'translations': []}) as called:
            with self.assertRaises(ValueError):
                translate(project, APIConfig(model='test', delay_seconds=0))
        self.assertEqual(called.call_count, 1)

    def test_only_errors_includes_old_target_skips_good_and_disabled(self):
        project = self.project(['Hello{comma} friend.', 'Start game', 'Quit game'])
        project.entries[0].error = 'Missing token'
        project.entries[0].translation = 'Old'
        project.entries[1].translation = 'Bắt đầu'
        project.entries[2].error = 'Missing token'
        project.entries[2].enabled = False
        def complete(client, messages, stop):
            items = json.loads(messages[-1]['content'])['items']
            self.assertEqual([item['id'] for item in items], [project.entries[0].id])
            return {'translations': [{'id': items[0]['id'], 'text': items[0]['text'].replace('Hello', 'Chào')}]}
        with patch.object(Client, 'complete', complete):
            self.assertEqual(translate(project, self.config(), only_errors=True), 1)
        self.assertFalse(project.entries[0].error)
        self.assertEqual(project.entries[1].translation, 'Bắt đầu')
        self.assertFalse(project.entries[2].translation)

    def test_cancel_during_recovery_stops_additional_calls(self):
        project = self.project(['Hello{comma} friend.'])
        stop = threading.Event()
        def complete(client, messages, event):
            event.set()
            return {'translations': [{'id': project.entries[0].id, 'text': 'Sai'}]}
        with patch.object(Client, 'complete', autospec=True, side_effect=complete) as called:
            self.assertEqual(translate(project, self.config(), stop=stop), 0)
        self.assertEqual(called.call_count, 1)

    def test_fragment_inventing_tokens_is_rejected(self):
        project = self.project(['Hello{comma} friend.'])
        def complete(client, messages, stop):
            item = json.loads(messages[-1]['content'])['items'][0]
            target = 'Sai' if '__VH' in item['text'] else 'Chào {new}'
            return {'translations': [{'id': item['id'], 'text': target}]}
        with patch.object(Client, 'complete', complete):
            self.assertEqual(translate(project, self.config()), 0)
        self.assertFalse(project.entries[0].translation)
        self.assertTrue(project.entries[0].error)

    def test_declared_locations_and_known_morta_names_are_protected(self):
        project = self.project(['Silk Caverns', 'Level'])
        project.root = r'E:\SteamLibrary\steamapps\common\ChildrenOfMorta'
        project.entries[0].context = 'Locations / Dòng 2 / en / a'
        project.entries[1].context = 'Menus / Dòng 8 / en / b'
        names = inferred_names(project)
        self.assertIn('Silk Caverns', names)
        self.assertIn('Barahut', names)
        self.assertNotIn('Level', names)

    def test_many_fragments_do_not_cause_unbounded_requests(self):
        project = self.project(['{comma}'.join(['Hello'] * 66)])
        with patch.object(Client, 'complete', return_value={'translations': []}) as called:
            self.assertEqual(translate(project, self.config()), 0)
        self.assertEqual(called.call_count, 2)

    def test_long_recovery_batches_fragments_and_keeps_every_separator(self):
        project = self.project(['{comma}'.join(['Hello'] * 12)])
        sizes = []
        def complete(client, messages, stop):
            items = json.loads(messages[-1]['content'])['items']
            if '__VH' in items[0]['text']:
                return {'translations': []}
            sizes.append(len(items))
            return {'translations': [{'id': item['id'], 'text': 'Chào'} for item in items]}
        with patch.object(Client, 'complete', complete):
            self.assertEqual(translate(project, self.config()), 1)
        self.assertEqual(sizes, [5, 5, 2])
        self.assertEqual(project.entries[0].translation, '{comma}'.join(['Chào'] * 12))

    def test_restore_standalone_name_preserves_prose_and_user_glossary(self):
        project = self.project(['City Of Thieves', 'Reach City Of Thieves', 'Start game'])
        project.protected_names = ['City Of Thieves']
        project.entries[0].translation = 'Thành phố cướp'
        project.entries[1].translation = 'Đến thành phố cướp'
        project.entries[2].translation = 'Bắt đầu'
        self.assertEqual(repair_protected_names(project), 1)
        self.assertEqual(project.entries[0].translation, 'City Of Thieves')
        self.assertEqual(project.entries[1].translation, 'Đến thành phố cướp')
        project.glossary = {'City Of Thieves': 'Thành phố Đạo Tặc'}
        self.assertEqual(repair_protected_names(project), 1)
        self.assertEqual(project.entries[0].translation, 'Thành phố Đạo Tặc')

    def test_generic_location_words_are_not_global_names(self):
        project = self.project(['Forest', 'Temple', 'Silk Caverns'])
        for entry in project.entries:
            entry.context = 'Locations / Dòng 1 / en / a'
        names = inferred_names(project)
        self.assertNotIn('Forest', names)
        self.assertNotIn('Temple', names)
        self.assertIn('Silk Caverns', names)

    def test_name_case_change_is_not_a_false_missing_name(self):
        project = self.project(['Talk to kevin'])
        project.protected_names = ['Kevin']
        self.assertEqual(validate_entry(project, project.entries[0], 'Nói chuyện với Kevin'), [])

    def test_table_neighbors_share_table_not_row_or_locale(self):
        project = self.project(['First', 'Second', 'Other table', 'Other language'])
        for entry, context in zip(project.entries, ['MentalBubbles / Dòng 1 / en / a', 'MentalBubbles / Dòng 2 / en / b', 'JournalEntries / Dòng 1 / en / c', 'MentalBubbles / Dòng 3 / fr / d']):
            entry.context = context
        neighbors = context_map(project)
        self.assertEqual(neighbors[project.entries[0].id]['previous_or_next'], ['Second'])


if __name__ == '__main__':
    unittest.main()
