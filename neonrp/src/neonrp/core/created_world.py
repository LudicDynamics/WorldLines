"""Finalize an LLM-authored world into a runnable, multi-agent NeonRP world.

The creation engine authors `game/` + `agents/world-agent/` (and usually flat
`game/npc/<id>.json` NPCs). That bundle is NOT a runnable project: it has no
real `.neonrp/` init (so the engine reports "NeonRP project not initialized")
and no souls / `playthrough.json` (so it can only run as a single-agent
orchestrator, never multi-agent).

`finalize_created_world` closes both gaps with pure code, after the bundle is
written to disk:

1. **Init** — `ensure_dirs` + a real `Manifest` at `.neonrp/manifest.json`
   (plus a config if none) so the project is actually initialized.
2. **Souls** — every authored character becomes a soul folder under
   `souls/<sid>-<iid>/` (reusing already-authored `souls/` if present, else
   converting `game/npc/*.json`).
3. **Binding** — a schema-2 `.neonrp/playthrough.json` registers the world,
   its agent team, the player, and the souls.
4. **Mode** — the runtime contract is set to `multi-agent`.

Everything is best-effort and tolerant: a sparse NPC still yields a valid
soul, and a world with no characters still inits cleanly (it just has no
cast).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", str(name or "").lower().strip())
    s = re.sub(r"[-\s]+", "-", s)
    return s.strip("-") or "world"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _npc_text(npc: dict[str, Any]) -> str:
    """Assemble prose persona for an NPC from whatever fields it carries."""
    parts: list[str] = []
    for key in (
        "description", "persona", "summary", "background", "personality",
        "appearance", "role", "voice", "goal", "current_goal",
        "relationship_to_player",
    ):
        v = npc.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(f"**{key}**: {v.strip()}")
        elif isinstance(v, list) and v:
            parts.append(f"**{key}**: " + ", ".join(str(x) for x in v))
    return "\n\n".join(parts)


def _write_soul_folder(
    soul_dir: Path, *, sid: str, name: str, name_local: str, body: str,
    location: str,
) -> None:
    """Write the minimal-but-valid soul folder (soul.json + soul.md + state)."""
    soul_dir.mkdir(parents=True, exist_ok=True)
    instance_id = soul_dir.name.split("-", 1)[1] if "-" in soul_dir.name else f"si-{sid}0001"
    if not (soul_dir / "soul.json").is_file():
        (soul_dir / "soul.json").write_text(json.dumps({
            "schema_version": 1,
            "sid": sid,
            "name": name,
            "name_local": name_local,
            "version": "1.0",
            "source": {"kind": "created", "version": "1.0"},
            "tags": ["npc", "created"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    if not (soul_dir / "soul.md").is_file():
        (soul_dir / "soul.md").write_text(
            f"# {name_local or name}\n\n{body or name}\n", encoding="utf-8"
        )
    # run_state always rewritten so location is well-defined. Empty location
    # means "kept with the player" (scene router), the safe default for a
    # freshly-created world with no authored town map.
    (soul_dir / "run_state.json").write_text(json.dumps({
        "sid": sid,
        "instance_id": instance_id,
        "location": location,
        "status": {"hp": 20, "max_hp": 20, "mood": "neutral"},
        "turn_count": 0,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _collect_souls(dest: Path, *, start_location: str) -> list[tuple[str, str]]:
    """Ensure every character is a soul folder. Returns [(sid, instance_id)].

    Prefers already-authored ``souls/<sid>-<iid>/`` folders; otherwise converts
    ``game/npc/*.json`` (the orchestrator-style flat NPCs the authoring LLM
    most often emits) into soul folders.
    """
    souls_root = dest / "souls"
    out: list[tuple[str, str]] = []
    used_sids: set[str] = set()

    def _uniq(sid: str) -> str:
        sid = _slug(sid)
        base, n = sid, 2
        while sid in used_sids:
            sid, n = f"{base}{n}", n + 1
        used_sids.add(sid)
        return sid

    # 1) Already-authored soul folders (LLM may emit these directly).
    if souls_root.is_dir():
        for d in sorted(p for p in souls_root.iterdir() if p.is_dir()):
            sj = _read_json(d / "soul.json")
            sid = _uniq(sj.get("sid") or d.name.split("-", 1)[0])
            iid = d.name.split("-", 1)[1] if "-" in d.name else f"si-{sid}0001"
            _write_soul_folder(
                d, sid=sid, name=sj.get("name") or sid,
                name_local=sj.get("name_local") or "",
                body="", location=start_location,
            )
            out.append((sid, iid))

    if out:
        return out

    # 2) Convert flat NPCs → souls.
    npc_dir = dest / "game" / "npc"
    if npc_dir.is_dir():
        for f in sorted(npc_dir.glob("*.json")):
            npc = _read_json(f)
            name = str(npc.get("name") or npc.get("name_local") or f.stem)
            sid = _uniq(npc.get("id") or name)
            iid = f"si-{sid}0001"
            _write_soul_folder(
                souls_root / f"{sid}-{iid}",
                sid=sid, name=name,
                name_local=str(npc.get("name_local") or ""),
                body=_npc_text(npc), location=start_location,
            )
            out.append((sid, iid))
    return out


def _seed_player_profile(dest: Path, world_name: str) -> None:
    """Write a default protagonist profile if the world has none.

    A created world otherwise has no player identity (only an empty
    ``game/player/`` folder), so the world-agent improvises and asks "who are
    you?" instead of narrating the player into the scene. We seed an
    open-identity traveller — present as a real entity in the docs, but
    deliberately undefined so the player (or the story) can shape it.
    """
    player_dir = dest / "game" / "player"
    player_dir.mkdir(parents=True, exist_ok=True)
    profile = player_dir / "profile.json"
    if profile.is_file():
        return
    wn = world_name or "这个世界"
    profile.write_text(json.dumps({
        "name": "旅人",
        "name_local": "旅人",
        "class": "旅行者",
        "origin": "未知",
        "background": f"刚来到{wn}的旅人，身份尚未确定。",
        "summary": f"一个刚抵达{wn}的人，身手与来历都还是谜——身份要靠你在故事里找回或定义。",
        "source_lang": "zh",
        "intro_i18n": {
            "en": f"A traveller who has just arrived in {wn}. Skills, past, and "
                  "name are all undefined — your identity is yours to discover "
                  "or decide as the story unfolds.",
            "zh": f"一个刚抵达{wn}的旅人。身手、来历与名字都未确定——身份要靠你在故事里找回或定义。",
            "ja": f"{wn}にたどり着いたばかりの旅人。腕も過去も名も未定——己の身元は、物語の中で見つけるか定めるかだ。",
            "ko": f"막 {wn}에 도착한 여행자. 솜씨도 과거도 이름도 정해지지 않았다——정체는 이야기 속에서 찾거나 정의하는 것은 당신의 몫이다.",
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _team_agents(dest: Path) -> list[Any]:
    """Build the world-agent team roster from the authored ``agents/`` dirs."""
    from neonrp.core.playthrough import TeamAgent

    agents_dir = dest / "agents"
    roster: list[Any] = []
    if agents_dir.is_dir():
        for d in sorted(p for p in agents_dir.iterdir() if p.is_dir()):
            aid = d.name
            if aid == "world-agent":
                roster.append(TeamAgent(id=aid, role="orchestrator", singleton=True))
            else:
                roster.append(TeamAgent(id=aid, role="functional-sub-agent", singleton=False))
    # The orchestrator must exist even if the LLM forgot to author it.
    if not any(a.id == "world-agent" for a in roster):
        roster.insert(0, TeamAgent(id="world-agent", role="orchestrator", singleton=True))
    return roster


def finalize_created_world(
    dest: Path, *, world_name: str = "", opening_location: str = "",
) -> dict[str, Any]:
    """Turn a freshly-written created-world bundle into a runnable multi-agent
    world (init + souls + playthrough + mode). Idempotent and best-effort.

    Returns a small report: ``{"initialized", "souls", "mode"}``.
    """
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_manifest_path, get_neonrp_dir
    from neonrp.core.playthrough import (
        Playthrough, PlayerRef, SoulRef, WorldAgentTeam, WorldRef,
        write_playthrough,
    )
    from neonrp.core.storage import atomic_write_json, ensure_dirs

    report = {"initialized": False, "souls": 0, "mode": "orchestrator"}
    slug = _slug(world_name or dest.name)

    # 1) Real init — this is what fixes "NeonRP project not initialized".
    ensure_dirs(dest)
    manifest_path = get_manifest_path(dest)
    if not manifest_path.is_file():
        atomic_write_json(manifest_path, Manifest().model_dump())
    report["initialized"] = manifest_path.is_file()

    # config — only if the launch flow hasn't written one (don't clobber a
    # provider the user already chose for this game).
    cfg_path = get_neonrp_dir(dest) / "config.json"
    if not cfg_path.is_file():
        try:
            from neonrp.presets import build_config_dict, list_presets
            presets = list_presets()
            if presets:
                atomic_write_json(cfg_path, build_config_dict(presets[0]["id"]))
        except Exception:
            logger.debug("created-world config seed skipped", exc_info=True)

    # player state folder + a default protagonist identity (else the
    # world-agent has no player to narrate and asks "who are you?").
    _seed_player_profile(dest, world_name or slug)

    # 2) Souls — convert authored characters into soul folders.
    souls = _collect_souls(dest, start_location=opening_location or "")
    report["souls"] = len(souls)

    # No cast → leave it a plain (orchestrator) world. Being initialized is
    # enough; don't fabricate an empty multi-agent binding or flip the mode.
    if not souls:
        return report

    # 3) Binding — the schema-2 playthrough.json.
    version_hash = re.sub(r"[^a-z0-9]", "", slug)[:24] or "created"
    soul_refs = [
        SoulRef(sid=sid, instance_id=iid, version_hash=version_hash,
                head_commit="", role="npc")
        for sid, iid in souls
    ]
    pt = Playthrough(
        schema_version=2,
        playthrough_id=f"pt-{slug}-001",
        world=WorldRef(
            wid=slug,
            instance_id=f"wi-{version_hash}0001",
            version_hash=version_hash,
            head_commit="seed-world-0001",
        ),
        world_agent_team=WorldAgentTeam(
            seeded_from="game/agents/manifest.json",
            agents=_team_agents(dest),
        ),
        souls=soul_refs,
        created_at="1970-01-01T00:00:00Z",
        players=(PlayerRef(pid="player", name="Player", state_path="game/player"),),
        # Every soul live from turn 1; the scene router re-derives the active
        # subset per turn from locations.
        active_souls=tuple(iid for _sid, iid in souls),
    )
    write_playthrough(dest, pt)

    # 4) Mode — multi-agent (souls each run as their own agent).
    try:
        from neonrp.core.runtime_contract import set_router_execution_mode
        set_router_execution_mode(dest, "multi-agent")
        report["mode"] = "multi-agent"
    except Exception:
        logger.debug("could not set multi-agent mode", exc_info=True)

    return report
