"""Tests for packaged template assets."""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.template_assets import (
    copy_game_support_files_from_template,
    copy_souls_and_playthrough_from_template,
    list_available_templates,
)
from neonrp.worlds import get_world


def test_stone_ford_world_uses_stoneford_orch_template() -> None:
    world = get_world("stone-ford")

    assert world["template"] == "stoneford-orch"


def test_stoneford_elena_world_uses_stoneford_elena_template() -> None:
    world = get_world("stoneford-elena")

    assert world["template"] == "stoneford-elena"


def test_stoneford_orch_template_is_packaged() -> None:
    templates = list_available_templates()

    assert "stoneford-orch" in templates


def test_stoneford_elena_template_is_packaged() -> None:
    templates = list_available_templates()

    assert "stoneford-elena" in templates


def test_copy_game_support_files_from_stoneford_orch(tmp_path: Path) -> None:
    copied = copy_game_support_files_from_template(
        tmp_path,
        template_name="stoneford-orch",
        data_dir_name="game",
        force=True,
    )

    assert "game/lore/story.md" in copied
    assert "game/rules/combat_rules.md" in copied
    assert (tmp_path / "game" / "lore" / "story.md").exists()
    assert (tmp_path / "game" / "rules" / "combat_rules.md").exists()


def test_copy_souls_and_playthrough_m20_no_player_projection(tmp_path: Path) -> None:
    # M20: stoneford-elena has no role=player soul, so the dead M16-E
    # player_projection.json is NOT scaffolded; playthrough carries players[]
    # and elena/rowan are independent NPC souls.
    copied = copy_souls_and_playthrough_from_template(
        tmp_path,
        template_name="stoneford-elena",
        force=True,
    )

    assert "souls/" in copied
    assert ".neonrp/playthrough.json" in copied
    assert ".neonrp/player_projection.json" not in copied
    assert not (tmp_path / ".neonrp" / "player_projection.json").exists()
    assert (tmp_path / "souls" / "elena-si-elena0001" / "soul.md").exists()
    # World art travels too: the template's root assets/ (cover art) + each
    # soul's assets/ (portraits) reach the game so the web /image can serve
    # them. Cards ship their image in assets/ by convention.
    assert "assets/" in copied
    assert (tmp_path / "assets").is_dir()
    assert (tmp_path / "souls" / "elena-si-elena0001" / "assets").is_dir()

    pt = json.loads(
        (tmp_path / ".neonrp" / "playthrough.json").read_text(encoding="utf-8")
    )
    assert [s["role"] for s in pt["souls"]] == ["npc", "npc"]
    assert pt["players"][0]["pid"] == "player"
    assert pt["players"][0]["state_path"] == "game/player"


def test_no_template_has_pre_m20_player_soul_binding() -> None:
    """M20 invariant: no template's game/meta/run_state.json may bind the
    player to a soul (the pre-M20 ``party.player.soul = souls/<sid>...``
    pattern). The human player is a non-soul entity (game/player/); a soul
    is never the player's avatar. Catches re-introduction of the leak that
    made the world-agent say "you are Elena"."""
    templates_root = Path("src/neonrp/templates")
    for run_state in templates_root.glob("*/game/meta/run_state.json"):
        data = json.loads(run_state.read_text(encoding="utf-8"))
        party = data.get("party") or {}
        player_entry = party.get("player") if isinstance(party, dict) else None
        if not isinstance(player_entry, dict):
            continue
        soul_binding = player_entry.get("soul")
        assert not (isinstance(soul_binding, str) and soul_binding.startswith("souls/")), (
            f"{run_state}: party.player.soul still points at a soul "
            f"({soul_binding!r}) — that's the pre-M20 'player IS a soul' "
            f"binding. Drop the soul field; player belongs at game/player/."
        )


def test_stoneford_elena_party_carries_h1_soul_coordination() -> None:
    """M20 Phase H1 seed data: stoneford-elena's party block carries an
    in-scene soul coordination entry (elena) with the fields the locality
    gate needs (state_file, location, available_for_interaction). This is
    the on-disk foundation H2 will read."""
    data = json.loads(
        Path("src/neonrp/templates/stoneford-elena/game/meta/run_state.json").read_text(
            encoding="utf-8"
        )
    )
    souls = (data.get("party") or {}).get("souls") or {}
    elena = souls.get("elena")
    assert isinstance(elena, dict), "party.souls.elena coordination entry missing"
    assert elena.get("state_file") == "souls/elena-si-elena0001/run_state.json"
    assert elena.get("location") == "north-gate"  # same vocab as world location.node
    assert isinstance(elena.get("available_for_interaction"), bool)
