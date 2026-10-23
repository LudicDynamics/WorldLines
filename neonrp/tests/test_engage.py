"""engage_soul(M30 V2a)契约回归:点名=leader 判断,引擎全档执行带回。

- 本体视角构建(她的场景 + 主持人转述,永不见玩家原文)
- soul JSON 报文解析带回(digest/inner_voice/intended_action)
- inbox 协议留痕:engage_request → soul_response(request_id 关联)
- 查无此人 → 报错不炸
"""

import shutil
from pathlib import Path
from unittest.mock import patch

from neonrp.core.conversation import ConversationTurnResult
from neonrp.core.engage import engage_soul_run
from neonrp.core.inbox import peek
from neonrp.core.skills import SKILL_SCHEMAS

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


_REPORT = (
    '{"state":"completed","digest":"她抬头看向门口,手按在药箱上。",'
    '"speech":"……你终于来了。","inner_voice":"他身上有血味。",'
    '"intended_action":"迎上去检查伤势","confidence":0.8,"urgency":0.7,'
    '"needs_world_decision":false,"memory_delta":"傍晚,他带伤回来了"}'
)


class _FakeBackend:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def respond(self, **kw):  # noqa: ANN003
        self.calls.append(kw)
        return ConversationTurnResult(
            success=True, run_id=kw.get("run_id", "r"), assistant_message=_REPORT,
            turns_used=1,
        )


def test_engage_full_loop_and_protocol(tmp_path: Path) -> None:
    root = _install(tmp_path)
    fake = _FakeBackend()
    with patch("neonrp.core.soul_backend.resolve_soul_backend", return_value=fake):
        out = engage_soul_run(root, "艾琳娜", note="玩家带伤推门而入")

    assert out["ok"] and out["iid"] == "si-elena0001" and out["name"] == "艾琳娜"
    # digest_line = 结构化报文行(role/state/action/speech/心象),给 leader 读
    assert out["digest"].startswith("- 艾琳娜") and "迎上去检查伤势" in out["digest"]
    assert out["inner_voice"] == "他身上有血味。"
    assert out["intended_action"] == "迎上去检查伤势"

    # 本体视角:场景包 + 角色权限 + 主持人转述;不含玩家原文机制
    perception = fake.calls[0]["messages"][0].content
    assert "【角色权限】" in perception and "玩家带伤推门而入" in perception
    assert "你的去向由 world-agent 裁定" in perception

    # 协议留痕:request → response 同一 request_id
    reqs = [m for m in peek(root, "si-elena0001") if m.kind == "engage_request"]
    resps = [m for m in peek(root, "world-agent") if m.kind == "soul_response"]
    assert reqs and resps
    assert resps[-1].payload["request_id"] == reqs[-1].payload["request_id"]


def test_engage_unknown_soul_errors(tmp_path: Path) -> None:
    root = _install(tmp_path)
    out = engage_soul_run(root, "不存在的人")
    assert not out["ok"] and "查无此人" in out["error"]


def test_engage_registered_in_skills() -> None:
    assert "engage_soul" in SKILL_SCHEMAS
    assert SKILL_SCHEMAS["engage_soul"]["parameters"]["required"] == ["soul"]


def test_engage_backend_failure_isolated(tmp_path: Path) -> None:
    # 工具失败带回 loop(M30 §5):backend 崩溃 → 错误结果,不炸回合
    root = _install(tmp_path)

    class _Boom:
        name = "boom"

        def respond(self, **kw):  # noqa: ANN003
            raise RuntimeError("soul worker crashed")

    with patch("neonrp.core.soul_backend.resolve_soul_backend", return_value=_Boom()):
        out = engage_soul_run(root, "艾琳娜")
    assert not out["ok"] and "隔离" in out["error"]


def test_escalate_note_reaches_next_preflight_channel(tmp_path: Path) -> None:
    # soul 上报 → 统一便签通道 → world-agent 下回合可 drain(deliver-once)
    from neonrp.core.notes import drain_notes, post_note

    root = _install(tmp_path)
    post_note(root, "escalation", "[soul:si-elena0001] 我要连夜去后山找草药", sender="si-elena0001")
    lines = drain_notes(root, "escalation")
    assert lines == ["[soul:si-elena0001] 我要连夜去后山找草药"]
    assert drain_notes(root, "escalation") == []  # deliver-once


def test_heartbeat_light_reaction(tmp_path: Path, monkeypatch) -> None:
    """在场轻心跳(M30 lifecycle):一次轻调用出一两句反应;失败回落。"""
    from neonrp.core import light_chat
    from neonrp.core.engage import heartbeat_soul_run
    from neonrp.core.playthrough import read_playthrough

    root = _install(tmp_path)
    ref = next(s for s in read_playthrough(root).souls if s.instance_id == "si-elena0001")

    class _R:
        class message:
            content = "(她抬眼看向门口,手指在桌沿轻敲了两下。)"

    class _A:
        def chat(self, messages, tools=None):  # noqa: ANN001
            assert tools is None
            assert "只做一件事" in messages[0].content  # 轻契约
            return _R()

    monkeypatch.setattr(light_chat, "_adapter", lambda _root: _A())
    out = heartbeat_soul_run(root, ref, "玩家推门而入,带着一身雨气")
    assert out["ok"] and "轻敲" in out["line"]

    class _Boom:
        def chat(self, *a, **k):  # noqa: ANN002, ANN003
            raise RuntimeError("down")

    monkeypatch.setattr(light_chat, "_adapter", lambda _root: _Boom())
    out2 = heartbeat_soul_run(root, ref, "x")
    assert not out2["ok"]  # 失败回落由调用方走 memo,不破回合
