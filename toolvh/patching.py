from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from .formats import decode_text, encode_text, rebuild
from .model import Project, atomic_write, digest, safe_child
from .terminology import validate_entry, term_policy
from .translation import normalize_translation
from .unity import rebuild_unity
from .addressables import catalog_updates
from .godot import RESOURCE_EXTENSIONS, rebuild_pack, rebuild_resource
from .unreal import rebuild_locres
from . import rpgmaker, renpy, pak


def export_csv(project: Project, path: str | Path):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["id", "file", "context", "source", "translation", "enabled"])
    for e in project.entries:
        writer.writerow([e.id, e.file, e.context, e.source, e.translation, int(e.enabled)])
    atomic_write(Path(path), stream.getvalue().encode("utf-8-sig"))


def import_csv(project: Project, path: str | Path):
    terms = term_policy(project)
    entries = {e.id: e for e in project.entries}
    edits, seen = [], set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            entry = entries.get(row.get("id"))
            if entry is None or entry.source != row.get("source") or entry.id in seen:
                raise ValueError("CSV có ID lạ, ID trùng hoặc text nguồn đã thay đổi.")
            seen.add(entry.id)
            translation = normalize_translation(row.get("translation", ""))
            if translation:
                errors = validate_entry(project, entry, translation, terms)
                if errors:
                    raise ValueError(f"{entry.context}: {' '.join(errors)}")
            enabled = row.get("enabled", "1")
            if enabled not in ("0", "1"):
                raise ValueError("Cột enabled chỉ nhận 0 hoặc 1.")
            edits.append((entry, translation, enabled == "1"))
    for entry, translation, enabled in edits:
        entry.translation, entry.enabled, entry.error = translation, enabled, ""
    return len(edits)


def prepare_changes(project, groups, progress=lambda text: None):
    root = Path(project.root).resolve()
    records = {f.path: f for f in project.files}
    changes = {}
    for relative, entries in groups.items():
        progress(f"Đang đóng gói: {relative}")
        record = records[relative]
        original = safe_child(root, relative).read_bytes()
        if digest(original) != record.sha256:
            raise ValueError(f"File game đã thay đổi kể từ lần quét: {relative}")
        if record.kind == "unity":
            modified = rebuild_unity(original, entries)
        elif record.kind == "pak":
            path = safe_child(root, relative)
            if path.with_suffix(".sig").exists() or Path(str(path) + ".sig").exists():
                raise ValueError("PAK có chữ ký; chưa hỗ trợ cài lại gói đã ký.")
            modified = pak.rebuild(original, entries)
        elif record.kind == "locres":
            modified = rebuild_locres(original, entries)
        elif record.kind == "pck":
            modified = rebuild_pack(original, entries)
        elif "." + record.kind in RESOURCE_EXTENSIONS:
            modified = rebuild_resource(original, record.kind, entries)
        elif record.kind in ("rpgmaker", "rpy"):
            text, encoding = decode_text(original)
            adapter = rpgmaker if record.kind == "rpgmaker" else renpy
            modified = encode_text(adapter.rebuild(text, entries), encoding)
        else:
            text, encoding = decode_text(original)
            modified = encode_text(rebuild(text, record.kind, entries), encoding)
        changes[relative] = (original, modified)
    changes.update(catalog_updates(root, changes))
    return changes


def preflight(project, progress=lambda text: None, cancelled=lambda: False):
    """Exercise real writers with source text, without writing game or calling API."""
    from dataclasses import replace
    project.require_current_scan()
    if project.applied_patch or project.font_patches:
        raise ValueError("Game đang có bản vá. Khôi phục trước khi chuẩn bị bản dịch mới cho chính game này.")
    groups = defaultdict(list)
    for entry in project.entries:
        if entry.enabled:
            groups[entry.file].append(replace(entry, translation=entry.source))
    if not groups:
        raise ValueError("Chọn text tiếng Anh cần dịch trước khi kiểm tra khả năng cài.")
    def checked_progress(text):
        if cancelled():
            raise InterruptedError("Đã dừng kiểm tra khả năng cài.")
        progress(text)
    changes = prepare_changes(project, groups, checked_progress)
    return {"selected_entries": sum(map(len, groups.values())), "checked_files": list(changes),
            "status": "Đọc/ghi và catalog đạt; font, bố cục và việc game nạp dữ liệu cần kiểm tra thực tế."}


