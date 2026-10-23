"""ToolRouter — unified dispatch for builtin + MCP tools (M11-T4/T5).

Single entry point that merges built-in skill schemas with MCP server
tool schemas, handles namespacing, routes tool calls, enforces
permissions, and emits audit logs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neonrp.core.mcp_client import MCPToolSchema
from neonrp.core.mcp_pool import MCPPool

logger = logging.getLogger(__name__)

# Separator used for MCP tool namespacing: {server}__{tool}
MCP_NS_SEP = "__"


@dataclass
class ToolRouterResult:
    """Result from a ToolRouter dispatch."""

    handled: bool = False  # True if the router handled the call (MCP or error)
    result_json: str = ""  # JSON string to return as tool result
    is_mcp: bool = False  # True if dispatched to an MCP server
    needs_confirm: bool = False  # True if permission == "confirm" (caller should prompt)


@dataclass
class MCPAuditEntry:
    """Audit log entry for an MCP tool call."""

    timestamp: str
    server: str
    tool: str
    arguments: dict[str, Any]
    permission: str  # "auto" | "confirm" | "deny"
    result_status: str  # "success" | "error" | "denied"
    duration_ms: int = 0
    run_id: str = ""
    agent_id: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "timestamp": self.timestamp,
            "server": self.server,
            "tool": self.tool,
            "arguments": self.arguments,
            "permission": self.permission,
            "result_status": self.result_status,
            "duration_ms": self.duration_ms,
        }
        if self.run_id:
            d["run_id"] = self.run_id
        if self.agent_id:
            d["agent_id"] = self.agent_id
        if self.error:
            d["error"] = self.error
        return d


class ToolRouter:
    """Merges builtin and MCP tool schemas and routes calls.

    MCP tools are exposed with namespaced names: ``{server_name}__{tool_name}``.
    Builtin tool names are unchanged. If a collision occurs, the builtin wins
    and the MCP tool is skipped with a warning.

    Permission enforcement (M11-T5):
    - ``deny``: block the call immediately
    - ``auto``: call proceeds without user confirmation
    - ``confirm``: sets ``needs_confirm=True`` on result (caller handles UI)

    Audit logging (M11-T5):
    All MCP tool calls are logged to ``{audit_path}/{server}/{run_id}.jsonl``.
    """

    def __init__(
        self,
        mcp_pool: MCPPool | None = None,
        *,
        configs: dict[str, Any] | None = None,
        audit_path: Path | None = None,
        run_id: str = "",
    ):
        self._pool = mcp_pool
        self._configs = configs or {}  # {server_name: MCPServerConfig}
        self._audit_base = audit_path  # base directory e.g. .neonrp/logs/mcp
        self._run_id = run_id

    # -- Schema merging ---------------------------------------------------

    def get_merged_schemas(self, builtin_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge builtin schemas with MCP schemas.

        MCP tool names are prefixed: ``{server}__{tool_name}``.
        Collisions with builtins are logged and skipped.
        Only includes tools from servers with permission != "deny".

        Returns:
            Combined list of tool schemas (builtin first, then MCP).
        """
        if not self._pool:
            return list(builtin_schemas)

        builtin_names = {s.get("name") for s in builtin_schemas}
        merged = list(builtin_schemas)
        all_mcp = self._pool.get_all_tool_schemas()

        for server_name, tools in all_mcp.items():
            server_config = self._configs.get(server_name)
            server_perm = getattr(server_config, "permission", "auto") if server_config else "auto"

            for tool in tools:
                # Check per-tool permission override
                tool_perm = server_perm
                if server_config:
                    tool_perms = getattr(server_config, "tool_permissions", {})
                    if tool.name in tool_perms:
                        tool_perm = tool_perms[tool.name]

                # Skip tools with "deny" permission
                if tool_perm == "deny":
                    continue

                namespaced = f"{server_name}{MCP_NS_SEP}{tool.name}"
                if namespaced in builtin_names:
                    logger.warning(
                        "MCP tool '%s' from server '%s' collides with builtin — skipping",
                        namespaced,
                        server_name,
                    )
                    continue
                merged.append(self._mcp_tool_to_schema(namespaced, tool))

        return merged

    # -- Dispatch ---------------------------------------------------------

    def dispatch(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        *,
        run_id: str = "",
        agent_id: str = "",
        confirmed: bool = False,
    ) -> ToolRouterResult:
        """Attempt to dispatch a tool call to an MCP server.

        Permission enforcement:
        - ``deny``: returns error immediately
        - ``confirm``: returns ``needs_confirm=True`` unless ``confirmed=True``
        - ``auto``: proceeds directly

        All MCP calls are audit-logged.

        Returns:
            ToolRouterResult indicating whether the call was handled.
        """
        if not self._pool:
            return ToolRouterResult(handled=False)

        server_name, mcp_tool = self._parse_namespaced(tool_name)
        if not server_name:
            return ToolRouterResult(handled=False)

        # Resolve permission
        perm = self._resolve_permission(server_name, mcp_tool)

        # Permission: deny
        if perm == "deny":
            self._audit_log(
                server=server_name,
                tool=mcp_tool,
                arguments=tool_args,
                permission=perm,
                result_status="denied",
                run_id=run_id,
                agent_id=agent_id,
            )
            return ToolRouterResult(
                handled=True,
                is_mcp=True,
                result_json=json.dumps({
                    "status": "error",
                    "error": f"MCP tool '{tool_name}' is denied by permission policy",
                }, ensure_ascii=False),
            )

        # Permission: confirm (and not yet confirmed)
        if perm == "confirm" and not confirmed:
            return ToolRouterResult(
                handled=True,
                is_mcp=True,
                needs_confirm=True,
                result_json=json.dumps({
                    "status": "pending_confirmation",
                    "server": server_name,
                    "tool": mcp_tool,
                    "arguments": tool_args,
                }, ensure_ascii=False),
            )

        # Permission: auto / confirmed
        try:
            client = self._pool.get_client(server_name)
        except (KeyError, RuntimeError) as exc:
            self._audit_log(
                server=server_name,
                tool=mcp_tool,
                arguments=tool_args,
                permission=perm,
                result_status="error",
                error=str(exc),
                run_id=run_id,
                agent_id=agent_id,
            )
            return ToolRouterResult(
                handled=True,
                is_mcp=True,
                result_json=json.dumps({"status": "error", "error": f"MCP server error: {exc}"}, ensure_ascii=False),
            )

        result = client.call_tool(mcp_tool, tool_args)
        duration_ms = result.duration_ms

        if result.success:
            self._audit_log(
                server=server_name,
                tool=mcp_tool,
                arguments=tool_args,
                permission=perm,
                result_status="success",
                duration_ms=duration_ms,
                run_id=run_id,
                agent_id=agent_id,
            )
            return ToolRouterResult(
                handled=True,
                is_mcp=True,
                result_json=json.dumps({
                    "status": "success",
                    "data": result.data,
                    "mcp_server": server_name,
                    "duration_ms": duration_ms,
                }, ensure_ascii=False),
            )
        else:
            self._audit_log(
                server=server_name,
                tool=mcp_tool,
                arguments=tool_args,
                permission=perm,
                result_status="error",
                error=result.error,
                duration_ms=duration_ms,
                run_id=run_id,
                agent_id=agent_id,
            )
            return ToolRouterResult(
                handled=True,
                is_mcp=True,
                result_json=json.dumps({
                    "status": "error",
                    "error": result.error or "Unknown MCP error",
                    "mcp_server": server_name,
                    "duration_ms": duration_ms,
                }, ensure_ascii=False),
            )

    # -- Permission -------------------------------------------------------

    def _resolve_permission(self, server_name: str, tool_name: str) -> str:
        """Resolve effective permission for a tool call.

        Tool-level overrides take precedence over server-level.
        """
        config = self._configs.get(server_name)
        if not config:
            return "auto"

        # Check tool-level override first
        tool_perms = getattr(config, "tool_permissions", {})
        if tool_name in tool_perms:
            return tool_perms[tool_name]

        # Fall back to server-level
        return getattr(config, "permission", "auto")

    # -- Audit logging ----------------------------------------------------

    def _audit_log(
        self,
        *,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        permission: str,
        result_status: str,
        duration_ms: int = 0,
        run_id: str = "",
        agent_id: str = "",
        error: str | None = None,
    ) -> None:
        """Append an audit log entry to the JSONL audit file."""
        entry = MCPAuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            server=server,
            tool=tool,
            arguments=arguments,
            permission=permission,
            result_status=result_status,
            duration_ms=duration_ms,
            run_id=run_id,
            agent_id=agent_id,
            error=error,
        )

        # Structured logger output
        logger.info(
            "MCP audit: server=%s tool=%s permission=%s result=%s duration=%dms",
            server,
            tool,
            permission,
            result_status,
            duration_ms,
        )

        # Write to JSONL file: .neonrp/logs/mcp/<server>/<run_id>.jsonl
        if self._audit_base:
            try:
                run_tag = self._run_id or "unknown"
                audit_file = self._audit_base / server / f"{run_tag}.jsonl"
                audit_file.parent.mkdir(parents=True, exist_ok=True)
                with open(audit_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            except Exception as exc:
                logger.warning("Failed to write MCP audit log: %s", exc)

    # -- Helpers ----------------------------------------------------------

    def _parse_namespaced(self, tool_name: str) -> tuple[str, str]:
        """Parse a namespaced tool name into (server_name, tool_name).

        Returns ('', '') if the name doesn't match MCP namespace pattern.
        """
        if MCP_NS_SEP not in tool_name:
            return ("", "")
        parts = tool_name.split(MCP_NS_SEP, 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return ("", "")
        server_name = parts[0]
        # Verify this server exists in the pool
        if self._pool and server_name in self._pool.server_names:
            return (server_name, parts[1])
        return ("", "")

    @staticmethod
    def _mcp_tool_to_schema(namespaced_name: str, tool: MCPToolSchema) -> dict[str, Any]:
        """Convert an MCPToolSchema to the dict format used by LLM adapters."""
        return {
            "name": namespaced_name,
            "description": tool.description,
            "parameters": tool.parameters or {"type": "object", "properties": {}},
        }
