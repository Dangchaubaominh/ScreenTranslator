import numpy as np
from PIL import Image, ImageDraw

from screen_translator.preprocess import INK_THRESHOLD, reflow_long_lines, to_black_on_white

CHAR, GAP = 20, 6


def fake_text(lines: list[int], *, fg="black", bg="white") -> Image.Image:
    """Ảnh giả chữ: mỗi dòng là một hàng ô vuông CHAR×CHAR cách nhau GAP (đủ để thử cắt dòng mà không cần font)."""
    width = max(lines) * (CHAR + GAP) + 40
    img = Image.new("RGB", (width, len(lines) * CHAR * 2 + 40), bg)
    draw = ImageDraw.Draw(img)
    for row, count in enumerate(lines):
        y = 20 + row * CHAR * 2
        for i in range(count):
            x = 20 + i * (CHAR + GAP)
            draw.rectangle((x, y, x + CHAR - 1, y + CHAR - 1), fill=fg)
    return img


def ink(img: Image.Image) -> int:
    return int((np.asarray(img.convert("L")) < INK_THRESHOLD).sum())


def test_dark_dialog_is_inverted_to_black_on_white():
    out = to_black_on_white(fake_text([5], fg="white", bg=(20, 20, 40)))
    gray = np.asarray(out.convert("L"))
    assert gray[0, 0] > 200  # nền thành trắng
    assert ink(out) == 5 * CHAR * CHAR


def test_light_image_keeps_its_colors():
    img = fake_text([5])
    assert np.array_equal(np.asarray(to_black_on_white(img)), np.asarray(img))


def test_short_lines_are_left_alone():
    img = fake_text([7, 6])  # dòng dài nhất 7 ô ≈ 176 px, chưa tới ngưỡng 10 × cao dòng
    assert reflow_long_lines(img) is img


def test_blank_image_is_left_alone():
    img = Image.new("RGB", (300, 60), "white")
    assert reflow_long_lines(img) is img


def test_long_line_is_stacked_into_a_squarer_image_without_losing_ink():
    img = fake_text([30])
    out = reflow_long_lines(img)
    assert out.width < img.width / 2
    assert out.height > img.height
    assert ink(out) == ink(img)


def test_cuts_fall_in_the_gaps_between_characters():
    out = reflow_long_lines(fake_text([30, 25]))
    gray = np.asarray(out.convert("L")) < INK_THRESHOLD
    rows = np.flatnonzero(np.diff(np.concatenate(([0], gray.any(axis=1).astype(np.int8), [0]))))
    for top, bottom in zip(rows[::2], rows[1::2], strict=True):
        assert bottom - top == CHAR  # mỗi đoạn vẫn cao đúng một dòng chữ
        columns = gray[top:bottom].any(axis=0)
        widths = np.diff(np.flatnonzero(np.diff(np.concatenate(([0], columns.astype(np.int8), [0])))))[::2]
        assert set(widths.tolist()) == {CHAR}  # không ô nào bị cắt đôi
