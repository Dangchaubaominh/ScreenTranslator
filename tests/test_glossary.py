import unicodedata

import pytest

from screen_translator.glossary import (
    TEMPLATE,
    Entry,
    Glossary,
    ensure_file,
    exact,
    parse,
    relevant,
    signature,
    substitute,
    vntl_metadata,
)

REIMU, MARISA, GENSOKYO = (
    Entry("霊夢", "Reimu", "Female"),
    Entry("魔理沙", "Marisa", "Female"),
    Entry("幻想郷", "Gensokyo"),
)


def test_parse_names_terms_and_comments():
    text = (
        "# chú thích\n"
        "\n"
        "霊夢 = Reimu (nữ)\n"
        "魔理沙＝Marisa (Female)\n"  # dấu ＝ của bộ gõ tiếng Nhật
        "  幻想郷 =  Gensokyo  \n"
        "クイックセーブ = Save (Quick)\n"  # ngoặc không phải giới tính: thuộc bản dịch
        "dòng không có dấu bằng\n"
        "霊夢 = Reimu Hakurei (nữ)\n"  # khai lại: lấy dòng sau
    )
    assert parse(text) == [
        Entry("霊夢", "Reimu Hakurei", "Female"),
        MARISA,
        GENSOKYO,
        Entry("クイックセーブ", "Save (Quick)"),
    ]


def test_parse_accepts_decomposed_vietnamese_and_male():
    # một số bộ gõ tiếng Việt ghi "nữ" dạng tổ hợp dấu rời
    assert parse(unicodedata.normalize("NFD", "早苗 = Sanae (nữ)\nタクミ = Takumi (nam)")) == [
        Entry("早苗", "Sanae", "Female"),
        Entry("タクミ", "Takumi", "Male"),
    ]


def test_template_has_only_comments():
    assert parse(TEMPLATE) == []


def test_only_entries_in_the_text_are_used():
    entries = [REIMU, MARISA, GENSOKYO]
    assert relevant(entries, "霊夢は幻想郷の巫女だ。") == [REIMU, GENSOKYO]
    assert exact(entries, " 幻想郷 ") == "Gensokyo"
    assert exact(entries, "幻想郷の朝") is None


def test_vntl_metadata_declares_names_with_gender_and_terms():
    assert vntl_metadata([REIMU, GENSOKYO]) == (
        "[character] Name: Reimu (霊夢) | Gender: Female\n[term] 幻想郷: Gensokyo\n"
    )


def test_substitute_replaces_longer_entries_first():
    entries = [REIMU, Entry("博麗霊夢", "Reimu Hakurei", "Female")]
    assert substitute("博麗霊夢と霊夢", entries) == "Reimu HakureiとReimu"


def test_signature_changes_with_any_field():
    assert signature([]) == ""
    assert signature([REIMU]) != signature([Entry("霊夢", "Reimu", "Male")])


def test_file_is_reread_after_editing(tmp_path):
    path = tmp_path / "glossary.txt"
    glossary = Glossary(path)
    assert glossary.entries() == []  # chưa có file
    path.write_text("﻿霊夢 = Reimu (nữ)\n", encoding="utf-8")  # Notepad có thể thêm BOM
    assert glossary.entries() == [REIMU]
    path.write_text("霊夢 = Reimu (nữ)\n幻想郷 = Gensokyo\n", encoding="utf-8")
    assert glossary.entries() == [REIMU, GENSOKYO]
    path.write_bytes("霊夢 = Reimu".encode("shift_jis"))
    with pytest.raises(UnicodeDecodeError):
        glossary.entries()


def test_ensure_file_writes_the_template_once(tmp_path):
    path = tmp_path / "sub" / "glossary.txt"
    assert ensure_file(path) == path and path.read_text(encoding="utf-8") == TEMPLATE
    path.write_text("霊夢 = Reimu (nữ)\n", encoding="utf-8")
    ensure_file(path)
    assert path.read_text(encoding="utf-8") == "霊夢 = Reimu (nữ)\n"
