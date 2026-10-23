"""MCP Client Core — single-server stdio client wrapper (M11-T2).

Wraps the official ``mcp`` SDK to provide a synchronous interface for
connecting to a single MCP server, listing tools, and calling them.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from neonrp.core.config import MCPServerConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPToolSchema:
    """Normalised schema for a single MCP tool."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPCallResult:
    """Result of a single MCP tool call."""

    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: int = 0


class MCPClient:
    """Manages a connection to a single MCP server (stdio transport).

    Usage::

        client = MCPClient("myserver", config)
        client.start()          # launches subprocess + initialize handshake
        schemas = client.list_tools()
        result  = client.call_tool("tool_name", {"arg": "val"})
        client.stop()
    """

    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self.config = config
        self._session: ClientSession | None = None
        self._started = False
        self._healthy = False
        self._tools: list[MCPToolSchema] = []
        # Async internals managed via a dedicated event loop in a thread
        self._loop: asyncio.AbstractEventLoop | None = None
        self._context_manager: Any = None  # stdio_client context manager
        self._read_stream: Any = None
        self._write_stream: Any = None
        self._cm_task: asyncio.Task | None = None

    # -- Properties -------------------------------------------------------

    @property
    def is_started(self) -> bool:
        """Whether the server has been started successfully."""
        return self._started

    # -- Public sync API --------------------------------------------------

    def start(self) -> None:
        """Start the server subprocess and perform the MCP initialize handshake."""
        if self._started:
            return

        if not self.config.command:
            raise ValueError(f"MCP server '{self.name}' has no command configured")

        try:
            self._loop = asyncio.new_event_loop()
            self._loop.run_until_complete(
                asyncio.wait_for(self._async_start(), timeout=self.config.timeout_s)
            )
            self._started = True
            self._healthy = True
            logger.info("MCP server '%s' started successfully", self.name)
        except Exception as exc:
            self._healthy = False
            # must-fix #2: clean up loop/context on failure
            if self._loop and not self._loop.is_closed():
                try:
                    self._loop.run_until_complete(self._async_stop())
                except Exception:
                    pass
                self._loop.close()
            self._loop = None
            self._session = None
            self._context_manager = None
            logger.error("MCP server '%s' failed to start: %s", self.name, exc)
            raise

    def stop(self) -> None:
        """Gracefully stop the server process."""
        if not self._started:
            return
        try:
            if self._loop and not self._loop.is_closed():
                self._loop.run_until_complete(self._async_stop())
        except Exception as exc:
            logger.warning("Error stopping MCP server '%s': %s", self.name, exc)
        finally:
            if self._loop and not self._loop.is_closed():
                self._loop.close()
            self._loop = None
            self._session = None
            self._started = False
            self._healthy = False
            self._tools = []

    def list_tools(self) -> list[MCPToolSchema]:
        """Return cached tool schemas (populated during start)."""
        return list(self._tools)

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> MCPCallResult:
        """Call a tool on this MCP server.

        Returns:
            MCPCallResult with success/data/error/duration.
        """
        if not self._started or not self._session:
            return MCPCallResult(success=False, error=f"MCP server '{self.name}' is not started")

        t0 = time.monotonic()
        try:
            result = self._run_with_timeout(
                self._session.call_tool(tool_name, arguments or {}),
                timeout=self.config.timeout_s,
            )
            duration_ms = int((time.monotonic() - t0) * 1000)

            # MCP SDK returns CallToolResult with content list
            if result.isError:
                error_text = ""
                for block in result.content:
                    if hasattr(block, "text"):
                        error_text += block.text
                return MCPCallResult(success=False, error=error_text or "Unknown MCP error", duration_ms=duration_ms)

            # Collect text content
            data_parts: list[str] = []
            for block in result.content:
                if hasattr(block, "text"):
                    data_parts.append(block.text)
            data = "\n".join(data_parts) if data_parts else None

            return MCPCallResult(success=True, data=data, duration_ms=duration_ms)

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - t0) * 1000)
            self._healthy = False
            return MCPCallResult(
                success=False,
                error=f"MCP call '{tool_name}' timed out after {self.config.timeout_s}s",
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            self._healthy = False
            return MCPCallResult(success=False, error=str(exc), duration_ms=duration_ms)

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    # -- Async internals --------------------------------------------------

    async def _async_start(self) -> None:
        """Async start: launch subprocess, initialize, list tools."""
        env = dict(os.environ)
        if self.config.env:
            env.update(self.config.env)

        server_params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=env,
        )

        # Enter the stdio_client context manager
        self._context_manager = stdio_client(server_params)
        streams = await self._context_manager.__aenter__()
        self._read_stream, self._write_stream = streams

        # Create and initialize session
        self._session = ClientSession(self._read_stream, self._write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

        # Cache tool list
        tools_result = await self._session.list_tools()
        self._tools = []
        for tool in tools_result.tools:
            params = {}
            if tool.inputSchema:
                params = dict(tool.inputSchema) if isinstance(tool.inputSchema, dict) else {}
            self._tools.append(
                MCPToolSchema(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=params,
                )
            )

    async def _async_stop(self) -> None:
        """Async shutdown."""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None

        if self._context_manager:
            try:
                await self._context_manager.__aexit__(None, None, None)
            except Exception:
                pass
            self._context_manager = None

    def _run_with_timeout(self, coro: Any, timeout: int) -> Any:
        """Run an async coroutine with timeout on the client's event loop."""
        if not self._loop:
            raise RuntimeError("No event loop available")
        return self._loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))


def create_mcp_client(name: str, config: MCPServerConfig) -> MCPClient:
    """Factory helper — create (but do not start) an MCPClient."""
    return MCPClient(name, config)
