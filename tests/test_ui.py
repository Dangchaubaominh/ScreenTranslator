import os

import pytest
from conftest import wait_until
from PIL import Image
from PySide6.QtCore import QObject, QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QMenu, QPushButton, QSystemTrayIcon

from screen_translator import app as app_module
from screen_translator.config import Config
from screen_translator.glossary import Entry
from screen_translator.ui import dialogs as dialogs_module
from screen_translator.ui import window as window_module
from screen_translator.ui.overlay import (
    GAP,
    MAX_PX,
    MIN_PX,
    Appearance,
    Overlay,
    fit_blocks,
    fit_text,
)
from screen_translator.ui.panel import ControlPanel
from screen_translator.ui.region_selector import RegionSelector
from screen_translator.ui.window import GLOSSARY_KINDS, SWATCHES, MainWindow
from screen_translator.worker import READY, Item

LONG_TEXT = "This is a rather long translated sentence that has to wrap over several lines. " * 4


def test_short_text_uses_the_biggest_font_and_keeps_the_box(qapp):
    rect = QRect(100, 100, 600, 120)
    fitted = fit_text(rect, "Hello.")
    assert fitted.font.pixelSize() == MAX_PX
    assert fitted.rect == rect
    assert fitted.padding == fitted.vpadding == 10


def test_longer_text_gets_a_smaller_font(qapp):
    rect = QRect(0, 0, 600, 120)
    short_font = fit_text(rect, "Hello, how are you today?").font
    long_font = fit_text(rect, LONG_TEXT[:160]).font
    assert MIN_PX <= long_font.pixelSize() < short_font.pixelSize()


def test_text_that_never_fits_grows_the_box_downwards(qapp):
    rect = QRect(50, 60, 300, 40)
    font, box, *_ = fit_text(rect, LONG_TEXT)
    assert font.pixelSize() == MIN_PX
    assert (box.x(), box.y(), box.width()) == (50, 60, 300)
    assert box.height() > rect.height()


def test_tiny_menu_label_grows_sideways_for_a_long_word(qapp):
    rect = QRect(20, 300, 28, 15)  # nhãn "台所" trên bản đồ phòng, tọa độ logic
    font, box, padding, _ = fit_text(rect, "Kitchen")
    assert padding == 3 and font.pixelSize() == MIN_PX
    assert box.topLeft() == rect.topLeft() and box.width() > rect.width() and box.height() > rect.height()


def overlapping(rects: list[QRect]) -> list[tuple[int, int]]:
    return [(i, j) for i, a in enumerate(rects) for j, b in enumerate(rects) if i < j and a.intersects(b)]


def test_window_blocks_grow_into_free_space_without_overlapping(qapp):
    # bản đồ phòng: nhãn chữ Nhật ngắn, cao ~18 px, bản dịch tiếng Anh dài hơn nhiều
    window = QRect(0, 0, 800, 600)
    kitchen, lounge = QRect(20, 100, 28, 18), QRect(200, 100, 28, 18)
    restaurant, hall, bath = QRect(20, 200, 60, 18), QRect(180, 200, 60, 18), QRect(20, 260, 60, 18)
    blocks = [
        (kitchen, "Kitchen"),
        (lounge, "Sakuya's room"),
        (restaurant, "Hayashida's restaurant"),
        (hall, "Hall"),
        (bath, "Bath"),
    ]
    fitted = fit_blocks(blocks, MAX_PX, window)
    boxes = [f.rect for f in fitted]
    assert overlapping(boxes) == []
    assert all(
        window.contains(box) and box.topLeft() == rect.topLeft() for box, (rect, _) in zip(boxes, blocks, strict=True)
    )
    # còn chỗ bên phải: chỉ nới ngang, vẫn một dòng, chữ cỡ vừa nhãn gốc
    assert boxes[0].height() == kitchen.height() and boxes[0].right() < lounge.left()
    assert fitted[0].font.pixelSize() == MIN_PX
    # bên phải có nhãn khác: xuống dòng trong chỗ trống, không đè nhãn bên phải hay bên dưới
    assert restaurant.height() < boxes[2].height() and boxes[2].bottom() < bath.top()
    assert boxes[3] == hall  # vừa sẵn: giữ đúng khung chữ gốc


def test_untranslated_block_keeps_its_space(qapp):
    restaurant, hall = QRect(20, 200, 60, 18), QRect(180, 200, 60, 18)
    fitted = fit_blocks([(restaurant, "Hayashida's restaurant"), (hall, None)], MAX_PX, QRect(0, 0, 800, 600))
    assert fitted[1] is None and not fitted[0].rect.intersects(hall)


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


def test_appearance_follows_the_settings(qapp):
    appearance = Appearance.from_config(Config(overlay_font_px=20, overlay_opacity=50, overlay_color="#ffffff"))
    assert appearance.max_px == 20 and round(appearance.background.alphaF(), 2) == 0.5
    assert appearance.text_color().lightnessF() < 0.2  # nền trắng thì chữ tối
    assert Appearance().text_color().lightnessF() > 0.8
    assert fit_text(QRect(0, 0, 600, 120), "Hello.", appearance.max_px).font.pixelSize() == 20


def test_see_through_background_outlines_the_text(qapp):
    assert Appearance.from_config(Config(overlay_opacity=88)).outline_color() is None  # nền đặc: không cần viền
    light_text = Appearance.from_config(Config(overlay_opacity=20)).outline_color()
    dark_text = Appearance.from_config(Config(overlay_opacity=0, overlay_color="#ffffff")).outline_color()
    assert light_text.lightnessF() < 0.2 and dark_text.lightnessF() > 0.8  # viền ngược màu chữ
    overlay = Overlay(Appearance.from_config(Config(overlay_opacity=0)))
    overlay.show_text(QRect(10, 20, 300, 60), "Hello.")
    overlay.grab()  # vẽ thử được
    overlay.hide()


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


