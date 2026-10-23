"""NEONRP_STRICT_PORT (10-18): the e2e launchers ask for one port and must never be moved to the next one quietly —
the test run would go on talking to the requested port, i.e. to whoever else holds it."""
from __future__ import annotations

import socket

import pytest

from neonrp.commands.web import _bind_server


def _taken() -> tuple[socket.socket, int]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def test_default_falls_back_to_a_free_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEONRP_STRICT_PORT", raising=False)
    s, port = _taken()
    try:
        srv = _bind_server("127.0.0.1", port)
        try:
            assert srv.server_address[1] != port
        finally:
            srv.server_close()
    finally:
        s.close()


def test_strict_port_refuses_a_taken_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEONRP_STRICT_PORT", "1")
    s, port = _taken()
    try:
        with pytest.raises(OSError):
            _bind_server("127.0.0.1", port)
    finally:
        s.close()


def test_strict_port_binds_a_free_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEONRP_STRICT_PORT", "1")
    s, port = _taken()
    s.close()
    srv = _bind_server("127.0.0.1", port)
    try:
        assert srv.server_address[1] == port
    finally:
        srv.server_close()
