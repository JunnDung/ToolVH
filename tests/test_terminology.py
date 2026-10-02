import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from toolvh.model import Project, Entry
from toolvh.translation import mask, unmask, translate, Client, APIConfig
from toolvh.terminology import term_policy, inferred_names, validate_entry, audit, context_map
from toolvh.scanner import carry_translations
from toolvh.patching import export_patch, import_csv

def entry(text, context="Quest / English / message 1", id="e1", **locator):
    return Entry(id, "resources.assets", {"type": "MoonTranslatedMessageProvider", "object": 1, **locator}, text, context)

class TerminologyTests(unittest.TestCase):
    def test_longest_names_do_not_steal_locations_or_substrings(self):
        p=Project(".", entries=[entry("Reach the Wellspring Glades with Ori and Oriana")])
        m,prefix,values=mask(p.entries[0].source,term_policy(p))
        self.assertEqual(values,["Wellspring Glades","Ori"])
        self.assertIn("Oriana",m)
        self.assertEqual(unmask(m.replace("Reach the", "Đến"),prefix,values), "Đến Wellspring Glades with Ori and Oriana")

    def test_names_tags_casing_and_repeated_names(self):
        text='<b>HOWL</b> meets Howl {0}'
        m,prefix,values=mask(text,{"Howl":"Howl"})
        target=unmask(m.replace('meets','gặp'),prefix,values)
        p=Project('.',entries=[entry(text)])
        self.assertEqual(target,'<b>HOWL</b> gặp Howl {0}')
        self.assertEqual(validate_entry(p,p.entries[0],target),[])
        with self.assertRaises(ValueError):unmask(m.replace(prefix+'1__',''),prefix,values)

    def test_glossary_overrides_preservation_including_case(self):
        p=Project('.',entries=[entry('New Spirit Shard!')],glossary={'spirit shard':'Mảnh linh hồn'})
        m,prefix,values=mask(p.entries[0].source,term_policy(p))
        self.assertEqual(unmask(m.replace('New','Nhận được').replace('!',' mới!'),prefix,values),'Nhận được Mảnh linh hồn mới!')
        self.assertEqual(validate_entry(p,p.entries[0],'Nhận được Mảnh linh hồn mới!'),[])
        self.assertTrue(validate_entry(p,p.entries[0],'Đá tinh thần mới!'))

    def test_conservative_inference_does_not_lock_achievement_or_prose(self):
        p=Project('.',entries=[Entry('a','en.json',{},'Shardless','C13_BeatGameWithoutEquippingShard_Name'),
            Entry('b','en.json',{},'Silver Valley','Location_Name / en'),
            Entry('c','en.json',{},'Open The Gate','Mission_Name'),
            Entry('d','en.json',{},'Use This Weapon','Weapon_Name_Description')])
        names=inferred_names(p)
        self.assertIn('Silver Valley',names)
        for text in ('Shardless','Open The Gate','Use This Weapon'):self.assertNotIn(text,names)

    def test_standalone_name_is_local_without_client(self):
        p=Project('.',entries=[entry('Horn Beetle')])
        with patch('toolvh.translation.Client',side_effect=AssertionError('network')):
            self.assertEqual(translate(p,APIConfig()),1)
        self.assertEqual(p.entries[0].translation,'Horn Beetle')

    def test_all_providers_receive_masked_names_and_context(self):
        for provider,url in [('ollama','http://localhost:11434'),('google-web','https://translate.googleapis.com'),('openai-compatible','https://example.org/v1'),('gemini','https://generativelanguage.googleapis.com/v1beta')]:
            p=Project('.',entries=[entry('Defeat the Horn Beetle')],game_context='Combat quest')
            def complete(client,messages,stop):
                item=json.loads(messages[-1]['content'])['items'][0]
                self.assertNotIn('Horn Beetle',item['text'])
                self.assertIn('Combat quest',messages[0]['content'])
                self.assertNotIn('Tên địa điểm có từ thông thường phải dịch nghĩa',messages[0]['content'])
                return {'translations':[{'id':item['id'],'text':item['text'].replace('Defeat the','Đánh bại')}]}
            with self.subTest(provider=provider),patch.object(Client,'complete',complete):
                translate(p,APIConfig(provider=provider,base_url=url,model='test',api_key='' if provider in ('ollama','google-web') else 'test',delay_seconds=0))
            self.assertEqual(p.entries[0].translation,'Đánh bại Horn Beetle')

    def test_google_web_does_not_send_names(self):
        client=Client(APIConfig(provider='google-web',base_url='https://translate.googleapis.com',delay_seconds=0))
        text,prefix,values=mask('Defeat the Willow Stone',{'Willow Stone':'Willow Stone'})
        with patch.object(Client,'_request',return_value=[[['Đánh bại','Defeat the',None,None]]]) as request:
            target=unmask(client.google_web_text(text,__import__('threading').Event()),prefix,values)
        self.assertEqual(target,'Đánh bại Willow Stone')
        self.assertNotIn('Willow',str(request.call_args))

    def test_failed_retranslation_retains_old_value(self):
        p=Project('.',entries=[entry('Defeat the Horn Beetle')])
        p.entries[0].translation='Bản dịch cũ'
        with patch.object(Client,'complete',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):translate(p,APIConfig(provider='ollama',base_url='http://localhost:11434',model='test'),overwrite=True)
        self.assertEqual(p.entries[0].translation,'Bản dịch cũ')
        with patch.object(Client,'complete',return_value={'translations':[{'id':'e1','text':'Đánh bại con bọ'}]}):
            self.assertEqual(translate(p,APIConfig(provider='ollama',base_url='http://localhost:11434',model='test'),overwrite=True),0)
        self.assertEqual(p.entries[0].translation,'Bản dịch cũ')
        self.assertTrue(p.entries[0].error)

    def test_old_bad_names_not_reused_and_audit_keeps_text(self):
        old=entry('Defeat the Willow Stone',id='old');old.translation='Thắng bại đá cây'
        new=entry(old.source,id='new')
        p=Project('.',entries=[old,new])
        self.assertEqual(audit(p),1)
        self.assertEqual(old.translation,'Thắng bại đá cây')
        def complete(client,messages,stop):
            item=json.loads(messages[-1]['content'])['items'][0]
            return {'translations':[{'id':item['id'],'text':item['text'].replace('Defeat the','Đánh bại')}]}
        with patch.object(Client,'complete',complete):translate(p,APIConfig(provider='ollama',base_url='http://localhost:11434',model='test'))
        self.assertEqual(new.translation,'Đánh bại Willow Stone')

    def test_context_neighbors_stay_inside_provider(self):
        entries=[entry('First',id='a'),entry('Second',context='Quest / English / message 2',id='b'),entry('Other',id='c',object=2)]
        contexts=context_map(Project('.',entries=entries))
        self.assertEqual(contexts['a']['previous_or_next'],['Second'])
        self.assertEqual(contexts['c']['previous_or_next'],[])

    def test_policy_roundtrip_rescan_and_switch_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Project(tmp,preserve_names=False,protected_names=['Jade Palace'],game_context='RPG')
            path=Path(tmp)/'p.json';p.save(path);loaded=Project.load(path)
            self.assertEqual(loaded.protected_names,['Jade Palace'])
            current=Project(tmp);carry_translations(loaded,current)
            self.assertFalse(current.preserve_names);self.assertEqual(current.game_context,'RPG')
            other=Project(tmp+'/other');carry_translations(loaded,other)
            self.assertTrue(other.preserve_names);self.assertEqual(other.protected_names,[])
            data=json.loads(path.read_text(encoding="utf8"));[data.pop(k) for k in ('preserve_names','protected_names','game_context')]
            path.write_text(json.dumps(data),encoding="utf8");self.assertTrue(Project.load(path).preserve_names)

    def test_export_and_import_block_names_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'game';root.mkdir()
            p=Project(str(root),entries=[entry('Defeat the Willow Stone')]);p.entries[0].translation='Đánh bại đá'
            with self.assertRaisesRegex(ValueError,'Willow Stone'):export_patch(p,Path(tmp)/'patch')
            self.assertFalse((Path(tmp)/'patch').exists())
            csv=Path(tmp)/'t.csv';csv.write_text('id,source,translation,enabled\ne1,Defeat the Willow Stone,Đánh bại đá,1\n',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'Willow Stone'):import_csv(p,csv)
            self.assertEqual(p.entries[0].translation,'Đánh bại đá')
