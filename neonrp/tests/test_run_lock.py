"""One writer per run, across processes (10-21 · TEMPLATE-LAYERS-1019 stage B): core/run_lock is a thread lock plus a
file lock on ``<run>/.neonrp/run.lock`` — a turn in one engine and a write from another process on the same run never
run at once; the lock goes away with a process that dies holding it."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from neonrp.core import run_lock

pytestmark = pytest.mark.skipif(run_lock._fcntl is None, reason="no file locks on this platform: the lock is per process")

HOLD = textwrap.dedent("""
    import sys, time
    from pathlib import Path
    from neonrp.core import run_lock
    lk = run_lock.of(Path(sys.argv[1]))
    assert lk.acquire(blocking=False)
    print("held", flush=True)
    if sys.argv[2] == "die":
        import os; os._exit(0)
    time.sleep(float(sys.argv[2]))
    lk.release()
""")


def _holder(root: Path, how: str) -> subprocess.Popen:
    p = subprocess.Popen([sys.executable, "-c", HOLD, str(root), how], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def test_another_process_holding_the_run_keeps_this_one_out(tmp_path):
    p = _holder(tmp_path, "30")
    try:
        with run_lock.try_hold(tmp_path) as ok:
            assert not ok, "another process is writing this run"
        assert not run_lock.of(tmp_path).acquire(blocking=False)
        assert not run_lock.of(tmp_path).locked(), "a refused file lock leaves the thread lock free"
    finally:
        p.kill()
        p.wait()
    with run_lock.try_hold(tmp_path) as ok:
        assert ok, "its holder is gone: the lock is free"


def test_a_process_that_dies_holding_it_lets_go(tmp_path):
    p = _holder(tmp_path, "die")
    p.wait()
    with run_lock.try_hold(tmp_path) as ok:
        assert ok


def test_held_here_another_process_waits(tmp_path):
    lk = run_lock.of(tmp_path)
    assert lk.acquire(blocking=False)
    try:
        probe = subprocess.run([sys.executable, "-c", "import sys\nfrom pathlib import Path\nfrom neonrp.core import run_lock\n"
                                "print(run_lock.of(Path(sys.argv[1])).acquire(blocking=False))", str(tmp_path)],
                               capture_output=True, text=True, timeout=60)
        assert probe.stdout.strip() == "False"
    finally:
        lk.release()
    assert not (tmp_path / ".neonrp").exists(), "no lock file left in the run"
    assert run_lock.lock_file(tmp_path).is_file()


def test_the_web_turn_holds_the_same_lock(tmp_path):
    from neonrp.commands.web import WebRuntime

    rt = WebRuntime(tmp_path, "world-agent")
    assert rt._busy is run_lock.of(tmp_path)
    p = _holder(tmp_path, "30")
    try:
        assert rt.submit("hello") is False, "another engine is in a turn on this run: no second turn here"
    finally:
        p.kill()
        p.wait()


def test_waiting_for_another_process_is_bounded(tmp_path):
    import time

    p = _holder(tmp_path, "30")
    try:
        t0 = time.monotonic()
        assert run_lock.of(tmp_path).acquire(timeout=1.0) is False and 0.8 < time.monotonic() - t0 < 5
    finally:
        p.kill()
        p.wait()
    assert run_lock.of(tmp_path).acquire(timeout=5.0)
    run_lock.of(tmp_path).release()


def test_a_folder_that_cannot_be_written_falls_back_to_this_process(tmp_path, monkeypatch):
    lk = run_lock.RunLock(tmp_path / "nowhere")
    monkeypatch.setattr(run_lock.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    assert lk.acquire(blocking=False) and lk.locked()
    lk.release()


def test_a_turn_outside_the_web_runtime_waits_for_the_run(tmp_path, monkeypatch):
    """The TUI / headless (ConversationSession.send without the web runtime): takes the run's lock, waiting while another
    process writes it; under the web runtime (its _busy already held) it takes nothing more."""
    import time

    from neonrp.core.conversation import ConversationSession

    sess = ConversationSession.__new__(ConversationSession)
    sess.root = tmp_path
    seen: list[bool] = []
    monkeypatch.setattr(ConversationSession, "_send", lambda self, text, *a, **k: seen.append(run_lock.of(self.root).locked()) or "ok")
    p = _holder(tmp_path, "2")
    t0 = time.monotonic()
    assert sess.send("hi") == "ok" and seen == [True]
    assert time.monotonic() - t0 > 1.0, "it waited for the other process's turn"
    p.wait()
    assert not run_lock.of(tmp_path).locked(), "and let go after its turn"
    lk = run_lock.of(tmp_path)
    lk.acquire()
    try:
        assert sess.send("again") == "ok" and seen == [True, True], "under the web runtime's lock: no second acquire"
    finally:
        lk.release()