@pytest.fixture(autouse=True)
def temporary_glossary(monkeypatch, tmp_path):
    monkeypatch.setattr(window_module, "GLOSSARY_PATH", tmp_path / "glossary.txt")
    monkeypatch.setattr(dialogs_module, "GLOSSARY_PATH", tmp_path / "glossary.txt")


def settings_dialog(qapp, **hotkeys: str):
    """Đổi phím tắt của các hành động (select="Ctrl+Shift+Q"…) rồi bấm Lưu."""
    dialog = MainWindow(Config(), ["a:1b", "b:2b"])
    edits = {edit.text(): edit for edit in dialog.findChildren(QLineEdit, "keyedit")}
    for action, text in hotkeys.items():
        edits[Config().hotkeys[action]].setText(text)
    dialog.findChild(QPushButton, "primary").click()
    return dialog


def test_settings_rejects_duplicate_hotkeys(qapp):
    assert settings_dialog(qapp, select="Ctrl+Alt+Q", repeat="ctrl + alt + q").result() != QDialog.DialogCode.Accepted
    assert (
        settings_dialog(qapp, select="Ctrl+Alt+F").result() != QDialog.DialogCode.Accepted
    )  # trùng phím dịch cả cửa sổ


def test_settings_rejects_invalid_hotkey(qapp):
    dialog = settings_dialog(qapp, select="Q")
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.current_page() == "hotkeys"  # mở đúng trang có ô cần sửa


def test_guide_shows_the_hotkeys_being_edited(qapp):
    dialog = MainWindow(Config(), [])
    assert dialog.current_page() == "guide"
    chips = [chip.text() for chip in dialog.findChildren(QLabel, "key")]
    assert chips.count("Ctrl+Alt+T") == 1 and chips.count("Ctrl+Alt+L") == 2
    dialog.findChildren(QLineEdit, "keyedit")[0].setText("Ctrl+Shift+Q")  # sửa phím Chọn vùng ở trang Phím tắt
    assert "Ctrl+Shift+Q" in [chip.text() for chip in dialog.findChildren(QLabel, "key")]


def test_settings_saves_valid_hotkeys(qapp):
    dialog = settings_dialog(qapp, select="Ctrl+Shift+Q")
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_config() == Config(hotkey_select="Ctrl+Shift+Q")


def test_settings_display_tab(qapp):
    dialog = MainWindow(Config(), [], {"start_menu": True, "desktop": False, "autostart": False})
    dialog.show_page("appearance")
    dialog._font_px.setValue(22)
    dialog._transparency.setValue(40)
    dialog._swatches.buttons()[list(SWATCHES).index("#14532d")].click()
    assert dialog._preview.appearance.max_px == 22
    dialog.grab()  # vẽ thử được cả cửa sổ
    config = dialog.result_config()
    assert (config.overlay_font_px, config.overlay_opacity, config.overlay_color) == (22, 60, "#14532d")
    assert dialog.startup.wanted() == {"start_menu": True, "desktop": False, "autostart": False}
    # chưa có screen-translator-gui.exe: không chọn được shortcut
    assert MainWindow(Config(), []).startup.wanted() is None


class FakeWorker(QObject):
    result = Signal(int, object, bool)
    failed = Signal(int, str)
    status = Signal(str, bool)
    idle = Signal(int)

    def __init__(self, config):
        super().__init__()
        self.jobs = []
        self.dialogue = []  # lượt ảnh nào dịch kèm ngữ cảnh hội thoại
        self.live_resets = 0
        self.paused = []

    def start(self):
        pass

    def set_paused(self, paused):
        self.paused.append(paused)

    def submit_image(self, image, *, dialogue=False):
        self.jobs.append(image)
        self.dialogue.append(dialogue)
        return len(self.jobs)

    def submit_live(self, image, *, settled):
        self.jobs.append(("live", settled))
        return len(self.jobs)

    def submit_page(self, image):
        self.jobs.append("page")
        return len(self.jobs)

    def reset_live(self):
        self.live_resets += 1


def make_tray_app(monkeypatch, config: Config | None = None):
    monkeypatch.setattr(app_module, "Worker", FakeWorker)
    monkeypatch.setattr(app_module.config_store, "load", lambda: config or Config())
    monkeypatch.setattr(app_module.config_store, "save", lambda config: None)  # không ghi đè cài đặt thật
    monkeypatch.setattr(app_module, "installed_models", list)  # không hỏi Ollama thật
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
    assert tray_app.worker.dialogue == [True]  # vùng tự chọn thường là khung thoại: dịch kèm câu trước
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

    def shown(self, boxes):
        self.boxes = boxes


def test_live_mode_over_a_whole_window_follows_scrolling(qapp, monkeypatch):
    tray_app, messages = make_tray_app(monkeypatch)
    worker, overlay = tray_app.worker, tray_app.overlay
    monitor = app_module.capture.Monitor(0, 0, 1920, 1080)
    area = app_module.capture.Region.from_physical(monitor, (0, 0), 1.0, 0, 0, 1920, 1040)
    tray_app._submit_image(area, Image.new("RGB", (1920, 1040)), selection=False)  # Cả cửa sổ: trang manga
    overlay.excluded_from_capture = True
    monkeypatch.setattr(app_module.capture, "grab_region", lambda area: Image.new("RGB", (area.width, area.height)))
    tray_app.toggle_live()
    assert isinstance(tray_app.watcher, app_module.live.PageWatcher) and "lật trang" in messages[-1]
    tray_app.watcher = watcher = FakeWatcher()

    watcher.events = ["settled"]
    tray_app._live_tick()
    assert worker.jobs[-1] == "page"
    scan = tray_app.job
    bubble = Item("先生、それはちょっと", "Teacher, that's a little far-fetched.", (1113, 125, 1191, 335), True)
    worker.result.emit(scan, [bubble], True)
    assert watcher.boxes == [(1113, 125, 1191, 335)] and overlay.isVisible()
    assert overlay.width() >= 0.8 * 210  # bóng chữ dọc hẹp: khung bản dịch nới ngang ra

    watcher.events = ["settled", "moved"]
    tray_app._live_tick()  # lượt đọc trang mới đang chạy thì vẫn theo dõi cuộn
    tray_app._live_tick()  # trang cuộn: bản dịch lệch chỗ, bỏ ngay
    assert not overlay.isVisible() and not overlay.has_text()
    worker.result.emit(scan + 1, [bubble], True)  # lượt đọc lúc chưa cuộn xong: không hiện nữa
    assert not overlay.isVisible()
    tray_app.toggle_live()
    tray_app.hotkeys.clear()


