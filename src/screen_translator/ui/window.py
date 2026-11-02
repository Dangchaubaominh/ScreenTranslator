"""Cửa sổ chính của app: hướng dẫn, tên riêng, phím tắt, cài đặt, chỉnh màu trong một cửa sổ, chọn trang ở cột trái.

Nền tối cùng tông với thanh điều khiển. Mở lúc mở app (màn hình chào, nút "Bắt đầu") hoặc từ menu Cài đặt / Hướng dẫn.
"""

import logging
import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import win32
from ..config import FONT_PX_RANGE, GLOSSARY_PATH, HOTKEY_LABELS, OPACITY_RANGE, PROFILES, Config
from ..glossary import Entry, Glossary, clean, ensure_file, update_file, valid_ja
from ..hotkeys import parse_hotkey
from ..shortcuts import LABELS as SHORTCUT_LABELS
from .overlay import Appearance, fit_text, paint_block
from .panel import glyph_icon

log = logging.getLogger(__name__)
BG, SIDEBAR, CARD, BORDER = "#0f121e", "#0b0e18", "#171c2c", "#252b3d"
CARD_MARGINS = (16, 12, 16, 12)
NAV_ICON_PX = 20  # chia hết cho 4: ở 125% / 150% / 175% vẫn tròn điểm ảnh, nét icon không bị co giãn lệch
TEXT, MUTED, ACCENT = "#e2e8f0", "#94a3b8", "#3b82f6"
PAGES = {  # trang → (chữ ở cột trái, biểu tượng Segoe Fluent Icons)
    "guide": ("Hướng dẫn", ""),
    "glossary": ("Tên riêng", ""),
    "hotkeys": ("Phím tắt", ""),
    "settings": ("Cài đặt", ""),
    "appearance": ("Chỉnh màu", ""),
}
SWATCHES = {  # màu nền bản dịch có sẵn; chữ tự đổi đen / trắng cho dễ đọc
    "#0c101c": "Xanh đêm (mặc định)",
    "#000000": "Đen",
    "#1e293b": "Xám xanh",
    "#172554": "Xanh dương đậm",
    "#14532d": "Xanh lá đậm",
    "#3b0764": "Tím",
    "#f8fafc": "Trắng",
}
STYLE = f"""
QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-family: "Segoe UI"; font-size: 13px; font-weight: normal; }}
#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#brand {{ font-size: 15px; font-weight: bold; }}
#logo {{ background: {ACCENT}; color: white; border-radius: 7px; font-family: "Yu Gothic UI"; font-size: 17px;
          font-weight: bold; }}
#nav {{ background: transparent; border: none; outline: none; }}
#nav::item {{ padding: 8px 10px; margin: 1px 0; border-radius: 6px; color: {MUTED}; }}
#nav::item:hover {{ background: rgba(255, 255, 255, 13); color: {TEXT}; }}
#nav::item:selected {{ background: #1c2740; color: white; }}
#tagline, #subtitle, #hint {{ color: {MUTED}; }}
#hint {{ font-size: 12px; }}
#title {{ font-size: 22px; font-weight: bold; }}
QScrollArea, #page {{ background: {BG}; border: none; }}
QGroupBox {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; margin-top: 24px; padding: 0;
             font-weight: bold; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 2px; top: 0px; }}
#key {{ background: #1e293b; border: 1px solid #334155; border-bottom: 2px solid #475569; border-radius: 5px;
        padding: 1px 7px; font-size: 12px; font-weight: bold; }}
#step {{ background: rgba(59, 130, 246, 46); color: #93c5fd; border-radius: 11px; font-size: 12px; font-weight: bold; }}
QComboBox, QLineEdit, QSpinBox, QPlainTextEdit {{ background: {SIDEBAR}; border: 1px solid #334155; border-radius: 6px;
                                                  padding: 5px 8px; selection-background-color: {ACCENT}; }}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QPlainTextEdit:hover {{ border-color: #475569; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: none; }}
QComboBox:editable {{ padding-left: 3px; }}
QComboBox QLineEdit {{ background: transparent; border: none; padding: 0; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid #334155; selection-background-color: #1c2740;
                               outline: none; }}
#keyedit {{ font-weight: bold; }}
QPushButton {{ background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 6px 16px; }}
QPushButton:hover {{ background: #273449; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: bold; }}
QPushButton#primary:hover {{ background: #2563eb; }}
#footer {{ border-top: 1px solid {BORDER}; }}
#error {{ color: #f87171; }}
QSlider::groove:horizontal {{ height: 4px; background: #334155; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; border-radius: 8px; background: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #334155; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid #334155; }}
QWellArray, QtPrivate--QColorShowLabel, QtPrivate--QColorPicker {{ border: 1px solid #475569; }}
QTableWidget {{ background: {SIDEBAR}; alternate-background-color: #111522; border: 1px solid {BORDER};
                border-radius: 6px; outline: none; }}
QTableWidget::item {{ padding: 0 8px; }}
QTableWidget QLineEdit {{ padding: 0 7px; border-radius: 0; }}
QTableWidget QComboBox {{ background: transparent; border: none; border-radius: 0; padding: 0 3px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
                        padding: 6px 11px; }}
#rowdelete {{ background: transparent; border: none; }}
#rowdelete:hover {{ background: rgba(248, 113, 113, 40); }}
"""


