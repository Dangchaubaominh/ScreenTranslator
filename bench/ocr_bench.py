"""Đo manga-ocr trên ảnh dựng từ câu mẫu: chữ ngang (hộp thoại game) và chữ dọc (bóng thoại manga).

Chạy:
    uv run python bench/ocr_bench.py          # GPU (nếu có) rồi CPU

Ảnh dựng ra là ảnh giả lập, chưa phải ảnh chụp game / manga thật; đủ để so tốc độ GPU với CPU
và thấy sơ bộ độ chính xác. Kết quả ghi vào bench/results/, ảnh ở bench/results/ocr-images/.
"""

import json
import statistics
import sys
import textwrap
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import torch
from manga_ocr import MangaOcr
from PIL import Image, ImageDraw, ImageFont

from screen_translator.preprocess import reflow_long_lines, to_black_on_white

BENCH_DIR = Path(__file__).parent
FONT_REGULAR = r"C:\Windows\Fonts\YuGothM.ttc"
FONT_BOLD = r"C:\Windows\Fonts\YuGothB.ttc"

ROTATED_IN_VERTICAL = set("「」『』（）ー～…")  # các ký tự này xoay 90° khi viết dọc
SHIFTED_IN_VERTICAL = set("、。")  # dấu câu nằm góc trên bên phải ô chữ khi viết dọc
CHARS_PER_COLUMN = 10


def render_horizontal(text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Hộp thoại kiểu visual novel: nền tối, chữ trắng, nhiều dòng."""
    size = int(font.size)
    lines = text.split("\n")
    line_h = int(size * 1.5)
    width = int(max(font.getlength(line) for line in lines)) + 2 * size
    img = Image.new("RGB", (width, len(lines) * line_h + size), (20, 24, 40))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((size, size // 2 + i * line_h), line, font=font, fill=(255, 255, 255))
    return img


def render_vertical(text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Bóng thoại kiểu manga: nền trắng, chữ dọc, cột đọc từ phải sang trái."""
    size = int(font.size)
    columns = [chunk for line in text.split("\n") for chunk in textwrap.wrap(line, CHARS_PER_COLUMN)]
    col_w = int(size * 1.4)
    pad = size
    width = len(columns) * col_w + 2 * pad
    img = Image.new("RGB", (width, max(len(c) for c in columns) * size + 2 * pad), "white")
    for ci, column in enumerate(columns):
        x = width - pad - (ci + 1) * col_w + (col_w - size) // 2
        for ri, ch in enumerate(column):
            glyph = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            ImageDraw.Draw(glyph).text((size / 2, size / 2), ch, font=font, fill="black", anchor="mm")
            dx = dy = 0
            if ch in ROTATED_IN_VERTICAL:
                glyph = glyph.rotate(-90)
            elif ch in SHIFTED_IN_VERTICAL:
                dx, dy = size // 2, -size // 2
            img.paste(glyph, (x + dx, pad + ri * size + dy), glyph)
    return img


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if not ch.isspace())


def char_accuracy(ref: str, hyp: str) -> float:
    """1 − (khoảng cách Levenshtein / độ dài chữ đúng)."""
    ref, hyp = normalize(ref), normalize(hyp)
    prev = list(range(len(hyp) + 1))
    for i, a in enumerate(ref, 1):
        cur = [i]
        for j, b in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a != b)))
        prev = cur
    return max(0.0, 1 - prev[-1] / len(ref))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    samples = [
        json.loads(line)
        for line in (BENCH_DIR / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    image_dir = BENCH_DIR / "results" / "ocr-images"
    image_dir.mkdir(parents=True, exist_ok=True)

    horizontal_font = ImageFont.truetype(FONT_REGULAR, 28)
    vertical_font = ImageFont.truetype(FONT_BOLD, 26)
    cases = []  # (layout, sample, image)
    for s in samples:
        horizontal = render_horizontal(s["ja"], horizontal_font)
        inverted = to_black_on_white(horizontal)
        for layout, img in (
            ("ngang", horizontal),
            ("ngang+đảo màu", inverted),
            ("ngang+đảo màu+xếp dòng", reflow_long_lines(inverted)),
            ("dọc", render_vertical(s["ja"], vertical_font)),
        ):
            img.save(image_dir / f"{s['id']}-{layout}.png")
            cases.append((layout, s, img))

    devices = ["gpu", "cpu"] if torch.cuda.is_available() else ["cpu"]
    if devices == ["cpu"]:
        print("CẢNH BÁO: PyTorch không thấy CUDA, chỉ đo được CPU.", flush=True)

    rows, errors = [], []
    for device in devices:
        print(f"== manga-ocr trên {device.upper()}", flush=True)
        start = time.perf_counter()
        mocr = MangaOcr(force_cpu=device == "cpu")
        mocr(cases[0][2])  # làm nóng
        load_s = time.perf_counter() - start
        if device == "gpu":
            torch.cuda.reset_peak_memory_stats()

        by_layout: dict[str, tuple[list[float], list[float]]] = {}
        for layout, s, img in cases:
            start = time.perf_counter()
            hyp = mocr(img)
            elapsed = time.perf_counter() - start
            acc = char_accuracy(s["ja"], hyp)
            times, accs = by_layout.setdefault(layout, ([], []))
            times.append(elapsed)
            accs.append(acc)
            print(f"  {s['id']}-{layout}: {elapsed * 1000:.0f} ms  {acc:.0%}  {hyp}", flush=True)
            if device == devices[0] and acc < 1:
                errors.append((f"{s['id']}-{layout}", s["ja"].replace("\n", " / "), hyp, acc))

        vram_gb = torch.cuda.max_memory_reserved() / 1e9 if device == "gpu" else None
        for layout, (times, accs) in by_layout.items():
            rows.append(
                {
                    "device": device,
                    "layout": layout,
                    "load_s": round(load_s, 1),
                    "median_ms": round(statistics.median(times) * 1000),
                    "max_ms": round(max(times) * 1000),
                    "accuracy": round(statistics.mean(accs) * 100, 1),
                    "vram_gb": round(vram_gb, 2) if vram_gb is not None else None,
                }
            )
        del mocr
        if device == "gpu":
            torch.cuda.empty_cache()

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    lines = [
        f"# Đo manga-ocr — {stamp}",
        "",
        (
            f"Ảnh giả lập dựng từ {len(samples)} câu mẫu. Chữ ngang: hộp thoại game chữ trắng nền tối, "
            "thử thêm hai cách tiền xử lý (đảo màu; đảo màu rồi xếp dòng dài thành ảnh gần vuông). "
            "Chữ dọc: bóng thoại manga chữ đen nền trắng."
        ),
        "",
        "| Thiết bị | Kiểu chữ | Nạp + làm nóng (s) | Trung vị (ms) | Chậm nhất (ms) | Ký tự đúng (%) | VRAM (GB) |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['device'].upper()} | {r['layout']} | {r['load_s']} | {r['median_ms']} | {r['max_ms']} "
        f"| {r['accuracy']} | {r['vram_gb'] if r['vram_gb'] is not None else '—'} |"
        for r in rows
    ]
    lines += ["", f"## Các ảnh đọc chưa đúng 100% ({devices[0].upper()})", ""]
    lines += [f"- **{case}** ({acc:.0%}): đúng `{ref}` · đọc ra `{hyp}`" for case, ref, hyp, acc in errors]

    report = BENCH_DIR / "results" / f"ocr-{stamp}.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nĐã ghi {report}")


if __name__ == "__main__":
    main()
