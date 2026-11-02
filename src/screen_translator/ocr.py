"""Đọc chữ Nhật, Trung, Hàn trong ảnh bằng OneOCR, trả về từng dòng kèm vị trí.

OneOCR là engine OCR có sẵn trong Snipping Tool của Windows 11. Chạy CPU, đọc cả màn hình ~0,2–0,5 s, đúng cả logo
cách điệu và chữ xám mờ trên ảnh game thật. Là thành phần nội bộ của Microsoft: chỉ chép file một lần, Snipping Tool
đời sau có thể đổi file làm thư viện oneocr không đọc được; khi đó app báo lỗi.

Chữ nhỏ (trang manga thu nhỏ trên web) đọc sai nhiều hơn, nên phóng to ảnh rồi đọc lại. Chỉ làm khi chữ nhỏ:
phóng to chữ đã đủ to thì đọc kém đi.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from statistics import median

import numpy as np
from PIL import Image, ImageOps

from .layout import TextBox, has_cjk

log = logging.getLogger(__name__)

ONEOCR_DIR = Path.home() / ".config" / "oneocr"  # thư viện oneocr đọc file ở đây
ONEOCR_FILES = ("oneocr.dll", "oneocr.onemodel", "onnxruntime.dll")
ONEOCR_MIN_SIZE = 50  # OneOCR bỏ qua ảnh nhỏ hơn 50 px mỗi chiều
MARGIN = 16  # viền thêm quanh ảnh: chữ sát mép vùng chọn vẫn đọc được
TEXT_PX = 22  # chữ thấp hơn chừng này thì phóng to ảnh cho chữ cao đúng chừng này rồi đọc lại
MIN_UPSCALE = 1.1  # chữ chỉ thiếu chút xíu thì thôi: đọc lại tốn gấp đôi thời gian mà không được gì
MAX_UPSCALE = 3  # chữ nhỏ tới đâu cũng không phóng to quá mức này: ảnh cả màn hình sẽ quá nặng


def _snipping_tool_dir() -> Path | None:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-AppxPackage Microsoft.ScreenSketch).InstallLocation"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(out.splitlines()[0]) / "SnippingTool" if out else None


def install_oneocr() -> bool:
    """Chép 3 file OneOCR từ Snipping Tool sang ONEOCR_DIR nếu chưa có. Trả về True khi đã sẵn sàng."""
    if all((ONEOCR_DIR / name).is_file() for name in ONEOCR_FILES):
        return True
    source = _snipping_tool_dir()
    if source is None or not all((source / name).is_file() for name in ONEOCR_FILES):
        return False
    ONEOCR_DIR.mkdir(parents=True, exist_ok=True)
    for name in ONEOCR_FILES:
        shutil.copy2(source / name, ONEOCR_DIR / name)
    log.info("Đã chép OneOCR từ %s sang %s", source, ONEOCR_DIR)
    return True


def pad(image: Image.Image, margin: int = MARGIN, min_size: int = ONEOCR_MIN_SIZE) -> Image.Image:
    """Thêm viền cùng màu nền quanh ảnh, đủ to để OneOCR chịu đọc. Chữ dịch đi (margin, margin)."""
    rgb = np.asarray(image.convert("RGB"))
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    color = tuple(int(c) for c in np.median(border, axis=0))
    out = ImageOps.expand(image.convert("RGB"), border=margin, fill=color)
    if out.width < min_size or out.height < min_size:
        canvas = Image.new("RGB", (max(out.width, min_size), max(out.height, min_size)), color)
        canvas.paste(out)
        out = canvas
    return out


def lines_from_result(result: dict, offset: int, size: tuple[int, int], scale: float = 1) -> list[TextBox]:
    """Đổi kết quả của oneocr sang TextBox trong hệ tọa độ của ảnh gốc (trước khi phóng to `scale` lần, thêm viền)."""
    width, height = size
    lines = []
    for line in result.get("lines", []):
        rect, text = line.get("bounding_rect"), (line.get("text") or "").strip()
        if not rect or not text:
            continue
        xs = [(rect[f"x{i}"] - offset) / scale for i in range(1, 5)]
        ys = [(rect[f"y{i}"] - offset) / scale for i in range(1, 5)]
        left, top = max(0, round(min(xs))), max(0, round(min(ys)))
        right, bottom = min(width, round(max(xs))), min(height, round(max(ys)))
        if right > left and bottom > top:
            lines.append(TextBox(text, left, top, right, bottom))
    return lines


def upscale_for(lines: list[TextBox]) -> float:
    """Cần phóng to ảnh bao nhiêu lần để chữ đủ cao; 1 nếu đã đủ hoặc không có chữ cần dịch."""
    sizes = [min(b.width, b.height) for b in lines if len(b.text) >= 2 and has_cjk(b.text)]
    scale = TEXT_PX / median(sizes) if sizes else 1
    return min(scale, MAX_UPSCALE) if scale >= MIN_UPSCALE else 1


class OneOcrReader:
    def __init__(self):
        if not install_oneocr():
            raise RuntimeError("không tìm thấy OneOCR (cần Snipping Tool bản mới của Windows 11)")
        import oneocr

        self._engine = oneocr.OcrEngine()

    def _read(self, image: Image.Image, scale: float = 1) -> list[TextBox]:
        big = image
        if scale != 1:
            size = (round(image.width * scale), round(image.height * scale))
            big = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        return lines_from_result(self._engine.recognize_pil(pad(big)), MARGIN, image.size, scale)

    def read_lines(self, image: Image.Image) -> list[TextBox]:
        lines = self._read(image)
        scale = upscale_for(lines)
        return lines if scale == 1 else self._read(image, scale)
