"""Godot text resources and standalone unencrypted PCK v1/v2/v3.

Pack edits append payloads and change only fixed-size directory fields. No script
execution, resource conversion or extraction of arbitrary archive paths to disk.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import struct
from collections import defaultdict
from pathlib import PurePosixPath

from .formats import (TEXT_EXTENSIONS, context_locale, decode_text, encode_text,
                      english_locale, extract, rebuild, score_text)
from .model import make_entry

RESOURCE_EXTENSIONS = {".tscn", ".tres", ".translation", ".po", ".mo"}
QUOTED = r'"(?:[^"\\]|\\.)*"'
PROPERTY = re.compile(r'(?m)^(text|placeholder_text|tooltip_text)\s*=\s*(' + QUOTED + r')\s*$')


def _entry(file, locator, source, label, locale):
    if locale and not english_locale(locale):
        return None
    if score_text(source, "localization", "text") <= 0:
        return None
    result = make_entry(file, locator, source, label, 0.95 if locale else 0.6)
    result.source_locale = locale
    result.enabled = english_locale(locale)
    result.detection = f"Godot; locale: {locale or 'chưa xác định, cần duyệt'}"
    return result


def po_messages(text):
    """Singular PO messages with source spans. Preserve plural/fuzzy/obsolete blocks."""
    results = []
    offset = 0
    for block in re.split(r'(\r?\n[ \t]*\r?\n)', text):
        fields, spans = {}, {}
        active = None
        cursor = offset
        skip = bool(re.search(r'^#~|^#,.*\bfuzzy\b|^msgid_plural\b', block, re.M))
        for line in block.splitlines(keepends=True):
            value = re.match(r'^(msgctxt|msgid|msgstr)\s+(' + QUOTED + r')\s*$', line)
            continuation = re.match(r'^(' + QUOTED + r')\s*$', line)
            if value:
                active = value[1]
                if active in fields:
                    raise ValueError("PO có trường lặp hoặc thiếu dòng phân cách.")
                fields[active] = ast.literal_eval(value[2])
                spans[active] = [cursor, cursor + len(line)]
            elif continuation and active:
                fields[active] += ast.literal_eval(continuation[1])
                spans[active][1] = cursor + len(line)
            elif line.strip() and not line.startswith("#"):
                active = None
                skip = True
            cursor += len(line)
        if not skip and "msgid" in fields and "msgstr" in fields:
            results.append((fields, spans))
        offset += len(block)
    return results


def read_mo(data):
    if data[:4] == b"\xde\x12\x04\x95":
        endian = "<"
    elif data[:4] == b"\x95\x04\x12\xde":
        endian = ">"
    else:
        raise ValueError("MO sai magic.")
    if len(data) < 28:
        raise ValueError("MO bị cắt.")
    _, revision, count, orig, trans, _, _ = struct.unpack_from(endian + "7I", data)
    if revision != 0 or count > 1_000_000:
        raise ValueError("MO phiên bản/số mục chưa hỗ trợ.")
    tables = []
    for start in (orig, trans):
        if start < 28 or start + count * 8 > len(data):
            raise ValueError("MO offset bảng không hợp lệ.")
        table = []
        for i in range(count):
            size, offset = struct.unpack_from(endian + "2I", data, start + i * 8)
            if offset + size >= len(data) or data[offset + size] != 0:
                raise ValueError("MO offset text không hợp lệ.")
            table.append(data[offset:offset + size].decode("utf-8"))
        tables.append(table)
    return endian, tables[0], tables[1]


def _header_locale(header, fallback):
    charset = re.search(r'charset=([^\s;\\]+)', header, re.I)
    if charset and charset[1].lower() not in ("utf-8", "utf8"):
        raise ValueError("Chỉ hỗ trợ gettext charset UTF-8.")
    language = re.search(r'^Language:\s*([^\s]+)', header, re.M | re.I)
    return language[1].lower().replace("_", "-") if language else fallback


def extract_resource(data, kind, file):
    entries = []
    locale = context_locale(file)
    if kind == "mo":
        _, originals, translated = read_mo(data)
        header = translated[originals.index("")] if "" in originals else ""
        locale = _header_locale(header, locale)
        for i, (key, value) in enumerate(zip(originals, translated)):
            if not key or "\x00" in key or "\x00" in value:
                continue  # preserve plural strings, no singular translation guess
            entry = _entry(file, {"index": i}, value or key.split("\x04")[-1], key, locale)
            if entry:
                entries.append(entry)
    else:
        text, _ = decode_text(data)
        if kind == "po":
            messages = po_messages(text)
            header = next((f["msgstr"] for f, _ in messages if not f["msgid"]), "")
            locale = _header_locale(header, locale)
            for i, (fields, _) in enumerate(messages):
                if not fields["msgid"]:
                    continue
                entry = _entry(file, {"message": i}, fields["msgstr"] or fields["msgid"],
                               fields.get("msgctxt", "") + " / " + fields["msgid"], locale)
                if entry:
                    entries.append(entry)
        else:
            if text.startswith(("RSRC", "RSCC")):
                raise ValueError("Tài nguyên Godot binary/OptimizedTranslation cần bộ đọc riêng.")
            if kind == "translation" and '[gd_resource type="Translation"' not in text:
                raise ValueError("Chỉ hỗ trợ Translation dạng text; OptimizedTranslation/binary chưa hỗ trợ.")
            if '[gd_resource type="Translation"' in text:
                language = re.search(r'^locale\s*=\s*(' + QUOTED + ')', text, re.M)
                if language:
                    locale = json.loads(language[1]).lower().replace("_", "-")
                match = re.search(r'^messages\s*=\s*\{\s*((?:&?' + QUOTED + r'\s*:\s*&?' + QUOTED + r'\s*,?\s*)*)\}', text, re.M)
                if match:
                    body = match[1]
                    for pair in re.finditer('&?(' + QUOTED + r')\s*:\s*&?(' + QUOTED + ')', body):
                        start, end = match.start(1) + pair.start(2), match.start(1) + pair.end(2)
                        entry = _entry(file, {"start": start, "end": end}, json.loads(pair[2]),
                                       json.loads(pair[1]), locale)
                        if entry:
                            entries.append(entry)
            else:
                for match in PROPERTY.finditer(text):
                    entry = _entry(file, {"start": match.start(2), "end": match.end(2)},
                                   json.loads(match[2]), f"{match[1]} / dòng {text.count(chr(10), 0, match.start()) + 1}", locale)
                    if entry:
                        entries.append(entry)
    return entries, "Godot: thay ngôn ngữ nguồn; mục thiếu bằng chứng tiếng Anh cần duyệt."


def rebuild_resource(data, kind, entries):
    if not entries:
        return data
    if kind == "mo":
        endian, originals, translated = read_mo(data)
        for entry in entries:
            i = entry.locator["index"]
            if (translated[i] or originals[i].split("\x04")[-1]) != entry.source:
                raise ValueError("Text MO nguồn đã thay đổi.")
            translated[i] = entry.translation
        result = bytearray(struct.pack(endian + "7I", 0x950412DE, 0, len(originals), 28,
                                       28 + len(originals) * 8, 0, 0))
        result.extend(b"\x00" * (len(originals) * 16))
        for table, values in enumerate((originals, translated)):
            for i, value in enumerate(values):
                encoded = value.encode("utf-8")
                struct.pack_into(endian + "2I", result, 28 + table * len(originals) * 8 + i * 8,
                                 len(encoded), len(result))
                result.extend(encoded + b"\x00")
        read_mo(result)
        return bytes(result)
    text, encoding = decode_text(data)
    replacements = []
    messages = po_messages(text) if kind == "po" else None
    for entry in entries:
        if kind == "po":
            fields, spans = messages[entry.locator["message"]]
            actual = fields["msgstr"] or fields["msgid"]
            start, end = spans["msgstr"]
            newline = "\r\n" if "\r\n" in text else "\n"
            new = "msgstr " + json.dumps(entry.translation, ensure_ascii=False) + newline
        else:
            start, end = entry.locator["start"], entry.locator["end"]
            actual = json.loads(text[start:end])
            new = json.dumps(entry.translation, ensure_ascii=False)
        if actual != entry.source:
            raise ValueError("Text Godot nguồn đã thay đổi.")
        replacements.append((start, end, new))
    boundary = len(text)
    for start, end, new in sorted(replacements, reverse=True):
        if not 0 <= start <= end <= boundary:
            raise ValueError("Vị trí text Godot trùng hoặc không hợp lệ.")
        text = text[:start] + new + text[end:]
        boundary = start
    return encode_text(text, encoding)


def read_pack(data):
    from .unreal import Reader
    r = Reader(data)
    if r.take(4) != b"GDPC":
        raise ValueError("PCK sai magic; PCK nhúng trong EXE chưa hỗ trợ.")
    version = r.number("I")
    if version not in (1, 2, 3):
        raise ValueError(f"PCK v{version} chưa hỗ trợ.")
    r.take(12)  # engine major/minor/patch
    flags, base = 0, 0
    if version >= 2:
        flags, base = r.number("I"), r.number("Q")
        if flags & ~2:
            raise ValueError("PCK mã hóa hoặc sparse bundle chưa hỗ trợ.")
    if version == 3:
        directory = r.number("Q")
        if not 104 <= directory <= len(data) - 4:
            raise ValueError("PCK offset thư mục không hợp lệ.")
        r.pos = directory
    else:
        r.take(64)
        directory = r.pos
    count = r.count()
    rows, names = [], set()
    for _ in range(count):
        raw = r.take(r.number("I"))
        name = raw.rstrip(b"\x00").decode("utf-8")
        normalized = name.removeprefix("res://")
        path = PurePosixPath(normalized)
        if not normalized or "\x00" in name or "\\" in name or ":" in normalized or path.is_absolute() or ".." in path.parts or normalized in names:
            raise ValueError("PCK có tên file không hợp lệ/trùng.")
        names.add(normalized)
        metadata = r.pos
        offset, size = r.number("Q") + base, r.number("Q")
        md5 = r.take(16)
        file_flags = r.number("I") if version >= 2 else 0
        if not file_flags and (offset < 84 or offset + size > len(data)):
            raise ValueError("PCK offset/kích thước file không hợp lệ.")
        rows.append(dict(name=name, path=normalized, offset=offset, size=size,
                         md5=md5, flags=file_flags, metadata=metadata))
    for row in rows:
        if not row["flags"] and row["size"] and row["offset"] < r.pos and row["offset"] + row["size"] > directory:
            raise ValueError("PCK payload chồng lên thư mục.")
    return base, rows


def _member_kind(row, names):
    suffix = PurePosixPath(row["path"]).suffix.lower()
    if row["flags"]:
        return ""
    if row["path"] + ".import" in names or row["path"] + ".remap" in names:
        return ""  # source file is remapped to an imported resource at runtime
    return suffix[1:] if suffix in TEXT_EXTENSIONS | RESOURCE_EXTENSIONS else ""


def _member_data(data, row):
    raw = data[row["offset"]:row["offset"] + row["size"]]
    if hashlib.md5(raw).digest() != row["md5"]:
        raise ValueError(f"PCK MD5 không khớp: {row['name']}")
    return raw


def extract_pack(data, file, cancelled=lambda: False):
    _, rows = read_pack(data)
    names = {r["path"] for r in rows}
    entries, failed, skipped = [], [], 0
    unavailable = []
    for row in rows:
        if cancelled():
            raise InterruptedError("Đã dừng quét.")
        kind = _member_kind(row, names)
        if not kind:
            skipped += 1
            if row["flags"] or "translation" in row["path"].lower() or row["path"] + ".import" in names or row["path"] + ".remap" in names:
                unavailable.append(row["name"])
            continue
        try:
            raw = _member_data(data, row)
            if "." + kind in RESOURCE_EXTENSIONS:
                children, _ = extract_resource(raw, kind, row["path"])
            else:
                text, _ = decode_text(raw)
                children = extract(text, kind, row["path"])
            for child in children:
                entry = make_entry(file, {"member": row["name"], "kind": kind, "inner": child.locator},
                                   child.source, f"{row['name']} / {child.context}", child.confidence)
                entry.source_locale, entry.enabled, entry.detection = child.source_locale, child.enabled, child.detection
                entries.append(entry)
        except (ValueError, UnicodeError) as exc:
            failed.append(f"{row['name']}: {exc}")
    note = f"Godot PCK: {len(rows)} file; {skipped} file binary/mã hóa/remap không đọc text."
    if unavailable:
        note += " Vị trí chưa hỗ trợ: " + ", ".join(unavailable[:8]) + "."
    if failed:
        note += " Tài nguyên chưa hỗ trợ: " + " | ".join(failed[:8])
    return entries, note


def rebuild_pack(data, entries):
    from dataclasses import replace
    base, rows = read_pack(data)
    names = {r["path"] for r in rows}
    groups = defaultdict(list)
    for entry in entries:
        groups[entry.locator["member"]].append(entry)
    result = bytearray(data)
    for row in rows:
        group = groups.pop(row["name"], [])
        if not group:
            continue
        kind = _member_kind(row, names)
        if not kind or any(e.locator["kind"] != kind for e in group):
            raise ValueError("PCK member/remap/mã hóa không hỗ trợ ghi.")
        raw = _member_data(data, row)
        children = [replace(e, locator=e.locator["inner"]) for e in group]
        if "." + kind in RESOURCE_EXTENSIONS:
            modified = rebuild_resource(raw, kind, children)
        else:
            text, encoding = decode_text(raw)
            modified = encode_text(rebuild(text, kind, children), encoding)
        result.extend(b"\x00" * (-len(result) % 16))
        offset = len(result)
        if offset < base:
            raise ValueError("PCK file base vượt cuối file.")
        result.extend(modified)
        struct.pack_into("<QQ", result, row["metadata"], offset - base, len(modified))
        result[row["metadata"] + 16:row["metadata"] + 32] = hashlib.md5(modified).digest()
    if groups:
        raise ValueError("Không tìm thấy PCK member.")
    read_pack(result)
    return bytes(result)
