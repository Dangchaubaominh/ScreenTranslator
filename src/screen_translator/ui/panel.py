"""Thanh điều khiển nổi: làm mọi việc bằng chuột thay cho phím tắt.

Luôn trên cùng, kéo đi đâu cũng được (nắm vào chỗ trống trên thanh). Bấm vào không lấy focus của game
(WindowDoesNotAcceptFocus), và thanh không lọt vào ảnh chụp nên không bị đọc nhầm thành chữ cần dịch.
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import win32
from ..config import HOTKEY_LABELS

ICON_FONTS = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]  # Windows 11 / Windows 10
GLYPHS = {
    "grip": "",
    "select": "",
    "screen": "",
    "repeat": "",
    "live": "",
    "toggle": "",
    "menu": "",
    "close": "",
}
BUTTONS = {  # hành động → (chữ trên nút, chú thích khi rê chuột); chữ rỗng: chỉ có biểu tượng
    "select": ("Chọn vùng", HOTKEY_LABELS["select"]),
    "screen": ("Cả cửa sổ", HOTKEY_LABELS["screen"]),
    "repeat": ("Dịch lại", HOTKEY_LABELS["repeat"]),
    "live": ("Live", HOTKEY_LABELS["live"]),
    "toggle": ("", HOTKEY_LABELS["toggle"]),
    "menu": ("", "Thêm: tạm dừng, sửa chữ OCR, tên riêng, cài đặt, hướng dẫn, thoát"),
    "orient": ("", ""),  # chú thích theo chiều đang xếp, xem set_vertical
    "close": ("", "Ẩn thanh này (bấm icon 訳 ở khay hệ thống để hiện lại)"),
}
ORIENT_GLYPHS = {False: "", True: ""}  # đang ngang: nút "xếp dọc" (DockLeft); đang dọc: DockBottom
STYLE = """
#panel { background: rgba(15, 18, 30, 238); border: 1px solid rgba(255, 255, 255, 40); border-radius: 10px; }
QToolButton { color: #e2e8f0; background: transparent; border: none; border-radius: 6px; padding: 5px 2px 5px 6px;
              font: 13px "Segoe UI"; }
