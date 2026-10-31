"""Gom các dòng chữ OCR thành khối (câu thoại bị ngắt dòng, đoạn mô tả…) để dịch cả khối một lần.

Chữ ngang (game): các dòng nối tiếp nhau từ trên xuống. Chữ dọc (bóng thoại manga): mỗi cột OneOCR trả về một
dòng; các cột sát nhau là một bóng, đọc từ phải sang trái.
"""

import re
from dataclasses import dataclass

# hiragana, katakana, kanji, katakana nửa độ rộng
_JAPANESE = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]")
WRAP_RATIO = 6  # dòng rộng hơn 6 lần chiều cao mới có thể là dòng bị ngắt giữa câu; nhãn ngắn thì không
MAX_GAP = 0.6  # khoảng trống tối đa giữa hai dòng của cùng một khối, tính theo chiều cao dòng (cột: bề rộng cột)
COLUMN_RATIO = 1.5  # dòng cao hơn 1,5 lần bề rộng là một cột chữ dọc (từ 2 chữ trở lên)


@dataclass(frozen=True)
class TextBox:
    """Một dòng hoặc một khối chữ và khung bao của nó, tính bằng pixel trong ảnh. vertical: khối chữ dọc."""

    text: str
    left: int
    top: int
    right: int
    bottom: int
    vertical: bool = False

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


def _next_column(block: list[TextBox], column: TextBox) -> bool:
    """`column` là cột kế tiếp (bên trái) của bóng thoại: sát cột trước, cùng cỡ chữ, nằm ngang hàng với bóng."""
    last = block[-1]
    w = max(last.width, column.width, 1)
    top, bottom = min(b.top for b in block), max(b.bottom for b in block)
    overlap = min(bottom, column.bottom) - max(top, column.top)
    return (
        0.7 <= column.width / max(last.width, 1) <= 1.4
        and -0.2 * w <= last.left - column.right <= MAX_GAP * w
        and overlap >= 0.5 * min(column.height, bottom - top)  # cột ngắn canh trên hay canh giữa đều được
    )


def _is_column(line: TextBox) -> bool:
    return len(line.text) >= 2 and line.height >= COLUMN_RATIO * line.width


def _merge(block: list[TextBox], vertical: bool) -> TextBox:
    text = block[0].text
    for line in block[1:]:
        text = _join(text, line.text)
    return TextBox(
        text,
        min(b.left for b in block),
        min(b.top for b in block),
        max(b.right for b in block),
        max(b.bottom for b in block),
        vertical,
    )


def group_lines(lines: list[TextBox]) -> list[TextBox]:
    """Khối chữ ngang theo thứ tự từ trên xuống, rồi tới các bóng thoại chữ dọc từ phải sang trái."""
    rows: list[list[TextBox]] = []
    for line in sorted((b for b in lines if not _is_column(b)), key=lambda b: (b.top, b.left)):
        target = next((b for b in reversed(rows) if _continues(b, line)), None)
        if target is None:
            rows.append([line])
        else:
            target.append(line)
    bubbles: list[list[TextBox]] = []
    for column in sorted((b for b in lines if _is_column(b)), key=lambda b: (-b.right, b.top)):
        target = next((b for b in reversed(bubbles) if _next_column(b, column)), None)
        if target is None:
            bubbles.append([column])
        else:
            target.append(column)
    return [_merge(block, False) for block in rows] + [_merge(block, True) for block in bubbles]
