import threading
from dataclasses import replace
from pathlib import Path

import ollama
import pytest
from conftest import wait_until
from PIL import Image

from screen_translator import worker as worker_module
from screen_translator.config import Config
from screen_translator.glossary import Entry
from screen_translator.layout import TextBox
from screen_translator.worker import UNTRANSLATED, Item, Worker, describe_error

WARM_UP = "こんにちは"


class FakeReader:
    """Ảnh giả mang sẵn danh sách dòng chữ trong image.info["lines"]."""

    def read_lines(self, image):
        return image.info.get("lines", [])


@pytest.fixture
def fake(monkeypatch):
    """Thay OCR và Ollama bằng đồ giả; ghi lại các lần gọi."""
    state = {
        "translated": [],
        "glossaries": [],
        "contexts": [],
        "languages": [],
        "unloaded": [],
        "release": threading.Event(),
        "fail": {},
        "slow": set(),
    }
    state["release"].set()

    def fake_translate(client, model, ja, **kwargs):
        if ja == WARM_UP:
            state["release"].wait(5)
        if ja in state["slow"]:
            state["release"].wait(5)
        if ja in state["fail"]:
            raise state["fail"][ja]
        state["translated"].append((model, ja, kwargs["options"]))
        state["glossaries"].append(kwargs.get("glossary"))
        state["contexts"].append((ja, kwargs.get("context")))
        state["languages"].append(kwargs.get("language"))
        return f"「{ja}」 in English", None

    monkeypatch.setattr(worker_module, "OneOcrReader", FakeReader)
    monkeypatch.setattr(worker_module, "translate", fake_translate)
    monkeypatch.setattr(worker_module, "unload", lambda client, model: state["unloaded"].append(model))
    return state


def start(qapp, config: Config | None = None, cache_path=":memory:", glossary_path: Path | None = None):
    # mặc định một file chưa tồn tại: không bao giờ đọc glossary thật của người dùng
    w = Worker(config or Config(), cache_path=cache_path, glossary_path=glossary_path or Path("không-có.txt"))
    events = {"result": [], "failed": [], "status": [], "idle": []}
    w.result.connect(lambda *args: events["result"].append(args))
    w.failed.connect(lambda *args: events["failed"].append(args))
    w.status.connect(lambda *args: events["status"].append(args))
    w.idle.connect(lambda *args: events["idle"].append(args))
    w.start()
    return w, events


def finished(events):
    return [args for args in events["result"] if args[2]]


def screen(*lines: TextBox) -> Image.Image:
    img = Image.new("RGB", (10, 10))
    img.info["lines"] = list(lines)
    return img


DIALOG = TextBox("自分が寝ていた部屋に戻ると、", 410, 810, 1285, 846)
MENU = TextBox("設定", 142, 764, 198, 791)
VERSION = TextBox("ver 1.00", 1847, 986, 1904, 1004)


def test_every_japanese_block_is_translated_and_shown_progressively(qapp, fake):
    w, events = start(qapp)
    job = w.submit_image(screen(MENU, DIALOG, VERSION))
    wait_until(qapp, lambda: finished(events))
    w.stop()
    # các khối giữ thứ tự từ trên xuống; câu dài dịch trước, nhãn ngắn sau; chữ không phải tiếng Nhật bỏ qua
    dialog_en = "“自分が寝ていた部屋に戻ると、” in English"
    first, last = events["result"]
    assert first == (
        job,
        [Item("設定", None, (142, 764, 198, 791)), Item(DIALOG.text, dialog_en, (410, 810, 1285, 846))],
        False,
    )
    assert last[2] is True
    assert [item.en for item in last[1]] == ["“設定” in English", dialog_en]
    assert ("Sẵn sàng", False) in events["status"]
    assert fake["unloaded"] == [Config().model]  # thoát thì trả VRAM


def test_only_the_latest_job_runs(qapp, fake):
    fake["release"].clear()  # giữ luồng phụ ở bước làm nóng cho tới khi gửi xong cả ba lượt
    w, events = start(qapp)
    jobs = [w.submit_text(t) for t in ("一", "二", "三")]
    fake["release"].set()
    wait_until(qapp, lambda: finished(events))
    w.stop()
    assert [args[0] for args in events["result"]] == [jobs[-1]]
    assert [ja for _, ja, _ in fake["translated"]] == [WARM_UP, "三"]


