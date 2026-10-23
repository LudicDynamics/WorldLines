"""`neonrp schema` — the open / closed schema from the command line (core/registry.py + core/ledger.py).

Register (write one overlay entry into ``game/meta/<table>.json``, validated first):

    neonrp schema register variables price.T001.grain --spec '{"type":"int","path":"game/towns/T001/market.json","key":"price.grain","min":1}'
    neonrp schema register classes faction --spec @faction.json
    neonrp schema unregister variables price.T001.grain

Read (pull):

    neonrp schema list [variables|classes|actions|triggers|entries] [--class faction]
    neonrp schema get player.gold
    neonrp schema history player.gold
    neonrp schema events --since 120 --type var.changed

Subscribe (push, from outside the engine process — tails game/meta/events.jsonl):

    neonrp schema watch "var.changed:player.gold"
    neonrp schema watch "entity.created:*" --timeout 60

Patterns are the same as ``sdk.on``: ``*`` | ``<type>`` | ``<type>:<key>`` | ``<type>:*``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click

TABLE_CHOICES = ["variables", "classes", "actions", "triggers", "entries"]


def _world(into: str | None) -> Path:
    from neonrp.core.paths import get_data_dir_name

    root = Path(into).expanduser() if into else Path.cwd()
    if not (root / get_data_dir_name(root)).is_dir():
        raise click.ClickException(f"{root} is not a world folder (no game/).")
    return root


def _spec(raw: str) -> dict[str, Any]:
    text = Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
    try:
        data = json.loads(text)
    except ValueError as e:
        raise click.ClickException(f"--spec is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise click.ClickException("--spec must be a JSON object")
    return data


def _emit(obj: Any, as_json: bool) -> None:
    click.echo(json.dumps(obj, ensure_ascii=False, indent=None if as_json else 2, default=str))


_world_opt = click.option("--world", "into", default=None, help="World folder (default: cwd).")
_json_opt = click.option("--json", "as_json", is_flag=True, help="One-line JSON output.")


@click.group("schema")
def schema_group() -> None:
    """Open / closed schema: register, read, and subscribe."""


@schema_group.command("register")
@click.argument("table", type=click.Choice(TABLE_CHOICES))
@click.argument("entry_id")
@click.option("--spec", "raw", required=True, help="JSON object, or @file.json")
@click.option("--no-replace", is_flag=True, help="Fail if the id is already registered.")
@_world_opt
@_json_opt
def register_cmd(table: str, entry_id: str, raw: str, no_replace: bool, into: str | None, as_json: bool) -> None:
    """Register one entry (validated) into game/meta/<table>.json."""
    from neonrp.core.registry import RegisterError, register

    root = _world(into)
    try:
        out = register(root, table, entry_id, _spec(raw), replace=not no_replace)
    except RegisterError as e:
        raise click.ClickException(str(e)) from e
    _emit(out, as_json)


@schema_group.command("unregister")
@click.argument("table", type=click.Choice(TABLE_CHOICES))
@click.argument("entry_id")
@_world_opt
@_json_opt
def unregister_cmd(table: str, entry_id: str, into: str | None, as_json: bool) -> None:
    """Remove an overlay entry (for actions: disable the op)."""
    from neonrp.core.registry import RegisterError, register

    root = _world(into)
    try:
        out = register(root, table, entry_id, None)
    except RegisterError as e:
        raise click.ClickException(str(e)) from e
    _emit(out, as_json)


def _row(table: str, name: str, spec: Any) -> dict[str, Any]:
    if hasattr(spec, "to_dict"):
        d = spec.to_dict()
    else:
        d = {k: v for k, v in getattr(spec, "__dict__", {}).items() if not k.startswith("_") and v not in (None, "", [], {}, False)}
    d.setdefault("name" if table != "entries" else "id", name)
    return d


@schema_group.command("list")
@click.argument("table", type=click.Choice(TABLE_CHOICES), default="variables")
@click.option("--class", "cls", default=None, help="entries only: filter by class")
@_world_opt
@_json_opt
def list_cmd(table: str, cls: str | None, into: str | None, as_json: bool) -> None:
    """List a table as the engine sees it now (template pack + world files + overlays)."""
    from neonrp.core.registry import load_registry

    reg = load_registry(_world(into))
    tab = getattr(reg, table)
    items = [(k, v) for k, v in tab.items() if table != "entries" or not cls or v.cls == cls]
    if as_json:
        _emit({"template": reg.template, table: [_row(table, k, v) for k, v in items]}, True)
        return
    click.echo(f"# template: {reg.template} · {table}: {len(items)}")
    for k, v in items:
        if table == "variables":
            rng = f" [{v.min if v.min is not None else ''}..{v.max if v.max is not None else (v.max_key or '')}]" if v.min is not None or v.max is not None or v.max_key else ""
            click.echo(f"{k:32} {v.type:5} = {v.value!r}{rng}{'  (readonly)' if v.readonly else ''}")
        elif table == "classes":
            click.echo(f"{k:16} parent={v.parent_class or '-'} required={v.required} folder={v.folder or '-'}")
        elif table == "actions":
            click.echo(f"{k:16} {v.kind:6} fields={getattr(v, 'fields', [])}")
        elif table == "entries":
            click.echo(f"{k:28} {v.cls:8} parent={v.parent or '-'} {v.name}")
        else:
            click.echo(f"{k:24} {json.dumps(_row(table, k, v), ensure_ascii=False, default=str)[:120]}")


@schema_group.command("get")
@click.argument("var")
@_world_opt
@_json_opt
def get_cmd(var: str, into: str | None, as_json: bool) -> None:
    """One registered variable: current value + its spec (pull)."""
    from neonrp.core.registry import load_registry

    reg = load_registry(_world(into))
    spec = reg.variables.get(var)
    if spec is None:
        raise click.ClickException(f"{var!r} is not registered — register it first (neonrp schema register variables …)")
    _emit(spec.to_dict(), as_json)


@schema_group.command("history")
@click.argument("var")
@click.option("--since-turn", default=0, type=int)
@_world_opt
@_json_opt
def history_cmd(var: str, since_turn: int, into: str | None, as_json: bool) -> None:
    """A variable's changes from the event ledger (pull)."""
    from neonrp.core.ledger import history

    _emit(history(_world(into), var, since_turn=since_turn), as_json)


