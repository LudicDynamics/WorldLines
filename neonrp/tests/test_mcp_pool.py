"""Tests for MCP Pool + Lifecycle Management (M11-T3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from neonrp.core.config import MCPServerConfig
from neonrp.core.mcp_pool import MCPPool

ECHO_SERVER = str(Path(__file__).parent / "fixtures" / "echo_mcp_server.py")


@pytest.fixture
def echo_configs() -> dict[str, MCPServerConfig]:
    """Two echo servers for pool testing.

    Note: timeout_s is generous (30s) because Windows runners on CI
    spawn Python subprocesses notably slower than Linux/macOS, and the
    MCP handshake includes that subprocess startup time.
    """
    return {
        "echo1": MCPServerConfig(command=sys.executable, args=[ECHO_SERVER], timeout_s=30),
        "echo2": MCPServerConfig(command=sys.executable, args=[ECHO_SERVER], timeout_s=30),
    }


class TestMCPPoolUnit:
    """Unit tests for MCPPool (no subprocess)."""

    def test_empty_pool(self):
        pool = MCPPool()
        assert pool.server_names == []
        assert pool.enabled_servers == []
        pool.stop_all()  # noop

    def test_get_client_unknown_raises(self):
        pool = MCPPool()
        with pytest.raises(KeyError, match="not configured"):
            pool.get_client("nonexistent")

    def test_get_client_disabled_raises(self):
        pool = MCPPool({"disabled": MCPServerConfig(command="echo", enabled=False)})
        with pytest.raises(RuntimeError, match="disabled"):
            pool.get_client("disabled")

    def test_server_names(self):
        pool = MCPPool({
            "a": MCPServerConfig(command="echo"),
            "b": MCPServerConfig(command="echo", enabled=False),
        })
        assert set(pool.server_names) == {"a", "b"}
        assert pool.enabled_servers == ["a"]

    def test_status_disabled_server(self):
        pool = MCPPool({"disabled": MCPServerConfig(command="echo", enabled=False)})
        statuses = pool.get_status()
        assert len(statuses) == 1
        assert statuses[0].status == "disabled"

    def test_status_stopped_server(self):
        pool = MCPPool({"stopped": MCPServerConfig(command="echo")})
        statuses = pool.get_status("stopped")
        assert len(statuses) == 1
        assert statuses[0].status == "stopped"

    def test_status_unknown_server(self):
        pool = MCPPool()
        statuses = pool.get_status("nonexistent")
        assert len(statuses) == 1
        assert statuses[0].status == "unknown"

    def test_restart_unknown_raises(self):
        pool = MCPPool()
        with pytest.raises(KeyError):
            pool.restart("nonexistent")

    def test_stop_unknown_is_noop(self):
        pool = MCPPool()
        pool.stop("nonexistent")  # should not raise

    def test_get_all_tool_schemas_empty(self):
        pool = MCPPool()
        assert pool.get_all_tool_schemas() == {}


class TestMCPPoolIntegration:
    """Integration tests that launch echo servers."""

    def test_lazy_start_and_use(self, echo_configs: dict[str, MCPServerConfig]):
        """get_client should lazily start the server."""
        pool = MCPPool(echo_configs)
        try:
            client = pool.get_client("echo1")
            assert client.is_started
            assert client.is_healthy
            tools = client.list_tools()
            assert any(t.name == "echo" for t in tools)
        finally:
            pool.stop_all()

    def test_multi_server_coexistence(self, echo_configs: dict[str, MCPServerConfig]):
        """Multiple servers should run simultaneously."""
        pool = MCPPool(echo_configs)
        try:
            c1 = pool.get_client("echo1")
            c2 = pool.get_client("echo2")
            assert c1.is_started and c2.is_started
            assert c1 is not c2

            r1 = c1.call_tool("echo", {"text": "from1"})
            r2 = c2.call_tool("echo", {"text": "from2"})
            assert r1.success and "from1" in r1.data
            assert r2.success and "from2" in r2.data
        finally:
            pool.stop_all()

    def test_stop_individual(self, echo_configs: dict[str, MCPServerConfig]):
        """Stopping one server should not affect others."""
        pool = MCPPool(echo_configs)
        try:
            pool.get_client("echo1")
            pool.get_client("echo2")
            pool.stop("echo1")

            statuses = pool.get_status()
            status_map = {s.name: s.status for s in statuses}
            assert status_map["echo1"] == "stopped"
            assert status_map["echo2"] == "healthy"
        finally:
            pool.stop_all()

    def test_restart_server(self, echo_configs: dict[str, MCPServerConfig]):
        """Restart should stop and re-start the server."""
        pool = MCPPool(echo_configs)
        try:
            pool.get_client("echo1")
            client = pool.restart("echo1")
            assert client.is_started
            assert client.is_healthy

            result = client.call_tool("echo", {"text": "after restart"})
            assert result.success
        finally:
            pool.stop_all()

    def test_get_all_tool_schemas(self, echo_configs: dict[str, MCPServerConfig]):
        """Should return schemas from all started servers."""
        pool = MCPPool(echo_configs)
        try:
            pool.get_client("echo1")
            schemas = pool.get_all_tool_schemas()
            assert "echo1" in schemas
            assert any(t.name == "echo" for t in schemas["echo1"])
        finally:
            pool.stop_all()

    def test_ensure_started(self, echo_configs: dict[str, MCPServerConfig]):
        """ensure_started should start all enabled servers."""
        pool = MCPPool(echo_configs)
        try:
            results = pool.ensure_started()
            assert results["echo1"] is None  # no error
            assert results["echo2"] is None
            # Both should now be healthy
            statuses = pool.get_status()
            for s in statuses:
                assert s.status == "healthy"
        finally:
            pool.stop_all()

    def test_ensure_started_with_disabled(self):
        """Disabled servers should be skipped by ensure_started."""
        configs = {
            "enabled": MCPServerConfig(command=sys.executable, args=[ECHO_SERVER], timeout_s=10),
            "disabled": MCPServerConfig(command=sys.executable, args=[ECHO_SERVER], enabled=False),
        }
        pool = MCPPool(configs)
        try:
            results = pool.ensure_started()
            assert results["enabled"] is None
            assert results["disabled"] == "disabled"
        finally:
            pool.stop_all()

    def test_status_healthy(self, echo_configs: dict[str, MCPServerConfig]):
        """Started server should report healthy status."""
        pool = MCPPool(echo_configs)
        try:
            pool.get_client("echo1")
            statuses = pool.get_status("echo1")
            assert len(statuses) == 1
            assert statuses[0].status == "healthy"
            assert statuses[0].tool_count > 0
        finally:
            pool.stop_all()