def test_vertical_bubble_is_widened_around_its_middle():
    column = QRect(100, 50, 40, 200)
    wide = app_module.widen_bubble(column)
    assert wide.width() == 160 and wide.height() == 200 and abs(wide.center().x() - column.center().x()) <= 1
    assert app_module.widen_bubble(QRect(0, 0, 300, 100)) == QRect(0, 0, 300, 100)  # đã đủ rộng


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


def test_glossary_menu_opens_its_page(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch)
    next(a for a in tray_app.menu.actions() if a.text().startswith("Tên riêng")).trigger()
    assert tray_app.window.current_page() == "glossary" and not tray_app.window.welcome
    tray_app.window.reject()
    tray_app.hotkeys.clear()


def edit_dialog(text: str) -> tuple[dialogs_module.EditDialog, list[str]]:
    dialog, sent = dialogs_module.EditDialog(), []
    dialog.retranslate.connect(sent.append)
    dialog.set_result(text, "Dream's room")
    dialog.show()
    return dialog, sent


def select(dialog: dialogs_module.EditDialog, start: int, end: int) -> None:
    cursor = dialog._ja.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    dialog._ja.setTextCursor(cursor)


def test_edit_dialog_adds_a_selected_name_and_translates_again(qapp, tmp_path):
    dialog, sent = edit_dialog("霊夢の部屋")
    select(dialog, 0, 2)
    assert dialog._term_ja.text() == "霊夢" and dialog._term_en.text() == ""
    dialog._term_en.setText(" Reimu ")
    dialog._term_kind.set_gender("Female")
    QTest.keyClick(dialog._term_en, Qt.Key.Key_Return)
    assert (tmp_path / "glossary.txt").read_text(encoding="utf-8").endswith("霊夢 = Reimu (nữ)\n")
    assert sent == ["霊夢の部屋"]  # đúng một lần: Enter không kích thêm nút Dịch lại
    assert dialog._term_ja.text() == dialog._term_en.text() == "" and dialog._term_kind.gender() is None
    assert "霊夢 = Reimu (nữ)" in dialog._term_message.text() and dialog._term_message.isVisible()
    assert dialog.isVisible()
    dialog.done(0)


def test_edit_dialog_shows_and_updates_a_known_name(qapp, tmp_path):
    path = tmp_path / "glossary.txt"
    path.write_text("# ghi chú\n霊夢 = Reimu (nữ)\n実績 = Achievements\n", encoding="utf-8")
    dialog, _ = edit_dialog("霊夢の実績")
    select(dialog, 0, 2)
    assert dialog._term_en.text() == "Reimu" and dialog._term_kind.gender() == "Female"
    select(dialog, 3, 5)  # đổi sang tên khác: không còn tên cũ trong ô
    assert dialog._term_en.text() == "Achievements" and dialog._term_kind.gender() is None
    select(dialog, 0, 2)
    dialog._term_en.setText("Reimu Hakurei")
    dialog._add_term()
    assert path.read_text(encoding="utf-8") == "# ghi chú\n霊夢 = Reimu Hakurei (nữ)\n実績 = Achievements\n"
    dialog.set_result("霊夢の実績", "Reimu Hakurei's achievements")  # kết quả dịch lại về: chữ được đặt lại
    select(dialog, 0, 2)
    assert dialog._term_en.text() == "Reimu Hakurei"  # đọc lại file vừa ghi
    dialog.done(0)


def test_edit_dialog_clearing_a_selection_keeps_what_was_typed(qapp):
    dialog, _ = edit_dialog("霊夢\nの部屋")
    select(dialog, 0, 5)  # bôi qua hai dòng: tên nối lại, không có ký tự xuống dòng
    assert dialog._term_ja.text() == "霊夢の部"
    dialog._term_en.setText("Reimu")
    select(dialog, 1, 1)
    assert dialog._term_ja.text() == "霊夢の部" and dialog._term_en.text() == "Reimu"
    dialog.done(0)


def test_edit_dialog_needs_both_fields_and_a_valid_name(qapp, tmp_path):
    dialog, sent = edit_dialog("霊夢の部屋")
    dialog._term_ja.setText("霊夢")
    dialog._add_term()
    dialog._term_ja.setText("a=b")
    dialog._term_en.setText("Reimu")
    dialog._add_term()
    assert "dấu =" in dialog._term_message.text() and dialog._term_ja.text() == "a=b"
    assert not (tmp_path / "glossary.txt").exists() and sent == []
    dialog.done(0)


