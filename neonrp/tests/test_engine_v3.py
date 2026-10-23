"""Engine v3 phase 1–3: registries (读时归一), engine.json config, SDK pack /
verify / apply, and the flagged five-phase turn (solve → verify → apply).

Baseline world = stoneford-elena. Everything is offline: the LLM
is a fake adapter, Jev is the stub backend, land_turn is patched where the
full session runs.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from neonrp.packs.rpg import contract as _rpg_contract
from neonrp.core import engine_config, place_tree, sdk, turn_v3
from neonrp.core import system_one as s1
from neonrp.core.registry import check_envelope, load_registry

_TPL = Path(__file__).resolve().parents[1] / "src" / "neonrp" / "templates" / "stoneford-elena"  # not the cwd: a CLI test may have chdir'd into a save


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


def _j(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _no_hazards(root: Path) -> None:
    """World override: nothing ever happens on the roads (tests about other things must not meet the seeded referee)."""
    wm = root / "game" / "world" / "world_map.json"
    d = _j(wm)
    d["travel"] = {"hazards": {k: {"p": 0.0} for k in ("bandit_risk", "beasts", "foggy")}}
    wm.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _register_unmapped_cellar(root: Path) -> None:
    """A place registered in entries.json but absent from town_map: judge_move refuses moving there."""
    (root / "game" / "meta" / "entries.json").write_text(
        json.dumps({"T001/cellar": {"class": "place", "parent": "T001", "props": {"name": "地窖"}}}, ensure_ascii=False), encoding="utf-8")


# ── registry ─────────────────────────────────────────────────────────────────


def test_registry_normalises_stoneford_two_id_conventions(tmp_path):
    reg = load_registry(_install(tmp_path))
    assert reg.current_town == "T001" and reg.player_location == "T001/gate_north"
    # both spellings + the display name land on the scoped node id
    assert reg.resolve("north-gate") == reg.resolve("gate_north") == reg.resolve("北门") == "T001/gate_north"
    assert reg.resolve("riverlamp-inn") == reg.resolve("河灯旅店") == "T001/inn"
    # souls / npcs / player by any alias; the role suffix is stripped
    assert reg.resolve("艾琳娜") == reg.resolve("Elena Vale") == reg.resolve("elena") == "si-elena0001"
    assert reg.resolve("赫伦(公会管事)") == reg.resolve("赫伦") == "NPC001"
    assert reg.resolve("玩家") == reg.resolve("player") == "player"
    assert reg.resolve("does-not-exist") is None
    # 10-05 the map is the folder tree: the market square is a spot inside 石津镇 (game/locations/T001/market-square/),
    # its links re-pointed at the town map's own ids — and the gate's exits now include it
    ms = reg.entries["T001/market-square"]
    assert ms.cls == "place" and ms.parent == "T001" and "T001/gate_north" in ms.links and "T001/inn" in ms.links
    assert reg.resolve("集市广场") == reg.resolve("market-square") == "T001/market-square"
    assert [e.id for e in reg.exits("T001/gate_north")] == ["T001/main_street", "T001/market-square"]
    # variables are typed + bound to files
    v = reg.variables
    assert v["player.gold"].value == 18 and v["player.gold"].path.endswith("player/wallet.json") and v["player.gold"].min == 0
    assert v["player.hp"].max_key == "hp.max" and v["location"].readonly and v["turn"].readonly
    assert v["flag.arrived_T001"].type == "bool" and v["flag.arrived_T001"].value is True
    # actions: mood is registered but soul-side only
    assert reg.actions["mood"].scope == "souls" and reg.actions["move_to"].kind == "action" and reg.actions["add"].kind == "update"
    # envelope invariants surface the world's own data gaps rather than hiding them
    probs = {e.id: check_envelope(reg, e) for e in reg.entries.values()}
    assert probs["T001/gate_north"] == ["link 'T001/main_street' not symmetric"], "town_map main_street does not link back"
    # the second stale map (market-square's one-way links to north-gate / riverlamp-inn) is gone: the folder migration
    # re-pointed them at the town map's ids and joined them back (10-05)
    assert set(k for k, p in probs.items() if p) == {"T001/gate_north"}


def test_registry_overlays_extend_and_remove(tmp_path):
    root = _install(tmp_path)
    meta = root / "game" / "meta"
    (meta / "variables.json").write_text(json.dumps({"town.mood": {"type": "str", "path": "game/towns/T001/town.json", "key": "state.mood", "default": "quiet"}}), encoding="utf-8")
    (meta / "actions.json").write_text(json.dumps({"new_npc": None, "roll": {"kind": "action", "handler": "dice.roll_check", "fields": ["skill", "target"], "doc": "掷骰"}}), encoding="utf-8")
    (meta / "entries.json").write_text(json.dumps({"T001/inn": {"aliases": ["旅店"], "props": {"hours": "夜间营业"}}}), encoding="utf-8")
    reg = load_registry(root)
    assert reg.variables["town.mood"].value == "quiet"
    assert "new_npc" not in reg.actions and reg.actions["roll"].handler == "dice.roll_check"
    assert reg.resolve("旅店") == "T001/inn" and reg.entries["T001/inn"].props["hours"] == "夜间营业"


# ── engine.json ──────────────────────────────────────────────────────────────


def test_engine_config_layers(tmp_path, monkeypatch):
    root = _install(tmp_path)
    monkeypatch.delenv("NEONRP_TURN_V3", raising=False)
    # v3 comes only from the rpg pack's own loop (Pack.loop): the stoneford templates carry no engine.json any more (10-01)
    assert not (root / "game" / "meta" / "engine.json").exists()
    assert engine_config.v3_enabled(root) and engine_config.get(root, "turn.parallel.souls.default_variant") == "S-judge"
    src0 = {k: s for k, _v, s in engine_config.explain(root)}
    assert src0["turn.mode"] == "pack" and src0["turn.solve.max_ops"] == "builtin"
    assert engine_config.DEFAULTS["turn"]["mode"] == "v2b"  # a pack without a loop still gets the old one
    (root / "game" / "meta" / "engine.json").write_text(json.dumps({"turn": {"mode": "v2b"}}), encoding="utf-8")
    assert engine_config.get(root, "turn.mode") == "v2b" and not engine_config.v3_enabled(root), "a world pins the old loop"
    (root / "game" / "meta" / "engine.json").write_text(json.dumps({"turn": {"mode": "v3", "verify": {"gate": {"max_loops": 2}}}}), encoding="utf-8")
    assert engine_config.v3_enabled(root) and engine_config.get(root, "turn.verify.gate.max_loops") == 2
    pt = _j(root / ".neonrp" / "playthrough.json")
    pt["engine"] = {"turn": {"verify": {"gate": {"max_loops": 0}}}}
    (root / ".neonrp" / "playthrough.json").write_text(json.dumps(pt), encoding="utf-8")
    assert engine_config.get(root, "turn.verify.gate.max_loops") == 0, "playthrough beats world"
    monkeypatch.setenv("NEONRP_V3_MAX_LOOPS", "3")
    monkeypatch.setenv("NEONRP_TURN_V3", "0")
    assert engine_config.get(root, "turn.verify.gate.max_loops") == 3 and not engine_config.v3_enabled(root), "env beats all"
    src = {k: s for k, _v, s in engine_config.explain(root)}
    assert src["turn.mode"] == "env" and src["turn.verify.gate.max_loops"] == "env" and src["turn.solve.max_ops"] == "builtin"


# ── pack ─────────────────────────────────────────────────────────────────────


def test_pack_world_view_and_soul_view(tmp_path):
    root = _install(tmp_path)
    sdk.pack(root)  # warm (imports, the status table cache, the OS file cache): the budget is for a pack in play, not a cold start
    p = min((sdk.pack(root) for _ in range(3)), key=lambda x: x.meta["ms"])  # best of three: a busy machine is not a regression
    txt = sdk.render_pack(p)
    # 100 ms on an idle machine; scaled by how overloaded it is right now (the full suite runs beside real-model benchmarks)
    import os as _os

    budget = 100 * max(1.0, _os.getloadavg()[0] / max(1, _os.cpu_count() or 1))
    assert p.here.id == "T001/gate_north" and p.meta["ms"] < budget, (p.meta["ms"], budget)
    assert "不要再读文件" in txt and "T001/main_street(主街)" in txt and "- elena 艾琳娜" in txt
    assert "罗文 @ T004" in txt and "世界背景" in txt and "- player.gold 18" in txt
    # the soul's observation o_i: own place, the player (same node), no lore, no other souls' persona
    ps = sdk.pack(root, viewer="si-elena0001")
    st = sdk.render_pack(ps)
    assert ps.me.id == "si-elena0001" and "## 你 si-elena0001" in st and "## 玩家 player" in st
    assert "世界背景" not in st and "异地角色" not in st and "人设" not in st and "player.gold" not in st
    # Rowan is in T004: from his view the player is not visible
    pr = sdk.pack(root, viewer="si-rowan0001")
    assert pr.player is None and pr.here is not None and pr.here.id == "T004"


# ── parsing ──────────────────────────────────────────────────────────────────


def test_parse_solve_output_json_fenced_and_tags():
    o = sdk.parse_solve_output('{"narration": "你走进主街。", "ops": [{"op": "move_to", "who": "player", "to": "main_street"}]}')
    assert o.fmt == "json" and o.narration == "你走进主街。" and o.ops[0]["to"] == "main_street"
    o = sdk.parse_solve_output('雾散了。\n```json\n{"ops": [{"op": "add", "var": "player.gold", "delta": -2}]}\n```')
    assert o.fmt == "json" and o.narration == "雾散了。" and o.ops[0]["delta"] == -2
    o = sdk.parse_solve_output("她点点头。\n⟦STATE⟧\nmove_to player inn\nadd player.gold -1\nflag met_mira\nengage 艾琳娜: 玩家要房\nneed 米拉\n⟦/STATE⟧")
    assert o.fmt == "tags" and o.narration == "她点点头。"
    assert [x["op"] for x in o.ops] == ["move_to", "add", "flag", "engage", "need"] and o.ops[3]["note"] == "玩家要房"
    o = sdk.parse_solve_output("只有叙事,没有块。")
    assert o.fmt == "none" and o.ops == [] and o.narration == "只有叙事,没有块。"
    # E1 v3-speak: literal newlines inside the JSON string (what models actually emit)
    raw = '{"narration": "雾贴着栅门不散。\n\n她停住脚,「昨晚?」", "ops": [{"op": "move_to", "who": "player", "to": "inn"}]}'
    o = sdk.parse_solve_output(raw)
    assert o.fmt == "json" and o.ops[0]["to"] == "inn" and "她停住脚" in o.narration and "\n\n" in o.narration
    # truncated object: prose is salvaged, never shown as JSON
    o = sdk.parse_solve_output('{"narration": "你推门进去,热气扑面。\n\n掌柜抬头', )
    assert o.fmt == "salvaged" and o.narration.startswith("你推门进去") and "{" not in o.narration and o.ops == []


# ── verify ───────────────────────────────────────────────────────────────────


def test_verify_three_scopes(tmp_path):
    root = _install(tmp_path)
    _register_unmapped_cellar(root)
    reg = load_registry(root)
    ops = [
        {"op": "ask", "who": "艾琳娜"},  # alias → id, `ask` → need (before the player walks off — co-location is judged after earlier moves)
        {"op": "move_to", "who": "player", "to": "main_street"},  # adjacent → ok
        {"op": "move_to", "who": "玩家", "to": "地窖"},  # registered but not a town_map node → judge refuses
        {"op": "move_to", "who": "player", "to": "T009/nowhere"},  # unknown town's place → entity refusal (an unknown place here grows, 10-02)
        {"op": "move_to", "who": "谁啊", "to": "inn"},  # unknown entity
        {"op": "add", "var": "player.gold", "delta": "-3"},  # str→int
        {"op": "add", "var": "player.gold", "delta": "many"},  # non-int
        {"op": "set", "var": "nope", "value": 1},  # unknown var
        {"op": "set", "var": "turn", "value": 9},  # engine-owned
        {"op": "mood", "who": "艾琳娜", "value": "guarded"},  # soul-side op
        {"op": "teleport", "who": "player"},  # unknown op
        {"op": "new_location", "name": "河灯旅店", "parent": "main_street"},  # exists
        {"op": "new_location", "name": "旧墓园", "parent": "gate_north", "links": ["north-gate"]},
        {"op": "flag", "key": "met_guard"},
    ]
    vr = sdk.verify(root, ops, reg)
    acc = {(o["op"], o.get("who") or o.get("var") or o.get("name") or o.get("key")): o for o in vr.accepted}
    assert ("move_to", "player") in acc and acc[("move_to", "player")]["to"] == "T001/main_street"
    assert acc[("need", "si-elena0001")]["who"] == "si-elena0001"
    assert acc[("add", "player.gold")]["delta"] == -3
    assert acc[("new_location", "旧墓园")]["parent"] == "T001/gate_north" and acc[("new_location", "旧墓园")]["links"] == ["T001/gate_north"]
    assert ("flag", "met_guard") in acc
    ref = {r.index: r for r in vr.refused}
    assert ref[2].scope == "world" and "没有节点" in ref[2].why and ref[2].fixable
    assert ref[3].scope == "entity" and ref[3].field == "to"
    assert ref[4].field == "who" and "艾琳娜" in ref[4].allowed
    assert ref[6].field == "delta" and ref[7].field == "var" and "player.gold" in ref[7].allowed
    assert ref[8].fixable is False and ref[9].fixable is False and ref[10].field == "op" and "move_to" in ref[10].allowed
    assert ref[11].scope == "world" and ref[11].fixable is False
    assert len(vr.accepted) + len(vr.refused) == len(ops)


# ── apply ────────────────────────────────────────────────────────────────────


def test_apply_writes_through_handlers_and_reports(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    ops = [
        {"op": "move_to", "who": "player", "to": "main_street"},
        {"op": "move_to", "who": "艾琳娜", "to": "main_street"},
        {"op": "add", "var": "player.gold", "delta": -3},
        {"op": "add", "var": "player.hp", "delta": -40},  # clamps to 0 → repaired
        {"op": "set", "var": "time.clock", "value": "09:00"},
        {"op": "flag", "key": "met_guard"},
        {"op": "new_location", "name": "旧墓园", "parent": "gate_north", "links": ["gate_north"]},
        {"op": "new_npc", "name": "守门人巴德", "at": "gate_north", "role": "guard"},
        {"op": "need", "who": "艾琳娜"},
    ]
    vr = sdk.verify(root, ops, reg)
    assert not vr.refused, [r.to_dict() for r in vr.refused]
    ar = sdk.apply(root, [o for o in vr.accepted if o["op"] != "need"], reg, turn=3)
    assert _j(root / "game" / "meta" / "run_state.json")["location"]["node"] == "main_street"
    # a dungeon is entered by its entry room: from main_street "D001" lands there this turn (repair, not refusal)
    vr2 = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "D001"}], reg)
    assert not vr2.refused and vr2.accepted[0]["to"] == "D001/D001_R001" and vr2.accepted[0]["_clamped"]["wanted"] == "D001"
    ar2 = sdk.apply(root, vr2.accepted, reg, turn=4)
    assert ar2.repaired[0]["from"] == "D001" and ar2.repaired[0]["to"] == "D001/D001_R001"
    assert load_registry(root).player_location == "D001/D001_R001"
    assert _j(root / "souls" / "elena-si-elena0001" / "run_state.json")["location"].endswith("main_street")
    assert _j(root / "game" / "player" / "wallet.json")["gold"] == 15
    assert _j(root / "game" / "player" / "stats.json")["hp"]["current"] == 0
    assert _j(root / "game" / "meta" / "run_state.json")["time"]["clock"] == "09:00"
    assert _j(root / "game" / "player" / "flags.json")["story_flags"]["met_guard"] is True
    npcs = _j(root / "game" / "towns" / "T001" / "npcs.json")["npcs"]
    assert npcs[-1]["name"] == "守门人巴德" and npcs[-1]["id"] == "NPC004" and npcs[-1]["provenance"]["turn"] == 3
    d = ar.to_dict()
    # hp 0 → the player goes down (packs/rpg/downed.py, 10-05): the down event and its 倒地 status ride the same apply
    assert d["turn"] == 3 and {a["op"] for a in d["applied"] if a.get("by") != "tick:downed" and a.get("op") != "new"} == {"move_to", "add", "set", "flag"}
    assert any(a.get("event") == "down" and a.get("who") == "player" for a in d["applied"])
    assert d["repaired"] == [{"op": "add", "var": "player.hp", "from": -16, "to": 0, "why": "range"}]
    assert {c["class"] for c in d["created"]} == {"place", "npc", "status"} and d["variables"]["player.gold"] == 15
    assert d["variables"]["location"] == "T001/main_street" and d["refused"] == []
    # the new place is registered and reachable next turn
    reg2 = load_registry(root)
    assert reg2.resolve("旧墓园") is not None and reg2.resolve("守门人巴德") is not None


# ── solve_turn (③–⑤ with a fake model) ───────────────────────────────────────


class _FakeAdapter:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.calls: list[list] = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        text = self.outputs.pop(0) if self.outputs else '{"narration": "……", "ops": []}'
        return SimpleNamespace(message=SimpleNamespace(content=text), usage={"prompt_tokens": 10, "completion_tokens": 5})


@pytest.fixture(autouse=True)
def _adv_shape(monkeypatch):
    """Most tests here script the one-call ADV shape (prose + <ops> in one answer) — an experiment shape now, pinned
    with NEONRP_V3_SOLVE; the engine default is the graph's Resolve state (pseudo, 10-11). A test may set its own."""
    monkeypatch.setenv("NEONRP_V3_SOLVE", "adv")


@pytest.fixture
def fake_adapter(monkeypatch):
    holder: dict = {}

    def factory(outputs: list[str]) -> _FakeAdapter:
        holder["a"] = _FakeAdapter(outputs)
        monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root, provider: holder["a"])
        return holder["a"]

    yield factory
    turn_v3.ADAPTER_FACTORY = None


def test_solve_turn_one_pass(tmp_path, fake_adapter):
    root = _install(tmp_path)
    a = fake_adapter(['{"narration": "你沿主街走去,付了一枚金币买面包。", "ops": [{"op": "move_to", "who": "player", "to": "主街"}, {"op": "add", "var": "player.gold", "delta": -1}]}'])
    out = turn_v3.solve_turn(root, user_text="我去主街买面包", provider=None, turn=1,
                             soul_reports=[{"iid": "si-elena0001", "name": "艾琳娜", "kind": "speak", "text": "「等等我。」"}])
    assert out["loops"] == 0 and out["narration"].startswith("你沿主街")
    assert [x["op"] for x in out["apply"].applied] == ["move_to", "add"] and out["apply"].variables["player.gold"] == 17
    sys_msg, user_msg = a.calls[0][0].content, a.calls[0][1].content
    assert "<lines>" in sys_msg and "move player inn" in sys_msg and "mood" not in sys_msg.split("<ops>")[1].split("</ops>")[0]
    assert "不要再读文件" in user_msg and "角色回包" in user_msg and "<say 艾琳娜>「等等我。」</say>" in user_msg and "# 玩家此刻\n我去主街买面包" in user_msg
    phases = [s["phase"] for s in out["spans"]]
    assert phases == ["plan", "solve", "verify", "apply"] and out["usage"]["prompt_tokens"] == 10


def test_solve_turn_re_proposes_once_on_fixable_refusal(tmp_path, fake_adapter):
    root = _install(tmp_path)
    _register_unmapped_cellar(root)
    a = fake_adapter([
        '{"narration": "你下到地窖。", "ops": [{"op": "move_to", "who": "player", "to": "地窖"}]}',  # registered, not on the map
        '{"narration": "你沿主街朝旅店走去。", "ops": [{"op": "move_to", "who": "player", "to": "main_street"}]}',
    ])
    out = turn_v3.solve_turn(root, user_text="我去旅店", provider=None, turn=2, soul_reports=[])
    assert out["loops"] == 1 and len(a.calls) == 2
    assert "上一次提案被拒" in a.calls[1][1].content and "T001/main_street(主街)" in a.calls[1][1].content
    assert out["apply"].applied[0]["to"] == "T001/main_street" and out["verify"]["refused"] == []
    assert [s["phase"] for s in out["spans"]] == ["plan", "solve", "verify", "solve", "verify", "apply"]


def test_solve_turn_need_runs_soul_then_continues(tmp_path, fake_adapter):
    root = _install(tmp_path)
    fake_adapter([
        '{"narration": "你问艾琳娜要不要同行。", "ops": [{"op": "need", "who": "艾琳娜"}]}',
        '{"narration": "艾琳娜想了想:「好。」你们一起走向主街。", "ops": [{"op": "move_to", "who": "player", "to": "main_street"}, {"op": "move_to", "who": "艾琳娜", "to": "main_street"}]}',
    ])
    asked: list[tuple[str, str]] = []

    def ask(who: str, ctx: str) -> dict:
        asked.append((who, ctx))
        return {"ok": True, "answer": "「好。」", "name": "艾琳娜"}

    out = turn_v3.solve_turn(root, user_text="要一起走吗?", provider=None, turn=3, soul_reports=[], ask_soul=ask)
    assert asked and asked[0][0] == "si-elena0001" and out["loops"] == 1
    assert [r["kind"] for r in out["reports"]] == ["need"] and out["reports"][0]["text"] == "「好。」"
    assert {a["who"] for a in out["apply"].applied} == {"player", "si-elena0001"}
    assert any(s["phase"] == "parallel" and s["actor"] == "need" for s in out["spans"])


def test_solve_turn_need_continuation_keeps_accepted_ops(tmp_path, fake_adapter):
    """E5 run3 C3c: the continuation after `need` came back with ops=[] and the
    player's move_to from the first attempt was silently dropped. A continuation
    keeps what was accepted; a restated op wins over the carried one."""
    root = _install(tmp_path)
    fake_adapter([
        '{"narration": "你回到公会,艾琳娜抬起头。", "ops": [{"op": "need", "who": "艾琳娜"}, {"op": "move_to", "who": "player", "to": "main_street"}, {"op": "add", "var": "player.gold", "delta": -1}]}',
        '{"narration": "「回来得比我押的快。」", "ops": [{"op": "add", "var": "player.gold", "delta": -2}]}',
    ])
    out = turn_v3.solve_turn(root, user_text="我回公会找艾琳娜", provider=None, turn=3, soul_reports=[], ask_soul=lambda who, ctx: {"ok": True, "answer": "「回来了。」"})
    assert out["loops"] == 1
    applied = {(a["op"], a.get("who") or a.get("var")): a for a in out["apply"].applied}
    assert applied[("move_to", "player")]["to"] == "T001/main_street"  # carried
    assert ("add", "player.gold") in applied and out["apply"].variables["player.gold"] == 16  # restated −2 wins over carried −1, not doubled


def test_solve_turn_gate_respects_max_loops_zero(tmp_path, fake_adapter, monkeypatch):
    root = _install(tmp_path)
    _register_unmapped_cellar(root)
    monkeypatch.setenv("NEONRP_V3_MAX_LOOPS", "0")
    a = fake_adapter(['{"narration": "x", "ops": [{"op": "move_to", "who": "player", "to": "地窖"}]}'])
    out = turn_v3.solve_turn(root, user_text="去地窖", provider=None, turn=1, soul_reports=[])
    assert out["loops"] == 0 and len(a.calls) == 1 and out["apply"].applied == [] and out["apply"].refused[0]["scope"] == "world"


# ── the full session turn under the flag ─────────────────────────────────────


def test_session_turn_v3_replaces_world_agent_loop(tmp_path, fake_adapter, monkeypatch):
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    monkeypatch.setenv("NEONRP_HEARTBEAT", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    s1.install_stub(None)
    root = _world(_setup_project(tmp_path))
    fake_adapter(['{"narration": "艾琳娜看了你一眼,和你一起走进旅店。", "ops": [{"op": "move_to", "who": "player", "to": "inn"}, {"op": "move_to", "who": "艾琳娜", "to": "inn"}]}'])
    notes: dict[str, str] = {}

    def fake_engage(root_, iid, *, note, **kw):
        notes[iid] = note
        return {"ok": True, "digest": f"{iid} 点头", "name": iid, "state": "completed"}

    def fake_ask(root_, iid, question, *, asker="", **kw):
        notes[iid] = question
        return {"ok": True, "answer": "「好啊。」", "name": iid}

    async def _land(deltas, *, turn_seq, branch="main"):
        return "wc-v3"

    with patch("neonrp.core.conversation.run_conversation_turn") as run, \
         patch("neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land), \
         patch("neonrp.core.engage.engage_soul_run", side_effect=fake_engage), \
         patch("neonrp.core.light_chat.ask_soul_deliver", side_effect=fake_ask), \
         patch("neonrp.core.engage.heartbeat_soul_run", return_value={"ok": True, "line": "…", "name": "x"}):
        res = ConversationSession(root, "test-agent", mode="play").send("我们去旅店吧")
    assert res.success and res.assistant_message.startswith("艾琳娜看了你一眼") and res.route_decision == "multi_agent_commit:wc-v3"
    assert not run.called, "v3 never runs the world-agent tool loop"
    assert res.tool_calls_made == ["move_to", "move_to"]
    # A soul reads the world's prose for her + the player's beat as she meets it + her own context
    assert "【你自己】" in notes["si-elena"] and "「我们去旅店吧」" in notes["si-elena"] and "# 你眼前" not in notes["si-elena"]
    # positions landed through the SDK
    assert _j(root / "game" / "meta" / "run_state.json")["location"]["node"] == "inn"
    assert _j(root / "souls" / "elena-si-elena" / "run_state.json")["location"].endswith("inn")
    tr = read_turn_traces(root, "main", last=1)[0]
    assert tr["apply"]["applied"][0]["op"] == "move_to" and tr["apply"]["commit"] is None
    assert [s_["iid"] for s_ in tr["apply"]["souls"]] == ["si-elena", "si-rowan"], "closed schema settled for both speakers"
    _ev = _j(root / "souls" / "elena-si-elena" / "short-term-memo" / "recent_events.json")["events"]
    assert any(e.get("by") == "engine.settle" and e.get("affect") == "" for e in _ev), "typed memo line written by the engine"
    phases = [s["phase"] for s in tr["spans"]]
    assert phases[0] == "plan" and "parallel" in phases and phases[-5:] == ["solve", "verify", "apply", "settle", "land"]
    assert [s["actor"] for s in tr["spans"] if s["phase"] == "plan"][:2] == ["scene", "stub"], "the whole wall clock is accounted"
    assert tr["timing"]["v3"]["loops"] == 0 and tr["world_agent"]["tool_calls"][0]["name"] == "op:move_to"


@pytest.mark.timeout(300)
def test_stub_provider_playthrough_survives_v3(tmp_path, monkeypatch):
    """The shipped stub provider does not speak the v3 grammar; the turn must still close cleanly."""
    from test_e2e_stub_play import _install as _install_full

    from neonrp.core.conversation import ConversationSession

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _install_full(tmp_path)
    sess = ConversationSession(root, "world-agent", mode="play")
    first = sess.send("开始游戏")  # an authored opening is served as is (core/opening.py, no model call)
    assert first.success and first.route_decision == "opening"
    res = sess.send("我看看四周")  # the first turn the stub provider has to answer
    assert res.success and res.route_decision and res.route_decision.startswith("multi_agent_commit:")
    assert _j(root / "game" / "meta" / "run_state.json")["location"]["node"] == "gate_north"


# ── split arm (叙事与 ops 分开出) + Jev backends ─────────────────────────────


def test_solve_turn_split_arm_two_calls(tmp_path, fake_adapter, monkeypatch):
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "split")
    a = fake_adapter([
        "你沿主街走去,在面包摊付了一枚金币。",
        '{"ops": [{"op": "move_to", "who": "player", "to": "main_street"}, {"op": "add", "var": "player.gold", "delta": -1}]}',
    ])
    out = turn_v3.solve_turn(root, user_text="我去主街买面包", provider=None, turn=1, soul_reports=[])
    assert len(a.calls) == 2 and "只写叙事" in a.calls[0][0].content and "状态抽取器" in a.calls[1][0].content
    assert "刚发生的叙事" in a.calls[1][1].content and out["solve"].fmt == "split"
    assert out["narration"].startswith("你沿主街") and out["apply"].variables["player.gold"] == 17
    assert [s["actor"] for s in out["spans"] if s["phase"] == "solve"] == ["world.narrate", "world.extract"]


def test_system_one_backend_priority_and_proxy_endpoint(monkeypatch, tmp_path):
    monkeypatch.delenv("NEONRP_S1_BACKEND", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("HUB_API_TOKEN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # no ~/.neonrp/config.json
    assert s1.backend_name() == "off", "local build without any key = off, and off is a complete engine"
    monkeypatch.setenv("HUB_API_TOKEN", "sess-abc")
    assert s1.backend_name() == "proxy" and s1.endpoint() == (s1.PROXY_URL_DEFAULT, "sess-abc")
    monkeypatch.setenv("NEONRP_S1_PROXY_URL", "https://dev-api.worldlines.gg/api/v1/systemone")
    assert s1.endpoint()[0].startswith("https://dev-api")
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    assert s1.backend_name() == "jev" and s1.endpoint() == (s1.JEV_URL, "ts-key"), "own key beats proxy"
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    assert s1.backend_name() == "off"


# ── soul settle: closed schema written back from the final narration ─────────


def test_soul_settle_with_judge_and_without(tmp_path):
    from neonrp.packs.rpg import soul_settle

    root = _install(tmp_path)
    reports = [{"iid": "si-elena0001", "name": "艾琳娜", "kind": "speak", "text": "「你别去,那条路夜里有狼。」"},
               {"iid": "si-rowan0001", "name": "罗文", "kind": "speak", "text": "", "ok": False}]
    narr = "你听了艾琳娜的话,收回了迈向北门外的脚。她松了口气,但眼神仍盯着雾。"
    # with a judge (stub answers)
    def ask(state, qs):
        assert state["soul"] == "艾琳娜" and "goals" in state and state["my_reaction"].startswith("「你别去")
        assert set(qs) == {"mood", "trust", "important", "intention"}
        return {"mood": s1.Answer("choice", "guarded", {}, 0.9), "trust": s1.Answer("choice", "1", {}, 0.8),
                "important": s1.Answer("noul", 0.7, {}, 0.9), "intention": s1.Answer("choice", "弄清灰雾北境究竟藏着什么", {}, 0.85)}
    out = soul_settle.settle_souls(root, reports=reports, narration=narr, turn=5, ask=ask)
    assert len(out) == 1 and out[0]["iid"] == "si-elena0001" and out[0]["mood"] == "guarded" and out[0]["trust_delta"] == 1 and out[0]["important"]
    rs = _j(root / "souls" / "elena-si-elena0001" / "run_state.json")
    assert rs["status"]["mood"] == "guarded" and rs["status"]["trust"]["player"] == 1 and rs["status"]["intention"].startswith("弄清")
    ev = _j(root / "souls" / "elena-si-elena0001" / "short-term-memo" / "recent_events.json")["events"]
    assert ev[-1]["by"] == "engine.settle" and ev[-1]["turn"] == 5 and "艾琳娜" in ev[-1]["event"] and ev[-1]["important"] is True
    # without a judge: nothing guessed, the typed event line still lands
    out = soul_settle.settle_souls(root, reports=reports[:1], narration="她没再说话。", turn=6, ask=lambda s, q: None)
    assert out[0]["source"] == "off" and out[0]["mood"] == "guarded" and out[0]["trust_delta"] == 0
    ev = _j(root / "souls" / "elena-si-elena0001" / "short-term-memo" / "recent_events.json")["events"]
    assert ev[-1]["turn"] == 6 and ev[-1]["affect"] == "guarded" and "important" not in ev[-1]
    # low confidence answers are not written
    out = soul_settle.settle_souls(root, reports=reports[:1], narration="x", turn=7,
                                   ask=lambda s, q: {"mood": s1.Answer("choice", "angry", {}, 0.3)})
    assert out[0]["mood"] == "guarded"


# ── pack budget + richness, register() write face, llm judge backend ─────────


def test_pack_is_rich_and_budgeted(tmp_path):
    root = _install(tmp_path)
    p = sdk.pack(root)
    txt = sdk.render_pack(p)
    # world view carries timeline, threads, present soul persona + goals, notes/lore, NPC traits
    assert "## 时间 第 1 天 上午 08:30" in txt and "进行中的线索" in txt
    assert "### 艾琳娜 人设" in txt and "目标:在石津镇拿到第一份真正像样的契约" in txt
    assert "## 世界背景" in txt and "(NPC,guildmaster,谨慎、重契约)" in txt
    assert 1800 < len(txt) <= sdk.WORLD_BUDGET_CHARS + 50
    # a tight budget trims lore / notes / persona tiers but never the scene tier
    tight = sdk.render_pack(sdk.pack(root, budget_chars=1500))
    assert "## 此地 T001/gate_north" in tight and "## 本镇地点 id" in tight and "# 变量" in tight
    assert "## 世界背景" not in tight and len(tight) <= 1700
    # soul view: persona, rules, goals, own memory — still no lore, no other souls' persona
    sv = sdk.render_pack(sdk.pack(root, viewer="si-elena0001"))
    assert "### 你是谁" in sv and "### 你的处事原则" in sv and "### 你的目标" in sv and "## 世界背景" not in sv
    assert 800 < len(sv) <= sdk.SOUL_BUDGET_CHARS + 50
    # facility data rides with the place (inn rooms/prices) once the viewer is there
    from neonrp.core.registry import load_registry as _lr
    reg = _lr(root)
    assert reg.entries["T001/inn"].props["facility"]["rooms"][1]["price"] == 8


def test_register_write_face(tmp_path):
    from neonrp.core.registry import RegisterError, load_registry, register

    root = _install(tmp_path)
    r = register(root, "entries", "T001/cellar", {"class": "place", "parent": "T001", "props": {"name": "地窖"}})
    assert r["path"] == "game/meta/entries.json" and load_registry(root).resolve("地窖") == "T001/cellar"
    register(root, "variables", "town.mood", {"type": "str", "path": "game/towns/T001/town.json", "key": "state.mood", "default": "quiet"})
    register(root, "actions", "roll", {"kind": "action", "handler": "dice.roll_check", "fields": ["skill", "target"]})
    register(root, "actions", "new_npc", None)  # remove an op
    reg = load_registry(root)
    assert reg.variables["town.mood"].value == "quiet" and "roll" in reg.actions and "new_npc" not in reg.actions
    with pytest.raises(RegisterError):
        register(root, "entries", "x", {"class": "dragon", "props": {"name": "x"}})  # unknown class
    with pytest.raises(RegisterError):
        register(root, "entries", "y", {"class": "place", "parent": "T001", "props": {}})  # missing required name
    with pytest.raises(RegisterError):
        register(root, "variables", "bad", {"type": "list", "path": "x", "key": "y"})
    with pytest.raises(RegisterError):
        register(root, "nope", "a", {})
    assert register(root, "entries", "T001/cellar", None)["removed"] and load_registry(root).resolve("地窖") is None


def test_llm_judge_backend_answers_same_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "llm")
    seen = {}

    class J:
        def chat(self, messages, tools=None):
            seen["sys"], seen["user"] = messages[0].content, messages[1].content
            return SimpleNamespace(message=SimpleNamespace(content='好的:{"mood": {"choice": "guarded", "probabilities": {"guarded": 0.7, "calm": 0.3}, "confidence": 0.8}, "important": {"yes": 0.2, "confidence": 0.9}, "tension": {"score": 1.5, "confidence": 0.6}}'), usage={})

    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: J())
    qs = {"mood": s1.choice("情绪?", {"guarded": "guarded", "calm": "calm"}), "important": s1.noul("重要?"), "tension": s1.score("张力", ["0", "1", "2"])}
    ans = s1.ask({"soul": "艾琳娜"}, qs)
    assert ans is not None and ans["mood"].value == "guarded" and ans["mood"].confidence == 0.8 and ans["mood"].probabilities["calm"] == 0.3
    assert ans["important"].yes == 0.2 and ans["tension"].value == 1.5
    assert "判断器" in seen["sys"] and "艾琳娜" in seen["user"] and s1.last_call()["backend"] == "llm"
    # auto chain: no keys but a judge preset configured ⇒ llm (isolate from ~/.neonrp/config.json)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("NEONRP_S1_BACKEND", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("HUB_API_TOKEN", raising=False)
    monkeypatch.setenv("NEONRP_S1_LLM_PRESET", "local-qwen")
    assert s1.backend_name() == "llm"


# ── trace html report (§11) ──────────────────────────────────────────────────


def test_trace_html_report_renders_spans_and_apply(tmp_path, fake_adapter, monkeypatch):
    from click.testing import CliRunner
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.cli import cli
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.trace_report import render_html

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    monkeypatch.setenv("NEONRP_HEARTBEAT", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    s1.install_stub(None)
    root = _world(_setup_project(tmp_path))
    fake_adapter(['{"narration": "你们走进旅店。", "ops": [{"op": "move_to", "who": "player", "to": "inn"}]}'])

    async def _land(deltas, *, turn_seq, branch="main"):
        return "wc-html"

    with patch("neonrp.core.conversation.run_conversation_turn"), \
         patch("neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land), \
         patch("neonrp.core.light_chat.ask_soul_deliver", return_value={"ok": True, "answer": "「好。」", "name": "x"}), \
         patch("neonrp.core.engage.heartbeat_soul_run", return_value={"ok": True, "line": "…", "name": "x"}):
        ConversationSession(root, "test-agent", mode="play").send("去旅店")
    res = CliRunner().invoke(cli, ["trace", "html", str(root)])
    assert res.exit_code == 0, res.output
    out = root / ".neonrp" / "orchestration" / "main.html"
    page = out.read_text(encoding="utf-8")
    assert "<svg" in page and "solve · world" in page and "op:move_to" in page and "wc-html" in page and "settle" in page
    assert render_html([]).count("0 回合") == 1


def test_fallback_depth_knob(monkeypatch):
    from neonrp.core import turn_plan as tp

    rows = [{"iid": "si-a", "name": "A", "present": True}, {"iid": "si-b", "name": "B", "present": False}]
    monkeypatch.delenv("NEONRP_S1_FALLBACK_DEPTH", raising=False)
    assert tp.fallback_plan(rows, None, "").depth_of("si-a") == "act"
    monkeypatch.setenv("NEONRP_S1_FALLBACK_DEPTH", "speak")
    p = tp.fallback_plan(rows, None, "")
    assert p.depth_of("si-a") == "speak" and p.depth_of("si-b") == "silent"


def test_solve_structured_modes_map_to_provider_kwargs():
    assert turn_v3.adapter_kwargs("together") == {}
    assert turn_v3.adapter_kwargs("json_object") == {"extra_kwargs": {"response_format": {"type": "json_object"}}}
    js = turn_v3.adapter_kwargs("json_schema")["extra_kwargs"]["response_format"]
    assert js["type"] == "json_schema" and js["json_schema"]["schema"]["required"] == ["narration", "ops"]


def test_jev_noul_criteria_is_folded_into_instructions():
    q = s1.noul("艾琳娜会有反应吗?", "被点名、被看到")
    d = q.to_dict()
    assert "criteria" not in d and d["instructions"].endswith("(判据:被点名、被看到)")
    assert s1.noul("x").to_dict() == {"type": "noul", "instructions": "x"}
    assert s1.choice("y", {"a": "A", "b": "B"}).to_dict()["criteria"] == {"a": "A", "b": "B"}


# ── S-judge soul step (phase 4) ──────────────────────────────────────────────


def test_soul_step_s_judge_gesture_speak_and_move(tmp_path, monkeypatch):
    from neonrp.packs.rpg import soul_step

    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    asked: list[dict] = []

    def stub(state, qs):
        asked.append({"state": state, "qs": sorted(qs)})
        return {"attitude": s1.Answer("choice", "probe", {}, 0.9), "register": s1.Answer("choice", "cold", {}, 0.8),
                "urgency": s1.Answer("choice", "1", {}, 0.9), "want_move": s1.Answer("noul", 0.85, {}, 0.9), "follow": s1.Answer("noul", 0.1, {}, 0.9),
                "move_to": s1.Answer("choice", "T001/main_street", {}, 0.8), "free": s1.Answer("noul", 0.1, {}, 0.9)}

    s1.install_stub(stub)
    try:
        j = soul_step.judge_soul(root, "si-elena0001", situation="# 你眼前 …\n\n场景:北门。玩家此刻:玩家问你昨晚的事")
        assert j.attitude == "probe" and j.register == "cold" and j.urgency == 1 and j.want_move and j.move_to == "T001/main_street"
        assert asked[0]["state"]["soul"] == "艾琳娜" and "persona" in asked[0]["state"] and "move_to" in asked[0]["qs"]
        assert list(asked[0]["state"])[0] == "player_says" and asked[0]["state"]["player_says"] == "玩家问你昨晚的事" and asked[0]["state"]["scene"].startswith("# 你眼前")
        assert "反问 / 追问" in j.baked() and "离开去 T001/main_street" in j.baked()
        assert "confides" in asked[0]["qs"] and j.confides < 0.6 and "倾诉" not in j.baked()
        # gesture: zero LLM, a register-table line
        g = soul_step.soul_step(root, "si-elena0001", situation="x", depth="gesture")
        assert g["kind"] == "gesture" and g["text"].startswith("艾琳娜") and g["proposed_move"] == "T001/main_street"
        # speak: one ask with the judgment baked into the question
        seen = {}

        def fake_ask(root_, iid, q, *, asker="", **_kw):
            seen["q"] = q
            return {"ok": True, "answer": "「昨晚?你先说你是谁。」", "name": "艾琳娜"}

        monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", fake_ask)
        sp = soul_step.soul_step(root, "si-elena0001", situation="玩家问你昨晚的事", depth="speak")
        assert sp["kind"] == "speak" and sp["text"].startswith("「昨晚") and "已经做了" in seen["q"] and "反问 / 追问" in seen["q"] and "骰" not in seen["q"]
        assert sp["judgment"]["attitude"] == "probe"
    finally:
        s1.install_stub(None)


def test_soul_step_no_judge_falls_back_to_plain_speak(tmp_path, monkeypatch):
    from neonrp.packs.rpg import soul_step

    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", lambda root_, iid, q, *, asker="", **_kw: {"ok": True, "answer": "嗯。", "name": "艾琳娜"})
    r = soul_step.soul_step(root, "si-elena0001", situation="x", depth="speak")
    # 10-01: no fast judge → she writes her own fields in the same call (S-direct); a bare line still comes through
    assert r["kind"] == "speak" and r["judgment"]["source"] == "llm-direct" and r["judgment"]["attitude"] is None and r["proposed_move"] is None
    assert r["text"] == "嗯。"


def test_session_v3_s_judge_variant_proposes_soul_move(tmp_path, fake_adapter, monkeypatch):
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    monkeypatch.setenv("NEONRP_HEARTBEAT", "1")
    monkeypatch.setenv("NEONRP_SOUL_VARIANT", "S-judge")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))

    def stub(state, qs):
        out = {}
        if "attitude" in qs:  # soul_step questions
            out = {"attitude": s1.Answer("choice", "comply", {}, 0.9), "register": s1.Answer("choice", "warm", {}, 0.9),
                   "urgency": s1.Answer("choice", "0", {}, 0.9), "want_move": s1.Answer("noul", 0.9, {}, 0.9), "follow": s1.Answer("noul", 0.1, {}, 0.9),
                   "move_to": s1.Answer("choice", "T001/inn", {}, 0.9), "free": s1.Answer("noul", 0.0, {}, 0.9)}
        for k in qs:  # plan questions: elena speaks, rowan silent
            if k.endswith(".reacts"):
                out[k] = s1.Answer("noul", 0.95 if "elena" in k else 0.1, {}, 0.9)
            if k.endswith(".depth"):
                out[k] = s1.Answer("choice", "speak", {}, 0.9)
        return out

    s1.install_stub(stub)
    fake_adapter(['{"narration": "她说好,你们一起往旅店走。", "ops": [{"op": "move_to", "who": "player", "to": "inn"}]}'])
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", lambda root_, iid, q, *, asker="", **_kw: {"ok": True, "answer": "「走吧。」", "name": "艾琳娜"})

    async def _land(deltas, *, turn_seq, branch="main"):
        return "wc-sj"

    try:
        with patch("neonrp.core.conversation.run_conversation_turn"), \
             patch("neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land), \
             patch("neonrp.core.engage.heartbeat_soul_run", return_value={"ok": True, "line": "…", "name": "x"}):
            res = ConversationSession(root, "test-agent", mode="play").send("我们去旅店吧")
    finally:
        s1.install_stub(None)
    assert res.success
    tr = read_turn_traces(root, "main", last=1)[0]
    rep = {r["iid"]: r for r in tr["apply"]["reports"]}
    assert rep["si-elena"]["judgment"]["attitude"] == "comply" and rep["si-elena"]["proposed_move"] == "T001/inn"
    # the soul's judged move went through verify like any op and landed
    assert {(a["op"], a["who"]) for a in tr["apply"]["applied"]} >= {("move_to", "player"), ("move_to", "si-elena")}
    assert _j(root / "souls" / "elena-si-elena" / "run_state.json")["location"].endswith("inn")
    assert [s_["speech"] for s_ in tr["souls"] if s_["instance_id"] == "si-elena"] == ["「走吧。」"]


# ── E5 fixes: need must be co-located; travel hints; clamped player move re-solves once ──


def test_need_refused_when_soul_not_here(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "need", "who": "罗文"}, {"op": "need", "who": "艾琳娜"}], reg)
    assert [o["who"] for o in vr.accepted] == ["si-elena0001"]
    assert vr.refused[0].scope == "world" and "not here" in vr.refused[0].why and vr.refused[0].allowed == ["艾琳娜"] and not vr.refused[0].fixable


def test_need_allowed_after_same_batch_move(tmp_path):
    """E7 A2b/A5a: solver moves the player to where Elena stands (or moves her to
    the player) and asks her in the same batch — co-location is judged after the
    batch's own moves, not against the pre-turn map."""
    root = _install(tmp_path)
    reg = load_registry(root)
    elena_at = reg.entries["si-elena0001"].parent
    # player elsewhere, moves back to Elena's spot, then asks her
    reg.player_location = next(e.id for e in reg.exits(elena_at))
    vr = sdk.verify(root, [{"op": "need", "who": "艾琳娜"}], reg)
    assert vr.refused and "not here" in vr.refused[0].why
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": elena_at}, {"op": "need", "who": "艾琳娜"}], reg)
    assert [o["op"] for o in vr.accepted] == ["move_to", "need"] and not vr.refused
    # Elena moved to the player first, then asked
    reg = load_registry(root)
    away = next(e.id for e in reg.exits(elena_at))
    reg.player_location = away
    vr = sdk.verify(root, [{"op": "move_to", "who": "艾琳娜", "to": away}, {"op": "need", "who": "艾琳娜"}], reg)
    assert [o["op"] for o in vr.accepted] == ["move_to", "need"] and not vr.refused


def test_travel_hints_describe_travel(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    h = _rpg_contract.travel_hints(root, reg)
    assert "## 远行" in h and "T004" in h and ("本回合可入镇" in h or "引擎会落在" in h)
    # off the gate: the same one beat out and in (10-19 — no beat stopped at our own gate)
    sdk.apply(root, sdk.verify(root, [{"op": "move_to", "who": "player", "to": "main_street"}], reg).accepted, reg)
    h2 = _rpg_contract.travel_hints(root, load_registry(root))
    assert "T004" in h2 and "不能写已到达" not in h2 and "落在 T004/gate_west" in h2


def test_clamped_player_move_re_solves_once(tmp_path, fake_adapter):
    root = _install(tmp_path)
    reg = load_registry(root)
    sdk.apply(root, sdk.verify(root, [{"op": "move_to", "who": "player", "to": "main_street"}], reg).accepted, reg)
    _no_hazards(root)
    a = fake_adapter([
        '{"narration": "你一路摸进了地穴最深处。", "ops": [{"op": "move_to", "who": "player", "to": "D001"}]}',
        '{"narration": "你走进地穴,停在潮湿的前室。", "ops": [{"op": "move_to", "who": "player", "to": "D001"}]}',
    ])
    out = turn_v3.solve_turn(root, user_text="我去地穴", provider=None, turn=2, soul_reports=[])
    assert out["loops"] == 1 and len(a.calls) == 2 and "本回合只能到 D001/D001_R001" in a.calls[1][1].content
    assert out["narration"].startswith("你走进地穴") and out["apply"].repaired[0]["to"] == "D001/D001_R001"
    assert load_registry(root).player_location == "D001/D001_R001"


# ── persuasion adjudication (轻的角色自判,重的掷骰,思考链公开) ──


def test_sjudge_confides_bakes_empathy_line(tmp_path, monkeypatch):
    """E7 A5b: the player opens up, Elena answered with a probe. A `confides`
    reading ≥ .6 bakes 'meet it first' into the speech prompt (still no LLM here)."""
    from neonrp.packs.rpg import soul_step

    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    root = _install(tmp_path)

    def stub(state, qs):
        return {"attitude": s1.Answer("choice", "probe", {}, 0.9), "register": s1.Answer("choice", "curt", {}, 0.8),
                "urgency": s1.Answer("choice", "2", {}, 0.9), "want_move": s1.Answer("noul", 0.1, {}, 0.9),
                "free": s1.Answer("noul", 0.1, {}, 0.9), "confides": s1.Answer("noul", 0.82, {}, 0.9), "asked": s1.Answer("noul", 0.1, {}, 0.9)}

    s1.install_stub(stub)
    try:
        j = soul_step.judge_soul(root, "si-elena0001", situation="场景:河边。玩家此刻:「我不知道自己还能不能撑下去。」")
        assert j.confides == 0.82 and "倾诉" in j.baked() and "先接住" in j.baked() and j.answers["confides"]["v"] == 0.82
    finally:
        s1.install_stub(None)


def test_ablation_knobs_adjudicate_off_and_pack_budget(tmp_path, monkeypatch):
    """Ablation arms: NEONRP_SOUL_ADJUDICATE=0 drops the persuasion verdict (judgment chain stays);
    NEONRP_PACK_BUDGET trims the world pack."""
    from neonrp.core import engine_config
    from neonrp.packs.rpg import soul_step

    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    monkeypatch.setenv("NEONRP_SOUL_ADJUDICATE", "0")
    monkeypatch.setenv("NEONRP_PACK_BUDGET", "1500")
    root = _install(tmp_path)
    assert engine_config.get(root, "turn.parallel.souls.adjudicate", 1) == 0 and engine_config.get(root, "turn.plan.pack_budget", 0) == 1500

    def stub(state, qs):
        return {"attitude": s1.Answer("choice", "probe", {}, 0.9), "asked": s1.Answer("noul", 0.95, {}, 0.9), "costly": s1.Answer("noul", 0.1, {}, 0.9),
                "willingness": s1.Answer("noul", 0.8, {}, 0.9), "urgency": s1.Answer("choice", "1", {}, 0.9), "want_move": s1.Answer("noul", 0.1, {}, 0.9), "free": s1.Answer("noul", 0.1, {}, 0.9)}

    s1.install_stub(stub)
    try:
        j = soul_step.judge_soul(root, "si-elena0001", situation="场景:北门。玩家此刻:帮我拿一下提灯")
        assert j.attitude == "probe" and j.decision is None and "你的决定是" not in j.baked()
    finally:
        s1.install_stub(None)
    lean = len(sdk.render_pack(sdk.pack(root, budget_chars=1500)))
    full = len(sdk.render_pack(sdk.pack(root)))
    assert lean < full and lean <= 1500 + 400


# ── triggers: the world author's rules over the closed schema ──


def _trig(root, tid, spec):
    from neonrp.core.registry import register
    register(root, "triggers", tid, spec)


def test_register_trigger_validates_and_loads(tmp_path):
    from neonrp.core.registry import RegisterError, register

    root = _install(tmp_path)
    with pytest.raises(RegisterError, match="then"):
        register(root, "triggers", "t0", {"on": {"var": "player.gold", "when": "<", "value": 3}})
    with pytest.raises(RegisterError, match="unknown variable"):
        register(root, "triggers", "t0", {"on": {"var": "nope", "when": "<", "value": 3}, "emit": [{"to": "log"}]})
    with pytest.raises(RegisterError, match="exactly one"):
        register(root, "triggers", "t0", {"on": {"var": "player.gold", "entry": "inn"}, "emit": [{"to": "log"}]})
    with pytest.raises(RegisterError, match="unknown soul"):
        register(root, "triggers", "t0", {"on": {"flag": "x"}, "emit": [{"to": "soul", "who": "谁", "text": "y"}]})
    register(root, "triggers", "gold_low", {"on": {"var": "player.gold", "when": "<", "value": 3}, "once": True, "doc": "钱快没了",
                                            "emit": [{"to": "narration", "text": "钱袋快空了({after} 枚)"}, {"to": "soul", "who": "艾琳娜", "text": "玩家的钱只剩 {after} 枚", "important": True}]})
    reg = load_registry(root)
    assert "gold_low" in reg.triggers and reg.triggers["gold_low"].once and reg.triggers["gold_low"].source == "game/meta/triggers.json"
    assert _j(root / "game" / "meta" / "triggers.json")["gold_low"]["doc"] == "钱快没了"
    # manifest.json is the world author's other door
    (root / "manifest.json").write_text(json.dumps({"triggers": [{"id": "day_passes", "on": {"var": "time.day", "when": "changed"}, "emit": [{"to": "log"}]}]}), encoding="utf-8")
    reg = load_registry(root)
    assert reg.triggers["day_passes"].source == "manifest.json"


def test_trigger_value_watch_is_edge_triggered_once_and_reaches_pack_and_soul(tmp_path):
    root = _install(tmp_path)
    _trig(root, "gold_low", {"on": {"var": "player.gold", "when": "<", "value": 3}, "once": True,
                             "emit": [{"to": "narration", "text": "钱袋快空了({after} 枚)"}, {"to": "soul", "who": "艾琳娜", "text": "玩家的钱只剩 {after} 枚", "important": True},
                                      {"to": "flag", "key": "broke"}, {"to": "tool", "name": "referee", "args": {"check": "poverty"}}]})
    reg = load_registry(root)
    ar = sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": -16}], reg, turn=3)
    assert len(ar.triggered) == 1 and ar.triggered[0]["trigger"] == "gold_low"
    assert ar.triggered[0]["payload"] == {"var": "player.gold", "before": 18, "after": 2}
    assert ar.triggered[0]["why"] == ["when:player.gold 变了:18 → 2", "if:player.gold = 2 < 3 成立"] and ar.triggered[0]["branch"] == "then"
    assert [e["to"] for e in ar.triggered[0]["emitted"]] == ["narration", "soul", "flag", "tool"]
    assert ar.variables["flag.broke"] is True and ar.requests[0] == {"kind": "tool", "name": "referee", "args": {"check": "poverty"}, "trigger": "gold_low", "payload": ar.triggered[0]["payload"]}
    evs = _j(root / "souls" / "elena-si-elena0001" / "short-term-memo" / "recent_events.json")["events"]
    assert evs[-1]["event"] == "玩家的钱只剩 2 枚" and evs[-1]["by"] == "engine.trigger:gold_low" and evs[-1]["important"] is True
    # the world sees it next pack (tier 0), the soul sees it in her recent memory
    reg = load_registry(root)
    text = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "# 引擎的消息" in text and "钱袋快空了(2 枚)" in text
    assert "玩家的钱只剩 2 枚" in sdk.render_pack(sdk.pack(root, viewer="si-elena0001", registry=reg))
    # still < 3 next turn: no re-fire (once, and edge)
    ar2 = sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": -1}], reg, turn=4)
    assert ar2.triggered == [] and _j(root / "game" / "meta" / "trigger_state.json")["gold_low"] == {"count": 1, "last_turn": 3}


def test_trigger_delta_entry_flag_and_cooldown(tmp_path):
    root = _install(tmp_path)
    _trig(root, "big_spend", {"on": {"var": "player.gold", "when": "delta<=", "value": -5}, "cooldown": 2, "emit": [{"to": "var", "var": "player.gold", "add": 1}, {"to": "log"}]})
    _trig(root, "into_street", {"on": {"entry": "主街", "event": "enter", "who": "player"}, "emit": [{"to": "narration", "text": "{who} 到了 {entry}"}]})
    _trig(root, "met", {"on": {"flag": "met_guard"}, "emit": [{"to": "narration", "text": "守门人记住了你"}]})
    _trig(root, "off", {"on": {"flag": "met_guard"}, "enabled": False, "emit": [{"to": "log"}]})
    reg = load_registry(root)
    ar = sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/main_street"}, {"op": "add", "var": "player.gold", "delta": -6}, {"op": "flag", "key": "met_guard"}], reg, turn=5)
    fired = {t["trigger"]: t for t in ar.triggered}
    assert set(fired) == {"big_spend", "into_street", "met"}  # `off` is disabled
    assert fired["big_spend"]["payload"]["delta"] == -6 and ar.variables["player.gold"] == 13  # 18 − 6 + 1 (emit var add)
    assert fired["into_street"]["emitted"][0]["text"] == "player 到了 T001/main_street"
    # cooldown 2: a second big spend on turn 6 is swallowed, turn 8 fires again
    assert sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": -6}], reg, turn=6).triggered == []
    assert [t["trigger"] for t in sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": -6}], reg, turn=8).triggered] == ["big_spend"]


def test_solve_turn_records_triggers_and_next_pack_shows_them(tmp_path, fake_adapter):
    root = _install(tmp_path)
    _trig(root, "gold_low", {"on": {"var": "player.gold", "when": "<", "value": 3}, "emit": [{"to": "narration", "text": "钱袋快空了"}]})
    fake_adapter(['{"narration": "你把几乎所有的钱都付给了掌柜。", "ops": [{"op": "add", "var": "player.gold", "delta": -16}]}'])
    out = turn_v3.solve_turn(root, user_text="我付钱", provider=None, turn=1, soul_reports=[])
    assert out["apply"].triggered and out["apply"].to_dict()["triggered"][0]["trigger"] == "gold_low"
    assert "钱袋快空了" in sdk.render_pack(sdk.pack(root))


# ── open-schema extension: a creator registers a class, the engine does the rest ──

QUEST = {"folder": "game/quests", "scope": "world", "tier": 1, "id_prefix": "Q",
         "props": {"name": {"type": "str", "required": True}, "stage": {"type": "int", "min": 0, "max": 5},
                   "status": {"type": "enum", "values": ["open", "done"]}, "reward": {"type": "int"}},
         "mutable": ["stage", "status"], "rels": {"giver": "npc|soul"},
         "render": "- {id} {name}:阶段 {stage} · {status} · 委托人 {rel_giver}"}


def test_register_class_with_props_rels_folder_and_validation(tmp_path):
    from neonrp.core.registry import RegisterError, register

    root = _install(tmp_path)
    with pytest.raises(RegisterError, match="template class"):
        register(root, "classes", "place", {"folder": "game/places"})
    with pytest.raises(RegisterError, match="enum needs values"):
        register(root, "classes", "quest", {**QUEST, "props": {"status": {"type": "enum"}}})
    with pytest.raises(RegisterError, match="mutable prop"):
        register(root, "classes", "quest", {**QUEST, "mutable": ["nope"]})
    with pytest.raises(RegisterError, match="unknown class"):
        register(root, "classes", "quest", {**QUEST, "rels": {"giver": "dragon"}})
    register(root, "classes", "quest", QUEST)
    reg = load_registry(root)
    c = reg.classes["quest"]
    assert c.custom and c.folder == "game/quests" and c.mutable == ["stage", "status"] and c.rels == {"giver": "npc|soul"} and c.tier == 1
    # an instance written by hand in the class folder loads like any entry, with typed props and rels checked
    (root / "game" / "quests").mkdir(parents=True)
    (root / "game" / "quests" / "Q900.json").write_text(json.dumps({"id": "Q900", "props": {"name": "找罗文", "stage": 1, "status": "open"}, "rels": {"giver": "si-elena0001"}, "aliases": ["罗文的下落"]}, ensure_ascii=False), encoding="utf-8")
    reg = load_registry(root)
    q = reg.entries["Q900"]
    assert q.cls == "quest" and q.rels == {"giver": "si-elena0001"} and reg.resolve("罗文的下落") == "Q900" and q.source == "game/quests/Q900.json"
    from neonrp.core.registry import check_envelope
    assert check_envelope(reg, q) == []
    from neonrp.core.registry import Envelope as _Env
    bad = _Env("Q901", "quest", props={"name": "x", "stage": 9, "status": "weird"}, rels={"giver": "T001/inn", "owner": "player"})
    probs = check_envelope(reg, bad)
    assert any("status" in x for x in probs) and any("rel 'giver'" in x and "place" in x for x in probs) and any("rel 'owner' not declared" in x for x in probs)
    # entries.json overlay can also carry rels; a wrong class is refused at register time
    with pytest.raises(RegisterError, match="allowed npc"):
        register(root, "entries", "Q902", {"class": "quest", "props": {"name": "y"}, "rels": {"giver": "T001/inn"}})


def test_new_and_patch_ops_write_instances_and_pack_shows_them(tmp_path):
    from neonrp.core.registry import register

    root = _install(tmp_path)
    register(root, "classes", "quest", QUEST)
    reg = load_registry(root)
    # the pack tells the model what it may register (and how), before any instance exists
    text = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "# 可登记的类" in text and "new quest <名字> stage=<int> status=open|done" in text and "patch <名字> stage=… status=…" in text and "remove <名字>" in text
    vr = sdk.verify(root, [
        {"op": "new", "class": "quest", "name": "找罗文", "props": {"stage": 7, "status": "open", "reward": "20"}},  # stage clamps to 5, reward coerces
        {"op": "new", "class": "faction", "name": "x"},  # unregistered class
        {"op": "new", "class": "quest", "name": ""},  # no name
        {"op": "new", "class": "quest", "name": "坏的", "props": {"status": "weird"}},  # enum
    ], reg)
    # an unregistered class grows on use (open schema, 10-20): defined, then the instance
    assert [o["op"] for o in vr.accepted] == ["new", "define", "new"] and vr.accepted[0]["props"]["stage"] == 5 and vr.accepted[0]["props"]["reward"] == 20
    assert [r.field for r in vr.refused] == ["name", "props"] and vr.accepted[1]["name"] == "faction"
    ar = sdk.apply(root, vr.accepted[:1], reg, turn=2)
    assert ar.created[0]["id"] == "Q001" and ar.created[0]["path"] == "game/quests/Q001.json" and ar.repaired[0]["prop"] == "stage"
    assert _j(root / "game" / "quests" / "Q001.json")["props"] == {"stage": 5, "status": "open", "reward": 20, "name": "找罗文"}
    reg = load_registry(root)
    assert reg.entries["Q001"].cls == "quest" and reg.resolve("找罗文") == "Q001"
    text = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "## quest" in text and "- Q001 找罗文:阶段 5 · open · 委托人 ?" in text
    # patch: only mutable props, typed
    vr = sdk.verify(root, [{"op": "patch", "who": "找罗文", "props": {"stage": 2, "status": "done"}},
                          {"op": "patch", "who": "Q001", "props": {"name": "改名"}},  # not mutable
                          {"op": "patch", "who": "Q001", "props": {"status": "weird"}},  # enum
                          {"op": "patch", "who": "谁", "props": {"stage": 1}}], reg)
    assert len(vr.accepted) == 1 and vr.accepted[0]["who"] == "Q001"
    assert [r.field for r in vr.refused] == ["props", "props", "who"] and vr.refused[0].allowed == ["stage", "status"]
    ar = sdk.apply(root, vr.accepted, reg, turn=3)
    assert ar.applied[0] == {"op": "patch", "who": "Q001", "props": {"stage": {"from": 5, "to": 2}, "status": {"from": "open", "to": "done"}}, "handler": "patch_props"}
    assert _j(root / "game" / "quests" / "Q001.json")["props"]["status"] == "done"
    # a second `new` gets the next id
    ar = sdk.apply(root, sdk.verify(root, [{"op": "new", "class": "quest", "name": "第二个"}], reg).accepted, reg, turn=4)
    assert ar.created[0]["id"] == "Q002"


def test_trigger_on_instance_prop(tmp_path):
    from neonrp.core.registry import register

    root = _install(tmp_path)
    register(root, "classes", "quest", QUEST)
    reg = load_registry(root)
    sdk.apply(root, sdk.verify(root, [{"op": "new", "class": "quest", "name": "找罗文", "props": {"stage": 0, "status": "open"}}], reg).accepted, reg, turn=1)
    register(root, "triggers", "quest_done", {"on": {"entry": "找罗文", "prop": "status", "when": "==", "value": "done"},
                                              "emit": [{"to": "narration", "text": "任务「{entry}」完成"}, {"to": "var", "var": "player.gold", "add": 5}]})
    register(root, "triggers", "quest_moves", {"on": {"entry": "Q001", "prop": "stage", "when": "changed"}, "emit": [{"to": "log"}]})
    reg = load_registry(root)
    ar = sdk.apply(root, sdk.verify(root, [{"op": "patch", "who": "Q001", "props": {"stage": 3}}], reg).accepted, reg, turn=2)
    assert [t["trigger"] for t in ar.triggered] == ["quest_moves"] and ar.triggered[0]["payload"] == {"entry": "Q001", "prop": "stage", "before": 0, "after": 3}
    ar = sdk.apply(root, sdk.verify(root, [{"op": "patch", "who": "Q001", "props": {"status": "done"}}], reg).accepted, reg, turn=3)
    assert [t["trigger"] for t in ar.triggered] == ["quest_done"] and ar.variables["player.gold"] == 23
    assert "任务「Q001」完成" in sdk.render_pack(sdk.pack(root, registry=load_registry(root)))


# ── ledger + hooks: one outlet, push and pull (design §2, T1) ──


def test_apply_writes_ledger_and_pushes_hooks(tmp_path):
    from neonrp.core import ledger

    root = _install(tmp_path)
    _trig(root, "gold_low", {"on": {"var": "player.gold", "when": "<", "value": 3}, "emit": [{"to": "tool", "name": "referee"}]})
    reg = load_registry(root)
    seen: list[dict] = []
    off_gold = sdk.on("var.changed:player.gold", seen.append)
    off_all = sdk.on("*", lambda ev: seen.append({"all": ev["type"]}))
    off_trig = sdk.on("trigger.fired:*", lambda ev: seen.append({"trig": ev["payload"]["id"]}))
    try:
        ar = sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/main_street"}, {"op": "add", "var": "player.gold", "delta": -16}, {"op": "flag", "key": "paid"}], reg, turn=7)
    finally:
        off_gold()
        off_all()
        off_trig()
    types = [e["type"] for e in ar.events]
    assert types == ["entry.entered", "var.changed", "flag.set", "trigger.fired", "tool.requested", "turn.done"]
    assert [e["seq"] for e in ar.events] == [1, 2, 3, 4, 5, 6] and ar.to_dict()["events"] == [1, 2, 3, 4, 5, 6]
    assert seen[0]["all"] == "entry.entered"  # "*" sees everything in seq order
    gold = [x for x in seen if x.get("type") == "var.changed"]
    assert gold and gold[0]["payload"] == {"var": "player.gold", "from": 18, "to": 2, "by": "solve"} and gold[0]["turn"] == 7
    assert {"trig": "gold_low"} in seen
    # pull: by type, since seq, variable history; the ledger file is one line per event
    assert [e["seq"] for e in sdk.events(root, since=4)] == [5, 6]
    assert sdk.events(root, type="flag.set")[0]["payload"] == {"key": "paid", "from": None}
    sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": 1}], reg, turn=8)
    assert [(h["turn"], h["from"], h["to"]) for h in sdk.history(root, "player.gold")] == [(7, 18, 2), (8, 2, 3)]
    assert len((root / "game" / "meta" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()) == 8
    # a subscriber that raises never breaks the turn
    off = sdk.on("*", lambda ev: 1 / 0)
    try:
        assert sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": 1}], reg, turn=9).events
    finally:
        off()


def test_hook_can_only_enqueue_and_the_op_rides_next_verify(tmp_path, fake_adapter):
    from neonrp.core import ledger

    root = _install(tmp_path)
    # a hook reacts to a landed change by queueing an op — it lands on the NEXT turn through verify, not by writing files
    off = sdk.on("flag.set:paid", lambda ev: sdk.enqueue(root, {"op": "add", "var": "player.gold", "delta": -2}, by="tax"))
    try:
        reg = load_registry(root)
        sdk.apply(root, [{"op": "flag", "key": "paid"}], reg, turn=1)
    finally:
        off()
    assert _j(root / "game" / "meta" / "op_queue.json")["ops"][0]["_by"] == "tax"
    fake_adapter(['{"narration": "你数了数钱。", "ops": []}'])
    out = turn_v3.solve_turn(root, user_text="数钱", provider=None, turn=2, soul_reports=[])
    assert [a["op"] for a in out["apply"].applied] == ["add"] and out["apply"].variables["player.gold"] == 16
    assert ledger.drain(root) == []  # queue consumed
    # a queued op that verify refuses is refused like any other, with the reason recorded
    sdk.enqueue(root, {"op": "add", "var": "nope", "delta": 1})
    fake_adapter(['{"narration": "x", "ops": []}'])
    out = turn_v3.solve_turn(root, user_text="x", provider=None, turn=3, soul_reports=[])
    first = out["proposals"][0]["refused"]  # refused on attempt 0, fed back to the model, attempt 1 came back clean
    assert first and "unknown variable" in first[0]["why"] and out["loops"] == 1 and out["verify"]["refused"] == []


# ── E2: the other two soul variants produce the same SoulPatch shape ──


def test_soul_step_s_direct_reads_fields_from_one_json_reply(tmp_path, monkeypatch):
    from neonrp.core import light_chat
    from neonrp.packs.rpg import soul_step

    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    root = _install(tmp_path)
    seen = {}

    def fake_deliver(root_, target, question, *, asker="world-agent", **_kw):
        seen["q"] = question
        return {"ok": True, "answer": '```json\n{"speech": "「拿着。」我把提灯递过去。", "attitude": "comply", "register": "warm", "urgency": 1, "want_move": false, "move_to": null, "free": 0.1, "asked": 0.95, "costly": 0.1, "why_costly": "none", "willingness": 0.8, "confides": 0.0}\n```'}

    monkeypatch.setattr(light_chat, "ask_soul_deliver", fake_deliver)
    r = soul_step.soul_step(root, "si-elena0001", situation="场景:北门。玩家此刻:帮我拿一下提灯", depth="speak", variant="S-direct")
    assert r["kind"] == "speak" and r["text"] == "「拿着。」我把提灯递过去。" and "<fields>" in seen["q"] and "JSON" not in seen["q"]
    j = r["judgment"]
    assert j["source"] == "llm-direct" and j["attitude"] == "comply" and j["register"] == "warm" and j["urgency"] == 1 and j["answers"]["willingness"]["v"] == 0.8
    assert j["decision"]["stakes"] == "light" and j["decision"]["outcome"] == "comply" and j["decision"]["post_hoc"] is True and j["decision"]["roll"] is None
    # a reply that is not JSON still yields the line, with no judgment fields
    monkeypatch.setattr(light_chat, "ask_soul_deliver", lambda *a, **k: {"ok": True, "answer": "「拿着。」"})
    r = soul_step.soul_step(root, "si-elena0001", situation="x", depth="speak", variant="S-direct")
    assert r["text"] == "「拿着。」" and r["judgment"]["attitude"] is None and r["judgment"]["decision"] is None


def test_soul_step_s_free_speaks_first_then_jev_classifies_the_text(tmp_path, monkeypatch):
    from neonrp.core import light_chat
    from neonrp.packs.rpg import soul_step

    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    root = _install(tmp_path)
    monkeypatch.setattr(light_chat, "ask_soul_deliver", lambda root_, t, q, *, asker="world-agent", **_kw: {"ok": True, "answer": "「不。剑不离身。」我按住剑鞘。"})
    states = []

    def stub(state, qs):
        states.append(state)
        return {"attitude": s1.Answer("choice", "refuse", {}, 0.9), "register": s1.Answer("choice", "curt", {}, 0.9), "urgency": s1.Answer("choice", "1", {}, 0.9),
                "want_move": s1.Answer("noul", 0.1, {}, 0.9), "free": s1.Answer("noul", 0.1, {}, 0.9), "asked": s1.Answer("noul", 0.95, {}, 0.9),
                "costly": s1.Answer("noul", 0.8, {}, 0.9), "why_costly": s1.Answer("choice", "interest", {}, 0.9), "willingness": s1.Answer("noul", 0.2, {}, 0.9)}

    s1.install_stub(stub)
    try:
        r = soul_step.soul_step(root, "si-elena0001", situation="场景:北门。玩家此刻:把你的短剑给我", depth="speak", variant="S-free")
    finally:
        s1.install_stub(None)
    assert r["kind"] == "speak" and r["text"].startswith("「不。") and states[0]["her_reaction"].startswith("「不。")
    j = r["judgment"]
    assert j["source"].endswith("-after") and j["attitude"] == "refuse" and j["decision"]["stakes"] == "heavy" and j["decision"]["post_hoc"] is True and j["decision"]["roll"] is None
    assert j["decision"]["outcome"] == "refuse"  # heavy without dice: willingness .2 against the threshold


def test_session_dispatches_soul_variant_from_env(tmp_path, monkeypatch):
    from neonrp.core import engine_config

    monkeypatch.setenv("NEONRP_SOUL_VARIANT", "S-free")
    root = _install(tmp_path)
    assert engine_config.get(root, "turn.parallel.souls.default_variant", "legacy") == "S-free"


# ── compact variable syntax + MVU-tag fallback ──


def test_compact_var_syntax_and_mvu_tags():
    from neonrp.core.sdk import parse_solve_output, var_op

    assert var_op("player.gold", "-3") == {"op": "add", "var": "player.gold", "delta": -3}
    assert var_op("player.gold", "+ 2") == {"op": "add", "var": "player.gold", "delta": 2}
    assert var_op("time.day", 4) == {"op": "set", "var": "time.day", "value": 4}
    assert var_op("time.day", "4") == {"op": "set", "var": "time.day", "value": 4}
    assert var_op("flag.x", "true") == {"op": "set", "var": "flag.x", "value": True}
    assert var_op("mood", "alert") == {"op": "set", "var": "mood", "value": "alert"}
    # every compact form lands as the same ops
    o = parse_solve_output('{"narration": "你付了钱。", "ops": [{"var": "player.gold", "value": "-3"}, {"time.day": 4}, "player.hp +5", "flag paid", {"op": "set", "var": "player.gold", "value": "+1"}], "vars": {"player.sanity": "-2"}}')
    assert o.fmt == "json" and o.ops == [
        {"op": "add", "var": "player.gold", "delta": -3}, {"op": "set", "var": "time.day", "value": 4}, {"op": "add", "var": "player.hp", "delta": 5},
        {"op": "flag", "key": "paid"}, {"op": "add", "var": "player.gold", "delta": 1}, {"op": "add", "var": "player.sanity", "delta": -2}]
    # E5 det-l2 09-27: the model wrote the compact form as an op named "vars"
    o = parse_solve_output('{"narration": "x", "ops": [{"op": "vars", "player.gold": "-2", "time.day": 3}, {"op": "vars", "vars": {"player.hp": "+1"}}]}')
    assert o.ops == [{"op": "add", "var": "player.gold", "delta": -2}, {"op": "set", "var": "time.day", "value": 3}, {"op": "add", "var": "player.hp", "delta": 1}]
    # weaker models: tags in the prose are lifted into ops and stripped from what the player reads
    o = parse_solve_output("药水滚烫地流过喉咙,但你感觉好多了。\n\n[player.hp: +20]\n[time.day: 4]")
    assert o.fmt == "brackets" and o.narration == "药水滚烫地流过喉咙,但你感觉好多了。" and o.ops == [{"op": "add", "var": "player.hp", "delta": 20}, {"op": "set", "var": "time.day", "value": 4}]
    o = parse_solve_output('{"narration": "她点点头。[player.gold: -1]", "ops": []}')
    assert o.narration == "她点点头。" and o.ops == [{"op": "add", "var": "player.gold", "delta": -1}]
    # prose brackets that are not tags are left alone
    o = parse_solve_output('{"narration": "门上刻着[禁入]两个字。", "ops": []}')
    assert o.narration == "门上刻着[禁入]两个字。" and o.ops == []


def test_compact_vars_pass_verify_and_apply(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    from neonrp.core.sdk import parse_solve_output

    o = parse_solve_output('{"narration": "x", "vars": {"player.gold": "-3"}, "ops": ["flag paid"]}')
    vr = sdk.verify(root, o.ops, reg)
    assert not vr.refused
    ar = sdk.apply(root, vr.accepted, reg, turn=1)
    assert ar.variables["player.gold"] == 15 and ar.variables["flag.paid"] is True


# ── companions follow an in-town player move unless they said otherwise (E1 v3-split T4) ──


def test_companion_follows_player_move_when_judged_so(tmp_path, fake_adapter):
    root = _install(tmp_path)
    rep = lambda follow, stay=0.1: [{"iid": "si-elena0001", "name": "艾琳娜", "kind": "speak", "text": "「走吧。」", "judgment": {"follow": follow, "stay": stay}}]  # noqa: E731
    # the model moves only the player; she was judged to follow → she moves too
    fake_adapter(['{"narration": "你推门进了旅店,她跟在半步后。", "ops": [{"op": "move_to", "who": "player", "to": "main_street"}]}'])
    out = turn_v3.solve_turn(root, user_text="我往主街走", provider=None, turn=1, soul_reports=rep(0.9))
    assert {(a["who"], a["to"]) for a in out["apply"].applied if a["op"] == "move_to"} == {("player", "T001/main_street"), ("si-elena0001", "T001/main_street")}
    assert any(o.get("_from") == "follow" for o in out["proposals"][0]["ops"]) is False  # the model's ops are untouched; the follow op is the engine's
    # judged not to follow (「你在这里等我」) → she stays; so does a follow .64 with an explicit "stay" .8 (E5 C3a)
    for follow, stay in ((0.2, 0.1), (0.64, 0.8)):
        root = _install(tmp_path / f"b{stay}")
        fake_adapter(['{"narration": "你独自往主街走。", "ops": [{"op": "move_to", "who": "player", "to": "main_street"}]}'])
        out = turn_v3.solve_turn(root, user_text="你在这里等我", provider=None, turn=1, soul_reports=rep(follow, stay))
        assert [(a["who"], a["to"]) for a in out["apply"].applied if a["op"] == "move_to"] == [("player", "T001/main_street")]
    # cross-town: the player is clamped to the gate this turn; she follows to the same landing (a quiet road: no referee stop)
    root = _install(tmp_path / "d")
    _no_hazards(root)
    fake_adapter(['{"narration": "你们出发去碧石镇。", "ops": [{"op": "move_to", "who": "player", "to": "T004"}]}', '{"narration": "你们走到北门。", "ops": [{"op": "move_to", "who": "player", "to": "T004"}]}'])
    out = turn_v3.solve_turn(root, user_text="我们去碧石镇", provider=None, turn=1, soul_reports=rep(0.9))
    mv = {a["who"]: a["to"] for a in out["apply"].applied if a["op"] == "move_to"}
    assert mv["player"] == mv["si-elena0001"]  # wherever the judge lands the player this turn, she lands too
    # the model already moved her somewhere else → no follow op on top
    root = _install(tmp_path / "c")
    fake_adapter(['{"narration": "她去了旅店,你去了主街。", "ops": [{"op": "move_to", "who": "player", "to": "main_street"}, {"op": "move_to", "who": "艾琳娜", "to": "inn"}]}'])
    out = turn_v3.solve_turn(root, user_text="分头走", provider=None, turn=1, soul_reports=rep(0.9))
    assert {(a["who"], a["to"]) for a in out["apply"].applied if a["op"] == "move_to"} == {("player", "T001/main_street"), ("si-elena0001", "T001/inn")}


def test_companion_follows_after_a_talk(tmp_path, fake_adapter, monkeypatch):
    # PL12 watch4 10-17: a Resolve after a talk — the people present take no turn, the board did not name her,
    # the model moved only the player. The companions rule now judges her over the whole talk.
    talk = ["旅人:我和艾琳娜直接去河灯旅店,先付钱住下。", "主持:去河灯旅店,通铺一晚 3 金。"]
    one = '{"narration": "你推门进了旅店。", "ops": [{"op": "move_to", "who": "player", "to": "inn"}]}'
    moves = lambda out: {(a["who"], a["to"]) for a in out["apply"].applied if a["op"] == "move_to"}  # noqa: E731
    # the judge answers: follow .84 → she comes along, and the trace keeps the numbers
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    seen = {}

    def stub(state, qs):
        seen["said"], seen["qs"] = state["player_says"], sorted(qs)
        return {"follow": s1.Answer("noul", 0.84, {}, 0.7), "stay": s1.Answer("noul", 0.02, {}, 0.9)}

    s1.install_stub(stub)
    try:
        root = _install(tmp_path / "a")
        fake_adapter([one])
        out = turn_v3.solve_turn(root, user_text="", provider=None, turn=1, soul_reports=[], talk=talk)
    finally:
        s1.install_stub(None)
    assert ("si-elena0001", "T001/inn") in moves(out) and seen["qs"] == ["follow", "stay"] and "我和艾琳娜" in seen["said"]
    assert out["companions"] == [{"iid": "si-elena0001", "name": "艾琳娜", "follow": 0.84, "stay": 0.02, "src": "talk", "moved": True}]
    # no judge: the player named her → she comes; not named → she stays
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    root = _install(tmp_path / "b")
    fake_adapter([one])
    out = turn_v3.solve_turn(root, user_text="", provider=None, turn=1, soul_reports=[], talk=talk)
    assert ("si-elena0001", "T001/inn") in moves(out) and out["companions"][0]["src"] == "named"
    root = _install(tmp_path / "c")
    fake_adapter([one])
    out = turn_v3.solve_turn(root, user_text="", provider=None, turn=1, soul_reports=[], talk=["旅人:我去旅店住下。"])
    assert moves(out) == {("player", "T001/inn")} and out["companions"][0]["moved"] is False
    # not a Resolve after a talk (talk None): a soul with no report is left alone, as before
    root = _install(tmp_path / "d")
    fake_adapter([one])
    out = turn_v3.solve_turn(root, user_text="我和艾琳娜去旅店", provider=None, turn=1, soul_reports=[])
    assert moves(out) == {("player", "T001/inn")} and out["companions"] == []


def test_companion_follows_a_move_the_narrate_transition_wrote(tmp_path, fake_adapter, monkeypatch):
    # follow-1017: in narrate mode the prose carries no ops — the player's move comes from the transition call,
    # after the first verify; the companions rule has to read that one
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    root = _install(tmp_path)
    fake_adapter(["<lines>\n你们推门进了旅店。\n</lines>", "<vars>\n</vars>\n<files>\nmove_to player inn\n</files>"])
    out = turn_v3.solve_turn(root, user_text="", provider=None, turn=1, soul_reports=[], talk=["旅人:我和艾琳娜去旅店。"])
    assert {(a["who"], a["to"]) for a in out["apply"].applied if a["op"] == "move_to"} == {("player", "T001/inn"), ("si-elena0001", "T001/inn")}
    assert out["companions"][0]["src"] == "named" and "companions" in [s["actor"] for s in out["spans"]]


def test_moves_into_an_invented_id_walk_into_the_batch_new_place(tmp_path, fake_adapter, monkeypatch):
    # N2 watch4 10-17: the transition named the new place and walked into an invented id — two places grew,
    # the player stood in the invented one. Now the moves mean the one new place of the batch.
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    root = _install(tmp_path)
    fake_adapter(["<lines>\n出了北门,小路窄下来。\n</lines>",
                  "<vars>\n</vars>\n<files>\nmove_to player T001/mossbarrow_path\nnew_location 苔墓小径\nmove_to 艾琳娜 T001/mossbarrow_path\n</files>"])
    out = turn_v3.solve_turn(root, user_text="", provider=None, turn=1, soul_reports=[])
    places = [c for c in out["apply"].created if c["class"] == "place"]
    assert len(places) == 1, places
    mv = {a["who"]: a["to"] for a in out["apply"].applied if a["op"] == "move_to"}
    assert mv["player"] == mv["si-elena0001"] == places[0]["id"] and "mossbarrow" not in places[0]["id"]
    # two new places in one batch: no guess — the invented id stays the model's choice
    reg = load_registry(_install(tmp_path / "b"))
    two = [{"op": "new_location", "name": "甲地"}, {"op": "new_location", "name": "乙地"}, {"op": "move_to", "who": "player", "to": "T001/x_place"}]
    assert sdk.bind_moves_to_new_place(reg, two) == two


def test_a_misnamed_layer_mark_enters_the_layer_and_an_unknown_one_is_recorded(tmp_path):
    # N2 watch4 10-17: the prose wrote [~combat_start]; the engine dropped it and the fight never entered its layer
    reg = load_registry(_install(tmp_path))
    turn_v3._set_wait_ops(reg)
    assert sdk.op_meant("combat_start") == sdk.op_meant("start_combat") == "combat" and sdk.op_meant("combat_over") is None
    o = sdk.parse_solve_output("<lines>\n第二只从草窝里站起来。[~combat_start]\n</lines>")
    assert [x["op"] for x in o.ops] == ["combat"] and any(m.get("as") == "combat" for m in o.marks)
    o = sdk.parse_solve_output("<lines>\n它扑上来。[~wolf_howl]\n</lines>")
    assert any(m.get("unknown") and m["op"] == "wolf_howl" for m in o.marks)


def test_sjudge_asks_follow(tmp_path, monkeypatch):
    from neonrp.packs.rpg import soul_step

    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    root = _install(tmp_path)
    asked = {}

    def stub(state, qs):
        asked["qs"] = sorted(qs)
        return {"attitude": s1.Answer("choice", "comply", {}, 0.9), "follow": s1.Answer("noul", 0.85, {}, 0.9), "want_move": s1.Answer("noul", 0.1, {}, 0.9), "free": s1.Answer("noul", 0.1, {}, 0.9)}

    s1.install_stub(stub)
    try:
        j = soul_step.judge_soul(root, "si-elena0001", situation="场景:北门。玩家此刻:走,去主街")
    finally:
        s1.install_stub(None)
    assert "follow" in asked["qs"] and j.follow == 0.85 and j.to_dict()["follow"] == 0.85


def test_tags_output_mode_contract_and_parse(tmp_path):
    from neonrp.core.sdk import parse_solve_output

    root = _install(tmp_path)
    reg = load_registry(root)
    c = _rpg_contract.contract(root, reg, "tags")
    assert "[move player inn]" in c and "只输出一个 JSON 对象" not in c
    assert "只输出一个 JSON 对象" in _rpg_contract.contract(root, reg, "json_object")
    o = parse_solve_output("你推门进了旅店,她跟在半步后。门上刻着[禁入]两个字。\n\n[move player inn]\n[move 艾琳娜 inn]\n[player.gold -3]\n[time.clock 09:55]\n[flag paid]\n[ask 艾琳娜]")
    assert o.fmt == "brackets" and o.narration == "你推门进了旅店,她跟在半步后。门上刻着[禁入]两个字。"
    assert o.ops == [{"op": "move_to", "who": "player", "to": "inn"}, {"op": "move_to", "who": "艾琳娜", "to": "inn"}, {"op": "add", "var": "player.gold", "delta": -3},
                     {"op": "set", "var": "time.clock", "value": "09:55"}, {"op": "flag", "key": "paid"}, {"op": "need", "who": "艾琳娜"}]
    vr = sdk.verify(root, o.ops, reg)
    assert [x["op"] for x in vr.accepted] == ["move_to", "move_to", "add", "set", "flag", "need"] and not vr.refused
    # the explicit no-change marker: parsed as a bracket block with no ops (so "none" now means the model gave nothing)
    o = parse_solve_output("她点点头,没说话。\n\n[无变化]")
    assert o.fmt == "brackets" and o.ops == [] and o.narration == "她点点头,没说话。"
    assert parse_solve_output("她点点头,没说话。").fmt == "none"
    assert "[无变化]" in _rpg_contract.contract(root, reg, "tags")


def test_variable_doc_is_shown_as_a_rule_in_the_pack(tmp_path):
    from neonrp.core.registry import register

    root = _install(tmp_path)
    register(root, "variables", "player.hp", {"type": "int", "path": "game/meta/run_state.json", "key": "player.hp", "min": 0, "max": 30,
                                              "doc": "受伤时减 10–30,休息时加 5–15;0 = 倒下"})
    reg = load_registry(root)
    assert reg.variables["player.hp"].doc.startswith("受伤")
    text = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "# 变量(一行一个" in text and "(受伤时减 10–30,休息时加 5–15;0 = 倒下)" in text.split("- player.hp ")[1].split("\n")[0]
    assert "变量规则" not in sdk.render_pack(sdk.pack(root, viewer="si-elena0001", registry=reg))  # the soul does not see the world's rules


def test_narration_must_carry_the_souls_line_verbatim(tmp_path, fake_adapter):
    """E1 v3-sjudge T2: the narrator paraphrased Elena's line and wrote her doing the opposite.
    A present soul's quoted line missing from the prose is a fixable refusal: re-solve once with the line."""
    root = _install(tmp_path)
    rep = [{"iid": "si-elena0001", "name": "艾琳娜", "kind": "speak", "text": "「饼买两个——你说要坐下说话,这顿算你的。」我朝街那头抬了抬下巴。"}]
    a = fake_adapter([
        '{"narration": "老苇递来热饼。艾琳娜没接,那半个问题还在原地等着。", "ops": []}',
        '{"narration": "老苇递来热饼。艾琳娜说:「饼买两个——你说要坐下说话,这顿算你的。」她朝街那头抬了抬下巴。", "ops": []}',
    ])
    out = turn_v3.solve_turn(root, user_text="我买个饼", provider=None, turn=2, soul_reports=rep)
    assert out["loops"] == 1 and len(a.calls) == 2
    fed = out["proposals"][1]["fed_back"]
    assert fed and fed[0]["field"] == "narration" and "饼买两个" in fed[0]["why"]
    assert "饼买两个" in out["narration"]
    # a line already carried (with slightly different punctuation) passes without a loop
    fake_adapter(['{"narration": "艾琳娜说「饼买两个,你说要坐下说话,这顿算你的」。", "ops": []}'])
    out = turn_v3.solve_turn(root, user_text="x", provider=None, turn=3, soul_reports=rep)
    assert out["loops"] == 0
    assert "原句照抄成一行" in _rpg_contract.contract(root, load_registry(root))


def test_prose_json_mode_prose_first_block_last_and_extract_fallback(tmp_path, fake_adapter, monkeypatch):
    """Prose inside a JSON string reads worse; keep the prose free and put one JSON ops block
    at the tail. A missing block is not 'no change' — one lean extraction call recovers the ops."""
    from neonrp.core.sdk import parse_solve_output

    root = _install(tmp_path)
    reg = load_registry(root)
    c = _rpg_contract.contract(root, reg, "prose_json")
    assert "先写叙事正文" in c and "```json" in c and '{"narration"' not in c
    o = parse_solve_output('你推门进了旅店,她跟在半步后。\n\n```json\n{"ops": [{"op": "move_to", "who": "player", "to": "inn"}, {"var": "player.gold", "value": "-1"}]}\n```')
    assert o.fmt == "json" and o.narration == "你推门进了旅店,她跟在半步后。" and o.ops == [{"op": "move_to", "who": "player", "to": "inn"}, {"op": "add", "var": "player.gold", "delta": -1}]
    monkeypatch.setenv("NEONRP_V3_SOLVE", "prose_json")
    a = fake_adapter(["你推门进了旅店,她跟在半步后。", '{"ops": [{"op": "move_to", "who": "player", "to": "main_street"}]}'])
    out = turn_v3.solve_turn(root, user_text="我进旅店", provider=None, turn=1, soul_reports=[])
    assert len(a.calls) == 2 and out["solve"].fmt == "extracted" and out["narration"] == "你推门进了旅店,她跟在半步后。"
    assert [x["op"] for x in out["apply"].applied] == ["move_to"] and any(s_["actor"] == "world.extract" for s_ in out["spans"])
    # with the block present there is exactly one call
    a = fake_adapter(['她点点头。\n\n```json\n{"ops": []}\n```'])
    out = turn_v3.solve_turn(root, user_text="x", provider=None, turn=2, soul_reports=[])
    assert len(a.calls) == 1 and out["solve"].fmt == "json" and out["narration"] == "她点点头。"


def test_parallel_mode_two_calls_prose_and_ops(tmp_path, fake_adapter, monkeypatch):
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "parallel")
    # the fake adapter hands outputs in call order; both calls are issued concurrently, so accept either order
    a = fake_adapter(["你推门进了旅店。", '{"ops": [{"op": "move_to", "who": "player", "to": "main_street"}]}'])
    out = turn_v3.solve_turn(root, user_text="我进旅店", provider=None, turn=1, soul_reports=[])
    assert len(a.calls) == 2 and out["solve"].fmt == "parallel"
    assert "你推门进了旅店" in out["narration"] or out["narration"].startswith("{")  # order-dependent with a scripted double
    assert {s_["actor"] for s_ in out["spans"] if s_["phase"] == "solve"} == {"world.narrate", "world.ops"}


# ── L2: menu / duplicate line (deterministic) + Jev audit (moved / answered / grounded) ──


def test_l2_deterministic_menu_and_duplicate_line(tmp_path):
    from neonrp.core import l2

    rep = [{"iid": "si-elena0001", "name": "艾琳娜", "kind": "speak", "text": "「饼买两个——这顿算你的。」"}]
    menu = "你站在门口。\n\n1. 去公会问赫伦\n2. 回旅店等\n3. 跟着艾琳娜"
    r = l2.deterministic(menu, rep)
    assert len(r) == 1 and r[0]["field"] == "narration" and "menu of options" in r[0]["why"] and r[0]["fixable"]
    dup = "艾琳娜说:「饼买两个——这顿算你的。」老苇笑了。她又重复:「饼买两个——这顿算你的。」"
    r = l2.deterministic(dup, rep)
    assert len(r) == 1 and "appears twice" in r[0]["why"]
    assert l2.deterministic("门上刻着 1. 2. 3. 的记号。她说:「饼买两个——这顿算你的。」", rep) == []  # one numbered line is not a menu; one quote is fine


def test_l2_jev_audit_moved_answered_grounded(tmp_path, monkeypatch):
    from neonrp.core import l2

    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    root = _install(tmp_path)
    reg = load_registry(root)
    rep = [{"iid": "si-elena0001", "name": "艾琳娜", "kind": "speak", "text": "「我去趟主街。」"}]
    seen = {}

    def stub(state, qs):
        seen["qs"] = sorted(qs)
        out = {}
        for k in qs:
            if k == "moved.si-elena0001":
                out[k] = s1.Answer("noul", 0.9, {}, 0.8)
            elif k == "answered":
                out[k] = s1.Answer("noul", 0.1, {}, 0.8)
            elif k.startswith("grounded."):
                out[k] = s1.Answer("noul", 0.2, {}, 0.8)
            else:
                out[k] = s1.Answer("noul", 0.5, {}, 0.5)
        return out

    s1.install_stub(stub)
    try:
        ops = [{"op": "add", "var": "player.gold", "delta": -3}, {"op": "set", "var": "time.clock", "value": "09:20"}]  # gold not in the prose; time is never asked
        fix, drop = l2.jev_audit(root, reg, narration="艾琳娜转身往主街走了。没人理会你的问题。", ops=ops, reports=rep, user_text="你知道罗文在哪吗?")
    finally:
        s1.install_stub(None)
    assert "moved.player" in seen["qs"] and "moved.si-elena0001" in seen["qs"] and "answered" in seen["qs"] and "grounded.0" in seen["qs"] and "grounded.1" not in seen["qs"]
    assert [f["op"] for f in fix] == [{"op": "move_to", "who": "si-elena0001"}, {"op": "answer"}] and all(f["fixable"] for f in fix)
    assert drop == [0]


def test_solve_turn_l2_jev_drops_ungrounded_and_feeds_back(tmp_path, fake_adapter, monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    monkeypatch.setenv("NEONRP_V3_L2", "jev")
    root = _install(tmp_path)
    s1.install_stub(lambda state, qs: {k: s1.Answer("noul", 0.1 if k.startswith("grounded.") else 0.2, {}, 0.8) for k in qs})
    try:
        fake_adapter(['{"narration": "她点点头。", "ops": [{"op": "add", "var": "player.gold", "delta": -3}]}'])
        out = turn_v3.solve_turn(root, user_text="你好", provider=None, turn=1, soul_reports=[])
    finally:
        s1.install_stub(None)
    assert out["apply"].applied == [] and out["apply"].variables["player.gold"] == 18
    assert any(r["why"].startswith("叙事里没有发生这件事") for r in out["apply"].refused)
    assert any(s_["actor"] == "l2" for s_ in out["spans"])


# ── the handler seam: a template swaps the map by name, the engine does not change ──


def test_move_to_uses_registered_validator_and_handler(tmp_path):
    import fake_map_sdk

    from neonrp.core.registry import register

    root = _install(tmp_path)
    reg = load_registry(root)
    assert reg.actions["move_to"].validator == "neonrp.packs.rpg.atlas.move:judge" and reg.actions["move_to"].handler == "neonrp.packs.rpg.atlas.move:move"
    # default: the engine's graph (unchanged behaviour)
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "main_street"}], reg)
    assert vr.accepted and vr.accepted[0]["to"] == "T001/main_street"
    # a template points move_to at an external SDK
    register(root, "actions", "move_to", {"validator": "fake_map_sdk:judge", "handler": "fake_map_sdk:move"})
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "inn"}, {"op": "move_to", "who": "player", "to": "guild"}, {"op": "move_to", "who": "艾琳娜", "to": "main_street"}], reg)
    assert vr.refused and "SDK says the inn is closed" in vr.refused[0].why and vr.refused[0].allowed == ["T001/main_street(主街)"]
    acc = {o["who"]: o for o in vr.accepted}
    assert acc["player"]["to"] == "T001/main_street" and acc["player"]["_clamped"]["wanted"] == "T001/guild"
    fake_map_sdk.landed.clear()
    ar = sdk.apply(root, vr.accepted, reg, turn=1)
    assert fake_map_sdk.landed == [("player", "T001/main_street"), ("si-elena0001", "T001/main_street")]
    assert ar.repaired and ar.repaired[0]["why"].startswith("SDK: the guild")
    # a bad name is a refusal with the reason, never a crash
    register(root, "actions", "move_to", {"validator": "nope.module:judge"})
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "main_street"}], load_registry(root))
    assert vr.refused and "cannot import handler" in vr.refused[0].why


def test_split2_prose_then_ops_share_the_prefix(tmp_path, fake_adapter, monkeypatch):
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "split2")
    a = fake_adapter(["你推门进了旅店。", '{"ops": [{"op": "move_to", "who": "player", "to": "main_street"}]}'])
    out = turn_v3.solve_turn(root, user_text="我进旅店", provider=None, turn=1, soul_reports=[])
    assert len(a.calls) == 2 and out["solve"].fmt == "split2" and out["narration"] == "你推门进了旅店。"
    sys1, u1 = a.calls[0][0].content, a.calls[0][1].content
    sys2, u2 = a.calls[1][0].content, a.calls[1][1].content
    assert sys1 == sys2 and u2.startswith(u1.split("## 本次只写叙事")[0])  # identical prefix → provider prefix cache
    assert "刚发生的叙事" in u2 and "你推门进了旅店" in u2
    assert [x["op"] for x in out["apply"].applied] == ["move_to"]


# ── mechanics: a template registers its own contract / observe by name; defaults = RPG ──


def test_mechanics_defaults_and_override(tmp_path, fake_adapter):
    from neonrp.core import mechanics

    root = _install(tmp_path)
    from neonrp.packs.rpg.pack import MECHANICS as _RPG

    assert mechanics.spec(root) == {**mechanics.DEFAULTS, **_RPG}  # the rpg pack fills every seam the core leaves generic
    assert "石津" in mechanics.get(root, "observe")(root, "si-elena0001") or "你眼前" in mechanics.get(root, "observe")(root, "si-elena0001")
    reg = load_registry(root)
    assert mechanics.get(root, "participation")(root, reg, "si-elena0001") is True and mechanics.get(root, "participation")(root, reg, "si-rowan0001") is False
    (root / "game" / "meta" / "mechanics.json").write_text(json.dumps({"contract": "fake_map_sdk:contract", "observe": "fake_map_sdk:observe"}), encoding="utf-8")
    assert mechanics.spec(root)["contract"] == "fake_map_sdk:contract" and mechanics.spec(root)["soul_turn"] == "neonrp.packs.rpg.soul_step:soul_step"
    assert mechanics.get(root, "observe")(root, "si-elena0001") == "[桌面] 你是 si-elena0001,天亮了。"
    a = fake_adapter(['{"narration": "天亮了,昨夜无人死亡。", "ops": []}'])
    out = turn_v3.solve_turn(root, user_text="投票", provider=None, turn=1, soul_reports=[])
    assert a.calls[0][0].content.startswith("你是狼人杀的法官") and out["narration"].startswith("天亮了")
    # participation: the RPG default keeps Rowan (another town) out; a werewolf template seats everyone
    from neonrp.core import turn_plan
    from neonrp.core.playthrough import read_playthrough

    class _U:
        away_roster = (("si-rowan0001", "罗文"),)

    pt = read_playthrough(root)
    rows = {r["iid"]: r["present"] for r in turn_plan.roster_rows(root, pt, _U())}
    assert rows["si-elena0001"] is True and rows["si-rowan0001"] is False
    (root / "game" / "meta" / "mechanics.json").write_text(json.dumps({"contract": "fake_map_sdk:contract", "observe": "fake_map_sdk:observe", "participation": "fake_map_sdk:everyone"}), encoding="utf-8")
    rows = {r["iid"]: r["present"] for r in turn_plan.roster_rows(root, pt, _U())}
    assert rows["si-elena0001"] is True and rows["si-rowan0001"] is True
    # manifest.json is the other door; game/meta wins over it
    (root / "manifest.json").write_text(json.dumps({"mechanics": {"settle": "fake_map_sdk:contract", "observe": "builtin:observe.pack"}}), encoding="utf-8")
    sp = mechanics.spec(root)
    assert sp["settle"] == "fake_map_sdk:contract" and sp["observe"] == "fake_map_sdk:observe"


def test_trigger_when_if_then_else(tmp_path):
    """A rule is WHEN (what woke it) → IF (conditions on values) → THEN / ELSE. The old on/emit
    shape normalises into it. `at` conditions make places carry logic; `else` fires when the rule woke but
    the condition failed; edge rules do not repeat while the condition stays true."""
    from neonrp.core import triggers as T

    root = _install(tmp_path)
    # normalisation of the 09-26 shape
    n = T.normalize({"on": {"var": "player.gold", "when": "<", "value": 3}, "emit": [{"to": "log"}], "level": True})
    assert n["when"] == {"var": "player.gold"} and n["if"] == [{"var": "player.gold", "<": 3}] and n["then"] == [{"to": "log"}] and n["edge"] is False
    n = T.normalize({"on": {"keyword": ["a", "b"], "where": "player"}, "emit": [{"to": "log"}]})
    assert n["when"] == {"text": "player"} and n["if"] == [{"text": ["a", "b"], "in": "player"}] and n["edge"] is True
    # rules in the four-word shape
    _trig(root, "toll", {"when": {"entry": "T001/inn", "event": "enter", "who": "player"},
                         "if": [{"var": "player.gold", ">=": 5}],
                         "then": [{"to": "var", "var": "player.gold", "add": -5}, {"to": "flag", "key": "paid_inn"}],
                         "else": [{"to": "narration", "text": "掌柜摇头:钱不够。"}]})
    _trig(root, "poor", {"when": {"var": "player.gold"}, "if": [{"var": "player.gold", "<": 3}], "then": [{"to": "log"}]})
    _trig(root, "here", {"when": {"turn": True}, "if": [{"who": "player", "at": "T001/inn"}, {"flag": "paid_inn"}], "once": True,
                         "then": [{"to": "narration", "text": "楼上有你的房。"}]})
    reg = load_registry(root)
    gold = reg.variables["player.gold"].value
    # not enough gold → ELSE
    reg.variables["player.gold"].value = 2
    sdk._save_json(root / "game" / "player" / "wallet.json", {**_j(root / "game" / "player" / "wallet.json"), "gold": 2})
    reg = load_registry(root)
    ar = sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/inn"}], reg, turn=1)
    by = {t["trigger"]: t for t in ar.triggered}
    assert by["toll"]["branch"] == "else" and by["toll"]["emitted"] == [{"to": "narration", "text": "掌柜摇头:钱不够。"}]
    assert "here" not in by  # at the inn but not paid
    assert by["toll"]["why"][0].startswith("when:player enter") and by["toll"]["why"][1] == "if:player.gold = 2 >= 5 不成立"
    # enough gold → THEN (pays), and the same-turn cascade sees the flag: `here` fires
    sdk._save_json(root / "game" / "player" / "wallet.json", {**_j(root / "game" / "player" / "wallet.json"), "gold": 9})
    reg = load_registry(root)
    ar = sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/main_street"}, {"op": "move_to", "who": "player", "to": "T001/inn"}], reg, turn=2)
    by = {t["trigger"]: t for t in ar.triggered}
    assert by["toll"]["branch"] == "then" and ar.variables["player.gold"] == 4 and ar.variables["flag.paid_inn"] is True
    assert by["here"]["branch"] == "then" and "第 2 层" in by["here"]["why"][-1]
    # edge: `poor` wakes on every gold change but fires only when < 3 turns true
    ar = sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": -2}], load_registry(root), turn=3)  # 4 → 2: fires
    assert [t["trigger"] for t in ar.triggered] == ["poor"]
    ar = sdk.apply(root, [{"op": "add", "var": "player.gold", "delta": -1}], load_registry(root), turn=4)  # 2 → 1: still <3, no repeat
    assert ar.triggered == []
    assert reg.triggers["toll"].to_dict()["else"] and gold is not None
    # validation speaks the four words
    from neonrp.core.registry import RegisterError, register
    with pytest.raises(RegisterError, match="`when`"):
        register(root, "triggers", "bad", {"if": [{"flag": "x"}], "then": [{"to": "log"}]})
    with pytest.raises(RegisterError, match="if\\[0\\]"):
        register(root, "triggers", "bad", {"when": {"turn": True}, "if": [{"var": "player.gold"}], "then": [{"to": "log"}]})


def test_adv_output_shape_parses_lines_ops_options(tmp_path):
    """抛弃 JSON — the narrator writes text + <cot>/<lines>/<ops>/<options>. One message per line,
    dialogue in 「」, ops one per line in the bracket grammar (no brackets), options as choices outside the prose."""
    raw = ("<cot>\n玩家付了钱进旅店,艾琳娜跟着。\n</cot>\n<lines>\n你推开河灯旅店的门。\n「一间房,两个人。」\n掌柜米拉抬眼看了你一下。\n"
           "「八枚一晚。」\n</lines>\n<ops>\nplayer.gold -8\nmove player inn\nmove 艾琳娜 inn\nflag paid_inn\n</ops>\n<options>\n「先付一晚」\n问她有没有见过罗文\n- 转身出去\n</options>")
    out = sdk.parse_solve_output(raw)
    assert out.fmt == "adv" and out.narration.splitlines() == ["你推开河灯旅店的门。", "「一间房,两个人。」", "掌柜米拉抬眼看了你一下。", "「八枚一晚。」"]
    assert out.ops == [{"op": "add", "var": "player.gold", "delta": -8}, {"op": "move_to", "who": "player", "to": "inn"},
                       {"op": "move_to", "who": "艾琳娜", "to": "inn"}, {"op": "flag", "key": "paid_inn"}]
    assert out.options == ["「先付一晚」", "问她有没有见过罗文", "转身出去"] and out.cot.startswith("玩家付了钱")
    # 无变化 · ask · new · positional template op · unterminated block (stream cut)
    out = sdk.parse_solve_output("<lines>\n她没有回答。\n</lines>\n<ops>\n无变化\nask 艾琳娜\nnew quest 找罗文\nvote S01 S02\n</ops>")
    assert out.ops == [{"op": "need", "who": "艾琳娜"}, {"op": "new", "class": "quest", "name": "找罗文"}, {"op": "vote", "args": ["S01", "S02"]}] and out.options == []
    out = sdk.parse_solve_output("<lines>\n雾散了。\n<ops>\ntime.day 4")
    assert out.narration == "雾散了。" and out.ops == [{"op": "set", "var": "time.day", "value": 4}]
    # inline action tags: <tag action> ≡ <tag action>message</tag> — the body stays a line, the tag is an op
    sdk.WAIT_OPS, sdk.FIRE_OPS = set(), set()  # no registry: the model's mark stands (registry case: test_async_mark_registry_decides)
    out = sdk.parse_solve_output("<lines>\n<move player inn>你推开旅店的门。</move>\n「一间房。」\n<player.gold -8>\n<ask 艾琳娜/>\n</lines>")
    assert out.narration.splitlines() == ["你推开旅店的门。", "「一间房。」"] and out.fmt == "adv"
    assert out.ops == [{"op": "move_to", "who": "player", "to": "inn"}, {"op": "add", "var": "player.gold", "delta": -8}, {"op": "need", "who": "艾琳娜"}]
    # bare labels instead of tags (adv4 N5·局2 leaked "ops: / move …" into the prose) are read as the blocks they name
    out = sdk.parse_solve_output("lines:\n你伸手抓住她的手腕。\n「松手。」\nops:\nmove player T001/gate_north\n无变化\noptions:\n「刚才是我急了」\n")
    assert out.fmt == "adv" and out.narration.splitlines() == ["你伸手抓住她的手腕。", "「松手。」"] and out.ops == [{"op": "move_to", "who": "player", "to": "T001/gate_north"}] and out.options == ["「刚才是我急了」"]
    # no <ops> block at all → recorded as adv-noops (the model forgot the block; not the same as 无变化)
    assert sdk.parse_solve_output("<lines>\n只有叙事。\n</lines>").fmt == "adv-noops"
    # JSON is still accepted for the old arms
    assert sdk.parse_solve_output('{"narration": "x", "ops": []}').fmt == "json"
    # the default contract is the ADV one; verify maps positional args onto a template op's fields
    root = _install(tmp_path)
    reg = load_registry(root)
    from neonrp.packs.rpg.contract import contract

    c = contract(root, reg)
    assert "<lines>" in c and "<ops>" in c and "<options>" in c and "输出 JSON" not in c.split("## 输出格式")[1] and "只输出一个 JSON" not in c
    vr = sdk.verify(root, [{"op": "move_to", "args": ["player", "main_street"]}], reg)
    assert vr.accepted and vr.accepted[0]["to"] == "T001/main_street"


def test_adv_request_roll_is_answered_by_the_engine_and_the_prose_continues(tmp_path, fake_adapter):
    """Third form: [tag_ask_request args] is the stream's stop point. The lines before it are final
    (already shown to the player); the engine runs the tool, then asks only for a continuation — never a rewrite.
    Final narration = prefix + continuation; ops = the whole turn's; the roll never lands as state; the number is seeded."""
    root = _install(tmp_path)
    a = fake_adapter([
        "<lines>\n你把骰子摇进杯里。\n「单数我请客。」\n[roll 1d6]\n这一行是盲写的,应当被丢掉。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n再摇一次\n</options>",
        "<lines>\n杯子一翻:三点。\n<player.gold -1>你把输掉的一枚铜币推过去。</player.gold>\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n再来\n「不玩了」\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="我掷一次骰子赌运气", provider=None, turn=3, soul_reports=[])
    assert out["loops"] == 1 and len(a.calls) == 2
    assert out["tool_returns"] and out["tool_returns"][0]["request"] == "roll 1d6" and 1 <= out["tool_returns"][0]["total"] <= 6
    user2 = a.calls[1][1].content
    assert "# 已写出的部分" in user2 and "<lines>\n你把骰子摇进杯里。\n「单数我请客。」\n</lines>" in user2 and "盲写" not in user2
    assert f"<roll 1d6>{out['tool_returns'][0]['total']}</roll>" in user2 and "# 续写" in user2
    assert out["narration"].splitlines() == ["你把骰子摇进杯里。", "「单数我请客。」", "杯子一翻:三点。", "你把输掉的一枚铜币推过去。"]
    assert [o["op"] for o in out["apply"].applied] == ["add"] and out["apply"].variables["player.gold"] == 17 and out["options"] == ["再来", "「不玩了」"]
    # seeded: the same request in the same turn / loop / index rolls the same number; d6 is written back as 1d6
    from neonrp.packs.rpg import tools

    assert tools.roll(root, None, {"op": "roll", "dice": "d6"}, seed="3:0:0")["total"] == out["tool_returns"][0]["total"]
    assert tools.roll(root, None, {"op": "roll", "dice": "2d10+1"}, seed="x")["dice"] == "2d10+1" and tools.roll(root, None, {"op": "roll", "dice": "banana"})["ok"] is False
    # the parser marks requests, not actions, and records the stop point
    p = sdk.parse_solve_output("<lines>\n<move player inn>\n先。\n[ask 艾琳娜]\n后。\n</lines>\n<ops>\n[roll 1d6]\nflag paid\n</ops>")
    assert [(o["op"], o.get("await", False)) for o in p.ops] == [("move_to", False), ("need", True), ("roll", True), ("flag", False)]
    assert p.request_at == 1 and p.prefix == "先。" and p.narration == "先。"


def test_adv_contract_is_i18n_and_reference_style(tmp_path):
    """The format section is short definitions + EXAMPLE OUTPUT, in zh / en / ja, chosen by the world's language;
    the v2 narrative.md (ask_user menus, dice in parentheses) is not used — voice.md is."""
    from neonrp.core.adv import lang_of_text, world_lang
    from neonrp.packs.rpg.contract import contract

    root = _install(tmp_path)
    reg = load_registry(root)
    assert world_lang(root) == "zh"
    zh = contract(root, reg)
    assert "EXAMPLE OUTPUT:" in zh and "<options>" in zh and "ask_user" not in zh and "子代理" not in zh and "第二人称写玩家" in zh
    assert "<cot>" not in zh and "cot:" not in zh  # cot is a pack's choice; rpg does not ask for it
    from neonrp.core.adv import adv_format

    with_cot = adv_format("zh", "无变化", blocks=("cot", "lines", "ops", "options"))
    assert with_cot.index("<cot>") < with_cot.index("<lines>") and "cot:" in with_cot
    # the parser takes blocks in any order, with or without cot
    out = sdk.parse_solve_output("<ops>\nflag x\n</ops>\n<options>\n走\n</options>\n<lines>\n先。\n</lines>")
    assert out.narration == "先。" and out.ops == [{"op": "flag", "key": "x"}] and out.options == ["走"] and out.cot == ""
    # the <ops> lines are generated from the registry: kinds render differently, docs follow the language
    assert "move <谁> <去哪>" in zh and "[ask <谁>]" in zh and "[roll <骰>]" in zh and "player.hp -3" in zh and "无变化" in zh
    en = contract(root, reg, "adv", lang="en")
    assert "## Output format" in en and "move <who> <to>" in en and "[roll <dice>]" in en and "never invent the number" in en and "Writable variables" in en
    ja = contract(root, reg, "adv", lang="ja")
    assert "次のフォーマットを厳守する" in ja and "変化なし" in ja and "[ask <誰>]" in ja and "出目を自分で作らない" in ja
    # a pack.json op with a per-language doc
    from neonrp.core.registry import action_from_dict

    a = action_from_dict("trade", {"kind": "action", "handler": "m:f", "fields": ["good", "qty"], "doc": {"zh": "买卖", "en": "trade goods"}})
    assert a.doc == "买卖" and a.doc_for("en") == "trade goods" and a.doc_for("ja") == "trade goods"  # 10-05 四语: lang → en → zh
    (root / "manifest.json").write_text(json.dumps({"lang": "ja"}), encoding="utf-8")
    assert world_lang(root) == "ja" and lang_of_text("I go to the inn") == "en" and lang_of_text("宿へ行く") == "ja" and lang_of_text("我去旅店") == "zh"
    assert sdk.parse_solve_output("<lines>\nx\n</lines>\n<ops>\n変化なし\n</ops>").ops == []


def test_manifest_prompt_entries_three_layers_and_schema_bound(tmp_path, fake_adapter):
    """条目可增可改,写进 manifest;manifest 可绑 world schema 或 template schema。
    Layers: pack.json prompt < manifest.json prompt < game/meta/prompt.json. Entry `when` = always | post |
    a triggers-IF condition (keyword sugar, at, var, flag …) judged against the registry at pack time."""
    from neonrp.core.adv import entries_for, prompt_spec
    from neonrp.packs.rpg.contract import contract

    root = _install(tmp_path)
    (root / "manifest.json").write_text(json.dumps({"prompt": {
        "voice": "短句。冷。",
        "ops_docs": {"move_to": {"zh": "走:谁 去哪(本镇 id)"}},
        "entries": [
            {"id": "world", "text": "灰雾北境的雾在白天不散。", "when": "always"},
            {"id": "tavern", "text": "河灯旅店:米拉认得每个赊账的人。", "when": {"keyword": ["旅店", "米拉"]}},
            {"id": "gate", "text": "北门守门人只在清晨说话。", "when": {"who": "player", "at": "T001/gate_north"}},
            {"id": "alert", "text": "镇上戒严,夜里不要出门。", "when": {"var": "town.alert", ">=": 3}},
            {"id": "post", "text": "台词短,不解释。", "when": "post"}]}}, ensure_ascii=False), encoding="utf-8")
    sdk._save_json(root / "game" / "meta" / "prompt.json", {"entries": [{"id": "world", "text": None}, {"id": "extra", "text": "今天是集日。", "when": "always"}]})
    spec = prompt_spec(root)
    assert [e["id"] for e in spec["entries"]] == ["tavern", "gate", "alert", "post", "extra"]  # world removed by the play-time layer, extra added
    reg = load_registry(root)
    c = contract(root, reg)
    assert "短句。冷。" in c and "今天是集日。" in c and "走:谁 去哪(本镇 id)" in c and c.rstrip().endswith("台词短,不解释。") and "灰雾北境的雾" not in c
    ents = entries_for(spec, "zh", texts="我去旅店找米拉", reg=reg)
    assert ents["keyword"] == ["河灯旅店:米拉认得每个赊账的人。", "北门守门人只在清晨说话。"]  # keyword hit + the player IS at the gate; alert 0 → no
    ents = entries_for(spec, "zh", texts="随便走走", reg=reg)
    assert ents["keyword"] == ["北门守门人只在清晨说话。"]
    # the matched entries land next to the player's line in the user block
    a = fake_adapter(["<lines>\n你往旅店走。\n</lines>\n<ops>\nmove player inn\n</ops>\n<options>\n进去\n</options>"])
    out = turn_v3.solve_turn(root, user_text="我去旅店找米拉", provider=None, turn=1, soul_reports=[])
    user_msg = a.calls[0][1].content
    assert "# 相关条目\n河灯旅店:米拉认得每个赊账的人。" in user_msg and user_msg.index("# 相关条目") < user_msg.index("# 玩家此刻") and out["apply"].applied


def test_pack_carries_player_profile_relations_recent_events_and_no_dev_notes(tmp_path):
    """Who the player is, the relation to each present soul, a ledger digest of the
    last turns, persona cut at a paragraph, variables one per line; author-facing notes.md never reaches the model."""
    root = _install(tmp_path)
    reg = load_registry(root)
    text = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "## 玩家档案 旅人(剑士)" in text and "在石津镇北门外醒来的失忆旅人" in text and "关系:艾琳娜:信任" in text
    assert "兼容投影" not in text and "demo" not in text  # notes.md is for authors
    assert "石津镇对新来的冒险者并不热情" not in text  # world-facing notes now come as prompt entries, not from notes.md
    persona = text.split("### 艾琳娜 人设\n")[1].split("\n目标:")[0]
    assert len(persona) <= 900 and not persona.endswith("iron") and persona.rstrip().endswith((".", "。", ")", "」"))
    assert "# 变量(一行一个" in text and "- player.gold 18" in text and "# 最近发生的事" not in text  # no ledger yet
    sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/main_street"}, {"op": "add", "var": "player.gold", "delta": -3}], reg, turn=1)
    sdk.apply(root, [{"op": "flag", "key": "paid"}], load_registry(root), turn=2)
    text = sdk.render_pack(sdk.pack(root, registry=load_registry(root)))
    assert "# 最近发生的事(引擎账本,最近 3 回合)\n- 回合 1:旅人 → 主街;player.gold 18→15\n- 回合 2:flag paid" in text
    # the world-facing notes arrive as entries: always one in the contract, keyword ones next to the player's line
    from neonrp.core.adv import entries_for, prompt_spec

    ents = entries_for(prompt_spec(root), "zh", texts="我去碧石镇找罗文", reg=load_registry(root))
    assert ents["always"] == ["石津镇对新来的冒险者并不热情,但会记住肯付账和肯守约的人。"] and ents["keyword"] and "罗文" in ents["keyword"][0]


def test_history_rides_as_chat_turns(tmp_path, fake_adapter):
    """(Yumina 对话历史): earlier player lines and narrator outputs reach the model as alternating
    user / assistant messages (assistant in its own <lines> shape), not as a digest inside the user block."""
    root = _install(tmp_path)
    a = fake_adapter(["<lines>\n她点头。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n走\n</options>"])
    hist = [{"user": "我推开门", "assistant": "一只手抓住了你的手腕。"}, {"user": "我甩开", "assistant": "<lines>\n她松了手。\n</lines>\n<ops>\n无变化\n</ops>"}]
    out = turn_v3.solve_turn(root, user_text="我问她是谁", provider=None, turn=3, soul_reports=[], history=hist)
    msgs = a.calls[0]
    assert [m.role for m in msgs] == ["system", "user", "assistant", "user", "assistant", "user"]
    assert msgs[1].content == "我推开门" and msgs[2].content == "<lines>\n一只手抓住了你的手腕。\n</lines>" and msgs[4].content.startswith("<lines>\n她松了手。")
    assert "# 最近叙事" not in msgs[5].content and "# 玩家此刻\n我问她是谁" in msgs[5].content and out["narration"] == "她点头。"


def test_mentions_examples_and_quote_only_rule(tmp_path, fake_adapter):
    """09-29 follow-ups: (1) someone the player names who is elsewhere is placed for the narrator (E5 C4c);
    (2) manifest / prompt.json `examples` ride as chat turns before the history (Yumina's example role);
    (3) the contract quotes only the 「」 words, first-person actions become third-person narration."""
    root = _install(tmp_path)
    sdk._save_json(root / "game" / "meta" / "prompt.json", {"examples": [{"user": "我推开门", "assistant": "一只手抓住了你的手腕。"}]})
    a = fake_adapter(["<lines>\n你往主街走。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n走\n</options>"])
    out = turn_v3.solve_turn(root, user_text="我去找罗文,顺便问问米拉", provider=None, turn=1, soul_reports=[], history=[{"user": "早", "assistant": "雾。"}])
    msgs = a.calls[0]
    assert [m.role for m in msgs] == ["system", "user", "assistant", "user", "assistant", "user"]
    assert msgs[1].content == "我推开门" and msgs[2].content == "<lines>\n一只手抓住了你的手腕。\n</lines>" and msgs[3].content == "早"
    u = msgs[-1].content
    # 10-01: the named-but-absent people now ride in the understanding block (the player's attempt + what the world says)
    assert "# 本回合的理解" in u and "- 罗文:在 碧石镇(T004)" in u and "- 米拉:不在这里,在 河灯旅店(T001/inn)" in u and u.index("# 本回合的理解") < u.index("# 玩家此刻")
    assert "「」里的话原句照抄" in msgs[0].content and "改成第三人称写成地文" in msgs[0].content and out["narration"] == "你往主街走。"
    # the judgment chain asks once more when Jev came back empty
    from neonrp.packs.rpg import soul_step

    calls = {"n": 0}

    def flaky(state, questions):
        calls["n"] += 1
        if calls["n"] == 1:
            return {}
        from neonrp.core import system_one as s1

        return {"attitude": s1.Answer("choice", "warm", {}, 0.9)}
    j = soul_step.judge_soul(root, "si-elena0001", situation="她看着你", ask=flaky, turn=1)
    assert calls["n"] == 2 and j is not None


def test_cross_town_travel_takes_days_and_follow_is_announced(tmp_path, fake_adapter):
    """逻辑 1(E5 C4b): a journey T001 → T004 is 45 on the map = 3 days; the engine moves the calendar
    itself and tells the narrator as <event travel>; the travel hint says so. A soul whose judgment says follow
    is announced to the narrator as follow=yes so the prose and the landing agree."""
    from neonrp.packs.rpg import travel
    from neonrp.packs.rpg.contract import travel_hints

    root = _install(tmp_path)
    reg = load_registry(root)
    assert travel.route_days(root, "T001", "T004") == 3 and travel.route_days(root, "T001", "T002") == 1 and travel.route_days(root, "T001", "D001") == 0
    assert "路程约 3 天" in travel_hints(root, reg)
    day0 = reg.variables["time.day"].value
    sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg, turn=5)
    reg2 = load_registry(root)
    assert reg2.variables["time.day"].value == day0 + 3 and reg2.player_location == "T004/gate_west"
    packed = sdk.render_pack(sdk.pack(root, registry=reg2))
    assert "<event travel>从石津镇到碧石镇路上走了 3 天,现在是第" in packed
    assert "这条路是road, 途经矮丘林地" in travel_hints(root, reg) and "路上会不会出事由引擎裁定" in travel_hints(root, reg) and "山贼拦路" not in travel_hints(root, reg)
    assert set(travel.encounters(root, "T001", "T004", seed="7")) <= {"路上遇到山贼拦路,要么交买路钱,要么绕远,要么打"} and travel.encounters(root, "T001", "T004", seed="7") == travel.encounters(root, "T001", "T004", seed="7")
    # a named person the world only places in a town is a search, not an appearance
    assert any("具体在镇上哪里没人知道" in m for m in turn_v3._mentions(reg2, "我去找罗文"))
    # the narrator is told who follows
    a = fake_adapter(["<lines>\n她跟上来。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n走\n</options>"])
    turn_v3.solve_turn(root, user_text="走", provider=None, turn=6, soul_reports=[{"iid": "si-elena0001", "name": "艾琳娜", "kind": "speak", "text": "「走。」", "judgment": {"follow": 0.9, "stay": 0.1, "attitude": "warm"}}])
    assert "<say 艾琳娜 attitude=warm follow=yes>「走。」</say>" in a.calls[0][-1].content


def test_keyword_trigger_and_ending(tmp_path):
    """Sandbox exits: beat the boss, die, leave, hit an ending condition, turn cap —
    all triggers; an ending is `emit.to = end`. Keywords fire on what the player said or what was narrated."""
    root = _install(tmp_path)
    _trig(root, "password", {"on": {"keyword": ["芝麻开门", "sesame"], "where": "player"}, "emit": [{"to": "flag", "key": "door_open"}, {"to": "narration", "text": "石门缓缓开了"}]})
    _trig(root, "fog_end", {"on": {"keyword": "雾吞没了镇子", "where": "narration"}, "once": True,
                            "emit": [{"to": "end", "ending": "E02", "title": "雾吞了镇子", "text": "你没有找到罗文。"}]})
    _trig(root, "turn_cap", {"on": {"var": "turn", "when": ">=", "value": 300}, "emit": [{"to": "end", "ending": "E99", "title": "时间到"}]})
    reg = load_registry(root)
    # the player's line carries the keyword; the narration does not carry the ending phrase yet
    ar = sdk.apply(root, [], reg, turn=1, narration="你站在石门前。", player_says="我低声说:芝麻开门")
    assert [t["trigger"] for t in ar.triggered] == ["password"] and ar.variables["flag.door_open"] is True and ar.ended is None
    assert ar.triggered[0]["why"] == ["when:有新文本(player)", "if:「芝麻开门」出现在玩家的话里"]
    # the narrator writes the ending phrase → the ending fires once: marked, flagged, the world hears it next pack
    ar = sdk.apply(root, [], reg, turn=2, narration="风停了。雾吞没了镇子。", player_says="……")
    assert ar.ended == {"id": "E02", "title": "雾吞了镇子", "turn": 2, "trigger": "fog_end"} and ar.variables["flag.ended"] is True
    assert _j(root / "game" / "meta" / "ending.json")["id"] == "E02" and any(e["type"] == "turn.ended" for e in ar.events)
    packed = sdk.render_pack(sdk.pack(root, registry=load_registry(root)))
    assert "<end E02>结局「雾吞了镇子」已触发" in packed and "# 引擎的消息" in packed
    ar = sdk.apply(root, [], reg, turn=3, narration="雾吞没了镇子。", player_says="")
    assert ar.ended is None and ar.triggered == []  # once
    # validation
    from neonrp.core.registry import RegisterError, register
    with pytest.raises(RegisterError, match="text condition"):
        register(root, "triggers", "bad", {"on": {"keyword": ""}, "emit": [{"to": "log"}]})
    with pytest.raises(RegisterError, match="end needs"):
        register(root, "triggers", "bad", {"on": {"flag": "x"}, "emit": [{"to": "end"}]})


def _plot_dir(tmp_path: Path, plot: dict, files: tuple[str, ...] = ("assets/key.png", "assets/crypt.png", "assets/e01.mp4")) -> Path:
    d = tmp_path / "plots" / plot["id"]
    (d / "assets").mkdir(parents=True)
    for f in files:
        (d / f).write_bytes(b"x")
    (d / "plot.json").write_text(json.dumps(plot, ensure_ascii=False), encoding="utf-8")
    return d


_PLOT = {"id": "P01", "title": "雾里的钥匙", "stages": ["起", "承", "合"],
         "entries": {"I900": {"class": "item", "name": "锈钥匙", "parent": "T001/main_street", "assets": {"image": "assets/key.png"}},
                     "T001/crypt": {"class": "place", "name": "地窖", "parent": "T001", "links": ["T001/main_street"], "assets": {"image": "assets/crypt.png"}}},
         "triggers": {"P01.key": {"when": {"text": "narration"}, "if": [{"text": "钥匙"}], "once": True, "then": [{"to": "var", "var": "P01.stage", "set": 1}]},
                      "P01.crypt": {"when": {"entry": "T001/crypt", "event": "enter"}, "then": [{"to": "var", "var": "P01.stage", "set": 2}]},
                      "P01.done": {"when": {"var": "P01.stage"}, "if": [{"var": "P01.stage", ">=": 2}], "then": [{"to": "end", "ending": "E01"}],
                                   "else": [{"to": "narration", "text": "还差一步。"}]}},
         "endings": {"E01": {"title": "雾散", "assets": {"video": "assets/e01.mp4"}}}}


def test_plot_pack_lint_and_install(tmp_path):
    """A plot pack (剧情包): key item + new place + if/else + ending + assets. Lint catches every
    dangling reference and every missing / wrong-kind file; install registers it through the five
    tables and the world then plays it: keyword → stage 1, entering the crypt → stage 2 → ending."""
    from neonrp.packs.rpg import plot as P

    root = _install(tmp_path)
    d = _plot_dir(tmp_path, _PLOT)
    plot = P.load(d)
    assert [str(p) for p in P.lint(plot, d, root)] == []
    assert P.assets(plot, base="game/plots/P01") == [
        {"owner": "I900", "owner_kind": "entry", "kind": "image", "path": "game/plots/P01/assets/key.png"},
        {"owner": "T001/crypt", "owner_kind": "entry", "kind": "image", "path": "game/plots/P01/assets/crypt.png"},
        {"owner": "E01", "owner_kind": "ending", "kind": "video", "path": "game/plots/P01/assets/e01.mp4"}]
    # lint: bad references / files / kinds / unreachable ending / stray file
    bad = json.loads(json.dumps(_PLOT))
    bad["entries"]["I900"]["parent"] = "T001/nowhere"
    bad["entries"]["I900"]["assets"] = {"image": "assets/missing.png", "bgm": "assets/key.png", "hologram": "x"}
    bad["triggers"]["P01.done"]["then"] = [{"to": "end", "ending": "E09"}]
    bad["endings"]["E02"] = {"title": "第二结局"}
    bad["endings"]["E01"] = {"title": "雾散"}  # drops the video → the file becomes a stray
    del bad["triggers"]["P01.key"]
    probs = {p.where: (p.level, p.msg) for p in P.lint(bad, d, root)}
    assert probs["entries.I900.parent"][0] == "error"
    assert probs["entries.I900.assets.image"] == ("warn", "file not found: assets/missing.png")  # 10-16: optional until made
    assert "not a bgm file" in probs["entries.I900.assets.bgm"][1]
    assert "unknown asset kind" in probs["entries.I900.assets.hologram"][1]
    assert "not declared" in probs["triggers.P01.done.then[0]"][1]
    assert probs["endings.E01"] == ("warn", "no trigger emits this ending (unreachable)") and probs["endings.E02"][0] == "warn"
    assert probs["assets/e01.mp4"][0] == "warn"  # the bad plot no longer references it
    assert "stages" not in probs  # P01.crypt still moves the stage var
    (d / "plot.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="lint errors"):
        P.install(root, d)
    (d / "plot.json").write_text(json.dumps(_PLOT, ensure_ascii=False), encoding="utf-8")
    # install → the world knows the item, the place, the stage var, the triggers; the folder travels with it
    info = P.install(root, d)
    assert info["entries"] == ["I900", "T001/crypt"] and info["vars"] == ["P01.stage"] and info["stage_var"] == "P01.stage"
    assert (root / "game" / "plots" / "P01" / "assets" / "key.png").exists() and _j(root / "game" / "meta" / "plots.json")["P01"]["endings"] == ["E01"]
    reg = load_registry(root)
    assert reg.entries["I900"].props["name"] == "锈钥匙" and reg.entries["T001/crypt"].cls == "place" and reg.variables["P01.stage"].value == 0
    tm = {n["id"]: n for n in place_tree.level_doc(root, "T001")["nodes"]}
    assert tm["crypt"]["links"] == ["main_street"] and "crypt" in tm["main_street"]["links"]  # the RPG map learned the place
    # play it: the narrator mentions the key → stage 1; the player walks into the crypt → stage 2 → ending E01
    ar = sdk.apply(root, [], reg, turn=1, narration="桌上有一把锈钥匙。")
    assert ar.variables["P01.stage"] == 1 and ar.ended is None
    ar = sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/crypt"}], load_registry(root), turn=2)
    assert ar.ended and ar.ended["id"] == "E01" and ar.variables["P01.stage"] == 2
    assert _j(root / "game" / "meta" / "plot_vars.json")["P01"]["stage"] == 2


def test_adjudicate_light_heavy_and_seeded_dice():
    from neonrp.packs.rpg import soul_step
    A = s1.Answer
    none = soul_step.adjudicate({"stakes": A("choice", "none", {}, 0.9), "willingness": A("noul", 0.9, {}, 0.9)})
    assert none["outcome"] is None
    # the two-noul classifier (E6 run1 fix): asked? costly?
    two = soul_step.adjudicate({"asked": A("noul", 0.9, {}, 0.9), "costly": A("noul", 0.1, {}, 0.9), "willingness": A("noul", 0.8, {}, 0.9)})
    assert two["stakes"] == "light" and two["outcome"] == "comply" and two["asked"] == 0.9
    assert soul_step.adjudicate({"asked": A("noul", 0.9, {}, 0.9), "costly": A("noul", 0.8, {}, 0.9), "willingness": A("noul", 0.5, {}, 0.9)}, seed="s")["stakes"] == "heavy"
    assert soul_step.adjudicate({"asked": A("noul", 0.2, {}, 0.9), "costly": A("noul", 0.9, {}, 0.9), "willingness": A("noul", 0.5, {}, 0.9)})["stakes"] == "none"
    light_yes = soul_step.adjudicate({"stakes": A("choice", "light", {}, 0.9), "willingness": A("noul", 0.7, {}, 0.9)}, trust=0)
    assert light_yes["outcome"] == "comply" and light_yes["roll"] is None and light_yes["adjusted"] == 0.7
    light_no = soul_step.adjudicate({"stakes": A("choice", "light", {}, 0.9), "willingness": A("noul", 0.2, {}, 0.9)}, trust=-2)
    assert light_no["outcome"] == "refuse" and light_no["adjusted"] == 0.14
    heavy = soul_step.adjudicate({"stakes": A("choice", "heavy", {}, 0.9), "willingness": A("noul", 0.4, {}, 0.9)}, trust=2, seed="elena:3:x")
    assert heavy["target"] == 46 and heavy["roll"] is not None and heavy["tier"] and heavy["outcome"] in ("comply", "partial", "refuse")
    assert soul_step.adjudicate({"stakes": A("choice", "heavy", {}, 0.9), "willingness": A("noul", 0.4, {}, 0.9)}, trust=2, seed="elena:3:x") == heavy, "same seed → same roll (replay)"
    rolls = {soul_step.adjudicate({"stakes": A("choice", "heavy", {}, 0.9), "willingness": A("noul", 0.5, {}, 0.9)}, seed=f"elena:{t}:x")["roll"] for t in range(12)}
    assert len(rolls) > 3, "different turns → different rolls"
    assert soul_step.adjudicate({"stakes": A("choice", "heavy", {}, 0.9), "willingness": A("noul", 0.4, {}, 0.9)}, dice=False)["roll"] is None


def test_soul_step_bakes_the_decision_into_speech(tmp_path, monkeypatch):
    from neonrp.packs.rpg import soul_step

    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(lambda state, qs: {"attitude": s1.Answer("choice", "refuse", {}, 0.9), "register": s1.Answer("choice", "cold", {}, 0.8),
                                       "urgency": s1.Answer("choice", "0", {}, 0.9), "want_move": s1.Answer("noul", 0.1, {}, 0.9),
                                       "free": s1.Answer("noul", 0.0, {}, 0.9), "asked": s1.Answer("noul", 0.95, {}, 0.9), "costly": s1.Answer("noul", 0.2, {}, 0.9),
                                       "willingness": s1.Answer("noul", 0.2, {}, 0.9)})
    seen = {}

    def fake_ask(root_, iid, q, *, asker="", **_kw):
        seen["q"] = q
        return {"ok": True, "answer": "「不。」", "name": "艾琳娜"}

    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", fake_ask)
    try:
        r = soul_step.soul_step(root, "si-elena0001", situation="玩家:把你的短剑借我", depth="speak")
    finally:
        s1.install_stub(None)
    d = r["judgment"]["decision"]
    assert d["stakes"] == "light" and d["outcome"] == "refuse" and d["roll"] is None
    assert "你的决定是:拒绝" in seen["q"] and "意愿" not in seen["q"] and "骰" not in seen["q"] and "怎么说是你的" in seen["q"]


# ── the road as referee (逻辑 1 closed loop): stop → respond + [roll 1d6] → resolve → arrive ─────────────

def _force_bandits(root: Path) -> None:
    """World override: the bandit road always stops the party (the referee is seeded; tests want the stop for sure)."""
    wm = root / "game" / "world" / "world_map.json"
    d = _j(wm)
    d["travel"] = {"hazards": {"bandit_risk": {"p": 1.0, "dc": 4}}}
    wm.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _at_gate(root: Path) -> None:
    from neonrp.core.turn_settlement import _apply_player_move

    if load_registry(root).player_location != "T001/gate_north":
        assert _apply_player_move(root, "T001/gate_north")


def test_journey_referee_stops_the_party_then_a_roll_settles_it(tmp_path):
    """T001 → T004 with bandits certain: the validator refuses the arrival and stamps the stop (calendar moved to the stop's
    day, <event travel> queued); asking again in the same turn is the same refusal without moving the calendar twice;
    the next turn's move is blocked until a die is thrown; the roll tool settles the stop (pass or pay days); the move
    then lands the player at the west gate with the remaining days on the calendar."""
    from neonrp.packs.rpg import tools, travel

    root = _install(tmp_path)
    _force_bandits(root)
    _at_gate(root)
    reg = load_registry(root)
    reg.variables["turn"].value = 5
    day0 = reg.variables["time.day"].value
    p = travel.plan(root, "T001", "T004", seed="5")
    assert p["days"] == 3 and [s["tag"] for s in p["stops"]] == ["bandit_risk"] and 1 <= p["stops"][0]["day"] <= 3
    stop_day = p["stops"][0]["day"]
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg)
    assert vr.accepted == [] and len(vr.refused) == 1
    r = vr.refused[0]
    assert r.fixable and r.field == "to" and f"走到第 {stop_day} 天,路上遇到山贼拦路" in r.why and "不要写抵达" in r.why and "不要写任何 move" in r.why
    j = travel.journey(root)
    assert j and j["pending"]["tag"] == "bandit_risk" and j["day"] == stop_day and j["stopped_turn"] == 5
    assert load_registry(root).variables["time.day"].value == day0 + stop_day
    # the same turn asks again (re-proposal): same answer, the calendar does not move twice
    vr2 = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg)
    assert vr2.refused[0].why == r.why and load_registry(root).variables["time.day"].value == day0 + stop_day
    # a soul cannot outrun the stopped party
    vr3 = sdk.verify(root, [{"op": "move_to", "who": "si-elena0001", "to": "T004/gate_west"}], reg)
    assert vr3.refused and not vr3.refused[0].fixable and "还在路上" in vr3.refused[0].why
    # the narrator hears it next turn: the event and the hint
    reg2 = load_registry(root)
    packed = sdk.render_pack(sdk.pack(root, registry=reg2))
    assert f"<event travel>从石津镇去碧石镇的路上,第 {stop_day} 天(现在是第 {day0 + stop_day} 天):路上遇到山贼拦路" in packed
    from neonrp.packs.rpg.contract import travel_hints
    h = travel_hints(root, reg2)
    assert f"\n- 在去 T004(碧石镇)的路上,第 {stop_day}/3 天,路上遇到山贼拦路" in h and "由你裁:对面动手或玩家动手 → 写 [combat" in h and "路程约 3 天" not in h
    # next turn, arriving is still blocked until the stop is settled
    reg2.variables["turn"].value = 6
    vr4 = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg2)
    assert vr4.refused and vr4.refused[0].fixable and "路上的事还没了结" in vr4.refused[0].why and "[combat]" in vr4.refused[0].why and "[referee" in vr4.refused[0].why
    # the die settles it: the tool's reply carries the verdict; the journey is no longer pending
    out = tools.roll(root, reg2, {"op": "roll", "dice": "1d6"}, seed="6:0:0")
    passed = out["total"] >= 4
    assert out["travel"] and (("过了(≥4):山贼退了" in out["text"]) if passed else ("没过(<4):没占到便宜" in out["text"]))
    j2 = travel.journey(root)
    assert j2["pending"] is None and j2["log"][0]["passed"] is passed and j2["day"] == stop_day + (0 if passed else 1)
    left = max(0, 3 - j2["day"])
    assert (f"还剩 {left} 天" in out["text"]) if left else ("今天就能到" in out["text"])
    assert f"\n- 在去 T004(碧石镇)的路上,第 {j2['day']}/3 天,路上的事已了结,还剩 {left} 天" in travel_hints(root, load_registry(root))
    # a second die in the same journey is just a die (nothing pending)
    assert tools.roll(root, reg2, {"op": "roll", "dice": "1d6"}, seed="6:0:1")["travel"] is None
    # now the move goes through and the calendar walks the rest
    reg3 = load_registry(root)
    reg3.variables["turn"].value = 7
    vr5 = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg3)
    assert vr5.refused == [] and vr5.accepted[0]["to"] == "T004/gate_west"
    sdk.apply(root, vr5.accepted, reg3, turn=7)
    reg4 = load_registry(root)
    assert reg4.player_location == "T004/gate_west" and travel.journey(root) is None
    assert reg4.variables["time.day"].value == day0 + 3 + (0 if passed else 1)
    packed = sdk.render_pack(sdk.pack(root, registry=reg4))
    assert ("到了碧石镇" in packed) and ("<event travel>" in packed)


def test_journey_stop_re_proposes_the_turn_and_keeps_the_player_on_the_road(tmp_path, fake_adapter):
    """Whole turn: the narrator writes the arrival; the road refuses; the re-proposal is told to stop at the ambush and
    write no move; the player stays at the gate, the calendar has moved to the stop's day."""
    from neonrp.packs.rpg import travel

    root = _install(tmp_path)
    _force_bandits(root)
    _at_gate(root)
    a = fake_adapter([
        "<lines>\n三天后你们到了碧石镇西门。\n</lines>\n<ops>\nmove player T004/gate_west\nmove 艾琳娜 T004/gate_west\n</ops>\n<options>\n进城\n</options>",
        "<lines>\n走出半个时辰,矮丘林地里横着一棵砍倒的树,二十来个人从林子里走出来。\n「留下买路钱。」\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n拔剑\n交钱\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="我们继续赶路,往碧石镇去。", provider=None, turn=5, soul_reports=[])
    assert out["loops"] == 1 and len(a.calls) == 2
    u2 = a.calls[1][1].content
    assert "<refused move_to to>走到第" in u2 and "不要写抵达" in u2
    assert out["narration"].startswith("走出半个时辰") and out["apply"].applied == []
    reg = load_registry(root)
    j = travel.journey(root)
    assert reg.player_location == "road_T001_T004" and j and j["pending"]["tag"] == "bandit_risk" and reg.variables["time.day"].value == 1 + j["day"]
    assert reg.entries["si-elena0001"].parent == "road_T001_T004", "the companion left town with the player"
    assert j["origin"] == "T001/gate_north" and reg.entries["road_T001_T004"].cls == "road"
    assert "## 在路上 驿路(石津镇→碧石镇):第" in sdk.render_pack(sdk.pack(root, registry=reg))
    # next turn, a fight is the narrator's call ([combat], D-20261018): the road stop's foes come from the hazards table
    b = fake_adapter(["<lines>\n你拔剑迎上去。\n[combat]山贼拦路,你拔剑迎上去[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
                      "<lines>\n[dice 1d20+2 vs 11]先攻[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
                      "<lines>\n你先动。\n</lines>\n<ops>\nfoe.bandit1.hp -3\n</ops>",
                      "<lines>\n山贼退了一步。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n继续\n</options>"])
    out2 = turn_v3.solve_turn(root, user_text="山贼拦路,我拔剑迎上去。", provider=None, turn=6, soul_reports=[])
    from neonrp.core import modes
    from neonrp.packs.rpg import combat
    assert "# 战斗裁判" not in b.calls[0][0].content and "# 战斗裁判" in b.calls[1][0].content
    assert modes.read_mode(root) is None and combat.standing(combat.read(root)) and travel.journey(root)["pending"] is not None, "the fight settles the stop, not the die"
    assert out2["tool_returns"][0]["request"].startswith("combat") and out2["tool_returns"][0]["answers"][0]["request"] == "dice 1d20+2 vs 11"
    combat.write(root, None)
    # …and anything but a fight is the narrator's call: it asks [referee …] itself; the ruling settles the stop
    c = fake_adapter(["<lines>\n你把钱袋解下来。\n[referee 玩家交买路钱换放行]\n</lines>\n<ops>\n无变化\n</ops>",
                      '{"ruling": "check_required", "check": {"type": "Persuasion", "attribute": "CHA", "dc": 1}, '
                      '"consequences": {"on_success": "山贼收了钱放行", "on_fail": "山贼翻脸"}, "narrative_hint": "头目掂了掂钱袋。"}',
                      "<lines>\n头目掂了掂钱袋。\n</lines>\n<ops>\nplayer.gold -4\n</ops>\n<options>\n继续赶路\n</options>"])
    out3 = turn_v3.solve_turn(root, user_text="我交买路钱。", provider=None, turn=7, soul_reports=[])
    assert len(c.calls) == 3 and not any(s_["actor"] == "gate" and s_.get("ruled") for s_ in out3["spans"])
    assert "三种调用场景" in c.calls[1][0].content and "# 待裁定\n玩家交买路钱换放行" in c.calls[1][1].content and "# 处境数值\n路上:去 T004" in c.calls[1][1].content
    u = c.calls[2][1].content
    assert "<referee 玩家交买路钱换放行>裁定:check_required" in u and "vs DC 1 → 过" in u and "结果:山贼收了钱放行" in u and "路上的事:过了" in u
    assert travel.journey(root)["pending"] is None and travel.journey(root)["log"][-1]["passed"] is True
    assert out3["tool_returns"][0]["request"].startswith("referee ") and out3["tool_returns"][0]["ruling"]["check"]["attribute"] == "CHA"


def test_journey_without_stops_arrives_in_one_move(tmp_path):
    """The patrolled road T001 → T002 never stops anyone: one move, one day on the calendar, no journey left behind."""
    from neonrp.packs.rpg import travel

    root = _install(tmp_path)
    _at_gate(root)
    reg = load_registry(root)
    reg.variables["turn"].value = 3
    assert travel.plan(root, "T001", "T002", seed="3")["stops"] == []
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T002"}], reg)
    assert vr.refused == []
    sdk.apply(root, vr.accepted, reg, turn=3)
    reg2 = load_registry(root)
    assert reg2.player_location.startswith("T002/") and reg2.variables["time.day"].value == 2 and travel.journey(root) is None


# ── 09-30 slice 1: the pack seats v2's sub-agents read from (rules · character sheet · quests · dungeons) ──────────

def test_pack_seats_rules_sheet_quests_dungeons(tmp_path):
    """The v3 pack was hollow (2.3 KB) — rules, attributes / gear / bag, the guild board and the dungeon never reached
    the model. The rpg loader now seats them: rules as a text for the mode layers (not the narrator), a one-line character
    sheet, quests per town, dungeons + rooms as packed classes with the layout graph as the map."""
    root = _install(tmp_path)
    reg = load_registry(root)
    assert {c: len(reg.of_class(c)) for c in ("job", "dungeon", "room")} == {"job": 6, "dungeon": 1, "room": 4}
    assert "先攻" in reg.texts["rules"] and "逃跑" in reg.texts["rules"]
    pk = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "先攻" not in pk, "rules text is for the referee / combat layers, not the narrator's base pack"
    assert "属性 STR5 DEX7 INT5 VIT6 CHA5;技能 快斩" in pk and "武器 短剑(atk 4,伤 3);护甲 旧皮短甲(def 2);背包 旅行黑麦面包×2" in pk
    assert "## 本镇委托\n- T001/Q001 雾中失踪者(阶1,available):码头区有人在雾里失踪。找回遗物或线索。;赏金 25 金" in pk
    assert "T004/" not in pk.split("## 本镇委托")[1].split("##")[0], "only this town's board"
    assert "- D001 苔墓地穴:潮湿古墓/苔藓/低语;危险 3;未探明;房间:D001/D001_R001" in pk
    from neonrp.packs.rpg.contract import travel_hints
    assert "- 去 D001(苔墓地穴):当天可到,写 move player D001 就落在入口 潮门前室(D001/D001_R001);潮湿古墓/苔藓/低语;危险 3" in travel_hints(root, reg)
    assert reg.entries["player"].props["attributes"]["dex"] == 7 and reg.entries["player"].props["weapon"]["atk"] == 4
    # into the dungeon: "去 D001" lands in the entry room; rooms move along the layout graph only
    reg.variables["turn"].value = 2
    _no_hazards(root)
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "D001"}], reg)
    assert vr.refused == [] and vr.accepted[0]["to"] == "D001/D001_R001" and vr.accepted[0]["_clamped"]["why"].startswith("进入 苔墓地穴,落在入口 潮门前室")
    sdk.apply(root, vr.accepted, reg, turn=2)
    reg2 = load_registry(root)
    assert reg2.player_location == "D001/D001_R001" and [e.id for e in reg2.exits("D001/D001_R001")] == ["D001/D001_R002"]
    pk2 = sdk.render_pack(sdk.pack(root, registry=reg2))
    assert "## 此处 D001/D001_R001 潮门前室(entry)\n石门半掩，潮气涌出。墙角有被拖拽的痕迹。\n可做:可调查拖痕、可点燃火把降低雾影响\n此刻在场的敌人:无\n出口:D001/D001_R002(苔廊)" in pk2
    assert "## 地穴 D001 苔墓地穴" not in pk2 and "苔墓地穴:潮湿古墓" in pk2  # the chain shows the dungeon once, as a heading
    assert "## 本镇地点 id" not in pk2
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "D001/D001_R004"}], reg2)
    assert vr.refused and "不相邻" in vr.refused[0].why
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "苔廊"}], reg2)
    assert vr.refused == [] and vr.accepted[0]["to"] == "D001/D001_R002"


# ── 09-30 slice 2: mode layers = v2 sub-agents (their own system.md, packed reads, ops, dice by the engine) ─────────

def test_mode_layer_system_is_the_subagents_prompt_with_v3_format(tmp_path):
    """The combat layer's system prompt is agents/combat-referee/system.md with v2's read / task / JSON / dice-skill
    sections stripped, plus the ADV format with only the layer's ops; its reads block carries game/rules."""
    from neonrp.core import modes

    root = _install(tmp_path)
    reg = load_registry(root)
    sysm = modes.layer_system(root, reg, "combat", "zh")
    assert "# 战斗裁判\n" in sysm and "先攻" in sysm and "AI 行为规则" in sysm, "the sub-agent's own knowledge stays"
    for gone in ("读写边界", "PATCH_PLAN", "Skill(skill=\"dice\")", "禁止使用 glob", "No menus", "语言匹配"):
        assert gone not in sysm, gone
    assert "[dice <骰> <vs>]" in sysm and "end_combat" not in sysm and "[combat" not in sysm.split("## 输出格式")[1], "no nested call; the layer's ops only"
    assert "move <谁> <去哪>" not in sysm.split("## 输出格式")[1]
    spec = modes.spec_of(root, "combat")
    assert "# 规则:rules" in modes.reads_block(root, reg, spec) and "d20 + Dex" in modes.reads_block(root, reg, spec)
    ref = modes.layer_system(root, reg, "referee", "zh")
    assert "三种调用场景" in ref and "所有输出都是 JSON" in ref and "<lines>" not in ref, "a one-shot ruling layer keeps its JSON contract"
    # the narrator's base contract documents the switch tag and the requests
    from neonrp.packs.rpg.contract import contract
    base = contract(root, reg, "adv")
    assert "[combat <roster> <note>]" in base and "[referee <question>]" in base.replace("[referee <问题>]", "[referee <question>]") or "[referee" in base
    assert "[dice <骰> <vs>]" in base


def test_combat_is_a_one_shot_call_and_the_narrator_goes_on_from_it(tmp_path, fake_adapter):
    """D-20261018: the narrator writes [combat roster]what each one does[/combat] → the combat layer (its own prompt,
    the packed rules, the foes) writes this exchange once, its [dice] thrown by the engine, its hp ops landing with the
    beat; the narrator goes on from the <combat> reply with its own contract. The fight is world data between beats,
    never a mode: the next beat is an ordinary Resolve that calls again; when no foe stands the engine ends it."""
    from neonrp.core import modes, orchestration
    from neonrp.packs.rpg import combat

    root = _install(tmp_path)
    _force_bandits(root)  # 10-01: [combat] needs grounds — a real road stop, not bandits invented at the gate
    _at_gate(root)
    reg0 = load_registry(root)
    reg0.variables["turn"].value = 5
    sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg0)
    a = fake_adapter([
        "<lines>\n你把手按上剑柄。\n[combat 山贼×1]山贼横在路中间,你拔剑砍向他[/combat]\n这一行是盲写的。\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n先攻。\n[dice 1d20+2 vs 11]玩家先攻:DEX+2 对山贼 DEF 11[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n你先动,剑走中门。\n山贼的刀擦过你的前臂。\n</lines>\n<ops>\nfoe.bandit1.hp -5\nplayer.hp -2\n</ops>",
        "<lines>\n他退了半步,刀还举着。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n再砍\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="我拔剑砍过去。", provider=None, turn=6, soul_reports=[])
    assert len(a.calls) == 4
    sys1, sys2, sys3, sys4 = (c[0].content for c in a.calls)
    assert "# 战斗裁判" not in sys1 and "# 战斗裁判" in sys2 and sys3 == sys2 and sys4 == sys1, "the layer's prompt is the call's, not the beat's"
    u2 = a.calls[1][1].content
    assert "# 战斗状态(第 1 轮;交接:山贼横在路中间,你拔剑砍向他)" in u2 and "- foe.bandit1" in u2 and "# 规则:rules" in u2
    assert "<dice 1d20+2 vs 11>" in a.calls[2][1].content
    u4 = a.calls[3][1].content
    assert "<lines>\n你把手按上剑柄。\n</lines>" in u4 and "<combat 山贼×1" in u4 and "你先动,剑走中门。" in u4, "the narrator goes on from the reply"
    assert out["narration"].startswith("你把手按上剑柄。\n他退了半步") and "盲写" not in out["narration"]
    assert out["tool_returns"][0]["request"].startswith("combat") and out["tool_returns"][0]["answers"][0]["request"].startswith("dice 1d20+2")
    reg2 = load_registry(root)
    assert reg2.variables["player.hp"].value == 22 and reg2.variables["foe.bandit1.hp"].value == 3
    assert modes.read_mode(root) is None and orchestration.current(root, reg2) == orchestration.RESOLVE
    assert combat.standing(combat.read(root)) == {"bandit1": combat.read(root)["foes"]["bandit1"]}
    # the next beat: an ordinary Resolve on the narrator's contract that calls again (round 2); the foe falls → over
    b = fake_adapter([
        "<lines>\n你再砍。\n[combat]再砍一刀[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n[dice 1d20+2 vs 11]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n剑落下,山贼倒了。\n</lines>\n<ops>\nfoe.bandit1.hp -3\n</ops>",
        "<lines>\n路空了。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n继续赶路\n</options>",
    ])
    turn_v3.solve_turn(root, user_text="再砍。", provider=None, turn=7, soul_reports=[])
    assert "# 战斗裁判" not in b.calls[0][0].content and "# 战斗状态(第 2 轮" in b.calls[1][1].content
    assert combat.read(root) is None, "no foe stands: the fight is over, nobody wrote end_combat"
    reg3 = load_registry(root)
    assert "foe.bandit1.hp" not in reg3.variables
    assert "<event combat>战斗赢了" in sdk.render_pack(sdk.pack(root, registry=reg3))


def test_referee_request_is_a_subagent_call_with_engine_dice(tmp_path, fake_adapter):
    """[referee 问题] runs the rules-referee layer once (its own prompt, JSON ruling), the engine throws the check the
    ruling asks for from the player's attributes, and the narrator continues from the <referee> reply."""
    root = _install(tmp_path)
    a = fake_adapter([
        "<lines>\n你压低声音跟守门人讨价还价。\n[referee 玩家想说服守门人免掉入城税]\n</lines>\n<ops>\n无变化\n</ops>",
        '{"ruling_type": "skill_check", "action": "说服守门人", "ruling": "check_required", "check": {"type": "Persuasion", "formula": "d20 + CHA_mod", "dc": 12},'
        ' "consequences": {"on_success": "守门人挥手放行", "on_fail": "守门人加价到两枚"}, "narrative_hint": "他看了你的靴子一眼。"}',
        "<lines>\n守门人看了你的靴子一眼。\n</lines>\n<ops>\n无变化\n</ops>",
    ])
    out = turn_v3.solve_turn(root, user_text="我跟守门人讨价还价。", provider=None, turn=3, soul_reports=[])
    assert len(a.calls) == 3
    ref_sys, ref_user = a.calls[1][0].content, a.calls[1][1].content
    assert "三种调用场景" in ref_sys and "<lines>" not in ref_sys and "# 待裁定\n玩家想说服守门人免掉入城税" in ref_user and "d20 + Dex" in ref_user
    tr = out["tool_returns"][0]
    assert tr["request"].startswith("referee") and tr["ok"] and "裁定:check_required" in tr["text"] and "vs DC 12 →" in tr["text"]
    assert tr["ruling"]["check"]["mod"] == 0 and 1 <= tr["ruling"]["check"]["roll"] <= 20  # CHA 5 → +0
    assert ("结果:守门人挥手放行" in tr["text"]) == tr["ruling"]["check"]["result"] == "success" or "结果:" in tr["text"]
    assert "提示:他看了你的靴子一眼。" in tr["text"]
    assert "<referee 玩家想说服守门人免掉入城税>裁定:check_required" in a.calls[2][1].content


def test_dungeon_room_entry_rolls_its_encounter_table_into_the_room(tmp_path):
    """Landing in a room with an encounter table: seeded roll; a hit puts the foes in the room (world data, no mode)
    and tells the narrator as an <event>; the next beats decide how to meet them. A cleared room never rolls."""
    from neonrp.core import modes
    from neonrp.packs.rpg import combat

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    # the boss room's table is chance 1.0 → always
    for r in reg.of_class("room"):
        if r.id == "D001/D001_R004":
            assert r.props["encounters"][0]["chance"] == 1.0
    # walk in through the entry and the hall (adjacency), then into the inner shrine
    from neonrp.core.turn_settlement import _apply_player_move
    assert _apply_player_move(root, "D001/D001_R003")
    reg = load_registry(root)
    reg.variables["turn"].value = 9
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "D001/D001_R002"}], reg)
    assert vr.refused == []
    sdk.apply(root, vr.accepted, reg, turn=9)
    reg = load_registry(root)
    reg.variables["turn"].value = 10
    combat.write(root, None)  # whatever the hall rolled (0.4), clear it for the deterministic room
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "D001/D001_R004"}], reg)
    assert vr.refused == []
    sdk.apply(root, vr.accepted, reg, turn=10)
    m = combat.read(root)
    assert modes.read_mode(root) is None and m and m["note"].startswith("进入棺语内殿就遇上:低语棺×1") and m["at"] == "D001/D001_R004"
    foes = m["foes"]
    assert list(foes) == ["coffin1"] and foes["coffin1"]["hp"] == 20
    packed = sdk.render_pack(sdk.pack(root, registry=load_registry(root)))
    assert "<event encounter>一进棺语内殿就遇上了 低语棺。" in packed


def test_dungeon_room_uses_the_dungeon_agents_prompt_for_the_turn(tmp_path, fake_adapter):
    """A place-keyed layer: standing in a dungeon room, the turn's whole system prompt is agents/dungeon-agent/system.md
    (stripped of v2 protocol) with all narrator ops and <combat> still available; nothing is written to run_state."""
    from neonrp.core import modes
    from neonrp.core.turn_settlement import _apply_player_move

    root = _install(tmp_path)
    _no_hazards(root)
    assert _apply_player_move(root, "D001/D001_R001")
    a = fake_adapter(["<lines>\n潮气涌出来。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n调查拖痕\n</options>"])
    turn_v3.solve_turn(root, user_text="我举灯看四周。", provider=None, turn=4, soul_reports=[])
    sysm = a.calls[0][0].content
    assert "# 地穴主持" in sysm and "dungeon" in sysm.lower() and "读写边界" not in sysm and "[combat 山贼×5" in sysm and "move <谁> <去哪>" in sysm
    assert "# 规则:rules" in a.calls[0][1].content and "## 此处 D001/D001_R001 潮门前室(entry)" in a.calls[0][1].content
    assert modes.read_mode(root) is None
    assert _apply_player_move(root, "T001/gate_north")
    b = fake_adapter(["<lines>\n雾。\n</lines>\n<ops>\n无变化\n</ops>"])
    turn_v3.solve_turn(root, user_text="看。", provider=None, turn=5, soul_reports=[])
    assert "# 地穴主持" not in b.calls[0][0].content


def test_combat_layer_without_a_die_is_asked_once_more(tmp_path, fake_adapter):
    """地穴冒烟 10-01: combat narrated hits with no dice and no hp ops. The combat layer's call must carry at least one
    [dice …] request; a reply without one is asked again once, and only the second reply counts."""
    from neonrp.packs.rpg import combat

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    combat.write(root, {**combat.spawn(root, reg, note="一只泥苔鼠", turn=3), "at": reg.player_location, "note": "一只泥苔鼠"})
    a = fake_adapter([
        "<lines>\n你出手。\n[combat]短剑横削[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n你侧身一让,短剑横削出去,咬实了。\n</lines>\n<ops>\nfoe.rat1.hp -5\n</ops>",
        "<lines>\n你侧身一让。\n[dice 1d20+2 vs 9]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n剑锋咬实了。\n</lines>\n<ops>\nfoe.rat1.hp -3\n</ops>",
        "<lines>\n泥苔鼠吱了一声。\n</lines>\n<ops>\n无变化\n</ops>",
    ])
    out = turn_v3.solve_turn(root, user_text="继续。", provider=None, turn=4, soul_reports=[])
    assert len(a.calls) == 5 and "这一轮没有任何 [dice …] 检定" in a.calls[2][1].content
    tr = out["tool_returns"][0]
    assert tr["answers"][0]["request"].startswith("dice 1d20+2 vs 9") and load_registry(root).variables["foe.rat1.hp"].value == 1, "the first reply's -5 never landed"


def test_fulllog_1001_bugs(tmp_path, fake_adapter):
    """fulllog-1001 (10-01): (a) [dice 1d6+3] without vs was refused as 'missing field vs' — damage never landed and the
    layer re-narrated the same stab for five rounds; (b) the referee's own 'CHA_mod(+5)' was trusted over the sheet;
    (c) 「四五名山贼」spawned one bandit; (d) a passed hit with no hp op sailed through."""
    from neonrp.packs.rpg import combat, referee

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    # (a)
    vr = sdk.verify(root, [{"op": "dice", "args": ["1d6+3"], "reason": "伤害"}], reg)
    assert vr.refused == [] and vr.accepted[0]["dice"] == "1d6+3" and "vs" not in vr.accepted[0]
    # (c)
    st = combat.spawn(root, reg, note="四五名山贼从坡上压下来;领队左眼蒙布", turn=3)
    assert len(st["foes"]) == 5 and all(f["kind"] == "bandit" for f in st["foes"].values())
    assert len(combat.spawn(root, reg, note="三个山贼", turn=3)["foes"]) == 3 and len(combat.spawn(root, reg, note="山贼×2 和一只雾牙狼", turn=3)["foes"]) == 3
    # (b): CHA 5 → +0 whatever the referee wrote; a stated situational modifier is honoured
    a = fake_adapter(['{"ruling": "check_required", "check": {"type": "Intimidation", "formula": "d20 + CHA_mod(+5) + 情境修正(-2)", "dc": 17}, "consequences": {"on_fail": "x"}}'])
    r = referee.ruling(root, reg, {"op": "referee", "question": "恐吓"}, None, seed="9")
    assert r["ok"] and r["ruling"]["check"]["mod"] == -2 and r["ruling"]["check"]["total"] == r["ruling"]["check"]["roll"] - 2
    # (d): a passed hit without any hp op is asked once more from the same stop
    combat.write(root, {**combat.spawn(root, reg, note="两个山贼", turn=4), "at": reg.player_location, "note": "两个山贼"})
    b = fake_adapter([
        "<lines>\n你出手。\n[combat]捅进去[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n你捅进去。\n[dice 1d20+4 vs 11]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n刃没入一半,实了。\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n[dice 1d6+3]伤害[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n他肩塌下去。\n</lines>\n<ops>\nfoe.bandit1.hp -6\n</ops>",
        "<lines>\n另一个往后缩。\n</lines>\n<ops>\n无变化\n</ops>",
    ])
    out = turn_v3.solve_turn(root, user_text="继续打。", provider=None, turn=5, soul_reports=[])
    ans = out["tool_returns"][0]["answers"]
    if ans[0].get("passed"):
        assert any("却没有任何 hp 变化" in c[1].content for c in b.calls[3:4]) and ans[1]["request"].startswith("dice 1d6+3")
        assert load_registry(root).variables["foe.bandit1.hp"].value == 2
    else:  # the seeded d20 missed: no damage demanded
        assert len(ans) == 1 and not any("却没有任何 hp 变化" in c[1].content for c in b.calls)


def test_journey_stop_refuses_prose_that_walks_past_the_stop_day(tmp_path, fake_adapter):
    """fulllog-1001 C4a: the referee stamped day 1 (bandits), the narrator wrote three days and 「第三天午后」an ambush.
    The rpg post_solve rule refuses once: write up to the stop day only."""
    from neonrp.packs.rpg import travel

    root = _install(tmp_path)
    _force_bandits(root)
    _at_gate(root)
    a = fake_adapter([
        "<lines>\n三天后你们到了西门。\n</lines>\n<ops>\nmove player T004/gate_west\n</ops>",
        "<lines>\n第一天雾大。\n第二天进林子。\n第三天午后,坡上站起四五个人。\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n第一天走出半个时辰,路当中横着一棵倒下的桦树,树后站起四五个人。\n</lines>\n<ops>\n无变化\n</ops>",
    ])
    out = turn_v3.solve_turn(root, user_text="我们继续赶路,往碧石镇去。", provider=None, turn=5, soul_reports=[])
    j = travel.journey(root)
    stop = j["day"]
    if stop < 3:
        assert len(a.calls) == 3 and f"叙事却写到了第 3 天。只写到第 {stop} 天被拦为止" in a.calls[2][1].content
        assert out["narration"].startswith("第一天走出半个时辰")
    else:
        assert len(a.calls) == 2  # stamped day 3: the prose was right
    assert travel._day_num("三") == 3 and travel._day_num("十二") == 12 and travel._day_num("2") == 2


def test_stop_turn_rewrite_cannot_walk_back_into_town(tmp_path, fake_adapter):
    """fulllog-1001d C4a: after the stop, the narrator's rewrite put the party back at the gate with `move player gate_north`,
    which the road judge read as turning back (journey cancelled, calendar +2). Same-turn moves to the origin are refused;
    the refusal tells the narrator where the party is now."""
    from neonrp.packs.rpg import travel

    root = _install(tmp_path)
    _force_bandits(root)
    _at_gate(root)
    a = fake_adapter([
        "<lines>\n三天后到了西门。\n</lines>\n<ops>\nmove player T004/gate_west\nmove 艾琳娜 T004/gate_west\n</ops>",
        "<lines>\n你们退回北门。\n</lines>\n<ops>\nmove player T001/gate_north\nmove 艾琳娜 T001/gate_north\n</ops>",
    ])
    out = turn_v3.solve_turn(root, user_text="我们出发去碧石镇。", provider=None, turn=5, soul_reports=[])
    u2 = a.calls[1][1].content
    assert "队伍现在在路上(位置已由引擎记为 road_T001_T004" in u2 and "ops 里不要写任何 move" in u2
    j = travel.journey(root)
    assert j and j["pending"] and load_registry(root).player_location == "road_T001_T004", "still on the road: the rewrite's move back was refused"
    assert any("这回合不回城" in (r.get("why") or "") for r in out["apply"].refused)
    assert sdk.var_op("foe.boss1.status", '"wounded"') == {"op": "set", "var": "foe.boss1.status", "value": "wounded"}
    from neonrp.packs.rpg import tools
    r = tools.dice(root, load_registry(root), {"op": "dice", "dice": "1d4+1]山贼乙的刀割在肋侧,掷伤害"}, seed="1")
    assert r["ok"] and r["dice"] == "1d4+1" and r["reason"].startswith("山贼乙的刀")


# ── 10-01 panels: a layer's <formation> card and the engine-drawn [map] (画面, never state) ──────────────────────────

def test_formation_panel_and_engine_map_are_cards_not_prose(tmp_path, fake_adapter):
    from neonrp.core import modes
    from neonrp.packs.rpg import combat, tools

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    # the combat layer's format asks for a formation block
    sysm = modes.layer_system(root, reg, "combat", "zh")
    assert ("formation:这一轮结束时的阵型图" in sysm or "formation:战斗层每轮写一个" in sysm) and "formation:formation:" not in sysm
    # the engine draws the town from state
    m = tools.draw_map(root, reg, {"op": "map"})
    assert m["ok"] and m["panel"] == "map" and m["text"].startswith("── 石津镇 ──\n[你的位置] 北门(gate_north)") and "├── 主街(main_street)" in m["text"] and "远处:" in m["text"]
    # the combat layer's <formation> comes back as a card, never as lines; the narrator's [map] is fired — a card for
    # the player, no stop, no continuation, nothing fed back (a plain [map] is the same op: the registry decides)
    combat.write(root, {**combat.spawn(root, reg, note="两个山贼", turn=3), "at": reg.player_location, "note": "两个山贼"})
    a = fake_adapter([
        "<lines>\n你出手。\n[combat]侧身刺甲[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n你侧身。\n[dice 1d20+4 vs 11]命中[/dice]\n</lines>\n<formation>\n🗡甲 ──3m── ⚔你\n     🗡乙(flanking)\n</formation>\n<ops>\n无变化\n</ops>",
        "<lines>\n剑咬实了。\n</lines>\n<formation>\n🗡甲(wounded) ──5m── ⚔你 ▮木桩\n</formation>\n<ops>\nfoe.bandit1.hp -3\n</ops>",
        "<lines>\n剑咬实了。\n[map]\n你退到木桩边。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n再砍\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="继续。", provider=None, turn=4, soul_reports=[])
    assert "🗡甲" not in out["narration"] and out["narration"] == "你出手。\n剑咬实了。\n你退到木桩边。"
    assert out["panels"]["formation"]["format"] == "text" and out["panels"]["formation"]["text"].startswith("🗡甲(wounded) ──5m── ⚔你")
    assert out["panels"]["map"]["source"] == "tool" and out["panels"]["map"]["text"].startswith("── 石津镇 ──")
    assert len(a.calls) == 4 and not any("── 石津镇 ──" in str(c[1].content) for c in a.calls), "the map goes to the player, not back to the narrator"
    assert any(t.get("async") and t.get("request") == "map" for t in out["tool_returns"])
    assert not any(o.get("op") == "formation" for o in out["ops"])
    # the road and a dungeon room draw their own kind of card
    from neonrp.core.turn_settlement import _apply_player_move
    combat.write(root, None)
    assert _apply_player_move(root, "D001/D001_R001")
    m2 = tools.draw_map(root, load_registry(root), {"op": "map"})
    assert m2["text"].startswith("── 苔墓地穴 ──\n[你的位置] 潮门前室(D001_R001)\n  │── [???](D001_R002) 未探")


def test_several_dice_at_one_stop_point_are_rolled_together(tmp_path, fake_adapter):
    """A run of [dice …] lines at one stop point of the combat layer → the engine rolls them all, one reply, one
    continuation (a round in 2 layer calls instead of 4–6)."""
    from neonrp.packs.rpg import combat

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    combat.write(root, {**combat.spawn(root, reg, note="两个山贼", turn=3), "at": reg.player_location, "note": "两个山贼"})
    a = fake_adapter([
        "<lines>\n你抢先动手。\n[combat]砍甲[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n你抢先动手。\n[dice 1d20+4 vs 11]命中 甲[/dice]\n[dice 1d6+3]伤害[/dice]\n[dice 1d20+2 vs 13]甲反击[/dice]\n这行是盲写的。\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n剑咬进肩窝。\n</lines>\n<ops>\nfoe.bandit1.hp -6\nplayer.hp -2\n</ops>",
        "<lines>\n甲捂着肩退开。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n再砍\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="砍。", provider=None, turn=4, soul_reports=[])
    assert len(a.calls) == 4, "one layer continuation for the whole run of dice"
    assert [t["request"][:14] for t in out["tool_returns"][0]["answers"]] == ["dice 1d20+4 vs", "dice 1d6+3", "dice 1d20+2 vs"]
    u3 = a.calls[2][1].content
    assert u3.count("<dice ") == 3 and "<lines>\n你抢先动手。\n</lines>" in u3 and "盲写" not in u3
    assert "剑咬进肩窝。" in out["tool_returns"][0]["text"] and out["narration"] == "你抢先动手。\n甲捂着肩退开。"
    reg2 = load_registry(root)
    assert reg2.variables["foe.bandit1.hp"].value == 2 and reg2.variables["player.hp"].value == 22


def test_layer_prompts_ship_with_the_pack_world_needs_no_agents_folder(tmp_path, fake_adapter):
    """A world without agents/ still has combat / referee / dungeon layers (the rpg pack's own prompts);
    the world's agents/<id>/system.md still wins for old worlds; a template / prompt.json override wins over both."""
    from neonrp.core import modes

    root = _install(tmp_path)
    shutil.rmtree(root / "agents" / "combat-referee")
    shutil.rmtree(root / "agents" / "rules-referee")
    shutil.rmtree(root / "agents" / "dungeon-agent")
    reg = load_registry(root)
    for name, marker in (("combat", "先攻"), ("referee", "三种调用场景"), ("dungeon", "")):
        text, where = modes.prompt_source(root, name, modes.spec_of(root, name) or {}, "zh")
        assert where == f"pack:{name}.md" and text and (marker in text)
    assert "# 战斗裁判\n" in modes.layer_system(root, reg, "combat", "zh") and "先攻" in modes.layer_system(root, reg, "combat", "zh")
    en, where_en = modes.prompt_source(root, "combat", modes.spec_of(root, "combat") or {}, "en")
    assert where_en == "pack:combat.en.md" and "Combat" in en
    # a whole combat call works with no agents/ folder
    from neonrp.packs.rpg import combat
    _no_hazards(root)
    combat.write(root, {**combat.spawn(root, reg, note="两个山贼", turn=3), "at": reg.player_location})
    a = fake_adapter(["<lines>\n你砍。\n[combat]砍甲[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
                      "<lines>\n[dice 1d20+4 vs 11]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
                      "<lines>\n中了。\n</lines>\n<ops>\nfoe.bandit1.hp -3\n</ops>",
                      "<lines>\n他退开。\n</lines>\n<ops>\n无变化\n</ops>"])
    turn_v3.solve_turn(root, user_text="砍。", provider=None, turn=4, soul_reports=[])
    assert "先攻" in a.calls[1][0].content
    # an override in game/meta/prompt.json wins
    pj = root / "game" / "meta" / "prompt.json"
    d = _j(pj) if pj.exists() else {}
    d["modes"] = {"combat": {"zh": "## 本世界的战斗\n只用拳头。"}}
    pj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    text, where = modes.prompt_source(root, "combat", modes.spec_of(root, "combat") or {}, "zh")
    assert where == "template" and "只用拳头" in text



def test_formation_panel_json_format_checked_filled_and_falls_back(tmp_path, fake_adapter):
    """A panel declared format=json — the layer is told the schema, the engine checks the shape, fills hp
    from foe.* and never refuses the turn; a malformed block shows as text with the reason."""
    from neonrp.core import modes, panels

    root = _install(tmp_path)
    _no_hazards(root)
    pj = root / "game" / "meta" / "prompt.json"
    d = _j(pj) if pj.exists() else {}
    d["panels"] = {"formation": {"format": "json", "schema": {"sides": [{"name": "str", "units": [{"id": "str", "name": "str", "hp": "int", "pos": "str"}]}], "round": "int"}}}
    pj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    reg = load_registry(root)
    sysm = modes.layer_system(root, reg, "combat", "zh")
    assert "formation:只写一个 JSON 对象" in sysm and '"sides"' in sysm
    from neonrp.packs.rpg import combat
    combat.write(root, {**combat.spawn(root, reg, note="两个山贼", turn=3), "at": reg.player_location})
    good = '{"round": 1, "sides": [{"name": "山贼", "units": [{"id": "bandit1", "name": "山贼甲", "hp": 99, "pos": "front"}]}, {"name": "我方", "units": [{"id": "player", "name": "你", "pos": "front"}]}]}'
    a = fake_adapter(["<lines>\n你砍。\n[combat]砍甲[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
                      "<lines>\n[dice 1d20+4 vs 11]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
                      f"<lines>\n中了。\n</lines>\n<formation>\n{good}\n</formation>\n<ops>\nfoe.bandit1.hp -3\n</ops>",
                      "<lines>\n他退开。\n</lines>\n<ops>\n无变化\n</ops>"])
    out = turn_v3.solve_turn(root, user_text="砍。", provider=None, turn=4, soul_reports=[])
    f = out["panels"]["formation"]
    assert f["format"] == "json" and f["data"]["sides"][0]["units"][0]["hp"] == 5 and f["data"]["sides"][0]["units"][0]["hp_max"] == 8, "hp from foe.bandit1, not the model's 99"
    assert f["data"]["sides"][1]["units"][0]["hp"] == 24
    bad = panels.finish(root, "formation", '{"sides": "oops"}')
    assert bad["format"] == "text" and bad["fallback"].startswith("shape: $.sides 应为数组")
    assert panels.finish(root, "formation", "not json")["fallback"].startswith("json:")
    # map as json: the world-map level with the player's pin
    d["panels"]["map"] = {"format": "json"}
    pj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    combat.write(root, None)
    from neonrp.packs.rpg import tools
    m = tools.draw_map(root, load_registry(root), {"op": "map"})["panel_value"]
    if m["format"] == "json":  # core/worldmap present (Template v3)
        assert m["data"]["here"] == "T001/gate_north" and any(n["addr"] == "T001/main_street" for n in m["data"]["nodes"])
    else:
        assert m["format"] == "text"
    assert panels.as_text(m)


# ── 10-01 #6 / #7: rpg sentences in zh / en / ja; rule tables as data a world overrides ─────────────────────────────

def test_rpg_sentences_follow_the_world_language_and_tables_are_data(tmp_path):
    from neonrp.core import modes
    from neonrp.packs.rpg import combat, data, travel
    from neonrp.packs.rpg.contract import travel_hints
    from neonrp.packs.rpg.i18n import S

    assert all(set(v) == {"zh", "en", "ja", "ko"} for v in S.values())  # 10-05 四语
    # the English world: travel hints, the road stop, the foes' names — all English
    en = tmp_path / "w-en"
    shutil.copytree(Path(__file__).resolve().parents[1] / "src" / "neonrp" / "templates" / "stoneford-elena-en", en)
    (en / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(en / "playthrough.json", en / ".neonrp" / "playthrough.json")
    reg = load_registry(en)
    h = travel_hints(en, reg)
    assert h.startswith("## Travel (the map rules") and "about 3 days" in h and "远行" not in h
    wm = en / "game" / "world" / "world_map.json"
    d = json.loads(wm.read_text(encoding="utf-8"))
    d["travel"] = {"hazards": {"bandit_risk": {"p": 1.0}}}
    wm.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    reg.variables["turn"].value = 5
    vr = sdk.verify(en, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg)
    assert vr.refused and "bandits block the road" in vr.refused[0].why and "The party is on the road now" in vr.refused[0].why
    st = combat.spawn(en, load_registry(en), roster="3 bandits and One-Eye Tiger", turn=6)
    assert sorted(f["kind"] for f in st["foes"].values()) == ["bandit", "bandit", "bandit", "boss"]
    assert {f["name"] for f in st["foes"].values()} >= {"bandit A", "One-Eye Tiger"}
    room_foes = combat.spawn(en, load_registry(en), note="", turn=6, room=SimpleNamespace(cls="room", props={"encounters": [{"enemy": "mire-moss rat", "count": "2", "chance": 1.0}]}))
    assert [f["kind"] for f in room_foes["foes"].values()] == ["rat", "rat"] and room_foes["foes"]["rat1"]["name"] == "mire-moss rat A"
    combat.write(en, {**combat.spawn(en, load_registry(en), note="bandits", turn=6), "note": "bandits"})
    assert combat.state_block(en, load_registry(en)).startswith("# Combat state (round 1; hand-off: bandits)")
    # world overrides: game/rules/<table>.json, key by key
    zh = _install(tmp_path / "zh")
    (zh / "game" / "rules" / "foes.json").write_text(json.dumps({"bandit": {"hp": 20}, "ogre": {"hp": 30, "def": 12, "atk": 5, "dmg": "2d6", "names": {"zh": "食人魔"}}}, ensure_ascii=False), encoding="utf-8")
    (zh / "game" / "rules" / "rules.json").write_text(json.dumps({"referee_difficulty": {"normal": 9}, "travel_per_day": 45}), encoding="utf-8")
    (zh / "game" / "rules" / "hazards.json").write_text(json.dumps({"bandit_risk": {"p": 0.0}}), encoding="utf-8")
    assert data.table(zh, "foes")["bandit"]["hp"] == 20 and data.table(zh, "foes")["bandit"]["def"] == 11, "key-by-key, the rest from the pack"
    assert data.foe_key(zh, "食人魔") == "ogre" and data.foe_key(zh, "山贼头目") == "bandit"
    assert data.rules(zh)["referee_difficulty"]["hard"] == 15 and data.rules(zh)["referee_difficulty"]["normal"] == 9
    assert travel.route_days(zh, "T001", "T004") == 1 and travel.plan(zh, "T001", "T004", seed="1")["stops"] == []


# ── 10-01 P0 understanding: the player's words are an attempt, checked against the world; <combat> needs grounds ──────

def test_understanding_marks_phantom_foes_and_combat_needs_grounds(tmp_path, fake_adapter):
    from neonrp.packs.rpg import understand

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    u = understand.understand(root, reg, "我拔剑冲向山贼,让罗文也来帮忙")
    refs = {r["id"]: r for r in u["refs"]}
    assert refs["bandit"]["status"] == "absent" and refs["si-rowan0001"]["status"] in ("town_only", "elsewhere")
    assert u["block"].startswith("# 本回合的理解") and "玩家试图:我拔剑冲向山贼" in u["block"] and "山贼:此处没有" in u["block"]
    # the narrator sees it; if the world then writes them in with <combat>, that is the encounter: they are spawned (10-20)
    a = fake_adapter([
        "<lines>\n你拔剑。\n<combat 山贼×3>三个山贼从雾里冲出来</combat>\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n你拔剑冲进雾里,三个山贼围上来。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n收剑\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="我拔剑冲向山贼", provider=None, turn=3, soul_reports=[])
    assert "# 本回合的理解" in a.calls[0][1].content and "山贼:此处没有" in a.calls[0][1].content
    assert not any("<refused combat" in c[1].content for c in a.calls if len(c) > 1)
    from neonrp.packs.rpg import combat
    assert [f["kind"] for f in (combat.read(root) or {}).get("foes", {}).values()] == ["bandit"] * 3
    assert out["understood"]["refs"][0]["status"] == "absent"
    # with a real road stop the same words find the bandits, and <combat> is allowed
    root2 = _install(tmp_path / "b")
    _force_bandits(root2)
    _at_gate(root2)
    reg2 = load_registry(root2)
    reg2.variables["turn"].value = 5
    sdk.verify(root2, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg2)
    reg2 = load_registry(root2)
    u2 = understand.understand(root2, reg2, "我拔剑冲向山贼")
    assert u2["refs"][0]["status"] == "here" and "山贼:就在这里(路上的停点)" in u2["block"]
    assert understand.combat_grounds(root2, reg2, {"op": "combat", "roster": "山贼×3"}).ok
    # turning on someone present is allowed (the referee should have ruled first; that is the narrator's step)
    gate = load_registry(root)
    npc_here = next((e for e in gate.of_class("npc") if e.parent == gate.player_location), None)
    if npc_here is not None:
        assert understand.combat_grounds(root, gate, {"op": "combat", "roster": npc_here.name}).ok


def test_souls_receive_the_attempt_not_the_raw_claim(tmp_path):
    """The soul side gets 「玩家此刻:」 + the understanding block (attempt + facts), so a soul cannot vouch for a phantom."""
    from neonrp.packs.rpg import understand, soul_step

    root = _install(tmp_path)
    reg = load_registry(root)
    block = understand.understand(root, reg, "I charge the bandits")["block"]
    seen = {}

    def fake_ask(state, qs, **_kw):
        seen.update(state)
        return {}

    soul_step.judge_soul(root, "si-elena0001", situation="场景:北门。玩家此刻:" + block, registry=reg, ask=fake_ask)
    assert seen["player_says"].startswith("# 本回合的理解") and "山贼:此处没有" in seen["player_says"]


def test_section_styles_restyle_and_parse_back():
    """10-01: turn.solve.sections = xml | divider | fence — the engine rewrites only whole-line section markers in what it
    sends; the parser reads every style back to the same output."""
    from neonrp.core.adv import restyle

    src = "## 输出格式\n严格按下面的格式输出。\n<lines>\n你推门。\n<move player inn>\n</lines>\n<ops>\nplayer.gold -8\n</ops>"
    d = restyle(src, "divider")
    assert "=== lines ===" in d and "</lines>" not in d and "<move player inn>" in d and "=== 名字 ===" in d
    f = restyle(src, "fence")
    body = f.split("\n", 3)[3]  # after the heading, the rule line and the style sentence
    assert body.startswith("```lines") and body.count("```") == 4 and "<move player inn>" in f
    assert restyle(src, "xml") == src
    outs = {
        "xml": "<lines>\n你推门。\n[dice 1d20 vs 10]撞门[/dice]\n</lines>\n<ops>\nplayer.gold -8\n</ops>\n<options>\n走\n</options>",
        "divider": "=== lines ===\n你推门。\n[dice 1d20 vs 10]撞门[/dice]\n=== ops ===\nplayer.gold -8\n=== options ===\n走",
        "fence": "```lines\n你推门。\n[dice 1d20 vs 10]撞门[/dice]\n```\n```ops\nplayer.gold -8\n```\n```options\n走\n```",
    }
    parsed = {k: sdk.parse_solve_output(v) for k, v in outs.items()}
    for k, o in parsed.items():
        assert o.narration.startswith("你推门。") and [x["op"] for x in o.ops][:1] == ["dice"], k
        assert any(x.get("var") == "player.gold" for x in o.ops) and o.options == ["走"], k


def test_async_mark_registry_decides() -> None:
    """[dice] waits, <map> / [~map] does not — the registry decides, the model's bracket is a hint, mismatches recorded."""
    from neonrp.core import sdk
    from neonrp.core.adv import async_restyle
    from neonrp.packs.rpg.pack import ACTIONS

    spec = {a.op: a for a in ACTIONS}
    assert spec["dice"].waits() and spec["referee"].waits() and not spec["map"].waits() and not spec["move_to"].waits()
    old = sdk.WAIT_OPS, sdk.FIRE_OPS
    try:
        sdk.WAIT_OPS, sdk.FIRE_OPS = {"dice", "referee", "ask", "need"}, {"map", "move", "move_to", "flag"}
        out = sdk.parse_solve_output("=== lines ===\n你摊开地图。\n[~map]\n[map]\n你朝北门走。[~move player gate_north]\n<referee 翻墙>\n写盲了的一行\n=== ops ===\n[~flag climbed]\n无变化")
        assert out.narration.splitlines() == ["你摊开地图。", "你朝北门走。"]  # <referee> (a sync op, angle-marked) became the stop point
        assert [o["op"] for o in out.ops] == ["map", "map", "move_to", "referee", "flag"] and out.ops[3].get("await")
        assert [(m["op"], m["wrote"], m["ok"]) for m in out.marks] == [("map", "tilde", True), ("map", "plain", False), ("move", "tilde", True), ("referee", "angle", False)]
        out = sdk.parse_solve_output("<lines>\n[~dice 1d20+2 vs 12]翻墙[/dice]\n</lines>\n<ops>\n无变化\n</ops>")
        assert out.ops[0]["op"] == "dice" and out.ops[0].get("await") and out.ops[0]["reason"] == "翻墙" and out.marks[0]["ok"] is False
    finally:
        sdk.WAIT_OPS, sdk.FIRE_OPS = old
    t = async_restyle("## 输出格式\n照做。\n<move player inn>你推门。</move> <flag paid> <map> <say 艾琳娜>「嗯」</say> <roll 1d6>4</roll>", "tilde", {"move", "flag", "map"})
    assert "[~move player inn]你推门。" in t and "[~flag paid]" in t and "[~map]" in t and "<say 艾琳娜>" in t and "<roll 1d6>4</roll>" in t and "[~ ]" in t


def test_gate_draws_the_map_when_the_player_asks_the_way(tmp_path, fake_adapter):
    """The model drew the map on its own 1 time in 4 — the engine fires it from the player's words (async: a card, no extra call)."""
    from neonrp.packs.rpg import gates

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    assert gates.pre_turn(root, reg, user_text="我把地图摊开看看")["fire"] == [{"op": "map"}]
    assert "fire" not in gates.pre_turn(root, reg, user_text="我去公会接委托")
    a = fake_adapter(["<lines>\n你摊开地图,北门在最上头。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n去公会\n</options>"])
    out = turn_v3.solve_turn(root, user_text="我把地图摊开,看看我们在哪儿。", provider=None, turn=2, soul_reports=[])
    assert out["panels"]["map"]["text"].startswith("── 石津镇 ──") and len(a.calls) == 1
    assert any(t.get("by") == "gate" and t.get("async") for t in out["tool_returns"])


def test_adversarial2_fixes_language_sheet_prices(tmp_path, fake_adapter):
    """adversarial2: H1 (an English line turned the run English), F2 (stats read into the prose),
    I2 (three runs, three prices for the same room)."""
    from neonrp.core import modes
    from neonrp.core.adv import lang_rule
    from neonrp.packs.rpg import contract, gates, understand

    root = _install(tmp_path)
    _no_hazards(root)
    reg = load_registry(root)
    # the run's language, not the player's line
    assert "用中文写" in contract.contract(root, reg, "adv") and "用玩家的语言" not in contract.contract(root, reg, "adv")
    assert "用中文写" in modes.layer_system(root, reg, "combat", "zh") and lang_rule(root, "zh", soul=True).startswith("用中文说")
    # the sheet is the engine's panel; the narrator is told not to read numbers
    assert {"op": "sheet"} in gates.pre_turn(root, reg, user_text="显示一下我的属性面板")["fire"]
    assert "不要列数值" in understand.understand(root, reg, "显示一下我的属性面板")["block"]
    a = fake_adapter(["<lines>\n你低头打量自己。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n走\n</options>"])
    out = turn_v3.solve_turn(root, user_text="显示一下我的属性面板", provider=None, turn=2, soul_reports=[])
    assert out["panels"]["sheet"]["text"].startswith("生命 24/24") and "钱袋 18g" in out["panels"]["sheet"]["text"] and len(a.calls) == 1
    # prices come from the facility files, with a unit
    hints = contract.pack_hints(root, reg)
    assert "## 本镇价目(单位:金" in hints and "河灯旅店:通铺 3 · 单间 8" in hints and "小治疗药水 12" in hints


def test_unsure_reads_are_decided_by_her_own_words(tmp_path, monkeypatch):
    """Follow .43 @ conf .14 / willingness .32 @ .36 must not decide 「拒绝」 — she decides in words,
    the engine reads it back off what she said."""
    from neonrp.core import system_one as s1
    from neonrp.packs.rpg import soul_step as ss

    root = _install(tmp_path)
    j = ss.SoulJudgment("si-elena0001", "艾琳娜", None, None, 0, False, None, 0.0, "jev", 0.0, 0.0)
    j.answers = {"follow": {"v": 0.43, "c": 0.14}, "willingness": {"v": 0.32, "c": 0.36}, "stay": {"v": 0.07, "c": 0.86}}
    j.follow, j.decision = 0.43, {"stakes": "light", "outcome": "refuse"}
    assert ss._unsure_reads(root, j) == {"follow", "willingness"}
    seen = {}

    def fake_ask(state, qs, **k):
        seen.update(state)
        return {"follow": s1.Answer("noul", 0.92, {}, 0.9), "stay": s1.Answer("noul", 0.05, {}, 0.9), "agreed": s1.Answer("noul", 0.88, {}, 0.9)}

    monkeypatch.setattr(s1, "ask", fake_ask)
    ss._read_her_words(root, j, "「行,主街我也正要去。」", situation="北门。玩家此刻:一起去主街吧", unsure={"follow", "willingness"})
    assert j.follow == 0.92 and j.stay == 0.05 and j.decision["outcome"] == "comply" and j.decision["post_hoc"]
    assert seen["her_words"].startswith("「行") and "post.follow" in j.answers
    j2 = ss.SoulJudgment("x", "x", None, None, 0, False, None, 0.0, "jev", 0.0, 0.0)
    j2.answers = {"follow": {"v": 0.8, "c": 0.9}, "willingness": {"v": 0.9, "c": 0.8}}
    assert ss._unsure_reads(root, j2) == set()


def test_annotated_output_marks_in_place(tmp_path, fake_adapter):
    """The turn's output carries every request, engine answer and state change in place; the player's text
    is strip_marks(annotated) == narration; mark_events feeds the SDK; a copied engine answer never reaches the screen."""
    from neonrp.core import modes, sdk

    root = _install(tmp_path)
    _no_hazards(root)
    from neonrp.packs.rpg import combat
    combat.write(root, {**combat.spawn(root, load_registry(root), note="两个山贼", turn=3), "at": load_registry(root).player_location})
    fake_adapter([
        "<lines>\n你侧身。\n[dice 1d20+4 vs 11]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n剑咬实了。\n[map]\n你退到木桩边。\n</lines>\n<ops>\nfoe.bandit1.hp -3\n</ops>\n<options>\n再砍\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="继续。", provider=None, turn=4, soul_reports=[])
    ann = out["annotated"]
    assert sdk.strip_marks(ann) == out["narration"] == "你侧身。\n剑咬实了。\n你退到木桩边。"
    lines = ann.splitlines()
    assert lines[0] == "你侧身。" and lines[1].startswith("[dice 1d20+4 vs 11]命中[/dice]<dice>") and lines[2] == "剑咬实了。"
    assert "[~map]" in ann and lines[-1] == "[~foe.bandit1.hp -3]"
    ev = sdk.mark_events(ann)
    assert [(e["kind"], e["op"], e["line"]) for e in ev][:2] == [("request", "dice", 1), ("answer", "dice", 1)]
    assert ("action", "foe.bandit1.hp", "-3") in [(e["kind"], e["op"], e["args"]) for e in ev]
    old = sdk.WAIT_OPS
    try:
        sdk.WAIT_OPS = {"referee", "dice"}
        assert sdk.parse_solve_output("<lines>\n他看着你。\n<referee 抢>检定 20 过</referee>\n</lines>\n<ops>\n无变化\n</ops>").narration == "他看着你。"
    finally:
        sdk.WAIT_OPS = old


def test_open_schema_list_store_and_effects(tmp_path):
    """The player's bag and states are open-schema instances (no migration — items of the existing lists);
    an effect class counts down, applies its per-turn change, adds its check modifier, and leaves at 0. The engine knows
    no effect by name: these names live in this test only."""
    from neonrp.core import effects

    root = _install(tmp_path)
    reg = load_registry(root)
    assert reg.entries["travel-bread"].cls == "carry" and reg.entries["travel-bread"].props["qty"] == 2
    ops = [sdk._adv_line_op(x) for x in ("patch 旅行黑麦面包 qty=1", "new status 腹痛 on=player turns=2 check=-2 each=player.hp:-1 note=吃坏了", "remove 罩灯")]
    assert ops[0] == {"op": "patch", "who": "旅行黑麦面包", "props": {"qty": "1"}}
    assert ops[1]["props"] == {"on": "player", "turns": "2", "check": "-2", "each": "player.hp:-1", "note": "吃坏了"}
    vr = sdk.verify(root, ops, reg)
    assert not vr.refused, [r.to_dict() for r in vr.refused]
    ar = sdk.apply(root, vr.accepted, reg, turn=3)
    inv = _j(root / "game" / "player" / "inventory.json")["items"]
    assert {x["id"]: x["qty"] for x in inv} == {"travel-bread": 1, "healing-herb": 1}  # bread used, the lantern gone
    st = _j(root / "game" / "player" / "stats.json")
    assert st["status_effects"][0]["name"] == "腹痛" and st["status_effects"][0]["turns"] == 2 and st["hp"]["current"] == 24  # starts next turn
    reg = load_registry(root)
    assert effects.check_mod(reg, "player") == -2 and "腹痛" in effects.describe(reg, "player")
    assert "身上的状态" in sdk.render_pack(sdk.pack(root, registry=reg))
    sdk.apply(root, [], reg, turn=4)  # an empty turn: the effect ticks
    st = _j(root / "game" / "player" / "stats.json")
    assert st["hp"]["current"] == 23 and st["status_effects"][0]["turns"] == 1
    sdk.apply(root, [], load_registry(root), turn=5)
    st = _j(root / "game" / "player" / "stats.json")
    assert st["hp"]["current"] == 22 and st["status_effects"] == []  # ran out → removed
    assert effects.check_mod(load_registry(root), "player") == 0
    # an instance of a non-open class cannot be removed
    vr = sdk.verify(root, [{"op": "remove", "who": "艾琳娜"}], load_registry(root))
    assert vr.refused and not vr.refused[0].fixable


def test_schema_grows_in_play_define_and_new_town(tmp_path):
    """Open schema is proven by the schema itself growing — a class / variable / town the template never had,
    defined in play, written as files, packed next turn, usable at once. These names exist only in this test."""
    from neonrp.packs.rpg import travel

    root = _install(tmp_path)
    reg = load_registry(root)
    assert "pet" not in reg.classes and "town.rumor_heat" not in reg.variables
    lines = ["define class pet 伙伴动物 kind=str hunger=int mood=calm|scared|happy mutable=hunger,mood",
             "new pet 灰灰 kind=雾狐 hunger=2 mood=scared",
             "define var town.rumor_heat int 0 min=0 max=10 note=镇上议论的热度",
             "town.rumor_heat +2",
             "new_town 雾港 from=T001 days=2 summary=河口的盐雾小港 tags=foggy"]
    ops = [sdk._adv_line_op(x) for x in lines]
    vr = sdk.verify(root, ops, reg)
    assert not vr.refused, [r.to_dict() for r in vr.refused]
    ar = sdk.apply(root, vr.accepted, reg, turn=2)
    assert {c.get("id") for c in ar.created} >= {"pet", "town.rumor_heat"}
    pet_file = next((root / "game" / "open" / "pet").glob("*.json"))
    assert _j(pet_file)["props"]["kind"] == "雾狐"
    reg = load_registry(root)  # the next turn
    assert reg.classes["pet"].custom and reg.resolve("灰灰", cls="pet") and reg.variables["town.rumor_heat"].value == 2
    town = reg.resolve("雾港", cls="town")
    assert town and travel.route_days(root, "T001", town) == 2 and bool((place_tree.level_doc(root, town) or {}).get("nodes"))
    text = sdk.render_pack(sdk.pack(root, registry=reg))
    assert "## 伙伴动物" in text and "灰灰" in text and "new pet <名字>" in text and "town.rumor_heat" in text
    vr = sdk.verify(root, [sdk._adv_line_op("patch 灰灰 hunger=0 mood=happy"), sdk._adv_line_op("define class pet 重复 x=int")], reg)
    assert len(vr.accepted) == 1 and vr.refused[0].field == "name"
    sdk.apply(root, vr.accepted, reg, turn=3)
    assert load_registry(root).entries[reg.resolve("灰灰", cls="pet")].props["mood"] == "happy"


def test_new_props_land_on_their_owner(tmp_path):
    """Adding a prop is a basic op, and it lands in the owner's own record — an NPC's grudge in that NPC's
    entry (its state block), the player's in the player's file; a thing not in the bag cannot be used."""
    root = _install(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [sdk._adv_line_op(x) for x in ("patch 老苇 attitude=hostile reason=被拔剑威胁", "patch player reputation_note=镇上有人认得这张脸")], reg)
    assert not vr.refused, [r.to_dict() for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=2)
    npc = next(n for n in _j(root / "game" / "towns" / "T001" / "npcs.json")["npcs"] if n["id"] == "NPC002")
    assert npc["state"]["attitude"] == "hostile" and npc["state"]["reason"] == "被拔剑威胁"
    assert _j(root / "game" / "player" / "profile.json")["reputation_note"] == "镇上有人认得这张脸"
    assert "status_effects" not in _j(root / "game" / "player" / "stats.json") or not _j(root / "game" / "player" / "stats.json")["status_effects"]
    reg = load_registry(root)
    assert "attitude=hostile" in sdk.render_pack(sdk.pack(root, registry=reg)) or reg.entries["NPC002"].props["state"]["attitude"] == "hostile"
    # identity never changes; a thing that is not in the bag cannot be used
    vr = sdk.verify(root, [sdk._adv_line_op("patch 老苇 name=别人"), sdk._adv_line_op("patch 治疗药水 qty=0")], reg)
    assert not vr.accepted and [r.field for r in vr.refused] == ["props", "who"]


def test_new_npc_then_patch_same_turn_and_souls_not_world_written(tmp_path):
    """A person who just appeared carries the grudge in their own record (new_npc → patch, one turn);
    a character's state is hers — the world side cannot patch a soul."""
    root = _install(tmp_path)
    reg = load_registry(root)
    ops = [{"op": "new_npc", "name": "守门老兵", "at": "", "role": "守门人"}, sdk._adv_line_op("patch 守门老兵 attitude=hostile"),
           sdk._adv_line_op("patch 艾琳娜 mood=wary")]
    vr = sdk.verify(root, ops, reg)
    assert [o["op"] for o in vr.accepted] == ["new_npc", "patch"] and vr.refused[0].field == "props" and not vr.refused[0].fixable  # her mood is hers
    sdk.apply(root, vr.accepted, reg, turn=2)
    npc = next(n for n in _j(root / "game" / "towns" / "T001" / "npcs.json")["npcs"] if n["name"] == "守门老兵")
    assert npc["state"]["attitude"] == "hostile"
    assert not any(k.startswith("~pending:") for k in reg.entries)


def test_world_file_ops_in_play(tmp_path):
    """Create / edit / delete files and folders is the open schema's floor — proposed as ops, checked, landed,
    and shown back in the pack (the narrator never reads files). Sandbox: the world folder, never meta/ or engine-owned files."""
    root = _install(tmp_path)
    reg = load_registry(sdk.SolveOutput and root)
    out = sdk.parse_adv("<lines>\n你在告示板上钉了一张纸。\n[~write notices/wanted.md]# 寻人\n罗文,背长弓,十日前出北门。[/write]\n</lines>\n"
                        "<ops>\nmkdir notices/old\nedit towns/T001/town.json state.notice=寻人告示\n</ops>")
    assert out.narration == "你在告示板上钉了一张纸。" and "寻人" not in out.narration
    w = next(o for o in out.ops if o["op"] == "write")
    assert w["path"] == "notices/wanted.md" and w["body"].startswith("# 寻人")
    vr = sdk.verify(root, out.ops, reg)
    assert not vr.refused, [r.to_dict() for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=2)
    g = root / "game"
    assert (g / "notices" / "wanted.md").read_text(encoding="utf-8").startswith("# 寻人") and (g / "notices" / "old").is_dir()
    assert _j(g / "towns" / "T001" / "town.json")["state"]["notice"] == "寻人告示"
    text = sdk.render_pack(sdk.pack(root, registry=load_registry(root)))
    assert "# 世界文件夹" in text and "notices/: wanted.md" in text and "--- notices/wanted.md" in text
    bad = [sdk._adv_line_op(x) for x in ("rm towns/T001/town.json", "mkdir ../outside", "edit meta/run_state.json x=1", "rm player/inventory.json")]
    bad.append({"op": "write", "path": "notes/x.json", "body": "{not json"})
    vr = sdk.verify(root, bad, load_registry(root))
    assert not vr.accepted and len(vr.refused) == 5, [r.why for r in vr.refused]
    vr = sdk.verify(root, [sdk._adv_line_op("rm notices/wanted.md"), sdk._adv_line_op("rmdir notices/old")], load_registry(root))
    assert len(vr.accepted) == 2
    sdk.apply(root, vr.accepted, load_registry(root), turn=3)
    assert not (g / "notices" / "wanted.md").exists() and not (g / "notices" / "old").exists()


def test_day_cannot_jump_and_owner_rule(tmp_path):
    """「三天后」 is an intent — time.day moves at most one per turn by the narrator's ops; and a lasting change
    in someone that was written nowhere goes back to the narrator (the judge asks; no state is named by the engine)."""
    from neonrp.core import l2
    from neonrp.core import system_one as s1

    root = _install(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [sdk._adv_line_op("time.day 4"), sdk._adv_line_op("time.day +3"), sdk._adv_line_op("time.day 2")], reg)
    assert [r.field for r in vr.refused] == ["value", "delta"] and "an intent" in vr.refused[0].why and len(vr.accepted) == 1
    yes = lambda st, qs, **k: {"lasting": s1.Answer("noul", 0.9, {}, 0.9)}  # noqa: E731
    assert l2.owner_rule(reg, "老兵抹掉脸上的唾沫,记住了你的脸。", [], ask=yes)[0]["fixable"]
    assert l2.owner_rule(reg, "老兵抹掉脸上的唾沫,记住了你的脸。", [{"op": "patch", "who": "老兵", "props": {"x": 1}}], ask=yes) == []
    assert l2.owner_rule(reg, "老兵看了你一眼。", [], ask=lambda st, qs, **k: {"lasting": s1.Answer("noul", 0.1, {}, 0.9)}) == []


def test_the_calendar_never_goes_back_even_after_a_journey_in_the_same_batch(tmp_path, fake_adapter):
    """10-14 V4 B1: the narrator wrote `move player T004/…` and `time.day 2` in one batch — checked against day 1 the set
    looked like +1, but the journey had already moved the calendar to day 4, and the set put it back to day 2."""
    root = _install(tmp_path)
    reg = load_registry(root)
    day0 = reg.variables["time.day"].value
    vr = sdk.verify(root, [sdk._adv_line_op(f"time.day {day0 + 1}"), sdk._adv_line_op("time.day -1")], reg)
    assert len(vr.accepted) == 1 and [r.field for r in vr.refused] == ["delta"] and "never goes back" in vr.refused[0].why
    sdk.apply(root, vr.accepted, reg, turn=4)
    reg = load_registry(root)
    assert reg.variables["time.day"].value == day0 + 1
    vr = sdk.verify(root, [sdk._adv_line_op(f"time.day {day0}")], reg)
    assert [r.field for r in vr.refused] == ["value"]
    # both passed their checks against day0 + 1 (the journey's stop is another test's business): applied in order
    res = sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}, {"op": "set", "var": "time.day", "value": day0 + 2}], reg, turn=5)
    assert load_registry(root).variables["time.day"].value == day0 + 1 + 3
    assert [r["field"] for r in res.refused] == ["value"] and "never goes back" in res.refused[0]["why"]


def test_the_clock_never_goes_back_and_a_night_carries_the_day(tmp_path):
    """10-14: a clock set earlier the same day is refused (11:00 → 10:55); set hours earlier it is the next morning and the
    day goes on by one (17:40 → 07:10) — unless the same batch already moved the day."""
    root = _install(tmp_path)
    reg = load_registry(root)
    sdk.apply(root, [{"op": "set", "var": "time.clock", "value": "17:40"}], reg, turn=1)
    reg = load_registry(root)
    day0 = reg.variables["time.day"].value
    vr = sdk.verify(root, [sdk._adv_line_op("time.clock 17:35")], reg)
    assert [r.field for r in vr.refused] == ["value"] and "never goes back" in vr.refused[0].why
    vr = sdk.verify(root, [sdk._adv_line_op("time.clock 07:10")], reg)
    assert not vr.refused
    res = sdk.apply(root, vr.accepted, reg, turn=2)
    reg = load_registry(root)
    assert reg.variables["time.clock"].value == "07:10" and reg.variables["time.day"].value == day0 + 1
    assert any(r.get("why", "").startswith("past midnight") for r in res.repaired)
    sdk.apply(root, [{"op": "set", "var": "time.clock", "value": "22:00"}], reg, turn=3)
    reg = load_registry(root)
    sdk.apply(root, [{"op": "set", "var": "time.day", "value": day0 + 2}, {"op": "set", "var": "time.clock", "value": "06:30"}], reg, turn=4)
    assert load_registry(root).variables["time.day"].value == day0 + 2, "the batch moved the day itself: no second carry"


def test_a_night_slept_through_sets_the_morning_clock_with_the_day(tmp_path):
    """10-21 PL12/S4: going to sleep at 09:15, the transition wrote `time.day +1` and `time.clock 07:10` in one batch — the
    clock was only two hours "earlier" and came back as going back, so day 2 read 09:15 while the prose said dawn (25 runs)."""
    root = _install(tmp_path)
    reg = load_registry(root)
    sdk.apply(root, [{"op": "set", "var": "time.clock", "value": "09:15"}], reg, turn=1)
    reg = load_registry(root)
    day0 = reg.variables["time.day"].value
    vr = sdk.verify(root, [sdk._adv_line_op("time.clock 07:10"), sdk._adv_line_op(f"time.day {day0 + 1}")], reg)
    assert not vr.refused
    sdk.apply(root, vr.accepted, reg, turn=2)
    reg = load_registry(root)
    assert (reg.variables["time.day"].value, reg.variables["time.clock"].value) == (day0 + 1, "07:10")
    sdk.apply(root, [{"op": "set", "var": "time.clock", "value": "22:00"}], reg, turn=3)
    reg = load_registry(root)
    vr = sdk.verify(root, [sdk._adv_line_op("time.clock 06:30"), sdk._adv_line_op("time.day +1")], reg)
    sdk.apply(root, vr.accepted, reg, turn=4)
    assert load_registry(root).variables["time.day"].value == day0 + 2, "the clock first, the day after: one day, not two"
    vr = sdk.verify(root, [sdk._adv_line_op("time.clock 05:00")], load_registry(root))
    assert [r.field for r in vr.refused] == ["value"], "without the day it is still going back"


def test_a_patch_that_changes_nothing_is_sent_back_and_a_move_to_where_one_is_is_no_refusal(tmp_path):
    """10-14 V4: ID2 wrote qty 1 → 1 for 「one more bundle」 and nothing changed; moves to where the player already stood
    came back as 「handler refused」 with no reason."""
    root = _install(tmp_path)
    reg = load_registry(root)
    assert reg.entries["healing-herb"].props["qty"] == 1
    vr = sdk.verify(root, [{"op": "patch", "who": "healing-herb", "props": {"qty": 1}}], reg)
    assert vr.refused and "nothing changes" in vr.refused[0].why and vr.refused[0].allowed == ["qty 2"], "the hint is the new total"
    vr = sdk.verify(root, [{"op": "patch", "who": "healing-herb", "props": {"qty": 2}}], reg)
    assert not vr.refused
    sdk.apply(root, [{"op": "patch", "who": "NPC002", "props": {"order": "一束止血草"}}], reg, turn=1)
    vr = sdk.verify(root, [{"op": "patch", "who": "NPC002", "props": {"order": "一束止血草"}}], load_registry(root))
    assert vr.refused and "nothing changes" in vr.refused[0].why, "an NPC's own props (kept in its state) count too"
    here = reg.player_location
    res = sdk.apply(root, [{"op": "move_to", "who": "player", "to": here}], load_registry(root), turn=3)
    assert not res.refused and any(r.get("why") == "already there" for r in res.repaired)


def test_reproposal_does_not_trip_on_last_attempts_placeholder(tmp_path):
    """10-02 J3: a re-proposal re-verifies new_npc + patch — the first attempt's placeholder must not make the person
    「already exist」 (that dropped the grudge on the floor)."""
    root = _install(tmp_path)
    reg = load_registry(root)
    ops = [{"op": "new_npc", "name": "托姆", "at": "", "role": "守门人"}, sdk._adv_line_op("patch 托姆 attitude=hostile")]
    sdk.verify(root, [dict(o) for o in ops], reg)  # first attempt (refused elsewhere → re-proposal)
    vr = sdk.verify(root, [dict(o) for o in ops], reg)
    assert [o["op"] for o in vr.accepted] == ["new_npc", "patch"] and not vr.refused
    sdk.apply(root, vr.accepted, reg, turn=2)
    npc = next(n for n in _j(root / "game" / "towns" / "T001" / "npcs.json")["npcs"] if n["name"] == "托姆")
    assert npc["state"]["attitude"] == "hostile"


def test_patch_finds_list_items_by_name_and_never_writes_the_file_top(tmp_path):
    """10-02 N2 / N7: a job's progress lands on the job (quests.json rows have qid, not id); a person's appointment on
    that person (the guild steward stands in the guild); a row that cannot be found is refused, never written to the top."""
    root = _install(tmp_path)
    reg = load_registry(root)
    assert reg.entries["NPC001"].parent == "T001/guild"  # the steward is where his job is
    vr = sdk.verify(root, [sdk._adv_line_op("patch 苔墓前的狼嚎 state=accepted"), sdk._adv_line_op("patch 赫伦 约定=今晚河灯旅店喝一杯")], reg)
    assert not vr.refused, [r.to_dict() for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=2)
    q = _j(root / "game" / "towns" / "T001" / "quests.json")
    assert next(x for x in q["quests"] if x["title"] == "苔墓前的狼嚎")["state"] == "accepted" and "state" not in q
    heron = next(n for n in _j(root / "game" / "towns" / "T001" / "npcs.json")["npcs"] if n["id"] == "NPC001")
    assert heron["state"]["约定"] == "今晚河灯旅店喝一杯"


def test_long_case_fixes_1002_dungeon_landing_quest_props_and_patched_location(tmp_path):
    """3× long-case run (10-02): N2 verify accepted the guild→dungeon move but the landing clamped to the gate (the
    narrator then fought at a gate it took for the dungeon); N6 clues patched onto a job vanished on reload;
    N7 a patched location moved nobody."""
    from neonrp.core.turn_settlement import _apply_player_move

    root = _install(tmp_path)
    _no_hazards(root)
    assert _apply_player_move(root, "T001/guild")
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "D001"}], reg)
    assert vr.refused == [] and vr.accepted[0]["to"] == "D001/D001_R001"  # verify says what the landing will do
    sdk.apply(root, vr.accepted, reg, turn=3)
    assert load_registry(root).player_location == "D001/D001_R001"  # guild → dungeon in one beat (10-19)
    # N6: an open prop on a job comes back on reload
    job = next(j for j in reg.of_class("job"))
    vr = sdk.verify(root, [{"op": "patch", "who": job.id, "props": {"clue": "北门外有成串兽爪印"}}], reg)
    assert vr.refused == []
    sdk.apply(root, vr.accepted, reg, turn=3)
    assert load_registry(root).entries[job.id].props.get("clue") == "北门外有成串兽爪印"
    # N7: location is moved, never patched
    reg = load_registry(root)
    npc = next(n for n in reg.of_class("npc"))
    vr = sdk.verify(root, [{"op": "patch", "who": npc.id, "props": {"location": "T001/inn"}}], reg)
    assert vr.accepted == [] and "move" in vr.refused[0].why


def test_unknown_place_grows_unless_it_is_another_name_or_does_not_fit(tmp_path, monkeypatch):
    """An unknown place (or anchor) is created, not refused — but 得看是否合理: another name for a place the
    town has walks there; a place the judge finds out of place is sent back; no judge answer → it grows."""
    from neonrp.core import system_one as s1
    from neonrp.core.turn_settlement import _apply_player_move

    def fresh():
        root = _install(tmp_path / str(len(list(tmp_path.iterdir()))))
        _no_hazards(root)
        _apply_player_move(root, "T001/gate_north")  # the opening spot already; the move is a no-op there
        return root, load_registry(root)

    root, reg = fresh()  # create + move in one batch, anchored to a town
    vr = sdk.verify(root, [{"op": "new_location", "name": "苔墓小径", "parent": "T001"}, {"op": "move_to", "who": "player", "to": "苔墓小径"}], reg)
    assert vr.refused == []
    sdk.apply(root, vr.accepted, reg, turn=5)
    reg = load_registry(root)
    assert reg.player_location == "T001/苔墓小径" and reg.entries["T001/苔墓小径"].links == ["T001/gate_north"]
    # the graph draws: both ends linked on the town map, the node beside its anchor, the world map (towns) untouched
    tm = place_tree.level_doc(root, "T001")
    nodes = {n["id"]: n for n in tm["nodes"]}
    assert "苔墓小径" in nodes["gate_north"]["links"] and nodes["苔墓小径"]["links"] == ["gate_north"]
    gx, gy, px, py = nodes["gate_north"]["pos"]["x"], nodes["gate_north"]["pos"]["y"], nodes["苔墓小径"]["pos"]["x"], nodes["苔墓小径"]["pos"]["y"]
    assert (gx - px) ** 2 + (gy - py) ** 2 <= 160 ** 2
    assert all(n["id"] != "苔墓小径" for n in place_tree.level_doc(root, "world")["nodes"])
    assert _j(root / "game/locations/T001/苔墓小径/location.json")["connections"] == ["gate_north"]  # its folder, in the town's
    root, reg = fresh()  # a bare move to a place nobody made
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "墓门前"}], reg)
    sdk.apply(root, vr.accepted, reg, turn=5)
    assert load_registry(root).player_location == "T001/墓门前"
    root, reg = fresh()  # another name for the guild
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "公会大厅"}], reg)
    assert [a["to"] for a in vr.accepted] == ["T001/guild"]
    vr = sdk.verify(root, [{"op": "new_location", "name": "公会"}], reg)
    assert vr.accepted == [] and vr.refused[0].allowed == ["T001/guild"]
    monkeypatch.setattr(s1, "ask", lambda st, qs, **k: {"fits": s1.Answer(type="noul", value=0.05)})
    root, reg = fresh()  # the judge: does not fit
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "地铁站"}], reg)
    assert vr.accepted == [] and "does not make sense" in vr.refused[0].why


def test_player_gate_hands_the_world_an_intent_and_what_the_player_cannot_know(tmp_path, monkeypatch):
    """The model only names what the player names; the engine searches everything the player could have
    met (this playthrough's prose, the world's rumours and lore, the registry's names). Met before → the world should
    land it (emergence); named out of nothing → the world does not make it because it was said."""
    from types import SimpleNamespace

    from neonrp.core import player_gate, system_one as s1

    root = _install(tmp_path)
    reg = load_registry(root)
    assert player_gate.gate(root, reg, "我要讨伐狼人。") is None  # no judge model in tests
    seen = {}

    class Fake:
        def chat(self, msgs):
            seen["user"] = msgs[-1].content
            return SimpleNamespace(message=SimpleNamespace(content=seen.get("answer", "")))

    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: Fake())
    (root / ".neonrp" / "orchestration").mkdir(parents=True, exist_ok=True)
    (root / ".neonrp" / "orchestration" / "main.jsonl").write_text(json.dumps({"turn": 4, "apply": {
        "narration_plain": "补网的老头说:往东两天,河口有个小港,叫雾港。", "options": ["去雾港"], "panels": {}}}, ensure_ascii=False) + "\n", encoding="utf-8")
    seen["answer"] = '{"intent": "去东边河口的小港", "named": ["雾港", "狼人", "会说话的棺材", "吸血鬼"]}'
    g = player_gate.gate(root, reg, "我要去雾港,顺便打听狼人和会说话的棺材。", history=[{"user": "x", "assistant": "墙上写着野兽。[~map]"}])
    src = {x["said"]: x["source"] for x in g["named"]}
    assert src == {"雾港": "第 4 回合", "狼人": None, "会说话的棺材": None}  # 吸血鬼 was never said
    assert "无中生有的(玩家哪里都没见过):\n- 「狼人」\n- 「会说话的棺材」" in g["block"]
    assert "玩家见过的(有出处):\n- 「雾港」(第 4 回合)" in g["block"] and "世界应该让它落地" in g["block"]
    assert "[~map]" not in seen["user"]  # the screen, marks stripped
    (root / "game" / "lore" / "rumors.md").write_text("- 「苔墓那边有个棺材会说话。」", encoding="utf-8")
    g = player_gate.gate(root, load_registry(root), "我要去雾港,顺便打听狼人和会说话的棺材。")
    assert {x["said"]: x["source"] for x in g["named"]}["会说话的棺材"] is None  # not this wording …
    seen["answer"] = '{"intent": "打听", "named": ["棺材会说话"]}'
    assert player_gate.gate(root, load_registry(root), "听说棺材会说话?")["named"][0]["source"] == "传闻"  # … the rumour's words are
    monkeypatch.setattr("neonrp.core.engine_config.get", lambda r, k, d=None: "off" if k == "turn.player_gate" else d)
    assert player_gate.gate(root, reg, "我要讨伐狼人。") is None

def test_town_graph_grows_between_two_places_and_by_new_or_cut_paths(tmp_path):
    """「不仅点上能新增点,还可以两点中间新建新的点,以及在这个点上再新连边」: new_location … between=A,B turns
    A–B into A–X–B (X drawn half-way); link adds a path; unlink cuts one, unless that leaves a place unreachable."""
    root = _install(tmp_path)
    _no_hazards(root)

    def go(line):
        reg = load_registry(root)
        vr = sdk.verify(root, [sdk._adv_line_op(line)], reg)
        sdk.apply(root, vr.accepted, reg, turn=1)
        return vr

    def tm():
        return {n["id"]: n for n in place_tree.level_doc(root, "T001")["nodes"]}

    assert go("new_location 鱼市 between=主街,码头").refused == []
    m = tm()
    assert m["鱼市"]["links"] == ["main_street", "dock"] and "dock" not in m["main_street"]["links"] and m["dock"]["links"] == ["鱼市"]
    xs = sorted([m["main_street"]["pos"]["x"], m["dock"]["pos"]["x"]])
    assert xs[0] - 50 <= m["鱼市"]["pos"]["x"] <= xs[1] + 50
    assert sorted(e.id for e in load_registry(root).exits("T001/鱼市")) == ["T001/dock", "T001/main_street"]
    assert go("unlink 鱼市 码头").refused[0].why.startswith("cutting this road")  # the dock would be cut off
    assert go("link 码头 杂货铺").refused == [] and "shop_general" in tm()["dock"]["links"]
    assert go("unlink 鱼市 码头").refused == [] and tm()["dock"]["links"] == ["shop_general"]
    assert go("link 主街 鱼市").refused[0].why == "these two places are already connected"


def test_player_gate_prompt_is_the_templates_to_change(tmp_path, monkeypatch):
    """The gate is core, its prompt per template / world — prompt spec key player_gate, merged per field."""
    from types import SimpleNamespace

    from neonrp.core import player_gate, system_one as s1

    root = _install(tmp_path)
    seen = {}

    class Fake:
        def chat(self, msgs):
            seen["system"], seen["user"] = msgs[0].content, msgs[-1].content
            return SimpleNamespace(message=SimpleNamespace(content='{"intent": "找人", "named": ["白衣客"]}'))

    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: Fake())
    meta = root / "game" / "meta" / "prompt.json"
    meta.write_text(json.dumps({"player_gate": {"extra": "玩家是穿越者,知道原作里每个人的名字。", "rule": "当作玩家的预知,别让世界照着他说的改。",
                                                "visible_classes": ["job"]}}, ensure_ascii=False), encoding="utf-8")
    g = player_gate.gate(root, load_registry(root), "我找白衣客。")
    assert "穿越者" in seen["system"] and g["block"].endswith("当作玩家的预知,别让世界照着他说的改。")
    assert "随身物品" not in seen["user"] and "本镇委托" in seen["user"]
    assert g["custom"] == ["extra", "rule", "visible_classes"]
    meta.write_text(json.dumps({"player_gate": {"enabled": False}}), encoding="utf-8")
    assert player_gate.gate(root, load_registry(root), "我找白衣客。") is None


def test_new_place_says_its_layer_and_unsure_ones_are_placed_after_the_turn(tmp_path, monkeypatch):
    """A new place states where it sits in the tree (near / between / in / over); in = one layer down,
    entered only through its parent; over = one layer up, taking the group's roads out; roads join one layer. A move to
    a place with no relation hangs it beside the player (the move is async) and the after-turn pass re-hangs it from
    the prose — the engine checks that answer like any other."""
    from types import SimpleNamespace

    from neonrp.core import system_one as s1, worldmap
    from neonrp.packs.rpg.atlas import fix as place_fix

    root = _install(tmp_path)
    _no_hazards(root)

    def go(line, turn=1):
        reg = load_registry(root)
        vr = sdk.verify(root, [sdk._adv_line_op(line) if isinstance(line, str) else line], reg)
        return vr, sdk.apply(root, vr.accepted, reg, turn=turn)

    def tm():
        return {n["id"]: n for n in place_tree.level_doc(root, "T001")["nodes"]}

    go("new_location 公会地下室 in=冒险者公会")
    go("new_location 档案室 in=冒险者公会")
    assert tm()["公会地下室"].get("parent") == "guild" and tm()["公会地下室"]["links"] == []
    reg = load_registry(root)
    assert sorted(e.id for e in reg.exits("T001/公会地下室")) == ["T001/guild"]  # only through the guild
    assert "T001/公会地下室" in [e.id for e in reg.exits("T001/guild")]
    assert go("link 公会地下室 主街")[0].refused[0].why.startswith("these two places are not on one layer")
    assert go("link 公会地下室 档案室")[0].refused == []
    go("new_location 码头区 over=码头,河灯旅店")
    m = tm()
    assert m["dock"]["parent"] == "码头区" and m["inn"]["parent"] == "码头区" and "码头区" in m["main_street"]["links"]
    assert "dock" not in m["main_street"]["links"] and "inn" not in m["main_street"]["links"]
    tree = worldmap.build_map_tree(root)
    assert sorted(tree["nodes"]["T001/guild"]["children"]) == ["T001/公会地下室", "T001/档案室"]
    assert sorted(tree["nodes"]["T001/码头区"]["children"]) == ["T001/dock", "T001/inn"]
    from neonrp.core.turn_settlement import _apply_player_move

    assert _apply_player_move(root, "T001/guild")
    packed = sdk.render_pack(sdk.pack(root, registry=load_registry(root)))
    assert "里面:T001/公会地下室(公会地下室)、T001/档案室(档案室)" in packed  # the here-block shows the layer below
    assert _apply_player_move(root, "T001/公会地下室")
    assert "出去回到:T001/guild(冒险者公会)" in sdk.render_pack(sdk.pack(root, registry=load_registry(root)))
    # a relation that does not draw (two layers) → beside the player, marked for the after-turn pass
    _vr, ar = go("new_location 钟塔 over=码头,冒险者公会")
    assert ar.created[0]["default"] is True and ar.created[0]["relation"] == "near"
    # the move-to-unknown path: no relation → default; the after-turn pass re-hangs it (between gate and main street)
    _vr, ar = go({"op": "move_to", "who": "player", "to": "苔墓小径"}, turn=2)
    assert place_fix.pending(ar.created) == ["T001/苔墓小径"]
    answers = iter(['{"rel": "between", "to": ["北门", "主街"], "why": "出了北门往主街去的半路上"}'])
    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: SimpleNamespace(chat=lambda msgs: SimpleNamespace(message=SimpleNamespace(content=next(answers)))))
    out = place_fix.fix(root, "你出了北门,沿着去主街的半路上那条小径走。", ["T001/苔墓小径"])
    assert out[0]["ok"] is True
    m = tm()
    assert sorted(m["苔墓小径"]["links"]) == ["gate_north", "main_street"] and "main_street" not in m["gate_north"]["links"]
    assert load_registry(root).player_location == "T001/苔墓小径"  # the player stays on the node
    assert _j(root / "game/meta/place_fixes.json")[-1]["rel"] == "between"
    answers = iter(['{"rel": "in", "to": ["不存在的地方"]}'])
    assert place_fix.fix(root, "", ["T001/钟塔"])[0]["ok"] is False  # a wrong answer leaves the default


def test_contract_runs_the_table_with_pacing_and_a_strictness_setting(tmp_path, monkeypatch):
    """Game-master pacing (dull time passes, the clock moves) and the referee's strictness for missing
    things — fair by default (say it is missing, leave a sensible way), strict / lenient by turn.referee.strictness."""
    from neonrp.packs.rpg.contract import contract

    root = _install(tmp_path)
    reg = load_registry(root)
    c = contract(root, reg)
    assert "张弛有度" in c and "就让时间过去" in c and "给一条说得通的路" in c
    real = __import__("neonrp.core.engine_config", fromlist=["get"]).get
    monkeypatch.setattr("neonrp.core.engine_config.get", lambda r, k, d=None: "strict" if k == "turn.referee.strictness" else real(r, k, d))
    c = contract(root, reg)
    assert "不替他找替代" in c and "给一条说得通的路" not in c


def test_solve_turn_with_the_player_gate_on_reaches_the_narrator(tmp_path, fake_adapter, monkeypatch):
    """10-02 regression: a whole turn with the gate answering — the KeyError on the gate's span made every gated turn
    fall back to the old world-agent. The narrator must get the gate block and the turn must stay on v3."""
    from types import SimpleNamespace

    from neonrp.core import system_one as s1

    root = _install(tmp_path)
    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: SimpleNamespace(
        chat=lambda msgs: SimpleNamespace(message=SimpleNamespace(content='{"intent": "去雾港", "named": ["雾港"]}'))))
    a = fake_adapter(['<lines>\n你往东望了望,只有雾。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n回镇上\n</options>'])
    out = turn_v3.solve_turn(root, user_text="我去雾港。", provider=None, turn=1, soul_reports=[])
    assert out["narration"].startswith("你往东望了望")
    assert "无中生有的(玩家哪里都没见过):\n- 「雾港」" in a.calls[0][1].content
    assert any(s.get("actor") == "player_gate" and s.get("unseen") == 1 for s in out["spans"])


def test_define_reads_props_written_as_one_list():
    """10-02 J6: 属性=species:str,mood:str (or species str,hp int across tokens) is the same as species=str mood=str."""
    a = sdk._adv_line_op("define class animal 动物 属性=species:str,mood:str,bond:int mutable=bond,mood")
    b = sdk._adv_line_op("define class animal 动物 属性=species str,bond int mutable=bond")
    assert a["props"] == {"species": "str", "mood": "str", "bond": "int"} and a["mutable"] == ["bond", "mood"] and a["title"] == "动物"
    assert b["props"] == {"species": "str", "bond": "int"} and b["mutable"] == ["bond"]


def test_soul_reads_the_worlds_prose_and_remembers_events_not_prompts(tmp_path, monkeypatch):
    """A soul plays like the player — she reads the world's prose (retold from where she stands, kept in her
    soul folder), the player's beat as she meets it, and her own context; not a block dump. Her own beat's system
    speaks to her as a player; her memory keeps the event, never the prompt. No player bag in her view."""
    from types import SimpleNamespace

    from neonrp.core import light_chat, soul_view, system_one as s1

    root = _install(tmp_path)
    iid = "si-elena0001"
    # after a turn: the narration retold for her (the small model), appended to her soul folder
    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: SimpleNamespace(
        chat=lambda msgs: SimpleNamespace(message=SimpleNamespace(content="你跟着旅人走进公会。赫伦抬头:「新人。登记要报名字和本事。」"))))
    soul_view.write_views(root, narration="你走进公会。艾琳娜跟在你身后。赫伦抬头:「新人。登记要报名字和本事。」", turn=1, iids=[iid], place="冒险者公会")
    assert soul_view.last_views(root, iid) == ["你跟着旅人走进公会。赫伦抬头:「新人。登记要报名字和本事。」"]
    reg = load_registry(root)
    text = soul_view.beat_text(root, reg, iid, seen="旅人走到柜台前,问:「赫伦在吗?」")
    assert text.startswith("你跟着旅人走进公会。") and "旅人走到柜台前,问:「赫伦在吗?」" in text and soul_view.OWN_MARK in text
    assert "旅行黑麦面包" not in text and "# 你眼前" not in text  # the player's bag is not hers; no block dump
    assert soul_view.split_beat(text)[1] == "旅人走到柜台前,问:「赫伦在吗?」"
    # her own beat: the system speaks to her as a player, from her soul folder; memory keeps the event
    seen = {}
    monkeypatch.setattr(light_chat, "_adapter", lambda root_: SimpleNamespace(chat=lambda msgs: (seen.setdefault("sys", msgs[0].content), SimpleNamespace(message=SimpleNamespace(content="「艾琳娜。止血、认药草。」")))[1]))
    r = light_chat.ask_soul_deliver(root, iid, text, beat={"event": "旅人走到柜台前,问:「赫伦在吗?」"})
    assert r["ok"] and "和玩家一样,是在这个世界里玩的一个人" in seen["sys"] and "主持人(world-agent)就当前剧情向你转达" not in seen["sys"]
    ev = _j(next((root / "souls").glob(f"*-{iid}")) / "short-term-memo" / "recent_events.json")["events"][-1]
    assert ev["event"] == "旅人走到柜台前,问:「赫伦在吗?」" and ev["my_reaction"].startswith("我:「艾琳娜") and "你眼前" not in ev["event"]


def _talk_until_told(root: Path) -> None:
    """Private 2cd1fa4 (10-15): the player's own check, once agreed and not a question he asked, ends the talk by itself
    (player:check-agreed). The talk tests below are about a talk that goes on until 定 — that rule off for them."""
    from neonrp.core.paths import get_data_dir_name

    eng = root / get_data_dir_name(root) / "meta" / "engine.json"
    eng.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(eng.read_text(encoding="utf-8")) if eng.exists() else {}
    cfg.setdefault("turn", {})["plan_loop_check_agreed_advances"] = False
    eng.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
def _old_talk_rule(root):
    """Turn off 10-15's 「the player's action with its check agreed goes to the Resolve」 for a run (game/meta/engine.json)."""
    p = Path(root) / "game" / "meta" / "engine.json"
    have = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    have.setdefault("turn", {})["plan_loop_check_agreed_advances"] = False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(have, ensure_ascii=False), encoding="utf-8")


def test_plan_loop_talks_without_landing_then_resolves_once(tmp_path, fake_adapter, monkeypatch):
    """先商量、后清算: a Planning beat (the world hosts, hands the mic, keeps a plan board) writes nothing
    to the world; 「定」 resolves once through the five-phase turn, with the board as the narrator's brief."""
    import hashlib

    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    _talk_until_told(root)
    soul = next(e for e in load_registry(root).of_class("soul"))
    hosts = iter([
        f"<lines>\n杂货铺就在主街,药水 8 银。\n</lines>\n<mic>\n{soul.name}: 他要卖掉罩灯,你怎么看?\n</mic>\n<board>\n玩家: 买药、卖灯\n</board>\nnext: wait",
        "<lines>\n她不同意卖灯。你:① 照原计划 ② 只买药\n</lines>\n<board>\n玩家: 只买药\n检定: 交涉 DC10(砍价)\n</board>\nnext: propose",
    ])
    monkeypatch.setattr(plan_loop, "host_again", lambda *a, **k: 0.9)  # 10-14: System One says the host must speak again
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(hosts))
    asked = []
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: (asked.append((iid, q)), {"ok": True, "answer": "<lines>\n「灯卖了晚上拿什么照路?」\n</lines>\n<draft>反对卖灯,去砍价</draft>"})[1])

    def files() -> dict[str, str]:
        g = root / "game"
        return {str(p.relative_to(g)): hashlib.sha1(p.read_bytes()).hexdigest() for p in g.rglob("*") if p.is_file()}

    before = files()
    res = ConversationSession(root, "test-agent", mode="play").send("我去杂货铺,买药,顺便把罩灯卖了。")
    assert res.success and res.route_decision == "plan_loop:plan"
    assert files() == before  # nothing landed while talking
    assert asked and asked[0][0] == soul.id and "他要卖掉罩灯" in asked[0][1]
    tr = read_turn_traces(root, "main", last=1)[0]
    beat = tr["apply"]["beat"]
    assert beat["kind"] == "plan" and beat["mic"] == [soul.id] and beat["board"][soul.name] == "反对卖灯,去砍价"
    assert beat["checks"][0]["text"] == "交涉 DC10(砍价)" and beat["checks"][0]["attr"] == "CHA" and beat["checks"][0]["dc"] == "10"
    assert beat["rolled"] == []  # agreed, not rolled
    assert "灯卖了晚上拿什么照路" in res.assistant_message and plan_loop.load(root)["proposed"] is True
    # 「定」 → the Resolve: one five-phase turn, the board is the narrator's brief, the talk is consumed
    a = fake_adapter(['<lines>\n你买下药水,灯留着。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n回公会\n</options>'])
    res2 = ConversationSession(root, "test-agent", mode="play").send("定。")
    assert res2.success and res2.route_decision != "plan_loop:plan"
    brief = a.calls[0][1].content
    assert "# 谈定的计划" in brief and "玩家:只买药" in brief and "检定:交涉 DC10(砍价)" in brief
    assert "# 检定结果(引擎已经按人物卡掷过" in brief  # the engine rolled the agreed check before the narrator wrote
    tr2 = read_turn_traces(root, "main", last=1)[0]
    assert tr2["apply"]["beat"]["kind"] == "resolve" and tr2["apply"]["beat"]["advanced_by"] == "player"
    assert tr2["apply"]["beat"]["rolled"] and "1d20" in tr2["apply"]["beat"]["rolled"][0]
    assert plan_loop.load(root) == {}


def test_plan_loop_at_world_gm_dm_advance_and_at_name_hands_the_mic(tmp_path, monkeypatch):
    """@world / @gm / @dm / @世界 are one effect — a call, not a switch: the host takes one round decisively,
    asks no one else, and advances or names what is still open; @<character> hands her the mic first, whatever the host
    chose; a character's @dm is a call too (the wrap-up is the host's decisive round)."""
    from neonrp.core import plan_loop

    for t in ("@world 我踢了", "@GM 动手", "@dm", "@世界 出发", "＠Dm 走"):
        assert plan_loop.wants_advance(t), t
    assert not plan_loop.wants_advance("@艾琳娜 你怎么看") and not plan_loop.wants_advance("我想去 world 那边")
    assert plan_loop.mentions("@艾琳娜 你怎么看?@罗文", {"艾琳娜": "si-e", "罗文": "si-r"}) == ["si-e", "si-r"]

    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.parent == reg.player_location)
    seen: list[str] = []
    asked = []
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: (asked.append(iid), {"ok": True, "answer": "<lines>\n「嗯。」\n</lines>"})[1])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (seen.append(user), "<lines>\n踢吧,鱼篓就在脚边。\n</lines>\n"
                        f"<mic>\n{elena.name}: 你拦不拦?\n</mic>\n<board>\n玩家: 把鱼篓踢翻\n</board>\nnext: advance")[1])
    out = plan_loop.step(root, user_text="@dm 我把鱼篓踢翻", last_narration="x")
    assert out["kind"] == "resolve" and out["advanced_by"] == "player" and "鱼篓踢翻" in json.dumps(out["board"], ensure_ascii=False)
    assert asked == [] and "果断接这一轮" in seen[-1] and "鱼篓就在脚边" in out["plan_beat"]["narration"]  # it asked no one
    plan_loop.clear(root)
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n你还没说踢谁的。\n</lines>\n"
                        f"<mic>\n{elena.name}: 你拦不拦?\n</mic>\nnext: wait")
    out = plan_loop.step(root, user_text="@dm 我踢", last_narration="x")
    assert out["kind"] == "plan" and asked == [] and out["beat"]["dm_called"] == "player"  # not 100%: the host said what is open
    plan_loop.clear(root)

    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n北门的雾很重。\n</lines>\nnext: wait")
    asked.clear()
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: (asked.append(iid), {"ok": True, "answer": "<lines>\n「走吧。」\n</lines>\n<draft>跟上</draft>"})[1])
    out = plan_loop.step(root, user_text=f"@{elena.name} 你怎么看?", last_narration="")
    assert out["kind"] == "plan" and asked == [elena.id] and out["beat"]["mic"] == [elena.id]  # the host named no one; the player did
    plan_loop.clear(root)
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: {"ok": True, "answer": "<lines>\n「我先去了。」\n</lines>\n<draft>先去码头</draft>\n@dm"})
    monkeypatch.setattr(plan_loop, "settled", lambda *a, **k: None)
    out = plan_loop.step(root, user_text=f"@{elena.name} 我们去码头?", last_narration="")
    assert out["kind"] == "plan" and out["beat"]["dm_called"] == f"soul:{elena.id}"  # the host's wrap said wait
    plan_loop.clear(root)
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n她先去码头。\n</lines>\nnext: advance")
    out = plan_loop.step(root, user_text=f"@{elena.name} 我们去码头?", last_narration="")
    assert out["kind"] == "resolve" and out["advanced_by"] == f"soul:{elena.id}" and out["board"][elena.name] == "先去码头"


def test_plan_loop_a_bare_walk_in_town_still_goes_through_the_host(tmp_path):
    """Every line enters Planning first — 「我去码头。」 reaches the host with a hint that it is a bare walk;
    the host decides (here: nothing to talk over → advance). A walk with more in it gets no hint."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    reg = load_registry(root)
    assert plan_loop.trivial_walk(reg, "我去码头。") == "T001/dock" and plan_loop.trivial_walk(reg, "去冒险者公会") == "T001/guild"
    assert plan_loop.trivial_walk(reg, "我去杂货铺,买一瓶药") is None and plan_loop.trivial_walk(reg, "我去雾港") is None
    # not a bypass: the host still hears it (with the hint) and decides — here it says there is nothing to talk over
    seen = {}
    import neonrp.core.plan_loop as _plm
    orig = _plm._host
    _plm._host = lambda root_, system, user: (seen.setdefault("user", user), "<lines>\n码头就在河边。\n</lines>\nnext: advance")[1]
    try:
        out = plan_loop.step(root, user_text="我去码头。", last_narration="")
    finally:
        _plm._host = orig
    assert "只是镇内走动" in seen["user"] and out["kind"] == "resolve" and out["advanced_by"] == "world:trivial"


def test_plan_loop_naming_her_or_her_alone_hands_her_the_mic(tmp_path, monkeypatch):
    """10-03 PL1: 「让她去砍价」 with only her present (or her name without @) hands her the mic — the host may not
    settle her part for her."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    reg = load_registry(root)
    here = [e for e in reg.of_class("soul") if e.parent == reg.player_location]
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n老苇等着。\n</lines>\nnext: wait")
    asked = []
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: (asked.append(iid), {"ok": True, "answer": "<lines>\n「我来。」\n</lines>\n<draft>去砍价</draft>"})[1])
    if len(here) == 1:
        out = plan_loop.step(root, user_text="只买药,让她去砍价。", last_narration="")
        assert asked == [here[0].id] and out["beat"]["board"][here[0].name] == "去砍价"
    plan_loop.clear(root)
    asked.clear()
    plan_loop.step(root, user_text=f"让{here[0].name}去跟老板说。", last_narration="")
    assert asked[:1] == [here[0].id]


def test_plan_loop_checks_are_agreed_as_data_and_rolled_by_the_engine_at_resolve(tmp_path):
    """「艾琳娜 CHA 难度 10 压药价 怎么进引擎」: a check talked over is parsed into {who, attr, dc | vs, why};
    at Resolve the engine rolls it by the sheet (rpg roll_check, seeded) and hands the result to the narrator."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul"))
    who = {elena.name: elena.id, "玩家": "player", "旅人": "player"}
    c1 = plan_loop.parse_check(f"{elena.name} CHA 难度 10(为了把药水压到六金)", who)
    assert c1["who"] == elena.id and c1["attr"] == "CHA" and c1["dc"] == "10" and c1["why"] == "为了把药水压到六金"
    c2 = plan_loop.parse_check(f"旅人 vs {elena.name} 力量 甩开她", who)
    assert c2["who"] == "player" and c2["vs"] == elena.id and c2["attr"] == "STR"
    c3 = plan_loop.parse_check("玩家 INT normal 雾里认路", who)
    assert c3["dc"] == "normal" and c3["attr"] == "INT"
    r = plan_loop.roll_checks(root, reg, [c1, c2, c3], seed="7")
    assert r == plan_loop.roll_checks(root, reg, [c1, c2, c3], seed="7")  # the same plan rolls the same numbers
    # 10-14: the number the host wrote reads as the nearest tier (10: halfway between easy 8 and normal 12 → the harder)
    assert r[0]["dc"] == 12 and r[0]["tier"] == "normal<-10" and r[0]["result"] in ("success", "fail") and "b" in r[1] and isinstance(r[2]["dc"], int)
    p_int = (reg.entries["player"].props.get("attributes") or {}).get("int")
    assert r[2]["a"]["mod"] == (int(p_int) - 5 if p_int is not None else 0)  # the sheet decides the modifier
    out = {"board": {"玩家": "只买药"}, "checks": [c1], "rolled": [{**r[0], "line": plan_loop.check_line(reg, r[0])}]}
    brief = plan_loop.resolve_facts(out)
    assert "# 检定结果(引擎已经按人物卡掷过" in brief and f"{elena.name} CHA 5(规则基线) 1d20" in brief and ("成功" in brief or "失败" in brief)


def test_plan_loop_two_planning_beats_in_a_row_and_no_check_means_none(tmp_path, monkeypatch):
    """10-03 run 3: the second Planning beat crashed rendering structured checks (and fell through to a plain turn
    that landed); 「检定: 无(…)」 was taken for a check and rolled."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    _talk_until_told(root)
    hosts = iter(["<lines>\n老苇报价。\n</lines>\n<board>\n玩家: 买药\n检定: 玩家 CHA 10 还价\n</board>\nnext: wait",
                  "<lines>\n他等你开口。\n</lines>\n<board>\n玩家: 只买药\n检定: 无(还没到要掷的事)\n</board>\nnext: propose"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(hosts))
    a = plan_loop.step(root, user_text="我买药,顺便还还价。", last_narration="")
    b = plan_loop.step(root, user_text="算了不还价。", last_narration="")
    assert a["kind"] == b["kind"] == "plan"
    assert [c["text"] for c in b["beat"]["checks"]] == ["玩家 CHA 10 还价"]  # 「无」 kept the agreed check, added none
    assert plan_loop.parse_check("无(还没到要掷的事)", {}) and not plan_loop._board("<board>\n检定: 无\n</board>")[1]


def test_plan_loop_the_players_own_agreed_check_ends_the_talk_unless_he_asked(tmp_path, monkeypatch):
    """Private 2cd1fa4 (niko 10-15, 「对温妮使用心理学」): the player's own action, its check agreed this beat and not a
    question he asked, is settled for him — straight to the resolve (player:check-agreed), the check on the board.
    A question keeps the talk going; the rule is a knob (turn.plan_loop_check_agreed_advances)."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    host = "<lines>\n老苇报价。\n</lines>\n<board>\n玩家: 买药\n检定: 玩家 CHA 10 还价\n</board>\nnext: wait"
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: host)
    out = plan_loop.step(root, user_text="我买药,顺便还还价。", last_narration="x")
    assert out["kind"] == "resolve" and out["advanced_by"] == "player:check-agreed"
    assert [c["text"] for c in out["checks"]] == ["玩家 CHA 10 还价"] and out["plan_beat"]["beat"]["ended_by"] == "player:check-agreed"
    plan_loop.clear(root)
    out = plan_loop.step(root, user_text="能还价吗?", last_narration="x")
    assert out["kind"] == "plan"  # he asked: the host answered, the talk goes on
    plan_loop.clear(root)
    _talk_until_told(root)
    assert plan_loop.step(root, user_text="我买药,顺便还还价。", last_narration="x")["kind"] == "plan"


def test_plan_loop_an_opposed_action_with_nothing_to_roll_gets_its_contest_by_the_gap_judge(tmp_path, monkeypatch):
    """Private e176151 (niko 10-15, rules-1014 C1: he drew on the crowd, she stood in the way, the host asked him again
    three beats running): someone else on the board, no check agreed — the gap judge decides. Yes: the host sets the
    contest in one more call and the talk goes to the resolve (player:contest). No: the talk stays, no extra call."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.parent == reg.player_location)
    systems: list[str] = []

    def host(root_, system, user):
        systems.append(user)
        if "切到清算之前" in user:  # the contest round
            return f"<lines>\n要掷对抗。\n</lines>\n<board>\n对抗: 玩家 vs {elena.name} 力量 冲出门\n</board>\nnext: advance"
        return f"<lines>\n{elena.name}挡在门口。\n</lines>\n<board>\n玩家: 冲出门\n{elena.name}: 拦住他\n</board>\nnext: wait"

    monkeypatch.setattr(plan_loop, "_host", host)
    monkeypatch.setattr(plan_loop, "settled", lambda *a, **k: None)
    gaps: list[dict] = []
    monkeypatch.setattr(plan_loop, "check_gap", lambda root_, board, checks, talk, present=None: (gaps.append(dict(board)), 0.9)[1])
    out = plan_loop.step(root, user_text="我冲出门去。", last_narration="x")
    assert gaps and elena.name in gaps[0]
    assert out["kind"] == "resolve" and out["advanced_by"] == "player:contest" and len(systems) == 2
    assert out["checks"][0]["who"] == "player" and out["checks"][0]["vs"] == elena.id
    plan_loop.clear(root)
    systems.clear()
    monkeypatch.setattr(plan_loop, "check_gap", lambda *a, **k: 0.1)
    out = plan_loop.step(root, user_text="我冲出门去。", last_narration="x")
    assert out["kind"] == "plan" and len(systems) == 1 and out["beat"]["check_gap"] == 0.1


def test_tool_watch_every_tool_call_tells_watchers_its_name_args_and_result(tmp_path):
    """Every tool call is bound to a watcher — after the call, an outside function is triggered with the
    tool's name (a dice animation for ``dice``…). Plan checks and the referee roll through the same [dice] tool."""
    from neonrp.core import ledger, plan_loop, tool_watch

    root = _install(tmp_path)
    reg = load_registry(root)
    seen_dice, seen_all = [], []
    off1 = tool_watch.watch(seen_dice.append, tools="dice")
    off2 = tool_watch.watch(seen_all.append)
    off3 = tool_watch.watch(lambda ev: 1 / 0)  # a broken watcher never breaks the turn
    try:
        r = tool_watch.call(root, reg, "dice", "neonrp.packs.rpg.tools:dice", {"dice": "1d20+2", "vs": 12, "reason": "撬锁"}, seed="t1")
        assert r["ok"] and seen_dice[-1]["tool"] == "dice" and seen_dice[-1]["source"] == "narrator"
        assert seen_dice[-1]["args"]["reason"] == "撬锁" and seen_dice[-1]["result"]["rolls"] == r["rolls"] and "passed" in seen_dice[-1]["result"]
        elena = next(e for e in reg.of_class("soul"))
        plan_loop.roll_checks(root, reg, [plan_loop.parse_check(f"{elena.name} CHA 10 砍价", {elena.name: elena.id})], seed="7")
        assert seen_dice[-1]["source"] == "plan" and seen_dice[-1]["args"]["who"] == elena.id and seen_dice[-1]["args"]["attr"] == "CHA"
        tool_watch.call(root, reg, "map", "neonrp.packs.rpg.atlas.draw:draw_map", {}, seed="t1")
        assert [e["tool"] for e in seen_all] == ["dice", "dice", "map"] and len(seen_dice) == 2
        assert [e["payload"]["tool"] for e in ledger.events(root, type="tool.ran")] == ["dice", "dice", "map"]
    finally:
        off1()
        off2()
        off3()
    tool_watch.call(root, reg, "dice", "neonrp.packs.rpg.tools:dice", {"dice": "1d6"}, seed="t2")
    assert len(seen_dice) == 2  # unwatched


def test_plan_loop_host_reads_real_data_instead_of_inventing_it(tmp_path, monkeypatch):
    """10-03 run 4: the host quoted prices the narrator then contradicted — it never saw the price list. The host gets
    the narrator's price hints, and [read 名字] reads an entry's own record to it (private to the world), then it writes on."""
    from neonrp.core import plan_loop, tool_watch

    root = _install(tmp_path)
    seen, calls = [], []
    off = tool_watch.watch(seen.append, tools="read")

    def host(root_, system, user):
        calls.append(user)
        if len(calls) == 1:
            return "<lines>\n我先看看那家店。\n</lines>\n[read 杂货铺]\nnext: wait"
        return "<lines>\n杂货铺的药水按价目卖。\n</lines>\n<board>\n玩家: 买药\n</board>\nnext: propose"

    monkeypatch.setattr(plan_loop, "_host", host)
    try:
        out = plan_loop.step(root, user_text="我想去杂货铺买瓶药。", last_narration="")
    finally:
        off()
    assert out["kind"] == "plan" and out["beat"]["reads"] == ["杂货铺"] and len(calls) == 2
    assert "# 你读到的(只有你知道" in calls[1] and "shop_general" in calls[1]  # the shop's own record reached the host
    assert seen and seen[0]["tool"] == "read" and seen[0]["source"] == "host"
    assert "杂货铺的药水按价目卖" in out["narration"] and "[read" not in out["narration"]


def test_plan_loop_talk_takes_time_and_outside_events_do_not_wait(tmp_path, monkeypatch):
    """10-03 rules 2 and 4: talking runs a clock (the host is told, and past the limit it should propose; the Resolve
    counts it); a fight already running or a road stop not yet settled does not wait for the talk."""
    from neonrp.core import modes, plan_loop
    from neonrp.packs.rpg import travel

    root = _install(tmp_path)
    users = []
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (users.append(user), "<lines>\n嗯。\n</lines>\nnext: wait")[1])
    for _ in range(11):
        plan_loop.step(root, user_text="我们再商量商量。", last_narration="")
    assert plan_loop.load(root)["talk_min"] == 22 and "谈得够久了,该提议推进了" in users[-1]
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n走。\n</lines>\nnext: advance")
    out = plan_loop.step(root, user_text="@dm 走", last_narration="")
    assert out["talk_min"] == 22 and "商量用了大约 22 分钟" in plan_loop.resolve_facts(out)
    plan_loop.clear(root)
    reg = load_registry(root)
    from neonrp.packs.rpg import combat
    combat.write(root, {**combat.spawn(root, reg, note="山贼冲上来了", turn=3), "at": reg.player_location})
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n你打算怎么打?\n</lines>\nnext: wait")
    out = plan_loop.step(root, user_text="我们先商量一下怎么打?", last_narration="")
    assert out["kind"] == "plan", "D-20261018: a fight under way is talked over like any beat — each says what they do"
    combat.write(root, None)
    monkeypatch.setattr(travel, "journey", lambda root_: {"pending": {"tag": "bandits"}, "from": "T001", "to": "T002"})
    out = plan_loop.step(root, user_text="我们绕路吧?", last_narration="")
    assert out["kind"] == "resolve" and out["advanced_by"] == "event:road_stop"


def test_plan_loop_opening_is_long_the_talk_after_it_is_short(tmp_path, monkeypatch):
    """The first host line of a playthrough is the opening — long, it sets the scene; every talk turn after
    it is 1–3 sentences."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    long_text = "。".join(f"第{i}句" for i in range(1, 9)) + "。"
    seen = []
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (seen.append(user), f"<lines>\n{long_text}\n</lines>\nnext: wait")[1])
    a = plan_loop.step(root, user_text="我看看四周。", last_narration="")
    assert "这是这一局的开场" in seen[0] and a["narration"].count("。") == 8
    b = plan_loop.step(root, user_text="那我去公会。", last_narration="")
    assert "这是这一局的开场" not in seen[1] and b["narration"].count("。") == 3


def test_plan_loop_settles_by_the_judge_without_asking_ding(tmp_path, monkeypatch):
    """Asking 「就这么定?」 every beat is silly — when everyone's part is clear the judge says so and the
    beat resolves at once (the player sees the talk, then what happened); unclear → keep talking; no judge → as before."""
    from types import SimpleNamespace

    from neonrp.core import plan_loop, system_one as s1

    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.parent == reg.player_location)
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n公会在主街那头,不花钱。\n</lines>\n"
                        f"<mic>\n{elena.name}: 一起走?\n</mic>\n<board>\n玩家: 去公会\n</board>\nnext: wait")
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: {"ok": True, "answer": "<lines>\n「顺路,一起走。」\n</lines>\n<draft>一起去公会</draft>"})
    out = plan_loop.step(root, user_text="我去公会。", last_narration="x")  # no judge in tests → keeps talking
    assert out["kind"] == "plan"
    plan_loop.clear(root)
    asked = {}
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: (asked.update(state), {"settled": SimpleNamespace(yes=0.9)})[1])
    out = plan_loop.step(root, user_text="我去公会。", last_narration="x")
    assert out["kind"] == "resolve" and out["advanced_by"] == "judge:settled" and out["settled"] == 0.9
    assert "顺路,一起走" in out["plan_beat"]["narration"] and out["plan_beat"]["beat"]["kind"] == "plan"  # two records
    assert "beat" in out and "script" not in out["beat"] and asked["board"] == {"玩家": "去公会", elena.name: "一起去公会"}
    plan_loop.clear(root)
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: {"settled": SimpleNamespace(yes=0.2)})
    assert plan_loop.step(root, user_text="我去公会。", last_narration="x")["kind"] == "plan"


def test_plan_loop_urges_after_n_beats_but_never_forces(tmp_path, monkeypatch):
    """A long talk is not cut (people get carried away) — after N beats the host urges, it does not resolve."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    seen: list[str] = []

    def host(root_, system, user):
        seen.append(user)
        return "<lines>\n嗯。\n</lines>\n<board>\n玩家: 去码头\n</board>\nnext: wait"

    monkeypatch.setattr(plan_loop, "_host", host)
    monkeypatch.setattr(plan_loop, "settled", lambda *a, **k: None)
    outs = [plan_loop.step(root, user_text=f"再想想{n}。", last_narration="x") for n in range(5)]
    assert [o["kind"] for o in outs] == ["plan"] * 5
    assert [o["beat"]["nudged"] for o in outs] == [False, False, True, True, True]
    assert "劝一劝" not in seen[0] and "劝一劝" in seen[2]


def test_a_grown_place_can_be_patched_later(tmp_path):
    """10-03 llm6 PL4: a place grown in one turn pointed at its folder; patching it the next turn opened the folder for
    writing (IsADirectoryError) and the whole Resolve patch was lost."""
    from neonrp.core import sdk

    root = _install(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "new_location", "name": "雾中洼地", "parent": "gate_north", "links": ["gate_north"]}], reg)
    sdk.apply(root, vr.accepted, reg, turn=3)
    reg = load_registry(root)
    env = next(e for e in reg.of_class("place") if e.name == "雾中洼地")
    assert (root / env.source.partition("#")[0]).is_file()
    ar = sdk.apply(root, [{"op": "patch", "who": env.id, "props": {"trampled": "石南被踩倒了一片"}}], reg, turn=4)
    assert ar.applied and ar.applied[0]["op"] == "patch" and not ar.refused
    assert "石南被踩倒了一片" in (root / env.source.partition("#")[0]).read_text(encoding="utf-8")  # landed in its file


def test_planning_and_resolve_are_two_agent_loops_two_records(tmp_path, fake_adapter, monkeypatch):
    """商量拍是一种 agent loop,清算拍是另一种. The Planning loop calls its tools ([read], <mic>) round by round
    and decides when to hand back; when the talk settles, that Planning beat is recorded on its own (no choices left in
    it) and the Resolve beat — the direct-output loop — runs as a second record with no mic and no talk in it."""
    from types import SimpleNamespace

    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop, system_one as s1
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    _old_talk_rule(root)  # this test is about the talk itself: a check agreed does not end it (the 10-15 switch off)
    from neonrp.core import plan_loop as _pl

    monkeypatch.setattr(_pl, "host_again", lambda *a, **k: 1.0)  # S1 is off here; 2cd1fa4: no judge = no second host round
    soul = next(e for e in load_registry(root).of_class("soul"))
    seen: list[str] = []
    rounds = iter([
        f"<lines>\n去杂货铺,一刻钟。\n</lines>\n<mic>\n{soul.name}: 他要你帮着砍价,你来吗?\n</mic>\n<board>\n玩家: 买药\n</board>\nnext: wait",
        # private 1399570 (10-19): a host line that asks the player (a ? or a ①②③ menu) hands the talk back — it is not
        # settled for him; this talk ends on a plain line, so the judge settles it
        "<lines>\n她来砍价,就这么去。\n</lines>\n<board>\n检定: 玩家 CHA 10 砍价\n</board>\nnext: wait",
    ])
    monkeypatch.setattr(plan_loop, "host_again", lambda *a, **k: 0.9)  # 10-14: System One says the host must speak again
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (seen.append(user), next(rounds))[1])
    soul_asks = []
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: (soul_asks.append(kw.get("beat")),
                                                     {"ok": True, "answer": "<lines>\n「行,我来砍。」\n</lines>\n<draft>帮着砍价</draft>"})[1])
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: {"settled": SimpleNamespace(yes=0.9)})
    # the narrator asks for her (`need`) in the Resolve: she carries out her part
    fake_adapter([f'老苇让了一金,你买下药水。\n⟦STATE⟧\nneed {soul.name}\n⟦/STATE⟧',
                  '老苇让了一金,你买下药水。\n⟦STATE⟧\n⟦/STATE⟧'])
    res = ConversationSession(root, "test-agent", mode="play").send("去杂货铺买药,让她帮我砍价。")
    assert res.success and "老苇让了一金" in res.assistant_message and "行,我来砍" not in res.assistant_message
    assert "## 工具结果" not in seen[0] and f"{soul.name} 回话" in seen[1]  # round 2 saw the mic's result
    plan_tr, resolve_tr = read_turn_traces(root, "main", last=2)
    pb, rb = plan_tr["apply"]["beat"], resolve_tr["apply"]["beat"]
    assert pb["kind"] == "plan" and pb["rounds"] == 2 and pb["mic"] == [soul.id] and pb["ended_by"] == "judge:settled"
    assert "行,我来砍" in plan_tr["apply"]["narration_plain"] and "①" not in plan_tr["apply"]["narration_plain"]
    assert rb["kind"] == "resolve" and rb["advanced_by"] == "judge:settled" and "script" not in rb and not rb.get("mic")
    assert rb["rolled"] and "1d20" in rb["rolled"][0]  # the agreed check, rolled in the Resolve loop
    # asked once in the talk (what she thinks), once in the Resolve (to carry it out) — two ways of asking, one character
    assert [a["event"][:2] for a in soul_asks] == ["商量", "执行"]


def test_the_opening_is_the_worlds_own_and_a_talked_resolve_asks_no_one(tmp_path, monkeypatch):
    """「主持的第一句应该是主持的开场」 — the start cue gets the world's authored opening (game-start.json) as
    its own beat, no LLM; and a Resolve from the talk has no character rounds (no ask_soul from the narrator's `need`)."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    gs = root / "game" / "meta" / "game-start.json"
    gs.parent.mkdir(parents=True, exist_ok=True)
    gs.write_text(json.dumps({"startup": {"opening_scene": "雾压在驿路上。你看见一扇歪斜的木栅门。", "opening_choices": ["和守门人说话", "走向镇中央"]}},
                             ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(plan_loop, "_host", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM for the opening")))
    out = plan_loop.step(root, user_text="开始游戏", last_narration="")
    assert out["kind"] == "plan" and out["beat"]["kind"] == "opening"
    assert out["narration"].startswith("雾压在驿路上") and "① 和守门人说话" in out["narration"]
    assert plan_loop.load(root).get("opened")
    seen = []
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (seen.append(user), "<lines>\n守门人在门房。\n</lines>\nnext: wait")[1])
    plan_loop.step(root, user_text="我去和守门人说话。", last_narration=out["narration"])
    assert "这是这一局的开场" not in seen[0]  # the host does not make up a second opening


def test_a_resolve_from_the_talk_asks_her_to_carry_out_her_part(tmp_path, fake_adapter, monkeypatch):
    """「砍价那段效果其实很好」 — the Resolve may still call on a character (`need`), but to *carry out* what
    she agreed (her own beat, her board line, the dice that concern her), not to talk it over again; at most twice."""
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    soul = next(e for e in load_registry(root).of_class("soul"))
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user:
                        f"<lines>\n走。\n</lines>\n<board>\n玩家: 买药\n{soul.name}: 去跟老板压价\n</board>\nnext: advance")
    asks = []
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: (asks.append((iid, q, kw.get("beat"))), {"ok": True, "answer": "「九金。」"})[1])
    fake_adapter([f"老板报十一金。\n⟦STATE⟧\nneed {soul.name}\n⟦/STATE⟧"] * 3 + ["老板让到九金。\n⟦STATE⟧\n⟦/STATE⟧"])
    ConversationSession(root, "test-agent", mode="play").send("@dm 买药")
    tr = read_turn_traces(root, "main", last=1)[0]
    assert tr["apply"]["beat"]["kind"] == "resolve" and 1 <= len(asks) <= 2
    iid, q, beat = asks[0]
    assert iid == soul.id and beat and beat["event"].startswith("执行") and "去跟老板压价" in q and "这是清算" in q
    assert "老板报十一金" in q  # she acts on the scene as written so far

def test_plan_loop_never_says_a_tool_call_at_the_table(tmp_path, monkeypatch):
    """10-03 llm10 PL2: the host put 「[read T001/guild]」 inside <lines> — the player saw the tool call."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    outs = iter(["<lines>\n[read 杂货铺]\n</lines>\nnext: wait", "<lines>\n药水 12 金。\n</lines>\nnext: wait"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(outs))
    out = plan_loop.step(root, user_text="杂货铺卖什么?", last_narration="x")
    assert out["beat"]["reads"] == ["杂货铺"] and "[read" not in out["narration"] and "药水 12 金" in out["narration"]


def test_agreed_checks_show_as_dice_lines_the_tui_highlights(tmp_path):
    """「没有渲染,我根本不知道这里是否用了骰子」 — the Resolve opens with one fixed dice line per agreed check,
    in the skeleton the TUI already colours (ConversationView._DICE_LINE_RE); a contest targets the other side's total."""
    from neonrp.core import plan_loop
    from neonrp.tui.app import ConversationView

    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul"))
    lines = plan_loop.dice_lines(reg, [
        {"a": {"who": elena.id, "roll": 13, "mod": 2, "total": 15}, "dc": 12, "attr": "CHA", "why": "压药价", "result": "success"},
        {"a": {"who": "player", "roll": 5, "mod": 2, "total": 7}, "b": {"who": elena.id, "roll": 11, "mod": 0, "total": 11},
         "attr": "DEX", "why": "挤过去", "result": "fail"}])
    assert lines == [f"[{elena.name} CHA(压药价): 13+2=15 >= 12] → 成功", f"[{reg.entries['player'].name if 'player' in reg.entries else '玩家'} DEX 对 {elena.name}(挤过去): 5+2=7 < 11] → 失败"]
    assert all(ConversationView._DICE_LINE_RE.match(x) for x in lines)


def test_player_gate_takes_world_facts_the_player_states_as_attempts(tmp_path, monkeypatch):
    """10-03 suite B4: 「我进镇的时候天已经黑了」 moved the clock 08:30 → 21:40. The gate lists what the player states as a
    world fact (time, weather, others' answers) — only words they really used — and tells the world (and the planning
    host) it is their account, not the fact; the player's own actions are not claims."""
    from types import SimpleNamespace

    from neonrp.core import plan_loop, player_gate, system_one as s1

    root = _install(tmp_path)
    reg = load_registry(root)
    answer = {"v": '{"intent": "进镇", "named": [], "claims": ["天已经黑了", "门卫答应放行"], "seen": "旅人走向镇门。"}'}

    class Fake:
        def chat(self, msgs):
            return SimpleNamespace(message=SimpleNamespace(content=answer["v"]))

    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: Fake())
    g = player_gate.gate(root, reg, "我进镇的时候天已经黑了。")
    assert g["claims"] == ["天已经黑了"]  # 「门卫答应放行」 was never said
    assert "玩家替世界说了算的" in g["block"] and "- 「天已经黑了」" in g["block"] and "时间只因为有人做了花时间的事才过去" in g["block"]
    answer["v"] = '{"intent": "等到天黑", "named": [], "claims": [], "seen": "旅人在门边坐下。"}'
    assert not player_gate.gate(root, reg, "我在门边等到天黑。")["claims"]  # waiting is an action, not a claim
    seen = []
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (seen.append(user), "<lines>\n雾还没散。\n</lines>\nnext: wait")[1])
    plan_loop.step(root, user_text="我进镇的时候天已经黑了。", last_narration="x", gate=g)
    assert "- 「天已经黑了」" in seen[0]  # the planning host plans with it as the player's account


def test_before_the_switch_an_unchecked_contest_gets_its_check(tmp_path, monkeypatch):
    """10-03 suite N3 / PL1: a fight and a haggle reached the Resolve with nothing to roll. Before switching, the judge is
    asked whether something uncertain or opposed has no check; yes → one more host round sets it (no word list)."""
    from types import SimpleNamespace

    from neonrp.core import plan_loop, system_one as s1

    root = _install(tmp_path)
    outs = iter(["<lines>\n那就去后巷。\n</lines>\n<board>\n玩家: 跟码头工人在后巷比试\n</board>\nnext: advance",
                 "<lines>\n这一架得掷:你 STR 对他 STR。\n</lines>\n<board>\n对抗: 玩家 vs 玩家 STR 比试摔跤\n检定: 玩家 STR 12 把他摔出去\n</board>\nnext: advance"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(outs))
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: {k: SimpleNamespace(yes=0.9 if k == "gap" else 0.1) for k in qs})
    out = plan_loop.step(root, user_text="@dm 我跟他去后巷比划比划。", last_narration="x")
    pb = out["plan_beat"]["beat"]
    assert out["kind"] == "resolve" and pb["check_gap"] == 0.9 and [c["attr"] for c in out["checks"]] == ["STR", "STR"]
    assert "host-check" in [c["who"] for c in pb["calls"]] and "这一架得掷" in out["plan_beat"]["narration"]
    plan_loop.clear(root)
    outs2 = iter(["<lines>\n走吧。\n</lines>\n<board>\n玩家: 去码头\n</board>\nnext: advance"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(outs2))
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: {k: SimpleNamespace(yes=0.1) for k in qs})
    out = plan_loop.step(root, user_text="@dm 去码头。", last_narration="x")
    assert out["kind"] == "resolve" and "host-check" not in [c["who"] for c in out["plan_beat"]["beat"]["calls"]]  # nothing to roll


# ── narrate, then transition ─────────────────────────────


def test_narrate_writes_prose_then_one_state_transition(tmp_path, fake_adapter, monkeypatch):
    """The narrator writes only the prose (options are a tool); one clean-context call then writes the state
    transition — <vars> new values of registered variables, <files> the file-system changes."""
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    a = fake_adapter(["<lines>\n你走进杂货铺,数出三枚金币。\n老苇把药水推过来。\n[options 回北门 | 问路]\n</lines>",
                      "<vars>\nplayer.gold = 15\ntime.clock = \"09:10\"\n</vars>\n<files>\nnew_npc 补网人 main_street\n</files>"])
    out = turn_v3.solve_turn(root, user_text="买药", provider=None, turn=1, soul_reports=[])
    assert len(a.calls) == 2 and "这一次:只写叙事" in a.calls[0][1].content and "这一拍写好的叙事" in a.calls[1][1].content
    assert "老苇把药水推过来" in a.calls[1][1].content and "[options" not in out["narration"]
    assert out["options"] == ["回北门", "问路"]
    assert out["apply"].variables["player.gold"] == 15 and out["apply"].variables["time.clock"] == "09:10"
    assert [c["class"] for c in out["apply"].created] == ["npc"]
    assert "world.transition" in [s["actor"] for s in out["spans"]]


def test_narrate_rules_a_world_changing_tool_mid_prose_and_refits_only_the_transition(tmp_path, fake_adapter, monkeypatch):
    """A world-changing tool in the prose gets the engine's verdict and the prose goes on from it; a refused transition
    is sent back alone — the prose is never rewritten; a tool's ruling wins over the transition."""
    root = _install(tmp_path)
    _register_unmapped_cellar(root)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    a = fake_adapter(["<lines>\n你推开地窖的门。\n[move player 地窖]\n</lines>",
                      "<lines>\n门后是实墙,你只好退回来,顺手付了三枚铜子给看门的。\n[player.copper -3]\n</lines>",
                      "<lines>\n他点点头。\n</lines>",
                      "<vars>\nlocation = 地窖\nplayer.copper = 1\n</vars>\n<files>\n</files>",
                      "<vars>\n</vars>\n<files>\n</files>"])
    out = turn_v3.solve_turn(root, user_text="我去地窖", provider=None, turn=1, soul_reports=[])
    users = [c[1].content for c in a.calls]
    assert len(a.calls) == 5 and "不行:" in users[1] and "可以" in users[2]  # the verdicts came back mid-prose
    assert "上一次状态转移被退回的" in users[4]  # only ② was sent back
    assert out["narration"].startswith("你推开地窖的门。") and "门后是实墙" in out["narration"] and "他点点头" in out["narration"]
    assert not any(x["op"] == "move_to" for x in out["apply"].applied)
    assert out["apply"].variables["player.copper"] == 6  # 9 - 3 by the tool; the transition's 「= 1」 lost to it


def test_a_refit_keeps_what_the_first_transition_already_got_through(tmp_path, fake_adapter, monkeypatch):
    """N2 M12 r3 t11: the first transition's `player.hp`/clock were good, one patch was sent back; the refit wrote only
    the fix (as the refit prompt asks) and the good part was lost with it."""
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    a = fake_adapter(["<lines>\n你数出三枚金币。\n</lines>",
                      "<vars>\nplayer.gold = 15\n</vars>\n<files>\npatch 谁也不是 x=1\n</files>",
                      "<vars>\n</vars>\n<files>\n</files>"])
    out = turn_v3.solve_turn(root, user_text="买药", provider=None, turn=1, soul_reports=[])
    assert len(a.calls) == 3 and "上一次状态转移被退回的" in a.calls[2][1].content
    assert out["apply"].variables["player.gold"] == 15


class _ThinkingProvider:
    """A provider with a thinking switch: the prose straight away; the write-down answers by whether it was asked to think."""
    base_url = "https://api.deepseek.com/v1"

    def __init__(self, think: str, straight: str, think_s: float = 0.0):
        self.think, self.straight, self.think_s, self.calls = think, straight, think_s, []

    def chat(self, messages, tools=None):
        import time

        from neonrp.core import llm_openai

        user = messages[-1].content
        on = llm_openai._THINK.get()
        self.calls.append(on)
        if "<vars>" not in user:
            text = "<lines>\n你数出三枚金币。\n</lines>"
        elif on:
            time.sleep(self.think_s)
            text = self.think
        else:
            text = self.straight
        return SimpleNamespace(message=SimpleNamespace(content=text), usage={"prompt_tokens": 10, "completion_tokens": 5})


@pytest.mark.parametrize("think, think_s, gold, used", [
    ("<vars>\nplayer.gold = 14\n</vars>\n<files>\n</files>", 0.3, 14, "think"),  # thinking came back: it is taken
    ("", 0.0, 15, "straight"),                                                        # thinking came back empty
    ("<vars>\nplayer.gold = 14\n</vars>\n<files>\n</files>", 3.0, 15, "straight"),  # thinking past the wait
])
def test_the_write_down_sends_thinking_and_straight_together(tmp_path, monkeypatch, think, think_s, gold, used):
    """10-21 niko: 「cot和无思考可以并发,然后如果是40秒或者1分钟超时的话,就fall back」 — fixc: the thinking
    write-down ran 15–31 s on a slow provider; before that, timed by the prose's leftovers, it came back empty and PL12's
    coins and night never landed. Both go out at once; the thinking one wins if it comes within the wait."""
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_TRANSITION_THINK_WAIT_S", "1.0")
    monkeypatch.setenv("NEONRP_TRANSITION_ASYNC", "0")  # the race itself; the background correction: test_write_down_async
    a = _ThinkingProvider(think, "<vars>\nplayer.gold = 15\n</vars>\n<files>\n</files>", think_s)
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: a)
    try:
        out = turn_v3.solve_turn(root, user_text="买药", provider=None, turn=1, soul_reports=[])
    finally:
        turn_v3.ADAPTER_FACTORY = None
    assert out["apply"].variables["player.gold"] == gold
    assert sorted(a.calls[-2:]) == [False, True], "both calls went out"
    assert [s.get("used") for s in out["spans"] if s.get("actor") == "world.transition"] == [used]


def test_a_beat_can_be_sure_of_its_own_seconds():
    import time

    from neonrp.core import beat_budget

    with beat_budget.turn(1.0):
        with beat_budget.beat("world"):
            time.sleep(0.1)
            beat_budget.ensure(3.0, "world.transition")
            assert beat_budget.remaining() > 2.8 and beat_budget.turn_remaining() > 2.8
        assert not beat_budget.hits()


def test_transition_keeps_a_written_text_whole():
    """10-04 n15 PL14: the transition's [~write path]…[/write] body spans lines — it was cut into nonsense ops."""
    ops = turn_v3.parse_transition("<vars>\ntime.clock = \"09:20\"\n</vars>\n<files>\npatch 粗纸 qty=2\n"
                                   "[~write towns/T001/notice_rowan.md]\n罗文,背长弓,十天前出北门。\n知情者报公会。\n[/write]\n</files>")
    assert [o["op"] for o in ops] == ["set", "patch", "write"]
    w = ops[-1]
    assert w["path"] == "towns/T001/notice_rowan.md" and "罗文,背长弓" in w["body"] and "知情者报公会" in w["body"]


def test_at_dm_skips_asking_her_but_not_her_opposition_nor_the_dice(tmp_path, monkeypatch):
    """「可以跳过和角色商量,但不能跳过投骰子,也不能跳过艾琳娜要拦,而是直接进入对抗清算」. In an @DM round
    nobody is asked; before the switch the judge sees who is present, and if she would stop him the host boards her
    part and a contest — without asking her."""
    from types import SimpleNamespace

    from neonrp.core import plan_loop, system_one as s1

    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.parent == reg.player_location)
    outs = iter(["<lines>\n鱼篓就在脚边。\n</lines>\n<board>\n玩家: 踢翻鱼篓\n</board>\nnext: advance",
                 f"<lines>\n她伸手拦你,这一下要掷:你 DEX 对她 DEX。\n</lines>\n<board>\n{elena.name}: 拦下他\n"
                 f"对抗: 玩家 vs {elena.name} DEX 踢翻鱼篓\n</board>\nnext: advance"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(outs))
    asked, seen = [], {}
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", lambda *a, **k: (asked.append(1), {"ok": True, "answer": "x"})[1])
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: (seen.update(state), {k: SimpleNamespace(yes=0.9 if k == "gap" else 0.1) for k in qs})[1])
    out = plan_loop.step(root, user_text="@dm 我一脚把鱼篓踢翻。", last_narration="x")
    assert out["kind"] == "resolve" and asked == []  # she was not asked
    assert [p["name"] for p in seen["present"]] == [elena.name]  # but the judge saw her
    assert out["board"][elena.name] == "拦下他" and out["checks"][0].get("vs") == elena.id  # her opposition, as a contest


def test_beat_display_marks_planning_and_resolve_apart_and_keeps_history_plain(tmp_path, fake_adapter, monkeypatch):
    """「骰子的判断和工具调用在前端能不能用特殊的文字渲染出来」「商量和清算的轮次会有不一样的效果」. With the
    beat display on, the planning beat and the resolve beat are shown in the TUI's line conventions (header, tool lines,
    dice lines, a state line); what is stored and fed back to models stays the plain prose."""
    from types import SimpleNamespace

    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop, system_one as s1
    from neonrp.core.conversation import ConversationSession
    from neonrp.tui.app import ConversationView

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_SHOW_BEATS", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    _old_talk_rule(root)  # this test is about the talk itself: a check agreed does not end it (the 10-15 switch off)
    from neonrp.core import plan_loop as _pl

    monkeypatch.setattr(_pl, "host_again", lambda *a, **k: 1.0)  # S1 is off here; 2cd1fa4: no judge = no second host round
    soul = next(e for e in load_registry(root).of_class("soul"))
    rounds = iter([f"<lines>\n杂货铺一刻钟。\n</lines>\n<mic>\n{soul.name}: 他要你帮着砍价?\n</mic>\n<board>\n玩家: 买药\n</board>\nnext: wait",
                   "<lines>\n她来砍价。\n</lines>\n<board>\n检定: 玩家 CHA 10 砍价\n</board>\nnext: advance"])
    monkeypatch.setattr(plan_loop, "host_again", lambda *a, **k: 0.9)  # 10-14: System One says the host must speak again
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(rounds))
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: {"ok": True, "answer": "<lines>\n「行,我来砍。」\n</lines>\n<draft>帮着砍价</draft>"})
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: {k: SimpleNamespace(yes=0.1) for k in qs})
    fake_adapter(["<lines>\n老苇让了一金,你买下药水。\n[options 回北门 | 问路]\n</lines>",
                  "<vars>\ntime.clock = \"09:10\"\n</vars>\n<files>\n</files>"])
    chunks: list[str] = []
    sess = ConversationSession(root, "test-agent", mode="play")
    res = sess.send("去杂货铺买药,让她帮我砍价。", on_chunk=chunks.append)
    # the planning beat arrives piece by piece, in the order it happened; she speaks as herself (her own speaker)
    plan = chunks[: next(i for i, c in enumerate(chunks) if c.startswith("// 清算"))]
    assert plan[0] == "// 商量\n" and plan[1].startswith("杂货铺一刻钟") and plan[2].startswith(f"[话筒 → {soul.name}]")
    assert plan[3] == f"[[subagent:{soul.name}]]「行,我来砍。」\n" and plan[4].startswith("[打算]") and plan[5].startswith("她来砍价")
    assert plan[-1].startswith("[→ 谈定,进入结算") and any(c.startswith("[计划]") for c in plan)
    shown_res = res.assistant_message
    assert shown_res.startswith("// 清算") and "[state_update] time.clock" in shown_res and "1. 回北门" in shown_res
    dice = [ln for ln in shown_res.splitlines() if "砍价" in ln and "→" in ln]
    assert dice and ConversationView._DICE_LINE_RE.match(dice[0])  # the TUI colours it as a die
    stored = [m.content for m in sess.messages if m.role == "assistant"]
    assert not any("// 商量" in c or "[state_update]" in c for c in stored)  # history stays plain


def test_her_view_does_not_decide_the_players_part_unless_he_gave_her_the_call(tmp_path, monkeypatch):
    """「你跟着我走吧」 → she: 「我先去旅店」 → the host settled on the inn for him. A character's
    answer that redirects the player's own part sends the beat back to the player — unless he handed her the call."""
    from types import SimpleNamespace

    from neonrp.core import plan_loop, system_one as s1

    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.parent == reg.player_location)

    def run(user: str) -> dict:
        plan_loop.clear(root)
        outs = iter([f"<lines>\n先听她的。\n</lines>\n<mic>\n{elena.name}: 他让你跟着他?\n</mic>\nnext: wait",
                     "<lines>\n那就一起去河灯旅店。\n</lines>\n<board>\n玩家: 去旅店\n</board>\nnext: advance",
                     "<lines>\n她想先去旅店放包。你:① 跟她去旅店 ② 照你的走\n</lines>\nnext: wait"])
        monkeypatch.setattr(plan_loop, "_host", lambda root_, system, u: next(outs))
        return plan_loop.step(root, user_text=user, last_narration="x")

    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda *a, **k: {"ok": True, "answer": "<lines>\n「我先去旅店放包。」\n</lines>\n<draft>先去旅店</draft>"})
    # every judge says yes — but nothing on the plan is left uncertain or opposed (the contest question, private
    # e176151 10-15, would otherwise send the talk to the resolve with a check)
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: {k: SimpleNamespace(yes=0.1 if k == "gap" else 0.9) for k in qs})
    out = run("我也第一次来,你跟着我走吧。")
    assert out["kind"] == "plan" and "host-handback" in [c["who"] for c in out["beat"]["calls"]]
    assert "① 跟她去旅店" in out["narration"] and "那就一起去河灯旅店" not in out["narration"]  # asked, not decided for him
    out = run("你定吧,你带路。")
    assert out["kind"] == "resolve"  # he gave her the call


class _StreamingFake(_FakeAdapter):
    """A provider that streams: each reply comes in small pieces."""

    def chat_stream(self, messages, tools=None):
        self.calls.append(messages)
        text = self.outputs.pop(0) if self.outputs else ""
        for i in range(0, len(text), 4):
            yield SimpleNamespace(delta=text[i:i + 4], thinking=None, tool_call_starts=None, finished=False)


def test_resolve_prose_streams_to_the_screen_and_tool_answers_land_where_they_happen(tmp_path, monkeypatch):
    """「agent 开始生成字的时候,马上渲染到 tui 上」. In the narrate shape the prose goes out in pieces as it is
    written, stops at a request line (what follows it is cut), the engine's answer is shown where it happened, and at the
    end only the state line and the options follow — the prose is not sent twice."""
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop
    from neonrp.core.conversation import ConversationSession
    from neonrp.tui.app import ConversationView

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_SHOW_BEATS", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n走。\n</lines>\n<board>\n玩家: 撬锁\n</board>\nnext: advance")
    a = _StreamingFake(["<lines>\n你蹲在门前,把铁丝伸进锁眼。\n[dice 1d20+2 vs 12]撬锁[/dice]\n这行写在停点之后,不该出现\n</lines>",
                        "<lines>\n锁舌一松,门开了。\n[options 进去 | 先听听]\n</lines>",
                        "<vars>\ntime.clock = \"09:10\"\n</vars>\n<files>\n</files>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: a)
    chunks: list[str] = []
    try:
        ConversationSession(root, "test-agent", mode="play").send("@dm 我撬开这扇门。", on_chunk=chunks.append)
    finally:
        turn_v3.ADAPTER_FACTORY = None
    res = chunks[next(i for i, c in enumerate(chunks) if c.startswith("// 清算")):]
    screen = "".join(res)
    before = screen[: screen.index("锁眼")]
    assert len([c for c in res[1:] if c and c in before]) >= 2  # in pieces, not one block
    assert "不该出现" not in screen and "[dice 1d20+2 vs 12]" not in screen  # stopped at the request line
    die = next(ln for ln in screen.splitlines() if "撬锁" in ln and "→" in ln)
    assert ConversationView._DICE_LINE_RE.match(die)
    assert screen.index("锁眼") < screen.index(die) < screen.index("门开了")  # the answer where it happened
    assert screen.count("你蹲在门前") == 1 and "[state_update] time.clock" in screen and "1. 进去" in screen


def test_a_fresh_session_on_a_played_world_continues_instead_of_reopening(tmp_path, fake_adapter, monkeypatch):
    """TUI 10-04 #6: after a TUI restart (a new session, no chat history) the host set the scene again from scratch and
    contradicted the prose just written. The last narration comes from the playthrough's own record."""
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop
    from neonrp.core.conversation import ConversationSession

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    seen: list[str] = []
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (seen.append(user), "<lines>\n走。\n</lines>\n<board>\n玩家: 进公会\n</board>\nnext: advance")[1])
    fake_adapter(["<lines>\n你推门进了公会,赫伦在长桌后翻登记册。\n</lines>", "<vars>\n</vars>"])
    ConversationSession(root, "test-agent", mode="play").send("@dm 进公会。")
    seen.clear()
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (seen.append(user), "<lines>\n赫伦抬头看你。\n</lines>\nnext: wait")[1])
    ConversationSession(root, "test-agent", mode="play").send("看看四周。")  # a new session: no chat history
    assert seen and "这是这一局的开场" not in seen[0] and "赫伦在长桌后翻登记册" in seen[0]


def test_no_check_to_add_says_nothing_and_a_talked_over_beat_is_not_trivial(tmp_path, monkeypatch):
    """TUI 10-04 #10: the pre-switch question found a gap, the extra host round set no check and only repeated the line;
    and a beat after several beats of talk was labelled 「没什么要商量」."""
    from types import SimpleNamespace

    from neonrp.core import plan_loop, system_one as s1

    root = _install(tmp_path)
    plan_loop.save(root, {"talk": ["旅人:想接活", "主持:有两件"], "beats": 3})
    outs = iter(["<lines>\n那就 Q002。\n</lines>\n<board>\n玩家: 接 Q002\n</board>\nnext: advance",
                 "<lines>\n那就 Q002,当场结。\n</lines>\n<board>\n玩家: 接 Q002\n</board>\nnext: advance"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(outs))
    monkeypatch.setattr(s1, "ask", lambda state, qs, **kw: {k: SimpleNamespace(yes=0.8 if k == "gap" else 0.1) for k in qs})
    out = plan_loop.step(root, user_text="想要接 Q002", last_narration="x")
    nb = out["plan_beat"]
    assert out["advanced_by"] == "world:settled"  # talked over before: not trivial
    assert "host-check" in [c["who"] for c in nb["beat"]["calls"]] and nb["narration"].count("Q002") == 1  # no repeat


def test_tui_play_on_an_unplayed_world_opens_with_its_opening(tmp_path, monkeypatch):
    """「一上来请有一个开场白」: `neonrp tui --play` on a world nobody has played sends the start cue itself (the
    opening is shown at once); a world already played continues where it was."""
    from click.testing import CliRunner

    from neonrp.commands import tui as tui_cmd
    from neonrp.tui import app as tui_app

    got: list = []
    monkeypatch.setattr(tui_app, "run_tui", lambda **kw: got.append(kw.get("startup_commands")))
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(tui_cmd.tui, ["--play"])
    assert got[-1] == ["开始游戏"]
    (tmp_path / ".neonrp" / "orchestration").mkdir(parents=True)
    (tmp_path / ".neonrp" / "orchestration" / "main.jsonl").write_text('{"turn_seq": 0}\n', encoding="utf-8")
    CliRunner().invoke(tui_cmd.tui, ["--play"])
    assert got[-1] == []


# ── 「艾琳娜已经不在身边,叙事里还有她」「她在公会一动不动」 ─────────────────────────────────────


def test_prompt_examples_carry_no_world_names():
    """The narrator's EXAMPLE put 「艾琳娜没说话…」 / 「move 艾琳娜 inn」 in every turn's prompt — the model copied her in as
    the player's companion although she was at the guild. Engine prompts carry no world's names (rule: 引擎代码不写世界词)."""
    from neonrp.core import adv, plan_loop, player_gate
    from neonrp.packs.rpg import contract

    names = set()
    for sj in Path("src/neonrp/templates").glob("*/souls/*/soul.json"):
        d = json.loads(sj.read_text(encoding="utf-8"))
        names |= {str(d.get(k)) for k in ("name", "name_local") if d.get(k)}
    names |= {"米拉", "Mira", "ミラ", "Rowan", "ローワン", "旅人"}
    texts = [plan_loop.PLAN_SYS, contract._TAGS_FORMAT, json.dumps(adv.SPEC, ensure_ascii=False), json.dumps(player_gate._SYS, ensure_ascii=False)]
    leaked = sorted({n for n in names for t in texts if n and len(n) >= 2 and n in t})
    assert not leaked, leaked


def test_narrate_prompt_says_only_present_people_appear_and_almost_always_offers_options():
    from neonrp.core import turn_v3

    zh, en = turn_v3.NARRATE["zh"], turn_v3.NARRATE["en"]
    assert "谁能出场" in zh and "异地角色" in zh and "Who can appear" in en
    assert "几乎每一拍都写" in zh and "almost every beat" in en


def test_pack_lists_town_npcs_elsewhere_apart_from_who_is_here(tmp_path):
    """The context put 赫伦 (at the guild) and 米拉 (at the inn) under 「在场角色与 NPC」 while the player stood at the gate."""
    root = _install(tmp_path)
    reg = load_registry(root)
    here = reg.player_location
    npcs = [e for e in reg.of_class("npc")]
    if not npcs:
        pytest.skip("no NPCs in this world")
    elsewhere = [e for e in npcs if e.parent != here]
    txt = "\n".join(t for _tier, t in sdk._sections(sdk.pack(root, registry=reg)))
    assert "在场角色与 NPC" not in txt and "## 在场(和玩家同一地点)" in txt
    if elsewhere:
        head, _, tail = txt.partition("## 本镇别处的 NPC")
        assert tail and all(e.name not in head.split("## 在场(和玩家同一地点)", 1)[1] for e in elsewhere)


def test_narrator_history_keeps_the_players_words_not_engine_notes():
    from neonrp.core.conversation import v3_history_pairs
    from neonrp.core.llm import Message

    msgs = [Message(role="user", content="往正东河滩探一条新路"),
            Message(role="assistant", content="那说定:出北门,往正东探一段。"),
            Message(role="user", content="[Player Controller / World Preflight — control-plane context]\nx"),
            Message(role="user", content="[预判 · System One] 玩家意图=move\n\n[主持工具(M30)] 你以工具主持本回合:get_roster"),
            Message(role="assistant", content="你从北门出去。")]
    pairs = v3_history_pairs(msgs)
    from neonrp import prompts as _pr  # the marker is whichever is active: ours (private layer) or the open engine's

    assert [p["user"] for p in pairs] == ["往正东河滩探一条新路", _pr.strings("conversation", "zh")["resolve_as_agreed"]]
    assert not any("主持工具" in p["user"] or "Preflight" in p["user"] for p in pairs)


def test_a_character_elsewhere_takes_her_own_turn_off_the_players_screen(tmp_path, fake_adapter, monkeypatch):
    """「理论上所有角色都需要有 1 turn」 / 10-05 「艾琳娜在冒险者公会一动不动」: away souls were always `silent`.
    In a Resolve she now acts where she is — from her own view (not the player's beat), not written into the player's
    prose, shown as an 「// 异地」 line."""
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop
    from neonrp.core.conversation import ConversationSession
    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    reg = load_registry(root)
    soul = next(e for e in reg.of_class("soul"))
    here = reg.player_location
    other = next((e.id for e in reg.exits(here)), None) if here else None
    if not other:
        pytest.skip("no second place in this world")
    sdir = next(d for d in (root / "souls").iterdir() if d.name.endswith(soul.id))
    rs = sdir / "run_state.json"
    st = json.loads(rs.read_text(encoding="utf-8")) if rs.is_file() else {}
    rs.write_text(json.dumps({**st, "location": other}, ensure_ascii=False), encoding="utf-8")
    assert load_registry(root).entries[soul.id].parent != load_registry(root).player_location
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n走。\n</lines>\n<board>\n玩家: 四处看看\n</board>\nnext: advance")
    asks = []
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver",
                        lambda root_, iid, q, **kw: (asks.append((iid, q)), {"ok": True, "answer": "她把告示抄了一遍。", "name": soul.name})[1])
    sent = []
    fake_adapter(["你四处看了看,雾很重。\n⟦STATE⟧\n⟦/STATE⟧"] * 4)
    import neonrp.core.turn_v3 as tv3

    _orig = tv3.solve_turn

    def _spy(*a, **k):
        sent.append(k.get("soul_reports"))
        return _orig(*a, **k)

    monkeypatch.setattr(tv3, "solve_turn", _spy)
    res = ConversationSession(root, "test-agent", mode="play").send("@dm 四处看看")
    assert any(iid == soul.id and "玩家不在你这里" in q for iid, q in asks), asks
    assert sent and not any((r or {}).get("iid") == soul.id and r.get("kind") != "plan" for r in (sent[0] or []))
    assert f"// 异地 · {soul.name}" in (res.assistant_message or "")


def test_a_status_with_a_spaced_delta_keeps_its_per_turn_change():
    """「骰完之后的效果有没有出?」 — the transition wrote `each=player.hp -1`; the -1 fell into the status
    name (「生吞腐鱼 -1」) and its per-turn hp loss was lost."""
    from neonrp.core.effects import parse_each

    for line in ("new status 恶心 turns=3 check=-2 each=player.hp -1 note=x", "new status 恶心 turns=3 check=-2 each=player.hp: -1",
                 "new status 恶心 turns=3 check=-2 each=player.hp:-1"):
        (op,) = turn_v3.parse_transition(f"<files>\n{line}\n</files>")
        assert op["name"] == "恶心" and op["props"]["each"] == "player.hp:-1" and op["props"]["check"] == "-2", op
        assert parse_each(op["props"]["each"]) == [("player.hp", -1)]
    (op,) = turn_v3.parse_transition("<files>\npatch 恶心 turns=2 each=player.hp -2\n</files>")
    assert op["props"]["each"] == "player.hp:-2"
    # 10-05 second take: the model names a status from the table, or writes one free rule line; no field syntax to get wrong
    assert "new status" in turn_v3.TRANSITION["zh"] and "note=" in turn_v3.TRANSITION["ko"] and "通缉" in turn_v3.TRANSITION["zh"]


def test_a_status_ticks_once_per_resolve_and_wears_off(tmp_path):
    """「状态是每过一次清算,会不会清算一次?」: an effect created in a Resolve starts the NEXT one; every Resolve
    (one sdk.apply) applies its `each` once and counts `turns` down; at 0 it is gone. Planning beats never apply."""
    from neonrp.core import effects

    root = _install(tmp_path)
    reg = load_registry(root)
    if "player.hp" not in reg.variables or "status" not in effects.effect_classes(reg):
        pytest.skip("world without hp / status")
    hp0 = int(reg.variables["player.hp"].value)
    (op,) = turn_v3.parse_transition("<files>\nnew status 恶心 turns=2 check=-2 each=player.hp -1\n</files>")
    sdk.apply(root, [op], reg, turn=1)
    reg = load_registry(root)
    assert int(reg.variables["player.hp"].value) == hp0, "created this resolve: starts next resolve"
    (st,) = [e for e in effects.instances(reg) if e.name == "恶心"]
    assert effects.check_mod(reg) <= -2
    sdk.apply(root, [], reg, turn=2)
    reg = load_registry(root)
    assert int(reg.variables["player.hp"].value) == hp0 - 1
    assert int(reg.entries[st.id].props["turns"]) == 1
    sdk.apply(root, [], reg, turn=3)
    reg = load_registry(root)
    assert int(reg.variables["player.hp"].value) == hp0 - 2
    assert st.id not in reg.entries and not [e for e in effects.instances(reg) if e.name == "恶心"], "worn off at 0"
    sdk.apply(root, [], reg, turn=4)
    assert int(load_registry(root).variables["player.hp"].value) == hp0 - 2, "nothing after it wore off"


def test_a_players_thought_never_reaches_a_character_through_the_mic(tmp_path, monkeypatch):
    """「闭上眼,在心里对自己说:再睁开眼的时候,我人已经在碧石镇的街上了」 — the host handed Elena
    「旅人闭上眼,说再睁眼就该到碧石镇了」 and she answered the thought. The host sees what a bystander met (`seen`) and
    is told the mic carries its question only; a line that still leaks the player's words is replaced by the plain ask."""
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    reg = load_registry(root)
    soul = next(e for e in reg.of_class("soul") if e.parent == reg.player_location) if any(
        e.parent == reg.player_location for e in reg.of_class("soul")) else None
    if soul is None:
        pytest.skip("no character with the player")
    line = "我不选这些，闭上眼，在心里对自己说：再睁开眼的时候，我人已经在碧石镇的街上了。"
    gate = {"seen": "旅人没有做任何选择，闭上眼，一言不发。", "named": [{"said": "碧石镇", "source": "世界里的名字"}], "claims": []}
    hosts = []
    outs = iter([f"<lines>\n闭眼不管用。\n</lines>\n<mic>\n{soul.name}: 旅人闭上眼，说再睁眼就该到碧石镇了。你怎么看？\n</mic>\nnext: wait",
                 "<lines>\n那就先这样。\n</lines>\nnext: wait"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: (hosts.append(user), next(outs))[1])
    asks = []
    monkeypatch.setattr(plan_loop, "ask_soul_deliver", lambda root_, iid, q, **kw: (asks.append(q), {"ok": True, "answer": "<lines>\n「你还好吗?」\n</lines>"})[1],
                        raising=False)
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", lambda root_, iid, q, **kw: (asks.append(q), {"ok": True, "answer": "<lines>\n「你还好吗?」\n</lines>"})[1])
    plan_loop.step(root, user_text=line, last_narration="雾压在驿路上。", gate=gate)
    assert gate["seen"] in hosts[0], "the host is shown what a bystander met"
    assert asks and all("碧石镇" not in q and "再睁开眼" not in q for q in asks), asks
    assert plan_loop.leaks_player_mind("那盏灯卖不卖,你怎么看?", "我去杂货铺,顺便把灯卖了。", "旅人说要去杂货铺,顺便把灯卖了。") is False
    assert "只写你问她的话" in plan_loop.plan_sys(root)


def test_a_character_in_a_fight_fights_as_herself_and_her_hp_is_her_own(tmp_path):
    """「改动的世界文件里面没有艾琳娜的 HP」 — `[combat 艾琳娜×1]` spawned a nameless 「foe1」 (hp 8) and the
    blows landed on it. A character the world has fights as herself: her hp from her sheet (the base), the blows land in
    her Character State (game/states/<id>.json); the soul's own folder is not touched (CHARACTER-STATE-1005)."""
    from neonrp.packs.rpg import character_state as cs, combat

    root = _install(tmp_path)
    reg = load_registry(root)
    soul = next(e for e in reg.of_class("soul") if e.props.get("sheet"))
    assert soul.props.get("hp"), "the registry knows her hp (from her sheet)"
    sheet0 = (root / soul.props["sheet"]).read_text(encoding="utf-8")
    combat.write(root, {**combat.spawn(root, reg, turn=1, roster=f"{soul.name}×1"), "at": reg.player_location})
    reg = load_registry(root)
    foes = combat.read(root)["foes"]
    assert list(foes) == [soul.id] and foes[soul.id]["ref"] == soul.id, foes
    assert reg.variables[f"foe.{soul.id}.hp"].path == cs.rel_path(root, soul.id)
    hp0 = int(soul.props["hp"])
    sdk.apply(root, [{"op": "set", "var": f"foe.{soul.id}.hp", "value": hp0 - 5}], reg, turn=2)
    assert cs.read(root, soul.id)["hp"] == hp0 - 5
    assert int(load_registry(root).entries[soul.id].props["hp"]) == hp0 - 5
    assert (root / soul.props["sheet"]).read_text(encoding="utf-8") == sheet0, "her soul folder stays clean"


def test_a_continuation_that_restates_what_was_written_is_not_doubled():
    """10-05 C1: after [combat] the model rewrote its first six lines before going on — the player saw them twice."""
    from neonrp.core.stream_lines import LinesFilter

    pre = "雾里只有你们两个。\n你的短剑先出。"
    cont = "雾里只有你们两个。\n你的短剑先出。\n你不收手,手腕一翻。\n她横架。"
    assert turn_v3.drop_restated(pre, cont) == "你不收手,手腕一翻。\n她横架。"
    assert turn_v3.drop_restated(pre, "她横架。") == "她横架。"
    f = LinesFilter(skip_lines=set(pre.splitlines()))
    shown = "".join(f.feed(ch) for ch in "<lines>\n" + cont + "\n</lines>")
    assert shown.strip() == "你不收手,手腕一翻。\n她横架。"


def test_async_map_is_drawn_on_the_world_after_the_write_down(tmp_path, fake_adapter, monkeypatch):
    """10-08: [~map] fires after the state transition — it must show where the player is NOW (it used the registry
    loaded before the write-down and kept showing the old place)."""
    root = _install(tmp_path)
    _no_hazards(root)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    # the gate fires the map itself when the player asks the way (real path: release-1007-c2 N2, the map said 北门
    # while the beat had moved the player to the guild)
    from neonrp.core import mechanics as _mech

    real_get = _mech.get
    monkeypatch.setattr(_mech, "get", lambda root, seam: (lambda *a, **k: {"fire": [{"op": "map"}]}) if seam == "gate" else real_get(root, seam))
    fake_adapter(["<lines>\n你沿着主街往里走。\n</lines>",
                  "<vars>\n</vars>\n<files>\nmove_to player main_street\n</files>"])
    out = turn_v3.solve_turn(root, user_text="先看看路,然后去主街", provider=None, turn=1, soul_reports=[])
    assert any(x["op"] == "move_to" for x in out["apply"].applied)
    assert "[你的位置] 主街(main_street)" in out["panels"]["map"]["text"], out["panels"]["map"]["text"][:120]


# ── two state modes of the Resolve beat: pseudo | jev (core/orchestration.STATE_MODES) ─────────────────


def _jev_stub(state, qs):
    """A Jev that reads the tags plainly: a line naming T001/guild is a move of the player there; nothing else changed."""
    out = {}
    for k, q in qs.items():
        if q.type == "noul":
            out[k] = s1.Answer("noul", 0.95 if k.endswith(".move_to") and "guild" in json.dumps(state, ensure_ascii=False) else 0.05, {}, 0.9)
            continue
        crit = q.criteria if isinstance(q.criteria, dict) else {}
        pick = next((c for c, t in crit.items() if k.endswith(".to") and "guild" in f"{c} {t}"), None) \
            or next((c for c, t in crit.items() if k.endswith(".who") and ("玩家" in f"{c} {t}" or "player" in f"{c} {t}")), None) \
            or next(iter(crit), None)
        out[k] = s1.Answer("choice", pick, {pick: 0.95}, 0.9)
    return out


def test_state_mode_pseudo_and_jev_are_two_orchestrations_and_jev_without_a_fast_jev_is_pseudo(tmp_path, fake_adapter, monkeypatch):
    """「状态文字直出 → Jev」and「伪代码 → JSON」are two modes the open engine carries — a parameter of the
    Resolve node in the graph (the one source: ``nodes.resolve.state``, default pseudo); jev with no fast Jev runs pseudo."""
    from neonrp.core import orchestration as orch

    monkeypatch.setenv("NEONRP_PRIVATE", "off")  # the open engine: no planning beat
    root = _install(tmp_path)
    monkeypatch.delenv("NEONRP_V3_SOLVE", raising=False)
    orch.override_path(root).parent.mkdir(parents=True, exist_ok=True)

    # pseudo — the default, nothing set: prose, then one pseudo-code call
    assert orch.graph(root)["nodes"]["resolve"]["state"] == "pseudo"
    assert orch.graph(root)["state"] == {"mode": "pseudo", "asked": "pseudo", "why": ""}
    a = fake_adapter(["<lines>\n你沿主街走进公会。\n</lines>", "<vars>\ntime.clock = \"09:10\"\n</vars>\n<files>\nmove_to player T001/guild\n</files>"])
    out = turn_v3.solve_turn(root, user_text="去公会", provider=None, turn=1, soul_reports=[])
    actors = [s["actor"] for s in out["spans"]]
    assert len(a.calls) == 2 and "world.transition" in actors and "world.jev" not in actors
    assert "<changes>" not in a.calls[0][1].content and out["apply"].variables["time.clock"] == "09:10"

    # jev: the changes in plain words after the prose (same call), Jev fills the JSON — no second model call
    root2 = _install(tmp_path / "b")
    orch.override_path(root2).parent.mkdir(parents=True, exist_ok=True)
    orch.override_path(root2).write_text(json.dumps({"nodes": {"resolve": {"state": "jev"}}}), encoding="utf-8")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_jev_stub)
    try:
        assert orch.graph(root2)["state"]["mode"] == "jev"
        a2 = fake_adapter(["<lines>\n你沿主街走进公会。\n</lines>\n<changes>\n玩家从 T001/gate_north 移动到 T001/guild。\n</changes>\n<possible>\n问委托\n</possible>"])
        out2 = turn_v3.solve_turn(root2, user_text="去公会", provider=None, turn=1, soul_reports=[])
        actors2 = [s["actor"] for s in out2["spans"]]
        assert len(a2.calls) == 1 and "<changes>" in a2.calls[0][1].content  # the description is asked in the prose call
        assert "world.jev" in actors2 and "world.transition" not in actors2 and "world.fallback" not in actors2
        assert any(o["op"] == "move_to" and o.get("to") == "T001/guild" for o in out2["ops"])
        assert "<changes>" not in out2["narration"] and "玩家从" not in out2["narration"]  # the player never sees the ledger lines
    finally:
        s1.install_stub(None)

    # jev asked, but no fast Jev answers → pseudo (and the graph says why)
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    assert orch.graph(root2)["state"] == {"mode": "pseudo", "asked": "jev", "why": "no_fast_jev"}
    a3 = fake_adapter(["<lines>\n你走进公会。\n</lines>", "<vars>\n</vars>\n<files>\nmove_to player T001/guild\n</files>"])
    out3 = turn_v3.solve_turn(root2, user_text="去公会", provider=None, turn=2, soul_reports=[])
    assert len(a3.calls) == 2 and "world.transition" in [s["actor"] for s in out3["spans"]]

    # nothing else sets it: engine.json's old knob is ignored; an unknown name runs the default and says so
    orch.override_path(root2).write_text(json.dumps({"nodes": {"resolve": {"state": "telepathy"}}}), encoding="utf-8")
    assert orch.state_mode(root2) == {"mode": "pseudo", "asked": "telepathy", "why": "unknown"}
    assert orch.solve_structured(root2) == "narrate"


def test_one_combat_round_per_beat_and_the_reply_shows_hp_after_it(tmp_path, fake_adapter):
    """10-19 (N2 combatT1 r1 t5: three [combat] in one beat, a rat cut down in round 1 got up in round 2 — the hp land
    with the beat, so every call read the foes at full hp). One beat is one round: a second call is answered, not run;
    the reply's foes are as the round leaves them."""
    root = _install(tmp_path)
    _force_bandits(root)
    _at_gate(root)
    reg0 = load_registry(root)
    reg0.variables["turn"].value = 5
    sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg0)
    a = fake_adapter([
        "<lines>\n你拔剑。\n[combat 山贼×1]你砍向他[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n[dice 1d20+2 vs 11]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n剑走中门。\n</lines>\n<ops>\nfoe.bandit1.hp -5\n</ops>",
        "<lines>\n他还站着。\n[combat]再砍一刀[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n他退了半步。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n再砍\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="我拔剑砍过去。", provider=None, turn=6, soul_reports=[])
    assert len(a.calls) == 5, "the second [combat] is not run: no layer call for it"
    first, second = out["tool_returns"][0], out["tool_returns"][1]
    assert first["foes"]["bandit1"]["hp"] == 3, "the reply shows the round's hits"
    assert second["ok"] is False and turn_v3._T("zh")["one_round_per_beat"][:10] in second["why"]
    assert load_registry(root).variables["foe.bandit1.hp"].value == 3, "one round's hits, landed once"


def test_the_world_writing_combat_is_the_encounter_and_its_foes_are_spawned(tmp_path):
    """10-20 niko: [combat …] means the party has met the foe — spawn whoever it names and go on, never 「nothing to
    fight」 (N2 T1 r4: 苔原狼 / 雾狼 refused; 1019: 食尸鬼 refused, then the transition beat tried to define a Ghoul class)."""
    from neonrp.packs.rpg import combat
    from neonrp.packs.rpg.understand import combat_grounds

    root = _install(tmp_path)
    _at_gate(root)
    reg = load_registry(root)
    for op in ({"op": "combat", "roster": "石皮蜥×2", "note": "它们扑上来"},
               {"op": "combat", "roster": "石皮蜥×1", "_seen": "你挥剑砍向那头石皮蜥。", "_player": "我砍那头石皮蜥!"},
               {"op": "combat", "note": "旅人顶正面猛砍先露头的那头"}):
        assert combat_grounds(root, reg, op).ok, op
    assert not combat_grounds(root, reg, {"op": "combat"}).ok, "a tag naming nobody, nothing here to fall back on"
    st = combat.spawn(root, reg, roster="石皮蜥×2", turn=6)
    names = [f["name"] for f in st["foes"].values()]
    assert len(names) == 2 and all(n.startswith("石皮蜥") for n in names), names


def test_a_combat_tag_after_the_lines_or_in_one_bracket_is_still_the_fight():
    """N2 T1 r4 / M9 r3: `</lines> [combat 苔原狼×2]…[/combat]` was dropped by the parser (only the blocks were read);
    1019: `[combat 食尸鬼(大)×1 食尸鬼(小)×2 | 旅人顶正面…]` took the whole hand-off as the roster."""
    o = sdk.parse_adv("<lines>\n你说完就动了。\n</lines>\n[combat 苔原狼×2]玩家快斩左边那匹;艾琳娜逼退右边[/combat]")
    assert [x["op"] for x in o.ops] == ["combat"] and o.ops[0]["roster"] == "苔原狼×2" and "快斩" in o.ops[0]["note"]
    assert o.narration == "你说完就动了。"
    o = sdk.parse_adv("<lines>\n你踏出两步。\n[combat 食尸鬼(大)×1 食尸鬼(小)×2 | 旅人顶正面猛砍;凯尔在坡上射箭]</lines>")
    assert o.ops[0]["roster"] == "食尸鬼(大)×1 食尸鬼(小)×2" and o.ops[0]["note"].startswith("旅人顶正面")
    o = sdk.parse_adv("<lines>\n门开着。\n[combat 山贼×3]\n后面写盲了的字。")  # unterminated: the tag is counted once
    assert [x["op"] for x in o.ops] == ["combat"]
    o = sdk.parse_adv("<lines>\n你走到门前。\n</lines>\n[~move player D001]\n[options]\n进去\n听一听")
    assert [x["op"] for x in o.ops] == ["move_to"] and o.options == ["进去", "听一听"], (o.ops, o.options)
    o = sdk.parse_adv("<lines>\n门开着。\n</lines>\n[options 进去 | 听一听]")
    assert o.options == ["进去", "听一听"] and not o.ops
    o = sdk.parse_adv("<cot>想想 [dice 1d20]</cot>\n<lines>\n门开着。\n</lines>\n<options>\n进去\n</options>")
    assert not o.ops, "a call in the thinking is not a call"


def test_a_room_shows_the_foes_there_now_not_its_encounter_odds(tmp_path):
    """10-19 (N2 combatT1 r1 t4: 「可能遭遇:泥苔鼠×1-2(50%)」 — the roll missed, the narrator wrote three rats that the
    engine never had). The room's line is who stands there now; the table's odds stay the engine's."""
    from neonrp.packs.rpg import combat

    root = _install(tmp_path)
    reg = load_registry(root)
    rid = next(k for k, e in reg.entries.items() if e.cls == "room" and e.props.get("encounters"))
    txt = reg.entries[rid].props["encounter_text"]
    assert "0." not in txt and "×" not in txt, txt
    combat.write(root, {"round": 1, "at": rid, "foes": {"x1": {"name": "泥苔鼠甲", "hp": 4, "kind": "x"}}})
    assert "泥苔鼠甲" in load_registry(root).entries[rid].props["encounter_text"]


def test_plan_loop_host_asking_the_player_hands_back_not_settled(tmp_path, monkeypatch):
    """niko 10-19 (N2 combatT1 r1 t1: the host's last line was 「登记写谁的名字?」, the beat was settled and the Resolve
    wrote the name, took the job and walked him to the path): a host line that asks the player goes back to him."""
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import plan_loop
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n单子还在。掌柜把笔推过来:「登记写谁的名字?」\n</lines>\n<board>\n玩家: 接下讨伐的委托\n</board>\nnext: advance")
    res = ConversationSession(root, "test-agent", mode="play").send("讨伐野兽的委托有吗?给我一张。")
    assert res.success and res.route_decision == "plan_loop:plan", res.route_decision
    beat = read_turn_traces(root, "main", last=1)[0]["apply"]["beat"]
    assert beat["kind"] == "plan" and beat["ended_by"] is None and "登记写谁的名字" in res.assistant_message


def test_a_fight_moves_with_the_player_in_its_beat_and_allies_in_the_note_are_not_foes(tmp_path):
    """10-19 (N2 combatM3 r3: the beat that fought also walked the player to the gate — the tick called it a flight, the
    next [combat] spawned a new fight and put 艾琳娜, named in the hand-off note, on the other side)."""
    from neonrp.packs.rpg import combat

    root = _install(tmp_path)
    _at_gate(root)
    reg = load_registry(root)
    soul = next(e for e in reg.of_class("soul"))
    st = combat.spawn(root, reg, roster="石皮蜥×1", note=f"{soul.name}贴地低进,短刀割它前腿", turn=3)
    assert soul.id not in st["foes"] and list(st["foes"]), "the note says what everyone does: no foe from it"
    st.update({"at": "T001/guild", "this_beat": True})
    combat.write(root, st)
    assert combat.tick(root, reg, turn=3) == [] and combat.read(root)["at"] == reg.player_location, "moved with the fight"
    st = combat.read(root)
    st["at"] = "T001/guild"
    combat.write(root, st)
    assert combat.tick(root, reg, turn=4) == [{"op": "end_combat", "outcome": "fled"}], "walked away in a beat with no fight"


def test_two_combat_requests_in_one_reply_run_one_round(tmp_path, fake_adapter):
    """10-19 (N2 combatM4 r3 t8: the narrator wrote two [combat] in one reply — both ran, round 4 and round 5, in one beat)."""
    root = _install(tmp_path)
    _force_bandits(root)
    _at_gate(root)
    reg0 = load_registry(root)
    reg0.variables["turn"].value = 5
    sdk.verify(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg0)
    a = fake_adapter([
        "<lines>\n你拔剑。\n[combat 山贼×1]你砍向他[/combat]\n[combat]再砍[/combat]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n[dice 1d20+2 vs 11]命中[/dice]\n</lines>\n<ops>\n无变化\n</ops>",
        "<lines>\n剑走中门。\n</lines>\n<ops>\nfoe.bandit1.hp -5\n</ops>",
        "<lines>\n他退了半步。\n</lines>\n<ops>\n无变化\n</ops>\n<options>\n再砍\n</options>",
    ])
    out = turn_v3.solve_turn(root, user_text="我拔剑砍过去。", provider=None, turn=6, soul_reports=[])
    ran = [t for t in out["tool_returns"] if str(t.get("request") or "").startswith("combat") and t.get("ok") is not False]
    assert len(ran) == 1 and len(a.calls) == 4, (len(ran), len(a.calls))


def test_a_party_that_has_set_out_stands_on_the_road(tmp_path):
    """10-19 N2 M5: 「这就从北门出发去苔墓,路上说给我听」 — the prose stopped on the trail, the state could only land at
    the dungeon's door. The road out is a place a move may name (its map id): the party stops on it, the next beat goes
    on to the entry room or back to the gate, companions with it."""
    from neonrp.core.turn_settlement import _apply_player_move
    from neonrp.packs.rpg.contract import travel_hints

    root = _install(tmp_path)
    _no_hazards(root)
    assert _apply_player_move(root, "T001/guild")
    reg = load_registry(root)
    elena = next(e.id for e in reg.of_class("soul"))
    from neonrp.packs.rpg.atlas.move import move as _mv

    _mv(root, reg, elena, "T001/guild")
    reg = load_registry(root)
    assert "走在路上、到了门外还没进去,写 move player R002,停在路上" in travel_hints(root, reg)
    assert "road_T001_D001" in reg.entries and reg.entries["road_T001_D001"].name not in sdk.render_pack(sdk.pack(root))  # a way out nobody is on: not a sight

    def step(*ops):
        nonlocal reg
        vr = sdk.verify(root, list(ops), reg)
        assert vr.refused == [], vr.refused
        sdk.apply(root, vr.accepted, reg, turn=3)
        reg = load_registry(root)
        return reg.player_location, reg.entries[elena].parent

    assert step({"op": "move_to", "who": "player", "to": "R002"}, {"op": "move_to", "who": elena, "to": "R002"}) == ("road_T001_D001",) * 2
    assert step({"op": "move_to", "who": "player", "to": "R002"}) == ("road_T001_D001",) * 2  # already on it
    assert step({"op": "move_to", "who": "player", "to": "D001"}, {"op": "move_to", "who": elena, "to": "D001"}) == ("D001/D001_R001",) * 2
    assert step({"op": "move_to", "who": "player", "to": "R002"}) == ("road_D001_T001",) * 2
    assert step({"op": "move_to", "who": "player", "to": "T001"}) == ("T001/gate_north",) * 2
    assert step({"op": "move_to", "who": "player", "to": "R002"}) == ("road_T001_D001",) * 2
    assert step({"op": "move_to", "who": "player", "to": "T001"}) == ("T001/gate_north",) * 2  # turned back (M7 r3: int(None))


def test_a_day_road_lets_the_party_through_and_meets_people_on_it(tmp_path):
    """M8 r5: a fog stop on the same-day trail kept the party on the road while the prose went in; r6: a hunter met
    on the road was refused (unknown place)."""
    from neonrp.core.turn_settlement import _apply_player_move

    root = _install(tmp_path)  # the seeded hazards stay on
    assert _apply_player_move(root, "T001/guild")
    reg = load_registry(root)
    for turn in range(3, 9):  # whatever the seed, the day road has no stop
        for to in ("R002", "D001", "T001", "T001/guild"):
            vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": to}], reg)
            assert vr.refused == [], (turn, to, vr.refused)
            sdk.apply(root, vr.accepted, reg, turn=turn)
            reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "R002"}], reg)
    sdk.apply(root, vr.accepted, reg, turn=9)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "new_npc", "name": "灰帽猎人", "at": "road_T001_D001", "role": "猎人"}], reg)
    assert vr.refused == [], vr.refused
    sdk.apply(root, vr.accepted, reg, turn=9)
    reg = load_registry(root)
    hunter = reg.resolve("灰帽猎人")
    assert hunter and reg.entries[hunter].parent == reg.player_location == "road_T001_D001"


def test_a_road_tagged_with_beasts_has_something_to_fight(tmp_path):
    """M9 r3 / r6: wolves on the trail — [combat] refused (no stop on a day road, no room), the fight was dice in talk."""
    from neonrp.core.turn_settlement import _apply_player_move
    from neonrp.packs.rpg.understand import combat_grounds

    root = _install(tmp_path)
    _no_hazards(root)
    assert _apply_player_move(root, "T001/guild")
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "R002"}], reg)
    sdk.apply(root, vr.accepted, reg, turn=3)
    reg = load_registry(root)
    assert reg.player_location == "road_T001_D001" and combat_grounds(root, reg, {"op": "combat", "roster": "灰狼×1"}).ok


def test_a_place_off_the_road_grows_by_the_gate_and_can_be_walked_into(tmp_path, monkeypatch):
    """M9 r3: on the trail the party walked into a camp in the reeds the map did not have; the narrator wrote the
    town's gate (the only place it could name) and the state said 北门 while the prose was at the camp."""
    from neonrp.core import system_one as s1
    from neonrp.core.turn_settlement import _apply_player_move

    monkeypatch.setattr(s1, "ask", lambda *a, **k: {})  # no judge answer: it grows
    root = _install(tmp_path)
    _no_hazards(root)
    assert _apply_player_move(root, "T001/guild")
    reg = load_registry(root)
    for to in ("R002", "老鸦营地"):
        vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": to}], reg)
        assert vr.refused == [], vr.refused
        sdk.apply(root, vr.accepted, reg, turn=3)
        reg = load_registry(root)
    camp = reg.entries[reg.player_location]
    assert camp.name == "老鸦营地" and camp.parent == "T001"
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "D001"}], reg)
    assert vr.refused == [] and vr.accepted[0]["to"] == "D001/D001_R001"


def test_a_placeholder_handed_back_is_the_name_again(tmp_path, monkeypatch):
    """N2 M10 r6: the re-proposal carried `move player ~pending:place:mossbarrow_path` (and a doubly-prefixed one);
    the old placeholder was gone, so the prefix grew a second place — folder `~pending-place-mossbarrow_path`."""
    from neonrp.core import system_one as s1
    from neonrp.core.turn_settlement import _apply_player_move

    monkeypatch.setattr(s1, "ask", lambda *a, **k: {})
    root = _install(tmp_path)
    _no_hazards(root)
    _apply_player_move(root, "T001/gate_north")  # the opening spot already
    reg = load_registry(root)
    ops = [{"op": "new_location", "name": "~pending:place:苔径", "parent": "T001"},
           {"op": "move_to", "who": "player", "to": "~pending:place:苔径"},
           {"op": "move_to", "who": "si-elena0001", "to": "~pending:place:~pending:place:苔径"}]
    vr = sdk.verify(root, ops, reg)
    res = sdk.apply(root, vr.accepted, reg, turn=3)
    made = [c["id"] for c in res.created if c.get("class") == "place"]
    assert made == ["T001/苔径"], made
    assert not list((root / "game" / "locations" / "T001").glob("~pending*"))


def test_the_schema_is_open_a_class_nobody_defined_grows_when_used(tmp_path):
    """N2 1019 (niko 10-20: 「class 只是给我们辅助,而不是让我们 refuse 所有不在 class list 里面的 entity」): the world
    wrote `define class Ghoul … hp:int` and `new Ghoul …` — refused for the capital letter, then 「not a registrable
    class」 three times. Any spelling is the same handle, unknown types are text, and `new` of an undefined class defines it."""
    root = _install(tmp_path)
    ops = [sdk._adv_line_op(x) for x in ("define class Ghoul 洼地食尸鬼 hp:int kind:str note:str",
                                         "new Ghoul 洼地大食尸鬼 hp=14 kind=大", "new Ghoul 洼地小食尸鬼一 hp=6 kind=小")]
    reg = load_registry(root)
    vr = sdk.verify(root, ops, reg)
    assert not vr.refused, [r.why for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=4)
    reg = load_registry(root)
    assert sorted((e.name, e.props.get("hp")) for e in reg.of_class("ghoul")) == [("洼地大食尸鬼", 14), ("洼地小食尸鬼一", 6)]
    vr = sdk.verify(root, [sdk._adv_line_op("new 沼犬 沼地野犬 hp=5"), sdk._adv_line_op("patch ghoul/洼地大食尸鬼 hp=9")], reg)
    assert not vr.refused, [r.why for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=5)
    reg = load_registry(root)
    assert [e.name for e in reg.entries.values() if reg.classes[e.cls].title == "沼犬"] == ["沼地野犬"]


def test_the_world_writes_what_happens_to_a_character_not_what_she_feels(tmp_path):
    """N2 1019 (niko 10-20: 「世界会决定角色的装备和其他物品,可能改不了角色的心理描写」): `patch 艾琳娜 箭=…` was refused
    whole. Her body and things are the world's — written on her sheet (character/) and read back; her mood is hers."""
    root = _install(tmp_path)
    reg = load_registry(root)
    sid = next(e.id for e in reg.of_class("soul"))
    vr = sdk.verify(root, [sdk._adv_line_op(f"patch {sid} 箭=3 hp=7")], reg)
    assert not vr.refused, [r.why for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=4)
    e = load_registry(root).entries[sid]
    assert (e.props.get("箭"), e.props.get("hp")) == ("3", 7)
    vr = sdk.verify(root, [sdk._adv_line_op(f"patch {sid} mood=害怕")], load_registry(root))
    assert vr.refused and "mood" in vr.refused[0].why
    vr = sdk.verify(root, [sdk._adv_line_op(f"patch {sid} hp=5 mood=害怕")], load_registry(root))  # niko 10-20: only her mood goes back, fast
    assert [o["props"] for o in vr.accepted] == [{"hp": 5}] and [r.fixable for r in vr.refused] == [False]
    assert "_dropped" not in vr.accepted[0]


def test_the_world_writing_about_what_is_not_there_costs_no_rewrite(tmp_path):
    """N2 M12 r3 (niko 10-20「鲁棒性问题」): `patch {{user}}/轻伤` after it ended, `patch towns/T001/contracts/Q002.md`
    (the file for the entry), `set foe.foe_14.hp` after the fight — a stale or file-shaped reference is read or let go,
    never a rewrite round."""
    root = _install(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [sdk._adv_line_op("patch {{user}}/没有这个伤 turns=2")], reg)
    assert [r.fixable for r in vr.refused] == [False]
    e = next(e for e in reg.entries.values() if e.cls == "place" and e.source and "#" not in e.source)
    vr = sdk.verify(root, [sdk._adv_line_op(f"patch {e.source} note=雾里有东西")], reg)
    assert [o["who"] for o in vr.accepted] == [e.id], [r.why for r in vr.refused]
    short = e.id.rpartition("/")[2]
    if sum(1 for x in reg.entries if x.endswith("/" + short)) == 1:
        assert reg.lookup(short).ids == [e.id]
    vr = sdk.verify(root, [sdk._adv_line_op("patch 谁也不是 x=1")], reg)
    assert [r.fixable for r in vr.refused] == [True], "a plain unknown name still gets its rewrite (it may be a typo)"


def test_a_new_place_near_a_full_path_and_a_gate_only_another_town_has(tmp_path):
    """10-21 ID2: `new_location 采药摊 near=T001/townhall` was split at the slash into T001 and townhall, read as places
    that do not exist, and hung by the gate. PL4: in another town the prose said 「回到北门」 — only 石津镇 has a 北门,
    and the move took the party two days back there; a bare name only another town has is a place here the map lacks."""
    root = _install(tmp_path)
    reg = load_registry(root)
    near = next(e.id for e in reg.of_class("place") if e.id.startswith("T001/") and e.id != reg.player_location)
    vr = sdk.verify(root, [{"op": "new_location", "name": "采药摊", "near": near}], reg)
    assert not vr.refused and vr.accepted[0].get("targets", [near])[0] == near, vr.accepted
    sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T004/gate_west"}], reg, turn=1)
    reg = load_registry(root)
    day = reg.variables["time.day"].value
    gate = next(e for e in reg.of_class("place") if e.id.startswith("T001/") and not any(x.name == e.name for x in reg.of_class("place") if x.id.startswith("T004/")))
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": gate.name}], reg)
    assert not vr.refused, [r.why for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=2)
    reg = load_registry(root)
    assert reg.player_location.startswith("T004/") and reg.variables["time.day"].value == day, reg.player_location
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": gate.id}], reg)
    assert vr.accepted and vr.accepted[0]["to"] == gate.id, "a full path still means that town's place"


def test_a_commit_word_opening_the_line_settles_the_talk():
    """10-21 fixd PL12 r1: 「定，就付3金通铺，钱和木牌当面点清。」 — the commit word opened the line, only the end of a
    line counted, and the host urged 「要不就这么办?」 four beats running."""
    from neonrp.core import plan_loop

    assert plan_loop.commits("定，就付3金通铺，钱和木牌当面点清。")
    assert plan_loop.commits("现在就付——就这么定。") and plan_loop.commits("出发!")
    assert not plan_loop.commits("定金多少?") and not plan_loop.commits("定了吗?") and not plan_loop.commits("我们再想想")


def test_vars_take_a_change_by_an_amount_as_files_do():
    """10-23 niko: the write-down is pseudocode — deepseek wrote `player.gold -6` in <vars> (5 of 40 beats) and the
    parser only knew `name = value`, so the payment never landed. A signed amount is an add, as <files> reads it."""
    from neonrp.core.turn_v3 import parse_transition

    def one(line):
        return parse_transition(f"<vars>\n{line}\n</vars>")

    assert one("player.gold -6") == [{"op": "add", "var": "player.gold", "delta": -6}]
    assert one("player.gold -= 6") == one("player.gold - 6") == one("player.gold -6")
    assert one("player.silver += 2") == [{"op": "add", "var": "player.silver", "delta": 2}]
    assert one("player.gold = 6") == [{"op": "set", "var": "player.gold", "value": 6}]
    assert one("time.clock = 08:45") == [{"op": "set", "var": "time.clock", "value": "08:45"}]
    assert one('location = "T001/inn"') == [{"op": "move_to", "who": "player", "to": "T001/inn"}]
