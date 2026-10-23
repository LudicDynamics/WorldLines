"""`neonrp schema` — register / list / get / history / events / watch on a real template world."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

import neonrp
from neonrp.commands.schema_cmd import schema_group
from neonrp.core import ledger

TEMPLATE = Path(neonrp.__file__).parent / "templates" / "stoneford-elena"


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dst = tmp_path / "w"
    shutil.copytree(TEMPLATE, dst)
    return dst


def run(world: Path, *args: str):
    r = CliRunner().invoke(schema_group, [*args, "--world", str(world)])
    return r


def test_register_variable_then_list_and_get(world: Path):
    spec = json.dumps({"type": "int", "path": "game/towns/T001/market.json", "key": "price.grain", "min": 1, "max": 99})
    r = run(world, "register", "variables", "price.T001.grain", "--spec", spec, "--json")
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["path"].endswith("meta/variables.json")
    r = run(world, "list", "variables", "--json")
    names = [v["name"] for v in json.loads(r.output)["variables"]]
    assert "price.T001.grain" in names and "player.gold" in names
    r = run(world, "get", "price.T001.grain", "--json")
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["max"] == 99


def test_register_rejects_bad_spec(world: Path):
    r = run(world, "register", "variables", "bad", "--spec", json.dumps({"type": "money", "path": "x", "key": "y"}))
    assert r.exit_code != 0 and "int|float|str|bool" in r.output
    r = run(world, "register", "entries", "F001", "--spec", json.dumps({"class": "faction", "props": {"name": "x"}}))
    assert r.exit_code != 0 and "register it in classes first" in r.output
    r = run(world, "get", "nope.var")
    assert r.exit_code != 0 and "not registered" in r.output


def test_open_schema_class_then_entry(world: Path):
    cls = {"required": ["name"], "folder": "game/factions", "props": {"power": {"type": "int", "min": 0, "max": 100}}, "mutable": ["power"]}
    r = run(world, "register", "classes", "faction", "--spec", json.dumps(cls))
    assert r.exit_code == 0, r.output
    r = run(world, "register", "entries", "F_bandits", "--spec", json.dumps({"class": "faction", "props": {"name": "独眼虎山贼", "power": 46}}))
    assert r.exit_code == 0, r.output
    r = run(world, "list", "classes", "--json")
    assert "faction" in [c["name"] for c in json.loads(r.output)["classes"]]


def test_unregister(world: Path):
    spec = json.dumps({"type": "int", "path": "game/x.json", "key": "a"})
    assert run(world, "register", "variables", "tmp.a", "--spec", spec).exit_code == 0
    assert run(world, "unregister", "variables", "tmp.a").exit_code == 0
    assert run(world, "get", "tmp.a").exit_code != 0


def test_history_events_and_watch(world: Path):
    ledger.append(world, 3, [("var.changed", {"var": "player.gold", "from": 18, "to": 25, "by": "solve"}),
                             ("entity.created", {"id": "N1", "class": "place"})])
    r = run(world, "history", "player.gold", "--json")
    assert json.loads(r.output)[0]["to"] == 25
    r = run(world, "events", "--type", "entity.created")
    assert json.loads(r.output.strip().splitlines()[0])["payload"]["id"] == "N1"
    r = run(world, "watch", "var.changed:player.gold", "--since", "0", "--timeout", "0.1", "--interval", "0.05")
    lines = [json.loads(x) for x in r.output.strip().splitlines()]
    assert len(lines) == 1 and lines[0]["payload"]["to"] == 25
