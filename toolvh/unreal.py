"""Unreal localization resources, versions 0–3. Preserve engine identity/hash bytes."""
from __future__ import annotations

import struct
from collections import Counter

from .formats import context_locale, english_locale, score_text
from .model import make_entry

MAGIC = bytes.fromhex("0e147475674a03fc4a15909dc3377f1b")


class Reader:
    def __init__(self, data, offset=0, limit=None):
        self.data, self.pos, self.limit = data, offset, len(data) if limit is None else limit

    def take(self, size):
        if size < 0 or self.pos + size > self.limit:
            raise ValueError("LOCRES bị cắt hoặc offset không hợp lệ.")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def number(self, fmt="i"):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))[0]

    def count(self):
        value = self.number()
        if not 0 <= value <= min(1_000_000, self.limit - self.pos):
            raise ValueError("Số mục LOCRES không hợp lệ.")
        return value

    def string(self):
        length = self.number()
        if not length:
            return ""
        raw = self.take(abs(length) * (2 if length < 0 else 1))
        terminator = b"\x00\x00" if length < 0 else b"\x00"
        if not raw.endswith(terminator):
            raise ValueError("FString thiếu ký tự kết thúc.")
        return raw[:-len(terminator)].decode("utf-16-le" if length < 0 else "utf-8")


def fstring(value):
    if "\x00" in value:
        raise ValueError("Bản dịch không được chứa NUL.")
    raw = value.encode("utf-16-le") + b"\x00\x00"
    return struct.pack("<i", -(len(raw) // 2)) + raw


def read_locres(data):
    r = Reader(data)
    modern = data.startswith(MAGIC)
    version = 0
    if modern:
        r.take(16)
        version = r.number("B")
    if version not in (0, 1, 2, 3):
        raise ValueError(f"LOCRES phiên bản {version} chưa hỗ trợ.")
    table_offset, strings = len(data), []
    if version >= 1:
        table_offset = r.number("q")
        if not r.pos <= table_offset <= len(data) - 4:
            raise ValueError("Offset bảng LOCRES không hợp lệ.")
        table = Reader(data, table_offset)
        for _ in range(table.count()):
            strings.append(table.string())
            if version >= 2:
                table.number()  # stored reference count; rebuilt from all keys
        if table.pos != len(data):
            raise ValueError("LOCRES có phần mở rộng chưa hỗ trợ.")
        r.limit = table_offset
    total = r.count() if version >= 2 else None
    entries = []
    for ns_index in range(r.count()):
        if version >= 2:
            r.number("I")  # namespace hash, preserve verbatim
        namespace = r.string()
        for key_index in range(r.count()):
            if version >= 2:
                r.number("I")  # key hash, preserve verbatim
            key = r.string()
            source_hash = r.number("I")
            start = r.pos
            if version >= 1:
                index = r.number()
                if not 0 <= index < len(strings):
                    raise ValueError("LOCRES tham chiếu string index không hợp lệ.")
                value = strings[index]
            else:
                index = None
                value = r.string()
            entries.append(dict(namespace=namespace, key=key, source_hash=source_hash,
                                ns=ns_index, item=key_index, start=start, end=r.pos,
                                index=index, value=value))
    if r.pos != table_offset or (total is not None and total != len(entries)):
        raise ValueError("Cấu trúc/số mục LOCRES không khớp.")
    return version, table_offset, strings, entries


def extract_locres(data, file):
    version, _, _, rows = read_locres(data)
    locale = context_locale(file)
    if locale and not english_locale(locale):
        return [], f"LOCRES v{version}: bỏ qua ngôn ngữ {locale}."
    entries = []
    for row in rows:
        if score_text(row["value"], "localization", "text") <= 0:
            continue
        entry = make_entry(file, {"namespace": row["ns"], "key": row["item"]}, row["value"],
                           f"{row['namespace']} / {row['key']}", 0.95 if locale else 0.6)
        entry.source_locale = locale
        entry.enabled = bool(locale)
        entry.detection = f"Unreal LOCRES v{version}; locale: {locale or 'cần duyệt'}"
        entries.append(entry)
    return entries, f"LOCRES v{version}; giữ namespace, key và hash nguồn; thay bảng ngôn ngữ hiện tại."


def rebuild_locres(data, entries):
    if not entries:
        return data
    version, table_offset, strings, rows = read_locres(data)
    edits = {}
    for entry in entries:
        identity = (entry.locator["namespace"], entry.locator["key"])
        if identity in edits:
            raise ValueError("LOCRES có vị trí bản dịch trùng.")
        edits[identity] = entry
    replacements, indices = [], []
    for row in rows:
        entry = edits.pop((row["ns"], row["item"]), None)
        if entry and row["value"] != entry.source:
            raise ValueError("Text nguồn LOCRES đã thay đổi.")
        if version == 0:
            if entry:
                replacements.append((row["start"], row["end"], fstring(entry.translation)))
        else:
            index = row["index"]
            if entry:
                # Separate a shared string when only one key was translated.
                index = len(strings)
                strings.append(entry.translation)
                replacements.append((row["start"], row["end"], struct.pack("<i", index)))
            indices.append(index)
    if edits:
        raise ValueError("Không tìm thấy vị trí LOCRES trong file nguồn.")
    prefix = data[:table_offset]
    for start, end, value in reversed(replacements):
        prefix = prefix[:start] + value + prefix[end:]
    if version == 0:
        result = prefix
    else:
        counts = Counter(indices)
        table = bytearray(struct.pack("<i", len(strings)))
        for index, value in enumerate(strings):
            table.extend(fstring(value))
            if version >= 2:
                table.extend(struct.pack("<i", counts[index]))
        result = prefix + table
    read_locres(result)  # verify serialization before any game write
    return bytes(result)
