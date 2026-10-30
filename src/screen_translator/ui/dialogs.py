"""Hộp thoại sửa chữ OCR và hộp thoại cài đặt."""

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..config import HOTKEY_LABELS, OCR_ENGINES, PROFILES, Config
from ..hotkeys import parse_hotkey


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


class SettingsDialog(QDialog):
    def __init__(self, config: Config, installed_models: list[str]):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Cài đặt — ScreenTranslator")
        self._config = config

        self._model = QComboBox(editable=True)
        self._model.addItems(installed_models)
        self._model.setCurrentText(config.model)
        self._profile = QComboBox()
        for key, profile in PROFILES.items():
            self._profile.addItem(profile["label"], key)
        self._profile.setCurrentIndex(self._profile.findData(config.profile))
        self._ocr_engine = QComboBox()
        for key, label in OCR_ENGINES.items():
            self._ocr_engine.addItem(label, key)
        self._ocr_engine.setCurrentIndex(self._ocr_engine.findData(config.ocr_engine))
        self._hotkeys = {action: QLineEdit(text) for action, text in config.hotkeys.items()}
        self._error = QLabel(styleSheet="color: #c0392b")

        form = QFormLayout()
        form.addRow("Model dịch (Ollama):", self._model)
        form.addRow("Đọc chữ (OCR):", self._ocr_engine)
        form.addRow("Hồ sơ hiệu năng:", self._profile)
        for action, edit in self._hotkeys.items():
            form.addRow(f"{HOTKEY_LABELS[action]}:", edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Phím tắt dạng Ctrl+Alt+T; dùng được Ctrl, Alt, Shift, Win với A–Z, 0–9, F1–F12."))
        layout.addWidget(self._error)
        layout.addWidget(buttons)

    def result_config(self) -> Config:
        return replace(
            self._config,
            model=self._model.currentText().strip(),
            profile=self._profile.currentData(),
            ocr_engine=self._ocr_engine.currentData(),
            **{f"hotkey_{action}": edit.text().strip() for action, edit in self._hotkeys.items()},
        )

    def _validate(self) -> None:
        parsed = []
        for action, edit in self._hotkeys.items():
            try:
                parsed.append(parse_hotkey(edit.text()))
            except ValueError as e:
                self._error.setText(f"{HOTKEY_LABELS[action]}: {e}")
                return
        if len(set(parsed)) != len(parsed):
            self._error.setText("Hai hành động đang dùng chung một phím tắt.")
            return
        if not self._model.currentText().strip():
            self._error.setText("Chưa chọn model dịch.")
            return
        self.accept()
