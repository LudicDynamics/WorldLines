from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import click


from neonrp.commands.init import init
from neonrp.commands.run import run
from neonrp.commands.save import save, load
from neonrp.commands.branch import branch, undo, redo
from neonrp.commands.validate import validate
from neonrp.commands.index import index
from neonrp.commands.find import find
from neonrp.commands.context import context
from neonrp.commands.agent import agent
from neonrp.commands.import_cmd import import_group
from neonrp.commands.game import game
from neonrp.commands.sandbox import sandbox_group
from neonrp.commands.replay import replay_group
from neonrp.commands.trace import trace_group
from neonrp.commands.mcp import mcp
from neonrp.commands.tui import tui
from neonrp.commands.play import play
from neonrp.commands.web import web
from neonrp.commands.serve import serve
from neonrp.commands.vault import vault
from neonrp.commands.self_update import self_update
from neonrp.commands.export_world import export_world, load_world
from neonrp.commands.world_hub import world_group
from neonrp.commands.soul_hub import soul_group
from neonrp.commands.commit import commit_group
from neonrp.commands.cast import cast
from neonrp.commands.mode import mode
from neonrp.commands.map_cmd import map_group
from neonrp.commands.schema_cmd import schema_group
from neonrp.commands.engine_cmd import engine_group
from neonrp.commands.template_cmd import template_group
from neonrp.commands.spec_cmd import spec_cmd


def _force_utf8_stdio() -> None:
    # Windows 管道/重定向下 stdout/stderr 默认本地代码页(cp1252/cp932),
    # 帮助文案或世界内容里任何非 ASCII 字符都会 UnicodeEncodeError 崩掉
    # 整条命令——桌面壳的能力探针(neonrp web --help)因此在 Windows 上
    # 误判引擎"不支持桌面模式"。统一 UTF-8,编不出的终端用替换字符兜底。
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8_stdio()


class _AppendPerEmitFileHandler(logging.Handler):
    """Append one log record per emit and close immediately.

    This avoids keeping long-lived file handles (notably on Windows) so
    `llm_raw.jsonl` can be inspected/rotated while TUI is running.
    """

    def __init__(self, filename: str | Path, encoding: str = "utf-8") -> None:
        super().__init__()
        target = Path(filename).resolve()
        # Keep FileHandler-compatible attribute name for existing tests/helpers.
        self.baseFilename = str(target)
        self._target_path = target
        self._encoding = encoding

    def emit(self, record: logging.LogRecord) -> None:
        try:
            rendered = self.format(record)
            with self._target_path.open("a", encoding=self._encoding, newline="\n") as f:
                f.write(rendered)
                f.write("\n")
        except Exception:
            self.handleError(record)


def _handler_target_path(handler: logging.Handler) -> str:
    base = getattr(handler, "baseFilename", "")
    if isinstance(base, str) and base:
        return str(Path(base).resolve())
    return ""


def _setup_logging(root: Path) -> None:
    """Configure project logging outputs.

    - Human-readable runtime log: ``.neonrp/logs/neonrp.log``
    - Raw LLM audit log (JSONL): ``.neonrp/logs/llm_raw.jsonl``
    """
    try:
        from neonrp.core.paths import get_neonrp_dir

        log_dir = get_neonrp_dir(root) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "neonrp.log"
        resolved_log = str(log_file.resolve())
        raw_file = log_dir / "llm_raw.jsonl"
        resolved_raw_log = str(raw_file.resolve())

        root_logger = logging.getLogger("neonrp")
        # Default to INFO for lower runtime noise. Opt into DEBUG explicitly.
        configured_level = str(os.getenv("NEONRP_LOG_LEVEL", "INFO")).upper().strip()
        level = getattr(logging, configured_level, logging.INFO)
        root_logger.setLevel(level)
        root_logger.propagate = False

        # Idempotent setup: avoid stacking duplicate file handlers when CLI is
        # invoked repeatedly in-process (e.g. TUI uses CliRunner.invoke()).
        has_main_handler = False
        for existing in root_logger.handlers:
            existing_path = _handler_target_path(existing)
            if existing_path and existing_path == resolved_log:
                has_main_handler = True
                break

        if not has_main_handler:
            handler = logging.FileHandler(resolved_log, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            )
            root_logger.addHandler(handler)

        # Dedicated raw JSONL logger for exact LLM request/response auditing.
        raw_logger = logging.getLogger("neonrp.raw_json")
        raw_logger.setLevel(logging.INFO)
        raw_logger.propagate = False
        has_raw_handler = False
        for existing in raw_logger.handlers:
            existing_path = _handler_target_path(existing)
            if existing_path and existing_path == resolved_raw_log:
                has_raw_handler = True
                break
        if not has_raw_handler:
            raw_handler = _AppendPerEmitFileHandler(resolved_raw_log, encoding="utf-8")
            raw_handler.setFormatter(logging.Formatter("%(message)s"))
            raw_logger.addHandler(raw_handler)
    except Exception:
        pass  # Logging is best-effort; don't crash CLI


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """NeonRP CLI entry point."""
    from neonrp.core.config import load_dotenv

    load_dotenv(Path.cwd())
    _setup_logging(Path.cwd())

    # One-shot, idempotent migration of any legacy flat games/ pile into the
    # world/run split (worlds/ library + plays/ runs). Best-effort: it logs and
    # never deletes, so a failure here must not block the CLI.
    try:
        from neonrp.worlds import migrate_legacy_games

        migrate_legacy_games()
    except Exception:
        logging.getLogger("neonrp").debug("legacy-game migration skipped", exc_info=True)

    # `neonrp` 裸 = TUI 世界选择器 launcher(挑世界→开局)。
    # 要直接在某 project 目录开引擎 TUI,用 `neonrp tui`(作用于当前目录)。
    if ctx.invoked_subcommand is None:
        # Same launch-time update banner the `worldlines` entry has — it only
        # ever ran there, so TUI users never saw a new engine.
        _launch_time_update_check()
        worldlines_tui()


