"""Ứng dụng chạy nền ở khay hệ thống: phím tắt → chọn vùng → OCR + dịch → overlay đè lên chữ gốc."""

import getpass
import logging
import os
import sys
import time
from dataclasses import replace

import ollama
from PIL import Image
from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QIcon, QPainter, QPixmap, QScreen
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from . import capture, live, shortcuts, win32
from . import config as config_store
from .config import GLOSSARY_PATH, HOTKEY_LABELS
from .glossary import ensure_file
from .hotkeys import HotkeyWindow
from .ui.dialogs import EditDialog, GuideDialog, SettingsDialog, StartupOptions
from .ui.overlay import GAP, HINT_PX, Appearance, Overlay, clamp, hint_size
from .ui.region_selector import RegionSelector
from .worker import READY, Item, Worker

log = logging.getLogger(__name__)
APP_NAME = "ScreenTranslator"
INSTANCE_KEY = f"{APP_NAME}-{getpass.getuser()}"  # kênh để bản mở sau báo cho bản đang chạy
MIN_WINDOW = 100  # pixel; cửa sổ đang mở nhỏ hơn thế trên màn hình này thì dịch cả màn hình
ICON_COLOR, LIVE_ICON_COLOR = QColor(59, 130, 246), QColor(22, 163, 74)  # xanh dương; xanh lá khi live mode bật
LOADING_ICON_COLOR = QColor(128, 136, 150)  # xám: đang nạp OCR / model dịch


