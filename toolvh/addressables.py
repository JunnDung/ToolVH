"""Targeted CRC updates for Unity Addressables binary catalog version 2.

Layout follows Unity's ContentCatalogData and BinaryStorageBuffer serializers.
No search-and-replace of arbitrary CRC bytes; resolve provider/options by pointers.
"""
from __future__ import annotations

import struct
import json
import zlib
from pathlib import Path

from UnityPy.files.BundleFile import BundleFile
from UnityPy.streams import EndianBinaryReader


def bundle_crc(data: bytes) -> int:
    class CRCBundle(BundleFile):
        def read_files(self, reader, directory):
            self.payload_crc = zlib.crc32(reader.bytes)
    if not data.startswith(b"UnityFS\0"):
        raise ValueError("Chưa hỗ trợ CRC của bundle khác UnityFS.")
    return CRCBundle(EndianBinaryReader(data), None).payload_crc


class BinaryCatalog:
    def __init__(self, data: bytes):
        self.data = data
        if self.values(0, 2) != (0x0DE38942, 2):
            raise ValueError("Catalog Addressables chưa hỗ trợ: cần binary version 2. Không cài để tránh lỗi khởi động.")

    def values(self, offset, count):
        if offset < 0 or offset + 4 * count > len(self.data):
            raise ValueError("Con trỏ catalog nằm ngoài dữ liệu.")
        return struct.unpack_from("<" + "I" * count, self.data, offset)

    def array(self, offset):
        size, = self.values(offset - 4, 1)
        if size % 4:
            raise ValueError("Mảng catalog không hợp lệ.")
        return self.values(offset, size // 4)

    def string(self, offset, separator="", seen=None):
        if offset == 0xFFFFFFFF:
            return ""
        seen = set() if seen is None else seen
        if offset in seen or len(seen) > 128:
            raise ValueError("Chuỗi catalog có con trỏ vòng.")
        seen.add(offset)
        position = offset & 0x3FFFFFFF
        if offset & 0x40000000:
            parts, nodes = [], set()
            while offset != 0xFFFFFFFF:
                position = offset & 0x3FFFFFFF
                if position in nodes or len(nodes) > 128:
                    raise ValueError("Chuỗi catalog có con trỏ vòng.")
                nodes.add(position)
                string_id, offset = self.values(position, 2)
                if string_id != 0xFFFFFFFF and string_id & 0x40000000:
                    raise ValueError("Mảnh chuỗi catalog chứa con trỏ dynamic không hợp lệ.")
                parts.append(self.string(string_id))
            return separator.join(reversed(parts))
        size, = self.values(position - 4, 1)
        if position + size > len(self.data):
            raise ValueError("Chuỗi catalog vượt giới hạn.")
        return self.data[position:position + size].decode("utf-16-le" if offset & 0x80000000 else "ascii")

    def bundles(self):
        keys_offset, = self.values(8, 1)
        keys = self.array(keys_offset)
        if len(keys) % 2:
            raise ValueError("Bảng key catalog không hợp lệ.")
        locations = {loc for offset in keys[1::2] for loc in self.array(offset)}
        result = []
        for offset in locations:
            primary, internal, provider, deps, dep_hash, extra, resource_type = self.values(offset, 7)
            if not self.string(provider, ".").endswith(".AssetBundleProvider"):
                continue
            type_id, options = self.values(extra, 2)
            assembly, class_id = self.values(type_id, 2)
            if self.string(class_id, ".") != "UnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions":
                raise ValueError("Kiểu options của AssetBundleProvider chưa hỗ trợ.")
            hash_id, name_id, crc, size, common = self.values(options, 5)
            self.values(hash_id, 4)
            self.values(common, 2)
            result.append((self.string(internal, "/").replace("\\", "/"), options, crc, size))
        return result


def update_catalog(data: bytes, changes: dict[str, tuple[bytes, bytes]]) -> bytes:
    catalog = BinaryCatalog(data)
    bundles = catalog.bundles()
    output = bytearray(data)
    for relative, (original, modified) in changes.items():
        filename = Path(relative).name
        matches = [(offset, crc, size) for path, offset, crc, size in bundles
                   if path.endswith("/" + filename) or path == filename]
        if len(matches) != 1:
            raise ValueError(f"Không xác định duy nhất bundle trong catalog: {filename}")
        offset, crc, size = matches[0]
        if crc and crc != bundle_crc(original):
            raise ValueError(f"CRC nguồn khác catalog: {filename}. Hãy xác minh file game và quét lại.")
        if size != len(original):
            raise ValueError(f"Kích thước bundle nguồn khác catalog: {filename}")
        common, = catalog.values(offset + 16, 1)
        _, flags = catalog.values(common, 2)
        if flags & 8:
            raise ValueError("Chưa hỗ trợ bundle local qua UnityWebRequest/cache. Không cài để tránh nạp bản cũ từ cache.")
        struct.pack_into("<II", output, offset + 8, bundle_crc(modified), len(modified))
    # Re-read the emitted catalog using the same bounded pointer traversal.
    BinaryCatalog(bytes(output)).bundles()
    return bytes(output)


def catalog_updates(root: Path, changes: dict[str, tuple[bytes, bytes]]):
    """Only local, dependency-free catalogs are supported; reject remote cache setups."""
    groups = {}
    for relative, payload in changes.items():
        parts = Path(relative).parts
        if "StreamingAssets" not in parts or "aa" not in parts or not payload[0].startswith(b"UnityFS\0"):
            continue
        index = parts.index("aa")
        folder = Path(*parts[:index + 1])
        groups.setdefault(folder, {})[relative] = payload
    result = {}
    for folder, bundles in groups.items():
        settings = json.loads((root / folder / "settings.json").read_text(encoding="utf-8-sig"))
        locations = settings.get("m_CatalogLocations", [])
        if (len(locations) != 1 or locations[0].get("m_Dependencies")
                or not locations[0].get("m_InternalId", "").endswith("/catalog.bin")
                or "://" in locations[0].get("m_InternalId", "")
                or settings.get("m_IsLocalCatalogInBundle")):
            raise ValueError("Chưa hỗ trợ catalog remote/JSON/đóng bundle. Không cài bản vá để tránh màn hình đen.")
        relative = (folder / "catalog.bin").as_posix()
        original = changes[relative][0] if relative in changes else (root / relative).read_bytes()
        result[relative] = (original, update_catalog(original, bundles))
        # catalog.hash has no dependency here: the runtime directly reads catalog.bin.
    return result
