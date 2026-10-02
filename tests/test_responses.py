import io
import json
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from toolvh import renpy
from toolvh.formats import extract
from toolvh.model import Project
from toolvh.terminology import context_map, inferred_names
from toolvh.translation import APIConfig, Client, translate


def response(data, **changes):
    result = {'status': 'completed', 'error': None, 'incomplete_details': None, 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'message', 'role': 'assistant', 'status': 'completed',
         'content': [{'type': 'output_text', 'text': json.dumps(data, ensure_ascii=False)}]}]}
    result.update(changes)
    return result


class ResponsesTests(unittest.TestCase):
    def config(self):
        return APIConfig(provider='openai-responses', base_url='https://example.org/v1', model='test', api_key='dummy-secret', delay_seconds=0)

    def test_http_request_uses_responses_shape_and_reads_null_error(self):
        client = Client(self.config())
        reply = io.BytesIO(json.dumps(response({'translation': 'Bắt đầu'})).encode())
        with patch.object(client.opener, 'open', return_value=reply) as opened:
            self.assertEqual(client.test_connection(), 'Bắt đầu')
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, 'https://example.org/v1/responses')
        self.assertEqual(request.get_header('Authorization'), 'Bearer dummy-secret')
        self.assertNotIn('dummy-secret', request.full_url)
        payload = json.loads(request.data)
        self.assertFalse(payload['store'])
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['text'], {'format': {'type': 'json_object'}})
        self.assertIn('JSON', payload['instructions'])
        self.assertEqual(payload['input'][0]['role'], 'user')
        self.assertNotIn('messages', payload)
        self.assertNotIn('response_format', payload)

    def test_auto_detection_and_full_url_normalization_without_mutating_config(self):
        for provider in ('openai-responses', 'openai-compatible'):
            config = replace(self.config(), provider=provider, base_url='https://example.org/v1/responses/')
            client = Client(config)
            self.assertEqual(client.config.provider, 'openai-responses')
            self.assertEqual(client.config.base_url, 'https://example.org/v1')
            self.assertTrue(config.base_url.endswith('/responses/'))
            with patch.object(client, '_request', return_value={'data': [{'id': 'test'}]}) as request:
                self.assertEqual(client.list_models(), ['test'])
            self.assertEqual(request.call_args.args[0], 'https://example.org/v1/models')

    def test_json_mode_can_be_disabled(self):
        client = Client(replace(self.config(), json_mode=False))
        with patch.object(client, '_request', return_value=response({'translation': 'Bắt đầu'})) as request:
            client.test_connection()
        self.assertNotIn('text', request.call_args.args[1])

    def test_incomplete_refusal_and_invalid_output_rejected(self):
        invalid = [response({}, status='incomplete'), response({}, status='failed'),
                   response({}, incomplete_details={'reason': 'max_output_tokens'}),
                   response({}, output=None), response({}, output=[None]),
                   response({}, output=[{'type': 'message', 'role': 'assistant', 'content': [
                       {'type': 'refusal', 'refusal': 'no'}]}]),
                   response({}, output=[{'type': 'message', 'role': 'assistant', 'content': [
                       {'type': 'output_text', 'text': None}]}]), response({}, error={'code': 'failed'})]
        for reply in invalid:
            with self.subTest(reply=reply), patch.object(Client, '_request', return_value=reply):
                with self.assertRaises(ValueError):
                    Client(self.config()).test_connection()

    def test_renpy_names_context_and_instructions_preserved_through_responses(self):
        source = 'label palace:\n    "Lucy" "Reach Jade Palace with Lucy, {player}."\n    bob "Be careful."\n'
        entries, _ = renpy.extract(source, 'en/story.rpy')
        project = Project('.', entries=entries, protected_names=['Jade Palace'], game_context='An adventure quest', instructions='Use friendly speech.')
        self.assertIn('Lucy', inferred_names(project))
        captured = []
        def request(client, url, payload, stop):
            self.assertTrue(url.endswith('/responses'))
            captured.append(payload)
            items = json.loads(payload['input'][-1]['content'])['items']
            return response({'translations': [{'id': item['id'], 'text': item['text'].replace('Reach', 'Đến').replace('with', 'cùng')} for item in items]})
        with patch.object(Client, '_request', request):
            self.assertEqual(translate(project, self.config()), 2)
        self.assertEqual(project.entries[0].translation, 'Đến Jade Palace cùng Lucy, {player}.')
        payload = captured[0]
        self.assertIn('An adventure quest', payload['instructions'])
        self.assertIn('Use friendly speech.', payload['instructions'])
        first = json.loads(payload['input'][-1]['content'])['items'][0]
        self.assertNotIn('Jade Palace', first['text'])
        self.assertNotIn('Lucy', first['text'])
        self.assertEqual(first['previous_or_next'], ['Be careful.'])

    def test_lost_name_tokens_do_not_replace_existing_translation(self):
        project = Project('.', entries=extract('"Reach Jade Palace"', 'json', 'en.json'), protected_names=['Jade Palace'])
        project.entries[0].translation = 'Đến Jade Palace'
        row = {'id': project.entries[0].id, 'text': 'Đến cung điện'}
        with patch.object(Client, '_request', return_value=response({'translations': [row]})):
            self.assertEqual(translate(project, self.config(), overwrite=True), 0)
        self.assertEqual(project.entries[0].translation, 'Đến Jade Palace')
        self.assertTrue(project.entries[0].error)

    def test_missing_ids_block_checkpoint(self):
        project = Project('.', entries=extract('["Start game", "Quit game"]', 'json', 'en.json'))
        with patch.object(Client, '_request', return_value=response({'translations': []})), patch('builtins.print') as save:
            with self.assertRaisesRegex(ValueError, 'ID'):
                translate(project, self.config(), save=save)
        save.assert_not_called()
        self.assertFalse(any(entry.translation for entry in project.entries))

    def test_larger_batches_reduce_requests_without_losing_entries(self):
        counts = []
        def request(client, url, payload, stop):
            items = json.loads(payload['input'][-1]['content'])['items']
            return response({'translations': [{'id': item['id'], 'text': 'Bắt đầu chơi'} for item in items]})
        source = json.dumps([f'Start game number {index}' for index in range(80)])
        for size in (20, 40):
            project = Project('.', entries=extract(source, 'json', 'en.json'))
            with patch.object(Client, '_request', autospec=True, side_effect=request) as called:
                self.assertEqual(translate(project, replace(self.config(), batch_size=size)), 80)
            counts.append(called.call_count)
        self.assertEqual(counts, [4, 2])

    def test_neighbors_cross_speakers_inside_label_only(self):
        entries, _ = renpy.extract('label first:\n    e "Hello."\n    b "Welcome."\nlabel second:\n    e "Other scene."\n', 'en/story.rpy')
        neighbors = context_map(Project('.', entries=entries))
        self.assertEqual(neighbors[entries[0].id]['previous_or_next'], ['Welcome.'])
        self.assertEqual(neighbors[entries[2].id]['previous_or_next'], [])
