import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from toolvh.bitmap_fonts import parse_bitmap, encode_bitmap, extend_atlas, AtlasPacker, signed_distance, script_matches
from toolvh.fonts import (VIETNAMESE, font_coverage, diagnose, export_font_patch, apply_font_patch,
                         restore_font, suggested_font, required_characters)
from toolvh.model import Project, Entry, digest
from toolvh.patching import restore_project, export_patch
from toolvh.scanner import carry_translations

def char(code,metrics):return dict(id=code,metrics=list(metrics),raw=struct.pack('<ii9fii',code,0,*metrics,0,0))
def fixture():
    source=suggested_font('candara');font=ImageFont.truetype(str(source),30)
    atlas=Image.new('RGBA',(512,512),(0,0,0,0))
    bbox=font.getbbox('H',anchor='ls');mask=Image.new('L',(bbox[2]-bbox[0]+8,bbox[3]-bbox[1]+8))
    ImageDraw.Draw(mask).text((4-bbox[0],4-bbox[1]),'H',font=font,fill=255,anchor='ls')
    sdf=signed_distance(mask);g=Image.new('RGBA',mask.size);g.putalpha(sdf);atlas.paste(g,(0,0))
    w,h=mask.size;asc=[char(i+33,(0,0,0,0,0,0,0,0,0)) for i in range(94)]
    asc[ord('H')-33]=char(ord('H'),(0,w/512,1-h/512,1,0,1,w/40,h/40,font.getlength('H')/40))
    header=bytes(16)+struct.pack('<iqi',1,3608,7)+b'candara'+b'\0'
    parsed=dict(header=header,name='candara',file_id=1,script_id=3608,ascii=asc,other=[],line=40,
                tail=struct.pack('<4f5i',40,-.65,-.35,.2,0,0,0,0,0))
    return parsed,atlas,source

