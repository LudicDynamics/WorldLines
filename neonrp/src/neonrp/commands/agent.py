"""Agent lifecycle commands for NeonRP."""

import json
import re
from pathlib import Path

import click

from neonrp.core.paths import get_data_dir_name, get_project_root, get_game_dir


def get_agents_dir(root: Path) -> Path:
    """Get the agents directory path."""
    return root / "agents"


def validate_agent_id(agent_id: str) -> bool:
    """Validate agent ID format (alphanumeric, hyphens, underscores)."""
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", agent_id))


def create_agent_template(agent_dir: Path, agent_id: str, data_dir_name: str) -> None:
    """Create agent template files."""
    agent_dir.mkdir(parents=True, exist_ok=True)

    # agent.json
    agent_json = {
        "id": agent_id,
        "name": agent_id,
        "description": "",
        "version": "0.1",
        "system_prompt": "system.md",  # Relative to agent directory
        "delegation_mode": "one-shot",
        "context_limit": 20,
        "permissions": {
            "read_globs": [f"{data_dir_name}/**", ".neonrp/manifest.json"],
            "write_globs": ["**"],
            "direct_write_globs": [],
        },
    }

    agent_json_path = agent_dir / "agent.json"
    with open(agent_json_path, "w", encoding="utf-8") as f:
        json.dump(agent_json, f, indent=2, ensure_ascii=False)

    # system.md
    system_md_path = agent_dir / "system.md"
    system_md_content = f"""# {agent_id} System Prompt

You are {agent_id}, an AI agent in the NeonRP role-playing game engine.

## Your Role
Describe the agent's role and responsibilities here.
- Help the player by making changes to game state
- Gather information using tools before making decisions
- Maintain consistency with existing game state

## Available Tools
1. **read_file(path)**: Read a file's content. Path relative to project root (e.g., "{data_dir_name}/npc/old-sage.json").
2. **write_file(path, content)**: Write content to a file (creates or overwrites).
3. **edit_file(path, edits)**: Apply targeted edits to a file (search/replace pairs).
4. **delete_file(path)**: Delete a single file (cannot delete directories).
5. **find(query, kind?, tag?)**: Search for entities by ID, keyword, kind, or tag.
6. **list_entities(kind?, tag?)**: List all indexed entities with optional filters.
7. **read_context(query, limit?)**: Get relevant entities for a query, ranked by relevance.
8. **glob(pattern)**: Find files matching a glob pattern (e.g., "{data_dir_name}/**/*.json").
9. **grep(pattern, path?)**: Search file contents with regex patterns.
10. **resolve_action(action, actor, ...)**: Compute mechanical outcomes (damage, heal, buy, sell, move).
11. **ask_user(question)**: Ask the player a clarifying question and wait for response.
12. **Skill(skill)**: Load a reusable skill document by name for specialized guidance.
13. **task(agent_id, prompt, resume_run_id?)**: Delegate a subtask to another agent with a self-contained prompt.
14. **submit_proposal(...)**: Submit your final changes. Call this when ready.

## Entity Format
Entities are JSON files in `{data_dir_name}/<kind>/<id>.json` with required fields:
- `id`: Unique identifier (string, kebab-case)
- `kind`: Entity type (player, npc, town, item, etc.)
- `name`: Display name (string)

Optional fields: `tags` (array), `summary` (string), and kind-specific fields like `hp`, `gold`, `inventory`, `location`.

## Rules
- Always read relevant files before modifying them
- Entity paths in ops are relative to `{data_dir_name}/` (e.g., `"npc/old-sage.json"` not `"{data_dir_name}/npc/old-sage.json"`)
- Use `upsert_text` op to create or update files
- Use `delete` op to remove files
- Only modify files within your `write_globs` permissions
- Provide clear rationale for all proposed changes

## Workflow
1. Use tools to gather information about the current game state
2. Analyze what changes are needed
3. Call `submit_proposal` with your ops array

Remember: You MUST call `submit_proposal` to complete your task.
"""
    with open(system_md_path, "w", encoding="utf-8") as f:
        f.write(system_md_content)


