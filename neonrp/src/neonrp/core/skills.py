"""Skill tool registry for NeonRP agents.

Provides controlled, permission-aware tools that agents can use to retrieve
context, find entities, and read files.
"""

import json
import logging
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neonrp.core.config import load_config
from neonrp.core.diffing import TurnChangeLedger, summarize_write
from neonrp.core.importers.sillytavern import build_entity_from_card_file, is_valid_entity_id
from neonrp.core.indexing import refresh_manifest_index
from neonrp.core.json_repair import JsonRepairError, repair_json
from neonrp.core.paths import get_game_dir, get_neonrp_dir
from neonrp.core.permissions import check_permission, check_write_permission, PermissionResult
from neonrp.core.retrieval import retrieve_context
from neonrp.core.rules import load_rules_profile, resolve_action as rules_resolve_action
from neonrp.core.storage import atomic_write_text
from neonrp.core.template_assets import (
    DEFAULT_TEMPLATE_NAME,
    ensure_playable_runtime_scaffold,
    list_playable_scaffold_targets,
)


logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """Result from a skill invocation."""

    success: bool
    data: Any = None
    error: str | None = None
    denied_paths: list[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class SkillCall:
    """Record of a skill invocation for auditing."""

    timestamp: str
    run_id: str
    agent_id: str
    skill_name: str
    args: dict[str, Any]
    result_summary: str
    error: str | None
    duration_ms: int
    denied_paths: list[str]


# Skill JSON schemas for LLM tool calling.
# NOTE: soul routing (which souls are active in a scene) is NOT a skill. As of
# M18 Phase 3 it is decided deterministically by the runtime's
# scene-understanding step (core/scene_understanding.py), which writes
# playthrough.json active_souls by locality — the world-agent no longer routes.
SKILL_SCHEMAS = {
    "read_spec": {
        "name": "read_spec",
        "description": (
            "Read a WorldLines spec before you write what it describes (build mode). "
            "world = the world folder · soul = the character folder and library · template = the template "
            "(cast, plots, slots, packages) · contract = the play contract · ops = the ops a play pack lets the "
            "model write (pass pack) · authoring = template authoring ops · contracts = the contracts in force. "
            "Returns Markdown."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": ["world", "soul", "template", "contract", "ops", "authoring", "contracts"]},
                "lang": {"type": "string", "enum": ["zh", "en"], "default": "en"},
                "pack": {"type": "string", "description": "ops only: rpg · pct · werewolf · monopoly"},
            },
            "required": ["name"],
        },
    },
    "read_context": {
        "name": "read_context",
        "description": (
            "Retrieve relevant context entities for a query using semantic search. "
            "Use this when you need background information about the game world "
            "before taking action. Returns entity summaries ranked by relevance. "
            "For game-start intents, prefer reading the runtime contract's configured startup file first "
            "before broad semantic retrieval. "
            "Example: read_context('the dragon king') returns entities related to that topic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query describing what you want to know about (e.g., 'dark forest monsters', 'player inventory')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10). Use smaller values for focused queries.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    "find": {
        "name": "find",
        "description": (
            "Find entities by exact id, tag, kind, or keyword. "
            "Use this when you know the specific entity you are looking for. "
            "For broad/semantic searches, prefer read_context instead. "
            "When you only know an entity id/name but not its file path, call this before read_file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Exact entity id (e.g., 'hero'), or keyword to search names/summaries",
                },
                "kind": {
                    "type": "string",
                    "description": "Filter by entity kind defined in the current project index.",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag (e.g., 'hostile', 'quest-giver')",
                },
            },
            "required": ["query"],
        },
    },
    "read_file": {
        "name": "read_file",
        "description": (
            "Read a file's contents. You MUST call this before write_file or edit_file "
            "on the same path to understand existing content and avoid accidental overwrites. "
            "Use project-root relative paths by default (absolute paths are also accepted). "
            "Do NOT use placeholder prefixes like '<project-root>' or '/workspace/project'. "
            "Content is truncated to max_chars. "
            "Only files within agent read permissions are accessible. "
            "Do NOT guess file paths from entity IDs; use find/list_entities/glob to confirm uncertain paths first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Project-root relative path preferred (e.g., 'src/main.py' or 'index.html'). Absolute path is also accepted.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return. Use smaller values for quick checks, larger for full reads. Default: 5000.",
                    "default": 5000,
                },
            },
            "required": ["path"],
        },
    },
    "list_entities": {
        "name": "list_entities",
        "description": (
            "List all indexed entities, optionally filtered by kind or tag. "
            "Use this to discover what entities exist before reading or modifying them. "
            "Do not use as the first startup step when an explicit entrypoint file is available. "
            "Returns entity ids, names, kinds, and tags."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Filter by entity kind defined in the current project index.",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag (e.g., 'hostile', 'merchant', 'quest')",
                },
            },
        },
    },
    "submit_proposal": {
        "name": "submit_proposal",
        "description": (
            "Submit a batch of changes to game/ state files as an atomic proposal. "
            "This is the ONLY way to create, update, or delete files under game/. "
            "All ops are applied atomically — either all succeed or none do. "
            "Always call read_file or read_context first to understand current state before proposing changes. "
            "Call this once per turn with ALL intended changes bundled together."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_version": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Proposal schema version (currently '0.1').",
                },
                "run_id": {"type": "string", "minLength": 1, "description": "The run ID for this agent run (provided in context)"},
                "agent_id": {"type": "string", "minLength": 1, "description": "The agent ID (provided in context)"},
                "branch": {"type": "string", "minLength": 1, "description": "Target branch name (provided in context)"},
                "base_head_event": {"type": "integer", "description": "Base event ID for optimistic concurrency (provided in context)"},
                "query": {"type": "string", "description": "Original user query that triggered this proposal"},
                "rationale": {
                    "type": "string",
                    "description": "Brief explanation of WHY these changes are being made (for audit log)",
                },
                "ops": {
                    "type": "array",
                    "description": "List of file operations. Each op targets a path under game/.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["upsert_text", "delete"],
                                "description": "upsert_text: create or overwrite file content. delete: remove the file.",
                            },
                            "path": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Path relative to game/ (e.g., 'character/hero.json', 'location/tavern.json'). Do NOT include the 'game/' prefix.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Full file content as a string. Required for upsert_text. For JSON entities, must be valid JSON with id/kind/name fields. Omit for delete ops.",
                            },
                        },
                        "required": ["op", "path"],
                    },
                },
            },
            "required": ["proposal_version", "run_id", "agent_id", "branch", "base_head_event", "ops"],
        },
    },
    "resolve_action": {
        "name": "resolve_action",
        "description": (
            "Compute the mechanical outcome of a game action (combat, healing, trading, movement). "
            "This is a PURE COMPUTATION tool — it does NOT modify any files. "
            "Use the returned values to build ops for submit_proposal. "
            "Typical workflow: resolve_action → read affected entities → submit_proposal with updated values."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["damage", "heal", "buy", "sell", "move"],
                    "description": "Action type: damage (deal damage), heal (restore hp), buy (purchase item), sell (sell item), move (change location)",
                },
                "actor": {
                    "type": "string",
                    "description": "Entity id performing the action (e.g., 'player', 'goblin_chief')",
                },
                "target": {
                    "type": "string",
                    "description": "Target entity id. Required for damage/heal. For buy, this is the shop entity id.",
                },
                "amount": {
                    "type": "integer",
                    "description": "Numeric amount: damage/heal points, or quantity for buy/sell",
                },
                "item": {
                    "type": "string",
                    "description": "Item entity id for buy/sell actions (e.g., 'iron_sword', 'health_potion')",
                },
                "destination": {
                    "type": "string",
                    "description": "Location entity id for move actions (e.g., 'dark_forest', 'castle_gate')",
                },
            },
            "required": ["action", "actor"],
        },
    },
    "roll_check": {
        "name": "roll_check",
        "description": (
            "掷骰判定(M27)。对抗与有失败可能的行动——攻击、闪避、说服、医治、"
            "追逐、窃取、危险攀爬等——**必须**用本工具掷骰决定结果,禁止自行"
            "口算或凭叙事需要指定成败。掷出后,你的叙事必须跟随结果"
            "(成功/失败/大成功/大失败),不得反着写。纯计算工具,不改任何文件;"
            "结果自动进 trace(玩家可审计)。日常无风险动作不必掷。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "判定名目(如 '医术' '斗殴' '说服' 'Stealth')",
                },
                "target": {
                    "type": "integer",
                    "description": "brp=技能值(roll-under d100);srd=DC(roll-over d20)。非负整数。",
                },
                "ruleset": {
                    "type": "string",
                    "enum": ["brp", "srd"],
                    "description": "规则系统,默认 brp(百分骰);srd = d20(旧写法 coc / 5e 也认)",
                },
                "modifier": {
                    "type": "integer",
                    "description": "仅 5e:加值(如属性调整值)",
                },
                "advantage": {"type": "boolean", "description": "仅 5e:优势"},
                "disadvantage": {"type": "boolean", "description": "仅 5e:劣势"},
            },
            "required": ["skill", "target"],
        },
    },
    "ask_soul": {
        "name": "ask_soul",
        "description": (
            "主权双向通道(M24 §5,类比 ask_user):当你(世界整合者)需要某个"
            " soul 的视角/回应/决定时调用 —— 玩家远程联系某人、你认为某 soul "
            "不该对眼前之事毫无反应、需要她对某个情境表态……**该不该问、问什么、"
            "这个世界联系不联系得上,全由你判断**(中世纪送信要三天是你的叙事,"
            "不是本工具的限制);引擎只负责把问题带着她的本体视角(她的场景/"
            "人格/记忆)送到她面前,并把她的原话带回给你。她的回答是她的主权:"
            "可以拒绝、可以反问,你不得代答、不得改写。纯问答,不移动、不写世界。"
            "每回合克制使用(≤3 次为宜)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "soul": {
                    "type": "string",
                    "description": "要问的 soul:名字(艾琳娜)或 instance_id(si-elena0001)",
                },
                "question": {
                    "type": "string",
                    "description": "转达/询问的内容(以主持人口吻,含必要情境)",
                },
            },
            "required": ["soul", "question"],
        },
    },
    "escalate": {
        "name": "escalate",
        "description": (
            "上报世界(M30,soul 侧;与 ask_soul 镜像,主权在你):当你判断"
            "「这件事世界/主持人应该知道」——你要做出影响场景之外的行动、"
            "你察觉了会改变局面的事、你需要世界回应——调用本工具留言。"
            "主持人下回合会看到。不移动、不写世界;克制使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "上报内容(一两句,第一人称)"},
            },
            "required": ["reason"],
        },
    },
    "engage_soul": {
        "name": "engage_soul",
        "description": (
            "点名(M30 V2):让某个 soul 以她的本体视角**全档思考一轮**——"
            "带工具、可写自己的记忆——并把她的报文(digest/内心/意图)带回。"
            "这是让在场角色「活」的方式:谁该对眼前之事有反应,就点谁;"
            "note 里转述她此刻感知到的情境(不是玩家原文)。没被点名的 soul "
            "本回合保持静默。与 ask_soul 的区别:ask 是轻问答,engage 是"
            "完整的一轮存在。每回合按需点名,不必全员。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "soul": {"type": "string", "description": "名字(艾琳娜)或 instance_id"},
                "note": {"type": "string", "description": "主持人转述的此刻情境(可空)"},
            },
            "required": ["soul"],
        },
    },
    "get_roster": {
        "name": "get_roster",
        "description": (
            "在场/离场名册(ontology 唯一数据,M30)。返回玩家位置 + 全部 souls "
            "的名字/iid/位置/是否同场。要点名、要判断谁听得见、要写谁的戏之前,"
            "先看名册——不要凭记忆猜谁在场。只读,零成本,可多次调用。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    "get_location": {
        "name": "get_location",
        "description": (
            "查任意实体的当前位置(ontology 唯一数据)。entity='player' 或 "
            "soul 的名字/instance_id。只读。位置以这里为准,不以你的印象为准。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "player / soul 名字 / instance_id"},
            },
            "required": ["entity"],
        },
    },
    "get_scene": {
        "name": "get_scene",
        "description": (
            "查地点数据 + 场景层状态(scene_state)。写某地的戏、衔接上次在该地"
            "发生的事之前调用。只读。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node": {"type": "string", "description": "地点(裸名或 T###/node)"},
            },
            "required": ["node"],
        },
    },
    "move_entity": {
        "name": "move_entity",
        "description": (
            "结算=工具调用(M30):把某实体移动到某地。你的叙事里谁走到哪,"
            "就调本工具落账——这是位置的唯一结算方式。内置地图裁判:目标不可达"
            "会报错带回(她仍在原地),由你决定改口还是绕路;不要与裁判结果"
            "相矛盾地叙事。entity='player' 或 soul 名字/iid。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "player / soul 名字 / instance_id"},
                "to": {"type": "string", "description": "目标地点(裸名或 T###/node)"},
            },
            "required": ["entity", "to"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": (
            "Create or overwrite a file. "
            "Use project-root relative paths by default (absolute paths are also accepted). "
            "Do NOT use placeholder prefixes like '<project-root>' or '/workspace/project'. "
            "Works only when the target path is allowed by direct_write_globs. "
            "\n\nIMPORTANT usage rules:\n"
            "- ALWAYS call read_file first if the file may already exist, to avoid losing content.\n"
            "- For small edits to existing files, prefer edit_file over write_file.\n"
            "- write_file completely OVERWRITES the file — pass the FULL desired content.\n"
            "- Parent directories are created automatically.\n"
            "- For .json files the content MUST parse as JSON (invalid JSON is rejected). "
            "Inside string values, use 「」/『』 for quoted dialogue instead of nested "
            'double quotes, and escape any literal " as \\".'
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Project-root relative path preferred (e.g., 'src/app.js' or 'docs/notes.md'). Absolute path is also accepted.",
                },
                "content": {
                    "type": "string",
                    "description": "The COMPLETE file content to write. This replaces the entire file. Use UTF-8 text.",
                },
            },
            "required": ["path", "content"],
        },
    },
    "edit_file": {
        "name": "edit_file",
        "description": (
            "Edit an existing file by replacing an exact text substring. "
            "Works only when the target path is allowed by direct_write_globs. "
            "Preferred over write_file when making small, targeted changes to existing files.\n\n"
            "IMPORTANT usage rules:\n"
            "- ALWAYS call read_file first to see the current content and find the exact text to replace.\n"
            "- old_text must match EXACTLY (including whitespace and newlines) and appear EXACTLY ONCE in the file.\n"
            "- If old_text is not found or appears multiple times, the edit will fail.\n"
            "- To insert text, use a surrounding passage as old_text and include the insertion in new_text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Project-root relative path preferred (e.g., 'src/app.js' or 'docs/notes.md'). Absolute path is also accepted.",
                },
                "old_text": {
                    "type": "string",
                    "minLength": 1,
                    "description": "The exact text to find in the file. Must match character-for-character and appear exactly once. Include enough surrounding context to be unique.",
                },
                "new_text": {
                    "type": "string",
                    "description": "The replacement text. Can be empty string to delete old_text. Can be longer or shorter than old_text.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    "delete_file": {
        "name": "delete_file",
        "description": (
            "Delete a single file. Cannot delete directories. "
            "Use project-root relative paths by default (absolute paths are also accepted). "
            "Works only when the target path is allowed by direct_write_globs. "
            "Returns the deleted file path on success."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Project-root relative path preferred (e.g., 'docs/old-notes.md'). Absolute path is also accepted.",
                },
            },
            "required": ["path"],
        },
    },
    "glob": {
        "name": "glob",
        "description": (
            "Find files matching a glob pattern within read permissions. "
            "Use this to discover files before reading them. "
            "Returns a list of matching file paths sorted by name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Glob pattern (e.g., '*.json', 'game/**/*.json', 'lore/*.md', 'notes/session*.txt')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from (default: project root). Relative to project root.",
                },
            },
            "required": ["pattern"],
        },
    },
    "import_sillytavern_card": {
        "name": "import_sillytavern_card",
        "description": (
            "Import a SillyTavern JSON or PNG character card into the current NeonRP project. "
            "Use this for Tavern/酒馆 cards instead of read_file when the source is a .png or raw card .json. "
            "The tool extracts embedded PNG card payloads, converts them to a NeonRP entity, "
            "can optionally set the destination path and visible name, writes the entity under game/, "
            "and returns the imported entity path and metadata."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Project-root relative or absolute path to a SillyTavern card file (.png or .json).",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Optional ASCII entity id override (must match [a-z0-9._-]+).",
                },
                "target_path": {
                    "type": "string",
                    "description": "Optional destination JSON path under game/ (e.g. 'game/npc/yan_chiyang.json' or 'npc/yan_chiyang.json').",
                },
                "name": {
                    "type": "string",
                    "description": "Optional visible name override for the imported entity. Chinese is allowed here.",
                },
            },
            "required": ["path"],
        },
    },
    "ensure_playable_scaffold": {
        "name": "ensure_playable_scaffold",
        "description": (
            "Ensure the current project has the minimum runtime scaffold required for play mode. "
            "This copies packaged play agents and runtime metadata when missing, and rewrites "
            "the active-agent state with the canonical protocol. Use this after build-mode world "
            "generation before claiming the project is playable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "Optional template source for scaffold assets. Defaults to 'default'.",
                    "default": DEFAULT_TEMPLATE_NAME,
                },
                "active_agent": {
                    "type": "string",
                    "description": "Optional agent id to set as the current active agent after scaffold creation. Defaults to the runtime router agent.",
                },
                "force": {
                    "type": "boolean",
                    "description": "When true, overwrite packaged scaffold files even if they already exist.",
                    "default": False,
                },
            },
        },
    },
    "open_in_viewer": {
        "name": "open_in_viewer",
        "description": (
            "Hand a file or folder to the user's own viewer — their editor, Obsidian, "
            "or the browser — so they can look at what you just changed (M31). The TUI "
            "renders text, not maps or images; when the thing worth seeing is visual "
            "(a world map canvas, generated art, the run folder as an Obsidian vault, "
            "a long markdown document), open it instead of describing it.\n\n"
            "Use sparingly and only for something you just produced or changed, and say "
            "why you are opening it. Never open anything the user did not ask about."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Project-relative path to open. A folder opens as a folder "
                        "(e.g. the run root, which is an Obsidian-readable vault)."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "One line the user sees: why this is worth looking at.",
                },
            },
            "required": ["path"],
        },
    },
    "cast_soul": {
        "name": "cast_soul",
        "description": (
            "Bring an already-authored character into THIS world, so the runtime can "
            "spin it up as a character-agent (M31). This is the *admitting* act, and it "
            "is the only one available while playing: build mode writes new characters, "
            "play mode can only let existing ones in.\n\n"
            "In build mode you write the soul's files under `.neonrp/soul-drafts/<sid>/` "
            "first (follow the `soul-authoring` skill for the folder shape) and then call "
            "this with that sid — authoring the folder alone does NOT put the character "
            "in the world. In play mode the folder already exists; you only name it.\n\n"
            "The tool copies the draft into the world, backfills anything structurally "
            "required, and updates the world's roster itself: the character is placed "
            "at `location` (default: right where the player is, so it is on stage now) "
            "and, in town-structured worlds, listed in that town's `npcs.json`.\n\n"
            "NEVER hand-write `.neonrp/playthrough.json` to add a character — it feeds "
            "the commit hash chain and a hand-edit makes the turn unlandable. This tool "
            "is the only supported way in."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sid": {
                    "type": "string",
                    "description": (
                        "The soul id — the folder name you authored under "
                        "`.neonrp/soul-drafts/`. A project-relative path to the draft "
                        "folder also works."
                    ),
                },
                "role": {
                    "type": "string",
                    "enum": ["npc", "player"],
                    "description": "Cast as a world NPC (default) or as the player's avatar.",
                    "default": "npc",
                },
                "activate": {
                    "type": "boolean",
                    "description": "Put the soul on stage immediately (multi-agent worlds). Defaults to true.",
                    "default": True,
                },
                "location": {
                    "type": "string",
                    "description": (
                        "Where the character is right now: a town-map node (`guild`, `T004/tavern`) "
                        "or a place you made with `new_location`. Omit to put it beside the player."
                    ),
                },
            },
            "required": ["sid"],
        },
    },
    "new_location": {
        "name": "new_location",
        "description": (
            "Create a NEW place in this world (任务 B2). Writes the place as a folder "
            "`game/locations/<id>/` (location.json + notes.md), links it both ways to the "
            "places you name in `connections`, and adds a node to `game/world/world_map.json` "
            "so the map and the canvas show it. In a world with towns (`game/towns/<T>/`) "
            "the place is also registered as a node of the right town's map — the one "
            "`town` names, else the parent's/connections' town, else the player's — so "
            "people can actually walk there. Available while playing too: when the "
            "story walks into somewhere that does not exist yet, create it here instead of "
            "describing a place the world cannot find. Refine it later with `update_location`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name (e.g. 河灯旅店)."},
                "id": {"type": "string", "description": "Optional id; derived from the name when omitted."},
                "summary": {"type": "string", "description": "One or two sentences: what this place is."},
                "connections": {"type": "array", "items": {"type": "string"}, "description": "Ids or names of places you can walk to from here (linked both ways)."},
                "parent": {"type": "string", "description": "Id/name of the containing place (a room inside an inn, a district inside a town)."},
                "tags": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string", "description": "Free-form detail for notes.md (layout, smells, who hangs around)."},
                "town": {"type": "string", "description": "Town id (T004) this place belongs to, when it is not obvious from parent/connections/the player."},
            },
            "required": ["name"],
        },
    },
    "update_location": {
        "name": "update_location",
        "description": (
            "Refine an existing place (任务 B2): rename, rewrite the summary, add/remove "
            "connections (kept symmetric), set its parent, append notes. Works on both the "
            "folder form and the older single-file form. The world map node is kept in sync."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Id or display name of the place."},
                "name": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "add_connections": {"type": "array", "items": {"type": "string"}},
                "remove_connections": {"type": "array", "items": {"type": "string"}},
                "parent": {"type": "string"},
                "notes_append": {"type": "string", "description": "Text appended to notes.md."},
            },
            "required": ["id"],
        },
    },
    "grep": {
        "name": "grep",
        "description": (
            "Search file contents using a regex pattern. "
            "Returns matching lines with file paths and line numbers. "
            "Use this to find specific content across multiple files. "
            "Results are filtered by read permissions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Regex pattern to search for (e.g., '\"kind\":\\s*\"character\"', 'dragon', 'hp.*[0-9]+')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search in (default: project root). Relative to project root.",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob filter for file names (e.g., '*.md' for markdown only, '**/*.json' for all JSON)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matching lines to return (default: 50). Use smaller values for targeted searches.",
                },
            },
            "required": ["pattern"],
        },
    },
    "ask_user": {
        "name": "ask_user",
        "description": (
            "Ask the user questions during gameplay. You MUST call this tool whenever "
            "the user faces a meaningful choice — do NOT decide on the user's behalf. "
            "Users will always be able to select 'Other' to provide custom text input. "
            "Use multiSelect: true to allow multiple answers for a question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "Questions to ask the user (1-4 questions)",
                    "minItems": 1,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": (
                                    "The complete question to ask the user. Should be clear, "
                                    "specific, and end with a question mark."
                                ),
                            },
                            "header": {
                                "type": "string",
                                "description": "Very short label displayed as a chip/tag (max 12 chars).",
                            },
                            "options": {
                                "type": "array",
                                "description": "The available choices (2-4 options). An 'Other' option is added automatically.",
                                "minItems": 2,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {
                                            "type": "string",
                                            "description": "Display text for this option (1-8 words).",
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": "Explanation of what this option means or what will happen.",
                                        },
                                    },
                                    "required": ["label", "description"],
                                },
                            },
                            "multiSelect": {
                                "type": "boolean",
                                "default": False,
                                "description": "Set to true to allow multiple selections.",
                            },
                        },
                        "required": ["question", "header", "options", "multiSelect"],
                    },
                },
            },
            "required": ["questions"],
        },
    },
}


