"""TUI command parser for `/` commands (Claude Code style)."""

from dataclasses import dataclass
from typing import Optional
import shlex


@dataclass
class ParsedCommand:
    """Result of parsing a `/` command."""

    command: str
    args: list[str]
    options: dict[str, str]
    raw: str
    error: Optional[str] = None


def parse_command(input_text: str) -> ParsedCommand:
    """Parse a `:` command string.

    Examples:
        :validate -> ParsedCommand(command="validate", args=[], options={})
        :index build -> ParsedCommand(command="index", args=["build"], options={})
        :find tokyo -> ParsedCommand(command="find", args=["tokyo"], options={})
        :sandbox new test-1 --from save_001 -> ParsedCommand(
            command="sandbox", args=["new", "test-1"], options={"from": "save_001"}
        )

    Args:
        input_text: Command string (with or without leading `:`)

    Returns:
        ParsedCommand with parsed command, args, and options
    """
    # Remove leading `/` or `:` if present (support both for compatibility)
    text = input_text.strip()
    if text.startswith("/") or text.startswith(":"):
        text = text[1:]

    if not text:
        return ParsedCommand(command="", args=[], options={}, raw=input_text, error="Empty command")

    try:
        # Use shlex for proper quote handling
        tokens = shlex.split(text)
    except ValueError as e:
        return ParsedCommand(command="", args=[], options={}, raw=input_text, error=f"Parse error: {e}")

    if not tokens:
        return ParsedCommand(command="", args=[], options={}, raw=input_text, error="Empty command")

    command = tokens[0]
    args = []
    options = {}

    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            # Option with value
            key = token[2:]
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                options[key] = tokens[i + 1]
                i += 2
            else:
                options[key] = "true"
                i += 1
        elif token.startswith("-") and len(token) == 2:
            # Short option
            key = token[1]
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                options[key] = tokens[i + 1]
                i += 2
            else:
                options[key] = "true"
                i += 1
        else:
            args.append(token)
            i += 1

    return ParsedCommand(command=command, args=args, options=options, raw=input_text)


