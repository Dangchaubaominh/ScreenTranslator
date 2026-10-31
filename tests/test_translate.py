from types import SimpleNamespace

import pytest

from screen_translator.glossary import Entry
from screen_translator.translate import (
    SYSTEM_PROMPT,
    keep_lines,
    max_tokens,
    style_of,
    tidy,
    translate,
    vntl_prompt,
)


class FakeClient:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(("generate", kwargs))
        return SimpleNamespace(response="  Hello.\n")

    def chat(self, **kwargs):
        self.calls.append(("chat", kwargs))
        return SimpleNamespace(message=SimpleNamespace(content=" Hi. "))


@pytest.mark.parametrize(
    ("tag", "style"),
    [
        ("hf.co/lmg-anon/vntl-gemma2-2b-gguf:Q6_K", "vntl"),
        ("hf.co/lmg-anon/vntl-llama3-8b-v2-gguf:Q4_K_M", "vntl"),
        ("translategemma:4b", "translategemma"),
        ("hf.co/LiquidAI/LFM2-350M-ENJP-MT-GGUF:Q4_K_M", "lfm2"),
        ("qwen3.5:4b", "chat"),
        ("qwen2.5:3b", "chat"),
    ],
)
def test_style_of(tag, style):
    assert style_of(tag) == style


def test_vntl_uses_raw_prompt_with_stop_words():
    client = FakeClient()
    text, _ = translate(client, "vntl-gemma2-2b", "猫だ", options={"num_gpu": 0}, keep_alive="5m")
    assert text == "Hello."
    kind, call = client.calls[0]
    assert kind == "generate"
    assert call["raw"] is True
    assert call["prompt"] == vntl_prompt("猫だ") == "<<METADATA>>\n<<TRANSLATE>>\n<<JAPANESE>>\n猫だ\n<<ENGLISH>>\n"
    assert call["options"] == {
        "num_ctx": 2048,
        "num_predict": max_tokens("猫だ"),
        "temperature": 0,
        "num_gpu": 0,
        "stop": ["<<", "<eos>", "\n"],  # câu một dòng: dừng ở cuối dòng
    }
    assert call["keep_alive"] == "5m"


def test_multi_line_input_may_answer_on_several_lines():
    client = FakeClient()
    translate(client, "vntl-gemma2-2b", "一行目\n二行目")
    assert client.calls[0][1]["options"]["stop"] == ["<<", "<eos>"]


def test_output_length_is_capped_by_input_length():
    assert max_tokens("設定") < max_tokens("自分が寝ていた部屋に戻ると、枕元に何かが転がっていた。") <= 300


def test_invented_extra_lines_are_dropped():
    # VNTL thật: dịch nhãn menu xong viết thêm một câu tự nghĩ ra
    en = "New Game Gallery - Achievements\n\n\nYou can now set the achievements for the New Game Gallery."
    assert keep_lines(en, "ニューゲームギャラリー実績設定") == "New Game Gallery - Achievements"
    assert keep_lines("Line one\n\nLine two\nLine three", "一\n二") == "Line one\nLine two"


def test_user_options_override_model_defaults():
    client = FakeClient()
    translate(client, "hf.co/LiquidAI/LFM2-350M-ENJP-MT-GGUF:Q4_K_M", "猫", options={"temperature": 0.1})
    _, call = client.calls[0]
    assert call["options"]["temperature"] == 0.1
    assert call["options"]["min_p"] == 0.1
    assert call["messages"][0] == {"role": "system", "content": "Translate to English."}


def test_translategemma_puts_everything_in_one_user_message():
    client = FakeClient()
    translate(client, "translategemma:4b", "猫")
    _, call = client.calls[0]
    assert len(call["messages"]) == 1
    assert call["messages"][0]["content"].endswith("English:\n\n\n猫")


def test_qwen3_disables_thinking():
    client = FakeClient()
    text, _ = translate(client, "qwen3.5:4b", "猫")
    assert text == "Hi."
    _, call = client.calls[0]
    assert call["think"] is False
    assert call["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}


def test_other_chat_models_get_no_think_flag():
    client = FakeClient()
    translate(client, "qwen2.5:3b", "猫")
    assert "think" not in client.calls[0][1]


GLOSSARY = [Entry("霊夢", "Reimu", "Female"), Entry("実績", "Achievements"), Entry("咲夜", "Sakuya", "Female")]


def test_vntl_prompt_declares_only_the_names_in_the_text():
    client = FakeClient()
    translate(client, "vntl-gemma2-2b", "霊夢の実績", glossary=GLOSSARY)
    assert client.calls[0][1]["prompt"] == (
        "<<METADATA>>\n"
        "[character] Name: Reimu (霊夢) | Gender: Female\n"
        "[term] 実績: Achievements\n"
        "<<TRANSLATE>>\n<<JAPANESE>>\n霊夢の実績\n<<ENGLISH>>\n"
    )


def test_a_label_that_is_a_glossary_entry_skips_the_model():
    client = FakeClient()
    assert translate(client, "vntl-gemma2-2b", " 実績 ", glossary=GLOSSARY) == ("Achievements", None)
    assert client.calls == []


def test_other_models_get_names_replaced_in_the_text():
    client = FakeClient()
    translate(client, "qwen2.5:3b", "咲夜は猫", glossary=GLOSSARY)
    assert client.calls[0][1]["messages"][1] == {"role": "user", "content": "Sakuyaは猫"}


CONTEXT = [("魔理沙、また来たの", "Marisa, you're here again?"), ("暇だろ？", "You're bored, right?")]


def test_previous_turns_come_before_the_line_to_translate():
    client = FakeClient()
    translate(client, "vntl-gemma2-2b", "暇じゃない", context=CONTEXT)
    assert client.calls[0][1]["prompt"] == (
        "<<METADATA>>\n<<TRANSLATE>>\n"
        "<<JAPANESE>>\n魔理沙、また来たの\n<<ENGLISH>>\nMarisa, you're here again?<eos>\n"
        "<<JAPANESE>>\n暇だろ？\n<<ENGLISH>>\nYou're bored, right?<eos>\n"
        "<<JAPANESE>>\n暇じゃない\n<<ENGLISH>>\n"
    )

    translate(client, "qwen2.5:3b", "暇じゃない", context=CONTEXT)  # model chat: các lượt hỏi / đáp trước
    assert client.calls[1][1]["messages"][1:] == [
        {"role": "user", "content": "魔理沙、また来たの"},
        {"role": "assistant", "content": "Marisa, you're here again?"},
        {"role": "user", "content": "暇だろ？"},
        {"role": "assistant", "content": "You're bored, right?"},
        {"role": "user", "content": "暇じゃない"},
    ]

    # mẫu prompt cố định, không có chỗ cho ngữ cảnh
    translate(client, "translategemma:4b", "暇じゃない", context=CONTEXT)
    translate(client, "hf.co/LiquidAI/LFM2-350M-ENJP-MT-GGUF:Q4_K_M", "暇じゃない", context=CONTEXT)
    assert [len(call["messages"]) for _, call in client.calls[2:]] == [1, 2]


def test_tidy_turns_japanese_quotes_into_english_ones():
    assert tidy(" 「Hello」 and 『hi』 ") == "“Hello” and ‘hi’"
