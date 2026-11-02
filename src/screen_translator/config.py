"""Cấu hình người dùng, lưu ở %APPDATA%\\ScreenTranslator\\config.json."""

import json
import os
import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .translate import DEFAULT_MODEL

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ScreenTranslator"
CONFIG_PATH = APP_DIR / "config.json"
GLOSSARY_PATH = APP_DIR / "glossary.txt"  # tên riêng, thuật ngữ: sửa ở trang Tên riêng hoặc bằng Notepad

# Hồ sơ hiệu năng (PLAN.md mục 7)
PROFILES = {
    "light": {  # game chạy trên Iris Xe, RTX 3050 dành cho dịch
        "label": "Nhẹ — game chạy trên Iris Xe, dịch bằng RTX 3050",
        "ollama_options": {},
        "keep_alive": "30m",
    },
    "heavy": {  # game cần RTX 3050, dịch chạy CPU
        "label": "Nặng — game dùng RTX 3050, dịch bằng CPU",
        "ollama_options": {"num_gpu": 0},
        "keep_alive": "5m",
    },
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
    hotkey_select: str = "Ctrl+Alt+T"
    hotkey_screen: str = "Ctrl+Alt+F"
    hotkey_repeat: str = "Ctrl+Alt+R"
    hotkey_live: str = "Ctrl+Alt+L"
    hotkey_toggle: str = "Ctrl+Alt+H"
    hotkey_edit: str = "Ctrl+Alt+E"
    overlay_font_px: int = 34  # cỡ chữ lớn nhất của bản dịch; khung nhỏ thì chữ tự thu nhỏ cho vừa
    overlay_opacity: int = 100  # % độ đặc của nền; thấp hơn thì chữ Nhật gốc lộ ra sau bản dịch
    overlay_color: str = "#0c101c"
    panel_vertical: bool = False  # thanh xếp thành cột dọc thay vì hàng ngang
    panel_pos: tuple[int, int] | None = None  # chỗ thanh điều khiển (tọa độ logic); None: giữa mép trên màn hình

    @property
    def hotkeys(self) -> dict[str, str]:
        """Hành động → phím tắt, theo thứ tự của HOTKEY_LABELS."""
        return {action: getattr(self, f"hotkey_{action}") for action in HOTKEY_LABELS}

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
    valid_color = re.fullmatch(r"#[0-9a-fA-F]{6}", str(config.overlay_color))
    pos = config.panel_pos
    valid_pos = isinstance(pos, list | tuple) and len(pos) == 2 and all(isinstance(v, int) for v in pos)
    return replace(
        config,
        profile=config.profile if config.profile in PROFILES else Config.profile,
        overlay_color=config.overlay_color if valid_color else Config.overlay_color,
        panel_pos=tuple(pos) if valid_pos else None,
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
