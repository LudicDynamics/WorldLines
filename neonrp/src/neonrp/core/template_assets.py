"""Reusable project template asset helpers.

These helpers back both ``neonrp game new`` and build-mode authoring tools
that need to copy packaged runtime assets into a project.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from neonrp.core.active_agent import write_active_agent
from neonrp.core.paths import get_data_dir_name
from neonrp.core.runtime_contract import get_runtime_contract_path, load_runtime_contract

TEMPLATE_PACKAGE = "neonrp.templates"
TEMPLATE_TOKEN_DATA_DIR = "{{DATA_DIR}}"
DEFAULT_TEMPLATE_NAME = "default"


def list_available_templates() -> list[str]:
    templates_root = resources.files(TEMPLATE_PACKAGE)
    with resources.as_file(templates_root) as root_path:
        return sorted(p.name for p in root_path.iterdir() if p.is_dir() and not p.name.startswith("_"))


def adapt_template_data(value: object, data_dir_name: str) -> object:
    if isinstance(value, dict):
        return {k: adapt_template_data(v, data_dir_name) for k, v in value.items()}
    if isinstance(value, list):
        return [adapt_template_data(v, data_dir_name) for v in value]
    if isinstance(value, str):
        replaced = value.replace(TEMPLATE_TOKEN_DATA_DIR, data_dir_name)
        # Backward-compat with legacy template literals that used "game/" directly.
        if replaced.startswith("game/"):
            return f"{data_dir_name}/{replaced[len('game/'):]}"
        return replaced
    return value


def adapt_template_text(text: str, data_dir_name: str) -> str:
    return text.replace(TEMPLATE_TOKEN_DATA_DIR, data_dir_name)


def load_game_template(name: str, data_dir_name: str = "game") -> list[tuple[str, dict[str, Any]]]:
    game_root = resources.files(TEMPLATE_PACKAGE).joinpath(name).joinpath("game")
    if not game_root.is_dir():
        raise KeyError(name)

    entities: list[tuple[str, dict[str, Any]]] = []
    with resources.as_file(game_root) as game_root_path:
        for path in sorted(game_root_path.rglob("*.json"), key=lambda p: p.as_posix()):
            rel_path = path.relative_to(game_root_path).as_posix()
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"Template entity must be JSON object: {name}/game/{rel_path}")
            entities.append((rel_path, adapt_template_data(payload, data_dir_name)))
    return entities


def list_template_agent_ids(name: str) -> list[str]:
    agents_root = resources.files(TEMPLATE_PACKAGE).joinpath(name).joinpath("agents")
    if not agents_root.is_dir():
        return []
    with resources.as_file(agents_root) as agents_root_path:
        return sorted(
            child.name
            for child in agents_root_path.iterdir()
            if child.is_dir() and (child / "agent.json").exists()
        )


def _iter_template_agent_files(template_name: str, agent_id: str) -> list[Path]:
    template_agent_root = resources.files(TEMPLATE_PACKAGE).joinpath(template_name).joinpath("agents").joinpath(agent_id)
    if not template_agent_root.is_dir():
        raise FileNotFoundError(f"Template '{template_name}' missing agent '{agent_id}'")
    with resources.as_file(template_agent_root) as src_root:
        return sorted((p for p in src_root.rglob("*") if p.is_file()), key=lambda p: p.as_posix())


def copy_game_support_files_from_template(
    root: Path,
    *,
    template_name: str,
    data_dir_name: str,
    force: bool,
) -> list[str]:
    """Copy non-JSON files from template ``game/`` into the project data dir."""
    game_root = resources.files(TEMPLATE_PACKAGE).joinpath(template_name).joinpath("game")
    if not game_root.is_dir():
        raise KeyError(template_name)

    created_paths: list[str] = []
    with resources.as_file(game_root) as src_root:
        for src_file in sorted((p for p in src_root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
            if src_file.suffix.lower() == ".json":
                continue
            rel = src_file.relative_to(src_root)
            dest = root / data_dir_name / rel
            if dest.exists() and not force:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                text = src_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copyfile(src_file, dest)
            else:
                dest.write_text(adapt_template_text(text, data_dir_name), encoding="utf-8")
            created_paths.append((Path(data_dir_name) / rel).as_posix())
    return created_paths


def list_playable_scaffold_targets(
    root: Path,
    *,
    template_name: str = DEFAULT_TEMPLATE_NAME,
    data_dir_name: str | None = None,
) -> list[str]:
    """Return relative paths that a playable scaffold may touch."""
    data_dir_name = data_dir_name or get_data_dir_name(root)
    runtime_contract = load_runtime_contract(root)
    targets: list[str] = [runtime_contract.active_agent_relpath, ".neonrp/runtime_contract.json"]
    for agent_id in list_template_agent_ids(template_name):
        for src_file in _iter_template_agent_files(template_name, agent_id):
            rel = src_file.relative_to(src_file.parents[1])
            targets.append((Path("agents") / rel).as_posix())
    deduped: list[str] = []
    for path in targets:
        normalized = adapt_template_text(path, data_dir_name).replace("\\", "/")
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def copy_runtime_contract_from_template(
    root: Path,
    *,
    template_name: str,
    data_dir_name: str,
    force: bool,
) -> list[str]:
    # Templates used to nest runtime_contract.json inside their own `.neonrp/`
    # directory. That made the packaged wheel ship what looked like a saved
    # game-state dir — plus `.gitignore` excluded the whole `.neonrp/` tree
    # by default. Now the contract lives at the template root as plain
    # config, and scaffolding writes it into the target game's `.neonrp/`
    # on first run. Kept the legacy path lookup as a fallback so external
    # / user-provided templates that still use the old layout keep working.
    template_root = resources.files(TEMPLATE_PACKAGE).joinpath(template_name)
    template_path = template_root.joinpath("runtime_contract.json")
    if not template_path.is_file():
        template_path = template_root.joinpath(".neonrp").joinpath("runtime_contract.json")
    if not template_path.is_file():
        return []

    dest_path = get_runtime_contract_path(root)
    if dest_path.exists() and not force:
        return []

    with resources.as_file(template_path) as src_path:
        payload = json.loads(src_path.read_text(encoding="utf-8"))
    adapted = adapt_template_data(payload, data_dir_name)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(adapted, indent=2, ensure_ascii=False), encoding="utf-8")
    return [".neonrp/runtime_contract.json"]


def copy_souls_and_playthrough_from_template(
    root: Path,
    *,
    template_name: str,
    force: bool,
) -> list[str]:
    """Scaffold a soul-world template's cast.

    A soul world (e.g. kagura-island) ships a ``souls/`` tree (full M16
    soul folders) and a ``playthrough.json`` (the world↔soul-team
    binding the multi-agent runtime reads). Templates without these
    (stoneford-orch, default) → no-op, so this is safe to call
    unconditionally in the scaffold sequence. ``souls/`` is copied
    verbatim (authored content, not data-dir relative);
    ``playthrough.json`` lands in the game's ``.neonrp/`` where
    ``read_playthrough`` looks, like the runtime contract.
    """
    template_root = resources.files(TEMPLATE_PACKAGE).joinpath(template_name)
    written: list[str] = []
    with resources.as_file(template_root) as troot:
        troot = Path(troot)

        src_souls = troot / "souls"
        if src_souls.is_dir():
            dest_souls = root / "souls"
            if not dest_souls.exists() or force:
                shutil.copytree(src_souls, dest_souls, dirs_exist_ok=True)
                written.append("souls/")

        src_pt = troot / "playthrough.json"
        if src_pt.is_file():
            dest_pt = root / ".neonrp" / "playthrough.json"
            if not dest_pt.exists() or force:
                dest_pt.parent.mkdir(parents=True, exist_ok=True)
                dest_pt.write_text(
                    src_pt.read_text(encoding="utf-8"), encoding="utf-8"
                )
                written.append(".neonrp/playthrough.json")

        # World art: the template's root assets/ (cover / key art) travels
        # into the game so the web runtime's /image?kind=world can serve it.
        # Soul portraits ride along inside souls/ above. No-op when absent.
        src_assets = troot / "assets"
        if src_assets.is_dir():
            dest_assets = root / "assets"
            if not dest_assets.exists() or force:
                shutil.copytree(src_assets, dest_assets, dirs_exist_ok=True)
                written.append("assets/")

    return written


def copy_agent_from_template(
    root: Path,
    *,
    template_name: str,
    agent_id: str,
    data_dir_name: str,
    force: bool,
) -> list[str]:
    template_agent_root = resources.files(TEMPLATE_PACKAGE).joinpath(template_name).joinpath("agents").joinpath(agent_id)
    if not template_agent_root.is_dir():
        raise FileNotFoundError(f"Template '{template_name}' missing agent '{agent_id}'")

    dest_root = root / "agents" / agent_id
    if dest_root.exists() and not force:
        return []

    created_paths: list[str] = []
    with resources.as_file(template_agent_root) as src_root:
        for src_file in sorted((p for p in src_root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
            rel = src_file.relative_to(src_root)
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src_file.suffix.lower() == ".json":
                payload = json.loads(src_file.read_text(encoding="utf-8"))
                adapted = adapt_template_data(payload, data_dir_name)
                dest.write_text(json.dumps(adapted, indent=2, ensure_ascii=False), encoding="utf-8")
            else:
                text = src_file.read_text(encoding="utf-8")
                dest.write_text(adapt_template_text(text, data_dir_name), encoding="utf-8")
            created_paths.append((Path("agents") / agent_id / rel).as_posix())
    return created_paths


@dataclass(frozen=True)
class PlayableScaffoldResult:
    files: list[str]
    created_agent_ids: list[str]
    active_agent: str
    active_agent_path: str


def ensure_playable_runtime_scaffold(
    root: Path,
    *,
    template_name: str = DEFAULT_TEMPLATE_NAME,
    force: bool = False,
    active_agent_id: str | None = None,
    reason: str = "play scaffold initialized",
    exit_condition: str = "",
    updated_by: str = "",
) -> PlayableScaffoldResult:
    """Ensure project runtime scaffold exists for play mode.

    This copies packaged play agents/runtime metadata when missing and rewrites
    the active-agent state using the canonical protocol so play mode can start.
    """
    data_dir_name = get_data_dir_name(root)
    files: list[str] = []
    created_agent_ids: list[str] = []

    for agent_id in list_template_agent_ids(template_name):
        agent_json_path = root / "agents" / agent_id / "agent.json"
        system_path = root / "agents" / agent_id / "system.md"
        needs_copy = force or not agent_json_path.exists() or (agent_id == "narrator" and not system_path.exists())
        if not needs_copy:
            continue
        copied = copy_agent_from_template(
            root,
            template_name=template_name,
            agent_id=agent_id,
            data_dir_name=data_dir_name,
            force=True,
        )
        if copied:
            files.extend(copied)
            created_agent_ids.append(agent_id)

    files.extend(
        copy_runtime_contract_from_template(
            root,
            template_name=template_name,
            data_dir_name=data_dir_name,
            force=force,
        )
    )

    router_agent_id = load_runtime_contract(root).router.agent_id
    desired_agent_id = (active_agent_id or router_agent_id or "narrator").strip() or "narrator"
    agent_json_path = root / "agents" / desired_agent_id / "agent.json"
    if not agent_json_path.exists():
        raise ValueError(
            f"Cannot set active_agent to '{desired_agent_id}': missing agent scaffold at {agent_json_path.as_posix()}"
        )

    state_path = write_active_agent(
        root,
        desired_agent_id,
        reason=reason,
        exit_condition=exit_condition,
        updated_by=updated_by or desired_agent_id,
    )
    state_relpath = state_path.relative_to(root).as_posix()
    if state_relpath not in files:
        files.append(state_relpath)

    return PlayableScaffoldResult(
        files=files,
        created_agent_ids=created_agent_ids,
        active_agent=desired_agent_id,
        active_agent_path=state_relpath,
    )
