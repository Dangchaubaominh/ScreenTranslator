"""Tiền xử lý ảnh trước khi đưa vào manga-ocr."""

import numpy as np
from PIL import Image, ImageOps

INK_THRESHOLD = 128
LINE_PITCH = 1.25  # khoảng cách giữa các dòng khi xếp chồng, tính theo chiều cao dòng
# Đoạn hẹp hơn ~10 chữ thì manga-ocr dễ tưởng các đoạn xếp chồng là chữ dọc và đọc lộn thứ tự
MIN_PIECE_CHARS = 10


def to_black_on_white(img: Image.Image) -> Image.Image:
    """manga-ocr học trên manga (chữ đen nền trắng); hộp thoại game thường là chữ sáng trên nền tối."""
    gray = ImageOps.grayscale(img)
    if np.asarray(gray).mean() < INK_THRESHOLD:
        gray = ImageOps.invert(gray)
    return gray.convert("RGB")


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Các đoạn liên tiếp mang giá trị True, dạng [(đầu, cuối), ...]."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], mask.astype(np.int8), [0]))))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist(), strict=True))


def reflow_long_lines(img: Image.Image) -> Image.Image:
    """Cắt các dòng chữ ngang dài thành đoạn ngắn tại khe trống giữa chữ rồi xếp chồng cho ảnh gần vuông.

    manga-ocr bóp mọi ảnh về 224×224, nên một dòng 25 chữ bị ép dẹt, mỗi chữ chỉ còn vài pixel.
    Ảnh vào phải là chữ đen nền trắng (xem to_black_on_white).
    """
    ink = np.asarray(img.convert("L")) < INK_THRESHOLD
    lines = []  # (top, bottom, left, right, mực theo cột)
    for top, bottom in _runs(ink.any(axis=1)):
        column_ink = ink[top:bottom].sum(axis=0)
        cols = np.flatnonzero(column_ink)
        lines.append((top, bottom, int(cols[0]), int(cols[-1]) + 1, column_ink))
    if not lines:
        return img

    line_h = max(bottom - top for top, bottom, *_ in lines)
    total_len = sum(right - left for _, _, left, right, _ in lines)
    # Rộng mỗi đoạn W sao cho (total_len / W) đoạn xếp chồng cao xấp xỉ W
    piece_w = max(line_h * MIN_PIECE_CHARS, int(np.sqrt(total_len * line_h * LINE_PITCH)))
    if all(right - left <= piece_w for _, _, left, right, _ in lines):
        return img  # không dòng nào đủ dài để bị bóp dẹt

    pieces = []
    for top, bottom, left, right, column_ink in lines:
        start = left
        while right - start > piece_w:
            # cắt ở cột ít mực nhất trong 30% cuối của đoạn, để không cắt ngang một chữ
            lo = start + int(piece_w * 0.7)
            cut = lo + int(column_ink[lo : start + piece_w].argmin())
            pieces.append(img.crop((start, top, cut, bottom)))
            start = cut
        pieces.append(img.crop((start, top, right, bottom)))

    pad = line_h // 4
    out = Image.new(
        "RGB",
        (max(p.width for p in pieces) + 2 * pad, sum(p.height + pad for p in pieces) + pad),
        "white",
    )
    y = pad
    for p in pieces:
        out.paste(p, (pad, y))
        y += p.height + pad
    return out
