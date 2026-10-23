"""Soul → world placement (casting).

A *soul* (``neonrp.core.souls``) is a reusable, world-agnostic character
asset. *Casting* projects that asset into a concrete world. The projection
form is **mode-dependent** — the same soul lands in a different place
depending on the world's ``execution_mode``:

* ``orchestrator`` — the soul is flattened into a world-baked NPC at
  ``game/npc/<id>.json``. The single world-agent voices it; no
  ``playthrough.json``, no per-soul agent, no ``active_souls``. This is the
  cheap path the Dark Train / Stoneford worlds use.
* ``multi-agent`` — the soul folder is copied into ``souls/<sid>-<iid>/``
  and registered as a ``SoulRef`` in ``playthrough.json``; each cast soul
  becomes its own ``soul:<sid>:<iid>`` agent and is added to
  ``active_souls``.
* ``fast`` — no characters at all; casting is rejected.

The *player avatar* (分身) is the same soul asset projected as the player:
``game/player/profile.json`` (orchestrator) or a ``PlayerRef`` /
``role="player"`` soul (multi-agent).

This module is a pure library leaf: it reads the soul bundle + writes the
world's placement store. It does not run turns or touch the LLM.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neonrp.core.playthrough import (
    PlayerRef,
    SoulRef,
    read_playthrough,
    write_playthrough,
)
from neonrp.core.souls import SOUL_HOME, read_soul_json


class PlacementError(Exception):
    """Raised when a soul cannot be cast into the target world."""


# ---------------------------------------------------------------------------
# Soul resolution
# ---------------------------------------------------------------------------


def trait_weights(doc: dict[str, Any]) -> dict[str, float]:
    """persona/core_traits.json → {trait: weight 0–1}, from either shape a soul ships (10-07, the 1.0 UI reported Elena's
    traits never reached placement): ``{"traits": {name: 0–1}}`` (older souls) or
    ``{"core_traits": [{"trait": name, "intensity": 0–100, …}]}`` (stoneford and the templates written since)."""
    out: dict[str, float] = {}
    raw = doc.get("traits") if isinstance(doc, dict) else None
    if isinstance(raw, dict):
        out.update({str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))})
    rows = doc.get("core_traits") if isinstance(doc, dict) else None
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("trait") and isinstance(r.get("intensity"), (int, float)):
            v = float(r["intensity"])
            out.setdefault(str(r["trait"]), v / 100.0 if v > 1 else v)
    return out

def resolve_soul_dir(token: str) -> Path:
    """Resolve a cast token to a soul directory.

    ``token`` may be:
      * an explicit path to a soul folder (contains ``soul.json``), or
      * a ``sid`` / folder-name prefix searched (newest-first) under
        ``~/.worldlines/souls/``.

    Raises :class:`PlacementError` if nothing matches.
    """
    p = Path(token).expanduser()
    if p.is_dir() and (p / "soul.json").exists():
        return p

    if SOUL_HOME.exists():
        matches = [
            d
            for d in SOUL_HOME.iterdir()
            if d.is_dir()
            and (d / "soul.json").exists()
            and (d.name == token or d.name.startswith(f"{token}-"))
        ]
        if matches:
            matches.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            return matches[0]

    raise PlacementError(
        f"No soul found for '{token}'. Pass a soul folder path, or a sid "
        f"present under {SOUL_HOME}."
    )


def read_world_native_cast(game_dir: Path, *, locale: str = "en") -> dict[str, Any]:
    """Scene-aware read of a multi-agent world's OWN cast.

    A true multi-agent world ships its characters natively: souls forked into
    ``souls/<sid>-<iid>/`` and registered in ``playthrough.json`` (with
    ``active_souls`` marking who is on-stage), plus a baked protagonist at
    ``game/player/profile.json``. Placement must surface THESE first — external
    souls are added on top, never in place of them (see
    project_scene_aware_placement). Orchestrator / fast worlds have no
    ``playthrough.json`` and get an empty cast here (they keep the flatten-NPC
    path).

    Returns ``{"souls": [entry, ...], "avatar": entry | None}``:
      * each soul entry mirrors :func:`neonrp.core.souls.list_souls`
        (``sid`` / ``display_name`` / ``path``) plus ``instance_id`` and the
        scene markers ``native=True`` / ``active`` (in ``active_souls``);
      * ``avatar`` is the prior protagonist as a player-avatar dict
        (``name`` / ``summary`` / ``data`` / ``path``, ``native=True``) or None.
    """
    from neonrp.core.souls import _display_name, read_soul_json

    game_dir = Path(game_dir)
    souls_out: list[dict[str, Any]] = []
    # Casting happens BEFORE the world is instantiated, so this must read BOTH
    # layouts: a live game dir (`<root>/.neonrp/playthrough.json`, validated via
    # read_playthrough) AND a raw template (`<root>/playthrough.json` at root,
    # parsed best-effort — the casting screen resolves the template path for the
    # picked world_id, which has no .neonrp/ yet).
    soul_refs, active = _read_playthrough_souls(game_dir)
    souls_root = game_dir / "souls"
    for sid, instance_id, role in soul_refs:
        sdir = souls_root / f"{sid}-{instance_id}"
        if not sdir.is_dir() and souls_root.is_dir():
            # Tolerate naming drift: match by instance_id suffix or sid prefix.
            cands = [
                d for d in souls_root.iterdir()
                if d.is_dir() and (d.name.endswith(instance_id) or d.name.startswith(f"{sid}-"))
            ]
            if cands:
                sdir = cands[0]
        meta = read_soul_json(sdir) if sdir.is_dir() else None
        souls_out.append({
            "sid": sid,
            "instance_id": instance_id,
            "display_name": _display_name(meta, locale) if meta else sid,
            "path": sdir,
            "role": role,
            "native": True,
            "active": instance_id in active,
        })

    return {"souls": souls_out, "avatar": _read_prior_protagonist(game_dir, locale=locale)}


def _read_playthrough_souls(root: Path) -> tuple[list[tuple[str, str, str]], set[str]]:
    """Return ``([(sid, instance_id, role), ...], active_instance_ids)`` from a
    world's playthrough, reading a live game dir's validated
    ``.neonrp/playthrough.json`` when present, else a template's root
    ``playthrough.json`` (best-effort, pre-instantiation). Empty when neither
    exists (orchestrator / fast worlds)."""
    from neonrp.core.playthrough import read_playthrough

    nested = root / ".neonrp" / "playthrough.json"
    if nested.is_file():
        try:
            pt = read_playthrough(root)
        except Exception:  # noqa: BLE001 — malformed must not crash casting
            return [], set()
        if pt is None:
            return [], set()
        return [(s.sid, s.instance_id, s.role) for s in pt.souls], set(pt.active_souls)

    template_pt = root / "playthrough.json"
    if not template_pt.is_file():
        return [], set()
    try:
        data = json.loads(template_pt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], set()
    if not isinstance(data, dict):
        return [], set()
    refs: list[tuple[str, str, str]] = []
    for s in data.get("souls") or []:
        if isinstance(s, dict) and s.get("sid") and s.get("instance_id"):
            refs.append((str(s["sid"]), str(s["instance_id"]), str(s.get("role") or "")))
    raw_active = data.get("active_souls")
    active = set(str(x) for x in raw_active) if isinstance(raw_active, list) else {iid for _, iid, _ in refs}
    return refs, active


def _read_prior_protagonist(game_dir: Path, *, locale: str = "en") -> dict[str, Any] | None:
    """The world's baked protagonist (``game/player/profile.json``) shaped as a
    player-avatar entry, or None when the world ships no PC. This is the
    "prior" avatar the placement screen offers alongside the Default."""
    from neonrp.core.i18n_card import card_name_for_locale

    profile_path = Path(game_dir) / "game" / "player" / "profile.json"
    if not profile_path.is_file():
        return None
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    name = card_name_for_locale(
        str(data.get("display_name") or data.get("name") or ""),
        str(data.get("name_local") or ""),
        locale,
    )
    return {
        "path": profile_path,
        "name": name or str(data.get("sid") or "Protagonist"),
        "summary": str(data.get("summary") or ""),
        "data": data,
        "native": True,
    }


# ---------------------------------------------------------------------------
# Best-effort soul content extraction (tolerant; blanks where unknown)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_soul_full(soul_dir: Path) -> dict[str, Any]:
    """Capture the *entire authored character* of a soul into one nested dict.

    This is the lossless core behind the orchestrator collapse: when a soul
    is flattened into ``game/npc/<id>.json`` there is no ``souls/`` folder
    to fall back on, so every authored file must travel into the JSON or it
    is gone. We carry charter + persona + background (incl. GM-only secrets,
    since the world-agent IS the GM) + character/RPG body + rules + the
    starting memory seed. Pure runtime state (short-term-memo, trajectory,
    run_state, .commits) and the soul's own sub-agent decomposition
    (agents/, only meaningful in multi-agent) are intentionally omitted —
    they are not part of "who the character is".

    Every field is best-effort: a missing file yields ``""`` / ``{}`` rather
    than raising, so partially-authored souls still cast cleanly.
    """
    persona_dir = soul_dir / "persona"
    bg = soul_dir / "background"
    char = soul_dir / "character"
    rules = soul_dir / "rules"
    ltm = soul_dir / "long-term-memo"

    meta = read_soul_json(soul_dir)
    return {
        "sid": meta.sid if meta else soul_dir.name.split("-")[0],
        "version": meta.version if meta else "",
        "charter": _read_text(soul_dir / "soul.md"),
        "persona": {
            "core_traits": trait_weights(_read_json(persona_dir / "core_traits.json")),
            "motivations": _read_json(persona_dir / "motivations.json").get("motivations", []),
            "values": _read_json(persona_dir / "values.json").get("values", []),
            "relationships": _read_json(persona_dir / "relationships.json").get("relationships", {}),
        },
        "background": {
            "origin": _read_text(bg / "origin.md"),
            "history": _read_text(bg / "history.md"),
            "secrets": _read_text(bg / "secrets.md"),  # GM-only; world-agent is the GM
        },
        "character": {
            "profile": _read_json(char / "profile.json"),
            "stats": _read_json(char / "stats.json"),
            "status": _read_json(char / "status.json"),
            "equipment": _read_json(char / "equipment.json"),
            "inventory": _read_json(char / "inventory.json"),
            "wallet": _read_json(char / "wallet.json"),
        },
        "rules": {
            "action": _read_text(rules / "action_rules.md"),
            "decision": _read_text(rules / "decision_rules.md"),
            "interaction": _read_text(rules / "interaction_rules.md"),
        },
        "memory_seed": {
            "emotional_memories": _read_json(ltm / "emotional_memories.json"),
            "important_events": _read_text(ltm / "important_events.md"),
            "learned_facts": _read_json(ltm / "learned_facts.json"),
        },
    }


def _md_section(text: str, heading: str) -> str:
    """Return the first paragraph under a ``## <heading>`` section, or ''."""
    pat = re.compile(rf"^#+\s*{re.escape(heading)}.*?$", re.IGNORECASE | re.MULTILINE)
    m = pat.search(text)
    if not m:
        return ""
    rest = text[m.end():].lstrip("\n")
    # First non-empty block up to the next blank line or heading.
    out: list[str] = []
    for line in rest.splitlines():
        if line.startswith("#"):
            break
        if not line.strip():
            if out:
                break
            continue
        out.append(line.strip())
    return " ".join(out).strip()