class Toggle(QCheckBox):
    """Công tắc bật / tắt kiểu Windows 11, vẫn là QCheckBox (isChecked, setChecked, toggled…)."""

    TRACK_W, TRACK_H = 40, 20

    def sizeHint(self) -> QSize:
        return QSize(self.TRACK_W + 12 + self.fontMetrics().horizontalAdvance(self.text()), 28)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        on, enabled = self.isChecked(), self.isEnabled()
        top = (self.height() - self.TRACK_H) / 2
        track = QColor(ACCENT if on else "#334155")
        if not enabled:
            track.setAlpha(90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, top, self.TRACK_W, self.TRACK_H), self.TRACK_H / 2, self.TRACK_H / 2)
        knob = self.TRACK_H - 8
        painter.setBrush(QColor("white" if on and enabled else "#94a3b8"))
        painter.drawEllipse(QRectF(self.TRACK_W - knob - 4 if on else 4, top + 4, knob, knob))
        painter.setPen(QColor(TEXT if enabled else MUTED))
        text_rect = QRectF(self.TRACK_W + 12, 0, self.width() - self.TRACK_W - 12, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())


class ComboBox(QComboBox):
    """Ô chọn tự vẽ mũi tên: tô QSS cho ô bo góc thì Qt bỏ mũi tên gốc, mà nút mũi tên gốc lại đè lên viền bo."""

    def wheelEvent(self, event) -> None:
        event.ignore()  # ô nằm trong trang cuộn được: lăn chuột để cuộn, không đổi nhầm lựa chọn

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(TEXT if self.underMouse() else MUTED), 1.5))
        x, y = self.width() - 18, self.height() / 2
        painter.drawPolyline([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])


class StartupOptions(QGroupBox):
    """Các cách mở app không cần terminal. `checked` None: chưa có screen-translator-gui.exe.

    Chỉ bật sẵn shortcut đang có thật; shortcut mới (kể cả tự chạy khi mở Windows) phải do người dùng tự bật.
    """

    def __init__(self, checked: dict[str, bool] | None):
        super().__init__("Mở app")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*CARD_MARGINS)
        self._available = checked is not None
        self._boxes = {}
        for key, label in SHORTCUT_LABELS.items():
            box = Toggle(label)
            box.setChecked(bool(checked and checked[key]))
            box.setEnabled(checked is not None)
            layout.addWidget(box)
            self._boxes[key] = box
        if checked is None:
            note = QLabel(
                "Chưa có screen-translator-gui.exe: chạy <code>uv sync</code> trong thư mục dự án rồi mở lại app.",
                objectName="hint",
            )
            note.setWordWrap(True)
            layout.addWidget(note)

    def wanted(self) -> dict[str, bool] | None:
        """Shortcut nào cần có; None khi không chọn được (chưa có exe)."""
        return {key: box.isChecked() for key, box in self._boxes.items()} if self._available else None


