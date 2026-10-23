"""Validate command for NeonRP CLI — world playability health-check.

Runs :func:`neonrp.core.validation.check_world`: a layered "can this world
actually be played?" report (JSON integrity, playthrough binding, scaffold,
soul bundles, location references, opening, entity lint) instead of the old
game/-only schema lint. Exit codes: 0 playable (warnings allowed), 1 blockers,
2 system error.
"""

import json
import sys

import click

from neonrp.core.paths import get_project_root
from neonrp.core.validation import ValidationIssue, check_world


def _echo_issue(issue: ValidationIssue) -> None:
    click.echo(f"  - {issue.file}: {issue.message}")
    if issue.suggestion:
        click.echo(f"      fix: {issue.suggestion}")


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def validate(as_json: bool) -> None:
    """Check the world is playable (JSON, playthrough, souls, scaffold, lint)."""
    root = get_project_root()

    try:
        health = check_world(root)
    except Exception as e:
        if as_json:
            click.echo(json.dumps({"error": str(e), "code": "system_error"}, ensure_ascii=False))
        else:
            click.echo(f"System error: {e}", err=True)
        sys.exit(2)

    if as_json:
        click.echo(json.dumps(health.to_dict(), indent=2, ensure_ascii=False))
        sys.exit(0 if health.playable else 1)

    s = health.stats
    summary = (
        f"{s.get('flavor', '?')} · {s.get('souls', 0)} soul(s) · "
        f"{s.get('locations', 0)} location(s) · {s.get('entities', 0)} entities · "
        f"router '{s.get('router', '?')}'"
    )
    if health.playable:
        click.echo(f"✓ playable — {summary}")
    else:
        click.echo(f"✗ NOT playable — {summary}")
        click.echo(f"\n{len(health.blockers)} blocker(s):")
        for issue in health.blockers:
            _echo_issue(issue)

    if health.warnings:
        click.echo(f"\n⚠ {len(health.warnings)} warning(s):")
        for issue in health.warnings:
            _echo_issue(issue)

    sys.exit(0 if health.playable else 1)
