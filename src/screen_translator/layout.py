"""Gom các dòng chữ OCR thành khối (câu thoại bị ngắt dòng, đoạn mô tả…) để dịch cả khối một lần."""

import re
from dataclasses import dataclass

# hiragana, katakana, kanji, katakana nửa độ rộng
_JAPANESE = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]")
WRAP_RATIO = 6  # dòng rộng hơn 6 lần chiều cao mới có thể là dòng bị ngắt giữa câu; nhãn ngắn thì không
MAX_GAP = 0.6  # khoảng trống tối đa giữa hai dòng của cùng một khối, tính theo chiều cao dòng


@dataclass(frozen=True)
class TextBox:
    """Một dòng hoặc một khối chữ và khung bao của nó, tính bằng pixel trong ảnh."""

    text: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def has_japanese(text: str) -> bool:
    return bool(_JAPANESE.search(text))


def _join(a: str, b: str) -> str:
    """Tiếng Nhật viết liền khi xuống dòng; chỉ chèn dấu cách giữa hai chữ Latin."""
    latin = a[-1:].isascii() and a[-1:].isalnum() and b[:1].isascii() and b[:1].isalnum()
    return f"{a} {b}" if latin else a + b


def _continues(block: list[TextBox], line: TextBox) -> bool:
    """`line` là phần tiếp theo của khối: ngay bên dưới, cùng lề trái, cùng cỡ chữ, dòng trên đã chạy dài."""
    last = block[-1]
    h = max(last.height, line.height, 1)
    return (
        last.width >= WRAP_RATIO * last.height
        and 0.7 <= line.height / max(last.height, 1) <= 1.4
        and -0.2 * h <= line.top - last.bottom <= MAX_GAP * h
        and abs(line.left - block[0].left) <= h
    )


def group_lines(lines: list[TextBox]) -> list[TextBox]:
    blocks: list[list[TextBox]] = []
    for line in sorted(lines, key=lambda b: (b.top, b.left)):
        target = next((b for b in reversed(blocks) if _continues(b, line)), None)
        if target is None:
            blocks.append([line])
        else:
            target.append(line)
    merged = []
    for block in blocks:
        text = block[0].text
        for line in block[1:]:
            text = _join(text, line.text)
        merged.append(
            TextBox(
                text,
                min(b.left for b in block),
                min(b.top for b in block),
                max(b.right for b in block),
                max(b.bottom for b in block),
            )
        )
    return merged
