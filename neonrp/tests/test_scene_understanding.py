"""Tests for the M18 §3 deterministic scene-understanding routing step.

Spec: docs/M18_DESIGN.md §3 (file-as-router), §3.3 (locality rule).
"""

import json
import shutil
from pathlib import Path

import pytest

from neonrp.core.message_bus import InProcessBus
from neonrp.core.player_controller import (
    ScenePacket,
    build_player_turn_intent,
    build_scene_packet,
)
from neonrp.core.playthrough import (
    SCHEMA_VERSION,
    Playthrough,
    SoulRef,
    WorldAgentTeam,
    WorldRef,
    read_playthrough,
    write_playthrough,
)
from neonrp.core.scene_understanding import broadcast, understand_scene
from neonrp.core.skills import SKILL_SCHEMAS, get_skill_schemas


def _playthrough(*souls: tuple[str, str], active: tuple[str, ...] | None = None) -> Playthrough:
    refs = [
        SoulRef(sid=sid, instance_id=iid, version_hash="v", head_commit="c", role="npc")
        for sid, iid in souls
    ]
    return Playthrough(
        schema_version=SCHEMA_VERSION,
        playthrough_id="pt-test",
        world=WorldRef(wid="w", instance_id="wi", version_hash="vh", head_commit="hc"),
        world_agent_team=WorldAgentTeam(seeded_from="x", agents=[]),
        souls=refs,
        created_at="2026-06-06T00:00:00Z",
        active_souls=tuple(iid for _, iid in souls) if active is None else active,
    )


def _write_soul(root: Path, sid: str, iid: str, node: str | None) -> None:
    d = root / "souls" / f"{sid}-{iid}"
    d.mkdir(parents=True, exist_ok=True)
    state: dict = {"sid": sid, "instance_id": iid}
    if node is not None:
        state["location"] = node
    (d / "run_state.json").write_text(json.dumps(state), encoding="utf-8")


def _scene(node: str | None) -> ScenePacket:
    location = {"node": node} if node else {}
    return ScenePacket(scene_label="L", location=location)


def test_co_located_soul_is_active(tmp_path: Path) -> None:
    # rowan is NOT in play (not prior-active) and elsewhere → inactive.
    pt = _playthrough(("elena", "si-e1"), ("rowan", "si-r1"), active=("si-e1",))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "elena", "si-e1", "north-gate")
    _write_soul(tmp_path, "rowan", "si-r1", "T004")

    u = understand_scene(tmp_path, pt, _scene("north-gate"))

    assert u.active_iids == ("si-e1",)
    assert u.fallback_used is False
    assert "co-located" in u.reasons["si-e1"]
    assert "elsewhere" in u.reasons["si-r1"]


def test_away_roster_lists_offsite_souls(tmp_path: Path) -> None:
    # 物理在场硬事实(far-away soul 修复):异地 soul 进 away_roster、同处的不进。
    # world-agent preflight 会把这份名册硬注入 prompt,防玩家 cue 拉回远方 soul。
    pt = _playthrough(("elena", "si-e1"), ("rowan", "si-r1"), active=("si-e1", "si-r1"))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "elena", "si-e1", "north-gate")
    _write_soul(tmp_path, "rowan", "si-r1", "T004")

    u = understand_scene(tmp_path, pt, _scene("north-gate"))

    away_iids = {iid for iid, _node in u.away_roster}
    assert "si-r1" in away_iids  # 异地 → 进名册(world-agent 会知道它不在场)
    assert "si-e1" not in away_iids  # 与玩家同处 → 不进名册


def test_soul_elsewhere_and_not_in_play_is_inactive(tmp_path: Path) -> None:
    pt = _playthrough(("shiro", "si-s1"), ("hane", "si-h1"), active=("si-h1",))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "shiro", "si-s1", "islet-dock")
    _write_soul(tmp_path, "hane", "si-h1", "south-shore")

    u = understand_scene(tmp_path, pt, _scene("south-shore"))

    assert u.active_iids == ("si-h1",)
    assert "si-s1" not in u.active_iids


