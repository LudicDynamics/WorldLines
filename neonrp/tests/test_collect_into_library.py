"""Who a run lets the player collect goes into their record (lead 10-18, web-create's audit): the plots' collect rules
(settlement ``collected``) are gained as characters (``how = collect:<why>``), plot NPC entries (the creation desk's
mine_N01) are characters the engine can take home (ending / companion / the truth quiz's reward), their snapshot is made
the way the phone makes their folder, the settlement screen gets their name; a Free-Zone run collects nobody; what was
gained goes up with the collection sync."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from neonrp import template
from neonrp.core import collection_sync as CS
from neonrp.core import player_data, rewards, sdk, soul_chat, truth_quiz
from neonrp.core.registry import load_registry

TEMPLATES = Path(__file__).resolve().parents[1] / "worldlines" / "templates"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr(player_data, "HOME", tmp_path / "player-data")
    rewards._STORE.clear()


def _copy(name: str, tmp_path: Path, edit=None) -> Path:
    cp = tmp_path / f"{name}-copy.template"
    shutil.copytree(TEMPLATES / f"{name}.template", cp, ignore=shutil.ignore_patterns("__pycache__"))
    if edit is not None:
        edit(cp)
    return cp


def _build(src: Path, dest: Path) -> Path:
    template.build(template.load(src), dest)
    return dest


def _beat(root: Path, turn: int, says: str = "", ops: list | None = None):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def _edit_json(p: Path, fn) -> None:
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _amu_back(cp: Path) -> None:
    """阿沐 (N201) may come home again: niko 10-20 made only Elena takeable in 石津镇 (props.takeable: false and no collect
    rule); these tests use the stoneford copy as it was to test the NPC paths themselves."""
    def f(d):
        d["entries"]["N201"]["props"]["takeable"] = True
        d.setdefault("collect", {})["N201"] = {"on": "clear", "rarity": "rare"}
    _edit_json(cp / "plots" / "P20" / "plot.json", f)


def _stoneford_amu(tmp_path: Path) -> Path:
    return _copy("stoneford-town", tmp_path, _amu_back)


def _stoneford_e1(root: Path):
    _beat(root, 1, "", [{"op": "flag", "key": "amu_found"}])
    r = _beat(root, 2, "", [{"op": "flag", "key": "coffin_answered"}])
    assert r.ended and r.ended["id"] == "E1" and r.settled
    return r


def test_the_official_stoneford_no_longer_lets_amu_go(tmp_path):
    root = _build(TEMPLATES / "stoneford-town.template", tmp_path / "run")
    assert not player_data.run_souls(root)["N201"]["takeable"]
    r = _stoneford_e1(root)
    assert not [c for c in r.settled["collected"] if c["who"] == "N201"] and not player_data.read()["characters"]


def test_a_templates_collect_rule_goes_into_the_record(tmp_path):
    root = _build(_stoneford_amu(tmp_path), tmp_path / "run")
    souls = player_data.run_souls(root)
    assert souls["N201"]["npc"] and souls["N201"]["name"] == "阿沐" and souls["N201"]["take_when"] == "clear", "the plot NPC is a character"
    r = _stoneford_e1(root)
    row = next(c for c in r.settled["collected"] if c["who"] == "N201")
    assert row["iid"] == "N201" and row["name"] == "阿沐" and row["cls"] == "npc", "the screen's face from the run's entry"
    got = {c["sid"]: c for c in player_data.read()["characters"]}
    assert got["N201"]["how"] == "collect:clear:E1" and got["N201"]["npc"] and got["N201"]["world"] == "stoneford-town"
    assert got["N201"]["rarity"] == "rare" and got["N201"]["memory"] == "fresh", "as written, like the settlement's floor"
    assert soul_chat._obtained("stoneford-town", "N201"), "the phone: gained, so it may be chatted with"


def test_a_free_zone_run_collects_nobody(tmp_path):
    src = _copy("stoneford-town", tmp_path, lambda cp: _edit_json(cp / "template.json", lambda d: (d.update(zone="open"), d.pop("forkable", None))))
    r = _stoneford_e1(_build(src, tmp_path / "run"))
    assert r.settled["collected"] == [] and player_data.read()["characters"] == []


def test_a_creation_desk_npc_comes_home_at_the_ending_or_as_a_companion(tmp_path):
    from neonrp.template import creation

    os.environ["NEONRP_TEMPLATE_WRITE_DIR"] = str(tmp_path / "mine")
    try:
        town = template.load(TEMPLATES / "stoneford-town.template")
        add = {"soul": [{"name": "阿青", "persona": "沉默的猎人", "collect": "clear"}, {"name": "老韩", "persona": "渡口的船夫"}],
               "ending": [{"title": "雾散", "kind": "true", "text": "雾散了"}],
               "rule": [{"trigger": {"when": {"text": "player"}, "if": [{"text": "脚印"}], "then": [{"to": "end", "ending": "#1"}], "once": True}}]}
        w = creation.save(town, add, work_id="stoneford-town-mine")
    finally:
        os.environ.pop("NEONRP_TEMPLATE_WRITE_DIR", None)
    # the desk does not place its characters yet: put 老韩 at the north gate (where the run starts) like an author would
    _edit_json(w.dir / "plots" / "mine" / "plot.json", lambda d: d["entries"]["mine_N02"].update(parent="T001/gate_north"))
    root = _build(w.dir, tmp_path / "run")
    souls = player_data.run_souls(root)
    assert souls["mine_N01"]["name"] == "阿青" and souls["mine_N01"]["take_when"] == "clear"
    assert souls["mine_N02"]["take_when"] == "companion_at_ending", "no rule: the one standing with the player at the ending"
    assert load_registry(root).entries["mine_N02"].parent == load_registry(root).player_location
    r = _beat(root, 1, "我看见泥里的脚印")
    assert r.ended and r.settled
    got = {c["sid"]: c for c in player_data.read()["characters"]}
    assert got["mine_N01"]["how"].startswith("collect:clear:") and got["mine_N01"]["name"] == "阿青"
    assert got["mine_N02"]["how"] == "companion_at_ending" and got["mine_N02"]["memory"] == "full"
    snap = soul_chat.snapshot_dir("stoneford-town-mine", "mine_N02")  # soul-drive's phone folder (npc_dir) → the full-memory snapshot
    assert json.loads((snap / "soul.json").read_text(encoding="utf-8"))["sid"] == "mine_N02" and "老韩" in (snap / "soul.md").read_text(encoding="utf-8")


def test_the_truth_quiz_reward_can_be_a_plot_npc(tmp_path):
    def add_npc(cp: Path) -> None:
        def f(d):
            d["entries"]["N9"] = {"class": "npc", "name": "老园丁", "parent": "T001/steps", "props": {"persona": "在宅子里干了三十年"}}
            d["truth_quiz"]["reward_soul"] = "N9"
        _edit_json(cp / "plots" / "P01" / "plot.json", f)
    root = _build(_copy("pct-house", tmp_path, add_npc), tmp_path / "run")
    assert truth_quiz.reward_soul(root) == {"iid": "N9", "sid": "N9", "name": "老园丁"}
    _beat(root, 1, "", [{"op": "set", "var": "P01.stage", "value": 1}])
    assert _beat(root, 2, "我要离开这里,逃出去").settled
    res = truth_quiz.answer(root, [1, 2, 0])
    assert res.get("all_right"), res
    got = {c["sid"]: c for c in player_data.read()["characters"]}
    assert got["N9"]["how"] == "truth_quiz" and got["N9"]["memory"] == "full" and got["N9"]["name"] == "老园丁"


def test_a_plot_npc_taken_with_full_memory_has_its_snapshot_and_the_phone_uses_it(tmp_path):
    """Full memory = a snapshot made from the phone's own folder for the NPC (soul_chat.npc_dir): what the plot says of
    it, its memory grown there comes along; the phone then talks with the snapshot. Fresh (a collect rule) = no snapshot."""
    town = _stoneford_amu(tmp_path)
    root = _build(town, tmp_path / "run")
    src = soul_chat.npc_dir("stoneford-town", "N201", {"name": "阿沐", "persona": "探路队里最年轻的一个"}, "zh")
    (src / "long-term-memo").mkdir(exist_ok=True)
    (src / "long-term-memo" / "phone.md").write_text("他在电话里说过苔墓第三间很冷", encoding="utf-8")
    assert player_data.take(root, "N201", "truth_quiz", memory="full")
    snap = soul_chat.snapshot_dir("stoneford-town", "N201")
    assert json.loads((snap / "soul.json").read_text(encoding="utf-8"))["sid"] == "N201"
    assert "阿沐" in (snap / "soul.md").read_text(encoding="utf-8")
    assert (snap / "long-term-memo" / "phone.md").read_text(encoding="utf-8") == "他在电话里说过苔墓第三间很冷", "its memory comes along"
    assert soul_chat.resolve("stoneford-town", "N201")["folder"] == snap, "the phone talks with the snapshot"
    other = _build(town, tmp_path / "run2")
    shutil.rmtree(snap)
    player_data.update("characters", {"sid": "N201", "world": "stoneford-town"}, {"memory": "fresh"})
    assert player_data.take(other, "N201", "truth_quiz", memory="full"), "fresh → full: upgraded"
    assert (snap / "soul.json").is_file(), "the upgrade makes the snapshot"


def test_what_was_collected_goes_up_with_the_sync(tmp_path, monkeypatch):
    from test_collection_sync import FakeData

    fake = FakeData()
    monkeypatch.setattr(CS, "_call", fake)
    monkeypatch.setattr(CS, "_token", lambda: "tok")
    _stoneford_e1(_build(_stoneford_amu(tmp_path), tmp_path / "run"))
    assert CS.sync()["state"] == "ok"
    ch = {b["key"]: b["character"] for b in fake.bodies("character")}
    assert ch["N201"]["how"] == "collect:clear:E1" and ch["N201"]["name"] == "阿沐"
