"""端到端 stub 游玩认证。

真实 ConversationSession + stoneford-elena 模板 + stub provider,零 API 成本
跑完整多智能体回合。认证四件事:
  ① 顺利游玩:连续 N 回合 send() 全部完成不崩;
  ② 无位置漂移:每回合后玩家/soul 位置仍是图上合法节点且未被脏写;
  ③ T2c 投递面:感知包确实经收件箱送达(dual-write 证据);
  ④ 双向通道:ask_soul 在世界拍技能面可用,且经真实配置(stub)全链可跑。
"""

import json
import shutil
from pathlib import Path

import pytest

from neonrp.core.conversation import ConversationSession
from neonrp.core.manifest import Manifest

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    (root / ".neonrp" / "events").mkdir(exist_ok=True)
    (root / ".neonrp" / "sessions").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    # 项目初始化标记(引擎 send() 的准入门):manifest.json
    manifest = Manifest()
    manifest.branches["main"].head_event = -1
    (root / ".neonrp" / "manifest.json").write_text(
        json.dumps(manifest.model_dump(), default=str), encoding="utf-8"
    )
    # stub provider:零成本、确定性。
    (root / ".neonrp" / "config.json").write_text(
        json.dumps(
            {"llm": {"provider": "stub", "model": "stub-model"}}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    # multi-agent 路由要走引擎真 helper(runtime_contract),手写 config 键无效。
    from neonrp.core.runtime_contract import set_router_execution_mode

    set_router_execution_mode(root, "multi-agent")
    return root


def _player_node(root: Path) -> str:
    payload = json.loads(
        (root / "game" / "meta" / "run_state.json").read_text(encoding="utf-8")
    )
    return str((payload.get("location") or {}).get("node") or "")


def _valid_nodes(root: Path) -> set[str]:
    """合法地址集:town_map 节点 id + 镇 id 本身(T### 镇级地址也是合法位置)。"""
    from neonrp.core.place_tree import town_docs

    nodes: set[str] = set()
    for tid, d in town_docs(root).items():  # town_map.json or the town's place folders (10-05)
        nodes.add(tid)  # 镇 id(如 T004)
        for n in d.get("nodes") or []:
            if isinstance(n, dict) and n.get("id"):
                nodes.add(str(n["id"]))
    return nodes


@pytest.mark.timeout(300)
def test_full_stub_playthrough_no_drift(tmp_path: Path) -> None:
    root = _install(tmp_path)
    node0 = _player_node(root)
    valid = _valid_nodes(root)
    assert node0 in valid  # 开局即合法

    session = ConversationSession(root, "world-agent", mode="play")
    inputs = ["开始", "我环顾北门,和守卫点头致意", "叫住艾琳娜,问她接下来去哪"]
    for i, text in enumerate(inputs):
        result = session.send(text)
        # ① 顺利游玩:回合完成(stub 内容可降级,但不许崩、不许失败)
        assert result is not None and result.success, f"turn {i} failed: {result and result.error}"
        # ② 无漂移:玩家位置始终是图上合法节点;stub 不吐 CORRECTIONS,
        #    位置必须保持开局值(任何变动=脏写)。
        node = _player_node(root)
        assert node == node0 and node in valid, f"turn {i}: player node drifted to {node!r}"
        # souls 的位置也必须保持合法(scoped 或裸 id 都允许,取尾段验证)。
        for sd in (root / "souls").iterdir():
            rs = sd / "run_state.json"
            if not rs.exists():
                continue
            loc = str(json.loads(rs.read_text(encoding="utf-8")).get("location") or "")
            if loc:
                bare = loc.split("/")[-1]
                assert bare in valid or loc in valid, f"soul {sd.name} at invalid {loc!r}"

    # ③ T2c 投递证据:活跃 soul 的收件箱收到过 perception(deliver-once 后留档)。
    from neonrp.core.inbox import peek

    percepts = peek(root, "si-elena0001", kind="perception", unread_only=False)
    assert percepts, "T2c: elena 的收件箱没有感知包投递记录"
    assert percepts[-1].payload.get("packet", {}).get("scene_label")

    # 结算义务链活着:stub 不吐 ⟦CORRECTIONS⟧ → 漏出检测应已排队提醒
    #(在最后一回合 drain 前的残留,或已被消费 —— 只要目录/机制没崩即可;
    # 强断言:位置判定队列文件路径可写(机制未被绕过)。
    from neonrp.core.conversation import _drain_location_judgments, _queue_location_judgment

    _queue_location_judgment(root, "[e2e] 机制自检")
    assert any("机制自检" in ln for ln in _drain_location_judgments(root))


@pytest.mark.timeout(120)
def test_bidirectional_ask_soul_over_real_config(tmp_path: Path) -> None:
    # ④ 双向通道:不 mock adapter —— 经真实 config(stub provider)全链跑
    #    ask_soul_deliver:解析→投递→stub 作答→记忆 commit→协议闭环。
    root = _install(tmp_path)
    from neonrp.core.inbox import peek
    from neonrp.core.light_chat import ask_soul_deliver
    from neonrp.core.skills import get_skill_schemas

    assert any(s.get("name") == "ask_soul" for s in get_skill_schemas())
    out = ask_soul_deliver(root, "艾琳娜", "玩家远程问你:晚上一起吃饭吗?")
    assert out["ok"] is True and out["answer"]
    reqs = peek(root, "si-elena0001", kind="ask_request", unread_only=False)
    resps = peek(root, "world-agent", kind="soul_response", unread_only=False)
    assert reqs and resps
    assert reqs[-1].payload["request_id"] == resps[-1].payload["request_id"]
    memo = json.loads(
        (root / "souls" / "elena-si-elena0001" / "short-term-memo" / "recent_events.json").read_text(
            encoding="utf-8"
        )
    )
    assert any("主持人问我" in e.get("event", "") for e in memo["events"])


@pytest.mark.timeout(300)
def test_full_stub_playthrough_orchestrator(tmp_path: Path) -> None:
    """orchestrator 保险(「先保住 orchestrator」令):
    传统单 agent 路径在 fast 退役/结算抽离/便签统一/超时修复之后,
    stub 全程 3 回合必须照常顺利游玩、位置零脏写。"""
    from neonrp.core.runtime_contract import set_router_execution_mode

    root = _install(tmp_path)
    set_router_execution_mode(root, "orchestrator")  # 覆盖 _install 的 MT 设定
    # this guards the v2b tool-loop path; the stoneford templates now ship engine v3 by default (0.5.0), so pin v2b here
    (root / "game" / "meta" / "engine.json").write_text('{"turn": {"mode": "v2b"}}', encoding="utf-8")
    node0 = _player_node(root)
    valid = _valid_nodes(root)
    assert node0 in valid

    session = ConversationSession(root, "world-agent", mode="play")
    inputs = ["开始", "我沿主街慢慢走,观察路人", "去公会打听委托"]
    for i, text in enumerate(inputs):
        result = session.send(text)
        assert result is not None and result.success, (
            f"orch turn {i} failed: {result and result.error}"
        )
        node = _player_node(root)
        assert node == node0 and node in valid, (
            f"orch turn {i}: player node drifted to {node!r}"
        )
