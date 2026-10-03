"""Read packed Unity player data per asset; copy resource blocks without inflating them."""
import bisect
import os
import struct
import tempfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from UnityPy.streams import EndianBinaryReader
from UnityPy.helpers.CompressionHelper import DECOMPRESSION_MAP


class TemporaryPayload(type(Path())):
    def __del__(self):
        try:
            self.unlink(missing_ok=True)
        except OSError:
            pass


class UnsupportedVersion(ValueError):
    pass


class Bundle:
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as source:
            r = EndianBinaryReader(source)
            if r.read_string_to_null() != 'UnityFS':
                raise ValueError('Cần UnityFS.')
            self.version = r.read_u_int()
            self.player, self.engine = r.read_string_to_null(), r.read_string_to_null()
            if self.version not in (7, 8) or int(self.engine.split('.')[0]) < 2022:
                raise UnsupportedVersion('UnityFS stream chỉ hỗ trợ v7/v8 Unity 2022+ không mã hóa.')
            size, compressed, expanded, self.flags = r.read_long(), r.read_u_int(), r.read_u_int(), r.read_u_int()
            if size != self.path.stat().st_size or compressed > 32*1024*1024 or expanded > 64*1024*1024:
                raise ValueError('UnityFS header/kích thước index không hợp lệ.')
            if self.flags & 0x400 or not self.flags & 0x40:
                raise ValueError('UnityFS mã hóa/index riêng chưa hỗ trợ stream.')
            r.align_stream(16)
            start = r.Position
            if self.flags & 0x80:
                r.Position = size - compressed
            info = self.inflate(r.read_bytes(compressed), expanded, self.flags)
            r.Position = start if self.flags & 0x80 else start + compressed
            if self.flags & 0x200:
                r.align_stream(16)
            self.data_start = r.Position
            self.data_end = size - compressed if self.flags & 0x80 else size
        i = EndianBinaryReader(info)
        i.read_bytes(16)
        count = i.read_int()
        if not 0 <= count <= len(info)//10:
            raise ValueError('UnityFS block count không hợp lệ.')
        self.blocks, self.starts = [], []
        position, logical = self.data_start, 0
        for _ in range(count):
            u, c, flags = i.read_u_int(), i.read_u_int(), i.read_u_short()
            if not 0 < u <= 64*1024*1024 or not c or flags & 0x100 or position+c > self.data_end:
                raise ValueError('UnityFS block vượt giới hạn/mã hóa/bị cắt.')
            self.starts.append(logical)
            self.blocks.append((u, c, flags, position))
            logical += u
            position += c
        self.total = logical
        if position != self.data_end:
            raise ValueError('UnityFS dữ liệu thừa hoặc bị cắt.')
        count = i.read_int()
        if not 0 <= count <= len(info)//21:
            raise ValueError('UnityFS node count không hợp lệ.')
        self.nodes = []
        for _ in range(count):
            offset, size, flags, name = i.read_long(), i.read_long(), i.read_u_int(), i.read_string_to_null()
            if offset < 0 or size < 0 or offset+size > logical or len(name) > 4096:
                raise ValueError('UnityFS member không hợp lệ.')
            self.nodes.append((offset, size, flags, name))
        if i.Position != len(info) or len({n[3] for n in self.nodes}) != len(self.nodes):
            raise ValueError('UnityFS index thừa/tên trùng.')

    @staticmethod
    def inflate(data, size, flags):
        method = flags & 63
        if method not in (0, 2, 3):
            raise ValueError('UnityFS stream chỉ hỗ trợ block không nén/LZ4/LZ4HC.')
        result = DECOMPRESSION_MAP[method](data, size)
        if len(result) != size:
            raise ValueError('UnityFS block giải nén sai kích thước.')
        return result

    def member(self, node, cancelled=lambda: False):
        offset, size, _, _ = node
        result = bytearray()
        with self.path.open('rb') as source:
            index = max(0, bisect.bisect_right(self.starts, offset)-1)
            while len(result) < size:
                if cancelled():
                    raise InterruptedError('Đã dừng đọc UnityFS.')
                u, c, flags, physical = self.blocks[index]
                source.seek(physical)
                raw = self.inflate(source.read(c), u, flags)
                start = max(0, offset-self.starts[index])
                result.extend(raw[start:start+min(u-start, size-len(result))])
                index += 1
        return bytes(result)


