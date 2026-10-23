from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.soul_agent import resolve_soul_agent_data


def test_resolve_soul_agent_data_inlines_soul_charter(tmp_path: Path) -> None:
    root = tmp_path
    soul_dir = root / "souls" / "elena-si-elena0001"
    (soul_dir / "agents").mkdir(parents=True)
    (soul_dir / "persona").mkdir(parents=True)
    (soul_dir / "agents" / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agents": [
                    {"id": "soul-memory", "role": "retention", "write_globs": ["short-term-memo/**"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (soul_dir / "soul.json").write_text(
        json.dumps({"sid": "elena", "name": "Elena", "name_local": "艾莲娜"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (soul_dir / "soul.md").write_text(
        "# Soul Charter — Elena\n\n## Core Presence\n\nShe wakes without her past.\n",
        encoding="utf-8",
    )
    (soul_dir / "persona" / "core_traits.json").write_text(
        json.dumps({"sid": "elena", "traits": {"courage": 0.8}}, ensure_ascii=False),
        encoding="utf-8",
    )

    agent = resolve_soul_agent_data(root, "elena", "si-elena0001")

    assert agent is not None
    prompt = agent["system_prompt"]
    assert "这个世界中的一个独立个体" in prompt
    assert "Soul Charter" in prompt
    assert "She wakes without her past." in prompt
    assert '"courage": 0.8' in prompt
    assert '"confidence"' in prompt
    assert '"urgency"' in prompt
    assert '"inner_voice"' in prompt


def test_player_soul_prompt_preserves_human_player_sovereignty(tmp_path: Path) -> None:
    root = tmp_path
    soul_dir = root / "souls" / "elena-si-elena0001"
    (root / ".neonrp").mkdir()
    (soul_dir / "agents").mkdir(parents=True)
    (soul_dir / "persona").mkdir(parents=True)
    (soul_dir / "agents" / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agents": [
                    {"id": "soul-memory", "role": "retention", "write_globs": ["short-term-memo/**"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (soul_dir / "soul.json").write_text(
        json.dumps({"sid": "elena", "name": "Elena", "name_local": "艾莲娜"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (soul_dir / "soul.md").write_text("# Elena\n", encoding="utf-8")
    (root / ".neonrp" / "playthrough.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "playthrough_id": "pt-1",
                "world": {
                    "wid": "stoneford-elena",
                    "instance_id": "wi-1",
                    "version_hash": "v",
                    "head_commit": "wc-1",
                },
                "world_agent_team": {
                    "seeded_from": "game/agents/manifest.json@v",
                    "agents": [{"id": "world-agent", "role": "orchestrator"}],
                },
                "souls": [
                    {
                        "sid": "elena",
                        "instance_id": "si-elena0001",
                        "version_hash": "v",
                        "head_commit": "sc-1",
                        "role": "player",
                    }
                ],
                "created_at": "2026-05-18T00:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    agent = resolve_soul_agent_data(root, "elena", "si-elena0001")

    assert agent is not None
    prompt = agent["system_prompt"]
    assert "玩家 Avatar，不是自动驾驶" in prompt
    assert "human player 才拥有行动主权" in prompt
    assert 'intended_action` 写 `"await human player choice"`' in prompt


def test_system_md_override_and_brace_safe_render(tmp_path):
    """M30 契约:soul 自己的 agents/soul-agent/system.md 整体覆盖引擎模板;
    渲染是逐 token 替换——override 正文里的 JSON 花括号必须原样保留。"""
    import json

    from neonrp.core.soul_agent import resolve_soul_agent_data

    root = tmp_path
    sd = root / "souls" / "elena-si-a1"
    (sd / "agents" / "soul-agent").mkdir(parents=True)
    (sd / "soul.json").write_text(
        json.dumps({"sid": "elena", "name_local": "艾琳娜"}), encoding="utf-8"
    )
    (sd / "agents" / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "agents": [
            {"id": "soul-agent", "role": "soul", "write_globs": ["short-term-memo/**"]}
        ]}), encoding="utf-8",
    )
    (sd / "agents" / "soul-agent" / "system.md").write_text(
        '你是 {name}(sid={sid})。回包例:{"state": "completed"}\n{role_contract}',
        encoding="utf-8",
    )

    data = resolve_soul_agent_data(root, "elena", "si-a1")
    assert data is not None
    sp = data["system_prompt"]
    assert "你是 艾琳娜(sid=elena)" in sp          # token 替换生效
    assert '{"state": "completed"}' in sp            # JSON 花括号原样保留
    assert "{role_contract}" not in sp                # 已注入
    assert "Soul-Agent —" not in sp                   # 引擎默认模板被整体覆盖


def test_default_template_renders_clean_json_example(tmp_path):
    """默认模板去掉 .format 双花括号转义后,JSON 例必须是单花括号。"""
    import json

    from neonrp.core.soul_agent import resolve_soul_agent_data

    root = tmp_path
    sd = root / "souls" / "rowan-si-b1"
    (sd / "agents").mkdir(parents=True)
    (sd / "soul.json").write_text(json.dumps({"sid": "rowan"}), encoding="utf-8")
    (sd / "agents" / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "agents": [
            {"id": "soul-agent", "role": "soul", "write_globs": []}
        ]}), encoding="utf-8",
    )
    data = resolve_soul_agent_data(root, "rowan", "si-b1")
    assert data is not None
    assert '"state": "completed"' in data["system_prompt"]
    assert "{{" not in data["system_prompt"]  # 转义残留=渲染坏
