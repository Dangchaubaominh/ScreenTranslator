"""Overlay vẽ bản dịch đè lên chữ gốc: trong suốt, luôn trên cùng, click xuyên qua, không lọt vào ảnh chụp.

Một overlay vẽ được nhiều khối (dịch cả cửa sổ game: mỗi dòng / đoạn chữ một khối, như Google Lens).
"""

from functools import lru_cache, reduce
from typing import NamedTuple

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from .. import win32
from ..config import Config

PADDING = 10
MIN_PX, MAX_PX = 12, 34
TINY_PX = 10  # dịch cả cửa sổ: cỡ chữ nhỏ nhất khi đã hết chỗ trống để nới khung
LINE_HEIGHT = 1.35  # chiều cao một dòng chữ Segoe UI / cỡ chữ
HINT_PX, HINT_WIDTH = 15, 480  # thông báo ngắn tự tắt
GAP = 6  # khoảng hở giữa vùng đang dịch và thông báo ngắn đặt ngay trên nó
BLOCK_GAP = 2  # khoảng hở giữa các khung bản dịch khi dịch cả cửa sổ
FONT_FAMILY = "Segoe UI"
TEXT_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
BACKGROUND = QColor(12, 16, 28)  # nền đặc: chữ Nhật gốc không lộ ra sau bản dịch
TEXT_COLOR, DIM_TEXT_COLOR = QColor(245, 245, 245), QColor(160, 168, 184)
DARK_TEXT_COLOR, DARK_DIM_TEXT_COLOR = QColor(20, 22, 28), QColor(96, 102, 116)  # trên nền sáng
OUTLINE_BELOW = 0.5  # nền trong hơn mức này thì viền quanh chữ cho dễ đọc trên hình game
OUTLINE_OFFSETS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


class Fitted(NamedTuple):
    font: QFont
    rect: QRect
    padding: int  # lề trái / phải
    vpadding: int  # lề trên / dưới


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

    def outline_color(self) -> QColor | None:
        """Màu viền chữ khi nền gần như trong suốt; nền đủ đặc thì không cần viền."""
        if self.background.alphaF() >= OUTLINE_BELOW:
            return None
        return QColor(0, 0, 0, 200) if self.text_color().lightnessF() > 0.5 else QColor(255, 255, 255, 200)


def _font(px: int) -> QFont:
    font = QFont(FONT_FAMILY)
    font.setPixelSize(px)
    return font


@lru_cache(maxsize=16384)
def _measure(px: int, width: int, text: str) -> tuple[int, int]:
    """(rộng, cao) của `text` cỡ `px`, tự xuống dòng trong bề rộng `width`."""
    needed = QFontMetrics(_font(px)).boundingRect(QRect(0, 0, max(1, width), 1_000_000), TEXT_FLAGS, text)
    return needed.width(), needed.height()