def _skill_schema_map(include_resolve_action: bool = True) -> dict[str, dict[str, Any]]:
    """Build effective skill schema map based on feature toggles."""
    if include_resolve_action:
        return SKILL_SCHEMAS
    return {name: schema for name, schema in SKILL_SCHEMAS.items() if name != "resolve_action"}


def _indexed_entity_kinds(root: Path | None) -> list[str]:
    """Read entity kinds from the current manifest index."""
    if not isinstance(root, Path):
        return []
    manifest_path = root / ".neonrp" / "manifest.json"
    if not manifest_path.exists():
        return []
    kinds: set[str] = set()
    try:
        manifest, _, _ = refresh_manifest_index(root, full_rebuild=False)
        kinds.update(str(record.kind).strip() for record in manifest.entities.values() if str(record.kind).strip())
    except Exception:
        pass
    if kinds:
        return sorted(kinds)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        entities = payload.get("entities", {})
        if isinstance(entities, dict):
            for record in entities.values():
                if isinstance(record, dict):
                    kind = str(record.get("kind", "")).strip()
                    if kind:
                        kinds.add(kind)
    except Exception:
        pass
    return sorted(kinds)


def _apply_dynamic_kind_enum(schemas: dict[str, dict[str, Any]], kinds: list[str]) -> None:
    """Inject available indexed kinds into find/list_entities kind parameters."""
    if not kinds:
        return
    kind_desc = f"Filter by entity kind. Must be one of indexed kinds: {', '.join(kinds)}."
    for tool_name in ("find", "list_entities"):
        tool_schema = schemas.get(tool_name)
        if not isinstance(tool_schema, dict):
            continue
        params = tool_schema.get("parameters")
        if not isinstance(params, dict):
            continue
        properties = params.get("properties")
        if not isinstance(properties, dict):
            continue
        kind_schema = properties.get("kind")
        if not isinstance(kind_schema, dict):
            continue
        kind_schema["enum"] = kinds
        kind_schema["description"] = kind_desc


