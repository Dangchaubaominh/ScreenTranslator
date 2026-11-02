# Đóng gói thành dist/ScreenTranslator/ và dist/ScreenTranslator.zip (đưa file zip lên GitHub Releases):
#     uv run --group build pyinstaller --noconfirm packaging/ScreenTranslator.spec
# Một thư mục chứ không gộp một file .exe: DLL của Qt phải thay được (LGPL), và mở app nhanh hơn.
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

NAME = "ScreenTranslator"
HERE = Path(SPECPATH)
ROOT = HERE.parent
# App không dùng tới: OpenGL giả lập bằng CPU (20 MB), bản dịch giao diện của Qt (7 MB), đọc ảnh AVIF (7,5 MB)
UNUSED = ("opengl32sw.dll", "translations", "_avif")


def used(entries):
    return [entry for entry in entries if not any(name in entry[0] for name in UNUSED)]


analysis = Analysis(
    [str(HERE / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=copy_metadata("screen-translator", recursive=True),  # kèm giấy phép của từng thư viện
    excludes=["pytest", "_pytest", "pygments", "setuptools"],  # công cụ phát triển, app không cần nhưng hay bị kéo theo
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(HERE / "icon.ico"),
)
COLLECT(exe, used(analysis.binaries), used(analysis.datas), name=NAME)

output = Path(DISTPATH) / NAME
# bản chạy từ mã nguồn ghi đường dẫn thư mục dự án vào đây; bản phát hành không cần
for build_path in output.glob("_internal/screen_translator-*.dist-info/direct_url.json"):
    build_path.unlink()
shutil.copy(ROOT / "LICENSE", output)
shutil.copy(HERE / "THIRD-PARTY-NOTICES.txt", output)
shutil.copytree(HERE / "licenses", output / "licenses", dirs_exist_ok=True)
shutil.make_archive(str(output), "zip", DISTPATH, NAME)
