import itertools

import numpy as np
from PIL import Image

from screen_translator.live import MAX_WAIT_S, RECHECK_S, SETTLE_S, ChangeWatcher, PageWatcher, thumbnail

BOX = np.zeros((50, 300), dtype=np.int16)  # hộp thoại 1200×200 thu nhỏ 4 lần


def frame(text: int = 0, arrow: bool = False) -> np.ndarray:
    """Hộp thoại giả: `text` ký tự trắng chạy từ trái sang, mũi tên "bấm để tiếp" ở góc phải dưới."""
    f = BOX.copy()
    f[10:20, 10 : 10 + 10 * text] = 255
    if arrow:
        f[40:46, 290:296] = 255
    return f


def play(watcher: ChangeWatcher, frames: list[np.ndarray], step: float = 0.25, start: float = 100.0):
    """Đưa lần lượt từng khung, mỗi khung cách nhau `step` giây; trả về (thời điểm, sự kiện) khác None."""
    events = []
    for i, f in enumerate(frames):
        now = start + i * step
        if (event := watcher.update(f, now)) is not None:
            events.append((round(now - start, 2), event))
    return events


def test_thumbnail_is_small_gray():
    assert thumbnail(Image.new("RGB", (1200, 200), "white")).shape == (50, 300)
    assert thumbnail(Image.new("RGB", (6, 6))).shape == (6, 6)  # ảnh quá nhỏ: không thu nhỏ


def test_typewriter_line_is_read_after_it_stops():
    watcher = ChangeWatcher()
    events = play(watcher, [frame(n) for n in range(1, 9)] + [frame(8)] * 6)
    # chữ chạy 2 s: đọc thử một lần giữa chừng; ký tự cuối hiện lúc 1,75 s, đứng yên tới 2,25 s thì đọc, sau đó im
    assert events == [(1.0, "moving"), (2.25, "settled")]


def test_final_frame_glanced_while_typing_is_still_read_when_it_settles():
    watcher = ChangeWatcher()
    # khung cuối (đủ câu) rơi đúng lúc đọc thử: luồng phụ chưa dịch nó, đứng yên rồi phải đọc lại
    events = play(watcher, [frame(n) for n in range(1, 6)] + [frame(5)] * 4)
    assert events == [(1.0, "moving"), (1.5, "settled")]


def test_static_frame_is_read_once_then_nothing():
    watcher = ChangeWatcher()
    assert play(watcher, [frame(3)] * 10) == [(0.5, "settled")]


