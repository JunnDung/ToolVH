import json
import threading
import unittest
from unittest.mock import patch
from toolvh.translation import Client, APIConfig, translate
from toolvh.model import Project
from toolvh.formats import extract


class OllamaTest(unittest.TestCase):
    def client(self):
        return Client(APIConfig(provider='ollama', base_url='http://localhost:11434', model='qwen3:4b'))

    def messages(self):
        return [{'role':'system','content':'Translate into Vietnamese, return translations JSON'},
                {'role':'user','content':json.dumps({'items':[{'id':'long-original-id','text':'Start game','context':'Menu'}]})}]

    def reply(self, rows=None, **extra):
        return dict(message={'content':json.dumps({'translations':rows if rows is not None else [{'id':'0','text':'Bắt đầu chơi'}]})}, done=True, **extra)

    def test_native_schema_short_ids_remap_without_mutating_input(self):
        messages=self.messages(); before=json.dumps(messages)
        with patch.object(Client,'_request',return_value=self.reply()) as request:
            result=self.client().complete(messages,threading.Event())
        self.assertEqual(result['translations'][0]['id'],'long-original-id')
        url,payload,_=request.call_args.args
        self.assertTrue(url.endswith('/api/chat'))
        self.assertFalse(payload['think'])
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['options']['num_ctx'],8192)
        self.assertEqual(payload['format']['properties']['translations']['items']['properties']['id']['enum'],['0'])
        self.assertEqual(json.dumps(messages),before)

    def test_bad_ids_missing_rows_and_bad_structure_are_rejected(self):
        for rows in ([{'id':'foreign','text':'Chơi'}],[],[{'id':'0','text':'Chơi'},{'id':'0','text':'Chơi'}]):
            with self.subTest(rows=rows), patch.object(Client,'_request',return_value=self.reply(rows)):
                with self.assertRaises(ValueError): self.client().complete(self.messages(),threading.Event())

    def test_truncated_output_is_not_accepted(self):
        with patch.object(Client,'_request',return_value=self.reply(done_reason='length')):
            with self.assertRaisesRegex(ValueError,'bị cắt'):self.client().complete(self.messages(),threading.Event())

    def test_connection_uses_same_native_contract(self):
        with patch.object(Client,'_request',return_value=self.reply()):
            self.assertEqual(self.client().test_connection(),'Bắt đầu chơi')

    def test_twenty_sentence_setting_is_split_and_checkpointed(self):
        p=Project('.',entries=extract(json.dumps({str(i):'Start game '+str(i) for i in range(12)}),'json','en.json'))
        sizes=[]; saves=[]
        def complete(client,messages,stop):
            rows=json.loads(messages[-1]['content'])['items'];sizes.append(len(rows))
            return {'translations':[{'id':r['id'],'text':'Bắt đầu '+r['text']} for r in rows]}
        with patch.object(Client,'complete',complete):
            count=translate(p,APIConfig(provider='ollama',base_url='http://localhost:11434',model='test',batch_size=20,delay_seconds=0),save=lambda:saves.append(1))
        self.assertEqual(count,12);self.assertEqual(sizes,[5,5,2]);self.assertEqual(len(saves),3)
