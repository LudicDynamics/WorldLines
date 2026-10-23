"""System prompt templates for conversation modes (M9-T4)."""

from __future__ import annotations

from typing import Literal


ConversationMode = Literal["build", "sandbox", "play"]


def build_system_prompt(
    agent_name: str,
    project_name: str,
    branch: str,
    mode: ConversationMode,
    skill_descriptions: list[str] | None = None,
    project_root: str | None = None,
    include_resolve_action: bool = True,
    is_sub_agent: bool = False,
    data_dir_name: str = "game",
    routing_state_path: str | None = None,
    startup_path: str | None = None,
    location_source_entity_id: str = "player",
    location_source_field: str = "location",
    output_lang: str = "zh",
) -> str:
    """Build a mode-aware system prompt.

    ``output_lang``(语言隔离):本局输出语({zh,en,ja}),作为
    world/keeper 面向玩家文本的**权威**语言,压过 authored 世界文件的创作语言。
    """
    if mode not in {"build", "sandbox", "play"}:
        raise ValueError(f"Unsupported mode: {mode}")

    skill_descriptions = skill_descriptions or []
    routing_state_path = routing_state_path or f"{data_dir_name}/meta/active-agent.json"
    startup_path = startup_path or f"{data_dir_name}/meta/game-start.json"
    skills_section = _format_skills(skill_descriptions)
    skill_names = _extract_skill_names(skill_descriptions)
    mode_section = _mode_rules(
        mode,
        skill_names,
        is_sub_agent=is_sub_agent,
        routing_state_path=routing_state_path,
        output_lang=output_lang,
    )
    from neonrp.core.souls import is_soul_workshop as _is_soul_workshop

    tools_section = _tools_for_mode(
        mode,
        soul_workshop=_is_soul_workshop(project_root),
        include_resolve_action=include_resolve_action,
        routing_state_path=routing_state_path,
        startup_path=startup_path,
        location_source_entity_id=location_source_entity_id,
        location_source_field=location_source_field,
    )

    root_section = f"- Project Root: {project_root}\n" if project_root else ""

    return f"""You are {agent_name}, the active AI agent for NeonRP.

## Project Context
- Project: {project_name}
- Branch: {branch}
- Working Style: Codex CLI
{root_section}- Path Convention: Use project-root relative paths by default (e.g., `index.html`, `src/app.ts`).
- Mode: {mode}

## Operating Rules
{mode_section}

## Available Tools
{tools_section}

## Entity Format
- Entities are JSON files in `{data_dir_name}/<kind>/<id>.json`.
- Required fields: `id`, `kind`, `name`.
- Optional fields: `tags`, `summary`, and kind-specific gameplay fields.

## Skill Catalog
{skills_section}

Prioritize clear narrative output for the user while keeping game files consistent.
"""


def _extract_skill_names(skill_descriptions: list[str]) -> set[str]:
    names: set[str] = set()
    for line in skill_descriptions:
        if not isinstance(line, str):
            continue
        name, sep, _ = line.partition(":")
        value = name.strip() if sep else line.strip()
        if value:
            names.add(value)
    return names


# 输出语显示名(强制语言指令用;与 core/output_lang.PROMPT_LANGS 对齐)。
_OUTPUT_LANG_NAMES = {"zh": "中文 (Chinese)", "en": "English", "ja": "日本語 (Japanese)", "ko": "한국어 (Korean)"}


