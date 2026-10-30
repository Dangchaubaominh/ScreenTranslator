import subprocess

from screen_translator import shortcuts


def quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def read_shortcut(path) -> tuple[str, str]:
    """(file đích, tham số) của một file .lnk, đọc lại bằng Shell.Application như Explorer."""
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        f"$link = (New-Object -ComObject Shell.Application).NameSpace({quote(path.parent)})"
        f".ParseName({quote(path.name)}).GetLink; $link.Path; $link.Arguments"
    )
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout.splitlines()
    return out[0], out[1] if len(out) > 1 else ""


def test_locations_are_start_menu_desktop_and_startup(qapp):
    paths = shortcuts.locations()
    assert paths["start_menu"].parent.name == "Programs" and "Start Menu" in str(paths["start_menu"])
    assert paths["autostart"].parent == paths["start_menu"].parent / "Startup"
    assert all(path.name == "ScreenTranslator.lnk" for path in paths.values())


def test_apply_creates_and_removes_shortcuts(tmp_path, monkeypatch):
    folder = tmp_path / "Thư mục 'thử'"  # dấu tiếng Việt, dấu nháy, dấu cách trong đường dẫn
    target = folder / "screen-translator-gui.exe"
    folder.mkdir()
    target.write_bytes(b"")
    monkeypatch.setattr(shortcuts, "launcher", lambda: target)
    monkeypatch.setattr(shortcuts, "ICON_PATH", folder / "icon.ico")
    paths = {key: folder / key / shortcuts.NAME for key in shortcuts.LABELS}

    shortcuts.apply({"start_menu": True, "desktop": False, "autostart": True}, paths)
    assert shortcuts.states(paths) == {"start_menu": True, "desktop": False, "autostart": True}
    assert read_shortcut(paths["start_menu"]) == (str(target), "")
    assert read_shortcut(paths["autostart"]) == (str(target), "--autostart")

    shortcuts.apply({"start_menu": False, "desktop": False, "autostart": True}, paths)
    assert shortcuts.states(paths) == {"start_menu": False, "desktop": False, "autostart": True}
