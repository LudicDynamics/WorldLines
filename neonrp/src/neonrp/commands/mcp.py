"""MCP server management commands for NeonRP CLI (M11-T6)."""

import json

import click

from neonrp.core.paths import get_project_root


@click.group()
def mcp():
    """MCP server management."""
    pass


@mcp.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mcp_list(as_json: bool):
    """List configured MCP servers."""
    from neonrp.core.config import load_config

    root = get_project_root()
    config = load_config(root)

    if not config.mcp_servers:
        if as_json:
            click.echo(json.dumps({"servers": [], "count": 0}, ensure_ascii=False))
        else:
            click.echo("No MCP servers configured.")
        return

    servers = []
    for name, cfg in config.mcp_servers.items():
        servers.append({
            "name": name,
            "command": cfg.command,
            "args": cfg.args,
            "enabled": cfg.enabled,
            "permission": cfg.permission,
            "timeout_s": cfg.timeout_s,
        })

    if as_json:
        click.echo(json.dumps({"servers": servers, "count": len(servers)}, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Configured MCP servers ({len(servers)}):\n")
        for s in servers:
            status = "enabled" if s["enabled"] else "disabled"
            click.echo(f"  {s['name']} [{status}] (permission: {s['permission']})")
            click.echo(f"    command: {s['command']} {' '.join(s['args'])}")


@mcp.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mcp_status(as_json: bool):
    """Show MCP server health status (starts servers temporarily to check)."""
    from neonrp.core.config import load_config
    from neonrp.core.mcp_pool import MCPPool

    root = get_project_root()
    config = load_config(root)

    if not config.mcp_servers:
        if as_json:
            click.echo(json.dumps({"servers": [], "count": 0}, ensure_ascii=False))
        else:
            click.echo("No MCP servers configured.")
        return

    enabled = {n: c for n, c in config.mcp_servers.items() if c.enabled}
    if not enabled:
        if as_json:
            click.echo(json.dumps({"servers": [], "count": 0, "note": "all disabled"}, ensure_ascii=False))
        else:
            click.echo("All MCP servers are disabled.")
        return

    with MCPPool(enabled) as pool:
        results = pool.ensure_started()
        statuses = []
        for name, err in results.items():
            entry = {"name": name, "healthy": err is None, "error": err}
            if not err:
                client = pool.get_started_client(name)
                tools = client.list_tools() if client else []
                entry["tool_count"] = len(tools)
                entry["tools"] = [t.name for t in tools]
                entry["permission"] = config.mcp_servers[name].permission
            statuses.append(entry)

        if as_json:
            click.echo(json.dumps({"servers": statuses, "count": len(statuses)}, indent=2, ensure_ascii=False))
        else:
            click.echo("MCP Server Status:\n")
            for s in statuses:
                if s["healthy"]:
                    click.echo(f"  ✔ {s['name']}: {s['tool_count']} tools (permission: {s['permission']})")
                    for t in s.get("tools", []):
                        click.echo(f"    · {t}")
                else:
                    click.echo(f"  ✖ {s['name']}: {s['error']}")


@mcp.command("restart")
@click.argument("server_name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mcp_restart(server_name: str, as_json: bool):
    """Restart a specific MCP server."""
    from neonrp.core.config import load_config
    from neonrp.core.mcp_pool import MCPPool

    root = get_project_root()
    config = load_config(root)

    if not config.mcp_servers or server_name not in config.mcp_servers:
        msg = f"Unknown MCP server: {server_name}"
        if as_json:
            click.echo(json.dumps({"success": False, "error": msg}, ensure_ascii=False))
        else:
            click.echo(f"Error: {msg}", err=True)
        raise SystemExit(1)

    srv_config = config.mcp_servers[server_name]
    with MCPPool({server_name: srv_config}) as pool:
        try:
            pool.ensure_started()
            status = pool.get_status(server_name)
            healthy = status and status[0].status == "healthy"
            if as_json:
                click.echo(json.dumps({"success": healthy, "server": server_name}, ensure_ascii=False))
                if not healthy:
                    raise SystemExit(1)
            else:
                if healthy:
                    click.echo(f"✔ Server '{server_name}' restarted successfully.")
                else:
                    click.echo(f"✖ Server '{server_name}' failed to restart.", err=True)
                    raise SystemExit(1)
        except Exception as exc:
            if as_json:
                click.echo(json.dumps({"success": False, "server": server_name, "error": str(exc)}, ensure_ascii=False))
            else:
                click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)
