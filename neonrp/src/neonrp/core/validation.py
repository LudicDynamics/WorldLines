import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from jsonschema import Draft7Validator

from neonrp.core.paths import (
    DEFAULT_SCHEMA_FILENAME,
    get_rules_dir,
    get_data_dir_name,
    get_game_dir,
)

ID_KIND_PATTERN = re.compile(r"^[a-z0-9._-]+$")

# Per-soul bundle pieces the multi-agent runtime reads. All of them DEGRADE
# rather than crash (soul_agent inlines "(persona 文件缺失)" placeholders), so
# their absence is a warning — the soul plays, but hollow. The soul *folder*
# itself missing is different: the cast entry is dangling and the character is
# an empty shell, which we treat as a blocker.
_SOUL_BUNDLE_WARN_PIECES = (
    ("soul.json", "soul identity (name/backend) falls back to the sid"),
    ("soul.md", "the soul plays without its charter voice"),
    ("persona", "the soul plays without its persona kernel"),
    ("agents/manifest.json", "the soul runs without its specialist roster"),
)


@dataclass
class ValidationIssue:
    file: str
    layer: str
    code: str
    path: str
    message: str
    suggestion: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "file": self.file,
            "layer": self.layer,
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "suggestion": self.suggestion,
        }


def load_schema(root: Path) -> Dict[str, Any]:
    schema_path = get_rules_dir(root) / DEFAULT_SCHEMA_FILENAME
    if schema_path.exists():
        with schema_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    try:
        schema_text = resources.files("neonrp.schema").joinpath(DEFAULT_SCHEMA_FILENAME).read_text(encoding="utf-8")
    except Exception as exc:
        raise FileNotFoundError("Default schema not found") from exc

    return json.loads(schema_text)


def _json_path_from_error(error) -> str:
    if not error.absolute_path:
        return "$"
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _iter_game_json_files(root: Path) -> Iterable[Path]:
    game_dir = get_game_dir(root)
    if not game_dir.exists():
        return []
    # game/secrets/** is the secrets overlay, not entity data — it has its own
    # schema and its own check_world layer (see _secrets_issues).
    return (p for p in game_dir.rglob("*.json") if p.parent.name != "secrets")


def validate_game_data(root: Path, schema: Dict[str, Any]) -> Tuple[List[ValidationIssue], List[Dict[str, Any]]]:
    issues: List[ValidationIssue] = []
    entities: List[Dict[str, Any]] = []
    validator = Draft7Validator(schema)
    data_dir_name = get_data_dir_name(root)

    for path in _iter_game_json_files(root):
        rel_path = path.relative_to(root).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(
                ValidationIssue(
                    file=rel_path,
                    layer="structure",
                    code="json",
                    path="$",
                    message=f"Invalid JSON: {exc.msg}",
                    suggestion="Fix JSON syntax.",
                )
            )
            continue

        schema_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if schema_errors:
            for err in schema_errors:
                issues.append(
                    ValidationIssue(
                        file=rel_path,
                        layer="structure",
                        code="schema",
                        path=_json_path_from_error(err),
                        message=err.message,
                        suggestion="Fix the value or add the required field.",
                    )
                )
            continue

        entities.append({"path": rel_path, "data": data})

    issues.extend(_constraint_issues(entities, data_dir_name=data_dir_name))
    # Player-projection validation retired with player_projection.py — under
    # the three-archetype ontology the player is not a soul and game/player/
    # is its own master, not a projection. There is no projection contract
    # to validate.
    return issues, entities


def _constraint_issues(entities: List[Dict[str, Any]], *, data_dir_name: str) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    id_index: Dict[str, str] = {}
    duplicate_reported: set[tuple[str, str]] = set()

    for entry in entities:
        rel_path = entry["path"]
        data = entry["data"]
        parts = Path(rel_path).parts

        # Sub-folders between <kind> and the file are allowed for organization
        # (game/<kind>/.../<id>.json); floor is 3 segments, not exactly 3. kind is
        # still the first folder under game/; id is the filename.
        if len(parts) < 3 or parts[0] != data_dir_name or not parts[-1].endswith(".json"):
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
            continue

        kind_from_path = parts[1]
        id_from_path = parts[-1][:-5]

        kind_value = data.get("kind")
        id_value = data.get("id")

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

        if id_value:
            if id_value in id_index:
                other = id_index[id_value]
                key = tuple(sorted([rel_path, other]))
                if key not in duplicate_reported:
                    duplicate_reported.add(key)
                    issues.append(
                        ValidationIssue(
                            file=rel_path,
                            layer="constraint",
                            code="id-duplicate",
                            path="$.id",
                            message=f"Duplicate id '{id_value}' also appears in {other}",
                            suggestion="Ensure ids are globally unique.",
                        )
                    )
                    issues.append(
                        ValidationIssue(
                            file=other,
                            layer="constraint",
                            code="id-duplicate",
                            path="$.id",
                            message=f"Duplicate id '{id_value}' also appears in {rel_path}",
                            suggestion="Ensure ids are globally unique.",
                        )
                    )
            else:
                id_index[id_value] = rel_path

    return issues