def test_edit_dialog_reports_an_unreadable_glossary_and_leaves_it_alone(qapp, tmp_path):
    path = tmp_path / "glossary.txt"
    bad = "霊夢 = Reimu".encode("shift_jis")
    path.write_bytes(bad)
    dialog, sent = edit_dialog("霊夢の部屋")
    select(dialog, 0, 2)  # bôi đen vẫn được, chỉ không tra được tên cũ
    assert dialog._term_ja.text() == "霊夢" and dialog._term_en.text() == ""
    dialog._term_en.setText("Reimu")
    dialog._add_term()
    assert "UTF-8" in dialog._term_message.text() and dialog._term_ja.text() == "霊夢"  # không mất chữ đã gõ
    assert path.read_bytes() == bad and sent == []
    dialog.done(0)


def test_edit_dialog_with_nothing_to_translate_only_saves_the_name(qapp, tmp_path):
    dialog, sent = edit_dialog("")
    dialog._term_ja.setText("霊夢")
    dialog._term_en.setText("Reimu")
    dialog._add_term()
    assert "霊夢 = Reimu" in (tmp_path / "glossary.txt").read_text(encoding="utf-8") and sent == []
    dialog.done(0)


def glossary_window(qapp, tmp_path, text: str | None = None) -> MainWindow:
    if text is not None:
        (tmp_path / "glossary.txt").write_text(text, encoding="utf-8")
    window = MainWindow(Config(), ["a:1b"])
    window.show_page("glossary")
    window.show()
    return window


def add_entry(window: MainWindow, ja: str, en: str, kind: str = "Thuật ngữ") -> None:
    window.glossary._ja.setText(ja)
    window.glossary._en.setText(en)
    window.glossary._kind.setCurrentText(kind)
    window.glossary._add()


def test_glossary_page_adds_edits_and_removes_entries(qapp, tmp_path):
    window = glossary_window(qapp, tmp_path, "# ghi chú\n霊夢 = Reimu (nữ)\n幻想郷 = Gensokyo\n")
    editor, table = window.glossary, window.glossary._table
    assert editor.entries() == [Entry("霊夢", "Reimu", "Female"), Entry("幻想郷", "Gensokyo")] and not editor.dirty()

    add_entry(window, " 魔理沙 ", "Marisa", "Nhân vật nữ")  # thêm: ô nhập trống lại, chờ mục sau
    assert editor.entries()[-1] == Entry("魔理沙", "Marisa", "Female") and editor.dirty()
    assert editor._ja.text() == "" and editor._kind.currentText() == "Thuật ngữ"
    add_entry(window, "霊夢", "Reimu Hakurei", "Nhân vật nữ")  # chữ Nhật đã có: sửa dòng đó
    assert table.rowCount() == 3 and table.item(0, 1).text() == "Reimu Hakurei"

    table.item(2, 1).setText("Marisa Kirisame")  # sửa trong bảng
    table.cellWidget(1, 3).click()  # nút xóa của 幻想郷
    assert [e.ja for e in editor.entries()] == ["霊夢", "魔理沙"]

    window.findChild(QPushButton, "primary").click()
    assert window.result() == QDialog.DialogCode.Accepted
    assert (tmp_path / "glossary.txt").read_text(encoding="utf-8") == (
        "# ghi chú\n霊夢 = Reimu Hakurei (nữ)\n魔理沙 = Marisa Kirisame (nữ)\n"
    )


def test_glossary_search_hides_other_rows(qapp, tmp_path):
    window = glossary_window(qapp, tmp_path, "霊夢 = Reimu (nữ)\n魔理沙 = Marisa (nữ)\n幻想郷 = Gensokyo\n")
    editor, table = window.glossary, window.glossary._table
    shown = lambda: [table.item(r, 0).text() for r in range(table.rowCount()) if not table.isRowHidden(r)]
    editor._search.setText("MARI")
    assert shown() == ["魔理沙"]
    editor._search.setText("幻想")
    assert shown() == ["幻想郷"]
    add_entry(window, "早苗", "Sanae")  # mục vừa thêm phải thấy được ngay
    assert editor._search.text() == "" and len(shown()) == 4


def test_glossary_enter_adds_instead_of_closing_the_window(qapp, tmp_path):
    window = glossary_window(qapp, tmp_path)
    editor = window.glossary
    editor._ja.setText("霊夢")
    QTest.keyClick(editor._ja, Qt.Key.Key_Return)  # thiếu tiếng Anh: chuyển sang ô đó, chưa thêm
    assert window.isVisible() and editor.entries() == []
    editor._en.setText("Reimu")
    QTest.keyClick(editor._en, Qt.Key.Key_Return)
    assert window.isVisible() and editor.entries() == [Entry("霊夢", "Reimu")]
    QTest.keyClick(editor._search, Qt.Key.Key_Return)  # ô tìm kiếm cũng không được bấm nhầm Lưu
    assert window.isVisible()
    window.done(0)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda table: table.item(0, 1).setText(""), "Dòng 1: thiếu tiếng Anh"),
        (lambda table: table.item(1, 0).setText(""), "Dòng 2: thiếu chữ Nhật"),
        (lambda table: table.item(1, 0).setText("霊夢"), "hai dòng"),
        (lambda table: table.item(1, 0).setText("a=b"), "dấu ="),
        (lambda table: table.item(1, 0).setText("#魔理沙"), "bắt đầu bằng #"),
    ],
)
def test_glossary_problems_stop_the_save_on_its_page(qapp, tmp_path, change, message):
    text = "霊夢 = Reimu (nữ)\n魔理沙 = Marisa (nữ)\n"
    window = glossary_window(qapp, tmp_path, text)
    change(window.glossary._table)
    window.show_page("hotkeys")
    window.findChild(QPushButton, "primary").click()
    assert window.isVisible() and window.current_page() == "glossary" and message in window._error.text()
    assert (tmp_path / "glossary.txt").read_text(encoding="utf-8") == text
    window.done(0)


