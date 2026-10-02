"""Read-only process checks before changing files of a running Windows game."""
from pathlib import Path
import sys

def running_game_processes(root):
    if sys.platform!='win32':return []
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    kernel.QueryFullProcessImageNameW.argtypes=(wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD))
    kernel.QueryFullProcessImageNameW.restype=wintypes.BOOL
    psapi.EnumProcesses.argtypes=(ctypes.POINTER(wintypes.DWORD),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD))
    psapi.EnumProcesses.restype=wintypes.BOOL
    pids=(wintypes.DWORD*8192)();used=wintypes.DWORD()
    if not psapi.EnumProcesses(pids,ctypes.sizeof(pids),ctypes.byref(used)):
        raise OSError('Không kiểm tra được game đang chạy; chưa cài/khôi phục file.')
    if used.value>=ctypes.sizeof(pids):raise OSError('Danh sách tiến trình quá lớn; chưa cài file.')
    root=Path(root).resolve();found=[]
    for pid in pids[:used.value//ctypes.sizeof(wintypes.DWORD)]:
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:continue
        try:
            name=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(name))
            if kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(length)):
                executable=Path(name.value).resolve()
                if executable.is_relative_to(root):found.append((int(pid),str(executable)))
        finally:kernel.CloseHandle(handle)
    return found

def assert_game_closed(root):
    active=running_game_processes(root)
    if active:
        raise ValueError('Game đang chạy; đóng game trước khi cài/khôi phục: '+', '.join(Path(path).name for _,path in active))