# ── World playability health-check ──────────────────────────────────
#
# `check_world` is what `neonrp validate` runs today: a layered "can this
# world actually be played?" report over the whole bundle (game/ + souls/ +
# .neonrp/ + agents/), not just a game/ schema lint. Severity is grounded in
# what the runtime actually does:
#
#   BLOCKER — the world plays wrong or content is silently lost:
#     · unparseable JSON anywhere in the bundle (the deepseek-quote bug:
#       entities/souls silently vanish from play)
#     · a broken .neonrp/playthrough.json (conversation.py catches the parse
#       error and silently downgrades a multi-agent world to single-agent)
#     · a cast soul whose souls/<sid>-<iid>/ folder is missing (dangling cast)
#     · duplicate entity ids (the index breaks)
#
#   WARNING — degraded but playable, or self-healing:
#     · missing router agent / active-agent drift (every launch path calls
#       ensure_playable_world, which scaffolds and repairs these)
#     · missing soul.json / soul.md / persona/ / agents/manifest.json inside a
#       soul (soul_agent inlines "(缺失)" placeholders — plays hollow)
#     · a location reference no town_map resolves (place_nav refuses the move;
#       nothing crashes)
#     · missing game-start opening; game/ schema drift (kind/id mismatch etc.)


@dataclass
class WorldHealth:
    """Result of :func:`check_world` — playable means no blockers."""

    playable: bool
    flavor: str  # "multi-agent" | "orchestrator" | "build"
    blockers: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.playable,
            "playable": self.playable,
            "flavor": self.flavor,
            "blockers": [i.to_dict() for i in self.blockers],
            "warnings": [i.to_dict() for i in self.warnings],
            "stats": dict(self.stats),
        }


def _scan_bundle_json(root: Path) -> tuple[List[ValidationIssue], set]:
    """Layer 1: every load-bearing JSON file in the bundle must parse.

    Scans <data_dir>/**/*.json, souls/**/*.json, agents/**/*.json and the
    top-level .neonrp/*.json (NOT .neonrp/commits/** — the commit DAG is
    content-addressed history, not authored content)."""
    issues: List[ValidationIssue] = []
    bad_files: set = set()

    candidates: List[Path] = []
    game_dir = get_game_dir(root)
    if game_dir.is_dir():
        candidates.extend(sorted(game_dir.rglob("*.json")))
    for sub in ("souls", "agents"):
        d = root / sub
        if d.is_dir():
            candidates.extend(sorted(d.rglob("*.json")))
    neonrp_dir = root / ".neonrp"
    if neonrp_dir.is_dir():
        candidates.extend(sorted(neonrp_dir.glob("*.json")))

    for path in candidates:
        rel = path.relative_to(root).as_posix()
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            bad_files.add(rel)
            issues.append(
                ValidationIssue(
                    file=rel,
                    layer="json",
                    code="json-parse",
                    path=f"line {exc.lineno}, column {exc.colno}",
                    message=f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})",
                    suggestion="Fix the JSON syntax — the runtime silently skips unreadable files, so this content is lost in play.",
                )
            )
        except OSError as exc:
            bad_files.add(rel)
            issues.append(
                ValidationIssue(
                    file=rel,
                    layer="json",
                    code="io",
                    path="$",
                    message=f"Unreadable file: {exc}",
                    suggestion="Check file permissions/encoding.",
                )
            )
    return issues, bad_files


def _known_locations(root: Path) -> tuple[Dict[str, set], bool]:
    """Map of town_id -> node-id set from game/towns/*/town_map.json.

    Returns (maps, has_maps). Worlds without town maps (name-only geography)
    return has_maps=False and reference checks are skipped entirely —
    conservative by design."""
    from neonrp.core.place_tree import town_docs

    maps: Dict[str, set] = {}
    for tid, data in town_docs(root).items():  # old town_map.json files and folder trees alike
        nodes = set()
        for n in data.get("nodes", []):
            if isinstance(n, dict) and n.get("id"):
                nodes.add(str(n.get("id")))
                nodes.update(str(a) for a in n.get("aliases") or [])
        maps[tid] = nodes
    return maps, bool(maps)