def test_a_newer_job_stops_a_long_one_between_blocks(qapp, fake):
    w, events = start(qapp)
    wait_until(qapp, lambda: ("Sẵn sàng", False) in events["status"])
    fake["release"].clear()
    fake["slow"].add("自分が寝ていた部屋に戻ると、")
    w.submit_image(screen(MENU, DIALOG))
    newer = w.submit_text("猫")
    fake["release"].set()
    wait_until(qapp, lambda: finished(events))
    w.stop()
    assert [args[0] for args in finished(events)] == [newer]
    assert "設定" not in [ja for _, ja, _ in fake["translated"]]  # khối còn lại của lượt cũ không dịch nữa


def test_cache_survives_restart_and_is_shown_first(qapp, fake, tmp_path):
    path = tmp_path / "cache.sqlite3"
    w, events = start(qapp, cache_path=path)
    w.submit_text(" 設定 ")
    wait_until(qapp, lambda: finished(events))
    w.stop()

    w, events = start(qapp, cache_path=path)
    w.submit_image(screen(DIALOG, MENU))
    wait_until(qapp, lambda: finished(events))
    w.stop()
    first = events["result"][0][1]
    assert [item.en is not None for item in first] == [True, False]  # nhãn "設定" có sẵn trong cache hiện ngay
    assert [ja for _, ja, _ in fake["translated"]].count("設定") == 1


def test_dialogue_is_translated_with_the_turns_before_it(qapp, fake):
    w, events = start(qapp)
    w.submit_image(screen(TextBox("おはよう", 410, 810, 600, 846)), dialogue=True)  # vùng tự chọn: khung thoại
    wait_until(qapp, lambda: len(finished(events)) == 1)
    w.submit_image(screen(TextBox("ロード", 1500, 980, 1540, 1000)))  # cả cửa sổ: không dùng, không ghi ngữ cảnh
    wait_until(qapp, lambda: len(finished(events)) == 2)
    w.submit_image(screen(MENU, DIALOG), dialogue=True)  # tên người nói + lời thoại: chung một lượt
    wait_until(qapp, lambda: len(finished(events)) == 3)
    w.submit_image(screen(MENU, DIALOG), dialogue=True)  # Dịch lại cùng câu: không ghi thêm
    wait_until(qapp, lambda: len(finished(events)) == 4)
    w.submit_live(screen(TextBox("また明日", 410, 810, 600, 846)), settled=True)
    wait_until(qapp, lambda: len(finished(events)) == 5)
    w.stop()
    morning = ("おはよう", "“おはよう” in English")
    turn = (f"設定\n{DIALOG.text}", f"“設定” in English\n“{DIALOG.text}” in English")
    assert fake["contexts"][1:] == [
        ("おはよう", []),
        ("ロード", []),
        (DIALOG.text, [morning]),
        ("設定", [morning]),
        ("また明日", [morning, turn]),
    ]


def test_korean_page_is_grouped_and_translated_in_the_chosen_language(qapp, fake):
    w, events = start(qapp, Config(language="ko", model="qwen3.5:4b"))
    w.submit_image(
        screen(TextBox("정말로", 140, 100, 200, 122), TextBox("그렇게 생각해?", 100, 126, 240, 148), VERSION)
    )
    wait_until(qapp, lambda: finished(events))
    w.stop()
    assert [item.ja for item in finished(events)[0][1]] == ["정말로 그렇게 생각해?"]
    assert fake["languages"][-1] == "ko"


def test_switching_language_forgets_the_dialogue_before_it(qapp, fake):
    w, events = start(qapp)
    w.submit_image(screen(TextBox("おはよう", 410, 810, 600, 846)), dialogue=True)
    wait_until(qapp, lambda: len(finished(events)) == 1)
    w.reconfigure(replace(Config(), language="zh"))
    w.submit_image(screen(TextBox("早上好", 410, 810, 600, 846)), dialogue=True)
    wait_until(qapp, lambda: len(finished(events)) == 2)
    w.stop()
    assert fake["contexts"][-1] == ("早上好", [])
    assert fake["languages"][-1] == "zh"
    assert fake["unloaded"] == [Config().model]  # cùng model: không nạp lại, chỉ gỡ lúc thoát


