from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from .formats import (LOCALIZATION, TEXT_KEYS, english_locale, extract, get_at, infer_kind,
                      locale_code, rebuild, score_text, set_at, walk_strings)
from .model import Entry, make_entry


def load_unity(data: bytes):
    try:
        import UnityPy
    except ImportError as exc:
        raise RuntimeError("Chưa cài UnityPy. Chạy pip install -r requirements.txt.") from exc
    env = UnityPy.Environment()
    # UnityPy uses Python's randomized bytes hash for unnamed streams. A fixed
    # root name keeps object locators stable across process restarts and edits.
    env.file = env.load_file(data, name="__root__")
    return env


def object_key(obj):
    return str(obj.assets_file.name), obj.path_id


def string_table_locale(tree):
    """Recognize localized table schema; MonoScript distinguishes String/AssetTable."""
    locale = tree.get("m_LocaleId")
    rows = tree.get("m_TableData")
    if not isinstance(locale, dict) or not isinstance(locale.get("m_Code"), str):
        return None
    if not isinstance(rows, list) or "m_SharedData" not in tree:
        return None
    if not all(isinstance(row, dict) and isinstance(row.get("m_Id"), int)
               and isinstance(row.get("m_Localized"), str) for row in rows):
        return None
    return locale["m_Code"].strip().lower().replace("_", "-")


def extract_string_table(tree, file, container, path_id, script_type=None):
    locale = string_table_locale(tree)
    if locale is None:
        return None
    if not english_locale(locale):
        return []
    if script_type is not None and script_type != ("UnityEngine.Localization.Tables", "StringTable"):
        return []
    name = str(tree.get("m_Name", "StringTable"))
    entries = []
    for index, row in enumerate(tree["m_TableData"]):
        value = row["m_Localized"]
        if score_text(value, name, "text") <= 0 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            continue
        # Keep the historical locator shape so existing translations can be matched.
        locator = {"container": container, "object": path_id, "type": "MonoBehaviour",
                   "path": ["m_TableData", index, "m_Localized"]}
        entry = make_entry(file, locator, value, f"{name} / English ({locale}) / ID {row['m_Id']}", 0.99)
        entry.source_locale = locale
        entry.enabled = script_type == ("UnityEngine.Localization.Tables", "StringTable")
        entry.detection = ("Unity StringTable + locale=" + locale if entry.enabled
                           else "Bảng locale=" + locale + "; chưa xác nhận MonoScript StringTable")
        entries.append(entry)
    return entries


def script_reference(obj, tree, file):
    pointer = tree.get("m_Script", {})
    file_id, path_id = pointer.get("m_FileID", 0), pointer.get("m_PathID", 0)
    if file_id == 0:
        asset = str(obj.assets_file.name)
        return (file if asset == "__root__" else asset.lower(), path_id)
    if 0 < file_id <= len(obj.assets_file.externals):
        external = obj.assets_file.externals[file_id - 1].path.replace("\\", "/").rsplit("/", 1)[-1]
        return (external.lower(), path_id)
    return None


def collect_scripts(env, file, registry):
    for obj in env.objects:
        if obj.type.name == "MonoScript":
            tree = obj.parse_as_dict()
            asset = str(obj.assets_file.name)
            key = (file if asset == "__root__" else asset.lower(), obj.path_id)
            registry[key] = (tree.get("m_Namespace"), tree.get("m_ClassName"))


def resolve_table_entries(entries, registry):
    result = []
    for entry in entries:
        if hasattr(entry, "_table_script"):
            script_type = registry.get(entry._table_script)
            if script_type is not None and script_type != ("UnityEngine.Localization.Tables", "StringTable"):
                continue
            if script_type == ("UnityEngine.Localization.Tables", "StringTable"):
                entry.enabled = True
                entry.detection = "Unity StringTable + locale=" + entry.source_locale
            del entry._table_script
        result.append(entry)
    return result


