"""Hộp thoại sửa chữ OCR. Hướng dẫn, phím tắt, cài đặt và chỉnh màu nằm chung trong cửa sổ chính (window.py)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout


class EditDialog(QDialog):
    """Xem chữ OCR đọc được, sửa tay rồi dịch lại; copy chữ gốc / bản dịch."""

    retranslate = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Sửa chữ OCR — ScreenTranslator")
        self.resize(520, 360)
        self._ja = QPlainTextEdit()
        self._en = QPlainTextEdit(readOnly=True)
        translate_button = QPushButton("Dịch lại")
        translate_button.setDefault(True)
        translate_button.clicked.connect(lambda: self.retranslate.emit(self._ja.toPlainText()))
        copy_ja = QPushButton("Copy chữ Nhật")
        copy_ja.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._ja.toPlainText()))
        copy_en = QPushButton("Copy bản dịch")
        copy_en.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._en.toPlainText()))

        buttons = QHBoxLayout()
        for button in (translate_button, copy_ja, copy_en):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Chữ tiếng Nhật (sửa được nếu OCR đọc sai):"))
        layout.addWidget(self._ja)
        layout.addWidget(QLabel("Bản dịch:"))
        layout.addWidget(self._en)
        layout.addLayout(buttons)

    def set_result(self, ja: str, en: str) -> None:
        self._ja.setPlainText(ja)
        self._en.setPlainText(en)

    def set_busy(self) -> None:
        self._en.setPlainText("Đang dịch…")