def test_page_scan_marks_speech_bubbles_and_an_empty_page_just_clears(qapp, fake):
    w, events = start(qapp)
    empty = w.submit_page(screen(VERSION))  # cuộn tới tranh không lời
    wait_until(qapp, lambda: finished(events))
    columns = [TextBox("本当に?", 1140, 767, 1164, 862), TextBox("えっ…", 1167, 772, 1191, 846)]
    page = w.submit_page(screen(*columns))
    wait_until(qapp, lambda: len(finished(events)) == 2)
    w.stop()
    assert finished(events)[0] == (empty, [], True) and events["failed"] == []
    assert finished(events)[1] == (
        page,
        [Item("えっ…本当に?", "“えっ…本当に?” in English", (1140, 767, 1191, 862))],
        True,
    )
    assert fake["contexts"][-1] == ("えっ…本当に?", [])  # trang manga: không dính ngữ cảnh khung thoại game


def test_one_bad_block_does_not_spoil_the_rest(qapp, fake):
    fake["fail"]["設定"] = ollama.ResponseError("prediction aborted, token repeat limit reached", 500)
    w, events = start(qapp)
    w.submit_image(screen(DIALOG, MENU))
    wait_until(qapp, lambda: finished(events))
    w.stop()
    assert [item.en for item in finished(events)[0][1]] == [UNTRANSLATED, "“自分が寝ていた部屋に戻ると、” in English"]


def test_errors_are_reported_in_plain_words(qapp, fake):
    fake["fail"]["猫"] = ConnectionError("refused")
    w, events = start(qapp)
    empty = w.submit_image(screen(VERSION))
    wait_until(qapp, lambda: events["failed"])
    job = w.submit_text("猫")
    wait_until(qapp, lambda: len(events["failed"]) == 2)
    w.stop()
    assert events["failed"] == [
        (empty, "Không thấy chữ cần dịch trong vùng này."),
        (job, "Không kết nối được Ollama. Hãy mở Ollama (chưa có thì cài từ ollama.com) rồi thử lại."),
    ]


def test_glossary_reaches_the_model_and_editing_it_retranslates(qapp, fake, tmp_path):
    glossary = tmp_path / "glossary.txt"
    glossary.write_text("霊夢 = Reimu (nữ)\n実績 = Achievements\n", encoding="utf-8")
    room, label = TextBox("霊夢の部屋", 20, 300, 90, 317), TextBox("実績", 1500, 980, 1540, 1000)
    w, events = start(qapp, glossary_path=glossary)
    w.submit_image(screen(room, label, DIALOG))
    wait_until(qapp, lambda: finished(events))
    first = {item.ja: item.en for item in finished(events)[0][1]}
    assert first["霊夢の部屋"] == "“霊夢の部屋” in English"
    assert first["実績"] == "Achievements"  # nhãn trùng hẳn một mục: khỏi gọi model
    assert sorted(ja for _, ja, _ in fake["translated"][1:]) == sorted(["霊夢の部屋", DIALOG.text])
    assert all(g == [Entry("霊夢", "Reimu", "Female"), Entry("実績", "Achievements")] for g in fake["glossaries"][1:])

    glossary.write_text("霊夢 = Reimu Hakurei (nữ)\n", encoding="utf-8")  # sửa tên
    fake["translated"].clear()
    w.submit_image(screen(room, label, DIALOG))
    wait_until(qapp, lambda: len(finished(events)) == 2)
    w.stop()
    # chỉ khối có tên vừa sửa phải dịch lại; câu thoại không có tên lấy từ cache; "実績" giờ phải qua model
    assert sorted(ja for _, ja, _ in fake["translated"]) == ["実績", "霊夢の部屋"]


def test_unreadable_glossary_is_reported_and_translation_goes_on(qapp, fake, tmp_path):
    glossary = tmp_path / "glossary.txt"
    glossary.write_bytes("霊夢 = Reimu".encode("shift_jis"))  # Notepad lưu nhầm kiểu ANSI
    w, events = start(qapp, glossary_path=glossary)
    w.submit_text("霊夢")
    wait_until(qapp, lambda: finished(events))
    w.stop()
    assert any("glossary.txt" in message and is_error for message, is_error in events["status"])
    assert finished(events)[0][1][0].en == "“霊夢” in English"


