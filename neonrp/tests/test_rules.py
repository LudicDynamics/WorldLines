"""Tests for rules engine and resolve_action skill (M7-T6)."""

import json
from pathlib import Path

from neonrp.core.rules import (
    RuleViolation,
    resolve_action,
    validate_game_rules,
)
from neonrp.core.skills import SkillRegistry


def _write_entity(root: Path, kind: str, entity_id: str, data: dict) -> Path:
    """Helper to write an entity file."""
    entity_dir = root / "game" / kind
    entity_dir.mkdir(parents=True, exist_ok=True)
    entity_path = entity_dir / f"{entity_id}.json"
    entity_path.write_text(json.dumps(data), encoding="utf-8")
    return entity_path


class TestValidateGameRules:
    """Test validate_game_rules function."""

    def test_valid_character_no_violations(self, tmp_path: Path):
        """Character with valid hp and gold has no violations."""
        staged = tmp_path / "staged"
        staged.mkdir()

        _write_entity(
            staged,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "hp": 100,
                "max_hp": 100,
                "gold": 50,
            },
        )

        violations = validate_game_rules(staged)
        assert len(violations) == 0

    def test_negative_hp_violation(self, tmp_path: Path):
        """Character with negative hp produces violation."""
        staged = tmp_path / "staged"
        staged.mkdir()

        _write_entity(
            staged,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "hp": -10,
                "max_hp": 100,
            },
        )

        violations = validate_game_rules(staged)
        assert len(violations) == 1
        assert violations[0].rule == "hp_non_negative"
        assert violations[0].value == -10

    def test_negative_gold_violation(self, tmp_path: Path):
        """Character with negative gold produces violation."""
        staged = tmp_path / "staged"
        staged.mkdir()

        _write_entity(
            staged,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "hp": 100,
                "gold": -50,
            },
        )

        violations = validate_game_rules(staged)
        assert len(violations) == 1
        assert violations[0].rule == "gold_non_negative"

    def test_invalid_inventory_not_array_violation(self, tmp_path: Path):
        """Character with non-array inventory produces violation."""
        staged = tmp_path / "staged"
        staged.mkdir()

        _write_entity(
            staged,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "hp": 100,
                "inventory": "not an array",
            },
        )

        violations = validate_game_rules(staged)
        assert len(violations) == 1
        assert violations[0].rule == "inventory_valid"

    def test_invalid_inventory_item_violation(self, tmp_path: Path):
        """Inventory item without id or name produces violation."""
        staged = tmp_path / "staged"
        staged.mkdir()

        _write_entity(
            staged,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "hp": 100,
                "inventory": [{"quantity": 1}],  # Missing id and name
            },
        )

        violations = validate_game_rules(staged)
        assert len(violations) == 1
        assert violations[0].rule == "inventory_item_valid"

    def test_multiple_violations(self, tmp_path: Path):
        """Multiple rule violations are all reported."""
        staged = tmp_path / "staged"
        staged.mkdir()

        _write_entity(
            staged,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "hp": -10,
                "gold": -50,
            },
        )

        violations = validate_game_rules(staged)
        assert len(violations) == 2
        rules = {v.rule for v in violations}
        assert "hp_non_negative" in rules
        assert "gold_non_negative" in rules

    def test_location_entities_not_validated_as_characters(self, tmp_path: Path):
        """Location entities are not checked for character rules."""
        staged = tmp_path / "staged"
        staged.mkdir()

        _write_entity(
            staged,
            "town",
            "town",
            {
                "id": "town",
                "kind": "town",
                "name": "Town",
                "connections": [],
            },
        )

        violations = validate_game_rules(staged)
        assert len(violations) == 0


