"""Conservative Ren'Py dialogue reader. Never execute scripts or expressions."""
import ast
import json
import re
from .formats import context_locale, english_locale
from .model import make_entry

LITERAL = r'''(?:"""(?:[^\\]|\\.)*?"""|\x27\x27\x27(?:[^\\]|\\.)*?\x27\x27\x27|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')'''
NAME = r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*'
SAY = re.compile(r'^\s*(?:(?P<speaker>' + NAME + r')(?P<attributes>(?:\s+(?:@|-)?[A-Za-z_]\w*|\s+@)*)\s+|(?P<named>' + LITERAL + r')\s+)?(?P<literal>' + LITERAL + r')(?P<tail>[^\r\n]*)\s*$', re.S)
PAIR = re.compile(r'^\s*(old|new)\s+(' + LITERAL + r')\s*(?:#[^\r\n]*)?\s*$', re.S)
KEYWORDS = {'image', 'scene', 'show', 'hide', 'play', 'queue', 'voice', 'stop', 'define', 'default', 'return', 'jump', 'call', 'pause', 'window', 'style', 'text', 'add', 'label', 'python', 'init', 'transform', 'if', 'elif', 'else', 'while', 'menu', 'translate', 'with', 'at', 'onlayer', 'rpy', 'camera', 'nvl', 'pass'}


def statements(text):
    """Keep literal spans across physical lines; comments never open a string."""
    start = index = 0
    number = 1
    line_number = 1
    quote = None
    comment = False
    while index < len(text):
        char = text[index]
        if quote:
            if char == '\\':
                if index + 1 < len(text) and text[index + 1] == '\n':
                    line_number += 1
                index += 2
                continue
            if text.startswith(quote, index):
                index += len(quote)
                quote = None
                continue
        elif not comment:
            if char == '#':
                comment = True
            elif char in ('"', "'"):
                quote = char * 3 if text.startswith(char * 3, index) else char
                index += len(quote)
                continue
        if char == '\n':
            line_number += 1
            if quote is None:
                yield start, number, text[start:index + 1]
                start = index + 1
                number = line_number
                comment = False
        index += 1
    if quote:
        raise ValueError('Ren’Py: chuỗi chưa đóng; không sửa script không hoàn chỉnh.')
    if start < len(text):
        yield start, number, text[start:]


def value(literal):
    # Ren'Py folds physical whitespace; explicit escaped newlines remain tokens.
    return ast.literal_eval(re.sub(r'(?<!\\)\s+', ' ', literal))


def valid_tail(tail):
    tail = tail.strip()
    if not tail or tail.startswith('#'):
        return True
    if re.fullmatch(r'(?:nointeract\s*)?(?:with\s+' + NAME + r'\s*)?(?:#[^\r\n]*)?', tail):
        return True
    if re.fullmatch(r'(?:if\s+[^\r\n]+)?:\s*(?:#[^\r\n]*)?', tail):
        return True
    # Only syntax-check say arguments. No evaluation and no edits to arguments.
    arguments = tail.split(' #', 1)[0].strip()
    if arguments.startswith('(') and arguments.endswith(')'):
        try:
            ast.parse('_say' + arguments, mode='eval')
            return True
        except SyntaxError:
            pass
    return False


def extract(text, file):
    locale = context_locale(file)
    if locale and not english_locale(locale):
        return [], 'Ren’Py: ngôn ngữ khác English; bỏ qua.'
    entries = []
    blocked = old = None
    label = ''
    skipped_monologues = 0
    monologue_none = bool(re.search(r'^\s*rpy\s+monologue\s+none\s*(?:#.*)?$', text, re.M))
    for offset, number, line in statements(text):
        indent = len(line) - len(line.lstrip(' \t'))
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and blocked is not None and indent <= blocked:
            blocked = None
        if re.match(r'^(?:python\b|init\b|screen\b|style\b|transform\b).*:', stripped) or re.match(r'^translate\s+(?!None\b|english\b|en\b)\w+\b', stripped):
            blocked = indent
            old = None
        if blocked is not None or stripped.startswith(('#', '$')):
            continue
        label_match = re.match(r'^label\s+(' + NAME + r')\b', stripped)
        if label_match:
            label = label_match[1]
        pair = PAIR.match(line)
        match = SAY.match(line) if pair is None else None
        token = source = None
        context = ''
        fragments = []
        if pair:
            if pair[2].startswith(('"""', "'''")):
                old = None
                skipped_monologues += 1
                continue
            if pair[1] == 'old':
                old = value(pair[2])
            elif old is not None:
                token = pair.span(2)
                source = value(pair[2]) or old
                context = f'UI translation / dòng {number}'
                old = None
        elif match and (match['speaker'] or '').split('.')[0] not in KEYWORDS and valid_tail(match['tail']):
            old = None
            token = match.span('literal')
            literal = match['literal']
            speaker = match['speaker'] or (value(match['named']) if match['named'] else 'Narrator/choice')
            context = f'{label + " / " if label else ""}{speaker}{match["attributes"] or ""} / dòng {number}'
            if literal.startswith(('"""', "'''")):
                if monologue_none:
                    skipped_monologues += 1
                    continue
                content = literal[3:-3]
                cursor = 0
                # Each blank-line-separated block is one say statement in Ren'Py.
                for separator in list(re.finditer(r'\r?\n[ \t]*\r?\n', content)) + [None]:
                    end = separator.start() if separator else len(content)
                    raw = content[cursor:end]
                    leading = len(raw) - len(raw.lstrip())
                    raw = raw.strip()
                    if raw:
                        start = token[0] + 3 + cursor + leading
                        fragments.append((start, start + len(raw), value(literal[:3] + raw + literal[:3]), True))
                    cursor = separator.end() if separator else len(content)
                token = None
            else:
                source = value(literal)
        elif stripped and not stripped.startswith('#'):
            old = None
        if token:
            fragments.append((*token, source, False))
        for index, (start, end, source, fragment) in enumerate(fragments, 1):
            if not isinstance(source, str) or not source.strip():
                continue
            start, end = offset + start, offset + end
            locator = {'start': start, 'end': end, 'literal': text[start:end]}
            if match and match['named']:
                locator['speaker_name'] = value(match['named'])
            if fragment:
                locator['fragment'] = True
            entry = make_entry(file, locator, source, context + (f' / đoạn {index}' if fragment else ''), 0.6)
            entry.enabled = english_locale(locale)
            entry.source_locale = locale
            entry.detection = 'Ren’Py source/template; cần xác nhận nguồn English nếu thiếu locale.'
            entries.append(entry)
    note = 'Ren’Py: thoại, menu, thuộc tính và nhiều dòng; không thực thi Python, không đọc RPYC/RPA.'
    if skipped_monologues:
        note += f' Bỏ qua {skipped_monologues} triple quote dùng chế độ/cú pháp chưa hỗ trợ.'
    return entries, note


def rebuild(text, entries):
    boundary = len(text)
    for entry in sorted(entries, key=lambda entry: entry.locator['start'], reverse=True):
        start, end = entry.locator['start'], entry.locator['end']
        if not 0 <= start <= end <= boundary or text[start:end] != entry.locator['literal']:
            raise ValueError('Ren’Py nguồn thay đổi hoặc vị trí trùng.')
        replacement = json.dumps(entry.translation, ensure_ascii=False)
        if entry.locator.get('fragment'):
            replacement = replacement[1:-1]
            # Escape both quote styles since monologues can use either delimiter.
            replacement = replacement.replace("'", "\\'")
        text = text[:start] + replacement + text[end:]
        boundary = start
    return text