def run_live(qapp, w, events, image, *, settled):
    """Gửi một lượt live, chờ xong; trả về "idle" hoặc danh sách bản dịch đã hiện."""
    done, idle = len(finished(events)), len(events["idle"])
    job = w.submit_live(image, settled=settled)
    wait_until(qapp, lambda: len(finished(events)) > done or len(events["idle"]) > idle)
    if len(events["idle"]) > idle:
        assert events["idle"][-1] == (job,)
        return "idle"
    assert finished(events)[-1][0] == job
    return [item.en for item in finished(events)[-1][1]]


def test_live_mode_shows_each_new_line_once(qapp, fake):
    w, events = start(qapp)
    typing = TextBox("枕元に何か", 410, 810, 700, 846)
    line = TextBox("枕元に何かが転がっていた。", 410, 810, 900, 846)

    def live(*boxes, settled):
        return run_live(qapp, w, events, screen(*boxes), settled=settled)

    assert live(DIALOG, settled=True) == ["“自分が寝ていた部屋に戻ると、” in English"]
    assert live(DIALOG, settled=True) == "idle"  # mũi tên nhấp nháy: chữ như cũ
    assert live(typing, settled=False) == "idle"  # câu sau đang chạy chữ
    assert live(line, settled=False) == "idle"  # đủ câu nhưng mới đọc được một lần
    assert live(line, settled=False) == ["“枕元に何かが転がっていた。” in English"]  # đọc lần hai vẫn vậy
    assert live(VERSION, settled=True) == []  # khung thoại trống / chuyển cảnh: bỏ bản dịch cũ
    assert live(VERSION, settled=True) == "idle"
    w.reset_live()  # bật lại live mode: hiện lại tình trạng hiện tại
    assert live(VERSION, settled=True) == []
    w.stop()
    assert [ja for _, ja, _ in fake["translated"][1:]] == [DIALOG.text, line.text]  # câu dở không bị dịch


def test_a_line_read_with_an_ocr_slip_is_not_translated_again(qapp, fake):
    w, events = start(qapp)
    line = TextBox("枕元に何かが転がっていた。", 410, 810, 900, 846)
    slip = replace(line, text="枕元に何かが転がつていた。")  # OneOCR đọc っ thành つ
    english = "“枕元に何かが転がっていた。” in English"
    assert run_live(qapp, w, events, screen(line), settled=True) == [english]
    assert run_live(qapp, w, events, screen(slip), settled=True) == "idle"  # vẫn câu đang hiện: bản dịch khỏi nháy
    w.submit_page(screen(slip))  # cuộn trang manga rồi đọc lại bóng thoại: dùng luôn bản dịch vừa có
    wait_until(qapp, lambda: len(finished(events)) == 2)
    w.stop()
    assert [item.en for item in finished(events)[-1][1]] == [english]
    assert [ja for _, ja, _ in fake["translated"][1:]] == [line.text]


def test_reports_when_oneocr_is_missing(qapp, fake, monkeypatch):
    def broken():
        raise RuntimeError("không tìm thấy OneOCR")

    monkeypatch.setattr(worker_module, "OneOcrReader", broken)
    w, events = start(qapp)
    wait_until(qapp, lambda: ("Sẵn sàng", False) in events["status"])
    job = w.submit_image(screen(DIALOG))
    wait_until(qapp, lambda: events["failed"])
    w.stop()
    assert any("không tìm thấy OneOCR" in message and is_error for message, is_error in events["status"])
    assert events["failed"] == [(job, "Chưa nạp được OCR, xem file log.")]


def test_reconfigure_switches_model(qapp, fake):
    w, events = start(qapp)
    w.reconfigure(replace(Config(), model="qwen2.5:3b", profile="heavy"))
    job = w.submit_text("猫")
    wait_until(qapp, lambda: finished(events))
    w.stop()
    assert fake["unloaded"] == [Config().model, "qwen2.5:3b"]
    assert fake["translated"][-1] == ("qwen2.5:3b", "猫", {"num_gpu": 0})
    assert finished(events)[0][0] == job


def test_missing_model_message():
    error = ollama.ResponseError("model not found", 404)
    assert describe_error(error, "abc:1b") == "Chưa có model abc:1b. Chạy lệnh: ollama pull abc:1b"
