"""Data-driven domain rules and action resolution for NeonRP.

Schema validation remains the structural gate. This module provides an optional,
thin domain-validation layer plus optional mechanical action resolution.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neonrp.core.config import load_config
from neonrp.core.paths import get_game_dir

logger = logging.getLogger(__name__)


DEFAULT_RULES_PROFILE: dict[str, Any] = {
    "kinds": {
        "character": ["character", "player", "npc"],
        "location": ["location", "town", "dungeon", "shop"],
    },
    "validation": {
        "entity_rules": [
            {
                "rule": "hp_non_negative",
                "entity_kind_set": "character",
                "field": "hp",
                "check": "number_min",
                "min": 0,
                "message": "HP cannot be negative: {value}",
            },
            {
                "rule": "gold_non_negative",
                "entity_kind_set": "character",
                "field": "gold",
                "check": "number_min",
                "min": 0,
                "message": "Gold cannot be negative: {value}",
            },
            {
                "rule": "location_exists",
                "entity_kind_set": "character",
                "field": "location",
                "check": "in_set",
                "set_name": "location_ids",
                "skip_if_set_empty": True,
                "message": "Location '{value}' does not exist. Valid locations: {valid_values}",
            },
            {
                "rule": "inventory_valid",
                "entity_kind_set": "character",
                "field": "inventory",
                "check": "array",
                "message": "Inventory must be an array",
            },
            {
                "rule": "inventory_item_valid",
                "entity_kind_set": "character",
                "field": "inventory",
                "check": "array_items_object_has_any",
                "any_fields": ["id", "name"],
                "non_object_message": "Inventory item must be an object, got {value_type}",
                "missing_keys_message": "Inventory item must have 'id' or 'name' field",
            },
        ]
    },
    "resolve_action": {
        "enabled_actions": ["damage", "heal", "buy", "sell", "move"],
        "fields": {
            "hp": "hp",
            "max_hp": "max_hp",
            "gold": "gold",
            "location": "location",
            "connections": "connections",
            "inventory": "inventory",
            "inventory_item_id": "id",
            "inventory_item_name": "name",
            "inventory_item_quantity": "quantity",
            "inventory_item_value": "value",
            "shop_items": "items_available",
            "shop_item_id": "id",
            "shop_item_name": "name",
            "shop_item_price": "price",
        },
        "defaults": {
            "max_hp": 100,
            "sell_item_value": 10,
        },
        "sell_price_divisor": 2,
        "min_sell_price": 1,
    },
}


@dataclass
class RuleViolation:
    """A domain rule violation found during validation."""

    entity_path: str
    field: str
    rule: str
    message: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_path": self.entity_path,
            "field": self.field,
            "rule": self.rule,
            "message": self.message,
            "value": self.value,
        }


@dataclass
class ActionResult:
    """Result of resolving a game action."""

    success: bool
    action: str
    message: str
    computed_values: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(existing, value)
        else:
            merged[key] = value
    return merged


def _normalize_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_RULES_PROFILE)
    if isinstance(profile, dict):
        merged = _deep_merge_dicts(merged, profile)
    return merged


def load_rules_profile(root: Path | None = None, profile_path: str | None = None) -> dict[str, Any]:
    """Load effective rules profile from defaults + optional JSON override file."""
    merged = copy.deepcopy(DEFAULT_RULES_PROFILE)
    resolved_path: Path | None = None
    configured_path = profile_path

    if configured_path is None and root is not None:
        try:
            configured_path = load_config(root).rules.profile_path
        except Exception as exc:
            logger.warning("Failed to read config for rules profile: %s", exc)

    if configured_path:
        candidate = Path(configured_path)
        resolved_path = candidate if candidate.is_absolute() else ((root or Path.cwd()) / candidate)

    if resolved_path is None:
        return merged
    if not resolved_path.exists():
        logger.warning("Rules profile not found: %s", resolved_path)
        return merged

    try:
        data = json.loads(resolved_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse rules profile '%s': %s", resolved_path, exc)
        return merged

    if not isinstance(data, dict):
        logger.warning("Rules profile must be a JSON object: %s", resolved_path)
        return merged

    return _deep_merge_dicts(merged, data)


def _kind_set(profile: dict[str, Any], set_name: str) -> set[str]:
    kinds = profile.get("kinds", {}).get(set_name, [])
    if not isinstance(kinds, list):
        return set()
    return {str(v) for v in kinds if isinstance(v, str)}


def validate_game_rules(
    staged_game: Path,
    proposal: Any = None,
    profile: dict[str, Any] | None = None,
) -> list[RuleViolation]:
    """Validate optional domain rules on staged game state."""
    del proposal  # Reserved for future contextual rules.
    effective_profile = _normalize_profile(profile)
    violations: list[RuleViolation] = []
    game_dir = get_game_dir(staged_game)
    if not game_dir.exists():
        return violations

    entities: list[tuple[str, dict[str, Any]]] = []
    location_ids: set[str] = set()
    location_kinds = _kind_set(effective_profile, "location")

    for json_file in game_dir.rglob("*.json"):
        rel_path = json_file.relative_to(staged_game).as_posix()
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            # JSON and schema errors are handled by structural validation.
            continue
        if not isinstance(data, dict):
            continue
        entities.append((rel_path, data))
        if data.get("kind") in location_kinds and isinstance(data.get("id"), str):
            location_ids.add(data["id"])

    context_sets: dict[str, set[str]] = {"location_ids": location_ids}
    entity_rules = effective_profile.get("validation", {}).get("entity_rules", [])
    if not isinstance(entity_rules, list):
        return violations

    for rel_path, data in entities:
        kind = str(data.get("kind", ""))
        for rule in entity_rules:
            if not isinstance(rule, dict):
                continue
            if not _entity_matches_rule_kind(kind, rule, effective_profile):
                continue
            violations.extend(_evaluate_rule(rel_path, data, rule, context_sets))

    return violations


def _entity_matches_rule_kind(kind: str, rule: dict[str, Any], profile: dict[str, Any]) -> bool:
    explicit_kinds = rule.get("entity_kinds")
    if isinstance(explicit_kinds, list) and explicit_kinds:
        return kind in {str(v) for v in explicit_kinds if isinstance(v, str)}

    kind_set_name = rule.get("entity_kind_set")
    if isinstance(kind_set_name, str) and kind_set_name:
        return kind in _kind_set(profile, kind_set_name)

    return True


def _evaluate_rule(
    entity_path: str,
    entity: dict[str, Any],
    rule: dict[str, Any],
    context_sets: dict[str, set[str]],
) -> list[RuleViolation]:
    check = str(rule.get("check", ""))
    field_name = str(rule.get("field", ""))
    value = entity.get(field_name)
    rule_name = str(rule.get("rule", "rule_violation"))
    violations: list[RuleViolation] = []

    if check == "number_min":
        min_value = rule.get("min", 0)
        if isinstance(value, (int, float)) and isinstance(min_value, (int, float)) and value < min_value:
            violations.append(
                RuleViolation(
                    entity_path=entity_path,
                    field=field_name,
                    rule=rule_name,
                    message=_format_message(rule, f"Value for '{field_name}' must be >= {min_value}", value=value),
                    value=value,
                )
            )
        return violations

    if check == "in_set":
        set_name = str(rule.get("set_name", ""))
        valid_set = context_sets.get(set_name, set())
        skip_if_empty = bool(rule.get("skip_if_set_empty", True))
        if value is not None and (valid_set or not skip_if_empty) and value not in valid_set:
            violations.append(
                RuleViolation(
                    entity_path=entity_path,
                    field=field_name,
                    rule=rule_name,
                    message=_format_message(
                        rule,
                        f"Value '{value}' is not in allowed set",
                        value=value,
                        valid_values=sorted(valid_set),
                    ),
                    value=value,
                )
            )
        return violations

    if check == "array":
        if value is not None and not isinstance(value, list):
            violations.append(
                RuleViolation(
                    entity_path=entity_path,
                    field=field_name,
                    rule=rule_name,
                    message=_format_message(rule, f"Field '{field_name}' must be an array", value_type=type(value).__name__),
                    value=type(value).__name__,
                )
            )
        return violations

    if check == "array_items_object_has_any":
        if value is None or not isinstance(value, list):
            return violations
        any_fields = [str(f) for f in rule.get("any_fields", []) if isinstance(f, str)]
        for idx, item in enumerate(value):
            item_field = f"{field_name}[{idx}]"
            if not isinstance(item, dict):
                message = str(rule.get("non_object_message", "Array item must be an object"))
                violations.append(
                    RuleViolation(
                        entity_path=entity_path,
                        field=item_field,
                        rule=rule_name,
                        message=message.format(index=idx, value_type=type(item).__name__, value=item),
                        value=item,
                    )
                )
                continue
            if any_fields and not any(field in item for field in any_fields):
                message = str(rule.get("missing_keys_message", f"Array item must include one of: {any_fields}"))
                violations.append(
                    RuleViolation(
                        entity_path=entity_path,
                        field=item_field,
                        rule=rule_name,
                        message=message,
                        value=item,
                    )
                )
        return violations

    logger.debug("Unknown rules check '%s' for field '%s'", check, field_name)
    return violations


def _format_message(rule: dict[str, Any], default_message: str, **values: Any) -> str:
    template = rule.get("message")
    if not isinstance(template, str) or not template:
        return default_message
    try:
        return template.format(**values)
    except Exception:
        return default_message


def resolve_action(
    root: Path,
    action: str,
    actor: str,
    target: str | None = None,
    amount: int | None = None,
    item: str | None = None,
    destination: str | None = None,
    profile: dict[str, Any] | None = None,
) -> ActionResult:
    """Resolve a game action mechanically without writing files."""
    effective_profile = _normalize_profile(profile or load_rules_profile(root))
    action_config = effective_profile.get("resolve_action", {})
    enabled_actions = action_config.get("enabled_actions", [])
    if not isinstance(enabled_actions, list):
        enabled_actions = []
    if action not in {str(v) for v in enabled_actions if isinstance(v, str)}:
        return ActionResult(
            success=False,
            action=action,
            message=f"Unknown or disabled action: {action}",
            error="unknown_action",
        )

    game_dir = get_game_dir(root)
    actor_data = _find_entity(game_dir, actor)
    if actor_data is None:
        return ActionResult(
            success=False,
            action=action,
            message=f"Actor '{actor}' not found",
            error="actor_not_found",
        )

    if action == "damage":
        return _resolve_damage(game_dir, actor, action_config, target, amount)
    if action == "heal":
        return _resolve_heal(actor, actor_data, action_config, amount)
    if action == "buy":
        return _resolve_buy(game_dir, actor, actor_data, action_config, item, amount, target)
    if action == "sell":
        return _resolve_sell(actor, actor_data, action_config, item, amount)
    if action == "move":
        return _resolve_move(game_dir, actor, actor_data, effective_profile, action_config, destination)

    return ActionResult(
        success=False,
        action=action,
        message=f"Unknown action: {action}",
        error="unknown_action",
    )


def _field_name(action_config: dict[str, Any], key: str, default: str) -> str:
    fields = action_config.get("fields", {})
    if isinstance(fields, dict):
        value = fields.get(key)
        if isinstance(value, str) and value:
            return value
    return default


def _config_number(action_config: dict[str, Any], key: str, default: int) -> int:
    value = action_config.get(key)
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _config_default_number(action_config: dict[str, Any], key: str, default: int) -> int:
    defaults = action_config.get("defaults", {})
    if isinstance(defaults, dict):
        value = defaults.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return default


def _find_entity(game_dir: Path, entity_id: str) -> dict[str, Any] | None:
    """Find an entity by id in the game directory.

    Falls back to SYNTHESIZED views for the two M16/M18 shapes that don't
    exist as single ``{"id": ...}`` files: the player (a folder of part-files
    — profile/stats/wallet/…) and souls (their bundle lives outside game/).
    Without this, ``resolve_action(actor="player")`` always failed with
    actor_not_found in M16-shaped worlds.
    """
    for json_file in game_dir.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id") == entity_id:
            return data
    if entity_id == "player":
        return _synthesize_player_entity(game_dir)
    return _synthesize_soul_entity(game_dir.parent, entity_id)


def _synthesize_player_entity(game_dir: Path) -> dict[str, Any] | None:
    """Merge the M16 player part-files into one mechanical entity view
    (wallet's gold, stats' hp, inventory — all top-level)."""
    pdir = game_dir / "player"
    if not pdir.is_dir():
        return None
    merged: dict[str, Any] = {"id": "player"}
    found = False
    for name in ("profile", "stats", "wallet", "inventory", "equipment", "flags"):
        try:
            data = json.loads((pdir / f"{name}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            merged.update(data)
            found = True
    return merged if found else None


def _synthesize_soul_entity(root: Path, entity_id: str) -> dict[str, Any] | None:
    """A soul (sid or instance_id) as a mechanical entity: soul.json +
    run_state.json merged, run_state's status flattened to top level."""
    souls = root / "souls"
    if not souls.is_dir():
        return None
    candidates = sorted(souls.glob(f"{entity_id}-*")) + sorted(
        souls.glob(f"*-{entity_id}")
    )
    for soul_dir in candidates:
        if not soul_dir.is_dir():
            continue
        merged: dict[str, Any] = {"id": entity_id}
        found = False
        for name in ("soul", "run_state"):
            try:
                data = json.loads(
                    (soul_dir / f"{name}.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                status = data.get("status")
                if isinstance(status, dict):
                    merged.update(status)
                merged.update({k: v for k, v in data.items() if k != "status"})
                found = True
        if found:
            return merged
    return None


def _resolve_damage(
    game_dir: Path,
    actor: str,
    action_config: dict[str, Any],
    target: str | None,
    amount: int | None,
) -> ActionResult:
    if target is None:
        return ActionResult(False, "damage", "Target required for damage action", error="missing_target")
    if amount is None or amount < 0:
        return ActionResult(False, "damage", "Positive damage amount required", error="invalid_amount")

    target_data = _find_entity(game_dir, target)
    if target_data is None:
        return ActionResult(False, "damage", f"Target '{target}' not found", error="target_not_found")

    hp_field = _field_name(action_config, "hp", "hp")
    current_hp = target_data.get(hp_field, 0)
    if not isinstance(current_hp, (int, float)):
        current_hp = 0
    new_hp = max(0, int(current_hp - amount))

    return ActionResult(
        success=True,
        action="damage",
        message=f"{actor} deals {amount} damage to {target}. HP: {current_hp} -> {new_hp}",
        computed_values={
            "target_id": target,
            "old_hp": current_hp,
            "new_hp": new_hp,
            "damage_dealt": amount,
            "is_defeated": new_hp == 0,
        },
    )


def _resolve_heal(actor: str, actor_data: dict[str, Any], action_config: dict[str, Any], amount: int | None) -> ActionResult:
    if amount is None or amount < 0:
        return ActionResult(False, "heal", "Positive heal amount required", error="invalid_amount")

    hp_field = _field_name(action_config, "hp", "hp")
    max_hp_field = _field_name(action_config, "max_hp", "max_hp")
    default_max_hp = _config_default_number(action_config, "max_hp", 100)

    current_hp = actor_data.get(hp_field, 0)
    max_hp = actor_data.get(max_hp_field, default_max_hp)
    if not isinstance(current_hp, (int, float)):
        current_hp = 0
    if not isinstance(max_hp, (int, float)):
        max_hp = default_max_hp

    new_hp = min(int(max_hp), int(current_hp + amount))
    actual_heal = new_hp - int(current_hp)

    return ActionResult(
        success=True,
        action="heal",
        message=f"{actor} heals for {actual_heal} HP. HP: {current_hp} -> {new_hp}",
        computed_values={
            "actor_id": actor,
            "old_hp": current_hp,
            "new_hp": new_hp,
            "max_hp": max_hp,
            "actual_heal": actual_heal,
        },
    )


def _resolve_buy(
    game_dir: Path,
    actor: str,
    actor_data: dict[str, Any],
    action_config: dict[str, Any],
    item: str | None,
    amount: int | None,
    shop: str | None,
) -> ActionResult:
    if item is None:
        return ActionResult(False, "buy", "Item id required for buy action", error="missing_item")

    quantity = amount if isinstance(amount, int) and amount > 0 else 1
    gold_field = _field_name(action_config, "gold", "gold")
    current_gold = actor_data.get(gold_field, 0)
    if not isinstance(current_gold, (int, float)):
        current_gold = 0

    shop_items_field = _field_name(action_config, "shop_items", "items_available")
    shop_item_id_field = _field_name(action_config, "shop_item_id", "id")
    shop_item_name_field = _field_name(action_config, "shop_item_name", "name")
    shop_item_price_field = _field_name(action_config, "shop_item_price", "price")

    price: int | None = None
    item_name = item
    if shop:
        shop_data = _find_entity(game_dir, shop)
        if isinstance(shop_data, dict):
            items_available = shop_data.get(shop_items_field, [])
            if isinstance(items_available, list):
                for available_item in items_available:
                    if not isinstance(available_item, dict):
                        continue
                    if available_item.get(shop_item_id_field) != item:
                        continue
                    raw_price = available_item.get(shop_item_price_field, 0)
                    if isinstance(raw_price, (int, float)):
                        price = int(raw_price)
                    item_name = str(available_item.get(shop_item_name_field, item))
                    break

    if price is None:
        return ActionResult(False, "buy", f"Item '{item}' not available for purchase", error="item_not_available")

    total_cost = price * quantity
    if current_gold < total_cost:
        return ActionResult(
            success=False,
            action="buy",
            message=f"Insufficient gold: have {current_gold}, need {total_cost}",
            error="insufficient_gold",
            computed_values={
                "actor_id": actor,
                "current_gold": current_gold,
                "required_gold": total_cost,
                "shortfall": total_cost - current_gold,
            },
        )

    new_gold = int(current_gold - total_cost)
    return ActionResult(
        success=True,
        action="buy",
        message=f"{actor} buys {quantity}x {item_name} for {total_cost} gold. Gold: {current_gold} -> {new_gold}",
        computed_values={
            "actor_id": actor,
            "item_id": item,
            "item_name": item_name,
            "quantity": quantity,
            "price_per_unit": price,
            "total_cost": total_cost,
            "old_gold": current_gold,
            "new_gold": new_gold,
        },
    )


def _resolve_sell(
    actor: str,
    actor_data: dict[str, Any],
    action_config: dict[str, Any],
    item: str | None,
    amount: int | None,
) -> ActionResult:
    if item is None:
        return ActionResult(False, "sell", "Item id required for sell action", error="missing_item")

    quantity = amount if isinstance(amount, int) and amount > 0 else 1
    gold_field = _field_name(action_config, "gold", "gold")
    inventory_field = _field_name(action_config, "inventory", "inventory")
    item_id_field = _field_name(action_config, "inventory_item_id", "id")
    item_quantity_field = _field_name(action_config, "inventory_item_quantity", "quantity")
    item_value_field = _field_name(action_config, "inventory_item_value", "value")
    default_item_value = _config_default_number(action_config, "sell_item_value", 10)
    sell_price_divisor = max(1, _config_number(action_config, "sell_price_divisor", 2))
    min_sell_price = max(1, _config_number(action_config, "min_sell_price", 1))

    current_gold = actor_data.get(gold_field, 0)
    inventory = actor_data.get(inventory_field, [])
    if not isinstance(current_gold, (int, float)):
        current_gold = 0
    if not isinstance(inventory, list):
        inventory = []

    found_item: dict[str, Any] | None = None
    found_quantity = 0
    for inv_item in inventory:
        if not isinstance(inv_item, dict):
            continue
        if inv_item.get(item_id_field) != item:
            continue
        found_item = inv_item
        raw_quantity = inv_item.get(item_quantity_field, 1)
        found_quantity = int(raw_quantity) if isinstance(raw_quantity, (int, float)) else 1
        break

    if found_item is None:
        return ActionResult(False, "sell", f"Item '{item}' not in inventory", error="item_not_in_inventory")
    if found_quantity < quantity:
        return ActionResult(
            False,
            "sell",
            f"Not enough {item}: have {found_quantity}, want to sell {quantity}",
            error="insufficient_quantity",
        )

    raw_item_value = found_item.get(item_value_field, default_item_value)
    if not isinstance(raw_item_value, (int, float)):
        raw_item_value = default_item_value
    sell_price = max(min_sell_price, int(raw_item_value) // sell_price_divisor)
    total_gain = sell_price * quantity
    new_gold = int(current_gold + total_gain)

    return ActionResult(
        success=True,
        action="sell",
        message=f"{actor} sells {quantity}x {item} for {total_gain} gold. Gold: {current_gold} -> {new_gold}",
        computed_values={
            "actor_id": actor,
            "item_id": item,
            "quantity_sold": quantity,
            "remaining_quantity": found_quantity - quantity,
            "price_per_unit": sell_price,
            "total_gain": total_gain,
            "old_gold": current_gold,
            "new_gold": new_gold,
        },
    )


def _resolve_move(
    game_dir: Path,
    actor: str,
    actor_data: dict[str, Any],
    profile: dict[str, Any],
    action_config: dict[str, Any],
    destination: str | None,
) -> ActionResult:
    if destination is None:
        return ActionResult(False, "move", "Destination required for move action", error="missing_destination")

    location_field = _field_name(action_config, "location", "location")
    connections_field = _field_name(action_config, "connections", "connections")
    location_kinds = _kind_set(profile, "location")

    current_location = actor_data.get(location_field)
    if isinstance(current_location, str) and current_location == destination:
        return ActionResult(
            success=True,
            action="move",
            message=f"{actor} is already at '{destination}'",
            computed_values={
                "actor_id": actor,
                "old_location": current_location,
                "new_location": destination,
                "no_op": True,
            },
        )
    destination_data = _find_entity(game_dir, destination)
    if destination_data is None:
        return ActionResult(False, "move", f"Destination '{destination}' not found", error="destination_not_found")

    destination_kind = destination_data.get("kind", "")
    if destination_kind not in location_kinds:
        return ActionResult(
            False,
            "move",
            f"'{destination}' is not a valid location (kind: {destination_kind})",
            error="invalid_destination_type",
        )

    if current_location:
        current_data = _find_entity(game_dir, str(current_location))
        if isinstance(current_data, dict):
            connections = current_data.get(connections_field, [])
            if isinstance(connections, list) and connections and destination not in connections:
                return ActionResult(
                    success=False,
                    action="move",
                    message=f"Cannot move to '{destination}' - not connected to '{current_location}'. Connected: {connections}",
                    error="not_connected",
                    computed_values={
                        "current_location": current_location,
                        "destination": destination,
                        "available_connections": connections,
                    },
                )

    return ActionResult(
        success=True,
        action="move",
        message=f"{actor} moves from '{current_location}' to '{destination}'",
        computed_values={
            "actor_id": actor,
            "old_location": current_location,
            "new_location": destination,
        },
    )

