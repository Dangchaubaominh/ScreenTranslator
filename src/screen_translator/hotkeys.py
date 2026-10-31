"""Phím tắt toàn cục bằng RegisterHotKey: Windows gửi WM_HOTKEY về một cửa sổ ẩn của app.

Khác với hook bàn phím (pynput), RegisterHotKey vẫn chạy khi game mở bằng quyền Admin.
"""

import logging
from ctypes import wintypes

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from . import win32

log = logging.getLogger(__name__)
_MODIFIERS = {"ctrl": win32.MOD_CONTROL, "alt": win32.MOD_ALT, "shift": win32.MOD_SHIFT, "win": win32.MOD_WIN}
_NAMED_KEYS = {f"f{i}": 0x6F + i for i in range(1, 13)} | {
    "space": 0x20,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}
ESCAPE_ID = 0x7FFF  # ngoài dải id của phím tắt trong cài đặt (1, 2, …)


def parse_hotkey(text: str) -> tuple[int, int]:
    """'Ctrl+Alt+T' → (cờ phím bổ trợ, mã phím ảo). Sai định dạng thì báo ValueError."""
    *modifier_names, key = [part.strip() for part in text.split("+")]
    modifiers = 0
    for name in modifier_names:
        if name.lower() not in _MODIFIERS:
            raise ValueError(f"phím bổ trợ không hợp lệ: {name!r} (dùng Ctrl, Alt, Shift, Win)")
        modifiers |= _MODIFIERS[name.lower()]
    if not modifiers:
        raise ValueError("cần ít nhất một phím Ctrl / Alt / Shift / Win")
    if len(key) == 1 and key.isascii() and key.isalnum():
        return modifiers, ord(key.upper())
    if key.lower() in _NAMED_KEYS:
        return modifiers, _NAMED_KEYS[key.lower()]
    raise ValueError(f"phím không hợp lệ: {key!r} (dùng A–Z, 0–9, F1–F12, Space…)")


class HotkeyWindow(QWidget):
    """Cửa sổ ẩn nhận WM_HOTKEY; phát `triggered(tên hành động)`."""

    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self._hwnd = int(self.winId())  # tạo cửa sổ native nhưng không hiện ra
        self._actions: dict[int, str] = {}

    def set_hotkeys(self, hotkeys: dict[str, str]) -> list[str]:
        """Đăng ký lại toàn bộ phím tắt (hành động → 'Ctrl+Alt+T'). Trả về danh sách lỗi để báo người dùng."""
        escape = self.has_escape()
        self.clear()
        self.set_escape(escape)
        errors = []
        for hotkey_id, (action, text) in enumerate(hotkeys.items(), start=1):
            try:
                modifiers, vk = parse_hotkey(text)
            except ValueError as e:
                errors.append(f"{text}: {e}")
                continue
            if win32.register_hotkey(self._hwnd, hotkey_id, modifiers | win32.MOD_NOREPEAT, vk):
                self._actions[hotkey_id] = action
            else:
                errors.append(f"{text}: chương trình khác đang dùng phím tắt này")
        return errors

    def set_escape(self, held: bool) -> None:
        """Giữ / nhả phím Esc (không phím bổ trợ); bấm thì phát `triggered("escape")`.

        Chỉ giữ lúc cần: đang giữ thì game không nhận được Esc.
        """
        if held == self.has_escape():
            return
        if not held:
            win32.unregister_hotkey(self._hwnd, ESCAPE_ID)
            del self._actions[ESCAPE_ID]
        elif win32.register_hotkey(self._hwnd, ESCAPE_ID, win32.MOD_NOREPEAT, win32.VK_ESCAPE):
            self._actions[ESCAPE_ID] = "escape"
        else:
            log.warning("Không giữ được phím Esc: chương trình khác đang dùng")

    def has_escape(self) -> bool:
        return ESCAPE_ID in self._actions

    def clear(self) -> None:
        for hotkey_id in self._actions:
            win32.unregister_hotkey(self._hwnd, hotkey_id)
        self._actions.clear()

    def nativeEvent(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == win32.WM_HOTKEY and msg.wParam in self._actions:
            self.triggered.emit(self._actions[msg.wParam])
            return True, 0
        return super().nativeEvent(event_type, message)