QToolButton:hover { background: rgba(255, 255, 255, 26); }
QToolButton#live:checked { background: #16a34a; }
QToolButton:disabled { color: #64748b; }
QToolButton::menu-indicator { image: none; }
QLabel { color: #94a3b8; font: 12px "Segoe UI"; padding: 0 3px; }
QSlider::groove:horizontal { height: 4px; background: #334155; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #e2e8f0; }
#separator { background: rgba(255, 255, 255, 40); }
"""


def glyph_icon(glyph: str, size: int = 16, color: QColor | None = None) -> QIcon:
    """Biểu tượng vẽ từ font icon có sẵn của Windows, nét theo DPI màn hình."""
    color = color or QColor(226, 232, 240)
    dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    pixmap = QPixmap(round(size * dpr), round(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    font = QFont()
    font.setFamilies(ICON_FONTS)
    font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)


def _separator(vertical: bool) -> QFrame:
    """Vạch ngăn nhóm nút: đứng khi thanh nằm ngang, nằm khi thanh dọc."""
    line = QFrame(objectName="separator")
    if vertical:
        line.setFixedHeight(1)
    else:
        line.setFixedSize(1, 22)
    return line


def _row(widgets: list[QWidget]) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(2)
    for widget in widgets:
        row.addWidget(widget)
    row.addStretch()
    return row


class ControlPanel(QWidget):
    triggered = Signal(str)  # hành động: select, screen, repeat, live, toggle, orient, close
    transparency_changed = Signal(int)  # % trong suốt của nền bản dịch
    moved = Signal(QPoint)  # kéo xong: chỗ mới của thanh

    def __init__(self, menu: QMenu, *, vertical: bool = False):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(STYLE)
        self._drag_from: QPoint | None = None

        self._frame = QFrame(self, objectName="panel")
        QVBoxLayout(self._frame).setContentsMargins(0, 0, 0, 0)
        self._body: QWidget | None = None  # chứa các nút; xoay thanh thì xếp lại vào một body mới
        self._grip = QLabel(toolTip="Kéo để dời thanh")
        self._grip.setPixmap(glyph_icon(GLYPHS["grip"], 14, QColor(100, 116, 139)).pixmap(14, 14))
        self.status = QLabel()  # icon 訳 tô màu theo trạng thái, giống icon ở khay

        self.buttons: dict[str, QToolButton] = {}
        for action, (text, tip) in BUTTONS.items():
            button = QToolButton(objectName=action, text=text, toolTip=tip)
            if action in GLYPHS:
                button.setIcon(glyph_icon(GLYPHS[action]))
            button.setIconSize(QSize(16, 16))
            style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else Qt.ToolButtonStyle.ToolButtonIconOnly
            button.setToolButtonStyle(style)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if action == "menu":
                button.setMenu(menu)
                button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            else:
                button.clicked.connect(lambda *_, action=action: self.triggered.emit(action))
            self.buttons[action] = button
        self.buttons["live"].setCheckable(True)

        self.transparency = QSlider(Qt.Orientation.Horizontal, toolTip="Độ trong suốt của nền bản dịch")
        self.transparency.setRange(0, 100)
        self.transparency.setSingleStep(5)
        self.transparency.setPageStep(10)
        self.transparency.setFixedWidth(90)
        self.transparency.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.transparency_value = QLabel()
        self.transparency_value.setFixedWidth(40)  # vừa "100%"
        self.transparency.valueChanged.connect(self._on_transparency)
        self._transparency_label = QLabel("Trong suốt")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)
        self.set_vertical(vertical)
        self.excluded_from_capture = win32.exclude_from_capture(int(self.winId()))

    def set_vertical(self, vertical: bool) -> None:
        """Xếp các nút thành một hàng ngang (để ở mép trên màn hình) hay một cột dọc (mép trái / phải)."""
        self.vertical = vertical
        body = QWidget(self._frame)
        direction = QBoxLayout.Direction.TopToBottom if vertical else QBoxLayout.Direction.LeftToRight
        layout = QBoxLayout(direction, body)
        layout.setContentsMargins(*((5, 6, 5, 6) if vertical else (6, 4, 6, 4)))
        layout.setSpacing(2)
        actions = [self.buttons[action] for action in ("select", "screen", "repeat", "live")]
        transparency = [self._transparency_label, self.transparency, self.transparency_value]
        if vertical:
            layout.addLayout(_row([self._grip, self.status]))
            for button in actions:
                layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(_separator(vertical))
            layout.addWidget(self._transparency_label)
            layout.addLayout(_row(transparency[1:]))
            layout.addWidget(_separator(vertical))
            layout.addLayout(_row([self.buttons[action] for action in ("toggle", "orient", "menu", "close")]))
        else:
            tail = [self.buttons[action] for action in ("toggle", "orient", "menu", "close")]
            sections = [[self._grip, self.status, *actions], transparency, tail]
            for i, section in enumerate(sections):
                if i:
                    layout.addWidget(_separator(vertical))
                for widget in section:
                    layout.addWidget(widget)
        old, self._body = self._body, body
        if old is not None:  # các nút đã chuyển sang body mới, body cũ chỉ còn vạch ngăn
            self._frame.layout().removeWidget(old)
            old.hide()
            old.deleteLater()
        self._frame.layout().addWidget(body)
        for widget in body.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            widget.show()  # đổi widget cha thì Qt ẩn widget đi
        body.show()
        orient = self.buttons["orient"]
        orient.setIcon(glyph_icon(ORIENT_GLYPHS[vertical]))
        orient.setToolTip("Xếp thanh nằm ngang" if vertical else "Xếp thanh thành cột dọc")
        # tính lại layout ngay (bình thường Qt để tới vòng sự kiện sau), không thì cỡ cũ chặn thanh co lại
        self._frame.layout().activate()
        if self.layout() is not None:
            self.layout().activate()
        self.resize(self.sizeHint())  # không dùng adjustSize: nó ép cửa sổ rộng ít nhất 200 px

    def set_hotkeys(self, hotkeys: dict[str, str]) -> None:
        for action, key in hotkeys.items():
            if action in self.buttons:
                self.buttons[action].setToolTip(f"{BUTTONS[action][1]} ({key})")

    def set_state(self, *, live: bool, paused: bool, transparency: int) -> None:
        """Cập nhật nút theo trạng thái của app; không phát lại signal."""
        self.buttons["live"].setChecked(live)
        for action in ("select", "screen", "repeat", "live", "toggle"):
            self.buttons[action].setEnabled(not paused)
        self.transparency.blockSignals(True)
        self.transparency.setValue(transparency)
        self.transparency.blockSignals(False)
        self.transparency_value.setText(f"{transparency}%")

    def set_status(self, icon: QIcon, text: str) -> None:
        self.status.setPixmap(icon.pixmap(18, 18))
        self.status.setToolTip(text)

    def _on_transparency(self, value: int) -> None:
        self.transparency_value.setText(f"{value}%")
        self.transparency_changed.emit(value)

    # --- kéo thanh đi chỗ khác ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_from is not None:
            self._drag_from = None
            self.moved.emit(self.pos())
