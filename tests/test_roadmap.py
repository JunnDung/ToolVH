import copy
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from toolvh import pak, renpy, rpgmaker, tmp_fonts
from toolvh.fonts import suggested_font
from toolvh.scanner import scan
from toolvh.patching import preflight, export_patch, install_patch
from toolvh.translation import mask,unmask,validate
from synthetic_addressables import make_fixture
from test_engines import locres
from toolvh.unreal import fstring,read_locres


def make_pak(version=3):
    output=bytearray();rows=[]
    for name,raw in [('Game/Content/Localization/UI/en/UI.locres',locres(3)),('Game/Content/image.bin',b'unchanged binary')]:
        offset=len(output)
        header=struct.pack('<qqqI',0,len(raw),len(raw),0)+(bytes(8) if version==1 else b'')+hashlib.sha1(raw).digest()
        if version>=3:header+=struct.pack('<BI',0,0)
        output.extend(header+raw)
        header=bytearray(header);struct.pack_into('<q',header,0,offset)
        rows.append(fstring(name)+header)
    index=fstring('../../../')+struct.pack('<i',len(rows))+b''.join(rows)
    offset=len(output);output.extend(index)
    footer=(bytes(16) if version>=7 else b'')+(b'\0' if version>=4 else b'')
    footer+=struct.pack('<Iiqq',pak.MAGIC,version,offset,len(index))+hashlib.sha1(index).digest()
    return bytes(output+footer)


