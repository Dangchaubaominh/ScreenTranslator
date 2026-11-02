"""Đọc chữ tiếng Nhật trong ảnh bằng OneOCR, trả về từng dòng kèm vị trí.

OneOCR là engine OCR có sẵn trong Snipping Tool của Windows 11. Chạy CPU, đọc cả màn hình ~0,2–0,5 s, đúng cả logo
cách điệu và chữ xám mờ trên ảnh game thật. Là thành phần nội bộ của Microsoft: chỉ chép file một lần, Snipping Tool
đời sau có thể đổi file làm thư viện oneocr không đọc được; khi đó app báo lỗi.
"""

import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .layout import TextBox

log = logging.getLogger(__name__)

ONEOCR_DIR = Path.home() / ".config" / "oneocr"  # thư viện oneocr đọc file ở đây
ONEOCR_FILES = ("oneocr.dll", "oneocr.onemodel", "onnxruntime.dll")
ONEOCR_MIN_SIZE = 50  # OneOCR bỏ qua ảnh nhỏ hơn 50 px mỗi chiều
MARGIN = 16  # viền thêm quanh ảnh: chữ sát mép vùng chọn vẫn đọc được


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


def lines_from_result(result: dict, offset: int, size: tuple[int, int]) -> list[TextBox]:
    """Đổi kết quả của oneocr sang TextBox trong hệ tọa độ của ảnh gốc (trước khi thêm viền)."""
    width, height = size
    lines = []
    for line in result.get("lines", []):
        rect, text = line.get("bounding_rect"), (line.get("text") or "").strip()
        if not rect or not text:
            continue
        xs = [rect[f"x{i}"] - offset for i in range(1, 5)]
        ys = [rect[f"y{i}"] - offset for i in range(1, 5)]
        left, top = max(0, round(min(xs))), max(0, round(min(ys)))
        right, bottom = min(width, round(max(xs))), min(height, round(max(ys)))
        if right > left and bottom > top:
            lines.append(TextBox(text, left, top, right, bottom))
    return lines


class OneOcrReader:
    def __init__(self):
        if not install_oneocr():
            raise RuntimeError("không tìm thấy OneOCR (cần Snipping Tool bản mới của Windows 11)")
        import oneocr

        self._engine = oneocr.OcrEngine()

    def read_lines(self, image: Image.Image) -> list[TextBox]:
        return lines_from_result(self._engine.recognize_pil(pad(image)), MARGIN, image.size)
