"""Hộp thoại sửa chữ OCR, cài đặt, và màn hình hướng dẫn."""

from dataclasses import replace
from html import escape

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import FONT_PX_RANGE, HOTKEY_LABELS, OCR_ENGINES, OPACITY_RANGE, OVERLAY_POSITIONS, PROFILES, Config
from ..hotkeys import parse_hotkey
from ..shortcuts import LABELS as SHORTCUT_LABELS
from .overlay import Appearance, fit_beside, fit_text, paint_block


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


class StartupOptions(QGroupBox):
    """Các cách mở app không cần terminal. `checked` None: chưa có screen-translator-gui.exe."""

    def __init__(self, checked: dict[str, bool] | None):
        super().__init__("Mở app")
        layout = QVBoxLayout(self)
        self._available = checked is not None
        self._boxes = {}
        for key, label in SHORTCUT_LABELS.items():
            box = QCheckBox(label)
            box.setChecked(bool(checked and checked[key]))
            box.setEnabled(checked is not None)
            layout.addWidget(box)
            self._boxes[key] = box
        if checked is None:
            note = QLabel(
                "Chưa có screen-translator-gui.exe: chạy <code>uv sync</code> trong thư mục dự án rồi mở lại app."
            )
            note.setWordWrap(True)
            layout.addWidget(note)

    def wanted(self) -> dict[str, bool] | None:
        """Shortcut nào cần có; None khi không chọn được (chưa có exe)."""
        return {key: box.isChecked() for key, box in self._boxes.items()} if self._available else None