class OverlayPreview(QWidget):
    """Khung thoại giả, vẽ bản dịch theo cỡ chữ / màu / độ trong đang chọn."""

    JA = "霊夢「おはよう、魔理沙。今日は早いのね」"
    EN = 'Reimu: "Good morning, Marisa. You\'re early today."'

    def __init__(self):
        super().__init__()
        self.setFixedSize(480, 150)
        self.appearance = Appearance()

    def set_appearance(self, appearance: Appearance) -> None:
        self.appearance = appearance
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(64, 82, 70))  # cảnh nền của game
        box = QRect(16, (self.height() - 70) // 2, self.width() - 32, 70)
        painter.fillRect(box, QColor(22, 26, 40))
        font = QFont("Yu Gothic UI")
        font.setPixelSize(20)
        painter.setFont(font)
        painter.setPen(QColor(240, 240, 240))
        painter.drawText(
            box.adjusted(14, 0, -14, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.JA
        )
        paint_block(painter, fit_text(box, self.EN, self.appearance.max_px), self.EN, self.appearance)


def _label(text: str, name: str = "", *, wrap: bool = True) -> QLabel:
    label = QLabel(text, objectName=name)
    label.setWordWrap(wrap)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


def _card(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    card = QGroupBox(title)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*CARD_MARGINS)
    layout.setSpacing(8)
    return card, layout


def _slider_row(slider: QSlider, value: QLabel) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(slider, 1)
    value.setFixedWidth(48)
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(value)
    return row


GLOSSARY_KINDS = {"Thuật ngữ": None, "Nhân vật nữ": "Female", "Nhân vật nam": "Male"}  # chữ trong ô chọn → Entry.gender


class KindBox(ComboBox):
    """Ô chọn loại của một mục tên riêng."""

    def __init__(self):
        super().__init__()
        self.addItems(list(GLOSSARY_KINDS))

    def gender(self) -> str | None:
        return list(GLOSSARY_KINDS.values())[self.currentIndex()]

    def set_gender(self, gender: str | None) -> None:
        self.setCurrentIndex(list(GLOSSARY_KINDS.values()).index(gender))


class TermForm(QHBoxLayout):
    """Hàng thêm một tên riêng: chữ Nhật, tiếng Anh, loại, nút Thêm. Enter ở hai ô chữ cũng là bấm Thêm."""

    def __init__(self, ja_hint: str, en_hint: str, on_add):
        super().__init__()
        self.ja = QLineEdit(placeholderText=ja_hint)
        self.en = QLineEdit(placeholderText=en_hint)
        self.kind = KindBox()
        self.kind.setFixedWidth(130)
        add = QPushButton("Thêm", autoDefault=False)
        add.clicked.connect(on_add)
        for field in (self.ja, self.en):
            field.returnPressed.connect(on_add)
        self.addWidget(self.ja, 1)
        self.addWidget(self.en, 1)
        self.addWidget(self.kind)
        self.addWidget(add)

    def entry(self) -> Entry | None:
        """Mục đang gõ. Thiếu ô nào thì đưa con trỏ tới ô đó và trả về None."""
        ja, en = clean(self.ja.text()), clean(self.en.text())
        if ja and en:
            return Entry(ja, en, self.kind.gender())
        (self.en if ja else self.ja).setFocus()
        return None

    def clear(self) -> None:
        self.ja.clear()
        self.en.clear()
        self.kind.set_gender(None)


class GlossaryEditor(QWidget):
    """Bảng các mục của glossary.txt: thêm, sửa, xóa, tìm, rồi lưu cùng các trang khác của cửa sổ.

    File vẫn sửa tay được; lúc lưu chỉ ghi phần đã đổi trong bảng (glossary.update_file).
    """

    def __init__(self, path: Path):
        super().__init__()
        self._path = path
        self._source = Glossary(path)
        self._saved: list[Entry] = []  # các mục đọc được từ file lần gần nhất

        self._message = _label("", "error")
        self._message.hide()
        self._form = TermForm("Chữ Nhật, vd. 霊夢", "Tiếng Anh, vd. Reimu", self._add)
        self._add_card, form = _card("Thêm mục")
        form.addLayout(self._form)

        self._search = QLineEdit(placeholderText="Tìm theo chữ Nhật hoặc tiếng Anh…")
        self._search.textChanged.connect(self._filter)
        notepad = QPushButton("Sửa bằng Notepad", autoDefault=False)
        notepad.clicked.connect(self._open_file)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Chữ Nhật", "Tiếng Anh", "Loại", ""])
        self._table.verticalHeader().hide()
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setMinimumHeight(150)
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionsClickable(False)
        header.setHighlightSections(False)
        for column in (0, 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        for column, width in ((2, 130), (3, 36)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self._table.setColumnWidth(column, width)
        card, layout = _card("Danh sách")
        tools = QHBoxLayout()
        tools.addWidget(self._search, 1)
        tools.addWidget(notepad)
        layout.addLayout(tools)
        layout.addWidget(self._table, 1)
        layout.addWidget(
            _label(
                "Bấm đúp vào ô để sửa. Nhân vật: chọn nữ / nam để bản dịch dùng đúng she / he. "
                "Khối chữ trùng hẳn một mục (nhãn menu, tên phòng…) thì dùng luôn bản dịch ở đây, không qua model.",
                "hint",
            )
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addWidget(self._message)
        outer.addWidget(self._add_card)
        outer.addWidget(card, 1)
        self.refresh()

    def _rows(self) -> list[Entry]:
        table = self._table
        return [
            Entry(clean(table.item(r, 0).text()), clean(table.item(r, 1).text()), table.cellWidget(r, 2).gender())
            for r in range(table.rowCount())
        ]

    def _set_row(self, row: int, entry: Entry) -> None:
        self._table.item(row, 0).setText(entry.ja)
        self._table.item(row, 1).setText(entry.en)
        self._table.cellWidget(row, 2).set_gender(entry.gender)

    def _append_row(self, entry: Entry) -> int:
        row = self._table.rowCount()
        self._table.insertRow(row)
        ja_item = QTableWidgetItem()
        self._table.setItem(row, 0, ja_item)
        self._table.setItem(row, 1, QTableWidgetItem())
        self._table.setCellWidget(row, 2, KindBox())
        remove = QToolButton(objectName="rowdelete", toolTip="Xóa mục này")
        remove.setIcon(glyph_icon("", 16, QColor(MUTED)))
        remove.clicked.connect(lambda: self._table.removeRow(self._table.row(ja_item)))
        self._table.setCellWidget(row, 3, remove)
        self._set_row(row, entry)
        return row

    def _form_text(self) -> str:
        return self._form.ja.text().strip() + self._form.en.text().strip()

    def _add(self) -> None:
        """Thêm mục đang gõ; chữ Nhật đã có trong bảng thì sửa dòng đó."""
        entry = self._form.entry()
        if entry is None:
            return
        self._search.clear()
        row = next((i for i, old in enumerate(self._rows()) if old.ja == entry.ja), None)
        if row is None:
            row = self._append_row(entry)
        else:
            self._set_row(row, entry)
        self._table.scrollToItem(self._table.item(row, 0))
        self._form.clear()
        self._form.ja.setFocus()

    def _filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for row, entry in enumerate(self._rows()):
            self._table.setRowHidden(row, needle not in f"{entry.ja}\n{entry.en}".casefold())

    def _open_file(self) -> None:
        try:
            os.startfile(ensure_file(self._path))
        except OSError as e:
            log.exception("Không mở được glossary")
            self._show_message(f"Không mở được {self._path}: {e}")

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._message.setVisible(bool(text))

    def refresh(self) -> None:
        """Đọc lại file (lúc mở, lúc quay lại cửa sổ sau khi sửa bằng Notepad). Bảng có thay đổi chưa lưu thì giữ nguyên."""
        if self.dirty():
            return
        try:
            entries = list(self._source.entries())
        except (OSError, UnicodeError) as e:
            log.warning("Không đọc được glossary: %s", e)
            self._set_readable(False)
            self._show_message(f"Không đọc được {self._path.name}. Mở bằng Notepad, lưu dạng UTF-8 rồi quay lại đây.")
            return
        self._set_readable(True)
        self._show_message("")
        if entries != self._saved:
            self._saved = entries
            self._table.setRowCount(0)
            for entry in entries:
                self._append_row(entry)
            self._filter(self._search.text())

    def _set_readable(self, readable: bool) -> None:
        for widget in (self._add_card, self._search, self._table):
            widget.setEnabled(readable)

    def entries(self) -> list[Entry]:
        return [entry for entry in self._rows() if entry.ja or entry.en]  # xóa trắng cả hai ô thì coi như xóa dòng

    def dirty(self) -> bool:
        return bool(self._form_text()) or set(self.entries()) != set(self._saved)

    def problem(self) -> str | None:
        """Lỗi cần sửa trước khi lưu, None nếu ổn. Mục đã gõ ở ô thêm mà quên bấm Thêm thì thêm luôn."""
        if self._form_text():
            self._add()
            if self._form_text():
                return f"Mục mới còn thiếu {'tiếng Anh' if self._form.ja.text().strip() else 'chữ Nhật'}."
        seen = set()
        for row, entry in enumerate(self._rows()):
            if not entry.ja and not entry.en:
                continue
            if not entry.ja or not entry.en:
                message = f"Dòng {row + 1}: thiếu {'tiếng Anh' if entry.ja else 'chữ Nhật'}."
            elif not valid_ja(entry.ja):
                message = f"Dòng {row + 1}: chữ Nhật không được có dấu = hay bắt đầu bằng #."
            elif entry.ja in seen:
                message = f"「{entry.ja}」đang có hai dòng."
            else:
                seen.add(entry.ja)
                continue
            self._search.clear()
            self._table.setCurrentCell(row, 0)
            return message
        return None

    def save(self) -> None:
        update_file(self._path, self._saved, self.entries())


class MainWindow(QDialog):
    """welcome: màn hình chào lúc mở app, nút chính là "Bắt đầu". `startup`: shortcut nào đang có (None: chưa có exe).

    Bấm nút chính thì lưu mọi trang một lần; đóng bằng ✕ (hay Hủy) thì bỏ hết thay đổi. Màn hình chào không đóng
    bằng Esc: ở đó ✕ là thoát app, lỡ tay bấm Esc (phím xóa bản dịch) thì không được thoát.
    """

    def __init__(
        self,
        config: Config,
        installed_models: list[str],
        startup: dict[str, bool] | None = None,
        *,
        welcome: bool = False,
    ):
        # cửa sổ thường: có nút thu nhỏ / phóng to, có ô ở thanh taskbar, app khác được đè lên
        super().__init__(
            None,
            Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint,
        )
        self.setWindowTitle("ScreenTranslator")
        self.setStyleSheet(STYLE)
        self.resize(880, 660)
        self.setMinimumSize(760, 520)
        self.welcome = welcome
        self._config = config
        self._chips: dict[str, list[QLabel]] = {}  # phím tắt in trong trang hướng dẫn, đổi theo ô sửa phím tắt

        self._hotkeys = {action: QLineEdit(text, objectName="keyedit") for action, text in config.hotkeys.items()}
        self._model = ComboBox(editable=True)
        self._model.addItems(installed_models)
        self._model.setCurrentText(config.model)
        self._profile = ComboBox()
        for key, profile in PROFILES.items():
            self._profile.addItem(profile["label"], key)
        self._profile.setCurrentIndex(self._profile.findData(config.profile))
        self.startup = StartupOptions(startup)
        self.glossary = GlossaryEditor(GLOSSARY_PATH)

        self._pages = QStackedWidget()
        builders = {
            "guide": self._guide_page,
            "glossary": self._glossary_page,
            "hotkeys": self._hotkeys_page,
            "settings": self._settings_page,
            "appearance": self._appearance_page,
        }
        self._nav = QListWidget(objectName="nav")
        self._nav.setIconSize(QSize(NAV_ICON_PX, NAV_ICON_PX))
        for page, (label, glyph) in PAGES.items():
            QListWidgetItem(glyph_icon(glyph, NAV_ICON_PX), f"  {label}", self._nav)
            self._pages.addWidget(builders[page]())
        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._nav.setCurrentRow(0)
        for action, edit in self._hotkeys.items():
            edit.textChanged.connect(
                lambda text, action=action: [chip.setText(text) for chip in self._chips.get(action, [])]
            )

        logo = QLabel("訳", objectName="logo", alignment=Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(32, 32)
        brand = QHBoxLayout()
        brand.addWidget(logo)
        brand.addWidget(QLabel("ScreenTranslator", objectName="brand"))
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 16, 12, 12)
        side.addLayout(brand)
        side.addSpacing(14)
        side.addWidget(self._nav, 1)
        side.addWidget(_label("Dịch chữ Nhật trên màn hình, chạy hoàn toàn trên máy.", "tagline"))

        self._error = _label("", "error")
        primary = QPushButton("Bắt đầu" if welcome else "Lưu", objectName="primary")
        primary.setDefault(True)
        primary.clicked.connect(self._validate)
        footer = QFrame(objectName="footer")
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(24, 12, 24, 12)
        bottom.addWidget(self._error, 1)
        if not welcome:
            cancel = QPushButton("Hủy")
            cancel.clicked.connect(self.reject)
            bottom.addWidget(cancel)
        bottom.addWidget(primary)

        content = QVBoxLayout()
        content.setSpacing(0)
        content.addWidget(self._pages, 1)
        content.addWidget(footer)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addLayout(content, 1)
        self._refresh_preview()
        win32.dark_title_bar(int(self.winId()), QColor(BG))

    def show_page(self, page: str) -> None:
        self._nav.setCurrentRow(list(PAGES).index(page))

    def current_page(self) -> str:
        return list(PAGES)[self._nav.currentRow()]

    # --- các trang ---

    def _page(self, title: str, subtitle: str, *items: QWidget, fill: bool = False) -> QScrollArea:
        """fill: mục cuối chiếm hết chỗ còn lại (bảng tự cuộn bên trong)."""
        page = QWidget(objectName="page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(4)
        layout.addWidget(_label(title, "title"))
        layout.addWidget(_label(subtitle, "subtitle"))
        layout.addSpacing(6)
        for item in items:
            layout.addWidget(item)
        if fill:
            layout.setStretchFactor(items[-1], 1)
        else:
            layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _chip(self, action: str) -> QLabel:
        chip = QLabel(self._config.hotkeys[action], objectName="key")
        self._chips.setdefault(action, []).append(chip)
        return chip

    def _steps(self, title: str, steps: list[tuple[str, str | None]]) -> QGroupBox:
        """Các bước đánh số; mỗi bước kèm phím tắt của nó (nếu có) ở bên phải."""
        card, layout = _card(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        for row, (text, action) in enumerate(steps):
            number = QLabel(str(row + 1), objectName="step", alignment=Qt.AlignmentFlag.AlignCenter)
            number.setFixedSize(22, 22)
            grid.addWidget(number, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(_label(text), row, 1)
            if action:
                grid.addWidget(self._chip(action), row, 2, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(grid)
        return card

    def _guide_page(self) -> QScrollArea:
        tips, layout = _card("Mẹo")
        for text in (
            "<b>Esc</b> xóa bản dịch đang hiện (bấm lần nữa thì game nhận Esc).",
            "Xem chữ Nhật gốc: kéo thanh <b>Trong suốt</b>, hoặc bấm nút ẩn / hiện bản dịch trên thanh.",
            "Tên dịch sai: menu <b>…</b> → <i>Sửa chữ OCR gần nhất</i>, bôi đen tên rồi gõ tên đúng.",
            "Chơi mà không dịch: menu <b>…</b> → <i>Tạm dừng</i> trả phím tắt cho game, gỡ model khỏi card đồ họa.",
            "Icon <b>訳</b> ở khay hệ thống: chuột trái ẩn / hiện thanh điều khiển, chuột phải mở menu.",
            "Mở app từ menu Start, Desktop hay tự chạy cùng Windows: trang <b>Cài đặt</b> → <i>Mở app</i>.",
        ):
            layout.addWidget(_label(f"•&nbsp; {text}"))
        dots = [("#808896", "đang nạp"), (ACCENT, "sẵn sàng"), ("#16a34a", "live mode"), ("#d97706", "tạm dừng")]
        legend = " &nbsp; ".join(f'<span style="color:{color}">●</span> {text}' for color, text in dots)
        layout.addWidget(_label(f"Màu icon: {legend}. Cần mở Ollama để dịch.", "hint"))
        return self._page(
            "Hướng dẫn",
            "Mọi nút đều có trên thanh điều khiển nổi; phím tắt dùng được cả lúc đang chơi.",
            self._steps(
                "Visual novel",
                [
                    ("<b>Chọn vùng</b> rồi kéo chuột quanh khung thoại.", "select"),
                    ("<b>Live</b>: câu mới tự được dịch, thanh điều khiển tự ẩn. <b>Esc</b> để tắt.", "live"),
                    ("Menu, nút bấm, bản đồ: <b>Cả cửa sổ</b>.", "screen"),
                ],
            ),
            self._steps(
                "Manga trên web",
                [
                    ("<b>Cả cửa sổ</b>: mỗi bóng thoại, kể cả chữ dọc, có một khung bản dịch.", "screen"),
                    (
                        "<b>Live</b>: cuộn hay lật trang là tự dịch lại. Chữ nhỏ quá thì phóng to trang (Ctrl +).",
                        "live",
                    ),
                ],
            ),
            tips,
        )

    def _glossary_page(self) -> QScrollArea:
        return self._page(
            "Tên riêng",
            "Tên nhân vật và thuật ngữ, để model dịch luôn đúng một kiểu. Lưu xong, lần dịch sau dùng ngay.",
            self.glossary,
            fill=True,
        )

    def _hotkeys_page(self) -> QScrollArea:
        card, layout = _card("Phím tắt toàn cục")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        for row, (action, edit) in enumerate(self._hotkeys.items()):
            edit.setFixedWidth(170)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(_label(HOTKEY_LABELS[action]), row, 0)
            grid.addWidget(edit, row, 1)
        esc = QLabel("Esc", objectName="key")
        grid.addWidget(_label("Xóa bản dịch đang hiện, tắt live mode"), len(self._hotkeys), 0)
        grid.addWidget(esc, len(self._hotkeys), 1, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(grid)
        layout.addWidget(_label("Gõ dạng Ctrl+Alt+T. Dùng được Ctrl, Alt, Shift, Win với A–Z, 0–9, F1–F12.", "hint"))
        return self._page("Phím tắt", "Bấm ở mọi nơi, kể cả khi game đang được chọn.", card)

    def _settings_page(self) -> QScrollArea:
        card, layout = _card("Dịch")
        for label, field in (
            ("Model dịch (Ollama)", self._model),
            ("Hồ sơ hiệu năng", self._profile),
        ):
            layout.addWidget(_label(label, wrap=False))
            layout.addWidget(field)
            layout.addSpacing(4)
        return self._page("Cài đặt", "Model dịch, hồ sơ hiệu năng và cách mở app.", card, self.startup)

    def _appearance_page(self) -> QScrollArea:
        self._preview = OverlayPreview()
        preview, layout = _card("Xem trước")
        layout.addWidget(self._preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._color = QColor(self._config.overlay_color)
        self._swatches = QButtonGroup(self)
        swatches = QHBoxLayout()
        swatches.setSpacing(8)
        for color, name in SWATCHES.items():
            swatch = QPushButton(toolTip=name, checkable=True)
            swatch.setFixedSize(28, 28)
            swatch.setStyleSheet(
                f"QPushButton {{ background: {color}; border: 2px solid #334155; border-radius: 14px; padding: 0; }}"
                "QPushButton:checked { border: 2px solid white; }"
            )
            swatch.clicked.connect(lambda *_, color=color: self._set_color(QColor(color)))
            self._swatches.addButton(swatch)
            swatches.addWidget(swatch)
        self._custom_color = QPushButton("Màu khác…")
        self._custom_color.clicked.connect(self._pick_color)
        swatches.addSpacing(6)
        swatches.addWidget(self._custom_color)
        swatches.addStretch()

        self._font_px = QSlider(Qt.Orientation.Horizontal)
        self._font_px.setRange(*FONT_PX_RANGE)
        self._font_px.setValue(self._config.overlay_font_px)
        self._font_px_value = QLabel()
        self._transparency = QSlider(Qt.Orientation.Horizontal)  # cài đặt lưu độ đặc = 100 − độ trong suốt
        self._transparency.setRange(100 - OPACITY_RANGE[1], 100 - OPACITY_RANGE[0])
        self._transparency.setSingleStep(5)
        self._transparency.setPageStep(10)
        self._transparency.setValue(100 - self._config.overlay_opacity)
        self._transparency_value = QLabel()
        for slider in (self._font_px, self._transparency):
            slider.valueChanged.connect(self._refresh_preview)

        card, layout = _card("Bản dịch")
        for label, row in (
            ("Màu nền", swatches),
            ("Cỡ chữ lớn nhất", _slider_row(self._font_px, self._font_px_value)),
            ("Độ trong suốt của nền", _slider_row(self._transparency, self._transparency_value)),
        ):
            layout.addWidget(_label(label, wrap=False))
            layout.addLayout(row)
            layout.addSpacing(4)
        layout.addWidget(_label("Trên 50% thì chữ có viền cho dễ đọc; chữ Nhật gốc lộ ra sau bản dịch.", "hint"))
        return self._page("Chỉnh màu", "Màu nền, cỡ chữ và độ trong suốt của khung bản dịch.", preview, card)

    # --- kết quả ---

    def changes(self) -> dict:
        """Các cài đặt sửa được trong cửa sổ này (để ghép vào cài đặt mới nhất của app)."""
        return {
            "model": self._model.currentText().strip(),
            "profile": self._profile.currentData(),
            "overlay_font_px": self._font_px.value(),
            "overlay_opacity": 100 - self._transparency.value(),
            "overlay_color": self._color.name(),
            **{f"hotkey_{action}": edit.text().strip() for action, edit in self._hotkeys.items()},
        }

    def result_config(self) -> Config:
        return replace(self._config, **self.changes())

    def _set_color(self, color: QColor) -> None:
        self._color = color
        self._refresh_preview()

    def keyPressEvent(self, event) -> None:
        if self.welcome and event.key() == Qt.Key.Key_Escape:
            return
        if self.current_page() == "glossary" and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return  # trang này gõ liên tục, Enter dùng để thêm mục chứ không phải bấm Lưu
        super().keyPressEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.glossary.refresh()

    def reject(self) -> None:
        """Đóng mà chưa lưu tên riêng thì hỏi lại: gõ cả danh sách tên rồi mất vì lỡ tay thì tiếc."""
        if self.glossary.dirty():
            answer = self._ask_unsaved()
            if answer == "save":
                self._validate()
            if answer != "discard":
                return
        super().reject()

    def _ask_unsaved(self) -> str:
        box = QMessageBox(
            QMessageBox.Icon.NoIcon, "ScreenTranslator", "Bạn đã sửa tên riêng nhưng chưa lưu.", parent=self
        )
        answers = {
            box.addButton("Lưu", QMessageBox.ButtonRole.AcceptRole): "save",
            box.addButton("Không lưu", QMessageBox.ButtonRole.DestructiveRole): "discard",
            box.addButton("Ở lại", QMessageBox.ButtonRole.RejectRole): "stay",
        }
        win32.dark_title_bar(int(box.winId()), QColor(BG))
        box.exec()
        return answers[box.clickedButton()]

    def _pick_color(self) -> None:
        # ô "Custom colors" (2 hàng, đánh số theo cột): hàng trên là các màu có sẵn, ô thừa cùng màu thẻ
        swatches = list(SWATCHES)
        for i in range(QColorDialog.customCount()):
            row_top = i % 2 == 0 and i // 2 < len(swatches)
            QColorDialog.setCustomColor(i, QColor(swatches[i // 2] if row_top else CARD))
        dialog = QColorDialog(self._color, self)
        dialog.setWindowTitle("Màu nền bản dịch")
        dialog.layout().setContentsMargins(16, 16, 16, 16)
        # cột độ sáng vẽ theo palette chứ không theo QSS (QSS chặn palette lan từ cửa sổ cha): nền tối, viền đều một
        # màu thay cho viền lõm sáng / tối, mũi tên chỉ độ sáng mới không trắng trên nền trắng
        for child in dialog.findChildren(QWidget):
            if child.metaObject().className() == "QtPrivate::QColorLuminancePicker":
                palette = child.palette()
                palette.setColor(QPalette.ColorRole.Window, QColor(BG))
                palette.setColor(QPalette.ColorRole.Light, QColor("#475569"))
                palette.setColor(QPalette.ColorRole.Dark, QColor("#475569"))
                child.setPalette(palette)
        win32.dark_title_bar(int(dialog.winId()), QColor(BG))
        if dialog.exec():
            self._set_color(dialog.selectedColor())

    def _refresh_preview(self) -> None:
        config = self.result_config()
        self._font_px_value.setText(f"{config.overlay_font_px} px")
        self._transparency_value.setText(f"{100 - config.overlay_opacity}%")
        for swatch, color in zip(self._swatches.buttons(), SWATCHES, strict=True):
            swatch.setChecked(color == config.overlay_color)
        custom = config.overlay_color not in SWATCHES
        self._custom_color.setStyleSheet(
            f"background: {config.overlay_color}; color: {Appearance.from_config(config).text_color().name()};"
            if custom
            else ""
        )
        self._preview.set_appearance(Appearance.from_config(config))

    def _validate(self) -> None:
        parsed = []
        for action, edit in self._hotkeys.items():
            try:
                parsed.append(parse_hotkey(edit.text()))
            except ValueError as e:
                self._fail("hotkeys", f"{HOTKEY_LABELS[action]}: {e}")
                return
        if len(set(parsed)) != len(parsed):
            self._fail("hotkeys", "Hai hành động đang dùng chung một phím tắt.")
            return
        if not self._model.currentText().strip():
            self._fail("settings", "Chưa chọn model dịch.")
            return
        if problem := self.glossary.problem():
            self._fail("glossary", problem)
            return
        try:
            self.glossary.save()
        except (OSError, UnicodeError) as e:
            log.exception("Không lưu được glossary")
            self._fail("glossary", f"Không lưu được tên riêng: {e}")
            return
        self.accept()

    def _fail(self, page: str, message: str) -> None:
        """Báo lỗi ở chân cửa sổ và mở trang có ô cần sửa."""
        self._error.setText(message)
        self.show_page(page)
