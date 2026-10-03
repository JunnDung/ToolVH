"""Format adapters. Locators remain stable between extraction and rebuilding."""
from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .model import Entry, make_entry

TEXT_EXTENSIONS = {".json", ".csv", ".tsv", ".xml", ".txt", ".ini", ".lang", ".srt"}
TECHNICAL_KEYS = {"id", "key", "guid", "uuid", "path", "file", "filename", "asset", "prefab",
                  "sprite", "texture", "script", "type", "shader", "url", "code", "command",
                  "m_name", "m_displayname", "term", "languagecode", "locale", "language", "font", "sound"}
TECHNICAL_KEYS |= {"assemblyname", "m_assemblyname", "classname", "m_classname", "namespace",
                   "m_namespace", "publickeytoken", "m_key", "m_keyid", "m_code",
                   "m_internalid", "m_providerid", "m_assemblytypename", "m_methodname"}
TEXT_KEYS = {"text", "description", "dialogue", "dialog", "message", "title", "label", "name",
             "caption", "subtitle", "english", "en", "en-us", "value", "content", "translation", "m_text"}
LOCALIZATION = re.compile(r"locali[sz]|language|dialog|subtitle|strings|translation|\blang\b", re.I)
LANGUAGES = {
    "english": "en", "french": "fr", "german": "de", "italian": "it",
    "spanish": "es", "portuguese": "pt", "russian": "ru", "chinese": "zh",
    "japanese": "ja", "korean": "ko", "polish": "pl", "turkish": "tr",
    "ukrainian": "uk", "vietnamese": "vi", "thai": "th", "arabic": "ar",
    "dutch": "nl", "indonesian": "id",
}
LOCALE_CODES = set(LANGUAGES.values()) | {"cs", "da", "fi", "sv", "no", "hu", "ro", "el", "he"}
RUNTIME_JSON = {"runtimeinitializeonloads.json", "scriptingassemblies.json",
                "unityservicesprojectconfiguration.json"}


def runtime_metadata(file: str) -> bool:
    path = "/" + file.replace("\\", "/").lower().lstrip("/")
    return ("/generatedsoundbanks/" in path or path.rsplit("/", 1)[-1] in RUNTIME_JSON | {"performancetestruninfo", "performancetestruninfo.json",
            "linebreaking leading characters", "linebreaking following characters", "thirdpartynotices.txt", "third-party-notices.txt", "steamworks.net.txt", "version.txt", "runtimebuildinformation", "runtimebuildinformation.json", "namedatabase"}
            or "fpstestoutput" in path.rsplit("/", 1)[-1]
            or path.endswith(("/aa/settings.json", "/aa/catalog.json", "/addressableslink/link.xml")))


def locale_code(label: str) -> str:
    label = label.strip().lower().replace("_", "-")
    if label in LANGUAGES:
        return LANGUAGES[label]
    if re.fullmatch(r"[a-z]{2}(?:-[a-z]{2,4}|-[0-9]{3})?", label) and label.split("-")[0] in LOCALE_CODES:
        return label
    match = re.fullmatch(r"english\s*\((en(?:-[a-z]{2})?)\)", label)
    return match[1] if match else ""


def english_locale(locale: str) -> bool:
    return locale == "en" or locale.startswith("en-")


def context_locale(context: str) -> str:
    # Filename/path evidence only, never guess a language from Latin letters.
    for segment in reversed(context.replace("\\", "/").split("/")):
        stem = Path(segment).stem
        direct = locale_code(stem)
        if direct:
            return direct
        for token in re.split(r"[_().\s]+", stem):
            direct = locale_code(token)
            if direct:
                return direct
    return ""


def decode_text(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        # Explicit endian codecs preserve the original BOM at encoding time.
        enc = "utf-16-le" if data[:2] == b"\xff\xfe" else "utf-16-be"
        return data[2:].decode(enc), enc + "-bom"
    if b"\x00" in data[:8192]:
        raise ValueError("Dữ liệu nhị phân hoặc UTF-16 không BOM; cần bộ đọc riêng.")
    return data.decode("utf-8"), "utf-8"


def encode_text(text: str, encoding: str) -> bytes:
    if encoding.endswith("-bom"):
        codec = encoding[:-4]
        return (b"\xff\xfe" if codec == "utf-16-le" else b"\xfe\xff") + text.encode(codec)
    return text.encode(encoding)


def score_text(value: str, context: str = "", key: str = "") -> float:
    value = value.strip()
    if not value or len(value) > 16000 or not any(c.isalpha() for c in value):
        return 0.0
    if any(ord(c) < 32 and c not in "\r\n\t" for c in value):
        return 0.0
    if key.lower() in TECHNICAL_KEYS:
        return 0.0
    if re.search(r"\b(?:Version=\d|Culture=neutral|PublicKeyToken=)", value, re.I):
        return 0.0
    if re.search(r"\.(?:dll|exe)(?:$|\s*,)", value, re.I):
        return 0.0
    if re.fullmatch(r"[0-9a-fA-F-]{16,}", value) or re.match(r"^(https?://|Assets/|Resources/)", value):
        return 0.0
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_0-9-]+)+", value):
        return 0.0  # localization IDs and resource references such as Text.Menu.Start
    if re.fullmatch(r"[\w./\\-]+\.(png|jpg|wav|ogg|mp3|prefab|asset|dll|exe|ttf)", value, re.I):
        return 0.0
    if re.fullmatch(r"[A-Z][A-Z0-9_]*_[A-Z0-9_]+", value):
        return 0.25
    if key.lower() in TEXT_KEYS or LOCALIZATION.search(context):
        return 0.95
    if " " in value or any(ord(c) > 0x2E80 for c in value):
        return 0.8
    return 0.55


