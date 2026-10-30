"""Luồng phụ chạy OCR + dịch để giao diện không bị đơ. Kết quả gửi về luồng giao diện qua Qt signal."""

import logging
import queue
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

import ollama
from PIL import Image
from PySide6.QtCore import QObject, Signal

from .cache import TranslationCache
from .config import APP_DIR, OCR_ENGINES, Config
from .layout import group_lines, has_japanese
from .ocr import MangaOcrReader, create_reader
from .translate import tidy, translate, unload

log = logging.getLogger(__name__)
CACHE_PATH = APP_DIR / "translations.sqlite3"
UNTRANSLATED = "(không dịch được)"


@dataclass(frozen=True)
class Item:
    """Một khối chữ và bản dịch của nó (None khi chưa dịch xong).

    box: (trái, trên, phải, dưới) tính bằng pixel trong ảnh đã gửi; None khi dịch chữ gõ tay.
    """

    ja: str
    en: str | None = None
    box: tuple[int, int, int, int] | None = None


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

    def __init__(self, config: Config, cache_path: Path | str = CACHE_PATH):
        super().__init__()
        self._config = config
        self._cache_path = cache_path
        self._jobs: queue.Queue = queue.Queue()
        self._latest = 0
        self._client = ollama.Client()
        self._reader = None
        self._thread = threading.Thread(target=self._run, name="ocr-translate", daemon=True)

    # --- gọi từ luồng giao diện ---

    def start(self) -> None:
        """Gọi sau khi đã nối signal, để không lỡ các thông báo lúc khởi động."""
        self._thread.start()

    def submit_image(self, image: Image.Image) -> int:
        return self._submit("image", image)

    def submit_text(self, ja: str) -> int:
        return self._submit("text", ja)

    def reconfigure(self, config: Config) -> None:
        self._jobs.put((0, "config", config))

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
        if kind == "image":
            if self._reader is None:
                self.failed.emit(job_id, "Chưa nạp được OCR, xem file log.")
                return
            blocks = [b for b in group_lines(self._reader.read_lines(payload)) if has_japanese(b.text)]
            items = [Item(b.text, box=(b.left, b.top, b.right, b.bottom)) for b in blocks]
        else:
            items = [Item(payload.strip())] if has_japanese(payload) else []
        ocr_s = time.perf_counter() - start
        if not items:
            self.failed.emit(job_id, "Không thấy chữ tiếng Nhật trong vùng này.")
            return

        model = self._config.model
        cached = [self._cache.get(model, item.ja) for item in items]
        # khối có sẵn trong cache hiện ngay; sau đó câu dài (thường là lời thoại) trước nhãn ngắn
        order = sorted(range(len(items)), key=lambda i: (cached[i] is None, -len(items[i].ja)))
        for done, i in enumerate(order, start=1):
            if job_id != self._latest:
                log.info("Lượt %d dừng giữa chừng: đã có lượt mới hơn", job_id)
                return
            items[i] = replace(items[i], en=cached[i] or self._translate(items[i].ja))
            self.result.emit(job_id, list(items), done == len(items))
        log.info(
            "Lượt %d: %d khối, OCR %.2fs, dịch %.2fs | %s",
            job_id,
            len(items),
            ocr_s,
            time.perf_counter() - start - ocr_s,
            " | ".join(f"{item.ja} → {item.en}" for item in items),
        )

    def _translate(self, ja: str) -> str:
        try:
            text, _ = translate(
                self._client,
                self._config.model,
                ja,
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
        self._cache.put(self._config.model, ja, en)
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
        self.status.emit("Sẵn sàng", False)

    def _apply(self, config: Config) -> None:
        old, self._config = self._config, config
        if (config.ocr_engine, config.ocr_device) != (old.ocr_engine, old.ocr_device):
            self._reader = None
            try:
                self._load_reader()
            except Exception as e:
                log.exception("Nạp OCR lỗi")
                self.status.emit(f"Nạp OCR lỗi: {e}", True)
        if (config.model, config.ollama_options) != (old.model, old.ollama_options):
            self._unload(old.model)
            self._warm_up()

    def _unload(self, model: str | None = None) -> None:
        try:
            unload(self._client, model or self._config.model)
        except Exception:
            log.exception("Gỡ model lỗi")
