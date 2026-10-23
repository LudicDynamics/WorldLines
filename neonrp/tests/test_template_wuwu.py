"""wuwu.template — 雾港 · 涨潮之前 (Living Canvas wuwu ported to a template, 10-13).

Lints clean on the pct pack and the mystery-trpg contract; builds and opens with its three souls; the plot's triggers
settle the tide, the lamp oil and all three endings deterministically from the flags the narrator writes (no model);
and the folder carries none of the words the original rules were borrowed under."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import packs, template
from neonrp.core import adv, sdk, settlement
from neonrp.core.registry import load_registry

TPL = PRODUCT_TEMPLATES / "wuwu.template"
BANNED = re.compile(r"cthulhu|克苏鲁|\bcoc\b|sanity|理智|\bSAN\b", re.IGNORECASE)


@pytest.fixture
def run(tmp_path: Path) -> Path:
    dest = tmp_path / "run"
    template.build(template.load(TPL), dest)
    return dest


def _play(root: Path, turns: list[tuple[list[dict], str]]) -> None:
    for i, (ops, said) in enumerate(turns, 1):
        sdk.apply(root, ops, load_registry(root), turn=i, player_says=said)


def _var(root: Path, name: str):
    return load_registry(root).variables[name].value


def _exit(root: Path) -> str | None:
    st = settlement.read(root)
    return st["exit"]["id"] if st else None


def test_lints_clean_on_pct_and_the_mystery_contract():
    rep = template.lint(template.load(TPL))
    assert rep["counts"]["block"] == 0, rep["problems"]
    t = template.load(TPL)
    assert t.data["play_contract"] == "mystery-trpg@1" and t.pack_name == "pct"


def test_opens_with_its_cast_sheet_and_clock(run):
    assert packs.template_of(run) == "pct"
    reg = load_registry(run)
    assert sorted(e.name for e in reg.of_class("soul")) == sorted(["薇拉", "银鸢", "老莫"])
    assert "导航 60%" in reg.entries["player"].props["sheet"]
    assert "player.san" not in reg.variables, "定力 is the world's own variable, not the pack's"
    assert "dice" in reg.actions and "san" not in reg.actions, "the pack's mind check op is switched off (world/game/meta/actions.json)"
    doc = reg.actions["dice"].doc
    assert "定力" in doc and not BANNED.search(doc), "the model reads this world's dice words"
    assert (_var(run, "P01.tide"), _var(run, "P01.oil"), _var(run, "player.dingli")) == (8, 0, 55)
    assert "定力 55%" in reg.entries["player"].props["sheet"], "[dice 定力] rolls against the same number erosion takes"
    vr = sdk.verify(run, [{"op": "add", "var": "P01.tide", "delta": -1}], reg)
    assert vr.refused, "the tide is the triggers' to move, not the narrator's"


def test_a_location_card_is_only_in_the_prompt_there(run):
    spec = adv.prompt_spec(run)
    here = lambda: " ".join(adv.entries_for(spec, "zh", reg=load_registry(run))["keyword"])  # noqa: E731
    assert "berth_rolled" not in here()
    _play(run, [([{"op": "move_to", "who": "player", "to": "T001/berth7"}], "")])
    assert "berth_rolled" in here() and "light_rolled" not in here()


def test_four_threads_then_the_accusation_is_the_true_ending(run):
    _play(run, [
        ([{"op": "move_to", "who": "player", "to": "T001/berth7"}], ""),
        ([{"op": "flag", "key": "berth_rolled"}, {"op": "flag", "key": "ev_decoy"}], ""),
        ([{"op": "move_to", "who": "player", "to": "T001/lighthouse"}], "能借我一份灯油吗"),
        ([{"op": "flag", "key": "light_rolled"}, {"op": "flag", "key": "half_tunnel"}], ""),
        ([{"op": "flag", "key": "long_tunnel"}], "请你拿日志一分一分对"),
        ([{"op": "move_to", "who": "player", "to": "T001/workshop"}], ""),
        ([{"op": "flag", "key": "shop_rolled"}, {"op": "flag", "key": "shop_quick"}, {"op": "flag", "key": "ev_ledger"}], ""),
        ([{"op": "move_to", "who": "player", "to": "T001/outer_mole"}], ""),
        ([{"op": "flag", "key": "fog_rolled"}, {"op": "flag", "key": "fog_fumble"}], ""),
        ([{"op": "flag", "key": "long_wake"}], "沿岸追水痕"),
        ([{"op": "move_to", "who": "player", "to": "T001/office"}], ""),
    ])
    # 8 − berth − lighthouse − its long way − (workshop was quick) − fog − its fumble − its long way = 2
    assert _var(run, "P01.tide") == 2 and _var(run, "P01.oil") == 3 and _var(run, "P01.stage") == 2
    assert _exit(run) is None, "the fumble with oil in hand lights the lamp, it does not end the run"
    sdk.apply(run, [], load_registry(run), turn=12, player_says="我在海图前当众指认")
    assert _exit(run) == "E01"


def test_accusing_too_early_does_not_end(run):
    _play(run, [([{"op": "flag", "key": "ev_decoy"}], "我要指认")])
    assert _exit(run) is None


def test_the_fog_without_oil_swallows_you(run):
    _play(run, [
        ([{"op": "move_to", "who": "player", "to": "T001/outer_mole"}], ""),
        ([{"op": "flag", "key": "fog_rolled"}, {"op": "flag", "key": "fog_fumble"}], ""),
    ])
    assert _exit(run) == "E09"


def test_the_tide_runs_out(run):
    spots = ["berth", "light", "shop", "fog"]
    _play(run, [([{"op": "flag", "key": f"{s}_rolled"}, {"op": "flag", "key": f"{s}_push"}], "") for s in spots])
    assert _var(run, "P01.tide") == 0 and _exit(run) == "E02"


def test_composure_at_zero_and_wounds_end_on_the_fail_ending(run, tmp_path):
    _play(run, [([{"op": "add", "var": "player.dingli", "delta": -60}], "")])
    assert _exit(run) == "E09"
    other = tmp_path / "run2"
    template.build(template.load(TPL), other)
    _play(other, [([{"op": "add", "var": "player.hp", "delta": -11}], "")])
    assert _exit(other) == "E09"


def test_no_borrowed_rule_words_in_what_the_template_authors():
    """spec/ is generated from the engine (neonrp spec sync) and is not the template's own text."""
    hits = []
    for p in TPL.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".json", ".txt") and "spec" not in p.relative_to(TPL).parts[:1]:
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                # the one exception: the key that switches off pct's built-in op in the world's actions overlay — an
                # engine op id, not content (the op itself is gone from the registry: see the cast test)
                if p.relative_to(TPL).as_posix() == "world/game/meta/actions.json" and line.strip() == '"san": null,':
                    continue
                if BANNED.search(line):
                    hits.append(f"{p.relative_to(TPL)}:{n}: {line[:80]}")
    assert not hits, hits
