import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from neonrp.core.manifest import EntityRecord, Manifest
from neonrp.core.paths import get_data_dir_name, get_manifest_path, get_game_dir
from neonrp.core.storage import atomic_write_json
from neonrp.core.validation import ValidationIssue, load_schema

ID_KIND_PATTERN = re.compile(r"^[a-z0-9._-]+$")


def entity_key(kind: str, entity_id: str) -> str:
    return f"{kind}:{entity_id}"


def compute_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _iter_game_json_files(root: Path) -> Iterable[Path]:
    game_dir = get_game_dir(root)
    if not game_dir.exists():
        return []
    # game/secrets/** never enters the index: retrieval/find must not be able
    # to surface unrevealed secrets to any agent (docs/SECRETS-DESIGN.md §b).
    return (p for p in game_dir.rglob("*.json") if p.parent.name != "secrets")


def _iter_game_doc_files(root: Path) -> Iterable[Path]:
    """Markdown entities — the native format (docs/DATA-FORMAT.md).

    Same secrets exclusion as JSON: switching a world to markdown must not
    quietly open a door that the JSON path keeps shut.
    """
    game_dir = get_game_dir(root)
    if not game_dir.exists():
        return []
    return (p for p in game_dir.rglob("*.md") if p.parent.name != "secrets")


def _load_entity_payload(path: Path) -> tuple[dict, ValidationIssue | None, str]:
    """Read one entity file. Returns (data, issue, rel_hint).

    JSON and Markdown-with-frontmatter are both first-class; a file that is
    neither (a plain note with no frontmatter) is not an entity and is
    skipped without complaint.
    """
    rel = path.name
    if path.suffix == ".json":
        try:
            return json.loads(path.read_text(encoding="utf-8")), None, rel
        except json.JSONDecodeError as exc:
            return {}, ValidationIssue(
                file=rel, layer="structure", code="json", path="$",
                message=f"Invalid JSON: {exc.msg}",
                suggestion="Fix JSON syntax.",
            ), rel

    from neonrp.core.frontmatter import FrontmatterError, parse

    try:
        doc = parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return {}, ValidationIssue(
            file=rel, layer="structure", code="read", path="$",
            message=f"读不出文件: {exc}", suggestion="检查文件编码。",
        ), rel
    except FrontmatterError as exc:
        return {}, ValidationIssue(
            file=rel, layer="structure", code="frontmatter", path="$",
            message=f"frontmatter 有问题: {exc}",
            suggestion="见 docs/DATA-FORMAT.md 的受支持子集。",
        ), rel
    if not doc.is_entity:
        # A note without id/kind is prose, not an entity. Not an error.
        return {}, None, rel
    data = dict(doc.fields)
    data.setdefault("summary", (doc.body.strip().splitlines() or [""])[0][:200] or None)
    return data, None, rel


def _validate_entity_for_index(
    rel_path: str,
    data: Dict[str, Any],
    id_index: Dict[str, str],
    *,
    data_dir_name: str,
) -> List[ValidationIssue]:
    """Validate a single entity for indexing purposes.

    Returns a list of issues (empty if valid).
    """
    issues: List[ValidationIssue] = []
    parts = Path(rel_path).parts

    # Check required fields
    for field in ("id", "kind", "name"):
        if field not in data:
            issues.append(
                ValidationIssue(
                    file=rel_path,
                    layer="structure",
                    code="missing-field",
                    path=f"$.{field}",
                    message=f"Missing required field: {field}",
                    suggestion=f"Add the '{field}' field to the entity.",
                )
            )

    if issues:  # Can't continue without required fields
        return issues

    # Check path format. Sub-folders between <kind> and the file are allowed for
    # organization (game/<kind>/.../<id>.json), so the floor is 3 segments, not
    # exactly 3. kind is still the first folder under game/; id is the filename.
    # `.md` is as legitimate as `.json` — markdown with frontmatter is the
    # native entity format now (docs/DATA-FORMAT.md); the layout convention
    # (game/<kind>/.../<id>.<ext>) is unchanged.
    if (
        len(parts) < 3
        or parts[0] != data_dir_name
        or not parts[-1].endswith((".json", ".md"))
    ):
        issues.append(
            ValidationIssue(
                file=rel_path,
                layer="constraint",
                code="path-format",
                path="$",
                message=f"Entity files must be stored under {data_dir_name}/<kind>/.../<id>.json",
                suggestion="Move or rename the file to match the convention.",
            )
        )
        return issues

    kind_from_path = parts[1]
    # Strip whichever suffix this file actually has — `[:-5]` silently
    # truncated `<id>.md` to `<id[:-2]>` and reported a bogus id mismatch.
    id_from_path = parts[-1].rsplit(".", 1)[0]

    kind_value = data.get("kind")
    id_value = data.get("id")

    # Check kind/path consistency
    if kind_value != kind_from_path:
        issues.append(
            ValidationIssue(
                file=rel_path,
                layer="constraint",
                code="kind-mismatch",
                path="$.kind",
                message=f"kind '{kind_value}' does not match path segment '{kind_from_path}'",
                suggestion="Update the kind or move the file to the correct folder.",
            )
        )

    # Check id/filename consistency
    if id_value != id_from_path:
        issues.append(
            ValidationIssue(
                file=rel_path,
                layer="constraint",
                code="id-mismatch",
                path="$.id",
                message=f"id '{id_value}' does not match filename '{id_from_path}'",
                suggestion="Update the id or rename the file to match.",
            )
        )

    # Check kind format
    if kind_value and not ID_KIND_PATTERN.fullmatch(kind_value):
        issues.append(
            ValidationIssue(
                file=rel_path,
                layer="constraint",
                code="kind-format",
                path="$.kind",
                message="kind contains invalid characters",
                suggestion="Use only lowercase letters, digits, '.', '_' or '-'.",
            )
        )

    # Check duplicate id (within this scan session)
    if id_value and id_value in id_index and id_index[id_value] != rel_path:
        issues.append(
            ValidationIssue(
                file=rel_path,
                layer="constraint",
                code="id-duplicate",
                path="$.id",
                message=f"Duplicate id '{id_value}' also appears in {id_index[id_value]}",
                suggestion="Ensure ids are globally unique.",
            )
        )

    return issues