class TestResolveAction:
    """Test resolve_action function."""

    def test_damage_action_computes_new_hp(self, tmp_path: Path):
        """Damage action correctly computes new hp."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "hp": 100, "max_hp": 100},
        )
        _write_entity(
            tmp_path,
            "npc",
            "goblin",
            {"id": "goblin", "kind": "npc", "name": "Goblin", "hp": 30, "max_hp": 30},
        )

        result = resolve_action(tmp_path, "damage", actor="player", target="goblin", amount=15)

        assert result.success
        assert result.action == "damage"
        assert result.computed_values["old_hp"] == 30
        assert result.computed_values["new_hp"] == 15
        assert result.computed_values["damage_dealt"] == 15

    def test_damage_action_respects_zero_floor(self, tmp_path: Path):
        """Damage cannot reduce hp below 0."""
        _write_entity(
            tmp_path,
            "npc",
            "goblin",
            {"id": "goblin", "kind": "npc", "name": "Goblin", "hp": 10, "max_hp": 30},
        )
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player"},
        )

        result = resolve_action(tmp_path, "damage", actor="player", target="goblin", amount=50)

        assert result.success
        assert result.computed_values["new_hp"] == 0
        assert result.computed_values["is_defeated"] is True

    def test_heal_action_computes_new_hp(self, tmp_path: Path):
        """Heal action correctly computes new hp."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "hp": 50, "max_hp": 100},
        )

        result = resolve_action(tmp_path, "heal", actor="player", amount=30)

        assert result.success
        assert result.computed_values["old_hp"] == 50
        assert result.computed_values["new_hp"] == 80
        assert result.computed_values["actual_heal"] == 30

    def test_heal_action_respects_max_hp_cap(self, tmp_path: Path):
        """Heal cannot exceed max_hp."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "hp": 90, "max_hp": 100},
        )

        result = resolve_action(tmp_path, "heal", actor="player", amount=50)

        assert result.success
        assert result.computed_values["new_hp"] == 100
        assert result.computed_values["actual_heal"] == 10

    def test_buy_action_insufficient_gold(self, tmp_path: Path):
        """Buy action fails with insufficient gold."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "gold": 10},
        )
        _write_entity(
            tmp_path,
            "town",
            "shop",
            {
                "id": "shop",
                "kind": "town",
                "name": "Shop",
                "items_available": [{"id": "sword", "name": "Sword", "price": 100}],
            },
        )

        result = resolve_action(tmp_path, "buy", actor="player", item="sword", target="shop")

        assert not result.success
        assert result.error == "insufficient_gold"
        assert result.computed_values["shortfall"] == 90

    def test_buy_action_success(self, tmp_path: Path):
        """Buy action succeeds with sufficient gold."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "gold": 150},
        )
        _write_entity(
            tmp_path,
            "town",
            "shop",
            {
                "id": "shop",
                "kind": "town",
                "name": "Shop",
                "items_available": [{"id": "sword", "name": "Sword", "price": 100}],
            },
        )

        result = resolve_action(tmp_path, "buy", actor="player", item="sword", target="shop")

        assert result.success
        assert result.computed_values["old_gold"] == 150
        assert result.computed_values["new_gold"] == 50
        assert result.computed_values["total_cost"] == 100

    def test_sell_action_success(self, tmp_path: Path):
        """Sell action computes gold gain correctly."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "gold": 50,
                "inventory": [{"id": "sword", "name": "Sword", "quantity": 1, "value": 100}],
            },
        )

        result = resolve_action(tmp_path, "sell", actor="player", item="sword")

        assert result.success
        assert result.computed_values["old_gold"] == 50
        assert result.computed_values["new_gold"] == 100  # 50 + (100/2)
        assert result.computed_values["price_per_unit"] == 50  # Half of value

    def test_sell_action_item_not_in_inventory(self, tmp_path: Path):
        """Sell action fails if item not in inventory."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "gold": 50,
                "inventory": [],
            },
        )

        result = resolve_action(tmp_path, "sell", actor="player", item="sword")

        assert not result.success
        assert result.error == "item_not_in_inventory"

    def test_move_action_success(self, tmp_path: Path):
        """Move action succeeds to valid destination."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "location": "town"},
        )
        _write_entity(
            tmp_path,
            "town",
            "town",
            {"id": "town", "kind": "town", "name": "Town", "connections": ["forest"]},
        )
        _write_entity(
            tmp_path,
            "location",
            "forest",
            {"id": "forest", "kind": "location", "name": "Forest"},
        )

        result = resolve_action(tmp_path, "move", actor="player", destination="forest")

        assert result.success
        assert result.computed_values["old_location"] == "town"
        assert result.computed_values["new_location"] == "forest"

    def test_move_action_destination_not_found(self, tmp_path: Path):
        """Move action fails if destination doesn't exist."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "location": "town"},
        )

        result = resolve_action(tmp_path, "move", actor="player", destination="nowhere")

        assert not result.success
        assert result.error == "destination_not_found"

    def test_move_action_not_connected(self, tmp_path: Path):
        """Move action fails if destination not connected."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "location": "town"},
        )
        _write_entity(
            tmp_path,
            "town",
            "town",
            {"id": "town", "kind": "town", "name": "Town", "connections": ["forest"]},
        )
        _write_entity(
            tmp_path,
            "location",
            "castle",
            {"id": "castle", "kind": "location", "name": "Castle"},
        )

        result = resolve_action(tmp_path, "move", actor="player", destination="castle")

        assert not result.success
        assert result.error == "not_connected"

    def test_move_action_same_location_is_noop_success(self, tmp_path: Path):
        """Move action to current location should succeed as no-op."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "location": "forest"},
        )
        _write_entity(
            tmp_path,
            "location",
            "forest",
            {"id": "forest", "kind": "location", "name": "Forest", "connections": ["town"]},
        )

        result = resolve_action(tmp_path, "move", actor="player", destination="forest")

        assert result.success
        assert result.computed_values["old_location"] == "forest"
        assert result.computed_values["new_location"] == "forest"
        assert result.computed_values["no_op"] is True

    def test_unknown_action(self, tmp_path: Path):
        """Unknown action returns error."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player"},
        )

        result = resolve_action(tmp_path, "teleport", actor="player")

        assert not result.success
        assert result.error == "unknown_action"


