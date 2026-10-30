import sqlite3

from screen_translator.cache import TranslationCache


def test_translations_survive_a_restart(tmp_path):
    path = tmp_path / "sub" / "cache.sqlite3"
    cache = TranslationCache(path)
    assert cache.get("vntl", "設定") is None
    cache.put("vntl", "設定", "Settings")
    cache.put("vntl", "設定", "Options")  # dịch lại thì ghi đè
    cache.close()

    cache = TranslationCache(path)
    assert cache.get("vntl", "設定") == "Options"
    assert cache.get("qwen2.5:3b", "設定") is None  # mỗi model một bản dịch riêng
    cache.close()


def test_translations_depend_on_the_glossary_used(tmp_path):
    path = tmp_path / "cache.sqlite3"
    with sqlite3.connect(path) as old:  # cache của bản trước, chưa có cột glossary
        old.execute("CREATE TABLE translations (model TEXT, ja TEXT, en TEXT, PRIMARY KEY (model, ja))")
    old.close()
    cache = TranslationCache(path)
    cache.put("vntl", "霊夢の部屋", "Reimu's room", glossary="霊夢=Reimu|Female")
    assert cache.get("vntl", "霊夢の部屋", glossary="霊夢=Reimu|Female") == "Reimu's room"
    assert cache.get("vntl", "霊夢の部屋") is None  # dịch lúc chưa khai tên: không dùng lại
    cache.close()