@schema_group.command("events")
@click.option("--since", default=0, type=int, help="seq to start after")
@click.option("--type", "typ", default=None, help="one ledger type, e.g. var.changed")
@click.option("--limit", default=100, type=int)
@_world_opt
def events_cmd(since: int, typ: str | None, limit: int, into: str | None) -> None:
    """Landed events from game/meta/events.jsonl, one JSON per line (pull)."""
    from neonrp.core.ledger import events

    for ev in events(_world(into), since=since, type=typ, limit=limit):
        click.echo(json.dumps(ev, ensure_ascii=False))


@schema_group.command("watch")
@click.argument("pattern", default="*")
@click.option("--since", default=None, type=int, help="seq to start after (default: now)")
@click.option("--timeout", default=0.0, type=float, help="stop after N seconds (0 = forever)")
@click.option("--interval", default=0.5, type=float)
@_world_opt
def watch_cmd(pattern: str, since: int | None, timeout: float, interval: float, into: str | None) -> None:
    """Subscribe from outside the engine: print each new event matching PATTERN (push)."""
    from neonrp.core.ledger import _matches, events

    root = _world(into)
    seq = since if since is not None else max((int(e.get("seq", 0)) for e in events(root, limit=10**9)), default=0)
    end = time.monotonic() + timeout if timeout else None
    while True:
        for ev in events(root, since=seq, limit=10**9):
            seq = max(seq, int(ev.get("seq", 0)))
            if _matches(pattern, ev):
                click.echo(json.dumps(ev, ensure_ascii=False), nl=True)
        if end is not None and time.monotonic() >= end:
            return
        time.sleep(interval)
