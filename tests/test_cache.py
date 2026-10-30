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
