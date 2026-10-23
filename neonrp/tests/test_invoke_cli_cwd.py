"""Regression: a slash command must not crash the app when the process's
working directory has vanished. Finishing a world import renames the workspace
we launched in; `_invoke_cli` then restored the (now-gone) original cwd with a
bare `os.chdir(old_cwd)` in its finally, raising FileNotFoundError and taking
the whole app down when the user ran `/validate`."""

import os
import sys
from pathlib import Path

import pytest

from neonrp.tui.app import NeonRPApp


# Windows 上进程持有 cwd 句柄,rmdir 自己的 cwd 直接 WinError 32 —
# 「cwd 消失」这个场景本身只在 POSIX 上构造得出来。
@pytest.mark.skipif(sys.platform == "win32", reason="cannot rmdir the process cwd on Windows")
def test_invoke_cli_survives_vanished_cwd(tmp_path):
    root = tmp_path / "world"
    root.mkdir()
    doomed = tmp_path / "doomed"
    doomed.mkdir()

    app = NeonRPApp.__new__(NeonRPApp)  # bypass __init__ — only _invoke_cli is exercised
    app.root = root

    safe = Path.cwd()
    try:
        os.chdir(doomed)
        doomed.rmdir()  # the process cwd no longer exists

        # Must not raise (previously: FileNotFoundError crashed the app).
        code, _out = app._invoke_cli(["--help"])

        assert Path.cwd().exists()  # ended on a valid cwd, not the deleted one
    finally:
        os.chdir(safe)
