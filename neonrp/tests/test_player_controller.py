from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.player_controller import (
    ScenePacket,
    build_player_turn_intent,
    build_scene_packet,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_start_input_does_not_authorize_avatar_autopilot(tmp_path: Path) -> None:
    root = tmp_path
    _write_json(
        root / "game" / "player" / "controller.json",
        {
            "schema_version": 1,
            "language_hint": "zh",
            "policy": {"autopilot_player_avatar": False},
        },
    )

    intent = build_player_turn_intent(root, "开始游戏")

    assert intent.kind == "start_or_continue"
    assert intent.declared_action == ""
    assert intent.avatar_action_authorized is False
    assert "avatar_action_authorized: false" in intent.to_prompt_block()


def test_declared_action_authorizes_only_that_raw_action(tmp_path: Path) -> None:
    intent = build_player_turn_intent(tmp_path, "和守门人说话")

    assert intent.kind == "declared_action"
    assert intent.declared_action == "和守门人说话"
    assert intent.avatar_action_authorized is True


def test_scene_packet_includes_startup_only_for_first_start_turn(tmp_path: Path) -> None:
    root = tmp_path
    _write_json(
        root / "game" / "meta" / "run_state.json",
        {
            "location": {"display": "石津镇·北门", "node": "north-gate"},
            "time": {"day": 1, "clock": "08:30"},
            "turn_count": 0,
        },
    )
    _write_json(
        root / "game" / "meta" / "game-start.json",
        {
            "startup": {
                "opening_scene": "雾压在北门上。",
                "opening_choices": ["自由行动", "和守门人说话"],
            }
        },
    )
    _write_json(
        root / "game" / "player" / "profile.json",
        {"name_local": "艾莲娜", "class": "剑士", "summary": "失忆的冒险者"},
    )
    intent = build_player_turn_intent(root, "start")

    packet = build_scene_packet(root, intent)

    assert packet.scene_label == "石津镇·北门 · 第1日·08:30"
    assert packet.startup_opening == "雾压在北门上。"
    assert packet.startup_choices == ["自由行动", "和守门人说话"]
    assert "艾莲娜 / 剑士 / 失忆的冒险者" in packet.player_summary
    assert "WorldPreflight / ScenePacket" in packet.to_prompt_block()


def test_scene_packet_last_narration_empty_when_no_trace(tmp_path: Path) -> None:
    """A fresh project with no prior turns → last_narration is empty."""
    packet = ScenePacket(scene_label="test")
    assert packet.last_narration == ""
    assert "上一回合" not in packet.to_prompt_block()


def test_scene_packet_last_narration_appears_in_prompt(tmp_path: Path) -> None:
    """When set, prior narration is visible in the soul's perception block."""
    packet = ScenePacket(
        scene_label="test",
        last_narration="雾还没散。艾莲娜说她叫艾莲娜。",
    )
    assert "上一回合的世界叙事" in packet.to_prompt_block()
    assert "雾还没散" in packet.to_prompt_block()


def test_strip_choice_block_removes_trailing_options() -> None:
    from neonrp.core.player_controller import strip_choice_block

    narration = (
        "雾散了些。她在等你。\n\n你可以：\n"
        "- 自由行动\n- 和守门人交谈\n"
    )
    out = strip_choice_block(narration)
    assert "你可以" not in out
    assert "自由行动" not in out
    assert out.strip() == "雾散了些。她在等你。"


def test_strip_choice_block_leaves_ordinary_prose() -> None:
    from neonrp.core.player_controller import strip_choice_block

    # "你可以" mid-sentence with no bullet list → untouched
    text = "她说你可以信任她，然后转身走了。"
    assert strip_choice_block(text) == text
