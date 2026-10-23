"""Created worlds must finalize into runnable, multi-agent NeonRP worlds."""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.created_world import finalize_created_world
from neonrp.core.paths import get_manifest_path
from neonrp.core.playthrough import read_playthrough
from neonrp.core.runtime_contract import get_router_execution_mode


def _bundle(dest: Path, npcs: list[dict]) -> None:
    """An LLM-authored orchestrator bundle: game/ + world-agent + flat NPCs."""
    (dest / "game" / "npc").mkdir(parents=True)
    (dest / "agents" / "world-agent").mkdir(parents=True)
    (dest / "agents" / "world-agent" / "agent.json").write_text(
        '{"id":"world-agent"}', encoding="utf-8"
    )
    for npc in npcs:
        (dest / "game" / "npc" / f"{npc['id']}.json").write_text(
            json.dumps(npc, ensure_ascii=False), encoding="utf-8"
        )


def test_created_world_is_initialized(tmp_path: Path) -> None:
    """The acute bug: a created world reported 'NeonRP project not initialized'."""
    dest = tmp_path / "mystic-vale"
    _bundle(dest, [{"id": "aria", "name": "Aria", "description": "a bard"}])
    rep = finalize_created_world(dest, world_name="Mystic Vale")
    assert rep["initialized"] is True
    # A real manifest with a valid current branch (the engine's init check).
    assert get_manifest_path(dest).is_file()


def test_created_world_is_multiagent_with_souls(tmp_path: Path) -> None:
    dest = tmp_path / "mystic-vale"
    _bundle(dest, [
        {"id": "aria", "name": "Aria", "name_local": "阿莉雅", "description": "a bard"},
        {"id": "kael", "name": "Kael", "description": "a mercenary", "current_goal": "survive"},
    ])
    finalize_created_world(dest, world_name="Mystic Vale")

    assert get_router_execution_mode(dest) == "multi-agent"
    pt = read_playthrough(dest)
    assert pt is not None
    assert len(pt.souls) == 2
    sids = {s.sid for s in pt.souls}
    assert sids == {"aria", "kael"}
    # every soul is registered active and has a valid on-disk folder
    assert set(pt.active_souls) == {s.instance_id for s in pt.souls}
    for s in pt.souls:
        d = dest / "souls" / f"{s.sid}-{s.instance_id}"
        assert (d / "soul.json").is_file()
        assert (d / "soul.md").is_file()
        assert (d / "run_state.json").is_file()
    # the orchestrator is always in the team roster
    assert any(a.id == "world-agent" for a in pt.world_agent_team.agents)


def test_prefers_authored_soul_folders(tmp_path: Path) -> None:
    """If the LLM already authored souls/, use them rather than NPCs."""
    dest = tmp_path / "w"
    (dest / "souls" / "lyra-si-lyra0001").mkdir(parents=True)
    (dest / "souls" / "lyra-si-lyra0001" / "soul.json").write_text(
        json.dumps({"sid": "lyra", "name": "Lyra"}), encoding="utf-8"
    )
    (dest / "souls" / "lyra-si-lyra0001" / "soul.md").write_text("# Lyra", encoding="utf-8")
    _bundle_npc = dest / "game" / "npc"
    _bundle_npc.mkdir(parents=True)
    (_bundle_npc / "ghost.json").write_text('{"id":"ghost","name":"Ghost"}', encoding="utf-8")

    finalize_created_world(dest, world_name="W")
    pt = read_playthrough(dest)
    assert pt is not None
    # authored soul wins; the flat NPC is NOT also converted
    assert [s.sid for s in pt.souls] == ["lyra"]


def test_no_characters_still_initializes(tmp_path: Path) -> None:
    """A world with no NPCs must still init cleanly — but stay a plain
    orchestrator world, not a fabricated empty multi-agent binding."""
    dest = tmp_path / "empty"
    (dest / "game" / "meta").mkdir(parents=True)
    rep = finalize_created_world(dest, world_name="Empty")
    assert rep["initialized"] is True
    assert rep["souls"] == 0
    # no cast → no playthrough written, mode not forced to multi-agent
    assert read_playthrough(dest) is None
    assert get_router_execution_mode(dest) != "multi-agent"


def test_seeds_a_player_profile(tmp_path: Path) -> None:
    """A created world must ship a protagonist, else the world-agent has no
    player to narrate and asks 'who are you?' (the 猫之岛 bug)."""
    dest = tmp_path / "cat-isle"
    _bundle(dest, [{"id": "afu", "name": "Afu"}])
    finalize_created_world(dest, world_name="猫之岛")
    profile = dest / "game" / "player" / "profile.json"
    assert profile.is_file()
    data = json.loads(profile.read_text(encoding="utf-8"))
    assert data.get("name") and data.get("intro_i18n")
    # the playthrough binds a player too
    pt = read_playthrough(dest)
    assert pt is not None and any(p.pid == "player" for p in pt.players)


def test_does_not_clobber_existing_player(tmp_path: Path) -> None:
    dest = tmp_path / "w"
    (dest / "game" / "player").mkdir(parents=True)
    (dest / "game" / "player" / "profile.json").write_text(
        json.dumps({"name": "Authored Hero"}), encoding="utf-8"
    )
    _bundle(dest, [{"id": "afu", "name": "Afu"}])
    finalize_created_world(dest, world_name="W")
    data = json.loads((dest / "game" / "player" / "profile.json").read_text(encoding="utf-8"))
    assert data["name"] == "Authored Hero"  # author's player preserved


def test_finalize_is_idempotent(tmp_path: Path) -> None:
    dest = tmp_path / "w"
    _bundle(dest, [{"id": "aria", "name": "Aria"}])
    r1 = finalize_created_world(dest, world_name="W")
    r2 = finalize_created_world(dest, world_name="W")
    pt = read_playthrough(dest)
    assert pt is not None
    # re-running doesn't duplicate the cast
    assert r1["souls"] == r2["souls"] == 1
    assert len(pt.souls) == 1