def test_glossary_blank_row_counts_as_removed(qapp, tmp_path):
    window = glossary_window(qapp, tmp_path, "霊夢 = Reimu (nữ)\n魔理沙 = Marisa (nữ)\n")
    window.glossary._table.item(0, 0).setText("")
    window.glossary._table.item(0, 1).setText("")
    window.findChild(QPushButton, "primary").click()
    assert (tmp_path / "glossary.txt").read_text(encoding="utf-8") == "魔理沙 = Marisa (nữ)\n"


def test_glossary_saves_what_was_typed_but_not_added(qapp, tmp_path):
    window = glossary_window(qapp, tmp_path)
    window.glossary._ja.setText("霊夢")  # thiếu tiếng Anh: báo lỗi, không mất chữ đã gõ
    window.findChild(QPushButton, "primary").click()
    assert window.isVisible() and "thiếu tiếng Anh" in window._error.text() and window.glossary._ja.text() == "霊夢"
    window.glossary._en.setText("Reimu")  # đủ cả hai: tự thêm rồi lưu
    window.findChild(QPushButton, "primary").click()
    assert not window.isVisible()
    assert "霊夢 = Reimu" in (tmp_path / "glossary.txt").read_text(encoding="utf-8")


def test_saving_without_glossary_changes_does_not_touch_the_file(qapp, tmp_path):
    window = glossary_window(qapp, tmp_path)
    window.findChild(QPushButton, "primary").click()
    assert window.result() == QDialog.DialogCode.Accepted and not (tmp_path / "glossary.txt").exists()


@pytest.mark.parametrize(
    ("answer", "closed", "saved"),
    [("save", True, True), ("discard", True, False), ("stay", False, False)],
)
def test_closing_with_unsaved_glossary_asks_first(qapp, monkeypatch, tmp_path, answer, closed, saved):
    window = glossary_window(qapp, tmp_path)
    asked = []
    monkeypatch.setattr(window, "_ask_unsaved", lambda: asked.append(True) or answer)
    window.reject()  # chưa sửa gì: đóng luôn, không hỏi
    assert not asked and not window.isVisible()

    window.show()
    add_entry(window, "霊夢", "Reimu")
    window.close()  # nút ✕ cũng đi qua reject
    assert asked == [True] and window.isVisible() != closed
    assert (tmp_path / "glossary.txt").exists() == saved
    window.done(0)


@pytest.mark.parametrize(("label", "answer"), [("Lưu", "save"), ("Không lưu", "discard"), ("Ở lại", "stay")])
def test_unsaved_question_returns_the_button_clicked(qapp, tmp_path, label, answer):
    window = glossary_window(qapp, tmp_path)

    def click() -> None:
        box = QApplication.activeModalWidget()
        next(b for b in box.buttons() if b.text() == label).click()

    QTimer.singleShot(0, click)
    assert window._ask_unsaved() == answer
    window.done(0)


def test_glossary_follows_the_file_edited_in_notepad(qapp, monkeypatch, tmp_path):
    window = glossary_window(qapp, tmp_path)
    path, opened = tmp_path / "glossary.txt", []
    monkeypatch.setattr(window_module.os, "startfile", opened.append)
    next(b for b in window.glossary.findChildren(QPushButton) if b.text() == "Sửa bằng Notepad").click()
    assert opened == [path] and path.read_text(encoding="utf-8").startswith("# Tên riêng")  # tạo file kèm hướng dẫn

    with path.open("a", encoding="utf-8") as file:
        file.write("霊夢 = Reimu (nữ)\n")
    window.glossary.refresh()  # quay lại cửa sổ
    assert window.glossary.entries() == [Entry("霊夢", "Reimu", "Female")] and not window.glossary.dirty()

    add_entry(window, "幻想郷", "Gensokyo")
    with path.open("a", encoding="utf-8") as file:
        file.write("早苗 = Sanae (nữ)\n")
    window.glossary.refresh()  # đang có thay đổi chưa lưu: giữ bảng; lúc lưu vẫn không mất 早苗
    assert [e.ja for e in window.glossary.entries()] == ["霊夢", "幻想郷"]
    window.findChild(QPushButton, "primary").click()
    assert path.read_text(encoding="utf-8").endswith("霊夢 = Reimu (nữ)\n早苗 = Sanae (nữ)\n幻想郷 = Gensokyo\n")


def test_unreadable_glossary_is_reported_and_left_alone(qapp, tmp_path):
    path = tmp_path / "glossary.txt"
    bad = "霊夢 = Reimu".encode("shift_jis")  # Notepad lưu nhầm kiểu ANSI
    path.write_bytes(bad)
    window = glossary_window(qapp, tmp_path)
    editor = window.glossary
    assert "UTF-8" in editor._message.text() and editor._message.isVisible() and not editor._table.isEnabled()
    window.findChild(QPushButton, "primary").click()
    assert not window.isVisible() and path.read_bytes() == bad  # vẫn lưu được các trang khác, không đè lên file

    path.write_text("霊夢 = Reimu\n", encoding="utf-8")  # sửa xong quay lại
    editor.refresh()
    assert editor._table.isEnabled() and editor._message.text() == "" and editor.entries() == [Entry("霊夢", "Reimu")]


def test_glossary_kind_box_does_not_change_on_wheel(qapp, tmp_path):
    window = glossary_window(qapp, tmp_path, "霊夢 = Reimu (nữ)\n")
    box = window.glossary._table.cellWidget(0, 2)
    assert box.currentText() == next(k for k, v in GLOSSARY_KINDS.items() if v == "Female")
    event = QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(box, event)
    assert box.currentIndex() == list(GLOSSARY_KINDS.values()).index("Female")


