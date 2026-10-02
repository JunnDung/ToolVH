"""Verified Ori WotW TranslatedMessageProvider schema; no heuristic byte replacement."""
import struct

from .model import make_entry

SCHEMA = "moon-wisp-2018-21-v1"
PROPERTIES_HASH = bytes.fromhex("5552dc23a6e13d7725f9b1fabb1ee952")
LOCALES = ("en", "fr", "it", "de", "es", "ja", "pt", "zh", "ru", "zh-tw", "cs",
           "da", "nl", "fi", "hu", "ko", "no", "pl", "es-mx", "sv", "tr")


def script_matches(tree):
    properties = tree.get("m_PropertiesHash", {})
    return (tree.get("m_AssemblyName") == "__mainWisp.dll"
            and tree.get("m_ClassName") == "TranslatedMessageProvider"
            and tree.get("m_Namespace") == ""
            and [properties.get(f"bytes[{i}]") for i in range(16)] == list(PROPERTIES_HASH))


def parse_provider(data, header_only=False):
    if len(data) < 32:
        raise ValueError("Moon provider bị cắt.")
    file_id, script_id = struct.unpack_from("<iq", data, 16)
    position = 28

    def integer():
        nonlocal position
        if position + 4 > len(data):
            raise ValueError("Moon provider bị cắt.")
        value = struct.unpack_from("<i", data, position)[0]
        position += 4
        return value

    def string():
        nonlocal position
        start = position
        length = integer()
        if not 0 <= length <= min(1_000_000, len(data) - position):
            raise ValueError("Moon provider có độ dài string không hợp lệ.")
        value = data[position:position + length].decode("utf-8")
        if "\x00" in value or any(ord(c) < 32 and c not in "\r\n\t" for c in value):
            raise ValueError("Moon provider có string điều khiển không hợp lệ.")
        position = (position + length + 3) & ~3
        if position > len(data):
            raise ValueError("Moon provider thiếu padding.")
        return {"value": value, "start": start, "end": position}

    name = string()["value"]
    result = dict(name=name, file_id=file_id, script_id=script_id, rows=[])
    if header_only:
        return result
    count = integer()
    if not 0 <= count <= min(10000, (len(data) - position) // 124):
        raise ValueError("Moon provider có số message không hợp lệ.")
    for _ in range(count):
        result["rows"].append([string() for _ in LOCALES])
        # Four serialized scalar fields + 16-byte GUID + final scalar.
        if position + 40 > len(data) or struct.unpack_from("<i", data, position + 16)[0] != 16:
            raise ValueError("Moon provider không khớp schema GUID/metadata.")
        position += 40
    if position != len(data):
        raise ValueError("Moon provider có phần mở rộng chưa hỗ trợ.")
    return result


def extract_provider(data, file, container, path_id):
    provider = parse_provider(data)
    entries = []
    for index, row in enumerate(provider["rows"]):
        source = row[0]["value"]
        if not source.strip() or not any(c.isalpha() for c in source):
            continue
        locator = {"container": container, "object": path_id, "type": "MoonTranslatedMessageProvider",
                   "schema": SCHEMA, "row": index, "name": provider["name"],
                   "script_file": provider["file_id"], "script_id": provider["script_id"]}
        entry = make_entry(file, locator, source, f"{provider['name']} / English / message {index + 1}", 0.99)
        entry.source_locale = "en"
        entry.detection = "Moon TranslatedMessageProvider: MonoScript + assembly + fingerprint; trường English"
        entries.append(entry)
    return entries


def rebuild_provider(data, entries):
    provider = parse_provider(data)
    replacements, seen = [], set()
    for entry in entries:
        locator = entry.locator
        index = locator["row"]
        if (locator.get("schema") != SCHEMA or locator.get("name") != provider["name"]
                or locator.get("script_file") != provider["file_id"]
                or locator.get("script_id") != provider["script_id"]
                or not isinstance(index, int) or not 0 <= index < len(provider["rows"]) or index in seen):
            raise ValueError("Vị trí/schema Moon provider không hợp lệ.")
        seen.add(index)
        field = provider["rows"][index][0]
        if field["value"] != entry.source:
            raise ValueError("Text nguồn Moon provider đã thay đổi.")
        if "\x00" in entry.translation:
            raise ValueError("Bản dịch không được chứa NUL.")
        raw = entry.translation.encode("utf-8")
        replacement = struct.pack("<i", len(raw)) + raw + b"\x00" * (-len(raw) % 4)
        replacements.append((field["start"], field["end"], replacement))
    result = data
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    verified = parse_provider(result)
    for entry in entries:
        if verified["rows"][entry.locator["row"]][0]["value"] != entry.translation:
            raise ValueError("Kiểm tra Moon provider sau khi ghi thất bại.")
    return result
