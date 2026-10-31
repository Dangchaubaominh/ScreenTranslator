from conftest import wait_until
from PIL import Image
from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QSystemTrayIcon

from screen_translator import app as app_module
from screen_translator.config import Config
from screen_translator.ui.dialogs import SettingsDialog
from screen_translator.ui.overlay import (
    GAP,
    MAX_PX,
    MIN_PX,
    Appearance,
    Overlay,
    fit_beside,
    fit_blocks,
    fit_text,
)
from screen_translator.ui.region_selector import RegionSelector
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


def test_translation_beside_the_region_flips_when_there_is_no_room(qapp):
    screen = QRect(0, 0, 1920, 1080)
    dialogue = QRect(100, 700, 1200, 200)
    below = fit_beside(dialogue, "Good morning.", "below", 30, screen).rect
    above = fit_beside(dialogue, "Good morning.", "above", 30, screen).rect
    assert (below.x(), below.width(), below.top()) == (100, 1200, dialogue.bottom() + 1 + GAP)
    assert (above.x(), above.width(), above.bottom()) == (100, 1200, dialogue.top() - GAP - 1)
    # khung thoại sát đáy màn hình: không còn chỗ bên dưới thì đặt lên trên
    low = QRect(100, 880, 1200, 200)
    assert fit_beside(low, "Good morning.", "below", 30, screen).rect.bottom() == low.top() - GAP - 1
    assert fit_beside(QRect(0, 0, 500, 80), "Hi.", "above", 30, screen).rect.top() == 80 + GAP


def test_overlay_can_show_text_below_the_region(qapp):
    overlay = Overlay(Appearance(max_px=20))
    overlay.show_text(QRect(50, 300, 500, 100), "Hello.", position="below")
    assert (overlay.geometry().x(), overlay.geometry().y(), overlay.geometry().width()) == (50, 400 + GAP, 500)
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


def test_settings_display_tab(qapp):
    dialog = SettingsDialog(Config(), [], {"start_menu": True, "desktop": False, "autostart": False})
    dialog._position.setCurrentIndex(dialog._position.findData("below"))
    dialog._font_px.setValue(22)
    dialog._transparency.setValue(40)
    assert dialog._preview.position == "below" and dialog._preview.appearance.max_px == 22
    dialog._preview.grab()  # vẽ thử được
    config = dialog.result_config()
    assert (config.overlay_position, config.overlay_font_px, config.overlay_opacity) == ("below", 22, 60)
    assert dialog.startup.wanted() == {"start_menu": True, "desktop": False, "autostart": False}
    # chưa có screen-translator-gui.exe: không chọn được shortcut
    assert SettingsDialog(Config(), []).startup.wanted() is None


class FakeWorker(QObject):
    result = Signal(int, object, bool)
    failed = Signal(int, str)
    status = Signal(str, bool)
    idle = Signal(int)

    def __init__(self, config):
        super().__init__()
        self.jobs = []
        self.live_resets = 0
        self.paused = []

    def start(self):
        pass

    def set_paused(self, paused):
        self.paused.append(paused)

    def submit_image(self, image):
        self.jobs.append(image)
        return len(self.jobs)

    def submit_live(self, image, *, settled):
        self.jobs.append(("live", settled))
        return len(self.jobs)

    def reset_live(self):
        self.live_resets += 1