def _mode_rules(
    mode: ConversationMode,
    available_skill_names: set[str] | None = None,
    *,
    is_sub_agent: bool = False,
    routing_state_path: str,
    output_lang: str = "zh",
) -> str:
    available_skill_names = available_skill_names or set()
    # 语言隔离:本局输出语是**权威**的,压过世界文件/角色卡/
    # 记忆/agent 指令的创作语言。此前只有软性"跟随玩家消息语言",导致日语进
    # 中文世界时,world-agent 仍照 authored 中文产出中文叙事。
    lang_name = _OUTPUT_LANG_NAMES.get(output_lang, _OUTPUT_LANG_NAMES["zh"])
    common_lines = [
        f"- **Output language: {lang_name}.** Write ALL player-facing text — narration, "
        f"dialogue, tool narration, reasoning summaries, and every `ask_user` question and "
        f"option — in {lang_name}. This is the world's selected output language; honor it "
        f"even when world files, character sheets, memories, or agent instructions are "
        f"written in another language, and do NOT switch languages to match those source "
        f"materials. Only override if the user explicitly asks for a different language.",
    ]
    common_lines.append(
        (
            "- **MANDATORY ask_user**: When the user faces a meaningful choice with 2+ valid options, "
            "you MUST call `ask_user({questions: [{question, header, options: [{label, description}], multiSelect}]})` "
            "and WAIT for their answer. The user can always type a custom response via 'Other'. "
            "NEVER silently pick an option for the user. Examples: choosing a destination, "
            "selecting a combat action, spending resources, picking a dialogue branch, or any decision "
            "that affects game outcome. When in doubt, ask."
        )
    )
    if mode == "sandbox":
        mode_lines = [
            "- Use tools to inspect game state and decide changes.",
            "- Complete the turn by calling `submit_proposal`.",
            "- Do not rely on direct game-data writes in this mode.",
            "- You can still delegate with `task(agent_id, prompt, resume_run_id?)` when specialized help is useful.",
        ]
        if is_sub_agent:
            mode_lines.append("- You are running as a delegated sub-agent; complete the assigned task and return results to caller.")
        return "\n".join(common_lines + mode_lines)
    if mode == "play":
        mode_lines = [
            "- Act as a game master: keep immersion, consequences, and pacing.",
            "- You may directly read/write/edit files when tools allow.",
            "- Keep output player-facing and narrative-first.",
            (
                "- NEVER narrate your own process or tool use. Do every "
                "read/lookup/tool call SILENTLY. Your reply must contain ONLY "
                "in-fiction content (narration, dialogue, scene) — never "
                "commentary about how you produced it. The VERY FIRST "
                "character of your reply must already be in-fiction. Do NOT "
                "emit any preamble before a '---' separator describing what "
                "you are about to do, then the 'real' story after it — there "
                "is no 'before', only the story. Forbidden openers (any "
                "language), e.g.: 'let me read/look at…', 'I'll now check…', "
                "'let me generate the narrative', '让我先读取…', '让我看看…', "
                "'让我读取灵魂卡', '现在让我生成叙事', '玩家角色还没有被创建'. "
                "If you need data, fetch it via tools without announcing it; "
                "the player sees only the story."
            ),
            "- You can delegate subtasks with `task(agent_id, prompt, resume_run_id?)`.",
            f"- Routing state (`{routing_state_path}`) is router-owned. Do NOT modify it unless your role and permissions explicitly allow routing-state writes.",
            (
                "- The world may grow under the story: when it walks into a place that "
                "does not exist yet, call `new_location(name, summary, connections, parent)` "
                "(silently) so the map knows it, and `update_location(id, ...)` as you learn "
                "more about a place. Never invent a place only in prose."
            ),
            (
                "- Other characters' folders under `souls/` are theirs, not yours: do not glob "
                "or read them (the result is empty by design). Who is here and where comes "
                "from `get_location(entity)`, the roster (`.neonrp/playthrough.json`) and "
                "`list_entities` — use those."
            ),
        ]
        if is_sub_agent:
            mode_lines.append("- You are running as a delegated sub-agent; focus on the assigned scope and avoid unrelated exploration.")
        return "\n".join(common_lines + mode_lines)
    lines = [
        *common_lines,
        "- Behave like Claude Code for general coding tasks.",
        "- You may directly read/write/edit files across the project.",
        "- Use project-root relative paths by default; absolute paths are optional.",
        "- NEVER use placeholder tokens like `<project-root>` or `/workspace/project` in tool paths.",
    ]
    if "entity-authoring" in available_skill_names:
        lines.append(
            "- When creating/updating game entities, call `Skill(skill=\"entity-authoring\")` to load schema/rules-aware workflow."
        )
    else:
        lines.append("- When creating/updating game entities, load a schema/rules authoring skill if available.")

    lines.extend(
        [
            "- Build mode can create sub-agents: add `agents/<agent_id>/agent.json` and `agents/<agent_id>/system.md`.",
            "- After creating/updating an agent, delegate via `task(agent_id, prompt, resume_run_id?)`.",
            f"- Only the router agent should update `{routing_state_path}` before rerouting; specialist agents should not edit it.",
        ]
    )
    if "sub-agent-orchestration" in available_skill_names:
        lines.append("- If you need the detailed workflow, call `Skill(skill=\"sub-agent-orchestration\")`.")
    else:
        lines.append("- If available, load a sub-agent orchestration skill for detailed workflow.")
    if is_sub_agent:
        lines.append("- You are running as a delegated sub-agent; complete the specific assignment and avoid broad repository discovery.")
    lines.append("- End naturally after finishing the requested work.")
    return "\n".join(lines)


