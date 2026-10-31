"""Live mode: chụp lại vùng hộp thoại vài lần mỗi giây, câu mới hiện xong thì tự đọc và dịch.

Mỗi lần chụp chỉ so ảnh thu nhỏ (đo được: chụp ~14 ms + so 0,3 ms); OCR (~110 ms) và dịch chỉ chạy khi hình đổi:
- hình đổi rồi đứng yên SETTLE_S → câu đã hiện xong, kể cả kiểu chữ chạy từng ký tự → "settled": đọc và dịch;
- hình quay về đúng một khung vừa thấy (mũi tên "bấm để tiếp" nhấp nháy; chữ đang chạy thì không bao giờ quay lại
  khung cũ) → cũng là "settled", khỏi chờ: mũi tên đổi mỗi 0,5 s thì không lúc nào đứng yên đủ SETTLE_S;
- hình đổi mãi kiểu khác (nền động) → cứ RECHECK_S lại "moving": đọc thử, luồng phụ chỉ dịch khi hai lần đọc
  liền ra cùng một chữ.
Khung hình đã đọc rồi thì không đọc lại.

Live mode cả cửa sổ (trang manga trên web) theo dõi kiểu khác, xem PageWatcher.
"""

import numpy as np
from PIL import Image

POLL_MS = 250
SETTLE_S = 0.4
RECHECK_S = 0.8
SCALE = 4  # thu nhỏ mỗi chiều trước khi so: nhanh, và bỏ qua lệch lẻ tẻ từng pixel
NOISE = 24  # độ sáng (0–255) chênh ít hơn mức này coi như không đổi
MEMORY = 8  # số khung hình đã đọc được nhớ
# trang manga: tỉ lệ điểm ảnh đổi (đo trên trang giả lập: cuộn 20 px đổi 6–14% cả cửa sổ, quảng cáo 300×250 đổi
# màu 3,7%, nút hiện khi rê chuột 0,1%)
BOX_MOVED = 0.1  # chữ dưới một khung bản dịch đổi chừng này: trang đã dời, bản dịch lệch chỗ
PAGE_MOVED = 0.05  # chưa có khung bản dịch nào: cả cửa sổ đổi chừng này mới coi là đã cuộn / lật trang
STILL = 0.02  # hai lần chụp liền nhau đổi ít hơn chừng này: trang đã đứng yên
MAX_WAIT_S = 2.0  # trang không đứng yên hẳn (video quảng cáo…) thì cũng đọc lại sau chừng này


def thumbnail(image: Image.Image) -> np.ndarray:
    gray = image.convert("L")
    if min(gray.size) >= 2 * SCALE:
        gray = gray.reduce(SCALE)
    return np.asarray(gray, dtype=np.int16)


