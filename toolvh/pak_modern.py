"""Bounded reader/writer for unencrypted PAK path-hash indexes (v10–12)."""
import hashlib
import struct
import zlib
from collections import defaultdict
from dataclasses import replace
from pathlib import PurePosixPath

from .unreal import Reader, extract_locres, rebuild_locres
from .formats import context_locale, english_locale
from .model import make_entry

MAGIC = 0x5A6F12E1
MAX_PAYLOAD = 64 * 1024 * 1024


def directory(data, version):
    r = Reader(data)
    rows = []
    for _ in range(r.count()):
        parent = r.string()
        for _ in range(r.count()):
            if version >= 12:
                length = r.count()
                leaf = r.take(length).decode('utf-8')  # v12 UTF8 filename has no NUL
            else:
                leaf = r.string()
            location_pos = r.pos
            location = r.number('i')
            name = (parent + leaf).lstrip('/')
            path = PurePosixPath(name)
            if not leaf or '/' in leaf or '\\' in name or ':' in name or '\0' in name or '..' in path.parts:
                raise ValueError('PAK tên member không hợp lệ.')
            rows.append(dict(name=name, location=location, location_pos=location_pos))
    if r.pos != r.limit:
        raise ValueError('PAK directory schema chưa hỗ trợ.')
    return rows


def read(data):
    if len(data) < 221:
        raise ValueError('PAK footer bị cắt.')
    magic, version, offset, size = struct.unpack_from('<Iiqq', data, len(data) - 204)
    if magic != MAGIC or version not in (10, 11, 12):
        raise ValueError('PAK: chỉ hỗ trợ path-hash index v10–12.')
    if data[-205]:
        raise ValueError('PAK index mã hóa chưa hỗ trợ.')
    footer_start = len(data) - 221
    regions = []

    def region(o, s, checksum):
        if o < 0 or s < 0 or o + s > footer_start:
            raise ValueError('PAK index offset/kích thước không hợp lệ.')
        result = data[o:o + s]
        if hashlib.sha1(result).digest() != checksum:
            raise ValueError('PAK index SHA1 không khớp.')
        if any(o < b and a < o + s for a, b in regions):
            raise ValueError('PAK index chồng lấn.')
        regions.append((o, o + s))
        return result

    index = region(offset, size, data[-180:-160])
    r = Reader(index)
    r.string()
    count = r.count()
    r.take(8)
    references = []
    for _ in range(2):
        flag = r.number()
        if flag not in (0, 1):
            raise ValueError('PAK index flag không hợp lệ.')
        if flag:
            position = r.pos
            o, s = r.number('q'), r.number('q')
            references.append((position, region(o, s, r.take(20))))
        else:
            references.append(None)
    if references[1] is None:
        raise ValueError('PAK thiếu full directory index; không thể xác định tên tài nguyên.')
    blob_size_pos = r.pos
    blob = r.take(r.count())
    if r.count() or r.pos != r.limit:
        raise ValueError('PAK non-encoded index/schema chưa hỗ trợ.')
    rows = directory(references[1][1], version)
    if len(rows) != count or len({row['name'] for row in rows}) != count:
        raise ValueError('PAK số member/tên trùng không hợp lệ.')
    for row in rows:
        location = row['location']
        if not 0 <= location < len(blob):
            raise ValueError('PAK encoded location không hợp lệ.')
        e = Reader(blob, location)
        flags = e.number('I')
        block_size = e.number('I') if flags & 63 == 63 else (flags & 63) << 11
        member_offset = e.number('I' if flags & (1 << 31) else 'Q')
        uncompressed = e.number('I' if flags & (1 << 30) else 'Q')
        compression = (flags >> 23) & 63
        stored = e.number('I' if flags & (1 << 29) else 'Q') if compression else uncompressed
        blocks = (flags >> 6) & 65535
        if blocks and (blocks > 1 or flags & (1 << 22)):
            e.take(blocks * 4)
        if member_offset + 53 + stored > min(a for a, b in regions):
            raise ValueError('PAK member vượt payload.')
        row.update(offset=member_offset, size=stored, uncompressed=uncompressed,
                   compression=compression, flags=bool(flags & (1 << 22)), block_size=block_size)
    methods = [data[-160 + i * 32:len(data) - 160 + (i + 1) * 32].split(b'\0')[0].decode('ascii') for i in range(5)]
    return dict(version=version, offset=offset, index=index, rows=rows, footer=data[-221:],
                references=references, blob=blob, blob_size_pos=blob_size_pos, methods=methods,
                payload_limit=min(a for a, b in regions))


