from __future__ import annotations

import os
import re
import struct
from pathlib import Path

from .formats import TEXT_EXTENSIONS, decode_text, extract, runtime_metadata
from .model import FileRecord, Project, digest
from .unity import extract_unity, resolve_table_entries
from .godot import RESOURCE_EXTENSIONS, extract_pack, extract_resource
from .unreal import extract_locres
from . import rpgmaker, renpy, pak

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "mono", "managed"}
BINARY_EXTENSIONS = {".dat", ".bin", ".pak", ".pck", ".rpa", ".rpyc", ".db", ".locres", ".uasset", ".bytes", ".utoc", ".ucas"}
UNITY_EXTENSIONS = {".assets", ".bundle", ".unity3d", ".assetbundle"}


def carry_translations(previous, current):
    """Retain exact-source edits on rescan, but use the corrected selection rules."""
    if previous is None or Path(previous.root).resolve() != Path(current.root).resolve():
        return 0
    current.glossary = dict(previous.glossary)
    current.instructions = previous.instructions
    current.preserve_names = previous.preserve_names
    current.protected_names = list(previous.protected_names)
    current.game_context = previous.game_context
    current.google_web_cache = dict(previous.google_web_cache)
    current.font_patches = list(previous.font_patches)
    old = {entry.id: entry for entry in previous.entries}
    from collections import defaultdict
    old_context, new_context = defaultdict(list), defaultdict(list)
    def identity(entry):
        return entry.file, entry.source, entry.context, entry.source_locale
    for entry in previous.entries:
        if entry.translation:
            old_context[identity(entry)].append(entry)
    for entry in current.entries:
        new_context[identity(entry)].append(entry)
    carried = 0
    for entry in current.entries:
        match = old.get(entry.id)
        if not (match and match.source == entry.source and match.locator == entry.locator and match.translation):
            candidates = old_context[identity(entry)]
            match = candidates[0] if len(candidates) == 1 and len(new_context[identity(entry)]) == 1 else None
        if match and match.translation:
            entry.translation = match.translation
            carried += 1
    return carried


def is_unity(path: Path, header: bytes) -> bool:
    return (header.startswith((b"UnityFS\x00", b"UnityWeb\x00", b"UnityRaw\x00"))
            or path.suffix.lower() in UNITY_EXTENSIONS
            or path.name == "globalgamemanagers" or bool(re.fullmatch(r"level\d+", path.name)))