def test_writes_active_souls_and_integrations_to_manifest(tmp_path: Path) -> None:
    pt = _playthrough(("elena", "si-e1"), ("rowan", "si-r1"), active=("si-e1",))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "elena", "si-e1", "north-gate")
    _write_soul(tmp_path, "rowan", "si-r1", "T004")

    understand_scene(tmp_path, pt, _scene("north-gate"))

    reread = read_playthrough(tmp_path)
    assert reread is not None
    assert reread.active_souls == ("si-e1",)
    assert reread.integrations[0]["world_agent"] == "world-agent"
    assert reread.integrations[0]["souls"] == ["si-e1"]


def test_away_live_soul_forms_location_group(tmp_path: Path) -> None:
    # M22: a soul IN PLAY that walked away stays live in its own location
    # group (destined for that location's world-agent), not the player scene.
    pt = _playthrough(("a", "si-a1"), ("b", "si-b1"), active=("si-a1", "si-b1"))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "a", "si-a1", "far-1")
    _write_soul(tmp_path, "b", "si-b1", "far-2")

    u = understand_scene(tmp_path, pt, _scene("player-node"))

    assert u.fallback_used is True
    assert u.active_iids == ("si-a1", "si-b1")
    assert "location group 'far-1'" in u.reasons["si-a1"]
    agents = [e["world_agent"] for e in u.integrations]
    assert agents == ["world-agent", "loc:far-1", "loc:far-2"]
    reread = read_playthrough(tmp_path)
    assert reread is not None and len(reread.integrations) == 3


def test_location_group_cap_deactivates_overflow(tmp_path: Path) -> None:
    pt = _playthrough(
        ("a", "si-a1"), ("b", "si-b1"), ("c", "si-c1"),
        active=("si-a1", "si-b1", "si-c1"),
    )
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "a", "si-a1", "loc-1")
    _write_soul(tmp_path, "b", "si-b1", "loc-2")
    _write_soul(tmp_path, "c", "si-c1", "loc-3")

    u = understand_scene(tmp_path, pt, _scene("player-node"))

    # cap = 2 groups; the third live-away soul goes off-stage this turn.
    assert u.active_iids == ("si-a1", "si-b1")
    assert "beyond location-group cap" in u.reasons["si-c1"]


def test_missing_location_stays_with_player(tmp_path: Path) -> None:
    pt = _playthrough(("a", "si-a1"), active=("si-a1",))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "a", "si-a1", None)  # no location key

    u = understand_scene(tmp_path, pt, _scene("anywhere"))

    assert u.active_iids == ("si-a1",)
    assert "no location" in u.reasons["si-a1"]
    assert u.integrations[0]["souls"] == ["si-a1"]  # primary group


def test_perspective_packets(tmp_path: Path) -> None:
    # M22 双视角: an away soul's packet is ITS location's scene with no
    # player-onboarding fields; a primary soul keeps the shared scene label
    # but is also stripped of player-perspective info.
    pt = _playthrough(("e", "si-e1"), ("a", "si-a1"), active=("si-e1", "si-a1"))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "e", "si-e1", "north-gate")
    _write_soul(tmp_path, "a", "si-a1", "riverlamp-inn")

    base = ScenePacket(
        scene_label="石津镇·北门 · 第1日·08:30",
        location={"node": "north-gate"},
        time={"day": 1, "clock": "08:30"},
        player_summary="艾文 / 剑士",
        startup_opening="开场白",
        startup_choices=["自由行动"],
    )
    u = understand_scene(tmp_path, pt, base)

    primary_pkt = u.per_soul_packets["si-e1"]
    assert primary_pkt.scene_label == base.scene_label
    assert primary_pkt.player_summary == ""        # 主角视角不进 soul feed
    assert primary_pkt.startup_opening == ""

    away_pkt = u.per_soul_packets["si-a1"]
    assert "riverlamp-inn" in away_pkt.scene_label  # 她自己的场景
    assert away_pkt.location == {"node": "riverlamp-inn"}
    assert away_pkt.player_summary == ""
    assert away_pkt.last_narration == ""            # 无该地点叙事 ⇒ 显式为空