def _location_resolves(loc: str, maps: Dict[str, set]) -> bool:
    """Does a location string resolve against the town maps? Mirrors
    place_nav's addressing: "T###" (town-level), "T###/node" (scoped),
    or a bare node id found in any town."""
    loc = str(loc or "").strip()
    if not loc:
        return True  # empty = unplaced; not a dangling reference
    if "/" in loc:
        town, node = loc.split("/", 1)
        return town in maps and node in maps[town]
    if loc in maps:
        return True  # town-level address
    return any(loc in nodes for nodes in maps.values())


def _secrets_issues(root: Path) -> List[ValidationIssue]:
    """Warnings for the game/secrets/ overlay: schema problems the loader
    reports (missing about/audience/content, unknown audience tokens, broken
    JSON) and secrets whose host entity does not exist (the reveal would have
    nowhere to merge). Worlds without secrets/ return []."""
    from neonrp.core.secrets import has_secrets, load_secrets

    if not has_secrets(root):
        return []
    issues: List[ValidationIssue] = []
    secrets, loader_issues = load_secrets(root)
    for line in loader_issues:
        file, _, message = line.partition(": ")
        issues.append(
            ValidationIssue(
                file=file or "game/secrets/",
                layer="secrets",
                code="secret-schema",
                path="$",
                message=message or line,
                suggestion="Fix the secret file — malformed secrets stay GM-only and can never be revealed.",
            )
        )
    game_dir = get_game_dir(root)
    for secret in secrets:
        if secret.about and not (game_dir / f"{secret.about}.json").exists():
            issues.append(
                ValidationIssue(
                    file=secret.rel_path,
                    layer="secrets",
                    code="secret-host-missing",
                    path="$.about",
                    message=f"Secret '{secret.secret_id}' is about '{secret.about}', which has no entity file",
                    suggestion="Point 'about' at an existing game/<kind>/<id>.json — a reveal has nowhere to merge otherwise.",
                )
            )
    return issues


def _travel_graph_issues(root: Path) -> List[ValidationIssue]:
    """Warnings for map defects the location judge routes around:

    - town_map nodes unreachable from any gate over ``links`` (orphan islands —
      souls can be placed there but never walk there);
    - world_map towns whose town_map has no gate node (untravelable — the
      judge can't stage the gate two-beat, so it stops clamping travel there).
    """
    from neonrp.core.place_nav import _gate_of, _map_nodes, _town_maps, load_world_map

    issues: List[ValidationIssue] = []
    town_maps = _town_maps(root)
    world_map = load_world_map(root)
    world_towns = {
        str(n.get("id"))
        for n in (world_map.get("nodes", []) if world_map else [])
        if isinstance(n, dict) and n.get("type") in ("town", "city", "village")
    }

    for tid, data in sorted(town_maps.items()):
        nodes = _map_nodes(data)
        gate = _gate_of(data)
        rel = f"game/towns/{tid}/town_map.json"
        if gate is None:
            if tid in world_towns:
                issues.append(
                    ValidationIssue(
                        file=rel,
                        layer="references",
                        code="town-gateless",
                        path="$.nodes",
                        message=f"Town '{tid}' is on the world map but has no gate node — travel in/out can't be staged",
                        suggestion='Add a node with "type": "gate" linked to the town graph.',
                    )
                )
            continue
        # BFS from every gate over undirected links.
        seen = {
            nid for nid, n in nodes.items() if n.get("type") == "gate" or nid.startswith("gate")
        }
        queue = list(seen)
        adj: Dict[str, set] = {}
        for nid, n in nodes.items():
            for link in n.get("links", []) or []:
                link = str(link)
                adj.setdefault(nid, set()).add(link)
                adj.setdefault(link, set()).add(nid)
        while queue:
            cur = queue.pop()
            for nxt in adj.get(cur, ()):
                if nxt in nodes and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        orphans = sorted(set(nodes) - seen)
        if orphans:
            issues.append(
                ValidationIssue(
                    file=rel,
                    layer="references",
                    code="node-unreachable",
                    path="$.nodes",
                    message=f"Town '{tid}' has nodes unreachable from any gate: {', '.join(orphans)}",
                    suggestion="Wire them into the town graph via links (or remove them).",
                )
            )
    return issues