class RoadmapTests(unittest.TestCase):
    def test_preflight_rejects_changed_files_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'en.json';file.write_text('{"text":"Start game"}')
            p=scan(root);original=file.read_bytes()
            report=preflight(p);self.assertEqual(report['selected_entries'],1)
            self.assertEqual(file.read_bytes(),original)
            file.write_text('{"text":"Changed source"}')
            with self.assertRaisesRegex(ValueError,'thay đổi'):preflight(p)
            p.applied_patch='somewhere'
            with self.assertRaisesRegex(ValueError,'bản vá'):preflight(p)

    def test_preflight_rejects_unknown_addressables_before_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);patch,relative,original,*_=make_fixture(root/'fixture')
            game=root/'game';target=game/relative;target.parent.mkdir(parents=True);target.write_bytes(original)
            # Unsupported catalog, using selected fixture with a writer intercepted below.
            from toolvh.model import Project,FileRecord,Entry,digest
            from unittest.mock import patch as mock
            settings=target.parent.parent/'settings.json'
            settings.write_text(json.dumps({'m_CatalogLocations':[{'m_InternalId':'https://example.com/catalog.bin'}]}))
            p=Project(str(game),files=[FileRecord(relative,'unity',digest(original))],entries=[Entry('x',relative,{},'Start game','')])
            with mock('toolvh.patching.rebuild_unity',return_value=original):
                with self.assertRaisesRegex(ValueError,'remote'):preflight(p)
            self.assertEqual(target.read_bytes(),original)

    def test_pak_versions_locres_edit_preserves_binary_payload(self):
        for version in range(1,8):
            with self.subTest(version=version):
                original=make_pak(version);entries,_=pak.extract(original,'content.pak')
                self.assertTrue(entries and entries[0].enabled)
                entries[0].translation='Bắt đầu chơi'
                changed=pak.rebuild(original,entries[:1])
                v,offset,_,rows,_=pak.read(changed)
                strings=read_locres(pak.payload(changed,rows[0],v,offset))[3]
                self.assertEqual(strings[0]['value'],'Bắt đầu chơi')
                self.assertEqual(pak.payload(changed,rows[1],v,offset),b'unchanged binary')
                self.assertEqual(original[:rows[1]['offset']],changed[:rows[1]['offset']])

    def test_pak_corruption_encryption_and_paths_rejected(self):
        raw=bytearray(make_pak(4));raw[-45]=1
        with self.assertRaisesRegex(ValueError,'mã hóa'):pak.read(bytes(raw))
        raw=bytearray(make_pak());raw[-1]^=1
        with self.assertRaisesRegex(ValueError,'SHA1'):pak.read(bytes(raw))
        raw=bytearray(make_pak());raw[60]^=1
        entries,note=pak.extract(bytes(raw),'a.pak')
        self.assertEqual(entries,[]);self.assertIn('SHA1',note)
        with self.assertRaisesRegex(ValueError,'v1'):pak.read(b'not Unreal')

    def test_pak_scan_install_restore_and_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'game';root.mkdir();target=root/'content.pak';original=make_pak();target.write_bytes(original)
            p=scan(root,deep=True);self.assertTrue(p.entries)
            preflight(p)
            p.entries[0].translation='Bắt đầu chơi'
            export_patch(p,Path(directory)/'patch')
            self.assertEqual(install_patch(Path(directory)/'patch',root),1)
            self.assertEqual(install_patch(Path(directory)/'patch',root,restore=True),1)
            self.assertEqual(target.read_bytes(),original)
            target.with_suffix('.sig').write_bytes(b'signed')
            with self.assertRaisesRegex(ValueError,'chữ ký'):preflight(p)
            with self.assertRaisesRegex(ValueError,'chữ ký'):install_patch(Path(directory)/'patch',root)
            self.assertEqual(target.read_bytes(),original)
            self.assertEqual(scan(root,deep=True).entries,[])

    def test_rpg_event_commands_and_database_names(self):
        data={'displayName':'Lost Forest','note':'DO NOT TRANSLATE','events':[{'pages':[{'list':[
            {'code':401,'indent':0,'parameters':['Hello \\N[1]!']},
            {'code':102,'indent':0,'parameters':[['Go west','Go east'],0]},
            {'code':355,'indent':0,'parameters':['dangerousScript("English")']},
            {'code':356,'indent':0,'parameters':['PluginCommand English']}]}]}]}
        source=json.dumps(data);entries,_=rpgmaker.extract(source,'data/Map001.json')
        self.assertEqual(len(entries),4);self.assertFalse(any(e.enabled for e in entries))
        entry=next(e for e in entries if e.source.startswith('Hello'));entry.translation='Xin chào \\N[1]!'
        changed=json.loads(rpgmaker.rebuild(source,[entry]));expected=copy.deepcopy(data)
        expected['events'][0]['pages'][0]['list'][0]['parameters'][0]=entry.translation
        self.assertEqual(changed,expected)
        names,_=rpgmaker.extract('[null,{"id":1,"name":"Moon Blade","description":"A sharp blade","note":"meta"}]','data/Weapons.json')
        from toolvh.terminology import inferred_names
        from toolvh.model import Project
        self.assertIn('Moon Blade',inferred_names(Project('.',entries=names)))

    def test_rpg_tokens_preserve_format_parameters_and_currency(self):
        source=r'%1 attacks %2! \G \N[1]'
        text,prefix,values=mask(source)
        self.assertEqual(unmask(text,prefix,values),source)
        self.assertNotIn('%1',text);self.assertNotIn(r'\G',text)
        self.assertTrue(validate(source,r'%1 tấn công! \G \N[1]'))

    def test_rpg_scan_roundtrip_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'game';(root/'js').mkdir(parents=True);(root/'js/rmmz_core.js').write_text('// fixture')
            (root/'data').mkdir();target=root/'data/Items.json';original=b'[null,{"id":1,"name":"Moon Blade","description":"A sharp blade","note":"meta"}]';target.write_bytes(original)
            p=scan(root);self.assertEqual(p.files[-1].kind,'rpgmaker')
            entry=next(e for e in p.entries if e.source=='A sharp blade');entry.enabled=True;entry.translation='Một lưỡi kiếm sắc'
            preflight(p);export_patch(p,Path(directory)/'patch');install_patch(Path(directory)/'patch',root)
            self.assertEqual(json.loads(target.read_bytes())[1]['note'],'meta')
            install_patch(Path(directory)/'patch',root,restore=True);self.assertEqual(target.read_bytes(),original)

    def test_renpy_dialogue_menu_templates_and_python_exclusion(self):
        source='label start:\n    e "Hello [player!t]!"\n    menu:\n        "Go west":\n            jump west\n    play music "audio.ogg"\n    python:\n        e "Not dialogue"\n        value = "Do not translate"\n    "Goodbye"\n'
        source+='screen image_ui:\n    imagebutton:\n        idle \"images/title.png\"\ninit:\n    e \"Not story text\"\n'
        entries,_=renpy.extract(source,'game/script.rpy')
        self.assertEqual([e.source for e in entries],['Hello [player!t]!','Go west','Goodbye'])
        entries[0].translation='Xin chào [player!t]!'
        changed=renpy.rebuild(source,entries[:1]);self.assertIn('e "Xin chào [player!t]!"',changed)
        self.assertIn('play music "audio.ogg"',changed);self.assertIn('value = "Do not translate"',changed)
        template='translate english strings:\n    old "Start game"\n    new ""\n'
        entries,_=renpy.extract(template,'game/tl/en/strings.rpy');self.assertTrue(entries[0].enabled)
        entries[0].translation='Bắt đầu chơi';changed=renpy.rebuild(template,entries)
        self.assertIn('old "Start game"',changed);self.assertIn('new "Bắt đầu chơi"',changed)
        self.assertEqual(renpy.extract(template,'game/tl/fr/strings.rpy')[0],[])
        masked,prefix,values=mask('Hello [player!t]!');self.assertEqual(unmask(masked,prefix,values),'Hello [player!t]!')
        self.assertTrue(validate('Hello [player!t]!','Xin chào [player]!'))

    def test_renpy_scan_apply_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'game';root.mkdir();target=root/'script.rpy';original=b'label start:\n    e "Hello player!"\n';target.write_bytes(original)
            p=scan(root);self.assertEqual(len(p.entries),1);p.entries[0].enabled=True;p.entries[0].translation='Xin chào!'
            preflight(p);export_patch(p,Path(directory)/'patch');install_patch(Path(directory)/'patch',root)
            self.assertIn('Xin chào!',target.read_text(encoding='utf-8'))
            install_patch(Path(directory)/'patch',root,restore=True);self.assertEqual(target.read_bytes(),original)

    def test_tmp_extension_preserves_metrics_kerning_and_old_pixels(self):
        tree={'m_AtlasPopulationMode':0,'m_AtlasRenderMode':0x1045,'m_AtlasPadding':4,'m_AtlasTextures':[{'m_FileID':0,'m_PathID':1}],
              'm_AtlasWidth':512,'m_AtlasHeight':512,'m_FontFeatureTable':{'kerning':'unchanged'},
              'm_GlyphTable':[{'m_Index':3,'m_AtlasIndex':0,'m_Scale':1.,'m_GlyphRect':{'m_X':20,'m_Y':20,'m_Width':20,'m_Height':25},
                  'm_Metrics':{'m_Width':20,'m_Height':25,'m_HorizontalBearingX':0,'m_HorizontalBearingY':25,'m_HorizontalAdvance':20}}],
              'm_CharacterTable':[{'m_ElementType':1,'m_Unicode':72,'m_GlyphIndex':3,'m_Scale':1.}]}
        original=copy.deepcopy(tree);image=Image.new('RGBA',(512,512),(0,0,0,0))
        image.paste((255,255,255,255),(16,463,44,496))
        updated,out,count=tmp_fonts.extend(tree,image,suggested_font('candara'),{72,ord('Đ'),ord('ữ')})
        self.assertEqual(count,2);self.assertEqual(tree,original)
        self.assertEqual(updated['m_GlyphTable'][0],tree['m_GlyphTable'][0])
        self.assertEqual(updated['m_CharacterTable'][0],tree['m_CharacterTable'][0])
        self.assertEqual(updated['m_FontFeatureTable'],tree['m_FontFeatureTable'])
        self.assertEqual(image.crop((16,463,44,496)).tobytes(),out.crop((16,463,44,496)).tobytes())
        self.assertEqual(tmp_fonts.coverage(updated),{72,ord('Đ'),ord('ữ')})
        for change in ({'m_AtlasPopulationMode':1},{'m_AtlasTextures':[]},{'m_AtlasPadding':0}):
            with self.assertRaises(ValueError):tmp_fonts.extend(dict(tree,**change),image,suggested_font('candara'),{ord('Đ')})