def _tools_for_mode(
    mode: ConversationMode,
    include_resolve_action: bool = True,
    *,
    routing_state_path: str,
    startup_path: str,
    location_source_entity_id: str,
    location_source_field: str,
    soul_workshop: bool = False,
) -> str:
    common = [
        "`read_file(path, max_chars?)` — read file contents (MUST call before write/edit, absolute path preferred)",
        "`read_context(query, limit?)` — semantic search for game knowledge",
        "`find(query, kind?, tag?)` — find a specific entity by id/keyword",
        "`list_entities(kind?, tag?)` — discover existing entities",
        "`ask_user({questions: [{question, header, options: [{label, description}], multiSelect}]})` — pause and ask the user a question",
        "`Skill(skill)` — load a local skill by name for specialized workflow guidance",
        "`task(agent_id, prompt, resume_run_id?)` — delegate work to a sub-agent",
    ]
    if include_resolve_action:
        common.insert(
            4,
            "`resolve_action(action, actor, ...)` — compute game mechanics (read-only, does NOT write files)",
        )
    if mode == "sandbox":
        tools = common + [
            "`submit_proposal(...)` — apply changes to game/ files (the ONLY way to modify game state)",
        ]
    else:
        tools = common + [
            "`write_file(path, content)` — create/overwrite files (absolute path preferred)",
            "`edit_file(path, old_text, new_text)` — surgically edit files (preferred for small changes)",
            "`delete_file(path)` — delete a single file (cannot delete directories)",
            "`import_sillytavern_card(path, entity_id?, target_path?, name?)` — import a Tavern PNG/JSON card into `game/`",
            "`ensure_playable_scaffold(template_name?, active_agent?, force?)` — copy missing play agents/runtime scaffold and normalize `active-agent.json`",
            "`glob(pattern, path?)` — find files by name pattern",
            "`grep(pattern, path?, glob?, max_results?)` — search inside files by regex",
        ]

    tool_list = "\n".join(f"- {tool}" for tool in tools)
    rules = _tool_usage_rules(
        mode,
        include_resolve_action=include_resolve_action,
        routing_state_path=routing_state_path,
        startup_path=startup_path,
        location_source_entity_id=location_source_entity_id,
        location_source_field=location_source_field,
        soul_workshop=soul_workshop,
    )
    return f"""{tool_list}

### Tool Usage Rules
{rules}"""


