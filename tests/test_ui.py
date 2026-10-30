from PIL import Image
from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit

from screen_translator import app as app_module
from screen_translator.config import Config
from screen_translator.ui.dialogs import SettingsDialog
from screen_translator.ui.overlay import MAX_PX, MIN_PX, Overlay, fit_text
from screen_translator.ui.region_selector import RegionSelector
from screen_translator.worker import Item

LONG_TEXT = "This is a rather long translated sentence that has to wrap over several lines. " * 4


def test_short_text_uses_the_biggest_font_and_keeps_the_box(qapp):
    rect = QRect(100, 100, 600, 120)
    font, box, padding = fit_text(rect, "Hello.")
    assert font.pixelSize() == MAX_PX
    assert box == rect
    assert padding == 10


def test_longer_text_gets_a_smaller_font(qapp):
    rect = QRect(0, 0, 600, 120)
    short_font = fit_text(rect, "Hello, how are you today?").font
    long_font = fit_text(rect, LONG_TEXT[:160]).font
    assert MIN_PX <= long_font.pixelSize() < short_font.pixelSize()


def test_text_that_never_fits_grows_the_box_downwards(qapp):
    rect = QRect(50, 60, 300, 40)
    font, box, _ = fit_text(rect, LONG_TEXT)
    assert font.pixelSize() == MIN_PX
    assert (box.x(), box.y(), box.width()) == (50, 60, 300)
    assert box.height() > rect.height()


def test_tiny_menu_label_grows_sideways_for_a_long_word(qapp):
    rect = QRect(20, 300, 28, 15)  # nhãn "台所" trên bản đồ phòng, tọa độ logic
    font, box, padding = fit_text(rect, "Kitchen")
    assert padding == 3 and font.pixelSize() == MIN_PX
    assert box.topLeft() == rect.topLeft() and box.width() > rect.width() and box.height() > rect.height()


def test_overlay_shows_text_over_the_region(qapp):
    overlay = Overlay()
    overlay.show_text(QRect(10, 20, 500, 100), "Hello.")
    assert overlay.isVisible() and overlay.has_text()
    assert overlay.geometry() == QRect(10, 20, 500, 100)
    overlay.hide()


def test_overlay_covers_all_blocks_and_hides_when_empty(qapp):
    overlay = Overlay()
    overlay.show_items([(QRect(100, 50, 300, 40), "Back to Title"), (QRect(20, 700, 600, 40), "First morning.")])
    assert overlay.geometry() == QRect(20, 50, 600, 690)
    overlay.grab()  # vẽ thử được
    overlay.show_items([])
    assert not overlay.isVisible() and not overlay.has_text()


def make_selector(qapp):
    screen = qapp.primaryScreen()
    size = screen.geometry().size() * screen.devicePixelRatio()
    selector = RegionSelector(screen, Image.new("RGB", (size.width(), size.height()), "gray"))
    events = {"selected": [], "cancelled": 0}
    selector.selected.connect(events["selected"].append)

    def on_cancel():
        events["cancelled"] += 1

    selector.cancelled.connect(on_cancel)
    selector.show()
    QTest.qWaitForWindowExposed(selector)
    return selector, events


def test_drag_selects_a_rect_in_any_direction(qapp):
    selector, events = make_selector(qapp)
    QTest.mousePress(selector, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(220, 180))
    QTest.mouseRelease(selector, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 30))
    assert events["cancelled"] == 0
    [rect] = events["selected"]
    assert (rect.topLeft(), rect.bottomRight()) == (QPoint(20, 30), QPoint(220, 180))


def test_tiny_drag_counts_as_cancel(qapp):
    selector, events = make_selector(qapp)
    QTest.mousePress(selector, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 50))
    QTest.mouseRelease(selector, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(53, 70))
    assert events == {"selected": [], "cancelled": 1}


