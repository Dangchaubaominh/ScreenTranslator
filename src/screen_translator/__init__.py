"""ScreenTranslator: dịch chữ tiếng Nhật trên màn hình sang tiếng Anh, chạy offline (OneOCR + Ollama)."""

import argparse
import logging
import sys
import time
from pathlib import Path


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream:  # không có khi chạy không cửa sổ console (pythonw, bản đóng gói)
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="screen-translator", description=__doc__)
    parser.add_argument("--image", type=Path, help="đọc và dịch một file ảnh rồi thoát, không mở giao diện")
    parser.add_argument("--autostart", action="store_true", help="chạy lúc mở Windows: chỉ có icon ở khay")
    args = parser.parse_args()

    from .config import APP_DIR

    APP_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(APP_DIR / "screen-translator.log", encoding="utf-8")]
    if sys.stderr:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)

    if args.image:
        translate_file(args.image)
    else:
        from .app import run

        sys.exit(run(autostart=args.autostart))


def translate_file(path: Path) -> None:
    """Đọc mọi khối chữ trong ảnh và in bản dịch từng khối (không dùng cache)."""
    import ollama
    from PIL import Image

    from . import config
    from .glossary import Glossary
    from .layout import group_lines, has_japanese
    from .ocr import OneOcrReader
    from .translate import tidy, translate

    cfg = config.load()
    glossary = Glossary(config.GLOSSARY_PATH).entries()
    reader = OneOcrReader()
    client = ollama.Client()
    start = time.perf_counter()
    blocks = [b for b in group_lines(reader.read_lines(Image.open(path))) if has_japanese(b.text)]
    ocr_s = time.perf_counter() - start
    for b in blocks:
        en, _ = translate(
            client, cfg.model, b.text, glossary=glossary, options=cfg.ollama_options, keep_alive=cfg.keep_alive
        )
        print(f"[{b.left},{b.top}–{b.right},{b.bottom}] {b.text}\n  → {tidy(en)}")
    print(
        f"({len(blocks)} khối; OCR {ocr_s:.2f}s, dịch {time.perf_counter() - start - ocr_s:.2f}s;"
        f" glossary {len(glossary)} mục)"
    )