def make_icon(color: QColor = ICON_COLOR, size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    font = QFont("Yu Gothic UI")
    font.setPixelSize(round(size * 0.66))
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
        self.overlay = Overlay(Appearance.from_config(self.config))
        self.hint = Overlay(Appearance(max_px=HINT_PX))  # thông báo ngắn tự tắt, thay cho popup của Windows
        self.hint_timer = QTimer(self, singleShot=True)
        self.hint_timer.timeout.connect(self.hint.hide)
        self.edit_dialog = EditDialog()
        self.guide: GuideDialog | None = None
        self.hotkeys = HotkeyWindow()
        self.selector: RegionSelector | None = None
        self.area: capture.Region | None = None  # vùng chụp gần nhất: vùng đã chọn, hoặc cả cửa sổ game
        self.area_is_selection = True
        self.job = 0
        self.last_ja = self.last_en = ""
        self.shown_items: list[Item] = []  # bản dịch đang hiện, để vẽ lại khi đổi cài đặt hiển thị
        self.status_text, self.loading = "Đang khởi động…", True
        self._previous_foreground = 0
        self.live_timer = QTimer(self)
        self.live_timer.setInterval(live.POLL_MS)
        self.live_timer.timeout.connect(self._live_tick)
        self.watcher = live.ChangeWatcher()
        self._live_job: int | None = None  # lượt live đang chờ luồng phụ; chưa xong thì không gửi thêm

        self._handlers = {
            "select": self.start_selection,
            "screen": self.translate_window,
            "repeat": self.repeat,
            "live": self.toggle_live,
            "toggle": self.toggle_overlay,
            "edit": self.open_editor,
        }
        self.menu = QMenu()  # giữ tham chiếu, không thì Python thu hồi mất menu
        self._menu_actions = {action: self.menu.addAction(label) for action, label in HOTKEY_LABELS.items()}
        for action, menu_action in self._menu_actions.items():
            # chờ menu đóng hẳn rồi mới chụp màn hình, không thì ảnh chụp dính cả menu
            menu_action.triggered.connect(lambda *_, handler=self._handlers[action]: QTimer.singleShot(200, handler))
        self._menu_actions["live"].setCheckable(True)
        self.menu.addSeparator()
        self.menu.addAction("Tên riêng, thuật ngữ…").triggered.connect(self.open_glossary)
        self.menu.addAction("Cài đặt…").triggered.connect(self.open_settings)
        self.menu.addAction("Hướng dẫn…").triggered.connect(self.show_guide)
        self.menu.addAction("Thoát").triggered.connect(self.quit)
        self.tray = QSystemTrayIcon()
        self._update_tray()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)

        self.worker.result.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.status.connect(self.on_status)
        self.worker.idle.connect(self.on_idle)
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
        """Lỗi: popup của Windows (còn lại trong Notification Center). Thông tin: dòng chữ ngắn tự tắt."""
        if warning:
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Warning)
        else:
            self._show_hint(message)

    def _show_hint(self, message: str) -> None:
        size = hint_size(message)
        if self.area is not None:  # ngay trên vùng đang dịch, chỗ người dùng đang nhìn
            x, y, _, _ = self.area.to_logical()
            rect = QRect(QPoint(x, y - GAP - size.height()), size)
        else:  # góc phải dưới, cạnh icon ở khay hệ thống
            corner = QGuiApplication.primaryScreen().availableGeometry().bottomRight()
            rect = QRect(corner - QPoint(size.width() + 12, size.height() + 12), size)
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        self.hint.show_text(clamp(rect, screen.geometry()), message)
        self.hint_timer.start(min(8000, 2500 + 40 * len(message)))

    def _update_tray(self) -> None:
        """Màu icon và tooltip theo trạng thái: đang nạp (xám), sẵn sàng (xanh dương), live mode (xanh lá)."""
        live_on = self.live_timer.isActive()
        color = LIVE_ICON_COLOR if live_on else LOADING_ICON_COLOR if self.loading else ICON_COLOR
        self.tray.setIcon(make_icon(color))
        self.tray.setToolTip(f"{APP_NAME} — {self.status_text}" + (" · live mode đang bật" if live_on else ""))

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
        if area != self.area:  # live mode theo dõi vùng mới
            self.watcher = live.ChangeWatcher()
        self.area, self.area_is_selection = area, selection
        self.job = self.worker.submit_image(image)
        if self.loading:  # lần đầu phải chờ nạp model: nói rõ đang chờ gì
            self._show_status(self.status_text)
        else:  # vùng chọn: câu cũ mờ đi trong lúc chờ câu mới
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
        self.overlay.show_text(rect, text, dim=True, position=self._position())

    def _position(self) -> str:
        """Bản dịch vùng đã chọn đặt theo cài đặt; dịch cả cửa sổ thì luôn đè lên từng khối chữ."""
        return self.config.overlay_position if self.area_is_selection else "cover"

    def _overlay_items(self, items: list[Item]) -> list[tuple[QRect, str]]:
        """Khung (tọa độ logic) và bản dịch của các khối đã dịch xong."""
        if self.area is None:
            return []
        if self.area_is_selection and (len(items) == 1 or self._position() != "cover"):
            # một khối chữ (thường là hộp thoại), hoặc bản dịch đặt cạnh vùng: một khung theo cả vùng đã chọn
            done = [item.en for item in items if item.en is not None]
            return [(QRect(*self.area.to_logical()), "\n".join(done))] if done else []
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
        if shown or (finished and not items):  # live mode: khung thoại trống thì ẩn bản dịch cũ
            self.overlay.show_items(shown, position=self._position())
            self.shown_items = items
        if finished and job == self._live_job:
            self._live_job = None
            self.watcher.forget()
        if finished and items:
            self.last_ja = "\n".join(item.ja for item in items)
            self.last_en = "\n".join(item.en for item in items)
            if self.edit_dialog.isVisible():
                self.edit_dialog.set_result(self.last_ja, self.last_en)

    def on_idle(self, job: int) -> None:
        if job == self._live_job:
            self._live_job = None

    def on_failed(self, job: int, message: str) -> None:
        if job == self._live_job:
            self._live_job = None
        if job != self.job:
            return
        self._show_status(message)
        if self.edit_dialog.isVisible():
            self.edit_dialog.set_result(self.last_ja, message)

    def on_status(self, message: str, is_error: bool) -> None:
        log.info("Trạng thái: %s", message)
        self.status_text, self.loading = message, not is_error and message != READY
        self._update_tray()
        if is_error:
            self.notify(message, warning=True)

    # --- live mode ---

    def toggle_live(self) -> None:
        if self.live_timer.isActive():
            self._set_live(False)
            self.notify("Đã tắt live mode.")
            return
        if self.area is None:
            self._set_live(False)
            self.notify(
                f"Chọn vùng hộp thoại trước ({self.config.hotkey_select}), "
                f"rồi bấm {self.config.hotkey_live} để bật live mode."
            )
            return
        if not self.overlay.excluded_from_capture:
            # app sẽ tự đọc lại bản dịch của chính nó trên màn hình
            self._set_live(False)
            self.notify(
                "Windows này không cho giấu bản dịch khỏi ảnh chụp, nên không bật được live mode.", warning=True
            )
            return
        self.watcher = live.ChangeWatcher()
        self.worker.reset_live()
        self._set_live(True)
        self.notify("Đã bật live mode: câu mới trong vùng đã chọn sẽ tự được dịch.")

    def _set_live(self, on: bool) -> None:
        if on:
            self.live_timer.start()
        else:
            self.live_timer.stop()
        self._live_job = None
        self._menu_actions["live"].setChecked(on)
        self._update_tray()

    def _live_busy(self) -> bool:
        # lượt live bị lượt bấm tay mới hơn thay thế thì luồng phụ bỏ qua nó: không còn coi là bận
        return self._live_job is not None and self._live_job == self.job

    def _live_tick(self) -> None:
        if self.area is None or self._live_busy():
            return
        image = capture.grab_region(self.area)
        event = self.watcher.update(live.thumbnail(image), time.monotonic())
        if event:
            self.job = self._live_job = self.worker.submit_live(image, settled=event == "settled")

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
        startup = self._shortcut_states()
        dialog = SettingsDialog(self.config, models, startup)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.result_config()
            config_store.save(self.config)
            self.worker.reconfigure(self.config)
            self.overlay.set_appearance(Appearance.from_config(self.config))
            if self.overlay.isVisible():  # vẽ lại bản dịch đang hiện theo kiểu mới
                self.overlay.show_items(self._overlay_items(self.shown_items), position=self._position())
            self._register_hotkeys()
            if (wanted := dialog.startup.wanted()) is not None and wanted != startup:
                self._apply_shortcuts(wanted)

    # --- hướng dẫn, shortcut ---

    def show_guide(self, *, first_run: bool = False) -> None:
        """Màn hình chào lần đầu (kèm lựa chọn tạo shortcut); sau đó mở lại từ menu, hoặc khi mở app lần nữa."""
        if self.guide is None:
            startup = None
            if first_run:
                states = self._shortcut_states()  # lần đầu: gợi ý menu Start + Desktop, tự chạy thì để người dùng chọn
                startup = StartupOptions(
                    states and {key: on or key != "autostart" for key, on in states.items()},
                )
            self.guide = GuideDialog(self.config.hotkeys, startup)
            self.guide.finished.connect(self._on_guide_closed)
        self.guide.show()
        self.guide.raise_()
        self.guide.activateWindow()

    def _on_guide_closed(self, result: int) -> None:
        guide, self.guide = self.guide, None
        guide.deleteLater()
        if guide.startup is None:
            return
        if result == QDialog.DialogCode.Accepted and (wanted := guide.startup.wanted()) is not None:
            self._apply_shortcuts(wanted)
        self.config = replace(self.config, welcomed=True)
        config_store.save(self.config)

    @staticmethod
    def _shortcut_states() -> dict[str, bool] | None:
        return shortcuts.states() if shortcuts.launcher().exists() else None

    def _apply_shortcuts(self, wanted: dict[str, bool]) -> None:
        try:
            shortcuts.ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
            make_icon(size=256).pixmap(256).save(str(shortcuts.ICON_PATH))
            shortcuts.apply(wanted)
        except OSError as e:
            log.exception("Không tạo được shortcut")
            self.notify(f"Không tạo được shortcut: {e}", warning=True)

    def quit(self) -> None:
        self.live_timer.stop()
        self.hotkeys.clear()
        self.overlay.hide()
        self.hint.hide()
        self.tray.hide()
        self.worker.stop()  # gỡ model dịch khỏi VRAM
        QApplication.quit()