def payload(data, row, archive):
    from .pak import entry
    if row['flags']:
        raise ValueError('PAK member mã hóa chưa hỗ trợ.')
    if row['uncompressed'] > MAX_PAYLOAD:
        raise ValueError('PAK LOCRES vượt giới hạn 64 MB giải nén.')
    r = Reader(data, row['offset'], archive['payload_limit'])
    header = entry(r, archive['version'])
    if header['offset'] or header['flags'] or any(header[k] != row[k] for k in ('size', 'uncompressed', 'compression')):
        raise ValueError('PAK header member khác index.')
    raw = r.take(row['size'])
    if hashlib.sha1(raw).digest() != header['checksum']:
        raise ValueError('PAK payload SHA1 không khớp.')
    if not row['compression']:
        if len(raw) != row['uncompressed']:
            raise ValueError('PAK member size không khớp.')
        return raw
    c = row['compression']
    method = archive['methods'][c - 1] if 1 <= c <= 5 else 'unknown'
    if method.lower() not in ('zlib', 'gzip', 'oodle'):
        raise ValueError(f'PAK LOCRES nén {method}: chưa có bộ giải nén; không chọn/dịch/cài mục này.')
    blocks_reader = Reader(data, row['offset'] + 48, r.pos)
    blocks = [(blocks_reader.number('q'), blocks_reader.number('q')) for _ in range(blocks_reader.count())]
    output = bytearray()
    end = r.pos - row['offset']
    previous = r.pos - row['offset'] - row['size']
    for start, stop in blocks:
        if start != previous or not start < stop <= end:
            raise ValueError('PAK compression block không hợp lệ.')
        block = data[row['offset'] + start:row['offset'] + stop]
        if method.lower() == 'oodle':
            from .oodle import decompress
            expected = min(row['block_size'] or row['uncompressed'], row['uncompressed'] - len(output))
            output.extend(decompress(block, expected))
        else:
            decoder = zlib.decompressobj(31 if method.lower() == 'gzip' else 15)
            output.extend(decoder.decompress(block, row['uncompressed'] - len(output) + 1))
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(output) > row['uncompressed']:
                raise ValueError('PAK block giải nén sai kích thước.')
        previous = stop
    if previous != end or len(output) != row['uncompressed']:
        raise ValueError('PAK dữ liệu giải nén bị cắt.')
    return bytes(output)


def extract(data, file, cancelled=lambda: False):
    archive = read(data)
    entries, notes = [], []
    localized = [row for row in archive['rows'] if row['name'].lower().endswith('.locres') and not row['name'].lower().startswith('engine/')]
    vietnamese = [row['name'] for row in localized if context_locale(row['name']).startswith('vi')]
    for row in localized:
        if cancelled():
            raise InterruptedError('Đã dừng quét PAK.')
        locale = context_locale(row['name'])
        if locale and not english_locale(locale):
            continue
        try:
            children, _ = extract_locres(payload(data, row, archive), row['name'])
        except ValueError as exc:
            notes.append(f'{row["name"]}: {exc}')
            continue
        for child in children:
            e = make_entry(file, {'member': row['name'], 'inner': child.locator}, child.source,
                           f'{row["name"]} / {child.context}', child.confidence)
            e.enabled, e.source_locale, e.detection = child.enabled, child.source_locale, child.detection
            entries.append(e)
    note = f'Unreal PAK v{archive["version"]}: {len(archive["rows"])} member, {len(localized)} LOCRES của game; {len(entries)} text đọc được. '
    if vietnamese:
        note += 'Có tài nguyên Vietnamese sẵn: ' + ', '.join(vietnamese[:3]) + '; thử chọn Tiếng Việt trong game trước (chưa xác nhận chất lượng/nạp runtime). '
    return entries, note + ' | '.join(notes[:8])


def rebuild(data, entries):
    archive = read(data)
    if not entries:
        return data
    groups = defaultdict(list)
    for e in entries:
        groups[e.locator['member']].append(e)
    output = bytearray(data[:-221])
    blob = bytearray(archive['blob'])
    locations = {}
    for row in archive['rows']:
        edits = groups.pop(row['name'], [])
        if not edits:
            continue
        raw = rebuild_locres(payload(data, row, archive), [replace(e, locator=e.locator['inner']) for e in edits])
        position = len(output)
        header = struct.pack('<qqqI', 0, len(raw), len(raw), 0) + hashlib.sha1(raw).digest() + struct.pack('<BI', 0, 0)
        output.extend(header + raw)
        locations[row['location']] = len(blob)
        blob.extend(struct.pack('<IQQ', 0, position, len(raw)))
    if groups:
        raise ValueError('Không tìm thấy PAK member.')
    index = bytearray(archive['index'][:archive['blob_size_pos']])
    for reference in archive['references']:
        if reference is None:
            continue
        field, original = reference
        secondary = bytearray(original)
        if reference is archive['references'][0]:
            r = Reader(secondary)
            for _ in range(r.count()):
                r.take(8)
                pos = r.pos
                old = r.number()
                if old in locations:
                    struct.pack_into('<i', secondary, pos, locations[old])
            directory_start = r.pos
        else:
            directory_start = 0
        for row in directory(secondary[directory_start:], archive['version']):
            if row['location'] in locations:
                struct.pack_into('<i', secondary, directory_start + row['location_pos'], locations[row['location']])
        struct.pack_into('<qq', index, field, len(output), len(secondary))
        index[field + 16:field + 36] = hashlib.sha1(secondary).digest()
        output.extend(secondary)
    index.extend(struct.pack('<i', len(blob)) + blob + struct.pack('<i', 0))
    footer = bytearray(archive['footer'])
    struct.pack_into('<qq', footer, 25, len(output), len(index))
    footer[41:61] = hashlib.sha1(index).digest()
    output.extend(index + footer)
    result = bytes(output)
    verified = read(result)
    changed_names = {e.locator['member'] for e in entries}
    for row in verified['rows']:
        if row['name'] in changed_names:
            payload(result, row, verified)
    return result
