"""Dịch sang tiếng Anh qua Ollama. Mỗi loại model cần một kiểu prompt riêng.

Trong code, `ja` là chữ gốc cần dịch: tên có từ lúc app chỉ dịch tiếng Nhật, giờ là ngôn ngữ đang chọn ở Cài đặt.
"""

from collections.abc import Sequence

import ollama

from .glossary import Entry, exact, relevant, substitute, vntl_metadata

DEFAULT_MODEL = "hf.co/lmg-anon/vntl-gemma2-2b-gguf:Q6_K"

MULTI_LANGUAGE_MODEL = "qwen3.5:4b"  # VNTL chỉ dịch tiếng Nhật

# mã ngôn ngữ → tên hiện ở Cài đặt, tên trong prompt, model nên dùng
LANGUAGES = {
    "ja": {"label": "Tiếng Nhật", "name": "Japanese", "model": DEFAULT_MODEL},
    "zh": {"label": "Tiếng Trung", "name": "Chinese", "model": MULTI_LANGUAGE_MODEL},
    "ko": {"label": "Tiếng Hàn", "name": "Korean", "model": MULTI_LANGUAGE_MODEL},
}

_STYLE_OPTIONS = {
    "vntl": {"temperature": 0},
    "translategemma": {"temperature": 0},
    # Thông số khuyến nghị trong tài liệu của Liquid AI
    "lfm2": {"temperature": 0.5, "top_p": 1.0, "min_p": 0.1, "repeat_penalty": 1.05},
    "chat": {"temperature": 0},
}

_QUOTES = str.maketrans({"「": "“", "」": "”", "『": "‘", "』": "’"})


def style_of(tag: str) -> str:
    """Kiểu prompt theo tên model: vntl, translategemma, lfm2, hoặc chat (system prompt thường)."""
    name = tag.lower()
    if "vntl" in name:
        return "vntl"
    if "translategemma" in name:
        return "translategemma"
    if "enjp-mt" in name:
        return "lfm2"
    return "chat"


def vntl_prompt(ja: str, glossary: Sequence[Entry] = (), context: Sequence[tuple[str, str]] = ()) -> str:
    """context: các câu trước (chữ gốc, bản dịch) xếp nối tiếp như lúc VNTL được huấn luyện, xem trang model."""
    history = "".join(f"<<JAPANESE>>\n{prev_ja}\n<<ENGLISH>>\n{prev_en}<eos>\n" for prev_ja, prev_en in context)
    return f"<<METADATA>>\n{vntl_metadata(glossary)}<<TRANSLATE>>\n{history}<<JAPANESE>>\n{ja}\n<<ENGLISH>>\n"


def translategemma_prompt(ja: str, language: str = "ja") -> str:
    # Mẫu prompt cố định trên trang model ở ollama.com; phải có hai dòng trống trước đoạn cần dịch
    name = LANGUAGES[language]["name"]
    return (
        f"You are a professional {name} ({language}) to English (en) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original {name} text "
        "while adhering to English grammar, vocabulary, and cultural sensitivities.\n"
        "Produce only the English translation, without any additional explanations or commentary. "
        f"Please translate the following {name} text into English:\n\n\n"
        f"{ja}"
    )


def system_prompt(language: str = "ja") -> str:
    name = LANGUAGES[language]["name"]
    return (
        f"You are a professional translator of {name} games and comics. "
        f"Translate the user's {name} text into natural English. "
        "Output only the English translation, nothing else."
    )


def max_tokens(ja: str) -> int:
    """Trần độ dài bản dịch. Model nhỏ gặp chữ OCR sai đôi khi lặp mãi không dừng (đã gặp: 6 phút một câu)."""
    return 32 + 4 * len(ja)


def keep_lines(en: str, ja: str) -> str:
    """Bỏ phần model bịa thêm: bản dịch không có nhiều dòng hơn bản gốc.

    VNTL hay dịch xong một nhãn menu rồi viết thêm một câu tự nghĩ ra sau vài dòng trống.
    """
    lines = [line for line in en.strip().splitlines() if line.strip()]
    return "\n".join(lines[: ja.strip().count("\n") + 1])


def translate(
    client: ollama.Client,
    tag: str,
    ja: str,
    *,
    glossary: Sequence[Entry] = (),
    context: Sequence[tuple[str, str]] = (),
    language: str = "ja",
    options: dict | None = None,
    keep_alive: str = "30m",
):
    """Dịch một đoạn. Trả về (bản dịch, phản hồi gốc của Ollama để đọc số liệu thời gian).

    glossary: cả danh sách tên riêng / thuật ngữ, chỉ các mục có trong `ja` vào prompt. Cả đoạn trùng một mục
    thì trả luôn bản dịch khai sẵn, phản hồi là None.
    context: vài câu thoại ngay trước (chữ gốc, bản dịch) để model hiểu mạch hội thoại: ai nói với ai, xưng hô,
    chủ ngữ bị lược. Mẫu prompt cố định của translategemma và LFM2 không có chỗ cho ngữ cảnh, nên bỏ qua.
    """
    terms = relevant(glossary, ja)
    if (known := exact(terms, ja)) is not None:
        return known, None
    style = style_of(tag)
    opts = {"num_ctx": 2048, "num_predict": max_tokens(ja), **_STYLE_OPTIONS[style], **(options or {})}
    if style == "vntl":
        # câu một dòng thì dừng ngay ở cuối dòng, không cho viết tiếp đoạn bịa
        stop = ["<<", "<eos>"] + ([] if "\n" in ja.strip() else ["\n"])
        r = client.generate(
            model=tag,
            prompt=vntl_prompt(ja, terms, context),
            raw=True,
            options={**opts, "stop": stop},
            keep_alive=keep_alive,
        )
        return keep_lines(r.response, ja), r

    source = substitute(ja, terms)  # các model khác không có chỗ khai báo tên: thay thẳng trong câu
    if style == "translategemma":
        messages = [{"role": "user", "content": translategemma_prompt(source, language)}]
    elif style == "lfm2":
        messages = [{"role": "system", "content": "Translate to English."}, {"role": "user", "content": source}]
    else:
        history = [
            {"role": role, "content": text}
            for prev_ja, prev_en in context
            for role, text in (("user", prev_ja), ("assistant", prev_en))
        ]
        messages = [
            {"role": "system", "content": system_prompt(language)},
            *history,
            {"role": "user", "content": source},
        ]
    think = {"think": False} if tag.lower().startswith("qwen3") else {}
    r = client.chat(model=tag, messages=messages, options=opts, keep_alive=keep_alive, **think)
    return keep_lines(r.message.content, ja), r


def unload(client: ollama.Client, tag: str) -> None:
    """Gỡ model khỏi bộ nhớ ngay, trả VRAM cho game."""
    client.generate(model=tag, keep_alive=0)


def tidy(text: str) -> str:
    """Đổi ngoặc Nhật mà VNTL giữ lại thành ngoặc kép tiếng Anh."""
    return text.translate(_QUOTES).strip()
