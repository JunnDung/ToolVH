"""Add missing Unicode glyphs to TrueType fonts without replacing existing glyphs."""
import copy
import io

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.ttLib.tables.ttProgram import Program


def extend_truetype(original, donor, required):
    with TTFont(io.BytesIO(original), ignoreDecompileErrors=True) as target, TTFont(io.BytesIO(donor)) as source:
        cmap = {c: g for c, g in (target.getBestCmap() or {}).items() if g != '.notdef'}
        original_ids = {c: target.getGlyphID(g) for c, g in cmap.items()}
        missing = set(required) - set(cmap)
        if not missing:
            return original
        available = {c: g for c, g in (source.getBestCmap() or {}).items() if g != '.notdef'}
        absent = missing - set(available)
        if absent:
            raise ValueError('Font nguồn thiếu glyph cần bổ sung: ' + ''.join(chr(c) for c in sorted(absent))[:100])
        if 'glyf' not in target or 'glyf' not in source:
            raise ValueError('Bổ sung font chỉ hỗ trợ TrueType glyf; CFF cần adapter riêng.')
        # Match capital height where possible, retaining the original line metrics.
        def height(font):
            name = (font.getBestCmap() or {}).get(ord('H'))
            if not name or name == '.notdef':
                return 0
            glyph = font['glyf'][name]
            glyph.recalcBounds(font['glyf'])
            return getattr(glyph, 'yMax', 0) - getattr(glyph, 'yMin', 0)
        old_height, new_height = height(target), height(source)
        units = (round(source['head'].unitsPerEm * old_height / new_height)
                 if old_height and new_height else target['head'].unitsPerEm)
        if not 1 <= units <= 16384:
            raise ValueError('Tỉ lệ glyph nguồn không phù hợp font gốc.')
        # Only outlines, cmap and metrics are copied; discard donor-only hint/layout tables.
        essential = {'head', 'maxp', 'loca', 'glyf', 'hhea', 'hmtx', 'cmap', 'name', 'post', 'OS/2', 'GlyphOrder'}
        for tag in list(source.keys()):
            if tag not in essential:
                del source[tag]
        options = subset.Options()
        options.hinting = False  # Donor instructions must not use the original font's CVT.
        reducer = subset.Subsetter(options=options)
        reducer.populate(unicodes=missing)
        reducer.subset(source)
        # The donor is never serialized; pixel fonts can require a temporary scale below 16.
        scale_upem(source, units)
        order = target.getGlyphOrder()
        names = {}
        for index, name in enumerate(source.getGlyphOrder()):
            candidate = f'toolvh{index}'
            while candidate in target['glyf'].glyphs or candidate in names.values():
                candidate += '_'
            names[name] = candidate
        for name in source.getGlyphOrder():
            glyph = copy.deepcopy(source['glyf'][name])
            if glyph.isComposite():
                for component in glyph.components:
                    component.glyphName = names[component.glyphName]
            if hasattr(glyph, 'program'):
                glyph.program = Program()
                glyph.program.fromBytecode([])
            renamed = names[name]
            target['glyf'].glyphs[renamed] = glyph
            target['hmtx'].metrics[renamed] = source['hmtx'].metrics[name]
            if 'vmtx' in target:
                target['vmtx'].metrics[renamed] = (target['head'].unitsPerEm, 0)
            order.append(renamed)
        target.setGlyphOrder(order)
        additions = {c: names[g] for c, g in source.getBestCmap().items() if c in missing}
        for table in target['cmap'].tables:
            if table.isUnicode() and table.format in (4, 12):
                table.cmap.update(additions)
        output = io.BytesIO()
        target.save(output)
    result = output.getvalue()
    with TTFont(io.BytesIO(result)) as check:
        updated = check.getBestCmap() or {}
        if not set(required) <= set(updated) or any(c not in updated or check.getGlyphID(updated[c]) != identity for c, identity in original_ids.items()):
            raise ValueError('Kiểm tra font bổ sung thất bại; không xuất bản vá.')
    return result
