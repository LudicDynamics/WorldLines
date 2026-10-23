"""Surgical town navigation — feed souls the real town_map they live on."""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.place_nav import resolve_move_target, town_node_view


def _town(root: Path, town_id: str, nodes: list[dict]) -> None:
    d = root / "game" / "towns" / town_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "town_map.json").write_text(
        json.dumps({"town_id": town_id, "nodes": nodes}, ensure_ascii=False),
        encoding="utf-8",
    )


def _stoneford(root: Path) -> None:
    _town(
        root,
        "T001",
        [
            {"id": "gate_north", "name": "北门", "links": ["main_street"]},
            {
                "id": "main_street",
                "name": "主街",
                "links": ["guild", "inn", "gate_north"],
            },
            {"id": "guild", "name": "冒险者公会", "links": ["main_street"]},
            {"id": "inn", "name": "河灯旅店", "links": ["main_street"]},
        ],
    )


def test_resolves_node_with_named_exits(tmp_path: Path) -> None:
    _stoneford(tmp_path)
    view = town_node_view(tmp_path, "gate_north")
    assert view["town"] == "T001"
    assert view["name"] == "北门"
    assert view["exits"] == [{"id": "main_street", "name": "主街"}]


def test_main_street_lists_guild(tmp_path: Path) -> None:
    """From main_street the guild is reachable — the path that unsticks elena."""
    _stoneford(tmp_path)
    view = town_node_view(tmp_path, "main_street")
    exit_ids = [e["id"] for e in view["exits"]]
    assert "guild" in exit_ids
    assert {"id": "guild", "name": "冒险者公会"} in view["exits"]


def test_wilderness_node_returns_none(tmp_path: Path) -> None:
    """A node in no town_map (rowan's north-cliff) degrades gracefully."""
    _stoneford(tmp_path)
    assert town_node_view(tmp_path, "north-cliff") is None


def test_legacy_id_aliases_to_canonical(tmp_path: Path) -> None:
    """Legacy 'north-gate' normalizes to canonical 'gate_north' on read."""
    from neonrp.core.place_nav import canonical_node

    _stoneford(tmp_path)
    assert canonical_node("north-gate") == "gate_north"
    view = town_node_view(tmp_path, "north-gate")
    assert view is not None
    assert view["id"] == "gate_north"
    assert view["name"] == "北门"


def test_town_disambiguation_prefers_player_town(tmp_path: Path) -> None:
    """'guild' exists in two towns; prefer_town decides which."""
    _stoneford(tmp_path)
    _town(
        tmp_path,
        "T004",
        [
            {"id": "guild", "name": "冒险者公会（碧石分部）", "links": ["main_street"]},
            {"id": "main_street", "name": "矿工大道", "links": ["guild"]},
        ],
    )
    v1 = town_node_view(tmp_path, "guild", prefer_town="T001")
    v4 = town_node_view(tmp_path, "guild", prefer_town="T004")
    assert v1["name"] == "冒险者公会"
    assert v4["name"] == "冒险者公会（碧石分部）"


def test_empty_and_missing(tmp_path: Path) -> None:
    assert town_node_view(tmp_path, None) is None
    assert town_node_view(tmp_path, "guild") is None  # no towns dir


def _two_towns(root: Path) -> None:
    """石津镇 (T001) and 碧石镇 (T004) — both have guild/main_street (the
    collision that made characters appear to jump between towns)."""
    _stoneford(root)
    _town(
        root,
        "T004",
        [
            {"id": "gate_west", "name": "西门", "links": ["main_street"]},
            {"id": "main_street", "name": "矿工大道", "links": ["guild", "gate_west"]},
            {"id": "guild", "name": "冒险者公会（碧石分部）", "links": ["main_street"]},
        ],
    )


def test_split_location() -> None:
    from neonrp.core.place_nav import split_location

    assert split_location("T004/guild") == ("T004", "guild")
    assert split_location("T004") == ("T004", None)
    assert split_location("guild") == (None, "guild")
    assert split_location("") == (None, None)
    assert split_location(None) == (None, None)
    # node ids canonicalize on split
    assert split_location("north-gate") == (None, "gate_north")
    assert split_location("T001/north-gate") == ("T001", "gate_north")


def test_join_location() -> None:
    from neonrp.core.place_nav import join_location

    assert join_location("T004", "guild") == "T004/guild"
    assert join_location("T004", None) == "T004"
    assert join_location(None, "guild") == "guild"
    assert join_location(None, None) == ""


def test_town_of_node_disambiguates(tmp_path: Path) -> None:
    from neonrp.core.place_nav import town_of_node

    _two_towns(tmp_path)
    # 'guild' is in both — prefer_town wins (default stay-in-town)…
    assert town_of_node(tmp_path, "guild", prefer_town="T004") == "T004"
    assert town_of_node(tmp_path, "guild", prefer_town="T001") == "T001"
    # …else first town that contains it (deterministic, sorted order).
    assert town_of_node(tmp_path, "guild") == "T001"
    # a node unique to one town resolves regardless of prefer_town
    assert town_of_node(tmp_path, "gate_west", prefer_town="T001") == "T004"
    # wilderness / unknown → None
    assert town_of_node(tmp_path, "north-cliff") is None


