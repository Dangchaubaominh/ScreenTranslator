from types import SimpleNamespace

import numpy as np
from PIL import Image

from screen_translator.layout import TextBox
from screen_translator.ocr import MARGIN, OneOcrReader, lines_from_result, pad, upscale_for


def rect(x1, y1, x2, y2):
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y1, "x3": x2, "y3": y2, "x4": x1, "y4": y2}


def read_with_fake_engine(line: TextBox, size=(200, 100)):
    """Đọc ảnh bằng engine giả luôn thấy `line`; trả về các dòng đọc được và cỡ từng ảnh đã gửi cho engine."""
    sent = []

    def recognize_pil(image):
        sent.append(image.size)
        s = (image.width - 2 * MARGIN) / size[0]  # ảnh được phóng to thì chữ cũng to theo
        box = rect(*(MARGIN + v * s for v in (line.left, line.top, line.right, line.bottom)))
        return {"lines": [{"text": line.text, "bounding_rect": box}]}

    reader = OneOcrReader.__new__(OneOcrReader)  # không cần file OneOCR thật
    reader._engine = SimpleNamespace(recognize_pil=recognize_pil)
    return reader.read_lines(Image.new("RGB", size, "white")), sent


def test_small_japanese_text_is_read_again_on_a_bigger_image():
    line = TextBox("火の雨を降らせ", 20, 10, 31, 90)  # cột chữ dọc rộng 11 px: phóng to 2 lần
    lines, sent = read_with_fake_engine(line)
    assert sent == [(232, 132), (432, 232)]
    assert lines == [line]  # tọa độ vẫn tính theo ảnh gốc


def test_text_big_enough_or_not_japanese_is_read_once():
    for line in (
        TextBox("屋敷で迎える", 20, 10, 180, 32),  # đủ cao
        TextBox("屋敷で迎える", 20, 10, 180, 31),  # chỉ thiếu 1 px: phóng to không đáng tốn một lượt đọc
        TextBox("ver 1.00", 20, 10, 80, 20),  # chữ giao diện không cần dịch
        TextBox("蔵", 20, 10, 30, 20),  # một chữ: chưa đủ biết cỡ chữ của ảnh
    ):
        lines, sent = read_with_fake_engine(line)
        assert lines == [line] and len(sent) == 1


def test_upscale_follows_most_lines_and_has_a_limit():
    small, big = TextBox("こんにちは", 0, 0, 200, 11), TextBox("こんにちは", 0, 0, 200, 40)
    assert upscale_for([small, small, big]) == 2
    assert upscale_for([small, big, big]) == 1
    assert upscale_for([TextBox("こんにちは", 0, 0, 200, 3)]) == 3
    assert upscale_for([]) == 1


def test_small_crop_is_padded_with_its_background_color():
    img = Image.new("RGB", (300, 30), (20, 20, 40))
    img.paste((255, 255, 255), (10, 10, 200, 20))  # "chữ" trắng giữa ảnh
    out = pad(img, margin=16, min_size=50)
    assert out.size == (332, 62)
    assert out.getpixel((0, 0)) == (20, 20, 40)
    assert np.array_equal(np.asarray(out.crop((16, 16, 316, 46))), np.asarray(img))


def test_tiny_crop_reaches_the_minimum_size():
    out = pad(Image.new("RGB", (10, 5), "white"), margin=4, min_size=50)
    assert out.size == (50, 50)


def test_lines_are_moved_back_to_original_coordinates_and_clamped():
    result = {
        "lines": [
            {"text": "屋敷で迎える、最初の朝だ。", "bounding_rect": rect(26.4, 20.2, 300.6, 49.9)},
            {"text": "  ", "bounding_rect": rect(0, 0, 10, 10)},  # dòng rỗng bỏ qua
            {"text": "×", "bounding_rect": None},
            {"text": "ログ", "bounding_rect": rect(10, 5, 400, 60)},  # tràn ra viền thêm vào
        ]
    }
    assert lines_from_result(result, 16, (320, 40)) == [
        TextBox("屋敷で迎える、最初の朝だ。", 10, 4, 285, 34),
        TextBox("ログ", 0, 0, 320, 40),
    ]
