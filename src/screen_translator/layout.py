"""Gom các dòng chữ OCR thành khối (câu thoại bị ngắt dòng, đoạn mô tả…) để dịch cả khối một lần.

Chữ ngang (game): các dòng nối tiếp nhau từ trên xuống. Chữ dọc (bóng thoại manga): mỗi cột OneOCR trả về một
dòng; các cột sát nhau là một bóng, đọc từ phải sang trái. Truyện Trung, Hàn thì bóng thoại là chữ ngang canh giữa.
"""

import re
from dataclasses import dataclass
from functools import reduce

_HANGUL = "가-힣ㄱ-ㆎ"  # âm tiết và chữ cái rời (ㅋㅋ, ㅠㅠ)
# hiragana, katakana, chữ Hán, katakana nửa độ rộng, chữ Hàn
_CJK = re.compile(rf"[぀-ヿ㐀-鿿ｦ-ﾟ{_HANGUL}]")
_KOREAN = re.compile(rf"[{_HANGUL}]")
WRAP_RATIO = 6  # dòng rộng hơn 6 lần chiều cao mới có thể là dòng bị ngắt giữa câu; nhãn ngắn thì không
MAX_GAP = 0.6  # khoảng trống tối đa giữa hai dòng của cùng một khối, tính theo chiều cao dòng (cột: bề rộng cột)
COLUMN_RATIO = 1.5  # dòng cao hơn 1,5 lần bề rộng là một cột chữ dọc (từ 2 chữ trở lên)
SIMILAR_PER = 10  # hai lần đọc cùng một câu được lệch 1 ký tự trên mỗi 10 ký tự (OCR đọc nhầm, chưa phải câu mới)


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


def has_cjk(text: str) -> bool:
    """Có chữ Nhật, Trung hoặc Hàn. Không phân biệt được: chuỗi ngắn như 設定 viết giống nhau ở cả tiếng Nhật và Trung."""
    return bool(_CJK.search(text))


def similar(a: str, b: str) -> bool:
    """Cùng một câu, chỉ lệch vì OCR (đọc っ thành つ, sót một dấu…): mỗi 10 ký tự được lệch 1 ký tự.

    Câu dưới 10 ký tự phải khớp hẳn: 「うん」 với 「ううん」 là hai câu khác nhau.
    """
    allowed = max(len(a), len(b)) // SIMILAR_PER
    if abs(len(a) - len(b)) > allowed:
        return False
    # khoảng cách Levenshtein (số ký tự phải thêm / bớt / thay), dừng sớm khi đã lệch quá mức cho phép
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        diagonal, row[0] = row[0], i
        for j, cb in enumerate(b, start=1):
            diagonal, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, diagonal + (ca != cb))
        if min(row) > allowed:
            return False
    return row[-1] <= allowed


def _join(a: str, b: str) -> str:
    """Tiếng Nhật, Trung viết liền khi xuống dòng; chỉ chèn dấu cách giữa hai chữ Latin và cạnh chữ Hàn."""
    latin = a[-1:].isascii() and a[-1:].isalnum() and b[:1].isascii() and b[:1].isalnum()
    return f"{a} {b}" if latin or _KOREAN.match(a[-1:]) or _KOREAN.match(b[:1]) else a + b


def _below(last: TextBox, line: TextBox) -> bool:
    """`line` ở ngay bên dưới `last` và cùng cỡ chữ."""
    h = max(last.height, line.height, 1)
    return 0.7 <= line.height / max(last.height, 1) <= 1.4 and -0.2 * h <= line.top - last.bottom <= MAX_GAP * h


def _continues(block: list[TextBox], line: TextBox) -> bool:
    """`line` là phần tiếp theo của khối: ngay bên dưới, cùng lề trái, cùng cỡ chữ, dòng trên đã chạy dài."""
    last = block[-1]
    return (
        _below(last, line)
        and last.width >= WRAP_RATIO * last.height
        and abs(line.left - block[0].left) <= max(last.height, line.height, 1)
    )


def _same_bubble(block: list[TextBox], line: TextBox) -> bool:
    """Bóng thoại chữ ngang: dòng có thể rất ngắn và lệch lề vì canh giữa, chỉ cần sát nhau và chồng theo chiều ngang."""
    last = block[-1]
    overlap = min(last.right, line.right) - max(last.left, line.left)
    return _below(last, line) and overlap >= 0.5 * min(last.width, line.width)


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


def _merge(block: list[TextBox]) -> TextBox:
    return TextBox(
        reduce(_join, (b.text for b in block)),
        min(b.left for b in block),
        min(b.top for b in block),
        max(b.right for b in block),
        max(b.bottom for b in block),
    )


def _group(lines: list[TextBox], belongs) -> list[list[TextBox]]:
    """Mỗi dòng nối vào khối gần nhất nhận nó (`belongs`); không khối nào nhận thì mở khối mới."""
    blocks: list[list[TextBox]] = []
    for line in lines:
        if target := next((b for b in reversed(blocks) if belongs(b, line)), None):
            target.append(line)
        else:
            blocks.append([line])
    return blocks


def group_lines(lines: list[TextBox], language: str = "ja") -> list[TextBox]:
    """Khối chữ ngang theo thứ tự từ trên xuống, rồi tới các bóng thoại chữ dọc từ phải sang trái.

    Tiếng Nhật giữ riêng các dòng ngắn (nhãn menu); tiếng Trung, Hàn gom lại vì đó thường là một bóng thoại chữ ngang.
    """
    rows = sorted((b for b in lines if not _is_column(b)), key=lambda b: (b.top, b.left))
    columns = sorted((b for b in lines if _is_column(b)), key=lambda b: (-b.right, b.top))
    belongs = _continues if language == "ja" else _same_bubble
    return [_merge(block) for block in _group(rows, belongs) + _group(columns, _next_column)]
