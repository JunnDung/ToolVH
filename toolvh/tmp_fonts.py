"""Bounded TextMeshPro static SDF atlas extension; no shader/material replacement."""
import copy
from PIL import Image, ImageDraw, ImageFont
from .bitmap_fonts import AtlasPacker, signed_distance


def coverage(tree):
    return {row['m_Unicode'] for row in tree.get('m_CharacterTable', [])}


def support(tree):
    if tree.get('m_AtlasPopulationMode') != 0:
        return 'TMP dynamic cần kiểm tra nguồn font và fallback riêng.'
    if tree.get('m_AtlasRenderMode', 0) & 0x300 or not tree.get('m_AtlasRenderMode', 0) & (0x20 | 0x40):
        return 'TMP bitmap/color chưa hỗ trợ; cần atlas SDF.'
    if len(tree.get('m_AtlasTextures', [])) != 1:
        return 'TMP multi-atlas chưa hỗ trợ.'
    if not isinstance(tree.get('m_GlyphTable'), list) or not isinstance(tree.get('m_CharacterTable'), list):
        return 'TMP thiếu bảng glyph/character hoặc type tree.'
    if not 1 <= tree.get('m_AtlasPadding', 0) <= 16:
        return 'TMP padding ngoài giới hạn hỗ trợ.'
    glyphs = tree['m_GlyphTable']
    indices = [g.get('m_Index') for g in glyphs]
    codes = [c.get('m_Unicode') for c in tree['m_CharacterTable']]
    if any(type(i) is not int or i < 0 for i in indices) or any(type(c) is not int or not 0 <= c <= 0x10ffff for c in codes):
        return 'TMP glyph index/Unicode không hợp lệ.'
    if len(set(indices)) != len(indices) or len(set(codes)) != len(codes):
        return 'TMP có glyph hoặc character trùng.'
    for g in glyphs:
        if g.get('m_AtlasIndex') != 0 or not isinstance(g.get('m_GlyphRect'), dict) or not isinstance(g.get('m_Metrics'), dict):
            return 'TMP schema glyph chưa hỗ trợ.'
    if any(c.get('m_GlyphIndex') not in indices for c in tree['m_CharacterTable']):
        return 'TMP character trỏ tới glyph không tồn tại.'
    return ''


def extend(tree, image, font_path, required):
    reason = support(tree)
    if reason:
        raise ValueError(reason)
    from .fonts import font_coverage
    missing = sorted(set(required) - coverage(tree))
    if not missing:
        return tree, image, 0
    if any(c > 65535 or c < 32 for c in missing) or set(missing) - font_coverage(font_path):
        raise ValueError('Font nguồn thiếu glyph hoặc có ký tự TMP chưa hỗ trợ.')
    width, height = image.size
    if (width, height) != (tree['m_AtlasWidth'], tree['m_AtlasHeight']):
        raise ValueError('TMP kích thước atlas không khớp.')
    glyphs = {g['m_Index']: g for g in tree['m_GlyphTable']}
    hchar = next((c for c in tree['m_CharacterTable'] if c['m_Unicode'] == 72), None)
    if hchar is None:
        raise ValueError('TMP thiếu H để cân kích thước chữ.')
    desired = glyphs[hchar['m_GlyphIndex']]['m_Metrics']['m_Height']
    if desired <= 0:
        raise ValueError('TMP cap-height không hợp lệ.')
    probe = ImageFont.truetype(str(font_path), 100)
    box = probe.getbbox('H', anchor='ls')
    font = ImageFont.truetype(str(font_path), max(1, round(100 * desired / (box[3] - box[1]))))
    pad = tree['m_AtlasPadding']
    rects = []
    for g in glyphs.values():
        r = g['m_GlyphRect']
        x, y, w, h = (r[k] for k in ('m_X', 'm_Y', 'm_Width', 'm_Height'))
        if min(x, y, w, h) < 0 or x + w > width or y + h > height:
            raise ValueError('TMP glyph rect vượt atlas.')
        if w and h:
            rects.append((max(0, x - pad), max(0, height - y - h - pad), w + pad * 2, h + pad * 2))
    packer = AtlasPacker(image.size, rects)
    updated, output = copy.deepcopy(tree), image.copy()
    index = max(glyphs, default=0) + 1
    for code in missing:
        left, top, right, bottom = font.getbbox(chr(code), anchor='ls')
        w, h = right - left, bottom - top
        if w <= 0 or h <= 0:
            raise ValueError('TMP glyph nguồn rỗng.')
        mask = Image.new('L', (w + 2 * pad, h + 2 * pad))
        ImageDraw.Draw(mask).text((pad - left, pad - top), chr(code), font=font, fill=255, anchor='ls')
        sdf = signed_distance(mask, pad + 1)
        x, y = packer.place(*sdf.size)
        patch = Image.new('RGBA', sdf.size, (255, 255, 255, 0)); patch.putalpha(sdf)
        output.paste(patch, (x, y))
        rect = dict(m_X=x + pad, m_Y=height - y - pad - h, m_Width=w, m_Height=h)
        updated['m_GlyphTable'].append(dict(m_Index=index, m_Metrics=dict(m_Width=w, m_Height=h,
            m_HorizontalBearingX=left, m_HorizontalBearingY=-top, m_HorizontalAdvance=font.getlength(chr(code))),
            m_GlyphRect=rect, m_Scale=1.0, m_AtlasIndex=0))
        updated['m_CharacterTable'].append(dict(m_ElementType=1, m_Unicode=code, m_GlyphIndex=index, m_Scale=1.0))
        index += 1
    return updated, output, len(missing)
