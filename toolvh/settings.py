"""Per-provider settings. Persisted keys use Windows DPAPI, never plaintext."""
from __future__ import annotations

import base64
import ctypes
import json
import os
from dataclasses import asdict
from pathlib import Path

from .model import atomic_write
from .translation import APIConfig, PROVIDERS


def settings_path():
    override = os.environ.get("TOOLVH_SETTINGS_PATH")
    if override:
        return Path(override)
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".config"))) / "ToolVH" / "settings.json"


def _dpapi(data: bytes, decrypt=False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Lưu key mã hóa hiện chỉ hỗ trợ Windows. Có thể dùng key trong phiên này.")
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Windows không thể xử lý key đã lưu. Hãy nhập lại key trên tài khoản Windows này.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(target.data)


class SettingsStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else settings_path()

    def load(self):
        if not self.path.exists():
            return {"provider": "gemini", "profiles": {}, "recent": [], "key_errors": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema") != 1:
            raise ValueError("Cấu hình ToolVH không đúng phiên bản.")
        profiles, errors = {}, []
        for provider, saved in data.get("profiles", {}).items():
            if provider not in PROVIDERS:
                continue
            saved = dict(saved)
            encrypted = saved.pop("encrypted_key", "")
            # Never accept a plaintext key in a settings file.
            saved.pop("api_key", None)
            remember = bool(saved.pop("remember", False))
            config = APIConfig(**saved)
            config.provider = provider
            if encrypted:
                try:
                    config.api_key = _dpapi(base64.b64decode(encrypted, validate=True), decrypt=True).decode("utf-8")
                except Exception:
                    errors.append(provider)
            profiles[provider] = (config, remember)
        return {"provider": data.get("provider", "gemini"), "profiles": profiles,
                "recent": data.get("recent", [])[:10], "key_errors": errors}

    def save(self, provider, profiles, recent):
        data = {"schema": 1, "provider": provider, "profiles": {}, "recent": list(recent)[:10]}
        for name, (config, remember) in profiles.items():
            values = asdict(config)
            key = values.pop("api_key")
            values["remember"] = remember
            if remember and key:
                values["encrypted_key"] = base64.b64encode(_dpapi(key.encode("utf-8"))).decode("ascii")
            data["profiles"][name] = values
        atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
