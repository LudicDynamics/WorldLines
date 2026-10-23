"""ask_soul 主权双向通道(M24 §5)契约回归。

判断力(该不该问/问什么/可达性)归 world-agent;引擎只投递与带回。
协议留痕:收件箱 ask_request→soul_response(request_id 关联);
soul 记忆 commit(被问也是经历);无同场硬门。
"""

import json
import shutil
from pathlib import Path

from neonrp.core import light_chat
from neonrp.core.inbox import peek
from neonrp.core.light_chat import ask_soul_deliver

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeRes:
    def __init__(self, content: str) -> None:
        self.message = _FakeMsg(content)


class _FakeAdapter:
    def __init__(self, reply: str = "……可以,但得等我处理完手上的伤口。") -> None:
        self.reply = reply
        self.calls: list[list] = []

    def chat(self, messages, tools=None):  # noqa: ANN001
        assert tools is None  # 纯问答,无工具
        self.calls.append(messages)
        return _FakeRes(self.reply)


def test_ask_by_local_name_full_loop(tmp_path: Path, monkeypatch) -> None:
    root = _install(tmp_path)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)

    out = ask_soul_deliver(root, "艾琳娜", "玩家发来讯息:晚上一起吃饭?你怎么回应?")

    assert out["ok"] is True and out["iid"] == "si-elena0001"
    assert out["answer"] == fake.reply and out["name"] == "艾琳娜"
    # 她的本体视角进了 system(场景+人格+记忆)
    system = fake.calls[0][0].content
    assert "你此刻在" in system and "你的人格" in system and "你的记忆" in system
    # 协议留痕:ask_request 与 soul_response 同一 request_id
    reqs = peek(root, "si-elena0001", kind="ask_request", unread_only=False)
    resps = peek(root, "world-agent", kind="soul_response", unread_only=False)
    assert len(reqs) == 1 and len(resps) == 1
    assert reqs[0].payload["request_id"] == resps[0].payload["request_id"]
    # 记忆 commit(被问也是经历)
    memo = json.loads(
        (root / "souls" / "elena-si-elena0001" / "short-term-memo" / "recent_events.json").read_text(
            encoding="utf-8"
        )
    )
    assert any("主持人问我" in e["event"] for e in memo["events"])


def test_ask_offsite_soul_no_hard_gate(tmp_path: Path, monkeypatch) -> None:
    # 无同场硬门:rowan 在 T004(异地)也能被问 —— 可达性是 world-agent 的
    # 叙事判断(中世纪送信三天是它的叙事);co_located=False 作为事实返回。
    root = _install(tmp_path)
    fake = _FakeAdapter("(在公会抬头)谁?哦——告诉他我月底回去。")
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    out = ask_soul_deliver(root, "罗文", "有人从石津镇捎话问你何时回去。")
    assert out["ok"] is True and out["co_located"] is False
    assert "T004" in out["location"]


def test_ask_unknown_and_empty(tmp_path: Path) -> None:
    root = _install(tmp_path)
    assert ask_soul_deliver(root, "神秘人", "你是谁")["ok"] is False
    assert ask_soul_deliver(root, "艾琳娜", "  ")["ok"] is False


def test_skill_surface(tmp_path: Path, monkeypatch) -> None:
    # world-agent 经 SkillRegistry 调用的技能面。
    from neonrp.core.skills import SKILL_SCHEMAS, SkillRegistry, get_skill_schemas

    assert "ask_soul" in SKILL_SCHEMAS
    assert any(s.get("name") == "ask_soul" for s in get_skill_schemas())
    root = _install(tmp_path)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    reg = SkillRegistry(
        root=root, run_id="t", agent_id="world-agent", read_globs=["**"], deny_globs=[]
    )
    r = reg.invoke("ask_soul", {"soul": "艾琳娜", "question": "你愿意带路吗?"})
    assert r.success is True and r.data["soul"] == "艾琳娜" and r.data["answer"]
    r2 = reg.invoke("ask_soul", {"soul": "", "question": ""})
    assert r2.success is False
