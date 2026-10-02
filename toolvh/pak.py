"""Unencrypted Unreal PAK v1–7: bounded index reader, uncompressed LOCRES edits."""
import hashlib
import struct
from collections import defaultdict
from dataclasses import replace
from pathlib import PurePosixPath
from .unreal import Reader, extract_locres, rebuild_locres
from .model import make_entry

MAGIC=0x5A6F12E1


def entry(reader,version):
    start=reader.pos
    offset,size,uncompressed=(reader.number('q') for _ in range(3))
    compression=reader.number('I')
    if version==1:reader.take(8)
    checksum=reader.take(20)
    if version>=3:
        if compression:reader.take(reader.count()*16)
        flags=reader.number('B');reader.take(4)
    else:flags=0
    return dict(offset=offset,size=size,uncompressed=uncompressed,compression=compression,
                checksum=checksum,flags=flags,start=start,end=reader.pos)


def read(data):
    if len(data)>=221 and struct.unpack_from('<I',data,len(data)-204)[0]==MAGIC:
        from . import pak_modern
        archive=pak_modern.read(data)
        return archive['version'],archive['offset'],archive['index'],archive['rows'],archive['footer']
    footer=None
    for version in range(1,8):
        size=44+(1 if version>=4 else 0)+(16 if version>=7 else 0)
        if len(data)<size:continue
        magic,found,offset,length=struct.unpack_from('<Iiqq',data,len(data)-44)
        if magic==MAGIC and found==version:
            footer=len(data)-size;break
    if footer is None:raise ValueError('PAK: chỉ hỗ trợ Unreal v1–7; PAK engine khác/IoStore cần adapter riêng.')
    if version>=4 and data[len(data)-45]:raise ValueError('PAK index mã hóa chưa hỗ trợ.')
    if offset<0 or length<0 or offset+length!=footer:raise ValueError('PAK index offset/kích thước không hợp lệ.')
    index=data[offset:footer]
    if hashlib.sha1(index).digest()!=data[-20:]:raise ValueError('PAK index SHA1 không khớp.')
    r=Reader(index);r.string();count=r.count();rows=[];names=set()
    for _ in range(count):
        name=r.string();path=PurePosixPath(name)
        if not name or '\x00' in name or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or name in names:
            raise ValueError('PAK tên member không hợp lệ/trùng.')
        names.add(name);row=entry(r,version);row['name']=name
        if row['offset']<0 or row['size']<0 or row['uncompressed']<0 or row['offset']+row['size']>offset:
            raise ValueError('PAK member vượt payload.')
        rows.append(row)
    if r.pos!=len(index):raise ValueError('PAK index có dữ liệu/schema chưa hỗ trợ.')
    return version,offset,index,rows,data[footer:]


def payload(data,row,version,index_offset):
    if version>=10:
        from . import pak_modern
        return pak_modern.payload(data,row,pak_modern.read(data))
    if row['compression'] or row['flags']:raise ValueError('PAK LOCRES nén/mã hóa/delete chưa hỗ trợ.')
    r=Reader(data,row['offset'],index_offset);header=entry(r,version)
    if header['offset']!=0 or any(header[k]!=row[k] for k in ('size','uncompressed','compression','checksum','flags')):
        raise ValueError('PAK header member khác index.')
    if row['size']!=row['uncompressed']:raise ValueError('PAK member size không khớp.')
    raw=r.take(row['size'])
    if hashlib.sha1(raw).digest()!=row['checksum']:raise ValueError('PAK payload SHA1 không khớp.')
    return raw


def extract(data,file,cancelled=lambda:False):
    if len(data)>=221 and struct.unpack_from('<I',data,len(data)-204)[0]==MAGIC:
        from . import pak_modern
        return pak_modern.extract(data,file,cancelled)
    version,offset,index,rows,footer=read(data);entries=[];notes=[]
    for row in rows:
        if cancelled():raise InterruptedError('Đã dừng quét PAK.')
        if not row['name'].lower().endswith('.locres'):continue
        try:children,_=extract_locres(payload(data,row,version,offset),row['name'])
        except ValueError as exc:notes.append(f'{row["name"]}: {exc}');continue
        for child in children:
            e=make_entry(file,{'member':row['name'],'inner':child.locator},child.source,f'{row["name"]} / {child.context}',child.confidence)
            e.enabled=child.enabled;e.source_locale=child.source_locale;e.detection=child.detection
            entries.append(e)
    return entries,f'Unreal PAK v{version}: LOCRES không nén; giữ member khác. '+(' | '.join(notes[:8]) or 'Font và runtime mount cần kiểm tra trong game.')


def rebuild(data,entries):
    if len(data)>=221 and struct.unpack_from('<I',data,len(data)-204)[0]==MAGIC:
        from . import pak_modern
        return pak_modern.rebuild(data,entries)
    version,offset,index,rows,footer=read(data)
    output=bytearray(data[:len(data)-len(footer)]);index=bytearray(index);groups=defaultdict(list)
    for e in entries:groups[e.locator['member']].append(e)
    for row in rows:
        edits=groups.pop(row['name'],[])
        if not edits:continue
        raw=payload(data,row,version,offset)
        modified=rebuild_locres(raw,[replace(e,locator=e.locator['inner']) for e in edits])
        header=bytearray(index[row['start']:row['end']]);position=len(output)
        struct.pack_into('<qqq',header,0,0,len(modified),len(modified))
        hash_offset=36 if version==1 else 28
        header[hash_offset:hash_offset+20]=hashlib.sha1(modified).digest()
        output.extend(header);output.extend(modified)
        struct.pack_into('<q',header,0,position)
        index[row['start']:row['end']]=header
    if groups:raise ValueError('Không tìm thấy PAK member.')
    new_offset=len(output);output.extend(index)
    footer=bytearray(footer)
    struct.pack_into('<qq',footer,len(footer)-36,new_offset,len(index))
    footer[-20:]=hashlib.sha1(index).digest();output.extend(footer)
    result=bytes(output)
    v,off,_,verified,_=read(result)
    for row in verified:
        if row['name'] in {e.locator['member'] for e in entries}:payload(result,row,v,off)
    return result
