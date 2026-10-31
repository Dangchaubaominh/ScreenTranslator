"""Cấu hình người dùng, lưu ở %APPDATA%\\ScreenTranslator\\config.json."""

import json
import os
import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .translate import DEFAULT_MODEL

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ScreenTranslator"
CONFIG_PATH = APP_DIR / "config.json"
GLOSSARY_PATH = APP_DIR / "glossary.txt"  # tên riêng, thuật ngữ: người dùng sửa bằng Notepad

# Hồ sơ hiệu năng (PLAN.md mục 7)
PROFILES = {
    "light": {  # game chạy trên Iris Xe, RTX 3050 dành cho dịch + OCR
        "label": "Nhẹ — game chạy trên Iris Xe, dịch bằng RTX 3050",
        "ocr_device": "gpu",
        "ollama_options": {},
        "keep_alive": "30m",
    },
    "heavy": {  # game cần RTX 3050, dịch + OCR chạy CPU
        "label": "Nặng — game dùng RTX 3050, dịch bằng CPU",
        "ocr_device": "cpu",
        "ollama_options": {"num_gpu": 0},
        "keep_alive": "5m",
    },
}

OCR_ENGINES = {
    "oneocr": "OneOCR — có sẵn trong Windows 11, chạy CPU, đọc được cả cửa sổ game",
    "manga-ocr": "manga-ocr — mỗi lần một khối chữ, hợp với manga chữ dọc (GPU/CPU theo hồ sơ)",
}

HOTKEY_LABELS = {
    "select": "Chọn vùng mới và dịch",
    "screen": "Dịch cả cửa sổ game",
    "repeat": "Dịch lại vùng trước",
    "live": "Live mode: tự dịch câu mới trong vùng",
    "toggle": "Ẩn / hiện bản dịch",
    "edit": "Sửa chữ OCR gần nhất",
}

FONT_PX_RANGE = (14, 48)
OPACITY_RANGE = (0, 100)


@dataclass(frozen=True)
class Config:
    model: str = DEFAULT_MODEL
    profile: str = "light"
    ocr_engine: str = "oneocr"
    hotkey_select: str = "Ctrl+Alt+T"
    hotkey_screen: str = "Ctrl+Alt+F"
    hotkey_repeat: str = "Ctrl+Alt+R"
    hotkey_live: str = "Ctrl+Alt+L"
    hotkey_toggle: str = "Ctrl+Alt+H"
    hotkey_edit: str = "Ctrl+Alt+E"
    overlay_font_px: int = 34  # cỡ chữ lớn nhất của bản dịch; khung nhỏ thì chữ tự thu nhỏ cho vừa
    overlay_opacity: int = 100  # % độ đặc của nền; thấp hơn thì chữ Nhật gốc lộ ra sau bản dịch
    overlay_color: str = "#0c101c"
    welcomed: bool = False  # đã xem màn hình chào lần đầu
    show_panel: bool = True  # thanh điều khiển nổi
    panel_pos: tuple[int, int] | None = None  # chỗ thanh điều khiển (tọa độ logic); None: giữa mép trên màn hình

    @property
    def hotkeys(self) -> dict[str, str]:
        """Hành động → phím tắt, theo thứ tự của HOTKEY_LABELS."""
        return {action: getattr(self, f"hotkey_{action}") for action in HOTKEY_LABELS}

    @property
    def ocr_device(self) -> str:
        return PROFILES[self.profile]["ocr_device"]

    @property
    def ollama_options(self) -> dict:
        return PROFILES[self.profile]["ollama_options"]

    @property
    def keep_alive(self) -> str:
        return PROFILES[self.profile]["keep_alive"]


def load(path: Path = CONFIG_PATH) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return Config()
    known = {f.name for f in fields(Config)}
    config = Config(**{k: v for k, v in data.items() if k in known})
    if config.profile not in PROFILES:
        config = replace(config, profile=Config.profile)
    if config.ocr_engine not in OCR_ENGINES:
        config = replace(config, ocr_engine=Config.ocr_engine)
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(config.overlay_color)):
        config = replace(config, overlay_color=Config.overlay_color)
    pos = config.panel_pos
    valid_pos = isinstance(pos, list | tuple) and len(pos) == 2 and all(isinstance(v, int) for v in pos)
    config = replace(config, panel_pos=tuple(pos) if valid_pos else None)
    return replace(
        config,
        overlay_font_px=_clamp(config.overlay_font_px, FONT_PX_RANGE, Config.overlay_font_px),
        overlay_opacity=_clamp(config.overlay_opacity, OPACITY_RANGE, Config.overlay_opacity),
    )


def _clamp(value, bounds: tuple[int, int], default: int) -> int:
    if not isinstance(value, int):
        return default
    return min(max(value, bounds[0]), bounds[1])


def save(config: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
