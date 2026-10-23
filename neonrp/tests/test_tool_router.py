"""Tests for ToolRouter (M11-T4/T5)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from neonrp.core.config import MCPServerConfig
from neonrp.core.mcp_pool import MCPPool
from neonrp.core.tool_router import ToolRouter, ToolRouterResult, MCP_NS_SEP

ECHO_SERVER = str(Path(__file__).parent / "fixtures" / "echo_mcp_server.py")


class TestToolRouterUnit:
    """Unit tests with no subprocess."""

    def test_no_pool_returns_builtin_only(self):
        router = ToolRouter(mcp_pool=None)
        builtins = [{"name": "read_file", "description": "Read"}, {"name": "find", "description": "Find"}]
        merged = router.get_merged_schemas(builtins)
        assert len(merged) == 2

    def test_dispatch_returns_not_handled_without_pool(self):
        router = ToolRouter(mcp_pool=None)
        result = router.dispatch("some_tool", {"arg": "val"})
        assert not result.handled

    def test_dispatch_returns_not_handled_for_builtin(self):
        pool = MagicMock(spec=MCPPool)
        pool.server_names = []
        router = ToolRouter(mcp_pool=pool)
        result = router.dispatch("read_file", {"path": "test"})
        assert not result.handled

    def test_namespace_separator(self):
        assert MCP_NS_SEP == "__"

    def test_router_result_defaults(self):
        result = ToolRouterResult()
        assert not result.handled
        assert not result.needs_confirm


class TestToolRouterIntegration:
    """Integration tests with real echo MCP server."""

    @pytest.fixture
    def echo_pool(self) -> MCPPool:
        config = MCPServerConfig(command=sys.executable, args=[ECHO_SERVER], timeout_s=10)
        pool = MCPPool({"echo": config})
        pool.ensure_started()
        yield pool
        pool.stop_all()

    def test_merge_schemas_adds_mcp_tools(self, echo_pool: MCPPool):
        router = ToolRouter(mcp_pool=echo_pool)
        builtins = [{"name": "read_file", "description": "Read"}]
        merged = router.get_merged_schemas(builtins)

        names = {s["name"] for s in merged}
        assert "read_file" in names
        assert "echo__echo" in names
        assert "echo__add" in names

    def test_collision_detection(self, echo_pool: MCPPool):
        router = ToolRouter(mcp_pool=echo_pool)
        builtins = [{"name": "echo__echo", "description": "Fake builtin"}]
        merged = router.get_merged_schemas(builtins)
        echo_schemas = [s for s in merged if s["name"] == "echo__echo"]
        assert len(echo_schemas) == 1
        assert echo_schemas[0]["description"] == "Fake builtin"

    def test_dispatch_mcp_tool(self, echo_pool: MCPPool):
        router = ToolRouter(mcp_pool=echo_pool)
        result = router.dispatch("echo__echo", {"text": "hello"})
        assert result.handled and result.is_mcp
        data = json.loads(result.result_json)
        assert data["status"] == "success"
        assert "hello" in data["data"]

    def test_dispatch_mcp_add(self, echo_pool: MCPPool):
        router = ToolRouter(mcp_pool=echo_pool)
        result = router.dispatch("echo__add", {"a": 5, "b": 3})
        data = json.loads(result.result_json)
        assert data["status"] == "success"
        assert "8" in data["data"]

    def test_dispatch_unknown_server(self, echo_pool: MCPPool):
        router = ToolRouter(mcp_pool=echo_pool)
        result = router.dispatch("nonexistent__tool", {"arg": "val"})
        assert not result.handled

    def test_dispatch_failing_tool(self, echo_pool: MCPPool):
        router = ToolRouter(mcp_pool=echo_pool)
        result = router.dispatch("echo__fail_always", {})
        assert result.handled and result.is_mcp
        data = json.loads(result.result_json)
        assert data["status"] == "error"


class TestToolRouterPermissions:
    """Permission enforcement tests (M11-T5)."""

    @pytest.fixture
    def echo_pool(self) -> MCPPool:
        config = MCPServerConfig(command=sys.executable, args=[ECHO_SERVER], timeout_s=10)
        pool = MCPPool({"echo": config})
        pool.ensure_started()
        yield pool
        pool.stop_all()

    def test_deny_server_blocks_call(self, echo_pool: MCPPool):
        """Server-level deny should block the call."""
        config = MCPServerConfig(command="echo", permission="deny")
        router = ToolRouter(mcp_pool=echo_pool, configs={"echo": config})
        result = router.dispatch("echo__echo", {"text": "test"})
        assert result.handled
        data = json.loads(result.result_json)
        assert data["status"] == "error"
        assert "denied" in data["error"]

    def test_deny_tool_blocks_call(self, echo_pool: MCPPool):
        """Tool-level deny should block even if server is auto."""
        config = MCPServerConfig(command="echo", permission="auto", tool_permissions={"echo": "deny"})
        router = ToolRouter(mcp_pool=echo_pool, configs={"echo": config})
        result = router.dispatch("echo__echo", {"text": "test"})
        data = json.loads(result.result_json)
        assert data["status"] == "error"
        assert "denied" in data["error"]

    def test_confirm_returns_needs_confirm(self, echo_pool: MCPPool):
        """Confirm permission should return needs_confirm=True."""
        config = MCPServerConfig(command="echo", permission="confirm")
        router = ToolRouter(mcp_pool=echo_pool, configs={"echo": config})
        result = router.dispatch("echo__echo", {"text": "test"})
        assert result.handled
        assert result.needs_confirm
        data = json.loads(result.result_json)
        assert data["status"] == "pending_confirmation"

    def test_confirm_proceeds_when_confirmed(self, echo_pool: MCPPool):
        """With confirmed=True, confirm permission should proceed."""
        config = MCPServerConfig(command="echo", permission="confirm")
        router = ToolRouter(mcp_pool=echo_pool, configs={"echo": config})
        result = router.dispatch("echo__echo", {"text": "hello"}, confirmed=True)
        assert result.handled
        assert not result.needs_confirm
        data = json.loads(result.result_json)
        assert data["status"] == "success"

    def test_auto_proceeds_directly(self, echo_pool: MCPPool):
        """Auto permission should proceed without confirmation."""
        config = MCPServerConfig(command="echo", permission="auto")
        router = ToolRouter(mcp_pool=echo_pool, configs={"echo": config})
        result = router.dispatch("echo__echo", {"text": "hello"})
        assert result.handled
        assert not result.needs_confirm
        data = json.loads(result.result_json)
        assert data["status"] == "success"

    def test_tool_permission_overrides_server(self, echo_pool: MCPPool):
        """Tool-level permission should override server-level."""
        config = MCPServerConfig(command="echo", permission="deny", tool_permissions={"echo": "auto"})
        router = ToolRouter(mcp_pool=echo_pool, configs={"echo": config})
        result = router.dispatch("echo__echo", {"text": "hello"})
        assert result.handled
        data = json.loads(result.result_json)
        assert data["status"] == "success"

    def test_deny_tools_excluded_from_schemas(self, echo_pool: MCPPool):
        """Denied tools should not appear in merged schemas."""
        config = MCPServerConfig(command="echo", permission="auto", tool_permissions={"echo": "deny"})
        router = ToolRouter(mcp_pool=echo_pool, configs={"echo": config})
        merged = router.get_merged_schemas([])
        names = {s["name"] for s in merged}
        assert "echo__echo" not in names
        assert "echo__add" in names  # only "echo" tool is denied


class TestToolRouterAudit:
    """Audit logging tests (M11-T5)."""

    @pytest.fixture
    def echo_pool(self) -> MCPPool:
        config = MCPServerConfig(command=sys.executable, args=[ECHO_SERVER], timeout_s=10)
        pool = MCPPool({"echo": config})
        pool.ensure_started()
        yield pool
        pool.stop_all()

    def test_audit_file_created_on_call(self, echo_pool: MCPPool, tmp_path: Path):
        """Successful call should write audit entry."""
        audit_base = tmp_path / "audit"
        config = MCPServerConfig(command="echo", permission="auto")
        router = ToolRouter(
            mcp_pool=echo_pool, configs={"echo": config},
            audit_path=audit_base, run_id="run-1",
        )

        router.dispatch("echo__echo", {"text": "test"}, run_id="run-1", agent_id="gm")

        audit_file = audit_base / "echo" / "run-1.jsonl"
        assert audit_file.exists()
        lines = audit_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["server"] == "echo"
        assert entry["tool"] == "echo"
        assert entry["result_status"] == "success"
        assert entry["run_id"] == "run-1"
        assert entry["agent_id"] == "gm"
        assert "timestamp" in entry

    def test_audit_logs_denied_calls(self, echo_pool: MCPPool, tmp_path: Path):
        """Denied calls should be audit-logged."""
        audit_base = tmp_path / "audit"
        config = MCPServerConfig(command="echo", permission="deny")
        router = ToolRouter(
            mcp_pool=echo_pool, configs={"echo": config},
            audit_path=audit_base, run_id="run-deny",
        )

        router.dispatch("echo__echo", {"text": "test"})

        audit_file = audit_base / "echo" / "run-deny.jsonl"
        lines = audit_file.read_text(encoding="utf-8").strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["result_status"] == "denied"
        assert entry["permission"] == "deny"

    def test_audit_logs_errors(self, echo_pool: MCPPool, tmp_path: Path):
        """Error calls should be audit-logged."""
        audit_base = tmp_path / "audit"
        config = MCPServerConfig(command="echo", permission="auto")
        router = ToolRouter(
            mcp_pool=echo_pool, configs={"echo": config},
            audit_path=audit_base, run_id="run-err",
        )

        router.dispatch("echo__fail_always", {})

        audit_file = audit_base / "echo" / "run-err.jsonl"
        lines = audit_file.read_text(encoding="utf-8").strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["result_status"] == "error"
        assert entry["error"]

    def test_confirm_no_audit_until_confirmed(self, echo_pool: MCPPool, tmp_path: Path):
        """Pending confirmation should NOT write audit entry."""
        audit_base = tmp_path / "audit"
        config = MCPServerConfig(command="echo", permission="confirm")
        router = ToolRouter(
            mcp_pool=echo_pool, configs={"echo": config},
            audit_path=audit_base, run_id="run-confirm",
        )

        router.dispatch("echo__echo", {"text": "test"})
        audit_file = audit_base / "echo" / "run-confirm.jsonl"
        assert not audit_file.exists()

    def test_multiple_audit_entries(self, echo_pool: MCPPool, tmp_path: Path):
        """Multiple calls should append entries."""
        audit_base = tmp_path / "audit"
        config = MCPServerConfig(command="echo", permission="auto")
        router = ToolRouter(
            mcp_pool=echo_pool, configs={"echo": config},
            audit_path=audit_base, run_id="run-multi",
        )

        router.dispatch("echo__echo", {"text": "first"})
        router.dispatch("echo__echo", {"text": "second"})

        audit_file = audit_base / "echo" / "run-multi.jsonl"
        lines = audit_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
