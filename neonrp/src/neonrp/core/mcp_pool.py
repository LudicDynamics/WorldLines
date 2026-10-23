"""MCP Pool — multi-server lifecycle manager (M11-T3).

Manages a collection of MCP servers: lazy start, health tracking,
restart, and graceful shutdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from neonrp.core.config import MCPServerConfig
from neonrp.core.mcp_client import MCPClient, MCPToolSchema

logger = logging.getLogger(__name__)


@dataclass
class ServerStatus:
    """Health snapshot for a single MCP server."""

    name: str
    status: str = "stopped"  # "healthy" | "unhealthy" | "stopped" | "disabled"
    tool_count: int = 0
    error: str | None = None


class MCPPool:
    """Manages multiple MCP server connections.

    Servers are lazily started on first access and can be restarted
    or stopped individually or all at once.
    """

    def __init__(self, configs: dict[str, MCPServerConfig] | None = None):
        self._configs: dict[str, MCPServerConfig] = dict(configs or {})
        self._clients: dict[str, MCPClient] = {}
        self._reconnect_attempted: set[str] = set()

    def __enter__(self) -> "MCPPool":
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop_all()

    # -- Public API -------------------------------------------------------

    def get_client(self, name: str) -> MCPClient:
        """Get a started MCP client for the named server.

        Lazily starts the server if not already running.
        Attempts one reconnect if the server is unhealthy.

        Raises:
            KeyError: if `name` is not in the config.
            RuntimeError: if the server cannot be started / reconnected.
        """
        if name not in self._configs:
            raise KeyError(f"MCP server '{name}' not configured")

        config = self._configs[name]
        if not config.enabled:
            raise RuntimeError(f"MCP server '{name}' is disabled")

        # Return existing healthy client
        if name in self._clients:
            client = self._clients[name]
            if client.is_started and client.is_healthy:
                return client
            # Unhealthy → try one reconnect
            if name not in self._reconnect_attempted:
                self._reconnect_attempted.add(name)
                logger.info("MCP server '%s' unhealthy, attempting reconnect", name)
                try:
                    client.stop()
                except Exception:
                    pass
                return self._start_client(name, config)
            raise RuntimeError(f"MCP server '{name}' is unhealthy and reconnect already attempted")

        # Lazy start
        return self._start_client(name, config)

    def stop(self, name: str) -> None:
        """Stop a specific server."""
        client = self._clients.pop(name, None)
        if client:
            try:
                client.stop()
            except Exception as exc:
                logger.warning("Error stopping MCP server '%s': %s", name, exc)
        self._reconnect_attempted.discard(name)

    def stop_all(self) -> None:
        """Stop all running servers."""
        for name in list(self._clients.keys()):
            self.stop(name)

    def restart(self, name: str) -> MCPClient:
        """Restart a specific server.

        Returns:
            The restarted MCPClient.

        Raises:
            KeyError: if `name` is not configured.
        """
        if name not in self._configs:
            raise KeyError(f"MCP server '{name}' not configured")
        self.stop(name)
        self._reconnect_attempted.discard(name)
        return self.get_client(name)

    def get_status(self, name: str | None = None) -> list[ServerStatus]:
        """Get health status for one or all servers.

        Args:
            name: If provided, return status for just this server.
                  If None, return status for all configured servers.
        """
        if name:
            return [self._server_status(name)]

        statuses: list[ServerStatus] = []
        for n in self._configs:
            statuses.append(self._server_status(n))
        return statuses

    def get_all_tool_schemas(self) -> dict[str, list[MCPToolSchema]]:
        """Return tool schemas for all enabled and started servers.

        Keys are server names, values are their tool schema lists.
        Does NOT start servers — only returns schemas for already-running ones.
        """
        result: dict[str, list[MCPToolSchema]] = {}
        for name, client in self._clients.items():
            if client.is_started and client.is_healthy:
                result[name] = client.list_tools()
        return result

    def ensure_started(self) -> dict[str, str | None]:
        """Start all enabled servers that aren't running yet.

        Returns:
            Dict of {server_name: error_message_or_None}.
        """
        results: dict[str, str | None] = {}
        for name, config in self._configs.items():
            if not config.enabled:
                results[name] = "disabled"
                continue
            if name in self._clients and self._clients[name].is_started:
                results[name] = None
                continue
            try:
                self._start_client(name, config)
                results[name] = None
            except Exception as exc:
                results[name] = str(exc)
        return results

    @property
    def server_names(self) -> list[str]:
        """Return list of all configured server names."""
        return list(self._configs.keys())

    @property
    def enabled_servers(self) -> list[str]:
        """Return list of configured and enabled servers."""
        return [n for n, c in self._configs.items() if c.enabled]

    def get_started_client(self, name: str) -> MCPClient | None:
        """Return the client for *name* if started, else None (no lazy start)."""
        client = self._clients.get(name)
        if client and client.is_started:
            return client
        return None

    # -- Internal ---------------------------------------------------------

    def _start_client(self, name: str, config: MCPServerConfig) -> MCPClient:
        """Create, start, and cache a client."""
        client = MCPClient(name, config)
        client.start()
        self._clients[name] = client
        logger.info("MCP pool: server '%s' started (%d tools)", name, len(client.list_tools()))
        return client

    def _server_status(self, name: str) -> ServerStatus:
        """Build a status snapshot for a single server."""
        if name not in self._configs:
            return ServerStatus(name=name, status="unknown", error="Not configured")

        config = self._configs[name]
        if not config.enabled:
            return ServerStatus(name=name, status="disabled")

        client = self._clients.get(name)
        if client is None:
            return ServerStatus(name=name, status="stopped")

        if not client.is_started:
            return ServerStatus(name=name, status="stopped")

        if client.is_healthy:
            return ServerStatus(name=name, status="healthy", tool_count=len(client.list_tools()))

        return ServerStatus(name=name, status="unhealthy")