def test_window_translation_puts_each_block_over_its_own_text(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch)
    monitor = app_module.capture.Monitor(0, 0, 1920, 1080)
    area = app_module.capture.Region.from_physical(monitor, (0, 0), 1.25, 0, 30, 1920, 1050)
    tray_app._submit_image(area, Image.new("RGB", (1920, 1020)), selection=False)
    assert tray_app.worker.dialogue == [False]  # menu, nút bấm…: không dính ngữ cảnh hội thoại
    items = [
        Item("屋敷で迎える、最初の朝だ。", "The first morning at the mansion.", (392, 981, 668, 1007)),
        Item("設定", None, (1840, 976, 1890, 996)),  # chưa dịch xong: chưa vẽ nhưng vẫn giữ chỗ
    ]
    assert tray_app._overlay_items(items) == (
        [(QRect(314, 809, 221, 21), "The first morning at the mansion."), (QRect(1472, 805, 40, 16), None)],
        True,
    )
    tray_app.worker.result.emit(1, items, False)
    assert tray_app.overlay.isVisible() and tray_app.overlay.geometry().topLeft() == QPoint(314, 809)
    tray_app.overlay.hide()
    tray_app.hotkeys.clear()


def selected_region(tray_app):
    monitor = app_module.capture.Monitor(0, 0, 1920, 1080)
    area = app_module.capture.Region.from_physical(monitor, (0, 0), 1.0, 100, 300, 700, 400)
    tray_app._submit_image(area, Image.new("RGB", (600, 100)), selection=True)
    return area


def test_selected_region_with_several_blocks_covers_each_block(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch)
    selected_region(tray_app)
    items = [Item("猫だ。", "A cat.", (0, 0, 200, 40)), Item("犬だ。", "A dog.", (0, 50, 200, 90)), Item("鳥", None)]
    assert tray_app._overlay_items(items) == (
        [(QRect(100, 300, 200, 40), "A cat."), (QRect(100, 350, 200, 40), "A dog.")],
        True,
    )
    tray_app.worker.result.emit(1, items, False)
    assert tray_app.overlay.geometry().topLeft() == QPoint(100, 300)
    tray_app.overlay.hide()
    tray_app.hotkeys.clear()


def test_escape_clears_the_translation_and_turns_live_mode_off(qapp, monkeypatch):
    monkeypatch.setattr(app_module.win32, "register_hotkey", lambda *args: True)
    monkeypatch.setattr(app_module.win32, "unregister_hotkey", lambda *args: None)
    keyboard = {"esc_down": False, "foreground_pid": 0}  # 0: game (chương trình khác) đang được focus
    monkeypatch.setattr(app_module.win32, "key_down", lambda vk: keyboard["esc_down"])
    monkeypatch.setattr(app_module.win32, "window_process_id", lambda hwnd: keyboard["foreground_pid"])
    tray_app, _ = make_tray_app(monkeypatch)
    hotkeys, overlay, watching = tray_app.hotkeys, tray_app.overlay, tray_app.escape_timer
    assert not hotkeys.has_escape() and not watching.isActive()  # chưa có bản dịch: Esc vẫn của game

    selected_region(tray_app)  # "Đang dịch…"
    assert hotkeys.has_escape() and watching.isActive()
    hotkeys.triggered.emit("escape")  # bấm Esc lúc đang dịch: bỏ luôn lượt đó
    assert not overlay.isVisible() and not hotkeys.has_escape() and not watching.isActive()
    tray_app.worker.result.emit(1, [Item("猫", "Cat", (5, 5, 40, 30))], True)
    assert not overlay.isVisible()

    selected_region(tray_app)
    tray_app.worker.result.emit(2, [Item("猫", "Cat", (5, 5, 40, 30))], True)
    # đang dùng cửa sổ của app (chọn vùng, hộp thoại): Esc đóng cửa sổ đó, không xóa bản dịch
    keyboard.update(esc_down=True, foreground_pid=os.getpid())
    tray_app._watch_escape()
    assert overlay.isVisible() and not hotkeys.has_escape()
    keyboard.update(esc_down=False, foreground_pid=0)
    tray_app._watch_escape()
    assert hotkeys.has_escape()
    keyboard["esc_down"] = True  # game chặn phím tắt toàn cục: vẫn thấy Esc qua trạng thái phím
    tray_app._watch_escape()
    tray_app.toggle_overlay()  # đã xóa hẳn: nút ẩn / hiện không gọi lại được
    assert not overlay.isVisible() and not overlay.has_text()
    keyboard["esc_down"] = False

    selected_region(tray_app)
    job = tray_app.job  # câu mới vừa hiện trong game, đang dịch
    overlay.excluded_from_capture = True
    tray_app.toggle_live()
    assert overlay.isVisible() and hotkeys.has_escape() and watching.isActive()
    hotkeys.triggered.emit("escape")  # live mode: Esc tắt live mode, xóa luôn bản dịch
    assert not tray_app.live_timer.isActive() and not tray_app._menu_actions["live"].isChecked()
    assert not overlay.isVisible() and not hotkeys.has_escape() and not watching.isActive()
    tray_app.worker.result.emit(job, [Item("犬", "Dog", (5, 5, 40, 30))], True)  # lượt đang dịch dở không hiện nữa
    assert not overlay.isVisible()

    tray_app.toggle_live()  # chưa có bản dịch nào trên màn hình: Esc vẫn tắt được live mode
    assert not overlay.isVisible() and hotkeys.has_escape() and watching.isActive()
    keyboard["esc_down"] = True  # cả lúc game chặn phím tắt toàn cục
    tray_app._watch_escape()
    assert not tray_app.live_timer.isActive() and not hotkeys.has_escape() and not watching.isActive()
    keyboard["esc_down"] = False
    tray_app.hint.hide()
    hotkeys.clear()


