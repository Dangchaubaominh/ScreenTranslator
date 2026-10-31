import json

from screen_translator.config import Config, load, save


def test_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "config.json") == Config()


def test_broken_file_gives_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{oops", encoding="utf-8")
    assert load(path) == Config()


def test_save_then_load(tmp_path):
    path = tmp_path / "sub" / "config.json"
    config = Config(model="qwen2.5:3b", profile="heavy", hotkey_select="Ctrl+Shift+Q")
    save(config, path)
    assert load(path) == config


def test_unknown_keys_and_bad_values_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    data = {"model": "x", "profile": "ultra", "ocr_engine": "tesseract", "old_setting": 1}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load(path) == Config(model="x", profile="light", ocr_engine="oneocr")


def test_overlay_settings_are_kept_in_range(tmp_path):
    path = tmp_path / "config.json"
    data = {"overlay_position": "left", "overlay_font_px": 200, "overlay_opacity": -5, "overlay_color": "red"}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load(path) == Config(overlay_font_px=48, overlay_opacity=0)
    data = {"overlay_position": "above", "overlay_font_px": "big", "panel_pos": [10, 20]}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load(path) == Config(overlay_position="above", panel_pos=(10, 20))
    path.write_text(json.dumps({"panel_pos": [10, "x"]}), encoding="utf-8")
    assert load(path) == Config()


def test_profiles():
    light, heavy = Config(profile="light"), Config(profile="heavy")
    assert (light.ocr_device, light.ollama_options) == ("gpu", {})
    assert (heavy.ocr_device, heavy.ollama_options) == ("cpu", {"num_gpu": 0})
    assert list(light.hotkeys) == ["select", "screen", "repeat", "live", "toggle", "edit"]