def walk_strings(value, path=()):
    if isinstance(value, str):
        yield list(path), value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from walk_strings(child, (*path, key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk_strings(child, (*path, i))


def get_at(value, path):
    for key in path:
        value = value[key]
    return value


def set_at(value, path, replacement):
    if not path:
        return replacement
    parent = get_at(value, path[:-1])
    parent[path[-1]] = replacement
    return value


def load_json(text):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError(f"JSON có key trùng: {key}")
            obj[key] = value
        return obj
    return json.loads(text, object_pairs_hook=pairs)


def infer_kind(name: str, text: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return ext[1:]
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        load_json(text)
        return "json"
    if stripped.startswith("<?xml"):
        return "xml"
    lines = text.splitlines()
    if lines and ("\t" in lines[0] or "," in lines[0]):
        if len(lines) > 1:
            return "tsv" if "\t" in lines[0] else "csv"
    return "txt"


def csv_data(text, kind):
    delimiter = "\t" if kind == "tsv" else ","
    if kind == "csv":
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t").delimiter
        except csv.Error:
            pass
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)), delimiter


def xml_tree(text):
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("XML có DTD/entity cần bộ đọc riêng.")
    return ET.fromstring(text, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))


def extract(text: str, kind: str, file: str, context: str = "") -> list[Entry]:
    entries = []
    context = context or file
    if runtime_metadata(file) or runtime_metadata(context):
        return []
    file_locale = context_locale(context)

    def add(value, locator, label, key="", force=None, locale="", evidence=""):
        locale = locale or file_locale
        if locale and not english_locale(locale):
            return
        confidence = score_text(value, context, key) if force is None else force
        if confidence > 0:
            if english_locale(locale) and confidence >= 0.55:
                confidence = 0.95
            entry = make_entry(file, locator, value, label, confidence)
            entry.source_locale = locale
            entry.detection = evidence or (f"Ngôn ngữ từ tên file: {locale}" if locale else "Chưa xác định ngôn ngữ; cần duyệt")
            entry.enabled = english_locale(locale) and confidence >= 0.75
            if not locale:
                entry.confidence = min(confidence, 0.6)
            entries.append(entry)

    if kind == "json":
        data = load_json(text)
        # Serialized language vectors explicitly label each slot; never guess slot 0.
        labels = data.get("CURRENT_LANGUAGE") if isinstance(data, dict) else None
        if (isinstance(labels, list) and
                sum(bool(v.strip()) for v in labels if isinstance(v, str)) >= 2 and
                all(isinstance(v, list) and len(v) == len(labels) for v in data.values())):
            english = [i for i, label in enumerate(labels)
                       if isinstance(label, str) and english_locale(locale_code(label))]
            for key, values in data.items():
                if key == "CURRENT_LANGUAGE":
                    continue
                for index in english:
                    value = values[index]
                    if isinstance(value, str) and value.strip():
                        add(value, {"path": [key, index]}, f"{key} / {labels[index]}",
                            "text", locale=locale_code(labels[index]),
                            evidence="JSON CURRENT_LANGUAGE xác nhận cột tiếng Anh")
            return entries
        for path, value in walk_strings(data):
            key = str(path[-1]) if path else ""
            if any(str(part).lower() in TECHNICAL_KEYS for part in path):
                continue
            locale = ""
            # Language maps (en/fr/...) and records with an explicit locale.
            node = data
            for part in path:
                if isinstance(node, dict):
                    for field in ("locale", "language", "languageCode"):
                        if isinstance(node.get(field), str):
                            locale = locale_code(node[field]) or node[field].strip().lower().replace("_", "-") or locale
                    if isinstance(part, str) and locale_code(part):
                        # 'id' is a technical key; a lone 'no' may be a UI label.
                        if part.lower() in LANGUAGES or sum(bool(locale_code(str(k))) for k in node) >= 2 or part.lower().startswith("en"):
                            locale = locale_code(part)
                node = node[part]
            add(value, {"path": path}, "/".join(map(str, path)), key, locale=locale,
                evidence=f"Ngôn ngữ trong JSON: {locale}" if locale else "")
    elif kind in ("csv", "tsv", "tsv-raw"):
        rows = [line.rstrip("\r\n").split("\t") for line in text.splitlines(keepends=True)] if kind == "tsv-raw" else csv_data(text, kind)[0]
        if not rows:
            return []
        headers = [h.strip().lower() for h in rows[0]]
        english = [i for i, h in enumerate(headers) if english_locale(locale_code(h))]
        language_columns = [i for i, h in enumerate(headers) if locale_code(h) and h != "id"]
        known_header = bool(english or any(h in TECHNICAL_KEYS | TEXT_KEYS for h in headers))
        for r, row in enumerate(rows):
            if r == 0 and known_header:
                continue
            for c, value in enumerate(row):
                if english and c not in english:
                    continue
                if not english and language_columns:
                    # A table with only non-English languages is not an English source.
                    continue
                key = headers[c] if known_header and c < len(headers) else ""
                add(value, {"row": r, "col": c}, f"Dòng {r+1} / {key or c+1}" + (f" / {row[0]}" if c else ""), key,
                    locale=locale_code(key) if english else "", evidence=f"Cột nguồn: {key}" if english else "")
    elif kind == "xml":
        for i, node in enumerate(xml_tree(text).iter()):
            if not isinstance(node.tag, str):
                continue
            if node.text and node.text.strip():
                add(node.text, {"node": i, "field": "text"}, f"{node.tag}[{i}]", node.tag.split("}")[-1])
            for key, value in node.attrib.items():
                if key.lower() in TEXT_KEYS:
                    add(value, {"node": i, "field": key}, f"{node.tag}[{i}] @{key}", key)
    elif kind in ("ini", "lang"):
        for i, line in enumerate(text.splitlines(keepends=True)):
            if line.lstrip().startswith(("#", ";", "[")):
                continue
            match = re.match(r"^(\s*[^=\r\n]+?\s*=\s*)(.*?)(\r?\n)?$", line)
            if match:
                add(match[2], {"line": i, "prefix": match[1]}, f"Dòng {i+1}: {match[1].strip()}", "text")
    else:
        for i, line in enumerate(text.splitlines(keepends=True)):
            value = line.rstrip("\r\n")
            if kind == "srt" and ("-->" in value or value.strip().isdigit()):
                continue
            if value.lstrip().startswith(("#", "//")):
                continue
            add(value, {"line": i}, f"Dòng {i+1}")
    return entries


