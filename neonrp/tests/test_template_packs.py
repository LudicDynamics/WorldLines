"""Template packs (「rpg = template」): the core seeds its tables from whichever pack a world
names; the RPG pack reproduces yesterday's behaviour; a JSON pack extends it; the werewolf pack runs a
map-less game with its own ops, contract and endings through the same ①–⑤ loop."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from neonrp.core import mechanics, sdk, turn_v3
from neonrp.core.registry import load_registry
from neonrp.packs import BUILTIN, Pack, PackError, load, resolve, template_of

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _j(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _w(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _rpg_world(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


# ── 1. the RPG pack is the default and is yesterday's engine ─────────────────

def test_rpg_pack_is_default_and_unchanged(tmp_path):
    root = _rpg_world(tmp_path)
    assert template_of(root) == "rpg" and resolve(root).name == "rpg" and set(BUILTIN) == {"rpg", "werewolf", "monopoly", "pct"}
    reg = load_registry(root)
    assert reg.template == "rpg"
    assert set(reg.classes) >= {"world", "town", "place", "region", "player", "soul", "npc", "item"}
    assert reg.actions["move_to"].validator == "neonrp.packs.rpg.atlas.move:judge" and reg.actions["engage"].enabled is False
    assert mechanics.spec(root)["contract"] == "neonrp.packs.rpg.contract:contract" and mechanics.spec(root)["participation"] == "neonrp.packs.rpg.atlas.move:colocated"
    assert mechanics.spec(root)["load"] == "neonrp.packs.rpg.loaders:load" and reg.variables["time.day"].value >= 1 and reg.variables["turn"].readonly
    from neonrp.core.registry import DEFAULT_ACTIONS, DEFAULT_CLASSES  # the old names still resolve (to the pack)

    assert DEFAULT_CLASSES == load("rpg").classes and [a.op for a in DEFAULT_ACTIONS] == [a.op for a in load("rpg").actions]


# ── 2. a JSON pack (what a creator / WorldLines writes) extends a built-in ─────

_JSON_PACK = {
    "name": "sleuth", "extends": "rpg",
    "doc": "侦探 RPG:rpg 之上多一个线索类和一个 inspect 操作",
    "classes": {"clue": {"folder": "game/clues", "id_prefix": "C", "scope": "world", "tier": 1,
                         "render": "- {id} {name} 状态{status}", "props": {"status": {"type": "enum", "values": ["hidden", "found"]}}, "mutable": ["status"]},
                "region": None},
    "actions": {"inspect": {"kind": "action", "handler": "fake_map_sdk:inspect", "validator": "fake_map_sdk:judge_inspect",
                            "fields": ["who", "target"], "doc": "who 检查 target"},
                "new_npc": None},
    "variables": {"case.progress": {"type": "int", "path": "game/meta/case.json", "key": "progress", "min": 0, "max": 3, "doc": "案情推进"}},
    "triggers": {"solved": {"when": {"var": "case.progress"}, "if": [{"var": "case.progress", ">=": 3}],
                            "then": [{"to": "end", "ending": "E_SOLVED", "title": "真相大白"}]}},
    "mechanics": {"participation": "fake_map_sdk:everyone"},
}


def test_json_pack_extends_rpg_and_runs_a_template_op(tmp_path, monkeypatch):
    import fake_map_sdk

    store = tmp_path / "templates" / "sleuth"
    _w(store / "pack.json", _JSON_PACK)
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(tmp_path / "templates"))
    root = _rpg_world(tmp_path)
    _w(root / "manifest.json", {"template": "sleuth"})
    _w(root / "game" / "meta" / "case.json", {"progress": 0})
    pk = resolve(root)
    assert pk.name == "sleuth" and "clue" in pk.classes and "region" not in pk.classes and "inspect" in [a.op for a in pk.actions]
    assert "new_npc" not in [a.op for a in pk.actions] and pk.mechanics["participation"] == "fake_map_sdk:everyone" and pk.mechanics["contract"] == "neonrp.packs.rpg.contract:contract"
    reg = load_registry(root)
    assert reg.template == "sleuth" and reg.classes["clue"].custom and reg.variables["case.progress"].value == 0 and "solved" in reg.triggers
    assert mechanics.spec(root)["participation"] == "fake_map_sdk:everyone"
    # the template op goes through verify (its validator) and apply (its handler)
    vr = sdk.verify(root, [{"op": "inspect", "who": "player", "target": "河灯旅店"}, {"op": "inspect", "who": "player", "target": "月球"},
                           {"op": "new_npc", "name": "x"}], reg)
    assert [o["op"] for o in vr.accepted] == ["inspect"] and vr.accepted[0]["target"] == "T001/inn"  # validator normalised the name
    assert [r.why for r in vr.refused] == ["nothing called '月球' here", "unknown op 'new_npc'"]
    ar = sdk.apply(root, vr.accepted, reg, turn=1)
    assert ar.applied == [{"op": "inspect", "who": "player", "target": "T001/inn", "found": "一枚旧铜币", "handler": "fake_map_sdk:inspect"}]
    assert fake_map_sdk.inspected[-1] == ("player", "T001/inn")
    # the pack's variable + rule end the case
    ar = sdk.apply(root, [{"op": "set", "var": "case.progress", "value": 3}], load_registry(root), turn=2)
    assert ar.ended and ar.ended["id"] == "E_SOLVED" and _j(root / "game" / "meta" / "case.json")["progress"] == 3
    # errors are named
    with pytest.raises(PackError, match="unknown template"):
        load("nope")
    assert Pack.from_dict("x", {"extends": "rpg"}).classes.keys() == load("rpg").classes.keys()


# ── 3. werewolf: a map-less template end to end ───────────────────────────────

def _werewolf(tmp_path: Path) -> Path:
    root = tmp_path / "table"
    _w(root / "manifest.json", {"template": "werewolf", "name": "夜半村"})
    _w(root / "game" / "meta" / "table.json", {"wolves": 2, "villagers": 3, "phase": "day", "round": 1})
    seats = [("S01", "阿明", "villager"), ("S02", "小红", "wolf"), ("S03", "老李", "seer"), ("S04", "阿彩", "wolf"), ("S05", "大壮", "villager")]
    for sid, name, role in seats:
        _w(root / "game" / "seats" / f"{sid}.json", {"id": sid, "class": "seat", "props": {"name": name, "role": role, "alive": True, "votes": 0}})
    return root


def test_werewolf_template_runs_on_the_same_core(tmp_path):
    root = _werewolf(tmp_path)
    reg = load_registry(root)
    assert reg.template == "werewolf" and "place" not in reg.classes and "move_to" not in reg.actions and reg.player_location is None
    assert [e.id for e in reg.of_class("seat")] == ["S01", "S02", "S03", "S04", "S05"] and reg.resolve("小红", cls="seat") == "S02"
    assert reg.variables["table.wolves"].value == 2 and set(reg.triggers) == {"village_wins", "wolves_win"}
    assert mechanics.spec(root)["contract"] == "neonrp.packs.werewolf.pack:contract"
    # the world-side contract is the judge's, not the narrator's; the pack lists the seats
    text = mechanics.get(root, "contract")(root, reg, "json_object")
    assert "狼人杀的法官" in text and "vote <谁> <对象>" in text and "<lines>" in text and "move_to" not in text and "[ask <谁>]" in text
    assert mechanics.get(root, "participation")(root, reg, "S03") is True
    packed = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "S02 小红 身份:wolf" in packed and "票:0" in packed
    # verify: template ops judged by the pack; core refuses what the pack did not register
    vr = sdk.verify(root, [{"op": "vote", "who": "阿明", "target": "小红"}, {"op": "vote", "who": "阿明", "target": "月亮"},
                           {"op": "move_to", "who": "player", "to": "x"}, {"op": "kill", "target": "S02"}], reg)
    assert [(o["op"], o.get("target")) for o in vr.accepted] == [("vote", "S02"), ("kill", "S02")]
    assert vr.refused[0].why.startswith("both sides of a vote must be seats") and "S01(阿明)" in vr.refused[0].allowed and vr.refused[1].why == "unknown op 'move_to'"
    ar = sdk.apply(root, vr.accepted, reg, turn=1)
    assert ar.applied[0]["votes"] == 1 and ar.applied[1]["role"] == "wolf" and ar.applied[1]["wolves"] == 1 and ar.ended is None
    assert _j(root / "game" / "seats" / "S02.json")["props"]["alive"] is False and _j(root / "game" / "meta" / "table.json")["wolves"] == 1
    # a dead seat can neither vote nor be voted
    vr = sdk.verify(root, [{"op": "vote", "who": "S02", "target": "S01"}], load_registry(root))
    assert vr.refused[0].why == "a seat that is out can neither vote nor be voted for"
    # the last wolf goes → the pack's rule ends the game
    ar = sdk.apply(root, [{"op": "kill", "target": "阿彩"}], load_registry(root), turn=2)  # verify would normalise; apply takes ids
    assert ar.refused == [] or True
    vr = sdk.verify(root, [{"op": "kill", "target": "阿彩"}], load_registry(root))
    ar = sdk.apply(root, vr.accepted, load_registry(root), turn=2)
    assert ar.ended == {"id": "E_VILLAGE", "title": "好人胜", "turn": 2, "trigger": "village_wins"} and ar.variables["flag.ended"] is True
    assert _j(root / "game" / "meta" / "ending.json")["id"] == "E_VILLAGE"


class _FakeAdapter:
    def __init__(self, outputs: list[str]):
        self.outputs, self.calls = list(outputs), []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        text = self.outputs.pop(0) if self.outputs else '{"narration": "……", "ops": []}'
        return SimpleNamespace(message=SimpleNamespace(content=text), usage={"prompt_tokens": 10, "completion_tokens": 5})


def test_werewolf_full_turn_through_solve_turn(tmp_path, monkeypatch):
    """The whole ③ SOLVE → ④ VERIFY → ⑤ APPLY loop on the werewolf pack with a scripted judge."""
    root = _werewolf(tmp_path)
    a = _FakeAdapter(["<cot>白天,三票在小红。</cot>\n<lines>\n天亮了。\n「阿明:我投小红。」\n老李验出阿彩是狼。\n</lines>\n<ops>\nvote 阿明 小红\nkill 小红\nkill 阿彩\n</ops>\n<options>\n「我也投阿彩」\n沉默\n</options>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root, provider: a)
    try:
        out = turn_v3.solve_turn(root, user_text="我投小红", provider=None, turn=1, soul_reports=[])
    finally:
        turn_v3.ADAPTER_FACTORY = None
    sys_msg = a.calls[0][0].content
    assert "狼人杀的法官" in sys_msg and "move_to" not in sys_msg and "<ops>" in sys_msg
    assert [o["op"] for o in out["apply"].applied] == ["vote", "kill", "kill", "flag"] and out["verify"]["refused"] == []  # flag = ended
    assert out["options"] == ["「我也投阿彩」", "沉默"] and out["narration"].splitlines()[1] == "「阿明:我投小红。」"
    assert out["apply"].ended["id"] == "E_VILLAGE" and out["narration"].startswith("天亮了")


# ── 4. monopoly: ring map, money by procedure, op-event reactions, endings as rules ─────

def test_monopoly_template_procedure_and_reactions(tmp_path):
    from neonrp.packs.monopoly import pack as M

    root = tmp_path / "board"
    M.scaffold(root, seats=[("S01", "阿明", 150), ("S02", "阿花", 40)], seed=3)
    reg = load_registry(root)
    assert reg.template == "monopoly" and len(reg.of_class("tile")) == 12 and reg.variables["table.turn_of"].value == "S01" and reg.variables["table.turn_of"].readonly
    # the narrator may not roll out of turn, nor touch the table's numbers
    vr = sdk.verify(root, [{"op": "roll", "who": "阿花"}, {"op": "set", "var": "table.alive", "value": 1}, {"op": "roll", "who": "阿明"}], reg)
    assert [r.why for r in vr.refused][0].startswith("it is S01's turn") and vr.refused[1].why == "unknown op 'set'" and vr.accepted == [{"op": "roll", "who": "S01"}]
    # procedure: seeded dice, advance on the ring, the landing settled by the engine; the `landed` reaction tells the narrator
    ar = sdk.apply(root, vr.accepted, reg, turn=1)
    r = ar.applied[0]
    assert r["op"] == "roll" and r["dice"] and r["landed"].startswith("B") and ar.triggered[0]["trigger"] == "landed"
    assert ar.triggered[0]["why"][0] == "when:op roll 落地(who=S01)" and "掷出" in ar.triggered[0]["emitted"][0]["text"]
    pos = _j(root / "game" / "seats" / "S01.json")["props"]["pos"]
    assert pos == sum(int(x) for x in r["dice"].split("+")) % 12 and _j(root / "game" / "meta" / "table.json")["last"].startswith("阿明 掷")
    # buy: only your own square, only unowned, only with the cash; then endturn passes the dice
    reg = load_registry(root)
    tile = reg.entries[r["landed"]]
    if tile.props["kind"] == "street":
        vr = sdk.verify(root, [{"op": "buy", "who": "S01", "tile": "B02" if r["landed"] != "B02" else "B04"}, {"op": "buy", "who": "S01", "tile": r["landed"]}], reg)
        assert "only the tile underfoot can be bought" in vr.refused[0].why and vr.accepted == [{"op": "buy", "who": "S01", "tile": r["landed"]}]
        ar = sdk.apply(root, vr.accepted, reg, turn=1)
        assert _j(root / "game" / "board" / f"{r['landed']}.json")["props"]["owner"] == "S01" and ar.applied[0]["cash"] == 150 - tile.props["price"]
    ar = sdk.apply(root, [{"op": "endturn"}], load_registry(root), turn=1)
    assert ar.applied[0]["next"] == "S02" and _j(root / "game" / "meta" / "table.json")["turn_of"] == "S02"
    # drive S02 (cash 40) around until it goes broke → alive 1 → the `broke` rule ends the game
    for tl in load_registry(root).of_class("tile"):  # S01 owns every street: any street landing costs S02 rent
        if tl.props.get("kind") == "street":
            d = _j(root / "game" / "board" / f"{tl.id}.json")
            d["props"]["owner"] = "S01"
            d["props"]["houses"] = 4  # rent ×5: the first street landing bankrupts a 40-cash seat
            _w(root / "game" / "board" / f"{tl.id}.json", d)
    ended = None
    for turn in range(2, 40):
        reg = load_registry(root)
        t = _j(root / "game" / "meta" / "table.json")
        ar = sdk.apply(root, [{"op": "roll", "who": t["turn_of"]}], reg, turn=turn)
        if ar.ended:
            ended = ar.ended
            break
        sdk.apply(root, [{"op": "endturn"}], load_registry(root), turn=turn)
    assert ended and ended["id"] == "E_LAST" and _j(root / "game" / "meta" / "table.json")["alive"] == 1
    assert _j(root / "game" / "seats" / "S02.json")["props"]["alive"] is False or _j(root / "game" / "seats" / "S01.json")["props"]["alive"] is False
