from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Entry:
    id: str
    file: str
    locator: dict[str, Any]
    source: str
    context: str
    confidence: float = 0.8
    enabled: bool = True
    translation: str = ""
    error: str = ""
    source_locale: str = ""
    detection: str = ""


@dataclass
class FileRecord:
    path: str
    kind: str
    sha256: str = ""
    encoding: str = ""
    size: int = 0
    count: int = 0
    note: str = ""


@dataclass
class Project:
    root: str
    engines: list[str] = field(default_factory=list)
    files: list[FileRecord] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    glossary: dict[str, str] = field(default_factory=dict)
    instructions: str = "Dịch tự nhiên, ngắn gọn, phù hợp giao diện và hội thoại game."
    preserve_names: bool = True
    protected_names: list[str] = field(default_factory=list)
    game_context: str = ""
    google_web_cache: dict[str, str] = field(default_factory=dict)
    schema: int = 1
    scan_revision: int = 2
    applied_patch: str = ""
    font_patches: list[str] = field(default_factory=list)

    def require_current_scan(self):
        if self.scan_revision < 2:
            raise ValueError("Project dùng bộ quét cũ. Mở project và bấm Quét dữ liệu lại trước khi dịch/xuất bản vá. Bản dịch có cùng nguồn và vị trí sẽ được giữ lại.")

    def save(self, path: str | Path) -> None:
        atomic_write(Path(path), json.dumps(asdict(self), ensure_ascii=False, indent=2).encode("utf-8"))

    @classmethod
    def load(cls, path: str | Path) -> Project:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if data.get("schema") != 1:
            raise ValueError("Phiên bản project không được hỗ trợ.")
        data.setdefault("scan_revision", 0)
        if not isinstance(data.get("google_web_cache", {}), dict):
            raise ValueError("Cache Google Dịch trong project không hợp lệ.")
        data["files"] = [FileRecord(**f) for f in data["files"]]
        data["entries"] = [Entry(**e) for e in data["entries"]]
        project = cls(**data)
        ids = [e.id for e in project.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Project có ID bị trùng.")
        for relative in {f.path for f in project.files} | {e.file for e in project.entries}:
            safe_child(Path(project.root), relative)
        return project


def safe_child(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or rel.drive or ".." in rel.parts or ":" in relative:
        raise ValueError(f"Đường dẫn không hợp lệ: {relative}")
    target = (root / rel).resolve()
    if target == root.resolve() or not target.is_relative_to(root.resolve()):
        raise ValueError(f"Đường dẫn nằm ngoài thư mục: {relative}")
    return target


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".toolvh-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_entry(file: str, locator: dict, source: str, context: str, confidence: float) -> Entry:
    key = json.dumps([file, locator, source], ensure_ascii=False, sort_keys=True)
    return Entry(digest(key.encode("utf-8"))[:24], file, locator, source, context,
                 confidence, confidence >= 0.75)