def _soul_identity(soul_dir: Path, char: dict[str, Any]) -> dict[str, Any]:
    """Resolve a soul's sid/name/version tolerantly.

    Prefer the M16 ``soul.json`` envelope; fall back to
    ``character/profile.json`` (which carries sid/display_name/name_local/
    tags) and finally the directory name. Hub-published souls built by
    bundle_factory ship the persona/character structure WITHOUT a soul.json,
    so requiring it would break casting/avatar projection for them.
    """
    meta = read_soul_json(soul_dir)
    if meta is not None:
        return {
            "sid": meta.sid,
            "name": meta.name_local or meta.name,
            "name_en": meta.name,
            "version": meta.version,
            "tags": list(meta.tags or []),
        }
    # No soul.json — derive from character/profile.json or the dir name.
    sid = str(char.get("sid") or soul_dir.name.split("-")[0] or soul_dir.name)
    name = str(
        char.get("name_local") or char.get("display_name") or char.get("name") or sid
    )
    return {
        "sid": sid,
        "name": name,
        "name_en": str(char.get("display_name") or char.get("name") or sid),
        "version": str(char.get("version") or ""),
        "tags": list(char.get("tags") or []),
    }


def _soul_profile(soul_dir: Path) -> dict[str, Any]:
    """Collect a normalized view of a soul for projection (best-effort).

    Tolerates soul-json-less bundles (hub/bundle_factory souls). Raises only
    if the folder is not a soul at all (no soul.json AND no persona/ AND no
    character/profile.json).
    """
    char = _read_json(soul_dir / "character" / "profile.json")
    ident = _soul_identity(soul_dir, char)
    if (
        not (soul_dir / "soul.json").is_file()
        and not (soul_dir / "persona").is_dir()
        and not char
    ):
        raise PlacementError(
            f"{soul_dir} is not a soul folder (no soul.json / persona/ / character/)."
        )

    traits_raw = trait_weights(_read_json(soul_dir / "persona" / "core_traits.json"))
    traits: list[str] = []
    if isinstance(traits_raw, dict):
        # Keep the salient traits (score >= 0.7) by descending weight.
        traits = [
            k
            for k, v in sorted(
                traits_raw.items(),
                key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0,
                reverse=True,
            )
            if isinstance(v, (int, float)) and v >= 0.7
        ]

    charter = ""
    try:
        charter = (soul_dir / "soul.md").read_text(encoding="utf-8")
    except OSError:
        charter = ""

    summary = (
        str(char.get("summary") or "").strip()
        or _md_section(charter, "Core Presence")
    )
    voice = _md_section(charter, "Voice And Social Posture") or _md_section(
        charter, "Voice"
    )

    drop = {"pc", "player", "ho1", "ho2", "ho3"}
    tags = [t for t in (ident["tags"] or []) if t not in drop]

    return {
        "sid": ident["sid"],
        "name": ident["name"],
        "name_en": ident["name_en"],
        "version": ident["version"],
        "summary": summary,
        "voice": voice,
        "traits": traits,
        "tags": tags,
        "dir_name": soul_dir.name,
    }


