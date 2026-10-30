"""Ứng dụng chạy nền ở khay hệ thống: phím tắt → chọn vùng → OCR + dịch → overlay đè lên chữ gốc."""

import logging
import os
import sys

import ollama
from PIL import Image
from PySide6.QtCore import QObject, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QIcon, QPainter, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from . import capture, win32
from . import config as config_store
from .config import GLOSSARY_PATH, HOTKEY_LABELS
from .glossary import ensure_file
from .hotkeys import HotkeyWindow
from .ui.dialogs import EditDialog, SettingsDialog
from .ui.overlay import Overlay
from .ui.region_selector import RegionSelector
from .worker import Item, Worker

log = logging.getLogger(__name__)
APP_NAME = "ScreenTranslator"
MIN_WINDOW = 100  # pixel; cửa sổ đang mở nhỏ hơn thế trên màn hình này thì dịch cả màn hình


def make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(59, 130, 246))
    painter.drawRoundedRect(0, 0, 64, 64, 14, 14)
    font = QFont("Yu Gothic UI")
    font.setPixelSize(42)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "訳")
    painter.end()
    return QIcon(pixmap)


class TrayApp(QObject):
    def __init__(self):
        super().__init__()
        self.config = config_store.load()
        self.worker = Worker(self.config)
        self.overlay = Overlay()
        self.edit_dialog = EditDialog()
        self.hotkeys = HotkeyWindow()
        self.selector: RegionSelector | None = None
        self.area: capture.Region | None = None  # vùng chụp gần nhất: vùng đã chọn, hoặc cả cửa sổ game
        self.area_is_selection = True
        self.job = 0
        self.last_ja = self.last_en = ""
        self._previous_foreground = 0

        self._handlers = {
            "select": self.start_selection,
            "screen": self.translate_window,
            "repeat": self.repeat,
            "toggle": self.toggle_overlay,
            "edit": self.open_editor,
        }
        self.menu = QMenu()  # giữ tham chiếu, không thì Python thu hồi mất menu
        self._menu_actions = {action: self.menu.addAction(label) for action, label in HOTKEY_LABELS.items()}
        for action, menu_action in self._menu_actions.items():
            # chờ menu đóng hẳn rồi mới chụp màn hình, không thì ảnh chụp dính cả menu
            menu_action.triggered.connect(lambda *_, handler=self._handlers[action]: QTimer.singleShot(200, handler))
        self.menu.addSeparator()
        self.menu.addAction("Tên riêng, thuật ngữ…").triggered.connect(self.open_glossary)
        self.menu.addAction("Cài đặt…").triggered.connect(self.open_settings)
        self.menu.addAction("Thoát").triggered.connect(self.quit)
        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip(APP_NAME)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)

        self.worker.result.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.status.connect(self.on_status)
        self.worker.start()
        self.hotkeys.triggered.connect(lambda action: self._handlers[action]())
        self.edit_dialog.retranslate.connect(self.retranslate)
        self._register_hotkeys()
        self.tray.show()

    def _register_hotkeys(self) -> None:
        errors = self.hotkeys.set_hotkeys(self.config.hotkeys)
        for action, menu_action in self._menu_actions.items():
            menu_action.setText(f"{HOTKEY_LABELS[action]}\t{self.config.hotkeys[action]}")
        if errors:
            self.notify("Không đăng ký được phím tắt:\n" + "\n".join(errors), warning=True)

    def notify(self, message: str, *, warning: bool = False) -> None:
        icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(APP_NAME, message, icon)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # bấm chuột trái vào icon
            self.start_selection()

    # --- chụp và gửi đi dịch ---

    @staticmethod
    def _screen_at_cursor() -> tuple[capture.Monitor, QScreen]:
        monitor = capture.monitor_at(*win32.cursor_pos())
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return monitor, screen

    def start_selection(self) -> None:
        if self.selector is not None:
            return
        monitor, screen = self._screen_at_cursor()
        shot = capture.grab_monitor(monitor)  # chụp trước khi hiện màn chọn vùng
        self._previous_foreground = win32.foreground_window()
        self.selector = RegionSelector(screen, shot)
        self.selector.selected.connect(lambda rect: self._on_selected(rect, screen, monitor, shot))
        self.selector.cancelled.connect(self._end_selection)
        self.selector.show()
        self.selector.raise_()
        self.selector.activateWindow()

    def _end_selection(self) -> None:
        self.selector = None
        win32.set_foreground_window(self._previous_foreground)  # trả focus lại cho game

    def _on_selected(self, rect: QRect, screen, monitor: capture.Monitor, shot: Image.Image) -> None:
        self._end_selection()
        origin = screen.geometry().topLeft()
        area = capture.Region.from_selection(
            monitor,
            (origin.x(), origin.y()),
            screen.devicePixelRatio(),
            rect.x(),
            rect.y(),
            rect.width(),
            rect.height(),
        )
        self.last_en = ""
        self._submit_image(area, shot.crop(area.crop_box()), selection=True)

    def translate_window(self) -> None:
        """Dịch mọi chữ trong cửa sổ đang mở (game), mỗi dòng / đoạn một khung như Google Lens."""
        monitor, screen = self._screen_at_cursor()
        origin, dpr = screen.geometry().topLeft(), screen.devicePixelRatio()
        whole = (monitor.left, monitor.top, monitor.left + monitor.width, monitor.top + monitor.height)
        hwnd = win32.foreground_window()
        rect = win32.window_rect(hwnd) if win32.window_process_id(hwnd) != os.getpid() else None
        area = capture.Region.from_physical(monitor, (origin.x(), origin.y()), dpr, *(rect or whole))
        if area.width < MIN_WINDOW or area.height < MIN_WINDOW:  # cửa sổ nằm ở màn hình khác: dịch cả màn hình
            area = capture.Region.from_physical(monitor, (origin.x(), origin.y()), dpr, *whole)
        self._submit_image(area, self._grab(area), selection=False)

    def repeat(self) -> None:
        """Chụp lại vùng trước (hộp thoại game ở chỗ cũ, hoặc cả cửa sổ) và dịch chữ mới."""
        if self.area is None:
            self.notify(f"Chưa có vùng nào. Bấm {self.config.hotkey_select} để chọn vùng chữ.")
            return
        self._submit_image(self.area, self._grab(self.area), selection=self.area_is_selection)

    def _grab(self, area: capture.Region) -> Image.Image:
        if not self.overlay.excluded_from_capture:
            self.overlay.hide()
            QApplication.processEvents()
        return capture.grab_region(area)

    def _submit_image(self, area: capture.Region, image: Image.Image, *, selection: bool) -> None:
        self.area, self.area_is_selection = area, selection
        self.job = self.worker.submit_image(image)
        # vùng chọn: câu cũ mờ đi trong lúc chờ câu mới
        self._show_status((self.last_en or "Đang dịch…") if selection else "Đang đọc chữ…")

    def retranslate(self, ja: str) -> None:
        self.job = self.worker.submit_text(ja)
        self.edit_dialog.set_busy()
        if self.area_is_selection:
            self._show_status("Đang dịch…")

    def _show_status(self, text: str) -> None:
        """Chữ xám phủ cả vùng đã chọn; khi dịch cả cửa sổ thì là một khung nhỏ ở góc trên-trái."""
        if self.area is None:
            return
        x, y, w, h = self.area.to_logical()
        rect = QRect(x, y, w, h) if self.area_is_selection else QRect(x + 16, y + 16, min(w - 32, 420), 48)
        self.overlay.show_text(rect, text, dim=True)

    def _overlay_items(self, items: list[Item]) -> list[tuple[QRect, str]]:
        """Khung (tọa độ logic) và bản dịch của các khối đã dịch xong."""
        if self.area is None:
            return []
        if self.area_is_selection and len(items) == 1:
            # một khối chữ (thường là hộp thoại): phủ cả vùng đã chọn cho chữ dịch to, dễ đọc
            return [(QRect(*self.area.to_logical()), items[0].en)] if items[0].en is not None else []
        return [
            (QRect(*self.area.sub(*item.box).to_logical()), item.en)
            for item in items
            if item.box is not None and item.en is not None
        ]

    # --- kết quả từ luồng phụ ---

    def on_result(self, job: int, items: list[Item], finished: bool) -> None:
        if job != self.job:
            return
        shown = self._overlay_items(items)
        if shown:
            self.overlay.show_items(shown)
        if finished:
            self.last_ja = "\n".join(item.ja for item in items)
            self.last_en = "\n".join(item.en for item in items)
            if self.edit_dialog.isVisible():
                self.edit_dialog.set_result(self.last_ja, self.last_en)

    def on_failed(self, job: int, message: str) -> None:
        if job != self.job:
            return
        self._show_status(message)
        if self.edit_dialog.isVisible():
            self.edit_dialog.set_result(self.last_ja, message)

    def on_status(self, message: str, is_error: bool) -> None:
        log.info("Trạng thái: %s", message)
        self.tray.setToolTip(f"{APP_NAME} — {message}")
        if is_error:
            self.notify(message, warning=True)

    # --- các hành động khác ---

    def toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
        elif self.overlay.has_text():
            self.overlay.show()

    def open_editor(self) -> None:
        self.edit_dialog.set_result(self.last_ja, self.last_en)
        self.edit_dialog.show()
        self.edit_dialog.raise_()
        self.edit_dialog.activateWindow()

    def open_glossary(self) -> None:
        """Mở glossary.txt bằng trình sửa mặc định (Notepad). Lưu xong thì lượt dịch sau dùng ngay."""
        try:
            os.startfile(ensure_file(GLOSSARY_PATH))
        except OSError as e:
            log.exception("Không mở được glossary")
            self.notify(f"Không mở được {GLOSSARY_PATH}: {e}", warning=True)

    def open_settings(self) -> None:
        try:
            models = sorted(m.model for m in ollama.Client().list().models)
        except (ConnectionError, ollama.ResponseError):
            models = []  # Ollama chưa chạy: vẫn cho gõ tên model bằng tay
        dialog = SettingsDialog(self.config, models)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.result_config()
            config_store.save(self.config)
            self.worker.reconfigure(self.config)
            self._register_hotkeys()

    def quit(self) -> None:
        self.hotkeys.clear()
        self.overlay.hide()
        self.tray.hide()
        self.worker.stop()  # gỡ model dịch khỏi VRAM
        QApplication.quit()


def run() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    tray_app = TrayApp()
    hotkeys = tray_app.config.hotkeys
    tray_app.notify(
        f"Đang chạy nền. {hotkeys['select']}: chọn vùng để dịch · {hotkeys['screen']}: dịch cả cửa sổ game."
    )
    return app.exec()