class OverlayPreview(QWidget):
    """Khung thoại giả, vẽ bản dịch theo cỡ chữ / màu / độ trong / vị trí đang chọn."""

    JA = "霊夢「おはよう、魔理沙。今日は早いのね」"
    EN = 'Reimu: "Good morning, Marisa. You\'re early today."'

    def __init__(self):
        super().__init__()
        self.setFixedSize(480, 310)  # đủ chỗ cho 3 dòng chữ 48 px bên trên / dưới khung thoại
        self.appearance, self.position = Appearance(), "cover"

    def set_appearance(self, appearance: Appearance, position: str) -> None:
        self.appearance, self.position = appearance, position
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(64, 82, 70))  # cảnh nền của game
        # khung thoại dồn về phía đối diện chỗ đặt bản dịch, để chữ to vẫn đủ chỗ
        top = {"above": self.height() - 86, "below": 16}.get(self.position, (self.height() - 70) // 2)
        box = QRect(16, top, self.width() - 32, 70)
        painter.fillRect(box, QColor(22, 26, 40))
        font = QFont("Yu Gothic UI")
        font.setPixelSize(20)
        painter.setFont(font)
        painter.setPen(QColor(240, 240, 240))
        painter.drawText(
            box.adjusted(14, 0, -14, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.JA
        )
        max_px = self.appearance.max_px
        fitted = (
            fit_text(box, self.EN, max_px)
            if self.position == "cover"
            else fit_beside(box, self.EN, self.position, max_px, self.rect())
        )
        paint_block(painter, fitted, self.EN, self.appearance)


class SettingsDialog(QDialog):
    """`startup`: shortcut nào đang có (None: chưa có exe để tạo shortcut)."""

    def __init__(self, config: Config, installed_models: list[str], startup: dict[str, bool] | None = None):
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
        self.startup = StartupOptions(startup)
        translation = QWidget()
        form = QFormLayout()
        form.addRow("Model dịch (Ollama):", self._model)
        form.addRow("Đọc chữ (OCR):", self._ocr_engine)
        form.addRow("Hồ sơ hiệu năng:", self._profile)
        layout = QVBoxLayout(translation)
        layout.addLayout(form)
        layout.addWidget(self.startup)
        layout.addStretch()

        self._position = QComboBox()
        for key, label in OVERLAY_POSITIONS.items():
            self._position.addItem(label, key)
        self._position.setCurrentIndex(self._position.findData(config.overlay_position))
        self._font_px = QSpinBox(suffix=" px")
        self._font_px.setRange(*FONT_PX_RANGE)
        self._font_px.setValue(config.overlay_font_px)
        self._transparency = QSpinBox(suffix=" %", singleStep=10)  # cài đặt lưu độ đặc = 100 − độ trong suốt
        self._transparency.setRange(100 - OPACITY_RANGE[1], 100 - OPACITY_RANGE[0])
        self._transparency.setValue(100 - config.overlay_opacity)
        self._color = QColor(config.overlay_color)
        self._color_button = QPushButton("Đổi màu…")
        self._color_button.clicked.connect(self._pick_color)
        self._preview = OverlayPreview()
        for signal in (
            self._position.currentIndexChanged,
            self._font_px.valueChanged,
            self._transparency.valueChanged,
        ):
            signal.connect(self._refresh_preview)
        self._refresh_preview()
        display = QWidget()
        form = QFormLayout()
        form.addRow("Chỗ hiện bản dịch:", self._position)
        form.addRow("Cỡ chữ lớn nhất:", self._font_px)
        form.addRow("Độ trong suốt của nền:", self._transparency)
        form.addRow("Màu nền:", self._color_button)
        layout = QVBoxLayout(display)
        layout.addLayout(form)
        layout.addWidget(self._preview, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(QLabel(f"Xem nhanh chữ Nhật gốc: {config.hotkey_toggle} ẩn / hiện bản dịch."))

        hotkeys = QWidget()
        form = QFormLayout()
        for action, edit in self._hotkeys.items():
            form.addRow(f"{HOTKEY_LABELS[action]}:", edit)
        layout = QVBoxLayout(hotkeys)
        layout.addLayout(form)
        layout.addWidget(QLabel("Phím tắt dạng Ctrl+Alt+T; dùng được Ctrl, Alt, Shift, Win với A–Z, 0–9, F1–F12."))
        layout.addStretch()

        tabs = QTabWidget()
        tabs.addTab(translation, "Dịch")
        tabs.addTab(display, "Hiển thị")
        tabs.addTab(hotkeys, "Phím tắt")
        self._error = QLabel(styleSheet="color: #c0392b")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

    def result_config(self) -> Config:
        return replace(
            self._config,
            model=self._model.currentText().strip(),
            profile=self._profile.currentData(),
            ocr_engine=self._ocr_engine.currentData(),
            overlay_position=self._position.currentData(),
            overlay_font_px=self._font_px.value(),
            overlay_opacity=100 - self._transparency.value(),
            overlay_color=self._color.name(),
            **{f"hotkey_{action}": edit.text().strip() for action, edit in self._hotkeys.items()},
        )

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self._color, self, "Màu nền bản dịch")
        if color.isValid():
            self._color = color
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        config = self.result_config()
        self._color_button.setStyleSheet(
            f"background-color: {config.overlay_color}; color: {Appearance.from_config(config).text_color().name()}"
        )
        self._preview.set_appearance(Appearance.from_config(config), config.overlay_position)

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


GUIDE = """
<h2>ScreenTranslator</h2>
<p>Mọi việc làm được bằng chuột trên <b>thanh điều khiển</b> nổi ở mép trên màn hình (nắm chỗ trống
để kéo đi), hoặc bằng phím tắt. Icon <b>訳</b> ở khay hệ thống, cạnh đồng hồ (có thể nằm trong mũi tên
<b>^</b>): chuột trái ẩn / hiện thanh điều khiển, chuột phải mở menu.</p>
<h3>Dịch visual novel</h3>
<ol>
<li>Mở game, bấm <b>Chọn vùng</b> ({select}) rồi kéo chuột quanh khung thoại.</li>
<li>Bấm <b>Live</b> ({live}): câu mới hiện ra là tự được dịch, icon chuyển xanh lá.</li>
<li>Menu, nút bấm, bản đồ…: bấm <b>Cả cửa sổ</b> ({screen}).</li>
<li>Muốn xem chữ Nhật gốc: chọn <b>Hiện: Trên / Dưới</b> cho bản dịch nằm ngay trên / dưới khung thoại,
kéo thanh <b>Trong suốt</b>, hoặc {toggle} ẩn / hiện bản dịch.</li>
<li>Cần chơi mà không dịch: <b>Tạm dừng</b> trả phím tắt cho game và gỡ model dịch khỏi card đồ họa.</li>
<li>Tên nhân vật bị dịch sai: menu → <i>Tên riêng, thuật ngữ…</i></li>
</ol>
<h3>Phím tắt</h3>
<table cellspacing="0" cellpadding="3">{rows}</table>
<p>Cần mở Ollama để dịch. Icon xám: đang nạp model, xanh dương: sẵn sàng, xanh lá: live mode đang bật,
chấm cam: đang tạm dừng.</p>
"""


class GuideDialog(QDialog):
    """Màn hình chào lần đầu (kèm lựa chọn shortcut), mở lại được từ menu Hướng dẫn."""

    def __init__(self, hotkeys: dict[str, str], startup: StartupOptions | None = None):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Hướng dẫn — ScreenTranslator")
        self.startup = startup
        rows = "".join(
            f"<tr><td><b>{escape(hotkeys[action])}</b></td><td>{escape(label)}</td></tr>"
            for action, label in HOTKEY_LABELS.items()
        )
        text = QLabel(GUIDE.format(rows=rows, **{action: escape(key) for action, key in hotkeys.items()}))
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        buttons = QDialogButtonBox()
        buttons.addButton("Bắt đầu" if startup is not None else "Đóng", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        if startup is not None:
            layout.addWidget(startup)
        layout.addWidget(buttons)
        self.setFixedWidth(560)
