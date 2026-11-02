"""Bản dịch đã có, lưu trên đĩa: nhãn menu, câu thoại gặp lại thì hiện ngay, kể cả sau khi mở lại app."""

import sqlite3
from collections import OrderedDict
from pathlib import Path

from .layout import similar

RECENT = 100  # số bản dịch vừa dùng được nhớ trong RAM, để câu OCR đọc lệch vài chữ vẫn lấy lại được


class TranslationCache:
    """Chỉ dùng trong một luồng (kết nối sqlite gắn với luồng tạo ra nó).

    glossary: dấu các tên riêng / thuật ngữ đã dùng khi dịch (glossary.signature) — sửa glossary thì dịch lại.
    Không có đúng câu đó thì dùng bản dịch của một câu vừa gặp gần giống hệt (layout.similar): OCR đọc lệch.
    """

    def __init__(self, path: Path | str):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        with self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS translations_v2"
                " (model TEXT, ja TEXT, glossary TEXT, en TEXT, PRIMARY KEY (model, ja, glossary))"
            )
        self._recent: OrderedDict[tuple[str, str, str], str] = OrderedDict()  # (model, chữ Nhật, glossary) → bản dịch

    def get(self, model: str, ja: str, *, glossary: str = "") -> str | None:
        row = self._db.execute(
            "SELECT en FROM translations_v2 WHERE model = ? AND ja = ? AND glossary = ?", (model, ja, glossary)
        ).fetchone()
        if row:
            self._remember(model, ja, glossary, row[0])
            return row[0]
        # vd. cuộn trang manga rồi đọc lại bóng thoại cũ, OCR ra つ thay cho っ: vẫn là câu vừa dịch
        for (m, seen, g), en in reversed(self._recent.items()):
            if (m, g) == (model, glossary) and similar(ja, seen):
                return en
        return None

    def put(self, model: str, ja: str, en: str, *, glossary: str = "") -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO translations_v2 VALUES (?, ?, ?, ?)", (model, ja, glossary, en))
        self._remember(model, ja, glossary, en)

    def _remember(self, model: str, ja: str, glossary: str, en: str) -> None:
        self._recent[(model, ja, glossary)] = en
        self._recent.move_to_end((model, ja, glossary))
        if len(self._recent) > RECENT:
            self._recent.popitem(last=False)

    def close(self) -> None:
        self._db.close()