def rebuild(text: str, kind: str, entries: list[Entry]) -> str:
    def check(actual, entry):
        if actual != entry.source:
            raise ValueError(f"Text nguồn thay đổi tại {entry.context}.")
        return entry.translation

    newline = "\r\n" if "\r\n" in text else "\n"
    if kind == "json":
        data = load_json(text)
        for e in entries:
            path = e.locator["path"]
            data = set_at(data, path, check(get_at(data, path), e))
        indent_match = re.search(r"\n([ \t]+)\S", text)
        indent = indent_match[1] if indent_match else None
        result = json.dumps(data, ensure_ascii=False, indent=indent)
        return result.replace("\n", newline) + (newline if text.endswith("\n") else "")
    if kind == "tsv-raw":
        lines = text.splitlines(keepends=True)
        for e in entries:
            r, c = e.locator["row"], e.locator["col"]
            line = lines[r]
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            cells = line[:-len(ending) if ending else None].split("\t")
            if any(ch in e.translation for ch in "\t\r\n"):
                raise ValueError("Bảng TSV Unity không chấp nhận tab/xuống dòng mới trong một ô.")
            cells[c] = check(cells[c], e)
            lines[r] = "\t".join(cells) + ending
        return "".join(lines)
    if kind in ("csv", "tsv"):
        rows, delimiter = csv_data(text, kind)
        for e in entries:
            r, c = e.locator["row"], e.locator["col"]
            rows[r][c] = check(rows[r][c], e)
        stream = io.StringIO(newline="")
        csv.writer(stream, delimiter=delimiter, lineterminator=newline).writerows(rows)
        return stream.getvalue()
    if kind == "xml":
        root = xml_tree(text)
        nodes = list(root.iter())
        for e in entries:
            node = nodes[e.locator["node"]]
            field = e.locator["field"]
            if field == "text":
                node.text = check(node.text, e)
            else:
                node.set(field, check(node.get(field), e))
        # XML is returned as Unicode; preserve declaration without changing encoding.
        declaration = re.match(r"\s*(<\?xml[^?]*\?>)", text)
        return (declaration[1] + newline if declaration else "") + ET.tostring(root, encoding="unicode")
    lines = text.splitlines(keepends=True)
    for e in entries:
        i = e.locator["line"]
        line = lines[i]
        suffix = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        prefix = e.locator.get("prefix", "")
        current = line[len(prefix):len(line)-len(suffix) if suffix else len(line)]
        lines[i] = prefix + check(current, e) + suffix
    return "".join(lines)
