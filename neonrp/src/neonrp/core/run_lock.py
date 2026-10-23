"""One writer per run (10-18; across processes 10-21): the lock a turn holds while it writes a run, shared by everything
that writes one — the web runtime's turn (commands/web.py ``_busy`` is this lock), in this process and in any other
process on the same machine (an engine on another port opening the same run), and a plugin settling something off the
player's screen. Keyed by the run's resolved path.

A :class:`RunLock` is a thread lock (this process) plus an advisory file lock (``flock``: other processes; released by
the OS when its holder dies). The lock file is not in the run (a turn must not leave a file behind in it): it sits in the
system's temp folder, named by the run's resolved path (``neonrp-run-locks/<sha1>.lock``) — every process of this user
finds the same one. Where file locks are not there (Windows, the browser engine) or that folder cannot be written, it
is the thread lock alone. A plugin takes it without waiting (:func:`try_hold`) and,
when a turn holds it — here or in another process — or any run's turn is running in this process (the turn's module
state is process-wide), does its write later."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX only; elsewhere the lock is this process's alone
    import fcntl as _fcntl
except ImportError:  # pragma: no cover
    _fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

def lock_file(root: Path) -> Path:
    """Where the run's lock file is (outside the run)."""
    import hashlib
    import tempfile

    key = hashlib.sha1(str(Path(root).resolve()).encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "neonrp-run-locks" / f"{key}.lock"


class RunLock:
    """``acquire(blocking=True)`` / ``release()`` / ``locked()`` like a ``threading.Lock`` — and while held here, no
    other process holding the same run's lock file gets it."""

    def __init__(self, root: Path):
        self.path = lock_file(root)
        self._t = threading.Lock()
        self._fh: Any = None

    def _file_lock(self, blocking: bool, timeout: float) -> bool:
        if _fcntl is None:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(self.path, "a+")  # noqa: SIM115 — held open while locked
        except OSError:  # a folder we cannot write: this process's lock only
            return True
        end = time.monotonic() + timeout if blocking and timeout >= 0 else None
        while True:
            try:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX | (0 if blocking and end is None else _fcntl.LOCK_NB))
                self._fh = fh
                return True
            except OSError:
                if not blocking or end is None or time.monotonic() >= end:
                    fh.close()
                    return False
                time.sleep(0.2)

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """``timeout`` (seconds, with ``blocking``) bounds the wait for this process's turn and another process's."""
        if not self._t.acquire(blocking, timeout):
            return False
        if not self._file_lock(blocking, timeout):  # another process is writing this run
            self._t.release()
            return False
        return True

    def release(self) -> None:
        fh, self._fh = self._fh, None
        if fh is not None:
            try:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            except OSError:
                logger.debug("run lock: unlock failed", exc_info=True)
            fh.close()
        self._t.release()

    def locked(self) -> bool:
        """Held in this process (another process holding it shows up only when acquiring)."""
        return self._t.locked()

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


_LOCKS: dict[str, RunLock] = {}
_GUARD = threading.Lock()


def of(root: Path) -> RunLock:
    """The run's lock (the same object for the same folder)."""
    key = str(Path(root).resolve())
    with _GUARD:
        lk = _LOCKS.get(key)
        if lk is None:
            lk = _LOCKS[key] = RunLock(Path(key))
        return lk


def busy() -> bool:
    """Some run's turn is running in this process."""
    with _GUARD:
        locks = list(_LOCKS.values())
    return any(lk.locked() for lk in locks)


@contextmanager
def try_hold(root: Path, *, alone: bool = True) -> Iterator[bool]:
    """``with try_hold(root) as ok:`` — ok = this run's lock is held now (and, ``alone``, no other run's turn was
    running in this process); False = someone is writing (here or in another process): do it later. Never waits."""
    if alone and busy():
        yield False
        return
    lk = of(root)
    if not lk.acquire(blocking=False):
        yield False
        return
    try:
        yield True
    finally:
        lk.release()
