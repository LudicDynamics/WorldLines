"""退役的斜杠命令 —— 能力还在,但不再占心智带宽。

`docs/COMMANDS.md` 把命令面从 48 条收到二十条上下,判据是「命令只做 agent
做不了、或不该做的事」。剩下这些不是废的:排障时 `/replay` `/index` 会救命,
`/validate` 有 CLI 等价物但在世界里敲更顺手。它们只是**不该出现在新用户的
补全列表里**。

所以它们集中在这一个文件:主表(`commands.COMMANDS`)不收,补全与 `/help`
读主表所以自然看不见;`_handle_slash_command` 在主表未命中时回落到这里。
将来真要删,删这一个文件加一行回落即可 —— 不必再去一万三千行里翻
(「可以 archive,并且打包整理到一个内容,方便以后删除」)。

分四组,注明各自为什么退役:

- **工程排障**:大多有 CLI 等价物,只在出事时用
- **已被合并**:功能仍在,只是入口换了名字(见 `docs/COMMANDS.md` 的取代表)
- **会话管理**:几条做的事对用户几乎一样,只留 `/clear`
- **命令行时代遗留**:属于 `neonrp` / `worldlines` 那一侧,不属于世界内
"""

from __future__ import annotations

from typing import Any

# 每条附一句「为什么退役」,而不只是列个名字 —— 将来删它的人需要知道
# 当初为什么留、现在为什么能删。
LEGACY_COMMANDS: dict[str, dict[str, Any]] = {
    # 看过全表后只留这七条(仍可直接敲,不进补全;常用入口在 /dev 与 /status 下)
    "validate": {"args": 0, "help": "检查世界是否可玩", "why": "排障;也在 /dev validate"},
    "mcp": {"args": "?", "args_hint": "[status|restart]", "subcommands": ["status", "restart"], "help": "MCP 服务管理",
            "why": "集成;也在 /dev mcp"},
    "bridge": {"args": "?", "help": "外部桥接", "why": "集成,不常用;也在 /dev bridge"},
    "debug": {"args": 0, "help": "切换调试输出", "why": "与 /verbose 同一个开关;合并为 /dev debug"},
    "verbose": {"args": "?", "args_hint": "[on|off|status]", "help": "详细日志", "why": "合并为 /dev debug"},
    "stats": {"args": 0, "help": "对话统计", "why": "在 /status usage"},
    "config": {"args": "?", "help": "读写配置", "why": "平时用 /settings;原始配置读写留着"},
}

# 这些删掉了 —— 功能已被别的命令覆盖。敲了不报「未知命令」,说去哪。
REMOVED_COMMANDS: dict[str, str] = {
    "models": "/settings", "auth": "/settings", "wl-model": "/settings", "locale": "/settings",
    "worlds": "/open", "worldlines": "/open", "continue": "/open", "game": "/open · /create",
    "load-world": "/import", "context": "/find", "export-world": "neonrp export-world",
    "branch": "/undo list · /undo <回合>", "run": "直接说话", "copy": "F6",
    "index": "引擎自动维护", "replay": "/dev dry-run", "agent": "直接说话", "skills": "agent 自己会用",
    "files": "命令行 git", "compact": "/clear", "sessions": "/load",
}


def is_legacy(name: str) -> bool:
    """这条命令是否已退役(仍可执行,只是不再露出)。"""
    return name in LEGACY_COMMANDS


def legacy_spec(name: str) -> dict[str, Any] | None:
    return LEGACY_COMMANDS.get(name)


def removed_notice(name: str) -> str | None:
    """A deleted command (10-08): where its job went."""
    to = REMOVED_COMMANDS.get(name)
    return f"/{name} 已删除 —— 用 {to}。" if to else None


def legacy_notice(name: str) -> str | None:
    """给用户的一行提示:它还在,但已经不是推荐入口了。"""
    spec = LEGACY_COMMANDS.get(name)
    if not spec:
        return None
    return f"/{name} 已退役({spec['why']}),仍可使用。见 docs/COMMANDS.md。"
