import pytest

from screen_translator import win32
from screen_translator.hotkeys import parse_hotkey


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ctrl+Alt+T", (win32.MOD_CONTROL | win32.MOD_ALT, ord("T"))),
        ("ctrl + shift + t", (win32.MOD_CONTROL | win32.MOD_SHIFT, ord("T"))),
        ("Win+1", (win32.MOD_WIN, ord("1"))),
        ("Alt+F12", (win32.MOD_ALT, 0x7B)),
        ("Ctrl+Space", (win32.MOD_CONTROL, 0x20)),
        ("Shift+PageDown", (win32.MOD_SHIFT, 0x22)),
    ],
)
def test_parse_valid(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["T", "F5", "Ctrl+", "Ctrl+Alt+TT", "Ctrl+Foo+T", "Ctrl+Alt+é", "Ctrl+F13", ""])
def test_parse_invalid(text):
    with pytest.raises(ValueError):
        parse_hotkey(text)
