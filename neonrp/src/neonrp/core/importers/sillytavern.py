"""SillyTavern character card import mapping."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

from neonrp.core.importers.png_extract import PNGExtractionError, extract_chara_from_png, is_png_file


# Must match game_entity.schema.json id/kind pattern
_ID_PATTERN = re.compile(r"^[a-z0-9._-]+$")


def name_to_id(name: str) -> str:
    """Convert a character name to a kebab-case entity ID.

    Args:
        name: The character name (e.g. "August Babenberg")

    Returns:
        Kebab-case ID matching [a-z0-9._-]+ (e.g. "august-babenberg")
    """
    # Lowercase, replace non-alphanum sequences with a single hyphen
    result = re.sub(r"[^a-z0-9]+", "-", name.lower())
    result = result.strip("-")
    if result:
        return result
    if not name:
        return "unnamed"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    return f"entity-{digest}"


def is_valid_entity_id(value: str) -> bool:
    """Return True when the value matches the entity id pattern."""
    return bool(_ID_PATTERN.match(value))


def resolve_id_conflict(base_id: str, existing_ids: set[str]) -> str:
    """Append -2, -3, ... until no conflict with existing IDs."""
    if base_id not in existing_ids:
        return base_id
    suffix = 2
    while f"{base_id}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base_id}-{suffix}"


def parse_card(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract the data payload from a SillyTavern card JSON.

    Handles both v2 format (``{"spec": ..., "data": {...}}``)
    and v1 format (flat keys at the top level).

    Returns:
        Dict with normalised keys: name, description, personality,
        scenario, first_mes, tags, creator, character_book, raw.

    Raises:
        ValueError: If the card has no recognisable ``name`` field.
    """
    # v2 has a "data" wrapper
    if "data" in raw and isinstance(raw.get("data"), dict):
        data = raw["data"]
    else:
        data = raw

    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Card has no 'name' field (or it is empty)")

    return {
        "name": name,
        "description": data.get("description", ""),
        "personality": data.get("personality", ""),
        "scenario": data.get("scenario", ""),
        "first_mes": data.get("first_mes", ""),
        "tags": data.get("tags", []),
        "creator": data.get("creator", ""),
        "character_book": data.get("character_book"),
        "raw": raw,
    }


def build_entity(
    parsed: dict[str, Any],
    *,
    entity_id: Optional[str] = None,
    existing_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Build a NeonRP world entity dict from a parsed card.

    Args:
        parsed: Output of :func:`parse_card`.
        entity_id: Explicit ID override (``--id`` flag).
        existing_ids: Set of IDs already present in ``game/character/``
            for conflict resolution.

    Returns:
        Dict conforming to ``game_entity.schema.json``.

    Raises:
        ValueError: If the supplied entity_id doesn't match the ID pattern.
    """
    name = parsed["name"]

    # Determine base ID
    if entity_id:
        base_id = entity_id
        if not is_valid_entity_id(base_id):
            raise ValueError(f"Invalid entity ID '{base_id}': must match pattern [a-z0-9._-]+")
    else:
        base_id = name_to_id(name)

    # Resolve conflicts
    final_id = resolve_id_conflict(base_id, existing_ids or set())

    # Build summary
    summary = _build_summary(parsed)

    # Filter tags
    tags = _filter_tags(parsed["tags"])

    entity: dict[str, Any] = {
        "id": final_id,
        "kind": "character",
        "name": name,
    }

    if tags:
        entity["tags"] = tags
    if summary:
        entity["summary"] = summary

    entity["meta"] = {
        "source": "sillytavern",
    }

    if parsed.get("creator"):
        entity["meta"]["creator"] = parsed["creator"]

    # Preserve full raw payload per ADR-0010
    entity["meta"]["raw"] = parsed["raw"]

    return entity


def load_card_file(file_path: Path | str) -> dict[str, Any]:
    """Load a SillyTavern card payload from JSON or PNG."""
    file_path = Path(file_path)

    if is_png_file(file_path):
        return extract_chara_from_png(file_path)

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {file_path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Cannot read {file_path}: {exc}") from exc


def build_entity_from_card_file(
    file_path: Path | str,
    *,
    entity_id: Optional[str] = None,
    existing_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Load a SillyTavern JSON/PNG card file and convert it to a NeonRP entity."""
    try:
        raw = load_card_file(file_path)
    except PNGExtractionError as exc:
        raise ValueError(str(exc)) from exc

    try:
        parsed = parse_card(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid SillyTavern card: {exc}") from exc

    return build_entity(parsed, entity_id=entity_id, existing_ids=existing_ids)


def _build_summary(parsed: dict[str, Any]) -> str:
    """Derive a summary string from card fields."""
    # Prefer explicit personality if present
    if parsed["personality"]:
        return parsed["personality"]

    # Fall back to description excerpt
    desc = parsed["description"]
    if not desc:
        return ""

    if len(desc) <= 300:
        return desc

    # Try to cut at a sentence boundary
    truncated = desc[:300]
    last_period = truncated.rfind(".")
    if last_period > 100:
        return truncated[: last_period + 1]
    return truncated + "..."


def _filter_tags(tags: list[Any]) -> list[str]:
    """Normalise and deduplicate tags."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if isinstance(tag, str) and tag.strip():
            normalised = tag.strip().lower()
            if normalised not in seen:
                seen.add(normalised)
                result.append(normalised)
    return result

