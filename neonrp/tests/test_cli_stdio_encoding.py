"""Regression: `neonrp web --help` must survive a legacy-codepage stdio.

On Windows, piped stdout/stderr default to the local code page (cp1252 /
cp932). The web help text contains non-ASCII characters (`—`, `→`), so the
command crashed with UnicodeEncodeError before printing anything — which made
the desktop shell's capability probe (looking for `--no-browser`) misjudge a
current engine as "too old". The CLI entry now reconfigures stdio to UTF-8.
"""

import os
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / "src")


def test_web_help_survives_cp1252_stdio():
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.argv = ['neonrp', 'web', '--help']; "
            "from neonrp.cli import cli; cli()",
        ],
        capture_output=True,
        env={
            **os.environ,
            "PYTHONPATH": SRC,  # 测本地源码,别被环境里的旧安装版拦截
            "PYTHONIOENCODING": "cp1252",  # simulate Windows piped stdio
            "PYTHONUTF8": "0",
        },
        timeout=120,
    )
    out = proc.stdout.decode("utf-8", errors="replace") + proc.stderr.decode(
        "utf-8", errors="replace"
    )
    assert proc.returncode == 0, out
    assert "--no-browser" in out
