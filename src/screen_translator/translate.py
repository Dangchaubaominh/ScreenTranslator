"""Dịch JA→EN qua Ollama. Mỗi loại model cần một kiểu prompt riêng (xem PLAN.md mục 6)."""

import ollama

DEFAULT_MODEL = "hf.co/lmg-anon/vntl-gemma2-2b-gguf:Q6_K"

SYSTEM_PROMPT = (
    "You are a professional translator of Japanese visual novels and manga. "
    "Translate the user's Japanese text into natural English. "
    "Output only the English translation, nothing else."
)

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


def vntl_prompt(ja: str) -> str:
    return f"<<METADATA>>\n<<TRANSLATE>>\n<<JAPANESE>>\n{ja}\n<<ENGLISH>>\n"


def translategemma_prompt(ja: str) -> str:
    # Mẫu prompt cố định trên trang model ở ollama.com; phải có hai dòng trống trước đoạn cần dịch
    return (
        "You are a professional Japanese (ja) to English (en) translator. "
        "Your goal is to accurately convey the meaning and nuances of the original Japanese text "
        "while adhering to English grammar, vocabulary, and cultural sensitivities.\n"
        "Produce only the English translation, without any additional explanations or commentary. "
        "Please translate the following Japanese text into English:\n\n\n"
        f"{ja}"
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


def translate(client: ollama.Client, tag: str, ja: str, *, options: dict | None = None, keep_alive: str = "30m"):
    """Dịch một đoạn. Trả về (bản dịch, phản hồi gốc của Ollama để đọc số liệu thời gian)."""
    style = style_of(tag)
    opts = {"num_ctx": 2048, "num_predict": max_tokens(ja), **_STYLE_OPTIONS[style], **(options or {})}
    if style == "vntl":
        # câu một dòng thì dừng ngay ở cuối dòng, không cho viết tiếp đoạn bịa
        stop = ["<<", "<eos>"] + ([] if "\n" in ja.strip() else ["\n"])
        r = client.generate(
            model=tag,
            prompt=vntl_prompt(ja),
            raw=True,
            options={**opts, "stop": stop},
            keep_alive=keep_alive,
        )
        return keep_lines(r.response, ja), r

    if style == "translategemma":
        messages = [{"role": "user", "content": translategemma_prompt(ja)}]
    else:
        system = "Translate to English." if style == "lfm2" else SYSTEM_PROMPT
        messages = [{"role": "system", "content": system}, {"role": "user", "content": ja}]
    think = {"think": False} if tag.lower().startswith("qwen3") else {}
    r = client.chat(model=tag, messages=messages, options=opts, keep_alive=keep_alive, **think)
    return keep_lines(r.message.content, ja), r


def unload(client: ollama.Client, tag: str) -> None:
    """Gỡ model khỏi bộ nhớ ngay, trả VRAM cho game."""
    client.generate(model=tag, keep_alive=0)


def tidy(text: str) -> str:
    """Đổi ngoặc Nhật mà VNTL giữ lại thành ngoặc kép tiếng Anh."""
    return text.translate(_QUOTES).strip()
