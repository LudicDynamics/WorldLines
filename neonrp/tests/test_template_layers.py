"""Stage A of the template layers (docs/planning/TEMPLATE-LAYERS-1019.md §3.2 step 3): a world names the orchestration
template it plays (template.json ``uses``) instead of having its play contract turn the planning beat on.

The check that the move changed nothing: for every official world, what a run plays with — the engine settings, the
orchestration graph and how each character acts — is computed two ways and must be the same item by item:

- **old**: the frozen record ``data/template_layers_baseline.<private|public>.json`` (written by :func:`snapshot` on
  NeonRP c295fee9 + NeonRP-private 5e48207, the code before this change; one record with the private layer — it names the
  private beat's prompts and tools, so it stays out of the open export — and one without);
- **new**: the same function now (the world's ``uses``), and once more with ``uses`` taken out (an old package: the
  template is inferred the old way).

neon-rebirth (七夜) is checked on its own as well: it plays the two beats now (23d81c4c), where it used to copy
stoneford-town's single beat.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from neonrp.core import node_kinds
from neonrp.core.paths import private_dir

ROOT = Path(__file__).resolve().parents[1]
TPLS = ROOT / "worldlines" / "templates"
DATA = Path(__file__).resolve().parent / "data"
WORLDS = ("guixiang", "kagura-island", "last-train", "neon-rebirth", "pct-house", "spice-witch", "stoneford-elena",
          "stoneford-market", "stoneford-three-towns", "stoneford-town", "werewolf-night-village", "wuwu")
ONE_BEAT: set[str] = {"werewolf-night-village"}   # 10-19: all twelve play the two beats — 狼人村 waits (pending: its resolve does not land vote / kill on two beats yet)
# switched to the two beats after parity was proven (their own commit): the only settings that differ from the old loading
SWITCHED = {"private": {"stoneford-town": {".desk_engine.turn.plan_loop": ("off", "on"), ".engine.turn.plan_loop": ("off", "on")},
                        },
            "public": {"stoneford-town": {".desk_engine.turn.plan_loop": ("off", None), ".engine.turn.plan_loop": ("off", None)}}}
PRIVATE = node_kinds.get("plan") is not None and private_dir("orchestrations") is not None


def _canon(x: Any) -> Any:
    return json.loads(json.dumps(x, ensure_ascii=False, sort_keys=True, default=str))


def snapshot(t: Any) -> dict[str, Any]:
    """What a run of template ``t`` plays with: the engine settings the desk sees (template layers, merged), the built
    run's effective engine settings (both without the env layer), its orchestration graph, and each character's way of acting in the world's turn
    (core/turn_runner: ``per_soul[sid]`` else ``default_variant``, legacy whenever the turn is not v3). Only APIs the code
    before stage A already had — the baseline was written with this same function."""
    from neonrp.core import engine_config as EC
    from neonrp.core import orchestration as OR
    from neonrp.core import soul_orchestration as SO
    from neonrp.template import v3

    desk: dict[str, Any] = {}
    for name, layer in SO._template_layers(t):
        if name != "env":   # experiments' env vars (the test session sets some) are not the world's
            desk = EC._deep_merge(desk, layer)
    with v3._scratch(t, None) as root:
        cfg: dict[str, Any] = {}
        for name, layer in EC._layers(root):
            if name != "env":
                cfg = EC._deep_merge(cfg, layer)
        g = OR.graph(root)
        graph = {"start": g.get("start"), "nodes": g.get("nodes"), "edges": g.get("edges"), "units": g.get("units")}
    is_v3 = str(EC._get_path(cfg, "turn.mode", "v2b")).lower() == "v3"
    dflt = str(EC._get_path(cfg, "turn.parallel.souls.default_variant", "legacy"))
    per = EC._get_path(cfg, "turn.parallel.souls.per_soul", {}) or {}
    souls = {str(s.get("sid")): (str(per.get(str(s.get("sid"))) or dflt) if is_v3 else "legacy")
             for s in t.data.get("souls") or [] if isinstance(s, dict) and s.get("sid")}
    return _canon({"desk_engine": desk, "engine": cfg, "graph": graph, "souls": souls})


def _mode() -> str:
    return "private" if PRIVATE else "public"


@pytest.fixture(scope="module")
def official(tmp_path_factory):
    """The twelve official worlds as they ship, copied (the old-package variant edits template.json)."""
    import os

    d = tmp_path_factory.mktemp("official")
    for tid in WORLDS:
        if not (TPLS / f"{tid}.template").is_dir():
            continue   # the open export ships the two built-in worlds only
        shutil.copytree(TPLS / f"{tid}.template", d / f"{tid}.template", ignore=shutil.ignore_patterns("__pycache__"))
    old = os.environ.get("NEONRP_TEMPLATE_PATH")
    os.environ["NEONRP_TEMPLATE_PATH"] = str(d)
    yield d
    if old is None:
        os.environ.pop("NEONRP_TEMPLATE_PATH", None)
    else:
        os.environ["NEONRP_TEMPLATE_PATH"] = old


def _load(tid: str) -> Any:
    from neonrp import template as TP

    found = TP.discover()
    if tid not in found:
        pytest.skip(f"{tid}: not in this checkout")
    return TP.load(found[tid])


def _dig(d: Any, keys: list[str]) -> Any:
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _drop(d: Any, keys: list[str]) -> None:
    for k in keys[:-1]:
        d = d.get(k) if isinstance(d, dict) else None
    if isinstance(d, dict):
        d.pop(keys[-1], None)


def _diff(a: Any, b: Any, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: {'missing' if k not in a else repr(a[k])[:80]} vs {'missing' if k not in b else repr(b[k])[:80]}")
            else:
                out += _diff(a[k], b[k], f"{path}.{k}")
        return out
    return [] if a == b else [f"{path}: {repr(a)[:120]} vs {repr(b)[:120]}"]


@pytest.mark.parametrize("tid", WORLDS)
def test_every_world_names_its_template(tid):
    if not (TPLS / f"{tid}.template").is_dir():
        pytest.skip(f"{tid}: not in this checkout")
    d = json.loads((TPLS / f"{tid}.template" / "template.json").read_text(encoding="utf-8"))
    u = d.get("uses")
    assert isinstance(u, dict) and u.get("template") and u.get("version"), tid
    want = "one_beat" if tid in ONE_BEAT else "two_beat"
    assert u["template"] == want, (tid, u)
    assert u.get("soul") == (None if tid == "werewolf-night-village" else "S-judge"), (tid, u)   # the characters' axis: what the pack made them do


@pytest.mark.parametrize("tid", WORLDS)
def test_new_loading_matches_the_old(official, tid):
    t = _load(tid)
    f = DATA / f"template_layers_baseline.{_mode()}.json"
    if not f.is_file():
        pytest.skip(f"{f.name}: not in this checkout")
    base = json.loads(f.read_text(encoding="utf-8"))["worlds"][tid]
    new = snapshot(t)
    want = SWITCHED.get(_mode(), {}).get(tid, {})
    for path, (old, now) in want.items():   # the switched worlds: exactly these settings changed, nothing else
        keys = path.strip(".").split(".")
        assert _dig(base, keys) == old and _dig(new, keys) == now, (tid, path, _dig(base, keys), _dig(new, keys))
        _drop(base, keys)
        _drop(new, keys)
    assert _diff(base, new) == [], tid


@pytest.mark.parametrize("tid", WORLDS)
def test_an_old_package_without_uses_plays_the_same(official, tid):
    _load(tid)
    f = official / f"{tid}.template" / "template.json"
    raw = f.read_text(encoding="utf-8")
    d = json.loads(raw)
    d.pop("uses", None)
    try:
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        old = snapshot(_load(tid))
    finally:
        f.write_text(raw, encoding="utf-8")
    assert _diff(old, snapshot(_load(tid))) == [], tid


@pytest.mark.skipif(not PRIVATE, reason="needs the private layer (the planning beat)")
def test_neon_rebirth_plays_the_two_beats(official):
    """七夜: a plain sandbox mystery (10-19) — the two beats, from its template, no longer a copy of the single beat."""
    from neonrp.core import engine_config as EC
    from neonrp.template import v3

    t = _load("neon-rebirth")
    assert t.data["uses"] == {"template": "two_beat", "version": "1.0", "soul": "S-judge"} and t.play_contract.startswith("mystery-trpg")
    assert "plan_loop" not in ((t.pack.get("engine") or {}).get("turn") or {})
    with v3._scratch(t, None) as root:
        assert EC.get(root, "turn.plan_loop") == "on"
        src = {k: s for k, _v, s in EC.explain(root)}
        assert src["turn.plan_loop"] == "orchestration", "the template turns it on, not the contract"
        from neonrp.core import orchestration as OR

        assert "plan" in OR.graph(root)["nodes"]


# ── the world's player-action block: ``act`` → ``player_action`` (§6; the old name still reads) ─────────────────────

def test_the_player_action_block_has_its_new_name_and_the_old_one_reads():
    p = node_kinds.get("player_action")
    assert p is not None and p.kind == "player_action"
    assert node_kinds.get("act") is p and node_kinds.canonical("act") == "player_action"
    assert "act" not in node_kinds.kinds() and "player_action" in node_kinds.kinds()


def test_the_players_own_move_takes_the_turn_before_any_talk():
    order = node_kinds.turn_order()
    assert order[0] == "player_action", order
    if "plan" in order:   # sorted by name alone, plan would come first now
        assert order.index("player_action") < order.index("plan")


def test_a_graph_node_of_the_old_kind_is_still_the_blocks(tmp_path):
    from test_engine_v3 import _install

    from neonrp.core import orchestration as OR

    root = _install(tmp_path / "run")
    g = OR.graph(root)
    g = {**g, "nodes": {**g["nodes"], "pick": {"kind": "act"}}}
    assert not [w for w in OR.lint_runnable(root, g) if w["msg"].startswith("pick:")]


# ── the templates themselves ────────────────────────────────────────────────

def test_the_open_templates_and_the_fallback(monkeypatch):
    from neonrp.core import orch_templates as OT

    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    assert [t["id"] for t in OT.templates()] == ["one_beat"]
    assert OT.get("two_beat") is None
    assert OT.resolve("two_beat")["id"] == "one_beat", "the plain turn"
    assert OT.layer({"template": "two_beat", "version": "1.0", "soul": "S-judge", "params": {"pace": "quick"}}, contract=True) == \
        {"turn": {"parallel": {"souls": {"default_variant": "S-judge"}}}}
    assert OT.layer(None, contract=True) == {} and OT.layer(None, contract=False) == {}


@pytest.mark.skipif(not PRIVATE, reason="needs the private layer (the two-beat template)")
def test_the_two_beat_template_and_its_quick_pace():
    from neonrp.core import orch_templates as OT

    t = OT.get("two_beat")
    assert t is not None and t["world"]["nodes"] == ["plan", "resolve"] and t["soul"]["variant"] == "legacy"
    assert OT.layer({"template": "two_beat"}, contract=False)["turn"]["plan_loop"] == "on"
    souls = lambda u: OT.layer(u, contract=False)["turn"]["parallel"]["souls"]["default_variant"]  # noqa: E731
    assert souls({"template": "two_beat"}) == "legacy" and souls({"template": "two_beat", "soul": "S-judge"}) == "S-judge", \
        "the characters' orchestration is the world's own axis (uses.soul), the template only gives the default"
    quick = OT.layer({"template": "two_beat", "params": {"pace": "quick"}}, contract=False)["turn"]
    assert (quick["plan_loop_max_rounds"], quick["plan_loop_nudge_at"], quick["plan_loop_talk_limit"]) == (2, 2, 6)
    assert OT.layer(None, contract=True) == {"turn": {"plan_loop": "on"}}, "an old package with a contract: the two beats, no characters' part"
    assert OT.ref(OT.from_ref("two_beat?pace=normal")) == "two_beat", "a parameter at its default is not written"
