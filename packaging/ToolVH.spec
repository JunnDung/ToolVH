# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = [], [], []
for package in ('UnityPy', 'texture2ddecoder', 'etcpak', 'astc_encoder', 'archspec'):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_imports)

a = Analysis(
    [str(root / 'launcher.py')],
    pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)

# Qt 6 uses the Windows 10/11 system ICU API. PyInstaller can accidentally
# resolve icuuc.dll from unrelated PATH tools such as Poppler. Those builds
# export versioned symbols and prevent QtCore from loading. Let Windows
# resolve its own unversioned ICU library; never redistribute the system DLL.
a.binaries = [
    item for item in a.binaries
    if Path(item[0]).name.lower() not in ('icuuc.dll', 'icuin.dll', 'icudt.dll')
    and not (
        Path(item[0]).name.lower().startswith('icu')
        and 'poppler' in item[1].lower()
    )
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='ToolVH',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='ToolVH',
)
