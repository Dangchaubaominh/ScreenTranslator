"""Đo các model dịch JA→EN qua Ollama: tốc độ, VRAM, điểm chrF so với bản dịch tham chiếu.

Chạy:
    uv run --group bench python bench/run_bench.py                  # mọi model, chạy GPU
    uv run --group bench python bench/run_bench.py --cpu            # ép chạy CPU (hồ sơ Nặng)
    uv run --group bench python bench/run_bench.py --models vntl lfm2

Prompt của từng model lấy từ screen_translator.translate (dùng chung với app).
Kết quả (bảng tổng hợp + bản dịch từng câu để chấm bằng mắt) ghi vào bench/results/.
"""

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import ollama
from sacrebleu.metrics import CHRF

from screen_translator.translate import translate, unload

BENCH_DIR = Path(__file__).parent

MODELS = {
    "lfm2": "hf.co/LiquidAI/LFM2-350M-ENJP-MT-GGUF:Q4_K_M",
    "vntl": "hf.co/lmg-anon/vntl-gemma2-2b-gguf:Q6_K",
    "translategemma": "translategemma:4b",
    "qwen3.5": "qwen3.5:4b",
    "qwen2.5": "qwen2.5:3b",  # mốc so sánh, máy đã có sẵn
}


def for_chrf(text: str) -> str:
    """Bỏ dấu ngoặc kép / ngoặc Nhật để chrF không phạt model chỉ vì khác kiểu ngoặc."""
    return re.sub(r"\s+", " ", re.sub(r"[「」『』\"“”]", "", text)).strip()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    parser.add_argument("--cpu", action="store_true", help="ép model chạy CPU (num_gpu=0)")
    args = parser.parse_args()

    samples = [
        json.loads(line)
        for line in (BENCH_DIR / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    client = ollama.Client()
    device = "cpu" if args.cpu else "gpu"
    extra_options = {"num_gpu": 0} if args.cpu else {}
    chrf = CHRF()
    summary = []
    outputs = {s["id"]: {} for s in samples}

    for name in args.models:
        tag = MODELS[name]
        print(f"== {name} ({tag}, {device})", flush=True)
        try:
            start = time.perf_counter()
            translate(client, tag, "こんにちは", options=extra_options, keep_alive="10m")  # nạp + làm nóng
            load_s = time.perf_counter() - start
        except ollama.ResponseError as e:
            print(f"  bỏ qua: {e}", flush=True)
            continue
        loaded = next((m for m in client.ps().models if m.model == tag), None)
        vram_gb = loaded.size_vram / 1e9 if loaded else 0.0
        total_gb = loaded.size / 1e9 if loaded else 0.0

        latencies, speeds, hyps = [], [], []
        for s in samples:
            start = time.perf_counter()
            text, r = translate(client, tag, s["ja"], options=extra_options, keep_alive="10m")
            latencies.append(time.perf_counter() - start)
            if r.eval_count and r.eval_duration:
                speeds.append(r.eval_count / (r.eval_duration / 1e9))
            hyps.append(text)
            outputs[s["id"]][name] = text
            print(f"  {s['id']}: {latencies[-1]:.2f}s  {text}", flush=True)

        unload(client, tag)  # trả bộ nhớ cho model kế tiếp
        score = chrf.corpus_score([for_chrf(h) for h in hyps], [[for_chrf(s["en"]) for s in samples]]).score
        summary.append(
            {
                "model": name,
                "tag": tag,
                "device": device,
                "vram_gb": round(vram_gb, 2),
                "total_gb": round(total_gb, 2),
                "load_s": round(load_s, 2),
                "median_s": round(statistics.median(latencies), 3),
                "max_s": round(max(latencies), 3),
                "tokens_per_s": round(statistics.median(speeds), 1) if speeds else None,
                "chrf": round(score, 1),
            }
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = BENCH_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    lines = [
        f"# Đo dịch JA→EN — {device.upper()} — {stamp}",
        "",
        "| Model | VRAM / tổng (GB) | Nạp + làm nóng (s) | Trung vị mỗi câu (s) | Chậm nhất (s) | Token/s | chrF |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['model']} | {r['vram_gb']} / {r['total_gb']} | {r['load_s']} | {r['median_s']} | {r['max_s']} "
        f"| {r['tokens_per_s']} | {r['chrf']} |"
        for r in summary
    ]
    lines += [
        "",
        (
            "chrF: độ giống bản dịch tham chiếu theo ký tự (0–100, cao hơn tốt hơn). Chỉ để tham khảo: "
            "một câu tiếng Nhật có nhiều cách dịch đúng, nên chấm bằng mắt ở phần dưới mới là thước đo chính."
        ),
        "",
    ]
    for s in samples:
        lines += [
            f"## {s['id']} ({s['kind']})",
            "",
            f"- **JA:** {s['ja'].replace(chr(10), ' / ')}",
            f"- **Tham chiếu:** {s['en']}",
        ]
        lines += [f"- **{r['model']}:** {outputs[s['id']].get(r['model'], '')}" for r in summary]
        lines.append("")

    report = out_dir / f"translate-{device}-{stamp}.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / f"translate-{device}-{stamp}.json").write_text(
        json.dumps({"summary": summary, "outputs": outputs}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nĐã ghi {report}")


if __name__ == "__main__":
    main()
