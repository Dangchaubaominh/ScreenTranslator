"""Tên riêng và thuật ngữ người dùng khai báo, để model dịch nhất quán (霊夢 → Reimu, không phải "a dream").

File glossary.txt, mỗi dòng một mục:
    霊夢 = Reimu (nữ)     tên người: ghi (nữ) / (nam) để bản dịch dùng đúng she / he
    幻想郷 = Gensokyo      thuật ngữ
Chỉ các mục có mặt trong đoạn đang dịch mới được đưa vào prompt: model nhỏ, prompt càng gọn càng tốt.
"""

import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .i18n import tr

log = logging.getLogger(__name__)
GENDERS = {"nữ": "Female", "nam": "Male", "female": "Female", "male": "Male"}
GENDER_WORDS = {"Female": "nữ", "Male": "nam"}  # ghi vào file, theo ngôn ngữ giao diện
# "Save (Quick)" không phải giới tính nên cả cụm là bản dịch; chấp nhận cả dấu ＝ gõ bằng bộ gõ tiếng Nhật
_LINE = re.compile(r"(?P<ja>[^=＝]+?)\s*[=＝]\s*(?P<en>.+?)(?:\s*\((?P<gender>nữ|nam|female|male)\))?", re.IGNORECASE)

TEMPLATE = """\
# Tên riêng và thuật ngữ dùng khi dịch. Sửa xong lưu lại (UTF-8) là lần dịch sau dùng ngay.
#
# Tên người:  chữ gốc = tên tiếng Anh (nữ)     ghi (nữ) hoặc (nam) để bản dịch dùng đúng she / he
# Thuật ngữ:  chữ gốc = tiếng Anh
# Khối chữ trùng hẳn một mục (nhãn menu, tên phòng…) thì dùng luôn bản dịch ở đây, không qua model.
#
# Ví dụ (bỏ dấu # ở đầu dòng để dùng):
# 雪菜 = Yukina (nữ)
# 実績 = Achievements
"""


@dataclass(frozen=True)
class Entry:
    ja: str
    en: str
    gender: str | None = None  # "Female" / "Male" với tên người; None với thuật ngữ


def parse(text: str) -> list[Entry]:
    """Đọc nội dung glossary.txt. Một chữ gốc khai hai lần thì lấy dòng sau."""
    found: dict[str, Entry] = {}
    for number, line in enumerate(unicodedata.normalize("NFC", text).splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not (m := _LINE.fullmatch(line)):
            log.warning("Glossary dòng %d bỏ qua, cần dạng 'chữ gốc = tiếng Anh': %s", number, line)
            continue
        gender = GENDERS[m["gender"].lower()] if m["gender"] else None
        found[m["ja"]] = Entry(m["ja"], m["en"], gender)
    return list(found.values())


def relevant(entries: Sequence[Entry], text: str) -> list[Entry]:
    return [e for e in entries if e.ja in text]


def exact(entries: Sequence[Entry], text: str) -> str | None:
    """Bản dịch khai sẵn khi cả khối chữ chính là một mục."""
    text = text.strip()
    return next((e.en for e in entries if e.ja == text), None)


def vntl_metadata(entries: Sequence[Entry]) -> str:
    """Các dòng cho phần <<METADATA>> của prompt VNTL.

    Tên người theo mẫu trong model card; thuật ngữ khai như nhân vật thì model bịa ("Achievements is a man…")
    nên dùng dòng [term], đo thử trên game thật thấy model làm theo.
    """
    return "".join(
        f"[character] Name: {e.en} ({e.ja}) | Gender: {e.gender}\n" if e.gender else f"[term] {e.ja}: {e.en}\n"
        for e in entries
    )


def substitute(text: str, entries: Sequence[Entry]) -> str:
    """Thay thẳng chữ gốc bằng tiếng Anh, cho model không có chỗ khai báo tên. Mục dài thay trước."""
    for e in sorted(entries, key=lambda e: -len(e.ja)):
        text = text.replace(e.ja, e.en)
    return text


def signature(entries: Sequence[Entry]) -> str:
    """Dấu của các mục đã dùng khi dịch: sửa glossary thì bản dịch cũ trong cache không còn khớp."""
    return "\n".join(f"{e.ja}={e.en}|{e.gender or ''}" for e in entries)


def ensure_file(path: Path) -> Path:
    """Tạo file kèm hướng dẫn nếu chưa có, để người dùng mở ra sửa."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tr(TEMPLATE), encoding="utf-8")
    return path


def clean(text: str) -> str:
    """Chuẩn hóa chữ người dùng gõ giống parse(), để cùng chữ thì so ra bằng nhau."""
    return unicodedata.normalize("NFC", text.strip())


def valid_ja(ja: str) -> bool:
    """Chữ gốc ghi được thành một dòng của file: không có dấu bằng, không giống dòng ghi chú."""
    return not (ja.startswith("#") or "=" in ja or "＝" in ja)


def format_line(entry: Entry) -> str:
    gender = f" ({tr(GENDER_WORDS[entry.gender])})" if entry.gender else ""
    return f"{entry.ja} = {entry.en}{gender}"


def update_file(path: Path, before: Sequence[Entry], after: Sequence[Entry]) -> None:
    """Ghi vào file phần đã đổi từ `before` sang `after`; không đổi gì thì không đụng tới file.

    Ghi chú, dòng sai mẫu và các mục không đổi (kể cả mục vừa thêm bằng Notepad) giữ nguyên chỗ cũ. Mục mới nằm cuối file.
    """
    removed = {e.ja for e in before} - {e.ja for e in after}
    changed = {e.ja: e for e in after if e not in before}
    if not removed and not changed:
        return
    lines, written = [], set()
    for line in unicodedata.normalize("NFC", ensure_file(path).read_text(encoding="utf-8-sig")).splitlines():
        stripped = line.strip()
        m = None if stripped.startswith("#") else _LINE.fullmatch(stripped)
        ja = m["ja"] if m else None
        if ja in removed or ja in written:  # mục khai hai lần: dòng sau không được đè lên bản vừa sửa
            continue
        if ja in changed:
            line = format_line(changed[ja])
            written.add(ja)
        lines.append(line)
    lines += [format_line(entry) for ja, entry in changed.items() if ja not in written]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Glossary:
    """Đọc lại file mỗi khi file đổi, để sửa trong Notepad xong là lượt dịch sau dùng ngay."""

    def __init__(self, path: Path):
        self.path = path
        self._stamp: tuple[int, int] | None = None
        self._entries: list[Entry] = []

    def entries(self) -> list[Entry]:
        """Lỗi đọc file (vd. không phải UTF-8) thì ném ra cho nơi gọi báo người dùng."""
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            self._stamp, self._entries = None, []
            return []
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp != self._stamp:
            self._entries = parse(self.path.read_text(encoding="utf-8-sig"))  # Notepad có thể thêm BOM
            self._stamp = stamp
            log.info("Nạp %d mục từ %s", len(self._entries), self.path)
        return self._entries
