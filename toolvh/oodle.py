"""Decode Oodle blocks in a bounded WASM instance, with no filesystem imports."""
from functools import lru_cache
from pathlib import Path

MAX_SIZE = 64 * 1024 * 1024


@lru_cache(maxsize=1)
def runtime():
    try:
        import wasmtime
    except ImportError as exc:
        raise ValueError('Thiếu Wasmtime; cài requirements.txt hoặc dùng bản EXE mới.') from exc
    config = wasmtime.Config()
    config.consume_fuel = True
    engine = wasmtime.Engine(config)
    path = Path(__file__).with_name('data') / 'toolvh_oodle.wasm'
    if not path.is_file():
        raise ValueError('Thiếu bộ giải nén toolvh_oodle.wasm; dùng bản ToolVH đầy đủ.')
    module = wasmtime.Module.from_file(engine, path)
    if module.imports:
        raise ValueError('Bộ giải nén WASM không được yêu cầu host imports.')
    return wasmtime, engine, module


def decompress(data, expected):
    if not data or not 0 < len(data) <= MAX_SIZE or not 0 < expected <= MAX_SIZE:
        raise ValueError('Oodle kích thước block không hợp lệ hoặc vượt 64 MB.')
    try:
        wasmtime, engine, module = runtime()
        with wasmtime.Store(engine) as store:
            store.set_limits(memory_size=256 * 1024 * 1024)
            store.set_fuel(1_000_000_000)
            exports = wasmtime.Instance(store, module, []).exports(store)
            source = exports['allocate'](store, len(data))
            target = exports['allocate'](store, expected)
            if not source or not target:
                raise ValueError('Oodle không cấp phát được bộ nhớ.')
            memory = exports['memory']
            memory.write(store, data, source)
            count = exports['decode'](store, source, len(data), target, expected)
            if count != expected:
                raise ValueError('Oodle block sai dữ liệu/kích thước sau giải nén.')
            return bytes(memory.read(store, target, target + count))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Oodle giải nén thất bại hoặc vượt giới hạn WASM.') from exc