def test_broadcast_publishes_one_request_per_active_soul(tmp_path: Path) -> None:
    pt = _playthrough(("elena", "si-e1"), ("rowan", "si-r1"), active=("si-e1",))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "elena", "si-e1", "north-gate")
    _write_soul(tmp_path, "rowan", "si-r1", "T004")
    u = understand_scene(tmp_path, pt, _scene("north-gate"))

    bus = InProcessBus()
    seen: list[str] = []
    bus.subscribe("soul/+/request", lambda m: seen.append(m.topic))

    broadcast(bus, u)

    assert seen == ["soul/si-e1/request"]


# --- Regression: deterministic routing on the SHIPPED templates (no LLM) ---

_TEMPLATES = Path("src/neonrp/templates")


def _install_template(tmp_path: Path, name: str) -> Path:
    """Copy a shipped template into the playable layout (.neonrp/playthrough.json)."""
    root = tmp_path / name
    shutil.copytree(_TEMPLATES / name, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


@pytest.mark.parametrize(
    ("template", "expected_active"),
    [
        # player at north-gate with elena; rowan is prior-active at T004 →
        # like makoto below, she stays live in her own location group rather
        # than being dropped for being off-scene.
        ("stoneford-elena", {"si-elena0001", "si-rowan0001"}),
        # hane+yuto at south-shore with the player; makoto is prior-active at
        # school per the template roster → she stays live in her own location
        # group (M22) rather than being dropped.
        ("kagura-island", {"si-hane0001", "si-yuto0001", "si-makoto001"}),
    ],
)
def test_real_template_locality(tmp_path: Path, template: str, expected_active: set) -> None:
    root = _install_template(tmp_path, template)
    pt = read_playthrough(root)
    assert pt is not None
    intent = build_player_turn_intent(root, "开始")
    sp = build_scene_packet(root, intent)

    u = understand_scene(root, pt, sp)

    assert set(u.active_iids) == expected_active
    # The decision is persisted to playthrough.json (file-as-router).
    reread = read_playthrough(root)
    assert reread is not None and set(reread.active_souls) == expected_active


def test_set_active_souls_skill_is_retired() -> None:
    # M18 §3.3: the world-agent no longer routes — the LLM routing tool is gone.
    assert "set_active_souls" not in SKILL_SCHEMAS
    offered = {s.get("name") for s in get_skill_schemas()}
    assert "set_active_souls" not in offered


def test_broadcast_dual_writes_perception_inbox(tmp_path: Path) -> None:
    # T2c(M24 双写过渡):broadcast 给了 root 时,感知包同时投进 soul 收件箱
    # (kind=perception),包体与内存包一致 —— 消费侧优先 drain 此包。
    from dataclasses import asdict

    from neonrp.core.inbox import peek
    from neonrp.core.player_controller import ScenePacket as SP

    pt = _playthrough(("elena", "si-e1"), active=("si-e1",))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "elena", "si-e1", "north-gate")
    u = understand_scene(tmp_path, pt, _scene("north-gate"))

    bus = InProcessBus()
    broadcast(bus, u, root=tmp_path)

    msgs = peek(tmp_path, "si-e1", kind="perception")
    assert len(msgs) == 1
    pk = msgs[0].payload["packet"]
    assert pk["scene_label"] == u.per_soul_packets["si-e1"].scene_label
    # 往返:收件箱包体能无损重建 ScenePacket(消费侧契约)。
    rebuilt = SP(**pk)
    assert asdict(rebuilt) == asdict(u.per_soul_packets["si-e1"])


def test_broadcast_without_root_stays_bus_only(tmp_path: Path) -> None:
    # 不给 root(旧调用形态)⇒ 纯 bus,不碰文件系统 —— 向后兼容。
    pt = _playthrough(("elena", "si-e1"), active=("si-e1",))
    write_playthrough(tmp_path, pt)
    _write_soul(tmp_path, "elena", "si-e1", "north-gate")
    u = understand_scene(tmp_path, pt, _scene("north-gate"))
    broadcast(InProcessBus(), u)
    assert not (tmp_path / ".neonrp" / "inboxes").exists()
