"""Luồng phụ chạy OCR + dịch để giao diện không bị đơ. Kết quả gửi về luồng giao diện qua Qt signal."""

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

import ollama
from PIL import Image
from PySide6.QtCore import QObject, Signal

from .cache import TranslationCache
from .config import APP_DIR, GLOSSARY_PATH, OCR_ENGINES, Config
from .glossary import Entry, Glossary, exact, relevant, signature
from .layout import group_lines, has_japanese
from .ocr import MangaOcrReader, create_reader
from .translate import tidy, translate, unload

log = logging.getLogger(__name__)
CACHE_PATH = APP_DIR / "translations.sqlite3"
UNTRANSLATED = "(không dịch được)"
READY = "Sẵn sàng"  # trạng thái khi đã nạp xong OCR và model dịch
CONTEXT_TURNS = 4  # số lượt thoại ngay trước gửi kèm khi dịch, để model hiểu mạch hội thoại
DIALOGUE = ("live", "dialogue")  # lượt dịch khung thoại (live mode, vùng tự chọn): dùng và ghi nhớ ngữ cảnh


@dataclass(frozen=True)
class Item:
    """Một khối chữ và bản dịch của nó (None khi chưa dịch xong).

    box: (trái, trên, phải, dưới) tính bằng pixel trong ảnh đã gửi; None khi dịch chữ gõ tay.
    vertical: chữ dọc (bóng thoại manga), khung bản dịch phải nới ngang ra mới đủ chỗ cho chữ tiếng Anh.
    """

    ja: str
    en: str | None = None
    box: tuple[int, int, int, int] | None = None
    vertical: bool = False


def describe_error(error: Exception, model: str) -> str:
    """Thông báo lỗi dễ hiểu cho người dùng."""
    if isinstance(error, ConnectionError):
        return "Không kết nối được Ollama. Hãy mở Ollama rồi thử lại."
    if isinstance(error, ollama.ResponseError) and error.status_code == 404:
        return f"Chưa có model {model}. Chạy lệnh: ollama pull {model}"
    return str(error)