def make_tray_app(monkeypatch, config: Config | None = None):
    monkeypatch.setattr(app_module, "Worker", FakeWorker)
    monkeypatch.setattr(app_module.config_store, "load", lambda: config or Config())
    monkeypatch.setattr(app_module.config_store, "save", lambda config: None)  # không ghi đè cài đặt thật
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
        Item("設定", None, (1840, 976, 1890, 996)),  # chưa dịch xong: chưa vẽ nhưng vẫn giữ chỗ
    ]
    assert tray_app._overlay_items(items) == (
        [(QRect(314, 809, 221, 21), "The first morning at the mansion."), (QRect(1472, 805, 40, 16), None)],
        "blocks",
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


def test_translation_above_the_region_joins_all_blocks(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch, Config(overlay_position="above"))
    selected_region(tray_app)
    items = [Item("猫だ。", "A cat.", (0, 0, 200, 40)), Item("犬だ。", "A dog.", (0, 50, 200, 90)), Item("鳥", None)]
    assert tray_app._overlay_items(items) == ([(QRect(100, 300, 600, 100), "A cat.\nA dog.")], "above")
    tray_app.worker.result.emit(1, items, False)
    assert tray_app.overlay.geometry().bottom() == 300 - GAP - 1  # ngay trên vùng, không che chữ gốc
    tray_app.overlay.hide()
    tray_app.hotkeys.clear()


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


def test_first_run_guide_offers_shortcuts_and_is_shown_once(qapp, monkeypatch, tmp_path):
    tray_app, _ = make_tray_app(monkeypatch)
    saved, applied = [], []
    monkeypatch.setattr(app_module.config_store, "save", saved.append)
    launcher = tmp_path / "screen-translator-gui.exe"
    launcher.write_bytes(b"")
    monkeypatch.setattr(app_module.shortcuts, "launcher", lambda: launcher)
    monkeypatch.setattr(app_module.shortcuts, "states", lambda: dict.fromkeys(app_module.shortcuts.LABELS, False))
    monkeypatch.setattr(app_module.shortcuts, "ICON_PATH", tmp_path / "icon.ico")
    monkeypatch.setattr(app_module.shortcuts, "apply", applied.append)

    tray_app.show_guide(first_run=True)
    assert tray_app.guide.isVisible()
    tray_app.guide.accept()
    assert applied == [{"start_menu": True, "desktop": True, "autostart": False}]
    assert (tmp_path / "icon.ico").exists()
    assert saved[-1].welcomed and tray_app.config.welcomed and tray_app.guide is None

    tray_app.show_guide()  # mở lại từ menu: chỉ có hướng dẫn
    assert tray_app.guide.startup is None
    tray_app.guide.accept()
    assert len(applied) == len(saved) == 1
    tray_app.hotkeys.clear()


def test_opening_the_app_again_shows_the_panel_of_the_running_one(qapp, monkeypatch):
    tray_app, _ = make_tray_app(monkeypatch, Config(welcomed=True, show_panel=False))
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

    panel.buttons["pause"].click()
    assert tray_app.paused and worker.paused == [True]
    assert not tray_app.live_timer.isActive() and not tray_app.overlay.isVisible()
    assert tray_app.hotkeys._actions == {}  # game dùng lại được các phím này
    assert "tạm dừng" in tray_app.tray.toolTip() and "Đã tạm dừng" in messages[-1]
    assert panel.buttons["pause"].isChecked() and panel.buttons["pause"].text() == "Tiếp tục"
    assert not panel.buttons["select"].isEnabled() and not tray_app._menu_actions["select"].isEnabled()
    worker.result.emit(1, [Item("猫", "Cat", (5, 5, 40, 30))], True)  # lượt đang dịch dở lúc bấm dừng
    assert not tray_app.overlay.isVisible()

    tray_app._pause_action.trigger()  # tiếp tục từ menu
    assert not tray_app.paused and worker.paused == [True, False]
    assert len(tray_app.hotkeys._actions) == len(tray_app.config.hotkeys)
    assert tray_app.live_timer.isActive() and worker.live_resets == 2  # lúc dừng đang bật live mode
    assert panel.buttons["select"].isEnabled() and not panel.buttons["pause"].isChecked()
    tray_app.toggle_live()
    tray_app.overlay.hide()
    tray_app.hint.hide()
    tray_app.hotkeys.clear()


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

    [above] = [button for button in panel.positions.buttons() if button.property("position") == "above"]
    above.click()
    panel.transparency.setValue(70)
    panel.moved.emit(QPoint(60, 80))
    assert tray_app.config.overlay_position == "above" and above.isChecked()
    assert tray_app.config.overlay_opacity == 30 and panel.transparency_value.text() == "70%"
    assert round(tray_app.overlay.appearance.background.alphaF(), 2) == 0.3
    assert tray_app.config.panel_pos == (60, 80)
    wait_until(qapp, lambda: saved)  # kéo xong mới lưu, một lần
    assert saved == [tray_app.config]

    panel.buttons["close"].click()
    assert not panel.isVisible() and not tray_app.config.show_panel and not tray_app._panel_action.isChecked()
    tray_app.hotkeys.clear()
