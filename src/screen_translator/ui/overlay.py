"""Overlay vẽ bản dịch đè lên chữ gốc: trong suốt, luôn trên cùng, click xuyên qua, không lọt vào ảnh chụp.

Một overlay vẽ được nhiều khối (dịch cả cửa sổ game: mỗi dòng / đoạn chữ một khối, như Google Lens).
"""

from functools import lru_cache, reduce
from typing import NamedTuple

from PySide6.QtCore import QPoint, QRect, QSize, Qt
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
BUBBLE_WIDTH = 0.8  # khối chữ dọc hẹp và cao: khung bản dịch nới rộng tới chừng này lần chiều cao, nếu còn chỗ trống
MOVED_WIDTH = 200  # bề rộng khung bản dịch khi quanh khối chữ hết chỗ, phải dời đi chỗ khác
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
    return max(2, min(PADDING, rect.height() // 5, rect.width() // 8))  # nhãn menu nhỏ, cột chữ hẹp thì lề nhỏ


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


def _free_span(low: int, high: int, limit_low: int, limit_high: int, others: list[tuple[int, int]]) -> tuple[int, int]:
    """Nới đoạn [low, high] ra hai phía, tới sát các đoạn `others` (chừa BLOCK_GAP) hoặc tới giới hạn."""
    for other_low, other_high in others:
        if other_low > high:
            limit_high = min(limit_high, other_low - BLOCK_GAP - 1)
        elif other_high < low:
            limit_low = max(limit_low, other_high + BLOCK_GAP + 1)
    return min(limit_low, low), max(limit_high, high)


def _free_row(rect: QRect, bounds: QRect, obstacles: list[QRect]) -> QRect:
    """Nới `rect` sang hai bên vào chỗ trống, không đổi chiều cao."""
    same_row = [(o.left(), o.right()) for o in obstacles if o.top() <= rect.bottom() and o.bottom() >= rect.top()]
    left, right = _free_span(rect.left(), rect.right(), bounds.left(), bounds.right(), same_row)
    return QRect(QPoint(left, rect.top()), QPoint(right, rect.bottom()))


def _free_column(rect: QRect, bounds: QRect, obstacles: list[QRect]) -> QRect:
    """Nới `rect` lên trên và xuống dưới vào chỗ trống, không đổi bề ngang."""
    same_column = [(o.top(), o.bottom()) for o in obstacles if o.left() <= rect.right() and o.right() >= rect.left()]
    top, bottom = _free_span(rect.top(), rect.bottom(), bounds.top(), bounds.bottom(), same_column)
    return QRect(QPoint(rect.left(), top), QPoint(rect.right(), bottom))


def _free_spot(rect: QRect, width: int, height: int, bounds: QRect, obstacles: list[QRect]) -> QRect | None:
    """Chỗ trống gần `rect` nhất đặt vừa khung cỡ (width, height), nếu có. Chỉ cần xét các chỗ sát mép hay sát khối khác."""
    xs, ys = {bounds.left(), bounds.right() + 1 - width}, {bounds.top(), bounds.bottom() + 1 - height}
    for other in obstacles:
        xs |= {other.left() - BLOCK_GAP - width, other.right() + BLOCK_GAP + 1}
        ys |= {other.top() - BLOCK_GAP - height, other.bottom() + BLOCK_GAP + 1}
    spots = (QRect(x, y, width, height) for x in xs for y in ys)
    free = [s for s in spots if bounds.contains(s) and not any(s.intersects(other) for other in obstacles)]
    return min(free, key=lambda s: (s.center() - rect.center()).manhattanLength(), default=None)


def _fit_block(rect: QRect, text: str, max_px: int, bounds: QRect, obstacles: list[QRect]) -> Fitted:
    row = _free_row(rect, bounds, obstacles)
    # cột chữ dọc hẹp và cao, bản dịch chữ ngang cần khung rộng hơn: nới đều hai bên, sát khối khác thì lệch đi
    wanted = round(rect.height() * BUBBLE_WIDTH)
    width = min(row.width(), max(rect.width(), wanted))
    box = clamp(QRect(rect.x() - (width - rect.width()) // 2, rect.y(), width, rect.height()), row)
    # khung OCR ôm sát chữ (nhãn menu chỉ cao ~18 px): gần như không chừa lề trên / dưới, không thì chữ cỡ
    # MIN_PX không bao giờ vừa một dòng
    padding = _padding(box)
    vpadding = min(padding, box.height() // 12)
    if found := _largest_fit(box, text, max_px, MIN_PX, padding, vpadding):
        return Fitted(_font(found[0]), box, padding, vpadding)
    # nới khung thì chữ không to hơn cỡ vừa một dòng chữ gốc, để khung chỉ to vừa đủ; không biết cỡ chữ của cột
    # chữ dọc nên dùng cỡ nhỏ nhất
    natural = MIN_PX if rect.width() < wanted else int((box.height() - 2 * vpadding) / LINE_HEIGHT)
    natural = max(MIN_PX, min(max_px, natural))
    rightwards = QRect(box.topLeft(), row.bottomRight())
    downwards = _free_column(rightwards, bounds, obstacles)
    downwards.setTop(box.top())
    around = _free_column(row, bounds, obstacles)
    for room, min_px in ((rightwards, MIN_PX), (downwards, MIN_PX), (around, MIN_PX), (around, TINY_PX)):
        if found := _largest_fit(room, text, natural, min_px, padding, vpadding):
            px, w, h = found
            # +2: chữ vẽ lại trong khung đúng bề rộng đo được không bị xuống dòng thêm vì làm tròn
            size = QSize(min(room.width(), max(box.width(), w + 2)), max(box.height(), h))
            return Fitted(_font(px), clamp(QRect(box.topLeft(), size), room), padding, vpadding)
    # quanh khối hết chỗ: dời bản dịch tới chỗ trống gần nhất; cả trang kín chỗ thì đành cắt bớt chữ, không đè khối khác
    w, h = _measure(MIN_PX, max(box.width(), MOVED_WIDTH) - 2 * padding, text)
    if spot := _free_spot(box, w + 2 * padding + 2, h + 2 * vpadding, bounds, obstacles):
        return Fitted(_font(MIN_PX), spot, padding, vpadding)
    return Fitted(_font(TINY_PX), around, padding, vpadding)


def _separate(rects: list[QRect]) -> list[QRect]:
    """Chia đôi phần chung nếu khung của hai khối chữ đè lên nhau (cột chữ hơi nghiêng), theo chiều phần chung hẹp."""
    rects = [QRect(rect) for rect in rects]
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            if not a.intersects(b):
                continue
            common = a.intersected(b)
            if common.width() <= common.height():
                first, second = (a, b) if a.center().x() <= b.center().x() else (b, a)
                first.setRight(common.center().x() - 1)
                second.setLeft(common.center().x() + 1)
            else:
                first, second = (a, b) if a.center().y() <= b.center().y() else (b, a)
                first.setBottom(common.center().y() - 1)
                second.setTop(common.center().y() + 1)
    return rects


def fit_blocks(blocks: list[tuple[QRect, str | None]], max_px: int, bounds: QRect) -> list[Fitted | None]:
    """Khung bản dịch cho từng khối chữ của cả cửa sổ, không khung nào đè lên khung khác.

    Cột chữ dọc được nới ngang. Bản dịch dài hơn chữ gốc thì thu nhỏ chữ, rồi nới khung sang phải, xuống dưới, rồi ra
    cả bốn phía, nhưng chỉ vào chỗ trống: không lấn lên chữ gốc của khối khác hay khung đã đặt. Khối chữ None (còn
    đang dịch) không vẽ nhưng vẫn giữ chỗ chữ gốc của nó, để khung đã hiện không phải dời đi khi khối đó dịch xong.
    """
    rects = _separate([rect for rect, _ in blocks])
    fitted: list[Fitted | None] = [None] * len(blocks)
    placed: list[QRect] = []
    waiting = set(range(len(blocks)))
    for i in sorted(waiting, key=lambda i: (rects[i].top(), rects[i].left())):  # thứ tự đọc
        text = blocks[i][1]
        if text is None:
            continue
        waiting.remove(i)
        fitted[i] = _fit_block(rects[i], text, max_px, bounds, placed + [rects[j] for j in waiting])
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