class TestSkillRegistryResolveAction:
    """Test resolve_action skill via SkillRegistry."""

    def test_skill_invoke_resolve_action(self, tmp_path: Path):
        """SkillRegistry.invoke resolves action correctly."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {"id": "player", "kind": "player", "name": "Player", "hp": 50, "max_hp": 100},
        )

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test_agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("resolve_action", {"action": "heal", "actor": "player", "amount": 30})

        assert result.success
        assert result.data["action"] == "heal"
        assert result.data["computed_values"]["new_hp"] == 80

    def test_skill_missing_required_args(self, tmp_path: Path):
        """Skill returns error if required args missing."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test_agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("resolve_action", {"action": "damage"})  # Missing actor

        assert not result.success
        assert "required" in result.error.lower()


class TestRuleViolationSerialization:
    """Test RuleViolation to_dict method."""

    def test_to_dict(self):
        """RuleViolation converts to dict correctly."""
        violation = RuleViolation(
            entity_path="game/player/player.json",
            field="hp",
            rule="hp_non_negative",
            message="HP cannot be negative: -10",
            value=-10,
        )

        d = violation.to_dict()

        assert d["entity_path"] == "game/player/player.json"
        assert d["field"] == "hp"
        assert d["rule"] == "hp_non_negative"
        assert d["message"] == "HP cannot be negative: -10"
        assert d["value"] == -10


class TestM16EntitySynthesis:
    """resolve_action must find M16-shaped actors: the player part-file
    folder and souls outside game/ (live failure: actor_not_found on buy)."""

    def _m16_player(self, root: Path) -> None:
        pdir = root / "game" / "player"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "profile.json").write_text(
            json.dumps({"name": "艾文", "class": "剑士"}), encoding="utf-8"
        )
        (pdir / "wallet.json").write_text(
            json.dumps({"gold": 12, "silver": 3}), encoding="utf-8"
        )
        (pdir / "stats.json").write_text(
            json.dumps({"level": 1, "hp": 20}), encoding="utf-8"
        )

    def test_player_synthesized_from_part_files(self, tmp_path: Path) -> None:
        from neonrp.core.rules import _find_entity

        self._m16_player(tmp_path)
        entity = _find_entity(tmp_path / "game", "player")
        assert entity is not None
        assert entity["id"] == "player"
        assert entity["gold"] == 12      # wallet.json merged top-level
        assert entity["hp"] == 20        # stats.json merged top-level

    def test_soul_synthesized_by_sid(self, tmp_path: Path) -> None:
        from neonrp.core.rules import _find_entity

        sdir = tmp_path / "souls" / "elena-si-e1"
        sdir.mkdir(parents=True)
        (sdir / "soul.json").write_text(
            json.dumps({"sid": "elena", "name": "艾莲娜"}), encoding="utf-8"
        )
        (sdir / "run_state.json").write_text(
            json.dumps(
                {"location": "inn", "status": {"hp": 24, "mood": "alert"}}
            ),
            encoding="utf-8",
        )
        (tmp_path / "game").mkdir()
        entity = _find_entity(tmp_path / "game", "elena")
        assert entity is not None
        assert entity["hp"] == 24        # status flattened
        assert entity["location"] == "inn"

    def test_resolve_buy_works_for_m16_player(self, tmp_path: Path) -> None:
        from neonrp.core.rules import resolve_action

        self._m16_player(tmp_path)
        result = resolve_action(
            tmp_path,
            action="buy",
            actor="player",
            item="torch",
            amount=1,
            profile={
                "resolve_action": {"enabled_actions": ["buy"], "fields": {}}
            },
        )
        # No shop given → price unknown is fine; the point is the actor
        # RESOLVES (no actor_not_found).
        assert result.error != "actor_not_found"
