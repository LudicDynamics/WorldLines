"""Tests for per-kind entity schema validation (M7-T5)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from neonrp.core.validation import load_schema, validate_game_data


@pytest.fixture
def schema(tmp_path: Path):
    """Load the built-in schema."""
    return load_schema(tmp_path)


def _write_entity(tmp_path: Path, kind: str, entity_id: str, data: dict) -> Path:
    """Helper to write an entity file."""
    entity_dir = tmp_path / "game" / kind
    entity_dir.mkdir(parents=True, exist_ok=True)
    entity_path = entity_dir / f"{entity_id}.json"
    entity_path.write_text(json.dumps(data), encoding="utf-8")
    return entity_path


class TestCharacterSchema:
    """Test character entity validation."""

    def test_character_with_all_fields_validates(self, tmp_path: Path, schema):
        """Character with hp, max_hp, gold, level, location, inventory validates."""
        _write_entity(
            tmp_path,
            "character",
            "hero",
            {
                "id": "hero",
                "kind": "character",
                "name": "Hero",
                "hp": 100,
                "max_hp": 100,
                "gold": 50,
                "level": 1,
                "location": "start-town",
                "inventory": [{"id": "sword", "name": "Sword", "quantity": 1}],
            },
        )
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0
        assert len(entities) == 1

    def test_character_without_optional_fields_validates(self, tmp_path: Path, schema):
        """Character without per-kind fields still validates (backward compat)."""
        _write_entity(
            tmp_path,
            "character",
            "hero",
            {
                "id": "hero",
                "kind": "character",
                "name": "Hero",
            },
        )
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0
        assert len(entities) == 1

    def test_player_entity_validates(self, tmp_path: Path, schema):
        """Player kind is treated as character-like."""
        _write_entity(
            tmp_path,
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
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0

    def test_npc_entity_validates(self, tmp_path: Path, schema):
        """NPC kind is treated as character-like."""
        _write_entity(
            tmp_path,
            "npc",
            "guard",
            {
                "id": "guard",
                "kind": "npc",
                "name": "Town Guard",
                "hp": 50,
                "max_hp": 50,
                "gold": 10,
            },
        )
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0


class TestItemSchema:
    """Test item entity validation."""

    def test_item_with_all_fields_validates(self, tmp_path: Path, schema):
        """Item with value, weight, quantity, effects validates."""
        _write_entity(
            tmp_path,
            "item",
            "sword",
            {
                "id": "sword",
                "kind": "item",
                "name": "Iron Sword",
                "value": 100,
                "weight": 5.0,
                "quantity": 1,
                "effects": [{"type": "damage", "value": 10}],
            },
        )
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0

    def test_item_without_optional_fields_validates(self, tmp_path: Path, schema):
        """Item without per-kind fields still validates (backward compat)."""
        _write_entity(
            tmp_path,
            "item",
            "potion",
            {
                "id": "potion",
                "kind": "item",
                "name": "Health Potion",
            },
        )
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0


class TestLocationSchema:
    """Test location entity validation."""

    def test_location_with_all_fields_validates(self, tmp_path: Path, schema):
        """Location with connections, npcs, items_available validates."""
        _write_entity(
            tmp_path,
            "location",
            "town",
            {
                "id": "town",
                "kind": "location",
                "name": "Town Square",
                "connections": ["forest", "castle"],
                "npcs": ["guard", "merchant"],
                "items_available": [{"id": "potion", "name": "Health Potion", "price": 25}],
            },
        )
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0

    def test_town_kind_validates(self, tmp_path: Path, schema):
        """Town kind is treated as location-like."""
        _write_entity(
            tmp_path,
            "town",
            "start-town",
            {
                "id": "start-town",
                "kind": "town",
                "name": "Starting Town",
                "connections": ["forest-path"],
            },
        )
        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0


class TestSchemaConstraints:
    """Test schema minimum value constraints."""

    def test_hp_minimum_zero_required(self, tmp_path: Path, schema):
        """HP below 0 should fail validation at schema level."""
        validator = Draft7Validator(schema)
        entity = {
            "id": "hero",
            "kind": "character",
            "name": "Hero",
            "hp": -1,  # Invalid: below minimum
        }
        errors = list(validator.iter_errors(entity))
        assert len(errors) > 0
        assert any("minimum" in str(e.message).lower() or "-1" in str(e.message) for e in errors)

    def test_gold_minimum_zero_required(self, tmp_path: Path, schema):
        """Gold below 0 should fail validation at schema level."""
        validator = Draft7Validator(schema)
        entity = {
            "id": "hero",
            "kind": "character",
            "name": "Hero",
            "gold": -100,  # Invalid: below minimum
        }
        errors = list(validator.iter_errors(entity))
        assert len(errors) > 0

    def test_max_hp_minimum_one_required(self, tmp_path: Path, schema):
        """max_hp below 1 should fail validation at schema level."""
        validator = Draft7Validator(schema)
        entity = {
            "id": "hero",
            "kind": "character",
            "name": "Hero",
            "max_hp": 0,  # Invalid: below minimum of 1
        }
        errors = list(validator.iter_errors(entity))
        assert len(errors) > 0

    def test_level_minimum_one_required(self, tmp_path: Path, schema):
        """Level below 1 should fail validation at schema level."""
        validator = Draft7Validator(schema)
        entity = {
            "id": "hero",
            "kind": "character",
            "name": "Hero",
            "level": 0,  # Invalid: below minimum of 1
        }
        errors = list(validator.iter_errors(entity))
        assert len(errors) > 0

    def test_item_value_minimum_zero(self, tmp_path: Path, schema):
        """Item value below 0 should fail validation."""
        validator = Draft7Validator(schema)
        entity = {
            "id": "sword",
            "kind": "item",
            "name": "Broken Sword",
            "value": -1,  # Invalid: below minimum
        }
        errors = list(validator.iter_errors(entity))
        assert len(errors) > 0


class TestMixedEntityValidation:
    """Test validation with multiple entity types."""

    def test_mixed_entities_all_validate(self, tmp_path: Path, schema):
        """Multiple entities of different kinds all validate together."""
        _write_entity(
            tmp_path,
            "player",
            "player",
            {
                "id": "player",
                "kind": "player",
                "name": "Player",
                "hp": 100,
                "max_hp": 100,
                "gold": 50,
                "inventory": [],
            },
        )
        _write_entity(
            tmp_path,
            "town",
            "start-town",
            {
                "id": "start-town",
                "kind": "town",
                "name": "Starting Town",
                "connections": [],
                "npcs": ["sage"],
            },
        )
        _write_entity(
            tmp_path,
            "npc",
            "sage",
            {
                "id": "sage",
                "kind": "npc",
                "name": "Old Sage",
                "hp": 50,
                "max_hp": 50,
            },
        )
        _write_entity(
            tmp_path,
            "item",
            "potion",
            {
                "id": "potion",
                "kind": "item",
                "name": "Health Potion",
                "value": 25,
            },
        )

        issues, entities = validate_game_data(tmp_path, schema)
        assert len(issues) == 0
        assert len(entities) == 4

