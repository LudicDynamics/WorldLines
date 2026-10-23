"""Run command for NeonRP.

M6-T3: Upgraded from echo placeholder to dispatcher-based agent execution.
"""

import json
import sys

import click

from neonrp.core.dispatcher import dispatch
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_manifest_path, get_project_root


@click.command()
@click.argument("query")
@click.option("--agent", "-a", "agent_id", default=None, help="Specific agent ID to run")
@click.option("--provider", "-p", default=None, help="LLM provider override")
@click.option("--fixture", default=None, help="Path to fixture file for stub provider")
@click.option("--apply", "do_apply", is_flag=True, help="Apply the proposal after generation")
@click.option("--agentic", is_flag=True, help="Use multi-turn agentic loop")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def run(
    query: str,
    agent_id: str | None,
    provider: str | None,
    fixture: str | None,
    do_apply: bool,
    agentic: bool,
    output_json: bool,
):
    """Run a query through the agent dispatcher.

    The dispatcher selects an agent based on:
    - Explicit --agent flag (direct selection)
    - Trigger patterns in agent.json (regex matching)
    - Tags in agent.json (keyword matching)
    - Priority (when multiple agents match)

    Examples:
        neonrp run "Create a new character named Alice"
        neonrp run "Create a quest" --agent narrator
        neonrp run "Add an item" --apply --agentic
    """
    root = get_project_root()
    manifest_path = get_manifest_path(root)

    if not manifest_path.exists():
        if output_json:
            click.echo(
                json.dumps({"success": False, "error": "Not initialized. Run 'neonrp init' first."}, ensure_ascii=False)
            )
        else:
            click.echo("Error: Not initialized. Run 'neonrp init' first.", err=True)
        sys.exit(1)

    # Load manifest
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
            Manifest(**manifest_data)  # Validate manifest format
    except Exception as e:
        if output_json:
            click.echo(json.dumps({"success": False, "error": f"Failed to load manifest: {e}"}, ensure_ascii=False))
        else:
            click.echo(f"Error: Failed to load manifest: {e}", err=True)
        sys.exit(2)

    # Dispatch the query
    result = dispatch(
        root=root,
        query=query,
        agent_id=agent_id,
        provider=provider,
        fixture_path=fixture,
        do_apply=do_apply,
        agentic=agentic,
    )

    if output_json:
        output = {
            "success": result.success,
            "agent_id": result.agent_id,
            "matched_trigger": result.matched_trigger,
            "matched_tags": result.matched_tags,
            "candidates": result.candidates,
            "error": result.error,
        }
        if result.run_result:
            output["run_id"] = result.run_result.run_id
            output["turns"] = result.run_result.turns
            output["provider"] = result.run_result.provider
            output["summary"] = result.run_result.summary
            if result.run_result.logs_dir:
                output["logs_dir"] = str(result.run_result.logs_dir)
            if result.run_result.apply_result:
                output["applied"] = result.run_result.apply_result.success
                output["event_id"] = result.run_result.apply_result.event_id
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
        if not result.success:
            if result.error and "Failed to initialize LLM adapter" in result.error:
                sys.exit(2)
            sys.exit(1)
        return

    # Human-readable output
    if not result.success:
        click.echo(f"Error: {result.error}", err=True)
        if result.candidates:
            click.echo(f"Available agents: {', '.join(result.candidates)}")
        if result.error and "Failed to initialize LLM adapter" in result.error:
            sys.exit(2)
        sys.exit(1)

    click.echo(f"Agent: {result.agent_id}")
    if result.matched_trigger:
        click.echo(f"Matched trigger: {result.matched_trigger}")
    if result.matched_tags:
        click.echo(f"Matched tags: {', '.join(result.matched_tags)}")

    run_result = result.run_result
    if run_result:
        click.echo(f"Run ID: {run_result.run_id}")
        if run_result.turns > 0:
            click.echo(f"Turns: {run_result.turns}")

        if run_result.summary:
            summary = run_result.summary
            click.echo(f"\nProposal: {summary.get('total', 0)} changes")
            if summary.get("added"):
                click.echo(f"  Added: {', '.join(summary['added'][:5])}")
            if summary.get("modified"):
                click.echo(f"  Modified: {', '.join(summary['modified'][:5])}")
            if summary.get("deleted"):
                click.echo(f"  Deleted: {', '.join(summary['deleted'][:5])}")

        if run_result.diff_content:
            click.echo(f"\n--- Diff Preview ---\n{run_result.diff_content[:1000]}")
            if len(run_result.diff_content) > 1000:
                click.echo("... (truncated)")

        if run_result.apply_result:
            ar = run_result.apply_result
            if ar.success:
                click.echo(f"\n[OK] Applied successfully (event {ar.event_id})")
            else:
                click.echo(f"\n[FAIL] Apply failed: {ar.error}", err=True)

        if run_result.logs_dir:
            click.echo(f"\nLogs: {run_result.logs_dir}")
