import os
import time

import pytest
from PySide6.QtWidgets import QApplication

from screen_translator.i18n import set_language

# Chạy giao diện không cần màn hình thật; phải đặt trước khi tạo QApplication
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def english():
    """Giao diện tiếng Anh trong lúc chạy test, xong thì trả về mặc định."""
    set_language("en")
    yield
    set_language("vi")


def wait_until(app: QApplication, predicate, timeout: float = 5.0) -> None:
    """Xử lý sự kiện Qt cho tới khi `predicate()` đúng (tín hiệu từ luồng phụ cần event loop mới tới nơi)."""
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "hết thời gian chờ"
        app.processEvents()
        time.sleep(0.01)