def test_tray_icon_and_waiting_text_show_loading(qapp, monkeypatch):
    tray_app, messages = make_tray_app(monkeypatch)
    assert tray_app.loading and "Đang khởi động" in tray_app.tray.toolTip()
    tray_app.on_status("Đang nạp model dịch…", False)
    selected_region(tray_app)
    assert tray_app.overlay._items[0][1] == "Đang nạp model dịch…"  # nói rõ đang chờ gì, không chỉ "Đang dịch…"

    tray_app.on_status(READY, False)
    assert not tray_app.loading and tray_app.tray.toolTip().endswith(READY)
    tray_app.overlay.excluded_from_capture = True
    tray_app.toggle_live()
    assert "live mode đang bật" in tray_app.tray.toolTip()
    tray_app.toggle_live()

    tray_app.on_status("Không kết nối được Ollama.", True)
    assert not tray_app.loading and messages[-1] == "Không kết nối được Ollama."
    tray_app.overlay.hide()
    tray_app.hotkeys.clear()


def test_info_is_a_short_hint_and_errors_are_windows_popups(qapp, monkeypatch):
    monkeypatch.setattr(app_module, "Worker", FakeWorker)
    monkeypatch.setattr(app_module.config_store, "load", lambda: Config())
    tray_app = app_module.TrayApp()
    popups = []
    monkeypatch.setattr(tray_app.tray, "showMessage", lambda *args: popups.append(args[1]))
    tray_app.notify("Đã bật live mode.")
    assert popups == [] and tray_app.hint.isVisible() and tray_app.hint_timer.isActive()
    tray_app.notify("Không kết nối được Ollama.", warning=True)
    assert popups == ["Không kết nối được Ollama."]

    selected_region(tray_app)
    tray_app.notify("Đã tắt live mode.")
    assert tray_app.hint.geometry().bottom() == 300 - GAP - 1  # ngay trên vùng đang dịch
    tray_app.hint.hide()
    tray_app.overlay.hide()
    tray_app.hotkeys.clear()


def test_welcome_screen_on_every_launch_and_shortcuts_only_when_ticked(qapp, monkeypatch, tmp_path):
    tray_app, messages = make_tray_app(monkeypatch, Config(show_panel=False))  # lần trước đã bấm ✕ ẩn thanh
    states, applied = dict.fromkeys(app_module.shortcuts.LABELS, False), []
    launcher = tmp_path / "screen-translator-gui.exe"
    launcher.write_bytes(b"")
    monkeypatch.setattr(app_module.shortcuts, "launcher", lambda: launcher)
    monkeypatch.setattr(app_module.shortcuts, "states", lambda: dict(states))
    monkeypatch.setattr(app_module.shortcuts, "ICON_PATH", tmp_path / "icon.ico")
    monkeypatch.setattr(app_module.shortcuts, "apply", lambda wanted: (applied.append(wanted), states.update(wanted)))

    tray_app.greet(autostart=True)  # tự chạy lúc mở Windows: chỉ có icon ở khay
    assert tray_app.window is None and not tray_app.panel.isVisible() and messages == []

    tray_app.greet(autostart=False)  # mở từ menu Start / Desktop
    assert tray_app.window.isVisible() and tray_app.window.current_page() == "guide"
    assert not tray_app.panel.isVisible()
    assert not any(tray_app.window.startup.wanted().values())  # không bật sẵn gì
    tray_app.window.accept()  # bấm "Bắt đầu" mà không bật gì: không tạo shortcut nào
    assert applied == [] and tray_app.window is None
    assert tray_app.panel.isVisible() and tray_app.config.show_panel and tray_app._panel_action.isChecked()

    tray_app.panel.hide()
    tray_app.greet(autostart=False)  # lần mở sau vẫn có màn hình chào
    tray_app.window.startup._boxes["autostart"].setChecked(True)  # người dùng tự bật ở trang Cài đặt
    tray_app.window.accept()
    assert applied == [{"start_menu": False, "desktop": False, "autostart": True}]
    assert (tmp_path / "icon.ico").exists()

    tray_app.panel.hide()
    quits = []
    monkeypatch.setattr(tray_app, "quit", lambda: quits.append(True))
    tray_app.greet(autostart=False)  # shortcut đã có thì được bật sẵn; đóng bằng ✕: không đổi gì, thoát app
    assert tray_app.window.startup.wanted()["autostart"]
    tray_app.window.startup._boxes["desktop"].setChecked(True)
    QTest.keyClick(tray_app.window, Qt.Key.Key_Escape)  # Esc (phím xóa bản dịch) không được đóng màn hình chào
    assert tray_app.window is not None and tray_app.window.isVisible() and quits == []
    tray_app.window.reject()
    assert len(applied) == 1 and not tray_app.panel.isVisible() and quits == [True]

    tray_app.open_window("settings")  # mở từ menu Cài đặt: Lưu / Hủy, không đụng tới thanh điều khiển
    assert not tray_app.window.welcome and tray_app.window.current_page() == "settings"
    flags = tray_app.window.windowFlags()  # cửa sổ thường: có nút thu nhỏ, app khác đè lên được
    assert flags & Qt.WindowType.WindowMinimizeButtonHint and not flags & Qt.WindowType.WindowStaysOnTopHint
    tray_app.window.showMinimized()
    tray_app.open_window("guide")  # đang mở (kể cả đang thu nhỏ) thì hiện lại và chỉ chuyển trang
    assert tray_app.window.current_page() == "guide" and not tray_app.window.isMinimized()
    tray_app.window._font_px.setValue(20)
    tray_app.window.accept()
    assert tray_app.config.overlay_font_px == 20 and not tray_app.panel.isVisible() and len(applied) == 1
    tray_app.hotkeys.clear()


def test_opening_the_app_again_shows_the_panel_of_the_running_one(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch, Config(show_panel=False))
    monkeypatch.setattr(app_module, "INSTANCE_KEY", f"ScreenTranslator-test-{id(tray_app)}")
    assert not app_module._wake_running_instance()
    app_module._listen_for_wake(tray_app)
    assert app_module._wake_running_instance()
    wait_until(qapp, lambda: tray_app.panel.isVisible())
    assert tray_app.config.show_panel
    tray_app.panel.hide()
    tray_app.hotkeys.clear()