def check_world(root: Path) -> WorldHealth:
    """Layered world playability health-check (see module notes above)."""
    from neonrp.core.active_agent import validate_active_agent
    from neonrp.core.playthrough import PlaythroughError, read_playthrough
    from neonrp.core.runtime_contract import (
        get_runtime_contract_path,
        load_runtime_contract,
        resolve_router_agent_id,
    )

    blockers: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    stats: Dict[str, Any] = {}

    # Layer 1 — JSON parse across the bundle.
    json_issues, bad_files = _scan_bundle_json(root)
    blockers.extend(json_issues)

    # Layer 2 — flavor + playthrough binding.
    playthrough = None
    pt_rel = ".neonrp/playthrough.json"
    if (root / pt_rel).exists():
        flavor = "multi-agent"
        try:
            playthrough = read_playthrough(root)
        except PlaythroughError as exc:
            # Layer-1 already flagged malformed JSON; schema violations
            # (missing fields / schema_version mismatch) surface only here.
            if pt_rel not in bad_files:
                blockers.append(
                    ValidationIssue(
                        file=pt_rel,
                        layer="playthrough",
                        code="playthrough-schema",
                        path="$",
                        message=str(exc),
                        suggestion="Fix the manifest — the engine treats a broken playthrough as 'no playthrough' and silently plays the world single-agent, without its souls.",
                    )
                )
        if playthrough is not None and not playthrough.souls:
            flavor = "orchestrator"
    else:
        contract_file = get_runtime_contract_path(root).exists()
        flavor = "orchestrator" if contract_file or (root / "agents").is_dir() else "build"

    # Layer 3 — runtime contract + router scaffold + active-agent.
    # load_runtime_contract never fails (it infers a default contract), and
    # every launch path calls ensure_playable_world which scaffolds a missing
    # router — so these are warnings, not blockers.
    try:
        contract = load_runtime_contract(root)
        router_id = resolve_router_agent_id(root)
    except Exception:
        contract = None
        router_id = "narrator"
    if flavor != "build" and not (root / "agents" / router_id / "agent.json").exists():
        warnings.append(
            ValidationIssue(
                file=f"agents/{router_id}/agent.json",
                layer="scaffold",
                code="router-missing",
                path="$",
                message=f"Router agent '{router_id}' has no agents/{router_id}/agent.json",
                suggestion="Launching the world auto-scaffolds it (ensure_playable_world); or run the ensure_playable_scaffold skill in build mode.",
            )
        )
    try:
        for msg in validate_active_agent(root):
            warnings.append(
                ValidationIssue(
                    file=(contract.active_agent_relpath if contract else "game/meta/active-agent.json"),
                    layer="scaffold",
                    code="active-agent",
                    path="$",
                    message=msg,
                    suggestion="Reset it by launching the world, or point active_agent at a real agent.",
                )
            )
    except Exception:
        pass

    # Layer 4 — soul bundles (multi-agent only).
    souls_total = 0
    if playthrough is not None and playthrough.souls:
        souls_total = len(playthrough.souls)
        souls_root = root / "souls"
        for soul in playthrough.souls:
            rel_dir = f"souls/{soul.sid}-{soul.instance_id}"
            soul_dir = souls_root / f"{soul.sid}-{soul.instance_id}"
            if not soul_dir.is_dir():
                blockers.append(
                    ValidationIssue(
                        file=rel_dir,
                        layer="souls",
                        code="soul-missing",
                        path="$",
                        message=f"Cast soul '{soul.sid}' ({soul.role}) has no folder at {rel_dir}",
                        suggestion="The playthrough casts this soul but its bundle is gone — restore the folder or remove the entry from .neonrp/playthrough.json.",
                    )
                )
                continue
            for piece, consequence in _SOUL_BUNDLE_WARN_PIECES:
                p = soul_dir / piece
                present = p.is_dir() and any(p.iterdir()) if piece == "persona" else p.exists()
                if not present:
                    warnings.append(
                        ValidationIssue(
                            file=f"{rel_dir}/{piece}",
                            layer="souls",
                            code="soul-incomplete",
                            path="$",
                            message=f"Soul '{soul.sid}' is missing {piece} — {consequence}",
                            suggestion="Author the missing piece (soul-authoring / soul-card-authoring produce the full bundle).",
                        )
                    )

    # Layer 5 — location reference integrity (only when town maps exist;
    # place_nav REFUSES unresolvable moves rather than crashing → warnings).
    maps, has_maps = _known_locations(root)
    if has_maps and playthrough is not None and playthrough.souls:
        for soul in playthrough.souls:
            rs = root / "souls" / f"{soul.sid}-{soul.instance_id}" / "run_state.json"
            try:
                state = json.loads(rs.read_text(encoding="utf-8"))
                loc = state.get("location") if isinstance(state, dict) else None
            except (OSError, ValueError):
                continue
            if loc and not _location_resolves(str(loc), maps):
                warnings.append(
                    ValidationIssue(
                        file=rs.relative_to(root).as_posix(),
                        layer="references",
                        code="location-dangling",
                        path="$.location",
                        message=f"Soul '{soul.sid}' is at '{loc}', which no game/towns/*/town_map.json defines",
                        suggestion="Move the soul to a mapped node — the locality router can't route it and moves from here are refused.",
                    )
                )
        for i, integ in enumerate(playthrough.integrations):
            loc = integ.get("location") if isinstance(integ, dict) else None
            if loc and not _location_resolves(str(loc), maps):
                warnings.append(
                    ValidationIssue(
                        file=pt_rel,
                        layer="references",
                        code="location-dangling",
                        path=f"$.integrations[{i}].location",
                        message=f"Integration routes location '{loc}', which no town_map defines",
                        suggestion="Point it at a mapped node (scene-understanding rewrites this each turn, so it usually self-corrects).",
                    )
                )

    # Layer 5b — travel-graph sanity (the location judge routes travel through
    # gates over town_map links + world_map adjacency; these warn where that
    # graph is broken). Warnings only: the judge degrades permissively.
    if has_maps:
        warnings.extend(_travel_graph_issues(root))
    # Layer 5b' — map lint (MAP-SCALES-1005 G3): dangling links, unbound / dangling ports, isolated places, old forms
    try:
        from neonrp.core.map_lint import lint_map

        for q in lint_map(root):
            warnings.append(ValidationIssue(file=q["where"].split("#")[0], layer="map", code=q["code"], path=q["where"],
                                            message=q["msg"], suggestion=""))
    except Exception:  # noqa: BLE001 — the lint never breaks the health check
        pass

    # Layer 5c — secrets overlay sanity (docs/SECRETS-DESIGN.md). Warnings
    # only: a malformed secret fails closed (GM-only, unrevealable), it does
    # not break play.
    warnings.extend(_secrets_issues(root))

    # Layer 6 — opening scene.
    if flavor != "build":
        startup_rel = contract.startup_relpath if contract else "game/meta/game-start.json"
        if not (root / startup_rel).exists():
            warnings.append(
                ValidationIssue(
                    file=startup_rel,
                    layer="opening",
                    code="game-start-missing",
                    path="$",
                    message="No game-start file — the world opens without an authored opening scene",
                    suggestion="Author it (world-game-authoring writes game/meta/game-start.json) or launch once to scaffold a minimal one.",
                )
            )

    # Layer 7 — legacy game/ schema + constraint lint, downgraded to warnings
    # (schema drift doesn't stop play) EXCEPT id-duplicate (the index breaks).
    entities: List[Dict[str, Any]] = []
    try:
        schema = load_schema(root)
        legacy_issues, entities = validate_game_data(root, schema)
        for issue in legacy_issues:
            if issue.code == "json":
                continue  # already a layer-1 blocker with line/col
            if issue.code == "id-duplicate":
                blockers.append(issue)
            else:
                warnings.append(issue)
    except Exception as exc:
        warnings.append(
            ValidationIssue(
                file="rules/schema",
                layer="structure",
                code="schema-unavailable",
                path="$",
                message=f"Entity schema lint skipped: {exc}",
                suggestion="Restore the packaged schema (reinstall) or rules/entity.schema.json.",
            )
        )

    # Stats.
    if has_maps:
        location_count = sum(len(v) for v in maps.values())
    else:
        location_count = sum(
            1 for e in entities if e["data"].get("kind") in ("location", "town", "place")
        )
    stats.update(
        {
            "flavor": flavor,
            "souls": souls_total,
            "active_souls": len(playthrough.active_souls) if playthrough else 0,
            "locations": location_count,
            "entities": len(entities),
            "router": router_id,
        }
    )

    return WorldHealth(
        playable=not blockers,
        flavor=flavor,
        blockers=blockers,
        warnings=warnings,
        stats=stats,
    )

