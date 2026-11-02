"""Hộp thoại sửa chữ OCR. Hướng dẫn, tên riêng, phím tắt, cài đặt, chỉnh màu nằm chung trong cửa sổ chính (window.py)."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .. import win32
from ..config import GLOSSARY_PATH
from ..glossary import Entry, Glossary, clean, format_line, update_file, valid_ja
from ..i18n import tr
from .window import BG, STYLE, TermForm

log = logging.getLogger(__name__)


class EditDialog(QDialog):
    """Xem chữ OCR đọc được, sửa tay rồi dịch lại; copy chữ gốc / bản dịch; thêm nhanh một tên dịch sai vào tên riêng."""

    retranslate = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(tr("Sửa chữ OCR — ScreenTranslator"))
        self.setStyleSheet(STYLE)
        self.resize(560, 460)
        self._glossary = Glossary(GLOSSARY_PATH)
        self._ja = QPlainTextEdit()
        self._ja.selectionChanged.connect(self._on_selection)
        self._en = QPlainTextEdit(readOnly=True)

        self._term = TermForm("Chữ gốc", "Tên đúng, tiếng Anh", self._add_term)
        self._term_message = QLabel(objectName="hint", wordWrap=True)
        self._term_message.hide()

        # không nút nào là nút mặc định: Enter ở hàng thêm tên chỉ để thêm tên
        translate_button = QPushButton(tr("Dịch lại"), objectName="primary", autoDefault=False)
        translate_button.clicked.connect(self._retranslate)
        copy_ja = QPushButton(tr("Copy chữ gốc"), autoDefault=False)
        copy_ja.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._ja.toPlainText()))
        copy_en = QPushButton(tr("Copy bản dịch"), autoDefault=False)
        copy_en.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._en.toPlainText()))

        buttons = QHBoxLayout()
        for button in (translate_button, copy_ja, copy_en):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(QLabel(tr("Chữ gốc (sửa được nếu OCR đọc sai):")))
        layout.addWidget(self._ja)
        layout.addWidget(QLabel(tr("Bản dịch:")))
        layout.addWidget(self._en)
        layout.addWidget(QLabel(tr("Tên dịch sai: bôi đen tên đó ở ô chữ gốc, gõ tên đúng rồi Enter.")))
        layout.addLayout(self._term)
        layout.addWidget(self._term_message)
        layout.addLayout(buttons)
        win32.dark_title_bar(int(self.winId()), QColor(BG))

    def set_result(self, ja: str, en: str) -> None:
        self._ja.setPlainText(ja)
        self._en.setPlainText(en)

    def set_busy(self) -> None:
        self._en.setPlainText(tr("Đang dịch…"))

    def _retranslate(self) -> None:
        self.retranslate.emit(self._ja.toPlainText())

    def _on_selection(self) -> None:
        """Bôi đen một tên: điền vào hàng thêm tên; tên đã có thì hiện luôn bản dịch đang dùng để sửa."""
        selected = clean("".join(self._ja.textCursor().selectedText().split()))  # bôi qua nhiều dòng thì nối lại
        if not selected:
            return
        entry = self._known_term(selected)
        self._term.ja.setText(selected)
        self._term.en.setText(entry.en if entry else "")
        self._term.kind.set_gender(entry.gender if entry else None)
        self._show_term_message("")

    def _known_term(self, ja: str) -> Entry | None:
        try:
            return next((entry for entry in self._glossary.entries() if entry.ja == ja), None)
        except (OSError, UnicodeError):
            return None  # lúc thêm sẽ báo lỗi: chưa cần báo khi mới bôi đen

    def _add_term(self) -> None:
        """Ghi tên vào glossary.txt và dịch lại ngay, để thấy kết quả với tên mới."""
        entry = self._term.entry()
        if entry is None:
            return
        if not valid_ja(entry.ja):
            self._show_term_message(tr("Chữ gốc không được có dấu = hay bắt đầu bằng #."), error=True)
            return
        try:
            update_file(GLOSSARY_PATH, [], [entry])
        except (OSError, UnicodeError) as e:
            log.exception("Không ghi được glossary")
            message = tr("Không ghi được {file} (cần lưu dạng UTF-8): {error}", file=GLOSSARY_PATH.name, error=e)
            self._show_term_message(message, error=True)
            return
        self._term.clear()
        self._show_term_message(tr("Đã lưu vào tên riêng: {line}", line=format_line(entry)))
        if self._ja.toPlainText().strip():
            self._retranslate()

    def _show_term_message(self, text: str, *, error: bool = False) -> None:
        self._term_message.setStyleSheet("color: #f87171; font-size: 12px;" if error else "")
        self._term_message.setText(text)
        self._term_message.setVisible(bool(text))