def scan_entities(root: Path) -> Tuple[List[EntityRecord], List[ValidationIssue]]:
    """Scan game/ directory and build entity records.

    Unlike the old all-or-nothing behavior, this now:
    - Indexes all valid entities
    - Skips invalid entities
    - Returns warnings for invalid entities (does not block indexing)
    """
    # Try to load schema to ensure it's available, but failures here are warnings
    try:
        load_schema(root)
    except FileNotFoundError:
        pass  # Proceed without schema validation for now

    records: List[EntityRecord] = []
    warnings: List[ValidationIssue] = []
    id_index: Dict[str, str] = {}  # id -> path (for duplicate detection)
    data_dir_name = get_data_dir_name(root)

    # Markdown is read AFTER json so that a world mid-migration resolves the
    # way docs/DATA-FORMAT.md promises: when the same id exists in both, the
    # markdown wins — and the collision is reported rather than silently
    # resolved, because two sources of truth is the failure mode this whole
    # migration has to avoid.
    for path in list(_iter_game_json_files(root)) + list(_iter_game_doc_files(root)):
        rel_path = path.relative_to(root).as_posix()
        is_doc = path.suffix == ".md"

        data, issue, _ = _load_entity_payload(path)
        if issue is not None:
            issue.file = rel_path
            warnings.append(issue)
            continue
        if not data:
            continue  # prose without id/kind — not an entity

        # Validate for indexing. A markdown entity that collides with a json
        # one is legitimate during migration, so it is not judged a duplicate.
        collided = is_doc and data.get("id") in id_index
        check_index = {k: v for k, v in id_index.items() if k != data.get("id")} if collided else id_index
        issues = _validate_entity_for_index(rel_path, data, check_index, data_dir_name=data_dir_name)
        if issues:
            warnings.extend(issues)
            continue

        if collided:
            warnings.append(
                ValidationIssue(
                    file=rel_path,
                    layer="structure",
                    code="format-collision",
                    path="$",
                    message=(
                        f"id '{data['id']}' 同时存在于 {id_index[data['id']]} 与本文件;"
                        f"markdown 生效"
                    ),
                    suggestion="迁移完成后删掉旧的 JSON(见 docs/DATA-FORMAT.md)。",
                )
            )
            records = [r for r in records if r.id != data["id"]]

        # Record id for duplicate detection
        id_value = data.get("id")
        if id_value:
            id_index[id_value] = rel_path

        # Build record
        mtime = path.stat().st_mtime
        record = EntityRecord(
            id=data["id"],
            kind=data["kind"],
            name=data["name"],
            tags=data.get("tags"),
            summary=data.get("summary"),
            path=rel_path,
            mtime=mtime,
            hash=compute_file_hash(path),
        )
        records.append(record)

    return records, warnings


def records_to_map(records: List[EntityRecord]) -> Dict[str, EntityRecord]:
    return {entity_key(record.kind, record.id): record for record in records}


def update_entities(
    existing: Dict[str, EntityRecord],
    records: List[EntityRecord],
) -> Tuple[Dict[str, EntityRecord], Dict[str, int]]:
    new_map = records_to_map(records)
    updated_map = dict(existing)

    added = 0
    updated = 0
    unchanged = 0

    for key, record in new_map.items():
        if key not in existing:
            updated_map[key] = record
            added += 1
            continue

        current = existing[key]
        if current.hash != record.hash or current.mtime != record.mtime:
            updated_map[key] = record
            updated += 1
        else:
            unchanged += 1

    removed = 0
    for key in list(existing.keys()):
        if key not in new_map:
            updated_map.pop(key, None)
            removed += 1

    stats = {
        "added": added,
        "updated": updated,
        "removed": removed,
        "unchanged": unchanged,
        "total": len(new_map),
    }

    return updated_map, stats


def refresh_manifest_index(
    root: Path,
    *,
    full_rebuild: bool = False,
) -> tuple[Manifest, dict[str, int], list[ValidationIssue]]:
    """Refresh manifest.entities from game/ and persist only on changes.

    Args:
        root: Project root.
        full_rebuild: When True, replace manifest.entities from scratch.
            When False, perform incremental update based on mtime/hash.

    Returns:
        (manifest, stats, warnings)

    Raises:
        FileNotFoundError: if manifest is missing.
        ValueError: if manifest cannot be loaded.
    """
    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        raise FileNotFoundError("Manifest not found")

    try:
        manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise ValueError(f"Failed to load manifest: {exc}") from exc

    records, warnings = scan_entities(root)

    if full_rebuild:
        new_entities = records_to_map(records)
        stats = {
            "added": max(0, len(new_entities) - len(manifest.entities)),
            "updated": 0,
            "removed": max(0, len(manifest.entities) - len(new_entities)),
            "unchanged": 0,
            "total": len(new_entities),
        }
    else:
        new_entities, stats = update_entities(manifest.entities, records)

    if new_entities != manifest.entities:
        manifest.entities = new_entities
        atomic_write_json(manifest_path, manifest.model_dump())
    return manifest, stats, warnings

