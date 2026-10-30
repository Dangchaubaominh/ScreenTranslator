import numpy as np
from PIL import Image

from screen_translator.layout import TextBox
from screen_translator.ocr import lines_from_result, pad


def rect(x1, y1, x2, y2):
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y1, "x3": x2, "y3": y2, "x4": x1, "y4": y2}


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