def test_pause_gives_hotkeys_back_and_resume_restores_live_mode(qapp, monkeypatch):
    # phím tắt thật có thể đang bị bản app đang chạy giữ: giả lập Windows nhận đăng ký
    monkeypatch.setattr(app_module.win32, "register_hotkey", lambda *args: True)
    monkeypatch.setattr(app_module.win32, "unregister_hotkey", lambda *args: None)
    tray_app, messages = make_tray_app(monkeypatch)
    worker, panel = tray_app.worker, tray_app.panel
    selected_region(tray_app)
    tray_app.overlay.excluded_from_capture = True
    tray_app.toggle_live()

    tray_app._pause_action.trigger()  # tạm dừng từ menu (nút "…" trên thanh, hoặc icon ở khay)
    assert tray_app.paused and worker.paused == [True] and tray_app._pause_action.isChecked()
    assert not tray_app.live_timer.isActive() and not tray_app.overlay.isVisible()
    assert tray_app.hotkeys._actions == {}  # game dùng lại được các phím này
    assert "tạm dừng" in tray_app.tray.toolTip() and "Đã tạm dừng" in messages[-1]
    assert not panel.buttons["select"].isEnabled() and not tray_app._menu_actions["select"].isEnabled()
    worker.result.emit(1, [Item("猫", "Cat", (5, 5, 40, 30))], True)  # lượt đang dịch dở lúc bấm dừng
    assert not tray_app.overlay.isVisible()

    tray_app._pause_action.trigger()  # tiếp tục từ menu
    assert not tray_app.paused and worker.paused == [True, False]
    assert tray_app.live_timer.isActive() and worker.live_resets == 2  # lúc dừng đang bật live mode
    assert len(tray_app.hotkeys._actions) == len(tray_app.config.hotkeys) + 1  # + Esc tắt live mode
    assert panel.buttons["select"].isEnabled() and not tray_app._pause_action.isChecked()
    tray_app.toggle_live()
    tray_app.overlay.hide()
    tray_app.hint.hide()
    tray_app.hotkeys.clear()


def test_live_mode_puts_the_control_panel_away_until_esc(qapp, monkeypatch):
    monkeypatch.setattr(app_module.win32, "register_hotkey", lambda *args: True)
    monkeypatch.setattr(app_module.win32, "unregister_hotkey", lambda *args: None)
    tray_app, messages = make_tray_app(monkeypatch, Config(panel_pos=(40, 50)))
    panel, hotkeys = tray_app.panel, tray_app.hotkeys
    assert "pause" not in panel.buttons  # tạm dừng chỉ còn trong menu
    tray_app.set_panel_visible(True)
    selected_region(tray_app)
    tray_app.overlay.excluded_from_capture = True

    panel.buttons["live"].click()
    assert tray_app.live_timer.isActive() and not panel.isVisible() and not tray_app._panel_action.isChecked()
    assert tray_app.config.show_panel and "Esc" in messages[-1]  # chỉ cất tạm: mở app lại thanh vẫn hiện
    hotkeys.triggered.emit("escape")
    assert not tray_app.live_timer.isActive() and panel.isVisible() and panel.pos() == QPoint(40, 50)
    assert tray_app._panel_action.isChecked()

    tray_app.toggle_live()
    tray_app._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)  # lúc live vẫn mở thanh ra được
    assert panel.isVisible()
    panel.buttons["close"].click()  # rồi tự ẩn thanh: tắt live mode xong thanh không hiện lại
    hotkeys.triggered.emit("escape")
    assert not tray_app.live_timer.isActive() and not panel.isVisible() and not tray_app.config.show_panel
    tray_app.overlay.hide()
    hotkeys.clear()


def test_control_panel_does_everything_by_mouse(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch, Config(panel_pos=(40, 50)))
    saved = []
    monkeypatch.setattr(app_module.config_store, "save", saved.append)
    panel, calls = tray_app.panel, []
    for action in ("select", "screen", "repeat", "live", "toggle"):
        tray_app._handlers[action] = lambda action=action: calls.append(action)
        panel.buttons[action].click()
    assert calls == ["select", "screen", "repeat", "live", "toggle"]

    tray_app._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)  # bấm icon ở khay
    assert panel.isVisible() and panel.pos() == QPoint(40, 50) and tray_app._panel_action.isChecked()
    panel.grab()  # vẽ thử được

    panel.transparency.setValue(70)
    panel.move(60, 80)  # kéo thanh
    panel.moved.emit(panel.pos())
    assert tray_app.config.overlay_opacity == 30 and panel.transparency_value.text() == "70%"
    assert round(tray_app.overlay.appearance.background.alphaF(), 2) == 0.3
    assert tray_app.config.panel_pos == (60, 80)
    wait_until(qapp, lambda: saved)  # kéo xong mới lưu, một lần
    assert saved == [tray_app.config]

    panel.buttons["orient"].click()  # xếp thành cột dọc, góc trên-trái giữ chỗ cũ
    assert panel.vertical and tray_app.config.panel_vertical and panel.height() > panel.width()
    assert panel.pos() == QPoint(60, 80) and panel.buttons["select"].isVisible()
    panel.buttons["orient"].click()
    assert not panel.vertical and not tray_app.config.panel_vertical and panel.width() > panel.height()
    assert ControlPanel(QMenu(), vertical=True).vertical  # mở app lại vẫn xếp như lần trước

    panel.buttons["close"].click()
    assert not panel.isVisible() and not tray_app.config.show_panel and not tray_app._panel_action.isChecked()
    tray_app.hotkeys.clear()
