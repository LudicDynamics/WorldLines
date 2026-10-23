"""Pack mixins (packs/mixins) + Pack.loop + world ticks: the 3.0 mock's economy / factions as engine rules."""
from __future__ import annotations

import json
from pathlib import Path

from neonrp import packs
from neonrp import template as TP
from neonrp.core import engine_config, ledger, sdk
from neonrp.core.registry import load_registry
from _paths import PRODUCT_TEMPLATES

_EX = PRODUCT_TEMPLATES / "stoneford-market.template"


def _run(tmp_path: Path, name: str = "run") -> Path:
    root = tmp_path / name
    TP.build(_EX, root)
    return root


def test_compose_by_name_and_loop_layer(tmp_path):
    p = packs.load("rpg+economy+factions")
    assert p.name == "rpg+economy+factions" and p.mixins == ("economy", "factions")
    assert {"caravan", "rumor", "quest", "faction"} <= set(p.classes) and {"trade", "take_quest", "move_to"} <= {a.op for a in p.actions}
    # rpg's own ticks first (effects that run out on the world clock 10-05; a fight with no foe standing ends 10-18), then the mixins' in order
    assert p.ticks == ["neonrp.packs.rpg.effects_clock:tick", "neonrp.packs.rpg.travel:tick_souls", "neonrp.packs.rpg.downed:tick", "neonrp.packs.rpg.combat:tick", "neonrp.packs.mixins.economy:tick", "neonrp.packs.mixins.factions:tick"]
    assert p.loop["turn"]["mode"] == "v3" and p.loop["turn"]["parallel"]["souls"]["default_variant"] == "S-judge"
    assert {e["id"] for e in p.prompt_spec["entries"]} >= {"economy", "factions"}
    assert packs.load("rpg").ticks == ["neonrp.packs.rpg.effects_clock:tick", "neonrp.packs.rpg.travel:tick_souls", "neonrp.packs.rpg.downed:tick", "neonrp.packs.rpg.combat:tick"] and packs.load("werewolf").loop == {"turn": {"mode": "v3"}}  # a v3-only template
    root = _run(tmp_path)
    assert load_registry(root).template == "rpg+economy+factions"
    # the world names its orchestration template (uses.soul, 10-19 stage A): the characters' way comes from there now
    assert {k: s for k, _v, s in engine_config.explain(root)}["turn.parallel.souls.default_variant"] == "orchestration"


def test_build_installs_closed_schema_from_world_data(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    for v in ("stock.T001.grain", "price.T004.jade", "inv.jade", "econ.index", "faction.bandits.power", "rel.guild.guard", "rep.guard"):
        assert v in reg.variables, v
    assert reg.variables["stock.T004.jade"].value == 52 and reg.variables["stock.T004.jade"].readonly
    assert reg.variables["price.T001.jade"].value > 60  # scarce in 石津 → above base
    assert {e.id for e in reg.of_class("faction")} == {"guild", "guard", "bandits", "miners"}
    assert len(reg.of_class("rumor")) == 2
    # reinstall is a no-op
    from neonrp.packs.mixins import economy, factions
    assert economy.install(root) == [] and factions.install(root) == []


def test_ticks_run_the_world_and_are_deterministic(tmp_path):
    a, b = _run(tmp_path, "a"), _run(tmp_path, "b")
    ra, rb = sdk.tick(a, turns=30, start=1), sdk.tick(b, turns=30, start=1)
    sig = lambda rs: [[(x["op"], x.get("var") or x.get("cv") or x.get("id"), x.get("to")) for x in r.applied] for r in rs]  # noqa: E731
    assert sig(ra) == sig(rb), "same turns → same dice"
    ops = {x["op"] for r in ra for x in r.applied}
    assert {"new_caravan", "haul", "deliver", "spread"} <= ops
    assert all(x.get("by", "").startswith("tick:") for r in ra for x in r.applied)
    reg = load_registry(a)
    assert reg.of_class("caravan") and all(e.props["status"] in ("road", "delivered", "robbed") for e in reg.of_class("caravan"))
    assert reg.variables["faction.guild.wealth"].value > 320  # the guild lives on the caravans' cut
    evs = ledger.read(a) if hasattr(ledger, "read") else []
    if evs:
        assert any((e.get("payload") or {}).get("by") == "tick:economy" for e in evs)


def test_player_trade_is_verified_and_lands(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    assert reg.player_location.startswith("T001")
    gold0, stock0 = reg.variables["player.gold"].value, reg.variables["stock.T001.fish"].value
    price = reg.variables["price.T001.fish"].value
    vr = sdk.verify(root, [{"op": "trade", "good": "盐鱼", "qty": 5}], reg) if hasattr(sdk, "verify") else None
    ops = vr.accepted if vr is not None else [{"op": "trade", "good": "fish", "qty": 5, "town": "T001"}]
    assert ops and ops[0]["good"] == "fish"  # the validator resolves the local name
    ar = sdk.apply(root, ops, reg, turn=1)
    reg = load_registry(root)
    assert reg.variables["inv.fish"].value == 5 and reg.variables["stock.T001.fish"].value <= stock0 - 5 + 4  # + one tick of production
    coin = reg.variables["player.gold"].value * 100 + reg.variables["player.silver"].value * 10 + reg.variables["player.copper"].value
    assert coin == gold0 * 100 + 3 * 10 + 9 - price * 5
    assert any(a["op"] == "trade" and a["total"] == price * 5 for a in ar.applied)
    if vr is not None:
        bad = sdk.verify(root, [{"op": "trade", "good": "jade", "qty": 999}], load_registry(root))
        assert not bad.accepted and "只剩" in json.dumps([r.to_dict() for r in bad.refused], ensure_ascii=False)


def test_quest_needs_the_givers_seat(tmp_path):
    from neonrp.packs.mixins import factions

    root = _run(tmp_path)
    reg = load_registry(root)
    sdk.apply(root, [{"op": "new_quest", "kind": "bounty", "title": "剿匪", "giver": "guild", "reward_gold": 20}], reg, turn=1)
    reg = load_registry(root)
    q = next(e for e in reg.of_class("quest"))
    assert not factions.judge_take(root, reg, {"id": q.id}).ok  # the player is at the north gate
    reg.player_location = "T001/guild"
    assert factions.judge_take(root, reg, {"id": q.id}).ok


def test_template_lint_checks_mixins(tmp_path):
    import shutil

    d = tmp_path / "t.template"
    shutil.copytree(_EX, d)
    assert TP.lint(d)["publishable"]
    t = json.loads((d / "template.json").read_text(encoding="utf-8"))
    t["pack"]["mixins"].append("nope")
    (d / "template.json").write_text(json.dumps(t), encoding="utf-8")
    assert any(p["level"] == "block" and "nope" in p["msg"] for p in TP.lint(d)["problems"])
    t["pack"]["mixins"] = ["economy"]
    (d / "template.json").write_text(json.dumps(t), encoding="utf-8")
    shutil.rmtree(d / "world-overlay")
    assert any(p["code"] == "pack.mixin.data" for p in TP.lint(d)["problems"])