def _padding(rect: QRect) -> int:
    return max(2, min(PADDING, rect.height() // 5))  # nhãn menu nhỏ thì lề nhỏ


def _largest_fit(
    room: QRect, text: str, max_px: int, min_px: int, padding: int, vpadding: int
) -> tuple[int, int, int] | None:
    """Cỡ chữ lớn nhất trong [min_px, max_px] để `text` vừa `room`: (cỡ, rộng, cao) kể cả lề; không vừa thì None."""
    inner_w, inner_h = room.width() - 2 * padding, room.height() - 2 * vpadding

    def fits(px: int) -> bool:
        w, h = _measure(px, inner_w, text)
        return w <= inner_w and h <= inner_h

    if inner_w <= 0 or max_px < min_px or not fits(min_px):
        return None
    low, high = min_px, max_px  # chữ càng to càng chiếm chỗ: tìm nhị phân
    while low < high:
        middle = (low + high + 1) // 2
        if fits(middle):
            low = middle
        else:
            high = middle - 1
    w, h = _measure(low, inner_w, text)
    return low, w + 2 * padding, h + 2 * vpadding


def fit_text(rect: QRect, text: str, max_px: int = MAX_PX) -> Fitted:
    """Cỡ chữ lớn nhất (max_px → MIN_PX) để `text` vừa trong `rect`.

    Nhỏ nhất rồi vẫn không vừa thì nới khung sang phải / xuống dưới cho đủ chỗ.
    """
    padding = _padding(rect)
    if found := _largest_fit(rect, text, max_px, MIN_PX, padding, padding):
        return Fitted(_font(found[0]), rect, padding, padding)
    w, h = _measure(MIN_PX, rect.width() - 2 * padding, text)
    grown = QRect(rect.x(), rect.y(), max(rect.width(), w + 2 * padding), max(rect.height(), h + 2 * padding))
    return Fitted(_font(MIN_PX), grown, padding, padding)


def _free_room(rect: QRect, bounds: QRect, obstacles: list[QRect]) -> tuple[QRect, QRect]:
    """Chỗ trống quanh `rect` không chạm `obstacles`: (nới sang phải, nới sang phải rồi xuống dưới)."""
    right = bounds.right() + 1
    for other in obstacles:  # khối cùng hàng, bên phải
        if other.left() > rect.right() and other.top() <= rect.bottom() and other.bottom() >= rect.top():
            right = min(right, other.left() - BLOCK_GAP)
    right = max(right, rect.right() + 1)
    bottom = bounds.bottom() + 1
    for other in obstacles:  # khối bên dưới, chồng lên khoảng ngang vừa nới
        if other.top() > rect.bottom() and other.left() < right and other.right() >= rect.left():
            bottom = min(bottom, other.top() - BLOCK_GAP)
    bottom = max(bottom, rect.bottom() + 1)
    return (
        QRect(rect.x(), rect.y(), right - rect.x(), rect.height()),
        QRect(rect.x(), rect.y(), right - rect.x(), bottom - rect.y()),
    )


def _fit_block(rect: QRect, text: str, max_px: int, bounds: QRect, obstacles: list[QRect]) -> Fitted:
    # khung OCR ôm sát chữ (nhãn menu chỉ cao ~18 px): gần như không chừa lề trên / dưới, không thì chữ cỡ
    # MIN_PX không bao giờ vừa một dòng
    padding = _padding(rect)
    vpadding = min(padding, rect.height() // 12)
    if found := _largest_fit(rect, text, max_px, MIN_PX, padding, vpadding):
        return Fitted(_font(found[0]), rect, padding, vpadding)
    # nới khung thì chữ không to hơn cỡ vừa một dòng chữ gốc, để khung chỉ to vừa đủ
    natural = max(MIN_PX, min(max_px, int((rect.height() - 2 * vpadding) / LINE_HEIGHT)))
    wide, tall = _free_room(rect, bounds, obstacles)
    for room, min_px in ((wide, MIN_PX), (tall, MIN_PX), (tall, TINY_PX)):
        if found := _largest_fit(room, text, natural, min_px, padding, vpadding):
            px, w, h = found
            # +2: chữ vẽ lại trong khung đúng bề rộng đo được không bị xuống dòng thêm vì làm tròn
            box = QRect(rect.x(), rect.y(), min(room.width(), max(rect.width(), w + 2)), max(rect.height(), h))
            return Fitted(_font(px), box, padding, vpadding)
    return fit_text(rect, text, max_px)  # hết chỗ trống: đành nới đè lên khối bên cạnh


def fit_blocks(blocks: list[tuple[QRect, str | None]], max_px: int, bounds: QRect) -> list[Fitted | None]:
    """Khung bản dịch cho từng khối chữ của cả cửa sổ, không khung nào đè lên khung khác.

    Bản dịch dài hơn chữ gốc thì thu nhỏ chữ, rồi nới khung sang phải, rồi xuống dưới, nhưng chỉ vào chỗ trống:
    không lấn lên chữ gốc của khối khác hay khung đã đặt. Khối chữ None (còn đang dịch) không vẽ nhưng vẫn
    giữ chỗ chữ gốc của nó, để khung đã hiện không phải dời đi khi khối đó dịch xong.
    """
    fitted: list[Fitted | None] = [None] * len(blocks)
    placed: list[QRect] = []
    for i in sorted(range(len(blocks)), key=lambda i: (blocks[i][0].top(), blocks[i][0].left())):  # thứ tự đọc
        rect, text = blocks[i]
        if text is None:
            continue
        obstacles = placed + [other for j, (other, _) in enumerate(blocks) if j != i]
        fitted[i] = _fit_block(rect, text, max_px, bounds, obstacles)
        placed.append(fitted[i].rect)
    return fitted


def clamp(rect: QRect, bounds: QRect) -> QRect:
    """Dời `rect` vào trong `bounds` (vd. màn hình), giữ nguyên kích thước."""
    x = max(bounds.left(), min(rect.x(), bounds.right() + 1 - rect.width()))
    y = max(bounds.top(), min(rect.y(), bounds.bottom() + 1 - rect.height()))
    return QRect(x, y, rect.width(), rect.height())


def hint_size(text: str) -> QSize:
    """Khung vừa khít một thông báo ngắn chữ cỡ HINT_PX, rộng tối đa HINT_WIDTH."""
    w, h = _measure(HINT_PX, HINT_WIDTH - 2 * PADDING, text)
    return QSize(w + 2 * PADDING + 2, h + 2 * PADDING)


def paint_block(painter: QPainter, fitted: Fitted, text: str, appearance: Appearance, dim: bool = False) -> None:
    rect, padding, vpadding = fitted.rect, fitted.padding, fitted.vpadding
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(appearance.background)
    radius = min(8, rect.height() // 4)
    painter.drawRoundedRect(rect, radius, radius)
    painter.setFont(fitted.font)
    inner = rect.adjusted(padding, vpadding, -padding, -vpadding)
    if outline := appearance.outline_color():
        painter.setPen(outline)
        for dx, dy in OUTLINE_OFFSETS:
            painter.drawText(inner.translated(dx, dy), TEXT_FLAGS, text)
    painter.setPen(appearance.text_color(dim))
    painter.drawText(inner, TEXT_FLAGS, text)


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
        self._dim = False
        # Nếu Windows quá cũ không hỗ trợ, app phải ẩn overlay trước mỗi lần chụp lại vùng
        self.excluded_from_capture = win32.exclude_from_capture(int(self.winId()))

    def show_items(
        self, items: list[tuple[QRect, str | None]], *, dim: bool = False, bounds: QRect | None = None
    ) -> None:
        """Hiện từng `(khung tọa độ logic, chữ)` đè lên khung đó. dim=True: chữ xám, dùng cho trạng thái chờ / lỗi.

        bounds: mỗi khối chữ của cả cửa sổ một khung, không khung nào đè lên khung khác, không ra ngoài `bounds`
        (chữ None: khối còn đang dịch, chỉ giữ chỗ).
        """
        max_px = self.appearance.max_px
        if bounds is not None:
            fitted = [(f, text) for f, (_, text) in zip(fit_blocks(items, max_px, bounds), items, strict=True) if f]
        else:
            fitted = [(fit_text(rect, text, max_px), text) for rect, text in items if text is not None]
        self._dim = dim
        if not fitted:
            self._items = []
            self.hide()
            return
        area = reduce(QRect.united, (f.rect for f, _ in fitted))
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
            paint_block(painter, fitted, text, self.appearance, self._dim)