def _wake_running_instance() -> bool:
    """Đã có một bản đang chạy (vd. bấm shortcut lần nữa) thì báo nó mở hướng dẫn, trả về True."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_KEY)
    if not socket.waitForConnected(500):
        return False
    socket.disconnectFromServer()
    return True


def _listen_for_wake(tray_app: TrayApp) -> None:
    server = QLocalServer(tray_app)

    def on_connection() -> None:
        server.nextPendingConnection().deleteLater()
        tray_app.show_guide()

    server.newConnection.connect(on_connection)
    if not server.listen(INSTANCE_KEY):
        log.warning("Không mở được kênh %s: %s", INSTANCE_KEY, server.errorString())


def run(*, autostart: bool = False) -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    if _wake_running_instance():  # chỉ một bản chạy: hai bản sẽ tranh nhau phím tắt
        return 0
    tray_app = TrayApp()
    _listen_for_wake(tray_app)
    hotkeys = tray_app.config.hotkeys
    if not tray_app.config.welcomed:
        tray_app.show_guide(first_run=True)
    elif not autostart:
        tray_app.notify(
            f"ScreenTranslator đang chạy nền (icon 訳 ở khay hệ thống).\n{hotkeys['select']}: chọn vùng · "
            f"{hotkeys['live']}: live mode · {hotkeys['screen']}: dịch cả cửa sổ game"
        )
    return app.exec()