def scan(root: str | Path, progress=lambda text: None, cancelled=lambda: False,
         deep=False, max_mb=256) -> Project:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Thư mục game không tồn tại.")
    project = Project(str(root))
    candidates = []
    engines = set()
    scripts = {}

    def walk_error(error):
        project.files.append(FileRecord(str(Path(error.filename).relative_to(root)), "error", note=str(error)))

    for directory, folders, files in os.walk(root, onerror=walk_error, followlinks=False):
        if cancelled():
            raise InterruptedError("Đã dừng quét.")
        folders[:] = [d for d in folders if d.lower() not in SKIP_DIRS and not (Path(directory) / d).is_symlink()]
        if any(d.endswith("_Data") for d in folders):
            engines.add("Unity")
        for filename in files:
            path = Path(directory) / filename
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            ext = path.suffix.lower()
            if filename.lower() == "unityplayer.dll":
                engines.add("Unity")
            if filename.lower() in ("rpg_core.js", "rmmz_core.js"):
                engines.add("RPG Maker MV/MZ")
            if ext in (".rpa", ".rpy", ".rpyc"):
                engines.add("Ren'Py (nhận diện)")
            if ext in (".uasset", ".locres", ".utoc", ".ucas", ".uproject"):
                engines.add("Unreal Engine")
            if ext == ".pak":
                engines.add("PAK (Unreal hoặc engine khác; cần xác minh)")
            if ext in (".pck", ".tscn", ".tres", ".godot", ".translation"):
                engines.add("Godot")
            if ext in (".godot", ".uproject"):
                continue
            if ext not in TEXT_EXTENSIONS | UNITY_EXTENSIONS | BINARY_EXTENSIONS | RESOURCE_EXTENSIONS | {".rpy", ".xnb", ".vpk", ".loc2"} and filename.lower() != "scripts.zip" and ext != "":
                continue
            rel = path.relative_to(root).as_posix()
            if ext in (".xnb", ".vpk", ".loc2") or filename.lower() == "scripts.zip":
                notes = {
                    ".xnb": "Tài nguyên XNB: có thể chứa text, ảnh hoặc âm thanh. Cần adapter theo ContentTypeReader; chưa đọc/ghi text. Kiểm tra Content/Strings và Characters/Dialogue nếu game dùng cấu trúc này.",
                    ".vpk": "Container VPK: cần bộ đọc directory và các chunk cùng bộ. Text thường cần tìm trong resource/ và bảng ngôn ngữ; chưa đọc/ghi VPK.",
                    ".loc2": "Bảng ngôn ngữ LOC2 biên dịch; chưa đọc/ghi. Nếu có *.string_table.xml, cần bộ biên dịch của game để đưa XML đã sửa vào runtime.",
                    ".zip": "scripts.zip có thể chứa script và bảng ngôn ngữ. Chưa hỗ trợ dịch Lua/đóng lại gói script; không coi chuỗi code là lời thoại."
                }
                project.files.append(FileRecord(rel, ext[1:], size=path.stat().st_size, note=notes[ext]))
                continue
            if ext in TEXT_EXTENSIONS | RESOURCE_EXTENSIONS and any(Path(str(path) + suffix).exists() for suffix in (".import", ".remap")):
                project.files.append(FileRecord(rel, "metadata", note="Godot import/remap: file nguồn không được dùng trực tiếp; cần đọc tài nguyên đích."))
                continue
            if (any(part.lower().endswith('-gse') or part.lower() == 'steam_settings' for part in Path(rel).parts[:-1])
                    or path.name.lower() in {'manifest_ufsfiles_win64.txt', 'manifest_nonufsfiles_win64.txt', 'notices.txt'}):
                project.files.append(FileRecord(rel, "metadata", note="Dữ liệu launcher/achievement/manifest phụ trợ; không phải localization trong game."))
                continue
            if runtime_metadata(rel):
                project.files.append(FileRecord(rel, "metadata", note="Cấu hình runtime Unity/Addressables; không phải text game."))
                continue
            try:
                with path.open("rb") as stream:
                    header = stream.read(64)
                unity = is_unity(path, header)
                if not unity and ext not in TEXT_EXTENSIONS | BINARY_EXTENSIONS | RESOURCE_EXTENSIONS | {".rpy"}:
                    continue
                size = path.stat().st_size
                if ext in ('.utoc', '.ucas'):
                    if ext == '.utoc':
                        with path.open('rb') as stream:
                            toc = stream.read(144)
                        if len(toc) < 144 or toc[:16] != b'-==--==--==--==-':
                            note = 'IoStore UTOC header không hợp lệ/bị cắt.'
                        else:
                            version = toc[16]
                            header_size, count, blocks = struct.unpack_from('<III', toc, 20)
                            flags = toc[80]
                            note = (f'IoStore v{version}: {count:,} chunk, {blocks:,} block; '
                                    f'{"mã hóa" if flags & 2 else "không mã hóa"}. '
                                    'Chưa đọc/ghi FText hoặc StringTable trong IoStore; cần adapter package theo phiên bản UE. '
                                    'Không tính chuỗi nhị phân thành text dịch được.')
                            if header_size < 144 or header_size > size:
                                note = 'IoStore UTOC header size không hợp lệ.'
                        if not path.with_suffix('.ucas').exists():
                            note += ' Thiếu file UCAS cùng tên.'
                    else:
                        note = 'Payload IoStore; xem UTOC cùng tên. Chưa hỗ trợ đọc/ghi text trong asset; không quét chuỗi nhị phân ngẫu nhiên.'
                        if not path.with_suffix('.utoc').exists():
                            note += ' Thiếu file UTOC cùng tên.'
                    project.files.append(FileRecord(rel, ext[1:], size=size, note=note))
                    continue
                packed_player = unity and path.name.lower() == "data.unity3d" and header.startswith(b"UnityFS\0")
                if size > max_mb * 1024 * 1024 and not packed_player:
                    project.files.append(FileRecord(rel, "skipped", size=size, note=f"Vượt giới hạn {max_mb} MB/file."))
                    continue
                # Quick scan visits root assets first; bundles are listed for optional deep scan.
                if not deep and ((unity and header.startswith((b"UnityFS", b"UnityWeb", b"UnityRaw"))) or ext in (".pck", ".pak")):
                    project.files.append(FileRecord(rel, "bundle", size=size, note="Chọn Quét sâu để đọc bundle/PCK."))
                    continue
                candidates.append((path, rel, size, unity, packed_player))
            except OSError as exc:
                project.files.append(FileRecord(rel, "error", note=str(exc)))
    project.engines = sorted(engines) or ["Engine riêng / chưa xác định"]
    # Read script identities before stripped Moon providers.
    candidates.sort(key=lambda item: item[0].name.lower() != "globalgamemanagers.assets")
    for i, (path, rel, size, unity, packed_player) in enumerate(candidates, 1):
        if cancelled():
            raise InterruptedError("Đã dừng quét.")
        progress(f"[{i}/{len(candidates)}] {rel}")
        record = FileRecord(rel, "unity" if unity else path.suffix.lower()[1:], size=size)
        try:
            data = b"" if packed_player else path.read_bytes()
            record.sha256 = digest(path if packed_player else data)
            if packed_player:
                from .unityfs_stream import extract_file, UnsupportedVersion
                record.kind = "unityfs"
                try:
                    entries, record.note = extract_file(path, rel, cancelled, scripts, progress, max_mb)
                except UnsupportedVersion:
                    if size > max_mb * 1024 * 1024:
                        raise
                    # Retain the existing bounded-file reader for older Unity versions.
                    record.kind = "unity"
                    entries, record.note = extract_unity(path.read_bytes(), rel, cancelled, script_registry=scripts)
            elif unity:
                entries, record.note = extract_unity(data, rel, cancelled, script_registry=scripts)
            elif record.kind == "pak":
                if path.with_suffix(".sig").exists() or Path(str(path) + ".sig").exists():
                    raise ValueError("PAK có chữ ký; chưa hỗ trợ cài lại gói đã ký.")
                entries, record.note = pak.extract(data, rel, cancelled)
                if "Unreal Engine" not in project.engines:project.engines.append("Unreal Engine")
            elif record.kind == "locres":
                entries, record.note = extract_locres(data, rel)
            elif record.kind == "pck":
                entries, record.note = extract_pack(data, rel, cancelled)
            elif path.suffix.lower() in RESOURCE_EXTENSIONS:
                entries, record.note = extract_resource(data, record.kind, rel)
            elif record.kind == "rpy":
                text, record.encoding = decode_text(data)
                entries, record.note = renpy.extract(text, rel)
            elif record.kind == "json" and "RPG Maker MV/MZ" in project.engines and rpgmaker.is_database(rel):
                text, record.encoding = decode_text(data)
                record.kind = "rpgmaker"
                entries, record.note = rpgmaker.extract(text, rel)
            elif path.suffix.lower() in TEXT_EXTENSIONS:
                text, record.encoding = decode_text(data)
                entries = extract(text, record.kind, rel)
            else:
                samples = []
                for match in re.finditer(rb"[\x20-\x7e]{12,160}", data[:4 * 1024 * 1024]):
                    text = match[0].decode("ascii")
                    if " " in text and sum(c.isalpha() for c in text) > 8:
                        samples.append(f"0x{match.start():X}: {text[:100]}")
                        if len(samples) >= 3:
                            break
                record.note = ({"pak": "PAK chưa hỗ trợ giải nén/đóng gói. Cần LOCRES rời hoặc adapter container phù hợp.",
                               "utoc": "Unreal IoStore UTOC/UCAS chưa hỗ trợ giải nén/đóng gói.",
                               "ucas": "Unreal IoStore UTOC/UCAS chưa hỗ trợ giải nén/đóng gói.",
                               "uasset": "UASSET có thể chứa StringTable/FText; chưa hỗ trợ đọc/ghi asset.",
                               "rpa": "Ren’Py RPA chưa hỗ trợ; cần source/template RPY.",
                               "rpyc": "Ren’Py RPYC chưa hỗ trợ; cần source/template RPY."}.get(record.kind, "Định dạng chưa hỗ trợ ghi lại.")
                               + " " + " | ".join(samples))
                entries = []
            record.count = len(entries)
            project.entries.extend(entries)
        except InterruptedError:
            raise
        except Exception as exc:
            record.note = f"Không đọc được: {type(exc).__name__}: {exc}"
        project.files.append(record)
    if "Unreal Engine" in project.engines:
        project.engines = [engine for engine in project.engines if not engine.startswith("PAK (")]
    project.entries = resolve_table_entries(project.entries, scripts)
    from collections import Counter
    counts = Counter(e.file for e in project.entries)
    for record in project.files:
        record.count = counts[record.path]
    progress(f"Xong: {len(project.entries):,} đoạn text; {sum(e.enabled for e in project.entries):,} vị trí tiếng Anh được chọn.")
    return project
