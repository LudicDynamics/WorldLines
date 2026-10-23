"""Echo MCP server for testing (M11-T2).

A minimal MCP server used purely as a test fixture.
It exposes a single tool ``echo`` that returns its input.

Run via: python tests/fixtures/echo_mcp_server.py
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo-test-server")


@mcp.tool()
def echo(text: str) -> str:
    """Echo back the given text."""
    return f"echo: {text}"


@mcp.tool()
def add(a: int, b: int) -> str:
    """Add two numbers."""
    return str(a + b)


@mcp.tool()
def fail_always() -> str:
    """A tool that always fails."""
    raise ValueError("intentional failure")


if __name__ == "__main__":
    mcp.run(transport="stdio")