class GodotBinaryTests(unittest.TestCase):
    def fixture(self,version=6):
        from toolvh.godot_binary import encode_string
        string=encode_string
        header=b'RSRC'+struct.pack('<5I',0,0,4,5,version)+string('Translation')+struct.pack('<QI',0,3)+struct.pack('<Q',1234)+bytes(44)
        names=['resource_name','locale','messages']
        header+=struct.pack('<I',3)+b''.join(string(n) for n in names)+struct.pack('<II',0,1)+string('local://1')
        header+=struct.pack('<Q',len(header)+8)
        resource=string('Translation')+struct.pack('<I',3)
        resource+=struct.pack('<II',0,5)+string('English fixture')
        resource+=struct.pack('<II',1,5)+string('en')
        resource+=struct.pack('<III',2,26,2)
        for key,value in [('MENU_START','Start game'),('UI_QUIT','Quit game')]:
            resource+=struct.pack('<I',5)+string(key)+struct.pack('<I',5)+string(value)
        return header+resource+b'RSRC'

    def test_translation_versions_and_preserve_uid_keys(self):
        from toolvh import godot_binary
        for version in (5,6):
            raw=self.fixture(version);entries,note=godot_binary.extract(raw,'en.translation')
            self.assertEqual(len(entries),2);self.assertTrue(all(e.enabled for e in entries))
            entries[0].translation='Bắt đầu chơi'
            output=godot_binary.rebuild(raw,entries[:1]);locale,rows=godot_binary.read(output)
            self.assertEqual(locale,'en');self.assertEqual([(k,v) for k,v,_ in rows],[('MENU_START','Bắt đầu chơi'),('UI_QUIT','Quit game')])
            self.assertEqual(output[:entries[0].locator['start']],raw[:entries[0].locator['start']])
            self.assertEqual(output[-4:],b'RSRC')

    def test_translation_inside_pck_and_install_restore(self):
        from test_engines import pack
        from toolvh.godot import extract_pack,rebuild_pack
        raw=pack(2,{'res://en.translation':self.fixture(),'res://image.bin':b'unchanged'})
        entries,_=extract_pack(raw,'game.pck');self.assertEqual(len(entries),2)
        entries[0].translation='Bắt đầu chơi'
        output=rebuild_pack(raw,entries[:1]);changed,_=extract_pack(output,'game.pck')
        self.assertEqual(changed[0].source,'Bắt đầu chơi');self.assertEqual(changed[1].source,'Quit game')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'game';root.mkdir();target=root/'game.pck';target.write_bytes(raw)
            p=scan(root,deep=True);preflight(p);p.entries[0].translation='Bắt đầu chơi'
            export_patch(p,Path(directory)/'patch');install_patch(Path(directory)/'patch',root)
            self.assertNotEqual(target.read_bytes(),raw)
            install_patch(Path(directory)/'patch',root,restore=True);self.assertEqual(target.read_bytes(),raw)

    def test_reject_compressed_unknown_class_truncated_and_wrong_offset(self):
        from toolvh import godot_binary
        with self.assertRaises(ValueError):godot_binary.read(b'RSCC'+self.fixture()[4:])
        with self.assertRaises(ValueError):godot_binary.read(self.fixture()[:-1])
        with self.assertRaises(ValueError):godot_binary.read(self.fixture().replace(b'Translation',b'Wrong_Class',1))
        raw=bytearray(self.fixture());struct.pack_into('<I',raw,4,1)
        with self.assertRaisesRegex(ValueError,'endian'):godot_binary.read(bytes(raw))