# ---------------------------------------------------------------------------
# World NPC capacity (optional authored limit — Dark Train=1, Stoneford=1)
# ---------------------------------------------------------------------------

def world_npc_capacity(game_dir: Path) -> int | None:
    """The world's authored NPC slot count, or ``None`` (= unlimited).

    Read from ``game/meta/game-start.json:npc_capacity``. Absent / non-int
    ⇒ no limit (most worlds). A capacity-1 world (e.g. Dark Train) holds one
    cast NPC alongside the player.
    """
    meta = _read_json(game_dir / "game" / "meta" / "game-start.json")
    cap = meta.get("npc_capacity")
    return cap if isinstance(cap, int) and cap >= 0 else None


def _current_npc_count_orchestrator(game_dir: Path, *, exclude_id: str = "") -> int:
    npc_dir = game_dir / "game" / "npc"
    if not npc_dir.is_dir():
        return 0
    return sum(
        1
        for p in npc_dir.glob("*.json")
        if p.stem != exclude_id
    )


def _check_capacity_orchestrator(game_dir: Path, npc_id: str, force: bool) -> None:
    cap = world_npc_capacity(game_dir)
    if cap is None or force:
        return
    # An overwrite of an existing slot doesn't grow the cast.
    current = _current_npc_count_orchestrator(game_dir, exclude_id=npc_id)
    if current >= cap:
        raise PlacementError(
            f"World is at NPC capacity ({cap}). Remove an NPC or pass "
            f"--force to override."
        )