def test_escape_and_right_click_cancel_once(qapp):
    selector, events = make_selector(qapp)
    QTest.keyClick(selector, Qt.Key.Key_Escape)
    assert events == {"selected": [], "cancelled": 1}

    selector, events = make_selector(qapp)
    QTest.mouseClick(selector, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(10, 10))
    assert events == {"selected": [], "cancelled": 1}


def settings_dialog(qapp, **hotkeys: str):
    """Đổi phím tắt của các hành động (select="Ctrl+Shift+Q"…) rồi bấm Lưu."""
    dialog = SettingsDialog(Config(), ["a:1b", "b:2b"])
    edits = {edit.text(): edit for edit in dialog.findChildren(QLineEdit)}
    for action, text in hotkeys.items():
        edits[Config().hotkeys[action]].setText(text)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    return dialog


def test_settings_rejects_duplicate_hotkeys(qapp):
    assert settings_dialog(qapp, select="Ctrl+Alt+Q", repeat="ctrl + alt + q").result() != QDialog.DialogCode.Accepted
    assert (
        settings_dialog(qapp, select="Ctrl+Alt+F").result() != QDialog.DialogCode.Accepted
    )  # trùng phím dịch cả cửa sổ


def test_settings_rejects_invalid_hotkey(qapp):
    assert settings_dialog(qapp, select="Q").result() != QDialog.DialogCode.Accepted


def test_settings_saves_valid_hotkeys(qapp):
    dialog = settings_dialog(qapp, select="Ctrl+Shift+Q")
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_config() == Config(hotkey_select="Ctrl+Shift+Q")


class FakeWorker(QObject):
    result = Signal(int, object, bool)
    failed = Signal(int, str)
    status = Signal(str, bool)
    idle = Signal(int)

    def __init__(self, config):
        super().__init__()
        self.jobs = []
        self.live_resets = 0

    def start(self):
        pass

    def submit_image(self, image):
        self.jobs.append(image)
        return len(self.jobs)

    def submit_live(self, image, *, settled):
        self.jobs.append(("live", settled))
        return len(self.jobs)

    def reset_live(self):
        self.live_resets += 1


def make_tray_app(monkeypatch):
    monkeypatch.setattr(app_module, "Worker", FakeWorker)
    monkeypatch.setattr(app_module.config_store, "load", lambda: Config())
    tray_app = app_module.TrayApp()
    messages = []
    monkeypatch.setattr(tray_app, "notify", lambda message, **_: messages.append(message))
    return tray_app, messages


def test_selected_region_with_one_block_is_covered_whole(qapp, monkeypatch):
    tray_app, messages = make_tray_app(monkeypatch)
    tray_app.repeat()  # chưa chọn vùng nào
    assert "Ctrl+Alt+T" in messages[-1]

    screen = qapp.primaryScreen()
    dpr = screen.devicePixelRatio()
    monitor = app_module.capture.Monitor(0, 0, round(screen.geometry().width() * dpr), 400)
    shot = Image.new("RGB", (monitor.width, monitor.height))
    tray_app._on_selected(QRect(10, 20, 300, 80), screen, monitor, shot)
    assert tray_app.worker.jobs[0].size == (round(300 * dpr), round(80 * dpr))
    assert tray_app.overlay.isVisible()  # "Đang dịch…"

    tray_app.worker.result.emit(2, [Item("猫", "Dog")], True)  # lượt cũ, bỏ qua
    tray_app.worker.result.emit(1, [Item("猫", "Cat", (5, 5, 40, 30))], True)
    assert (tray_app.last_ja, tray_app.last_en) == ("猫", "Cat")
    assert tray_app.overlay.geometry().topLeft() == QPoint(10, 20)  # phủ cả vùng chọn, không chỉ khung chữ

    tray_app.toggle_overlay()
    assert not tray_app.overlay.isVisible()
    tray_app.toggle_overlay()
    assert tray_app.overlay.isVisible()
    tray_app.overlay.hide()
    tray_app.hotkeys.clear()


