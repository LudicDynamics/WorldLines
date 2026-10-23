"""The planning beat + narrate-then-transition is the contract's, not an engine default — a world built from a
template that declares a contract plays that way; a world without one keeps the engine's defaults; the world's own
engine.json still wins over the contract.

10-08 (open engine · private orchestration): the turn settings are
ours — the public contracts carry no ``engine`` block; the private layer's ``contracts/<id>.engine.json`` lays it on at
run time. Without the private layer a contract changes nothing about how a turn runs.

10-19 stage A (docs/planning/TEMPLATE-LAYERS-1019.md): a contract no longer decides the orchestration — the world names an
orchestration template (``uses``) and the two-beat template turns the planning beat on; the private layer carries no
contract engine block any more. A world without ``uses`` (an old package) plays as its contract used to say.
"""
from __future__ import annotations

import json

import pytest

from neonrp import template as TP
from neonrp.core import engine_config as EC
from neonrp.template import v3

TURN = {"turn": {"plan_loop": "on"}}  # how the Resolve writes state is the graph's (10-11), not the contract's


@pytest.fixture
def private_layer(tmp_path, monkeypatch):
    """A private layer that turns on our two beats for every official contract (the shape NeonRP-private ships)."""
    d = tmp_path / "private" / "contracts"
    d.mkdir(parents=True)
    for cid in ("mystery-trpg", "open-adventure", "murder-mystery", "romance-companion"):
        (d / f"{cid}.engine.json").write_text(json.dumps(TURN), encoding="utf-8")
    monkeypatch.delenv("NEONRP_PRIVATE", raising=False)
    monkeypatch.setenv("NEONRP_PRIVATE_DIR", str(tmp_path / "private"))
    return d


def _built(ref):
    t = TP.load(TP.discover()[ref])
    return t, v3._scratch(t, None)


@pytest.mark.parametrize("ref", ["pct-house", "stoneford-three-towns"])
def test_the_template_turns_on_plan_and_narrate(ref, monkeypatch):
    """The real private layer: its two-beat template (the world's ``uses``) turns the planning beat on, its contracts
    carry no turn settings."""
    for k in ("NEONRP_PLAN_LOOP", "NEONRP_V3_SOLVE", "NEONRP_TURN_V3"):
        monkeypatch.delenv(k, raising=False)
    t, sc = _built(ref)
    assert t.play_contract and t.uses["template"] == "two_beat"
    with sc as root:
        from neonrp.core import orchestration as OR

        assert EC.get(root, "turn.plan_loop") == "on" and OR.solve_structured(root) == "narrate"  # pseudo, the Resolve default
        src = {k: s for k, _v, s in EC.explain(root)}
        assert src["turn.plan_loop"] == "orchestration"
        assert "plan_loop" not in (EC._contract_engine(root).get("turn") or {}), "the contract says nothing about the beats"
        from neonrp.core import plan_loop

        assert plan_loop.enabled(root)


def test_a_contract_with_the_single_beat_template_stays_single(monkeypatch, private_layer):
    """A contract's own engine block (the private layer may still carry one) is under the template: a world on the
    single-beat template plays one beat whatever the contract's block says — unless the block sets it itself."""
    monkeypatch.delenv("NEONRP_PLAN_LOOP", raising=False)
    t, sc = _built("pct-house")
    with sc as root:
        from neonrp.core.paths import get_data_dir_name

        rec = root / get_data_dir_name(root) / "meta" / "template.json"
        d = json.loads(rec.read_text(encoding="utf-8"))
        d["uses"] = {"template": "one_beat", "version": "1.0"}
        rec.write_text(json.dumps(d), encoding="utf-8")
        assert EC.get(root, "turn.plan_loop") == "on", "the fixture's contract block still says on — and it is a lower layer"
        for f in private_layer.glob("*.engine.json"):
            f.unlink()
        assert EC.get(root, "turn.plan_loop", "off") == "off"


def test_no_contract_keeps_engine_defaults(monkeypatch):
    monkeypatch.delenv("NEONRP_PLAN_LOOP", raising=False)
    monkeypatch.delenv("NEONRP_V3_SOLVE", raising=False)
    t, sc = _built("werewolf-night-village")
    assert not t.play_contract
    with sc as root:
        from neonrp.core import orchestration as OR
        from neonrp.core.paths import get_data_dir_name

        assert OR.state_mode(root)["mode"] == "pseudo"
        assert "plan_loop" not in (EC._contract_engine(root).get("turn") or {}), "no contract: nothing from a contract"
        # 10-19: it stays on the single beat for now (its uses: one_beat) — pending niko, the two beats do not land its votes yet
        assert t.uses["template"] == "one_beat" and EC.get(root, "turn.plan_loop", "off") == "off"
        rec = root / get_data_dir_name(root) / "meta" / "template.json"
        d = json.loads(rec.read_text(encoding="utf-8"))
        d.pop("uses", None)
        rec.write_text(json.dumps(d), encoding="utf-8")
        assert EC.get(root, "turn.plan_loop", "off") == "off", "an old package of it (no uses, no contract) keeps the engine's defaults"


@pytest.mark.parametrize("ref", ["pct-house", "stoneford-three-towns"])
def test_public_contracts_carry_no_turn_settings(ref, monkeypatch):
    """The open repo ships the contract format only: no engine block, and without the private layer no two beats."""
    for k in ("NEONRP_PLAN_LOOP", "NEONRP_V3_SOLVE", "NEONRP_TURN_V3"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    from neonrp.template import contract as C

    for cid in C.available():
        assert "engine" not in C.load(cid), f"{cid}: turn settings belong in NeonRP-private/contracts/{cid}.engine.json"
    t, sc = _built(ref)
    with sc as root:
        assert EC.get(root, "turn.plan_loop", "off") == "off"


def test_world_engine_json_overrides_the_template(monkeypatch):
    monkeypatch.delenv("NEONRP_PLAN_LOOP", raising=False)
    t, sc = _built("pct-house")
    with sc as root:
        p = root / "game" / "meta" / "engine.json"
        p.write_text(json.dumps({"turn": {"plan_loop": "off"}}), encoding="utf-8")
        assert EC.get(root, "turn.plan_loop") == "off"
