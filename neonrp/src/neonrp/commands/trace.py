"""``neonrp trace`` — the run's span/ApplyResult record as a static page (§11)."""

from __future__ import annotations

from pathlib import Path

import click


@click.group("trace")
def trace_group() -> None:
    """Turn-trace tools (engine v3 spans + ApplyResult)."""


@trace_group.command("html")
@click.argument("root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--out", type=click.Path(path_type=Path), default=None, help="Output .html (default: <root>/.neonrp/orchestration/<branch>.html)")
@click.option("--branch", default="main", show_default=True)
@click.option("--title", default=None)
def trace_html(root: Path, out: Path | None, branch: str, title: str | None) -> None:
    """Render every recorded turn (Gantt of spans, ops, ApplyResult) to one HTML file."""
    from neonrp.core.trace_report import write_run_report

    target = out or (root / ".neonrp" / "orchestration" / f"{branch}.html")
    meta = write_run_report(root, target, branch=branch, title=title)
    click.echo(f"✓ {meta['path']} ({meta['turns']} turns, v3 {meta['v3_turns']})")