def load_agent_json(agent_dir: Path) -> dict | None:
    """Load agent.json from agent directory."""
    agent_json_path = agent_dir / "agent.json"
    if not agent_json_path.exists():
        return None
    try:
        with open(agent_json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


@click.group()
def agent():
    """Agent lifecycle commands."""
    pass


@agent.command("new")
@click.argument("agent_id")
def agent_new(agent_id: str):
    """Create a new agent with ID AGENT_ID."""
    # Validate agent ID
    if not validate_agent_id(agent_id):
        click.echo(
            f"Error: Invalid agent ID '{agent_id}'. Must start with a letter and contain only alphanumeric characters, hyphens, or underscores.",
            err=True,
        )
        raise SystemExit(1)

    root = get_project_root()
    agents_dir = get_agents_dir(root)
    agent_dir = agents_dir / agent_id

    # Check if agent already exists
    if agent_dir.exists():
        click.echo(f"Error: Agent '{agent_id}' already exists at {agent_dir}", err=True)
        raise SystemExit(1)

    # Create agent template
    create_agent_template(agent_dir, agent_id, get_data_dir_name(root))

    click.echo(f"Created agent '{agent_id}' at {agent_dir}")
    click.echo("  - agent.json: Agent definition and permissions")
    click.echo("  - system.md: System prompt template")


@agent.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def agent_list(as_json: bool):
    """List all agents in the project."""
    root = get_project_root()
    agents_dir = get_agents_dir(root)

    if not agents_dir.exists():
        if as_json:
            click.echo(json.dumps({"agents": [], "count": 0}, ensure_ascii=False))
        else:
            click.echo("No agents directory found. Create an agent with 'neonrp agent new <id>'.")
        return

    agents = []
    for agent_dir in sorted(agents_dir.iterdir()):
        if agent_dir.is_dir():
            agent_data = load_agent_json(agent_dir)
            if agent_data:
                agents.append(
                    {
                        "id": agent_data.get("id", agent_dir.name),
                        "name": agent_data.get("name", agent_dir.name),
                        "description": agent_data.get("description", ""),
                        "version": agent_data.get("version", "unknown"),
                        "path": str(agent_dir),
                    }
                )

    if as_json:
        click.echo(json.dumps({"agents": agents, "count": len(agents)}, indent=2, ensure_ascii=False))
    else:
        if not agents:
            click.echo("No agents found. Create an agent with 'neonrp agent new <id>'.")
        else:
            click.echo(f"Found {len(agents)} agent(s):\n")
            for a in agents:
                click.echo(f"  {a['id']} (v{a['version']})")
                if a["description"]:
                    click.echo(f"    {a['description']}")


@agent.command("show")
@click.argument("agent_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def agent_show(agent_id: str, as_json: bool):
    """Show details of agent AGENT_ID."""
    root = get_project_root()
    agents_dir = get_agents_dir(root)
    agent_dir = agents_dir / agent_id

    if not agent_dir.exists():
        click.echo(f"Error: Agent '{agent_id}' not found at {agent_dir}", err=True)
        raise SystemExit(1)

    agent_data = load_agent_json(agent_dir)
    if not agent_data:
        click.echo(f"Error: Cannot read agent.json for '{agent_id}'", err=True)
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(agent_data, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Agent: {agent_data.get('name', agent_id)}")
        click.echo(f"  ID: {agent_data.get('id', agent_id)}")
        click.echo(f"  Version: {agent_data.get('version', 'unknown')}")
        if agent_data.get("description"):
            click.echo(f"  Description: {agent_data['description']}")
        click.echo(f"  System Prompt: {agent_data.get('system_prompt', 'N/A')}")
        # M8-T5: Show LLM configuration if present
        if "llm" in agent_data:
            llm = agent_data["llm"]
            click.echo("  LLM Configuration:")
            if "provider" in llm:
                click.echo(f"    Provider: {llm['provider']}")
            if "model" in llm:
                click.echo(f"    Model: {llm['model']}")
            if "provider_ref" in llm:
                click.echo(f"    Provider Ref: {llm['provider_ref']} (see config.json)")
            if "temperature" in llm:
                click.echo(f"    Temperature: {llm['temperature']}")
            if "base_url" in llm:
                click.echo(f"    Base URL: {llm['base_url']}")
        if "permissions" in agent_data:
            perms = agent_data["permissions"]
            click.echo("  Permissions:")
            click.echo(f"    read_globs: {perms.get('read_globs', [])}")
            click.echo(f"    write_globs: {perms.get('write_globs', [])}")
            click.echo(f"    deny_globs: {perms.get('deny_globs', [])}")


@agent.command("path")
@click.argument("agent_id")
def agent_path(agent_id: str):
    """Print the directory path of agent AGENT_ID."""
    root = get_project_root()
    agents_dir = get_agents_dir(root)
    agent_dir = agents_dir / agent_id

    if not agent_dir.exists():
        click.echo(f"Error: Agent '{agent_id}' not found at {agent_dir}", err=True)
        raise SystemExit(1)

    click.echo(str(agent_dir))


@agent.command("apply")
@click.argument("agent_id")
@click.option("--proposal", "proposal_path", required=True, type=click.Path(exists=True), help="Path to proposal.json")
@click.option("--dry-run", is_flag=True, help="Show what would happen without applying")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def agent_apply(agent_id: str, proposal_path: str, dry_run: bool, as_json: bool):
    """Apply a proposal for agent AGENT_ID."""
    from neonrp.core.proposal import parse_proposal
    from neonrp.core.apply import apply_proposal
    from neonrp.core.diffing import render_diff, render_diff_summary

    root = get_project_root()
    agents_dir = get_agents_dir(root)
    agent_dir = agents_dir / agent_id

    if not agent_dir.exists():
        click.echo(f"Error: Agent '{agent_id}' not found", err=True)
        raise SystemExit(1)

    # Load agent permissions
    agent_data = load_agent_json(agent_dir)
    if not agent_data:
        click.echo(f"Error: Cannot read agent.json for '{agent_id}'", err=True)
        raise SystemExit(1)

    permissions = agent_data.get("permissions", {})

    # Load and validate proposal
    try:
        with open(proposal_path, "r", encoding="utf-8") as f:
            proposal_data = json.load(f)
        proposal = parse_proposal(proposal_data)
    except Exception as e:
        click.echo(f"Error: Invalid proposal: {e}", err=True)
        raise SystemExit(1)

    # Verify agent_id matches
    if proposal.agent_id != agent_id:
        click.echo(f"Error: Proposal agent_id '{proposal.agent_id}' does not match '{agent_id}'", err=True)
        raise SystemExit(1)

    # Generate diff
    game_root = get_game_dir(root)
    diff_content = render_diff(proposal, game_root)
    summary = render_diff_summary(proposal, game_root)

    if not as_json:
        if diff_content:
            click.echo("=== Proposed Changes ===")
            click.echo(diff_content)
            click.echo("")
        click.echo(f"Summary: {summary['total']} file(s) affected")
        click.echo(f"  Added: {len(summary['added'])}")
        click.echo(f"  Modified: {len(summary['modified'])}")
        click.echo(f"  Deleted: {len(summary['deleted'])}")
        click.echo("")

    # Apply proposal
    result = apply_proposal(root, proposal, permissions, dry_run=dry_run)

    if as_json:
        output = {
            "success": result.success,
            "applied_paths": result.applied_paths,
            "event_id": result.event_id,
            "error": result.error,
            "dry_run": dry_run,
            "summary": summary,
        }
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if result.success:
            if dry_run:
                click.echo("[OK] Dry run successful - no changes committed")
            else:
                click.echo(f"[OK] Applied successfully (event_id: {result.event_id})")
                for path in result.applied_paths:
                    click.echo(f"  - {path}")
        else:
            click.echo(f"[FAIL] Failed: {result.error}", err=True)
            if result.validation_errors:
                click.echo("\nValidation errors:", err=True)
                for err in result.validation_errors:
                    click.echo(f"  - {err['file']}: {err['message']}", err=True)
            raise SystemExit(1)


@agent.command("logs")
@click.option("--tail", "tail_n", type=int, default=10, help="Number of recent runs to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def agent_logs(tail_n: int, as_json: bool):
    """Show recent agent run logs."""
    from neonrp.core.paths import get_neonrp_dir

    root = get_project_root()
    logs_dir = get_neonrp_dir(root) / "logs" / "agents"

    if not logs_dir.exists():
        if as_json:
            click.echo(json.dumps({"runs": [], "count": 0}, ensure_ascii=False))
        else:
            click.echo("No agent runs found.")
        return

    # List run directories (sorted by name = timestamp)
    runs = []
    for run_dir in sorted(logs_dir.iterdir(), reverse=True)[:tail_n]:
        if run_dir.is_dir():
            run_info = {"run_id": run_dir.name, "path": str(run_dir)}

            # Try to load apply.json for status
            apply_json = run_dir / "apply.json"
            if apply_json.exists():
                try:
                    with open(apply_json, "r", encoding="utf-8") as f:
                        apply_data = json.load(f)
                    run_info["success"] = apply_data.get("success")
                    run_info["event_id"] = apply_data.get("event_id")
                except Exception:
                    pass

            # Try to load proposal.json for agent_id
            proposal_json = run_dir / "proposal.json"
            if proposal_json.exists():
                try:
                    with open(proposal_json, "r", encoding="utf-8") as f:
                        proposal_data = json.load(f)
                    run_info["agent_id"] = proposal_data.get("agent_id")
                    run_info["query"] = proposal_data.get("query", "")[:50]
                except Exception:
                    pass

            runs.append(run_info)

    if as_json:
        click.echo(json.dumps({"runs": runs, "count": len(runs)}, indent=2, ensure_ascii=False))
    else:
        if not runs:
            click.echo("No agent runs found.")
            return

        click.echo(f"Recent agent runs (showing {len(runs)}):\n")
        for run in runs:
            status = "[OK]" if run.get("success") else "[FAIL]" if run.get("success") is False else "?"
            agent_id = run.get("agent_id", "unknown")
            query = run.get("query", "")
            if len(query) > 40:
                query = query[:37] + "..."
            click.echo(f"  {status} {run['run_id']} [{agent_id}]")
            if query:
                click.echo(f'      "{query}"')


@agent.command("context")
@click.argument("agent_id")
@click.option("--query", "-q", required=True, help="Query for context retrieval")
@click.option("--limit", "-n", default=8, type=int, help="Max context items")
@click.option("--output", "-o", type=click.Path(), help="Path to write input.json")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def agent_context(agent_id: str, query: str, limit: int, output: str, as_json: bool):
    """Retrieve context for agent AGENT_ID using a query.

    This command integrates with the retrieval system to gather relevant
    entities and prepare input.json for agent consumption.
    """
    from neonrp.core.retrieval import retrieve_context
    from neonrp.core.apply import generate_run_id
    from neonrp.core.paths import get_manifest_path
    from neonrp.core.manifest import Manifest

    root = get_project_root()
    agents_dir = get_agents_dir(root)
    agent_dir = agents_dir / agent_id

    if not agent_dir.exists():
        click.echo(f"Error: Agent '{agent_id}' not found", err=True)
        raise SystemExit(1)

    # Load agent config
    agent_data = load_agent_json(agent_dir)
    if not agent_data:
        click.echo(f"Error: Cannot read agent.json for '{agent_id}'", err=True)
        raise SystemExit(1)

    # Get context limit from agent defaults or use CLI arg
    context_limit = agent_data.get("defaults", {}).get("context_limit", limit)
    if limit != 8:  # CLI override
        context_limit = limit

    # Get current head event from manifest
    manifest_path = get_manifest_path(root)
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = Manifest(**json.load(f))
        branch = manifest.current_branch
        head_event = manifest.branches[branch].head_event
    except Exception as e:
        click.echo(f"Error: Cannot read manifest: {e}", err=True)
        raise SystemExit(1)

    # Retrieve context
    try:
        context_items = retrieve_context(root, query, max_results=context_limit)
    except Exception as e:
        click.echo(f"Error: Context retrieval failed: {e}", err=True)
        raise SystemExit(1)

    # Prepare input data structure
    run_id = generate_run_id()
    input_data = {
        "run_id": run_id,
        "agent_id": agent_id,
        "branch": branch,
        "base_head_event": head_event,
        "query": query,
        "context_items": [
            {
                "entity_key": f"{item.get('kind', 'unknown')}:{item.get('id', 'unknown')}",
                "path": item.get("path", ""),
                "data": item.get("data", {}),
            }
            for item in context_items
        ],
        "read_files": [item.get("path", "") for item in context_items if item.get("path")],
    }

    # Output results
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(input_data, f, indent=2, ensure_ascii=False)
        if not as_json:
            click.echo(f"Wrote input context to {output_path}")
            click.echo(f"  Run ID: {run_id}")
            click.echo(f"  Context items: {len(context_items)}")

    if as_json:
        click.echo(json.dumps(input_data, indent=2, ensure_ascii=False))
    elif not output:
        click.echo(f"Context for agent '{agent_id}':")
        click.echo(f"  Run ID: {run_id}")
        click.echo(f"  Query: {query}")
        click.echo(f"  Branch: {branch}")
        click.echo(f"  Head Event: {head_event}")
        click.echo(f"  Context Items: {len(context_items)}")
        if context_items:
            click.echo("\n  Entities:")
            for item in context_items[:5]:
                key = f"{item.get('kind', '?')}:{item.get('id', '?')}"
                name = item.get("data", {}).get("name", "")
                click.echo(f"    - {key}: {name}")
            if len(context_items) > 5:
                click.echo(f"    ... and {len(context_items) - 5} more")


@agent.command("run")
@click.argument("agent_id")
@click.option("--query", "-q", required=True, help="Query/instruction for the agent")
@click.option("--provider", default=None, help="LLM provider (default: from config or 'stub')")
@click.option("--fixture", type=click.Path(exists=True), help="Proposal fixture file for stub provider")
@click.option("--apply", "do_apply", is_flag=True, help="Apply the proposal after preview")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def agent_run(agent_id: str, query: str, provider: str | None, fixture: str | None, do_apply: bool, as_json: bool):
    """Run agent AGENT_ID with LLM to generate and optionally apply a proposal.

    This command:
    1. Loads agent spec and system prompt
    2. Retrieves relevant context entities
    3. Calls LLM to generate a proposal
    4. Renders diff preview
    5. Optionally applies the proposal (with --apply)

    All logs are saved to .neonrp/logs/agents/<run_id>/
    """
    from neonrp.core.agent_runner import run_agent

    root = get_project_root()

    # Call core function
    result = run_agent(
        root=root,
        agent_id=agent_id,
        query=query,
        provider=provider,
        fixture_path=fixture,
        do_apply=do_apply,
    )

    # Output results
    if as_json:
        output = {
            "success": result.success,
            "run_id": result.run_id,
            "agent_id": result.agent_id,
            "provider": result.provider,
            "logs_dir": str(result.logs_dir) if result.logs_dir else None,
            "proposal_path": str(result.logs_dir / "proposal.json") if result.logs_dir else None,
            "diff_path": str(result.logs_dir / "diff.txt") if result.logs_dir else None,
            "summary": result.summary,
            "applied": result.apply_result.success if result.apply_result else False,
            "event_id": result.apply_result.event_id if result.apply_result else None,
        }
        if not result.success:
            output["error"] = result.error
        if result.apply_result and not result.apply_result.success:
            output["apply_error"] = result.apply_result.error
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if not result.success:
            click.echo(f"Error: {result.error}", err=True)
            # Exit code 2 for adapter errors
            if result.error and "Failed to initialize LLM adapter" in result.error:
                raise SystemExit(2)
            raise SystemExit(1)

        click.echo(f"Running agent '{agent_id}' with provider '{result.provider}'...")
        click.echo("")
        click.echo(f"=== Agent Run: {result.run_id} ===")
        click.echo(f"Provider: {result.provider}")
        click.echo(f"Query: {query}")
        click.echo("")

        if result.diff_content:
            click.echo("=== Proposed Changes ===")
            click.echo(result.diff_content)
            click.echo("")

        click.echo(f"Summary: {result.summary.get('total', 0)} file(s) affected")
        click.echo(f"  Added: {len(result.summary.get('added', []))}")
        click.echo(f"  Modified: {len(result.summary.get('modified', []))}")
        click.echo(f"  Deleted: {len(result.summary.get('deleted', []))}")
        click.echo("")
        click.echo(f"Logs saved to: {result.logs_dir}")

        if result.apply_result:
            click.echo("")
            if result.apply_result.success:
                click.echo(f"[OK] Applied successfully (event_id: {result.apply_result.event_id})")
                for path in result.apply_result.applied_paths:
                    click.echo(f"  - {path}")
            else:
                click.echo(f"[FAIL] Apply failed: {result.apply_result.error}", err=True)
                raise SystemExit(1)

    # Exit with error code if not successful
    if not result.success:
        if result.error and "Failed to initialize LLM adapter" in result.error:
            raise SystemExit(2)
        raise SystemExit(1)


def _build_user_prompt(
    run_id: str,
    agent_id: str,
    branch: str,
    base_head_event: int,
    query: str,
    context_items: list,
    data_dir_name: str = "game",
) -> str:
    """Build user prompt for LLM from query and context."""
    context_json = json.dumps(
        {"run_id": run_id, "agent_id": agent_id, "branch": branch, "base_head_event": base_head_event, "query": query},
        indent=2,
        ensure_ascii=False,
    )

    prompt_parts = [
        "Generate a proposal.json for the following request:\n",
        f"Context:\n```json\n{context_json}\n```\n",
        f"Query: {query}\n",
    ]

    if context_items:
        prompt_parts.append("\nRelevant entities:\n")
        for item in context_items[:10]:
            entity_summary = {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "name": item.get("data", {}).get("name"),
                "path": item.get("path"),
            }
            prompt_parts.append(f"- {json.dumps(entity_summary, ensure_ascii=False)}\n")

    prompt_parts.append("""
Response format: Return a valid proposal.json with this structure:
{
  "proposal_version": "0.1",
  "run_id": "<run_id from context>",
  "agent_id": "<agent_id from context>",
  "branch": "<branch from context>",
  "base_head_event": <base_head_event from context>,
  "query": "<query from context>",
  "rationale": "<explanation of changes>",
  "ops": [
    {"op": "upsert_text", "path": "<kind>/<id>.json", "content": "..."},
    {"op": "delete", "path": "<kind>/<id>.json"}
  ]
}

IMPORTANT: Paths in ops are relative to the game/ directory. Use "<kind>/<id>.json" format, NOT "game/<kind>/<id>.json".
""".replace("game/", f"{data_dir_name}/"))

    return "".join(prompt_parts)


def _output_error(as_json: bool, run_id: str, message: str, logs_dir: str = None):
    """Output error in appropriate format."""
    if as_json:
        output = {"success": False, "run_id": run_id, "error": message}
        if logs_dir:
            output["logs_dir"] = logs_dir
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Error: {message}", err=True)

