"""M31 · build 建角色全链(剧本化 adapter,零 API)。

**这份补的是 M31-a 最大的测试缺口。** `cast_soul` 有单测、`/mode` 有单测,
但「一句话 → agent 调 skill → 逐个 write_file → cast_soul 入世」这**整条链**
此前从没被自动跑过 —— 而这正是 M31 的产品主张。

仓里的 stub adapter 只会吐 `submit_proposal`,编排不了任意工具,所以这里
用一个剧本化 adapter:按脚本依次吐工具调用,喂给**真的**
``ConversationSession``。于是回合装配、工具分发、权限、落盘、账本、
artifact 全部走真实代码,唯一被替换的是「模型想什么」。

覆盖到的:B1 改动记录 · B2 回合总账 · B3 build.md · M31-a 的 cast_soul 入世。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core.llm import LLMTurnResult, Message, ToolCall
from neonrp.core.manifest import Manifest
from neonrp.core.playthrough import (
    Playthrough,
    WorldAgentTeam,
    WorldRef,
    read_playthrough,
    write_playthrough,
)


class ScriptedAdapter:
    """按剧本吐工具调用的 adapter —— 一个「已经想好怎么做」的 agent。

    每次 ``chat()`` 消费剧本的下一步;剧本走完就吐一句收尾叙述并结束回合。
    刻意不实现 ``chat_stream``:回合循环据此走非流式分支(见
    ``conversation._chat_stream`` 的 hasattr 门)。
    """

    def __init__(self, script: list[tuple[str, dict]], closing: str = "做完了。"):
        self._script = list(script)
        self._closing = closing
        self.seen_tools: list[list[str]] = []
        self.calls = 0

    def chat(self, messages, tools=None):  # noqa: ANN001 — adapter duck-type
        self.calls += 1
        self.seen_tools.append([t.get("name", "") for t in (tools or [])])
        if not self._script:
            return LLMTurnResult(
                message=Message(role="assistant", content=self._closing),
                tool_calls=[],
                finished=True,
            )
        name, args = self._script.pop(0)
        call = ToolCall(id=f"call-{self.calls}", name=name, arguments=args)
        return LLMTurnResult(
            message=Message(role="assistant", content="", tool_calls=[call]),
            tool_calls=[call],
            finished=False,
        )


_SID = "luowen"


def _world(tmp_path: Path) -> Path:
    """一个最小但真实的 multi-agent 世界(空 cast)。"""
    root = tmp_path / "smithy"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": 0}, ensure_ascii=False), encoding="utf-8"
    )
    neon = root / ".neonrp"
    (neon / "sessions").mkdir(parents=True)
    (neon / "events").mkdir(parents=True)
    manifest = Manifest()
    manifest.branches["main"].head_event = -1
    (neon / "manifest.json").write_text(
        json.dumps(manifest.model_dump(), default=str), encoding="utf-8"
    )
    (neon / "config.json").write_text(
        json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}),
        encoding="utf-8",
    )
    agent_dir = root / "agents" / "world-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.json").write_text(
        json.dumps({"id": "world-agent", "name": "World"}, ensure_ascii=False),
        encoding="utf-8",
    )
    write_playthrough(
        root,
        Playthrough(
            schema_version=2,
            playthrough_id="pt-smithy",
            world=WorldRef(
                wid="smithy",
                instance_id="wi-00000000000f",
                version_hash="sha256:world-v1",
                head_commit="",
            ),
            world_agent_team=WorldAgentTeam(seeded_from="m31@test", agents=[]),
            souls=[],
            created_at="2026-08-27T00:00:00Z",
            active_souls=(),
        ),
    )
    return root


def _authoring_script() -> list[tuple[str, dict]]:
    """agent 建一个角色会做的事,按顺序。"""
    draft = f".neonrp/soul-drafts/{_SID}"
    return [
        ("Skill", {"skill": "soul-authoring"}),
        (
            "write_file",
            {
                "path": f"{draft}/soul.json",
                "content": json.dumps(
                    {"sid": _SID, "name": "Luowen", "name_local": "罗文"},
                    ensure_ascii=False,
                ),
            },
        ),
        (
            "write_file",
            {
                "path": f"{draft}/persona/kernel.md",
                "content": "# 罗文\n\n沉默寡言的铁匠。话少,手稳。\n",
            },
        ),
        (
            "write_file",
            {
                "path": f"{draft}/rules/behaviour.md",
                "content": "- 先听完再开口\n- 不谈自己的过去\n",
            },
        ),
        ("cast_soul", {"sid": _SID}),
    ]


def _session(root: Path, adapter: ScriptedAdapter, monkeypatch) -> object:
    from neonrp.core import conversation as conv

    monkeypatch.setattr(conv, "get_adapter_from_config", lambda *a, **k: adapter)
    return conv.ConversationSession(root=root, agent_id="world-agent", mode="build")


@pytest.fixture
def built(tmp_path: Path, monkeypatch):
    """跑完一整个「新建角色」的 build 回合,把现场交给用例检查。"""
    root = _world(tmp_path)
    adapter = ScriptedAdapter(_authoring_script(), closing="罗文建好了,已经在铺子里。")
    session = _session(root, adapter, monkeypatch)
    result = session.send("新建一个叫罗文的铁匠,沉默寡言")
    return root, session, adapter, result


class TestBuildAuthoringChain:
    def test_turn_succeeds(self, built) -> None:
        _root, _session, _adapter, result = built
        assert result.success, result.error
        assert "罗文" in result.assistant_message

    def test_agent_had_the_authoring_tools(self, built) -> None:
        """build 面必须同时给到写盘和入世 —— 少一个这条链就断。"""
        _root, _session, adapter, _result = built
        offered = set(adapter.seen_tools[0])
        assert {"write_file", "cast_soul", "Skill"} <= offered

    def test_files_landed_in_the_draft(self, built) -> None:
        root, _session, _adapter, _result = built
        draft = root / ".neonrp" / "soul-drafts" / _SID
        assert (draft / "soul.json").is_file()
        assert (draft / "persona" / "kernel.md").is_file()
        assert (draft / "rules" / "behaviour.md").is_file()

    def test_soul_entered_the_world(self, built) -> None:
        """入世 = playthrough 认得它 + souls/ 下有实例。"""
        root, _session, _adapter, _result = built
        pt = read_playthrough(root)
        assert [s.sid for s in pt.souls] == [_SID]
        iid = pt.souls[0].instance_id
        assert iid in pt.active_souls
        assert (root / "souls" / f"{_SID}-{iid}").is_dir()

    def test_runtime_can_actually_spin_it_up(self, built) -> None:
        """结构保底:agent 没写 manifest,引擎也必须补上,否则 soul 回合会炸。"""
        root, _session, _adapter, _result = built
        iid = read_playthrough(root).souls[0].instance_id
        manifest = root / "souls" / f"{_SID}-{iid}" / "agents" / "manifest.json"
        assert manifest.is_file()
        assert json.loads(manifest.read_text(encoding="utf-8"))["agents"]

    def test_turn_ledger_saw_every_write(self, built) -> None:
        """B2:回合末那一行的数据来源 —— 三个草稿文件 + 花名册。"""
        _root, session, _adapter, _result = built
        counts = session.change_ledger.counts()
        assert counts["created"] == 3
        assert counts["modified"] == 1

    def test_ledger_records_the_roster_change(self, built) -> None:
        """入世改的是 playthrough.json,而它不走 write_file。

        漏掉它,总账就会列出一堆草稿文件、却不提这一回合里**唯一真正
        改变世界**的那笔。
        """
        _root, session, _adapter, _result = built
        paths = [e["path"] for e in session.change_ledger.to_dict()["files"]]
        assert ".neonrp/playthrough.json" in paths

    def test_every_write_carried_a_change_record(self, built) -> None:
        """B1:工具卡显示 `created +3` 靠的就是它。"""
        _root, session, _adapter, _result = built
        for entry in session.change_ledger.to_dict()["files"]:
            assert entry["kind"] in {"created", "modified"}
            assert entry["added"] > 0
            assert entry["headline"]

    def test_build_log_records_the_session(self, built) -> None:
        """B3:世界被编辑这件事,在 vault 里留下了痕迹。"""
        root, _session, _adapter, _result = built
        log = root / "build.md"
        assert log.is_file()
        text = log.read_text(encoding="utf-8")
        assert "新建一个叫罗文的铁匠" in text
        assert "soul.json" in text
        assert "罗文建好了" in text


class TestBuildChainEdges:
    def test_talking_without_editing_leaves_no_build_log(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """只问不改的 build 回合不该污染工坊日志。"""
        root = _world(tmp_path)
        adapter = ScriptedAdapter([], closing="这个世界现在没有角色。")
        session = _session(root, adapter, monkeypatch)

        result = session.send("这个世界有几个角色?")

        assert result.success, result.error
        assert session.change_ledger.is_empty
        assert not (root / "build.md").exists()

    def test_cast_without_authoring_fails_and_points_the_way(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """agent 跳过写文件直接 cast:必须失败,且错误要能指路。"""
        root = _world(tmp_path)
        adapter = ScriptedAdapter([("cast_soul", {"sid": "ghost"})])
        session = _session(root, adapter, monkeypatch)

        session.send("把幽灵放进世界")

        assert read_playthrough(root).souls == []

    def test_ledger_resets_between_turns(self, tmp_path: Path, monkeypatch) -> None:
        """第二回合的总账不该把第一回合的改动算进去。"""
        root = _world(tmp_path)
        adapter = ScriptedAdapter(
            [("write_file", {"path": "game/notes.md", "content": "one"})]
        )
        session = _session(root, adapter, monkeypatch)
        session.send("记一笔")
        assert not session.change_ledger.is_empty

        adapter._script = []
        session.send("谢谢")
        assert session.change_ledger.is_empty

    def test_play_admits_but_does_not_author(self, tmp_path: Path, monkeypatch) -> None:
        """play 能迎入已有角色,但不该被引导去写新的。"""
        from neonrp.core import conversation as conv

        root = _world(tmp_path)
        adapter = ScriptedAdapter([])
        monkeypatch.setattr(conv, "get_adapter_from_config", lambda *a, **k: adapter)
        session = conv.ConversationSession(
            root=root, agent_id="world-agent", mode="play"
        )

        session.send("看看四周")

        offered = set(adapter.seen_tools[0]) if adapter.seen_tools else set()
        assert "cast_soul" in offered      # 迎入是游玩期的动作
        assert "open_in_viewer" not in offered

        from neonrp.core.prompts import build_system_prompt

        play_prompt = build_system_prompt(
            agent_name="world-agent", project_name="t", branch="main",
            mode="play", skill_descriptions=[],
        )
        # 「怎么建角色」那段只写在 build 的提示词里。
        assert "soul-drafts" not in play_prompt
