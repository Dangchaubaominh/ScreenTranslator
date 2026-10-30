"""Bản dịch đã có, lưu trên đĩa: nhãn menu, câu thoại gặp lại thì hiện ngay, kể cả sau khi mở lại app."""

import sqlite3
from pathlib import Path


class TranslationCache:
    """Chỉ dùng trong một luồng (kết nối sqlite gắn với luồng tạo ra nó)."""

    def __init__(self, path: Path | str):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS translations (model TEXT, ja TEXT, en TEXT, PRIMARY KEY (model, ja))"
        )

    def get(self, model: str, ja: str) -> str | None:
        row = self._db.execute("SELECT en FROM translations WHERE model = ? AND ja = ?", (model, ja)).fetchone()
        return row[0] if row else None

    def put(self, model: str, ja: str, en: str) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO translations VALUES (?, ?, ?)", (model, ja, en))

    def close(self) -> None:
        self._db.close()
