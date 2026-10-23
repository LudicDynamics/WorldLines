"""`neonrp engine` — the turn engine's mode for a world or a run (core/engine_config.py).

    neonrp engine mode                 show v2b | v3 and which layer it comes from
    neonrp engine mode v2b             switch this folder back to the old world-agent loop
    neonrp engine mode v3              five-phase loop (propose → verify → apply, event ledger)
    neonrp engine explain              every effective knob with its layer
    neonrp engine tick [-n 10]         the world runs on its own: pack ticks + triggers, no player, 0 token
    neonrp engine graph [--json]       the orchestration graph in effect (states + transitions, O1)
    neonrp engine hooks                what an editor may pick from: seams · handlers · triggers · ops · modes · ticks (O5)
    neonrp engine graph-test <script>  scripted lines through a stub model: state sequence · tools per node · edges walked (O6)

Writes ``game/meta/engine.json`` of the folder (a run's copy when pointed at a save). ``NEONRP_TURN_V3``
in the environment still wins — `mode` prints the source so that is never silent.
"""

from __future__ import annotations

from pathlib import Path

import click


def _world(into: str | None) -> Path:
    from neonrp.core.paths import get_data_dir_name

    root = Path(into).expanduser() if into else Path.cwd()
    if not (root / get_data_dir_name(root)).is_dir():
        raise click.ClickException(f"{root} is not a world folder (no game/).")
    return root


@click.group("engine")
def engine_group() -> None:
    """Turn-engine mode (v2b ⇄ v3) and effective engine config."""


@engine_group.command("mode")
@click.argument("mode", required=False, type=click.Choice(["v2b", "v3"]))
@click.option("--world", "into", default=None, help="World or run folder (default: cwd).")
def mode_cmd(mode: str | None, into: str | None) -> None:
    from neonrp.webui.mode_routes import set_turn_mode, turn_mode

    root = _world(into)
    st = set_turn_mode(root, mode) if mode else turn_mode(root)
    click.echo(f"turn.mode = {st['mode']}  (from {st['source']})" + (f"  → wrote {st['file']}" if mode else ""))
    if mode and st["mode"] != mode:
        click.echo(f"note: the {st['source']} layer overrides it (unset NEONRP_TURN_V3 to take effect)", err=True)


@engine_group.command("explain")
@click.option("--world", "into", default=None)
def explain_cmd(into: str | None) -> None:
    from neonrp.core import engine_config

    for k, v, src in engine_config.explain(_world(into)):
        click.echo(f"{k:48} {v!r:24} {src}")


@engine_group.command("graph")
@click.option("--world", "into", default=None, help="World or run folder (default: cwd).")
@click.option("--json", "as_json", is_flag=True, help="The graph as JSON (worldlines.orchestration/1).")
@click.option("--default", "dflt", is_flag=True, help="The engine's default graph, without the run / template override.")
@click.option("--template", "tpl", default=None, help="A template id or folder instead of a run (built in a throwaway copy).")
def graph_cmd(into: str | None, as_json: bool, dflt: bool, tpl: str | None) -> None:
    """The orchestration graph in effect: nodes (states) and edges (transitions) — O1, 10-05."""
    import json as _json

    from neonrp.core import orchestration

    if tpl:
        from neonrp.template import v3

        try:
            r = v3.graph_of(tpl)
        except KeyError as exc:
            raise click.ClickException(str(exc)) from exc
        g = r["default"] if dflt else r["graph"]
    else:
        root = _world(into)
        g = orchestration.default_graph(root) if dflt else orchestration.graph(root)
    click.echo(_json.dumps(g, ensure_ascii=False, indent=1) if as_json else orchestration.describe(g))


@engine_group.command("hooks")
@click.option("--world", "into", default=None, help="World or run folder (default: cwd).")
def hooks_cmd(into: str | None) -> None:
    """What an orchestration editor may pick from (O5): seams, handlers, edge triggers, judges, ops, modes, ticks (JSON)."""
    import json as _json

    from neonrp.core import orchestration

    click.echo(_json.dumps(orchestration.hooks(_world(into)), ensure_ascii=False, indent=1))


@engine_group.command("graph-test")
@click.argument("script", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, help="The result as JSON.")
def graph_test_cmd(script: str, as_json: bool) -> None:
    """Run a scripted line list through a stub model (O6): the state sequence, each node's tools, the edges walked."""
    import json as _json

    from neonrp.core import graph_test

    res = graph_test.run(_json.loads(Path(script).read_text(encoding="utf-8")))
    click.echo(_json.dumps(res, ensure_ascii=False, indent=1) if as_json else graph_test.describe(res))


@engine_group.command("tick")
@click.option("-n", "--turns", default=1, show_default=True, help="How many world steps.")
@click.option("--world", "into", default=None, help="World or run folder (default: cwd).")
def tick_cmd(turns: int, into: str | None) -> None:
    from neonrp.core import sdk

    root = _world(into)
    for r in sdk.tick(root, turns=turns):
        acts = [a for a in r.applied if a.get("op") not in ("add", "set")]
        line = " · ".join(f"{a['op']} {a.get('cv') or a.get('id') or a.get('good') or ''}".strip() for a in acts)
        changed = sum(1 for a in r.applied if a.get("op") in ("add", "set"))
        click.echo(f"turn {r.turn}: {changed} values changed" + (f" · {line}" if line else "") + (f" · ENDED {r.ended['id']}" if r.ended else ""))
