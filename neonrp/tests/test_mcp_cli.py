"""Tests for MCP CLI commands (M11-T6)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli

ECHO_SERVER = str((Path(__file__).parent / "fixtures" / "echo_mcp_server.py").resolve())


def _write_config(data: dict) -> None:
    """Write project config in current working directory."""
    neonrp_dir = Path(".neonrp")
    neonrp_dir.mkdir(parents=True, exist_ok=True)
    (neonrp_dir / "config.json").write_text(json.dumps(data), encoding="utf-8")


class TestMCPCLI:
    def test_mcp_group_help_lists_subcommands(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["mcp", "--help"])
            assert result.exit_code == 0, result.output
            assert "list" in result.output
            assert "status" in result.output
            assert "restart" in result.output

    def test_mcp_list_json_no_servers(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["mcp", "list", "--json"])
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["servers"] == []
            assert payload["count"] == 0

    def test_mcp_status_json_all_disabled(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _write_config(
                {
                    "mcp_servers": {
                        "disabled": {
                            "command": sys.executable,
                            "args": [ECHO_SERVER],
                            "enabled": False,
                        }
                    }
                }
            )
            result = runner.invoke(cli, ["mcp", "status", "--json"])
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["servers"] == []
            assert payload["count"] == 0
            assert payload["note"] == "all disabled"

    def test_mcp_restart_unknown_server_json_exit_1(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["mcp", "restart", "missing", "--json"])
            assert result.exit_code == 1
            payload = json.loads(result.output)
            assert payload["success"] is False
            assert "Unknown MCP server" in payload["error"]

    def test_mcp_restart_disabled_server_json_exit_1(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _write_config(
                {
                    "mcp_servers": {
                        "disabled": {
                            "command": sys.executable,
                            "args": [ECHO_SERVER],
                            "enabled": False,
                        }
                    }
                }
            )
            result = runner.invoke(cli, ["mcp", "restart", "disabled", "--json"])
            assert result.exit_code == 1
            payload = json.loads(result.output)
            assert payload["success"] is False
            assert payload["server"] == "disabled"

    def test_mcp_restart_enabled_server_json_success(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _write_config(
                {
                    "mcp_servers": {
                        "echo": {
                            "command": sys.executable,
                            "args": [ECHO_SERVER],
                            "enabled": True,
                            "timeout_s": 10,
                        }
                    }
                }
            )
            result = runner.invoke(cli, ["mcp", "restart", "echo", "--json"])
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["success"] is True
            assert payload["server"] == "echo"