def export_patch(project: Project, destination: str | Path, progress=lambda text: None):
    project.require_current_scan()
    if project.font_patches:
        raise ValueError("Khôi phục bản vá font trước khi xuất/cài bản dịch mới; bản dịch đang cài sẽ được giữ.")
    if project.applied_patch:
        raise ValueError("Hãy khôi phục bản gốc trước khi xuất/cài bản dịch mới từ project này.")
    root, destination = Path(project.root).resolve(), Path(destination).resolve()
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("Chọn thư mục bản vá nằm ngoài thư mục game và không chứa thư mục game.")
    if destination.exists():
        raise ValueError("Thư mục đích đã tồn tại. Chọn tên mới để giữ các bản vá cũ.")
    terms = term_policy(project)
    groups = defaultdict(list)
    for e in project.entries:
        if e.enabled and e.translation:
            errors = validate_entry(project, e, e.translation, terms)
            if errors:
                raise ValueError(f"{e.context}: {' '.join(errors)}")
            groups[e.file].append(e)
    if not groups:
        raise ValueError("Chưa có bản dịch được chọn để xuất.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".toolvh-patch-", dir=destination.parent))
    manifest = {"schema": 1, "game_root": str(root), "files": [],
                "translated": sum(map(len, groups.values())),
                "remaining": sum(e.enabled and not e.translation for e in project.entries)}
    try:
        changes = prepare_changes(project, groups, progress)
        for relative, (original, modified) in changes.items():
            atomic_write(safe_child(staging / "files", relative), modified)
            atomic_write(safe_child(staging / "backup", relative), original)
            manifest["files"].append({"path": relative, "original_sha256": digest(original), "patched_sha256": digest(modified)})
        atomic_write(staging / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        atomic_write(staging / "README.txt", (
            "ToolVH — bản vá tiếng Việt\n\n"
            "Đóng game trước khi cài. Trong ToolVH chọn Cài bản vá, chọn thư mục này và thư mục game.\n"
            "Tool kiểm tra SHA-256 trước khi cài. Khôi phục dùng backup và kiểm tra bản đã cài.\n"
            "files/ chứa các file đã dịch; backup/ chứa bản gốc. Giữ nguyên cả thư mục bản vá.\n"
            "Bản vá thay text ở ngôn ngữ nguồn; nếu dịch cột English hãy chọn English trong game.\n"
            "Chưa xác nhận font và hiển thị trong game. Cần thử màn hình menu/hội thoại thực tế.\n"
            f"Đã dịch: {manifest['translated']}; còn thiếu trong mục đã chọn: {manifest['remaining']}.\n"
        ).encode("utf-8-sig"))
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def install_patch(patch: str | Path, game: str | Path, restore=False):
    from .processes import assert_game_closed
    assert_game_closed(game)
    patch, game = Path(patch).resolve(), Path(game).resolve()
    manifest = json.loads((patch / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not manifest.get("files"):
        raise ValueError("Manifest không hợp lệ.")
    tasks, seen = [], set()
    if not restore:
        changes = {f["path"]: (safe_child(patch / "backup", f["path"]).read_bytes(),
                                safe_child(patch / "files", f["path"]).read_bytes())
                   for f in manifest["files"]}
        # Recompute required catalogs against the installation, including old patches.
        for relative, (_, expected_catalog) in catalog_updates(game, changes).items():
            if relative not in changes or changes[relative][1] != expected_catalog:
                raise ValueError("Bản vá thiếu/sai catalog CRC. Hãy xuất lại bằng ToolVH mới; không cài để tránh màn hình đen.")
    for file in manifest["files"]:
        target = safe_child(game, file["path"])
        if not restore and target.suffix.lower() == ".pak" and (target.with_suffix(".sig").exists() or Path(str(target) + ".sig").exists()):
            raise ValueError("PAK có chữ ký; chưa hỗ trợ cài lại gói đã ký.")
        if target in seen:
            raise ValueError("Manifest có đường dẫn trùng.")
        seen.add(target)
        # Check all inputs and backups before modifying any game file.
        original = safe_child(patch / "backup", file["path"]).read_bytes()
        modified = safe_child(patch / "files", file["path"]).read_bytes()
        if digest(original) != file["original_sha256"] or digest(modified) != file["patched_sha256"]:
            raise ValueError(f"Dữ liệu bản vá không còn khớp: {file['path']}")
        current = target.read_bytes()
        expected = file["patched_sha256"] if restore else file["original_sha256"]
        desired = file["original_sha256"] if restore else file["patched_sha256"]
        if digest(current) == desired:
            continue  # Allow safe retry after an interrupted install/restore.
        if digest(current) != expected:
            raise ValueError(f"File hiện tại khác phiên bản cần {'khôi phục' if restore else 'cài'}: {file['path']}")
        tasks.append((target, current, original if restore else modified))
    applied = []
    try:
        for target, current, new in tasks:
            if target.read_bytes() != current:
                raise ValueError(f"File thay đổi trong lúc cài: {target}")
            atomic_write(target, new)
            applied.append((target, current))
    except Exception:
        for target, current in reversed(applied):
            atomic_write(target, current)
        raise
    return len(applied)


def apply_project(project: Project, destination: str | Path, progress=lambda text: None,
                  save=lambda: None):
    """Build and verify backups before installing into the scanned game folder."""
    manifest = export_patch(project, destination, progress)
    project.applied_patch = str(Path(destination).resolve())
    save()  # Recovery path persists before any game writes.
    progress("Đã lưu backup. Đang cài bản dịch vào thư mục game…")
    count = install_patch(destination, project.root)
    return {"files": count, "translated": manifest["translated"], "patch": project.applied_patch}


def restore_project(project: Project, save=lambda: None):
    if project.font_patches:
        raise ValueError("Khôi phục font trước, sau đó khôi phục bản dịch để đúng thứ tự backup.")
    if not project.applied_patch:
        raise ValueError("Project chưa ghi nhận bản vá đã cài.")
    count = install_patch(project.applied_patch, project.root, restore=True)
    project.applied_patch = ""
    save()
    return count
