"""Cấu hình người dùng, lưu ở %APPDATA%\\ScreenTranslator\\config.json."""

import json
import os
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .translate import DEFAULT_MODEL

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ScreenTranslator"
CONFIG_PATH = APP_DIR / "config.json"

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
    "toggle": "Ẩn / hiện bản dịch",
    "edit": "Sửa chữ OCR gần nhất",
}


@dataclass(frozen=True)
class Config:
    model: str = DEFAULT_MODEL
    profile: str = "light"
    ocr_engine: str = "oneocr"
    hotkey_select: str = "Ctrl+Alt+T"
    hotkey_screen: str = "Ctrl+Alt+F"
    hotkey_repeat: str = "Ctrl+Alt+R"
    hotkey_toggle: str = "Ctrl+Alt+H"
    hotkey_edit: str = "Ctrl+Alt+E"

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
    return config


def save(config: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
