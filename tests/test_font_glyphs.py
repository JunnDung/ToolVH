import io
import unittest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from toolvh.font_glyphs import extend_truetype


def font(characters, size=600):
    builder=FontBuilder(1000,isTTF=True)
    names={ord(c):f'uni{ord(c):04X}' for c in characters}
    order=['.notdef']+list(names.values())
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(names)
    glyphs={}
    for name in order:
        pen=TTGlyphPen(None)
        pen.moveTo((0,0));pen.lineTo((size,0));pen.lineTo((size,size));pen.lineTo((0,size));pen.closePath()
        glyphs[name]=pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({n:(size+100,20) for n in order})
    builder.setupHorizontalHeader(ascent=800,descent=-200)
    builder.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
    builder.setupNameTable({'familyName':'Original Pixel','styleName':'Regular','uniqueFontIdentifier':'Original Pixel','fullName':'Original Pixel','psName':'OriginalPixel'})
    builder.setupPost()
    stream=io.BytesIO();builder.save(stream)
    return stream.getvalue()


class FontGlyphTests(unittest.TestCase):
    def test_add_vietnamese_without_removing_korean_or_changing_original_glyph(self):
        original=font('aH한')
        result=extend_truetype(original,font('aHạ',400),set(map(ord,'aạ')))
        with TTFont(io.BytesIO(original)) as old,TTFont(io.BytesIO(result)) as new:
            self.assertEqual(set(new.getBestCmap()),set(map(ord,'aH한ạ')))
            for c,g in old.getBestCmap().items():
                self.assertEqual(new.getBestCmap()[c],g)
                self.assertEqual(new['glyf'][g].compile(new['glyf']),old['glyf'][g].compile(old['glyf']))
                self.assertEqual(new['hmtx'][g],old['hmtx'][g])
            self.assertEqual(new['hhea'].ascent,old['hhea'].ascent)
            self.assertEqual(new['hhea'].descent,old['hhea'].descent)
            self.assertEqual(new['name'].getDebugName(1),'Original Pixel')
            added=new['glyf'][new.getBestCmap()[ord('ạ')]]
            self.assertEqual(added.yMax,600)

    def test_already_supported_font_is_byte_identical(self):
        original=font('Hạ')
        self.assertEqual(extend_truetype(original,font('Ha'),{ord('ạ')}),original)

    def test_source_missing_requested_character_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'thiếu glyph'):
            extend_truetype(font('Ha'),font('Ha'),{ord('ạ')})

    def test_font_with_padded_auxiliary_table_preserves_original_raw_table(self):
        from fontTools.ttLib.tables.DefaultTable import DefaultTable
        raw=b"\x00\x01\x00\x01\x00\x08\x00\x02\x00\x00"
        def padded(data):
            with TTFont(io.BytesIO(data)) as value:
                table=DefaultTable('gasp');table.data=raw;value['gasp']=table
                stream=io.BytesIO();value.save(stream);return stream.getvalue()
        original=padded(font('Ha한'))
        result=extend_truetype(original,padded(font('Hạ')),{ord('ạ')})
        with TTFont(io.BytesIO(result)) as value:
            self.assertEqual(value.reader['gasp'],raw)
            self.assertIn(ord('ạ'),value.getBestCmap())
            self.assertIn(ord('한'),value.getBestCmap())

    def test_post_format_three_font_keeps_original_glyph_ids(self):
        original=font('Ha한')
        with TTFont(io.BytesIO(original)) as value:
            value['post'].formatType=3.0
            stream=io.BytesIO();value.save(stream);original=stream.getvalue()
        result=extend_truetype(original,font('Hạ'),{ord('ạ')})
        with TTFont(io.BytesIO(original)) as old,TTFont(io.BytesIO(result)) as new:
            for c,g in old.getBestCmap().items():
                self.assertEqual(old.getGlyphID(g),new.getGlyphID(new.getBestCmap()[c]))

    def test_pixel_font_keeps_small_cap_height_and_valid_original_units(self):
        original=font('Ha',7)
        with TTFont(io.BytesIO(original)) as value:
            value['head'].unitsPerEm=16
            stream=io.BytesIO();value.save(stream);original=stream.getvalue()
        result=extend_truetype(original,font('Hạ',600),{ord('ạ')})
        with TTFont(io.BytesIO(result)) as value:
            self.assertEqual(value['head'].unitsPerEm,16)
            self.assertEqual(value['glyf'][value.getBestCmap()[ord('ạ')]].yMax,7)

    def test_notdef_cmap_entry_does_not_count_as_supported_character(self):
        original=font('Ha')
        with TTFont(io.BytesIO(original)) as value:
            for table in value['cmap'].tables:
                if table.isUnicode():table.cmap[ord('ạ')]='.notdef'
            stream=io.BytesIO();value.save(stream);original=stream.getvalue()
        result=extend_truetype(original,font('Hạ'),{ord('ạ')})
        with TTFont(io.BytesIO(result)) as value:
            self.assertNotEqual(value.getGlyphID(value.getBestCmap()[ord('ạ')]),0)