def test_qualify_location_scopes_bare_ids(tmp_path: Path) -> None:
    from neonrp.core.place_nav import qualify_location

    _two_towns(tmp_path)
    # Bare ambiguous id stays in the agent's CURRENT town (the anti-jump rule).
    assert qualify_location(tmp_path, "guild", current_town="T004") == "T004/guild"
    assert qualify_location(tmp_path, "guild", current_town="T001") == "T001/guild"
    # No context → first match, but still scoped (no more global collapse).
    assert qualify_location(tmp_path, "guild") == "T001/guild"
    # Already-scoped passes through (and canonicalizes the node).
    assert qualify_location(tmp_path, "T004/guild", current_town="T001") == "T004/guild"
    assert qualify_location(tmp_path, "T001/north-gate") == "T001/gate_north"
    # Town-only address is preserved.
    assert qualify_location(tmp_path, "T004", current_town="T001") == "T004"
    # An id only in another town moves there even with a current_town set.
    assert qualify_location(tmp_path, "gate_west", current_town="T001") == "T004/gate_west"
    # Wilderness stays unscoped (no town to attach).
    assert qualify_location(tmp_path, "north-cliff", current_town="T001") == "north-cliff"
    assert qualify_location(tmp_path, "") == ""


def test_soul_packet_injects_exits(tmp_path: Path) -> None:
    """_soul_packet feeds the soul its town_map exits in the perception block."""
    from neonrp.core.player_controller import ScenePacket
    from neonrp.core.scene_understanding import _soul_packet

    _stoneford(tmp_path)
    base = ScenePacket(
        scene_label="石津镇 · 第1日·09:00",
        location={"scope": "town", "node_id": "T001", "node": "inn"},
        time={"day": 1, "clock": "09:00"},
    )
    pkt = _soul_packet(base, node="gate_north", root=tmp_path)
    assert pkt.place_name == "北门"
    assert pkt.exits == [{"id": "main_street", "name": "主街"}]
    block = pkt.to_prompt_block()
    assert "main_street" in block
    assert "moved_to" in block


# --- resolve_move_target: the mover's anti-teleport gate --------------------
# Reuses _two_towns above: T001 has gate_north; T004 has gate_west (no north
# gate); both share 'guild' (the collision that caused the jumping).
def test_move_rejects_hallucinated_cross_town_gate(tmp_path: Path) -> None:
    """The real bug: Rowan in T004 reports 'north-gate' (aliased to T001's
    gate_north). It must NOT teleport him to T001 — the move is rejected."""
    _two_towns(tmp_path)
    assert resolve_move_target(tmp_path, "north-gate", current_location="T004") is None
    assert resolve_move_target(tmp_path, "gate_north", current_location="T004") is None


def test_move_scopes_in_town_node_to_current_town(tmp_path: Path) -> None:
    """A bare node the current town HAS stays in that town, scoped."""
    _two_towns(tmp_path)
    assert resolve_move_target(tmp_path, "guild", current_location="T004") == "T004/guild"
    assert resolve_move_target(tmp_path, "gate_west", current_location="T004") == "T004/gate_west"
    # 'guild' exists in both towns — current town wins (no first-match guess).
    assert resolve_move_target(tmp_path, "guild", current_location="T001") == "T001/guild"


def test_move_allows_explicit_cross_town_address(tmp_path: Path) -> None:
    """Cross-town travel is fine when the target names its town explicitly."""
    _two_towns(tmp_path)
    assert resolve_move_target(tmp_path, "T001/gate_north", current_location="T004") == "T001/gate_north"
    assert resolve_move_target(tmp_path, "T001", current_location="T004") == "T001"


def test_move_wilderness_node_leaves_town_unscoped(tmp_path: Path) -> None:
    """A node in no town_map (wilderness) is allowed, unscoped."""
    _two_towns(tmp_path)
    assert resolve_move_target(tmp_path, "north-cliff", current_location="T004") == "north-cliff"


def test_move_cross_town_allowed_for_authority(tmp_path: Path) -> None:
    """cross_town=True (the authoritative world-agent) scopes a bare node to its
    real town instead of rejecting it — souls keep the default reject."""
    _two_towns(tmp_path)
    # Soul path (default): a bare node only in T001 is rejected from T004.
    assert resolve_move_target(tmp_path, "gate_north", current_location="T004") is None
    # World-agent path: honored, scoped to the town that actually has it.
    assert (
        resolve_move_target(tmp_path, "gate_north", current_location="T004", cross_town=True)
        == "T001/gate_north"
    )