# 在编的命令(docs/COMMANDS.md)。退役的那批住在 `legacy_commands.py`:
# 能力保留、仍可执行,但不进补全与 /help —— 它们不该占新用户的心智带宽,
# 而集中在一处也让将来真要删时是一刀的事。
COMMANDS = {
    "find": {"args": 1, "args_hint": "<keyword>", "help": "Search entities by keyword"},
    # 取代 /worlds /worldlines /continue 三条(docs/COMMANDS.md)。它们各答
    # 一半,而且 /worlds 并不「打开」世界 —— 它把模板 scaffold 进当前工作区。
    "open": {
        "args": "?",
        "args_hint": "[世界|存档]",
        "help": "接着玩一个存档,或用一个世界开新局(不带参数=看有哪些;--build 进自己世界的工坊)",
    },
    # 从零建一个自己的世界:源落 ~/.worldlines/worlds/<名字>,进工坊交给
    # agent 著述。老义(初始化当前目录)是命令行 `neonrp init` 的事。
    "init": {
        "args": "?",
        "args_hint": "[世界]",
        "help": "用一个世界开新局(不带参数=选;从零建空白世界在选单里;读存档是 /load 与 /open)",
    },
    # 从上方看这个世界:投影成 Obsidian vault 并一键打开(画布=层级+立绘)。
    "vault": {
        "args": "?",
        "args_hint": "[build]",
        "help": "在 Obsidian 里打开这个世界的观察台(build=只投影不开窗)",
    },
    # 世界与角色共用一个入口(「import 是世界和角色合并
    # 一个入口」)。用户手里只有一个文件,不该先替我们判断它属于哪一类 ——
    # 分派交给 `_cmd_import`。旧的 `sillytavern-card` 子命令不再露出,但仍
    # 受理(`--import-card` 排的启动命令还是那个形状)。
    "import": {
        "args": 1,
        "args_hint": "<文件>",
        "help": "导入世界包或角色卡(按内容分派)",
    },
    # 角色的四个动词(docs/COMMANDS.md)。它们挂在**角色**上而不是会话上,
    # 所以命令名本身就说明你站在哪一侧:create 在 build 造,cast 在 play 迎。
    "create": {
        "args": "?",
        "args_hint": "<名字>",
        "help": "在 build 模式里造一个新角色(交给 agent 著述)",
    },
    "remove": {
        "args": 1,
        "args_hint": "<角色>",
        "help": "让角色从这个世界消失(来源保留,可再 /new 回来)",
    },
    "reset": {
        "args": 1,
        "args_hint": "<角色>",
        "help": "把角色清回出厂状态(忘掉记忆与轨迹,著述内容不动)",
    },
    "cast": {
        "args": "?",
        "args_hint": "[角色] [npc|player]",
        "help": "把已建好的角色迎进这个世界(不带参数=列出可用角色)",
    },
    "who": {
        "args": "?",
        "args_hint": "[角色]",
        "help": "进一个角色的 context:它在哪、记得什么、最近几回合做了什么;t 直聊,输入一句替它行动(不带参数=选)",
    },
    "save": {"args": "?", "args_hint": "[save_name]", "help": "Create save snapshot [name]"},
    "load": {"args": "?", "args_hint": "[存档|快照]", "help": "读存档(~/.worldlines/plays 里的一局)或本局快照;不带参数=选"},
    "undo": {"args": "?", "args_hint": "[list|<turn>]", "help": "Undo last change · list = this line's turns · <turn> = a new line from that turn"},
    "redo": {"args": 0, "help": "Redo last undone change"},
    # `new` 的旧义(开一个新对话)已让位给角色动词(docs/COMMANDS.md)。
    # 清当前对话仍是 /clear;开新会话这件事本身与它几乎重合,不再单列。
    # M31: only build ↔ play are player-facing. `sandbox` still parses
    # (engine-internal dry-run plumbing) but is no longer advertised.
    "mode": {"args": "?", "args_hint": "[build|play]", "help": "Switch between build and play in this world"},
    "clear": {"args": 0, "help": "Clear conversation history"},
    "help": {"args": 0, "help": "Show help"},
    "quit": {"args": 0, "help": "Exit TUI"},
    "q": {"args": 0, "help": "Exit TUI (alias)"},
    # WorldLines commands
    "update": {
        "args": "?",
        "args_hint": "[check|apply|status|channel <name>]",
        "subcommands": ["check", "apply", "status", "channel"],
        "help": "Check / apply neonrp updates",
    },
    # One Worldlines account — Jev (the judge), the model relay, uploading worlds. Optional: the engine is free.
    # one command (the live table stays small — ≤ 25 since 10-08): /login · /login code (no browser) · /login status · /login out
    "login": {"args": "?", "args_hint": "[code|status|out]", "help": "Worldlines account (optional: Jev judge · model relay · world uploads) — sign in / code / status / out"},  # localized: cmd.login.help
    "settings": {
        "args": 0,
        "help": "Open unified model / api key / discord settings",
    },
    # 10-08 the two-beat play (tui/play_commands.py) — three commands, the rest as sub-items (live table ≤ 25)
    "status": {"args": "?", "args_hint": "[player|agents|plan|dice|settlement|contract|account|usage|room]",
               "subcommands": ["player", "agents", "plan", "dice", "settlement", "contract", "account", "usage", "room"],
               "help": "Player / Agent status · the plan board · dice · the ending · the play contract · the networked room"},
    "lang": {"args": "?", "args_hint": "[zh|en|ja|ko]", "subcommands": ["zh", "en", "ja", "ko"], "help": "The language this run is narrated in"},
    "dev": {"args": "?", "args_hint": "[graph|dry-run|beats|template|validate|mcp|bridge|debug]",
            "subcommands": ["graph", "dry-run", "beats", "template", "validate", "mcp", "bridge", "debug"],
            "help": "Orchestration graph · dry run one beat · beat skeleton in the prose · templates"},
}