cli.add_command(init)
cli.add_command(run)
cli.add_command(save)
cli.add_command(load)
cli.add_command(branch)
cli.add_command(undo)
cli.add_command(redo)
cli.add_command(validate)
cli.add_command(index)
cli.add_command(find)
cli.add_command(context)
cli.add_command(agent)
cli.add_command(import_group)
cli.add_command(game)
cli.add_command(sandbox_group)
cli.add_command(replay_group)
cli.add_command(trace_group)
cli.add_command(mcp)
cli.add_command(tui)
cli.add_command(play)
cli.add_command(web)
cli.add_command(serve)
cli.add_command(vault)
cli.add_command(self_update)
cli.add_command(export_world)
cli.add_command(load_world)
cli.add_command(world_group)
cli.add_command(soul_group)
cli.add_command(commit_group)
cli.add_command(cast)
cli.add_command(mode)
cli.add_command(map_group)
cli.add_command(schema_group)
cli.add_command(engine_group)
cli.add_command(template_group)
cli.add_command(spec_cmd)


# ---------------------------------------------------------------------------
# WorldLines CLI entry point
# ---------------------------------------------------------------------------


def _worldlines_prompt_choice(prompt: str, options: list[str], allow_back: bool = False) -> int | None:
    """Simple numbered choice prompt.

    Returns 0-based index into *options*, or None if user picks '返回'.
    When allow_back is True, '返回' is shown as the last numbered item.
    """
    click.echo()
    click.echo(prompt)
    click.echo()
    for i, opt in enumerate(options, 1):
        click.echo(f"  {i}. {opt}")
    back_num = len(options) + 1
    if allow_back:
        click.echo(f"  {back_num}. 返回")
    click.echo()

    while True:
        raw = click.prompt(">", type=str, default="1").strip()
        if not raw:
            continue
        try:
            choice = int(raw)
        except ValueError:
            click.echo("  请输入数字。")
            continue
        if allow_back and choice == back_num:
            return None
        if 1 <= choice <= len(options):
            return choice - 1
        click.echo(f"  请输入 1-{len(options) + (1 if allow_back else 0)}。")


