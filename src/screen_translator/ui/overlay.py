"""Overlay vẽ bản dịch đè lên chữ gốc: trong suốt, luôn trên cùng, click xuyên qua, không lọt vào ảnh chụp.

Một overlay vẽ được nhiều khối (dịch cả cửa sổ game: mỗi dòng / đoạn chữ một khối, như Google Lens).
"""

from typing import NamedTuple

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from .. import win32

PADDING = 10
MIN_PX, MAX_PX = 12, 34
FONT_FAMILY = "Segoe UI"
TEXT_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
BACKGROUND = QColor(12, 16, 28)  # nền đặc: chữ Nhật gốc không lộ ra sau bản dịch
TEXT_COLOR = QColor(245, 245, 245)
DIM_TEXT_COLOR = QColor(160, 168, 184)


class Fitted(NamedTuple):
    font: QFont
    rect: QRect
    padding: int


def fit_text(rect: QRect, text: str) -> Fitted:
    """Cỡ chữ lớn nhất (MAX_PX → MIN_PX) để `text` vừa trong `rect`.

    Nhỏ nhất rồi vẫn không vừa thì nới khung sang phải / xuống dưới cho đủ chỗ.
    """
    padding = max(2, min(PADDING, rect.height() // 5))  # nhãn menu nhỏ thì lề nhỏ
    font = QFont(FONT_FAMILY)
    for px in range(MAX_PX, MIN_PX - 1, -1):
        font.setPixelSize(px)
        inner = rect.adjusted(padding, padding, -padding, -padding)
        needed = QFontMetrics(font).boundingRect(inner, TEXT_FLAGS, text)
        if needed.height() <= inner.height() and needed.width() <= inner.width():
            return Fitted(font, rect, padding)
    grown = QRect(
        rect.x(),
        rect.y(),
        max(rect.width(), needed.width() + 2 * padding),
        max(rect.height(), needed.height() + 2 * padding),
    )
    return Fitted(font, grown, padding)


class Overlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._items: list[tuple[Fitted, str]] = []  # khung tính theo góc trên-trái của overlay
        self._fitted: dict[tuple, Fitted] = {}  # khi hiện dần từng khối, các khối cũ không phải tính lại
        self._dim = False
        # Nếu Windows quá cũ không hỗ trợ, app phải ẩn overlay trước mỗi lần chụp lại vùng
        self.excluded_from_capture = win32.exclude_from_capture(int(self.winId()))

    def show_items(self, items: list[tuple[QRect, str]], *, dim: bool = False) -> None:
        """Hiện từng `(khung tọa độ logic, chữ)`. dim=True: chữ xám, dùng cho trạng thái chờ / lỗi."""
        fitted = []
        for rect, text in items:
            key = (rect.x(), rect.y(), rect.width(), rect.height(), text)
            if key not in self._fitted:
                self._fitted[key] = fit_text(rect, text)
            fitted.append((self._fitted[key], text))
        if len(self._fitted) > 2000:
            self._fitted.clear()
        self._dim = dim
        if not fitted:
            self._items = []
            self.hide()
            return
        area = fitted[0][0].rect
        for f, _ in fitted[1:]:
            area = area.united(f.rect)
        self._items = [(f._replace(rect=f.rect.translated(-area.topLeft())), text) for f, text in fitted]
        self.setGeometry(area)
        self.show()
        self.update()

    def show_text(self, rect: QRect, text: str, *, dim: bool = False) -> None:
        self.show_items([(rect, text)], dim=dim)

    def has_text(self) -> bool:
        return bool(self._items)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for fitted, text in self._items:
            rect, padding = fitted.rect, fitted.padding
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(BACKGROUND)
            radius = min(8, rect.height() // 4)
            painter.drawRoundedRect(rect, radius, radius)
            painter.setFont(fitted.font)
            painter.setPen(DIM_TEXT_COLOR if self._dim else TEXT_COLOR)
            painter.drawText(rect.adjusted(padding, padding, -padding, -padding), TEXT_FLAGS, text)