# ---------------------------------------------------------------------------
# 任务 B3 · world-registered play actions
#
# A world can declare its own *actions* — 移动 / 交谈 / 调查 … — and they show
# up as `/` commands next to ours. Two kinds must stay visibly apart: the
# **play** actions the world registers (green, the play accent) and the
# **tool** commands we ship (red, the build accent). Registration lives in
# `game/meta/actions.json` (world content, so it travels with the world):
#
#     {"actions": [{"name": "go", "help": "走到某个地点", "args_hint": "<地点>",
#                   "prompt": "我走向{args}。"}]}
#
# Running one is a thin trigger, exactly like /create: the templated prompt is
# sent as the player's own words. The engine never grows a second behaviour.
# ---------------------------------------------------------------------------
ACTIONS_FILE_REL = ("game", "meta", "actions.json")
WORLD_ACTIONS: dict[str, dict] = {}


def load_world_actions(root) -> dict[str, dict]:
    """Read and validate the world's action table. Bad entries are skipped,
    never fatal; names that collide with a built-in or retired command are
    dropped (ours win — a world must not be able to shadow /open)."""
    from pathlib import Path

    from neonrp.core.play_menu import world_actions  # the same table the web front end completes from (10-14)
    from neonrp.tui.legacy_commands import legacy_spec

    try:
        rows = world_actions(Path(root))
    except (OSError, ValueError, TypeError):
        return {}
    out: dict[str, dict] = {}
    for e in rows:
        name = e["name"]
        if name in COMMANDS or legacy_spec(name) is not None or name in out:
            continue
        out[name] = {"kind": "play", "args": "?", "args_hint": e["args_hint"], "help": e["help"], "prompt": e["prompt"]}
    return out


def register_world_actions(actions: dict[str, dict]) -> None:
    WORLD_ACTIONS.clear()
    WORLD_ACTIONS.update({k: dict(v) for k, v in (actions or {}).items() if k not in COMMANDS})


def clear_world_actions() -> None:
    WORLD_ACTIONS.clear()


def command_kind(command: str) -> str:
    """'play' for a world-registered action, 'legacy' for a retired one,
    'tool' for everything else of ours."""
    if command in WORLD_ACTIONS:
        return "play"
    if command not in COMMANDS:
        from neonrp.tui.legacy_commands import is_legacy

        if is_legacy(command):
            return "legacy"
    return "tool"


def command_spec(command: str) -> dict | None:
    if command in COMMANDS:
        return COMMANDS[command]
    if command in WORLD_ACTIONS:
        return WORLD_ACTIONS[command]
    from neonrp.tui.legacy_commands import legacy_spec

    return legacy_spec(command)


def render_action_prompt(command: str, args: list[str]) -> str:
    """The player's words for an action: `{args}` is filled in; without the
    placeholder, arguments are appended."""
    spec = WORLD_ACTIONS.get(command) or {}
    prompt = str(spec.get("prompt", "") or "")
    joined = " ".join(a for a in args if a).strip()
    if "{args}" in prompt:
        return prompt.replace("{args}", joined)
    return (prompt + (" " + joined if joined else "")).strip()


def localized_spec(command: str, locale: str | None = None) -> dict:
    """A command's spec with `help` / `args_hint` in the UI language when
    i18n has them (`cmd.<name>.help` / `cmd.<name>.args`); world actions
    and anything without a translation come back as authored.
    「英语环境里输入 / 后面的 suggestion 都是汉字」."""
    base = dict(command_spec(command) or {})
    if not base or command in WORLD_ACTIONS or not locale:
        return base
    from neonrp.tui.i18n import get_message

    help_key, args_key = f"cmd.{command}.help", f"cmd.{command}.args"
    help_txt = get_message(locale, help_key)
    if help_txt != help_key:
        base["help"] = help_txt
    args_txt = get_message(locale, args_key)
    if args_txt != args_key:
        base["args_hint"] = args_txt
    return base


def get_command_args_hint(command: str, spec: dict | None = None, locale: str | None = None) -> str:
    """Get a display placeholder hint for command arguments."""
    cmd_spec = spec if spec is not None else (localized_spec(command, locale) if locale else (command_spec(command) or {}))

    explicit_hint = cmd_spec.get("args_hint")
    if isinstance(explicit_hint, str) and explicit_hint.strip():
        return explicit_hint

    if "subcommands" in cmd_spec:
        return "[" + "|".join(cmd_spec["subcommands"]) + "]"
    if cmd_spec.get("args") == 1:
        return f"[{command}]"
    if cmd_spec.get("args") == "?":
        return "[name]"
    return ""


