"""Original synthetic data: no commercial game files or extracted game text."""
import json
import struct
import zlib
from pathlib import Path


def bundle(payload, compressed=False):
    if compressed:
        import lz4.block
        stored = lz4.block.compress(payload, store_size=False)
    else:
        stored = payload
    info = (bytes(16) + struct.pack('>IIIH', 1, len(payload), len(stored), 2 if compressed else 0)
            + struct.pack('>IqqI', 1, 0, len(payload), 0) + b'payload.bytes\0')
    prefix = b'UnityFS\0' + struct.pack('>I', 6) + b'5.x.x\0' + b'5.6.0f3\0'
    header = prefix + struct.pack('>qIII', len(prefix) + 20 + len(info) + len(stored), len(info), len(info), 0x40)
    return header + info + stored


def catalog(crc, size):
    data = bytearray(32)
    def values(*items):
        offset = len(data)
        data.extend(struct.pack('<' + 'I' * len(items), *items))
        return offset
    def string(text):
        encoded = text.encode('ascii')
        values(len(encoded))
        offset = len(data)
        data.extend(encoded)
        return offset
    def array(items):
        values(len(items) * 4)
        return values(*items)
    provider = string('UnityEngine.ResourceManagement.ResourceProviders.AssetBundleProvider')
    assembly = string('Unity.ResourceManager')
    class_id = string('UnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions')
    type_id = values(assembly, class_id)
    keys = []
    for name, checksum, length in [('english.bundle', crc, size), ('other.bundle', 123, 12)]:
        internal = string('{UnityEngine.AddressableAssets.Addressables.RuntimePath}/StandaloneWindows64/' + name)
        hash_id = values(0, 0, 0, 0)
        common = values(0, 0)
        options = values(hash_id, string(name), checksum, length, common)
        extra = values(type_id, options)
        location = values(0, internal, provider, 0xFFFFFFFF, 0, extra, type_id)
        keys.extend([0, array([location])])
    key_offset = array(keys)
    struct.pack_into('<III', data, 0, 0x0DE38942, 2, key_offset)
    return bytes(data)


def make_fixture(root: Path):
    relative = 'Sample_Data/StreamingAssets/aa/StandaloneWindows64/english.bundle'
    source = b'Synthetic English text. Start game.'
    translated = 'Dữ liệu thử nghiệm. Bắt đầu chơi.'.encode('utf-8')
    original, modified = bundle(source), bundle(translated)
    patch = root / 'patch'
    for folder, data in [('backup', original), ('files', modified)]:
        path = patch / folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    from toolvh.model import digest
    manifest = {'schema': 1, 'game_root': 'synthetic-game', 'translated': 1, 'remaining': 0,
                'files': [{'path': relative, 'original_sha256': digest(original), 'patched_sha256': digest(modified)}]}
    (patch / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    data = catalog(zlib.crc32(source), len(original))
    (root / 'catalog.bin').write_bytes(data)
    return patch, relative, original, modified, data, zlib.crc32(source), zlib.crc32(translated)