class FontTests(unittest.TestCase):
    def test_complete_vietnamese_source_coverage(self):
        self.assertTrue(VIETNAMESE<=font_coverage(suggested_font('candara')))
        self.assertTrue({ord('Đ'),ord('ữ'),ord('Ắ')}<=VIETNAMESE)
        with self.assertRaises(Exception):font_coverage(b'not a font')

    def test_bitmap_roundtrip_preserves_metadata_and_original_glyphs(self):
        parsed,atlas,source=fixture();raw=encode_bitmap(parsed,[])
        decoded=parse_bitmap(raw)
        self.assertEqual(encode_bitmap(decoded,[]),raw)
        updated,output,count=extend_atlas(decoded,atlas,source,{ord('H'),ord('Đ'),ord('ữ')})
        self.assertEqual(count,2)
        rebuilt=parse_bitmap(encode_bitmap(updated,[]))
        self.assertEqual(rebuilt['header'],decoded['header']);self.assertEqual(rebuilt['tail'],decoded['tail'])
        self.assertEqual([r['raw'] for r in rebuilt['ascii']],[r['raw'] for r in decoded['ascii']])
        old_rect=(0,0,round(decoded['ascii'][39]['metrics'][1]*512),round((1-decoded['ascii'][39]['metrics'][2])*512))
        self.assertEqual(atlas.crop(old_rect).tobytes(),output.crop(old_rect).tobytes())
        self.assertEqual(output.size,atlas.size)
        self.assertEqual([r['id'] for r in rebuilt['other']],[ord('Đ'),ord('ữ')])
        again,same,n=extend_atlas(rebuilt,output,source,{ord('H'),ord('Đ'),ord('ữ')})
        self.assertEqual(n,0);self.assertEqual(same.tobytes(),output.tobytes())

    def test_parser_rejects_unknown_truncated_and_icon_schemas(self):
        parsed,_,_=fixture();raw=encode_bitmap(parsed,[])
        for bad in (raw[:-1],raw+b'x',raw[:20]):
            with self.subTest(length=len(bad)),self.assertRaises(ValueError):parse_bitmap(bad)
        icon=bytearray(raw);struct.pack_into('<i',icon,len(parsed['header'])+8,1)
        with self.assertRaises(ValueError):parse_bitmap(bytes(icon))
        self.assertFalse(script_matches({'m_ClassName':'BitmapFont','m_AssemblyName':'other.dll'}))

    def test_full_atlas_fails_without_mutating_source(self):
        parsed,atlas,source=fixture();parsed['other']=[char(1000,(0,1,0,1,0,1,1,1,1))]
        before=atlas.tobytes()
        with self.assertRaisesRegex(ValueError,'không đủ'):extend_atlas(parsed,atlas,source,{ord('Đ')})
        self.assertEqual(atlas.tobytes(),before)
        p=AtlasPacker((16,16),[(0,0,16,16)])
        with self.assertRaises(ValueError):p.place(4,4)

    def test_sdf_inside_outside_and_atlas_no_overlap(self):
        mask=Image.new('L',(16,16));ImageDraw.Draw(mask).rectangle((5,5,10,10),fill=255)
        field=signed_distance(mask)
        self.assertGreater(field.getpixel((7,7)),128);self.assertLess(field.getpixel((0,0)),128)
        pack=AtlasPacker((64,64),[(0,0,32,32)])
        x,y=pack.place(16,16);self.assertTrue(x>=32 or y>=32)

    def test_required_chars_include_translation_and_full_vietnamese(self):
        p=Project('.',entries=[Entry('a','en.json',{},'Text','',translation='<b>Đúng</b> {0} Ω')])
        required=required_characters(p)
        self.assertIn(ord('Ω'),required);self.assertTrue(VIETNAMESE<=required)
        self.assertNotIn(ord('{'),required)

    def test_loose_font_diagnose_export_apply_restore_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'game';root.mkdir();source=suggested_font('candara');old=source.read_bytes()
            target=root/'menu.ttf';target.write_bytes(old);p=Project(str(root))
            report=diagnose(p);self.assertEqual(len(report['fonts']),1)
            self.assertTrue(report['fonts'][0]['repairable']);self.assertEqual(report['fonts'][0]['missing'],'')
            other=suggested_font('roboto')
            # This fixture uses a compatible font subset to check all existing glyph preservation.
            with patch('toolvh.fonts.font_coverage',return_value=VIETNAMESE|{65}):
                manifest=export_font_patch(p,report,report['fonts'],Path(tmp)/'fontpatch',other)
            self.assertEqual(target.read_bytes(),old)
            self.assertEqual(manifest['kind'],'font')
            snapshots=[]
            count=apply_font_patch(p,Path(tmp)/'fontpatch',save=lambda:snapshots.append(list(p.font_patches)))
            self.assertEqual(count,1);self.assertEqual(len(snapshots[0]),1)
            self.assertEqual(target.read_bytes(),other.read_bytes())
            with self.assertRaisesRegex(ValueError,'font'):restore_project(p)
            with self.assertRaisesRegex(ValueError,'font'):export_patch(p,Path(tmp)/'textpatch')
            self.assertEqual(restore_font(p),1);self.assertEqual(target.read_bytes(),old);self.assertEqual(p.font_patches,[])

    def test_stale_hash_source_missing_glyph_and_checkpoint_fail_no_game_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'game';root.mkdir();source=suggested_font('candara');target=root/'menu.ttf';target.write_bytes(source.read_bytes());p=Project(str(root))
            report=diagnose(p);target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'đổi'):export_font_patch(p,report,report['fonts'],Path(tmp)/'patch')
            self.assertFalse((Path(tmp)/'patch').exists());target.write_bytes(source.read_bytes())
            with patch('toolvh.fonts.font_coverage',return_value={65}):
                with self.assertRaisesRegex(ValueError,'không đủ'):export_font_patch(p,report,report['fonts'],Path(tmp)/'patch',source)
            target.write_bytes(b'original');modified=b'patched';directory=Path(tmp)/'manual';(directory/'files').mkdir(parents=True);(directory/'backup').mkdir()
            (directory/'files/menu.ttf').write_bytes(modified);(directory/'backup/menu.ttf').write_bytes(b'original')
            (directory/'manifest.json').write_text(json.dumps({'schema':1,'kind':'font','game_root':str(root),'files':[dict(path='menu.ttf',original_sha256=digest(b'original'),patched_sha256=digest(modified))]}))
            with self.assertRaises(OSError):apply_font_patch(p,directory,save=lambda:(_ for _ in ()).throw(OSError('disk')))
            self.assertEqual(target.read_bytes(),b'original');self.assertEqual(p.font_patches,[])

    def test_font_recovery_not_carried_to_other_game(self):
        p=Project('.',font_patches=['backup']);current=Project('.');carry_translations(p,current)
        self.assertEqual(current.font_patches,['backup'])
        other=Project('./another');carry_translations(p,other);self.assertEqual(other.font_patches,[])

class UnicodeTests(unittest.TestCase):
    def test_normalize_keeps_formatting_and_names_masked(self):
        from toolvh.translation import normalize_translation, mask, unmask
        text='Ngôn ngữ <sprite name="â"> {â}'
        self.assertEqual(normalize_translation(text),'Ngôn ngữ <sprite name="â"> {â}')
        masked,prefix,values=mask('Meet Â',{ 'Â':'Â'})
        self.assertEqual(unmask(normalize_translation(masked.replace('Meet','Gặp')),prefix,values),'Gặp Â')

    def test_bitmap_combining_marks_require_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Project(tmp,entries=[Entry('x','a.assets',{},'Language','',translation='Ngôn ngữ')])
            record=dict(file='a.assets',kind='ori-bitmap',container='__root__',object=1,repairable=True)
            report={'root':str(Path(tmp).resolve()),'fonts':[record]}
            with self.assertRaisesRegex(ValueError,'kết hợp'):export_font_patch(p,report,[record],Path(tmp).parent/'outsidefontpatch')

class RunningGameTests(unittest.TestCase):
    def test_active_game_blocks_install_before_any_patch_reads(self):
        from toolvh.patching import install_patch
        with patch('toolvh.processes.running_game_processes',return_value=[(42,'C:/game/game.exe')]):
            with self.assertRaisesRegex(ValueError,'đang chạy'):install_patch('does-not-exist','C:/game')
            with self.assertRaisesRegex(ValueError,'đang chạy'):install_patch('does-not-exist','C:/game',restore=True)