def _launch_surface(root: Path, render_surface: str = "tui", **tui_kwargs: Any) -> None:
    """Render the session where the launcher chose: the terminal (run_tui)
    or the browser (`neonrp web` — play + watch every agent live). Web is
    only offered for play; build always passes 'tui'. Defaults to
    TUI so every existing caller is unchanged."""
    # Safety net for play: a created/authored/imported world can reach play
    # without a real init (no .neonrp/manifest.json → "NeonRP project not
    # initialized") or without its soul↔world binding (souls/ authored but no
    # playthrough.json — the agentic-builder path does exactly this). This is
    # the one funnel EVERY play launch passes through, so finalize the world
    # into a runnable multi-agent world here. Guarded so an already-initialized
    # world (built-ins, hub downloads, worlds finalized at creation) is a no-op.
    if tui_kwargs.get("mode", "play") == "play":
        try:
            from neonrp.core.paths import get_manifest_path

            souls_dir = root / "souls"
            has_souls = souls_dir.is_dir() and any(p.is_dir() for p in souls_dir.iterdir())
            has_pt = (root / ".neonrp" / "playthrough.json").is_file()
            if not get_manifest_path(root).is_file() or (has_souls and not has_pt):
                from neonrp.core.created_world import finalize_created_world
                from neonrp.worlds import read_local_world_name

                finalize_created_world(
                    root, world_name=read_local_world_name(root) or root.name
                )
        except Exception:
            logging.getLogger("neonrp").debug(
                "created-world finalize at launch skipped", exc_info=True
            )
    # Surface-mode worlds (Soul Talk) pick their execution mode + router from
    # the render surface: web → multi-agent (narrator), tui → orchestrator
    # (world-agent). No-op for every ordinary world (no surface_modes marker),
    # so their single baked mode is untouched on either surface.
    try:
        from neonrp.core.runtime_contract import apply_surface_execution_mode

        apply_surface_execution_mode(root, render_surface)
    except Exception:
        logging.getLogger("neonrp").debug(
            "apply_surface_execution_mode failed for %s", root, exc_info=True
        )
    if render_surface == "web":
        import webbrowser

        from neonrp.commands.web import make_server
        from neonrp.core.debug_flag import force_enable
        from neonrp.core.runtime_contract import get_startup_entry_agent

        force_enable()  # web lanes want /debug-grade trace, like `neonrp web`
        agent_id = get_startup_entry_agent(root) or "world-agent"
        # Forward the localized opening (the TUI run_tui branch consumes the
        # same startup_commands); web plays it once on first /start.
        server = make_server(
            root, agent_id, "127.0.0.1", 8787,
            startup_commands=tui_kwargs.get("startup_commands"),
        )
        bound_port = server.server_address[1]
        url = f"http://127.0.0.1:{bound_port}"
        if bound_port != 8787:
            click.echo(f"\n  (port 8787 was busy — using {bound_port})")
        click.echo(f"\n  ▸ WorldLines · web — open {url}\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            click.echo("\n  bye.")
        return
    from neonrp.tui.app import run_tui

    run_tui(root=root, **tui_kwargs)


def _worldlines_init_and_launch(
    world_id: str,
    preset_id: str,
    mode: str = "play",
    player_profile: dict[str, Any] | None = None,
    bring_in_souls: tuple[str, ...] = (),
    engine_mode: str = "orchestrator",
    npc_placements: dict[str, dict[str, Any]] | None = None,
    npc_locations: dict[str, str] | None = None,
    render_surface: str = "tui",
) -> None:
    """Initialize a new game directory and launch the TUI.

    Launch is world_id-driven (the world/run split):
    - OWNED world (created locally or hub-downloaded; ``get_world`` reports
      ``owned``): the run dir is a COPY of the library source via
      :func:`worlds.instantiate_run` — no packaged template, no template
      scaffold. We then apply the player profile + startup handoff and launch
      THAT run dir. The library source under WORLDS_HOME is never launched.
    - BUILT-IN world (manifest id): :func:`worlds.scaffold_builtin_run` (a fresh
      run under PLAYS_HOME from the packaged template, as the web's new game),
      then the same post-steps.
    """
    from neonrp.worlds import get_world
    from neonrp.presets import build_config_dict
    from neonrp.tui.i18n import resolve_locale

    world = get_world(world_id)

    # OWNED world: copy its library source into a fresh run and launch the run.
    # It carries no packaged template, so skip the whole template-scaffold path.
    if world.get("owned"):
        _worldlines_launch_owned_world(
            world_id,
            world,
            preset_id,
            mode=mode,
            player_profile=player_profile,
            bring_in_souls=bring_in_souls,
            engine_mode=engine_mode,
            npc_placements=npc_placements,
            npc_locations=npc_locations,
            render_surface=render_surface,
        )
        return

    # 1. A fresh run of the built-in world in PLAYS_HOME, in the player's UI
    #    language where the world ships one — the same scaffold the web's new
    #    game runs for a built-in (worlds.scaffold_builtin_run).
    from neonrp.core.paths import get_neonrp_dir
    from neonrp.core.storage import atomic_write_json
    from neonrp.worlds import scaffold_builtin_run

    click.echo(f"\n  Initializing {world['name']} ({world['name_local']})...")
    game_dir = scaffold_builtin_run(world_id, resolve_locale())

    # 2. cd into the game directory (NeonRP operates on cwd)
    import os
    os.chdir(game_dir)

    # The launcher's post-steps on the run:
    # 3. the preset the player picked (the scaffold seeded the default model)
    config_dict = build_config_dict(preset_id)
    _tag_worldlines_preset(config_dict, preset_id)
    atomic_write_json(get_neonrp_dir(game_dir) / "config.json", config_dict)

    # 4. the chosen player character
    if player_profile:
        _apply_player_profile(game_dir, player_profile)

    # 5. Casting ②: apply the chosen play mode to the world's
    # runtime_contract (orchestrator / multi-agent; the engine folds the old fast).
    try:
        from neonrp.core.runtime_contract import set_router_execution_mode

        set_router_execution_mode(game_dir, engine_mode)
    except Exception:
        logging.getLogger("neonrp").debug(
            "could not set engine_mode=%s", engine_mode, exc_info=True
        )

    # 6. Casting ②: cast the souls the player chose to bring into the world
    # as NPCs, via the shared placement machinery (same as `neonrp cast`).
    # Form depends on the world's mode (orchestrator → game/npc;
    # multi-agent → playthrough).
    if bring_in_souls:
        _cast_bring_in_souls(
            game_dir, bring_in_souls,
            placements=npc_placements, npc_locations=npc_locations,
        )

    click.echo("  Done.\n")

    # 7. Launch TUI — inject a localized "start the game" message so the
    # agent opens the scene in the user's language without them typing first.
    _setup_logging(game_dir)
    startup_commands = _build_startup_handoff(player_profile)
    _launch_surface(game_dir, render_surface, mode=mode, startup_commands=startup_commands)


def _worldlines_launch_owned_world(
    world_id: str,
    world: dict[str, Any],
    preset_id: str,
    mode: str = "play",
    player_profile: dict[str, Any] | None = None,
    bring_in_souls: tuple[str, ...] = (),
    engine_mode: str = "orchestrator",
    npc_placements: dict[str, dict[str, Any]] | None = None,
    npc_locations: dict[str, str] | None = None,
    render_surface: str = "tui",
) -> None:
    """Launch an OWNED world by instantiating a fresh run from its library source.

    Owned worlds (created locally or hub-downloaded) live under WORLDS_HOME as
    reusable SOURCES. Playing one copies the source into ``PLAYS_HOME/<id>-<ts>``
    via :func:`worlds.instantiate_run` and launches THAT run — placement, soul
    casting, play state, and the preset config all land on the run, never on the
    library source. No packaged template / template scaffold is involved; the
    world content was authored/downloaded into the source already.
    """
    from neonrp.worlds import instantiate_run
    from neonrp.presets import build_config_dict
    from neonrp.core.paths import get_neonrp_dir
    from neonrp.core.storage import atomic_write_json

    # 1. Copy the library source into a fresh run (the only dir we touch/launch).
    run_dir = instantiate_run(world_id)
    click.echo(f"\n  Initializing {world.get('name', world_id)}...")

    # 2. Write preset config onto the run.
    config_dict = build_config_dict(preset_id)
    _tag_worldlines_preset(config_dict, preset_id)
    atomic_write_json(get_neonrp_dir(run_dir) / "config.json", config_dict)

    # 3. Apply the chosen play mode to the run's runtime contract.
    try:
        from neonrp.core.runtime_contract import set_router_execution_mode

        set_router_execution_mode(run_dir, engine_mode)
    except Exception:
        logging.getLogger("neonrp").debug(
            "could not set engine_mode=%s on owned run", engine_mode, exc_info=True
        )

    # 4. Apply player profile if provided.
    if player_profile:
        _apply_player_profile(run_dir, player_profile)

    # 5. Cast any souls the player chose to bring in (placement on the RUN).
    if bring_in_souls:
        _cast_bring_in_souls(
            run_dir, bring_in_souls,
            placements=npc_placements, npc_locations=npc_locations,
        )

    # 6. Guarantee playability before the first turn (resolves router / writes
    #    the orchestrator contract / fixes game-start). Idempotent for a source
    #    that already ships a valid contract.
    try:
        from neonrp.core.runtime_contract import ensure_playable_world

        ensure_playable_world(run_dir)
    except Exception:
        pass

    click.echo("  Done.\n")

    # 7. Launch the RUN with the localized startup handoff.
    _setup_logging(run_dir)
    startup_commands = _build_startup_handoff(player_profile)
    _launch_surface(run_dir, render_surface, mode=mode, startup_commands=startup_commands)


def _tag_worldlines_preset(config_dict: dict[str, Any], preset_id: str) -> None:
    """Stamp the active WorldLines preset onto the game's config.json.

    We can't rely on `llm.model_ref` to recover this — custom user models
    use their own id. Store
    the preset id under `worldlines.last_preset_id` so the launcher's
    continue flow can pre-select it next time.
    """
    wl = config_dict.get("worldlines") if isinstance(config_dict.get("worldlines"), dict) else {}
    wl["last_preset_id"] = str(preset_id or "").strip()
    config_dict["worldlines"] = wl


def read_worldlines_last_preset(game_path: Path) -> str | None:
    """Read the last preset id used for this saved game, if recorded."""
    import json as _json

    cfg_path = game_path / ".neonrp" / "config.json"
    if not cfg_path.exists():
        return None
    try:
        data = _json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    wl = data.get("worldlines") if isinstance(data, dict) else None
    if not isinstance(wl, dict):
        return None
    preset_id = str(wl.get("last_preset_id", "") or "").strip()
    return preset_id or None


def _build_startup_handoff(
    player_profile: dict[str, Any] | None,
    *,
    world_intent: dict[str, Any] | None = None,
    locale: str | None = None,
) -> list[str]:
    """Return a list of localized opening messages for the TUI to inject.

    ``locale`` = the run's own language (a web / iOS run's output_lang); without it, the process / system locale.

    Order of concatenation in the single opening message:
    - world build/import handoff (when world_intent present)
    - character create/import handoff (when player_profile is a pending marker)
    - start-game prompt (always)
    """
    from neonrp.tui.i18n import get_message, resolve_locale

    locale = locale or resolve_locale()
    parts: list[str] = []

    if world_intent:
        action = world_intent.get("action")
        if action == "create":
            parts.append(
                get_message(locale, "handoff.world_create").format(
                    prompt=(world_intent.get("prompt") or "").strip()
                )
            )
        elif action == "import":
            parts.append(
                get_message(locale, "handoff.world_import").format(
                    path=(world_intent.get("source_path") or "").strip()
                )
            )

    if isinstance(player_profile, dict):
        if player_profile.get("__pending_ai__"):
            parts.append(
                get_message(locale, "handoff.character_create").format(
                    prompt=(player_profile.get("summary") or "").strip()
                )
            )
        elif player_profile.get("__pending_import__"):
            parts.append(
                get_message(locale, "handoff.character_import").format(
                    path=(player_profile.get("source_path") or "").strip()
                )
            )
        else:
            # Regular saved-profile or manual-entry persona: ask the agent to
            # translate it into the template's actual player schema (stats,
            # location, inventory, world-specific flags) since our 6-field
            # merge only covers universal persona fields.
            import json as _json

            persona_clean = {
                k: v for k, v in player_profile.items() if not k.startswith("__")
            }
            if persona_clean:
                parts.append(
                    get_message(locale, "handoff.character_adapt").format(
                        persona_json=_json.dumps(persona_clean, ensure_ascii=False, indent=2)
                    )
                )

    # End with the language-specific "start the game" cue — EXCEPT for a
    # world import. An import must be authored by the agent (via the
    # `tavern-game-import` skill) into a playable slice FIRST; appending
    # "Start the game" here makes the agent jump straight into narrating
    # play with the raw, un-authored card (the "导入卡直接进游戏" bug).
    # Play happens afterwards via the play_after_build relaunch, which
    # builds its own clean start handoff once the slice exists.
    is_world_import = bool(world_intent) and (
        world_intent.get("action") == "import"
    )
    if not is_world_import:
        parts.append(get_message(locale, "handoff.start_game"))

    # One single composite message — the agent sees a coherent brief.
    return ["\n\n".join(parts)]


def _apply_player_profile(game_dir: Path, profile: dict[str, Any]) -> None:
    """Merge player profile into the game's player.json after scaffolding.

    If the profile carries a `__pending_ai__` / `__pending_import__` marker
    set by the TUI launcher, write a handoff brief instead and let the
    relevant built-in skill (player-character-authoring /
    character-card-authoring) finish the authoring inside the running TUI.
    """
    import json
    from neonrp.players import merge_player_into_template
    from neonrp.core.paths import get_game_dir as _get_gd

    # Placement landing: when the player picked an existing soul as their
    # avatar (分身), project that soul into the world's player slot via the
    # shared placement machinery (game/player/profile.json), rather than a
    # generic key-merge. This is the same projection `neonrp cast --as player`
    # uses, so the launcher and the CLI stay one code path.
    soul_dir = profile.get("__soul_dir__")
    if soul_dir:
        try:
            from neonrp.core.placement import project_avatar_orchestrator

            project_avatar_orchestrator(game_dir, Path(str(soul_dir)))
            return
        except Exception:
            logging.getLogger("neonrp").debug(
                "avatar placement failed; falling back to merge", exc_info=True
            )

    if profile.get("__pending_ai__") or profile.get("__pending_import__"):
        brief_path = game_dir / ".neonrp" / "worldlines_character_intent.json"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return

    gd = _get_gd(game_dir)
    player_path = gd / "player" / "player.json"
    if not player_path.exists():
        # WorldLines templates store the player identity in profile.json
        # (the same file project_avatar_orchestrator writes); prefer it.
        # Fall back to a SORTED glob so the target is deterministic — an
        # arbitrary glob[0] could land on stats.json/wallet.json and leave
        # the real profile untouched.
        player_dir = gd / "player"
        profile_json = player_dir / "profile.json"
        if profile_json.exists():
            player_path = profile_json
        elif player_dir.exists():
            candidates = sorted(player_dir.glob("*.json"))
            if candidates:
                player_path = candidates[0]

    if player_path.exists():
        template_player = json.loads(player_path.read_text(encoding="utf-8"))
        merged = merge_player_into_template(template_player, profile)
        player_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def _cast_bring_in_souls(
    game_dir: Path,
    soul_dirs: tuple[str, ...],
    *,
    placements: dict[str, dict[str, Any]] | None = None,
    npc_locations: dict[str, str] | None = None,
) -> None:
    """Cast bring-in souls into the world as NPCs (the casting ② result).

    Mode-aware via the shared placement machinery: orchestrator → game/npc;
    multi-agent → playthrough. Best-effort per soul.

    ``placements`` — per-soul-path overrides for the placement block
    (role_in_world / why_here / relationship_to_player / current_goal),
    sourced from user edits in the casting preview.

    ``npc_locations`` — per-soul-path location overrides (user-picked
    starting location), e.g. ``{"<soul_dir>": "T002"}``.
    """
    try:
        from neonrp.core.placement import (
            project_soul_as_npc,
            project_soul_into_town_npcs,
            project_soul_multiagent,
        )
        from neonrp.core.runtime_contract import (
            get_router_execution_mode,
        )
    except Exception:
        return

    mode = get_router_execution_mode(game_dir)
    # Co-locate cast NPCs at the player's start so the world-agent actually
    # places them in the opening scene. For town-structured worlds the active
    # roster the world-agent reads is game/towns/<town>/npcs.json — writing to
    # the standalone game/npc/<id>.json there is an orphan the agent never
    # consults (the bug that made casting feel like it didn't take). Drop the
    # NPC into the player's town roster, co-located at their subnode.
    log = logging.getLogger("neonrp")
    town_npcs, subnode = _player_town_npcs(game_dir)
    start_loc = _player_start_location(game_dir)
    _pl = placements or {}
    _lo = npc_locations or {}
    for sd in soul_dirs:
        overrides = _pl.get(sd)
        loc = _lo.get(sd)
        try:
            if mode == "multi-agent":
                project_soul_multiagent(game_dir, Path(sd), role="npc", force=True)
            elif town_npcs is not None:
                project_soul_into_town_npcs(
                    town_npcs, Path(sd),
                    location=loc or subnode, overwrite=True, overrides=overrides,
                )
            else:
                project_soul_as_npc(
                    game_dir, Path(sd),
                    location=loc or start_loc, overwrite=True, overrides=overrides,
                )
        except Exception:
            log.debug("bring-in cast failed: %s", sd, exc_info=True)

    # The opening turn reads startup.read_first, which lists town.json but not
    # npcs.json — so a freshly-cast companion wouldn't be in the first scene.
    # Add the town roster to read_first so she's beside the player from turn 1.
    if town_npcs is not None and mode != "multi-agent":
        try:
            _ensure_read_first(game_dir, town_npcs)
        except Exception:
            log.debug("could not add %s to startup.read_first", town_npcs, exc_info=True)


def _player_town_npcs(game_dir: Path) -> tuple[Path | None, str]:
    from neonrp.core.placement import player_town_roster

    return player_town_roster(game_dir)


def _ensure_read_first(game_dir: Path, target: Path) -> None:
    from neonrp.core.placement import ensure_read_first

    ensure_read_first(game_dir, target)


def _player_start_location(game_dir: Path) -> str:
    from neonrp.core.placement import player_start_location

    return player_start_location(game_dir)


def _worldlines_select_player(preset_id: str) -> dict[str, Any] | None:
    """Prompt user to select, create, or edit a player profile.

    Returns the chosen profile dict, or None to skip (use template default).
    """
    from neonrp.players import (
        list_players,
        prompt_create_player,
        prompt_edit_player,
        prompt_ai_create_player,
    )

    players = list_players()

    if not players:
        idx = _worldlines_prompt_choice(
            "  角色：",
            ["用一句话创建角色（AI 生成）", "手动填写创建", "跳过（使用默认角色）"],
            allow_back=True,
        )
        if idx is None:
            return None
        if idx == 0:
            return prompt_ai_create_player(preset_id)
        if idx == 1:
            return prompt_create_player()
        return None  # skip

    # Show existing profiles + create/skip options
    options = [f"{p['name']}  {p['summary'][:30] if p['summary'] else ''}" for p in players]
    options.append("用一句话创建角色（AI 生成）")
    options.append("手动填写创建")
    options.append("跳过（使用默认角色）")

    idx = _worldlines_prompt_choice("  选择角色：", options, allow_back=True)
    if idx is None:
        return None

    if idx < len(players):
        # Selected existing — offer to use or edit
        selected = players[idx]
        click.echo(f"\n  角色: {selected['name']}")
        if selected.get("summary"):
            click.echo(f"  简介: {selected['summary']}")

        action_idx = _worldlines_prompt_choice(
            "  操作：", ["使用此角色", "编辑后使用"], allow_back=True
        )
        if action_idx is None:
            return _worldlines_select_player(preset_id)  # re-select
        if action_idx == 0:
            return selected["data"]
        return prompt_edit_player(selected["data"])

    # Extra options after saved profiles
    extra_start = len(players)
    if idx == extra_start:
        return prompt_ai_create_player(preset_id)
    if idx == extra_start + 1:
        return prompt_create_player()

    return None  # skip


def _worldlines_launch_existing_dir(
    game_path: Path,
    preset_id: str,
    player_profile: dict[str, Any] | None = None,
    render_surface: str = "tui",
) -> bool:
    """Launch an already-extracted but never-started game directory.

    Used for fresh WorldHub downloads and freshly loaded zips — the
    directory exists on disk but the engine hasn't run a turn yet, so
    we go through the *new-game* startup path (injecting the localized
    "开始游戏" handoff) rather than the continue path. That makes the
    world-agent read `game-start.json` and play the opening scene on
    first turn, instead of leaving the user staring at an empty TUI.

    Compared with `_worldlines_init_and_launch`:
    - No `create_game_dir(world_id)` (the dir is already there)
    - No template scaffold (already extracted)
    - Still applies `player_profile`, still writes preset config,
      still builds the startup handoff.
    """
    from neonrp.presets import build_config_dict
    from neonrp.core.paths import get_neonrp_dir
    from neonrp.core.storage import atomic_write_json

    config_dict = build_config_dict(preset_id)
    _tag_worldlines_preset(config_dict, preset_id)
    config_path = get_neonrp_dir(game_path) / "config.json"
    atomic_write_json(config_path, config_dict)

    if player_profile:
        _apply_player_profile(game_path, player_profile)

    # Guarantee playability before the first turn. An imported/authored world
    # extracted here may lack a conventional world-agent + runtime contract
    # (→ "Agent 'world-agent' not found"); ensure_playable_world resolves the
    # router, writes the orchestrator contract, and fixes game-start's
    # entry_agent. Idempotent — a no-op for built-in worlds that already ship a
    # valid contract pointing at an agent on disk.
    try:
        from neonrp.core.runtime_contract import ensure_playable_world
        ensure_playable_world(game_path)
    except Exception:
        pass

    _setup_logging(game_path)
    startup_commands = _build_startup_handoff(player_profile)
    _launch_surface(game_path, render_surface, mode="play", startup_commands=startup_commands)
    return True


def _worldlines_continue_game_with_preset(
    game_path: Path,
    preset_id: str,
    render_surface: str = "tui",
    *,
    runtime_mode: str | None = None,
    startup_commands: list[str] | None = None,
) -> bool:
    """Continue an existing game using a preselected preset.

    ``runtime_mode="build"`` opens the directory in the workshop instead
    (the dashboard's 创作世界 / 创作角色 land here with a fresh blank world
    and the agent's first words in ``startup_commands``)."""
    from neonrp.presets import build_config_dict
    from neonrp.core.paths import get_neonrp_dir
    from neonrp.core.storage import atomic_write_json

    mode = "build" if runtime_mode == "build" else "play"

    # 计划-分批导入的恢复钩(core/import_plan.py):这个目录里躺着一份有
    # pending 批次的转换计划时,继续 = 接着转换,不是接着玩 —— play 模式
    # 写受限,批次落不了盘,所以切 build 并把续跑指令作为开场消息注入
    # (它就是用户本来要打的那句话,不新增 LLM 调用)。
    resume_import_cmd: str | None = None
    try:
        from neonrp.core.import_plan import resume_startup_command

        resume_import_cmd = resume_startup_command(game_path)
    except Exception:
        resume_import_cmd = None
    if resume_import_cmd:
        mode = "build"

    config_dict = build_config_dict(preset_id)
    _tag_worldlines_preset(config_dict, preset_id)
    config_path = get_neonrp_dir(game_path) / "config.json"
    atomic_write_json(config_path, config_dict)

    import os

    os.chdir(game_path)
    _setup_logging(game_path)

    from neonrp.core.config import load_dotenv

    load_dotenv(game_path)

    # `continue_session=True`: restore the local session.
    commands: list[str] = list(startup_commands or [])
    if resume_import_cmd:
        commands.insert(0, resume_import_cmd)
    _launch_surface(
        game_path,
        render_surface,
        continue_session=True,
        mode=mode,
        startup_commands=commands or None,
    )
    return True


def _worldlines_continue_game(game_path: Path) -> bool:
    """Continue an existing game. Prompts for model selection.

    Returns False if user backs out (don't launch).
    """
    from neonrp.presets import list_presets, ensure_preset_key

    presets = list_presets()
    preset_options = [p["display"] for p in presets]
    preset_idx = _worldlines_prompt_choice(
        "  \u2699\uFE0F  选择模型：", preset_options, allow_back=True
    )
    if preset_idx is None:
        return False

    selected_preset = presets[preset_idx]

    if not ensure_preset_key(selected_preset["id"]):
        return False

    return _worldlines_continue_game_with_preset(game_path, selected_preset["id"])


def _launch_time_update_check() -> None:
    """Check for a newer release and offer the user to upgrade.

    Best-effort: any error is silently swallowed so a bad network never
    blocks launch. Honors `updates.check_on_launch` and `last_skipped_version`.
    """
    try:
        from neonrp.core import updater
        from neonrp.tui.i18n import get_message, resolve_locale

        locale = resolve_locale()

        settings = updater.get_update_settings()
        if not settings.get("enabled", True) or not settings.get("check_on_launch", True):
            return
        result = updater.check_for_update_cached()
        if not result.update_available or not result.latest_version:
            return
        if settings.get("last_skipped_version") == result.latest_version:
            return
        click.echo()
        click.echo(
            "  "
            + get_message(locale, "update.launch_banner").format(
                current=result.current_version,
                latest=result.latest_version,
                channel=result.channel,
                package=getattr(result, "package", "neonrp"),
            )
        )
        if result.release_notes_url:
            click.echo(
                "    "
                + get_message(locale, "update.launch_release_notes").format(url=result.release_notes_url)
            )
        if not result.install_mode.allow_auto_apply:
            click.echo("    " + get_message(locale, "update.launch_editable_blocked"))
            return
        mode = updater.launch_mode(settings)
        if mode == "notify":
            return
        if mode == "auto":  # 10-24: it should just update — one line, then the new version takes over
            click.echo("    " + get_message(locale, "update.launch_auto"))
            choice = "y"
        else:
            choice = click.prompt(
                "    " + get_message(locale, "update.launch_choice_prompt"),
                default="n",
                show_default=False,
            ).strip().lower()
        if choice in ("y", "yes"):
            ok, output = updater.apply_update_in_background()
            if output:
                click.echo(output)
            if ok:
                click.echo("  " + get_message(locale, "upgrade.success"))
                # Re-exec into the freshly-installed version so the user lands
                # on the new code automatically (this process still holds the
                # old modules in memory). Only continues past here if exec
                # fails — then we tell them to restart.
                click.echo("  " + get_message(locale, "update.relaunching"))
                updater.relaunch_self()
                click.echo("  " + get_message(locale, "update.restart_hint"))
                raise SystemExit(0)
            # Upgrade did NOT happen. Do not silently drop into the old
            # version — tell the user the exact manual command.
            click.echo("  " + get_message(locale, "update.launch_failed"))
            click.echo("  " + get_message(locale, "update.manual_hint"))
        elif choice in ("s", "skip"):
            updater.mark_version_skipped(result.latest_version)
            click.echo(
                "  "
                + get_message(locale, "update.launch_skipped").format(version=result.latest_version)
            )
    except SystemExit:
        raise
    except Exception:
        return


@click.group(invoke_without_command=True)
@click.option("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1).")
@click.option("--port", default=8787, type=int, help="Port (default 8787).")
@click.option("--no-browser", is_flag=True, help="Don't auto-open a browser window.")
@click.pass_context
def worldlines_cli(ctx: click.Context, host: str, port: int, no_browser: bool) -> None:
    """WorldLines — the player's entry point. With no command it opens the web UI in your browser.

    \b
        worldlines          # web UI (http://127.0.0.1:8787/local)
        worldlines web      # the same, explicitly
        # terminal UI: `neonrp` (see neonrp --help)

    The web UI and the terminal UI share the same library, saves and
    settings (`~/.worldlines`), so you can switch between them at any time.
    """
    # host / port / no_browser 传给 web 子命令(bare 现默认开 web)。
    from neonrp.core.paths import ensure_template_store

    ensure_template_store()  # 10-08: the player's own templates live in ~/.worldlines/templates
    _launch_time_update_check()
    if ctx.invoked_subcommand is not None:
        return
    ctx.invoke(worldlines_web, host=host, port=port, no_browser=no_browser)


@worldlines_cli.command("web")
@click.option("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1).")
@click.option("--port", default=8787, type=int, help="Port (default 8787).")
@click.option("--no-browser", is_flag=True, help="Don't auto-open a browser window.")
@click.pass_context
def worldlines_web(ctx: click.Context, host: str, port: int, no_browser: bool) -> None:
    """The web UI (http://127.0.0.1:8787/local): your library, play, create and watch, in the browser.

    It runs a local web server on your machine (default port 8787) and
    opens it in your browser.
    """
    from neonrp.commands.web import web as _web_cmd

    ctx.invoke(
        _web_cmd,
        project=None,
        host=host,
        port=port,
        parent_pid=None,
        no_browser=no_browser,
    )


def worldlines_tui() -> None:
    """TUI 世界选择器 launcher(由 `neonrp` 裸命令调用)。

    (`worldlines tui` 已退役 2026-09-01:worldlines=Web launcher / neonrp=TUI launcher。)"""
    from neonrp.presets import ensure_preset_key
    from neonrp.tui.app import run_worldlines_launcher

    selection = run_worldlines_launcher()
    if selection is None:
        return

    if not ensure_preset_key(selection.preset_id):
        return

    if selection.mode == "continue":
        if selection.game_path is None:
            return
        _worldlines_continue_game_with_preset(
            selection.game_path,
            selection.preset_id,
            selection.render_surface,
            runtime_mode=selection.runtime_mode,
            startup_commands=list(selection.startup_commands),
        )
        return

    if selection.mode == "launch_existing":
        # Fresh hub-download / loaded-zip: dir exists, never been started.
        # Go through new-game startup path so the "开始游戏" handoff is injected.
        if selection.game_path is None:
            return
        _worldlines_launch_existing_dir(
            selection.game_path,
            selection.preset_id,
            player_profile=selection.player_profile,
            render_surface=selection.render_surface,
        )
        return

    if selection.world_id in ("__wl_create__", "__wl_import__") and selection.world_intent:
        _worldlines_init_custom_world(
            selection.world_intent,
            selection.preset_id,
            mode=selection.runtime_mode,
            player_profile=selection.player_profile,
            render_surface=selection.render_surface,
            play_after_build=selection.play_after_build,
        )
        return

    # M16: soul-authoring path — mirror of the world custom-create path above.
    # When the user picks "create new character", the launcher may set
    # world_id = "__wl_create__" with a soul_intent instead of a world_intent.
    if selection.soul_intent:
        _worldlines_init_custom_world(
            selection.soul_intent,
            selection.preset_id,
            mode=selection.runtime_mode,
            player_profile=selection.player_profile,
        )
        return

    if not selection.world_id:
        # The TUI has already exited by now, so a silent return drops the user
        # to a blank shell with no clue why (this is exactly what the character-
        # import path hit when it forgot to set a world). Surface it.
        click.echo(
            "  Nothing to launch — the launch selection carried no world. "
            "This is a launcher bug; please report it with this line:\n"
            f"  selection: mode={selection.mode} runtime={selection.runtime_mode} "
            f"preset={selection.preset_id} game_path={selection.game_path} "
            f"world_intent={'yes' if selection.world_intent else 'no'} "
            f"soul_intent={'yes' if selection.soul_intent else 'no'} "
            f"surface={selection.render_surface}"
        )
        return
    _worldlines_init_and_launch(
        selection.world_id,
        selection.preset_id,
        mode=selection.runtime_mode,
        player_profile=selection.player_profile,
        bring_in_souls=selection.bring_in_souls,
        engine_mode=selection.engine_mode,
        npc_placements=selection.npc_placements,
        npc_locations=selection.npc_locations,
        render_surface=selection.render_surface,
    )


def _worldlines_init_custom_world(
    intent: dict[str, Any],
    preset_id: str,
    *,
    mode: str,
    player_profile: dict[str, Any] | None,
    render_surface: str = "tui",
    play_after_build: bool = False,
) -> None:
    """Create a fresh game directory and delegate world creation to a skill.

    The launcher has already captured the user's intent (create vs. import,
    plus a natural-language prompt or source path). We scaffold a minimal
    game directory, seed a starter message pointing at the relevant built-in
    skill, and hand off to the TUI runtime so the active agent picks up the
    thread with `world-game-authoring` or `tavern-game-import`.
    """
    from datetime import datetime
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_manifest_path, get_neonrp_dir
    from neonrp.core.storage import atomic_write_json
    from neonrp.presets import build_config_dict
    from neonrp.worlds import GAME_HOME

    action = intent.get("action") or "create"
    skill_name = intent.get("skill") or "world-game-authoring"
    slug = "custom-create" if action == "create" else "custom-import"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    game_dir = GAME_HOME / f"{slug}-{timestamp}"
    game_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"\n  Preparing {action} workspace at {game_dir}...")

    import os
    os.chdir(game_dir)

    from neonrp.core.storage import ensure_dirs
    ensure_dirs(game_dir)
    atomic_write_json(get_manifest_path(game_dir), Manifest().model_dump())

    config_dict = build_config_dict(preset_id)
    _tag_worldlines_preset(config_dict, preset_id)
    atomic_write_json(get_neonrp_dir(game_dir) / "config.json", config_dict)

    # Seed the runtime scaffold with the "default" template so the TUI has
    # working narrator/router agents to hand the intent to. The skill itself
    # will write the real world content from the prompt/source.
    from neonrp.commands.game import create_rule_samples, create_skill_samples
    from neonrp.core.paths import get_data_dir_name
    from neonrp.core.template_assets import (
        copy_agent_from_template,
        copy_runtime_contract_from_template,
        list_template_agent_ids,
    )

    template_name = "default"
    data_dir_name = get_data_dir_name(game_dir)
    for agent_id in list_template_agent_ids(template_name):
        copy_agent_from_template(
            game_dir,
            template_name=template_name,
            agent_id=agent_id,
            data_dir_name=data_dir_name,
            force=True,
        )
    copy_runtime_contract_from_template(
        game_dir,
        template_name=template_name,
        data_dir_name=data_dir_name,
        force=True,
    )
    create_rule_samples(game_dir)
    create_skill_samples(game_dir)

    # 源卡持久化(计划-分批协议的前置,core/import_plan.py):把卡原样拷进
    # game/import/source.<ext>,handoff 指向仓内副本 —— 转换从此不依赖外部
    # 路径(/tmp 卡片消失、换机、中断恢复都不再断链)。顺带算一个体量信号,
    # 大卡向用户推荐分批(仅推荐,不擅自切换协议)。
    src_raw = str(intent.get("source_path") or "").strip()
    if action == "import" and src_raw:
        try:
            from neonrp.core.import_plan import estimate_source, persist_source_card

            persisted = persist_source_card(game_dir, src_raw)
            intent = {**intent, "source_path": str(persisted.relative_to(game_dir))}
            est = estimate_source(persisted)
            if est.get("recommend_plan"):
                click.echo(
                    "  提示:源卡较大"
                    f"({est['bytes'] // 1024}KB"
                    + (f",{est['entries']} 条设定" if est.get("entries") else "")
                    + ")。可让 agent 使用【计划-分批协议】:先制定 game/import/plan.json,再分批转换,可中断续跑。"
                )
        except Exception:
            pass  # 拷不进去就保留外部路径,行为同旧版

    # Write the handoff brief the TUI will pick up as an opening instruction.
    brief_path = game_dir / ".neonrp" / "worldlines_intent.json"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    brief_path.write_text(
        _json.dumps(
            {
                "action": action,
                "skill": skill_name,
                "prompt": intent.get("prompt", ""),
                "source_path": intent.get("source_path", ""),
                "player_profile": player_profile,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Build localized handoff from the user's chosen ui.language. The same
    # helper composes world_intent + (optional) character intent + the
    # start-game cue into one message the agent sees on turn 1.
    startup_commands = _build_startup_handoff(player_profile, world_intent=intent)

    click.echo("  Done.\n")
    click.echo("  Handoff brief:")
    for line in (startup_commands[0] if startup_commands else "").splitlines():
        click.echo(f"    {line}")
    click.echo()

    _setup_logging(game_dir)
    from neonrp.tui.app import run_tui

    run_tui(root=game_dir, mode=mode, startup_commands=startup_commands)

    # C+A: an import that chose "play" authored the world in the build session
    # above; once it exits, relaunch the now-materialised world in play mode
    # (terminal or browser per the launcher choice). Only when the world is
    # actually playable — a startup/active-agent file means the slice got built.
    if play_after_build:
        from neonrp.core.runtime_contract import (
            ensure_playable_world,
            get_startup_entry_agent,
        )

        try:
            playable = (game_dir / ".neonrp").is_dir() and (
                get_startup_entry_agent(game_dir) is not None
                or (game_dir / "agents").is_dir()
            )
        except Exception:
            playable = (game_dir / ".neonrp").is_dir()
        if playable:
            # The skill authored game/** + agents/** but does not reliably
            # produce a conventional world-agent + runtime contract, so play
            # would error "Agent 'world-agent' not found". Guarantee a resolved
            # router agent + orchestrator contract + game-start entry_agent now
            # (idempotent — a no-op for an already-playable world).
            try:
                ensure_playable_world(game_dir)
            except Exception:
                pass

            # The authored dir is now a world SOURCE. Register it into the
            # library (worlds/<id>) so it appears alongside built-ins /
            # downloads, then play a FRESH RUN copied from that source — keeping
            # the library source pristine while play state lands on the run.
            play_dir = game_dir
            try:
                from neonrp.worlds import (
                    instantiate_run,
                    read_local_world_name,
                    register_owned_world,
                    _slugify_world,
                )

                world_name = read_local_world_name(game_dir) or game_dir.name
                world_id = _slugify_world(world_name) or _slugify_world(game_dir.name)
                register_owned_world(game_dir, world_id)
                play_dir = instantiate_run(world_id)
            except Exception:
                logging.getLogger("neonrp").debug(
                    "could not register/instantiate authored world; "
                    "playing the authored dir directly",
                    exc_info=True,
                )
                play_dir = game_dir

            click.echo("\n  ▸ World ready — starting play…\n")
            startup = _build_startup_handoff(player_profile)
            # _launch_surface's finalize_created_world safety net runs on the
            # run dir, keeping it playable as a multi-agent world.
            _launch_surface(play_dir, render_surface, mode="play", startup_commands=startup)


if __name__ == "__main__":
    cli()
