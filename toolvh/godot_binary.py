"""Godot 4 RSRC v5/v6, standalone Translation with no external/script resources."""
import struct
from .unreal import Reader
from .formats import english_locale,score_text
from .model import make_entry


def string(reader):
    length=reader.number('I')
    if length>reader.limit-reader.pos:raise ValueError('RSRC string vượt dữ liệu.')
    raw=reader.take(length)
    if raw and not raw.endswith(b'\0'):raise ValueError('RSRC string thiếu terminator.')
    return raw[:-1].decode('utf-8') if raw else ''


def encode_string(value):
    if '\0' in value:raise ValueError('RSRC string có NUL.')
    raw=value.encode('utf-8')+b'\0'
    return struct.pack('<I',len(raw))+raw


def read(data):
    r=Reader(data)
    if r.take(4)!=b'RSRC':raise ValueError('Godot RSCC/scene/OptimizedTranslation cần adapter riêng.')
    if r.number('I') or r.number('I'):raise ValueError('RSRC endian/real64 header chưa hỗ trợ.')
    major,minor,version=(r.number('I') for _ in range(3))
    if major!=4 or version not in (5,6):raise ValueError('Chỉ hỗ trợ Translation RSRC Godot 4 v5/v6.')
    if string(r)!='Translation':raise ValueError('RSRC không phải Translation; OptimizedTranslation/scene chưa hỗ trợ.')
    if r.number('Q'):raise ValueError('RSRC import metadata có offset chưa hỗ trợ.')
    flags=r.number('I');r.take(8)
    if flags & ~7:raise ValueError('RSRC script class/flags chưa hỗ trợ.')
    if any(r.take(44)):raise ValueError('RSRC reserved fields không hợp lệ.')
    names=[string(r) for _ in range(r.count())]
    if r.count()!=0 or r.count()!=1:raise ValueError('RSRC external/multi-resource chưa hỗ trợ.')
    string(r);offset=r.number('Q')
    if not r.pos<=offset<len(data)-4:raise ValueError('RSRC resource offset không hợp lệ.')
    r.pos=offset
    if string(r)!='Translation':raise ValueError('RSRC internal class không khớp.')
    messages=[];locale='';properties=set()
    def value(depth=0):
        if depth>8:raise ValueError('RSRC Variant quá sâu.')
        kind=r.number('I');start=r.pos
        if kind==1:return None,None
        if kind in (2,3):return r.number('I'),None
        if kind==40:return r.number('q'),None
        if kind in (5,44):
            result=string(r);return result,(start,r.pos)
        if kind==24 and r.number('I')==0:return None,None
        if kind==26:
            length=r.number('I')&0x7fffffff
            if length>min(100000,(r.limit-r.pos)//8):raise ValueError('RSRC dictionary quá lớn.')
            pairs=[];keys=set()
            for _ in range(length):
                key,_=value(depth+1);v,span=value(depth+1)
                if not isinstance(key,str) or key in keys:raise ValueError('RSRC dictionary key trùng/không phải string.')
                keys.add(key);pairs.append((key,v,span))
            return pairs,None
        raise ValueError('RSRC Variant chưa hỗ trợ.')
    for _ in range(r.count()):
        name=r.number('I')
        if name&0x80000000:
            raw=r.take(name&0x7fffffff);name=raw.rstrip(b'\0').decode('utf-8')
        else:
            if name>=len(names):raise ValueError('RSRC property index không hợp lệ.')
            name=names[name]
        if name in properties:raise ValueError('RSRC property trùng.')
        properties.add(name);v,span=value()
        if name=='locale':
            if not isinstance(v,str):raise ValueError('RSRC locale không phải string.')
            locale=v.lower().replace('_','-')
        elif name=='messages':
            if not isinstance(v,list) or any(not isinstance(item[1],str) or item[2] is None for item in v):
                raise ValueError('RSRC messages không phải dictionary string.')
            messages=v
    if r.pos!=len(data)-4 or r.take(4)!=b'RSRC':raise ValueError('RSRC trailer/schema không hợp lệ.')
    return locale,messages


def extract(data,file):
    locale,rows=read(data);entries=[]
    if locale and not english_locale(locale):return [],'Godot RSRC Translation: bỏ qua locale khác English.'
    for key,source,(start,end) in rows:
        if not source.strip() or score_text(source,key,'text')<=0:continue
        e=make_entry(file,{'start':start,'end':end},source,f'Translation / {locale or "cần duyệt"} / {key}',.95 if locale else .6)
        e.source_locale=locale;e.enabled=english_locale(locale);e.detection='Godot 4 RSRC Translation; locale='+locale
        entries.append(e)
    return entries,'Godot RSRC Translation v5/v6: giữ key, locale, UID và metadata.'


def rebuild(data,entries):
    locale,rows=read(data);spans={(start,end):source for _,source,(start,end) in rows}
    output=data;boundary=len(data)
    for e in sorted(entries,key=lambda e:e.locator['start'],reverse=True):
        start,end=e.locator['start'],e.locator['end']
        if spans.get((start,end))!=e.source or not 0<=start<=end<=boundary:raise ValueError('RSRC source thay đổi/vị trí trùng.')
        output=output[:start]+encode_string(e.translation)+output[end:];boundary=start
    new_locale,new_rows=read(output)
    expected={(e.locator['start'],e.locator['end']):e.translation for e in entries}
    if locale!=new_locale or [(key,expected.get(span,source)) for key,source,span in rows]!=[(key,source) for key,source,_ in new_rows]:
        raise ValueError('RSRC reopen không khớp bản dịch.')
    return output