def extract_file(path, file, cancelled=lambda: False, registry=None, progress=lambda text: None, max_mb=256):
    from .unity import extract_unity
    bundle = Bundle(path)
    registry = registry if registry is not None else {}
    entries, notes = [], []
    nodes = sorted((n for n in bundle.nodes if n[2] & 4), key=lambda n: n[3] != 'globalgamemanagers.assets')
    for index, node in enumerate(nodes, 1):
        progress(f'UnityFS asset {index}/{len(nodes)}: {node[3]}')
        if node[1] > max_mb*1024*1024:
            notes.append(f'{node[3]} vượt giới hạn asset {max_mb} MB; chưa đọc.')
            continue
        found, note = extract_unity(bundle.member(node, cancelled), file, cancelled, registry, node[3])
        for e in found:
            e.locator['bundle_member'] = node[3]
        entries.extend(found)
        if note:
            notes.append(f'{node[3]}: {note}')
    return entries, f'UnityFS stream: {len(nodes)} asset; {len(bundle.nodes)-len(nodes)} resource giữ nguyên, không giải nén khi quét. ' + ' | '.join(notes[:12])


def rebuild_file(path, entries):
    from .unity import rebuild_unity
    bundle = Bundle(path)
    groups = defaultdict(list)
    for e in entries:
        locator = dict(e.locator)
        member = locator.pop('bundle_member')
        locator['container'] = '__root__'
        groups[member].append(replace(e, locator=locator))
    edited = {}
    for node in bundle.nodes:
        if node[3] in groups:
            edited[node[3]] = rebuild_unity(bundle.member(node), groups.pop(node[3]))
    if groups:
        raise ValueError('Không tìm thấy UnityFS asset cần sửa.')
    fd, name = tempfile.mkstemp(prefix='toolvh-unityfs-', suffix='.unity3d')
    os.close(fd)
    output = TemporaryPayload(name)
    blocks = [b[:3] for b in bundle.blocks]
    nodes = []
    logical = bundle.total
    signature = b'UnityFS\0'+struct.pack('>I', bundle.version)+bundle.player.encode()+b'\0'+bundle.engine.encode()+b'\0'
    header = signature+struct.pack('>QIII', 0, 0, 0, 0x2c0)
    with output.open('wb') as target, Path(path).open('rb') as source:
        target.write(header)
        target.write(bytes((-target.tell()) % 16))
        source.seek(bundle.data_start)
        remaining = bundle.data_end-bundle.data_start
        while remaining:
            raw = source.read(min(8*1024*1024, remaining))
            if not raw:
                raise ValueError('UnityFS nguồn thay đổi/bị cắt.')
            target.write(raw)
            remaining -= len(raw)
        for offset, size, flags, member in bundle.nodes:
            raw = edited.get(member)
            if raw is not None:
                offset, size = logical, len(raw)
                for start in range(0, len(raw), 128*1024):
                    block = raw[start:start+128*1024]
                    blocks.append((len(block), len(block), 0))
                    target.write(block)
                logical += size
            nodes.append((offset, size, flags, member))
        info = bytes(16)+struct.pack('>I', len(blocks))+b''.join(struct.pack('>IIH', *b) for b in blocks)
        info += struct.pack('>I', len(nodes))+b''.join(struct.pack('>QQI', o, s, f)+n.encode()+b'\0' for o,s,f,n in nodes)
        target.write(info)
        length = target.tell()
        target.seek(len(signature))
        target.write(struct.pack('>QIII', length, len(info), len(info), 0x2c0))
    check = Bundle(output)
    for node in check.nodes:
        if node[3] in edited and check.member(node) != edited[node[3]]:
            raise ValueError('UnityFS kiểm tra asset sau ghi thất bại.')
    return output