def get_subcommand_suggestions(command: str, prefix: str = "") -> list[str]:
    """Get subcommand suggestions for a given command.

    Args:
        command: The parent command name
        prefix: Optional prefix to filter subcommands

    Returns:
        List of matching subcommand names
    """
    cmd_spec = COMMANDS.get(command, {})
    subcmds = cmd_spec.get("subcommands", [])
    if prefix:
        return [s for s in subcmds if s.startswith(prefix.lower())]
    return subcmds


def get_command_suggestions(prefix: str) -> list[str]:
    """Get command suggestions for fuzzy matching.

    Args:
        prefix: Partial command input

    Returns:
        List of matching command names
    """
    prefix = prefix.lower()
    names = list(COMMANDS.keys()) + [n for n in WORLD_ACTIONS if n not in COMMANDS]
    if not prefix:
        return names

    hits = [cmd for cmd in names if cmd.startswith(prefix)]
    # Retired commands (legacy_commands.py) stay out of the bare `/` list but
    # answer to a typed prefix, greyed —「/auth 不在
    # suggestion 里面」. They still run; the panel just says they're retired.
    from neonrp.tui.legacy_commands import LEGACY_COMMANDS

    hits += [cmd for cmd in LEGACY_COMMANDS if cmd.startswith(prefix) and cmd not in hits]
    return hits


def validate_command(parsed: ParsedCommand) -> Optional[str]:
    """Validate a parsed command.

    Args:
        parsed: ParsedCommand to validate

    Returns:
        Error message if invalid, None if valid
    """
    if parsed.error:
        return parsed.error

    if not parsed.command:
        return "Empty command"

    if parsed.command in WORLD_ACTIONS:
        return None  # a world action takes free text; nothing to validate
    if parsed.command not in COMMANDS:
        # 退役命令仍然可用,只是不再露出:补全和 /help 只读主表,所以它们
        # 看不见,但敲出来照样执行(docs/COMMANDS.md 的「归档」而非「删除」)。
        from neonrp.tui.legacy_commands import legacy_spec, removed_notice

        gone = removed_notice(parsed.command)
        if gone:  # deleted — where its job went
            return gone
        retired = legacy_spec(parsed.command)
        if retired is None:
            suggestions = get_command_suggestions(parsed.command)
            if suggestions:
                return f"Unknown command: {parsed.command}. Did you mean: {', '.join(suggestions[:3])}?"
            return f"Unknown command: {parsed.command}. Type /help for available commands."
        cmd_spec = retired
    else:
        cmd_spec = COMMANDS[parsed.command]

    # Check subcommand if required
    if "subcommands" in cmd_spec:
        if not parsed.args:
            return f"Command '{parsed.command}' requires a subcommand: {', '.join(cmd_spec['subcommands'])}"
        if parsed.args[0] not in cmd_spec["subcommands"]:
            return f"Unknown subcommand '{parsed.args[0]}'. Valid options: {', '.join(cmd_spec['subcommands'])}"

    return None


def format_help(locale: str | None = None) -> str:
    """Help in two sections: our tools, then the world's play actions."""
    lines = ["[bold]Available Commands:[/]", ""]
    if WORLD_ACTIONS:
        lines.append("[bold]── 工具 · tools ──[/]")
    for cmd, _raw in sorted(COMMANDS.items()):
        spec = localized_spec(cmd, locale) if locale else _raw
        help_text = spec.get("help", "")
        if "subcommands" in spec:
            help_text += f" ({', '.join(spec['subcommands'])})"
        lines.append(f"  [cyan]/{cmd}[/] - {help_text}")
    if WORLD_ACTIONS:
        lines.append("")
        lines.append("[bold]── 行动 · play ──[/]  [dim]这个世界登记的游玩行动(game/meta/actions.json)[/]")
        for cmd, spec in sorted(WORLD_ACTIONS.items()):
            hint = f" {spec['args_hint']}" if spec.get("args_hint") else ""
            lines.append(f"  [green]/{cmd}[/][dim]{hint}[/] - {spec.get('help', '')}")
    return "\n".join(lines)