class FakeWatcher:
    def __init__(self):
        self.events, self.forgotten = [], 0

    def update(self, frame, now):
        return self.events.pop(0) if self.events else None

    def forget(self):
        self.forgotten += 1


def test_live_mode_needs_a_region_first(qapp, monkeypatch):
    tray_app, messages = make_tray_app(monkeypatch)
    tray_app.toggle_live()
    assert not tray_app.live_timer.isActive() and "Ctrl+Alt+T" in messages[-1]
    assert not tray_app._menu_actions["live"].isChecked()
    tray_app.hotkeys.clear()


def test_live_mode_sends_one_frame_at_a_time_and_follows_results(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch)
    worker = tray_app.worker
    monitor = app_module.capture.Monitor(0, 0, 1920, 1080)
    tray_app._submit_image(
        app_module.capture.Region.from_physical(monitor, (0, 0), 1.0, 400, 800, 1600, 1000),
        Image.new("RGB", (1200, 200)),
        selection=True,
    )
    tray_app.overlay.excluded_from_capture = True
    monkeypatch.setattr(app_module.capture, "grab_region", lambda area: Image.new("RGB", (area.width, area.height)))
    tray_app.toggle_live()
    assert tray_app.live_timer.isActive() and tray_app._menu_actions["live"].isChecked()
    assert worker.live_resets == 1
    tray_app.watcher = watcher = FakeWatcher()

    watcher.events = ["settled", "moving"]
    tray_app._live_tick()
    tray_app._live_tick()  # lượt trước chưa xong: không chụp, không gửi thêm
    assert worker.jobs[1:] == [("live", True)] and watcher.events == ["moving"]

    worker.idle.emit(2)  # chữ không đổi
    tray_app._live_tick()
    assert worker.jobs[-1] == ("live", False)

    worker.result.emit(3, [Item("猫", "Cat", (5, 5, 40, 30))], True)  # câu mới
    assert watcher.forgotten == 1 and tray_app.overlay.isVisible()
    watcher.events = ["settled"]
    tray_app._live_tick()
    worker.result.emit(4, [], True)  # khung thoại trống
    assert not tray_app.overlay.isVisible() and tray_app.last_en == "Cat"

    tray_app.toggle_live()
    assert not tray_app.live_timer.isActive() and not tray_app._menu_actions["live"].isChecked()
    tray_app.hotkeys.clear()


def test_glossary_menu_creates_and_opens_the_file(qapp, monkeypatch, tmp_path):
    tray_app, _ = make_tray_app(monkeypatch)
    path, opened = tmp_path / "glossary.txt", []
    monkeypatch.setattr(app_module, "GLOSSARY_PATH", path)
    monkeypatch.setattr(app_module.os, "startfile", opened.append)
    tray_app.open_glossary()
    assert opened == [path] and path.read_text(encoding="utf-8").startswith("# Tên riêng")
    tray_app.hotkeys.clear()


def test_window_translation_puts_each_block_over_its_own_text(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch)
    monitor = app_module.capture.Monitor(0, 0, 1920, 1080)
    area = app_module.capture.Region.from_physical(monitor, (0, 0), 1.25, 0, 30, 1920, 1050)
    tray_app._submit_image(area, Image.new("RGB", (1920, 1020)), selection=False)
    items = [
        Item("屋敷で迎える、最初の朝だ。", "The first morning at the mansion.", (392, 981, 668, 1007)),
        Item("設定", None, (1840, 976, 1890, 996)),  # chưa dịch xong: chưa hiện
    ]
    assert tray_app._overlay_items(items) == [(QRect(314, 809, 221, 21), "The first morning at the mansion.")]
    tray_app.worker.result.emit(1, items, False)
    assert tray_app.overlay.isVisible() and tray_app.overlay.geometry().topLeft() == QPoint(314, 809)
    tray_app.overlay.hide()
    tray_app.hotkeys.clear()
