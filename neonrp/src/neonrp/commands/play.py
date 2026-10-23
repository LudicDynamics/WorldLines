"""Headless play command — drive multi-agent turns without the TUI.

Two shapes, one engine path (the full M18 pipeline: scene-understanding →
souls → world-agent → commit, all over the bus):

- ``neonrp play "input"`` — one-shot, for scripts / batch experiments
  (``--json --trace`` emits the complete orchestration record).
- ``neonrp play`` — interactive REPL. One process for the whole session, so
  in-process continuity (soul sticky histories, world-agent conversation
  context) is preserved across turns — this is the simple play-testing
  terminal. ``/trace`` and ``/debug`` bring the observability surfaces
  inline; no TUI needed.

The per-turn orchestration trace is written to
``.neonrp/orchestration/<branch>.jsonl`` in both shapes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from neonrp.core.conversation import ConversationSession
from neonrp.core.orchestration_trace import read_turn_traces
from neonrp.core.paths import get_manifest_path, get_project_root
from neonrp.core.runtime_contract import get_startup_entry_agent

_REPL_HELP = """\
commands:
  /trace        show last turn's routing (commit, per-soul activation + reason)
  /debug        show recent agent calls (perception, tokens, output previews)
  /map          the engine draws where you are, from state (no LLM): town exits / dungeon rooms / the road
  /help         this help
  /quit         exit (also: /exit, /q, Ctrl-D)
anything else is sent to the world as your action."""


@click.command()
@click.argument("query", required=False, default=None)
@click.option(
    "--project", "-p",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Project directory (default: current directory).",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON (for scripts / experiments).")
@click.option("--trace", "show_trace", is_flag=True, help="Append the last turn's orchestration trace to the output.")
def play(query: str | None, project: str | None, output_json: bool, show_trace: bool) -> None:
    """Play the multi-agent engine from the terminal — no TUI.

    With QUERY: send one turn and print the narration (one-shot; scriptable).
    Without QUERY: enter an interactive REPL — one process for the whole
    session, so souls keep their sticky histories between turns. Inside the
    REPL, /trace and /debug show the orchestration.

    \b
    Examples:
        neonrp play "我走进北门。"
        neonrp play --project playground/stoneford-elena
        neonrp play "开始游戏" --json --trace
    """
    root = Path(project).resolve() if project else get_project_root()
    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        _fail("Not initialized. Run 'neonrp init' first.", output_json)
        return

    agent_id = get_startup_entry_agent(root) or "world-agent"

    if query is None:
        if output_json:
            _fail("--json requires a QUERY (one-shot mode); the REPL is interactive.", True)
            return
        _repl(root, agent_id)
        return

    session = ConversationSession(root=root, agent_id=agent_id, mode="play")
    result = session.send(query)

    if output_json:
        obj: dict = {
            "success": result.success,
            "route_decision": result.route_decision,
            "error": result.error,
            "narration": (result.assistant_message or "")[:3000],
            "narration_chars": len(result.assistant_message or ""),
            "panels": dict(getattr(result, "panels", None) or {}),
            "options": list(getattr(result, "options", None) or []),
        }
        if show_trace:
            traces = read_turn_traces(root, session.branch, last=1)
            if traces:
                obj["trace"] = traces[0]
        click.echo(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        if not result.success:
            click.echo(f"Error: {result.error}", err=True)
            sys.exit(1)
        click.echo(result.assistant_message or "")
        for name, card in (getattr(result, "panels", None) or {}).items():  # a layer's / the engine's monospace cards
            click.echo(f"┌─ {name} " + "─" * max(4, 40 - len(name)))
            from neonrp.core.panels import as_text

            for ln in as_text(card).splitlines():
                click.echo("│ " + ln)
            click.echo("└" + "─" * 44)
        for i, opt in enumerate(getattr(result, "options", None) or [], 1):  # ADV <options>: choices, never part of the prose
            click.echo(f"  {i}. {opt}")
        if show_trace:
            _echo_trace(root, session.branch)


def _repl(root: Path, agent_id: str) -> None:
    """Interactive loop: one ConversationSession lives for the whole run."""
    # Make /debug work without requiring NEONRP_DEBUG at launch.
    from neonrp.core.debug_flag import force_enable

    force_enable()

    session = ConversationSession(root=root, agent_id=agent_id, mode="play")
    click.echo(f"neonrp play · {root.name} · agent={agent_id}")
    click.echo("type /help for commands; /quit to exit.\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("")
            break
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            break
        if line in ("/help", "/?"):
            click.echo(_REPL_HELP)
            continue
        if line == "/trace":
            _echo_trace(root, session.branch)
            continue
        if line == "/debug":
            _echo_debug()
            continue
        if line == "/map":  # engine-drawn, deterministic — the same card the narrator gets from [map]
            try:
                from neonrp.core.registry import load_registry
                from neonrp.packs.rpg.tools import draw_map

                r = draw_map(root, load_registry(root), {"op": "map"})
                click.echo(r.get("text") or r.get("why") or "")
            except Exception as exc:  # noqa: BLE001
                click.echo(f"[map failed: {exc}]", err=True)
            continue

        try:
            result = session.send(line)
        except Exception as exc:  # noqa: BLE001 — REPL must survive a bad turn
            click.echo(f"[turn crashed: {exc}]", err=True)
            continue
        if not result.success:
            click.echo(f"[error: {result.error}]", err=True)
        text = (result.assistant_message or "").strip()
        if text:
            click.echo(text)
        if result.route_decision:
            click.echo(f"  · {result.route_decision}")
        click.echo("")


def _echo_trace(root: Path, branch: str) -> None:
    traces = read_turn_traces(root, branch, last=1)
    if not traces:
        click.echo("(no trace yet)")
        return
    t = traces[0]
    click.echo("--- trace ---")
    click.echo(
        f"  turn_seq={t.get('turn_seq')}  loc={t.get('world_location')}  "
        f"commit={t.get('land', {}).get('commit_id', '?')}"
    )
    for s in t.get("souls", []):
        tag = "⬤" if s.get("activated") else "○"
        click.echo(
            f"  {tag} {s.get('instance_id')}: {s.get('state', '?')} · {s.get('reason', '?')}"
        )


def _echo_debug(limit: int = 12) -> None:
    from neonrp.core import debug_sink

    records = debug_sink.get_recent_calls(limit=limit)
    if not records:
        click.echo("(no agent calls recorded yet — play a turn first)")
        return
    click.echo(f"--- last {len(records)} agent calls ---")
    for rec in records:
        agent = rec.get("agent_id", "?")
        model = rec.get("model") or "-"
        dur = rec.get("duration_ms", 0)
        pt, ct = int(rec.get("prompt_tokens", 0)), int(rec.get("completion_tokens", 0))
        head = f"#{rec.get('seq', '?')} {agent}"
        if rec.get("provider") != "perception":
            head += f" · {model} · {dur}ms · in={pt} out={ct}"
        click.echo(head)
        preview = str(rec.get("text_preview") or "").replace("\n", " ")
        if preview:
            click.echo(f"   {preview[:160]}")
        err = str(rec.get("error") or "")
        if err:
            click.echo(f"   ERROR: {err[:160]}")


def _fail(msg: str, json_out: bool) -> None:
    if json_out:
        click.echo(json.dumps({"success": False, "error": msg}, ensure_ascii=False))
    else:
        click.echo(f"Error: {msg}", err=True)
    sys.exit(1)
