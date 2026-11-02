import ast
import re
from pathlib import Path
from string import Formatter

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QTableWidget,
    QWidget,
)

import screen_translator
from screen_translator.config import Config
from screen_translator.hotkeys import parse_hotkey
from screen_translator.i18n import EN, UI_LANGUAGES, tr
from screen_translator.ui import dialogs as dialogs_module
from screen_translator.ui import window as window_module
from screen_translator.ui.dialogs import EditDialog
from screen_translator.ui.panel import ControlPanel
from screen_translator.ui.window import MainWindow

VIETNAMESE = re.compile("[À-ỹ]")
LANGUAGE_FIELD = (
    "Ngôn ngữ giao diện (Interface language)"  # viết hai thứ tiếng, để ai lỡ chọn nhầm cũng tìm được đường về
)
SOURCES = {
    path: ast.parse(path.read_text(encoding="utf-8"))
    for path in Path(screen_translator.__file__).parent.rglob("*.py")
    if path.name != "i18n.py"
}


def fields(text: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(text) if field}


def test_vietnamese_is_the_default_and_values_are_filled_in():
    assert tr("Đang dịch…") == "Đang dịch…"
    assert tr("Nạp OCR lỗi: {error}", error="x") == "Nạp OCR lỗi: x"


def test_english_text_and_values(english):
    assert tr("Đang dịch…") == "Translating…"
    assert tr("Nạp OCR lỗi: {error}", error="x") == "Could not load OCR: x"
    assert tr("chữ của model, không có trong bảng") == "chữ của model, không có trong bảng"
    with pytest.raises(ValueError, match="invalid modifier key"):
        parse_hotkey("Foo+T")


def test_every_literal_passed_to_tr_has_an_english_text():
    literals = []
    for tree in SOURCES.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "tr":
                first = node.args[0]
                literals += [first.body, first.orelse] if isinstance(first, ast.IfExp) else [first]
    texts = [node.value for node in literals if isinstance(node, ast.Constant)]
    assert texts  # phép kiểm tra thật sự thấy các lời gọi tr
    assert [text for text in texts if text not in EN] == []


def test_every_english_text_is_still_used_and_keeps_its_placeholders():
    used = {node.value for tree in SOURCES.values() for node in ast.walk(tree) if isinstance(node, ast.Constant)}
    assert [text for text in EN if text not in used] == []
    assert [text for text, english in EN.items() if fields(text) != fields(english)] == []


def test_english_texts_are_really_english():
    allowed = {EN[LANGUAGE_FIELD]}
    assert [english for english in EN.values() if VIETNAMESE.search(english) and english not in allowed] == []


def shown_texts(widget) -> list[str]:
    texts = [widget.windowTitle(), widget.toolTip()]
    for child in widget.findChildren(QWidget):
        texts.append(child.toolTip())
        if isinstance(child, QLabel | QAbstractButton):
            texts.append(child.text())
        if isinstance(child, QGroupBox):
            texts.append(child.title())
        if isinstance(child, QLineEdit):
            texts.append(child.placeholderText())
        if isinstance(child, QComboBox):
            texts += [child.itemText(i) for i in range(child.count())]
        if isinstance(child, QListWidget):
            texts += [child.item(i).text() for i in range(child.count())]
        if isinstance(child, QTableWidget):
            headers = (child.horizontalHeaderItem(i) for i in range(child.columnCount()))
            texts += [header.text() for header in headers if header]
    return [text for text in texts if text]


@pytest.mark.parametrize(
    "build",
    [
        lambda: MainWindow(Config(), [], welcome=True),  # có cả khung "Chuẩn bị một lần" và ghi chú thiếu exe
        lambda: MainWindow(Config(), [], {"start_menu": True, "desktop": False, "autostart": False}),
        EditDialog,
        lambda: ControlPanel(QMenu()),
    ],
    ids=["welcome", "settings", "edit-dialog", "panel"],
)
def test_no_vietnamese_is_left_on_screen_in_english(qapp, monkeypatch, tmp_path, english, build):
    monkeypatch.setattr(window_module, "GLOSSARY_PATH", tmp_path / "glossary.txt")
    monkeypatch.setattr(dialogs_module, "GLOSSARY_PATH", tmp_path / "glossary.txt")
    allowed = {UI_LANGUAGES["vi"], EN[LANGUAGE_FIELD]}
    widget = build()
    texts = shown_texts(widget)
    assert len(texts) >= 5  # phép kiểm tra thật sự đọc được chữ trên cửa sổ
    assert [text for text in texts if VIETNAMESE.search(text) and text not in allowed] == []
