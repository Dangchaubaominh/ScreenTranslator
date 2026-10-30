"""Bản dịch đã có, lưu trên đĩa: nhãn menu, câu thoại gặp lại thì hiện ngay, kể cả sau khi mở lại app."""

import sqlite3
from pathlib import Path


class TranslationCache:
    """Chỉ dùng trong một luồng (kết nối sqlite gắn với luồng tạo ra nó).

    glossary: dấu các tên riêng / thuật ngữ đã dùng khi dịch (glossary.signature) — sửa glossary thì dịch lại.
    """

    def __init__(self, path: Path | str):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        with self._db:
            self._db.execute("DROP TABLE IF EXISTS translations")  # bảng cũ, chưa có cột glossary
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS translations_v2"
                " (model TEXT, ja TEXT, glossary TEXT, en TEXT, PRIMARY KEY (model, ja, glossary))"
            )

    def get(self, model: str, ja: str, *, glossary: str = "") -> str | None:
        row = self._db.execute(
            "SELECT en FROM translations_v2 WHERE model = ? AND ja = ? AND glossary = ?", (model, ja, glossary)
        ).fetchone()
        return row[0] if row else None

    def put(self, model: str, ja: str, en: str, *, glossary: str = "") -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO translations_v2 VALUES (?, ?, ?, ?)", (model, ja, glossary, en))

    def close(self) -> None:
        self._db.close()
