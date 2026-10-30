"""Mở app không cần terminal: shortcut ở menu Start, Desktop và thư mục Startup (tự chạy khi mở Windows).

Shortcut trỏ tới screen-translator-gui.exe, bản không mở cửa sổ console mà uv tạo từ [project.gui-scripts].
Tự chạy dùng thư mục Startup chứ không ghi registry, nên tắt được cả ở Task Manager → Startup apps.
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .config import APP_DIR

NAME = "ScreenTranslator.lnk"
LABELS = {
    "start_menu": "Thêm vào menu Start",
    "desktop": "Tạo shortcut trên Desktop",
    "autostart": "Tự chạy khi mở Windows",
}
ICON_PATH = APP_DIR / "icon.ico"
AUTOSTART_ARG = "--autostart"  # chạy lúc mở Windows thì không hiện thông báo khởi động
DESCRIPTION = "Dịch chữ tiếng Nhật trên màn hình"

# Tạo .lnk bằng IShellLinkW của Windows qua ctypes. WScript.Shell (PowerShell) không nhận đường dẫn có
# ký tự ngoài bảng mã ANSI, như tên người dùng hay thư mục Desktop tiếng Việt.
CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
IID_SHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
IID_PERSIST_FILE = "{0000010B-0000-0000-C000-000000000046}"
# vị trí các hàm trong vtable, theo thứ tự khai báo ở ShObjIdl_core.h / ObjIdl.h
QUERY_INTERFACE, RELEASE = 0, 2
SET_DESCRIPTION, SET_WORKING_DIRECTORY, SET_ARGUMENTS, SET_ICON_LOCATION, SET_PATH = 7, 9, 11, 17, 20
SAVE = 6  # IPersistFile

ole32 = ctypes.OleDLL("ole32")
ole32.CoUninitialize.restype = None


class GUID(ctypes.Structure):
    _fields_ = [
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> "GUID":
        guid = cls()
        ole32.CLSIDFromString(text, ctypes.byref(guid))
        return guid


def com_call(obj: ctypes.c_void_p, index: int, argtypes: tuple, *args, restype=ctypes.HRESULT):
    """Gọi hàm thứ `index` trong vtable của đối tượng COM `obj`; HRESULT lỗi thì ném OSError."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])(obj, *args)


def launcher() -> Path:
    return Path(sys.prefix) / "Scripts" / "screen-translator-gui.exe"


def locations() -> dict[str, Path]:
    def folder(location: QStandardPaths.StandardLocation) -> Path:
        return Path(QStandardPaths.writableLocation(location))

    programs = folder(QStandardPaths.StandardLocation.ApplicationsLocation)  # ...\Start Menu\Programs
    return {
        "start_menu": programs / NAME,
        "desktop": folder(QStandardPaths.StandardLocation.DesktopLocation) / NAME,
        "autostart": programs / "Startup" / NAME,
    }


def states(paths: dict[str, Path] | None = None) -> dict[str, bool]:
    return {key: path.exists() for key, path in (paths or locations()).items()}


def apply(wanted: dict[str, bool], paths: dict[str, Path] | None = None) -> None:
    """Tạo / xoá từng shortcut cho khớp `wanted`; shortcut đã có thì để nguyên."""
    paths = paths or locations()
    for key, on in wanted.items():
        if not on:
            paths[key].unlink(missing_ok=True)
        elif not paths[key].exists():
            create(paths[key], launcher(), AUTOSTART_ARG if key == "autostart" else "", ICON_PATH)


def create(path: Path, target: Path, arguments: str, icon: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ole32.CoInitialize(None)
        initialized = True
    except OSError:  # luồng đã bật COM theo kiểu khác: vẫn dùng được
        initialized = False
    link, file = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(
            ctypes.byref(GUID.parse(CLSID_SHELL_LINK)),
            None,
            1,  # CLSCTX_INPROC_SERVER
            ctypes.byref(GUID.parse(IID_SHELL_LINK_W)),
            ctypes.byref(link),
        )
        text = (wintypes.LPCWSTR,)
        com_call(link, SET_PATH, text, str(target))
        com_call(link, SET_ARGUMENTS, text, arguments)
        com_call(link, SET_WORKING_DIRECTORY, text, str(target.parent))
        com_call(link, SET_DESCRIPTION, text, DESCRIPTION)
        com_call(link, SET_ICON_LOCATION, (wintypes.LPCWSTR, ctypes.c_int), str(icon), 0)
        guid = GUID.parse(IID_PERSIST_FILE)
        com_call(link, QUERY_INTERFACE, (ctypes.c_void_p, ctypes.c_void_p), ctypes.byref(guid), ctypes.byref(file))
        com_call(file, SAVE, (wintypes.LPCWSTR, wintypes.BOOL), str(path), True)
    finally:
        for obj in (file, link):
            if obj:
                com_call(obj, RELEASE, (), restype=ctypes.c_ulong)
        if initialized:
            ole32.CoUninitialize()
