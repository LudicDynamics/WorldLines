"""M27 v1 — roll_check skill(dice.py 原语接入结算链)契约回归。

裁定/掷分离:target 由调用方给,点数由引擎掷;纯计算不改文件;
对话拍无此工具(拍分层)。
"""

from pathlib import Path

from neonrp.core.skills import SKILL_SCHEMAS, SkillRegistry, get_skill_schemas


def _registry(tmp_path: Path) -> SkillRegistry:
    return SkillRegistry(
        root=tmp_path,
        run_id="test-run",
        agent_id="world-agent",
        read_globs=["**"],
        deny_globs=[],
    )


def test_roll_check_registered_and_offered() -> None:
    assert "roll_check" in SKILL_SCHEMAS
    offered = {s.get("name") for s in get_skill_schemas()}
    assert "roll_check" in offered


def test_coc_roll_returns_structured_result(tmp_path: Path) -> None:
    r = _registry(tmp_path).invoke("roll_check", {"skill": "医术", "target": 65})
    assert r.success is True
    d = r.data
    assert d["ruleset"] == "brp" and d["skill"] == "医术" and d["target"] == 65
    assert 1 <= d["roll"] <= 100
    assert isinstance(d["passed"], bool) and isinstance(d["margin"], int)
    assert d["outcome"] and isinstance(d["line"], str) and "医术" in d["line"]


def test_5e_roll_with_modifier(tmp_path: Path) -> None:
    r = _registry(tmp_path).invoke(
        "roll_check",
        {"skill": "Stealth", "target": 15, "ruleset": "5e", "modifier": 3},
    )
    assert r.success is True
    assert r.data["ruleset"] == "srd", "the old id 5e reads as srd"
    # 5e:roll 字段 = natural(1..20);modifier 体现在格式化行与判定里。
    assert 1 <= r.data["roll"] <= 20
    assert "+3" in r.data["line"]  # 5e 行含加值分解(natural+mod=total)


def test_invalid_args_fail_cleanly(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    assert reg.invoke("roll_check", {"target": 50}).success is False  # 缺名目
    assert reg.invoke("roll_check", {"skill": "斗殴"}).success is False  # 缺 target
    assert reg.invoke("roll_check", {"skill": "斗殴", "target": -5}).success is False
    assert reg.invoke("roll_check", {"skill": "斗殴", "target": "很高"}).success is False


def test_no_file_mutation(tmp_path: Path) -> None:
    # 纯计算契约:掷骰前后 run 目录无任何文件变化。
    before = sorted(p.name for p in tmp_path.rglob("*"))
    _registry(tmp_path).invoke("roll_check", {"skill": "侦查", "target": 40})
    after = sorted(p.name for p in tmp_path.rglob("*"))
    assert before == after


def test_dialogue_lane_has_no_dice() -> None:
    # 拍分层(M24 §3 / M27 §2.4):对话拍 = 纯 LLM 调用,无工具——
    # light_chat 的调用路径断言 tools is None(test_light_chat 全套已覆盖);
    # 这里守住注册表侧:roll_check 不在酒馆导入用的白名单口(布防样例)。
    from neonrp.core import light_chat

    assert not hasattr(light_chat, "roll_check")