class Worker(QObject):
    # mã lượt, danh sách Item, đã dịch xong hết chưa — phát sau mỗi khối dịch xong để hiện dần
    result = Signal(int, object, bool)
    failed = Signal(int, str)  # mã lượt, thông báo lỗi
    status = Signal(str, bool)  # trạng thái, có phải lỗi không
    idle = Signal(int)  # lượt live mode xong mà không có gì mới để hiện

    def __init__(self, config: Config, cache_path: Path | str = CACHE_PATH, glossary_path: Path = GLOSSARY_PATH):
        super().__init__()
        self._config = config
        self._cache_path = cache_path
        self._glossary = Glossary(glossary_path)
        self._jobs: queue.Queue = queue.Queue()
        self._latest = 0
        self._client = ollama.Client()
        self._reader = None
        # live mode: chữ đang hiện trên overlay, và chữ đọc được ở lần trước lúc hình còn đang đổi
        self._live_shown: tuple[str, ...] | None = None
        self._live_pending: tuple[str, ...] | None = None
        # các lượt thoại vừa hiện (chữ Nhật, bản dịch), mỗi lượt là cả khung thoại (tên người nói + lời thoại)
        self._context: deque[tuple[str, str]] = deque(maxlen=CONTEXT_TURNS)
        self._thread = threading.Thread(target=self._run, name="ocr-translate", daemon=True)

    # --- gọi từ luồng giao diện ---

    def start(self) -> None:
        """Gọi sau khi đã nối signal, để không lỡ các thông báo lúc khởi động."""
        self._thread.start()

    def submit_image(self, image: Image.Image, *, dialogue: bool = False) -> int:
        """dialogue: vùng tự chọn (thường là khung thoại), dịch kèm ngữ cảnh. Cả cửa sổ (menu, nút…) thì không."""
        return self._submit("dialogue" if dialogue else "image", image)

    def submit_text(self, ja: str) -> int:
        return self._submit("text", ja)

    def submit_page(self, image: Image.Image) -> int:
        """Live mode cả cửa sổ (trang manga trên web): đọc lại cả trang sau khi cuộn / lật trang.

        Như dịch cả cửa sổ, nhưng không có chữ (cuộn tới tranh không lời) thì chỉ ẩn bản dịch, không báo lỗi.
        """
        return self._submit("page", image)

    def submit_live(self, image: Image.Image, *, settled: bool) -> int:
        """Ảnh live mode. settled=False: hình chưa đứng yên, chỉ dịch khi chữ giống lần đọc trước."""
        return self._submit("live", (image, settled))

    def reset_live(self) -> None:
        """Vừa bật live mode: lượt live đầu tiên luôn hiện bản dịch, kể cả khi chữ không đổi."""
        self._jobs.put((0, "live-reset", None))

    def reconfigure(self, config: Config) -> None:
        self._jobs.put((0, "config", config))

    def set_paused(self, paused: bool) -> None:
        """Tạm dừng: bỏ lượt đang dịch dở và gỡ model dịch khỏi VRAM cho game. Tiếp tục: nạp lại model."""
        if paused:
            self._latest += 1  # lượt đang dịch dở dừng ở khối kế tiếp
        self._jobs.put((0, "pause" if paused else "resume", None))

    def stop(self) -> None:
        self._latest += 1  # lượt đang dịch dở dừng ở khối kế tiếp
        self._jobs.put(None)
        self._thread.join(timeout=10)

    def _submit(self, kind: str, payload) -> int:
        self._latest += 1
        self._jobs.put((self._latest, kind, payload))
        return self._latest

    # --- chạy trong luồng phụ ---

    def _run(self) -> None:
        self._cache = TranslationCache(self._cache_path)
        try:
            self._load_reader()
        except Exception as e:
            log.exception("Nạp OCR lỗi")
            self.status.emit(f"Nạp OCR lỗi: {e}", True)
        self._warm_up()
        while (item := self._jobs.get()) is not None:
            job_id, kind, payload = item
            if kind == "config":
                self._apply(payload)
            elif kind == "live-reset":
                self._live_shown = self._live_pending = None
            elif kind == "pause":
                self._unload()
            elif kind == "resume":
                self._warm_up()
            elif job_id == self._latest:  # bỏ qua các lượt cũ khi người dùng đã bấm lượt mới hơn
                try:
                    self._process(job_id, kind, payload)
                except Exception as e:
                    log.exception("Lượt %d lỗi", job_id)
                    self.failed.emit(job_id, describe_error(e, self._config.model))
        self._unload()
        self._cache.close()

    def _process(self, job_id: int, kind: str, payload) -> None:
        start = time.perf_counter()
        if kind == "text":
            items = [Item(payload.strip())] if has_japanese(payload) else []
        elif self._reader is None:
            self.failed.emit(job_id, "Chưa nạp được OCR, xem file log.")
            return
        else:
            image = payload[0] if kind == "live" else payload
            blocks = [b for b in group_lines(self._reader.read_lines(image)) if has_japanese(b.text)]
            items = [Item(b.text, box=(b.left, b.top, b.right, b.bottom), vertical=b.vertical) for b in blocks]
        ocr_s = time.perf_counter() - start
        key = tuple(item.ja for item in items)
        if kind == "live":
            settled = payload[1]
            if key == self._live_shown or (not settled and key != self._live_pending):
                # chữ không đổi, hoặc hình còn đang đổi mà chữ khác lần đọc trước (câu đang chạy dở): chờ tiếp
                self._live_pending = key
                self.idle.emit(job_id)
                return
            if not items:  # khung thoại trống / đã chuyển cảnh: bỏ bản dịch cũ đi
                self._live_shown = key
                self.result.emit(job_id, [], True)
                return
        if not items:
            if kind == "page":  # cuộn tới chỗ không có chữ: bỏ bản dịch cũ đi
                self.result.emit(job_id, [], True)
            else:
                self.failed.emit(job_id, "Không thấy chữ tiếng Nhật trong vùng này.")
            return

        glossary = self._read_glossary()
        context = list(self._context) if kind in DIALOGUE else []
        known = [self._known(item.ja, glossary) for item in items]
        # khối có sẵn bản dịch hiện ngay; sau đó câu dài (thường là lời thoại) trước nhãn ngắn
        order = sorted(range(len(items)), key=lambda i: (known[i] is None, -len(items[i].ja)))
        for done, i in enumerate(order, start=1):
            if job_id != self._latest:
                log.info("Lượt %d dừng giữa chừng: đã có lượt mới hơn", job_id)
                return
            items[i] = replace(items[i], en=known[i] or self._translate(items[i].ja, glossary, context))
            self.result.emit(job_id, list(items), done == len(items))
        # chỉ ghi nhận khi đã dịch hết: lượt bị ngắt giữa chừng thì lượt live sau dịch tiếp
        if kind == "live":
            self._live_shown = key
        if kind in DIALOGUE:
            self._remember(items)
        log.info(
            "Lượt %d: %d khối, OCR %.2fs, dịch %.2fs | %s",
            job_id,
            len(items),
            ocr_s,
            time.perf_counter() - start - ocr_s,
            " | ".join(f"{item.ja} → {item.en}" for item in items),
        )

    def _read_glossary(self) -> list[Entry]:
        try:
            return self._glossary.entries()
        except (OSError, UnicodeDecodeError) as e:
            log.warning("Không đọc được glossary: %s", e)
            self.status.emit(f"Không đọc được {self._glossary.path.name} (cần lưu dạng UTF-8): {e}", True)
            return []

    def _known(self, ja: str, glossary: list[Entry]) -> str | None:
        """Bản dịch có ngay: khai sẵn trong glossary, hoặc đã dịch trước đây với đúng các tên riêng hiện tại."""
        terms = relevant(glossary, ja)
        return exact(terms, ja) or self._cache.get(self._config.model, ja, glossary=signature(terms))

    def _remember(self, items: list[Item]) -> None:
        """Cả khung thoại vừa hiện thành một lượt ngữ cảnh cho câu sau; bấm Dịch lại cùng câu thì không ghi thêm."""
        shown = [item for item in items if item.en != UNTRANSLATED]
        turn = ("\n".join(item.ja for item in shown), "\n".join(item.en for item in shown))
        if shown and turn not in self._context:
            self._context.append(turn)

    def _translate(self, ja: str, glossary: list[Entry], context: list[tuple[str, str]]) -> str:
        try:
            text, _ = translate(
                self._client,
                self._config.model,
                ja,
                glossary=glossary,
                context=context,
                options=self._config.ollama_options,
                keep_alive=self._config.keep_alive,
            )
        except ollama.ResponseError as e:
            if e.status_code == 404:  # thiếu model: cả lượt đều hỏng, báo lên
                raise
            log.warning("Không dịch được %r: %s", ja, e)  # vd. model lặp chữ bị Ollama ngắt; bỏ qua khối này
            return UNTRANSLATED
        en = tidy(text)
        if not en:
            return UNTRANSLATED
        self._cache.put(self._config.model, ja, en, glossary=signature(relevant(glossary, ja)))
        return en

    def _load_reader(self) -> None:
        engine, device = self._config.ocr_engine, self._config.ocr_device
        self.status.emit(f"Đang nạp {OCR_ENGINES[engine].split(' — ')[0]}…", False)
        start = time.perf_counter()
        try:
            self._reader = create_reader(engine, device)
        except Exception as e:
            if engine == "manga-ocr":
                raise
            log.exception("OneOCR lỗi, chuyển sang manga-ocr")
            self.status.emit(f"OneOCR không dùng được ({e}), chuyển sang manga-ocr", True)
            self._reader = MangaOcrReader(device)
        log.info("Nạp %s mất %.1fs", self._reader.name, time.perf_counter() - start)

    def _warm_up(self) -> None:
        """Nạp model dịch vào bộ nhớ ngay, để lần dịch đầu không phải chờ."""
        self.status.emit("Đang nạp model dịch…", False)
        try:
            translate(
                self._client,
                self._config.model,
                "こんにちは",
                options=self._config.ollama_options,
                keep_alive=self._config.keep_alive,
            )
        except Exception as e:
            log.exception("Làm nóng model lỗi")
            self.status.emit(describe_error(e, self._config.model), True)
            return
        self.status.emit(READY, False)

    def _apply(self, config: Config) -> None:
        old, self._config = self._config, config
        new_reader = (config.ocr_engine, config.ocr_device) != (old.ocr_engine, old.ocr_device)
        if new_reader:
            self._reader = None
            try:
                self._load_reader()
            except Exception as e:
                log.exception("Nạp OCR lỗi")
                self.status.emit(f"Nạp OCR lỗi: {e}", True)
                new_reader = False  # không báo "Sẵn sàng" đè lên lỗi
        if (config.model, config.ollama_options) != (old.model, old.ollama_options):
            self._unload(old.model)
            self._warm_up()
        elif new_reader:
            self.status.emit(READY, False)

    def _unload(self, model: str | None = None) -> None:
        try:
            unload(self._client, model or self._config.model)
        except Exception:
            log.exception("Gỡ model lỗi")