# ---------------------------------------------------------------------------
# Orchestrator projection — soul → game/npc/<id>.json
# ---------------------------------------------------------------------------

def project_soul_as_npc(
    game_dir: Path,
    soul_dir: Path,
    *,
    location: str = "",
    npc_id: str | None = None,
    overwrite: bool = False,
    overrides: dict[str, Any] | None = None,
) -> Path:
    """Flatten a soul into a world-baked NPC at ``game/npc/<id>.json``.

    The single world-agent reads ``game/npc/*.json`` and voices these
    characters directly — no playthrough, no per-soul agent. Returns the
    path written.

    ``overrides`` patches the placement block after projection (e.g.
    user-edited fields from the casting preview: role_in_world / why_here /
    relationship_to_player / current_goal).
    """
    prof = _soul_profile(soul_dir)
    npc_id = npc_id or prof["sid"]
    npc_path = game_dir / "game" / "npc" / f"{npc_id}.json"
    if npc_path.exists() and not overwrite:
        raise PlacementError(
            f"NPC '{npc_id}' already exists at {npc_path}. "
            f"Pass overwrite=True / --force to replace."
        )
    _check_capacity_orchestrator(game_dir, npc_id, force=overwrite)

    placement = {
        "role_in_world": "",
        "why_here": "",
        "relationship_to_player": "",
        "current_goal": "",
        "known_lore": [],
        "unknown_lore": [],
        "adapted": False,
    }
    if overrides:
        placement.update({k: v for k, v in overrides.items() if k in placement})
        placement["adapted"] = True

    npc = {
        # --- engine-facing NPC convention (game/npc/<id>.json) ---
        "id": npc_id,
        "kind": "npc",
        "name": prof["name"],
        "tags": ["npc", *prof["tags"]],
        "summary": prof["summary"],
        "location": location,
        "inventory": [],
        "voice": prof["voice"],
        "traits": prof["traits"],
        "state": {
            "met": False,
            "affection": 0,
            "mood": "neutral",
            "inner_state": "",
        },
        "memory": "",
        # --- placement overlay: how this soul is adapted INTO this world ---
        # The deterministic fast-path leaves these blank; the casting skill
        # (builtin_skills/casting) fills them by reading world lore + the
        # existing cast. This is the CharacterPlacement adaptation surface.
        "placement": placement,
        # --- lossless capture of the whole authored soul ---
        # Orchestrator worlds have no souls/ folder, so the soul travels
        # inline here or it is gone. The world-agent reads game/npc/* and has
        # the complete character (incl. GM-only secrets).
        "soul": load_soul_full(soul_dir),
        # Provenance so a cast NPC is traceable back to its soul asset.
        "source_soul": {"sid": prof["sid"], "dir": prof["dir_name"]},
    }
    npc_path.parent.mkdir(parents=True, exist_ok=True)
    npc_path.write_text(
        json.dumps(npc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return npc_path


def player_start_location(game_dir: Path) -> str:
    """The player's current location as the NPC ``location`` field wants it
    (most specific node available). '' when unknown."""
    try:
        from neonrp.core.paths import get_data_dir_name

        rs_path = game_dir / get_data_dir_name(game_dir) / "meta" / "run_state.json"
        loc = json.loads(rs_path.read_text(encoding="utf-8")).get("location")
        if isinstance(loc, dict):
            return str(loc.get("subnode_id") or loc.get("node_id") or loc.get("id") or "")
        return str(loc or "")
    except Exception:
        return ""


def player_town_roster(game_dir: Path) -> tuple[Path | None, str]:
    """``(npcs.json of the player's town, player's subnode)`` for a town-
    structured world, ``(None, "")`` otherwise."""
    try:
        from neonrp.core.paths import get_data_dir_name

        data_dir = game_dir / get_data_dir_name(game_dir)
        loc = json.loads((data_dir / "meta" / "run_state.json").read_text(encoding="utf-8")).get("location")
        if not isinstance(loc, dict):
            return None, ""
        node_id = str(loc.get("node_id") or "")
        subnode = str(loc.get("subnode_id") or node_id or "")
        if not node_id:
            return None, ""
        npcs = data_dir / "towns" / node_id / "npcs.json"
        return (npcs, subnode) if npcs.is_file() else (None, "")
    except Exception:
        return None, ""


def ensure_read_first(game_dir: Path, target: Path) -> bool:
    """Idempotently list ``target`` in game-start.json ``startup.read_first``
    (game-dir-relative). Returns True when the file changed."""
    from neonrp.core.paths import get_data_dir_name

    gs_path = game_dir / get_data_dir_name(game_dir) / "meta" / "game-start.json"
    data = json.loads(gs_path.read_text(encoding="utf-8"))
    startup = data.get("startup")
    if not isinstance(startup, dict):
        return False
    read_first = startup.get("read_first")
    if not isinstance(read_first, list):
        return False
    rel = str(target.relative_to(game_dir))
    if rel in read_first:
        return False
    read_first.append(rel)
    startup["read_first"] = read_first
    data["startup"] = startup
    gs_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def seed_soul_location(game_dir: Path, soul_ref: "SoulRef", location: str | None) -> str:
    """Give a freshly cast multi-agent soul a well-defined spot (its
    ``run_state.json.location``): ``location`` if given, else wherever the
    player stands, so the roster lists it as present. Returns the scoped
    address written ('' when nothing is known)."""
    from neonrp.core.light_chat import _player_node
    from neonrp.core.place_nav import qualify_location, split_location

    player = _player_node(game_dir)
    cur_town, _ = split_location(player)
    target = qualify_location(game_dir, str(location or "").strip(), current_town=cur_town) if location else (player or "")
    sdir = game_dir / "souls" / f"{soul_ref.sid}-{soul_ref.instance_id}"
    path = sdir / "run_state.json"
    state = _read_json(path) if path.is_file() else {}
    state.setdefault("sid", soul_ref.sid)
    state.setdefault("instance_id", soul_ref.instance_id)
    state.setdefault("status", {"hp": 20, "max_hp": 20, "mood": "neutral"})
    state.setdefault("turn_count", 0)
    state["location"] = target or ""
    sdir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target or ""


def project_soul_into_town_npcs(
    town_npcs_path: Path,
    soul_dir: Path,
    *,
    location: str = "",
    npc_id: str | None = None,
    overwrite: bool = False,
    overrides: dict[str, Any] | None = None,
) -> str:
    """Append a soul as an NPC entry inside a town's ``npcs.json`` roster.

    The location-aware counterpart to :func:`project_soul_as_npc`. Town-
    structured orchestrator worlds (e.g. stoneford) store who-is-where in
    ``game/towns/<town>/npcs.json`` and the world-agent reads *that*; a soul
    flattened into the standalone ``game/npc/<id>.json`` is an orphan the
    agent never consults. This drops the cast character into the roster the
    agent actually reads, co-located at ``location`` (a subnode within the
    town) so it surfaces beside the player.

    The full soul bundle travels inline under ``soul`` (same lossless capture
    as ``project_soul_as_npc``) so voice/secrets survive. Returns the npc_id.

    ``overrides`` patches the placement block after projection (e.g.
    user-edited fields from the casting preview).
    """
    prof = _soul_profile(soul_dir)
    npc_id = npc_id or prof["sid"]
    data = _read_json(town_npcs_path)
    roster = data.get("npcs")
    if not isinstance(roster, list):
        roster = []
    idx = next(
        (i for i, n in enumerate(roster) if isinstance(n, dict) and n.get("id") == npc_id),
        None,
    )
    if idx is not None and not overwrite:
        raise PlacementError(
            f"NPC '{npc_id}' already in {town_npcs_path}. Pass overwrite=True / --force."
        )

    placement = {
        "role_in_world": "",
        "why_here": "",
        "relationship_to_player": "",
        "current_goal": "",
        "known_lore": [],
        "unknown_lore": [],
        "adapted": False,
    }
    if overrides:
        placement.update({k: v for k, v in overrides.items() if k in placement})
        placement["adapted"] = True

    entry = {
        "id": npc_id,
        "kind": "npc",
        "name": prof["name"],
        "role": "companion",  # brought in by the player, not a native townsfolk
        "tags": ["npc", "cast", *prof["tags"]],
        "summary": prof["summary"],
        "location": location,
        "traits": prof["traits"],
        "voice": prof["voice"],
        "state": {"met": False, "affection": 0, "mood": "neutral", "inner_state": ""},
        "placement": placement,
        # Lossless capture of the whole authored soul (charter/persona/secrets)
        # so the world-agent can voice the character faithfully.
        "soul": load_soul_full(soul_dir),
        "source_soul": {"sid": prof["sid"], "dir": prof["dir_name"]},
    }
    if idx is not None:
        roster[idx] = entry
    else:
        roster.append(entry)

    data.setdefault("town_id", town_npcs_path.parent.name)
    data["npcs"] = roster
    town_npcs_path.parent.mkdir(parents=True, exist_ok=True)
    town_npcs_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return npc_id


def project_avatar_orchestrator(game_dir: Path, soul_dir: Path) -> Path:
    """Project the player's avatar soul into ``game/player/profile.json``.

    Merges over any existing player profile so a world's authored player
    scaffold (class/origin/etc.) survives; the avatar supplies name +
    background/summary. Returns the path written.
    """
    prof = _soul_profile(soul_dir)
    player_path = game_dir / "game" / "player" / "profile.json"
    existing = _read_json(player_path)
    merged = {
        **existing,
        "name": prof["name"],
        "summary": prof["summary"] or existing.get("summary", ""),
        "source_soul": {"sid": prof["sid"], "dir": prof["dir_name"]},
    }
    player_path.parent.mkdir(parents=True, exist_ok=True)
    player_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return player_path


# ---------------------------------------------------------------------------
# Multi-agent projection — soul → souls/<sid>-<iid>/ + playthrough.json
# ---------------------------------------------------------------------------

def _mint_instance_id() -> str:
    return f"si-{uuid.uuid4().hex[:12]}"


def _copy_soul_instance(game_dir: Path, soul_dir: Path, sid: str, instance_id: str) -> Path:
    dest = game_dir / "souls" / f"{sid}-{instance_id}"
    if not dest.exists():
        shutil.copytree(soul_dir, dest)
    return dest


def project_soul_multiagent(
    game_dir: Path,
    soul_dir: Path,
    *,
    role: str = "npc",
    activate: bool = True,
    force: bool = False,
) -> SoulRef:
    """Cast a soul into a multi-agent world's ``playthrough.json``.

    Copies the soul into ``souls/<sid>-<iid>/``, appends a ``SoulRef`` to
    the playthrough, and (by default) adds it to ``active_souls``. Requires
    an existing ``playthrough.json`` — multi-agent worlds always ship one;
    building a fresh world↔soul binding from nothing is world-creation's job,
    not casting's. Returns the new ``SoulRef``.
    """
    pt = read_playthrough(game_dir)
    if pt is None:
        raise PlacementError(
            "multi-agent cast requires an existing playthrough.json; this "
            "world has none. Initialise the world↔soul binding first."
        )

    # NPC capacity (player-role souls don't count against the NPC limit).
    cap = world_npc_capacity(game_dir)
    if cap is not None and not force and role == "npc":
        npc_souls = sum(1 for s in pt.souls if (s.role or "npc") == "npc")
        if npc_souls >= cap:
            raise PlacementError(
                f"World is at NPC capacity ({cap}). Remove an NPC or pass "
                f"--force to override."
            )

    prof = _soul_profile(soul_dir)
    sid = prof["sid"]
    instance_id = _mint_instance_id()
    _copy_soul_instance(game_dir, soul_dir, sid, instance_id)

    soul_ref = SoulRef(
        sid=sid,
        instance_id=instance_id,
        version_hash=prof["version"] or "",
        head_commit="",
        role=role,
    )
    new_souls = list(pt.souls) + [soul_ref]
    new_active = pt.active_souls
    if activate:
        new_active = tuple(pt.active_souls) + (instance_id,)
    write_playthrough(game_dir, replace(pt, souls=new_souls, active_souls=new_active))
    return soul_ref


def project_avatar_multiagent(game_dir: Path, soul_dir: Path, *, name: str = "") -> PlayerRef:
    """Bind an avatar soul as the human player in a multi-agent playthrough.

    Adds a :class:`PlayerRef` (M20) pointing at the world's player state
    folder. Returns the new ``PlayerRef``.
    """
    pt = read_playthrough(game_dir)
    if pt is None:
        raise PlacementError(
            "multi-agent avatar projection requires an existing playthrough.json."
        )
    prof = _soul_profile(soul_dir)
    pid = "player"
    player_ref = PlayerRef(
        pid=pid,
        name=name or prof["name"],
        state_path="game/player",
        kind="human",
    )
    # Replace any existing same-pid player, else append.
    others = tuple(p for p in pt.players if p.pid != pid)
    write_playthrough(game_dir, replace(pt, players=others + (player_ref,)))
    return player_ref


# ---------------------------------------------------------------------------
# Provenance helper (for callers that want a one-line cast receipt)
# ---------------------------------------------------------------------------

def cast_receipt(mode: str, target: str, as_role: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"[{ts}] cast → mode={mode} as={as_role} → {target}"
