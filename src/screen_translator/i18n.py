"""Ngôn ngữ giao diện. Chữ trong code là tiếng Việt, đồng thời là khóa để tra bản tiếng Anh trong EN."""

UI_LANGUAGES = {"vi": "Tiếng Việt", "en": "English"}  # mã → tên hiện ở Cài đặt, viết bằng chính ngôn ngữ đó

_language = "vi"


def set_language(language: str) -> None:
    global _language
    _language = language


def tr(text: str, /, **values) -> str:
    """Chữ theo ngôn ngữ giao diện, điền `values` vào các chỗ {tên}. Chữ không có trong EN thì giữ nguyên."""
    translated = EN.get(text, text) if _language == "en" else text
    return translated.format(**values) if values else translated


EN = {
    # cài đặt
    "Game nhẹ — dịch bằng card đồ họa, nhanh hơn": "Light game: translate on the graphics card, faster",
    "Game nặng — dịch bằng CPU, nhường card đồ họa cho game": "Heavy game: translate on the CPU, leave the graphics card to the game",
    "Tiếng Nhật": "Japanese",
    "Tiếng Trung": "Chinese",
    "Tiếng Hàn": "Korean",
    "Thêm vào menu Start": "Add to the Start menu",
    "Tạo shortcut trên Desktop": "Create a desktop shortcut",
    "Tự chạy khi mở Windows": "Start with Windows",
    "Dịch chữ Nhật, Trung, Hàn trên màn hình": "Translate on-screen Japanese, Chinese and Korean",
    # phím tắt
    "Chọn vùng mới và dịch": "Select a new region and translate",
    "Dịch cả cửa sổ game": "Translate the whole game window",
    "Dịch lại vùng trước": "Translate the previous region again",
    "Live mode: tự dịch câu mới trong vùng": "Live mode: translate new lines in the region automatically",
    "Ẩn / hiện bản dịch": "Hide / show the translation",
    "Sửa chữ OCR gần nhất": "Edit the latest OCR text",
    "phím bổ trợ không hợp lệ: {name!r} (dùng Ctrl, Alt, Shift, Win)": "invalid modifier key: {name!r} (use Ctrl, Alt, Shift, Win)",
    "cần ít nhất một phím Ctrl / Alt / Shift / Win": "needs at least one of Ctrl / Alt / Shift / Win",
    "phím không hợp lệ: {key!r} (dùng A–Z, 0–9, F1–F12, Space…)": "invalid key: {key!r} (use A–Z, 0–9, F1–F12, Space…)",
    "{text}: chương trình khác đang dùng phím tắt này": "{text}: another program is using this hotkey",
    # tên riêng
    "nữ": "female",
    "nam": "male",
    """\
# Tên riêng và thuật ngữ dùng khi dịch. Sửa xong lưu lại (UTF-8) là lần dịch sau dùng ngay.
#
# Tên người:  chữ gốc = tên tiếng Anh (nữ)     ghi (nữ) hoặc (nam) để bản dịch dùng đúng she / he
# Thuật ngữ:  chữ gốc = tiếng Anh
# Khối chữ trùng hẳn một mục (nhãn menu, tên phòng…) thì dùng luôn bản dịch ở đây, không qua model.
#
# Ví dụ (bỏ dấu # ở đầu dòng để dùng):
# 雪菜 = Yukina (nữ)
# 実績 = Achievements
""": """\
# Names and terms used when translating. Save this file as UTF-8 and the next translation uses it.
#
# People:  original text = English name (female)     write (female) or (male) so the translation uses she / he
# Terms:   original text = English
# Text that exactly matches an entry (a menu label, a room name…) uses the translation here, not the model.
#
# Examples (remove the # at the start of a line to use it):
# 雪菜 = Yukina (female)
# 実績 = Achievements
""",
    # OCR và dịch
    "không tìm thấy OneOCR (cần Snipping Tool bản mới của Windows 11)": "OneOCR not found (needs a recent Snipping Tool on Windows 11)",
    "(không dịch được)": "(could not translate)",
    "Sẵn sàng": "Ready",
    "Không kết nối được Ollama. Hãy mở Ollama (chưa có thì cài từ ollama.com) rồi thử lại.": "Could not connect to Ollama. Open Ollama (or install it from ollama.com) and try again.",
    "Chưa có model {model}. Chạy lệnh: ollama pull {model}": "The model {model} is not installed. Run: ollama pull {model}",
    "Chưa nạp được OCR, xem file log.": "OCR is not loaded, see the log file.",
    "Không thấy chữ cần dịch trong vùng này.": "No text to translate in this region.",
    "Không đọc được {file} (cần lưu dạng UTF-8): {error}": "Could not read {file} (it must be saved as UTF-8): {error}",
    "Đang nạp OneOCR…": "Loading OneOCR…",
    "Nạp OCR lỗi: {error}": "Could not load OCR: {error}",
    "Đang nạp model dịch…": "Loading the translation model…",
    # khay hệ thống và thông báo
    "Đang khởi động…": "Starting…",
    "Thanh điều khiển": "Control panel",
    "Tạm dừng": "Pause",
    "Tên riêng, thuật ngữ…": "Names and terms…",
    "Cài đặt…": "Settings…",
    "Hướng dẫn…": "Guide…",
    "Thoát": "Quit",
    "Không đăng ký được phím tắt:": "Could not register hotkeys:",
    "Đang tạm dừng": "Paused",
    " · live mode đang bật": " · live mode is on",
    "Chưa có vùng nào: bấm Chọn vùng ({key}) rồi kéo quanh chữ cần dịch.": "No region yet: click Select region ({key}), then drag around the text.",
    "Đang dịch…": "Translating…",
    "Đang đọc chữ…": "Reading text…",
    "Đã tắt live mode.": "Live mode is off.",
    "Chọn vùng hộp thoại trước (Chọn vùng, {select}), rồi bấm Live ({live}).": "Select the dialogue box first (Select region, {select}), then click Live ({live}).",
    "Windows này không cho giấu bản dịch khỏi ảnh chụp, nên không bật được live mode.": "This version of Windows cannot hide the translation from screenshots, so live mode cannot be turned on.",
    "Đã bật live mode: câu mới trong vùng đã chọn sẽ tự được dịch. Bấm Esc để tắt.": "Live mode is on: new lines in the selected region are translated automatically. Press Esc to turn it off.",
    "Đã bật live mode cả cửa sổ: cuộn hay lật trang là tự dịch lại. Bấm Esc để tắt.": "Whole-window live mode is on: scrolling or turning the page translates again. Press Esc to turn it off.",
    "Đã tạm dừng: phím tắt trả lại cho game, model dịch đã gỡ khỏi VRAM.": "Paused: the hotkeys are back with the game and the translation model has left VRAM.",
    "Tiếp tục dịch.": "Translating again.",
    "Không tạo được shortcut: {error}": "Could not create the shortcut: {error}",
    "ScreenTranslator đang chạy rồi.": "ScreenTranslator is already running.",
    # thanh điều khiển, màn chọn vùng
    "Chọn vùng": "Select region",
    "Cả cửa sổ": "Whole window",
    "Dịch lại": "Translate again",
    "Thêm: tạm dừng, sửa chữ OCR, tên riêng, cài đặt, hướng dẫn, thoát": "More: pause, edit OCR text, names, settings, guide, quit",
    "Ẩn thanh này (bấm icon 訳 ở khay hệ thống để hiện lại)": "Hide this panel (click the 訳 icon in the system tray to show it again)",
    "Kéo để dời thanh": "Drag to move the panel",
    "Độ trong suốt của nền bản dịch": "Transparency of the translation background",
    "Trong suốt": "Transparency",
    "Xếp thanh nằm ngang": "Lay the panel out horizontally",
    "Xếp thanh thành cột dọc": "Stack the panel vertically",
    "Kéo chuột để khoanh vùng chữ  ·  Esc hoặc chuột phải để huỷ": "Drag around the text  ·  Esc or right-click to cancel",
    # hộp thoại sửa chữ OCR
    "Sửa chữ OCR — ScreenTranslator": "Edit OCR text — ScreenTranslator",
    "Chữ gốc": "Original text",
    "Tên đúng, tiếng Anh": "Correct name, in English",
    "Copy chữ gốc": "Copy original",
    "Copy bản dịch": "Copy translation",
    "Chữ gốc (sửa được nếu OCR đọc sai):": "Original text (edit it if OCR misread it):",
    "Bản dịch:": "Translation:",
    "Tên dịch sai: bôi đen tên đó ở ô chữ gốc, gõ tên đúng rồi Enter.": "Name translated wrongly: select it in the original text, type the correct name, then press Enter.",
    "Chữ gốc không được có dấu = hay bắt đầu bằng #.": "The original text cannot contain = or start with #.",
    "Không ghi được {file} (cần lưu dạng UTF-8): {error}": "Could not write {file} (it must be saved as UTF-8): {error}",
    "Đã lưu vào tên riêng: {line}": "Saved to names: {line}",
    # cửa sổ chính: chung
    "Hướng dẫn": "Guide",
    "Tên riêng": "Names",
    "Phím tắt": "Hotkeys",
    "Cài đặt": "Settings",
    "Chỉnh màu": "Appearance",
    "Dịch chữ Nhật, Trung, Hàn, chạy hoàn toàn trên máy.": "Translates Japanese, Chinese and Korean, entirely on your computer.",
    "Bắt đầu": "Start",
    "Lưu": "Save",
    "Hủy": "Cancel",
    "Bạn đã sửa tên riêng nhưng chưa lưu.": "You changed the names but have not saved them.",
    "Không lưu": "Don't save",
    "Ở lại": "Stay",
    "Hai hành động đang dùng chung một phím tắt.": "Two actions are using the same hotkey.",
    "Chưa chọn model dịch.": "No translation model selected.",
    "Không lưu được tên riêng: {error}": "Could not save the names: {error}",
    # trang Hướng dẫn
    "Chuẩn bị một lần": "One-time setup",
    "Cài {link}. Đã cài rồi thì mở nó lên.": "Install {link}. If it is already installed, open it.",
    "Mở Terminal, chạy lệnh tải model dịch (khoảng 2–3 GB):<br>{pull}": "Open Terminal and run this command to download the translation model (about 2–3 GB):<br>{pull}",
    "Bấm <b>Bắt đầu</b> rồi dịch thử.": "Click <b>Start</b> and try a translation.",
    "Mẹo": "Tips",
    "<b>Esc</b> xóa bản dịch đang hiện (bấm lần nữa thì game nhận Esc).": "<b>Esc</b> clears the translation on screen (press it again and the game receives Esc).",
    "Xem chữ gốc: kéo thanh <b>Trong suốt</b>, hoặc bấm nút ẩn / hiện bản dịch trên thanh.": "To see the original text: drag the <b>Transparency</b> slider, or click the hide / show button on the panel.",
    "Tên dịch sai: menu <b>…</b> → <i>Sửa chữ OCR gần nhất</i>, bôi đen tên rồi gõ tên đúng.": "Name translated wrongly: menu <b>…</b> → <i>Edit the latest OCR text</i>, select the name, then type the correct one.",
    "Chơi mà không dịch: menu <b>…</b> → <i>Tạm dừng</i> trả phím tắt cho game, gỡ model khỏi card đồ họa.": "Playing without translating: menu <b>…</b> → <i>Pause</i> gives the hotkeys back to the game and removes the model from the graphics card.",
    "Icon <b>訳</b> ở khay hệ thống: chuột trái ẩn / hiện thanh điều khiển, chuột phải mở menu.": "The <b>訳</b> icon in the system tray: left-click hides or shows the control panel, right-click opens the menu.",
    "Mở app từ menu Start, Desktop hay tự chạy cùng Windows: trang <b>Cài đặt</b> → <i>Mở app</i>.": "To open the app from the Start menu or desktop, or start it with Windows: <b>Settings</b> page → <i>Opening the app</i>.",
    "đang nạp": "loading",
    "sẵn sàng": "ready",
    "tạm dừng": "paused",
    "Màu icon: {legend}. Cần mở Ollama để dịch.": "Icon color: {legend}. Ollama must be open to translate.",
    "Mọi nút đều có trên thanh điều khiển nổi; phím tắt dùng được cả lúc đang chơi.": "Every action has a button on the floating control panel; hotkeys also work while you play.",
    "<b>Chọn vùng</b> rồi kéo chuột quanh khung thoại.": "<b>Select region</b>, then drag around the dialogue box.",
    "<b>Live</b>: câu mới tự được dịch, thanh điều khiển tự ẩn. <b>Esc</b> để tắt.": "<b>Live</b>: new lines are translated automatically and the control panel hides itself. <b>Esc</b> turns it off.",
    "Menu, nút bấm, bản đồ: <b>Cả cửa sổ</b>.": "Menus, buttons, maps: <b>Whole window</b>.",
    "Manga trên web": "Comics on the web",
    "<b>Cả cửa sổ</b>: mỗi bóng thoại, kể cả chữ dọc, có một khung bản dịch.": "<b>Whole window</b>: each speech bubble, even with vertical text, gets its own translation box.",
    "<b>Live</b>: cuộn hay lật trang là tự dịch lại. Chữ nhỏ quá thì phóng to trang (Ctrl +).": "<b>Live</b>: scrolling or turning the page translates again. If the text is too small, zoom in on the page (Ctrl +).",
    # trang Tên riêng
    "Tên nhân vật và thuật ngữ, để model dịch luôn đúng một kiểu. Lưu xong, lần dịch sau dùng ngay.": "Character names and terms, so the model always translates them the same way. Once saved, the next translation uses them.",
    "Thuật ngữ": "Term",
    "Nhân vật nữ": "Female name",
    "Nhân vật nam": "Male name",
    "Thêm": "Add",
    "Chữ gốc, vd. 霊夢": "Original text, e.g. 霊夢",
    "Tiếng Anh, vd. Reimu": "English, e.g. Reimu",
    "Thêm mục": "Add an entry",
    "Tìm theo chữ gốc hoặc tiếng Anh…": "Search by original text or English…",
    "Sửa bằng Notepad": "Edit in Notepad",
    "Tiếng Anh": "English",
    "Loại": "Type",
    "Danh sách": "List",
    "Bấm đúp vào ô để sửa. Nhân vật: chọn nữ / nam để bản dịch dùng đúng she / he. Khối chữ trùng hẳn một mục (nhãn menu, tên phòng…) thì dùng luôn bản dịch ở đây, không qua model.": "Double-click a cell to edit it. Characters: choose female or male so the translation uses she or he correctly. Text that exactly matches an entry (a menu label, a room name…) uses the translation here, not the model.",
    "Xóa mục này": "Delete this entry",
    "Không mở được {path}: {error}": "Could not open {path}: {error}",
    "Không đọc được {file}. Mở bằng Notepad, lưu dạng UTF-8 rồi quay lại đây.": "Could not read {file}. Open it in Notepad, save it as UTF-8, then come back here.",
    "Mục mới còn thiếu tiếng Anh.": "The new entry is missing the English text.",
    "Mục mới còn thiếu chữ gốc.": "The new entry is missing the original text.",
    "Dòng {row}: thiếu tiếng Anh.": "Line {row}: the English text is missing.",
    "Dòng {row}: thiếu chữ gốc.": "Line {row}: the original text is missing.",
    "Dòng {row}: chữ gốc không được có dấu = hay bắt đầu bằng #.": "Line {row}: the original text cannot contain = or start with #.",
    "「{ja}」đang có hai dòng.": "「{ja}」 appears on two lines.",
    # trang Phím tắt
    "Phím tắt toàn cục": "Global hotkeys",
    "Xóa bản dịch đang hiện, tắt live mode": "Clear the translation on screen, turn off live mode",
    "Gõ dạng Ctrl+Alt+T. Dùng được Ctrl, Alt, Shift, Win với A–Z, 0–9, F1–F12.": "Type them like Ctrl+Alt+T. You can use Ctrl, Alt, Shift and Win with A–Z, 0–9 and F1–F12.",
    "Bấm ở mọi nơi, kể cả khi game đang được chọn.": "They work everywhere, even while the game has focus.",
    # trang Cài đặt
    "Giao diện": "Interface",
    "Ngôn ngữ giao diện (Interface language)": "Interface language (Ngôn ngữ giao diện)",
    "Dịch": "Translation",
    "Ngôn ngữ trên màn hình": "Language on screen",
    "Model dịch (Ollama)": "Translation model (Ollama)",
    "Hồ sơ hiệu năng": "Performance profile",
    "Đổi ngôn ngữ thì model đổi theo. VNTL chỉ dịch tiếng Nhật; tiếng Trung và tiếng Hàn cần tải thêm:<br><b>ollama pull {model}</b>": "Changing the language also changes the model. VNTL only translates Japanese; Chinese and Korean need one more download:<br><b>ollama pull {model}</b>",
    "Ngôn ngữ, model dịch, hồ sơ hiệu năng và cách mở app.": "Languages, translation model, performance profile and how to open the app.",
    "Mở app": "Opening the app",
    "Chưa có screen-translator-gui.exe: chạy <code>uv sync</code> trong thư mục dự án rồi mở lại app.": "screen-translator-gui.exe is missing: run <code>uv sync</code> in the project folder, then open the app again.",
    # trang Chỉnh màu
    "Xanh đêm (mặc định)": "Midnight blue (default)",
    "Đen": "Black",
    "Xám xanh": "Slate",
    "Xanh dương đậm": "Dark blue",
    "Xanh lá đậm": "Dark green",
    "Tím": "Purple",
    "Trắng": "White",
    "Xem trước": "Preview",
    "Màu khác…": "Other color…",
    "Bản dịch": "Translation",
    "Màu nền": "Background color",
    "Cỡ chữ lớn nhất": "Largest font size",
    "Độ trong suốt của nền": "Background transparency",
    "Trên 50% thì chữ có viền cho dễ đọc; chữ gốc lộ ra sau bản dịch.": "Above 50%, the text gets an outline so it stays readable, and the original text shows through.",
    "Màu nền, cỡ chữ và độ trong suốt của khung bản dịch.": "Background color, font size and transparency of the translation box.",
    "Màu nền bản dịch": "Translation background color",
}