def _effective_skill_schema_map(include_resolve_action: bool = True, root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return feature-gated schemas with optional dynamic kind enum injection."""
    schemas = deepcopy(_skill_schema_map(include_resolve_action=include_resolve_action))
    _apply_dynamic_kind_enum(schemas, _indexed_entity_kinds(root))
    return schemas


def get_skill_schemas(include_resolve_action: bool = True, root: Path | None = None, *, include_spec: bool = False) -> list[dict]:
    """Get all skill schemas for LLM tool calling. ``read_spec`` only when asked (the authoring side — build mode)."""
    return [s for s in _effective_skill_schema_map(include_resolve_action=include_resolve_action, root=root).values()
            if include_spec or s.get("name") != "read_spec"]


def validate_tool_arguments(
    name: str,
    args: dict[str, Any],
    *,
    include_resolve_action: bool = True,
    allowed_tool_names: set[str] | None = None,
    root: Path | None = None,
) -> tuple[bool, str | None]:
    """Validate tool arguments against schema.

    Args:
        name: Tool name
        args: Arguments to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    schemas = _effective_skill_schema_map(include_resolve_action=include_resolve_action, root=root)
    if allowed_tool_names is not None:
        schemas = {tool_name: schema for tool_name, schema in schemas.items() if tool_name in allowed_tool_names}

    if name not in schemas:
        available = ", ".join(sorted(schemas.keys()))
        return False, (
            f"Unknown tool: {name}. "
            f"Available tools: {available}. "
            f"Call tools by name with arguments as a JSON object, e.g. "
            f'{{\"name\": \"glob\", \"input\": {{\"pattern\": \"**/*.json\"}}}}'
        )

    schema = schemas[name]
    params = schema.get("parameters", {})
    properties = params.get("properties", {})
    required = params.get("required", [])

    # Detect completely empty arguments — give a detailed example to help the
    # model self-correct (especially for Ollama/compatible providers that may
    # drop arguments during streaming).
    if not args and required:
        example_args = {}
        for field_name in required:
            prop = properties.get(field_name, {})
            ptype = prop.get("type", "string")
            desc = prop.get("description", "")
            if ptype == "array":
                example_args[field_name] = ["option1", "option2"]
            else:
                example_args[field_name] = desc[:60] if desc else f"<{field_name}>"
        example_json = json.dumps(example_args, ensure_ascii=False)
        return False, (
            f"Tool '{name}' received empty arguments. "
            f"Required fields: {', '.join(required)}. "
            f"You MUST pass arguments as a JSON object, e.g.: {example_json}"
        )

    # Check required fields
    for field_name in required:
        if field_name not in args:
            return False, f"Missing required field: {field_name}"
        if args[field_name] is None:
            return False, f"Field '{field_name}' cannot be null"

    # Validate each provided field
    for field_name, value in args.items():
        if field_name not in properties:
            # Allow extra fields (additionalProperties not explicitly false)
            continue

        prop_schema = properties[field_name]
        prop_type = prop_schema.get("type")

        # Auto-coerce: some models pass dict/list where a string is expected
        # (e.g. write_file content as a JSON object instead of serialized string).
        if prop_type == "string" and isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
            args[field_name] = value

        # Type validation
        if prop_type == "string":
            if not isinstance(value, str):
                return False, f"Field '{field_name}' must be a string, got {type(value).__name__}"
            # minLength validation
            min_length = prop_schema.get("minLength")
            if min_length is not None and len(value) < min_length:
                return False, f"Field '{field_name}' must be at least {min_length} character(s)"
            # enum validation
            enum_values = prop_schema.get("enum")
            if enum_values is not None and value not in enum_values:
                return False, f"Field '{field_name}' must be one of: {', '.join(enum_values)}"
        elif prop_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                return False, f"Field '{field_name}' must be an integer, got {type(value).__name__}"
        elif prop_type == "array":
            if not isinstance(value, list):
                return False, f"Field '{field_name}' must be an array, got {type(value).__name__}"
            # Validate array items if items schema exists
            items_schema = prop_schema.get("items", {})
            if items_schema.get("type") == "object":
                item_props = items_schema.get("properties", {})
                item_required = items_schema.get("required", [])
                for i, item in enumerate(value):
                    if not isinstance(item, dict):
                        return False, f"{field_name}[{i}] must be an object"
                    # Check required fields in item
                    for req_field in item_required:
                        if req_field not in item:
                            return False, f"{field_name}[{i}] missing required field: {req_field}"
                    # Validate item fields
                    for item_field, item_value in item.items():
                        if item_field not in item_props:
                            continue
                        item_prop_schema = item_props[item_field]
                        item_prop_type = item_prop_schema.get("type")
                        if item_prop_type == "string":
                            if not isinstance(item_value, str):
                                return False, f"{field_name}[{i}].{item_field} must be a string"
                            item_min_len = item_prop_schema.get("minLength")
                            if item_min_len is not None and len(item_value) < item_min_len:
                                return (
                                    False,
                                    f"{field_name}[{i}].{item_field} must be at least {item_min_len} character(s)",
                                )
                            item_enum = item_prop_schema.get("enum")
                            if item_enum is not None and item_value not in item_enum:
                                return False, f"{field_name}[{i}].{item_field} must be one of: {', '.join(item_enum)}"

    return True, None


class SkillRegistry:
    """Permission-aware skill registry for agent tool calls.

    Enforces agent permissions on file access and logs all invocations.
    """

    def __init__(
        self,
        root: Path,
        run_id: str,
        agent_id: str,
        read_globs: list[str],
        deny_globs: list[str],
        direct_write_globs: list[str] | None = None,
        allow_protected_paths: bool = False,
        enable_resolve_action: bool | None = None,
        rules_profile: dict[str, Any] | None = None,
        change_ledger: TurnChangeLedger | None = None,
    ):
        """Initialize skill registry.

        Args:
            root: Project root directory
            run_id: Current agent run ID
            agent_id: Agent identifier
            read_globs: Agent read permission globs
            deny_globs: Agent deny globs (takes priority)
            direct_write_globs: Paths allowed for direct writes via write_file/edit_file
            allow_protected_paths: Whether to allow writing in protected directories
            enable_resolve_action: Whether resolve_action tool is available
            rules_profile: Optional preloaded rules profile for resolve_action
        """
        self.root = root
        self.run_id = run_id
        self.agent_id = agent_id
        self.read_globs = read_globs
        self.deny_globs = deny_globs
        self.direct_write_globs = direct_write_globs or []
        self.allow_protected_paths = allow_protected_paths
        config = load_config(root)
        self.enable_resolve_action = (
            config.rules.enable_resolve_action if enable_resolve_action is None else bool(enable_resolve_action)
        )
        self._rules_profile = rules_profile or load_rules_profile(root, config.rules.profile_path)
        self._calls: list[SkillCall] = []
        # M31 B2: every direct write this turn, so the surface can answer
        # "what did this turn actually change" once, instead of leaving the
        # reviewer to scroll back through individual tool cards. The caller
        # may own the ledger (the session does) so it survives every exit
        # path this function has.
        self._change_ledger = change_ledger if change_ledger is not None else TurnChangeLedger()

    @property
    def change_ledger(self) -> TurnChangeLedger:
        """Files touched by direct writes since the last :meth:`reset_ledger`."""
        return self._change_ledger

    def reset_ledger(self) -> None:
        """Start a fresh turn's ledger."""
        self._change_ledger = TurnChangeLedger()

    @staticmethod
    def _read_text_before(file_path: Path) -> str | None:
        """Pre-write content, or None when there is nothing there to diff.

        Binary and undecodable files read as None: they have no line-level
        story to tell, so they show up as a plain create/overwrite.
        """
        try:
            if not file_path.is_file():
                return None
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _record_change(
        self, path: str, before: str | None, after: str | None
    ) -> dict[str, Any]:
        """Summarize one write and file it into this turn's ledger."""
        summary = summarize_write(path, before, after)
        self._change_ledger.record(summary)
        return summary.to_dict()

    def _resolve_path(self, path: str) -> Path:
        mapped = self._map_model_placeholder(path)
        if mapped is not None:
            return self.root / mapped if mapped else self.root
        candidate = Path(path)
        return candidate if candidate.is_absolute() else (self.root / candidate)

    def _map_model_placeholder(self, path: str) -> str | None:
        """Map common model placeholder paths to the current project root.

        Some models emit placeholders like '/workspace/project/...' or
        '<project-root>/...'. On Windows these can resolve outside the active
        project or fail path validation. We remap those placeholders to self.root.
        """
        raw = str(path).replace("\\", "/")
        prefixes = (
            "/workspace/project/",
            "<project-root>/",
            "${PROJECT_ROOT}/",
            "$PROJECT_ROOT/",
            "{{project_root}}/",
        )
        roots = (
            "/workspace/project",
            "<project-root>",
            "${PROJECT_ROOT}",
            "$PROJECT_ROOT",
            "{{project_root}}",
        )
        if raw in roots:
            return ""
        for prefix in prefixes:
            if raw.startswith(prefix):
                return raw[len(prefix) :]
        return None

    def _path_for_permission(self, path: str) -> str:
        raw = str(path).replace("\\", "/")
        if ".." in raw.split("/"):
            return raw
        candidate = self._resolve_path(path)
        try:
            rel = candidate.resolve().relative_to(self.root.resolve())
            return str(rel).replace("\\", "/")
        except Exception:
            # Keep best-effort normalized path for error reporting when target is outside root.
            return str(candidate).replace("\\", "/")

    def invoke(self, skill_name: str, args: dict[str, Any]) -> SkillResult:
        """Invoke a skill by name.

        Args:
            skill_name: Name of the skill to invoke
            args: Skill arguments

        Returns:
            SkillResult with data or error
        """
        start_time = time.time()

        if skill_name == "resolve_action" and not self.enable_resolve_action:
            return SkillResult(success=False, error="resolve_action is disabled by rules config")

        available_schemas = _skill_schema_map(include_resolve_action=self.enable_resolve_action)
        if skill_name not in available_schemas:
            return SkillResult(success=False, error=f"Unknown skill: {skill_name}")

        # Dispatch to skill implementation
        try:
            if skill_name == "read_spec":
                result = self._skill_read_spec(args)
            elif skill_name == "read_context":
                result = self._skill_read_context(args)
            elif skill_name == "find":
                result = self._skill_find(args)
            elif skill_name == "read_file":
                result = self._skill_read_file(args)
            elif skill_name == "list_entities":
                result = self._skill_list_entities(args)
            elif skill_name == "resolve_action":
                result = self._skill_resolve_action(args)
            elif skill_name == "roll_check":
                result = self._skill_roll_check(args)
            elif skill_name == "ask_soul":
                result = self._skill_ask_soul(args)
            elif skill_name == "engage_soul":
                result = self._skill_engage_soul(args)
            elif skill_name == "escalate":
                result = self._skill_escalate(args)
            elif skill_name == "get_roster":
                result = self._skill_get_roster(args)
            elif skill_name == "get_location":
                result = self._skill_get_location(args)
            elif skill_name == "get_scene":
                result = self._skill_get_scene(args)
            elif skill_name == "move_entity":
                result = self._skill_move_entity(args)
            elif skill_name == "write_file":
                result = self._skill_write_file(args)
            elif skill_name == "edit_file":
                result = self._skill_edit_file(args)
            elif skill_name == "delete_file":
                result = self._skill_delete_file(args)
            elif skill_name == "glob":
                result = self._skill_glob(args)
            elif skill_name == "import_sillytavern_card":
                result = self._skill_import_sillytavern_card(args)
            elif skill_name == "ensure_playable_scaffold":
                result = self._skill_ensure_playable_scaffold(args)
            elif skill_name == "cast_soul":
                result = self._skill_cast_soul(args)
            elif skill_name == "new_location":
                result = self._skill_new_location(args)
            elif skill_name == "update_location":
                result = self._skill_update_location(args)
            elif skill_name == "open_in_viewer":
                result = self._skill_open_in_viewer(args)
            elif skill_name == "grep":
                result = self._skill_grep(args)
            else:
                result = SkillResult(success=False, error=f"Skill not implemented: {skill_name}")
        except Exception as e:
            result = SkillResult(success=False, error=str(e))

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        result.duration_ms = duration_ms

        # Log the call
        self._log_call(skill_name, args, result)

        return result

    def _check_path_permission(self, path: str) -> PermissionResult:
        """Check if a path is allowed by agent permissions."""
        return check_permission(self._path_for_permission(path), self.read_globs, self.deny_globs)

    def _filter_paths(self, items: list[dict], path_key: str = "path") -> tuple[list[dict], list[str]]:
        """Filter items by path permission.

        Returns:
            Tuple of (allowed items, denied paths)
        """
        allowed = []
        denied = []

        for item in items:
            path = item.get(path_key, "")
            result = self._check_path_permission(path)
            if result.allowed:
                if isinstance(path, str) and path:
                    item_copy = dict(item)
                    item_copy[path_key] = str(self._resolve_path(path).resolve())
                    allowed.append(item_copy)
                else:
                    allowed.append(item)
            else:
                denied.append(path)
                logger.warning(f"Path denied for agent {self.agent_id}: {path}")

        return allowed, denied

    def _skill_read_spec(self, args: dict[str, Any]) -> SkillResult:
        """The spec for what the agent is about to write (neonrp/spec.py)."""
        from neonrp import spec

        try:
            text = spec.read(str(args.get("name") or ""), lang=str(args.get("lang") or "en"), pack=args.get("pack") or None)
        except KeyError as e:
            return SkillResult(success=False, error=str(e).strip("'\""))
        except Exception as e:  # noqa: BLE001 — e.g. an unknown pack
            return SkillResult(success=False, error=str(e)[:300])
        return SkillResult(success=True, data={"name": args.get("name"), "spec": text})

    def _skill_read_context(self, args: dict[str, Any]) -> SkillResult:
        """Execute read_context skill."""
        query = args.get("query", "")
        limit = args.get("limit", 10)

        if not query:
            return SkillResult(success=False, error="Query is required")

        items = retrieve_context(self.root, query, max_results=limit * 2)  # Get extra to filter
        allowed, denied = self._filter_paths(items)

        return SkillResult(success=True, data=allowed[:limit], denied_paths=denied)

    def _skill_find(self, args: dict[str, Any]) -> SkillResult:
        """Execute find skill."""
        query = args.get("query", "")
        kind_filter = args.get("kind")
        tag_filter = args.get("tag")

        if not query:
            return SkillResult(success=False, error="Query is required")

        # Use retrieval for now (could optimize with direct manifest access)
        items = retrieve_context(self.root, query, max_results=50)

        # Apply filters
        if kind_filter:
            items = [i for i in items if i.get("kind") == kind_filter]
        if tag_filter:
            items = [i for i in items if tag_filter in i.get("data", {}).get("tags", [])]

        allowed, denied = self._filter_paths(items)

        return SkillResult(success=True, data=allowed, denied_paths=denied)

    def _skill_read_file(self, args: dict[str, Any]) -> SkillResult:
        """Execute read_file skill."""
        path = args.get("path", "")
        max_chars = args.get("max_chars", 5000)  # Default truncation limit

        if not path:
            return SkillResult(success=False, error="Path is required")

        result = self._check_path_permission(path)
        if not result.allowed:
            return SkillResult(success=False, error=f"Permission denied for path: {path}", denied_paths=[path])

        file_path = self._resolve_path(path)
        if not file_path.exists():
            return SkillResult(success=False, error=f"File not found: {path}")

        try:
            content = file_path.read_text(encoding="utf-8")
            truncated = False
            if len(content) > max_chars:
                content = content[:max_chars]
                truncated = True
            return SkillResult(
                success=True,
                data={"path": str(file_path.resolve()), "content": content, "truncated": truncated},
            )
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to read file: {e}")

    def _skill_list_entities(self, args: dict[str, Any]) -> SkillResult:
        """Execute list_entities skill."""
        kind_filter = args.get("kind")
        tag_filter = args.get("tag")

        try:
            manifest, _, warnings = refresh_manifest_index(self.root, full_rebuild=False)
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to refresh entity index: {e}")

        if warnings:
            logger.info("list_entities index refresh warnings: %d", len(warnings))

        entities = []
        for _, record in manifest.entities.items():
            entity = {
                "id": record.id,
                "kind": record.kind,
                "name": record.name,
                "path": record.path,
                "tags": record.tags or [],
                "summary": record.summary,
            }

            # Apply filters
            if kind_filter and record.kind != kind_filter:
                continue
            if tag_filter and tag_filter not in (record.tags or []):
                continue

            entities.append(entity)

        allowed, denied = self._filter_paths(entities)

        return SkillResult(success=True, data=allowed, denied_paths=denied)

    def _skill_resolve_action(self, args: dict[str, Any]) -> SkillResult:
        """Resolve a game action mechanically.

        This skill computes the outcome of game actions without modifying files.
        The agent should use the computed values to build correct ops.
        """
        action = args.get("action")
        actor = args.get("actor")
        target = args.get("target")
        amount = args.get("amount")
        item = args.get("item")
        destination = args.get("destination")

        if not action or not actor:
            return SkillResult(success=False, error="action and actor are required")

        # Use the rules engine to resolve the action
        result = rules_resolve_action(
            root=self.root,
            action=action,
            actor=actor,
            target=target,
            amount=amount,
            item=item,
            destination=destination,
            profile=self._rules_profile,
        )

        return SkillResult(
            success=result.success,
            data={
                "action": result.action,
                "message": result.message,
                "computed_values": result.computed_values,
            },
            error=result.error,
        )

    def _skill_roll_check(self, args: dict[str, Any]) -> SkillResult:
        """掷骰判定(M27 v1)—— dice.py 原语接入结算链。

        裁定/掷分离:要不要 check、target 多少由调用方(world-agent)裁定;
        点数由引擎掷。纯计算,不改文件;工具调用本身即 trace 记录
        (M17 replay 从 trace 重现,不重掷)。
        """
        from neonrp.core.dice import canonical_ruleset, format_dice_line, roll_check

        skill = str(args.get("skill") or "").strip()
        if not skill:
            return SkillResult(success=False, error="skill(判定名目)必填")
        try:
            target = int(args.get("target"))
        except (TypeError, ValueError):
            return SkillResult(success=False, error="target 必须是非负整数")
        ruleset = canonical_ruleset(args.get("ruleset"))
        try:
            result = roll_check(
                skill,
                target,
                ruleset=ruleset,  # type: ignore[arg-type]
                modifier=int(args.get("modifier") or 0),
                advantage=bool(args.get("advantage")),
                disadvantage=bool(args.get("disadvantage")),
            )
        except ValueError as exc:
            return SkillResult(success=False, error=str(exc))
        return SkillResult(
            success=True,
            data={
                "skill": result.skill_name,
                "ruleset": ruleset,
                "roll": result.roll,
                "target": result.target,
                "outcome": result.outcome.value,
                "passed": result.passed,
                "margin": result.margin,
                "line": format_dice_line(result, locale="zh"),
            },
        )

    def _skill_ask_soul(self, args: dict[str, Any]) -> SkillResult:
        """主权双向通道(M24 §5):world-agent 判断,引擎投递与带回。"""
        from neonrp.core.light_chat import ask_soul_deliver

        target = str(args.get("soul") or "").strip()
        question = str(args.get("question") or "").strip()
        if not target or not question:
            return SkillResult(success=False, error="soul 与 question 必填")
        out = ask_soul_deliver(self.root, target, question, asker=self.agent_id or "world-agent")
        if not out.get("ok"):
            return SkillResult(success=False, error=str(out.get("error")))
        return SkillResult(
            success=True,
            data={
                "soul": out["name"],
                "instance_id": out["iid"],
                "answer": out["answer"],
                "co_located": out["co_located"],
                "location": out["location"],
            },
        )

    def _skill_escalate(self, args: dict[str, Any]) -> SkillResult:
        """soul 上报(M30):主权在 soul,引擎只投递;下回合 preflight 送达。"""
        from neonrp.core.notes import post_note

        reason = str(args.get("reason") or "").strip()
        if not reason:
            return SkillResult(success=False, error="reason 必填")
        post_note(
            self.root,
            "escalation",
            f"[{self.agent_id}] {reason}",
            sender=self.agent_id or "soul",
        )
        return SkillResult(success=True, data={"delivered": True})

    def _skill_engage_soul(self, args: dict[str, Any]) -> SkillResult:
        """点名(M30 V2):leader 判断点谁,引擎全档执行并带回报文。"""
        from neonrp.core.engage import engage_soul_run

        out = engage_soul_run(
            self.root,
            str(args.get("soul") or ""),
            str(args.get("note") or ""),
        )
        if not out.get("ok"):
            return SkillResult(success=False, error=str(out.get("error")))
        return SkillResult(success=True, data=out)

    # ── ontology 面(M30 V1):数据唯一权威,校验在工具内脏 ─────────

    def _skill_get_roster(self, args: dict[str, Any]) -> SkillResult:
        from neonrp.core.ontology import get_roster

        return SkillResult(success=True, data=get_roster(self.root))

    def _skill_get_location(self, args: dict[str, Any]) -> SkillResult:
        from neonrp.core.ontology import get_location

        out = get_location(self.root, str(args.get("entity") or ""))
        if not out.get("ok"):
            return SkillResult(success=False, error=str(out.get("error")))
        return SkillResult(success=True, data=out)

    def _skill_get_scene(self, args: dict[str, Any]) -> SkillResult:
        from neonrp.core.ontology import get_scene

        out = get_scene(self.root, str(args.get("node") or ""))
        if not out.get("ok"):
            return SkillResult(success=False, error=str(out.get("error")))
        return SkillResult(success=True, data=out)

    def _skill_move_entity(self, args: dict[str, Any]) -> SkillResult:
        from neonrp.core.ontology import move_entity

        out = move_entity(
            self.root, str(args.get("entity") or ""), str(args.get("to") or "")
        )
        if not out.get("ok"):
            # 拒绝也带回位置事实,leader 自行改口/绕路(M30 §4)。
            return SkillResult(success=False, error=str(out.get("error")), data=out)
        return SkillResult(success=True, data=out)

    @staticmethod
    def _normalize_json_text_for_write(path: str, content: Any) -> str:
        """Canonicalize JSON payloads at the write boundary.

        ``.json`` targets are parsed — healing the known LLM malformations
        (unescaped inner quotes, trailing commas, smart-quote delimiters …)
        via ``neonrp.core.json_repair`` — and re-serialized canonically, so
        escaping is always normalized and repairable output never lands on
        disk raw. Unrepairable JSON raises ``JsonRepairError``: the caller
        REJECTS the write and bounces the precise parse error back to the
        model, so garbage never lands silently."""
        text = content if isinstance(content, str) else str(content)
        normalized_path = str(path or "").replace("\\", "/").lower()
        if not normalized_path.endswith(".json"):
            return text
        return repair_json(text)

    @staticmethod
    def _json_reject_error(path: str, exc: JsonRepairError) -> str:
        """The rejection message the model sees — precise and actionable."""
        return (
            f"Rejected write to {path}: {exc} "
            "The file was NOT written. Rewrite the FULL content as valid JSON: "
            'escape inner double quotes as \\" (or use 「」/『』 for dialogue '
            "inside string values), no trailing commas, ASCII \" delimiters only."
        )

    def _skill_write_file(self, args: dict[str, Any]) -> SkillResult:
        """Execute write_file skill.

        Writes content to a file if path is in direct_write_globs.
        For game/ changes, guide user to use submit_proposal.
        """
        path = args.get("path", "")
        content = args.get("content", "")

        if not path:
            return SkillResult(success=False, error="path is required")

        # Check write permission
        permission_path = self._path_for_permission(path)
        perm_result = check_write_permission(
            permission_path,
            self.direct_write_globs,
            self.deny_globs,
            allow_protected_paths=self.allow_protected_paths,
        )
        if not perm_result.allowed:
            return SkillResult(success=False, error=perm_result.reason, denied_paths=[path])

        # Repair/canonicalize .json payloads; reject unparseable ones so the
        # model gets the parse error instead of garbage landing on disk.
        try:
            normalized_content = self._normalize_json_text_for_write(path, content)
        except JsonRepairError as e:
            return SkillResult(success=False, error=self._json_reject_error(path, e))

        # Perform atomic write
        try:
            file_path = self._resolve_path(path)
            # M31: capture the before-state while we still have it — this is
            # the only cheap moment to answer "how did it change".
            before = self._read_text_before(file_path)
            atomic_write_text(file_path, normalized_content)
            logger.info(f"write_file: wrote {len(normalized_content)} chars to {path}")
            return SkillResult(
                success=True,
                data={
                    "path": str(file_path.resolve()),
                    "bytes_written": len(normalized_content.encode("utf-8")),
                    "change": self._record_change(path, before, normalized_content),
                },
            )
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to write file: {e}")

    def _skill_edit_file(self, args: dict[str, Any]) -> SkillResult:
        """Execute edit_file skill.

        Replaces exact text in a file if path is in direct_write_globs.
        old_text must appear exactly once for safe replacement.
        """
        path = args.get("path", "")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")

        if not path:
            return SkillResult(success=False, error="path is required")
        if not old_text:
            return SkillResult(success=False, error="old_text is required")

        # Check write permission
        permission_path = self._path_for_permission(path)
        perm_result = check_write_permission(
            permission_path,
            self.direct_write_globs,
            self.deny_globs,
            allow_protected_paths=self.allow_protected_paths,
        )
        if not perm_result.allowed:
            return SkillResult(success=False, error=perm_result.reason, denied_paths=[path])

        file_path = self._resolve_path(path)

        # Check file exists
        if not file_path.exists():
            return SkillResult(success=False, error=f"File not found: {path}")

        # Read current content
        try:
            current_content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to read file: {e}")

        # Count occurrences
        count = current_content.count(old_text)

        if count == 0:
            return SkillResult(success=False, error="Text not found in file")
        if count > 1:
            return SkillResult(
                success=False,
                error=f"Text found {count} times, must be unique for safe replacement",
            )

        # Perform replacement; repair/canonicalize .json results and reject
        # edits that leave the file unparseable (file stays untouched).
        new_content = current_content.replace(old_text, new_text, 1)
        try:
            new_content = self._normalize_json_text_for_write(path, new_content)
        except JsonRepairError as e:
            return SkillResult(success=False, error=self._json_reject_error(path, e))

        # Atomic write
        try:
            atomic_write_text(file_path, new_content)
            logger.info(f"edit_file: replaced text in {path}")
            return SkillResult(
                success=True,
                data={
                    "path": str(file_path.resolve()),
                    "replaced": True,
                    "change": self._record_change(path, current_content, new_content),
                },
            )
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to write file: {e}")

    def _skill_delete_file(self, args: dict[str, Any]) -> SkillResult:
        """Execute delete_file skill.

        Deletes a single file if path is in direct_write_globs.
        Cannot delete directories.
        """
        path = args.get("path", "")

        if not path:
            return SkillResult(success=False, error="path is required")

        # Check write permission (delete is a write operation)
        permission_path = self._path_for_permission(path)
        perm_result = check_write_permission(
            permission_path,
            self.direct_write_globs,
            self.deny_globs,
            allow_protected_paths=self.allow_protected_paths,
        )
        if not perm_result.allowed:
            return SkillResult(success=False, error=perm_result.reason, denied_paths=[path])

        file_path = self._resolve_path(path)

        if not file_path.exists():
            return SkillResult(success=False, error=f"File not found: {path}")

        if file_path.is_dir():
            return SkillResult(success=False, error=f"Cannot delete directory: {path}. Only files can be deleted.")

        try:
            before = self._read_text_before(file_path)
            file_path.unlink()
            logger.info(f"delete_file: deleted {path}")
            return SkillResult(
                success=True,
                data={
                    "path": str(file_path.resolve()),
                    "deleted": True,
                    "change": self._record_change(path, before, None),
                },
            )
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to delete file: {e}")

    def _skill_glob(self, args: dict[str, Any]) -> SkillResult:
        """Execute glob skill.

        Find files matching a glob pattern, filtered by read permissions.
        Max 200 results.
        """
        pattern = args.get("pattern", "")
        base_path = args.get("path", "")

        if not pattern:
            return SkillResult(success=False, error="pattern is required")

        # Reject path traversal in pattern
        if ".." in pattern:
            return SkillResult(success=False, error="Path traversal (..) not allowed in pattern")

        # Determine search root
        if base_path:
            if ".." in base_path:
                return SkillResult(success=False, error="Path traversal (..) not allowed in path")
            search_root = self.root / base_path
        else:
            search_root = self.root

        if not search_root.exists():
            return SkillResult(success=False, error=f"Path not found: {base_path or '.'}")

        # Collect matching files
        matches = []
        denied_paths = []
        max_results = 200

        try:
            # Path.glob() natively supports ** for recursive matching since Python 3.5
            file_iter = search_root.glob(pattern)

            for file_path in file_iter:
                if len(matches) >= max_results:
                    break

                if not file_path.is_file():
                    continue

                # Get relative path from project root
                try:
                    rel_path = str(file_path.relative_to(self.root)).replace("\\", "/")
                except ValueError:
                    continue

                # Check read permission
                perm_result = self._check_path_permission(rel_path)
                if perm_result.allowed:
                    matches.append(
                        {
                            "path": rel_path,
                            "size": file_path.stat().st_size,
                        }
                    )
                else:
                    denied_paths.append(rel_path)

        except Exception as e:
            return SkillResult(success=False, error=f"Glob error: {e}")

        return SkillResult(
            success=True,
            data={"files": matches, "count": len(matches), "capped": len(matches) >= max_results},
            denied_paths=denied_paths,
        )

    def _skill_import_sillytavern_card(self, args: dict[str, Any]) -> SkillResult:
        """Import a SillyTavern JSON/PNG card into game/character/."""
        source_path = args.get("path", "")
        entity_id = args.get("entity_id")
        target_path = str(args.get("target_path", "") or "").strip()
        name_override = str(args.get("name", "") or "").strip()

        if not source_path:
            return SkillResult(success=False, error="path is required")

        read_result = self._check_path_permission(source_path)
        if not read_result.allowed:
            return SkillResult(success=False, error=f"Permission denied for path: {source_path}", denied_paths=[source_path])

        resolved_source = self._resolve_path(source_path)
        if not resolved_source.exists():
            return SkillResult(success=False, error=f"File not found: {source_path}")

        data_dir = get_game_dir(self.root)
        normalized_entity_id = str(entity_id).strip() if entity_id is not None else None
        rel_path = ""
        target_kind = "character"
        target_entity_id = normalized_entity_id or None
        existing_ids: set[str] | None = None

        if target_path:
            normalized_target = target_path.replace("\\", "/").strip()
            if ".." in normalized_target.split("/"):
                return SkillResult(success=False, error="Path traversal (..) not allowed in target_path")
            if normalized_target.startswith("/"):
                return SkillResult(success=False, error="target_path must be project-relative under game/")
            if not normalized_target.startswith(f"{data_dir.name}/"):
                normalized_target = f"{data_dir.name}/{normalized_target.lstrip('/')}"
            target_parts = Path(normalized_target)
            parts = list(target_parts.parts)
            if len(parts) < 3 or parts[0] != data_dir.name or target_parts.suffix.lower() != ".json":
                return SkillResult(
                    success=False,
                    error=f"target_path must point to a JSON entity under {data_dir.name}/<kind>/<id>.json",
                )
            target_kind = parts[-2]
            target_entity_id = target_parts.stem
            if normalized_entity_id and normalized_entity_id != target_entity_id:
                return SkillResult(
                    success=False,
                    error=f"entity_id '{normalized_entity_id}' does not match target_path id '{target_entity_id}'",
                )
            if not is_valid_entity_id(target_entity_id):
                return SkillResult(
                    success=False,
                    error=f"Invalid target_path id '{target_entity_id}': must match pattern [a-z0-9._-]+",
                )
            rel_path = normalized_target
        else:
            target_dir = data_dir / "character"
            existing_ids = {path.stem for path in target_dir.glob("*.json")} if target_dir.exists() else set()

        try:
            entity = build_entity_from_card_file(
                resolved_source,
                entity_id=target_entity_id,
                existing_ids=existing_ids,
            )
        except ValueError as exc:
            return SkillResult(success=False, error=str(exc))

        entity["kind"] = target_kind
        if name_override:
            entity["name"] = name_override

        if not rel_path:
            rel_path = f"{data_dir.name}/character/{entity['id']}.json"

        permission_path = self._path_for_permission(rel_path)
        perm_result = check_write_permission(
            permission_path,
            self.direct_write_globs,
            self.deny_globs,
            allow_protected_paths=self.allow_protected_paths,
        )
        if not perm_result.allowed:
            return SkillResult(success=False, error=perm_result.reason, denied_paths=[rel_path])

        target_path = self._resolve_path(rel_path)
        try:
            atomic_write_text(target_path, json.dumps(entity, indent=2, ensure_ascii=False))
        except Exception as exc:
            return SkillResult(success=False, error=f"Failed to write imported card: {exc}")

        return SkillResult(
            success=True,
            data={
                "id": entity["id"],
                "name": entity["name"],
                "kind": entity["kind"],
                "path": str(target_path.resolve()),
                "source_path": str(resolved_source.resolve()),
                "tags_count": len(entity.get("tags", [])),
            },
        )

    # M31: where an agent authors a soul before it exists in the world.
    # Project-local on purpose — the engine face only knows the project
    # directory; `~/.worldlines` is the launcher's.
    _SOUL_DRAFT_DIR = ".neonrp/soul-drafts"

    def _resolve_draft_soul_dir(self, sid: str) -> Path | None:
        """Find a soul folder for `sid`: the project draft first, then the
        library (``~/.worldlines/souls/<sid>``) — 任务 B1: casting a library
        character into this world is the same act as casting a fresh draft."""
        candidates = [
            self.root / self._SOUL_DRAFT_DIR / sid,
            self.root / sid,
        ]
        for cand in candidates:
            try:
                resolved = cand.resolve()
                # Never escape the project — `sid` comes from the model.
                resolved.relative_to(self.root.resolve())
            except (OSError, ValueError):
                continue
            if resolved.is_dir():
                return resolved
        # The library is only consulted for a plain sid — a path-ish token
        # ("../x", "a/b") must not be resolved against the user's home.
        if sid and "/" not in sid and "\\" not in sid and ".." not in sid:
            try:
                from neonrp.core.souls import SOUL_HOME

                lib = SOUL_HOME / sid
                if lib.is_dir() and (lib / "soul.json").is_file():
                    return lib
            except Exception:
                pass
            # Library folders made by /import or the launcher are named
            # `<sid>-<timestamp>`; resolve exactly the way `/cast` does.
            try:
                from neonrp.core.placement import PlacementError, resolve_soul_dir

                try:
                    found = resolve_soul_dir(sid)
                except PlacementError:
                    found = None
                if found is not None and found.is_dir():
                    return found
            except Exception:
                pass
        return None

    # Set to a callable in tests / headless runs to keep the OS out of it.
    _viewer_opener: Any = None

    def _skill_open_in_viewer(self, args: dict[str, Any]) -> SkillResult:
        """M31 B4 — show, don't describe.

        The TUI is a text surface by design (visualisation belongs to
        Obsidian and the web shell), so the way an agent "shows" you a map
        or a vault is to hand it to the viewer you already use. Opening is
        an agent *action* in the conversation, not a panel the TUI has to
        grow.
        """
        raw = str(args.get("path", "") or "").strip()
        if not raw:
            return SkillResult(success=False, error="open_in_viewer requires 'path'.")

        target = self._resolve_path(raw)
        try:
            resolved = target.resolve()
            # The path comes from the model — it opens things on a real
            # desktop, so it never leaves the project.
            resolved.relative_to(self.root.resolve())
        except (OSError, ValueError):
            return SkillResult(
                success=False, error=f"Path is outside the project: {raw}"
            )
        if not resolved.exists():
            return SkillResult(success=False, error=f"Nothing to open at: {raw}")

        opener = self._viewer_opener
        note = ""
        try:
            if opener is not None:
                opener(str(resolved))
            elif self._is_vault_path(resolved):
                # The vault's viewer is Obsidian, and a bare folder open would
                # land in Finder. Never restart the user's app from inside a
                # tool call — report instead, and the user can `/vault`.
                from neonrp.core.obsidian import open_vault
                from neonrp.core.vault import VAULT_DIRNAME

                vault_dir = self.root.resolve() / VAULT_DIRNAME
                extra: dict[str, Any] = {}
                if resolved != vault_dir:
                    extra["land_on"] = resolved.relative_to(vault_dir).as_posix()
                report = open_vault(vault_dir, restart=False, **extra)
                note = " ".join(report.lines())
            else:
                import webbrowser

                webbrowser.open(resolved.as_uri())
        except Exception as exc:  # noqa: BLE001 — a failed open is not fatal
            return SkillResult(success=False, error=f"Could not open viewer: {exc}")

        return SkillResult(
            success=True,
            data={
                "path": str(resolved),
                "kind": "directory" if resolved.is_dir() else "file",
                "reason": str(args.get("reason", "") or "").strip(),
                "note": note,
            },
        )

    def _is_vault_path(self, resolved: Path) -> bool:
        from neonrp.core.vault import VAULT_DIRNAME

        vault_dir = self.root.resolve() / VAULT_DIRNAME
        return resolved == vault_dir or vault_dir in resolved.parents

    def _skill_cast_soul(self, args: dict[str, Any]) -> SkillResult:
        """M31 — put an agent-authored soul into THIS world.

        Authoring the folder is the model's job (write_file + the
        `soul-authoring` skill). Registering it is not: the roster lives
        in `.neonrp/playthrough.json`, whose soul refs feed the turn's
        commit hash chain, so a hand-edit makes the next turn unlandable.
        Registration therefore goes through the same deterministic
        projector the `/cast` command uses.
        """
        sid = str(args.get("sid", "") or "").strip()
        if not sid:
            return SkillResult(success=False, error="cast_soul requires 'sid'.")
        if any(part in sid for part in ("..", "\\")) or Path(sid).is_absolute():
            return SkillResult(success=False, error=f"Invalid sid: {sid}")
        role = str(args.get("role", "npc") or "npc").strip().lower()
        if role not in ("npc", "player"):
            return SkillResult(
                success=False, error=f"Unsupported role: {role}. Use 'npc' or 'player'."
            )
        activate = bool(args.get("activate", True))
        location = str(args.get("location", "") or "").strip() or None

        soul_dir = self._resolve_draft_soul_dir(sid)
        if soul_dir is None:
            return SkillResult(
                success=False,
                error=(
                    f"No soul folder found for '{sid}'. Author it under "
                    f"{self._SOUL_DRAFT_DIR}/{sid}/ first (follow the soul-authoring "
                    f"skill for the folder shape), then call cast_soul again."
                ),
            )

        # Structural floor: the runtime needs a valid agents/manifest.json to
        # spin a soul up at all, and that file is template policy — never
        # LLM-authored (soul-authoring skill, §manifest). Idempotent.
        try:
            from neonrp.core.soul_authoring import ensure_soul_agent

            ensure_soul_agent(soul_dir)
        except Exception as exc:  # noqa: BLE001
            return SkillResult(
                success=False, error=f"Failed to ensure soul agent manifest: {exc}"
            )

        try:
            from neonrp.core.placement import (
                PlacementError,
                ensure_read_first,
                player_start_location,
                player_town_roster,
                project_avatar_multiagent,
                project_avatar_orchestrator,
                project_soul_as_npc,
                project_soul_into_town_npcs,
                project_soul_multiagent,
                seed_soul_location,
            )
            from neonrp.core.runtime_contract import is_soul_world

            # Structure decides the cast form, not the router flag: a world
            # that ships playthrough.json IS a soul world (runtime_contract
            # .is_soul_world), and `get_router_execution_mode` falls back to
            # "orchestrator" whenever the contract is missing — which would
            # flatten a soul into game/npc/ and orphan it.
            multi_agent = is_soul_world(self.root)
            exec_mode = "multi-agent" if multi_agent else "orchestrator"
        except Exception as exc:  # noqa: BLE001
            return SkillResult(success=False, error=f"Cast unavailable: {exc}")

        data: dict[str, Any] = {
            "sid": sid,
            "role": role,
            "execution_mode": exec_mode,
            "source": str(soul_dir),
        }
        # The roster file is what actually puts a character in the world, and
        # it is rewritten here rather than through write_file — so capture it
        # by hand, or the turn's ledger would list the draft files and omit
        # the one change that mattered.
        roster = self.root / ".neonrp" / "playthrough.json"
        roster_before = self._read_text_before(roster)
        # TODO #5: a cast character is also *registered* —
        # town-structured worlds keep who-is-where in game/towns/<T>/npcs.json
        # (what the world-agent reads; game/npc/<id>.json there is an orphan),
        # and a multi-agent soul gets a location so the roster shows it present.
        town_npcs, subnode = player_town_roster(self.root)
        extra_files: list[Path] = [p for p in (town_npcs,) if p is not None]
        gs_path = self.root / "game" / "meta" / "game-start.json"
        if town_npcs is not None and gs_path.is_file():
            extra_files.append(gs_path)
        extra_before = {p: self._read_text_before(p) for p in extra_files}
        try:
            if role == "player":
                if multi_agent:
                    ref = project_avatar_multiagent(self.root, soul_dir)
                    data["target"] = f"playthrough player '{ref.pid}'"
                    data["pid"] = ref.pid
                else:
                    data["target"] = str(project_avatar_orchestrator(self.root, soul_dir))
            elif not multi_agent:
                if town_npcs is not None:
                    npc_id = project_soul_into_town_npcs(
                        town_npcs, soul_dir, location=location or subnode, overwrite=True
                    )
                    data["target"] = str(town_npcs.relative_to(self.root)) + f"#{npc_id}"
                    data["location"] = location or subnode
                    data["town"] = town_npcs.parent.name
                    try:
                        ensure_read_first(self.root, town_npcs)
                    except Exception:  # noqa: BLE001 — roster entry is what matters
                        pass
                else:
                    start = location or player_start_location(self.root)
                    data["target"] = str(
                        project_soul_as_npc(self.root, soul_dir, location=start, overwrite=True)
                    )
                    data["location"] = start
            else:
                ref = project_soul_multiagent(
                    self.root, soul_dir, role="npc", activate=activate
                )
                data["sid"] = ref.sid
                data["instance_id"] = ref.instance_id
                data["target"] = f"souls/{ref.sid}-{ref.instance_id}"
                data["on_stage"] = activate
                try:
                    data["location"] = seed_soul_location(self.root, ref, location)
                except Exception as exc:  # noqa: BLE001
                    data["location_error"] = str(exc)
        except PlacementError as exc:
            return SkillResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return SkillResult(success=False, error=f"Cast failed: {exc}")

        roster_rel = ".neonrp/playthrough.json"
        data["change"] = self._record_change(
            roster_rel, roster_before, self._read_text_before(roster)
        )
        registered = []
        for p, before_text in extra_before.items():
            after = self._read_text_before(p)
            if after != before_text:
                rel = str(p.relative_to(self.root)) if p.is_relative_to(self.root) else str(p)
                registered.append(self._record_change(rel, before_text, after))
        if registered:
            data["registered"] = registered
        # 任务 B1: a cast character also lives in the library from now on, so
        # it can be brought into any other world (and shows in 角色库).
        try:
            from neonrp.core.souls import archive_soul

            data["library"] = str(archive_soul(soul_dir, sid))
        except Exception as exc:  # noqa: BLE001 — the cast itself succeeded
            data["library_error"] = str(exc)
        return SkillResult(success=True, data=data)

    # ── 任务 B2 · places as folders ─────────────────────────────────
    def _location_change_capture(self, rel_paths: list[str]) -> dict[str, str | None]:
        return {rel: self._read_text_before(self.root / rel) for rel in rel_paths}

    def _skill_new_location(self, args: dict[str, Any]) -> SkillResult:
        from neonrp.core.locations import LocationError, create_location, world_map_path

        name = str(args.get("name", "") or "").strip()
        if not name:
            return SkillResult(success=False, error="new_location requires 'name'.")
        from neonrp.core.locations import town_ids, town_map_file

        map_rel = world_map_path(self.root)
        map_rel_s = str(map_rel.relative_to(self.root)) if map_rel.is_relative_to(self.root) else str(map_rel)
        tracked = [map_rel_s]
        for tid in town_ids(self.root):
            tm = town_map_file(self.root, tid)
            if tm.is_file():
                tracked.append(str(tm.relative_to(self.root)) if tm.is_relative_to(self.root) else str(tm))
        before = self._location_change_capture(tracked)
        try:
            result = create_location(
                self.root,
                name=name,
                loc_id=str(args.get("id", "") or "").strip() or None,
                summary=str(args.get("summary", "") or ""),
                connections=[str(c) for c in (args.get("connections") or []) if str(c).strip()],
                parent=str(args.get("parent", "") or "").strip() or None,
                tags=[str(t) for t in (args.get("tags") or []) if str(t).strip()],
                notes=str(args.get("notes", "") or ""),
                town=str(args.get("town", "") or "").strip() or None,
            )
        except LocationError as exc:
            return SkillResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return SkillResult(success=False, error=f"new_location failed: {exc}")
        changes = []
        for rel in result.get("written", []):
            if rel in before:
                continue
            changes.append(self._record_change(rel, None, self._read_text_before(self.root / rel)))
        for rel in tracked:
            after = self._read_text_before(self.root / rel)
            if after != before[rel]:
                changes.append(self._record_change(rel, before[rel], after))
        result["changes"] = [c for c in changes if c]
        return SkillResult(success=True, data=result)

    def _skill_update_location(self, args: dict[str, Any]) -> SkillResult:
        from neonrp.core.locations import LocationError, location_record_path, resolve_location_id, update_location, world_map_path

        token = str(args.get("id", "") or "").strip()
        if not token:
            return SkillResult(success=False, error="update_location requires 'id'.")
        rid = resolve_location_id(self.root, token)
        if rid is None:
            return SkillResult(success=False, error=f"no such place: {token}")
        rec = location_record_path(self.root, rid)
        map_rel = world_map_path(self.root)
        rels = [str(p.relative_to(self.root)) if p.is_relative_to(self.root) else str(p) for p in (rec, map_rel) if p]
        before = self._location_change_capture(rels)
        try:
            result = update_location(
                self.root,
                rid,
                name=args.get("name"),
                summary=args.get("summary"),
                tags=args.get("tags"),
                add_connections=[str(c) for c in (args.get("add_connections") or []) if str(c).strip()],
                remove_connections=[str(c) for c in (args.get("remove_connections") or []) if str(c).strip()],
                notes_append=args.get("notes_append"),
                parent=args.get("parent"),
            )
        except LocationError as exc:
            return SkillResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return SkillResult(success=False, error=f"update_location failed: {exc}")
        result["changes"] = [
            c for c in (self._record_change(rel, before[rel], self._read_text_before(self.root / rel)) for rel in rels) if c
        ]
        return SkillResult(success=True, data=result)

    def _skill_ensure_playable_scaffold(self, args: dict[str, Any]) -> SkillResult:
        """Ensure packaged play scaffold assets exist and active-agent state is canonical."""
        template_name = str(args.get("template_name", "") or DEFAULT_TEMPLATE_NAME).strip() or DEFAULT_TEMPLATE_NAME
        active_agent = str(args.get("active_agent", "") or "").strip() or None
        force = bool(args.get("force", False))

        try:
            scaffold_targets = list_playable_scaffold_targets(self.root, template_name=template_name)
        except Exception as exc:
            return SkillResult(success=False, error=f"Failed to inspect scaffold targets: {exc}")
        denied_paths: list[str] = []
        for rel_path in scaffold_targets:
            permission_path = self._path_for_permission(rel_path)
            perm_result = check_write_permission(
                permission_path,
                self.direct_write_globs,
                self.deny_globs,
                allow_protected_paths=self.allow_protected_paths,
            )
            if not perm_result.allowed:
                denied_paths.append(rel_path)

        if denied_paths:
            denied_list = ", ".join(denied_paths)
            return SkillResult(
                success=False,
                error=f"Write blocked by direct_write_globs/deny_globs for scaffold targets: {denied_list}",
                denied_paths=denied_paths,
            )

        try:
            result = ensure_playable_runtime_scaffold(
                self.root,
                template_name=template_name,
                force=force,
                active_agent_id=active_agent,
            )
        except Exception as exc:
            return SkillResult(success=False, error=f"Failed to ensure playable scaffold: {exc}")

        absolute_files = [str((self.root / rel_path).resolve()) for rel_path in result.files]
        return SkillResult(
            success=True,
            data={
                "path": str((self.root / result.active_agent_path).resolve()),
                "files": absolute_files,
                "relative_files": result.files,
                "active_agent": result.active_agent,
                "created_agent_ids": result.created_agent_ids,
            },
        )

    def _skill_grep(self, args: dict[str, Any]) -> SkillResult:
        """Execute grep skill.

        Search file contents using regex.
        Returns matching lines with file paths and line numbers.
        Max 50 results, lines truncated to 500 chars.
        """
        pattern = args.get("pattern", "")
        base_path = args.get("path", "")
        glob_pattern = args.get("glob", "**/*")
        max_results = args.get("max_results", 50)

        if not pattern:
            return SkillResult(success=False, error="pattern is required")

        # Compile regex
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return SkillResult(success=False, error=f"Invalid regex pattern: {e}")

        # Reject path traversal
        if ".." in glob_pattern:
            return SkillResult(success=False, error="Path traversal (..) not allowed in glob")
        if base_path and ".." in base_path:
            return SkillResult(success=False, error="Path traversal (..) not allowed in path")

        # Determine search root
        if base_path:
            search_root = self.root / base_path
        else:
            search_root = self.root

        if not search_root.exists():
            return SkillResult(success=False, error=f"Path not found: {base_path or '.'}")

        # Collect matching lines
        results = []
        denied_paths = []
        max_line_length = 500

        try:
            # Get files matching glob
            for file_path in search_root.rglob(
                glob_pattern.replace("**/", "").replace("**", "*") if "**" in glob_pattern else glob_pattern
            ):
                if len(results) >= max_results:
                    break

                if not file_path.is_file():
                    continue

                # Get relative path
                try:
                    rel_path = str(file_path.relative_to(self.root)).replace("\\", "/")
                except ValueError:
                    continue

                # Check read permission
                perm_result = self._check_path_permission(rel_path)
                if not perm_result.allowed:
                    denied_paths.append(rel_path)
                    continue

                # Search file contents
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for line_num, line in enumerate(content.splitlines(), 1):
                        if len(results) >= max_results:
                            break
                        if regex.search(line):
                            # Truncate long lines
                            display_line = line[:max_line_length]
                            if len(line) > max_line_length:
                                display_line += "..."
                            results.append(
                                {
                                    "file": rel_path,
                                    "line_number": line_num,
                                    "line_content": display_line,
                                }
                            )
                except Exception:
                    # Skip files that can't be read
                    continue

        except Exception as e:
            return SkillResult(success=False, error=f"Grep error: {e}")

        return SkillResult(
            success=True,
            data={"matches": results, "count": len(results), "capped": len(results) >= max_results},
            denied_paths=denied_paths,
        )

    def _log_call(self, skill_name: str, args: dict[str, Any], result: SkillResult) -> None:
        """Log a skill call for auditing."""
        # Build result summary (bounded to 500 chars)
        if result.success:
            if isinstance(result.data, list):
                summary = f"Returned {len(result.data)} items"
            elif isinstance(result.data, dict):
                summary = f"Returned dict with keys: {list(result.data.keys())[:5]}"
            else:
                summary = str(result.data)[:500]
        else:
            summary = f"Error: {result.error}"

        call = SkillCall(
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=self.run_id,
            agent_id=self.agent_id,
            skill_name=skill_name,
            args=args,
            result_summary=summary[:500],
            error=result.error,
            duration_ms=result.duration_ms,
            denied_paths=result.denied_paths,
        )

        self._calls.append(call)

    def save_audit_log(self) -> Path:
        """Save all skill calls to JSONL audit log.

        Returns:
            Path to the saved log file
        """
        logs_dir = get_neonrp_dir(self.root) / "logs" / "skills"
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_path = logs_dir / f"{self.run_id}.jsonl"

        with open(log_path, "w", encoding="utf-8") as f:
            for call in self._calls:
                record = {
                    "timestamp": call.timestamp,
                    "run_id": call.run_id,
                    "agent_id": call.agent_id,
                    "skill_name": call.skill_name,
                    "args": call.args,
                    "result_summary": call.result_summary,
                    "error": call.error,
                    "duration_ms": call.duration_ms,
                    "denied_paths": call.denied_paths,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return log_path
