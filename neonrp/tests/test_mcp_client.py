"""Tests for MCP Client Core (M11-T2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from neonrp.core.config import MCPServerConfig
from neonrp.core.mcp_client import MCPClient, MCPCallResult, MCPToolSchema, create_mcp_client

# Path to the echo fixture server
ECHO_SERVER = str(Path(__file__).parent / "fixtures" / "echo_mcp_server.py")


class TestMCPClientUnit:
    """Unit tests for MCPClient (no subprocess)."""

    def test_create_mcp_client_factory(self):
        """Factory should return an MCPClient instance."""
        config = MCPServerConfig(command="echo")
        client = create_mcp_client("test", config)
        assert isinstance(client, MCPClient)
        assert client.name == "test"
        assert not client.is_started
        assert not client.is_healthy

    def test_call_tool_when_not_started(self):
        """Calling a tool before start should return error."""
        config = MCPServerConfig(command="echo")
        client = MCPClient("test", config)
        result = client.call_tool("some_tool", {"arg": "val"})
        assert not result.success
        assert "not started" in result.error

    def test_start_without_command_raises(self):
        """Starting without a command should raise ValueError."""
        config = MCPServerConfig(command="")
        client = MCPClient("test", config)
        with pytest.raises(ValueError, match="no command"):
            client.start()

    def test_list_tools_when_not_started(self):
        """list_tools should return empty list when not started."""
        config = MCPServerConfig(command="echo")
        client = MCPClient("test", config)
        assert client.list_tools() == []

    def test_stop_when_not_started_is_noop(self):
        """Stopping a client that was never started should not raise."""
        config = MCPServerConfig(command="echo")
        client = MCPClient("test", config)
        client.stop()  # should not raise


class TestMCPCallResult:
    """Tests for MCPCallResult dataclass."""

    def test_success_result(self):
        result = MCPCallResult(success=True, data="hello", duration_ms=42)
        assert result.success
        assert result.data == "hello"
        assert result.duration_ms == 42
        assert result.error is None

    def test_error_result(self):
        result = MCPCallResult(success=False, error="boom")
        assert not result.success
        assert result.error == "boom"


class TestMCPToolSchema:
    """Tests for MCPToolSchema dataclass."""

    def test_basics(self):
        schema = MCPToolSchema(name="test", description="A test tool", parameters={"type": "object"})
        assert schema.name == "test"
        assert schema.description == "A test tool"
        assert schema.parameters == {"type": "object"}

    def test_defaults(self):
        schema = MCPToolSchema(name="minimal")
        assert schema.description == ""
        assert schema.parameters == {}


class TestMCPClientIntegration:
    """Integration tests that actually launch the echo MCP server subprocess.

    These tests are slower and require the mcp package to be installed
    with server support.
    """

    @pytest.fixture
    def echo_config(self) -> MCPServerConfig:
        """Config pointing at our echo fixture server."""
        return MCPServerConfig(
            command=sys.executable,
            args=[ECHO_SERVER],
            timeout_s=10,
        )

    def test_start_list_tools_stop(self, echo_config: MCPServerConfig):
        """Should connect, list tools, and disconnect cleanly."""
        client = MCPClient("echo", echo_config)
        try:
            client.start()
            assert client.is_started
            assert client.is_healthy

            tools = client.list_tools()
            tool_names = {t.name for t in tools}
            assert "echo" in tool_names
            assert "add" in tool_names
        finally:
            client.stop()
        assert not client.is_started

    def test_call_echo_tool(self, echo_config: MCPServerConfig):
        """Should call the echo tool and get back result."""
        client = MCPClient("echo", echo_config)
        try:
            client.start()
            result = client.call_tool("echo", {"text": "hello world"})
            assert result.success
            assert "hello world" in result.data
            assert result.duration_ms >= 0
        finally:
            client.stop()

    def test_call_add_tool(self, echo_config: MCPServerConfig):
        """Should call the add tool successfully."""
        client = MCPClient("echo", echo_config)
        try:
            client.start()
            result = client.call_tool("add", {"a": 3, "b": 7})
            assert result.success
            assert "10" in result.data
        finally:
            client.stop()

    def test_call_failing_tool(self, echo_config: MCPServerConfig):
        """A tool that raises should return an error result."""
        client = MCPClient("echo", echo_config)
        try:
            client.start()
            result = client.call_tool("fail_always", {})
            assert not result.success
            assert result.error  # should have error message
        finally:
            client.stop()

    def test_call_nonexistent_tool(self, echo_config: MCPServerConfig):
        """Calling a tool that doesn't exist should return error."""
        client = MCPClient("echo", echo_config)
        try:
            client.start()
            result = client.call_tool("nonexistent_tool_xyz", {})
            assert not result.success
            assert result.error
        finally:
            client.stop()