def _tool_usage_rules(
    mode: ConversationMode,
    include_resolve_action: bool = True,
    *,
    routing_state_path: str,
    startup_path: str,
    location_source_entity_id: str,
    location_source_field: str,
    soul_workshop: bool = False,
) -> str:
    """Return mode-specific tool usage rules for the system prompt."""
    common_rules = [
        "**Read before write**: ALWAYS call `read_file` before `write_file`, `edit_file`, or `delete_file` on the same path to understand existing content.",
        (
            "**Game-start protocol**: If the user intent is to start/begin/continue the game "
            "(e.g., 'start game', 'begin adventure', '开始游戏', '开始冒险'), first call "
            f"`read_file('{startup_path}')`. If it exists, follow its startup instructions "
            "(especially any `startup.read_first` list) before doing anything else. "
            f"If it is missing, locate the configured bootstrap entity with `find(query='{location_source_entity_id}')` "
            "and read its canonical path before any broad search."
        ),
        (
            "**No blind startup search**: Before reading startup entry files, do NOT call "
            "`read_context`, `find`, `list_entities`, `glob`, or `grep` just to explore."
        ),
        (
            "**Gather context after bootstrap**: After startup files are loaded (or for non-start turns), "
            "use `read_context`, `find`, `list_entities`, and `read_file` to understand current state."
        ),
        "**Language lock**: Follow the **Output language** rule above for ALL natural-language output; do not switch to match the language of world files, character sheets, or source materials, unless the user explicitly requests a switch.",
        "**NEVER assume user choices**: When multiple valid options exist, you MUST call `ask_user` with structured questions. Each option needs a short label and description. Do NOT pick for the user or narrate a choice they didn't make. If you catch yourself writing 'I will choose X' or 'Let's go with X', STOP and call `ask_user` instead.",
    ]
    if include_resolve_action:
        common_rules.append(
            "**resolve_action is read-only**: It computes outcome values but writes nothing — you must apply changes separately."
        )
        common_rules.extend(
        [
            (
            "**Routing gate before task()**: Before delegating with `task(...)`, first confirm routing state by reading "
            f"`{routing_state_path}` and the configured location-source entity (`find(query='{location_source_entity_id}')`, "
            f"then inspect its `{location_source_field}` field). If the domain has changed, update the routing state first, "
            f"then delegate. This update is router-only; non-router specialists must not write `{routing_state_path}`."
            ),
            (
                "**Binary Tavern cards**: For SillyTavern `.png` or raw card `.json` sources, use "
                "`import_sillytavern_card(...)` instead of `read_file` on the source card."
            ),
            (
                "**Playable scaffold**: After generating a new game slice from Tavern/world content, call "
                "`ensure_playable_scaffold(...)` before claiming the project is ready to play. "
                "Do NOT hand-write `agents/` scaffolds or invent a custom `active-agent.json` shape."
            ),
            (
                "**No path guessing for read_file**: Do NOT invent file paths from entity IDs. "
                "When path is uncertain, use `find`/`list_entities`/`glob` to confirm first, then call `read_file`."
            ),
            (
                "**No repeated dead-end probing**: If `read_file` returns `File not found`, avoid trying many path variants. "
                "Switch to discovery (`find`/`list_entities`/`glob`) or proceed with confirmed context."
            ),
            "**Path style**: Prefer project-root relative paths (`index.html`, `src/main.py`). Do NOT use placeholder prefixes like `<project-root>` or `/workspace/project`.",
            "**Sub-agent calls**: Use `task(agent_id, prompt, resume_run_id?)` with a complete, self-contained prompt because sub-agents cannot see your full parent conversation.",
            "**Skill calls**: Use `Skill(skill)` when the user mentions a skill or when you need specialized procedures.",
        ]
    )
    if mode == "sandbox":
        specific_rules = [
            "**One proposal per turn**: Bundle all `game/` changes into a single `submit_proposal` call with multiple ops.",
            "**No direct file writes**: In sandbox mode, all changes go through `submit_proposal`. Direct `write_file`/`edit_file`/`delete_file` are not available.",
        ]
    else:
        specific_rules = [
            "**Prefer edit over write**: For small changes to existing files, use `edit_file` (safer, preserves surrounding content). Use `write_file` only for new files or full rewrites.",
            "**Direct write workflow**: In build mode, `write_file`/`edit_file`/`delete_file` can modify project files directly.",
        ]
        if mode == "build":
            specific_rules.append(
                "**Showing your work (M31)**: This surface renders text, so when the "
                "thing worth looking at is visual — a map canvas, generated art, a long "
                "document, the run folder as an Obsidian vault — call "
                "`open_in_viewer(path, reason)` instead of describing it. Only for "
                "something you just changed, and say why."
            )
            if soul_workshop:
                specific_rules.append(
                    "**Character workshop**: this project IS one character's folder — "
                    "`soul.json` sits at the root and there is no world here. Author the "
                    "character in place: call `Skill('soul-authoring')` for the layout, then "
                    "write `soul.json`, `persona/`, `background/`, `character/`, `rules/` with "
                    "`write_file` (project-relative paths, no `.neonrp/soul-drafts/`). Put the "
                    "portrait at `assets/portrait.png`. Do NOT call `cast_soul` — there is no "
                    "roster; the character lives in the library and is cast into worlds later."
                )
            if not soul_workshop:
                specific_rules.append(
                "**Creating a character (M31)**: When asked to add/create a character, "
                "you build it yourself — do not send the user elsewhere. Call "
                "`Skill('soul-authoring')` for the folder contract, write the files under "
                "`.neonrp/soul-drafts/<sid>/` with `write_file`, then call "
                "`cast_soul(sid)` to put it in the world. `cast_soul` is the ONLY way to "
                "add a character to the roster — never hand-write "
                "`.neonrp/playthrough.json`, it feeds the commit hash chain. A cast "
                "character is also archived into the user's library "
                "(`~/.worldlines/souls/<sid>/`), so `cast_soul(sid)` can bring a library "
                "character into any world."
            )
            specific_rules.append(
                "**Places are folders**: create a place with `new_location(name, summary, "
                "connections, parent, notes)` — it writes `game/locations/<id>/location.json` "
                "+ `notes.md`, links both ways and adds the map node. Refine with "
                "`update_location`. Do not hand-write `world_map.json` nodes for places."
            )

    all_rules = common_rules + specific_rules
    return "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(all_rules, start=1))


def _format_skills(skill_descriptions: list[str]) -> str:
    if not skill_descriptions:
        return "- (no skills loaded)"
    return "\n".join(f"- {line}" for line in skill_descriptions)
