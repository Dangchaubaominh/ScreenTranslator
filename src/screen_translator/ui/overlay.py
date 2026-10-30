"""Overlay vẽ bản dịch đè lên chữ gốc: trong suốt, luôn trên cùng, click xuyên qua, không lọt vào ảnh chụp.

Một overlay vẽ được nhiều khối (dịch cả cửa sổ game: mỗi dòng / đoạn chữ một khối, như Google Lens).
Bản dịch của vùng đã chọn cũng có thể đặt ngay trên / dưới vùng đó để chữ Nhật gốc vẫn thấy.
"""

from typing import NamedTuple

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from .. import win32
from ..config import Config

PADDING = 10
MIN_PX, MAX_PX = 12, 34
HINT_PX, HINT_WIDTH = 15, 480  # thông báo ngắn tự tắt
GAP = 6  # khoảng hở giữa vùng đã chọn và bản dịch đặt bên trên / dưới nó
FONT_FAMILY = "Segoe UI"
TEXT_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
BACKGROUND = QColor(12, 16, 28)  # nền đặc: chữ Nhật gốc không lộ ra sau bản dịch
TEXT_COLOR, DIM_TEXT_COLOR = QColor(245, 245, 245), QColor(160, 168, 184)
DARK_TEXT_COLOR, DARK_DIM_TEXT_COLOR = QColor(20, 22, 28), QColor(96, 102, 116)  # trên nền sáng


class Fitted(NamedTuple):
    font: QFont
    rect: QRect
    padding: int


class Appearance(NamedTuple):
    max_px: int = MAX_PX
    background: QColor = BACKGROUND  # kể cả độ trong (alpha)

    @classmethod
    def from_config(cls, config: Config) -> "Appearance":
        background = QColor(config.overlay_color)
        background.setAlphaF(config.overlay_opacity / 100)
        return cls(config.overlay_font_px, background)

    def text_color(self, dim: bool = False) -> QColor:
        if self.background.lightnessF() > 0.55:
            return DARK_DIM_TEXT_COLOR if dim else DARK_TEXT_COLOR
        return DIM_TEXT_COLOR if dim else TEXT_COLOR


def fit_text(rect: QRect, text: str, max_px: int = MAX_PX) -> Fitted:
    """Cỡ chữ lớn nhất (max_px → MIN_PX) để `text` vừa trong `rect`.

    Nhỏ nhất rồi vẫn không vừa thì nới khung sang phải / xuống dưới cho đủ chỗ.
    """
    padding = max(2, min(PADDING, rect.height() // 5))  # nhãn menu nhỏ thì lề nhỏ
    font = QFont(FONT_FAMILY)
    for px in range(max_px, MIN_PX - 1, -1):
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


def clamp(rect: QRect, bounds: QRect) -> QRect:
    """Dời `rect` vào trong `bounds` (vd. màn hình), giữ nguyên kích thước."""
    x = max(bounds.left(), min(rect.x(), bounds.right() + 1 - rect.width()))
    y = max(bounds.top(), min(rect.y(), bounds.bottom() + 1 - rect.height()))
    return QRect(x, y, rect.width(), rect.height())


def fit_beside(rect: QRect, text: str, position: str, max_px: int, bounds: QRect) -> Fitted:
    """Khung rộng bằng `rect`, cao vừa đủ cho chữ cỡ `max_px`, đặt ngay trên ("above") / dưới ("below") `rect`.

    Phía đó hết chỗ trong `bounds` thì đặt sang phía bên kia.
    """
    font = QFont(FONT_FAMILY)
    font.setPixelSize(max_px)
    inner = QRect(0, 0, max(1, rect.width() - 2 * PADDING), 100_000)
    height = QFontMetrics(font).boundingRect(inner, TEXT_FLAGS, text).height() + 2 * PADDING
    above = QRect(rect.x(), rect.top() - GAP - height, rect.width(), height)
    below = QRect(rect.x(), rect.bottom() + 1 + GAP, rect.width(), height)
    first, second = (above, below) if position == "above" else (below, above)
    box = first if bounds.contains(first) or not bounds.contains(second) else second
    return Fitted(font, clamp(box, bounds), PADDING)


def hint_size(text: str) -> QSize:
    """Khung vừa khít một thông báo ngắn chữ cỡ HINT_PX, rộng tối đa HINT_WIDTH."""
    font = QFont(FONT_FAMILY)
    font.setPixelSize(HINT_PX)
    needed = QFontMetrics(font).boundingRect(QRect(0, 0, HINT_WIDTH - 2 * PADDING, 10_000), TEXT_FLAGS, text)
    return QSize(needed.width() + 2 * PADDING + 2, needed.height() + 2 * PADDING)


def paint_block(painter: QPainter, fitted: Fitted, text: str, appearance: Appearance, dim: bool = False) -> None:
    rect, padding = fitted.rect, fitted.padding
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(appearance.background)
    radius = min(8, rect.height() // 4)
    painter.drawRoundedRect(rect, radius, radius)
    painter.setFont(fitted.font)
    painter.setPen(appearance.text_color(dim))
    painter.drawText(rect.adjusted(padding, padding, -padding, -padding), TEXT_FLAGS, text)


def _screen_bounds(rect: QRect) -> QRect:
    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    return screen.geometry()


class Overlay(QWidget):
    def __init__(self, appearance: Appearance | None = None):
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
        self.appearance = appearance or Appearance()
        self._items: list[tuple[Fitted, str]] = []  # khung tính theo góc trên-trái của overlay
        self._fitted: dict[tuple, Fitted] = {}  # khi hiện dần từng khối, các khối cũ không phải tính lại
        self._dim = False
        # Nếu Windows quá cũ không hỗ trợ, app phải ẩn overlay trước mỗi lần chụp lại vùng
        self.excluded_from_capture = win32.exclude_from_capture(int(self.winId()))

    def set_appearance(self, appearance: Appearance) -> None:
        """Áp dụng từ lần show_items sau."""
        self.appearance = appearance
        self._fitted.clear()

    def show_items(self, items: list[tuple[QRect, str]], *, dim: bool = False, position: str = "cover") -> None:
        """Hiện từng `(khung tọa độ logic, chữ)`. dim=True: chữ xám, dùng cho trạng thái chờ / lỗi.

        position "above" / "below": đặt chữ ngay trên / dưới khung thay vì đè lên.
        """
        max_px = self.appearance.max_px
        fitted = []
        for rect, text in items:
            key = (rect.x(), rect.y(), rect.width(), rect.height(), text, position)
            if key not in self._fitted:
                self._fitted[key] = (
                    fit_text(rect, text, max_px)
                    if position == "cover"
                    else fit_beside(rect, text, position, max_px, _screen_bounds(rect))
                )
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

    def show_text(self, rect: QRect, text: str, *, dim: bool = False, position: str = "cover") -> None:
        self.show_items([(rect, text)], dim=dim, position=position)

    def has_text(self) -> bool:
        return bool(self._items)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for fitted, text in self._items:
            paint_block(painter, fitted, text, self.appearance, self._dim)
