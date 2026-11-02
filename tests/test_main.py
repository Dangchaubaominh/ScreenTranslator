import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "setup",
    ["", "import sys; sys.stdout = sys.stderr = None; "],  # có console (mã hóa cp1252 khi bị pipe) và không có console
)
def test_help_does_not_crash(setup):
    done = subprocess.run(
        [sys.executable, "-c", f"{setup}from screen_translator import main; main()", "--help"],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": ""},
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
