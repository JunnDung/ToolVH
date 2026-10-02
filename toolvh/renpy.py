"""Conservative single-line Ren'Py source/template reader. Never execute scripts."""
import ast
import json
import re
from .formats import context_locale, english_locale
from .model import make_entry

LITERAL=r'''(?:"(?:[^"\\\r\n]|\\.)*"|'(?:[^'\\\r\n]|\\.)*')'''
SAY=re.compile(r'^\s*(?:(?P<speaker>[A-Za-z_]\w*)\s+)?(?P<literal>'+LITERAL+r')\s*(?P<tail>:|(?:#.*)?)$')
PAIR=re.compile(r'^\s*(old|new)\s+('+LITERAL+r')\s*(?:#.*)?$')
KEYWORDS={'image','scene','show','hide','play','queue','voice','stop','define','default','return','jump','call','pause','window','style','text','add','label','python','init','transform'}


def extract(text,file):
    locale=context_locale(file)
    if locale and not english_locale(locale):return [],'Ren’Py: langue khác English; bỏ qua.'
    entries=[];offset=0;blocked=None;old=None
    for number,line in enumerate(text.splitlines(keepends=True),1):
        indent=len(line)-len(line.lstrip(' \t'))
        stripped=line.strip()
        if stripped and not stripped.startswith('#') and blocked is not None and indent<=blocked:blocked=None
        if re.match(r'^(?:python\b|init\b|screen\b|style\b|transform\b).*:',stripped) or re.match(r'^translate\s+(?!None\b|english\b|en\b)\w+\b',stripped):
            blocked=indent;old=None
        if blocked is not None or stripped.startswith(('#','$')):
            offset+=len(line);continue
        pair=PAIR.match(line)
        match=SAY.match(line) if pair is None else None
        token=None;source=None;context=''
        if pair:
            if pair[1]=='old':old=ast.literal_eval(pair[2])
            elif old is not None:
                token=pair.span(2);value=ast.literal_eval(pair[2]);source=value or old;context=f'UI translation / dòng {number}';old=None
        elif match and match['speaker'] not in KEYWORDS:
            token=match.span('literal');source=ast.literal_eval(match['literal'])
            context=f'{match["speaker"] or "Narrator/choice"} / dòng {number}'
        elif stripped and not stripped.startswith('#'):
            old=None
        if token and isinstance(source,str) and source.strip():
            start,end=offset+token[0],offset+token[1]
            e=make_entry(file,{'start':start,'end':end,'literal':text[start:end]},source,context,0.6)
            e.enabled=english_locale(locale);e.source_locale=locale;e.detection='Ren’Py source/template; cần xác nhận nguồn English nếu thiếu locale.'
            entries.append(e)
        offset+=len(line)
    return entries,'Ren’Py: source/template một dòng; không thực thi Python, không đọc RPYC/RPA hoặc suy đoán chuỗi trong code.'


def rebuild(text,entries):
    boundary=len(text)
    for e in sorted(entries,key=lambda e:e.locator['start'],reverse=True):
        start,end=e.locator['start'],e.locator['end']
        if not 0<=start<=end<=boundary or text[start:end]!=e.locator['literal']:
            raise ValueError('Ren’Py nguồn thay đổi hoặc vị trí trùng.')
        replacement=json.dumps(e.translation,ensure_ascii=False)
        text=text[:start]+replacement+text[end:];boundary=start
    return text