class TranslationMigrationTests(unittest.TestCase):
    def test_unique_context_reuses_shifted_locator_but_not_changed_source(self):
        from toolvh.scanner import carry_translations
        from toolvh.model import Project,Entry
        old=Project('.',entries=[Entry('old','en.json',{'path':[0]},'Start game','UI / start',translation='Bắt đầu chơi',source_locale='en')])
        new=Project('.',entries=[Entry('new','en.json',{'path':[5]},'Start game','UI / start',source_locale='en')])
        self.assertEqual(carry_translations(old,new),1);self.assertEqual(new.entries[0].translation,'Bắt đầu chơi')
        new.entries[0].source='New game';new.entries[0].translation=''
        self.assertEqual(carry_translations(old,new),0)

    def test_ambiguous_context_is_never_reused(self):
        from toolvh.scanner import carry_translations
        from toolvh.model import Project,Entry
        old=Project('.',entries=[Entry(str(i),'en.json',{'path':[i]},'Open','UI',translation=t,source_locale='en') for i,t in enumerate(('Mở','Mở cửa'))])
        new=Project('.',entries=[Entry('new','en.json',{'path':[5]},'Open','UI',source_locale='en')])
        self.assertEqual(carry_translations(old,new),0)
        self.assertEqual(new.entries[0].translation,'')