def test_blinking_arrow_is_read_once_when_it_comes_back():
    watcher = ChangeWatcher()
    blink = [frame(5, arrow=bool(i // 2 % 2)) for i in range(24)]  # mũi tên đổi trạng thái mỗi 0,5 s
    # chụp 4 lần/giây thì không lúc nào thấy đứng yên đủ 0,4 s; hình quay về khung cũ lúc 1 s: đọc, rồi thôi hẳn
    assert play(watcher, blink) == [(1.0, "settled")]


def test_line_followed_by_blinking_arrow_is_read_soon_after_it_ends():
    watcher = ChangeWatcher()
    typing = [frame(n) for n in range(1, 9)]  # ký tự cuối lúc 1,75 s
    blink = [frame(8, arrow=not i // 2 % 2) for i in range(12)]  # mũi tên hiện ngay sau đó, đổi mỗi 0,5 s
    # mũi tên ẩn đi lúc 2,5 s, hình quay về khung đủ câu: đọc luôn, không chờ hai lần đọc thử giống nhau
    assert play(watcher, typing + blink) == [(1.0, "moving"), (2.0, "moving"), (2.5, "settled")]


def test_a_line_repeated_later_is_read_again():
    watcher = ChangeWatcher()
    assert play(watcher, [frame(3)] * 3) == [(0.5, "settled")]
    watcher.forget()  # bản dịch câu này đã hiện
    assert play(watcher, [frame(6)] * 3, start=101) == [(0.5, "settled")]
    watcher.forget()
    assert play(watcher, [frame(3)] * 3, start=102) == [(0.5, "settled")]  # 「うん」 lặp lại vẫn được dịch


def test_endless_animation_is_read_every_recheck_interval():
    watcher = ChangeWatcher()
    rng = np.random.default_rng(0)
    noisy = [frame(5) + rng.integers(0, 2, BOX.shape, dtype=np.int16) * 100 for _ in range(16)]  # nền động
    events = play(watcher, noisy)
    times = [t for t, e in events]
    assert all(e == "moving" for _, e in events) and len(events) >= 3
    assert all(b - a >= RECHECK_S for a, b in itertools.pairwise(times))


def test_settle_time_is_measured_from_the_last_change():
    watcher = ChangeWatcher()
    assert watcher.update(frame(1), 0.0) is None
    assert watcher.update(frame(2), SETTLE_S - 0.1) is None
    assert watcher.update(frame(2), SETTLE_S + 0.05) is None  # mới đứng yên 0,15 s
    assert watcher.update(frame(2), 2 * SETTLE_S) == "settled"


# --- live mode cả cửa sổ: trang manga trên web ---

TEXTURE = np.random.default_rng(0).integers(0, 2, (500, 300), dtype=np.int16) * 255  # nét vẽ, chữ của trang
BUBBLE = (400, 200, 480, 440)  # khung bản dịch đang hiện (pixel ảnh chụp) = (100, 50, 120, 110) khi thu nhỏ


def page(scroll: int = 0, ad: int = 0) -> np.ndarray:
    """Cửa sổ trình duyệt 1920×1080 thu nhỏ: trang manga cuộn `scroll` px (ảnh thu nhỏ), quảng cáo bên phải."""
    f = np.zeros((270, 480), dtype=np.int16)
    f[30:250, 50:350] = TEXTURE[scroll : scroll + 220]
    f[20:80, 400:470] = ad  # quảng cáo 280×240 px, 3,2% cửa sổ
    return f


def test_page_is_read_once_it_stands_still():
    assert play(PageWatcher(), [page()] * 8) == [(0.5, "settled")]


def test_scrolling_hides_the_translation_at_once_and_reads_the_page_again_when_it_stops():
    watcher = PageWatcher()
    assert play(watcher, [page()] * 3) == [(0.5, "settled")]
    watcher.shown([BUBBLE])
    scrolling = [page(5), page(10), page(15)] + [page(15)] * 3
    assert play(watcher, scrolling) == [(0.0, "moved"), (1.0, "settled")]


def test_animated_ad_elsewhere_does_not_disturb_the_translation():
    watcher = PageWatcher()
    play(watcher, [page()] * 3)
    watcher.shown([BUBBLE])
    assert play(watcher, [page(ad=255 * (i % 2)) for i in range(12)]) == []
    # chưa có bản dịch nào (trang không có chữ): quảng cáo cũng không làm đọc lại; cuộn trang thì có
    watcher = PageWatcher()
    play(watcher, [page()] * 3)
    assert play(watcher, [page(ad=255 * (i % 2)) for i in range(4)] + [page(5)]) == [(1.0, "moved")]


def test_page_that_never_stands_still_is_read_after_a_while():
    watcher = PageWatcher()
    play(watcher, [page()] * 3)
    watcher.shown([BUBBLE])
    video = [page(5, ad=255 * (i % 2)) for i in range(12)]  # cuộn xong nhưng video quảng cáo chạy mãi
    assert play(watcher, video) == [(0.0, "moved"), (MAX_WAIT_S, "settled")]


def test_resized_window_counts_as_moved():
    watcher = PageWatcher()
    play(watcher, [page()] * 3)
    watcher.shown([BUBBLE])
    assert watcher.update(page()[:200], 200.0) == "moved"