def extract_unity(data: bytes, file: str, cancelled=lambda: False, script_registry=None):
    env = load_unity(data)
    registry = script_registry if script_registry is not None else {}
    collect_scripts(env, file, registry)
    entries, notes = [], []
    skipped_mono = 0
    for obj in env.objects:
        if cancelled():
            raise InterruptedError("Đã dừng quét.")
        if obj.type.name not in ("TextAsset", "MonoBehaviour"):
            continue
        container, path_id = object_key(obj)
        if obj.type.name == "MonoBehaviour" and not obj.serialized_type.node:
            skipped_mono += 1
            continue
        try:
            if obj.type.name == "TextAsset":
                asset = obj.parse_as_object()
                name, text = asset.m_Name, asset.m_Script
                if not text or "\x00" in text[:4096]:
                    continue
                kind = infer_kind(name, text)
                # Overcooked localization uses literal, unquoted tab-separated cells.
                if kind == "tsv" and name.startswith("Localization"):
                    kind = "tsv-raw"
                for e in extract(text, kind, file, name):
                    if any(0xD800 <= ord(c) <= 0xDFFF for c in e.source):
                        continue
                    locator = {"container": container, "object": path_id, "type": "TextAsset",
                               "format": kind, "inner": e.locator, "name": name}
                    entry = make_entry(file, locator, e.source, f"{name} / {e.context}", e.confidence)
                    entry.enabled = e.enabled
                    entry.source_locale, entry.detection = e.source_locale, e.detection
                    if name.startswith("Localization") and " - " in name and name.rsplit(" - ", 1)[1] not in ("Shared", "PC"):
                        entry.enabled = False
                    entries.append(entry)
            else:
                tree = obj.parse_as_dict()
                name = str(tree.get("m_Name", "MonoBehaviour"))
                reference = script_reference(obj, tree, file)
                table = extract_string_table(tree, file, container, path_id, registry.get(reference))
                if table is not None:
                    for entry in table:
                        entry._table_script = reference
                    entries.extend(table)
                    locale = string_table_locale(tree)
                    notes.append(f"Bảng localization {name}: locale={locale}; {len(table)} câu ứng viên tiếng Anh.")
                    continue
                for path, value in walk_strings(tree):
                    key = str(path[-1]) if path else ""
                    # UI text defaults are candidates for review. Object names,
                    # localization key maps, font metadata and service config are not.
                    if key.lower() not in TEXT_KEYS - {"name", "value", "content", "translation"}:
                        continue
                    confidence = score_text(value, name, key)
                    if confidence <= 0 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
                        continue
                    locator = {"container": container, "object": path_id, "type": "MonoBehaviour", "path": path}
                    entry = make_entry(file, locator, value, f"{name} / {'/'.join(map(str, path))}", confidence)
                    # MonoBehaviour strings may be runtime keys even when they look like prose.
                    entry.enabled = False  # require review: serialized UI defaults may be localization references
                    entry.confidence = min(entry.confidence, 0.6)
                    entry.detection = "Text UI chưa xác định ngôn ngữ; cần duyệt"
                    entries.append(entry)
        except Exception as exc:
            notes.append(f"Object {path_id}: {str(exc)[:160]}")
    if skipped_mono:
        notes.append(f"{skipped_mono} MonoBehaviour thiếu type tree; chưa đọc text bên trong.")
    return entries, " | ".join(notes[:12])


def rebuild_unity(data: bytes, entries: list[Entry]) -> bytes:
    env = load_unity(data)
    groups = defaultdict(list)
    for e in entries:
        groups[(e.locator["container"], e.locator["object"])].append(e)
    for obj in env.objects:
        key = object_key(obj)
        edits = groups.pop(key, None)
        if not edits:
            continue
        if edits[0].locator["type"] == "TextAsset":
            asset = obj.parse_as_object()
            inner = [replace(e, locator=e.locator["inner"]) for e in edits]
            asset.m_Script = rebuild(asset.m_Script, edits[0].locator["format"], inner)
            asset.save()
        else:
            tree = obj.parse_as_dict()
            for e in edits:
                path = e.locator["path"]
                if get_at(tree, path) != e.source:
                    raise ValueError(f"Text nguồn thay đổi: {e.context}")
                tree = set_at(tree, path, e.translation)
            obj.patch(tree)
    if groups:
        raise ValueError("Không tìm thấy object Unity trong dữ liệu nguồn.")
    if env.file is None:
        raise ValueError("Unity container nhiều file chưa được hỗ trợ ghi lại.")
    result = env.file.save()
    # Verify each edited value by reopening the emitted asset, before publishing it.
    verify_env = load_unity(result)
    objects = {object_key(obj): obj for obj in verify_env.objects}
    for key, edits in _verification_groups(entries).items():
        obj = objects.get(key)
        if obj is None:
            raise ValueError("Object Unity biến mất sau khi ghi.")
        if edits[0].locator["type"] == "TextAsset":
            asset = obj.parse_as_object()
            # Rebuild checks every exact locator against the translated source;
            # do not rerun language heuristics against Vietnamese for verification.
            rebuild(asset.m_Script, edits[0].locator["format"],
                    [replace(e, source=e.translation, locator=e.locator["inner"]) for e in edits])
        else:
            tree = obj.parse_as_dict()
            for e in edits:
                if get_at(tree, e.locator["path"]) != e.translation:
                    raise ValueError(f"Kiểm tra asset sau khi ghi thất bại: {e.context}")
    return result


def _verification_groups(entries):
    groups = defaultdict(list)
    for entry in entries:
        groups[(entry.locator["container"], entry.locator["object"])].append(entry)
    return groups