def same(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and not (np.abs(a - b) > NOISE).any()


def _seen(frame: np.ndarray, frames: list[np.ndarray]) -> bool:
    return any(same(frame, f) for f in frames)


def _remember(frames: list[np.ndarray], frame: np.ndarray) -> list[np.ndarray]:
    return [*frames[-(MEMORY - 1) :], frame]


class ChangeWatcher:
    """Nhận ảnh thu nhỏ của vùng theo thời gian, báo khi nào nên đọc chữ."""

    def __init__(self):
        self._frame: np.ndarray | None = None  # khung hình lúc đổi gần nhất
        self._changed_at = self._asked_at = 0.0
        self._done = True  # khung hình hiện tại đã xử lý xong
        # kể từ lần bản dịch đổi gần nhất: khung đã đọc lúc đứng yên (luồng phụ đã dịch / thấy chữ không đổi),
        # và khung đã đọc thử lúc còn đổi (chưa chắc đã dịch: đứng yên rồi vẫn phải đọc lại)
        self._read: list[np.ndarray] = []
        self._glanced: list[np.ndarray] = []
        self._recent: list[np.ndarray] = []  # các khung đã thấy trong đợt thay đổi hiện tại

    def update(self, frame: np.ndarray, now: float) -> str | None:
        """Trả về "settled", "moving", hoặc None khi không cần làm gì."""
        changed = self._frame is None or not same(frame, self._frame)
        blinking = False
        if changed:
            if self._done:  # bắt đầu một đợt thay đổi mới
                self._asked_at, self._recent = now, []
            blinking = _seen(frame, self._recent)
            if self._frame is not None:
                self._recent = _remember(self._recent, self._frame)
            self._frame, self._changed_at, self._done = frame, now, False
        if self._done:
            return None
        settled = blinking or now - self._changed_at >= SETTLE_S
        if _seen(frame, self._read):  # chữ như lúc đã đọc: chờ đứng yên rồi thôi hẳn
            self._done = settled
            return None
        if settled:
            event, self._done = "settled", True
            self._read = _remember(self._read, frame)
        elif changed and now - self._asked_at >= RECHECK_S and not _seen(frame, self._glanced):
            event = "moving"
            self._glanced = _remember(self._glanced, frame)
        else:
            return None
        self._asked_at = now
        return event

    def forget(self) -> None:
        """Bản dịch vừa đổi sang câu mới: quên các khung đã đọc, để câu cũ lặp lại (vd. 「うん」) vẫn được dịch lại."""
        self._read, self._glanced = [], []


def _changed(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Điểm ảnh nào đổi (mảng True / False); khác cỡ (cửa sổ đổi kích thước) thì coi như đổi hết."""
    return np.abs(a - b) > NOISE if a.shape == b.shape else np.ones(a.shape, dtype=bool)


class PageWatcher:
    """Live mode cả cửa sổ: cuộn, lật trang thì báo "moved" để ẩn ngay bản dịch đã lệch chỗ; trang đứng yên lại thì
    "settled": đọc lại cả trang (bóng thoại đã dịch lấy từ cache nên hiện lại ngay).

    Trang đã dời khi chữ dưới các khung bản dịch đang hiện đổi khác, nên quảng cáo động hay nút hiện lên khi rê
    chuột ở chỗ khác không làm bản dịch nhấp nháy. Chưa có khung nào thì xét cả cửa sổ.
    """

    def __init__(self):
        self._anchor: np.ndarray | None = None  # khung hình lúc đọc trang gần nhất
        self._last: np.ndarray | None = None
        self._boxes: list[tuple[int, int, int, int]] = []  # khung bản dịch đang hiện, tính trong ảnh thu nhỏ
        self._moving = True  # vừa bật: đọc trang ngay khi đứng yên
        self._moving_since = self._still_since = 0.0

    def shown(self, boxes: list[tuple[int, int, int, int]]) -> None:
        """Bản dịch vừa hiện ở các khung này (pixel trong ảnh chụp)."""
        self._boxes = [tuple(v // SCALE for v in box) for box in boxes]

    def _moved(self, frame: np.ndarray) -> bool:
        changed = _changed(frame, self._anchor)
        if not self._boxes:
            return changed.mean() > PAGE_MOVED
        regions = (changed[top:bottom, left:right] for left, top, right, bottom in self._boxes)
        return any(region.size and region.mean() > BOX_MOVED for region in regions)

    def update(self, frame: np.ndarray, now: float) -> str | None:
        """Trả về "moved", "settled", hoặc None khi không cần làm gì."""
        last, self._last = self._last, frame
        if last is None:  # lần chụp đầu
            self._moving_since = self._still_since = now
            return None
        event = None
        if not self._moving and self._moved(frame):
            self._moving, self._moving_since, self._still_since = True, now, now
            event = "moved"
        elif self._moving:
            if _changed(frame, last).mean() > STILL:
                self._still_since = now
            if now - self._still_since >= SETTLE_S or now - self._moving_since >= MAX_WAIT_S:
                self._moving, self._anchor, self._boxes = False, frame, []
                event = "settled"
        return event
