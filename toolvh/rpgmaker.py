"""RPG Maker MV/MZ JSON: database fields and explicit event text commands."""
import json
from pathlib import Path
from .formats import load_json, get_at, set_at, score_text
from .model import make_entry

DATABASES = {'Actors':'character','Items':'item','Weapons':'weapon','Armors':'item',
             'Skills':'ability','Enemies':'character','Classes':'class','States':'state'}


def is_database(file):
    p=Path(file)
    return p.parent.name.lower()=='data' and (p.stem in DATABASES or p.stem in ('System','CommonEvents','Troops') or p.stem.startswith('Map') and p.stem[3:].isdigit())


def extract(text, file):
    data=load_json(text);entries=[];stem=Path(file).stem
    def add(path, context):
        value=get_at(data,path)
        if isinstance(value,str) and value.strip() and score_text(value,context,'text')>0:
            e=make_entry(file,{'path':path},value,context,0.6)
            e.enabled=False;e.detection='RPG Maker: xác nhận nguồn English trước khi chọn dịch.'
            entries.append(e)
    if stem in DATABASES and isinstance(data,list):
        for i,row in enumerate(data):
            if not isinstance(row,dict):continue
            for field in ('name','description','nickname','profile','message1','message2','message3','message4'):
                if field in row:add([i,field],f'{DATABASES[stem]} {field} / ID {row.get("id",i)}')
    if stem.startswith('Map') and isinstance(data,dict) and 'displayName' in data:
        add(['displayName'],'location name / '+stem)
    if stem=='System' and isinstance(data,dict):
        def terms(node,path):
            if isinstance(node,str):add(path,'System terms / '+' / '.join(map(str,path)))
            elif isinstance(node,list):
                for i,v in enumerate(node):terms(v,path+[i])
            elif isinstance(node,dict):
                for k,v in node.items():terms(v,path+[k])
        if 'terms' in data:terms(data['terms'],['terms'])
        if 'gameTitle' in data:add(['gameTitle'],'game name')
    def events(node,path):
        if isinstance(node,dict):
            parameters=node.get('parameters')
            if isinstance(parameters,list) and isinstance(node.get('indent'),int):
                code=node.get('code')
                if code in (401,405) and parameters:
                    add(path+['parameters',0],f'Event dialogue / {path}')
                elif code==102 and parameters and isinstance(parameters[0],list):
                    for i in range(len(parameters[0])):add(path+['parameters',0,i],f'Event choice / {path} / {i}')
            for k,v in node.items():events(v,path+[k])
        elif isinstance(node,list):
            for i,v in enumerate(node):events(v,path+[i])
    events(data,[])
    return entries,'RPG Maker MV/MZ: chỉ trường hiển thị/lời thoại/lựa chọn; giữ script, note, lệnh plugin và ID. Nguồn cần duyệt.'


def rebuild(text, entries):
    data=load_json(text)
    for e in entries:
        if get_at(data,e.locator['path'])!=e.source:raise ValueError('Text RPG Maker nguồn đã thay đổi.')
        set_at(data,e.locator['path'],e.translation)
    return json.dumps(data,ensure_ascii=False,separators=(',',':'))
