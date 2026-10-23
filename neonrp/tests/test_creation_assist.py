"""创作台「用一句话说」(niko 10-18 · PLATFORM-PLAY-RULES-1015 §10 / §5「不让作者写 if / else」):作者说一句规则 / 脑洞,
小 agent 只用模板开放的那一层(creation.form 的分区、触发、收集条件)把它落成表单的行,回补丁 + 预览,不写盘;作者确认后
照旧走 creation/work 存,过 check()。做不到的说人话(「这个模板不开放 X」)+ 最接近的替代。

假模型按固定输出回放(read_form → propose → done),不真调 LLM。"""
from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from neonrp import template as TP
from neonrp.template import creation, creation_assist as CA

TPLS = Path(__file__).resolve().parents[1] / "worldlines" / "templates"


class Replay:
    """A model that says the given replies in order and remembers what it was asked."""

    def __init__(self, *replies):
        self.replies, self.asked = [json.dumps(r, ensure_ascii=False) if not isinstance(r, str) else r for r in replies], []

    def generate(self, system, user, tools=None):
        self.asked.append((system, user))
        return SimpleNamespace(raw_output=self.replies.pop(0) if self.replies else '{"tool": "done"}', error=None)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    ro, mine = tmp_path / "official", tmp_path / "mine"
    for n in ("stoneford-town", "guixiang", "neon-rebirth"):
        shutil.copytree(TPLS / f"{n}.template", ro / f"{n}.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    return mine


def _t(tid):
    return TP.load(TP.discover()[tid])


def test_read_form_shows_only_what_the_template_opens(desk):
    ctx = CA.context(_t("guixiang"), {})
    assert [s["key"] for s in ctx["sections"]] == ["clue", "ending", "rule"] and "soul" in ctx["closed"]
    assert ctx["triggers"] == {"when": ["text", "flag", "entry"], "then": ["narration", "soul", "flag", "end"]}
    assert {"id": "T001/well", "name": "村口老井"} in ctx["world"]["places"]
    assert any(c["id"] == "xiulian" for c in ctx["world"]["characters"])


def test_a_character_condition_she_leaves_after_three_lies(desk):
    """角色条件(var 开放的模板):「她被骗三次就会离开」→ 一条每次 +1、一条 ≥3 时她走。"""
    lie = {"doc": "对伊瑟说谎记一次", "trigger": {"when": {"text": "player"}, "if": [{"text": ["骗", "谎"]}],
                                                "then": [{"to": "var", "var": "lied.isse", "add": 1}]}}
    leave = {"doc": "被骗三次伊瑟离开", "trigger": {"when": {"var": "lied.isse"}, "if": [{"var": "lied.isse", ">=": 3}],
                                                 "then": [{"to": "narration", "text": "伊瑟不再看你,转身走进雨里。"},
                                                          {"to": "flag", "key": "left.isse"}], "once": True}}
    m = Replay({"tool": "read_form"}, {"tool": "propose", "ops": [{"op": "add", "sec": "rule", "row": lie}, {"op": "add", "sec": "rule", "row": leave}]},
               {"tool": "done", "reply": "加了两条规则:你每骗她一次记一笔,第三次她就走。"})
    start = {"ending": [{"title": "雨停", "kind": "true"}], "reveal": "九条就是终章机"}
    r = CA.assist(_t("neon-rebirth"), start, "她被骗三次就会离开", adapter=m)
    assert r["ok"] and r["problems"] == [] and r["unsupported"] == [], r
    assert r["addition"]["rule"] == [lie, leave] and r["addition"]["ending"] == start["ending"]
    assert [p["op"] for p in r["preview"]] == ["add", "add"]
    assert "第 3" not in r["preview"][1]["text"] and "lied.isse >= 3" in r["preview"][1]["text"] and "旁白" in r["preview"][1]["text"]
    assert "她被骗三次就会离开" in m.asked[0][1] and '"places"' in m.asked[1][1], "read_form's answer goes back to the model"
    assert start == {"ending": [{"title": "雨停", "kind": "true"}], "reveal": "九条就是终章机"}, "the creator's draft is not edited in place"


def test_a_place_gate_key_before_the_cellar(desk):
    """地点门槛:「拿到钥匙后才能进地下室」→ 线索 + 拿到时设标记 + 没标记时进入就被旁白挡回;存进作品照样过 check。"""
    rows = [{"op": "add", "sec": "clue", "row": {"name": "铁钥匙", "summary": "教堂地下室的钥匙,挂在杂货铺柜台后", "where": "T001/shop_general"}},
            {"op": "add", "sec": "rule", "row": {"doc": "拿到钥匙", "trigger": {"when": {"text": "player"}, "if": [{"text": "钥匙"}],
                                                                              "then": [{"to": "flag", "key": "has.key"}], "once": True}}},
            {"op": "add", "sec": "rule", "row": {"doc": "没钥匙进不去地下室", "trigger": {
                "when": {"entry": "T004/chapel", "event": "enter", "who": "player"}, "if": [{"flag": "has.key", "is": False}],
                "then": [{"to": "narration", "text": "地下室的门锁着,你只能退回去。"}]}}}]
    m = Replay({"tool": "read_form"}, {"tool": "propose", "ops": rows}, {"tool": "check"}, {"tool": "done", "reply": "钥匙放在杂货铺;没拿到时进教堂地下室会被挡回来。"})
    t = _t("stoneford-town")
    r = CA.assist(t, {}, "拿到钥匙后才能进地下室", adapter=m)
    assert r["ok"] and r["steps"] == 4 and len(r["addition"]["rule"]) == 2 and r["addition"]["clue"][0]["where"] == "T001/shop_general", r
    gate = r["preview"][2]["text"]
    assert "进入 晨光小教堂 时" in gate and "T004/chapel" not in gate and "还没有标记「has.key」" in gate, gate
    w = creation.save(t, r["addition"], work_id="stoneford-town-mine")
    plot = json.loads((w.dir / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))
    assert plot["triggers"]["mine_R02"]["when"]["entry"] == "T004/chapel" and plot["entries"]["mine_C01"]["name"] == "铁钥匙"


def test_a_collect_condition_take_the_boss_home_at_the_bad_ending(desk):
    """收集条件:「玩到坏结局可以带走老板」→ 一个失败结局 + 一个能在那个结局带走的角色;存进作品后 collect 指向它。"""
    m = Replay({"tool": "read_form"},
               {"tool": "propose", "ops": [{"op": "add", "sec": "ending", "row": {"title": "雾吞小镇", "kind": "fail", "text": "雾没有退。"}},
                                           {"op": "add", "sec": "soul", "row": {"name": "老板", "persona": "河灯旅店的老板,嘴硬心软", "collect": "ending",
                                                                                "collect_ending": "#2", "rarity": "rare"}}]},
               {"tool": "done", "reply": "加了坏结局「雾吞小镇」,走到它就能带走老板。"})
    t = _t("stoneford-town")
    start = {"ending": [{"title": "雾散", "kind": "true"}]}
    r = CA.assist(t, start, "玩到坏结局可以带走老板", adapter=m)
    assert r["ok"], r
    assert "走到结局 #2 能带走" in r["preview"][1]["text"] and "坏结局" in r["preview"][0]["text"]
    w = creation.save(t, r["addition"], work_id="stoneford-town-mine")
    plot = json.loads((w.dir / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))
    assert plot["collect"] == {"mine_N01": {"on": {"ending": "mine_E2"}, "rarity": "rare"}} and plot["endings"]["mine_E2"]["kind"] == "fail"


def test_what_the_template_does_not_open_is_said_plainly(desk):
    """做不到的:guixiang 不开放新角色 —— 引擎拒掉 soul 行,模型给最接近的替代;模型没说的引擎自己补一句人话。"""
    m = Replay({"tool": "read_form"},
               {"tool": "propose", "ops": [{"op": "add", "sec": "soul", "row": {"name": "黑猫", "persona": "会说话的黑猫"}}]},
               {"tool": "done", "reply": "这个世界不能加新角色。",
                "unsupported": [{"what": "这个模板不开放新角色", "nearest": "把黑猫写成一条线索,让莲妹在井边提起它"}]})
    r = CA.assist(_t("guixiang"), {}, "加一只会说话的黑猫,结局时能带走它", adapter=m)
    assert not r["ok"] and r["ops"] == [] and r["addition"] == {} and r["preview"] == []
    assert r["unsupported"][0] == {"what": "这个模板不开放新角色", "nearest": "把黑猫写成一条线索,让莲妹在井边提起它"}
    assert {"what": "这个模板不开放「角色」", "nearest": ""} in r["unsupported"]
    assert '"rejected": [{"op"' in m.asked[2][1] and "closed:soul" in m.asked[2][1], "the model hears why"
    # a trigger effect the template does not open (stoneford: no var), in English
    m = Replay({"tool": "propose", "ops": [{"op": "add", "sec": "rule", "row": {"trigger": {"when": {"text": "player"}, "then": [{"to": "var", "var": "x", "add": 1}]}}}]},
               {"tool": "done"})
    r = CA.assist(_t("stoneford-town"), {}, "count every lie", lang="en", adapter=m)
    assert r["unsupported"] == [{"what": "This template does not open the “value” effect", "nearest": ""}] and not r["ok"]


def test_set_and_del_ops_and_bad_replies(desk):
    t = _t("stoneford-town")
    start = {"soul": [{"name": "阿青", "persona": "猎人", "collect": "clear"}], "clue": [{"name": "a", "summary": "b"}]}
    m = Replay("not json at all",
               {"tool": "propose", "ops": [{"op": "set", "sec": "soul", "i": 0, "field": "collect", "value": "companion"},
                                           {"op": "set", "sec": "soul", "i": 0, "field": "collect", "value": "flag"},
                                           {"op": "set", "sec": "soul", "i": 0, "field": "collect_flag", "value": "joined.aqing"},
                                           {"op": "del", "sec": "clue", "i": 0}, {"op": "del", "sec": "clue", "i": 5},
                                           {"op": "add", "sec": "clue", "row": {"name": "x", "summary": "y", "secret": 1}}]},
               "```json\n{\"tool\": \"done\", \"reply\": \"ok\"}\n```")
    r = CA.assist(t, start, "阿青入队就能带走", adapter=m)
    assert "exactly one JSON object" in m.asked[1][1]
    assert r["addition"]["soul"][0] == {"name": "阿青", "persona": "猎人", "collect": "flag", "collect_flag": "joined.aqing"}
    assert r["addition"]["clue"] == [{"name": "x", "summary": "y"}] and r["reply"] == "ok" and r["ok"]
    assert {"what": "这个模板的「怎么被收集」只能选:clear, ending, flag", "nearest": ""} in r["unsupported"]
    assert [p["op"] for p in r["preview"]] == ["set", "set", "del", "add"]
    assert "怎么被收集:通关就能带走" not in r["preview"][0]["text"] and "clear → flag" in r["preview"][0]["text"]


def test_no_model_and_nothing_said(desk, monkeypatch):
    t = _t("stoneford-town")
    with pytest.raises(CA.AssistError) as e:
        CA.assist(t, {}, "  ", adapter=Replay())
    assert e.value.code == "empty"
    from neonrp.core.llm_stub import StubAdapter

    with patch("neonrp.core.hub_publish.adapter_for_preset", return_value=StubAdapter()), pytest.raises(CA.AssistError) as e:
        CA.assist(t, {}, "随便")
    assert e.value.code == "no_model"


def test_every_language_has_the_lines():
    from neonrp import prompts

    zh = prompts.strings("creation_assist_lines", "zh")
    for lg in prompts.LANGS:
        assert set(prompts.strings("creation_assist_lines", lg)) == set(zh)
        assert '"tool": "read_form"' in prompts.text("creation_assist", lg)


def test_assist_route(desk, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    m = Replay({"tool": "propose", "ops": [{"op": "add", "sec": "ending", "row": {"title": "雾散", "kind": "true"}}]}, {"tool": "done", "reply": "好"})
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
        patch("neonrp.template.creation_assist._adapter", return_value=m),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, b):
            req = urllib.request.Request(base + path, data=json.dumps(b).encode(), method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        try:
            st, b = call("/api/v1/local/templates/stoneford-town/creation/assist", {"addition": {}, "say": "好结局叫雾散", "lang": "zh"})
            assert st == 200 and b["ok"] and b["addition"] == {"ending": [{"title": "雾散", "kind": "true"}]} and b["reply"] == "好", b
            assert not (desk / "stoneford-town-mine").exists(), "assist never writes"
            st, b = call("/api/v1/local/templates/stoneford-town/creation/assist", {"addition": {}, "say": ""})
            assert st == 400 and b["error"] == "empty"
            st, b = call("/api/v1/local/templates/nope/creation/assist", {"say": "x"})
            assert st == 404
        finally:
            server.shutdown()
