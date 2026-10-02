"""Targeted CRC updates for local Unity Addressables binary v2 and JSON catalogs.

Layout follows Unity's ContentCatalogData and BinaryStorageBuffer serializers.
No search-and-replace of arbitrary CRC bytes; resolve provider/options by pointers.
"""
from __future__ import annotations

import struct
import base64
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


def update_json_catalog(data: bytes, changes: dict[str, tuple[bytes, bytes]]) -> bytes:
    """Unity JSON catalog: seven int32s per location, typed UTF-16 options.

    Append replacement options so unrelated offsets and serialized objects stay intact.
    Layout: ContentCatalogData.CreateLocator / SerializationUtilities.JsonObject.
    """
    catalog = json.loads(data.decode("utf-8-sig"))
    entries = bytearray(base64.b64decode(catalog["m_EntryDataString"], validate=True))
    extra = bytearray(base64.b64decode(catalog["m_ExtraDataString"], validate=True))
    if len(entries) < 4:
        raise ValueError("Bảng location JSON catalog bị thiếu.")
    count, = struct.unpack_from("<i", entries)
    if count < 0 or len(entries) != 4 + count * 28:
        raise ValueError("Kích thước bảng location JSON catalog không hợp lệ.")
    bundles = []
    for i in range(count):
        offset = 4 + i * 28
        internal, provider, _, _, options, _, _ = struct.unpack_from("<7i", entries, offset)
        if not 0 <= provider < len(catalog["m_ProviderIds"]):
            raise ValueError("Provider JSON catalog nằm ngoài dữ liệu.")
        if not catalog["m_ProviderIds"][provider].endswith(".AssetBundleProvider"):
            continue
        if not 0 <= internal < len(catalog["m_InternalIds"]):
            raise ValueError("Internal ID JSON catalog nằm ngoài dữ liệu.")
        if not 0 <= options < len(extra) or extra[options] != 7:
            raise ValueError("Options JSON catalog chưa hỗ trợ.")
        end = options + 1
        names = []
        for _ in range(2):
            if end >= len(extra) or end + 1 + extra[end] > len(extra):
                raise ValueError("Tên kiểu JSON catalog vượt giới hạn.")
            length = extra[end]
            names.append(bytes(extra[end + 1:end + 1 + length]).decode("ascii"))
            end += 1 + length
        if names[1] != "UnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions":
            raise ValueError("Kiểu options JSON catalog chưa hỗ trợ.")
        if end + 4 > len(extra):
            raise ValueError("Options JSON catalog bị thiếu độ dài.")
        length, = struct.unpack_from("<i", extra, end)
        if length < 0 or length % 2 or end + 4 + length > len(extra):
            raise ValueError("Options JSON catalog vượt giới hạn.")
        value = json.loads(extra[end + 4:end + 4 + length].decode("utf-16-le"))
        bundles.append((catalog["m_InternalIds"][internal].replace("\\", "/"),
                        offset, bytes(extra[options:end]), value))
    for relative, (original, modified) in sorted(changes.items()):
        filename = Path(relative).name
        matches = [item for item in bundles if item[0].endswith("/" + filename)]
        if len(matches) != 1:
            raise ValueError(f"Không xác định duy nhất bundle trong JSON catalog: {filename}")
        path, offset, prefix, value = matches[0]
        if not path.startswith("{UnityEngine.AddressableAssets.Addressables.RuntimePath}/") or value.get("m_UseUWRForLocalBundles", False):
            raise ValueError("Chưa hỗ trợ bundle remote/UnityWebRequest/cache trong JSON catalog.")
        if value["m_Crc"] and value["m_Crc"] != bundle_crc(original):
            raise ValueError(f"CRC nguồn khác catalog: {filename}. Hãy xác minh file game và quét lại.")
        if value["m_BundleSize"] != len(original):
            raise ValueError(f"Kích thước bundle nguồn khác catalog: {filename}")
        value = dict(value, m_Crc=bundle_crc(modified), m_BundleSize=len(modified))
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-16-le")
        struct.pack_into("<i", entries, offset + 16, len(extra))
        extra.extend(prefix + struct.pack("<i", len(encoded)) + encoded)
    catalog["m_EntryDataString"] = base64.b64encode(entries).decode("ascii")
    catalog["m_ExtraDataString"] = base64.b64encode(extra).decode("ascii")
    return json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


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
                or not locations[0].get("m_InternalId", "").replace("\\", "/").endswith(("/catalog.bin", "/catalog.json"))
                or "://" in locations[0].get("m_InternalId", "")
                or settings.get("m_IsLocalCatalogInBundle")):
            raise ValueError("Chưa hỗ trợ catalog remote/có dependency/đóng bundle. Không cài bản vá để tránh màn hình đen.")
        catalog_name = locations[0]["m_InternalId"].replace("\\", "/").rsplit("/", 1)[1]
        relative = (folder / catalog_name).as_posix()
        original = changes[relative][0] if relative in changes else (root / relative).read_bytes()
        updater = update_json_catalog if catalog_name == "catalog.json" else update_catalog
        result[relative] = (original, updater(original, bundles))
        # No catalog hash dependency: runtime reads this local catalog directly.
    return result
