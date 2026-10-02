import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from toolvh.bitmap_bindings import (STYLE_HASH, LANGUAGE_HASH, binding_script,
                                   parse_language_style, parse_style_fonts, english_font_usage)
from toolvh.fonts import font_coverage
from toolvh.bitmap_fonts import TEXT_FONTS, parse_bitmap, encode_bitmap, extend_atlas
from tests.test_fonts import fixture

def text(value):
    b=value.encode('utf8');return struct.pack('<i',len(b))+b+b'\0'*(-len(b)%4)

def header(name,sid):return bytes(16)+struct.pack('<iq',1,sid)+text(name)

def styles(font=777):
    rows=b''
    for name,code in [('normal',font),('icon',888),('blue',0)]:
        rows+=text(name)+bytes([255]*4)+struct.pack('<iqiqffifiiii',0,code,0,0,0,1,1,1,1,1,1,1)
    return header('menuStyles',100)+struct.pack('<i',3)+rows

def languages():return header('mainMenuLanguageStyle',200)+struct.pack('<iq',0,123)+bytes(244)

def script(kind,namespace,h):
    return {'m_AssemblyName':'__mainWisp.dll','m_Namespace':namespace,'m_ClassName':kind,
            'm_PropertiesHash':{f'bytes[{i}]':b for i,b in enumerate(h)}}

class BindingsTests(unittest.TestCase):
    def test_trace_english_menu_to_font_even_with_unexpected_name(self):
        objects=[SimpleNamespace(type=SimpleNamespace(name='MonoBehaviour'),path_id=123,get_raw_data=styles),
                 SimpleNamespace(type=SimpleNamespace(name='MonoBehaviour'),path_id=456,get_raw_data=languages)]
        registry={100:script('TextStyleCollection','CatlikeCoding.TextBox',STYLE_HASH),
                  200:script('MessageBoxLanguageStyles','',LANGUAGE_HASH)}
        with patch('toolvh.unity.script_reference',side_effect=lambda o,t,f:t['m_Script']['m_PathID']):
            usage=english_font_usage(SimpleNamespace(objects=objects),'resources.assets',registry)
        self.assertEqual(usage[777],['mainMenuLanguageStyle / menuStyles / normal'])
        self.assertIn(888,usage);self.assertNotIn(0,usage)
        self.assertIn('sakkalMajalla',TEXT_FONTS)

    def test_reject_unknown_binding_schema_and_truncation(self):
        tree=script('TextStyleCollection','CatlikeCoding.TextBox',STYLE_HASH)
        self.assertEqual(binding_script(tree),'styles')
        tree['m_PropertiesHash']['bytes[0]']^=1;self.assertIsNone(binding_script(tree))
        for raw in (styles()[:-1],styles()+b'new field',styles()[:35]):
            with self.assertRaises(ValueError):parse_style_fonts(raw)
        for raw in (languages()[:-4],languages()+b'new!'):
            with self.assertRaises(ValueError):parse_language_style(raw)
        self.assertEqual(parse_language_style(languages())[1],(0,123))

    def test_bitmap_uses_fallback_for_non_latin_names(self):
        from pathlib import Path
        source=Path('C:/Windows/Fonts/msjh.ttc')
        if not source.exists():self.skipTest('Windows CJK font collection unavailable')
        self.assertIn(ord('蜘'),font_coverage(source))
        parsed,atlas,primary=fixture()
        with self.assertRaisesRegex(ValueError,'thiếu ký tự'):
            extend_atlas(parsed,atlas,primary,{ord('ữ'),ord('蜘')})
        updated,_,count=extend_atlas(parsed,atlas,primary,{ord('ữ'),ord('蜘')},[source])
        self.assertEqual(count,2)
        self.assertEqual({r['id'] for r in updated['other']},{ord('ữ'),ord('蜘')})

    def test_sakkal_glyphs_resolve_like_game_binary_search(self):
        parsed,atlas,source=fixture();parsed['name']='sakkalMajalla'
        parsed['header']=header('sakkalMajalla',3608)
        needed=set(map(ord,'ặữịộơưỂẮ'))
        updated,_,count=extend_atlas(parsed,atlas,source,needed)
        decoded=parse_bitmap(encode_bitmap(updated,[]));self.assertEqual(count,len(needed))
        rows=decoded['other']
        # Match the shipped get_Item search; existence in a set alone is insufficient.
        for code in needed:
            lo,hi=0,len(rows)-1;found=None
            while lo<=hi:
                mid=(lo+hi)//2;value=rows[mid]['id']
                if value==code:found=rows[mid];break
                if value<code:lo=mid+1
                else:hi=mid-1
            self.assertIsNotNone(found);self.assertGreater(found['metrics'][6],0)

if __name__=='__main__':unittest.main()
