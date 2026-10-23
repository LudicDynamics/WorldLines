"""NeonRP TUI — Claude Code style conversational interface.

M9-T5: Single-pane conversational TUI replacing 4-pane layout as default.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal

import regex as regex_re
from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from rich.rule import Rule
from textual.app import App, ComposeResult, ScreenStackError
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual import events
from textual.message import Message
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.widgets.selection_list import Selection
from textual.widgets import (
    Button, Collapsible, Input, Markdown, RadioButton, RadioSet,
    Select, SelectionList, Static, TextArea,
)
from textual.worker import get_current_worker

from neonrp.core.conversation import (
    ASK_USER_CANCELLED_RESPONSE,
    ConversationMode,
    ConversationSession,
    ConversationTurnResult,
)

AppMode = ConversationMode

# M31:模式要能被余光认出来,而不是去读一个词。build 与 play 各有一个
# 主色,同时染输入提示符和状态栏的模式字——你打字时看的就是这两处。
# build 是红:在这一侧你改的是世界本身,那是有后果的动作,值得被看见
# (「从绿色的 play 进入红色的 build」)。错误色是灰调的
# #cf7f7f,所以这支饱和红不会跟报错混;它与提示符原本的 #2ed573 同属
# flat-ui 家族。
MODE_ACCENTS: dict[str, str] = {
    "build": "#ff4757",
    "play": "#18FF82",
    "sandbox": "#A78BFA",  # 引擎内部干跑;正常不该在 TUI 里见到
}
MODE_ACCENT_DIM: dict[str, str] = {
    "build": "#4d1a20",
    "play": "#173b23",
    "sandbox": "#2e2545",
}


def mode_accent(mode: str | None, *, dim: bool = False) -> str:
    """The colour that says which half of the product you are in."""
    table = MODE_ACCENT_DIM if dim else MODE_ACCENTS
    return table.get(str(mode or "build"), table["build"])
from neonrp.core.debug_flag import DEBUG_ENABLED
from neonrp.core.config import (
    create_default_config_template,
    get_api_key,
    get_config_path,
    get_user_config_path,
    load_config,
    resolve_provider,
)
from neonrp.core.manifest import Manifest
from neonrp.core.mcp_pool import MCPPool
from neonrp.core.paths import get_data_dir_name, get_manifest_path, get_neonrp_dir, get_game_dir
from neonrp.core.runtime_contract import get_router_execution_mode, get_startup_entry_agent
from neonrp.core.session import get_session_path
from neonrp.core.skill_loader import SkillLoader
from neonrp.core.state import get_auto_apply
from neonrp.core.storage import atomic_write_json
from neonrp.tui.commands import COMMANDS, get_command_suggestions, get_subcommand_suggestions, parse_command, WORLD_ACTIONS, command_kind, render_action_prompt, localized_spec, command_spec
from neonrp.tui.commands import get_command_args_hint
from neonrp.tui.build_surface import BuildStage
from neonrp.tui.i18n import get_message, localize_mode, resolve_locale
from neonrp.tui.palette import CommandPalette
from neonrp.tui.game_state_panel import GameStatePanel
from neonrp.tui.map_panel import MapPanel, MapView
from neonrp.tui.location_header import LocationHeader
from neonrp.tui.portrait import PortraitPanel

try:
    from neonrp import __version__ as _NEONRP_VERSION
except Exception:
    _NEONRP_VERSION = "0.0.0"

LOCAL_SLASH_COMMANDS = {
    "status",  # 10-08 the two-beat play (tui/play_commands.py)
    "lang",
    "dev",
    "login",
    "mode",
    "who",
    "cast",
    "create",
    "remove",
    "import",
    "open",
    "init",
    "vault",
    "reset",
    "clear",
    "mcp",
    "help",
    "undo",
    "save",
    "load",
    "stats",
    "new",
    "verbose",
    "config",
    "quit",
    "q",
    "debug",
    "update",
    "settings",
    "bridge",
}

CLI_FORWARD_COMMANDS = {
    # `init` 曾透传给 CLI(初始化当前目录)。它现在是本地命令:在
    # ~/.worldlines/worlds 里建一个新世界并进工坊,见 `_cmd_init`。
    "validate",
    "find",
    "redo",
    # `import` 曾在这里透传给 CLI,只认得酒馆卡子命令。它现在是本地命令
    # (按内容分派世界包/角色卡),见 `_cmd_import`。
}


@dataclass
class _ReopenRequest:
    """「换一局」的交接单。

    `self.root` 在 app 构造时定死,session、引擎、每个控件都挂在它上面,
    全程没有任何地方重绑它。所以 `/open` 换世界不能改字段 —— 它退出当前
    app,把新 root 交给 `run_tui`,由后者起一局新的。与 launcher 的交接
    (`app.exit(selection)` → CLI 再启动)是同一套路子。
    """

    root: Path
    continue_session: bool = False
    # None = 沿用当前 app 的模式;`/init` 要求进 build,`/open <世界>` 进 play。
    mode: AppMode | None = None
    # 新一局挂载后要执行的输入:`/…` 走命令,其余当作交给 agent 的第一句话
    # (`/init` 用它把世界设定递给 build agent)。
    startup_commands: list[str] | None = None


@dataclass
class WorldLinesLaunchSelection:
    # "continue"        — resume an existing started game (run_tui continue_session=True)
    # "new"             — scaffold a fresh game from a builtin world template
    # "launch_existing" — launch an already-extracted but never-started game
    #                     directory (e.g. fresh WorldHub download or fresh .zip
    #                     load), running the new-game startup handoff so the
    #                     world-agent reads game-start.json and plays the opening.
    mode: Literal["continue", "new", "launch_existing"]
    preset_id: str
    runtime_mode: AppMode
    game_path: Path | None = None
    world_id: str | None = None
    player_profile: dict[str, Any] | None = None
    # Populated when the user picked "Create new world" or "Import world";
    # CLI launcher inspects this to run the relevant built-in skill.
    world_intent: dict[str, Any] | None = None
    # Soul-side analogue (M16): set when the user picked "create new
    # character"; carries the soul-authoring intent the same way
    # world_intent carries world-game-authoring.
    soul_intent: dict[str, Any] | None = None
    # Casting ②: soul dirs to cast INTO the world as NPCs at launch
    # (via neonrp.core.placement). Empty = none.
    bring_in_souls: tuple[str, ...] = ()
    # Casting ②: chosen play mode applied to runtime_contract at launch.
    engine_mode: str = "orchestrator"
    # First words handed to the agent when the launch lands in build mode
    # (创作世界 / 创作角色 from the dashboard).
    startup_commands: tuple[str, ...] = ()
    # Casting ②: per-soul-path placement overrides (user-edited fields from
    # the casting preview — role_in_world / why_here / relationship_to_player
    # / current_goal).
    npc_placements: dict[str, dict[str, Any]] | None = None
    # Casting ②: per-soul-path starting-location overrides (user-picked
    # from the world template node list). A missing key = co-locate with
    # the player (default).
    npc_locations: dict[str, str] | None = None
    # Where to render this session: "tui" (terminal) or "web" (browser
    # play+observe via `neonrp web`). Only play mode offers the choice.
    render_surface: str = "tui"
    # World import authors the slice in build mode; when True, relaunch the
    # finished world in play (render_surface) once the build session exits.
    play_after_build: bool = False


def _runtime_state(runtime: Any) -> str:
    """Derive a display state for one ``CharacterRuntime`` (M18 Phase E1).

    Pure read of the *already-computed* world-agent state — this function
    NEVER awaits a task, sets ``cancel_event``, or touches the registry. It
    only inspects what the world-agent has already produced so the lane is a
    cosmetic mirror, not a second source of truth:

    * no task yet ⇒ ``idle`` (registered but the scene hasn't kicked it);
    * task running ⇒ ``thinking`` (the soul's LLM round is in flight);
    * task done ⇒ the ``state`` of the ``CharacterDelta`` it returned
      (``completed`` collapses to ``idle``; ``interrupted`` / ``degraded``
      pass straight through — they are the §3.4/§3.8 lifecycle states the
      world-agent already stamped, not anything re-derived here);
    * task raised / cancelled ⇒ ``degraded`` (a crashed soul is the §3.8
      dead-letter case; surfacing it as degraded matches what the
      world-agent's own collection records).
    """
    task = getattr(runtime, "task", None)
    if task is None:
        return "idle"
    if not task.done():
        return "thinking"
    # ``task.done()`` — read the result WITHOUT re-raising into the UI
    # thread. A cancelled / excepted task is the §3.8 dead-letter signal.
    if task.cancelled():
        return "degraded"
    if task.exception() is not None:
        return "degraded"
    delta = task.result()
    state = getattr(delta, "state", "completed")
    return "idle" if state == "completed" else str(state)


def _runtime_tokens(runtime: Any) -> int:
    """Best-effort token count for one runtime (Phase E1, read-only).

    The committed A–D runtime does not yet carry per-character token
    accounting on the ``CharacterDelta`` (the budget caps in §2.3 are
    advisory in Phase B). We therefore read it *defensively*: if a later
    phase attaches ``tokens`` / ``total_tokens`` to the delta or the agent,
    the lane shows it for free; until then it shows 0. This keeps E1 a pure
    render of existing state — we add no token counter of our own here
    (cost details stay local; nothing is sent off the machine).
    """
    task = getattr(runtime, "task", None)
    if task is not None and task.done() and not task.cancelled():
        if task.exception() is None:
            delta = task.result()
            for attr in ("tokens", "total_tokens", "token_count"):
                val = getattr(delta, attr, None)
                if isinstance(val, int):
                    return max(0, val)
    agent = getattr(runtime, "agent", None)
    for attr in ("tokens", "total_tokens", "token_count"):
        val = getattr(agent, attr, None)
        if isinstance(val, int):
            return max(0, val)
    return 0


class CharacterStatusLane(Static):
    """M18 Phase E1 — one status line per live character-agent.

    Renders ``"<name> · turn <n> · <state> · <ntok> tok"`` for each entry
    in the world-agent's ``CharacterRuntime`` registry. This widget owns NO
    runtime state of its own: :meth:`render_runtimes` is handed the registry
    snapshot and formats it. A game with no world-agent / no characters (the
    legacy single-agent path) renders nothing and occupies zero rows, so
    build / sandbox and pre-M18 play sessions are visually unchanged.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._soul_snapshot: dict[str, dict[str, str]] = {}
        self._soul_spin_frame = 0
        self._soul_spin_timer: Any | None = None
        # The characters moved to the right column's Agent view; the lane stays (tests / other modes)
        # but never shows itself while this is set
        self.retired = False

    @property
    def is_scrollable(self) -> bool:
        """Yes — see :class:`GameStatePanel` for why a leaf widget must say so.

        One line per live character against a 12-row cap: a seven-soul world
        pushes half its cast out of sight, and without this the lane cannot
        be scrolled to reach them.
        """
        return True

    def render_runtimes(self, runtimes: dict[str, Any]) -> None:
        """Repaint the lane from a registry snapshot (pure render)."""
        lines = format_character_status_lines(runtimes)
        # Empty ⇒ collapse to zero height so the legacy layout is intact.
        self.display = bool(lines) and not self.retired
        self.update("\n".join(lines))

    def render_soul_status(self, snapshot: dict[str, dict[str, str]]) -> None:
        """Repaint from the unified soul=agent lifecycle snapshot
        (``{instance_id: {name, role, state}}``) emitted by
        ``_run_multi_agent_turn`` via the ``on_soul_status`` callback.

        A ``running`` soul gets an animated braille spinner (same look as
        the thinking indicator) — an interval timer ticks the frame while
        any soul is running, and stops itself when none are."""
        self._soul_snapshot = snapshot or {}
        self._repaint_souls()
        has_running = any(
            (v or {}).get("state") == "running"
            for v in self._soul_snapshot.values()
        )
        if has_running and self._soul_spin_timer is None:
            self._soul_spin_timer = self.set_interval(0.1, self._tick_soul_spin)
        elif not has_running and self._soul_spin_timer is not None:
            try:
                self._soul_spin_timer.stop()
            except Exception:
                pass
            self._soul_spin_timer = None

    def _tick_soul_spin(self) -> None:
        self._soul_spin_frame = (self._soul_spin_frame + 1) % len(_SOUL_SPIN_FRAMES)
        self._repaint_souls()

    def _repaint_souls(self) -> None:
        lines = format_soul_status_lines(
            getattr(self, "_soul_snapshot", {}), spin_frame=self._soul_spin_frame
        )
        self.display = bool(lines) and not self.retired
        self.update("\n".join(lines))

    # ── TODO #3 · 点角色名进它的 context ─────────────────────────────
    class SoulPicked(Message):
        """A name in the lane was clicked; ``iid`` is the instance id."""

        def __init__(self, iid: str) -> None:
            super().__init__()
            self.iid = iid

    def iid_at_row(self, row: int) -> str | None:
        """Row 0 is the title; row n is the n-th soul in lane order."""
        rows = ordered_soul_rows(getattr(self, "_soul_snapshot", {}) or {})
        if row <= 0 or row > len(rows):
            return None
        return rows[row - 1][0]

    def on_click(self, event: events.Click) -> None:
        # the row inside the content region — the lane's border-top is a row of its own, and counting from the border
        # put every click one row down (clicking 罗文 did nothing; clicking 艾琳娜 opened 罗文)
        try:
            off = event.get_content_offset(self)
            if off is None:
                return
            row = int(off.y) + int(self.scroll_offset.y)
        except Exception:
            row = int(getattr(event, "y", 0))
        iid = self.iid_at_row(row)
        if iid:
            event.stop()
            self.post_message(self.SoulPicked(iid))


def format_character_status_lines(runtimes: dict[str, Any]) -> list[str]:
    """Format the Phase E1 status lines from a registry snapshot.

    Sorted by sid so the lane order is stable across repaints (mirrors the
    world-agent's own sorted-sid fan-out determinism). One line per live
    character; ``state`` comes from :func:`_runtime_state` (which only reads
    the world-agent's already-computed task/delta state — no mutation).
    """
    lines: list[str] = []
    for sid in sorted(runtimes):
        runtime = runtimes[sid]
        agent = getattr(runtime, "agent", None)
        name = getattr(agent, "sid", sid) or sid
        turn = int(getattr(agent, "turn_index", 0) or 0)
        state = _runtime_state(runtime)
        ntok = _runtime_tokens(runtime)
        lines.append(f"{name} · turn {turn} · {state} · {ntok} tok")
    return lines


# State → glyph. Labels are i18n'd via the "soul.state.<state>" keys (see
# format_soul_status_lines); keep this glyph-only so the lane localizes.
_SOUL_STATE_GLYPH: dict[str, str] = {
    "queued": "·",
    "running": "⠋",
    "completed": "✓",
    "degraded": "⚠",
    "background": "◌",
    "offstage": "◌",
}

# Braille spinner frames for the "running" soul — same cycle the run-
# status / thinking indicator uses, so an active soul reads as "spinning"
# rather than a static play glyph.
_SOUL_SPIN_FRAMES: tuple[str, ...] = (
    "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
)


def ordered_soul_rows(snapshot: dict[str, dict[str, str]]) -> list[tuple[str, dict[str, str]]]:
    """Lane order: active souls first then inactive, each group by name —
    the same order the lane paints, so a clicked row maps back to its iid."""
    return sorted(
        snapshot.items(),
        key=lambda kv: (kv[1].get("role") != "active", kv[1].get("name", "")),
    )


def format_soul_status_lines(
    snapshot: dict[str, dict[str, str]],
    locale: str | None = None,
    spin_frame: int = 0,
) -> list[str]:
    """Format the persistent per-soul lane from the unified lifecycle
    snapshot. Active souls first then inactive, each group name-sorted, so
    the lane order is stable across repaints. Empty ⇒ no lines (lane
    collapses, legacy/non-multi-agent layout unchanged). ``locale`` defaults
    to the resolved UI locale (config/env) so the lane title is i18n'd.

    ``spin_frame`` indexes the braille spinner used for a ``running`` soul,
    so a host that ticks it on a timer gets a live "is thinking" cue."""
    if not snapshot:
        return []
    loc = resolve_locale(locale)
    items = [info for _iid, info in ordered_soul_rows(snapshot)]
    rows = [get_message(loc, "soul.lane.title").format(n=len(items))]
    for info in items:
        state = info.get("state", "")
        if state == "running":
            glyph = _SOUL_SPIN_FRAMES[spin_frame % len(_SOUL_SPIN_FRAMES)]
        else:
            glyph = _SOUL_STATE_GLYPH.get(state, "·")
        # Label is localized; unknown states fall back to the raw string.
        label = get_message(loc, f"soul.state.{state}") if state in _SOUL_STATE_GLYPH else (state or "?")
        rows.append(f"  {glyph} {info.get('name', '?')} · {label}")
    return rows


class ConversationView(VerticalScroll):
    """Main conversation panel with segmented markdown/code rendering."""

    BINDINGS = [Binding("y", "copy_selection", "Copy selection")]
    _FENCED_CODE_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
    _KEYCAP_RE = re.compile(r"([0-9#*])(?:\ufe0f|\ufe0e)?\u20e3")
    _DANGLING_ZWJ_RE = re.compile(r"\u200d(?=\s|$)")
    _UNSAFE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _GRAPHEME_CLUSTER_RE = regex_re.compile(r"\X")
    _MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
    _MARKDOWN_STRONG_RE = re.compile(r"\*\*(.+?)\*\*")
    # Inline spans inside a narrative line: **bold** or a dialogue quote.
    # Dialogue quotes get a distinct warm tint so spoken lines read apart
    # from narration — only the safe paired quote marks (CJK 「」『』《》
    # and curly “”) so we never mis-span on a stray ASCII quote.
    _INLINE_SPAN_RE = re.compile(
        r"\*\*(?P<bold>.+?)\*\*"
        r"|(?P<quote>「[^」]*」|『[^』]*』|“[^”]*”|《[^》]*》)"
    )
    # Dice/check resolution line — the fixed skeleton emitted by
    # core.dice.format_dice_line. The `[name: expr op target] → outcome`
    # shape is locale-stable (only name/outcome words localize), so this
    # regex matches all four languages. `expr` is a bare roll for BRP or
    # `natural+mod=total` for 5e.
    _DICE_LINE_RE = re.compile(
        r"^\[(?P<name>.+?):\s*(?P<expr>.+?)\s*(?P<op><=|>=|<|>|≤|≥)\s*(?P<target>\d+)\]"
        r"\s*→\s*(?P<outcome>.+?)\s*$"
    )
    # Braille dot spinner — the classic 10-frame ⠋⠙⠹… cycle. Colors index
    # independently (idx % len), so frame/color counts need not match.
    _PCT_CRIT_DIV, _PCT_SPECIAL_DIV, _PCT_FUMBLE_MIN = 20, 5, 99  # BRP: a critical is ≤ 1/20 of the target (rounded up), a fumble 99 / 00
    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _SPINNER_COLORS = ["#4f97df", "#66a9ec", "#7bb8f4", "#66a9ec", "#4f97df", "#3f83c7"]
    _OK_COLOR = "#67c587"
    _ERR_COLOR = "#cf7f7f"
    _NEUTRAL_COLOR = "#8a919b"
    _TOOL_TITLE_TEXT_COLOR = "#8e96a1"
    _EXECUTION_FOLD_TITLE_COLOR = "#7c8591"

    def __init__(self, display_mode: AppMode = "build", **kwargs):
        super().__init__(**kwargs)
        self.display_mode: AppMode = display_mode
        # Keep framework auto-scroll disabled and control follow behavior explicitly.
        self.auto_scroll = False
        self._follow_output = True
        self._programmatic_scroll = False
        self._scroll_end_pending = False
        self._scroll_end_reschedule = False
        self._plain_chunks: list[str] = []
        self._stream_render_timer = None
        self._assistant_stream_needs_render = False
        self._assistant_stream_open = False
        self._assistant_stream_buffer = ""
        self._assistant_stream_widget: Any | None = None
        self._assistant_stream_speaker: str = "Narrator"
        # Widget reference for the last mounted "### Speaker" header — so
        # we can remove it if the segment turns out to have no content
        # (e.g. the LLM produced only a tool call then delegated, leaving
        # a "[World Agent]" header with nothing under it).
        self._assistant_header_widget: Static | None = None
        # Per-turn accumulator for bridge broadcasting. Each entry is
        # (speaker_name, segment_text). Populated on every
        # `_flush_assistant_stream_segment` and drained at `add_assistant_end`.
        # Without this, bridges would only see the LAST segment of a multi-
        # speaker turn — so sub-agent chatter (town-agent, character-agent)
        # would mask the orchestrator's narration on Discord.
        self._bridge_segment_buffer: list[tuple[str, str]] = []
        # Last speaker we emitted a header for in the current user-turn.
        # Reset on add_user_message / add_assistant_end so subsequent turns
        # get their own header; keeps multi-tool-call turns under one label.
        self._last_header_speaker_in_turn: str | None = None
        self._thinking_stream_needs_render = False
        self._thinking_stream_open = False
        self._thinking_stream_buffer = ""
        self._thinking_stream_widget: Static | None = None
        self._thinking_stream_speaker: str | None = None
        self._tool_cards: list[dict[str, Any]] = []
        self._tool_spinner_frame = 0
        self._tool_spinner_timer = None
        self._pending_execution_items: list[dict[str, Any]] = []
        self._execution_live_widget: Static | None = None
        self._current_thinking_execution_item: dict[str, Any] | None = None
        self._assistant_activity_widget: Static | None = None
        self._assistant_activity_base: str = ""
        self._assistant_activity_pulse: int = 0
        self._assistant_activity_speaker: str | None = None
        self._assistant_activity_animating = False
        # Monotonic counter so each agent-error callout gets unique
        # button ids (multiple errors can stack in scrollback).
        self._agent_error_seq = 0
        # Typewriter reveal state for the streaming preview (play only).
        # `_reveal_n` chases len(buffer); `_reveal_hold` is a per-tick
        # countdown that pauses the reveal after sentence punctuation.
        self._assistant_reveal_n = 0
        self._assistant_reveal_hold = 0.0

    def set_display_mode(self, mode: AppMode) -> None:
        """Update transcript presentation mode."""
        self.display_mode = mode

    def _use_narrative_folding(self) -> bool:
        return self.display_mode == "play"

    @staticmethod
    def _to_plain_text(content: Any) -> str:
        """Convert rich/markup content into plain text for clipboard export."""
        if isinstance(content, Text):
            return content.plain
        if isinstance(content, str):
            try:
                return Text.from_markup(content).plain
            except Exception:
                return content
        return str(content)

    def _append_plain(self, text: str) -> None:
        plain = self._to_plain_text(text)
        if plain:
            self._plain_chunks.append(plain)

    def _is_near_bottom(self, y_value: float | None = None, threshold: float = 3.0) -> bool:
        y = self.scroll_y if y_value is None else y_value
        return (self.max_scroll_y - y) <= threshold

    def _pause_follow_output(self) -> None:
        self._follow_output = False

    def _resume_follow_output(self) -> None:
        self._follow_output = True

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        """Track user scroll intent to control output tail-following."""
        # Preserve Textual's default scroll bookkeeping (scrollbar position, refresh, anchoring).
        super().watch_scroll_y(old_value, new_value)
        if not self.is_mounted:
            return
        if self._programmatic_scroll:
            return
        if self._is_near_bottom(new_value):
            self._resume_follow_output()
            return
        # Dragging the scrollbar is explicit user intent to inspect older output.
        if self.is_vertical_scrollbar_grabbed:
            self._pause_follow_output()
            return
        # Wheel / keyboard scroll-up should also suspend follow mode.
        if new_value < old_value:
            self._pause_follow_output()

    def _safe_scroll_end(self) -> None:
        if not self.is_mounted:
            return
        if not self._follow_output:
            return
        if self._scroll_end_pending:
            self._scroll_end_reschedule = True
            return
        self._scroll_end_pending = True
        self.call_after_refresh(self._scroll_end_now)

    def _scroll_end_now(self) -> None:
        """Scroll to bottom after layout refresh so scrollbar state stays in sync."""
        if not self.is_mounted or not self._follow_output:
            self._scroll_end_pending = False
            self._scroll_end_reschedule = False
            return
        try:
            self._programmatic_scroll = True
            self.scroll_end(animate=False, immediate=True, x_axis=False)
        except Exception:
            try:
                self.scroll_end(animate=False)
            except Exception:
                pass
        finally:
            self._programmatic_scroll = False
            if self._scroll_end_reschedule and self.is_mounted and self._follow_output:
                self._scroll_end_reschedule = False
                self.call_after_refresh(self._scroll_end_now)
            else:
                self._scroll_end_pending = False
                self._scroll_end_reschedule = False

    def _mount_role_header(
        self,
        title: str,
        role: str,
        *,
        accent: str | None = None,
    ) -> Static | None:
        """Mount a `### Speaker` row. Returns the widget so the caller
        can remove it later if the segment turns out to be empty.

        ``accent`` (a hex color) tints an assistant header so each agent's
        output reads as authored by that agent — a thin ``▍`` glyph plus
        the role name in the agent's color. Without it, headers fall back
        to the flat ``msg-{role}`` CSS class.
        """
        if not self.is_mounted:
            return None
        self._mount_content_divider()
        display = title
        if self._use_narrative_folding() and role == "assistant":
            display = f"[{title}]"
        if accent and role == "assistant":
            content = Text()
            content.append("▍ ", style=accent)
            content.append(display, style=f"bold {accent}")
        else:
            content = Text(display)
        header = Static(content, classes=f"msg-header msg-{role}")
        self.mount(header)
        self._safe_scroll_end()
        return header

    def _resolve_agent_accent(self, agent_ref: str | None) -> str | None:
        """Hex accent color for an agent, or None if it can't be resolved."""
        try:
            from neonrp.tui.theme import agent_accent

            app_ctx = self._get_app_context()
            root = getattr(app_ctx, "root", None)
            return agent_accent(root, agent_ref)
        except Exception:
            return None

    def _resolve_view_locale(self) -> str:
        app_ctx = getattr(self, "_app_context", None)
        if app_ctx is None:
            try:
                app_ctx = self.app
            except Exception:
                app_ctx = None
        locale = str(getattr(app_ctx, "ui_locale", "en") or "en")
        return resolve_locale(locale)

    def _get_app_context(self) -> Any | None:
        app_ctx = getattr(self, "_app_context", None)
        if app_ctx is not None:
            return app_ctx
        try:
            return self.app
        except Exception:
            return None

    def _notify_portrait(self, speaker_ref: str | None) -> None:
        """Best-effort: update the play-mode portrait for the new speaker.

        Fully optional. Any failure (no panel composed, no asset, no
        imaging libs) is swallowed — the transcript never depends on it.
        """
        try:
            app_ctx = self._get_app_context()
            if app_ctx is None:
                return
            panel = app_ctx.query_one("#portrait-panel", PortraitPanel)
            panel.update_for(getattr(app_ctx, "root", None), speaker_ref)
        except Exception:
            return

    # L14 presentation-role resolution relies ONLY on agent.json:
    #
    #   {
    #     "presentation_role":        "World",    // optional, locale-neutral
    #     "presentation_roles":       { "zh": "世界", "en": "World" },
    #     "display_name":             "World",
    #     "display_names":            { "zh": "世界", "en": "World" },
    #     "presentation_hidden":      false        // if true, this agent's
    #                                              // turns are folded away
    #                                              // in the default view
    #   }
    #
    # The engine stays dumb — it doesn't know that `town-agent` means "Town"
    # or that `orchestrator` should be hidden. Templates / projects own those
    # decisions and set the fields on their own agent.json files.

    @staticmethod
    def _agent_is_hidden_at(root: Path | None, agent_ref: str | None) -> bool:
        """Mode-aware `presentation_hidden` read from agents/<ref>/agent.json.

        Implemented as a pure staticmethod so NeonRPApp can call it without
        going through the `view` instance — otherwise test mocks
        (`view = MagicMock()`) would make `view._is_agent_hidden(...)`
        return a truthy Mock, treating every agent as hidden.

        Engine is deliberately NAME-AGNOSTIC — no hardcoded list of
        "sub-agent" names. Whether a speaker is hidden depends entirely
        on the author-supplied `presentation_hidden` flag on the game's
        own agent.json. Same engine works for combat-referee (visible
        result), town-agent (author might hide), rules-referee
        (author might show), etc., without code changes.

        Mode gating:
        - `orchestrator` mode: respect per-agent `presentation_hidden`.
        - `fast` / non-orchestrator: sub-agents ARE the primary
          narrators via active-agent routing — never hide, regardless
          of flag.
        """
        raw = str(agent_ref or "").strip()
        if not raw or root is None:
            return False
        try:
            from neonrp.core.runtime_contract import get_router_execution_mode

            mode = get_router_execution_mode(Path(root))
        except Exception:
            mode = "orchestrator"
        if mode != "orchestrator":
            return False
        agent_json = Path(root) / "agents" / raw / "agent.json"
        if not agent_json.exists():
            return False
        try:
            payload = json.loads(agent_json.read_text(encoding="utf-8"))
        except Exception:
            return False
        return bool(payload.get("presentation_hidden", False))

    def _is_agent_hidden(self, agent_ref: str | None) -> bool:
        """Instance wrapper around `_agent_is_hidden_at` using the current root."""
        app_ctx = self._get_app_context()
        root = getattr(app_ctx, "root", None)
        return ConversationView._agent_is_hidden_at(root, agent_ref)

    # the engine's generic speaker refs for the one who runs the table — shown as the host (主持 / GM), never "Narrator"
    _HOST_REFS = frozenset({"narrator", "world", "gm", "host"})

    @staticmethod
    def host_label(locale: str) -> str:
        """主持 / GM — the host's display name in ``locale`` (prompts/beat_display.<lang>.json "host")."""
        try:
            from neonrp import prompts as _prompts

            return str(_prompts.strings("beat_display", locale).get("host") or "GM")
        except Exception:  # noqa: BLE001
            return "GM"

    def _host_label(self) -> str:
        return self.host_label(self._resolve_view_locale())

    def _resolve_agent_transcript_meta(self, agent_ref: str | None) -> tuple[str, str, str, str]:
        raw = str(agent_ref or "").strip()
        locale = self._resolve_view_locale()
        default_thinking = get_message(locale, "status.thinking")
        default_narrating = get_message(locale, "status.narrating")
        default_acting = get_message(locale, "status.acting")
        generic = (not raw) or raw.lower() in self._HOST_REFS
        shown = self._host_label() if generic else raw
        if not raw:
            return (shown, default_thinking, default_narrating, default_acting)
        app_ctx = self._get_app_context()
        root = getattr(app_ctx, "root", None)
        if root is None:
            return (shown, default_thinking, default_narrating, default_acting)
        agent_json = Path(root) / "agents" / raw / "agent.json"
        if not agent_json.exists():
            return (shown, default_thinking, default_narrating, default_acting)
        try:
            payload = json.loads(agent_json.read_text(encoding="utf-8"))
        except Exception:
            return (raw, default_thinking, default_narrating, default_acting)
        if not isinstance(payload, dict):
            return (raw, default_thinking, default_narrating, default_acting)

        # Presentation role: optional locale-aware alias from agent.json.
        presentation_roles = payload.get("presentation_roles")
        if isinstance(presentation_roles, dict):
            presentation_role = str(presentation_roles.get(locale, "") or "").strip()
        else:
            presentation_role = ""
        if not presentation_role:
            presentation_role = str(payload.get("presentation_role", "") or "").strip()

        localized_names = payload.get("display_names")
        if isinstance(localized_names, dict):
            localized_name = str(localized_names.get(locale, "") or "").strip()
        else:
            localized_name = ""
        display_name = (
            presentation_role
            or localized_name
            or str(payload.get(f"display_name_{locale}", "") or "").strip()
            or str(payload.get("name_local", "") or "").strip()
            or str(payload.get("display_name", "") or "").strip()
            or str(payload.get("name", "") or "").strip()
            or raw
        )

        localized_thinking = payload.get("thinking_labels")
        if isinstance(localized_thinking, dict):
            thinking_label = str(localized_thinking.get(locale, "") or "").strip()
        else:
            thinking_label = ""
        thinking_label = (
            thinking_label
            or str(payload.get(f"thinking_label_{locale}", "") or "").strip()
            or str(payload.get("thinking_label", "") or "").strip()
            or default_thinking
        )

        localized_narrating = payload.get("narrating_labels")
        if isinstance(localized_narrating, dict):
            narrating_label = str(localized_narrating.get(locale, "") or "").strip()
        else:
            narrating_label = ""
        narrating_label = (
            narrating_label
            or str(payload.get(f"narrating_label_{locale}", "") or "").strip()
            or str(payload.get("narrating_label", "") or "").strip()
            or default_narrating
        )

        localized_acting = payload.get("acting_labels")
        if isinstance(localized_acting, dict):
            acting_label = str(localized_acting.get(locale, "") or "").strip()
        else:
            acting_label = ""
        acting_label = (
            acting_label
            or str(payload.get(f"acting_label_{locale}", "") or "").strip()
            or str(payload.get("acting_label", "") or "").strip()
            or default_acting
        )
        return (display_name, thinking_label, narrating_label, acting_label)

    def add_beat_row(self, row: Any, classes: str = "beat-row") -> None:
        """A row a beat produced (a die it rolled, a tool it called, the state it changed) — under the prose, after the
        segment streaming so far is closed. ``row`` is rich Text or a ready widget."""
        self._flush_assistant_stream_segment()
        if not self.is_mounted or row is None:
            return
        self.mount(row if isinstance(row, Static) else Static(row, classes=f"msg-body {classes}"))
        try:
            self.scroll_end(animate=False)
        except Exception:
            pass

    def add_beat_marker(self, label: str, color: str) -> None:
        """A colored band where a beat begins (10-08: planning green · resolving red · a layer amber) — the segment
        streaming so far is closed first, so the band sits between the two beats."""
        self._flush_assistant_stream_segment()
        if not self.is_mounted:
            return
        band = Text()
        band.append("━━ ", style=color)
        band.append(label, style=f"bold {color}")
        band.append(" " + "━" * 24, style=color)
        self.mount(Static(band, classes="beat-marker"))
        try:
            self.scroll_end(animate=False)
        except Exception:
            pass

    def _mount_content_divider(self) -> None:
        if not self.is_mounted:
            return
        try:
            children = list(self.children)
        except Exception:
            children = []
        if not children:
            return
        last = children[-1]
        try:
            if "msg-divider" in str(getattr(last, "classes", "")):
                return
        except Exception:
            pass
        self.mount(Static(Rule(style="#3F3F46", characters="─"), classes="msg-divider"))

    def _build_away_fold(self, line: str) -> Any:
        """A character elsewhere took her own turn: a folded 「✓ 罗文 @ 碧石镇」 notice — click to open her
        whole line (from the engine's `away` event; the prose line itself is cut at 80), click again to fold it."""
        from textual.widgets import Collapsible

        head = line.strip()[2:].lstrip()
        for lb in self._away_labels():
            if head.startswith(lb + " ·"):
                head = head[len(lb) + 2:].strip()
                break
        who_where, _sep, text = head.partition(":")
        name, _at, where = who_where.partition(" @ ")
        name, where = name.strip(), where.strip()
        full = text.strip()
        try:
            st = getattr(self.app, "_beat_state", None)
            item = (st.away.get(name) if st is not None else None) or {}
            full = str(item.get("text") or full)
        except Exception:  # noqa: BLE001 — no app (tests building widgets bare): the line's own text
            pass
        title = f"✓ {name}" + (f" @ {where}" if where else "")
        if not full:
            return Static(Text(title, style="#94a3b8"), classes="msg-body away-fold")
        return Collapsible(Static(Text(full, style="#cbd5e1"), classes="msg-body"), title=title, collapsed=True,
                           classes="away-fold")

    @staticmethod
    def _is_away_line(stripped: str) -> bool:
        """``// 异地 · 罗文 @ 碧石镇:…`` in any of the four languages (core/beat_display.away_lines)."""
        labels = ConversationView._away_labels()
        head = stripped[2:].lstrip()
        return any(head.startswith(lb + " ·") for lb in labels)

    @staticmethod
    def _away_labels() -> tuple[str, ...]:
        cached = getattr(ConversationView, "_AWAY_LABELS", None)
        if cached is None:
            try:
                from neonrp import prompts as _prompts

                cached = tuple(str(_prompts.strings("beat_display", lg).get("away") or "") for lg in ("zh", "en", "ja", "ko"))
            except Exception:  # noqa: BLE001
                cached = ("异地",)
            ConversationView._AWAY_LABELS = tuple(x for x in cached if x)
            cached = ConversationView._AWAY_LABELS
        return cached

    @staticmethod
    def _semantic_line_class(line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return "semantic-spacer"
        if ConversationView._MARKDOWN_HEADING_RE.match(stripped):
            return "semantic-markdown-heading"
        if stripped.startswith("//") and ConversationView._is_away_line(stripped):
            return "semantic-away-line"
        if stripped.startswith("//") or "═══" in stripped:
            return "semantic-scene-header"
        if re.match(r"^\[\s*~?\s*san\b", stripped, re.IGNORECASE):
            return "semantic-san-line"
        if stripped.startswith("[state_update]"):
            return "semantic-state-update"
        if stripped.startswith("[awaiting_player_action]"):
            return "semantic-awaiting"
        if ConversationView._DICE_LINE_RE.match(stripped):
            return "semantic-dice-line"
        if stripped.startswith("[") and "]" in stripped:
            return "semantic-agent-tag"
        if stripped.startswith("内心独白"):
            return "semantic-inner"
        if stripped.startswith(">"):
            return "semantic-player-line"
        if re.match(r"^\d+\.\s", stripped):
            return "semantic-choice-line"
        return "semantic-narrative-line"

    @staticmethod
    def _semantic_base_color(css_class: str) -> str:
        mapping = {
            "semantic-scene-header": "#34D399",
            "semantic-markdown-heading": "#4ADE80",
            "semantic-agent-tag": "#5BE0B0",
            "semantic-state-update": "#86efac",
            "semantic-awaiting": "#fcd34d",
            "semantic-dice-line": "#e8a33d",
            "semantic-san-line": "#c084fc",  # sanity: violet
            "semantic-away-line": "#94a3b8",  # a character elsewhere: muted, not the scene header's green
            "semantic-inner": "#9BE89B",
            "semantic-choice-line": "#f5f5f5",
            "semantic-player-line": "#e4e4e7",
            "semantic-narrative-line": "#d8d2c0",
        }
        return mapping.get(css_class, "#f8fafc")

    @classmethod
    def _build_semantic_inline_text(cls, line: str, css_class: str = "semantic-narrative-line") -> Text:
        raw = cls._sanitize_terminal_text(line)
        heading_match = cls._MARKDOWN_HEADING_RE.match(raw.strip())
        content = heading_match.group(2) if heading_match else raw
        base_style = cls._semantic_base_color(css_class)

        rendered = Text()
        cursor = 0
        for match in cls._INLINE_SPAN_RE.finditer(content):
            if match.start() > cursor:
                rendered.append(content[cursor:match.start()], style=base_style)
            if match.group("bold") is not None:
                rendered.append(match.group("bold"), style="bold #5BE0B0")
            else:
                # Dialogue — warm gold so spoken lines lift off the
                # parchment narration.
                rendered.append(match.group("quote"), style="#e8c98a")
            cursor = match.end()
        if cursor < len(content):
            rendered.append(content[cursor:], style=base_style)
        return rendered

    def _build_semantic_stream_text(self, text: str) -> Text:
        combined = Text()
        sanitized = self._sanitize_terminal_text(text)
        lines = sanitized.splitlines()
        for idx, line in enumerate(lines):
            css_class = self._semantic_line_class(line)
            if css_class == "semantic-spacer":
                if idx < len(lines) - 1:
                    combined.append("\n")
                continue
            combined.append_text(self._build_semantic_inline_text(line, css_class=css_class))
            if idx < len(lines) - 1:
                combined.append("\n")
        return combined

    def _build_semantic_text_widgets(self, text: str, role: str = "assistant") -> list[Any]:
        widgets: list[Any] = []
        sanitized = self._sanitize_terminal_text(text)
        for line in sanitized.splitlines():
            css_class = self._semantic_line_class(line)
            if css_class == "semantic-spacer":
                widgets.append(Static("", classes="msg-spacer"))
                continue
            if css_class == "semantic-dice-line":
                dice_widget = self._build_dice_widget(line, role=role)
                if dice_widget is not None:
                    widgets.append(dice_widget)
                    continue
                # Parse miss — fall through to the plain semantic render.
            if css_class == "semantic-away-line":
                fold = self._build_away_fold(line)
                if fold is not None:
                    widgets.append(fold)
                    continue
            widgets.append(
                Static(self._build_semantic_inline_text(line, css_class=css_class), classes=f"msg-body msg-{role} {css_class}")
            )
        return widgets

    _DICE_TIER_STYLE = {
        "critical": ("#f5c542", "✦"),  # gold
        "special": ("#7dd3fc", "✧"),   # sky blue — better than a plain success, short of a critical
        "success": ("#67c587", "◈"),   # green
        "fail": ("#cf7f7f", "◇"),      # muted red
        "fumble": ("#cf5b5b", "✠"),    # dark red
    }

    @classmethod
    def _dice_tier(cls, level: str | None, outcome: str, expr: str, target: str, is_5e: bool) -> str | None:
        from neonrp.core.beat_display import LEVELS, outcome_level

        if level:
            lv = outcome_level({"level": level})
            if lv:
                return lv
        word, said = str(outcome or "").strip(), None
        for loc in ("zh", "en", "ja", "ko"):
            for lv in LEVELS:
                if said is None and word == get_message(loc, f"dice.outcome.{lv}"):
                    said = lv
        if said in ("critical", "special", "fumble"):
            return said
        nat = re.match(r"\d+", expr)
        if nat is None:
            return said
        natural = int(nat.group(0))
        if is_5e:  # 14-1=13 · 17+3=20: the natural die is the first number (a single d20)
            if re.fullmatch(r"\d+[+-]\d+=\-?\d+|\d+=\-?\d+", expr.replace(" ", "")) is None:
                return said
            return "critical" if natural == 20 else "fumble" if natural == 1 else said
        t = int(target) if str(target or "").isdigit() else 0
        if natural >= cls._PCT_FUMBLE_MIN and (natural >= 100 or t < cls._PCT_FUMBLE_MIN):
            return "fumble"
        if natural <= max(1, -(-t // cls._PCT_CRIT_DIV)):
            return "critical"
        if natural <= max(1, -(-t // cls._PCT_SPECIAL_DIV)) and natural <= t:
            return "special"
        return said

    @classmethod
    def _build_dice_widget(cls, line: str, role: str = "assistant", level: str | None = None) -> Static | None:
        """Render a dice/check resolution line as a single boxed row.

        Returns None if the line doesn't parse — caller falls back to
        plain rendering. Pass/fail color comes from the operator
        (``<=``/``>=`` pass, ``<``/``>`` fail); critical/fumble are
        detected from the raw roll value so the styling is locale-free.
        """
        m = cls._DICE_LINE_RE.match(line.strip())
        if m is None:
            return None
        name = m.group("name").strip()
        expr = m.group("expr").strip()
        op = m.group("op")
        target = m.group("target")
        outcome = m.group("outcome").strip()

        is_5e = "=" in expr
        face = "d20" if is_5e else "d100"
        # the engine writes the comparison that held: roll-over passes with >= / ≥, roll-under with <= / ≤;
        # < / > are the failing side of each (10-08: a percentile `37 ≤ 60` was drawn as a failure)
        passed = op in ("<=", ">=", "≤", "≥")

        # The tier: the event's own `level` (beat_events, pct's `crit` read as `critical`) → the outcome word in any of the
        # four languages (dice.outcome.*) → the raw die (locale-free; BRP critical ≤ ⌈t/20⌉, special ≤ ⌈t/5⌉, 99 / 00).
        tier = cls._dice_tier(level, outcome, expr, target, is_5e)
        accent, glyph = cls._DICE_TIER_STYLE.get(tier or ("success" if passed else "fail"), ("#cf7f7f", "◇"))

        text = Text()
        text.append(f"{glyph} ", style=f"bold {accent}")
        text.append(f"{face}", style="dim #9a8fb0")
        text.append("  ", style="")
        text.append(name, style="#d8dee9")
        text.append("  ", style="")
        text.append(f"{expr} {op} {target}", style=f"{accent}")
        text.append("  →  ", style="dim #9a8fb0")
        text.append(outcome, style=f"bold {accent}")

        return Static(text, classes=f"msg-body msg-{role} semantic-dice-line")

    @staticmethod
    def _is_hidden_json_code_block(lang: str, content: str) -> bool:
        text = str(content or "").strip()
        if not text:
            return False
        normalized_lang = str(lang or "").strip().lower()
        if normalized_lang not in {"", "json", "jsonc", "javascript", "js"} and not text.startswith(("{", "[")):
            return False
        try:
            parsed = json.loads(text)
        except Exception:
            return False
        return isinstance(parsed, (dict, list))

    @classmethod
    def _split_markdown_segments(cls, text: str) -> list[tuple[str, str, str]]:
        """Split markdown into text/code segments."""
        segments: list[tuple[str, str, str]] = []
        pos = 0
        for match in cls._FENCED_CODE_RE.finditer(text):
            start, end = match.span()
            if start > pos:
                text_seg = text[pos:start]
                if text_seg.strip():
                    segments.append(("text", "", text_seg))
            lang = (match.group(1) or "").strip().lower()
            code = match.group(2).strip("\n")
            segments.append(("code", lang, code))
            pos = end
        if pos < len(text):
            tail = text[pos:]
            if tail.strip():
                segments.append(("text", "", tail))
        return segments

    def _build_code_block(self, role: str, lang: str, content: str) -> Vertical:
        lexer = lang or "text"
        try:
            syntax = Syntax(content, lexer, theme="monokai", word_wrap=True, line_numbers=False)
        except Exception:
            syntax = Syntax(content, "text", theme="monokai", word_wrap=True, line_numbers=False)
        code_lang = lang or "code"
        return Vertical(
            Static(f"[{code_lang}]", classes="code-lang"),
            Static(syntax, classes="code-body"),
            classes=f"code-block msg-{role}",
        )

    def _build_segment_widgets(self, markdown: str, role: str = "system") -> list:
        """Create widgets for markdown/code segments."""
        widgets = []
        for seg_type, lang, content in self._split_markdown_segments(markdown):
            if seg_type == "text":
                safe_content = self._sanitize_terminal_text(content)
                if self._use_narrative_folding() and role == "assistant":
                    widgets.extend(self._build_semantic_text_widgets(safe_content, role=role))
                else:
                    widgets.append(Markdown(safe_content, classes=f"msg-body msg-{role}"))
            else:
                safe_content = self._sanitize_terminal_text(content)
                if self._use_narrative_folding() and role == "assistant" and self._is_hidden_json_code_block(lang, safe_content):
                    continue
                widgets.append(self._build_code_block(role, lang, safe_content))
        return widgets

    def _render_markdown_segments(
        self,
        markdown: str,
        role: str = "system",
        parent: Any | None = None,
        before: Any | None = None,
    ) -> None:
        if not self.is_mounted:
            return
        target = parent or self
        is_first = True
        for widget in self._build_segment_widgets(markdown, role):
            mount_kwargs: dict[str, Any] = {}
            if before is not None and is_first:
                mount_kwargs["before"] = before
            target.mount(widget, **mount_kwargs)
            is_first = False
        self._safe_scroll_end()

    @staticmethod
    def _split_scoped_tool_name(tool_name: str) -> tuple[str | None, str]:
        raw = str(tool_name or "").strip()
        if ":" not in raw:
            return None, raw
        scope, base = raw.split(":", 1)
        scope = scope.strip()
        base = base.strip()
        if not scope or not base:
            return None, raw
        return scope, base

    @staticmethod
    def _extract_ask_user_question(params: dict[str, Any]) -> str:
        if not isinstance(params, dict):
            return ""
        question = str(params.get("question", "") or "").strip()
        if question:
            return question
        questions = params.get("questions")
        if isinstance(questions, str):
            # LLM 偶发把数组双重编码成 JSON 字符串;防御性解一层(根治在 schema/提示词)。
            try:
                questions = json.loads(questions)
            except (ValueError, TypeError):
                questions = None
        if isinstance(questions, list):
            first = next((item for item in questions if isinstance(item, dict)), None)
            if first:
                return str(first.get("question", "") or "").strip()
        return ""

    @staticmethod
    def _tool_summary(tool_name: str, params: dict[str, Any]) -> str:
        """Build one-line tool call summary with readable phrasing."""
        MAX_LEN = 80
        # 防御(issue 实测崩点):LLM 偶发把 params 吐成 list/str,直接 .get
        # 会在回滚重放渲染历史消息时炸整个 TUI('list' object has no 'get')。
        if not isinstance(params, dict):
            return str(tool_name or "").strip() or "tool"
        scope, base_name = ConversationView._split_scoped_tool_name(tool_name)
        normalized = str(base_name or "").strip().lower()

        summary = str(base_name or tool_name or "").strip()
        if normalized in {"read_file", "write_file", "edit_file", "delete_file"}:
            path = str(params.get("path", "") or "").strip()
            if path:
                verb = {
                    "read_file": "Read",
                    "write_file": "Write",
                    "edit_file": "Edit",
                    "delete_file": "Delete",
                }[normalized]
                summary = f"{verb} {path}"
        elif normalized == "ask_user":
            question = ConversationView._extract_ask_user_question(params)
            if question:
                summary = f'Ask "{question}"'
            else:
                summary = "Ask player"
        elif normalized == "task":
            target = str(params.get("agent_id", "") or "").strip()
            summary = f"Delegate to {target}" if target else "Delegate task"
        elif normalized == "resolve_action":
            action = str(params.get("action", "") or "").strip()
            summary = f'Resolve "{action}"' if action else "Resolve action"
        elif normalized == "glob":
            pattern = str(params.get("pattern", "") or "").strip()
            summary = f'Search "{pattern}"' if pattern else "Search files"
        elif normalized == "list_entities":
            etype = str(params.get("entity_type", "") or "").strip()
            summary = f"List {etype}" if etype else "List entities"
        elif normalized == "read_context":
            query = str(params.get("query", "") or "").strip()
            summary = f'Read context "{query}"' if query else "Read context"
        elif params:
            pairs: list[str] = []
            for key, value in params.items():
                text = str(value).replace("\n", " ").strip()
                if len(text) > 36:
                    text = f"{text[:33]}..."
                pairs.append(f"{key}={text}")
            tail = " ".join(pairs).strip()
            summary = f"{base_name} {tail}".strip()

        if scope:
            result = f"{scope}: {summary}"
        else:
            result = summary

        if len(result) > MAX_LEN:
            return f"{result[: MAX_LEN - 3]}..."
        return result

    @staticmethod
    def _tool_payload_text(params: dict[str, Any]) -> str:
        """Serialize tool params for detail panel."""
        if not params:
            return "(no params)"
        serialized = json.dumps(params, ensure_ascii=False, indent=2, default=str)
        return serialized if len(serialized) <= 500 else f"{serialized[:497]}..."

    @staticmethod
    def _tool_result_text(raw_result: str) -> str:
        """Serialize tool result payload for detail panel with safe truncation."""
        if not isinstance(raw_result, str) or not raw_result.strip():
            return "(no result yet)"
        try:
            payload = json.loads(raw_result)
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict):
                    # Large file reads can dominate the card; keep a compact preview.
                    content = data.get("content")
                    if isinstance(content, str) and len(content) > 320:
                        data = dict(data)
                        data["content"] = f"{content[:317]}..."
                        payload = dict(payload)
                        payload["data"] = data
                serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            else:
                serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        except Exception:
            serialized = raw_result

        if len(serialized) > 900:
            return f"{serialized[:897]}..."
        return serialized

    @staticmethod
    def _change_diff_block(raw_result: str | None) -> str:
        """M31 B1 — the actual edit, as a diff, above the raw payloads.

        A write's result JSON carries the change record, but nobody reads a
        diff out of escaped JSON. Expanding a write card should show what
        an author would want to review: the lines that moved.
        """
        if not raw_result:
            return ""
        try:
            change = (json.loads(raw_result).get("data") or {}).get("change")
        except Exception:  # noqa: BLE001 — malformed result: fall back to raw
            return ""
        if not isinstance(change, dict):
            return ""
        preview = str(change.get("preview", "") or "").rstrip()
        if not preview:
            return ""
        header = f"{change.get('path', '')} — {change.get('headline', '')}".strip(" —")
        tail = "\n… (truncated)" if change.get("truncated") else ""
        return f"{header}\n```diff\n{preview}{tail}\n```\n\n"

    def _tool_body_markdown(self, params: dict[str, Any], raw_result: str | None = None) -> str:
        payload = self._tool_payload_text(params)
        if raw_result is None:
            return self._normalize_markdown(f"```json\n{payload}\n```")
        result_payload = self._tool_result_text(raw_result)
        diff_block = self._change_diff_block(raw_result)
        return self._normalize_markdown(
            f"{diff_block}Params:\n```json\n{payload}\n```\n\nResult:\n```json\n{result_payload}\n```"
        )

    def _refresh_tool_card_details(self, state: dict[str, Any]) -> None:
        """Rebuild an existing tool card's details panel from its latest params."""
        card = state.get("card")
        params = state.get("params", {})
        if card is None or not isinstance(params, dict):
            return
        raw_result = state.get("result_raw")
        if not isinstance(raw_result, str):
            raw_result = None
        body = self._tool_body_markdown(params, raw_result)
        details = self._build_segment_widgets(body, role="tool")
        if not details:
            details = [Static("(no details)", classes="msg-body msg-tool")]

        try:
            contents = card.query_one(Collapsible.Contents)
        except Exception:
            contents = None

        if contents is not None:
            try:
                contents.remove_children()
            except Exception:
                pass
            for widget in details:
                try:
                    contents.mount(widget)
                except Exception:
                    # Best effort: avoid breaking tool flow if widget internals differ by Textual version.
                    break
            return

        # Fallback for unexpected widget states.
        for widget in details:
            try:
                card.mount(widget)
            except Exception:
                break

    @staticmethod
    def _canonical_tool_name(tool_name: str) -> str:
        """Normalize tool labels so early stream markers and real calls match."""
        raw = str(tool_name or "").strip()
        if not raw:
            return raw
        raw = raw.strip("`")
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_:\.-]*)\s*\(", raw)
        if match:
            return match.group(1)
        return raw

    def write(
        self,
        content: Any,
        *_args: Any,
        **_kwargs: Any,
    ) -> "ConversationView":
        """Append plain text content to the transcript area."""
        plain = self._to_plain_text(content)
        if not plain:
            return self
        return self.write_markdown(plain)

    def write_markdown(self, text: str) -> "ConversationView":
        """Append markdown/plain text directly to the transcript."""
        if not text:
            return self
        self._append_plain(text)
        if self.is_mounted:
            self._render_markdown_segments(self._normalize_markdown(text), role="system")
        return self

    def clear(self) -> "ConversationView":
        """Clear transcript content."""
        self._plain_chunks.clear()
        self._stop_stream_timer()
        self._assistant_stream_needs_render = False
        self._assistant_stream_open = False
        self._assistant_stream_buffer = ""
        self._assistant_stream_widget = None
        self._assistant_stream_speaker = "Narrator"
        self._thinking_stream_needs_render = False
        self._thinking_stream_open = False
        self._thinking_stream_buffer = ""
        self._thinking_stream_widget = None
        self._thinking_stream_speaker = None
        self._tool_cards = []
        self._tool_spinner_frame = 0
        self._stop_tool_spinner()
        self._pending_execution_items = []
        self._execution_live_widget = None
        self._current_thinking_execution_item = None
        self._assistant_activity_widget = None
        self._assistant_activity_base = ""
        self._assistant_activity_pulse = 0
        self._assistant_activity_speaker = None
        self._assistant_activity_animating = False
        if self.is_mounted:
            self.remove_children()
        return self

    @staticmethod
    def _truncate_inline(text: str, max_len: int = 72) -> str:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(value) <= max_len:
            return value
        return f"{value[: max_len - 3]}..."

    def _queue_execution_widget(self, widget: Any, summary: str, kind: str) -> dict[str, Any]:
        item = {
            "widget": widget,
            "summary": self._truncate_inline(summary),
            "kind": kind,
        }
        self._pending_execution_items.append(item)
        return item

    @staticmethod
    def _format_thinking_summary(label: str, thinking_label: str, text: str) -> str:
        prefix = f"[{label} {thinking_label}]"
        excerpt = re.sub(r"\s+", " ", str(text or "")).strip()
        if excerpt:
            return f"{prefix} {excerpt}"
        return prefix

    @staticmethod
    def _animated_suffix(frame: int) -> str:
        return [".", "..", "..."][frame % 3]

    def _tool_execution_summary(self, tool_name: str, params: dict[str, Any]) -> str:
        scope, base_name = ConversationView._split_scoped_tool_name(tool_name)
        normalized = str(base_name or "").strip().lower()
        actor = ""
        if scope:
            display_label, _thinking, _narrating, acting_label = self._resolve_agent_transcript_meta(scope)
            actor = f"[{display_label} {acting_label}] "
        if normalized == "task":
            target = str(params.get("agent_id", "") or "").strip()
            return f"{actor}delegate → {target}" if target else f"{actor}delegate"
        if normalized == "read_file":
            path = str(params.get("path", "") or "").strip()
            return f"{actor}read {path}" if path else f"{actor}read file"
        if normalized == "glob":
            pattern = str(params.get("pattern", "") or "").strip()
            return f"{actor}search {pattern}" if pattern else f"{actor}search files"
        if normalized == "ask_user":
            return f"{actor}await player action"
        return f"{actor}{ConversationView._tool_summary(tool_name, params)}"

    def _build_execution_summary_text(self) -> str:
        if not self._pending_execution_items:
            return "working..."
        parts: list[str] = []
        thinking_count = sum(1 for item in self._pending_execution_items if item.get("kind") == "thinking")
        if thinking_count:
            parts.append("thinking")
        tool_summaries = [
            str(item.get("summary", "")).strip()
            for item in self._pending_execution_items
            if item.get("kind") == "tool" and str(item.get("summary", "")).strip()
        ]
        if tool_summaries:
            preview = "; ".join(tool_summaries[:2])
            if len(tool_summaries) > 2:
                preview = f"{preview} +{len(tool_summaries) - 2}"
            parts.append(preview)
        return self._truncate_inline(" · ".join(parts) if parts else "working...", max_len=88)

    def _update_live_execution_preview(self) -> None:
        if not self._use_narrative_folding() or not self.is_mounted or not self._pending_execution_items:
            return
        text = self._build_execution_summary_text()
        content = f"[dim]{text}[/]"
        if self._execution_live_widget is None:
            self._execution_live_widget = Static(content, classes="msg-system execution-live")
            self.mount(self._execution_live_widget)
        else:
            self._execution_live_widget.update(content)
        self._safe_scroll_end()

    def _clear_live_execution_preview(self) -> None:
        if self._execution_live_widget is None:
            return
        try:
            self._execution_live_widget.remove()
        except Exception:
            pass
        self._execution_live_widget = None

    def _mount_assistant_activity_note(self, speaker_ref: str | None, *, animated: bool) -> None:
        if not self._use_narrative_folding() or not self.is_mounted:
            return
        speaker_key = str(speaker_ref or "Narrator").strip() or "Narrator"
        if self._assistant_activity_speaker == speaker_key and self._assistant_activity_widget is not None:
            if not animated:
                self._finalize_assistant_activity_note()
            return
        self._assistant_activity_pulse = 0
        label, _thinking, narrating_label, _acting = self._resolve_agent_transcript_meta(speaker_ref)
        _ = label
        self._assistant_activity_base = narrating_label
        text = narrating_label + (self._animated_suffix(self._assistant_activity_pulse) if animated else "")
        widget = Static(Text(text), classes="msg-system assistant-activity-line")
        self.mount(widget)
        self._assistant_activity_widget = widget
        self._assistant_activity_speaker = speaker_key
        self._assistant_activity_animating = animated

    def _finalize_assistant_activity_note(self) -> None:
        if self._assistant_activity_widget is not None:
            try:
                self._assistant_activity_widget.update(Text(self._assistant_activity_base))
            except Exception:
                pass
        self._assistant_activity_animating = False

    def _release_assistant_activity_tracking(self) -> None:
        self._assistant_activity_widget = None
        self._assistant_activity_base = ""
        self._assistant_activity_pulse = 0
        self._assistant_activity_speaker = None
        self._assistant_activity_animating = False

    def _mount_execution_summary_note(self) -> None:
        if not self._use_narrative_folding() or not self.is_mounted or not self._pending_execution_items:
            return
        summary = self._build_execution_summary_text()
        self._append_plain(f"_{summary}_\n")
        self.mount(Static(f"[dim]{summary}[/]", classes="msg-system execution-summary"))

    def _format_execution_fold_title(self) -> str:
        if not self._pending_execution_items:
            return f"[{self._EXECUTION_FOLD_TITLE_COLOR}]Behind the scene[/]"
        thinking_count = sum(1 for item in self._pending_execution_items if item.get("kind") == "thinking")
        tool_summaries = [
            str(item.get("summary", "")).strip()
            for item in self._pending_execution_items
            if item.get("kind") == "tool" and str(item.get("summary", "")).strip()
        ]
        parts: list[str] = []
        if thinking_count:
            parts.append("reasoning")
        if tool_summaries:
            preview = "; ".join(tool_summaries[:2])
            if len(tool_summaries) > 2:
                preview = f"{preview} +{len(tool_summaries) - 2}"
            parts.append(preview)
        if not parts:
            parts.append(f"{len(self._pending_execution_items)} steps")
        body = self._truncate_inline(" · ".join(parts), max_len=84)
        return f"[{self._EXECUTION_FOLD_TITLE_COLOR}]Behind the scene · {body}[/]"

    def flush_pending_execution_details(self) -> None:
        if not self._pending_execution_items or not self.is_mounted:
            return
        self._clear_live_execution_preview()
        self._mount_content_divider()
        widgets = [item.get("widget") for item in self._pending_execution_items if item.get("widget") is not None]
        if not widgets:
            self._pending_execution_items = []
            return
        card = Collapsible(
            *widgets,
            title=self._format_execution_fold_title(),
            collapsed=True,
            collapsed_symbol="▸",
            expanded_symbol="▾",
            classes="tool-collapsible msg-system execution-fold",
        )
        self.mount(card)
        self._pending_execution_items = []
        self._safe_scroll_end()

    @staticmethod
    def is_compact_summary_message(text: str) -> bool:
        content = str(text or "").strip()
        return content.startswith("[System: Previous conversation was compacted. Summary follows.]")

    @staticmethod
    def is_compact_ack_message(text: str) -> bool:
        content = str(text or "").strip()
        return content.startswith("Understood. I have the summary of our previous conversation")

    def add_compact_summary_fold(self, summary_text: str, acknowledgement: str | None = None) -> None:
        """Render compacted history as a collapsed narrative fold."""
        summary_body = self._normalize_markdown(str(summary_text or "").strip())
        ack = str(acknowledgement or "").strip()
        if ack:
            summary_body = f"{summary_body}\n\n---\n\n{ack}"
        if not summary_body:
            return
        if not self.is_mounted:
            self.write_markdown(f"\n### Story So Far\n\n{summary_body}\n")
            return
        self._mount_content_divider()
        self._append_plain(f"\n### Story So Far\n\n{summary_body}\n")
        details = self._build_segment_widgets(summary_body, role="system")
        if not details:
            details = [Static("(no summary)", classes="msg-body msg-system")]
        card = Collapsible(
            *details,
            title="[dim]Story so far (folded)[/]",
            collapsed=True,
            collapsed_symbol="▸",
            expanded_symbol="▾",
            classes="tool-collapsible msg-system",
        )
        self.mount(card)
        self._safe_scroll_end()

    def get_plain_text(self) -> str:
        """Get full conversation as plain text."""
        return "".join(self._plain_chunks).strip()

    def add_user_message(self, text: str) -> None:
        """Add a user message to the view."""
        # New user message should resume tail-following.
        self._resume_follow_output()
        self._clear_live_execution_preview()
        self._release_assistant_activity_tracking()
        self.flush_pending_execution_details()
        # New user-turn → reset per-turn speaker-header dedup state so the
        # next assistant response gets its own header.
        self._last_header_speaker_in_turn = None
        # Drop any leftover bridge segments from an aborted previous turn.
        self._bridge_segment_buffer.clear()
        lines = text.splitlines() or [text]
        quoted = "\n".join(f"> {line}" if line else ">" for line in lines)
        if not self.is_mounted:
            self.write_markdown(f"\n### You\n\n{quoted}\n")
            return
        self._append_plain(f"\n### You\n\n{quoted}\n")
        self._mount_role_header("You", "user")
        self._render_markdown_segments(quoted, role="user")

    def _ensure_stream_timer(self) -> None:
        if self._stream_render_timer is None:
            self._stream_render_timer = self.set_interval(1 / 15.0, self._tick_stream_render)

    def _stop_stream_timer(self) -> None:
        if self._stream_render_timer is not None:
            try:
                self._stream_render_timer.stop()
            except Exception:
                pass
            self._stream_render_timer = None

    # Typewriter tuning. The stream timer runs at 15fps; these are
    # per-tick budgets. CJK costs less budget than Latin so Chinese prose
    # reveals faster (each han char carries ~a word). Sentence-ending
    # punctuation parks the reveal for a few ticks for a reading beat.
    _TW_BASE_BUDGET = 7.0
    _TW_CATCHUP_WINDOW = 20      # ticks allowed to absorb a model burst
    _TW_COST_CJK = 1.0
    _TW_COST_LATIN = 1.6
    _TW_PUNCT_HOLD = {
        "。": 3.0, "！": 3.0, "？": 3.0, "．": 3.0, "…": 3.0, "—": 2.0,
        ".": 2.0, "!": 2.0, "?": 2.0,
        "，": 1.0, "、": 1.0, ",": 1.0, "；": 1.0, ";": 1.0, "\n": 1.0,
    }

    @staticmethod
    def _is_cjk(ch: str) -> bool:
        o = ord(ch)
        return (
            0x4E00 <= o <= 0x9FFF      # CJK unified
            or 0x3040 <= o <= 0x30FF   # hiragana + katakana
            or 0xAC00 <= o <= 0xD7AF   # hangul syllables
            or 0x3400 <= o <= 0x4DBF   # CJK ext-A
            or 0xFF00 <= o <= 0xFFEF   # fullwidth forms
        )

    def _advance_typewriter(self, full: str) -> str:
        """Advance the reveal cursor one tick and return the visible slice.

        Reveal speed is a fixed budget per tick, raised on demand so the
        cursor never lags more than ``_TW_CATCHUP_WINDOW`` ticks behind a
        model that dumped a big block at once. Stops early on punctuation
        to bank a hold.
        """
        total = len(full)
        n = self._assistant_reveal_n
        if n >= total:
            self._assistant_reveal_n = total
            return full
        if self._assistant_reveal_hold > 0:
            self._assistant_reveal_hold -= 1.0
            return full[:n]

        backlog = total - n
        budget = max(self._TW_BASE_BUDGET, backlog / self._TW_CATCHUP_WINDOW)
        spent = 0.0
        end = n
        while spent < budget and end < total:
            ch = full[end]
            end += 1
            spent += self._TW_COST_CJK if self._is_cjk(ch) else self._TW_COST_LATIN
            hold = self._TW_PUNCT_HOLD.get(ch, 0.0)
            if hold:
                self._assistant_reveal_hold = hold
                break
        self._assistant_reveal_n = end
        return full[:end]

    def typewriter_active(self) -> bool:
        """True while the streaming preview is mid-reveal (Esc can skip)."""
        return (
            self._assistant_stream_open
            and self._use_narrative_folding()
            and self._assistant_reveal_n < len(self._assistant_stream_buffer)
        )

    def skip_typewriter(self) -> bool:
        """Jump the reveal straight to the end of the current buffer."""
        if not self.typewriter_active():
            return False
        self._assistant_reveal_n = len(self._assistant_stream_buffer)
        self._assistant_reveal_hold = 0.0
        self._assistant_stream_needs_render = True
        return True

    def _tick_stream_render(self) -> None:
        if self._assistant_activity_widget is not None and self._assistant_activity_animating:
            self._assistant_activity_pulse = (self._assistant_activity_pulse + 1) % 3
            try:
                self._assistant_activity_widget.update(
                    Text(self._assistant_activity_base + self._animated_suffix(self._assistant_activity_pulse))
                )
            except Exception:
                pass

        if self._assistant_stream_widget is not None:
            if self._use_narrative_folding():
                # Typewriter: reveal the buffer at a paced rhythm. The tick
                # must keep firing while the cursor catches up even when no
                # fresh tokens arrived, so render whenever either new text
                # landed OR the reveal is still behind the buffer.
                buf = self._assistant_stream_buffer
                if self._assistant_stream_needs_render or self._assistant_reveal_n < len(buf):
                    revealed = self._advance_typewriter(buf)
                    try:
                        self._assistant_stream_widget.update(
                            self._build_semantic_stream_text(revealed)
                        )
                    except Exception:
                        pass
                    self._assistant_stream_needs_render = False
                    self._safe_scroll_end()
            elif self._assistant_stream_needs_render:
                rendered = self._sanitize_terminal_text(self._assistant_stream_buffer)
                try:
                    self._assistant_stream_widget.update(rendered)
                except Exception:
                    pass
                self._assistant_stream_needs_render = False
                self._safe_scroll_end()

        if self._thinking_stream_needs_render and self._thinking_stream_widget is not None:
            try:
                self._thinking_stream_widget.update(self._thinking_stream_buffer)
            except Exception:
                pass
            self._thinking_stream_needs_render = False
            self._safe_scroll_end()

        # Live thinking ticker — push the tail of the reasoning buffer to
        # the transient input-area ticker so the player can watch the
        # model think even while the full reasoning stays folded away.
        if self._thinking_stream_open:
            self._push_thinking_ticker()

    def _push_thinking_ticker(self) -> None:
        """Send the current reasoning tail to the host's thinking ticker."""
        # Only in play — build/sandbox already shows reasoning inline.
        if not self._use_narrative_folding():
            return
        app_ctx = self._get_app_context()
        if app_ctx is None or not hasattr(app_ctx, "_set_thinking_ticker"):
            return
        buf = self._thinking_stream_buffer or ""
        # Collapse whitespace into a single flowing line, keep the tail —
        # as the buffer grows the visible window slides ("流水").
        flowing = re.sub(r"\s+", " ", buf).strip()
        if not flowing:
            return
        tail = flowing[-180:]
        try:
            app_ctx._set_thinking_ticker(tail)
        except Exception:
            pass

    def add_assistant_chunk(self, text: str, speaker: str = "Narrator") -> None:
        """Add an assistant chunk (streaming).

        Speaker-header dedup: within a single user-turn, if the stream is
        re-opened with the SAME speaker (e.g. after a tool call flushed the
        segment), we do NOT emit another `### Speaker` header or role row —
        the tool cards render inline, and the narrative just continues under
        the already-mounted speaker label. `_last_header_speaker_in_turn` is
        reset when `add_user_message` or `add_assistant_end` fires.

        Hidden agents (presentation_hidden:true in agent.json) short-circuit
        at the top. They skip TUI render, session log, and bridge emit — the
        TUI is the single source of truth, and hidden means hidden everywhere.
        """
        if not text:
            return
        speaker_ref = str(speaker or "Narrator").strip() or "Narrator"
        if self._is_agent_hidden(speaker_ref):
            return
        display_label, _thinking_label, _narrating_label, _acting_label = self._resolve_agent_transcript_meta(speaker_ref)
        speaker_name = speaker_ref or display_label
        if self._assistant_stream_open and self._assistant_stream_speaker != speaker_name:
            self._flush_assistant_stream_segment()
        if not self._assistant_stream_open:
            self._assistant_stream_open = True
            self._assistant_stream_buffer = ""
            self._assistant_stream_speaker = speaker_name
            # Fresh segment → restart the typewriter reveal from zero.
            self._assistant_reveal_n = 0
            self._assistant_reveal_hold = 0.0
            # Only emit a fresh speaker header when this speaker hasn't
            # already spoken in the current user-turn. Otherwise the stream
            # is just resuming after a tool call — keep it visually under
            # the previous header.
            suppress_header = (
                getattr(self, "_last_header_speaker_in_turn", None) == speaker_name
            )
            if not self.is_mounted:
                if not suppress_header:
                    self.write_markdown(f"\n### {display_label}\n\n")
            else:
                if not suppress_header:
                    self._append_plain(f"\n### {display_label}\n\n")
                    self._assistant_header_widget = self._mount_role_header(
                        display_label,
                        "assistant",
                        accent=self._resolve_agent_accent(speaker_ref),
                    )
                    self._mount_assistant_activity_note(speaker_ref, animated=False)
                self._clear_live_execution_preview()
                self._mount_execution_summary_note()
                if self._use_narrative_folding():
                    self._assistant_stream_widget = Static(Text(""), classes="msg-body msg-assistant semantic-stream")
                else:
                    self._assistant_stream_widget = Markdown("", classes="msg-body msg-assistant")
                self.mount(self._assistant_stream_widget)
            self._last_header_speaker_in_turn = speaker_name
            self._notify_portrait(speaker_ref)
        if not self.is_mounted or self._assistant_stream_widget is None:
            self.write_markdown(text)
            return
        self._assistant_stream_buffer += text
        self._assistant_stream_buffer = re.sub(r"\n{3,}", "\n\n", self._assistant_stream_buffer)
        self._append_plain(text)
        self._ensure_stream_timer()
        self._assistant_stream_needs_render = True

    def _flush_assistant_stream_segment(self) -> None:
        """Close current streaming assistant segment while preserving stable scroll behavior."""
        if not self._assistant_stream_open:
            return

        # Capture this speaker's segment BEFORE we clear the buffer, so the
        # bridge emission at turn end can reconstruct the full turn even
        # across speaker changes (orchestrator → town-agent → character-agent)
        # or tool-call interruptions (ask_user).
        seg_text = self._assistant_stream_buffer
        seg_speaker = self._assistant_stream_speaker or "Narrator"
        has_content = bool(seg_text and seg_text.strip())
        if has_content:
            self._bridge_segment_buffer.append((seg_speaker, seg_text))

        if self.is_mounted:
            if self._assistant_stream_widget is not None:
                finalized = self._normalize_markdown(self._assistant_stream_buffer)
                stream_widget = self._assistant_stream_widget
                try:
                    if has_content:
                        self._render_markdown_segments(finalized, role="assistant", before=stream_widget)
                    stream_widget.remove()
                except Exception:
                    try:
                        stream_widget.update(finalized)
                    except Exception:
                        pass
            # Empty segment cleanup: scrub the speaker header + activity
            # note so the transcript doesn't carry a lonely "[Speaker]"
            # row with nothing under it (LLM produced a tool call then
            # delegated and said nothing visible itself).
            if not has_content:
                for ghost in (self._assistant_header_widget, self._assistant_activity_widget):
                    if ghost is not None:
                        try:
                            ghost.remove()
                        except Exception:
                            pass
                self._assistant_header_widget = None
                self._release_assistant_activity_tracking()

        self._assistant_stream_needs_render = False
        self._assistant_stream_open = False
        self._assistant_stream_buffer = ""
        self._assistant_stream_widget = None
        self._assistant_header_widget = None
        self._assistant_stream_speaker = "Narrator"
        self._finalize_assistant_activity_note()
        if getattr(self, "_thinking_stream_open", False) is False:
            self._stop_stream_timer()

    def add_thinking_chunk(self, text: str, speaker: str | None = None) -> None:
        """Append model thinking/reasoning chunk when provider exposes it.

        Hidden agents short-circuit here too — otherwise the reasoning
        stream briefly flashes on screen before the assistant segment
        check hides the actual narrative, giving the "peek-then-hide" UX.
        """
        if not text:
            return
        speaker_ref = str(speaker or "").strip() or None
        if speaker_ref and self._is_agent_hidden(speaker_ref):
            return
        display_label, thinking_label, _narrating_label, _acting_label = self._resolve_agent_transcript_meta(
            speaker_ref
        )
        speaker_name = speaker_ref or display_label
        if self._thinking_stream_open and self._thinking_stream_speaker != speaker_name:
            self._flush_thinking_stream_segment()

        if not self._thinking_stream_open:
            self._thinking_stream_open = True
            self._thinking_stream_buffer = ""
            self._thinking_stream_speaker = speaker_name
            label = f"[{display_label} {thinking_label}]"
            if not self.is_mounted:
                self.write_markdown(f"\n{label}")
            else:
                self._append_plain(f"\n{label}")
                self._thinking_stream_widget = Static("", classes="thinking-content")
                row = Horizontal(
                    Static(label, classes="thinking-label"),
                    self._thinking_stream_widget,
                    classes="thinking-row",
                )
                if self._use_narrative_folding():
                    self._mount_assistant_activity_note(speaker_ref or display_label, animated=True)
                    self._current_thinking_execution_item = self._queue_execution_widget(
                        row,
                        self._format_thinking_summary(display_label, thinking_label, ""),
                        kind="thinking",
                    )
                    self._update_live_execution_preview()
                else:
                    self.mount(row)

        if not self.is_mounted or self._thinking_stream_widget is None:
            self.write_markdown(text)
            return

        self._thinking_stream_buffer += text
        self._thinking_stream_buffer = re.sub(r"\n{3,}", "\n\n", self._thinking_stream_buffer)
        if self._current_thinking_execution_item is not None:
            self._current_thinking_execution_item["summary"] = self._truncate_inline(
                self._format_thinking_summary(display_label, thinking_label, self._thinking_stream_buffer),
                max_len=88,
            )
            self._update_live_execution_preview()
        self._append_plain(text)
        self._ensure_stream_timer()
        self._thinking_stream_needs_render = True

    def _flush_thinking_stream_segment(self) -> None:
        """Close current thinking segment while preserving current rendered content."""
        if not self._thinking_stream_open:
            return

        if self.is_mounted and self._thinking_stream_widget is not None:
            try:
                self._thinking_stream_widget.update(self._thinking_stream_buffer)
            except Exception:
                pass

        self._thinking_stream_needs_render = False
        self._thinking_stream_open = False
        self._thinking_stream_buffer = ""
        self._thinking_stream_widget = None
        self._thinking_stream_speaker = None
        self._current_thinking_execution_item = None
        # The thinking segment is done — drop the transient ticker so it
        # never lingers (it must "not stay", per the live-ticker spec).
        app_ctx = self._get_app_context()
        if app_ctx is not None and hasattr(app_ctx, "_clear_thinking_ticker"):
            try:
                app_ctx._clear_thinking_ticker()
            except Exception:
                pass
        if getattr(self, "_assistant_stream_open", False) is False:
            self._stop_stream_timer()

    def add_markdown_message(self, text: str) -> None:
        """Append a complete assistant message."""
        if not text.strip():
            return
        self._flush_thinking_stream_segment()
        self._flush_assistant_stream_segment()
        body = self._normalize_markdown(text.strip())
        host = self._host_label()
        if not self.is_mounted:
            self.write_markdown(f"\n### {host}\n\n{body}\n")
            return
        self._append_plain(f"\n### {host}\n\n{body}\n")
        self._mount_role_header(
            host, "assistant", accent=self._resolve_agent_accent("narrator")
        )
        self._clear_live_execution_preview()
        self._mount_execution_summary_note()
        self._mount_assistant_activity_note("narrator", animated=False)
        self._render_markdown_segments(body, role="assistant")
        self.flush_pending_execution_details()

    @staticmethod
    def _clean_error_text(raw: str) -> str:
        """Reduce a raw error/exception string to one readable line.

        Drops Python tracebacks and over-long tails — the transcript
        should never show a stack dump to a player.
        """
        text = str(raw or "").strip()
        if not text:
            return "(unknown error)"
        # If a traceback leaked in, keep only the final exception line.
        if "Traceback (most recent call last)" in text:
            tail = [ln for ln in text.splitlines() if ln.strip()]
            text = tail[-1].strip() if tail else text
        else:
            text = text.splitlines()[0].strip()
        if len(text) > 240:
            text = text[:237] + "…"
        return text

    def add_agent_error(self, speaker: str | None, message: str) -> None:
        """Render an agent failure as a styled callout with retry/skip.

        Replaces the old raw ``[red]Error: …[/]`` line. The callout is a
        bordered block (accent color); below it sits an action row with
        Retry / Skip buttons handled by ``NeonRPApp.on_button_pressed``.
        """
        from neonrp.tui.i18n import get_message

        locale = self._resolve_view_locale()
        clean = self._clean_error_text(message)
        speaker_label = str(speaker or "").strip() or "agent"

        if not self.is_mounted:
            self.write(f"\n[red]{get_message(locale, 'agent.error.title')}: {clean}[/]\n")
            return

        seq = self._agent_error_seq
        self._agent_error_seq += 1

        self._mount_content_divider()

        title = Text()
        title.append("⚠ ", style="bold #e0a64a")
        title.append(get_message(locale, "agent.error.title"), style="bold #e0a64a")
        title.append(f"  ·  {speaker_label}", style="dim #9a8fb0")
        self.mount(Static(title, classes="agent-error-callout agent-error-head"))
        self.mount(Static(Text(clean, style="#e4d9c4"),
                          classes="agent-error-callout agent-error-body"))

        actions = Horizontal(
            Button(get_message(locale, "agent.error.retry"),
                   id=f"agent-error-retry-{seq}", classes="agent-error-btn"),
            Button(get_message(locale, "agent.error.skip"),
                   id=f"agent-error-skip-{seq}", classes="agent-error-btn"),
            # 模型上游挂了(opencode 免费档「Model is
            # unavailable」)时只有 重试/跳过,换模型要自己想起 /settings。
            Button(get_message(locale, "agent.error.settings"),
                   id=f"agent-error-settings-{seq}", classes="agent-error-btn"),
            id=f"agent-error-actions-{seq}",
            classes="agent-error-actions",
        )
        self.mount(actions)
        self._safe_scroll_end()

    def add_named_assistant_message(self, name: str, text: str, *, mirror_to_bridge: bool = True) -> None:
        """Append a complete assistant-like message with a custom speaker name.

        Skips hidden agents entirely (no TUI, no session, no bridge).
        Unlike the streaming path, this is a one-shot whole message — so
        we also append directly to the per-turn bridge-segment buffer
        here, since there's no flush hook to capture it.

        ``mirror_to_bridge=False`` renders to the local transcript ONLY.
        Used for the ask_user narration echo: the bridge already receives
        that text via the explicit ``ask_user`` event, so buffering it
        here too would double-post it to Discord at turn end.
        """
        speaker_ref = str(name or "Sub-agent").strip() or "Sub-agent"
        if self._is_agent_hidden(speaker_ref):
            return
        display_label, _thinking_label, _narrating_label, _acting_label = self._resolve_agent_transcript_meta(speaker_ref)
        speaker = display_label
        if not text.strip():
            return
        self._flush_thinking_stream_segment()
        self._flush_assistant_stream_segment()
        # Mirror to the bridge buffer so the next `add_assistant_end`
        # (which Discord relies on) sees this one-shot narration.
        if mirror_to_bridge:
            self._bridge_segment_buffer.append((speaker, text.strip()))
        body = self._normalize_markdown(text.strip())
        if not self.is_mounted:
            self.write_markdown(f"\n### {speaker}\n\n{body}\n")
            return
        self._append_plain(f"\n### {speaker}\n\n{body}\n")
        self._mount_role_header(
            speaker, "assistant", accent=self._resolve_agent_accent(speaker_ref)
        )
        self._clear_live_execution_preview()
        self._mount_execution_summary_note()
        self._mount_assistant_activity_note(speaker_ref, animated=False)
        self._render_markdown_segments(body, role="assistant")
        self.flush_pending_execution_details()

    def _finalize_predicted_tool_indicators(
        self,
        confirmed_tool_name: str | None = None,
        detail: str = "not called",
    ) -> None:
        """Close unresolved predicted cards once real tool flow is known."""
        confirmed = self._canonical_tool_name(confirmed_tool_name or "") if confirmed_tool_name else ""
        updated = False
        for state in self._tool_cards:
            if state.get("done") or not state.get("predicted"):
                continue
            state_tool_name = self._canonical_tool_name(str(state.get("tool_name", "")))
            if confirmed and state_tool_name == confirmed:
                continue
            state["done"] = True
            state["ok"] = False
            state["detail"] = detail
            card = state.get("card")
            params = state.get("params", {})
            if not isinstance(params, dict):
                params = {}
            if card is not None:
                card.title = self._format_tool_title(
                    state_tool_name or "tool", params, detail=detail, done=True, ok=False
                )
            updated = True
        if updated:
            if all(state.get("done") for state in self._tool_cards):
                self._stop_tool_spinner()
            self._safe_scroll_end()

    def add_tool_indicator(self, tool_name: str, params: dict[str, Any], predicted: bool = False) -> None:
        """Add a tool use indicator."""
        tool_name = self._canonical_tool_name(tool_name)
        if not predicted:
            self._finalize_predicted_tool_indicators(confirmed_tool_name=tool_name)

        # Deduplicate/upgrade existing in-flight indicator for the same tool.
        for state in self._tool_cards:
            if state.get("done"):
                continue
            state_tool_name = self._canonical_tool_name(str(state.get("tool_name", "")))
            if state_tool_name != tool_name:
                continue
            state_params = state.get("params")
            state_predicted = bool(state.get("predicted"))
            if state_params == params and state_predicted == predicted:
                return
            # Upgrade predicted placeholder to a real running tool once confirmed.
            if state_predicted and not predicted:
                state["predicted"] = False
                state["detail"] = "running"
                if isinstance(state_params, dict) and not state_params and params:
                    state["params"] = params
                    self._refresh_tool_card_details(state)
                card = state.get("card")
                effective_params = state.get("params", params)
                if card is not None and isinstance(effective_params, dict):
                    card.title = self._format_tool_title(tool_name, effective_params, detail="running", done=False)
                self._safe_scroll_end()
                return
            # Upgrade an early placeholder (no params yet) once full args arrive.
            if isinstance(state_params, dict) and not state_params and params:
                state["params"] = params
                self._refresh_tool_card_details(state)
                card = state.get("card")
                if card is not None:
                    detail = "preparing" if bool(state.get("predicted")) else "running"
                    card.title = self._format_tool_title(tool_name, params, detail=detail, done=False)
                self._safe_scroll_end()
                return
            # If we already have an in-flight card for this tool and the new call has
            # no params (early calling marker), do not create duplicates.
            if not params:
                return

        # Seal current stream first so tool cards stay chronologically stable.
        self._flush_thinking_stream_segment()
        self._flush_assistant_stream_segment()

        body = self._tool_body_markdown(params)
        if not self.is_mounted:
            self.write_markdown(f"\n### Tool `{tool_name}`\n\n{body}\n")
            return
        self._append_plain(f"\n### Tool `{tool_name}`\n\n{body}\n")
        details = self._build_segment_widgets(body, role="tool")
        if not details:
            details = [Static("(no details)", classes="msg-body msg-tool")]
        card = Collapsible(
            *details,
            title=self._format_tool_title(
                tool_name,
                params,
                detail="preparing" if predicted else "running",
                done=False,
            ),
            collapsed=True,
            collapsed_symbol="▸",
            expanded_symbol="▾",
            classes="tool-collapsible msg-tool",
        )
        if self._use_narrative_folding():
            self._queue_execution_widget(card, self._tool_execution_summary(tool_name, params), kind="tool")
            self._update_live_execution_preview()
        else:
            self.mount(card)
        self._tool_cards.append(
            {
                "card": card,
                "tool_name": tool_name,
                "params": params,
                "result_raw": None,
                "done": False,
                "detail": "preparing" if predicted else "running",
                "ok": True,
                "predicted": predicted,
            }
        )
        self._ensure_tool_spinner()
        self._safe_scroll_end()

    def complete_tool_indicator(self, tool_name: str, params: dict[str, Any], raw_result: str) -> None:
        """Finalize one running tool indicator with concise result details."""
        tool_name = self._canonical_tool_name(tool_name)
        self._finalize_predicted_tool_indicators(confirmed_tool_name=tool_name)
        target: dict[str, Any] | None = None
        for state in self._tool_cards:
            if state.get("done"):
                continue
            state_tool_name = self._canonical_tool_name(str(state.get("tool_name", "")))
            if state_tool_name == tool_name and state.get("params") == params:
                target = state
                break
        if target is None:
            for state in self._tool_cards:
                if state.get("done"):
                    continue
                state_tool_name = self._canonical_tool_name(str(state.get("tool_name", "")))
                if state_tool_name == tool_name:
                    target = state
                    break
        if target is None:
            for state in self._tool_cards:
                if state.get("done") or state.get("predicted"):
                    continue
                target = state
                break
        if target is None:
            for state in self._tool_cards:
                if not state.get("done"):
                    target = state
                    break
        if target is None:
            return

        if params and isinstance(target.get("params"), dict) and not target.get("params"):
            target["params"] = params
            self._refresh_tool_card_details(target)

        ok, detail = self._tool_result_detail(tool_name, raw_result)
        target["done"] = True
        target["ok"] = ok
        target["detail"] = detail
        target["result_raw"] = raw_result
        target["predicted"] = False
        self._refresh_tool_card_details(target)
        card = target["card"]
        target_tool_name = str(target.get("tool_name", tool_name))
        target_params = target.get("params", params)
        if not isinstance(target_params, dict):
            target_params = params
        card.title = self._format_tool_title(target_tool_name, target_params, detail=detail, done=True, ok=ok)
        if all(state.get("done") for state in self._tool_cards):
            self._stop_tool_spinner()
        self._safe_scroll_end()

    def fail_open_tool_indicators(self, detail: str = "aborted") -> None:
        """Mark any running tool indicators as failed and stop spinner animation."""
        self._clear_live_execution_preview()
        updated = False
        for state in self._tool_cards:
            if state.get("done"):
                continue
            state["done"] = True
            state["ok"] = False
            state["detail"] = detail
            state["result_raw"] = json.dumps({"status": "error", "error": detail}, ensure_ascii=False)
            self._refresh_tool_card_details(state)
            card = state.get("card")
            tool_name = str(state.get("tool_name", "tool"))
            params = state.get("params", {})
            if not isinstance(params, dict):
                params = {}
            if card is not None:
                card.title = self._format_tool_title(tool_name, params, detail=detail, done=True, ok=False)
            updated = True
        if updated or self._tool_spinner_timer is not None:
            self._stop_tool_spinner()
            self._safe_scroll_end()

    def _format_tool_title(
        self,
        tool_name: str,
        params: dict[str, Any],
        detail: str,
        done: bool,
        ok: bool = True,
    ) -> str:
        summary = self._tool_summary(tool_name, params)
        # Keep a single space gap to avoid odd spacing with some terminal glyph rendering.
        gap = " "
        if done:
            # Keep completion marks understated (avoid emoji-heavy appearance).
            neutral_details = {"not called", "cancelled"}
            if str(detail or "").strip().lower() in neutral_details:
                icon = "○"
                color = self._NEUTRAL_COLOR
            else:
                icon = "✓" if ok else "✕"
                color = self._OK_COLOR if ok else self._ERR_COLOR
            return f"[{color}]{icon}[/]{gap}[{self._TOOL_TITLE_TEXT_COLOR}]{summary}[/]"
        idx = self._tool_spinner_frame % len(self._SPINNER_FRAMES)
        frame = self._SPINNER_FRAMES[idx]
        color = self._SPINNER_COLORS[idx % len(self._SPINNER_COLORS)]
        return f"[{color}]{frame}[/]{gap}[{self._TOOL_TITLE_TEXT_COLOR}]{summary}[/]"

    def _ensure_tool_spinner(self) -> None:
        if self._tool_spinner_timer is None:
            self._tool_spinner_timer = self.set_interval(0.18, self._tick_tool_spinner)

    def _stop_tool_spinner(self) -> None:
        if self._tool_spinner_timer is not None:
            try:
                self._tool_spinner_timer.stop()
            except Exception:
                pass
            self._tool_spinner_timer = None

    def _tick_tool_spinner(self) -> None:
        self._tool_spinner_frame = (self._tool_spinner_frame + 1) % len(self._SPINNER_FRAMES)
        for state in self._tool_cards:
            if state.get("done"):
                continue
            card = state["card"]
            card.title = self._format_tool_title(
                state["tool_name"],
                state["params"],
                detail=state.get("detail", "running"),
                done=False,
            )

    @staticmethod
    def _tool_result_detail(tool_name: str, raw_result: str) -> tuple[bool, str]:
        """Convert tool result JSON to short one-line detail."""
        try:
            payload = json.loads(raw_result)
        except Exception:
            return True, "done"

        status = str(payload.get("status", "success")).lower()
        if status == "cancelled":
            return False, "cancelled"
        ok = status in {"success", "proposal_submitted"}
        if not ok:
            err = str(payload.get("error", "failed"))
            err = err.replace("\n", " ")
            if len(err) > 50:
                err = f"{err[:47]}..."
            return False, err

        if status == "proposal_submitted" or tool_name == "submit_proposal":
            return True, "proposal ready"

        data = payload.get("data")
        # M31 B1: a direct write says what it did to the file, not how many
        # bytes went out — "created +18" reads; "1042 bytes written" doesn't.
        if isinstance(data, dict):
            change = data.get("change")
            if isinstance(change, dict):
                headline = str(change.get("headline", "") or "").strip()
                if headline:
                    return True, headline
        if tool_name == "glob" and isinstance(data, dict):
            count = data.get("count")
            if isinstance(count, int):
                return True, f"{count} files"
            files = data.get("files")
            if isinstance(files, list):
                return True, f"{len(files)} files"
        if tool_name == "read_file" and isinstance(data, dict):
            content = str(data.get("content", ""))
            lines = len(content.splitlines()) if content else 0
            truncated = bool(data.get("truncated"))
            if truncated:
                return True, f"{lines} lines (truncated)"
            return True, f"{lines} lines"
        if tool_name == "ask_user":
            # New format: {"answers": {"0": "label"}} or old format: {"data": {"response": ...}}
            answers = data.get("answers") if isinstance(data, dict) else None
            if isinstance(answers, dict):
                first_answer = str(next(iter(answers.values()), "")).strip().replace("\n", " ")
                if first_answer:
                    if len(first_answer) > 36:
                        first_answer = f"{first_answer[:33]}..."
                    return True, f"selected: {first_answer}"
                return True, "answered"
            # Legacy fallback
            if isinstance(data, dict):
                response = str(data.get("response", "")).strip().replace("\n", " ")
                if response:
                    if len(response) > 36:
                        response = f"{response[:33]}..."
                    return True, f"selected: {response}"
            return True, "answered"

        return True, "done"

    def add_todo_display(self, items: list[dict]) -> None:
        """Add todo list display."""
        if not items:
            return
        lines = ["### Todo", ""]
        for item in items:
            status = item.get("status", "pending")
            content = item.get("content", "")
            if status in {"completed", "done"}:
                lines.append(f"- `[x]` {content}")
            elif status == "in_progress":
                lines.append(f"- `[>]` {content}")
            else:
                lines.append(f"- `[ ]` {content}")
        body = "\n".join(lines)
        if not self.is_mounted:
            self.write_markdown(f"\n{body}\n")
            return
        self._append_plain(f"\n{body}\n")
        self._mount_role_header("Todo", "system")
        self._render_markdown_segments("\n".join(lines[2:]), role="system")

    def add_skill_indicator(self, skill_name: str) -> None:
        """Add skill loading indicator."""
        if not self.is_mounted:
            self.write_markdown(f"\n### Skill\n\nLoading `{skill_name}`\n")
            return
        body = f"Loading `{skill_name}`"
        self._append_plain(f"\n### Skill\n\n{body}\n")
        self._mount_role_header("Skill", "system")
        self._render_markdown_segments(body, role="system")

    def set_semantic_mode(self, mode: str) -> None:
        """Enable L14.5 semantic-annotation footer for play mode."""
        self._semantic_mode = mode

    def set_semantic_layer(self, layer: int) -> None:
        """Switch transcript visibility: 1 = narrative only, 2 = + chips, 3 = + raw trace."""
        layer = max(1, min(3, int(layer)))
        for cls in ("layer-1", "layer-2", "layer-3"):
            try:
                self.remove_class(cls)
            except Exception:
                pass
        try:
            self.add_class(f"layer-{layer}")
        except Exception:
            pass
        self._semantic_layer = layer

    def add_assistant_end(self) -> None:
        """Mark end of assistant response."""
        self._flush_thinking_stream_segment()
        # Snapshot the buffer before it gets cleared by flush, so callers can
        # run post-hoc parsing (e.g. L14.5 semantic annotations in play).
        self._last_assistant_text = self._assistant_stream_buffer
        turn_text = self._assistant_stream_buffer
        if not self._assistant_stream_open:
            if not self.is_mounted:
                self.write_markdown("\n")
        else:
            if not self.is_mounted:
                self.write_markdown("\n")
            else:
                self._flush_assistant_stream_segment()
                self._append_plain("\n")
                self.flush_pending_execution_details()
                self._release_assistant_activity_tracking()
                self._safe_scroll_end()
        # Turn is finished — reset the per-turn header-dedup state so the
        # next turn's first assistant text gets a proper speaker header.
        self._last_header_speaker_in_turn = None

        # Bridge broadcast: emit from the accumulated per-segment buffer so
        # multi-speaker turns AND turns interrupted by tool calls (ask_user)
        # get a complete relay. In play mode we keep only the primary
        # narrator's segments — sub-agents (town-agent, character-agent) are
        # internal state-updaters that would clutter Discord.
        segments = list(self._bridge_segment_buffer)
        self._bridge_segment_buffer.clear()
        self._emit_turn_to_bridges(segments)

        # L14.5 — append semantic chips below the narrative in play mode.
        semantic_mode = getattr(self, "_semantic_mode", "")
        speaker_for_parse = segments[0][0] if segments else (
            getattr(self, "_assistant_stream_speaker", "") or "world"
        )
        if semantic_mode == "play" and turn_text:
            try:
                from neonrp.core.semantic_events import (
                    SEMANTIC_EVENT_ENABLED_MODES,
                    parse_semantic_events,
                )
                if semantic_mode in SEMANTIC_EVENT_ENABLED_MODES:
                    events = parse_semantic_events(
                        turn_text,
                        speaker_hint=speaker_for_parse,
                        mode=semantic_mode,
                    )
                    if events:
                        self.emit_semantic_annotations(events)
            except Exception:
                # Rendering errors must never break transcript flow.
                pass

    def _emit_turn_to_bridges(self, segments: list[tuple[str, str]]) -> None:
        """Fan out a completed turn to registered bridges (Discord etc).

        `segments` already excludes hidden agents — they were short-circuited
        at the `add_assistant_chunk` / `add_named_assistant_message` entry
        point. So whatever reaches here also reached the TUI, by design.

        We emit one merged message per turn, joined by blank lines, using
        the first visible speaker's name as the Discord header. This keeps
        Discord messages coherent rather than one-chunk-per-post.
        """
        if not segments:
            return
        try:
            app = self._get_app_context()
            emit = getattr(app, "_emit_bridge_event", None)
            if not callable(emit):
                return
            speaker = str(segments[0][0] or "").strip()
            if not speaker or speaker.lower() in self._HOST_REFS:
                speaker = self._host_label()
            text = "\n\n".join(tx.strip() for _sp, tx in segments if tx.strip())
            if text.strip():
                emit("narrator_text", speaker=speaker, text=text.strip())
        except Exception:
            pass

    def get_last_assistant_text(self) -> str:
        """Return the raw text of the most recently completed assistant turn."""
        return getattr(self, "_last_assistant_text", "") or ""

    def emit_semantic_annotations(self, events: list[Any]) -> None:
        """Render L2 semantic chips below the latest assistant turn (L14.5).

        Accepts a list of `SemanticEvent` objects. Only the subset with
        layer=='L2' (state_update / rule_check / execution_summary) is
        rendered — L1 events are already visible in the streamed text.
        Unknown layers are ignored.
        """
        if not events or not self.is_mounted:
            return
        try:
            from neonrp.core.semantic_events import SemanticEvent as _SE  # local import
        except Exception:
            _SE = None
        lines: list[str] = []
        icon_map = {
            "state_update":       "⟳",
            "rule_check":         "◉",
            "execution_summary":  "∴",
        }
        color_map = {
            "state_update":       "#86EFAC",
            "rule_check":         "#FCD34D",
            "execution_summary":  "#5BE0B0",
        }
        for ev in events:
            layer = getattr(ev, "layer", None)
            etype = getattr(ev, "type", None)
            text = (getattr(ev, "text", "") or "").strip()
            if layer != "L2" or etype not in icon_map or not text:
                continue
            icon = icon_map[etype]
            color = color_map[etype]
            lines.append(f"[dim]{icon}[/] [{color}]{text}[/]")
        if not lines:
            return
        try:
            self.mount(
                Static(
                    "\n".join(lines),
                    classes="msg-body msg-semantic-footer",
                )
            )
            self._safe_scroll_end()
        except Exception:
            pass

    def action_copy_selection(self) -> None:
        """Copy full transcript text to clipboard."""
        transcript = self.get_plain_text()
        if transcript:
            self.app.copy_to_clipboard(transcript)
            self.notify(f"Copied {len(transcript)} chars")

    @classmethod
    def _sanitize_terminal_text(cls, text: str) -> str:
        """Sanitize text sequences that can break Rich/Textual width calculation."""
        cleaned = cls._UNSAFE_CONTROL_RE.sub("", text)
        clusters = cls._GRAPHEME_CLUSTER_RE.findall(cleaned)
        safe_clusters: list[str] = []
        for cluster in clusters:
            if cluster == "\u200d":
                continue
            if cluster.endswith("\u200d"):
                cluster = cls._DANGLING_ZWJ_RE.sub("", cluster)
                cluster = cluster.rstrip("\u200d")
                if not cluster:
                    continue
            safe_clusters.append(cluster)
        return "".join(safe_clusters)

    @classmethod
    def _normalize_markdown(cls, text: str) -> str:
        """Normalize markdown code fences for better readability/highlighting."""

        normalized_text = cls._KEYCAP_RE.sub(r"\1", text)
        normalized_text = cls._sanitize_terminal_text(normalized_text)

        def repl(match: re.Match[str]) -> str:
            lang = (match.group(1) or "").strip().lower()
            body = match.group(2).strip()
            if lang == "json":
                try:
                    parsed = json.loads(body)
                    body = json.dumps(parsed, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            if lang:
                return f"```{lang}\n{body}\n```"
            return f"```\n{body}\n```"

        return cls._FENCED_CODE_RE.sub(repl, normalized_text)


class AskUserInlinePanel(Container):
    """Inline ask_user panel rendered between conversation and main input."""

    CANCEL_RESULT = "__ask_user_cancelled__"
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+backslash", "toggle_minimize", "Minimize / expand"),
    ]
    # Plain ASCII so it renders on terminal fonts that lack the unicode
    # geometric shapes (▾ ▸ printed as box-of-tofu on some setups).
    _BTN_EXPANDED = "v"
    _BTN_MINIMIZED = "^"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._question = ""
        self._options: list[str] = []
        self._on_submit: Callable[[str], None] | None = None
        # When True, panel is visible but compact: just the question line +
        # the toggle button. Inner options / input / hint are hidden so the
        # user can read the transcript or type in the main input bar
        # without losing the still-pending prompt.
        self._minimized = False

    def compose(self) -> ComposeResult:
        locale = getattr(self.app, "ui_locale", None) or getattr(self.app, "locale", "en")
        placeholder = get_message(locale or "en", "ask_user.placeholder")
        esc_hint = get_message(locale or "en", "ui.hint.esc_cancel")
        with Horizontal(id="ask-inline-header"):
            yield Static("", id="ask-inline-question")
            yield Button(
                self._BTN_EXPANDED,
                id="ask-inline-minimize",
                variant="default",
            )
        with VerticalScroll(id="ask-inline-options-scroll"):
            yield Vertical(id="ask-inline-options")
        yield ImeInput(placeholder=placeholder, id="ask-inline-input")
        with Horizontal(id="ask-inline-actions"):
            yield Static(f"[dim]{esc_hint}[/]", id="ask-inline-hint")

    def on_mount(self) -> None:
        self.add_class("hidden")

    @property
    def is_active(self) -> bool:
        return self._on_submit is not None

    @property
    def is_minimized(self) -> bool:
        return self._minimized

    def show_prompt(self, question: str, options: list[str], on_submit: Any) -> None:
        """Render prompt + options and wait for user response."""
        self._question = str(question or "").strip()
        self._options = [str(opt or "").strip() for opt in options if str(opt or "").strip()]
        self._on_submit = on_submit

        question_widget = self.query_one("#ask-inline-question", Static)
        question_widget.update(f"[bold]{self._question}[/]" if self._question else "[bold]Question[/]")

        options_box = self.query_one("#ask-inline-options", Vertical)
        options_box.remove_children()
        if self._options:
            for i, opt in enumerate(self._options):
                options_box.mount(Button(f"{i + 1}. {opt}", id=f"ask-inline-opt-{i}", variant="default"))
        else:
            options_box.mount(Static("[dim](No options provided; please type your response.)[/]"))

        hint_widget = self.query_one("#ask-inline-hint", Static)
        self.remove_class("options-only")
        locale = getattr(self.app, "ui_locale", None) or getattr(self.app, "locale", "en")
        hint_widget.update(f"[dim]{get_message(locale or 'en', 'ui.hint.esc_cancel_enter_submit')}[/]")

        ask_input = self.query_one("#ask-inline-input", Input)
        ask_input.value = ""
        # Always start expanded — minimization is a per-prompt choice the
        # user has to opt into.
        self._minimized = False
        self.remove_class("minimized")
        self._sync_minimize_button()
        self.remove_class("hidden")
        self.add_class("visible")
        ask_input.focus()

    def hide_prompt(self) -> None:
        """Hide panel and clear pending prompt state."""
        self._on_submit = None
        self._question = ""
        self._options = []
        self._minimized = False
        self.remove_class("visible")
        self.remove_class("minimized")
        self.add_class("hidden")
        try:
            self.query_one("#ask-inline-options", Vertical).remove_children()
        except Exception:
            pass

    def cancel_current(self) -> bool:
        """Cancel current prompt if one is active."""
        if not self.is_active:
            return False
        self._submit(self.CANCEL_RESULT)
        return True

    def toggle_minimize(self) -> bool:
        """Collapse / expand the panel without dismissing the pending prompt.

        Returns True if the toggle had effect (i.e. there's an active
        prompt). When minimized, the question line + toggle button remain
        visible so the user knows the agent is still waiting; the options
        list, input, and hint are CSS-hidden so the transcript reclaims
        most of the screen. Re-expand by pressing the same hot-key or
        clicking the button.
        """
        if not self.is_active:
            return False
        self._minimized = not self._minimized
        if self._minimized:
            self.add_class("minimized")
        else:
            self.remove_class("minimized")
        self._sync_minimize_button()
        if not self._minimized:
            try:
                self.query_one("#ask-inline-input", Input).focus()
            except Exception:
                pass
        return True

    def _sync_minimize_button(self) -> None:
        try:
            btn = self.query_one("#ask-inline-minimize", Button)
        except Exception:
            return
        btn.label = self._BTN_MINIMIZED if self._minimized else self._BTN_EXPANDED

    def _submit(self, value: str) -> None:
        callback = self._on_submit
        self.hide_prompt()
        if callback is not None:
            callback(value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "ask-inline-minimize":
            self.toggle_minimize()
            event.stop()
            return
        if btn_id.startswith("ask-inline-opt-"):
            idx = int(btn_id.split("-")[-1])
            if 0 <= idx < len(self._options):
                self._submit(self._options[idx])
                event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "ask-inline-input":
            return
        value = event.value.strip()
        if value:
            self._submit(value)
        else:
            self._submit(self.CANCEL_RESULT)
        event.stop()

    def action_cancel(self) -> None:
        self.cancel_current()

    def action_toggle_minimize(self) -> None:
        self.toggle_minimize()


def section(title: str) -> tuple[str, str]:
    """Build a centered section-header row for ChoicePickerScreen options."""
    return (title, "__section__")


def spacer() -> tuple[str, str]:
    """Build a blank spacer row for ChoicePickerScreen options."""
    return ("", "__spacer__")


def _ellipsize(text: str, width: int) -> str:
    """Trim to ``width`` columns, ending with `…` if it had to cut.

    Counts code points, not terminal columns — good enough for the
    mostly-Latin labels in pickers; wide CJK glyphs will end up slightly
    longer than ``width`` but never wrap (rows are ``height: 1``).
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


class ChoicePickerScreen(ModalScreen[str | None]):
    """Generic modal picker with section headers + spacers.

    Options list supports three kinds of rows:
    - Selectable option: ``(label, value)`` — left-aligned Button
    - Section header:    ``(title, "__section__")`` — centered Static, bold
    - Spacer:            ``("", "__spacer__")``     — blank line

    Keyboard navigation skips non-selectable rows.
    """

    CSS = """
    ChoicePickerScreen {
        align: center middle;
        background: #09090B;
    }

    #choice-modal {
        width: 80%;
        max-width: 96;
        max-height: 85%;
        background: #09090B;
        border-top: double #00B960;
        border-bottom: double #00B960;
        border-left: solid #00B960;
        border-right: solid #00B960;
        padding: 1 2;
        layout: vertical;
    }

    #choice-title {
        height: auto;
        margin-bottom: 0;
        color: #E4E4E7;
        text-style: bold;
        content-align: center middle;
    }

    #choice-hint {
        height: auto;
        margin-bottom: 1;
        color: #71717A;
        content-align: center middle;
    }

    #choice-list {
        height: 1fr;
        margin-bottom: 1;
        overflow-y: auto;
    }

    #choice-list Button {
        width: 100%;
        height: 1;
        margin-bottom: 0;
        background: #09090B;
        color: #D4D4D8;
        border: none;
        padding: 0 1;
        content-align: left middle;
        text-style: none;
    }

    #choice-list Button:focus {
        background: #18181B;
        color: #4ADE80;
        text-style: bold;
    }

    #choice-list .section-header {
        width: 100%;
        height: 1;
        margin: 0;
        padding: 0 1;
        color: #18FF82;
        content-align: center middle;
        text-style: bold;
    }

    #choice-list .row-spacer {
        width: 100%;
        height: 1;
        background: #09090B;
    }

    #choice-actions {
        height: auto;
        color: #71717A;
    }

    #choice-actions Button {
        background: #09090B;
        color: #71717A;
        border: none;
        padding: 0 1;
        height: 1;
    }

    #choice-actions Button:focus {
        color: #A1A1AA;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("up", "move_prev", "Prev"),
        Binding("down", "move_next", "Next"),
        Binding("left", "move_prev", "Prev"),
        Binding("right", "move_next", "Next"),
        Binding("tab", "move_next", "Next"),
        Binding("shift+tab", "move_prev", "Prev"),
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        hint: str | None = None,
        *,
        initial_focus: str | None = None,
    ):
        super().__init__()
        self._title = title
        self._options = options
        # Default hint resolved lazily in `compose` via `self.app.ui_locale`
        # so it honors the user's selected language. Callers may still pass
        # an explicit hint string.
        self._hint = hint
        # When the caller rebuilds the picker (e.g. toggling a checkbox in
        # batch-delete mode), pass the previously-focused option's value here
        # so focus lands on the same row instead of snapping back to the top.
        self._initial_focus = initial_focus
        # Index of the currently focused row in `options` (may point at a
        # selectable row only; headers/spacers are always skipped).
        self._focus_index = self._first_selectable_index()

    def _is_selectable(self, idx: int) -> bool:
        if not (0 <= idx < len(self._options)):
            return False
        _, value = self._options[idx]
        return value not in ("__section__", "__spacer__")

    def _first_selectable_index(self) -> int:
        for i in range(len(self._options)):
            if self._is_selectable(i):
                return i
        return 0

    def _last_selectable_index(self) -> int:
        for i in range(len(self._options) - 1, -1, -1):
            if self._is_selectable(i):
                return i
        return 0

    def _next_selectable_from(self, start: int, direction: int) -> int:
        """Return next selectable index moving in `direction` (+1/-1), wrapping."""
        if not self._options:
            return 0
        n = len(self._options)
        for step in range(1, n + 1):
            idx = (start + direction * step) % n
            if self._is_selectable(idx):
                return idx
        return start  # no selectable rows

    def compose(self) -> ComposeResult:
        hint = self._hint
        if hint is None:
            locale = getattr(self.app, "ui_locale", None) or getattr(self.app, "locale", "en")
            hint = get_message(locale or "en", "ui.hint.picker_default")
        with Container(id="choice-modal"):
            yield Static(f"[bold #18FF82]◆[/] [bold]{self._title}[/]", id="choice-title")
            yield Static(f"[dim]{hint}[/]", id="choice-hint")
            with VerticalScroll(id="choice-list"):
                for i, (label, value) in enumerate(self._options):
                    if value == "__section__":
                        yield Static(label, classes="section-header")
                    elif value == "__spacer__":
                        yield Static("", classes="row-spacer")
                    else:
                        yield Button(label, id=f"choice-opt-{i}", variant="default")
            with Horizontal(id="choice-actions"):
                yield Button("Back", id="choice-cancel", variant="default")

    def on_mount(self) -> None:
        # Honor initial_focus if the caller asked to land on a specific row
        # (e.g. multi-select pickers rebuilding after a toggle).
        target = self._first_selectable_index()
        if self._initial_focus is not None:
            for i, (_, value) in enumerate(self._options):
                if value == self._initial_focus and self._is_selectable(i):
                    target = i
                    break
        self._focus_button(target)

    def _focus_button(self, index: int) -> None:
        if not self._options:
            return
        if not self._is_selectable(index):
            index = self._next_selectable_from(index - 1, 1)
        self._focus_index = index
        try:
            self.query_one(f"#choice-opt-{index}", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "choice-cancel":
            self.dismiss(None)
            return
        if not btn_id.startswith("choice-opt-"):
            return
        idx = int(btn_id.split("-")[-1])
        if not self._is_selectable(idx):
            return
        self._focus_index = idx
        self.dismiss(self._options[idx][1])

    def action_move_prev(self) -> None:
        self._focus_button(self._next_selectable_from(self._focus_index, -1))

    def action_move_next(self) -> None:
        self._focus_button(self._next_selectable_from(self._focus_index, 1))

    def action_confirm(self) -> None:
        if self._is_selectable(self._focus_index):
            self.dismiss(self._options[self._focus_index][1])

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Specialized picker subclasses — all share ChoicePickerScreen's section /
# spacer support, keyboard nav, and styling. Each only customizes its title.
# Kept as distinct types so existing callers and tests (isinstance checks)
# keep working.
# ---------------------------------------------------------------------------

class SessionPickerScreen(ChoicePickerScreen):
    """Modal for selecting a saved session or starting a new one."""

    def __init__(self, branch: str, options: list[tuple[str, str]]):
        super().__init__(f"Sessions ({branch})", options)


class ModelPickerScreen(ChoicePickerScreen):
    """Modal for selecting an active model_ref."""

    def __init__(self, options: list[tuple[str, str]]):
        super().__init__("Select Active Model", options)


class SavePickerScreen(ChoicePickerScreen):
    """Modal for selecting a save snapshot to load."""

    def __init__(self, options: list[tuple[str, str]]):
        super().__init__("Load Snapshot", options)


class WorldPickerScreen(ChoicePickerScreen):
    """Modal for selecting a WorldLines world template."""

    def __init__(self, options: list[tuple[str, str]]):
        super().__init__("Choose WorldLines World", options)


class SpinnerWorkerScreen(ModalScreen[str]):
    """Run a blocking worker in a thread while showing an animated spinner.

    The worker returns a result string which is passed to the caller via the
    usual `push_screen(..., on_dismiss)` callback. Esc cancels — the worker
    thread keeps running but its result is discarded.
    """

    CSS = """
    SpinnerWorkerScreen {
        align: center middle;
        background: #09090B;
    }

    #spinner-modal {
        width: 60%;
        max-width: 80;
        min-height: 7;
        background: #09090B;
        border-top: double #00B960;
        border-bottom: double #00B960;
        border-left: solid #00B960;
        border-right: solid #00B960;
        padding: 1 2;
        layout: vertical;
    }

    #spinner-title {
        height: auto;
        color: #E4E4E7;
        text-style: bold;
        content-align: center middle;
        margin-bottom: 1;
    }

    #spinner-body {
        height: auto;
        color: #D4D4D8;
        content-align: center middle;
    }

    #spinner-hint {
        height: auto;
        color: #71717A;
        content-align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, title: str, label: str, worker: Callable[[], str], hint: str | None = None):
        super().__init__()
        self._title = title
        self._label = label
        self._worker = worker
        self._hint = hint
        self._frame_idx = 0
        self._result: str | None = None
        self._done = False
        self._tick_timer: Any = None

    def compose(self) -> ComposeResult:
        hint = self._hint
        if hint is None:
            locale = getattr(self.app, "ui_locale", None) or getattr(self.app, "locale", "en")
            hint = get_message(locale or "en", "ui.hint.esc_cancel")
        with Container(id="spinner-modal"):
            yield Static(f"[bold #18FF82]◆[/] [bold]{self._title}[/]", id="spinner-title")
            yield Static(self._render_body(), id="spinner-body")
            yield Static(f"[dim]{hint}[/]", id="spinner-hint")

    def _render_body(self) -> str:
        frame = self._FRAMES[self._frame_idx % len(self._FRAMES)]
        return f"[#18FF82]{frame}[/]  {self._label}"

    def on_mount(self) -> None:
        self._tick_timer = self.set_interval(0.08, self._tick_spinner)
        threading.Thread(target=self._run_worker, daemon=True, name="spinner-worker").start()

    def _tick_spinner(self) -> None:
        if self._done:
            return
        self._frame_idx = (self._frame_idx + 1) % len(self._FRAMES)
        try:
            self.query_one("#spinner-body", Static).update(self._render_body())
        except Exception:
            pass

    def _run_worker(self) -> None:
        try:
            result = self._worker()
        except Exception as exc:
            result = f"✗  {exc}"
        self._result = result
        self._done = True
        try:
            self.app.call_from_thread(self._finish)
        except Exception:
            pass

    def _finish(self) -> None:
        self._stop_timer()
        self.dismiss(self._result or "")

    def _stop_timer(self) -> None:
        if self._tick_timer is not None:
            try:
                self._tick_timer.stop()
            except Exception:
                pass
            self._tick_timer = None

    def action_cancel(self) -> None:
        # User cancelled before worker finished — leave the daemon thread to
        # finish on its own; we just discard the result.
        self._done = True
        self._stop_timer()
        self.dismiss("")


class ImeInput(Input):
    """Single-line Input that re-anchors the terminal cursor on focus so CJK
    IME composition (Chinese / Japanese input) works.

    Textual's bare Input reports its caret to the terminal, but on first focus
    the widget's region may not be laid out yet, so the OS IME reads a stale
    cursor-position escape and parks its candidate window at the screen origin
    (0, 0) — where many terminals then refuse to compose at all ("can't type
    Chinese in the launcher"). Re-pushing the laid-out caret after the first
    refresh fixes it. This mirrors the IME handling SubmitTextArea already does
    for the multi-line editor (WOR-14).
    """

    def _sync_terminal_cursor(self) -> None:
        if not self.has_focus or not self.is_mounted:
            return
        try:
            self.app.cursor_position = self.cursor_screen_offset
            self.refresh()
        except Exception:
            pass

    def _on_focus(self, event) -> None:  # noqa: ANN001 — textual event
        super()._on_focus(event)
        self.call_after_refresh(self._sync_terminal_cursor)


class TextInputScreen(ModalScreen[str | None]):
    """Generic modal text input used by WorldLines settings + create flows.

    Pure-TUI styling: no thick border, a single prompt line ("> ") in the
    spirit of Claude Code's input shell.
    """

    CSS = """
    TextInputScreen {
        align: center middle;
        background: #09090B;
    }

    #text-input-modal {
        width: 80%;
        max-width: 96;
        background: #09090B;
        border-top: double #00B960;
        border-bottom: double #00B960;
        border-left: solid #00B960;
        border-right: solid #00B960;
        padding: 1 2;
        layout: vertical;
    }

    #text-input-title {
        height: auto;
        margin-bottom: 0;
        color: #E4E4E7;
        text-style: bold;
    }

    #text-input-hint {
        height: auto;
        margin-bottom: 1;
        color: #71717A;
    }

    #text-input-field {
        height: 3;
        margin-bottom: 1;
        background: #09090B;
        color: #E4E4E7;
        border: none;
    }

    #text-input-actions {
        height: auto;
    }

    #text-input-actions Button {
        background: #09090B;
        color: #71717A;
        border: none;
        padding: 0 1;
        height: 1;
    }

    #text-input-actions Button:focus {
        color: #4ADE80;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("enter", "submit", "Submit"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, default: str = "", hint: str | None = None):
        super().__init__()
        self._title = title
        self._default = default
        self._hint = hint

    def compose(self) -> ComposeResult:
        hint = self._hint
        if hint is None:
            locale = getattr(self.app, "ui_locale", None) or getattr(self.app, "locale", "en")
            hint = get_message(locale or "en", "ui.hint.text_input_default")
        with Container(id="text-input-modal"):
            yield Static(f"[bold #18FF82]▸[/] [bold]{self._title}[/]", id="text-input-title")
            yield Static(f"[dim]{hint}[/]", id="text-input-hint")
            yield ImeInput(value=self._default, id="text-input-field")
            with Horizontal(id="text-input-actions"):
                yield Button("Save", id="text-input-save", variant="primary")
                yield Button("Cancel", id="text-input-cancel")

    def on_mount(self) -> None:
        try:
            self.query_one("#text-input-field", Input).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "text-input-save":
            self._submit_value()
        elif btn_id == "text-input-cancel":
            self.dismiss(None)

    def action_submit(self) -> None:
        self._submit_value()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit_value(self) -> None:
        try:
            value = self.query_one("#text-input-field", Input).value
        except Exception:
            value = self._default
        self.dismiss(value)


class SoulSeedScreen(ModalScreen[tuple[str, str, str] | None]):
    """Immersive entry for soul creation.

    Asks for a character name + a one-sentence description, then Generate.
    A secondary action switches to the canon template picker.

    Dismiss values:
      ("generate", name, description) — author from the seed
      ("template", "", "")            — user wants the template picker
      None                            — cancelled
    """

    CSS = """
    SoulSeedScreen {
        align: center middle;
        background: #09090B;
    }

    #soul-seed-modal {
        width: 80%;
        max-width: 96;
        background: #09090B;
        border-top: double #00B960;
        border-bottom: double #00B960;
        border-left: solid #00B960;
        border-right: solid #00B960;
        padding: 1 2;
        layout: vertical;
    }

    #soul-seed-title {
        height: auto;
        color: #E4E4E7;
        text-style: bold;
    }

    #soul-seed-hint {
        height: auto;
        margin-bottom: 1;
        color: #71717A;
    }

    #soul-seed-name {
        height: 3;
        margin-bottom: 1;
        background: #09090B;
        color: #E4E4E7;
        border: none;
    }

    #soul-seed-desc-label {
        height: 1;
        color: #71717A;
    }

    /* Multi-line, soft-wrapping description so long text wraps onto new
       lines instead of scrolling endlessly to the right. */
    #soul-seed-desc {
        height: 5;
        margin-bottom: 1;
        background: #09090B;
        border: none;
    }

    #soul-seed-actions {
        height: auto;
        color: #71717A;
    }

    /* Custom TuiButton (not native): flat, dark, muted → green on focus. */
    #soul-seed-actions TuiButton {
        width: auto;
        height: 1;
        background: #18181B;
        color: #A1A1AA;
        border: none;
        padding: 0 2;
        margin-right: 2;
        text-style: none;
    }

    #soul-seed-actions TuiButton:focus {
        background: #27272A;
        color: #18FF82;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("enter", "generate", "Generate"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, lang: str = "en"):
        super().__init__()
        self._lang = lang

    def _t(self, key: str) -> str:
        return get_message(self._lang or "en", key)

    def compose(self) -> ComposeResult:
        from neonrp.tui.buttons import TuiButton
        with Container(id="soul-seed-modal"):
            yield Static(f"[bold #5BE0B0]◆[/] [bold]{self._t('create.soul_title')}[/]", id="soul-seed-title")
            yield Static(f"[dim]{self._t('create.soul_seed_hint')}[/]", id="soul-seed-hint")
            yield ImeInput(placeholder=self._t("create.soul_seed_name_placeholder"), id="soul-seed-name")
            yield Static(f"[dim]{self._t('create.soul_seed_desc_placeholder')}[/]", id="soul-seed-desc-label")
            yield TextArea("", id="soul-seed-desc", soft_wrap=True, show_line_numbers=False)
            with Horizontal(id="soul-seed-actions"):
                yield TuiButton(self._t("create.soul_seed_generate"), id="soul-seed-generate")
                yield TuiButton(self._t("create.soul_seed_use_template"), id="soul-seed-template")

    def on_mount(self) -> None:
        try:
            self.query_one("#soul-seed-name", Input).focus()
        except Exception:
            pass

    def on_tui_button_pressed(self, event) -> None:
        btn_id = event.button.id or ""
        if btn_id == "soul-seed-generate":
            self.action_generate()
        elif btn_id == "soul-seed-template":
            self.dismiss(("template", "", ""))

    def action_generate(self) -> None:
        try:
            name = self.query_one("#soul-seed-name", Input).value.strip()
            desc = self.query_one("#soul-seed-desc", TextArea).text.strip()
        except Exception:
            name, desc = "", ""
        if not name:
            try:
                self.query_one("#soul-seed-name", Input).focus()
            except Exception:
                pass
            return
        self.dismiss(("generate", name, desc))

    def action_cancel(self) -> None:
        self.dismiss(None)


class AvatarSeedScreen(ModalScreen[tuple[str, str] | None]):
    """Create a 分身 (player avatar) — a lightweight, local-only player
    profile, separate from the soul library. Asks for a name + a one-line
    self-description. Dismiss: ``(name, description)`` or ``None``."""

    CSS = """
    AvatarSeedScreen { align: center middle; background: #09090B; }
    #avatar-seed-modal {
        width: 80%; max-width: 96; background: #09090B;
        border-top: double #00B960; border-bottom: double #00B960;
        border-left: solid #00B960; border-right: solid #00B960;
        padding: 1 2; layout: vertical;
    }
    #avatar-seed-title { height: auto; color: #E4E4E7; text-style: bold; }
    #avatar-seed-hint { height: auto; margin-bottom: 1; color: #71717A; }
    #avatar-seed-name {
        height: 3; margin-bottom: 1; background: #09090B; color: #E4E4E7; border: none;
    }
    #avatar-seed-desc-label { height: 1; color: #71717A; }
    #avatar-seed-desc { height: 5; margin-bottom: 1; background: #09090B; border: none; }
    #avatar-seed-actions { height: auto; color: #71717A; }
    #avatar-seed-actions TuiButton {
        width: auto; height: 1; background: #18181B; color: #A1A1AA;
        border: none; padding: 0 2; margin-right: 2; text-style: none;
    }
    #avatar-seed-actions TuiButton:focus { background: #27272A; color: #18FF82; text-style: bold; }
    """

    BINDINGS = [
        Binding("enter", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, *, locale: str = "en") -> None:
        super().__init__()
        self._locale = locale

    def _t(self, key: str) -> str:
        return get_message(self._locale or "en", key)

    def compose(self) -> ComposeResult:
        from neonrp.tui.buttons import TuiButton
        with Container(id="avatar-seed-modal"):
            yield Static(f"[bold #5BE0B0]◆[/] [bold]{self._t('avatar.seed_title')}[/]", id="avatar-seed-title")
            yield Static(f"[dim]{self._t('avatar.seed_hint')}[/]", id="avatar-seed-hint")
            yield ImeInput(placeholder=self._t("avatar.seed_name_placeholder"), id="avatar-seed-name")
            yield Static(f"[dim]{self._t('avatar.seed_desc_placeholder')}[/]", id="avatar-seed-desc-label")
            yield TextArea("", id="avatar-seed-desc", soft_wrap=True, show_line_numbers=False)
            with Horizontal(id="avatar-seed-actions"):
                yield TuiButton(self._t("avatar.seed_save"), id="avatar-seed-save")

    def on_mount(self) -> None:
        try:
            self.query_one("#avatar-seed-name", Input).focus()
        except Exception:
            pass

    def on_tui_button_pressed(self, event) -> None:
        if (event.button.id or "") == "avatar-seed-save":
            self.action_save()

    def action_save(self) -> None:
        try:
            name = self.query_one("#avatar-seed-name", Input).value.strip()
            desc = self.query_one("#avatar-seed-desc", TextArea).text.strip()
        except Exception:
            name, desc = "", ""
        if not name:
            try:
                self.query_one("#avatar-seed-name", Input).focus()
            except Exception:
                pass
            return
        self.dismiss((name, desc))

    def action_cancel(self) -> None:
        self.dismiss(None)


class CastingScreen(ModalScreen[dict | None]):
    """Two selections on one screen (the casting ② screen):

    * LEFT  — キャラクター選択 / 分身: who the PLAYER is (the protagonist).
              Single-select; "就做我自己" (no avatar soul) is the default.
    * RIGHT — 带入世界的角色: souls cast INTO the world as NPCs. Multi-select.

    Both lists come from the soul library (``list_souls``). Returns
    ``{"player": <soul dir|None>, "bring_in": [<soul dir>, ...]}`` or
    ``None`` if cancelled.
    """

    CSS = """
    CastingScreen { align: center middle; background: #09090B; }
    #cast-modal {
        width: 90%; max-width: 110; max-height: 88%;
        background: #09090B;
        border-top: double #00B960; border-bottom: double #00B960;
        border-left: solid #00B960; border-right: solid #00B960;
        padding: 1 2; layout: vertical;
    }
    #cast-title { height: auto; color: #E4E4E7; text-style: bold; content-align: center middle; }
    #cast-cols { height: 1fr; layout: horizontal; }
    .cast-col { width: 1fr; height: 100%; padding: 0 1; }
    .cast-col-title { height: 1; color: #18FF82; text-style: bold; margin-bottom: 1; }
    #cast-player { height: 1fr; }
    #cast-bring { height: 1fr; }
    #cast-preview {
        height: auto; max-height: 22; overflow-y: auto; border: round #14361f;
        padding: 0 1; margin: 1 0; color: #A1A1AA;
    }
    .preview-npc-name { height: 1; color: #18FF82; text-style: bold; margin-top: 1; }
    .preview-field-label { height: 1; color: #71717A; margin-top: 1; }
    #cast-actions { height: auto; align: center middle; }
    #cast-actions Button { margin: 0 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(
        self,
        *,
        title: str,
        souls: list[dict],
        locale: str,
        avatars: list[dict] | None = None,
        world_id: str | None = None,
        world_mode: str = "orchestrator",
    ) -> None:
        super().__init__()
        self._souls = souls
        # 分身 (player avatars) come from a SEPARATE local store, not the soul
        # library — a soul cannot be the protagonist. Each entry is a
        # lightweight player profile: {name, summary, data, path, ...}.
        self._avatars = list(avatars or [])
        self._title = title
        self._locale = locale
        self._world_id = world_id
        # Game mode is BAKED INTO the world (runtime_contract) — read-only
        # here. fast = no characters; orchestrator / multi-agent = NPCs OK.
        self._world_mode = world_mode or "orchestrator"
        # Populated by _render_after; None = no preview done yet.
        self._preview_results: list | None = None

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical

        m = lambda k: get_message(self._locale, k)  # noqa: E731
        mode_key = f"cast.mode_{self._world_mode.replace('-', '_')}"
        with Vertical(id="cast-modal"):
            yield Static(self._title, id="cast-title")
            # Mode is the world's property — shown read-only, not switchable.
            yield Static(
                f"{m('cast.mode_title')}: {m(mode_key)}", id="cast-mode", markup=False
            )
            with Horizontal(id="cast-cols"):
                with Vertical(classes="cast-col", id="cast-player-col"):
                    yield Static(m("cast.player_title"), classes="cast-col-title", markup=False)
                    # Player avatar (分身) — single-select; default = 就做我自己.
                    # Sourced from the local avatar store, NOT the soul library.
                    yield self._build_avatar_radio()
                    yield Button(m("cast.new_avatar"), id="cast-new-avatar", classes="cast-new-avatar")
                with Vertical(classes="cast-col"):
                    yield Static(m("cast.bring_title"), classes="cast-col-title", markup=False)
                    # Bring-in NPCs — multi-select. The world's OWN souls
                    # (native) come first, marked, and the on-stage ones are
                    # pre-checked (default present, removable); external souls
                    # from the library follow, added on top.
                    yield SelectionList(
                        *(
                            Selection(
                                self._bring_label(s), i,
                                bool(s.get("native") and s.get("active")),
                            )
                            for i, s in enumerate(self._souls)
                        ),
                        id="cast-bring",
                    )
            # Placement preview: BEFORE (raw card) instantly; AFTER (what the
            # character becomes in THIS world) on demand via the casting skill.
            # VerticalScroll so editable fields can be mounted per NPC.
            with VerticalScroll(id="cast-preview"):
                yield Static(m("cast.preview_hint"), id="cast-preview-hint", markup=False)
            with Horizontal(id="cast-actions"):
                yield Button(m("cast.preview"), id="cast-preview-btn")
                yield Button(m("cast.start"), id="cast-start", variant="primary")
                yield Button(m("cast.back"), id="cast-back")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _build_avatar_radio(self) -> RadioSet:
        """Fresh single-select RadioSet for the 分身 picker. RadioButtons are
        composed inline in the constructor so single-select works (a dynamic
        post-mount mount breaks it). Index 0 = 就做我自己 (no avatar)."""
        m = lambda k: get_message(self._locale, k)  # noqa: E731
        return RadioSet(
            RadioButton(m("character.use_default"), value=True),
            *(RadioButton(self._avatar_label(a)) for a in self._avatars),
            id="cast-player",
        )

    @staticmethod
    def _avatar_label(avatar: dict) -> str:
        name = str(avatar.get("name") or avatar.get("file") or "?")
        summary = str(avatar.get("summary") or "").strip()
        # Mark the world's baked protagonist (the "prior" avatar) so the player
        # can tell it apart from their own local avatars.
        prefix = "★ " if avatar.get("native") else ""
        label = f"{prefix}{name}"
        return f"{label} — {summary[:40]}" if summary else label

    @staticmethod
    def _bring_label(soul: dict) -> str:
        """Label for a bring-in soul. Native (world's own) souls get a marker:
        ● = on-stage in the world, ○ = native but currently off-stage; external
        library souls get no marker (they are added on top)."""
        name = str(soul.get("display_name") or soul.get("name") or soul.get("sid") or "?")
        if soul.get("native"):
            return f"{'● ' if soul.get('active') else '○ '}{name}"
        return name

    def _selected_avatar(self) -> dict | None:
        """The chosen 分身 profile dict, or None for 就做我自己."""
        rs = self.query_one("#cast-player", RadioSet)
        pidx = rs.pressed_index
        if pidx is not None and pidx >= 1 and pidx - 1 < len(self._avatars):
            return dict(self._avatars[pidx - 1].get("data") or {})
        return None

    def _chosen_souls(self) -> list[tuple[str, dict]]:
        """Bring-in NPCs selected for the adaptation preview. The 分身 is a
        lightweight local avatar (no world-adaptation), so it is not previewed
        here — only souls cast as NPCs get the AFTER adaptation."""
        out: list[tuple[str, dict]] = []
        sel = self.query_one("#cast-bring", SelectionList)
        for i in sel.selected:
            out.append(("NPC", self._souls[i]))
        return out

    @staticmethod
    def _before_text(soul: dict) -> str:
        from neonrp.core.placement import _soul_profile

        try:
            p = _soul_profile(Path(str(soul["path"])))
            return f"{p['name']} — {p['summary'][:80]}"
        except Exception:
            return str(soul.get("display_name", "?"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cast-preview-btn":
            self._render_preview()
            return
        if event.button.id == "cast-new-avatar":
            self._create_avatar()
            return
        if event.button.id == "cast-back":
            self.dismiss(None)
            return
        if event.button.id == "cast-start":
            # 分身 → the chosen avatar's lightweight profile dict (or None for
            # 就做我自己). The CLI merges it into the world's player slot.
            player = self._selected_avatar()
            sel = self.query_one("#cast-bring", SelectionList)
            # Native souls are ALREADY in the world (materialized at
            # instantiation) — only EXTERNAL library souls get cast here, or
            # they'd be double-cast. Selected native souls are reported
            # separately as `active_souls` (which of the world's own cast is
            # on-stage), to be applied via set_active_souls at launch.
            bring = [
                str(self._souls[i]["path"])
                for i in sel.selected
                if not self._souls[i].get("native")
            ]
            active_souls = [
                str(self._souls[i].get("instance_id") or "")
                for i in sel.selected
                if self._souls[i].get("native") and self._souls[i].get("instance_id")
            ]
            # Collect placement edits + location confirmations from the preview
            # panel (if the user previewed). Not previewing = no overrides.
            placements = self._read_placements() if bring else None
            npc_locations = self._read_locations() if bring else None
            # Mode is the world's baked property, not user-chosen here.
            self.dismiss({
                "player": player,
                "bring_in": bring,
                "active_souls": active_souls,
                "mode": self._world_mode,
                "placements": placements,
                "npc_locations": npc_locations,
            })

    def _create_avatar(self) -> None:
        """Open the 分身 seed modal; on save, add it to the local avatar store
        and rebuild the picker with the new avatar available."""
        def on_seed(result: tuple[str, str] | None) -> None:
            if not result:
                return
            name, desc = result
            if not name.strip():
                return
            from neonrp import players as _players

            _players.save_avatar({"name": name.strip(), "summary": desc.strip()})
            try:
                self._avatars = _players.list_avatars()
            except Exception:
                self._avatars = []
            # Rebuild the RadioSet in place. remove() is async — await it
            # before mounting the replacement, or the new #cast-player collides
            # with the not-yet-removed old one (DuplicateIds). Fresh inline
            # RadioButtons keep single-select intact.
            self.run_worker(self._rebuild_avatar_radio(), exclusive=True)

        self.app.push_screen(
            AvatarSeedScreen(locale=self._locale), on_seed
        )

    async def _rebuild_avatar_radio(self) -> None:
        try:
            await self.query_one("#cast-player", RadioSet).remove()
        except Exception:
            pass
        col = self.query_one("#cast-player-col", Vertical)
        await col.mount(
            self._build_avatar_radio(),
            before=self.query_one("#cast-new-avatar", Button),
        )

    def _render_preview(self) -> None:
        """Show BEFORE (raw cards) instantly; if a world is known, kick a
        worker to fill in AFTER (what each becomes in this world)."""
        pane = self.query_one("#cast-preview", VerticalScroll)
        chosen = self._chosen_souls()
        if not chosen:
            self._clear_preview()
            pane.mount(Static(get_message(self._locale, "cast.preview_none")))
            return
        lines = [f"[{role}] {self._before_text(soul)}" for role, soul in chosen]
        if self._world_id:
            lines += ["", get_message(self._locale, "cast.adapting")]
            self._clear_preview()
            pane.mount(Static("\n".join(lines)))
            self.run_worker(lambda: self._preview_worker(chosen), thread=True)
        else:
            self._clear_preview()
            pane.mount(Static("\n".join(lines)))

    def _clear_preview(self) -> None:
        """Remove all children from the preview pane except the hint."""
        try:
            pane = self.query_one("#cast-preview", VerticalScroll)
            pane.remove_children()
        except Exception:
            pass

    def _preview_worker(self, chosen: list[tuple[str, dict]]) -> None:
        from neonrp.core.cast_agent import preview_placement

        results = []
        for role, soul in chosen:
            r = preview_placement(Path(str(soul["path"])), self._world_id or "")
            results.append((role, soul, r))
        self.app.call_from_thread(self._render_after, results)

    def _render_after(self, results: list) -> None:
        """Show AFTER adaptation with editable placement fields + location
        selectors per NPC. The user can tweak role_in_world / why_here /
        relationship_to_player / current_goal and pick a starting location
        before casting.

        Every NPC ALWAYS gets a location selector + editable fields — even
        when the LLM adaptation preview failed (missing/invalid key, a weak
        model, or an unparseable reply). On failure we degrade to empty
        fields the user can fill in by hand instead of dead-ending with just
        a "preview failed" line that left no way to place or cast (WOR-20)."""
        # Normalize a failed preview (None) into an empty overlay so the
        # downstream readers still collect this NPC's location + fields.
        norm = [(role, soul, (r or {})) for (role, soul, r) in results]
        self._preview_results = norm
        pane = self.query_one("#cast-preview", VerticalScroll)
        # Clear existing children
        try:
            pane.remove_children()
        except Exception:
            pass

        m = lambda k: get_message(self._locale, k)  # noqa: E731
        loc_opts = self._build_location_options()

        for i, (role, soul, r) in enumerate(norm):
            pane.mount(Static(f"▸ {self._before_text(soul)}", classes="preview-npc-name"))
            if not r:
                # Adaptation preview unavailable — still fully placeable by
                # hand via the selector + empty fields mounted just below.
                pane.mount(Static(
                    m("cast.preview_fail"),
                    id=f"preview-fail-{i}",
                    classes="preview-field-label",
                ))
            # Location selector — default = "和我在一起" (co-locate with player).
            pane.mount(Static(m("cast.location_label"), classes="preview-field-label"))
            pane.mount(Select(
                loc_opts,
                prompt=m("cast.location_default"),
                id=f"preview-loc-{i}",
                classes="preview-loc",
            ))
            # Editable placement fields
            pane.mount(Static(m("cast.field_role"), classes="preview-field-label"))
            pane.mount(ImeInput(value=str(r.get("role_in_world", "")), id=f"preview-role-{i}"))
            pane.mount(Static(m("cast.field_why"), classes="preview-field-label"))
            pane.mount(ImeInput(value=str(r.get("why_here", "")), id=f"preview-why-{i}"))
            pane.mount(Static(m("cast.field_rel"), classes="preview-field-label"))
            pane.mount(ImeInput(value=str(r.get("relationship_to_player", "")), id=f"preview-rel-{i}"))
            pane.mount(Static(m("cast.field_goal"), classes="preview-field-label"))
            pane.mount(ImeInput(value=str(r.get("current_goal", "")), id=f"preview-goal-{i}"))

        # Locations default to "with you" — explain how to change them.
        pane.mount(Static(
            f"\n{m('cast.location_hint')}", id="preview-loc-hint",
        ))

    def _build_location_options(self) -> list[tuple[str, str]]:
        """Read location nodes from the world template's world_map.json.
        Returns ``[(display_label, node_id), ...]`` for the Select widget."""
        if not self._world_id:
            return []
        try:
            import importlib.resources as _res
            from neonrp.worlds import get_world

            world = get_world(self._world_id)
            template = (world or {}).get("template") or self._world_id
            from neonrp.core.place_tree import WORLD, level_doc

            tpl_root = Path(str(_res.files("neonrp") / "templates" / template))
            wm = level_doc(tpl_root, WORLD)  # world_map.json nodes, or the template's top place folders
            if wm is not None:
                nodes = wm.get("nodes") or []
                return [
                    (f"{n.get('name', n.get('id', '?'))} ({n.get('id', '?')})", str(n.get("id", "")))
                    for n in nodes if n.get("id")
                ]
        except Exception:
            pass
        return []

    def _read_placements(self) -> dict[str, dict]:
        """Collect edited placement fields from the preview widgets.
        Returns ``{soul_path: {role_in_world, why_here, ...}, ...}``."""
        placements: dict[str, dict] = {}
        if not getattr(self, "_preview_results", None):
            return placements
        for i, (_role, soul, r) in enumerate(self._preview_results):
            # No `if not r: continue` — a failed preview still mounts the
            # fields (empty), and the user may have filled them in by hand.
            try:
                placements[str(soul["path"])] = {
                    "role_in_world": self.query_one(f"#preview-role-{i}", Input).value,
                    "why_here": self.query_one(f"#preview-why-{i}", Input).value,
                    "relationship_to_player": self.query_one(f"#preview-rel-{i}", Input).value,
                    "current_goal": self.query_one(f"#preview-goal-{i}", Input).value,
                }
            except Exception:
                pass
        return placements

    def _read_locations(self) -> dict[str, str]:
        """Collect location selections from the preview widgets.
        Returns ``{soul_path: node_id, ...}`` for NPCs whose location was
        explicitly changed from the default ("和我在一起")."""
        locations: dict[str, str] = {}
        if not getattr(self, "_preview_results", None):
            return locations
        for i, (_role, soul, r) in enumerate(self._preview_results):
            # No `if not r: continue` — the location selector is mounted even
            # when the adaptation preview failed, so honor any explicit pick.
            try:
                sel = self.query_one(f"#preview-loc-{i}", Select)
                if sel.value != Select.BLANK:
                    locations[str(soul["path"])] = str(sel.value)
            except Exception:
                pass
        return locations


class HubUploadScreen(ModalScreen[None]):
    """Upload a world or soul to WorldHub.

    Auth flow: opens browser to the Hub account page (non-blocking), user
    copies their token and pastes it below. The token is saved locally so
    subsequent uploads skip this step.
    """

    CSS = """
    HubUploadScreen { align: center middle; background: #09090B; }
    #hub-upload-modal {
        width: 80%; max-width: 100; max-height: 90%;
        background: #09090B;
        border-top: double #00B960; border-bottom: double #00B960;
        border-left: solid #00B960; border-right: solid #00B960;
        padding: 1 2; layout: vertical;
    }
    #hub-upload-title { height: auto; color: #E4E4E7; text-style: bold; }
    #hub-upload-auth { height: auto; margin: 1 0; color: #A1A1AA; }
    #hub-token-row { height: auto; margin-bottom: 1; layout: horizontal; }
    #hub-token-input { width: 1fr; }
    #hub-upload-list { height: 1fr; margin: 1 0; }
    #hub-upload-actions { height: auto; align: center middle; }
    #hub-upload-actions Button { margin: 0 1; }
    #hub-upload-feedback { height: auto; margin-top: 1; color: #71717A; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(self, *, kind: str = "worlds", locale: str = "en") -> None:
        super().__init__()
        self._kind = kind  # "worlds" or "souls"
        self._locale = locale
        self._token: str | None = None
        self._items: list = []

    def _t(self, key: str) -> str:
        try:
            return get_message(self._locale, key)
        except Exception:
            return key

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical
        kind_label = self._t("hub.upload_world_title") if self._kind == "worlds" else self._t("hub.upload_soul_title")
        # Build the item list at compose time — no dynamic mount/remove dance.
        options, self._items = self._build_item_options()
        with Vertical(id="hub-upload-modal"):
            yield Static(f"[bold #5BE0B0]◆[/] [bold]{kind_label}[/]", id="hub-upload-title")
            yield Static("", id="hub-upload-auth")
            # Token input row — shown when not logged in, hidden when logged in.
            with Horizontal(id="hub-token-row"):
                yield Input(placeholder=self._t("hub.token_placeholder"), id="hub-token-input")
                yield Button(self._t("hub.save_token"), id="hub-save-token-btn")
            with Vertical(id="hub-upload-list"):
                yield SelectionList[int](*options, id="hub-upload-sel")
            with Horizontal(id="hub-upload-actions"):
                yield Button(self._t("hub.login_btn"), id="hub-login-btn")
                yield Button(self._t("hub.upload_btn"), id="hub-upload-btn", variant="primary")
                yield Button(self._t("cast.back"), id="hub-back-btn")
            yield Static("", id="hub-upload-feedback")

    def _build_item_options(self) -> tuple[list[tuple[str, int]], list]:
        """Return (options_for_SelectionList, items) for the current kind."""
        if self._kind == "worlds":
            # World *sources* first (what belongs on the hub), then saved
            # runs, tagged — one of the two worlds on the hub today was a
            # timestamped run folder uploaded by mistake.
            from neonrp.worlds import list_owned_worlds, list_saved_games

            items: list = []
            options: list[tuple[str, int]] = []
            try:
                for w in list_owned_worlds():
                    items.append({"path": Path(str(w.get("template") or w.get("source_dir") or "")), "display_name": w.get("name") or w.get("id"), "is_source": True})
            except Exception:
                pass
            try:
                for g in list_saved_games():
                    items.append({**g, "is_source": False})
            except Exception:
                pass
            tag = self._t("hub.save_tag")
            for i, it in enumerate(items):
                label = str(it.get("display_name") or it.get("dir_name") or it.get("path"))
                options.append((f"🌍 {label}" if it.get("is_source") else f"💾 {label}  {tag}", i))
            return options, items
        else:
            from neonrp.core.souls import list_souls
            try:
                souls = list_souls()
                return (
                    [(s.get("display_name", s["sid"]), i) for i, s in enumerate(souls)],
                    souls,
                )
            except Exception:
                return [], []

    def on_mount(self) -> None:
        self._token = None
        try:
            from neonrp.core.hub_auth import get_hub_token
            self._token = get_hub_token()
        except Exception:
            pass
        self._refresh_auth_status()

    def _refresh_auth_status(self) -> None:
        try:
            auth = self.query_one("#hub-upload-auth", Static)
            token_row = self.query_one("#hub-token-row", Horizontal)
        except Exception:
            return
        if self._token:
            auth.update(f"[#18FF82]✓ {self._t('hub.logged_in')}[/]")
            token_row.display = False
        else:
            auth.update(f"[#F59E0B]⚠ {self._t('hub.not_logged_in')}[/]")
            token_row.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "hub-login-btn":
            self._open_browser_to_account()
        elif bid == "hub-save-token-btn":
            self._save_pasted_token()
        elif bid == "hub-upload-btn":
            self._do_upload()
        elif bid == "hub-back-btn":
            self.dismiss(None)

    def _set_feedback(self, msg: str) -> None:
        try:
            self.query_one("#hub-upload-feedback", Static).update(msg)
        except Exception:
            pass

    def _open_browser_to_account(self) -> None:
        """Sign in with the Worldlines account (10-02: one sign-in for Jev, the relay and uploads) — off the UI thread.
        A pasted Hub token (the row below) still works for old accounts."""
        from neonrp.core import worldlines_auth as wa

        self._set_feedback(self._t("account.logging_in"))

        def worker() -> None:
            try:
                wa.connect(on_url=lambda u: self.app.call_from_thread(self._set_feedback, self._t("account.open_url").format(url=u)))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._set_feedback, "[red]" + self._t("account.failed").format(err=str(exc)[:160]) + "[/]")
                return
            from neonrp.core.hub_auth import get_hub_token

            self._token = get_hub_token()
            self.app.call_from_thread(self._refresh_auth_status)
            self.app.call_from_thread(self._set_feedback, "[#18FF82]" + self._t("account.done") + "[/]")

        self.run_worker(worker, exclusive=True, thread=True, name="hub-login")

    def _save_pasted_token(self) -> None:
        """Read the token from the input field, validate, and persist."""
        try:
            raw = self.query_one("#hub-token-input", Input).value.strip()
        except Exception:
            raw = ""
        if not raw:
            self._set_feedback(f"[#F59E0B]⚠ {self._t('hub.token_empty')}[/]")
            return
        from neonrp.core.hub_auth import save_hub_token
        save_hub_token(raw)
        self._token = raw
        self._refresh_auth_status()
        self._set_feedback("[#18FF82]✓ Token saved.[/]")

    def _do_upload(self) -> None:
        if not self._token:
            self._set_feedback(f"[#F59E0B]⚠ {self._t('hub.need_login')}[/]")
            return
        sel = self.query_one("#hub-upload-sel", SelectionList)
        if not sel.selected:
            self._set_feedback(self._t("hub.pick_one"))
            return
        idx = sel.selected[0]
        if idx >= len(self._items):
            return
        item = self._items[idx]
        path = item.get("path")
        if isinstance(path, str):
            path = Path(path)
        if not path or not Path(path).exists():
            self._set_feedback(f"[red]Path not found: {path}[/]")
            return
        # Validate first, then let the user confirm title / description /
        # cover on a form. Nothing leaves the machine before that.
        from neonrp.core.worldhub import UploadCheck, validate_for_upload

        if self._kind == "worlds" and item.get("is_source") is False:
            # A saved run is not a world: it goes up as a REPLAY (TODO #2) —
            # story / feed / backstage / cover only, into the 回放馆.
            from neonrp.core.replay_export import validate_replay_source

            rc = validate_replay_source(Path(path))
            check = UploadCheck(kind="replays", source=Path(path), errors=list(rc.errors), warnings=list(rc.warnings), cover=rc.cover)
            check.title = f"{rc.world_name} · {self._t('hub.replay_word')}"
            check.description = self._t("hub.replay_desc").replace("{world}", rc.world_name).replace("{turns}", str(rc.turns))
            check.title_i18n = {self._locale: check.title} if check.title else {}
            check.description_i18n = {self._locale: check.description} if check.description else {}
            self.app.push_screen(HubUploadFormScreen(check, locale=self._locale), self._on_form_done)
            return
        check = validate_for_upload(Path(path), kind=self._kind)
        self.app.push_screen(HubUploadFormScreen(check, locale=self._locale), self._on_form_done)

    def _on_form_done(self, form: dict[str, Any] | None) -> None:
        if not form:
            return
        self._set_feedback(self._t("hub.uploading"))
        try:
            from neonrp.core.worldhub import replace_cover_via_api, update_meta_via_api, upload_via_api

            path = Path(str(form["source"]))
            if form.get("kind") == "replays":
                from neonrp.core.worldhub import upload_replay_via_api

                cover = form.get("cover")
                entry = upload_replay_via_api(
                    path, name=form.get("title") or None, lang=self._locale,
                    cover=Path(str(cover)) if cover else None, api_token=self._token,
                )
                self._set_feedback(f"[#18FF82]✓ {self._t('hub.upload_ok')}: {entry.get('slug') or '?'}  ({entry.get('turns')} T)[/]")
                return
            # The four-language title/description stay with the source
            # (hub.json) so the next upload starts from them.
            title_i18n = dict(form.get("title_i18n") or {})
            desc_i18n = dict(form.get("description_i18n") or {})
            if title_i18n or desc_i18n:
                try:
                    from neonrp.core.hub_publish import save_hub_meta

                    save_hub_meta(path, self._kind, title=title_i18n, description=desc_i18n)
                except Exception:  # noqa: BLE001 — metadata still travels in the request
                    pass
            # Force unlisted: an upload must NEVER go straight to the public
            # listing. It lands as a private/unlisted draft; the author makes
            # it public later from the Hub.
            result = upload_via_api(path, kind=self._kind, name=form["title"], api_token=self._token, unlisted=True)
            slug = str(result.get("slug") or "")
            notes: list[str] = []
            if slug and (form.get("description") or title_i18n or desc_i18n):
                try:
                    update_meta_via_api(
                        self._kind, slug, api_token=self._token, description=form.get("description") or None,
                        name_i18n=title_i18n or None, description_i18n=desc_i18n or None,
                    )
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"{self._t('hub.form_meta_failed')}: {exc}")
            cover = form.get("cover")
            if slug and cover and form.get("cover_changed"):
                try:
                    replace_cover_via_api(self._kind, slug, Path(str(cover)), api_token=self._token)
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"{self._t('hub.form_cover_failed')}: {exc}")
            msg = f"[#18FF82]✓ {self._t('hub.upload_ok')}: {slug or '?'}[/]"
            if notes:
                msg += "\n[#F59E0B]" + "\n".join(notes) + "[/]"
            self._set_feedback(msg)
        except Exception as exc:
            self._set_feedback(f"[red]Upload failed: {exc}[/]")

    def action_cancel(self) -> None:
        self.dismiss(None)


class HubUploadFormScreen(ModalScreen[dict[str, Any] | None]):
    """Title · description (zh/en/ja/ko) · cover, with the validation verdict on top.

    「得有一个编辑图片、title 和 description 的方法 ——
    agent 去做,还是上传时有个 form?」— a form. Metadata is deterministic
    and the user must see exactly what goes public; the *content* (a
    cover, a good description) is the agent's job in build mode, and the
    form's error lines say so when they are missing.

    (publish gate): before anything can go PUBLIC the form
    shows what still blocks it — a config with a key inside, a character
    without a portrait, a language without a title — and offers to fill
    the missing languages with the configured model. Uploads always land
    as a draft; the public step is the Hub's review.

    Returns ``{"source", "title", "description", "title_i18n",
    "description_i18n", "cover", "cover_changed"}`` or ``None``.
    """

    CSS = """
    HubUploadFormScreen { align: center middle; background: #09090B; }
    #hub-form {
        width: 90%; max-width: 120; max-height: 96%;
        background: #09090B;
        border-top: double #00B960; border-bottom: double #00B960;
        border-left: solid #00B960; border-right: solid #00B960;
        padding: 1 2; layout: vertical;
    }
    #hub-form-body { height: 1fr; }
    #hub-form-title { height: auto; color: #E4E4E7; text-style: bold; margin-bottom: 1; }
    #hub-form-checks { height: auto; margin-bottom: 1; }
    #hub-form-public { height: auto; margin-bottom: 1; }
    .hub-form-label { height: 1; color: #A1A1AA; margin-top: 1; }
    .hub-form-lang { height: 1; color: #71717A; }
    .hub-form-row { height: auto; }
    .hub-form-row Input { width: 1fr; }
    #hub-form-actions { height: auto; align: center middle; margin-top: 1; }
    #hub-form-actions Button { margin: 0 1; }
    #hub-form-note { height: auto; color: #71717A; margin-top: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Back")]
    LANGS = ("zh", "en", "ja", "ko")

    def __init__(self, check: Any, *, locale: str = "en", preset_id: str | None = None) -> None:
        super().__init__()
        self._check = check
        self._locale = locale
        self._preset_id = preset_id
        self._translating = False

    def _t(self, key: str) -> str:
        try:
            return get_message(self._locale, key)
        except Exception:
            return key

    def _check_lines(self) -> str:
        c = self._check
        lines: list[str] = []
        for key in c.errors:
            text = self._t(key)
            if key == "check.secret_found":
                files = sorted({str(h.get("path")) for h in (getattr(c, "secrets", None) or []) if isinstance(h, dict)})
                text = text.replace("{files}", "、".join(files[:6]) + (" …" if len(files) > 6 else ""))
            lines.append(f"[#EF4444]✗ {text}[/]")
        for key in c.warnings:
            text = self._t(key)
            if key == "check.souls_no_portrait":
                text = text.replace("{names}", "、".join(getattr(c, "souls_without_portrait", []) or []))
            lines.append(f"[#F59E0B]⚠ {text}[/]")
        if not lines:
            lines.append("[#18FF82]✓ OK[/]")
        return f"[bold]{self._t('hub.form_checks')}[/]\n" + "\n".join(lines)

    def _public_lines(self) -> str:
        """The publish gate: what a PUBLIC listing still needs (live, from the inputs)."""
        c = self._check
        items: list[str] = []
        if c.cover is None and not self._value("#hub-form-cover"):
            items.append(self._t("check.no_cover"))
        names = getattr(c, "souls_without_portrait", None) or []
        if names:
            items.append(self._t("check.souls_no_portrait").replace("{names}", "、".join(names)))
        missing = [lang for lang in self.LANGS if not self._value(f"#hub-form-name-{lang}") or not self._value(f"#hub-form-desc-{lang}")]
        if missing and getattr(c, "kind", None) != "replays":
            items.append(self._t("check.i18n_missing").replace("{langs}", " / ".join(missing)))
        if getattr(c, "secrets", None):
            items.append(self._t("check.secret_found").replace("{files}", str(len(c.secrets))))
        if not items:
            return f"[#18FF82]✓ {self._t('hub.form_public_ok')}[/]"
        return f"[bold #F59E0B]{self._t('hub.form_public_title')}[/]\n" + "\n".join(f"[#F59E0B]· {i}[/]" for i in items)

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical, VerticalScroll

        c = self._check
        title_i18n = dict(getattr(c, "title_i18n", None) or {})
        desc_i18n = dict(getattr(c, "description_i18n", None) or {})
        with Vertical(id="hub-form"):
            yield Static(f"[bold #5BE0B0]◆[/] [bold]{self._t('hub.form_title')}[/]  [dim]{c.source.name}[/]", id="hub-form-title")
            with VerticalScroll(id="hub-form-body"):
                yield Static(self._check_lines(), id="hub-form-checks")
                yield Static("", id="hub-form-public")
                yield Static(self._t("hub.form_name"), classes="hub-form-label", markup=False)
                for lang in self.LANGS:
                    with Horizontal(classes="hub-form-row"):
                        yield Static(f" {lang} ", classes="hub-form-lang", markup=False)
                        yield Input(value=title_i18n.get(lang, ""), id=f"hub-form-name-{lang}")
                yield Static(self._t("hub.form_desc"), classes="hub-form-label", markup=False)
                for lang in self.LANGS:
                    with Horizontal(classes="hub-form-row"):
                        yield Static(f" {lang} ", classes="hub-form-lang", markup=False)
                        yield Input(value=desc_i18n.get(lang, ""), id=f"hub-form-desc-{lang}")
                yield Static(self._t("hub.form_cover"), classes="hub-form-label", markup=False)
                yield Input(value=str(c.cover) if c.cover else "", id="hub-form-cover")
            with Horizontal(id="hub-form-actions"):
                yield Button(self._t("hub.form_translate"), id="hub-form-translate")
                yield Button(self._t("hub.form_upload"), id="hub-form-upload", variant="primary", disabled=not c.ok)
                yield Button(self._t("cast.back"), id="hub-form-back")
            yield Static("" if c.ok else self._t("hub.form_fix"), id="hub-form-note", markup=False)

    def on_mount(self) -> None:
        self._refresh_public()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_public()

    def _refresh_public(self) -> None:
        try:
            self.query_one("#hub-form-public", Static).update(self._public_lines())
        except Exception:
            pass

    def _value(self, wid: str) -> str:
        try:
            return self.query_one(wid, Input).value.strip()
        except Exception:
            return ""

    def _set(self, wid: str, value: str) -> None:
        try:
            self.query_one(wid, Input).value = value
        except Exception:
            pass

    def _note(self, text: str) -> None:
        try:
            self.query_one("#hub-form-note", Static).update(text)
        except Exception:
            pass

    def _i18n_values(self) -> tuple[dict[str, str], dict[str, str]]:
        titles = {lang: self._value(f"#hub-form-name-{lang}") for lang in self.LANGS}
        descs = {lang: self._value(f"#hub-form-desc-{lang}") for lang in self.LANGS}
        return {k: v for k, v in titles.items() if v}, {k: v for k, v in descs.items() if v}

    def result(self) -> dict[str, Any] | None:
        c = self._check
        titles, descs = self._i18n_values()
        title = titles.get(self._locale) or next(iter(titles.values()), "") or c.title
        description = descs.get(self._locale) or next(iter(descs.values()), "") or c.description
        cover_raw = self._value("#hub-form-cover")
        cover = Path(cover_raw) if cover_raw else None
        if cover is not None and not cover.is_file():
            self._note(f"{self._t('check.missing_dir')}: {cover}")
            return None
        return {
            "source": c.source,
            "kind": getattr(c, "kind", None),
            "title": title,
            "description": description,
            "title_i18n": titles,
            "description_i18n": descs,
            "cover": cover,
            "cover_changed": bool(cover) and cover != c.cover,
        }

    # ── auto-translate the missing languages ─────────────────────────
    def _translate(self) -> None:
        if self._translating:
            return
        from neonrp.core.hub_publish import HubMeta

        titles, descs = self._i18n_values()
        meta = HubMeta(title=titles, description=descs)
        if meta.complete:
            self._note(self._t("hub.form_public_ok"))
            return
        if not (titles or descs):
            self._note(self._t("hub.form_translate_failed"))
            return
        self._translating = True
        self._note(self._t("hub.form_translating"))

        def _work() -> HubMeta:
            from neonrp.core.hub_publish import adapter_for_preset, translate_missing

            return translate_missing(meta, llm=adapter_for_preset(self._preset_id))

        def _done(worker: Any) -> None:
            self._translating = False
            if worker.state.name != "SUCCESS":
                self._note(f"{self._t('hub.form_translate_failed')}: {worker.error}")
                return
            self._apply_translation(worker.result)

        try:
            worker = self.run_worker(_work, thread=True, exit_on_error=False)
            worker._hub_done = _done  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 — no event loop (tests): run inline
            try:
                self._apply_translation(_work())
            except Exception as inner:  # noqa: BLE001
                self._note(f"{self._t('hub.form_translate_failed')}: {inner or exc}")
            finally:
                self._translating = False

    def _apply_translation(self, meta: Any) -> None:
        for lang in self.LANGS:
            if not self._value(f"#hub-form-name-{lang}") and meta.title.get(lang):
                self._set(f"#hub-form-name-{lang}", meta.title[lang])
            if not self._value(f"#hub-form-desc-{lang}") and meta.description.get(lang):
                self._set(f"#hub-form-desc-{lang}", meta.description[lang])
        self._refresh_public()
        self._note("")

    def on_worker_state_changed(self, event: Any) -> None:
        done = getattr(event.worker, "_hub_done", None)
        if done is None:
            return
        if event.worker.state.name in ("SUCCESS", "ERROR", "CANCELLED"):
            done(event.worker)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "hub-form-upload":
            if not self._check.ok:
                return
            res = self.result()
            if res is not None:
                self.dismiss(res)
        elif bid == "hub-form-translate":
            self._translate()
        elif bid == "hub-form-back":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ImportScreen(ModalScreen[str | None]):
    """Import a world or character card — file selector or paste.

    Returns a file path (string) or pasted JSON content (string), or
    ``None`` if cancelled.
    """

    CSS = """
    ImportScreen { align: center middle; background: #09090B; }
    #import-modal {
        width: 70%; max-width: 90; background: #09090B;
        border-top: double #00B960; border-bottom: double #00B960;
        border-left: solid #00B960; border-right: solid #00B960;
        padding: 1 2; layout: vertical;
    }
    #import-title { height: auto; color: #E4E4E7; text-style: bold; margin-bottom: 1; }
    #import-paste { height: 12; margin: 1 0; background: #09090B; border: solid #27272A; }
    #import-actions { height: auto; align: center middle; margin-top: 1; }
    #import-actions Button { margin: 0 1; }
    #import-feedback { height: auto; margin-top: 1; color: #71717A; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(self, *, locale: str = "en", title_key: str = "import.title") -> None:
        super().__init__()
        self._locale = locale

    def _t(self, key: str) -> str:
        try:
            return get_message(self._locale, key)
        except Exception:
            return key

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical
        with Vertical(id="import-modal"):
            yield Static(f"[bold #5BE0B0]◆[/] [bold]{self._t('import.title')}[/]", id="import-title")
            yield Static(self._t("import.hint"), id="import-feedback")
            yield TextArea("", id="import-paste", soft_wrap=True, show_line_numbers=False)
            with Horizontal(id="import-actions"):
                yield Button(self._t("import.select_file"), id="import-file-btn", variant="primary")
                yield Button(self._t("import.paste_import"), id="import-paste-btn")
                yield Button(self._t("cast.back"), id="import-back-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "import-file-btn":
            path = self._open_file_dialog()
            if path:
                self.dismiss(path)
        elif bid == "import-paste-btn":
            try:
                content = self.query_one("#import-paste", TextArea).text.strip()
            except Exception:
                content = ""
            if content:
                self.dismiss(content)
        elif bid == "import-back-btn":
            self.dismiss(None)

    @staticmethod
    def _open_file_dialog() -> str | None:
        """Open a native file picker. Returns the selected path or None."""
        import platform
        import subprocess
        system = platform.system()
        try:
            if system == "Darwin":
                proc = subprocess.run(
                    ["osascript", "-e",
                     'POSIX path of (choose file of type {"png","json","zip"} '
                     'with prompt "Select a world or character card")'],
                    capture_output=True, text=True, timeout=120,
                )
                return proc.stdout.strip() or None
            elif system == "Linux":
                # Try zenity first, then kdialog
                for cmd in (
                    ["zenity", "--file-selection", "--file-filter=*.png *.json *.zip"],
                    ["kdialog", "--getopenfilename", ".", "*.png *.json *.zip"],
                ):
                    try:
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        out = proc.stdout.strip()
                        if out:
                            return out
                    except Exception:
                        continue
                return None
            else:
                return None
        except Exception:
            return None

    def action_cancel(self) -> None:
        self.dismiss(None)


class PostImportChoiceScreen(ModalScreen[str]):
    """Shown after a character card imports into the library: open Soul Talk
    with it now, or go back to the library. Returns ``"play"`` / ``"library"``."""

    CSS = """
    PostImportChoiceScreen { align: center middle; background: #09090B; }
    #pic-modal {
        width: 70%; max-width: 90; background: #09090B;
        border-top: double #00B960; border-bottom: double #00B960;
        border-left: solid #00B960; border-right: solid #00B960;
        padding: 1 2; layout: vertical;
    }
    #pic-title { height: auto; color: #E4E4E7; text-style: bold; margin-bottom: 1; }
    #pic-msg { height: auto; margin-bottom: 1; color: #71717A; }
    #pic-actions { height: auto; align: center middle; margin-top: 1; }
    #pic-actions Button { margin: 0 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(self, *, locale: str = "en", soul_name: str = "") -> None:
        super().__init__()
        self._locale = locale
        self._soul_name = soul_name

    def _t(self, key: str) -> str:
        try:
            return get_message(self._locale, key)
        except Exception:
            return key

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical
        with Vertical(id="pic-modal"):
            yield Static(
                f"[bold #5BE0B0]◆[/] [bold]{self._t('import.done_title')}[/]",
                id="pic-title",
            )
            yield Static(
                self._t("import.done_msg").replace("{name}", self._soul_name),
                id="pic-msg",
            )
            with Horizontal(id="pic-actions"):
                yield Button(self._t("import.done_play"), id="pic-play-btn", variant="primary")
                yield Button(self._t("import.done_library"), id="pic-library-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "pic-play-btn":
            self.dismiss("play")
        elif bid == "pic-library-btn":
            self.dismiss("library")

    def action_cancel(self) -> None:
        self.dismiss("library")


class WorldLinesLauncherApp(App[None]):
    """Guided startup flow for the public `worldlines` entry command."""

    BINDINGS = [
        Binding("up", "move_prev", "Prev"),
        Binding("down", "move_next", "Next"),
        Binding("left", "move_prev", "Prev"),
        Binding("right", "move_next", "Next"),
        Binding("tab", "move_next", "Next"),
        Binding("shift+tab", "move_prev", "Prev"),
        Binding("enter", "confirm_choice", "Confirm"),
        Binding("r", "quick_resume", "Resume"),
        Binding("c", "continue_flow", "Continue"),
        Binding("n", "new_flow", "New"),
        Binding("s", "settings_flow", "Settings"),
        Binding("escape", "quit_launcher", "Quit"),
    ]

    CSS = """
    WorldLinesLauncherApp {
        background: #09090B;
        color: #E4E4E7;
    }

    #worldlines-launcher {
        align: center middle;
        width: 100%;
        height: 100%;
        layout: vertical;
    }

    /* Scroll wrapper: when the terminal is shorter than the menu content,
       the user scrolls instead of losing buttons. Centers the panel while
       there is spare room; falls back to top-anchored scrolling when not. */
    #worldlines-shell {
        align: center middle;
        width: 100%;
        height: 100%;
        layout: vertical;
        background: #09090B;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
    }

    #worldlines-panel {
        width: 100%;
        max-width: 110;
        height: auto;
        background: #09090B;
        padding: 1 2;
        layout: vertical;
    }

    #worldlines-header {
        width: 100%;
        height: 2;
        padding-left: 15;
        margin: 0 0 1 0;
    }

    /* Opening visual (left) + single-screen dashboard (right), side by
       side. The intro animation stays as the brand opener; the dashboard
       is 2x2 quadrants + a bottom strip — every action one click, no
       nested menus. */
    #wl-dash {
        width: 100%;
        height: auto;
        layout: vertical;
    }

    /* Animation sits BELOW the options, centered, as a footer banner.
       Fluid height so it yields room to the menu on short terminals; the
       graph itself is capped but allowed to shrink with the row. */
    #worldlines-anim-row {
        width: 100%;
        height: auto;
        max-height: 18;
        align: center middle;
        margin: 1 0 0 0;
    }

    #worldlines-graph {
        width: 100%;
        max-width: 58;
        height: auto;
        max-height: 18;
    }

    .wl-row {
        width: 100%;
        height: auto;
        layout: horizontal;
    }

    .wl-quad {
        width: 1fr;
        height: auto;
        border: round #14361f;
        padding: 0 2 1 2;
        margin: 0 1 1 0;
    }

    .wl-quad-title {
        width: 100%;
        height: 1;
        color: #18FF82;
        text-style: bold;
        margin: 0 0 1 0;
    }

    .wl-strip {
        width: 100%;
        height: auto;
        layout: horizontal;
        margin: 0 1 0 0;
    }

    /* Strip buttons share the row evenly so neither is pushed off the
       right edge on narrow terminals (a 100% width each would overflow). */
    .wl-strip > .worldlines-menu-button {
        width: 1fr;
        margin: 0 1 0 0;
    }

    #worldlines-menu {
        width: 100%;
        height: auto;
        layout: vertical;
    }

    .worldlines-menu-button {
        width: 100%;
        min-width: 0;
        height: 1;
        margin: 0;
        background: #09090B;
        color: #00B960;
        border: none;
        padding: 0;
        text-align: left;
        content-align: left middle;
    }

    .worldlines-menu-button:focus {
        background: #09090B;
        color: #18FF82;
        text-style: bold;
    }

    #worldlines-hint {
        width: 100%;
        height: 1;
        color: #005F3A;
        content-align: center middle;
        text-align: center;
        margin: 1 0 0 0;
    }
    """

    def __init__(self):
        super().__init__()
        self.launch_selection: WorldLinesLaunchSelection | None = None
        from neonrp.players import list_players
        from neonrp.presets import list_presets
        from neonrp.worlds import list_saved_games, list_worlds
        from neonrp.core.user_config import get_user_locale

        self._saved_games: list[dict[str, Any]] = list_saved_games()
        self._worlds: list[dict[str, str]] = list_worlds(locale=resolve_locale())
        self._presets: list[dict[str, Any]] = list_presets()
        self._players: list[dict[str, Any]] = list_players()
        self._selected_game: Path | None = None
        self._selected_world_id: str | None = None
        self._selected_player: dict[str, Any] | None = None
        # Casting ②: soul dirs the player chose to bring INTO the world as
        # NPCs (cast via placement at launch). Empty = none brought in.
        self._bring_in_souls: list[str] = []
        # Casting ②: chosen play mode (fast / orchestrator / multi-agent),
        # applied to the world's runtime_contract at launch.
        self._engine_mode: str = "orchestrator"
        # Casting ②: per-soul placement overrides from in-preview editing.
        self._npc_placements: dict[str, dict[str, Any]] | None = None
        # Casting ②: per-soul location confirmations.
        self._npc_locations: dict[str, str] | None = None
        self._custom_world_intent: dict[str, Any] | None = None
        # Soul-side analogue of `_custom_world_intent`: set by the
        # soul-create flow, consumed downstream to hand the freshly
        # picked description/template off to the `soul-authoring` skill
        # (the skill itself is built elsewhere — we only carry intent).
        self._custom_soul_intent: dict[str, Any] | None = None
        # M16: legacy ~/.worldlines/players/ profiles surface as souls.
        # `migrate_players_to_souls` is idempotent (marker-guarded), so a
        # best-effort call on launcher init is safe and side-effect-free
        # once it has run once.
        try:
            from neonrp.core.souls import migrate_players_to_souls

            migrate_players_to_souls()
        except Exception:
            pass
        # When set, the new-game preset flow emits selection.mode =
        # "launch_existing" with this path instead of scaffolding a new
        # builtin world. Used for freshly-downloaded WorldHub games and
        # freshly-loaded .zip imports — the dir is on disk, never been
        # started, and we want the new-game startup handoff to fire.
        self._launch_existing_dir: Path | None = None
        # Dashboard direct flows (「选完 LLM 直接进 build /
        # play」): `_direct_surface` skips the「在哪里玩」picker after the
        # preset; `_pending_create` turns the preset step into「建一个空白
        # 世界 → 进它的工坊」.
        self._direct_surface: str | None = None
        self._pending_create: tuple[str, str] | None = None  # ("world"|"soul", name)
        # An existing character's folder to reopen in build (角色库 card + `b`).
        self._pending_workshop: tuple[Path, str] | None = None
        self._menu_focus_index = 0
        # Continue-picker fold state: wid keys currently expanded. By
        # default everything is collapsed — buckets with multiple runs
        # show only the latest, with an "expand" row to reveal the rest.
        self._continue_expanded: set[str] = set()
        # Track whether user has ever chosen a locale. If not, the launcher
        # shows a first-run language picker before the main menu.
        self._user_locale_on_disk: str = get_user_locale()
        self._first_run_locale: bool = self._user_locale_on_disk == "auto"
        self.locale: str = resolve_locale()

    def compose(self) -> ComposeResult:
        if self._saved_games:
            continue_label = f"{get_message(self.locale, 'menu.continue')} ({len(self._saved_games)})"
        else:
            continue_label = get_message(self.locale, "menu.continue_empty")
        continue_variant = "primary" if self._saved_games else "default"
        m = lambda k: get_message(self.locale, k)  # noqa: E731 — local shorthand
        n_worlds, n_souls = self._library_counts()
        with Container(id="worldlines-launcher"):
            with Container(id="worldlines-shell"):
                with Vertical(id="worldlines-panel"):
                    yield Static(self._header_markup(), id="worldlines-header", markup=True)
                    # Options on top, opening animation below (footer banner).
                    # Top row = PLAY (saved | new); bottom row = LIBRARIES
                    # (worlds | characters); strip = settings + exit. One
                    # screen, one click, no nesting.
                    #
                    # 08-31 曾砍成四行;09-10 要回了仪表盘。回来的
                    # 是**盘面**,不是创建管线:「新建世界 / 新建角色」两格仍
                    # 不在(裁决①,创建归 build 模式的 /init 与 agent)。
                    with Vertical(id="wl-dash"):
                        with Horizontal(classes="wl-row"):
                            with Vertical(classes="wl-quad"):
                                yield Static(m("menu.section_continue"), id="wl-title-continue", classes="wl-quad-title", markup=False)
                                # ⚡ one key into the newest save (no pickers).
                                yield Button(self._resume_label(), id="wl-resume", variant="success" if self._saved_games else "default", classes="worldlines-menu-button")
                                yield Button(continue_label, id="wl-continue", variant=continue_variant, classes="worldlines-menu-button")
                            with Vertical(classes="wl-quad"):
                                yield Static(m("menu.section_new"), id="wl-title-new", classes="wl-quad-title", markup=False)
                                yield Button(m("menu.new"), id="wl-new", variant="default", classes="worldlines-menu-button")
                        with Horizontal(classes="wl-row"):
                            # 世界库三件 —— 创作 / 上传 / 一览游玩;
                            # 角色库四件 —— 对话 / 创作 / 上传 / 一览游玩。导入 /
                            # 下载 / 管理仍在「新游戏」的列表里,不占首屏。
                            with Vertical(classes="wl-quad"):
                                yield Static(f'{m("menu.section_world_lib")} ({n_worlds})', id="wl-title-world", classes="wl-quad-title", markup=False)
                                yield Button(m("menu.world_create"), id="wl-world-create", variant="default", classes="worldlines-menu-button")
                                yield Button(m("menu.hub_upload_world"), id="wl-upload-world", variant="default", classes="worldlines-menu-button")
                                yield Button(m("menu.world_browse"), id="wl-world-browse", variant="primary", classes="worldlines-menu-button")
                            with Vertical(classes="wl-quad"):
                                yield Static(f'{m("menu.section_char_lib")} ({n_souls})', id="wl-title-char", classes="wl-quad-title", markup=False)
                                yield Button(m("menu.soul_talk"), id="wl-soul-talk", variant="default", classes="worldlines-menu-button")
                                yield Button(m("menu.soul_create"), id="wl-soul-create", variant="default", classes="worldlines-menu-button")
                                yield Button(m("menu.hub_upload_soul"), id="wl-upload-soul", variant="default", classes="worldlines-menu-button")
                                yield Button(m("menu.soul_browse"), id="wl-soul-browse", variant="primary", classes="worldlines-menu-button")
                        with Horizontal(classes="wl-strip"):
                            yield Button(m("menu.settings"), id="wl-settings", variant="default", classes="worldlines-menu-button")
                            yield Button(m("menu.exit"), id="wl-exit", variant="default", classes="worldlines-menu-button")
                    # Opening animation — footer banner below the options.
                    with Horizontal(id="worldlines-anim-row"):
                        yield Static("", id="worldlines-graph", markup=True)
                    yield Static(get_message(self.locale, "launcher.shortcuts"), id="worldlines-hint")

    def _header_markup(self) -> str:
        return (
            f"[#B6FFDA bold]Welcome to WorldLines[/]\n"
            f"[#005F3A]v{_NEONRP_VERSION}-alpha[/]"
        )

    def _resume_label(self) -> str:
        """The ⚡ tile: names the save it would open, or says there is none."""
        if self._saved_games:
            name = str(self._saved_games[0].get("display_name") or self._saved_games[0].get("dir_name") or "")
            return get_message(self.locale, "menu.resume").format(name=name)
        return get_message(self.locale, "menu.resume_none")

    def _quick_resume(self) -> None:
        """One key from the home screen into the newest save, in the terminal.

        「提供一个不用 launcher 点这么多的入口,变成第一个
        选项」。Skips the save picker, the model picker and the surface
        picker: newest save + the model that save last used (or the user's
        default) + TUI. Anything it cannot decide on its own falls back to
        the ordinary continue flow instead of guessing.
        """
        from neonrp.worlds import list_saved_games

        self._saved_games = list_saved_games()
        if not self._saved_games:
            self._start_new_flow()
            return
        game = self._saved_games[0]
        path = game.get("path")
        if path is None:
            from neonrp.worlds import PLAYS_HOME

            path = PLAYS_HOME / str(game.get("dir_name", ""))
        path = Path(path)

        preset_id: str | None = None
        try:
            from neonrp.cli import read_worldlines_last_preset

            preset_id = read_worldlines_last_preset(path)
        except Exception:
            preset_id = None
        if not preset_id:
            try:
                from neonrp.presets import default_model_ref

                preset_id = default_model_ref()
            except Exception:
                preset_id = None
        known = {p["id"] for p in (self._presets or [])}
        try:
            from neonrp.presets import preset_ready

            ready = bool(preset_id) and preset_ready(str(preset_id))
        except Exception:  # noqa: BLE001
            ready = True
        # 10-24: a remembered model that cannot run now (Worldlines after the session ended, a key removed) goes
        # through the chooser here instead of the launcher's 「Paste API key」 prompt
        if not preset_id or preset_id not in known or not ready:
            self._selected_game = path
            self._step_choose_preset(True)
            return

        self._pending_card_import = None
        self._selected_game = path
        self.launch_selection = WorldLinesLaunchSelection(
            mode="continue",
            preset_id=preset_id,
            runtime_mode="play",
            game_path=path,
            render_surface="tui",
        )
        self.exit()

    def action_quick_resume(self) -> None:
        self._quick_resume()

    # ── dashboard direct flows ──────────────────────
    #
    # 「选完 LLM 直接进 build 或 play」。四条路都在 preset 之后收口到
    # `finalize_launch`:创作 → 建空白世界 → build;一览 → play(终端),不再
    # 问「在哪里玩」,也不再过分身/带谁进来两屏。

    def _reset_direct_state(self) -> None:
        self._selected_game = None
        self._selected_world_id = None
        self._selected_player = None
        self._bring_in_souls = []
        self._custom_world_intent = None
        self._custom_soul_intent = None
        self._launch_existing_dir = None
        self._direct_surface = None
        self._pending_create = None
        self._pending_workshop = None

    _BLANK_WORLD_NAME = "新世界"

    def _start_world_create_flow(self) -> None:
        """创作世界 = 建一个空壳,进去。不问名字(「其实就是建立
        一个空壳,然后进入」):壳叫「新世界」(重名自动 -2、-3),名字之后在
        工坊里跟 agent 一起定。模型还是要选一下 —— 空壳也得有个能说话的模型。"""
        self._reset_direct_state()
        self._pending_create = ("world", self._BLANK_WORLD_NAME)
        self._step_choose_preset(False)

    def _start_soul_create_flow(self) -> None:
        self._reset_direct_state()

        def got_name(name: str | None) -> None:
            name = (name or "").strip()
            if not name:
                return
            self._pending_create = ("soul", name)
            self._step_choose_preset(False)

        self.push_screen(
            TextInputScreen(
                get_message(self.locale, "create.soul_name"),
                hint=get_message(self.locale, "create.soul_name_hint"),
            ),
            got_name,
        )

    @staticmethod
    def _create_brief(kind: str, name: str) -> str:
        """The agent's first words in the fresh workshop (never a slash command)."""
        if kind == "soul":
            return (
                f"这是角色「{name}」自己的文件夹。先问我两三个关键设定(是谁、想要什么、怕什么),"
                "然后按 soul-authoring 的结构把 soul.json、persona、背景写出来,并给一张立绘。"
            )
        return f"这个世界叫「{name}」。先看一遍现有结构,然后和我一起把它写出来。"

    def _materialize_pending_create(self, preset_id: str) -> Path:
        """What a 创作 flow builds in: a blank world, or — for a character —
        its own folder in the library (「应该是新建一个
        souls/<npc name> 的文档,然后在里面进行操作」, not a throw-away world)."""
        kind, name = self._pending_create or ("world", "world")
        if kind == "soul":
            from neonrp.core.souls import create_soul_workshop

            return create_soul_workshop(name, model_ref=preset_id)
        from neonrp.worlds import create_blank_world

        return create_blank_world(name, model_ref=preset_id)

    def _world_source_dir(self, world_id: str) -> Path | None:
        """Where a world's pictures live: the owned source, or the packaged
        template for a built-in."""
        try:
            from neonrp.worlds import get_world, resolve_template

            info = get_world(world_id)
            if info.get("owned") and info.get("source_dir"):
                return Path(str(info["source_dir"]))
            import neonrp.templates as _templates

            return Path(_templates.__file__).parent / resolve_template(world_id, self.locale)
        except Exception:
            return None

    def _world_card_items(self) -> list:
        from neonrp.core.image_render import discover_world_images
        from neonrp.tui.card_grid import CardItem

        items = []
        for w in self._worlds:
            src = self._world_source_dir(str(w["id"]))
            image = None
            if src is not None:
                try:
                    pics = discover_world_images(src)
                    image = pics[0] if pics else None
                except Exception:
                    image = None
            items.append(CardItem(key=str(w["id"]), title=str(w.get("display_name") or w["id"]), caption=str(w.get("desc") or ""), image=image))
        return items

    def _soul_card_items(self) -> list:
        from neonrp.core.image_render import discover_world_images
        from neonrp.core.souls import list_souls
        from neonrp.tui.card_grid import CardItem

        items = []
        try:
            souls = list_souls(locale=self.locale)
        except Exception:
            souls = []
        for sd in souls:
            image = None
            path = sd.get("path")
            if path is not None:
                try:
                    pics = discover_world_images(Path(path))
                    image = pics[0] if pics else None
                except Exception:
                    image = None
            items.append(CardItem(key=str(sd["sid"]), title=str(sd.get("display_name") or sd["sid"]), caption=f"v{sd.get('version', '')}", image=image))
        return items

    def _start_world_browse_flow(self) -> None:
        from neonrp.tui.card_grid import CardGridScreen

        self._reset_direct_state()
        try:
            from neonrp.worlds import list_worlds

            self._worlds = list_worlds(locale=self.locale)
        except Exception:
            pass

        def picked(world_id: str | None) -> None:
            if not world_id:
                self._focus_menu_button(self._menu_button_ids().index("wl-world-browse"))
                return
            self._selected_world_id = world_id
            self._direct_surface = "tui"
            self._step_choose_preset(False)

        self.push_screen(
            CardGridScreen(
                get_message(self.locale, "cards.worlds_title"),
                self._world_card_items(),
                hint=get_message(self.locale, "cards.hint"),
            ),
            picked,
        )

    def _start_soul_browse_flow(self) -> None:
        from neonrp.tui.card_grid import CardGridScreen

        self._reset_direct_state()

        def picked(sid: str | None) -> None:
            if not sid:
                self._focus_menu_button(self._menu_button_ids().index("wl-soul-browse"))
                return
            if sid.startswith("build::"):
                # `b` on the card: back into this character's own folder
                # (TODO #9 角色工坊的回门) — model, then build.
                sid = sid.split("::", 1)[1]
                try:
                    from neonrp.core.placement import resolve_soul_dir

                    soul_dir = resolve_soul_dir(sid)
                except Exception as exc:  # noqa: BLE001
                    self.notify(f"{sid}: {exc}", severity="error")
                    return
                self._pending_workshop = (Path(soul_dir), sid)
                self._step_choose_preset(False)
                return
            # Talk to this one: the Soul Talk world with the soul brought in.
            self._selected_world_id = "soul-talk"
            self._bring_in_souls = [sid]
            self._direct_surface = "tui"
            self._step_choose_preset(False)

        self.push_screen(
            CardGridScreen(
                get_message(self.locale, "cards.souls_title"),
                self._soul_card_items(),
                hint=get_message(self.locale, "cards.souls_hint"),
            ),
            picked,
        )

    def _library_counts(self) -> tuple[int, int]:
        """(worlds, souls) for the two library quadrant titles."""
        n_worlds = len(getattr(self, "_worlds", None) or [])
        try:
            from neonrp.core.souls import list_souls

            n_souls = len(list_souls())
        except Exception:
            n_souls = 0
        return n_worlds, n_souls

    def on_mount(self) -> None:
        # Default focus: ⚡ resume when there is a save (Enter = in the game),
        # otherwise「新游戏」.
        try:
            ids = self._menu_button_ids()
            self._focus_menu_button(ids.index("wl-resume") if self._saved_games else ids.index("wl-new"))
        except Exception:
            pass
        # First run — prompt for UI language before anything else.
        if self._first_run_locale:
            self.call_after_refresh(self._prompt_first_run_locale)
        # Kick off the intro animation. If the intro module fails to
        # import, the right-side pane just stays blank.
        self._start_intro_animation()

    def _start_intro_animation(self) -> None:
        try:
            from neonrp.tui.intro_animation import (
                PLAYBACK_FPS,
                WorldLinesAnimation,
            )
        except Exception:
            return
        try:
            graph = self.query_one("#worldlines-graph", Static)
        except Exception:
            return

        self._intro_anim = WorldLinesAnimation()
        # Seed the first frame so the right pane isn't blank for one tick.
        graph.update(self._intro_anim.tick())

        def _tick() -> None:
            anim = getattr(self, "_intro_anim", None)
            if anim is None:
                return
            try:
                graph.update(anim.tick())
            except Exception:
                # Widget removed mid-tick (e.g. screen swapped); stop.
                self._intro_anim = None

        interval = 1.0 / max(1, PLAYBACK_FPS)
        self.set_interval(interval, _tick)

    def _prompt_first_run_locale(self) -> None:
        from neonrp.core.user_config import set_user_locale

        options = [
            ("English",    "en"),
            ("简体中文",   "zh"),
            ("日本語",     "ja"),
            ("한국어",     "ko"),
            ("Auto (system default)", "auto"),
        ]

        def on_selected(value: str | None) -> None:
            self._first_run_locale = False
            if value:
                set_user_locale(value)
                self._user_locale_on_disk = value
                self.locale = resolve_locale()
                self.ui_locale = self.locale  # keep SettingsFlow in sync
                self._relabel_launcher()

        self.push_screen(
            ChoicePickerScreen(
                "Language / 语言 / 言語 / 언어",
                options,
                hint="Enter to confirm · Esc to keep default",
            ),
            on_selected,
        )

    def _relabel_launcher(self) -> None:
        """Re-render every launcher label after a locale change.

        Covers the header, hint, the four section titles, AND every menu
        button. Missing any of these leaves it frozen in the locale
        resolved at construction (system env), so on a JP system the
        section titles + import/upload buttons used to stay Japanese even
        after the user picked another language.

        Also re-reads the saved-game / world caches from disk so the live
        counts ("继续 (N)", world-lib count) reflect deletes or additions
        made in a sub-flow — the construction-time snapshot is otherwise
        never refreshed once we pop back to the home menu.
        """
        try:
            from neonrp.worlds import list_saved_games, list_worlds
            self._saved_games = list_saved_games()
            self._worlds = list_worlds(locale=resolve_locale())
        except Exception:
            pass
        m = lambda k: get_message(self.locale, k)  # noqa: E731

        def _set(widget_id: str, kind: type, value: str) -> None:
            try:
                w = self.query_one(widget_id, kind)
            except Exception:
                return
            if kind is Button:
                w.label = value
            else:
                w.update(value)

        # Header + hint.
        _set("#worldlines-header", Static, self._header_markup())
        _set("#worldlines-hint", Static, m("launcher.shortcuts"))

        # Section titles (the world/char libs carry a live count).
        n_worlds, n_souls = self._library_counts()
        _set("#wl-title-continue", Static, m("menu.section_continue"))
        _set("#wl-title-new", Static, m("menu.section_new"))
        _set("#wl-title-world", Static, f'{m("menu.section_world_lib")} ({n_worlds})')
        _set("#wl-title-char", Static, f'{m("menu.section_char_lib")} ({n_souls})')

        # ⚡ tile names the newest save; continue button carries the count.
        _set("#wl-resume", Button, self._resume_label())
        if self._saved_games:
            _set("#wl-continue", Button, f"{m('menu.continue')} ({len(self._saved_games)})")
        else:
            _set("#wl-continue", Button, m("menu.continue_empty"))

        # Every other button → its message key.
        for btn_id, key in (
            ("#wl-new", "menu.new"),
            ("#wl-world-create", "menu.world_create"),
            ("#wl-upload-world", "menu.hub_upload_world"),
            ("#wl-world-browse", "menu.world_browse"),
            ("#wl-soul-talk", "menu.soul_talk"),
            ("#wl-soul-create", "menu.soul_create"),
            ("#wl-upload-soul", "menu.hub_upload_soul"),
            ("#wl-soul-browse", "menu.soul_browse"),
            ("#wl-settings", "menu.settings"),
            ("#wl-exit", "menu.exit"),
        ):
            _set(btn_id, Button, m(key))

    def pop_screen(self):  # type: ignore[override]
        """Refresh the home menu whenever we pop back to it.

        Sub-flows (delete a save, create/import a world, download from the
        Hub) change what's on disk, but the home menu was composed once at
        startup with construction-time counts. `ScreenResume` does not
        bubble to the App, so we hook the pop itself — which `dismiss()`
        also routes through — and relabel once only the base/home screen
        remains. Otherwise a user who deletes every save still sees the old
        "继续 (39)", and a freshly created world isn't counted (WOR-46-home).
        """
        result = super().pop_screen()
        try:
            if len(self.screen_stack) <= 1:
                self._relabel_launcher()
        except Exception:
            pass
        return result

    @staticmethod
    def _menu_button_ids() -> list[str]:
        # Order must mirror `compose()`'s yield order so keyboard
        # navigation index ↔ on-screen button stays aligned. Dashboard
        # order: PLAY row (continue | new), LIBRARY row (world: new +
        # download | char: soul-talk + new + download), then the
        # settings/exit strip.
        return [
            "wl-resume",
            "wl-continue",
            "wl-new",
            "wl-world-create",
            "wl-upload-world",
            "wl-world-browse",
            "wl-soul-talk",
            "wl-soul-create",
            "wl-upload-soul",
            "wl-soul-browse",
            "wl-settings",
            "wl-exit",
        ]

    def _menu_actions(self) -> dict[str, Any]:
        """Button id → what it does. One table for click and Enter, and the
        same methods the「选世界」list calls — a tile is a shortcut, never a
        second implementation."""
        return {
            "wl-resume": self._quick_resume,
            "wl-continue": self._start_continue_flow,
            "wl-new": self._start_new_flow,
            "wl-world-create": self._start_world_create_flow,
            "wl-upload-world": lambda: self._start_hub_upload_flow("worlds"),
            "wl-world-browse": self._start_world_browse_flow,
            "wl-soul-talk": self._start_soul_talk_flow,
            "wl-soul-create": self._start_soul_create_flow,
            "wl-upload-soul": lambda: self._start_hub_upload_flow("souls"),
            "wl-soul-browse": self._start_soul_browse_flow,
            "wl-settings": self._start_settings_flow,
            "wl-exit": self.exit,
        }

    def _run_menu_action(self, btn_id: str) -> None:
        action = self._menu_actions().get(btn_id)
        if action is None:
            # Not a home tile. Button.Pressed from a modal (the model picker's
            # rows, a form's buttons…) bubbles up here too, and resetting
            # state on it wiped `_pending_create` between「选模型」and
            # finalize — the real cause of「Nothing to launch」/「还没选世界」
            # when the model was picked with the MOUSE.
            return
        # Picking any home action clears a stale character-card import pending
        # from an abandoned earlier import — otherwise finalize_launch's card
        # branch would hijack the next flow into a card-authoring spinner that
        # just spins. The import button's own flow re-sets it after the file
        # is chosen.
        self._pending_card_import = None
        # Direct-flow state never leaks from one tile into the next.
        self._direct_surface = None
        self._pending_create = None
        self._pending_workshop = None
        action()

    def _focus_menu_button(self, index: int) -> None:
        menu_ids = self._menu_button_ids()
        if not menu_ids:
            return
        self._menu_focus_index = index % len(menu_ids)
        try:
            self.query_one(f"#{menu_ids[self._menu_focus_index]}", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._run_menu_action(event.button.id or "")

    def action_continue_flow(self) -> None:
        self._start_continue_flow()

    def action_new_flow(self) -> None:
        self._start_new_flow()

    def action_settings_flow(self) -> None:
        self._start_settings_flow()

    def action_move_prev(self) -> None:
        self._focus_menu_button(self._menu_focus_index - 1)

    def action_move_next(self) -> None:
        self._focus_menu_button(self._menu_focus_index + 1)

    def action_confirm_choice(self) -> None:
        menu_ids = self._menu_button_ids()
        if not menu_ids:
            return
        self._run_menu_action(menu_ids[self._menu_focus_index % len(menu_ids)])

    def action_quit_launcher(self) -> None:
        self.exit()

    def _start_continue_flow(self) -> None:
        # Refresh before the routing check — a game created/imported this
        # session won't be in the construction-time cache, so a stale empty
        # list would wrongly bounce the user to the new-world picker.
        from neonrp.worlds import list_saved_games

        self._saved_games = list_saved_games()
        if not self._saved_games:
            self._step_choose_world()
            return
        self._step_choose_saved_game()

    def _start_new_flow(self) -> None:
        self._step_choose_world()

    def _start_soul_talk_flow(self) -> None:
        """Soul Talk: pick a character → launch a minimal world where the
        player can just talk to that character. No quests, no combat."""
        self._selected_world_id = "soul-talk"
        self._step_choose_player()

    def _start_hub_upload_flow(self, kind: str) -> None:
        """Open the Hub upload screen for worlds or souls.

        ``kind`` is ``"worlds"`` or ``"souls"``."""
        self.push_screen(
            HubUploadScreen(kind=kind, locale=self.locale),
            callback=lambda _: None,
        )

    def _start_settings_flow(self) -> None:
        self._step_settings_menu()

    def _refresh_presets(self) -> None:
        from neonrp.presets import list_presets

        self._presets = list_presets()

    def _step_settings_menu(self) -> None:
        """Open the unified settings flow (shared with NeonRPApp /settings)."""
        from neonrp.tui.settings_flow import SettingsFlow

        flow = SettingsFlow(
            host=self,
            on_exit=lambda: (self._refresh_presets(), self.call_later(self._return_to_main)),
        )
        # Locale attribute used by SettingsFlow is read as `ui_locale` (it
        # wins over `self.locale`); the launcher stores the live choice under
        # `self.locale`. Sync it EVERY time — a `hasattr` guard would pin the
        # construction-time locale and leave Settings in the old language
        # after a mid-session switch.
        self.ui_locale = self.locale
        flow.open_root()

    def _step_configure_discord(self) -> None:
        """Discord setup — guided wizard with status dashboard.

        Two states:
        - If nothing is configured yet → show welcome + 4 progressive steps
        - Once any field exists → show dashboard with ✓/○ per field + actions
        """
        from neonrp.core.discord_config import (
            get_discord_settings,
            set_discord_settings,
            clear_discord_settings,
            get_discord_inline_status,
            discord_oauth_invite_url,
            VALID_RELAY_MODES,
        )
        from neonrp.bridges.discord_bridge import discord_py_status

        t = lambda k: get_message(self.locale, k)  # noqa: E731

        settings = get_discord_settings()
        token = settings.get("bot_token", "")
        app_id = settings.get("application_id", "")
        channel = settings.get("channel_id", "")
        guild = settings.get("guild_id", "")
        relay = settings.get("relay_mode", "mirror")
        status = get_discord_inline_status()
        masked = (token[:4] + "…" + token[-4:]) if token else "(not set)"
        lib_ok, lib_version, _lib_err = discord_py_status()
        if lib_ok:
            lib_line = f"✓  discord.py installed  (v{lib_version or '?'})"
        else:
            lib_line = "⚠  discord.py NOT installed — run:  uv tool install --force worldlines"

        # Is the runtime bridge currently wired into the hub? We read this
        # live so the dashboard reflects `/bridge start|stop discord`.
        hub = getattr(self, "_bridge_hub", None)
        bridge_running = False
        if hub is not None:
            try:
                bridge_running = "discord" in hub.list_bridges()
            except Exception:
                bridge_running = False

        def _mark(ok: bool) -> str:
            return "✓" if ok else "○"

        has_any = bool(token or app_id or channel)

        options: list[tuple[str, str]] = []
        options.append(section(f"── {t('discord_setup.title')} ──"))
        options.append(spacer())

        if not has_any:
            # First-run welcome
            for line in t("discord_setup.welcome").split("\n"):
                options.append((line or " ", "__noop__"))
            options.append(spacer())
            options.append((f"▶  {t('discord_setup.begin')}", "step_portal"))
            options.append((t("discord_setup.skip"), "back"))
        else:
            # Dashboard — show progress + actions.
            # Relay on/off is the single source of truth: toggling it both
            # persists `autostart` and starts/stops the runtime bridge, so
            # the user never has two controls for the same thing.
            relay_marker = "●" if bridge_running else "○"
            relay_label = "ON  — mirroring narrator turns to Discord" if bridge_running else "OFF — turns stay local to the TUI"
            options.append((f"{_mark(bool(app_id))}  Application ID:  {app_id or '(not set)'}", "set_app_id"))
            options.append((f"{_mark(bool(token))}  Bot token:       {masked}", "set_token"))
            options.append((f"{_mark(bool(channel))}  Channel ID:      {channel or '(not set)'}", "set_channel"))
            options.append((f"   Guild ID:        {guild or '(optional)'}", "set_guild"))
            options.append((f"   Relay mode:      {relay}  ({' | '.join(VALID_RELAY_MODES)})", "set_relay"))
            if token and channel and lib_ok:
                options.append((f"{relay_marker}  Relay:           {relay_label}", "toggle_relay"))
            else:
                options.append(("○  Relay:           disabled (complete setup above first)", "__noop__"))
            options.append(spacer())
            options.append((f"   {t('discord_setup.status')}:          {status}", "__noop__"))
            options.append((f"   {lib_line}", "__noop__"))
            options.append(spacer())
            options.append(section("── actions ──"))
            options.append(spacer())
            if app_id or token:
                options.append((f"🔗  {t('discord_setup.invite_url_title')}", "show_invite"))
            if token and channel:
                options.append((f"▶  {t('discord_setup.test_connection')}  (ping + send test message)", "test_conn"))
            options.append(("✗  Delete Discord config", "delete"))
            options.append(spacer())
            options.append((t("settings.back"), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self._step_settings_menu()
                return
            if value in ("__noop__",):
                self._step_configure_discord()
                return
            if value == "step_portal":
                self._step_discord_portal_hint()
                return
            if value == "set_app_id":
                self._step_prompt_text(
                    t("discord_setup.app_id_prompt"),
                    default=app_id,
                    on_submit=lambda v: self._discord_save_and_refresh({"application_id": v}),
                )
                return
            if value == "set_token":
                self._step_prompt_text(
                    t("discord_setup.token_prompt"),
                    default="",
                    on_submit=lambda v: self._discord_save_and_refresh({"bot_token": v}),
                )
                return
            if value == "set_channel":
                self._step_prompt_text(
                    t("discord_setup.channel_prompt"),
                    default=channel,
                    on_submit=lambda v: self._discord_save_and_refresh({"channel_id": v}),
                )
                return
            if value == "set_guild":
                self._step_prompt_text(
                    t("discord_setup.guild_prompt"),
                    default=guild,
                    on_submit=lambda v: self._discord_save_and_refresh({"guild_id": v}),
                )
                return
            if value == "set_relay":
                self._step_prompt_text(
                    f"Relay mode ({' | '.join(VALID_RELAY_MODES)})",
                    default=relay,
                    on_submit=lambda v: self._discord_save_and_refresh({"relay_mode": v}),
                )
                return
            if value == "toggle_relay":
                # The launcher is a separate App instance from the running
                # NeonRPApp — their bridge hubs don't share state. Any
                # in-process start/stop here would target the launcher's
                # (empty) hub, not the game. So we only flip the persisted
                # `autostart` flag; the new value takes effect on the next
                # `worldlines` / `neonrp` launch. This also matches the
                # user's mental model: Discord relay = "on/off for next run".
                new_state = not bridge_running
                set_discord_settings(autostart=new_state)  # type: ignore[call-arg]
                # If we're inside a live NeonRPApp (the in-app /settings
                # flow), apply immediately via its real `_cmd_bridge`.
                cmd_bridge = getattr(self, "_cmd_bridge", None)
                if callable(cmd_bridge):
                    cmd_bridge(["start", "discord"] if new_state else ["stop", "discord"])
                self._step_configure_discord()
                return
            if value == "show_invite":
                invite = discord_oauth_invite_url(application_id=app_id, bot_token=token)
                if not invite:
                    # Couldn't resolve a valid Application ID from either the
                    # explicit field or by decoding the bot token.
                    err_note = [
                        section("── Can't build invite URL ──"),
                        spacer(),
                        ("Discord needs a numeric Application ID (Snowflake).", "__noop__"),
                        ("Go back and fill the 'Application ID' row from the developer portal:", "__noop__"),
                        ("   https://discord.com/developers/applications", "__noop__"),
                        ("   → your app → General Information → Application ID", "__noop__"),
                        spacer(),
                        (t("settings.back"), "back"),
                    ]
                    self.push_screen(
                        ChoicePickerScreen("Discord — invite URL", err_note),
                        lambda _v: self._step_configure_discord(),
                    )
                    return

                # Best-effort: open the invite URL in the user's browser so
                # they don't have to copy-paste manually. Falls through if
                # no browser is available (SSH session, etc).
                browser_opened = False
                try:
                    import webbrowser

                    browser_opened = webbrowser.open(invite, new=2)
                except Exception:
                    browser_opened = False

                hint = (
                    "✓  Browser opened — authorize the bot in the page that appeared."
                    if browser_opened
                    else "Browser couldn't open automatically. Copy the URL below and paste it:"
                )
                note = [
                    section(f"── {t('discord_setup.invite_url_title')} ──"),
                    spacer(),
                    (hint, "__noop__"),
                    spacer(),
                    (invite, "__noop__"),
                    spacer(),
                    ("After authorizing, come back here and run 'Test connection'.", "__noop__"),
                    spacer(),
                    (t("settings.back"), "back"),
                ]

                def _invite_back(v: str | None) -> None:
                    # Only return to wizard on explicit Back / Esc; clicking
                    # a noop row would otherwise dismiss the modal before the
                    # user can read the URL.
                    if v is None or v == "back":
                        self._step_configure_discord()
                        return
                    # Re-push the screen (no-op rows shouldn't close it).
                    self.push_screen(
                        ChoicePickerScreen(t("discord_setup.invite_url_title"), note),
                        _invite_back,
                    )

                self.push_screen(
                    ChoicePickerScreen(t("discord_setup.invite_url_title"), note),
                    _invite_back,
                )
                return
            if value == "test_conn":
                self._step_discord_test_connection()
                return
            if value == "delete":
                clear_discord_settings()
                self._step_configure_discord()

        self.push_screen(
            ChoicePickerScreen(t("discord_setup.title"), options),
            on_selected,
        )

    def _discord_save_and_refresh(self, updates: dict[str, Any]) -> None:
        """Persist partial Discord updates and redisplay the wizard."""
        from neonrp.core.discord_config import set_discord_settings

        cleaned = {k: str(v).strip() for k, v in updates.items() if v is not None and str(v).strip()}
        if cleaned:
            set_discord_settings(**cleaned)  # type: ignore[arg-type]
        self._step_configure_discord()

    def _step_discord_portal_hint(self) -> None:
        """Step 1: point the user at the Discord developer portal."""
        t = lambda k: get_message(self.locale, k)  # noqa: E731
        options = [
            section("── step 1 / 4: developer portal ──"),
            spacer(),
            ("Open this URL in your browser:", "__noop__"),
            ("   https://discord.com/developers/applications", "__noop__"),
            spacer(),
            ("Then:  New Application → Bot → Reset Token (copy the token).", "__noop__"),
            ("Scroll down to 'Application ID' on the General page — copy it too.", "__noop__"),
            spacer(),
            ("▶  Next: paste Application ID", "goto_app_id"),
            (t("settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            if value == "goto_app_id":
                self._step_prompt_text(
                    t("discord_setup.app_id_prompt"),
                    default="",
                    on_submit=lambda v: self._discord_save_and_refresh({"application_id": v}),
                )
                return
            self._step_configure_discord()

        self.push_screen(
            ChoicePickerScreen(t("discord_setup.title"), options),
            on_selected,
        )

    def _step_discord_test_connection(self) -> None:
        """Two-step probe: REST ping + send a real test message to the channel.

        Runs in a background thread behind an animated spinner so the TUI
        stays responsive. The worker uses urllib directly — discord.py isn't
        required for REST — but we also report whether the runtime lib is
        installed, because the live relay needs it.

        The second step posts `POST /channels/{id}/messages` so the user
        sees an actual message land in the configured Discord channel and
        knows the pipe works end-to-end.
        """
        from neonrp.core.discord_config import get_discord_settings
        from neonrp.bridges.discord_bridge import discord_py_status

        settings = get_discord_settings()
        token = settings.get("bot_token", "")
        channel_id = str(settings.get("channel_id", "") or "").strip()
        t = lambda k: get_message(self.locale, k)  # noqa: E731

        lib_ok, lib_version, lib_err = discord_py_status()
        lib_line = (
            f"✓  discord.py installed  (v{lib_version or '?'})"
            if lib_ok
            else "⚠  discord.py NOT installed — live relay won't start"
        )

        def _show_result(lines: list[str]) -> None:
            rows: list[tuple[str, str]] = [
                section(f"── {t('discord_setup.test_connection')} ──"),
                spacer(),
                (lib_line, "__noop__"),
            ]
            for line in lines:
                rows.append((line, "__noop__"))
            if not lib_ok:
                rows.append(spacer())
                rows.append(("Install runtime dep with:  uv sync --extra discord", "__noop__"))
            rows.append(spacer())
            rows.append((t("settings.back"), "back"))
            self.push_screen(
                ChoicePickerScreen(t("discord_setup.test_connection"), rows),
                lambda _v: self._step_configure_discord(),
            )

        if not token:
            _show_result(["✗  No bot token configured"])
            return

        def _worker() -> str:
            import urllib.request
            import urllib.error
            import json as _json

            lines: list[str] = []

            # Step 1 — GET /users/@me (validates the token)
            try:
                req = urllib.request.Request(
                    "https://discord.com/api/v10/users/@me",
                    headers={
                        "Authorization": f"Bot {token}",
                        "User-Agent": "neonrp-discord-test",
                    },
                )
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                bot_name = str(data.get("username", "?"))
                bot_id = str(data.get("id", ""))
                lines.append(f"✓  Auth OK — {bot_name} (id={bot_id})")
            except Exception as exc:
                msg = str(exc).split("\n")[0][:120]
                lines.append(f"✗  Auth failed — {msg}")
                # Don't try step 2 if auth failed.
                return "\n".join(lines)

            # Step 2 — POST /channels/{id}/messages
            if not channel_id:
                lines.append("⚠  No channel_id configured — skipped send test")
                return "\n".join(lines)
            try:
                payload = _json.dumps(
                    {"content": "✅ NeonRP test message — bridge wiring verified."}
                ).encode("utf-8")
                req2 = urllib.request.Request(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    data=payload,
                    method="POST",
                    headers={
                        "Authorization": f"Bot {token}",
                        "Content-Type": "application/json",
                        "User-Agent": "neonrp-discord-test",
                    },
                )
                with urllib.request.urlopen(req2, timeout=6.0) as resp:
                    resp.read()
                lines.append(f"✓  Sent test message to channel {channel_id}")
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", "ignore")[:200]
                except Exception:
                    pass
                hint = ""
                if exc.code == 403:
                    hint = "  (bot missing 'Send Messages' / 'View Channel' on that channel)"
                elif exc.code == 404:
                    hint = "  (channel_id wrong, or bot not in that server)"
                lines.append(f"✗  Send failed — HTTP {exc.code}{hint}")
                if body:
                    lines.append(f"   {body[:120]}")
            except Exception as exc:
                msg = str(exc).split("\n")[0][:120]
                lines.append(f"✗  Send failed — {msg}")

            return "\n".join(lines)

        def _on_spinner_done(result: str) -> None:
            # Esc cancelled before the worker finished → go back.
            if not result:
                self._step_configure_discord()
                return
            _show_result(result.split("\n"))

        self.push_screen(
            SpinnerWorkerScreen(
                t("discord_setup.test_connection"),
                "Validating token + sending test message …",
                _worker,
            ),
            _on_spinner_done,
        )

    def _return_to_main(self) -> None:
        try:
            self._focus_menu_button(0)
        except Exception:
            pass

    def _step_show_config_path(self) -> None:
        from neonrp.presets import _USER_CONFIG_PATH

        path_str = str(_USER_CONFIG_PATH)
        exists = "(exists)" if _USER_CONFIG_PATH.exists() else "(not created yet)"
        options = [(f"{path_str}  {exists}", "ok"), ("Back", "back")]

        def on_selected(value: str | None) -> None:
            self._step_settings_menu()

        self.push_screen(ChoicePickerScreen("Config file location", options), on_selected)

    def _step_configure_preset(self, preset_id: str) -> None:
        from neonrp.presets import PRESETS, _load_user_config_models

        user_models = _load_user_config_models()
        cur_key = user_models.get(preset_id, {}).get("api_key", "")
        cur_model = user_models.get(preset_id, {}).get("model", "") or PRESETS.get(preset_id, {}).get("model", "")

        masked = (cur_key[:4] + "…" + cur_key[-4:]) if cur_key else "(not set)"
        options = [
            (f"Current key: {masked}", "noop"),
            (f"Current model: {cur_model}", "noop"),
            ("Update API key", "set_key"),
            ("Update model id", "set_model"),
            ("Delete entry", "delete"),
            ("Back", "back"),
        ]

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self._step_settings_menu()
                return
            if value == "set_key":
                self._step_prompt_text(
                    f"API key for {preset_id}",
                    default="",
                    on_submit=lambda raw: self._apply_key_update(preset_id, raw),
                )
                return
            if value == "set_model":
                self._step_prompt_text(
                    f"model id for {preset_id}",
                    default=cur_model,
                    on_submit=lambda raw: self._apply_model_update(preset_id, raw),
                )
                return
            if value == "delete":
                self._delete_preset_entry(preset_id)
                self._step_settings_menu()
                return
            self._step_configure_preset(preset_id)

        self.push_screen(ChoicePickerScreen(f"Configure {preset_id}", options), on_selected)

    def _apply_key_update(self, preset_id: str, raw: str) -> None:
        from neonrp.presets import _save_key_to_user_config

        raw = (raw or "").strip()
        if raw:
            _save_key_to_user_config(preset_id, raw)
            os.environ.setdefault("_", "")
        self._refresh_presets()
        self._step_configure_preset(preset_id)

    def _apply_model_update(self, preset_id: str, raw: str) -> None:
        import json
        from neonrp.presets import _USER_CONFIG_PATH

        raw = (raw or "").strip()
        if not raw:
            self._step_configure_preset(preset_id)
            return
        try:
            data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8")) if _USER_CONFIG_PATH.exists() else {}
            models = data.setdefault("models", {})
            entry = models.setdefault(preset_id, {})
            entry["model"] = raw
            _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self._refresh_presets()
        self._step_configure_preset(preset_id)

    def _delete_preset_entry(self, preset_id: str) -> None:
        import json
        from neonrp.presets import _USER_CONFIG_PATH

        if not _USER_CONFIG_PATH.exists():
            return
        try:
            data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
            if "models" in data and preset_id in data["models"]:
                del data["models"][preset_id]
                _USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self._refresh_presets()

    def _step_add_custom_model(self) -> None:
        self._step_prompt_text(
            "custom model id (e.g. my-llama)",
            default="",
            on_submit=self._after_custom_model_id,
        )

    def _after_custom_model_id(self, model_id: str) -> None:
        model_id = (model_id or "").strip().lower().replace(" ", "-")
        if not model_id:
            self._step_settings_menu()
            return
        self._step_prompt_text(
            f"base_url for {model_id}",
            default="http://localhost:11434/v1",
            on_submit=lambda base_url: self._after_custom_base_url(model_id, base_url),
        )

    def _after_custom_base_url(self, model_id: str, base_url: str) -> None:
        self._step_prompt_text(
            f"model name to send to the API for {model_id}",
            default=model_id,
            on_submit=lambda model_name: self._after_custom_model_name(model_id, base_url, model_name),
        )

    def _after_custom_model_name(self, model_id: str, base_url: str, model_name: str) -> None:
        self._step_prompt_text(
            f"api key for {model_id} (leave blank if not needed)",
            default="",
            on_submit=lambda api_key: self._write_custom_model(model_id, base_url, model_name, api_key),
        )

    def _write_custom_model(self, model_id: str, base_url: str, model_name: str, api_key: str) -> None:
        from neonrp.presets import save_custom_model

        try:
            save_custom_model(model_id, base_url, model_name, api_key)
        except Exception:
            pass
        self._refresh_presets()
        self._step_settings_menu()

    def _step_prompt_text(
        self,
        title: str,
        default: str,
        on_submit: Callable[[str], None],
        *,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        def handler(value: str | None) -> None:
            if value is None:
                if on_cancel is not None:
                    on_cancel()
                else:
                    self._step_settings_menu()
                return
            on_submit(value)

        self.push_screen(TextInputScreen(title, default=default), handler)

    def _step_choose_entry(self) -> None:
        if not self._saved_games:
            self._step_choose_world()
            return

        options = [
            (f"Continue existing game ({len(self._saved_games)})", "__continue__"),
            ("Start a new game", "__new__"),
        ]

        def on_selected(value: str | None) -> None:
            if value is None:
                self.exit()
                return
            if value == "__continue__":
                self._step_choose_saved_game()
                return
            self._step_choose_world()

        self.push_screen(ChoicePickerScreen("WorldLines", options), on_selected)

    def _step_choose_saved_game(self) -> None:
        # Continue picker only shows games that have actually been
        # played (≥ 1 session logged). Freshly-downloaded but never-
        # started games live under "Start new game" — see
        # `_step_choose_world`.
        from neonrp.worlds import group_games_by_wid, list_saved_games

        # Re-scan on open so a game played/created/imported mid-session is
        # reflected (self._saved_games is otherwise the construction-time cache).
        self._saved_games = list_saved_games()

        started_games = [g for g in self._saved_games if g.get("started")]

        options: list[tuple[str, str]] = []
        options.append(section(f"── {get_message(self.locale, 'saved.section.runs')} ──"))
        options.append(spacer())

        if started_games:
            buckets = group_games_by_wid(started_games)
            for bucket in buckets:
                runs = bucket["runs"]
                wid = bucket["wid"]
                if len(runs) == 1:
                    g = runs[0]
                    options.append(
                        (f"  {g['display_name']}  —  {g['mtime_display']}", f"pick::{g['path']}")
                    )
                else:
                    # Multi-run bucket. Parent always picks the latest;
                    # an expand/collapse child row toggles whether the
                    # older runs are visible.
                    head = runs[0]
                    is_expanded = wid in self._continue_expanded
                    arrow = "▾" if is_expanded else "▸"
                    options.append(
                        (
                            f"{arrow} {bucket['display_name']}  —  [{len(runs)} runs]  ·  latest {head['mtime_display']}",
                            f"pick::{head['path']}",
                        )
                    )
                    if is_expanded:
                        for g in runs[1:]:
                            options.append(
                                (f"     · {g['mtime_display']}  ({g['dir_name']})", f"pick::{g['path']}")
                            )
                        options.append(("     └ collapse", f"collapse::{wid}"))
                    else:
                        options.append(
                            (f"     └ show {len(runs) - 1} more", f"expand::{wid}")
                        )
        else:
            options.append(("(no saved runs yet)", "__noop__"))

        options.append(spacer())
        options.append(section(f"── {get_message(self.locale, 'saved.section.actions')} ──"))
        options.append(spacer())
        if started_games:
            options.append((get_message(self.locale, "saved.export"), "export_pick"))
            options.append((get_message(self.locale, "saved.delete"), "delete_pick"))

        def on_selected(value: str | None) -> None:
            if value is None:
                # Top-level picker: just dismiss; main launcher panel shows again.
                self._focus_menu_button(0)
                return
            if value == "__noop__":
                self._step_choose_saved_game()
                return
            if value == "export_pick":
                self._step_export_pick_game()
                return
            if value == "delete_pick":
                self._step_delete_pick_game()
                return
            if value.startswith("expand::"):
                self._continue_expanded.add(value.split("::", 1)[1])
                self._step_choose_saved_game()
                return
            if value.startswith("collapse::"):
                self._continue_expanded.discard(value.split("::", 1)[1])
                self._step_choose_saved_game()
                return
            if value.startswith("pick::"):
                self._selected_game = Path(value.split("::", 1)[1])
                self._step_world_preview(
                    self._selected_game,
                    on_play=lambda: self._step_choose_preset(continue_mode=True),
                    on_back=self._step_choose_saved_game,
                )
                return

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "picker.continue_game"), options),
            on_selected,
        )

    def _step_world_preview(
        self,
        world_path: Path,
        *,
        on_play: "Any",
        on_back: "Any",
        title: str | None = None,
    ) -> None:
        """Show an ASCII-rendered preview of ``world_path`` before launching.

        Synchronous render — the world is already unpacked locally so we
        just walk its image assets and matrix-braille them. Falls back to
        the bundled card-door.png when the world ships no imagery.
        """
        from neonrp.core.image_render import (
            DEFAULT_CARD_PATH,
            discover_world_images,
            render_image_lines,
        )

        images = discover_world_images(world_path)
        if not images and DEFAULT_CARD_PATH.is_file():
            images = [DEFAULT_CARD_PATH]

        ascii_rows: list[tuple] = []
        for img in images[:2]:
            lines = render_image_lines(img, width=60, height=22, mode="braille")
            if not lines:
                continue
            for line in lines:
                ascii_rows.append((line, "__section__"))
            ascii_rows.append(spacer())

        screen_title = title or world_path.name
        options = [
            section(f"── {screen_title} ──"),
            spacer(),
            *ascii_rows,
            section("── actions ──"),
            spacer(),
            ("▶  Play", "play"),
            (get_message(self.locale, "settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            if value == "play":
                on_play()
                return
            on_back()

        self.push_screen(
            ChoicePickerScreen(screen_title, options),
            on_selected,
        )

    # ------------------------------------------------------------------
    # Export / Load saved runs — sub-flows triggered from the saved-game
    # picker. Both delegate to neonrp.core.world_export under the hood.
    # ------------------------------------------------------------------

    def _step_export_pick_game(self) -> None:
        """Ask the user which saved run to export, then prompt for a path."""
        if not self._saved_games:
            self._step_choose_saved_game()
            return
        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'saved.section.runs')} ──"),
            spacer(),
        ]
        for game in self._saved_games:
            options.append(
                (f"{game['display_name']}  —  {game['mtime_display']}", f"exp::{game['path']}")
            )
        options.append(spacer())
        options.append((get_message(self.locale, "settings.back"), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self._step_choose_saved_game()
                return
            if value.startswith("exp::"):
                self._step_export_prompt_path(Path(value.split("::", 1)[1]))

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "saved.export"), options),
            on_selected,
        )

    def _step_export_prompt_path(self, world_path: Path) -> None:
        """Ask for the output .zip path (default: ~/Downloads/)."""
        from neonrp.core.world_export import default_export_path

        default_out = str(default_export_path(world_path))

        def on_submit(raw: str) -> None:
            raw = (raw or "").strip()
            target = Path(raw or default_out).expanduser()
            self._run_export(world_path, target)

        self._step_prompt_text(
            f"{get_message(self.locale, 'saved.export')}",
            default=default_out,
            on_submit=on_submit,
        )

    def _run_export(self, world_path: Path, output_path: Path) -> None:
        """Run the export, then show a result screen."""
        from neonrp.core.world_export import export_world, summarize_archive

        try:
            final = export_world(world_path, output_path)
            info = summarize_archive(final)
            msg = get_message(self.locale, "export.success").format(
                files=info["file_count"], mb=info["size_mb"]
            )
            lines = [f"✓  {msg}", f"   {final}"]
        except Exception as exc:
            lines = [f"✗  {type(exc).__name__}: {exc}"]

        self._show_result_screen(get_message(self.locale, "saved.export"), lines)

    def _step_load_zip_prompt(self) -> None:
        """Ask the user for the .zip path to load (new-game flow)."""
        def on_submit(raw: str) -> None:
            raw = (raw or "").strip()
            if not raw:
                self._step_choose_world()
                return
            self._run_load(Path(raw).expanduser())

        self._step_prompt_text(
            get_message(self.locale, "prompt.zip_path"),
            default="",
            on_submit=on_submit,
        )

    def _run_load(self, zip_path: Path) -> None:
        from neonrp.core.world_export import load_world_zip
        from neonrp.worlds import list_saved_games

        try:
            target = load_world_zip(zip_path)
        except Exception as exc:
            self._show_result_screen(
                get_message(self.locale, "saved.load"),
                [f"✗  {type(exc).__name__}: {exc}"],
            )
            return

        self._saved_games = list_saved_games()

        # If the imported zip has actual session history (someone uploaded
        # their saved game), open it via the continue path so their state
        # resumes. Otherwise treat it like a fresh download — route to the
        # new-game preset picker, then run the startup handoff.
        loaded = next((g for g in self._saved_games if g["path"] == target), None)
        if loaded is not None and loaded.get("started"):
            self._selected_game = target
            self._step_choose_preset(continue_mode=True)
            return

        self._launch_existing_dir = target
        self._selected_player = None
        self._step_choose_preset(continue_mode=False)

    # ------------------------------------------------------------------
    # WorldHub download — picker over the public registry, with manual
    # hash entry as a fallback.
    # ------------------------------------------------------------------

    def _step_hub_download_prompt(self, *, kind: str = "worlds") -> None:
        """Fetch the hub registry for ``kind`` (worlds or souls), show
        stories grouped by slug, each row downloads the latest version.
        Manual hash entry stays as a fallback option."""
        from neonrp.core.worldhub import WorldHubError, list_stories

        self._hub_kind = kind
        stories: list[dict] = []
        fetch_error: str | None = None
        try:
            stories = list_stories(kind=kind)
        except WorldHubError as exc:
            fetch_error = str(exc)
        except Exception as exc:
            fetch_error = f"{type(exc).__name__}: {exc}"

        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'hub.picker.section')} ──"),
            spacer(),
        ]
        if fetch_error is not None:
            note = get_message(self.locale, "hub.picker.fetch_failed").format(error=fetch_error)
            options.append((f"  {note}", "__noop__"))
        elif not stories:
            options.append((f"  {get_message(self.locale, 'hub.picker.empty')}", "__noop__"))
        else:
            # One row per slug, latest version only. Older versions
            # remain reachable through the "manual hash entry" fallback.
            for s in stories:
                latest = s["versions"][0]
                slug = s["slug"]
                latest_size_mb = latest.get("size_bytes", 0) / (1024 * 1024)
                slug_col = _ellipsize(slug, 22)
                name_col = _ellipsize(latest.get("name") or s["display_name"], 36)
                version_col = _ellipsize(f"v{s['latest_version']}", 10)
                label = f"  {slug_col:<22}  {name_col:<36}  {version_col:<10}  {latest_size_mb:>5.2f} MB"
                options.append((_ellipsize(label, 90), f"slug::{slug}"))

        options.append(spacer())
        options.append(section(f"── {get_message(self.locale, 'hub.picker.actions')} ──"))
        options.append(spacer())
        options.append((get_message(self.locale, "hub.picker.refresh"), "refresh"))
        options.append((get_message(self.locale, "hub.picker.manual"), "manual"))

        def on_selected(value: str | None) -> None:
            if value is None:
                # Back to main launcher menu — WorldHub/SoulHub are now
                # top-level entries, not steps inside the new-game flow.
                menu_ids = self._menu_button_ids()
                target_id = "wl-soul-download" if kind == "souls" else "wl-hub-download"
                if target_id in menu_ids:
                    self._focus_menu_button(menu_ids.index(target_id))
                return
            if value == "__noop__":
                self._step_hub_download_prompt(kind=kind)
                return
            if value == "refresh":
                self._step_hub_download_prompt(kind=kind)
                return
            if value == "manual":
                self._step_hub_manual_prompt(kind=kind)
                return
            if value.startswith("slug::"):
                slug = value.split("::", 1)[1]
                if kind == "worlds":
                    self._step_hub_world_detail(slug, kind=kind)
                else:
                    self._run_hub_download(slug, kind=kind)
                return
            if value.startswith("hub::"):
                hash_short = value.split("::", 1)[1]
                if kind == "worlds":
                    self._step_hub_world_detail(hash_short, kind=kind)
                else:
                    self._run_hub_download(hash_short, kind=kind)
                return

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "hub.picker.title"), options),
            on_selected,
        )

    def _step_hub_manual_prompt(self, *, kind: str = "worlds") -> None:
        """Fallback path: paste a hash or slug@version manually (useful
        before a world is in the registry, or for testing)."""
        def on_submit(raw: str) -> None:
            raw = (raw or "").strip()
            if not raw:
                self._step_hub_download_prompt(kind=kind)
                return
            self._run_hub_download(raw, kind=kind)

        self._step_prompt_text(
            get_message(self.locale, "prompt.hub_hash"),
            default="",
            on_submit=on_submit,
        )

    # ------------------------------------------------------------------
    # World detail — after picker click, fetch the bundle, show
    # ASCII-rendered cover/portraits, then offer Play / Back.
    # ------------------------------------------------------------------
    def _step_hub_world_detail(self, query: str, *, kind: str = "worlds") -> None:
        """Show a preview screen for the selected world.

        Kicks off ``worldhub.download`` in a worker thread (already
        idempotent for installed worlds), then re-renders with ASCII
        previews of any bundled cover / portrait imagery.
        """
        # Hold the resolved target dir across the worker hop.
        self._hub_detail_dir: Path | None = None
        self._hub_detail_kind = kind
        self._hub_detail_query = query

        self._push_hub_detail_loading(query=query)

        def worker() -> None:
            from neonrp.core.worldhub import download

            try:
                target = download(query, kind=kind)
            except Exception as exc:
                self.call_from_thread(self._on_hub_detail_failed, str(exc))
                return
            self.call_from_thread(self._on_hub_detail_ready, target)

        self.run_worker(worker, exclusive=True, thread=True, name="hub-detail")

    def _push_hub_detail_loading(self, *, query: str) -> None:
        options = [
            section(f"── {get_message(self.locale, 'hub.picker.title')} ──"),
            spacer(),
            (f"  {query}", "__noop__"),
            (f"  {get_message(self.locale, 'hub.downloading')}", "__noop__"),
            spacer(),
            (get_message(self.locale, "settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            # Cancel-back from a loading screen → straight back to the
            # picker. The worker will still complete; its callback notices
            # the screen is gone and does nothing.
            self._hub_detail_dir = None
            self._step_hub_download_prompt(kind=self._hub_detail_kind)

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "hub.picker.title"), options),
            on_selected,
        )

    def _on_hub_detail_failed(self, error: str) -> None:
        lines = [get_message(self.locale, "hub.failed").format(error=error)]
        self._show_result_screen(get_message(self.locale, "saved.hub_download"), lines)

    def _on_hub_detail_ready(self, target: Path) -> None:
        self._hub_detail_dir = target

        # Drop the loading screen first so the preview pushed below is
        # the only modal on the stack.
        try:
            self.pop_screen()
        except Exception:
            pass

        def go_play() -> None:
            from neonrp.worlds import list_saved_games

            self._saved_games = list_saved_games()
            self._launch_existing_dir = self._hub_detail_dir
            self._selected_player = None
            self._step_choose_preset(continue_mode=False)

        self._step_world_preview(
            target,
            on_play=go_play,
            on_back=lambda: self._step_hub_download_prompt(kind=self._hub_detail_kind),
            title=target.name,
        )

    def _run_hub_download(self, hash_query: str, *, kind: str = "worlds") -> None:
        from neonrp.core.worldhub import download
        from neonrp.worlds import list_saved_games

        try:
            target = download(hash_query, kind=kind)
        except Exception as exc:
            lines = [
                get_message(self.locale, "hub.failed").format(error=f"{type(exc).__name__}: {exc}")
            ]
            title_key = "menu.soul_download" if kind == "souls" else "saved.hub_download"
            self._show_result_screen(get_message(self.locale, title_key), lines)
            return

        if kind == "souls":
            # SoulHub: don't auto-launch — just confirm the install.
            lines = [str(target)]
            self._show_result_screen(get_message(self.locale, "menu.soul_download"), lines)
            return

        # Refresh in-memory state, then route the user straight into the
        # new-game launch path: the dir is on disk but the engine has
        # never run a turn, so the next step is "pick a model and start
        # the game" — exactly the same flow as a builtin new world.
        self._saved_games = list_saved_games()
        self._launch_existing_dir = target
        # No player profile yet; downloaded worlds bring their own
        # player/profile.json. The preset picker is the only thing
        # left between the user and the opening scene.
        self._selected_player = None
        self._step_choose_preset(continue_mode=False)

    # ------------------------------------------------------------------
    # Delete — two-step picker to make accidental removal impossible.
    # ------------------------------------------------------------------

    # --- world / soul library overviews (一览 + delete) --------------------
    # Mirror the saved-run delete flow above: a ChoicePickerScreen lists every
    # item, each owned item carries a "删除" row that routes to a confirm step,
    # and a successful delete refreshes the same overview so the removed item
    # disappears. Built-in (packaged) worlds are listed read-only — no delete.

    def _step_manage_worlds(self) -> None:
        """世界一览: list every world; owned worlds get a 删除 action."""
        from neonrp.worlds import list_worlds

        worlds = list_worlds(locale=self.locale)
        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'manage.world_title')} ──"),
            spacer(),
        ]
        owned = [w for w in worlds if w.get("owned")]
        builtin = [w for w in worlds if not w.get("owned")]
        # Owned worlds first (the deletable ones), then read-only built-ins.
        for w in owned:
            origin = w.get("origin", "created")
            options.append((f"  {w['display_name']}  ·  {origin}", "__noop__"))
            options.append(
                (f"     {get_message(self.locale, 'manage.delete')}", f"del::{w['id']}")
            )
        for w in builtin:
            label = get_message(self.locale, "manage.builtin_readonly")
            options.append((f"  {w['display_name']}  ·  {label}", "__noop__"))
        if not worlds:
            options.append((get_message(self.locale, "manage.empty"), "__noop__"))
        options.append(spacer())
        options.append((get_message(self.locale, "manage.back"), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                return  # pop back to the home menu (it re-relabels counts)
            if value == "__noop__":
                self._step_manage_worlds()
                return
            if value.startswith("del::"):
                world_id = value.split("::", 1)[1]
                name = next(
                    (w["display_name"] for w in worlds if w["id"] == world_id), world_id
                )
                self._step_confirm_delete_world(world_id, name)
                return

        self.push_screen(
            ChoicePickerScreen(
                get_message(self.locale, "manage.world_title"), options
            ),
            on_selected,
        )

    def _step_confirm_delete_world(self, world_id: str, name: str) -> None:
        """Confirm + delete one owned world, then refresh the overview."""
        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'manage.delete')} ──"),
            spacer(),
            (get_message(self.locale, "manage.confirm_delete").format(name=name), "__noop__"),
            spacer(),
            # Cancel first so focus lands on the safe option.
            (get_message(self.locale, "saved.delete.cancel"), "cancel"),
            (get_message(self.locale, "saved.delete.yes"), "confirm"),
        ]

        def on_selected(value: str | None) -> None:
            if value == "confirm":
                from neonrp.worlds import delete_owned_world

                delete_owned_world(world_id)
                self._show_world_manage_result(
                    get_message(self.locale, "manage.deleted").format(name=name)
                )
                return
            if value == "__noop__":
                self._step_confirm_delete_world(world_id, name)
                return
            self._step_manage_worlds()

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "manage.delete"), options),
            on_selected,
        )

    def _show_world_manage_result(self, line: str) -> None:
        """Brief status, then back into the (now-refreshed) world overview."""
        options: list[tuple[str, str]] = [
            spacer(),
            (line, "__noop__"),
            spacer(),
            (get_message(self.locale, "manage.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            self._step_manage_worlds()

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "manage.world_title"), options),
            on_selected,
        )

    def _step_manage_souls(self) -> None:
        """角色一览: list every soul in the library; each gets a 删除 action."""
        from neonrp.core.souls import list_souls

        souls = list_souls(locale=self.locale)
        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'manage.char_title')} ──"),
            spacer(),
        ]
        for s in souls:
            options.append((f"  {s['display_name']}", "__noop__"))
            options.append(
                (f"     {get_message(self.locale, 'manage.delete')}", f"del::{s['dir_name']}")
            )
        if not souls:
            options.append((get_message(self.locale, "manage.empty"), "__noop__"))
        options.append(spacer())
        options.append((get_message(self.locale, "manage.back"), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                return
            if value == "__noop__":
                self._step_manage_souls()
                return
            if value.startswith("del::"):
                dir_name = value.split("::", 1)[1]
                name = next(
                    (s["display_name"] for s in souls if s["dir_name"] == dir_name),
                    dir_name,
                )
                self._step_confirm_delete_soul(dir_name, name)
                return

        self.push_screen(
            ChoicePickerScreen(
                get_message(self.locale, "manage.char_title"), options
            ),
            on_selected,
        )

    def _step_confirm_delete_soul(self, dir_name: str, name: str) -> None:
        """Confirm + delete one library soul, then refresh the overview."""
        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'manage.delete')} ──"),
            spacer(),
            (get_message(self.locale, "manage.confirm_delete").format(name=name), "__noop__"),
            spacer(),
            (get_message(self.locale, "saved.delete.cancel"), "cancel"),
            (get_message(self.locale, "saved.delete.yes"), "confirm"),
        ]

        def on_selected(value: str | None) -> None:
            if value == "confirm":
                from neonrp.core.souls import delete_soul

                delete_soul(dir_name)
                self._show_soul_manage_result(
                    get_message(self.locale, "manage.deleted").format(name=name)
                )
                return
            if value == "__noop__":
                self._step_confirm_delete_soul(dir_name, name)
                return
            self._step_manage_souls()

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "manage.delete"), options),
            on_selected,
        )

    def _show_soul_manage_result(self, line: str) -> None:
        """Brief status, then back into the (now-refreshed) soul overview."""
        options: list[tuple[str, str]] = [
            spacer(),
            (line, "__noop__"),
            spacer(),
            (get_message(self.locale, "manage.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            self._step_manage_souls()

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "manage.char_title"), options),
            on_selected,
        )

    def _step_delete_pick_game(self, focus_value: str | None = None) -> None:
        """Select-mode picker: tap rows to toggle, then confirm delete N.

        The action ID used in the continue picker is still `delete_pick` and
        this method is still named `_step_delete_pick_game` so the call
        sites don't change. But the UX is now multi-select instead of
        single-pick, matching user ask "click delete → select mode →
        press delete button after picking what to delete".

        ``focus_value`` lets a re-render (e.g. after a toggle) re-focus the
        same row the user just acted on — otherwise the cursor snaps back to
        the top of the list every keypress.
        """
        if not self._saved_games:
            self._step_choose_saved_game()
            return
        if not hasattr(self, "_delete_selection"):
            self._delete_selection: set[Path] = set()
        # Drop paths that no longer correspond to real saves (a previous
        # batch delete might have removed them without clearing the set).
        live_paths = {g["path"] for g in self._saved_games}
        self._delete_selection &= live_paths

        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'saved.section.runs')} ──"),
            spacer(),
            (f"  {get_message(self.locale, 'saved.delete.select_hint')}", "__noop__"),
            spacer(),
        ]
        for game in self._saved_games:
            mark = "[x]" if game["path"] in self._delete_selection else "[ ]"
            options.append(
                (
                    f"{mark}  {game['display_name']}  —  {game['mtime_display']}",
                    f"toggle::{game['path']}",
                )
            )
        options.append(spacer())
        options.append(section("── actions ──"))
        options.append(spacer())
        selected_count = len(self._delete_selection)
        if selected_count > 0:
            options.append(
                (
                    get_message(self.locale, "saved.delete.action_selected").format(count=selected_count),
                    "confirm_selected",
                )
            )
        options.append((get_message(self.locale, "settings.back"), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                # Bail: discard selection so next entry starts clean.
                self._delete_selection.clear()
                self._step_choose_saved_game()
                return
            if value == "__noop__":
                # Hint row — re-render picker, preserve selection + focus.
                self._step_delete_pick_game(focus_value=value)
                return
            if value.startswith("toggle::"):
                target = Path(value.split("::", 1)[1])
                if target in self._delete_selection:
                    self._delete_selection.discard(target)
                else:
                    self._delete_selection.add(target)
                # Keep the cursor on the row we just toggled — the same
                # value still exists in the rebuilt list (just with the
                # checkbox flipped), so initial_focus matches cleanly.
                self._step_delete_pick_game(focus_value=value)
                return
            if value == "confirm_selected":
                self._step_delete_confirm_batch()
                return

        self.push_screen(
            ChoicePickerScreen(
                get_message(self.locale, "saved.delete.pick_title"),
                options,
                initial_focus=focus_value,
            ),
            on_selected,
        )

    def _step_delete_confirm_batch(self) -> None:
        """Confirm batch deletion — shows every selected save by name."""
        selected = list(self._delete_selection)
        if not selected:
            self._step_delete_pick_game()
            return

        # Keep rows sorted by mtime (newest first) so the confirm list
        # matches the picker order above it.
        lookup = {g["path"]: g for g in self._saved_games}
        entries = [lookup[p] for p in selected if p in lookup]
        entries.sort(key=lambda g: g.get("mtime", 0), reverse=True)

        options: list[tuple[str, str]] = [
            section(f"── {get_message(self.locale, 'saved.delete.confirm_title')} ──"),
            spacer(),
            (get_message(self.locale, "saved.delete.confirm_line1"), "__noop__"),
        ]
        for entry in entries:
            options.append((f"   • {entry['display_name']}  —  {entry['mtime_display']}", "__noop__"))
        options.append(spacer())
        options.append((get_message(self.locale, "saved.delete.confirm_warn"), "__noop__"))
        options.append(spacer())
        # Cancel listed first so keyboard focus lands on the safe option.
        options.append((get_message(self.locale, "saved.delete.cancel"), "cancel"))
        options.append(
            (
                get_message(self.locale, "saved.delete.action_selected").format(count=len(entries)),
                "confirm",
            )
        )

        def on_selected(value: str | None) -> None:
            if value == "confirm":
                self._run_delete_batch()
                return
            if value == "__noop__":
                self._step_delete_confirm_batch()
                return
            # cancel / back / Esc → return to select picker, selection kept
            # so the user can refine their choice without reselecting from
            # scratch.
            self._step_delete_pick_game()

        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "saved.delete.confirm_title"), options),
            on_selected,
        )

    def _run_delete_batch(self) -> None:
        """Remove all selected saved-run directories."""
        from neonrp.worlds import list_saved_games

        selected = list(self._delete_selection)
        self._delete_selection.clear()

        deleted: list[str] = []
        errors: list[str] = []
        lookup = {g["path"]: g for g in self._saved_games}
        for path in selected:
            meta = lookup.get(path)
            name = meta["display_name"] if meta else path.name
            try:
                cc_sibling = path.with_name(path.name + "-cc")
                shutil.rmtree(path, ignore_errors=False)
                if cc_sibling.exists():
                    shutil.rmtree(cc_sibling, ignore_errors=True)
                deleted.append(name)
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")

        self._saved_games = list_saved_games()

        lines: list[str] = []
        if deleted:
            lines.append(
                get_message(self.locale, "saved.delete.success_count").format(count=len(deleted))
            )
            for name in deleted:
                lines.append(f"  • {name}")
        for err in errors:
            lines.append(
                get_message(self.locale, "saved.delete.failed").format(error=err)
            )

        self._show_result_screen(get_message(self.locale, "saved.delete"), lines)

    def _show_result_screen(self, title: str, body_lines: list[str]) -> None:
        """Tiny wrapper: push a ChoicePickerScreen that only shows status."""
        options: list[tuple[str, str]] = [spacer()]
        for line in body_lines:
            options.append((line, "__noop__"))
        options.append(spacer())
        options.append((get_message(self.locale, "settings.back"), "back"))

        def on_selected(value: str | None) -> None:
            self._step_choose_saved_game()

        self.push_screen(ChoicePickerScreen(title, options), on_selected)

    def _step_choose_world(self) -> None:
        # Re-resolve display names against the CURRENT locale — self._worlds was
        # built once at construction, so a mid-session language switch (the
        # first-run picker) would otherwise leave the world list in the old
        # language ("choose world still in Chinese after picking English").
        from neonrp.worlds import list_saved_games, list_worlds

        # Re-scan the games dir EVERY time the picker opens. self._saved_games
        # is cached at app construction; a world created / imported mid-session
        # lands as a new dir under ~/.worldlines/games/ that the stale cache
        # never sees — so the picker kept showing only the old worlds. Refresh
        # here so the just-created/imported world shows up immediately.
        self._saved_games = list_saved_games()

        worlds = list_worlds(locale=self.locale)
        if not worlds:
            self.exit()
            return

        # Games on disk that have never been played a turn — surfaced here
        # (NOT in the continue picker) so the user enters via the new-game
        # flow that fires the "开始游戏" handoff. BUT: an abandoned new-game
        # instance of a built-in / standard world (e.g. opening Kagura then
        # quitting) leaves a dir whose world_id is in the registry — it is
        # redundant with that world's own picker entry above and, being
        # unstarted, has nothing to resume. So show only genuine downloads
        # (hub worlds NOT in the registry), deduped by wid so repeated
        # downloads of one slug collapse to a single (newest) row. This is
        # why the list used to fill with duplicate Kagura / Stone Ford rows.
        from neonrp.worlds import WORLDS

        unstarted = []
        _seen_wid: set[str] = set()
        for g in self._saved_games:
            if g.get("started") or g.get("world_id") in WORLDS:
                continue
            wid = g.get("wid") or g.get("world_id") or g.get("dir_name")
            if wid in _seen_wid:
                continue
            _seen_wid.add(wid)
            unstarted.append(g)

        # Two shelves: "builtin" = the 3 engine test worlds (one per mode);
        # "standard" = polished content worlds (sakura / otome …) — shown under
        # 已下载 alongside the player's own unstarted downloads, NOT 内置.
        builtin = [w for w in worlds if w.get("shelf", "builtin") == "builtin"]
        # OWNED worlds (created or hub-downloaded) live in the world LIBRARY
        # under WORLDS_HOME and carry a world `id`. They are NOT raw on-disk
        # runs — selecting one must launch by world_id (so cli's
        # instantiate_run copies the library source into a fresh run), exactly
        # like a built-in. Split by origin only for display grouping; both
        # groups emit `w["id"]` through the normal world-id selection path.
        owned_standard = [
            w for w in worlds if w.get("owned") and w.get("shelf") == "standard"
        ]
        owned_created = [
            w for w in worlds if w.get("owned") and w.get("shelf") == "created"
        ]

        options: list[tuple[str, str]] = []
        options.append(section(f"── {get_message(self.locale, 'worlds.section.builtin')} ──"))
        options.append(spacer())
        for world in builtin:
            # 🌟 marks the recommended first play — stoneford-elena is the
            # flagship multi-agent demo we steer new users to (best paired
            # with the web UI render surface).
            star = "🌟 " if world["id"] == "stoneford-elena" else ""
            options.append(
                (f"{star}{world['display_name']}  —  {world['desc']}", world["id"])
            )

        if owned_standard or owned_created or unstarted:
            options.append(spacer())
            options.append(section(f"── {get_message(self.locale, 'worlds.section.ready')} ──"))
            options.append(spacer())
            # Owned standard worlds (hub-downloaded polished content) first,
            # then the player's own created worlds — both are library worlds
            # with an `id`, so they emit `w["id"]` and launch via the same
            # world-id path as the built-ins (cli instantiates a fresh run).
            for world in owned_standard:
                options.append(
                    (f"{world['display_name']}  —  {world['desc']}", world["id"])
                )
            for world in owned_created:
                options.append((world["display_name"], world["id"]))
            # Unstarted downloads are raw on-disk runs (no world identity yet)
            # — route through launch-existing on their dir.
            for g in unstarted:
                path_str = str(g["path"])
                options.append((g["display_name"], f"__ready__::{path_str}"))

        # M31: the home screen is four rows, so this list is where the rest of
        # the library lives. Authoring a world is no longer among them —
        # creation moved into build mode and external agents; what remains
        # here are the ways to *get* and *tend* worlds you did not write.
        m = lambda k: get_message(self.locale, k)  # noqa: E731 — local shorthand
        options.append(spacer())
        options.append(section(f"── {m('menu.section_world_lib')} ──"))
        options.append(spacer())
        options.append((m("menu.import_lore"), "__import_world__"))
        options.append((m("menu.hub_download"), "__hub_download__"))
        options.append((m("menu.hub_upload_world"), "__upload_world__"))
        options.append((m("menu.manage_world"), "__manage_world__"))
        options.append(spacer())
        options.append(section(f"── {m('menu.section_char_lib')} ──"))
        options.append(spacer())
        options.append((m("menu.soul_talk"), "__soul_talk__"))
        options.append((m("menu.import_soul"), "__import_soul__"))
        options.append((m("menu.soul_download"), "__soul_download__"))
        options.append((m("menu.hub_upload_soul"), "__upload_soul__"))
        options.append((m("menu.manage_char"), "__manage_char__"))

        library_actions = {
            "__import_world__": self._step_world_import_prompt,
            "__hub_download__": lambda: self._step_hub_download_prompt(kind="worlds"),
            "__upload_world__": lambda: self._start_hub_upload_flow("worlds"),
            "__manage_world__": self._step_manage_worlds,
            "__soul_talk__": self._start_soul_talk_flow,
            "__import_soul__": self._step_character_import_prompt,
            "__soul_download__": lambda: self._step_hub_download_prompt(kind="souls"),
            "__upload_soul__": lambda: self._start_hub_upload_flow("souls"),
            "__manage_char__": self._step_manage_souls,
        }

        def on_selected(value: str | None) -> None:
            if value is None:
                # Top-level picker: just dismiss; main launcher panel shows again.
                self._focus_menu_button(1)  # "start new run" button
                return
            action = library_actions.get(value)
            if action is not None:
                action()
                return
            if value.startswith("__ready__::"):
                path = Path(value.split("::", 1)[1])
                self._launch_existing_dir = path
                self._selected_player = None
                self._step_world_preview(
                    path,
                    on_play=lambda: self._step_choose_preset(continue_mode=False),
                    on_back=self._step_choose_world,
                )
                return
            self._selected_world_id = value
            self._step_choose_player()

        # First-time guidance: nudge new users toward the 🌟 flagship and
        # land focus on it explicitly (it is already listed first under
        # built-in, but initial_focus makes the recommended row the default
        # even if shelf ordering changes later).
        flagship_focus = "stoneford-elena" if any(
            v == "stoneford-elena" for _, v in options
        ) else None
        self.push_screen(
            ChoicePickerScreen(
                get_message(self.locale, "picker.choose_world"),
                options,
                hint=get_message(self.locale, "worlds.hint"),
                initial_focus=flagship_focus,
            ),
            on_selected,
        )

    # ------------------------------------------------------------------
    # World create / import — the launcher captures the intent here, and
    # the actual authoring is delegated to the relevant built-in skill
    # (`world-game-authoring` or `tavern-game-import`) once the TUI starts
    # inside the new game directory.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Soul create — the soul-side mirror of world create. Same shape:
    # capture a one-line description, then an agent_template, then an LLM
    # preset; stash the intent in `_custom_soul_intent` and let the
    # downstream build-mode TUI run the `soul-authoring` skill.
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_dropped_path(raw: str) -> str:
        """Normalize a path that may have been drag-dropped into the terminal.

        Terminals don't deliver real file-drop events to a TUI; they paste
        the file PATH as text. That path is often quoted ('/a/b c.png') or
        shell-escaped (/a/b\\ c.png) depending on the emulator. Strip one
        layer of surrounding quotes, unescape escaped spaces / shell-special
        chars (leaving Windows back-slash separators intact), and expand ~.
        """
        import re as _re
        from pathlib import Path as _P

        s = (raw or "").strip()
        if not s:
            return ""
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
            s = s[1:-1]
        else:
            # Only unescape backslash before a space / shell-special char,
            # so C:\Users\... on Windows is not mangled.
            s = _re.sub(r"\\([ ()\[\]'\"&;`$])", r"\1", s)
        s = s.strip()
        try:
            s = str(_P(s).expanduser())
        except Exception:
            pass
        return s

    def _step_world_import_prompt(self) -> None:
        self.push_screen(
            ImportScreen(locale=self.locale),
            callback=lambda result: self._after_world_import_prompt(result or ""),
        )

    def _after_world_import_prompt(self, path_or_content: str) -> None:
        path = self._resolve_import_input(path_or_content)
        if not path:
            # Cancelled / empty: import-lore launches straight from the main
            # menu, so return THERE — not into the world picker (the old
            # behavior, which read as a jump to an unrelated screen).
            self.call_later(self._return_to_main)
            return
        self._selected_world_id = "__wl_import__"
        self._custom_world_intent = {
            "action": "import",
            "skill": "tavern-game-import",
            "source_path": path,
        }
        self._step_choose_player()

    @staticmethod
    def _resolve_import_input(path_or_content: str) -> str:
        """If the input looks like a file path, return it. If it looks like
        JSON content, save to a temp file and return that path. Returns ''
        on empty input."""
        text = (path_or_content or "").strip()
        if not text:
            return ""
        # Check if it looks like a file path (exists on disk, or looks like
        # a path with slashes)
        import os
        if os.path.exists(text):
            return text
        # Check if it looks like JSON content (starts with {)
        if text.startswith("{"):
            import tempfile
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="wl-import-", delete=False,
                encoding="utf-8",
            )
            tmp.write(text)
            tmp.close()
            return tmp.name
        # Assume it's a path (drag-and-drop, etc.)
        return text

    def _step_choose_player(self) -> None:
        # Casting ② screen: two selections on ONE screen — the player's
        # 分身 (avatar, single-select incl. "就做我自己") on the left, and the
        # souls to bring INTO the world as NPCs (multi-select) on the right.
        # The avatar comes from the SEPARATE local avatar store (a soul cannot
        # be the protagonist); souls become NPCs via placement at launch.
        from neonrp.core import souls as _souls
        from neonrp import players as _players

        try:
            soul_entries = _souls.list_souls(locale=self.locale)
        except Exception:
            soul_entries = []
        try:
            avatar_entries = _players.list_avatars()
        except Exception:
            avatar_entries = []

        # Soul Talk needs a soul to talk to. If the library is EMPTY there is
        # nothing to bring in — don't drop the user into an empty casting
        # screen. Guide them to create/import a character first, then back to
        # the menu. (Soul Talk's world has no native souls of its own.)
        if self._selected_world_id == "soul-talk" and not soul_entries:
            # Nothing pushed → the user stays on the launcher menu, where the
            # 新建角色 / import-character buttons live (the guidance message
            # points them there).
            self.notify(
                get_message(self.locale, "soul_talk.empty_library"),
                severity="warning",
            )
            return

        world_mode = self._world_template_mode(self._selected_world_id)

        # Scene-aware (multi-agent only): the world ships its own souls + a
        # baked protagonist. Surface THOSE first — native souls marked +
        # on-stage ones pre-checked, the prior protagonist offered alongside
        # Default — with external library souls/avatars added on top. orch/fast
        # worlds have no playthrough → empty native cast → unchanged behaviour.
        wid = self._selected_world_id
        if world_mode == "multi-agent" and wid and not wid.startswith("__"):
            try:
                import importlib.resources as _res
                from neonrp.worlds import resolve_template
                from neonrp.core.placement import read_world_native_cast

                tpl = resolve_template(wid, self.locale)
                template_dir = Path(str(_res.files("neonrp") / "templates" / tpl))
                native = read_world_native_cast(template_dir, locale=self.locale)
                if native.get("souls"):
                    soul_entries = list(native["souls"]) + list(soul_entries)
                if native.get("avatar"):
                    avatar_entries = [native["avatar"], *avatar_entries]
            except Exception:
                pass

        def on_cast(result: dict | None) -> None:
            if result is None:
                # Back/cancel: Soul Talk launches straight from the main menu
                # (not the world picker), so return THERE; other worlds came
                # via the picker, so they go back to it.
                if self._selected_world_id == "soul-talk":
                    self.call_later(self._return_to_main)
                else:
                    self._step_choose_world()
                return
            # 分身 is now a lightweight avatar profile dict (or None for
            # 就做我自己) — merged into the world's player slot at launch.
            player = result.get("player")
            self._selected_player = player if isinstance(player, dict) and player else None
            bring_in = list(result.get("bring_in") or [])
            # Soul Talk is a 1:1 conversation — it MUST have at least one soul
            # to talk to (its world ships only a narrator orchestrator, no
            # native souls). Block launch with an empty cast and re-open the
            # casting screen so the user can pick. Other worlds are unaffected.
            if self._selected_world_id == "soul-talk" and not bring_in:
                self.notify(
                    get_message(self.locale, "soul_talk.need_soul"),
                    severity="warning",
                )
                self._step_choose_player()
                return
            self._bring_in_souls = bring_in
            # Mode is the world's baked property (read-only in casting).
            self._engine_mode = result.get("mode") or world_mode
            # Placement overrides from in-preview editing.
            self._npc_placements = result.get("placements") if isinstance(result.get("placements"), dict) else None
            # Location overrides from per-NPC location confirmation.
            self._npc_locations = result.get("npc_locations") if isinstance(result.get("npc_locations"), dict) else None
            self._step_choose_preset(continue_mode=False)

        self.push_screen(
            CastingScreen(
                title=get_message(self.locale, "picker.choose_character"),
                souls=soul_entries,
                avatars=avatar_entries,
                locale=self.locale,
                world_id=self._selected_world_id,
                world_mode=world_mode,
            ),
            on_cast,
        )

    @staticmethod
    def _world_template_mode(world_id: str | None) -> str:
        """Read a world's baked play mode from its template runtime_contract.
        Mode is a world property, not a per-session choice. Defaults to
        orchestrator (custom/unknown worlds have no template mode yet)."""
        if not world_id or world_id.startswith("__"):
            return "orchestrator"
        try:
            import importlib.resources as _res
            import json as _json

            from neonrp.worlds import resolve_template

            # staticmethod — no self; resolve the UI locale from config/env.
            tpl = resolve_template(world_id, resolve_locale())
            rc = Path(str(_res.files("neonrp") / "templates" / tpl / "runtime_contract.json"))
            if rc.is_file():
                mode = (
                    _json.loads(rc.read_text(encoding="utf-8"))
                    .get("router", {})
                    .get("execution_mode")
                )
                if mode == "fast":  # 旧模板契约,fast 已退役
                    mode = "orchestrator"
                if mode in ("orchestrator", "multi-agent"):
                    return mode
        except Exception:
            pass
        return "orchestrator"

    # ------------------------------------------------------------------
    # Character create / import — mirrors world create/import. The launcher
    # captures the intent; actual AI generation happens after preset selection
    # so we have an LLM to talk to.
    # ------------------------------------------------------------------

    def _step_character_import_prompt(self) -> None:
        self.push_screen(
            ImportScreen(locale=self.locale),
            callback=lambda result: self._after_character_import(result or ""),
        )

    def _after_character_import(self, path_or_content: str) -> None:
        path = self._resolve_import_input(path_or_content)
        if not path:
            # Cancelled the file picker — back to the main menu.
            self.call_later(self._return_to_main)
            return

        # Authoring the card into a RICH soul needs a real LLM — and the
        # launcher only has one via a chosen PRESET. (There is no effective/
        # session provider here like in-game; the default user config often
        # resolves to an unusable placeholder model.) So pick a model first;
        # finalize_launch's card-import branch then authors on that preset's
        # LLM behind a spinner.
        self._pending_card_import = path
        self._step_choose_preset(continue_mode=False)

    def _run_card_import_authoring(self, card_path: str, preset_id: str) -> None:
        """Author the pending card into the soul library using the LLM from the
        just-chosen PRESET. Runs on a worker behind the spinner; on success →
        a/b choice screen, on failure → notify + back to 角色库 (never blank)."""
        def _work() -> str:
            from neonrp.core.config import _parse_config, resolve_provider
            from neonrp.core.importers.card_to_soul import import_card_to_library
            from neonrp.core.llm import get_adapter_from_config
            from neonrp.presets import build_config_dict

            cfg = _parse_config(build_config_dict(preset_id))
            llm = get_adapter_from_config(resolve_provider(cfg))
            soul_dir = import_card_to_library(card_path, llm=llm)
            return f"OK\t{soul_dir}"

        self.push_screen(
            SpinnerWorkerScreen(
                get_message(self.locale, "import.authoring_title"),
                get_message(self.locale, "import.authoring_label"),
                _work,
            ),
            callback=self._after_character_import_worked,
        )

    def _after_character_import_worked(self, result: str | None) -> None:
        result = result or ""
        if result.startswith("OK\t"):
            from pathlib import Path as _P

            from neonrp.core.souls import read_soul_json

            soul_dir = _P(result[3:])
            meta = read_soul_json(soul_dir)
            soul_name = meta.name if meta is not None else ""
            # Success → let the user choose: play now, or back to library.
            self.push_screen(
                PostImportChoiceScreen(locale=self.locale, soul_name=soul_name),
                callback=self._after_import_choice,
            )
            return
        # Bad card or LLM failure — SpinnerWorkerScreen returns "✗ <err>".
        err = result.lstrip("✗").strip() or "?"
        try:
            self.notify(
                get_message(self.locale, "import.failed").replace("{err}", err),
                severity="error",
                timeout=8,
            )
        except Exception:
            pass
        self._step_manage_souls()

    def _after_import_choice(self, choice: str | None) -> None:
        if choice == "play":
            # The imported soul is now in the library; Soul Talk's cast step
            # lets the user pick it.
            self._start_soul_talk_flow()
        else:
            # "library" / dismissed — show the 角色库 so the new soul is visible.
            self._step_manage_souls()

    def _step_choose_preset(self, continue_mode: bool) -> None:
        if not self._presets:
            self.exit()
            return

        # On continue, peek at the saved game's config.json and move the
        # last-used preset to the top with a "✓ last used" marker so the
        # default-focused first option is a 1-key resume.
        last_preset_id: str | None = None
        if continue_mode and self._selected_game is not None:
            try:
                from neonrp.cli import read_worldlines_last_preset

                last_preset_id = read_worldlines_last_preset(self._selected_game)
            except Exception:
                last_preset_id = None

        ordered_presets: list[dict[str, Any]] = list(self._presets)
        if last_preset_id:
            last_entry = next((p for p in ordered_presets if p["id"] == last_preset_id), None)
            if last_entry is not None:
                ordered_presets.remove(last_entry)
                ordered_presets.insert(0, last_entry)

        custom_badge = get_message(self.locale, "preset.badge.custom")
        # Preset ids that should render dim — entry-level / experimental
        # options we don't actively recommend but still want discoverable.
        # `glm` (free tier) is the main case today.
        DIM_PRESET_IDS = {"glm"}

        options: list[tuple[str, str]] = []
        for preset in ordered_presets:
            label = preset["display"]
            if preset.get("from_user_config"):
                # Insert localized `[custom]` badge before any trailing ✓
                if label.endswith(" ✓"):
                    label = f"{label[:-2]} [{custom_badge}] ✓"
                else:
                    label = f"{label} [{custom_badge}]"
            if last_preset_id and preset["id"] == last_preset_id:
                label = f"{label}   ← last used"
            if preset["id"] in DIM_PRESET_IDS:
                label = f"[dim]{label}[/]"
            options.append((label, preset["id"]))
        # Tail entry so users discover they can wire up a Qwen / Ollama /
        # any OpenAI-compatible endpoint directly from the model picker.
        options.append((get_message(self.locale, "preset.add_custom"), "__add_custom__"))

        def finalize_launch(value: str) -> None:
            # Pending character-card import: don't launch a game — author the
            # card into the soul library using THIS preset's LLM, then offer
            # play-now / back-to-library. `value` is a real preset id here
            # (None / __add_custom__ are handled in on_selected above).
            if getattr(self, "_pending_card_import", None):
                card_path = self._pending_card_import
                self._pending_card_import = None
                self._run_card_import_authoring(card_path, value)
                return
            # Nothing to launch? Say so here, on screen, instead of exiting
            # into the CLI's「Nothing to launch — launcher bug」line (seen after
            # ~3 min in the launcher).
            if (
                not continue_mode
                and self._pending_create is None
                and self._pending_workshop is None
                and self._launch_existing_dir is None
                and not self._selected_world_id
                and self._custom_world_intent is None
                and self._custom_soul_intent is None
            ):
                self.notify(
                    "还没选世界 —— 先从「一览 · 游玩」或「新游戏」挑一个。"
                    if str(self.locale).startswith("zh")
                    else "No world picked yet — choose one from Browse or New Game first.",
                    severity="warning",
                )
                self._direct_surface = None
                self._focus_menu_button(self._menu_button_ids().index("wl-new"))
                return

            # Runtime mode decision:
            # - World create/import → build (agent needs free file writes to
            #                                scaffold the slice; not play)
            # - Everything else     → play (default gameplay loop)
            runtime_mode: AppMode
            if (not continue_mode) and (
                self._custom_world_intent is not None
                or self._custom_soul_intent is not None
            ):
                # Soul-create needs build mode for the same reason
                # world-create does: the authoring skill must write
                # files freely to seed the new folder.
                runtime_mode = "build"
            else:
                runtime_mode = "play"

            def build_and_exit(render_surface: str, play_after_build: bool = False) -> None:
                if continue_mode:
                    self.launch_selection = WorldLinesLaunchSelection(
                        mode="continue",
                        preset_id=value,
                        runtime_mode=runtime_mode,
                        game_path=self._selected_game,
                        render_surface=render_surface,
                    )
                elif self._launch_existing_dir is not None:
                    # Fresh WorldHub download / loaded .zip — dir exists on
                    # disk but the engine hasn't run a turn yet. Go through
                    # the new-game startup path so "开始游戏" gets injected.
                    self.launch_selection = WorldLinesLaunchSelection(
                        mode="launch_existing",
                        preset_id=value,
                        runtime_mode=runtime_mode,
                        game_path=self._launch_existing_dir,
                        player_profile=self._selected_player,
                        bring_in_souls=tuple(self._bring_in_souls),
                        render_surface=render_surface,
                    )
                else:
                    self.launch_selection = WorldLinesLaunchSelection(
                        mode="new",
                        preset_id=value,
                        runtime_mode=runtime_mode,
                        world_id=self._selected_world_id,
                        player_profile=self._selected_player,
                        world_intent=self._custom_world_intent,
                        soul_intent=self._custom_soul_intent,
                        bring_in_souls=tuple(self._bring_in_souls),
                        engine_mode=self._engine_mode,
                        npc_placements=self._npc_placements,
                        npc_locations=self._npc_locations,
                        render_surface=render_surface,
                        play_after_build=play_after_build,
                    )
                self.exit()

            # Dashboard direct flows: no more questions after the model.
            if self._pending_workshop is not None:
                soul_dir, sid = self._pending_workshop
                try:
                    from neonrp.core.souls import ensure_soul_workshop_project
                    from neonrp.worlds import seed_run_model

                    ensure_soul_workshop_project(soul_dir)
                    seed_run_model(soul_dir, value)
                except Exception as exc:  # noqa: BLE001
                    self.notify(f"{sid}: {exc}", severity="error")
                    self._pending_workshop = None
                    return
                self.launch_selection = WorldLinesLaunchSelection(
                    mode="continue",
                    preset_id=value,
                    runtime_mode="build",
                    game_path=soul_dir,
                    render_surface="tui",
                    startup_commands=(f"这是角色「{sid}」的文件夹,我们接着把它写完。先读一遍现有的 soul.json 和 persona,告诉我还缺什么。",),
                )
                self.exit()
                return
            if self._pending_create is not None:
                kind, name = self._pending_create
                try:
                    source = self._materialize_pending_create(value)
                except Exception as exc:
                    self.notify(f"{name}: {exc}", severity="error")
                    self._pending_create = None
                    return
                self.launch_selection = WorldLinesLaunchSelection(
                    mode="continue",
                    preset_id=value,
                    runtime_mode="build",
                    game_path=source,
                    render_surface="tui",
                    startup_commands=(self._create_brief(kind, name),),
                )
                self.exit()
                return
            if self._direct_surface:
                build_and_exit(self._direct_surface)
                return

            _zh = str(self.locale).startswith("zh")
            is_world_import = (
                not continue_mode
                and self._custom_world_intent is not None
                and self._custom_world_intent.get("action") == "import"
            )

            # World import ALWAYS authors the slice in the Builder first (the
            # deepseek agent runs `tavern-game-import` to read the card and
            # write a playable world). It must never drop straight into play
            # with the raw, un-authored card. Authoring in the Builder is the
            # default; play happens AFTER authoring via the play_after_build
            # relaunch.
            #
            # 「web 可以保留路径,但不在 tui 上推荐或显示」。
            # The browser is never offered here any more — `worldlines web`
            # stays as an explicit command for those who want it. There is
            # no「在哪里玩」question either: from the TUI you play in the TUI.
            if is_world_import:
                self.push_screen(
                    ChoicePickerScreen(
                        "导入卡 → 进 NeonRP Builder 用 AI 编写世界" if _zh
                        else "Import → author the world in the NeonRP Builder",
                        [
                            ("进 Builder 编写（默认）" if _zh else "Author in Builder (default)", "build"),
                            ("编写后直接玩" if _zh else "Author, then Play", "play_tui"),
                        ],
                        hint="AI 先在 Builder 里把卡编写成可玩世界；选「编写后直接玩」会在建好后自动开始游玩" if _zh
                        else "The agent authors the card into a playable world first; 'then Play' launches it once built",
                    ),
                    lambda v: (
                        # Back (Esc → None) returns to the preset/API picker —
                        # it must NOT fall through to a default and launch the
                        # game (WOR-21: "返回仍然进入游戏").
                        self._step_choose_preset(continue_mode) if v is None
                        else build_and_exit("tui", play_after_build=(v == "play_tui"))
                    ),
                )
            else:
                build_and_exit("tui")

        # Stash so other steps (setup wizard, custom-add) can call back in
        # without re-deriving the runtime-mode logic.
        self._pending_finalize_launch = finalize_launch

        def on_selected(value: str | None) -> None:
            if value is None:
                if self._pending_create is not None or self._pending_workshop is not None or self._direct_surface:
                    # A dashboard direct flow: Esc goes home, not into the
                    # casting screen it never showed.
                    self._pending_create = None
                    self._pending_workshop = None
                    self._direct_surface = None
                    self._focus_menu_button(0)
                elif continue_mode:
                    self._step_choose_saved_game()
                else:
                    self._step_choose_player()
                return

            if value == "__add_custom__":
                self._step_add_custom_provider(continue_mode)
                return

            # First-time use of a built-in PRESET (deepseek / openai /
            # anthropic / glm / openrouter / opus): if the API key isn't
            # already on file, route through the same model+key wizard
            # Settings uses, then auto-launch on save. Without this the
            # user picked the preset and got no chance to override the
            # model — which made model edits feel inconsistent with the
            # Settings flow that does ask.
            from neonrp.presets import PRESETS, _preset_key_available, get_provider_type

            if value in PRESETS and not _preset_key_available(value):
                if get_provider_type(value) is not None:
                    self._step_setup_preset(value, continue_mode)
                    return

            finalize_launch(value)

        # Default focus = the model you would actually want: the save's
        # last-used one, else the user's default.
        focus_id: str | None = last_preset_id
        if not focus_id:
            try:
                from neonrp.presets import default_model_ref

                focus_id = default_model_ref()
            except Exception:
                focus_id = None
        if focus_id and not any(v == focus_id for _, v in options):
            focus_id = None
        self.push_screen(
            ChoicePickerScreen(get_message(self.locale, "picker.choose_model"), options, initial_focus=focus_id),
            on_selected,
        )

    def _step_setup_preset(self, preset_id: str, continue_mode: bool) -> None:
        """Run the Settings model+key wizard for an unconfigured built-in preset.

        On done, refresh the cached preset list and auto-launch with the
        just-saved entry. On exit (user backed out mid-wizard), drop them
        back into the model picker rather than the Settings menu.
        """
        from neonrp.tui.settings_flow import SettingsFlow

        reopen_picker = lambda: (  # noqa: E731
            self._refresh_presets(),
            self._step_choose_preset(continue_mode),
        )

        def after_saved(entry_id: str) -> None:
            self._refresh_presets()
            finalize = getattr(self, "_pending_finalize_launch", None)
            if finalize is not None:
                finalize(entry_id)
            else:
                self._step_choose_preset(continue_mode)

        flow = SettingsFlow(host=self, on_exit=reopen_picker)
        flow._open_add_flow(preset_id, on_done=after_saved)

    def _step_add_custom_provider(self, continue_mode: bool) -> None:
        """Jump into the Settings custom-add wizard, return to picker on done."""
        from neonrp.presets import get_provider_type
        from neonrp.tui.settings_flow import SettingsFlow

        ptype = get_provider_type("custom")
        if ptype is None:
            self._step_choose_preset(continue_mode)
            return

        reopen_picker = lambda: (  # noqa: E731
            self._refresh_presets(),
            self._step_choose_preset(continue_mode),
        )

        def after_saved(_entry_id: str) -> None:
            reopen_picker()

        flow = SettingsFlow(host=self, on_exit=reopen_picker)
        flow._open_add_custom(ptype, on_done=after_saved)



class InputArea(Container):
    """Input area with inline Claude-style status metadata."""

    def __init__(self, mode: AppMode = "build", **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self.router_mode = "-"
        self.locale = "en"
        self.model_display = "-"
        self.world_time = "-"
        self.world_location = "-"
        self.connection_state = "discord:-"
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._prompt_visible = True
        self._prompt_timer = None
        self._run_status_text = ""
        self._run_active = False
        self._run_anim_frame = 0
        self._run_anim_timer = None

    _RUN_MIN_WIDTH = 24
    _RUN_BASE_COLOR = "#23282f"
    _RUN_GLOW_COLORS = ["#2a3038", "#313843", "#39414d", "#485363", "#39414d", "#313843", "#2a3038"]

    def compose(self) -> ComposeResult:
        """Compose the input area."""
        yield Static("", id="run-activity-line")
        # Live "thinking ticker" — a transient tail of the model's current
        # reasoning, refreshed in place under the run-status line. Never
        # persists: cleared the moment the thinking segment ends.
        yield Static("", id="thinking-ticker")
        yield Static("", id="slash-suggestions")
        with Horizontal(id="input-row"):
            yield Static(">", id="input-prompt", classes="input-prompt-on")
            yield ImeInput(
                placeholder=get_message(self.locale, "input_hint"),
                id="message-input",
                suggester=SlashCommandSuggester(),
            )
        with Vertical(id="input-status-block"):
            with Horizontal(classes="input-status-row"):
                yield Static("", id="input-status-top-left")
                yield Static("", id="input-status-top-center")
                yield Static("", id="input-status-top-right")
            with Horizontal(classes="input-status-row"):
                yield Static("", id="input-status-bottom-left")
                yield Static("", id="input-status-bottom-center")
                yield Static("", id="input-status-bottom-right")

    def on_mount(self) -> None:
        self._render_run_activity()
        self._prompt_timer = self.set_interval(0.55, self._tick_prompt_indicator)
        self._render_input_placeholder()
        self._render_status_line()

    def set_mode(self, mode: AppMode) -> None:
        """Update mode metadata."""
        self.mode = mode
        self._render_status_line()

    def set_locale(self, locale: str) -> None:
        """Update UI locale for inline input copy."""
        self.locale = resolve_locale(locale)
        self._render_input_placeholder()
        self._render_status_line()

    def update_status(
        self,
        *,
        mode: AppMode | None = None,
        router_mode: str | None = None,
        model_display: str | None = None,
        world_time: str | None = None,
        world_location: str | None = None,
        connection_state: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        """Update inline status metadata shown under the input."""
        if mode is not None:
            self.mode = mode
        if router_mode is not None:
            self.router_mode = router_mode or "-"
        if model_display is not None:
            self.model_display = model_display or "-"
        if world_time is not None:
            self.world_time = world_time or "-"
        if world_location is not None:
            self.world_location = world_location or "-"
        if connection_state is not None:
            self.connection_state = connection_state or "-"
        if prompt_tokens is not None:
            self.prompt_tokens = max(0, int(prompt_tokens))
        if completion_tokens is not None:
            self.completion_tokens = max(0, int(completion_tokens))
        self._render_status_line()

    def _tick_prompt_indicator(self) -> None:
        self._prompt_visible = not self._prompt_visible
        try:
            prompt = self.query_one("#input-prompt", Static)
        except Exception:
            return
        # The caret is the most-looked-at pixel on the screen, so it carries
        # the mode colour: you never have to read the status line to know
        # whether what you type edits the world or plays it.
        accent = mode_accent(self.mode, dim=not self._prompt_visible)
        prompt.update(f"[bold {accent}]>[/]")

    def _render_input_placeholder(self) -> None:
        try:
            input_widget = self.query_one("#message-input", Input)
        except Exception:
            return
        input_widget.placeholder = get_message(self.locale, "input_hint")

    def _render_status_line(self) -> None:
        try:
            top_left, top_center, top_right, bottom_left, bottom_center, bottom_right = self._build_status_segments()
            # Colour the mode word itself; the segment text stays plain so
            # `_build_status_text` remains a readable snapshot for tests.
            mode_word = localize_mode(self.locale, self.mode or "build")
            if top_left.startswith(mode_word):
                accent = mode_accent(self.mode)
                top_left = f"[bold {accent}]{mode_word}[/]" + top_left[len(mode_word):]
            self.query_one("#input-status-top-left", Static).update(top_left)
            self.query_one("#input-status-top-center", Static).update(top_center)
            self.query_one("#input-status-top-right", Static).update(top_right)
            self.query_one("#input-status-bottom-left", Static).update(bottom_left)
            self.query_one("#input-status-bottom-center", Static).update(bottom_center)
            self.query_one("#input-status-bottom-right", Static).update(bottom_right)
        except Exception:
            pass

    @staticmethod
    def _format_compact_count(value: int) -> str:
        if value < 1000:
            return str(value)
        if value < 10_000:
            return f"{value / 1000:.1f}k".rstrip("0").rstrip(".")
        return f"{value // 1000}k"

    def _build_status_segments(self) -> tuple[str, str, str, str, str, str]:
        prompt = self._format_compact_count(self.prompt_tokens)
        completion = self._format_compact_count(self.completion_tokens)
        top_left = f"{localize_mode(self.locale, self.mode or 'build')} · {self.router_mode or '-'}"
        top_center = self.model_display or "-"
        top_right = f"{self.connection_state or '-'} · ↑{prompt} ↓{completion}"
        bottom_left = self.world_time or "-"
        bottom_center = self.world_location or "-"
        bottom_right = ""
        return top_left, top_center, top_right, bottom_left, bottom_center, bottom_right

    def _build_status_text(self) -> str:
        """Return a plain-text snapshot useful for tests/debugging."""
        return "\n".join(" | ".join(part for part in row if part) for row in [self._build_status_segments()[:3], self._build_status_segments()[3:]])

    def set_run_status(self, text: str) -> None:
        """Enable fixed-height input activity animation while waiting."""
        self._run_status_text = text
        self._run_active = True
        if self._run_anim_timer is None:
            self._run_anim_timer = self.set_interval(0.07, self._tick_run_activity)
        self._render_run_activity()

    def clear_run_status(self) -> None:
        """Disable input activity animation."""
        self._run_status_text = ""
        self._run_active = False
        if self._run_anim_timer is not None:
            try:
                self._run_anim_timer.stop()
            except Exception:
                pass
            self._run_anim_timer = None
        self._render_run_activity()
        self.clear_thinking_ticker()

    def set_thinking_ticker(self, text: str) -> None:
        """Show the live thinking tail under the run-status line.

        Transient: the host pushes a fresh tail each render tick and
        clears it when the thinking segment ends — it never lands in the
        transcript."""
        try:
            line = self.query_one("#thinking-ticker", Static)
        except Exception:
            return
        text = (text or "").strip()
        if not text:
            line.display = False
            line.update("")
            return
        line.display = True
        line.update(Text(f"  ⟫ {text}", style="dim italic #6f9a82"))

    def clear_thinking_ticker(self) -> None:
        """Hide the live thinking ticker."""
        self.set_thinking_ticker("")

    def _tick_run_activity(self) -> None:
        if not self._run_active:
            return
        width = self._current_run_line_width()
        self._run_anim_frame = (self._run_anim_frame + 1) % width
        self._render_run_activity()

    def _current_run_line_width(self) -> int:
        width = 0
        try:
            line = self.query_one("#run-activity-line", Static)
            width = int(getattr(line.size, "width", 0) or 0)
        except Exception:
            width = 0
        if width <= 0:
            width = int(getattr(self.size, "width", 0) or 0)
        if width <= 0:
            width = int(getattr(getattr(self.app, "size", None), "width", 0) or 0) - 2
        return max(self._RUN_MIN_WIDTH, width)

    def _render_run_activity(self) -> None:
        try:
            line = self.query_one("#run-activity-line", Static)
        except Exception:
            return
        width = self._current_run_line_width()
        if not self._run_active:
            line.display = False
            line.update("")
            return
        line.display = True

        # Overlay the status text at the start of the glow bar so the
        # user actually sees *what* is happening, not just a pulsing line.
        status_text = str(self._run_status_text or "").strip()
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"][self._run_anim_frame % 10]
        if status_text:
            label = f" {spinner}  {status_text}   "
        else:
            label = f" {spinner}  "
        label_len = len(label)

        chars: list[str] = []
        color_by_pos: list[str] = []
        for i, ch in enumerate(label):
            chars.append(ch)
            color_by_pos.append("#E4E4E7" if ch != " " else self._RUN_BASE_COLOR)

        # Fill the remaining width with the existing glow bar.
        remaining = max(0, width - label_len)
        bar_chars = ["─"] * remaining
        bar_colors = [self._RUN_BASE_COLOR] * remaining
        trail_len = len(self._RUN_GLOW_COLORS)
        if remaining > 0:
            start = self._run_anim_frame % remaining
            for i, color in enumerate(self._RUN_GLOW_COLORS):
                pos = (start + i) % remaining
                bar_colors[pos] = color
                if 2 <= i <= trail_len - 3:
                    bar_chars[pos] = "━"
        chars.extend(bar_chars)
        color_by_pos.extend(bar_colors)

        # Render as compact color runs for better performance/readability.
        runs: list[tuple[str, str]] = []
        run_color = color_by_pos[0]
        run_text = chars[0]
        for i in range(1, len(chars)):
            if color_by_pos[i] == run_color:
                run_text += chars[i]
            else:
                runs.append((run_color, run_text))
                run_color = color_by_pos[i]
                run_text = chars[i]
        runs.append((run_color, run_text))

        markup = "".join(f"[{color}]{text}[/]" for color, text in runs)
        line.update(markup)


class SlashCommandSuggester(Suggester):
    """Inline ghost-text suggester for slash commands."""

    def __init__(self) -> None:
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        if not value.startswith("/"):
            return None
        command_text = value[1:]
        if not command_text:
            return None

        parts = command_text.split()
        if not parts:
            return None  # "/ " — nothing typed yet (this crashed)
        has_trailing_space = value.endswith(" ")
        cmd_name = parts[0]
        spec = COMMANDS.get(cmd_name, {})
        has_subcommands = isinstance(spec.get("subcommands"), list)

        # Partial command name → suggest full command + args hint
        if cmd_name not in COMMANDS and not has_trailing_space and len(parts) == 1:
            matches = get_command_suggestions(cmd_name)
            if matches:
                best = matches[0]
                best_spec = COMMANDS.get(best, {})
                hint = _args_hint(best, best_spec)
                return f"/{best} {hint}" if hint else f"/{best}"
            return None

        # Complete command, user just added space → show args hint
        if cmd_name in COMMANDS and has_trailing_space and len(parts) == 1:
            if has_subcommands:
                subs = spec["subcommands"]
                return f"{value}{subs[0]}"
            hint = _args_hint(cmd_name, spec)
            if hint:
                return f"{value}{hint}"
            return None

        # Typing subcommand → suggest full subcommand + its args hint
        if has_subcommands and len(parts) == 2 and not has_trailing_space:
            sub_prefix = parts[1]
            subs = get_subcommand_suggestions(cmd_name, sub_prefix)
            if subs:
                sub_hint = spec.get("sub_args_hint", {}).get(subs[0], "")
                suffix = f" {sub_hint}" if sub_hint else ""
                return f"/{cmd_name} {subs[0]}{suffix}"
            return None

        # Subcommand complete with trailing space → show sub args hint
        if has_subcommands and len(parts) == 2 and has_trailing_space:
            sub_name = parts[1]
            sub_hint = spec.get("sub_args_hint", {}).get(sub_name, "")
            if sub_hint:
                return f"{value}{sub_hint}"
            return None

        return None


def _args_hint(cmd_name: str, spec: dict, locale: str | None = None) -> str:
    """Return placeholder hint for a command's expected arguments (UI language)."""
    if locale is None:
        try:
            from neonrp.tui.i18n import resolve_locale

            locale = resolve_locale()
        except Exception:  # noqa: BLE001
            locale = None
    if locale and cmd_name in COMMANDS:
        spec = localized_spec(cmd_name, locale) or spec
    return get_command_args_hint(cmd_name, spec)


class NeonRPApp(App):
    """NeonRP conversational TUI ."""

    CSS = """
    Screen {
        layout: vertical;
        padding: 0;
    }

    /* M18 Phase E1 — per-character status lane. Auto height so it
       occupies zero rows when there are no live characters (legacy
       single-agent path), keeping the original layout untouched. */
    CharacterStatusLane {
        height: auto;
        max-height: 12;
        width: 1fr;
        padding: 0 1;
        color: #9BE89B;
        background: $surface-darken-1;
        border-top: solid #1f3a29;
        overflow-y: auto;
        /* A thin rail is the only hint that the lane holds more souls than
           its 12-row cap shows. */
        scrollbar-size-vertical: 1;
    }

    /* Play visual-novel stack. In build/sandbox this container is
       never composed, so these rules are inert there. Vertical: a wide
       scene-image band on top, the location scene-card, a control row,
       then the transcript fills the rest. */
    /* M31: the transcript moved OUT of the play stage (it is shared with
       build and must never be reparented), so the stage is now just the
       furniture and takes only the height it needs. The visual stacking is
       unchanged: band → location card → controls → transcript fills the rest. */
    #play-stage {
        width: 1fr;
        height: auto;
        layout: vertical;
    }

    ConversationView {
        width: 1fr;
        height: 1fr;
    }

    #conv-row {
        width: 100%;
        height: 1fr;
    }

    /* a character elsewhere = a folded notice; click opens her whole line, click again folds it */
    Collapsible.away-fold {
        height: auto;
        border: none;
        padding: 0 0 0 1;
        margin: 0;
        background: transparent;
    }
    Collapsible.away-fold > CollapsibleTitle {
        color: #94a3b8;
        padding: 0;
    }
    Collapsible.away-fold > CollapsibleTitle:hover {
        color: #e2e8f0;
        background: #1f2937;
    }
    Collapsible.away-fold > Contents {
        padding: 0 0 0 3;
    }

    /* Build-side furniture: narrow tree, wide reader. A terminal is wider
       than it is tall, so the split is vertical — and the conversation below
       keeps every row it can. */
    #build-stage {
        width: 1fr;
        /* Proportional, not fixed: a fixed 20 rows leaves nothing for the
           conversation on an 80x24 terminal, and the conversation is still
           where the work happens. */
        height: 40%;
        max-height: 24;
        layout: horizontal;
        border-bottom: solid #1f3a29;
    }

    #world-tree {
        width: 34;
        height: 100%;
        background: #070b08;
        color: #9BE89B;
        border-right: solid #1f3a29;
        overflow-y: auto;
        scrollbar-size-vertical: 1;
    }

    #doc-reader {
        width: 1fr;
        height: 100%;
        layout: vertical;
        padding: 0 1;
        background: #090d0a;
        overflow-y: auto;
        scrollbar-size-vertical: 1;
    }

    #doc-reader-title {
        height: auto;
        color: #ff4757;
        text-style: bold;
    }

    #doc-reader-md, #doc-reader-text {
        height: auto;
        color: #d8d2c0;
    }

    #stage-top {
        width: 100%;
        height: 20;
        /* On a short terminal the band yields rows to the transcript instead
           of pushing it off the screen (the tab row above it costs one). */
        /* was `max-height: 50%` — percent-of-parent made
           the parent count 20 rows while rendering 12, leaving an 8-row
           blank band under the controls. vh resolves the same both ways. */
        max-height: 45vh;
        layout: horizontal;
    }

    /* 任务 A1: three tabs over the play stage. Switching a
       tab swaps the whole content block below it; the transcript and the
       input line are never re-mounted, only shown or hidden. */
    /* One row, no border: a border on a 1-row container leaves a 0-row
       content area and the tab buttons are never laid out (headless probe:
       get_widget_at hit the Horizontal, never the Button). */
    #play-tabs {
        height: 1;
        width: 100%;
        background: #070b08;
    }

    .play-tab {
        height: 1;
        min-width: 12;
        margin: 0 1 0 0;
        border: none;
        padding: 0 1;
        background: #0d1a12;
        color: #7f9a86;
        text-style: none;
    }

    .play-tab:hover, .play-tab:focus {
        background: #14301f;
        color: #b9ffd0;
    }

    .play-tab.active {
        background: #14301f;
        color: #18FF82;
        text-style: bold;
    }

    #play-tab-chat {
        width: 100%;
        height: auto;
        layout: vertical;
    }

    #play-tab-image {
        width: 100%;
        height: 1fr;
        layout: vertical;
    }

    #scene-panel {
        width: 100%;
        height: 1fr;
        padding: 1 1 0 1;
        background: #070b08;
        color: #9BE89B;
        content-align: center middle;
        overflow: hidden;
    }

    #scene-controls {
        height: 1;
        width: 100%;
        background: #0d1a12;
        align: left middle;
    }

    #play-tab-map {
        width: 100%;
        height: 1fr;
    }

    #play-stage.tab-wide {
        height: 1fr;
    }

    PortraitPanel,
    #portrait-panel {
        width: 1fr;
        height: 100%;
        padding: 1 1 0 1;
        background: #070b08;
        color: #9BE89B;
        content-align: center middle;
        overflow: hidden;
    }

    #game-state-side, #game-state-side-2 {
        width: 38;
        height: 100%;
        background: #090d0a;
        border-left: solid #1f3a29;
    }

    #scene-band { width: 100%; height: 1fr; }
    #scene-panel { width: 1fr; height: 100%; }
    #game-state-scroll-2 {
        width: 100%;
        height: 1fr;
        background: #090d0a;
        overflow-y: scroll;
        overflow-x: hidden;
        scrollbar-size-vertical: 2;
        scrollbar-background: #0d1710;
        scrollbar-color: #1f3a29;
    }
    #game-state-panel-2 { width: 100%; height: auto; padding: 0 1 0 1; background: #090d0a; color: #d8d2c0; }
    #side-map { width: 100%; height: 1fr; display: none; }
    .side-toggle { color: #18FF82; text-style: bold; }

    #game-state-scroll {
        width: 100%;
        height: 1fr;
        background: #090d0a;
        overflow-y: scroll;
        overflow-x: hidden;
        scrollbar-size-vertical: 2;
        scrollbar-background: #0d1710;
        scrollbar-color: #1f3a29;
        scrollbar-color-hover: #18FF82;
        scrollbar-color-active: #18FF82;
    }

    #game-state-panel {
        width: 100%;
        height: auto;
        padding: 0 1 0 1;
        background: #090d0a;
        color: #d8d2c0;
    }

    .state-scroll-btn {
        width: 100%;
        height: 1;
        min-width: 0;
        border: none;
        padding: 0;
        margin: 0;
        background: #0d1710;
        color: #5b8a6e;
        text-style: none;
        content-align: center middle;
    }

    .state-scroll-btn:hover {
        color: #18FF82;
        background: #14361f;
    }

    #location-header {
        height: auto;
        width: 100%;
        padding: 0 1;
        background: #070b08;
        color: #18FF82;
        border-bottom: solid #1f3a29;
    }

    #play-controls {
        height: 1;
        width: 100%;
        background: #0d1a12;
        align: left middle;
    }

    .play-ctl-btn {
        height: 1;
        min-width: 18;
        margin: 0 1 0 0;
        border: none;
        background: #14301f;
        color: #18FF82;
        text-style: bold;
        padding: 0 1;
    }

    .play-ctl-btn:focus {
        background: #1d4a30;
        color: #b9ffd0;
        text-style: bold;
    }

    .play-ctl-btn:hover {
        background: #1d4a30;
        color: #b9ffd0;
        text-style: bold;
    }

    /* Cohesive VN theme — scoped to the play split only, so build
       and sandbox transcripts are visually untouched. Accents the
       speaker name plate and warms the in-character narrative. */
    #play-stage ConversationView .msg-header.msg-assistant {
        color: #18FF82;
        text-style: bold;
    }

    #play-stage ConversationView .semantic-narrative-line {
        color: #d8d2c0;
    }

    #play-stage ConversationView .msg-divider {
        color: #1f3a29;
    }

    ConversationView {
        height: 1fr;
        border: none;
        padding: 1 2 0 2;
        layout: vertical;
        overflow-y: auto;
        overflow-x: hidden;
    }

    ConversationView .msg-header {
        margin: 0 0 0 0;
        color: $text-muted;
    }

    ConversationView .msg-user {
        color: $text;
    }

    ConversationView .msg-header.msg-user {
        color: $text;
    }

    ConversationView .msg-assistant {
        color: $text;
    }

    ConversationView .msg-header.msg-assistant {
        color: #4ADE80;
    }

    ConversationView .msg-tool {
        color: #8a919b;
    }

    ConversationView .msg-system {
        color: $text-muted;
    }

    ConversationView .msg-thinking {
        color: #b18a53;
    }

    ConversationView .thinking-row {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        align: left top;
    }

    ConversationView .thinking-label {
        width: auto;
        color: #b18a53;
    }

    ConversationView .thinking-content {
        width: 1fr;
        height: auto;
        color: #a9b0b9;
    }

    ConversationView .msg-body {
        width: 1fr;
        height: auto;
        margin: 0;
    }

    /* L14.5 semantic footer: compact chip list shown under narrative in play. */
    ConversationView .msg-semantic-footer {
        width: 1fr;
        height: auto;
        margin: 0 2 1 2;
        padding: 0 1;
        background: transparent;
        color: #a1a1aa;
    }

    /* L14.5 layer toggle (Ctrl+L cycles layer-1 → layer-2 → layer-3).
       layer-1: narrative only
       layer-2: + semantic footer (state_update / rule_check chips)
       layer-3: + tool calls + execution details + thinking
       Default (no class) == layer-2. */
    ConversationView.layer-1 .msg-semantic-footer,
    ConversationView.layer-1 .msg-tool,
    ConversationView.layer-1 .tool-collapsible,
    ConversationView.layer-1 .execution-live,
    ConversationView.layer-1 .execution-fold,
    ConversationView.layer-1 .execution-summary,
    ConversationView.layer-1 .assistant-activity-line {
        display: none;
    }

    ConversationView.layer-2 .msg-tool,
    ConversationView.layer-2 .tool-collapsible,
    ConversationView.layer-2 .execution-live,
    ConversationView.layer-2 .execution-fold,
    ConversationView.layer-2 .execution-summary,
    ConversationView.layer-2 .assistant-activity-line {
        display: none;
    }

    ConversationView .code-block {
        width: 1fr;
        height: auto;
        margin: 0 2 1 2;
        padding: 0 1;
        border: none;
        background: transparent;
        layout: vertical;
    }

    ConversationView .code-lang {
        width: 1fr;
        height: auto;
        color: $success;
    }

    ConversationView .code-body {
        width: 1fr;
        height: auto;
        margin: 0;
    }

    ConversationView .tool-collapsible {
        width: 1fr;
        margin: 0 0 1 0;
        padding: 0;
        border: none;
        background: transparent;
    }

    ConversationView .tool-collapsible > Contents {
        padding: 0 0 0 1;
    }

    ConversationView .execution-live {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        color: #8a919b;
    }

    ConversationView .execution-summary {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        color: #8a919b;
    }

    ConversationView .assistant-activity-line {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        color: #94A3B8;
    }

    ConversationView .semantic-scene-header {
        color: #34D399;
        margin: 0 0 1 0;
    }

    ConversationView .semantic-markdown-heading {
        color: #4ADE80;
        margin: 0 0 1 0;
    }

    ConversationView .semantic-agent-tag {
        color: #5BE0B0;
    }

    ConversationView .semantic-state-update {
        color: #86efac;
    }

    ConversationView .semantic-awaiting {
        color: #fcd34d;
    }

    ConversationView .semantic-inner {
        color: #9BE89B;
    }

    ConversationView .semantic-choice-line {
        color: #f5f5f5;
        margin: 0 0 0 2;
    }

    ConversationView .semantic-player-line {
        color: #e4e4e7;
    }

    ConversationView .semantic-narrative-line {
        color: #d8d2c0;
    }

    ConversationView .semantic-dice-line {
        width: auto;
        margin: 1 0;
        padding: 0 2;
        background: #1a160e;
        border-left: thick #e8a33d;
    }

    ConversationView .agent-error-callout {
        width: 1fr;
        padding: 0 2;
        background: #1c1409;
        border-left: thick #e0a64a;
    }

    ConversationView .agent-error-head {
        margin-top: 1;
    }

    ConversationView .agent-error-body {
        margin-bottom: 0;
    }

    ConversationView .agent-error-actions {
        width: auto;
        height: 1;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    ConversationView .agent-error-btn {
        height: 1;
        min-width: 12;
        margin: 0 1 0 0;
        border: none;
        background: #2a2010;
        color: #e0a64a;
        padding: 0 1;
    }

    ConversationView .agent-error-btn:focus {
        background: #3a2c14;
        color: #f5c542;
        text-style: bold;
    }

    ConversationView .msg-spacer {
        height: 1;
    }

    ConversationView .msg-divider {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        color: #3F3F46;
    }

    AskUserInlinePanel {
        display: none;
        width: 1fr;
        height: auto;
        max-height: 50%;
        overflow-y: auto;
        overflow-x: hidden;
        border: solid #34414f;
        padding: 0 1;
        margin: 0;
        layout: vertical;
        background: #10151b;
    }

    AskUserInlinePanel.visible {
        display: block;
    }

    /* Compact mode — keeps the header (question + toggle button) but hides
     * options / input / hint so the transcript reclaims the screen while
     * the prompt is still pending. */
    AskUserInlinePanel.minimized #ask-inline-options-scroll,
    AskUserInlinePanel.minimized #ask-inline-input,
    AskUserInlinePanel.minimized #ask-inline-actions {
        display: none;
    }

    #ask-inline-header {
        width: 1fr;
        height: auto;
        align: left middle;
    }

    #ask-inline-question {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        color: #d4d8dd;
    }

    AskUserInlinePanel.minimized #ask-inline-question {
        margin: 0;
    }

    #ask-inline-minimize {
        width: 3;
        min-width: 3;
        height: 1;
        margin: 0 0 0 1;
        padding: 0;
        background: #18212b;
        border: solid #2e3b49;
        color: #c5ccd4;
    }

    #ask-inline-minimize:hover {
        background: #223042;
        border: solid #4a6780;
        color: #e5edf6;
    }

    #ask-inline-options-scroll {
        width: 1fr;
        height: auto;
        min-height: 1;
        max-height: 14;
        overflow-y: scroll;
        margin: 0 0 1 0;
    }

    #ask-inline-options {
        height: auto;
        padding: 0 0 0 0;
    }

    #ask-inline-options Button {
        width: 1fr;
        height: auto;
        min-height: 1;
        margin: 0;
        background: #18212b;
        border: solid #2e3b49;
        color: #c5ccd4;
    }

    #ask-inline-options Button:hover {
        background: #223042;
        border: solid #4a6780;
        color: #e5edf6;
        text-style: bold;
    }

    #ask-inline-options Button:focus {
        background: #223042;
        border: solid #5c83a3;
        color: #f0f5fa;
        text-style: bold;
    }

    #ask-inline-input {
        width: 1fr;
        margin: 0;
    }

    #ask-inline-actions {
        width: 1fr;
        height: auto;
        align: left middle;
        margin: 0;
    }

    #ask-inline-hint {
        width: 1fr;
        color: #7f8995;
    }

    InputArea {
        width: 1fr;
        height: auto;
        min-height: 3;
        border-top: solid #2a2f36;
        padding: 0 2 1 2;
        layout: vertical;
    }

    InputArea.ask-user-active {
        height: 0;
        min-height: 0;
        padding: 0;
    }

    InputArea.ask-user-active #run-activity-line {
        display: none;
    }

    InputArea.ask-user-active #slash-suggestions {
        display: none;
    }

    InputArea.ask-user-active Horizontal {
        display: none;
    }

    InputArea.ask-user-active #input-status-block {
        display: none;
    }

    #slash-suggestions {
        display: none;
        width: 1fr;
        border: round $primary-darken-1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        max-height: 14;
    }

    #slash-suggestions.visible {
        display: block;
    }

    #run-activity-line {
        display: block;
        width: 1fr;
        height: 1;
        align: left middle;
        margin: 0 0 1 0;
    }

    #thinking-ticker {
        display: none;
        width: 1fr;
        height: auto;
        max-height: 2;
        overflow: hidden;
        margin: 0 0 1 0;
    }

    InputArea.ask-user-active #thinking-ticker {
        display: none;
    }

    InputArea Horizontal {
        width: 1fr;
        height: auto;
        margin: 0;
        align: left middle;
    }

    #input-row {
        height: auto;
    }

    #input-status-block {
        width: 1fr;
        height: auto;
        margin: 0;
        padding: 0 0 0 2;
    }

    .input-status-row {
        width: 1fr;
        height: auto;
        align: left middle;
    }

    #input-status-top-left,
    #input-status-bottom-left {
        width: 1fr;
        color: #7f8995;
        text-align: left;
    }

    #input-status-top-center,
    #input-status-bottom-center {
        width: 1fr;
        color: #7f8995;
        text-align: center;
    }

    #input-status-top-right,
    #input-status-bottom-right {
        width: 1fr;
        color: #7f8995;
        text-align: right;
    }

    #input-prompt {
        width: 2;
        color: #2ed573;
        text-style: bold;
        content-align: left middle;
    }

    .input-prompt-on {
        color: #2ed573;
    }

    .input-prompt-off {
        color: #173b23;
    }

    InputArea Input {
        width: 1fr;
        margin: 0;
        background: transparent;
        border: none;
        color: #d8dee9;
    }

    #message-input {
        background: transparent;
        border: none;
        color: #d8dee9;
        padding: 0;
    }

    InputArea Input:disabled {
        color: #6e7682;
    }

    .bg-blue {
        background: $primary;
        color: $text;
    }

    .bg-yellow {
        background: $warning;
        color: $text;
    }

    .bg-green {
        background: $success;
        color: $text;
    }

    .bg-magenta {
        background: #a855f7;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+q", "safe_quit", "Quit"),
        Binding("ctrl+k", "command_palette", "Commands"),
        Binding("ctrl+p", "command_palette", "Commands"),
        Binding("ctrl+l", "cycle_layer", "Cycle L1/L2/L3"),
        Binding("ctrl+backslash", "toggle_ask_user_minimize", "Min/expand ask_user"),
        Binding("f6", "copy_transcript", "Copy"),
        # M18 Phase E2 — cancel the focused character-agent. Wired straight
        # to the committed world_agent.interrupt(sid) primitive; this
        # binding adds NO new cancel mechanism of its own.
        Binding("ctrl+x", "cancel_character", "Cancel character"),
    ] + ([Binding("f12", "show_debug", "Debug")] if DEBUG_ENABLED else [])
    _CALLING_CHUNK_RE = re.compile(r"^\s*\[calling\s+([^\]]+?)\.\.\.\]\s*$", re.IGNORECASE)
    _TOOL_NAME_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:\.-]*$")
    _TOOL_CALL_FUNC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_:\.-]*)\s*\(")
    _SUB_AGENT_TAG_RE = re.compile(r"^\[\[subagent:([^\]]+)\]\](.*)$", re.DOTALL)
    _TOKEN_SPLIT_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
    _MAX_VISIBLE_SLASH_SUGGESTIONS = 10

    def __init__(
        self,
        root: Path | None = None,
        branch: str | None = None,
        provider: str | None = None,
        continue_session: bool = False,
        startup_commands: list[str] | None = None,
        verbose: bool = False,
        mode: AppMode = "build",
    ):
        super().__init__()
        self.root = root or Path.cwd()
        # A character workshop (soul.json at the root) is a project of its own;
        # folders made before 2026-09-11 lack the manifest the engine checks.
        try:
            from neonrp.core.souls import ensure_soul_workshop_project, is_soul_workshop

            if is_soul_workshop(self.root):
                ensure_soul_workshop_project(self.root)
        except Exception:
            pass
        # 任务 B3: the world's own play actions become `/` commands for this
        # session (root never changes for an app instance, so once is enough).
        try:
            from neonrp.tui.commands import load_world_actions, register_world_actions

            register_world_actions(load_world_actions(self.root))
        except Exception:
            pass
        # `/open` 换世界时填上,退出后由 run_tui 接手(见 _ReopenRequest)。
        self.reopen_request: _ReopenRequest | None = None
        self.branch = branch
        self.provider = provider
        self.continue_session = continue_session
        self.startup_commands = list(startup_commands or [])
        self.verbose = verbose
        self.mode: AppMode = mode
        self.ui_locale = "en"
        # External bridge hub (Discord / Telegram / future adapters). Starts
        # empty; launcher or /bridge command attaches bridges when enabled.
        # None until `_ensure_bridge_hub()` lazily creates it — keeps cost
        # at zero for users who don't use external bridges.
        self._bridge_hub: Any = None  # BridgeHub | None
        self.session: ConversationSession | None = None
        self.skill_loader = SkillLoader(self.root)
        self.auto_apply = get_auto_apply(self.root)
        self._pending_proposal: dict[str, Any] | None = None
        self._current_run_result: ConversationTurnResult | None = None
        self._provider_notice_shown = False
        self._stream_started = False
        self._subagent_stream_seen: set[str] = set()
        self._last_user_input = ""
        self._est_prompt_tokens_total = 0
        self._est_completion_tokens_total = 0
        self._active_send_thread: threading.Thread | None = None
        # When a turn is paused on ask_user, this holds the panel's submit
        # callback so that typed input (from the main TUI input OR a Discord
        # bridge inbound) can answer the prompt instead of bouncing off the
        # "A request is already running" guard. Cleared the moment we hand
        # the text back to the blocked worker thread.
        self._active_ask_user_submit: Callable[[str], None] | None = None
        self._slash_suggestions: list[tuple[str, str]] = []
        self._slash_selected_index = 0
        self._suppress_input_change = False
        self._input_history: list[str] = []
        self._history_index: int | None = None
        self._history_draft = ""
        self._verbose_log_path: Path | None = None
        self._verbose_lock = threading.Lock()
        self._conversation_epoch = 0

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        # Load manifest
        manifest_path = get_manifest_path(self.root)
        if manifest_path.exists():
            manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
            self.branch = self.branch or manifest.current_branch
        else:
            self.branch = self.branch or "main"

        # Yield components.
        #
        # Play modes get a visual-novel split: the transcript on the
        # left and an optional character portrait (立绘) on the right. The
        # portrait panel starts hidden and only reveals itself when the
        # active speaker has a portrait asset, so this is purely additive —
        # build / sandbox keep the exact original single-column layout.
        # M31: play and build are two places, so both sets of furniture are
        # composed and the mode decides which is on screen. `compose()` runs
        # once at mount, so a runtime `/mode` switch can only flip `display`
        # — it cannot rebuild the tree.
        #
        # ConversationView sits OUTSIDE both stages and is never reparented:
        # it holds the whole transcript, and moving it between containers
        # would throw the conversation away. The play stage therefore stops
        # at the furniture (image band, location card, controls) and lets the
        # transcript fill what is left, which stacks exactly as before.
        # Built with constructor arguments rather than `with` blocks: the
        # context-manager form needs a live App, and these widgets are now
        # composed in every mode — including the unmounted `compose()` calls
        # the tests make.
        _b = lambda k: f"［ {get_message(self.ui_locale, k).strip()} ］"  # noqa: E731
        _t = lambda k: get_message(self.ui_locale, k).strip()  # noqa: E731
        yield Vertical(
            # 任务 A1: the tab bar. Plain buttons so mouse and keyboard both
            # work (no key bindings, no slash command for tabs).
            Horizontal(
                Button(_t("play.tab.chat"), id="tab-chat", classes="play-tab active"),
                Button(_t("play.tab.image"), id="tab-image", classes="play-tab"),
                Button(_t("play.tab.map"), id="tab-map", classes="play-tab"),
                id="play-tabs",
            ),
            # ── 对话 tab: everything the play stage always had ──
            Vertical(
            # Top band: scene image (left) + adaptive game-state doc
            # (right). Both collapse together when the image is hidden.
            Horizontal(
                PortraitPanel(id="portrait-panel"),
                # Right column: the state doc scrolls, with a visible bar
                # and ▲ / ▼ for people who do not reach for the wheel
                # (「右边的 status bar 添加一个 scroll bar,
                # 然后有向上和向下的按钮」).
                # The doc itself is a leaf Static: Textual never gives a leaf
                # a virtual height taller than its box, so `overflow-y` on it
                # scrolled nothing (verified headless). A real scroll
                # container owns the bar; the doc grows to its content.
                # 「常驻的状态栏可以切换成是常驻地图」— one
                # button at the top flips the column between the status doc
                # and a resident map (the same MapPanel as the 地图 tab).
                Vertical(
                    Button(_t("play.side.map"), id="btn-side-toggle", classes="state-scroll-btn side-toggle"),
                    Button("▲", id="btn-state-up", classes="state-scroll-btn"),
                    VerticalScroll(GameStatePanel(id="game-state-panel"), id="game-state-scroll"),
                    Button("▼", id="btn-state-down", classes="state-scroll-btn"),
                    MapPanel(id="side-map"),
                    id="game-state-side",
                    classes="state-side",
                ),
                id="stage-top",
            ),
            LocationHeader(id="location-header"),
            Horizontal(
                # Initial labels so the toolbar is never a blank strip even
                # before on_mount relabels it; already localized so no
                # Chinese flashes in a non-zh UI.
                Button(_b("play.btn.hide_image"), id="btn-toggle-image", classes="play-ctl-btn"),
                Button(_b("play.btn.skip"), id="btn-skip-reveal", classes="play-ctl-btn"),
                Button(_b("play.btn.gen_scene"), id="btn-gen-scene", classes="play-ctl-btn"),
                id="play-controls",
            ),
            id="play-tab-chat",
            ),
            # ── 文生图 tab: the latest scene image, large, + generate ──
            # 「文生图放大图是好,也可以添加状态栏」— the same
            # status doc rides along on the right (its own instance; the
            # panel just watches files, so a second one is cheap).
            Vertical(
                Horizontal(
                    PortraitPanel(id="scene-panel"),
                    Vertical(
                        VerticalScroll(GameStatePanel(id="game-state-panel-2"), id="game-state-scroll-2"),
                        id="game-state-side-2",
                        classes="state-side",
                    ),
                    id="scene-band",
                ),
                Horizontal(
                    Button(_b("play.btn.gen_scene"), id="btn-gen-scene-2", classes="play-ctl-btn"),
                    id="scene-controls",
                ),
                id="play-tab-image",
            ),
            # ── 地图 tab ──
            MapView(id="play-tab-map"),
            id="play-stage",
        )
        # M18 Phase E1: the per-character status lane. Collapses to zero rows
        # until a world-agent has live characters, so even a legacy
        # single-agent play session looks identical.
        yield CharacterStatusLane(id="character-status-lane")
        # Build-side furniture: what the world is made of.
        yield BuildStage(id="build-stage")
        # The status column sits to the RIGHT of the transcript (player / Agent toggle on its top); the
        # row is composed once, so ConversationView is still never reparented
        from neonrp.tui.status_side import StatusSide

        yield Horizontal(
            ConversationView(display_mode=self.mode, id="conversation-view"),
            StatusSide(locale=self.ui_locale, id="status-side"),
            id="conv-row",
        )
        yield AskUserInlinePanel(id="ask-user-inline")
        from neonrp.tui.options_bar import OptionsBar, QuickBar

        yield OptionsBar(on_pick=self._pick_option, id="options-bar")
        yield QuickBar(on_pick=self._quick_insert, id="quick-bar")
        yield InputArea(mode=self.mode, id="input-area")

    def on_mount(self) -> None:
        """Initialize on mount."""
        self.title = f"NeonRP — {self.root.name}"
        self.ui_locale = self._resolve_ui_locale()
        self.query_one("#input-area", InputArea).set_locale(self.ui_locale)

        # Insurance hook: if the process is torn down without going
        # through action_quit / action_safe_quit (terminal closed,
        # SIGTERM, etc.), atexit still gives us a chance to write a
        # cancel tool message for any pending ask_user so the JSONL
        # doesn't end with an orphan tool_call that would 400 the
        # next session's first LLM call.
        import atexit
        atexit.register(self._sync_finalize_pending_ask_user)

        # M31: both stages were composed; show only this mode's furniture.
        self._apply_mode_chrome(self.mode)

        # L14.5 — enable semantic annotations in play mode only.
        try:
            view = self.query_one("#conversation-view", ConversationView)
            view.set_semantic_mode(str(self.mode))
            # Default layer: L2 in play (narrative + semantic chips),
            # L3 in build/sandbox (author wants to see tool calls).
            default_layer = 2 if self.mode == "play" else 3
            view.set_semantic_layer(default_layer)
            self._semantic_layer = default_layer
        except Exception:
            self._semantic_layer = 2

        # Persistent multi-agent soul lane: seed from playthrough at mount
        # so it's visible from launch (not only mid-turn) in play.
        if self.mode == "play":
            self._prime_soul_lane()
            # Seed the portrait panel with the bundled default so it carries
            # the WorldLines art style from the very first frame (no blank
            # column while the user waits for the opening turn).
            try:
                panel = self.query_one("#portrait-panel", PortraitPanel)
                panel.update_for(self.root, None)
            except Exception:
                pass
            # Pin the location header to the active world so it can poll
            # run_state.json without needing turn-event plumbing. The
            # on_change hook fires a scene text-to-image when the player
            # moves to a new location.
            try:
                header = self.query_one("#location-header", LocationHeader)
                header.set_root(self.root)
                header.on_change = self._on_location_changed
            except Exception:
                pass
            # Pin the adaptive game-state panel beside the image (+ its twin on
            # the 文生图 tab, and the resident map in the right column).
            from neonrp.tui.status_side import StatusSide

            try:  # the lane's content lives in the right column now
                self.query_one("#character-status-lane", CharacterStatusLane).retired = True
                self.query_one("#character-status-lane").display = False
            except Exception:  # noqa: BLE001
                pass
            for wid, kind in (("#game-state-panel", GameStatePanel), ("#game-state-panel-2", GameStatePanel), ("#side-map", MapPanel),
                              ("#status-side", StatusSide)):
                try:
                    self.query_one(wid, kind).set_root(self.root)
                except Exception:
                    pass
            # Label the play-stage control buttons for the current locale.
            self._relabel_play_controls()
            # 任务 A1: start on the 对话 tab; the other two are composed but hidden.
            self._set_play_tab(getattr(self, "_play_tab", "chat") or "chat")
            # Kick a cover image on entry if a text-to-image backend is set.
            self.call_after_refresh(lambda: self._kick_scene_imagegen(reason="cover"))

        # Initialize conversation session
        self._init_session()

        # Startup policy: default new session; optional continue.
        self._apply_startup_session_policy()

        # Show provider setup hints
        self._show_provider_setup_notice()
        self._show_init_hint_if_needed()

        # (The VN entry banner was removed — the scene image band + the
        # location scene-card already brand the play stage, and dropping
        # the banner hands those rows back to the transcript.)

        # Start external bridges (Discord, etc) if user has autostart=true.
        # No-op for users without any bridge configured.
        try:
            self._ensure_bridge_hub()
        except Exception:
            pass

        if self.verbose:
            self._set_verbose_enabled(True, announce=True)

        # Focus input
        self.query_one("#message-input", Input).focus()
        self._refresh_status(include_event_count=False)
        if self.startup_commands:
            self.call_after_refresh(self._run_startup_commands)

    def _run_startup_commands(self) -> None:
        """Execute deferred commands after the UI has mounted.

        Inputs that start with `/` go through slash-command handling;
        anything else is the startup handoff brief — fed to the agent as
        the opening turn but sent silently, since it's a system
        instruction the player never typed and shouldn't see echoed.
        """
        commands = list(self.startup_commands)
        self.startup_commands = []
        for command in commands:
            if not command:
                continue
            if command.startswith("/"):
                self._handle_slash_command(command)
            else:
                self._send_message(command, silent=True)

    def _show_init_hint_if_needed(self) -> None:
        """Show hint when project is not initialized yet."""
        manifest_path = get_manifest_path(self.root)
        if manifest_path.exists():
            return
        view = self.query_one("#conversation-view", ConversationView)
        view.write("[yellow]Project not initialized in this directory.[/]\n")
        view.write("[dim]Run /init or /open to start a world here.[/]\n")

    def _show_play_banner(self) -> None:
        """Cosmetic VN-style ASCII title shown once on entering play.

        Skipped when the transcript already has content (continue/replay)
        so it never displaces restored history. Pure decoration — any
        failure is swallowed by the caller.
        """
        view = self.query_one("#conversation-view", ConversationView)
        # If we restored a session there will already be mounted children;
        # only banner a pristine screen.
        try:
            if any(True for _ in view.children):
                return
        except Exception:
            pass
        title = (
            "[#c9a3ff]┌────────────────────────────────────────┐[/]\n"
            "[#c9a3ff]│[/]  [bold #f0e6ff]W O R L D L I N E S[/]  [#8a7fae]· NeonRP[/]            [#c9a3ff]│[/]\n"
            "[#c9a3ff]│[/]  [#8a7fae]a conversation that remembers you[/]     [#c9a3ff]│[/]\n"
            "[#c9a3ff]└────────────────────────────────────────┘[/]\n"
        )
        view.write(title)

    def _init_session(self) -> None:
        """Initialize conversation session."""
        import os

        from neonrp.net.client import connect

        agent = self._get_default_agent()
        # 10-10: the TUI is a client — of the engine in this process (default, unchanged), or of a headless host
        url = os.environ.get("NEONRP_CONNECT_URL", "").strip()
        self.session = connect(self.root, agent_id=agent, mode=self.mode, provider=self.provider,  # type: ignore[assignment]
                               url=url or None, token=os.environ.get("NEONRP_CONNECT_TOKEN", ""))
        if url:
            from neonrp.tui import net_room

            net_room.attach(self)

    def _ensure_bus_bridge(self) -> None:
        """M18 §6 / Phase 4.3 — subscribe the TUI to the session bus, once
        per session. Events dispatch into ``self._turn_event_sink`` — the
        CURRENT turn's closures (they carry the worker/staleness guards), so
        stale-turn events are dropped exactly as the old callbacks were.
        Dispatch happens on the turn's worker thread, same as the callbacks
        it replaces; the sink closures already _safe_call_from_thread."""
        session = self.session
        if session is None or getattr(self, "_bus_bridged_session", None) is session:
            return
        bus_fn = getattr(session, "bus", None)
        if not callable(bus_fn):
            return  # test fakes without a broker
        self._bus_bridged_session = session
        bus = bus_fn()

        def _sink(kind: str):
            return (getattr(self, "_turn_event_sink", None) or {}).get(kind)

        def _on_stream(msg: Any) -> None:
            p = msg.payload
            kind = p.get("kind")
            if kind == "chunk":
                fn = _sink("chunk")
                if fn:
                    fn(p.get("text", ""))
            elif kind == "thinking":
                fn = _sink("thinking")
                if fn:
                    fn(p.get("text", ""))
            elif kind == "tool_use":
                fn = _sink("tool_use")
                if fn:
                    fn(p.get("name", ""), p.get("args") or {})
            elif kind == "tool_result":
                fn = _sink("tool_result")
                if fn:
                    fn(p.get("name", ""), p.get("args") or {}, p.get("result", ""))

        def _on_event(msg: Any) -> None:
            p = msg.payload
            if p.get("kind") == "soul_status":
                fn = _sink("soul_status")
                if fn:
                    fn(p.get("statuses") or {})

        def _on_beat(msg: Any) -> None:
            fn = _sink("beat")
            if fn:
                fn(dict(msg.payload or {}))

        bus.subscribe("engine/stream", _on_stream)
        bus.subscribe("engine/event", _on_event)
        bus.subscribe("engine/beat", _on_beat)

    def _apply_startup_session_policy(self) -> None:
        """Choose startup behavior: default new session unless continue requested."""
        if self.continue_session:
            restored = self._restore_session()
            if not restored:
                view = self.query_one("#conversation-view", ConversationView)
                view.write("[dim]No previous session found. Started a new session.[/]\n")
            return
        self._start_new_session(announce=False)

    def _restore_session(self) -> bool:
        """Restore previous session messages."""
        if not self.session:
            return False

        loaded = self.session.resume()
        if loaded <= 0:
            return False

        messages = self.session.get_messages()
        if not any(m.role in {"user", "assistant"} for m in messages):
            return False

        view = self.query_one("#conversation-view", ConversationView)
        view.write("[dim]--- Previous session restored ---[/]\n")
        self._render_session_messages(messages)
        return True

    def _render_session_messages(self, messages: list[Any]) -> None:
        """Render persisted user/assistant messages into conversation view."""
        view = self.query_one("#conversation-view", ConversationView)
        root_speaker = self._get_root_speaker_name()
        ask_user_fallbacks: dict[str, tuple[str, list[str]]] = {}
        pending_tool_calls: dict[str, tuple[str, dict[str, Any]]] = {}
        idx = 0
        while idx < len(messages):
            message = messages[idx]
            if message.role == "system":
                idx += 1
                continue
            # Call the compact-message detectors on the CLASS (they're
            # @staticmethod), not via `view`. Otherwise unit tests that use
            # a bare `MagicMock()` for view get a truthy Mock back and take
            # this branch for every user message, skipping real render.
            if message.role == "user" and ConversationView.is_compact_summary_message(message.content or ""):
                acknowledgement = None
                if idx + 1 < len(messages):
                    next_message = messages[idx + 1]
                    if next_message.role == "assistant" and ConversationView.is_compact_ack_message(next_message.content or ""):
                        acknowledgement = next_message.content or ""
                        idx += 1
                view.add_compact_summary_fold(message.content or "", acknowledgement)
                idx += 1
                continue
            if message.role == "user":
                view.add_user_message(message.content or "")
            elif message.role == "assistant":
                for tool_call in getattr(message, "tool_calls", []) or []:
                    tool_name = ConversationView._canonical_tool_name(getattr(tool_call, "name", ""))
                    tool_call_id = str(getattr(tool_call, "id", "") or "").strip()
                    raw_args = getattr(tool_call, "arguments", {})
                    params = raw_args if isinstance(raw_args, dict) else {}
                    if tool_call_id:
                        pending_tool_calls[tool_call_id] = (tool_name, params)
                    view.add_tool_indicator(tool_name, params)
                    if tool_name == "ask_user" and tool_call_id:
                        question, options = self._extract_ask_user_prompt_from_args(params)
                        ask_user_fallbacks[tool_call_id] = (question, options)
                if message.content:
                    cleaned_content = self._normalize_assistant_text(message.content)
                    if not cleaned_content:
                        continue
                    speaker_name = root_speaker
                    message_speaker = str(getattr(message, "name", "") or "").strip()
                    if message_speaker:
                        speaker_name = self._get_agent_display_name(message_speaker)
                    view.add_named_assistant_message(speaker_name, cleaned_content)
                    view.add_assistant_end()
            elif message.role == "tool":
                tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
                tool_name = ConversationView._canonical_tool_name(getattr(message, "name", "") or "")
                params: dict[str, Any] = {}
                if tool_call_id in pending_tool_calls:
                    pending_name, pending_params = pending_tool_calls[tool_call_id]
                    if pending_name:
                        tool_name = pending_name
                    if isinstance(pending_params, dict):
                        params = pending_params
                raw_tool_result = getattr(message, "content", "") or ""
                if tool_name:
                    if not params:
                        view.add_tool_indicator(tool_name, {})
                    view.complete_tool_indicator(tool_name, params, raw_tool_result)
                if self._is_todo_tool_message(message):
                    items = self._extract_todo_items_from_tool_message(message)
                    if items:
                        view.add_todo_display(items)
                elif self._is_ask_user_tool_message(message):
                    fallback_question, fallback_options = ask_user_fallbacks.get(tool_call_id, ("", []))
                    selected = self._extract_ask_user_selection(
                        raw_tool_result,
                        fallback_question=fallback_question,
                        fallback_options=fallback_options,
                    )
                    if selected:
                        question, response, options = selected
                        rendered = self._format_ask_user_selection_message(question, response, options)
                        if rendered:
                            view.add_user_message(rendered)
                    else:
                        cancelled = False
                        try:
                            payload = json.loads(raw_tool_result)
                            cancelled = str(payload.get("status", "")).strip().lower() == "cancelled"
                        except Exception:
                            cancelled = False
                        if cancelled:
                            rendered_cancelled = self._format_ask_user_cancelled_message(
                                fallback_question,
                                fallback_options,
                            )
                            if rendered_cancelled:
                                view.add_user_message(rendered_cancelled)
                elif self._is_task_tool_message(message):
                    rendered_task = self._extract_task_tool_transcript(raw_tool_result)
                    if rendered_task:
                        speaker, body = rendered_task
                        view.add_named_assistant_message(speaker, body)
                        view.add_assistant_end()
            idx += 1

    @staticmethod
    def _is_todo_tool_message(message: Any) -> bool:
        return str(getattr(message, "name", "") or "").strip() == "TodoWrite"

    @staticmethod
    def _is_ask_user_tool_message(message: Any) -> bool:
        return str(getattr(message, "name", "") or "").strip() == "ask_user"

    @staticmethod
    def _is_task_tool_message(message: Any) -> bool:
        return str(getattr(message, "name", "") or "").strip() == "task"

    @staticmethod
    def _extract_ask_user_prompt_from_args(raw_args: Any) -> tuple[str, list[str]]:
        """Parse ask_user tool-call args into fallback question/options."""
        if not isinstance(raw_args, dict):
            return "", []

        question = ""
        options_raw: list[Any] = []

        questions = raw_args.get("questions")
        if isinstance(questions, str):
            try:
                questions = json.loads(questions)
            except (ValueError, TypeError):
                questions = None
        if isinstance(questions, list):
            first = next((item for item in questions if isinstance(item, dict)), None)
            if first:
                question = str(first.get("question", "") or "").strip()
                options_value = first.get("options", [])
                if isinstance(options_value, list):
                    options_raw = options_value
        if not question:
            question = str(raw_args.get("question", "") or "").strip()
        if not options_raw:
            options_value = raw_args.get("options", [])
            if isinstance(options_value, list):
                options_raw = options_value

        options: list[str] = []
        for option in options_raw:
            if isinstance(option, dict):
                label = str(option.get("label", "") or "").strip()
            else:
                label = str(option or "").strip()
            if label:
                options.append(label)
        return question, options

    @staticmethod
    def _extract_ask_user_selection(
        raw_result: str,
        fallback_question: str = "",
        fallback_options: list[str] | None = None,
    ) -> tuple[str, str, list[str]] | None:
        """Best-effort parse of ask_user tool output payload.

        Supports both new format ``{"answers": {"0": "label"}}`` and
        legacy format ``{"data": {"question": ..., "response": ...}}``.
        """
        if not isinstance(raw_result, str) or not raw_result.strip():
            return None
        try:
            payload = json.loads(raw_result)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        # --- New lean format: {"answers": {"0": "label", ...}} ---
        answers = payload.get("answers")
        if isinstance(answers, dict) and answers:
            first_answer = str(next(iter(answers.values()), "")).strip()
            if not first_answer:
                return None
            question = str(fallback_question or "").strip()
            options = [str(o).strip() for o in (fallback_options or []) if str(o or "").strip()]
            return question, first_answer, options

        # --- Legacy format: {"data": {"question", "options", "response"}} ---
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        response = str(data.get("response", "") or "").strip()
        if not response:
            return None
        question = str(data.get("question", "") or "").strip()
        if not question:
            question = str(fallback_question or "").strip()
        options_raw = data.get("options")
        if not isinstance(options_raw, list):
            options_raw = fallback_options if isinstance(fallback_options, list) else []
        options: list[str] = []
        for option in options_raw:
            value = str(option or "").strip()
            if value:
                options.append(value)
        return question, response, options

    @staticmethod
    def _format_ask_user_selection_message(question: str, response: str, options: list[str] | None = None) -> str:
        """Format ask_user selection as a user-visible transcript message."""
        q = str(question or "").strip()
        r = str(response or "").strip()
        opts = [str(option or "").strip() for option in (options or []) if str(option or "").strip()]
        if not r:
            return ""
        if opts:
            lines = [f"- [{'x' if option == r else ' '}] {option}" for option in opts]
            if r not in opts:
                lines.append(f"- [x] {r}")
            return f"{q}\n" + "\n".join(lines) if q else "\n".join(lines)
        if q:
            return f"{q}\n{r}"
        return r

    def _format_ask_user_cancelled_message(self, question: str, options: list[str] | None = None) -> str:
        """Render ask_user prompt details when user cancels via ESC."""
        locale = getattr(self, "ui_locale", None) or getattr(self, "locale", "en") or "en"
        cancelled = get_message(locale, "ask_user.cancelled")
        q = str(question or "").strip()
        opts = [str(option or "").strip() for option in (options or []) if str(option or "").strip()]
        if opts:
            body = "\n".join(f"- [ ] {option}" for option in opts)
            if q:
                return f"{q}\n{body}\n{cancelled}"
            return f"{body}\n{cancelled}"
        if q:
            return f"{q}\n{cancelled}"
        return cancelled

    @staticmethod
    def _normalize_assistant_text(text: str) -> str:
        """Normalize assistant text for transcript rendering."""
        if not isinstance(text, str):
            return ""
        return text

    def _extract_task_tool_transcript(self, raw_result: str) -> tuple[str, str] | None:
        """Extract speaker + text from task() tool result for session replay."""
        if not isinstance(raw_result, str) or not raw_result.strip():
            return None
        try:
            payload = json.loads(raw_result)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}

        status = str(payload.get("status", "") or "").strip().lower()
        agent_id = str(data.get("agent_id", "") or "").strip()
        speaker = self._get_agent_display_name(agent_id) if agent_id else "Sub-agent"
        assistant_text = str(data.get("assistant_text", "") or "")

        if not assistant_text:
            if status == "success":
                assistant_text = "Sub-task completed."
            elif status == "cancelled":
                error_text = str(payload.get("error") or data.get("error") or "").strip()
                assistant_text = f"Sub-task canceled: {error_text}" if error_text else "Sub-task canceled by user."
            else:
                error_text = str(payload.get("error") or data.get("error") or "").strip()
                assistant_text = f"Sub-task failed: {error_text}" if error_text else "Sub-task failed."

        if not assistant_text:
            return None
        return speaker, assistant_text

    @classmethod
    def _extract_sub_agent_tag(cls, text: str) -> tuple[str | None, str]:
        """Decode tagged nested-agent stream payload: [[subagent:<id>]]<payload>."""
        if not isinstance(text, str):
            return None, str(text)
        match = cls._SUB_AGENT_TAG_RE.match(text)
        if not match:
            return None, text
        speaker = str(match.group(1) or "").strip() or None
        payload = match.group(2) or ""
        return speaker, payload

    @staticmethod
    def _scope_tool_name(tool_name: str, speaker: str | None) -> str:
        """Attach speaker scope so sub-agent tool cards don't collide with parent cards."""
        base = str(tool_name or "").strip()
        if not speaker:
            return base
        return f"{speaker}:{base}"

    @staticmethod
    def _extract_todo_items_from_tool_message(message: Any) -> list[dict]:
        """Best-effort parse of TodoWrite tool output payload."""
        content = getattr(message, "content", "") or ""
        if not isinstance(content, str) or not content.strip():
            return []
        try:
            payload = json.loads(content)
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        items = data.get("items")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def _count_session_entries(self, path: Path) -> int:
        """Count non-empty lines in a session JSONL file."""
        if not path.exists():
            return 0
        try:
            with open(path, encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0

    def _history_dir_for_branch(self, branch: str) -> Path:
        return get_neonrp_dir(self.root) / "sessions" / "history" / branch

    def _archive_active_session(self, branch: str) -> Path | None:
        """Archive current active session into history/branch if non-empty."""
        active_path = get_session_path(self.root, branch)
        if self._count_session_entries(active_path) == 0:
            return None

        history_dir = self._history_dir_for_branch(branch)
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = history_dir / f"{stamp}.jsonl"
        idx = 1
        while target.exists():
            target = history_dir / f"{stamp}-{idx}.jsonl"
            idx += 1

        active_path.replace(target)
        return target

    def _start_new_session(self, announce: bool = True) -> None:
        """Start a fresh session and archive existing active conversation."""
        if not self.session:
            return

        view = self.query_one("#conversation-view", ConversationView)
        # Invalidate late callbacks from older turns before clearing UI/session state.
        self._conversation_epoch += 1
        self._stream_started = False
        self._subagent_stream_seen.clear()
        self._pending_proposal = None
        self._clear_run_status()
        self._cancel_active_ask_user()

        if self._active_send_thread is not None and self._active_send_thread.is_alive():
            self.session.cancel()
            self._active_send_thread.join(timeout=1.0)
            if self._active_send_thread.is_alive():
                view.write("[yellow]Current request is still stopping. Please run /new again in a moment.[/]\n")
                return
        self._active_send_thread = None

        branch = self.session.branch
        archived = self._archive_active_session(branch)
        self.session.clear()

        view.clear()
        self._reset_estimated_tokens()
        self._refresh_status()
        if announce:
            view.write("[green]Started a new session.[/]\n")
            if archived:
                view.write(f"[dim]Archived previous session: {archived.name}[/]\n")

    def _get_event_count(self) -> int:
        """Get current event count."""
        if not self.branch:
            return 0
        try:
            events_file = get_neonrp_dir(self.root) / "logs" / self.branch / "events.jsonl"
            if events_file.exists():
                count = 0
                with open(events_file, encoding="utf-8") as f:
                    for _ in f:
                        count += 1
                return count
        except (OSError, IOError):
            pass
        return 0

    def _get_default_agent(self) -> str:
        """Get default agent ID."""
        narrator_agent_id = self._get_narrator_agent_id()
        startup_entry_agent = get_startup_entry_agent(self.root)

        if self.mode in {"build", "play"}:
            data_dir_name = get_data_dir_name(self.root)
            run_state_path = self.root / data_dir_name / "meta" / "run_state.json"
            if startup_entry_agent and run_state_path.exists():
                try:
                    run_state = json.loads(run_state_path.read_text(encoding="utf-8"))
                except Exception:
                    run_state = None
                if isinstance(run_state, dict):
                    try:
                        turn_count = int(run_state.get("turn_count", 0) or 0)
                    except Exception:
                        turn_count = 0
                    if turn_count <= 0:
                        return startup_entry_agent
        agents_dir = self.root / "agents"
        if agents_dir.exists():
            agents = sorted(d.name for d in agents_dir.iterdir() if d.is_dir())
            if agents:
                if narrator_agent_id in agents:
                    return narrator_agent_id
                if "narrator" in agents:
                    return "narrator"
                # Prefer an orchestrator / world-agent if present, before
                # falling back to the alphabetical first entry. Otherwise the
                # default speaker ends up being whichever agent happens to
                # sort first (e.g. `clock-keeper`).
                for preferred in ("orchestrator", "world-agent", "world"):
                    if preferred in agents:
                        return preferred
                return agents[0]
        return narrator_agent_id

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        event_input = getattr(event, "input", None)
        event_input_id = getattr(event_input, "id", None)
        if isinstance(event_input_id, str) and event_input_id != "message-input":
            return
        if not event.value.strip():
            return

        text = event.value.strip()
        input_widget = self.query_one("#message-input", Input)

        # If slash suggestions are visible, Enter selects and immediately executes
        # Only apply completion when user text is a partial prefix of the suggestion
        if text.startswith("/") and self._slash_suggestions:
            completion = self._get_selected_slash_completion()
            if completion and completion.startswith(text):
                text = completion

        input_widget.value = ""
        self._hide_slash_suggestions()
        self._push_input_history(text)

        # Handle slash commands
        if text.startswith("/"):
            self._handle_slash_command(text)
            return

        # Send to conversation
        self._send_message(text)

    def _handle_slash_command(self, text: str) -> None:
        """Handle slash commands."""
        view = self.query_one("#conversation-view", ConversationView)
        view.add_user_message(text)

        parsed = parse_command(text)
        if parsed.error:
            view.write(f"[red]Error: {parsed.error}[/]\n")
            return

        cmd = parsed.command

        from neonrp.tui.play_commands import PLAY_COMMANDS, undo_turn

        if cmd in PLAY_COMMANDS:  # 10-08 the two-beat play: /status · /lang · /dev
            PLAY_COMMANDS[cmd](self, parsed.args)
            return
        if cmd == "undo" and undo_turn(self, parsed.args):  # /undo list · /undo <turn>
            return
        from neonrp.tui.legacy_commands import legacy_notice, removed_notice

        _rn = removed_notice(cmd)
        if _rn:  # deleted — say where its job went
            view.write(f"[yellow]{_rn}[/]\n")
            return
        _ln = legacy_notice(cmd)
        if _ln:  # a retired command still runs, but says where it went
            view.write(f"[dim]{_ln}[/]\n")

        if cmd == "mode":
            self._cmd_mode(parsed.args)
        elif cmd == "clear":
            self._cmd_clear()
        elif cmd == "help":
            self._cmd_help()
        elif cmd == "login":
            sub_cmd = (parsed.args[0].lower() if parsed.args else "")
            if sub_cmd in ("out", "logout"):
                self._cmd_logout()
            elif sub_cmd in ("status", "account", "?"):
                self._cmd_account()
            elif sub_cmd in ("billing", "plan", "订阅", "额度"):
                self._cmd_billing()
            else:
                self._cmd_login(parsed.args)
        elif cmd == "undo":
            self._cmd_undo()
        elif cmd == "save":
            self._cmd_save(parsed.args)
        elif cmd == "load":
            self._cmd_load(parsed.args)
        elif cmd == "stats":
            self._cmd_stats()
        elif cmd == "cast":
            # 迎入已建好的角色。名字统一用 `cast` —— 与其他项目一致,而且
            # `new` 读起来更像 `create`,两个词太近会让
            # 「造」和「迎」这条心智分界模糊掉,所以 `new` 撤下。
            if parsed.args:
                self._cmd_cast(parsed.args)
            else:
                # 不带参数 = 给我看菜单(与 /load 同一习惯)。
                self._cmd_list_souls()
        elif cmd == "who":
            # TODO #3:进一个角色的 context(不带参数=选一个)。
            self._cmd_who(parsed.args)
        elif cmd == "create":
            self._cmd_create(parsed.args)
        elif cmd == "open":
            self._cmd_open(parsed.args, parsed.options)
        elif cmd == "init":
            self._cmd_init(parsed.args)
        elif cmd == "vault":
            self._cmd_vault(parsed.args)
        elif cmd == "import":
            self._cmd_import(parsed.args)
        elif cmd == "remove":
            self._cmd_remove_soul(parsed.args)
        elif cmd == "reset":
            self._cmd_reset_soul(parsed.args)
        elif cmd == "verbose":
            self._cmd_verbose(parsed.args)
        elif cmd == "debug":
            self._cmd_debug(parsed.args)
        elif cmd == "config":
            self._cmd_config(parsed.args)
        elif cmd == "mcp":
            self._cmd_mcp(parsed.args)
        elif cmd == "update":
            self._cmd_update(parsed.args)
        elif cmd == "settings":
            self._cmd_settings()
        elif cmd == "bridge":
            self._cmd_bridge(parsed.args)
        elif cmd in WORLD_ACTIONS:
            self._run_world_action(cmd, parsed.args)
        elif cmd in CLI_FORWARD_COMMANDS:
            self._forward_cli_command(parsed)
        elif cmd in ("quit", "q"):
            self.exit()
        elif self.mode == "play":  # a player's command the engine reads (10-21:「/侦查 井口」 never left the TUI): skills, world actions
            self._send_message(text, silent=True)  # already shown above
        else:
            view.write(f"[yellow]Unknown command: /{cmd}[/]\n")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show inline slash command suggestions as user types."""
        if event.input.id != "message-input":
            return
        if self._suppress_input_change:
            self._suppress_input_change = False
            return
        if self._history_index is None:
            self._history_draft = event.value
        self._portrait_note_typing()
        self._update_slash_suggestions(event.value)

    def _portrait_note_typing(self) -> None:
        """Hold the portrait's matrix rain while the user types (a frame is
        ~0.5 s of pure Python and used to steal the keystroke's turn)."""
        try:
            from neonrp.tui.portrait import PortraitPanel

            for panel in self.query(PortraitPanel):
                panel.note_typing()
        except Exception:
            pass

    def on_key(self, event) -> None:
        """Handle key events for slash suggestions and command history."""
        if event.key == "escape":
            if self._cancel_active_ask_user():
                event.stop()
                event.prevent_default()
                return
            # No ask_user active, but a turn may be running. ESC cancels it
            # (sets ConversationSession._cancel_event; the turn loop checks
            # at every step and exits). Without this, ESC during a turn did
            # nothing and the user only saw "A request is already running".
            if self._cancel_running_turn():
                event.stop()
                event.prevent_default()
                return

        # When a modal screen is active (model picker / sessions / etc.),
        # let the modal own keyboard handling and do not mutate base input state.
        try:
            if isinstance(self.screen, ModalScreen):
                return
        except ScreenStackError:
            # App not mounted in unit tests; continue with normal logic.
            pass

        input_widget = self.query_one("#message-input", Input)
        if not input_widget.has_focus:
            return

        if self._slash_suggestions:
            if event.key == "up":
                self._move_slash_selection(-1)
                event.stop()
                event.prevent_default()
                return
            if event.key == "down":
                self._move_slash_selection(1)
                event.stop()
                event.prevent_default()
                return
            if event.key == "tab":
                completion = self._get_selected_slash_completion()
                if completion:
                    new_value = completion + " "
                    self._set_input_text(new_value)
                    self._update_slash_suggestions(new_value)
                event.stop()
                event.prevent_default()
                return
            if event.key == "escape":
                self._hide_slash_suggestions()
                event.stop()
                event.prevent_default()
                return

        if event.key == "up":
            # Two-stage navigation: ↑ first moves the caret to the start of
            # the line; only when the caret is *already* at the start does
            # ↑ scroll into the input-history buffer. Lets users edit
            # mid-line drafts without losing them to a history recall.
            if input_widget.cursor_position > 0:
                input_widget.cursor_position = 0
                event.stop()
                event.prevent_default()
            elif self._navigate_input_history(-1):
                event.stop()
                event.prevent_default()
        elif event.key == "down":
            value_len = len(input_widget.value or "")
            if input_widget.cursor_position < value_len:
                input_widget.cursor_position = value_len
                event.stop()
                event.prevent_default()
            elif self._navigate_input_history(1):
                event.stop()
                event.prevent_default()
        elif event.key == "escape":
            # ESC while an LLM request is in-flight → interrupt
            if (
                self._active_send_thread is not None
                and self._active_send_thread.is_alive()
                and self.session is not None
            ):
                self.session.cancel()
                view = self.query_one("#conversation-view", ConversationView)
                view.write("\n[yellow]⚡ Interrupted by user (ESC)[/]\n")
                self._clear_run_status()
                event.stop()
                event.prevent_default()

    _CHANNEL_AT = ("@", "＠")
    _CHANNEL_HASH = ("#", "＃")

    def _channel_targets(self) -> list[tuple[str, str, bool]]:
        """Souls you can `@`: ``(display name, sid, present-in-room)``,
        present ones first. From this world's roster + souls/ folders."""
        try:
            from neonrp.core.light_chat import _display_name, resolve_room_souls
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.root)
        except Exception:  # noqa: BLE001
            return []
        if pt is None:
            return []
        try:
            present = {iid for iid, _d, _n in resolve_room_souls(self.root)}
        except Exception:  # noqa: BLE001
            present = set()
        out: list[tuple[str, str, bool]] = []
        for ref in pt.souls:
            soul_dir = self.root / "souls" / f"{ref.sid}-{ref.instance_id}"
            try:
                name = _display_name(soul_dir, ref.sid) if soul_dir.is_dir() else ref.sid
            except Exception:  # noqa: BLE001
                name = ref.sid
            out.append((str(name or ref.sid), ref.sid, ref.instance_id in present))
        out.sort(key=lambda t: (not t[2], t[0]))
        return out

    def _compute_channel_suggestions(self, value: str) -> list[tuple[str, str]]:
        """`@` → who you can talk to (在场 first); `#` → the two room forms.
        Play-only: channels are interlude beats (「@ 会有
        suggestion 吗?」— now it does, same panel as `/`)."""
        if self.mode != "play":
            return []
        v = value.replace("\r", "").replace("\n", "")
        head = v[:1]
        if head in self._CHANNEL_HASH:
            if v[1:].strip():
                return []
            return [
                (f"[green]#[/] [dim]{self._sugg('sugg.room_peek')}[/]", "#"),
                (f"[green]# …[/] [dim]{self._sugg('sugg.room_say')}[/]", "# "),
            ]
        if head not in self._CHANNEL_AT:
            return []
        rest = v[1:]
        if " " in rest or "　" in rest:  # already addressing someone — unless a name with a space is still being typed
            from neonrp.tui import play_hints as H

            return H.token_rows(H.menu(getattr(self, "root", None)), v, getattr(self, "ui_locale", "zh") or "zh",
                                at_head_people=True)
        prefix = rest.strip().lower()
        rows: list[tuple[str, str]] = []
        here = self._sugg("sugg.in_room")
        for name, sid, present in self._channel_targets():
            if prefix and not (name.lower().startswith(prefix) or sid.lower().startswith(prefix)):
                continue
            tag = f" · {here}" if present else ""
            rows.append((f"[green]@{name}[/] [dim]{sid}{tag}[/]", f"@{name}"))
        from neonrp.tui import play_hints as H  # 10-23: the other people standing here (the engine's menu)

        listed = {c for _l, c in rows}
        rows += [r for r in H.token_rows(H.menu(getattr(self, "root", None)), v, getattr(self, "ui_locale", "zh") or "zh",
                                         at_head_people=True) if r[1] not in listed]
        return rows

    def _compute_slash_suggestions(self, value: str) -> list[tuple[str, str]]:
        """Compute slash suggestions as (display_markup, completion)."""
        value = value.replace("\r", "").replace("\n", "")
        if not value.startswith("/"):
            return []

        command_text = value[1:]
        play_rows = self._play_slash_rows(command_text)
        if play_rows is not None:
            return play_rows
        if not command_text:
            command_names = get_command_suggestions("")
            return self._format_command_suggestions(command_names)

        parts = command_text.split()
        if not parts:
            # "/ " — same as a bare slash: list everything.
            return self._format_command_suggestions(get_command_suggestions(""))
        has_trailing_space = value.endswith(" ")
        cmd_name = parts[0]
        spec = COMMANDS.get(cmd_name, {})
        has_subcommands = isinstance(spec.get("subcommands"), list)

        # If command expects subcommands and user completed "/cmd ", suggest subcommands.
        if has_subcommands and (has_trailing_space or len(parts) > 1):
            sub_prefix = ""
            if len(parts) > 1 and not has_trailing_space:
                sub_prefix = parts[1]
            # Subcommand fully matched + user typing args beyond it: hide suggestions.
            valid_subs = spec.get("subcommands", [])
            if len(parts) > 2 or (len(parts) == 2 and has_trailing_space and parts[1] in valid_subs):
                return []
            subcommands = get_subcommand_suggestions(cmd_name, sub_prefix)
            return self._format_subcommand_suggestions(cmd_name, subcommands)

        # Commands without subcommands can still have enum-like first args
        # (e.g. /mode build|sandbox|play).
        if cmd_name in COMMANDS and not has_subcommands and (has_trailing_space or len(parts) > 1):
            # 「/cast 还有 /init 可以 suggestion 已经有的世界和
            # 角色」— live lists for the commands whose argument is a thing
            # that already exists on disk. Checked BEFORE the enum path: /open's
            # hint `[世界|存档]` would otherwise read as two literal choices.
            if cmd_name in self._DYNAMIC_ARG_COMMANDS and len(parts) <= 2:
                prefix = "" if has_trailing_space else str(parts[1] if len(parts) > 1 else "")
                return self._dynamic_argument_suggestions(cmd_name, prefix)
            arg_suggestions = self._extract_enum_arg_suggestions(cmd_name, parts, has_trailing_space)
            if arg_suggestions:
                return self._format_argument_suggestions(cmd_name, arg_suggestions)
            return []

        # Command without subcommands and already complete: hide suggestions.
        command_names = get_command_suggestions(cmd_name)
        return self._format_command_suggestions(command_names)

    def _play_slash_rows(self, command_text: str) -> list[tuple[str, str]] | None:
        """In play (10-23, as the standard front end): `/` + a prefix → the sheet's skills (value · line) first, then the
        world's actions and our commands for this run, then the rest; `/skill ` → what to use it on. None = not play /
        nothing of the sheet's typed (the caller's own command logic)."""
        if self.mode != "play":
            return None
        from neonrp.tui import play_hints as H

        m = H.menu(getattr(self, "root", None))
        if not m.get("skills"):
            return None
        loc = getattr(self, "ui_locale", "zh") or "zh"
        typed = H.skill_typed(m, command_text)
        if typed is not None and typed[0]:
            return H.target_rows(m, H.skill_completion(typed[0], self._taken_names()), typed[1], loc) or []
        skills = H.skill_rows(m, command_text, self._taken_names(), loc)  # 「/Quick S」: names may hold spaces
        if " " in command_text.strip() or command_text.endswith(" "):
            return skills or None  # else an argument to one of ours: the command logic below
        names = get_command_suggestions(command_text.strip())
        first = [n for n in names if n in WORLD_ACTIONS] + [n for n in H.PLAY_COMMANDS if n in names]
        rows = skills + self._format_command_suggestions(first + [n for n in names if n not in first])
        return rows

    def _taken_names(self) -> set[str]:
        """Names a `/` line runs here rather than sending: ours, the retired ones, the world's actions."""
        from neonrp.tui.legacy_commands import LEGACY_COMMANDS

        return {n.casefold() for n in (*COMMANDS, *LEGACY_COMMANDS, *WORLD_ACTIONS)}

    def _format_command_suggestions(self, command_names: list[str]) -> list[tuple[str, str]]:
        # 任务 B3: two kinds, two colours — the world's play actions wear the
        # play accent (green), our tools the build accent (red). Same rule in
        # /help and in the echo when one runs.
        suggestions: list[tuple[str, str]] = []
        action_tag = self._sugg("sugg.action")
        loc = getattr(self, "ui_locale", None)
        for cmd in command_names:
            kind = command_kind(cmd)
            spec = localized_spec(cmd, loc) if cmd in COMMANDS else (WORLD_ACTIONS.get(cmd) or command_spec(cmd) or {})
            desc = spec.get("help", "")
            if kind == "play":
                accent = mode_accent("play")
                hint = f" {spec['args_hint']}" if spec.get("args_hint") else ""
                suggestions.append((f"[{accent}]/{cmd}[/][dim]{hint} - {desc} · {action_tag}[/]", f"/{cmd}"))
            elif kind == "legacy":
                suggestions.append((f"[dim]/{cmd} - {desc} · {self._sugg('sugg.retired')}[/]", f"/{cmd}"))
            else:
                accent = mode_accent("build")
                suggestions.append((f"[{accent}]/{cmd}[/] [dim]- {desc}[/]", f"/{cmd}"))
        return suggestions

    def _run_world_action(self, name: str, args: list[str]) -> None:
        """A world-registered play action: templated words sent as the
        player's own (thin trigger, like /create). Play actions belong to
        play — from build we switch first, visibly (red → green)."""
        view = self.query_one("#conversation-view", ConversationView)
        if self.mode != "play":
            view.write(f"[dim]{self._sugg('sugg.action_switch', name=name)}[/]\n")
            self._apply_mode("play")
        text = render_action_prompt(name, args)
        if not text:
            view.write(f"[yellow]/{name} 没有可发的内容(actions.json 里 prompt 为空)。[/]\n")
            return
        view.write(f"[{mode_accent('play')}]▶ /{name}[/] [dim]{text}[/]\n")
        self._submit_user_text(text)

    @staticmethod
    def _format_subcommand_suggestions(parent: str, subcommands: list[str]) -> list[tuple[str, str]]:
        suggestions: list[tuple[str, str]] = []
        for sub in subcommands:
            suggestions.append((f"[cyan]/{parent}[/] [magenta]{sub}[/]", f"/{parent} {sub}"))
        return suggestions

    @staticmethod
    def _parse_enum_choices_from_args_hint(args_hint: str) -> list[str]:
        hint = str(args_hint or "").strip()
        if not (hint.startswith("[") and hint.endswith("]")):
            return []
        content = hint[1:-1].strip()
        if "|" not in content:
            return []
        # Skip composite hints like "set <name>|show [name]".
        if "<" in content:
            return []
        choices = [part.strip() for part in content.split("|")]
        if not choices or any(not c or " " in c for c in choices):
            return []
        return choices

    def _extract_enum_arg_suggestions(self, cmd_name: str, parts: list[str], has_trailing_space: bool) -> list[str]:
        spec = COMMANDS.get(cmd_name, {})
        choices = self._parse_enum_choices_from_args_hint(str(spec.get("args_hint", "") or ""))
        if not choices:
            return []
        if len(parts) > 2:
            return []
        if len(parts) == 1:
            return choices if has_trailing_space else []
        arg_prefix = "" if has_trailing_space else str(parts[1] or "").strip().lower()
        if has_trailing_space and str(parts[1] or "").strip().lower() in {c.lower() for c in choices}:
            return []
        if not arg_prefix:
            return choices
        return [choice for choice in choices if choice.lower().startswith(arg_prefix)]

    _ARG_CACHE_TTL = 5.0
    _DYNAMIC_ARG_COMMANDS = ("open", "init", "cast", "remove", "reset", "load")

    def _cached_rows(self, key: str, build) -> list[tuple[str, str]]:
        """Per-keystroke completion must not rescan ~/.worldlines each time
        (list_saved_games is ~0.3 s cold): remember rows for a few seconds."""
        import time

        cache = getattr(self, "_arg_rows_cache", None)
        if cache is None:
            cache = self._arg_rows_cache = {}
        now = time.monotonic()
        hit = cache.get(key)
        if hit and now - hit[0] < self._ARG_CACHE_TTL:
            return hit[1]
        try:
            rows = list(build())
        except Exception:  # noqa: BLE001 — completion never breaks typing
            rows = []
        cache[key] = (now, rows)
        return rows

    def _sugg(self, key: str, **fmt: Any) -> str:
        """Suggestion vocabulary in the UI language (「换语言
        之后 open cast init 的 suggestion 还是中文」)."""
        from neonrp.tui.i18n import get_message

        text = get_message(getattr(self, "ui_locale", "zh"), key)
        return text.format(**fmt) if fmt else text

    def _argument_rows(self, cmd_name: str) -> list[tuple[str, str]]:
        """``(value, note)`` candidates for a command's first argument."""
        loc = getattr(self, "ui_locale", "zh")

        def open_rows():
            from neonrp.worlds import list_saved_games, list_worlds

            rows = [(g["dir_name"], f"{g.get('display_name', '')} · {self._sugg('sugg.save')} {g.get('mtime_display', '')}".strip()) for g in list_saved_games()]
            rows += [(w["id"], f"{w.get('display_name', '')} · {self._sugg('sugg.world')}") for w in list_worlds(locale=loc)]
            return rows

        def world_names():
            from neonrp.worlds import list_worlds

            return [(w["id"], f"{w.get('display_name', '')} · {self._sugg('sugg.exists', id=w['id'])}") for w in list_worlds(locale=loc)]

        def cast_rows():
            from neonrp.core.souls import list_souls

            here = {sid for _n, sid, _p in self._channel_targets()}
            present, library, draft = self._sugg("sugg.present"), self._sugg("sugg.library"), self._sugg("sugg.draft")
            rows = []
            for s in list_souls(loc):
                sid = str(s.get("sid") or "")
                if not sid:
                    continue
                rows.append((sid, f"{s.get('display_name', '')} · {library}" + (f" · {present}" if sid in here else "")))
            drafts = self.root / ".neonrp" / "soul-drafts"
            if drafts.is_dir():
                rows += [(d.name, draft + (f" · {present}" if d.name in here else "")) for d in sorted(drafts.iterdir()) if d.is_dir()]
            return rows

        def world_souls():
            here = self._sugg("sugg.in_room")
            return [(sid, f"{name}" + (f" · {here}" if present else "")) for name, sid, present in self._channel_targets()]

        def load_rows():
            from neonrp.commands.save import list_loadable_save_snapshots
            from neonrp.worlds import list_saved_games

            rows = [(g["dir_name"], f"{g.get('display_name', '')} · {self._sugg('sugg.save')} {g.get('mtime_display', '')}".strip()) for g in list_saved_games()]
            for snap in list_loadable_save_snapshots(self.root):
                sid = str(snap.get("save_id") or "")
                if not sid:
                    continue
                note = " · ".join(str(snap.get(k)) for k in ("name", "created", "branch", "head_event") if snap.get(k))
                rows.append((sid, note or self._sugg("sugg.snapshot")))
            return rows

        builders = {"open": open_rows, "init": world_names, "cast": cast_rows, "remove": world_souls, "reset": world_souls, "load": load_rows}
        build = builders.get(cmd_name)
        return self._cached_rows(f"{cmd_name}:{loc}", build) if build else []

    def _dynamic_argument_suggestions(self, cmd_name: str, prefix: str) -> list[tuple[str, str]]:
        p = prefix.strip().lower()
        out: list[tuple[str, str]] = []
        for value, note in self._argument_rows(cmd_name):
            if p and not (value.lower().startswith(p) or note.lower().startswith(p) or p in value.lower() or p in note.lower()):
                continue
            out.append((f"[cyan]/{cmd_name}[/] [magenta]{value}[/] [dim]{note}[/]", f"/{cmd_name} {value}"))
        return out

    @staticmethod
    def _format_argument_suggestions(command: str, args: list[str]) -> list[tuple[str, str]]:
        suggestions: list[tuple[str, str]] = []
        for arg in args:
            suggestions.append((f"[cyan]/{command}[/] [magenta]{arg}[/]", f"/{command} {arg}"))
        return suggestions

    def _update_slash_suggestions(self, value: str) -> None:
        """Refresh the suggestion panel: `/` commands, or `@` / `#` channels."""
        suggestions = self._compute_slash_suggestions(value)
        if not suggestions:
            suggestions = self._compute_channel_suggestions(value)
        if not suggestions and self.mode == "play":  # `@` / `#` inside the line: people · places and things
            from neonrp.tui import play_hints as H

            suggestions = H.token_rows(H.menu(getattr(self, "root", None)), value, getattr(self, "ui_locale", "zh") or "zh")
        if not suggestions:
            self._hide_slash_suggestions()
            return

        self._slash_suggestions = suggestions
        if self._slash_selected_index >= len(suggestions):
            self._slash_selected_index = 0
        self._render_slash_suggestions()

    def _render_slash_suggestions(self) -> None:
        """Render slash suggestions panel."""
        panel = self.query_one("#slash-suggestions", Static)
        lines: list[str] = []
        total = len(self._slash_suggestions)
        max_visible = self._MAX_VISIBLE_SLASH_SUGGESTIONS
        if total <= max_visible:
            start = 0
            end = total
        else:
            start = max(0, min(self._slash_selected_index - (max_visible // 2), total - max_visible))
            end = start + max_visible

        for idx, (label, _) in enumerate(self._slash_suggestions[start:end], start=start):
            prefix = "[bold]>[/] " if idx == self._slash_selected_index else "  "
            lines.append(f"{prefix}{label}")
        if total > 0:
            if total > max_visible:
                lines.append(
                    f"[dim]{self._slash_selected_index + 1}/{total} · "
                    "↑↓ select · Tab complete · Enter run · Esc close[/]"
                )
            elif total > 1:
                lines.append("[dim]↑↓ select · Tab complete · Enter run · Esc close[/]")
        panel.update("\n".join(lines))
        panel.add_class("visible")

    def _hide_slash_suggestions(self) -> None:
        """Hide slash suggestions panel."""
        self._slash_suggestions = []
        self._slash_selected_index = 0
        panel = self.query_one("#slash-suggestions", Static)
        panel.remove_class("visible")
        panel.update("")

    def _move_slash_selection(self, delta: int) -> None:
        """Move selected suggestion up/down."""
        if not self._slash_suggestions:
            return
        self._slash_selected_index = (self._slash_selected_index + delta) % len(self._slash_suggestions)
        self._render_slash_suggestions()

    def _get_selected_slash_completion(self) -> str | None:
        """Return completion text for selected suggestion."""
        if not self._slash_suggestions:
            return None
        return self._slash_suggestions[self._slash_selected_index][1]

    _hint_tip_shown = False

    def _refresh_play_hints(self, fresh: bool = False) -> None:
        """The quick bar from the engine's menu; the one-line tip the first time it shows in this session."""
        from neonrp.tui import play_hints as H
        from neonrp.tui.options_bar import QuickBar

        if fresh:
            H.invalidate()
        playing = self.mode == "play"
        try:
            bar = self.query_one("#quick-bar", QuickBar)
        except Exception:  # noqa: BLE001 — not mounted
            return
        items = H.quick(H.menu(getattr(self, "root", None))) if playing else []
        bar.set_items(items, show=playing)
        if items and not self._hint_tip_shown:
            self._hint_tip_shown = True
            try:
                self.query_one("#conversation-view", ConversationView).write(f"[dim]{escape(self._sugg('hint.tip'))}[/]\n")
            except Exception:  # noqa: BLE001
                pass

    def _quick_insert(self, text: str) -> None:
        """A quick-bar word into the input (a skill starts the line; a person / a thing joins it), then focus."""
        try:
            inp = self.query_one("#message-input", Input)
        except Exception:  # noqa: BLE001
            return
        cur = (inp.value or "").strip()
        if text.startswith(("/", "[skill ")):
            value = f"{text} {cur}".rstrip() + " "
        else:
            value = f"{cur} {text} ".lstrip()
        self._set_input_text(value)
        inp.focus()

    def _set_input_text(self, value: str) -> None:
        """Set input text without re-entering change handlers."""
        input_widget = self.query_one("#message-input", Input)
        self._suppress_input_change = True
        input_widget.value = value
        input_widget.cursor_position = len(value)

    def _push_input_history(self, text: str) -> None:
        """Store submitted input in history."""
        normalized = text.strip()
        if not normalized:
            return
        self._input_history.append(normalized)
        self._history_index = None
        self._history_draft = ""

    def _navigate_input_history(self, direction: int) -> bool:
        """Navigate input history; direction -1 for up, +1 for down."""
        if not self._input_history:
            return False

        input_widget = self.query_one("#message-input", Input)

        if direction < 0:
            if self._history_index is None:
                self._history_draft = input_widget.value
                self._history_index = len(self._input_history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
            self._set_input_text(self._input_history[self._history_index])
            return True

        if self._history_index is None:
            return False

        if self._history_index < len(self._input_history) - 1:
            self._history_index += 1
            self._set_input_text(self._input_history[self._history_index])
        else:
            self._history_index = None
            self._set_input_text(self._history_draft)
            self._history_draft = ""
        return True

    def _ensure_verbose_log_path(self) -> Path | None:
        """Ensure debug log file path exists when verbose mode is enabled."""
        if self._verbose_log_path:
            return self._verbose_log_path
        try:
            log_dir = get_neonrp_dir(self.root) / "logs" / "tui"
            log_dir.mkdir(parents=True, exist_ok=True)
            branch = self.session.branch if self.session else (self.branch or "main")
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self._verbose_log_path = log_dir / f"debug_{stamp}_{branch}.jsonl"
            return self._verbose_log_path
        except Exception:
            return None

    def _append_verbose_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Append one verbose debug event to JSONL log."""
        if not self.verbose:
            return
        path = self._ensure_verbose_log_path()
        if not path:
            return
        event = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event": event_type,
            "payload": payload or {},
        }
        try:
            line = json.dumps(event, ensure_ascii=False)
            with self._verbose_lock:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            pass

    def _write_verbose_line(self, message: str) -> None:
        """Write a one-line verbose status message to conversation view."""
        if not self.verbose:
            return
        try:
            view = self.query_one("#conversation-view", ConversationView)
            view.write(f"[dim][verbose][/dim] {message}\n")
        except Exception:
            pass

    def _set_verbose_enabled(self, enabled: bool, announce: bool = True) -> None:
        """Enable/disable verbose mode and announce status."""
        if enabled:
            self.verbose = True
            log_path = self._ensure_verbose_log_path()
            self._append_verbose_event("verbose_enabled", {"path": str(log_path) if log_path else ""})
            if announce:
                if log_path:
                    self._write_verbose_line(f"Verbose mode enabled. Log: {log_path}")
                else:
                    self._write_verbose_line("Verbose mode enabled. Log file unavailable.")
            return

        if self.verbose:
            self._append_verbose_event("verbose_disabled", {})
        self.verbose = False
        if announce:
            try:
                view = self.query_one("#conversation-view", ConversationView)
                view.write("[dim]Verbose mode disabled.[/]\n")
            except Exception:
                pass

    def _verbose_turn_context(self, text: str) -> dict[str, Any]:
        """Collect safe debug context for an outgoing turn."""
        session = self.session
        context: dict[str, Any] = {
            "input_chars": len(text),
            "input_preview": text[:240],
            "branch": session.branch if session else (self.branch or "main"),
            "mode": session.mode if session else "build",
            "agent": session.agent_id if session else self._get_default_agent(),
            "message_count": len(session.messages) if session else 0,
        }
        try:
            provider_cfg = self._get_effective_provider_config()
            context.update(
                {
                    "provider": provider_cfg.provider,
                    "model": provider_cfg.model,
                    "base_url": provider_cfg.base_url,
                    "api_key_env": provider_cfg.api_key_env,
                    "api_key_configured": bool(provider_cfg.api_key) or self._has_api_credential(provider_cfg),
                }
            )
        except Exception as exc:
            context["provider_resolve_error"] = str(exc)
        return context

    def _cmd_verbose(self, args: list[str]) -> None:
        """Enable/disable verbose debug mode."""
        view = self.query_one("#conversation-view", ConversationView)
        if not args:
            self._set_verbose_enabled(True, announce=True)
            return

        action = args[0].strip().lower()
        if action in {"on", "enable", "enabled", "true", "1"}:
            self._set_verbose_enabled(True, announce=True)
            return
        if action in {"off", "disable", "disabled", "false", "0"}:
            self._set_verbose_enabled(False, announce=True)
            return
        if action in {"status", "show"}:
            status = "enabled" if self.verbose else "disabled"
            if self.verbose:
                log_path = self._verbose_log_path if self._verbose_log_path else self._ensure_verbose_log_path()
                view.write(f"[dim]Verbose mode: {status}. Log: {log_path}[/]\n")
            else:
                view.write(f"[dim]Verbose mode: {status}. Use /verbose on to enable.[/]\n")
            return

        view.write("[yellow]Usage: /verbose [on|off|status][/]\n")

    def _cmd_mode(self, args: list[str]) -> None:
        """Switch conversation mode in place (M31 A1 — build ↔ play).

        The switch has to move BOTH halves or the surface lies about
        itself: the engine half (`session.mode` — system prompt, write
        permissions, multi-agent routing) and the app half (`self.mode`
        — which reads as the mode everywhere outside the session, e.g.
        the scene-imagegen gate). Before M31 only the engine half moved,
        so `/mode play` left the status line reading "play" while the
        transcript stayed on build's semantics.

        Sandbox stays accepted but unadvertised: it is engine-internal
        plumbing (sub-agents dry-running proposals), not a mode a player
        switches into.
        """
        view = self.query_one("#conversation-view", ConversationView)

        if not args:
            view.write(f"[yellow]Current mode: {self.session.mode if self.session else self.mode}[/]\n")
            view.write("Usage: /mode build|play\n")
            return

        new_mode = args[0].lower()
        if new_mode not in ("build", "sandbox", "play"):
            view.write(f"[red]Invalid mode: {new_mode}. Use: build or play[/]\n")
            return

        self._apply_mode(new_mode)
        view.write(f"[green]Switched to {new_mode} mode[/]\n")

    def _apply_mode(self, new_mode: AppMode) -> None:
        """Move every mode-derived surface to `new_mode`. Pure state
        transition — safe to call on an unmounted app (each widget
        lookup is guarded), which is what the unit tests drive."""
        # Engine half.
        if self.session:
            self.session.set_mode(new_mode)
        # App half. Nothing else writes self.mode after __init__, so a
        # stale value here is what silently split the two worlds.
        self.mode = new_mode

        # M31: swap the furniture. Play shows the world as it looks now;
        # build shows what it is made of. Both were composed at mount, so
        # this is a visibility flip, not a rebuild.
        self._apply_mode_chrome(new_mode)

        # Presentation half. Mirrors the on_mount seeding exactly:
        # play folds narration and hides raw trace (L2), build shows the
        # tool calls the author is there to inspect (L3). The layer is app
        # state, so it moves whether or not a view is mounted.
        layer = 2 if new_mode == "play" else 3
        self._semantic_layer = layer
        try:
            input_area = self.query_one("#input-area", InputArea)
            input_area.set_mode(new_mode)
        except Exception:  # noqa: BLE001 — unmounted app / no input area
            pass
        try:
            view = self.query_one("#conversation-view", ConversationView)
            view.set_display_mode(new_mode)
            view.set_semantic_mode(str(new_mode))
            view.set_semantic_layer(layer)
        except Exception:  # noqa: BLE001 — unmounted app / no view
            pass
        try:
            self._refresh_status(include_event_count=False)
        except Exception:  # noqa: BLE001 — status line is cosmetic
            pass

    def _apply_mode_chrome(self, mode: AppMode) -> None:
        """Show the furniture that belongs to `mode`, hide the other set.

        Guarded per widget: this runs on unmounted apps in tests, and a
        missing panel must never stop the mode from switching.
        """
        playing = mode == "play"
        try:
            self.call_later(self._refresh_play_hints)  # the quick bar comes and goes with play (10-23)
        except Exception:  # noqa: BLE001 — unmounted (tests)
            pass
        for wid, visible in (
            ("#play-stage", playing),
            # The characters live in the right column now (Agent view, lifecycle beside each name)
            ("#character-status-lane", False),
            ("#status-side", playing),
            ("#build-stage", not playing),
        ):
            try:
                self.query_one(wid).display = visible
            except Exception:  # noqa: BLE001 — unmounted / absent
                pass
        # PortraitPanel re-shows itself on every repaint (it sets
        # `display = True` in __init__ and again in update_for/show_image),
        # so a plain display flip would be undone by the next scene refresh.
        # Its own set_hidden() is the switch that sticks.
        try:
            panel = self.query_one("#portrait-panel", PortraitPanel)
            panel.set_hidden(not playing)
        except Exception:  # noqa: BLE001 — absent / older widget
            pass
        # 任务 A1: the tabs only mean something while playing. Coming back to
        # play restores the tab that was open; leaving play brings the
        # transcript back for build, whatever tab was open.
        if playing:
            self._set_play_tab(getattr(self, "_play_tab", "chat") or "chat", mode=mode)
        else:
            # (The ask_user inline panel manages its own visibility — forcing
            # it on here stole ten rows from the transcript in build mode.)
            try:
                self.query_one("#conversation-view").display = True
            except Exception:  # noqa: BLE001
                pass
            try:
                self.query_one("#scene-panel", PortraitPanel).set_hidden(True)
            except Exception:  # noqa: BLE001
                pass
        # Point the tree at this world when build comes forward (harmless
        # to repeat; the tree only re-reads when the path actually changes).
        if not playing:
            try:
                self.query_one("#build-stage", BuildStage).set_root(self.root)
            except Exception:  # noqa: BLE001 — unmounted / absent
                pass

    def _cmd_cast(self, args: list[str]) -> None:
        """Cast a soul into THIS world (mode-aware placement).

        Form depends on the world's play mode: orchestrator → flatten into
        game/npc/<id>.json; multi-agent → souls/<sid>-<iid>/ +
        playthrough.json. `/cast <soul> [npc|player]`.
        """
        view = self.query_one("#conversation-view", ConversationView)
        if not args:
            view.write("Usage: /cast <soul> [npc|player]\n")
            view.write(
                "[dim]Casts a soul into this world. orchestrator → game/npc/ · "
                "multi-agent → playthrough.[/]\n"
            )
            return

        soul_token = args[0]
        as_role = (
            args[1].lower()
            if len(args) > 1 and args[1].lower() in ("npc", "player")
            else "npc"
        )
        try:
            from neonrp.core.placement import (
                PlacementError,
                project_avatar_multiagent,
                project_avatar_orchestrator,
                project_soul_as_npc,
                project_soul_multiagent,
                resolve_soul_dir,
            )

            mode = get_router_execution_mode(self.root)
            soul_dir = resolve_soul_dir(soul_token)
            if as_role == "player":
                if mode == "orchestrator":
                    target = str(project_avatar_orchestrator(self.root, soul_dir))
                else:
                    ref = project_avatar_multiagent(self.root, soul_dir)
                    target = f"playthrough player '{ref.pid}'"
            else:
                if mode == "orchestrator":
                    target = str(
                        project_soul_as_npc(self.root, soul_dir, overwrite=True)
                    )
                else:
                    ref = project_soul_multiagent(
                        self.root, soul_dir, role="npc", force=True
                    )
                    target = f"souls/{ref.sid}-{ref.instance_id}"
            view.write(
                f"[green]Cast {soul_token} as {as_role} ({mode}) → {target}[/]\n"
            )
        except PlacementError as exc:
            view.write(f"[red]{exc}[/]\n")
        except Exception as exc:  # noqa: BLE001 — surface any cast failure in-TUI
            view.write(f"[red]cast failed: {exc}[/]\n")

    # ── TODO #3 · 点角色名进它的 context ───────────────────────────────
    def on_character_status_lane_soul_picked(self, message: "CharacterStatusLane.SoulPicked") -> None:
        self.open_soul_context(message.iid)

    def _cmd_who(self, args: list[str]) -> None:
        """`/who <角色>` 进它的 context;不带参数弹在场名册。"""
        if args:
            self.open_soul_context(" ".join(args))
            return
        snap = getattr(self, "_soul_status_snapshot", None) or {}
        options = [(str(info.get("name") or iid), iid) for iid, info in ordered_soul_rows(snap)]
        if not options:
            try:
                view = self.query_one("#conversation-view", ConversationView)
                view.write(f"[dim]{get_message(self.ui_locale, 'soul.ctx.nobody')}[/]\n")
            except Exception:
                pass
            return

        def picked(iid: str | None) -> None:
            if iid:
                self.open_soul_context(iid)

        self.push_screen(
            ChoicePickerScreen(get_message(self.ui_locale, "soul.ctx.pick_title"), options, hint=get_message(self.ui_locale, "soul.ctx.pick_hint")),
            picked,
        )

    def open_soul_context(self, token: str) -> None:
        """Team-mode style: the character's own context screen (progress /
        memory / thread), `t` to talk to it, an input to act as it."""
        from neonrp.core.soul_context import build_soul_context
        from neonrp.tui.soul_context import SoulContextScreen

        root = getattr(self, "root", None)
        if root is None:
            return
        try:
            ctx = build_soul_context(Path(root), token)
        except Exception as exc:  # noqa: BLE001
            ctx = {"ok": False, "error": str(exc)[:200]}
        if not ctx.get("ok"):
            try:
                view = self.query_one("#conversation-view", ConversationView)
                view.write(f"[yellow]{get_message(self.ui_locale, 'soul.ctx.unknown_soul')}: {ctx.get('error', token)}[/]\n")
            except Exception:
                pass
            return

        def engaged(out: dict[str, Any]) -> None:
            try:
                view = self.query_one("#conversation-view", ConversationView)
            except Exception:
                return
            name = out.get("name") or ctx.get("name")
            if out.get("ok"):
                view.write(f"[cyan]「{name}」[/]{out.get('digest', '')}\n")
                if out.get("intended_action"):
                    view.write(f"[dim]→ {out['intended_action']}[/]\n")
            else:
                view.write(f"[yellow]({name}: {out.get('error', '?')})[/]\n")

        def done(result: tuple[str, str] | None) -> None:
            if not result:
                return
            action, _iid = result
            if action == "talk":
                try:
                    box = self.query_one("#message-input", Input)
                    box.value = f"@{ctx.get('name')} "
                    box.cursor_position = len(box.value)
                    box.focus()
                except Exception:
                    pass

        self.push_screen(SoulContextScreen(ctx, root=Path(root), locale=self.ui_locale, on_engaged=engaged), done)

    def _cmd_list_souls(self) -> None:
        """`/cast` 不带参数 —— 谁已经在了,以及能请进来的角色有哪些。

        没有这一屏,`/cast <角色>` 就要求你先知道名字,而你根本没地方看到它。
        跟着仓里既有的习惯(`/load` 不带参数就列存档):不带参数 = 给我看菜单,
        并且弹一个选单,选了就请进来。
        """
        view = self.query_one("#conversation-view", ConversationView)

        here: dict[str, str] = {}
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.root)
            if pt is not None:
                here = {ref.sid: ref.instance_id for ref in pt.souls}
        except Exception:  # noqa: BLE001 — 世界没绑 playthrough 也要能列
            pass

        # 先答「谁已经在这个世界里」—— 从世界自己的 souls/ 读,而不是拿
        # 角色库去对花名册:`/create` 造出来直接入世的角色不在库里,只对库
        # 会让刚建好的人整个消失(「找不到 cast 一览」)。
        present = self._world_cast()
        if present:
            view.write("[bold]此刻在这个世界里[/]\n")
            for name, sid, where in present:
                tail = f"  [dim]{where}[/]" if where else ""
                view.write(f"  [#18FF82]{name}[/]  [dim]{sid}[/]{tail}\n")
            view.write("\n")

        rows: list[tuple[str, str, str, str]] = []  # (标签, sid, 来源, 状态)

        # build 期写出来、还没入世的草稿:它们是最可能想请进来的。
        drafts = self.root / ".neonrp" / "soul-drafts"
        if drafts.is_dir():
            for d in sorted(p for p in drafts.iterdir() if p.is_dir()):
                rows.append((d.name, d.name, "草稿", "已在场" if d.name in here else ""))

        try:
            from neonrp.core.souls import list_souls

            for soul in list_souls(self.ui_locale):
                sid = str(soul.get("sid") or "")
                if not sid or any(r[1] == sid for r in rows):
                    continue
                # 库里的 display_name 常常是导入时攒出来的长串
                # (`main_august-<hash>_spec_v2 (艾琳娜)`),而且好几个不同的
                # sid 会显示成同一个中文名。列表要能让人**分辨**,所以取
                # 括号里的本地名做主标,并且始终把 sid 亮出来——sid 才是
                # `/new` 真正要用的那个词。
                raw = str(soul.get("name_local") or soul.get("display_name")
                          or soul.get("name") or sid).strip()
                if "(" in raw and raw.endswith(")"):
                    raw = raw.rsplit("(", 1)[1].rstrip(")").strip() or raw
                label = f"{raw}  [dim]{sid}[/]" if raw != sid else sid
                rows.append((label, sid, "角色库", "已在场" if sid in here else ""))
        except Exception:  # noqa: BLE001 — 没有库也不该让这条命令失败
            pass

        if not rows:
            view.write(
                "[yellow]还没有可以请进来的角色。[/]\n"
                "[dim]用 /create <名字> 造一个 —— 在 build 模式里,交给 agent 写。[/]\n"
            )
            return

        view.write("[bold]可以请进这个世界的角色[/]\n")
        for label, _sid, source, state in rows:
            mark = f"  [dim]· {state}[/]" if state else ""
            view.write(f"  [#18FF82]{label}[/]  [dim]{source}[/]{mark}\n")
        view.write("[dim]用 /cast <名字> 请进来 · /remove <名字> 请出去。[/]\n")

        # 选单:选了就是 `/cast <sid>`。已在场的不列 —— 再请一次没有意义。
        options: list[tuple[str, str]] = []
        for label, sid, source, state in rows:
            if state:
                continue
            plain = label.replace("[dim]", "").replace("[/]", "")
            options.append((f"{plain}  · {source}", sid))
        if not options:
            return

        def on_selected(sid: str | None) -> None:
            if sid:
                self._cmd_cast([sid])

        self.push_screen(
            ChoicePickerScreen("请谁进来?", options, hint="↑↓ 选 · Enter 请进来 · Esc 先不"),
            on_selected,
        )

    def _world_cast(self) -> list[tuple[str, str, str]]:
        """这个世界里的角色:(名字, sid, 所在)。

        真相在 `souls/<sid>-<iid>/`(multi-agent)——花名册只列 sid,名字
        与位置得回到各自的文件夹里读。orchestrator 世界的 NPC 是扁平的
        `game/npc/*.json`,也一并列上,否则那类世界这一栏永远是空的。
        """
        out: list[tuple[str, str, str]] = []
        souls_dir = self.root / "souls"
        if souls_dir.is_dir():
            for d in sorted(p for p in souls_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
                identity = self._read_json_quiet(d / "soul.json")
                run_state = self._read_json_quiet(d / "run_state.json")
                sid = str(identity.get("sid") or run_state.get("sid") or d.name.split("-")[0])
                name = str(identity.get("name_local") or identity.get("name") or sid)
                out.append((name, sid, str(run_state.get("location") or "")))
        if out:
            return out
        npc_dir = self.root / "game" / "npc"
        if npc_dir.is_dir():
            for f in sorted(npc_dir.glob("*.json")):
                data = self._read_json_quiet(f)
                if data.get("name"):
                    out.append((str(data["name"]), str(data.get("id") or f.stem), str(data.get("location") or "")))
        return out

    @staticmethod
    def _read_json_quiet(path: Path) -> dict:
        try:
            import json as _json

            data = _json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _cmd_open(self, args: list[str], options: dict[str, str] | None = None) -> None:
        """`/open [世界|存档]` —— 一条命令回答「我能玩什么、接着玩哪个」。

        取代 `/worlds` `/worldlines` `/continue` 三条。它们各自只答了一半,
        而且 `/worlds` 其实并不「打开」世界 —— 它把模板 scaffold 进**当前**
        工作区(破坏性的 `game new`),名字和行为对不上,还要弹一个模态窗。

        不带参数 = 给我看菜单(与 `/cast` `/load` 同一个习惯:命令自己会
        告诉你有什么可选,不用先背 id)。

        打开**世界**= 开一局新的(`~/.worldlines/plays/<世界>-<时间>`),
        世界库里的源永远不被直接玩 —— 与 launcher 一致(world/run 分离)。
        `--new` 在已有存档时也强制开新局;`--build` 打开自己造的世界的
        **源**进工坊(接着 `/init` 之后的活)。
        """
        view = self.query_one("#conversation-view", ConversationView)
        if not args:
            self._list_openable(view)
            self._pick_openable()
            return
        options = options or {}

        target = args[0].strip()
        match = self._resolve_openable(
            target, prefer_world=bool(options.get("new") or options.get("build"))
        )
        if match is None:
            view.write(
                f"[red]没有叫「{target}」的世界或存档[/]\n"
                "[dim]敲 /open 看看有哪些。[/]\n"
            )
            return

        kind, name, path = match
        mode: AppMode | None = None
        if kind == "template":
            try:
                from neonrp import template as TP

                from neonrp.tui.i18n import resolve_locale

                path = TP.new_run(Path(path), model_ref=self._current_model_ref(), lang=resolve_locale())
            except Exception as exc:  # noqa: BLE001 — 开局失败要说清楚
                view.write(f"[red]开不了新局:{exc}[/]\n")
                return
            mode = "play"
            view.write(f"[dim]从模板开了新一局:{Path(path).name}[/]\n")
        elif kind == "world":
            if options.get("build"):
                if not Path(path).is_dir():
                    view.write(f"[red]「{name}」是内置世界,没有可编辑的源;/init 一个自己的。[/]\n")
                    return
                mode = "build"
            else:
                try:
                    path = self._start_new_run(target)
                except Exception as exc:  # noqa: BLE001 — 开局失败要说清楚
                    view.write(f"[red]开不了新局:{exc}[/]\n")
                    return
                mode = "play"
                view.write(f"[dim]新一局:{Path(path).name}[/]\n")

        if Path(path) == Path(self.root):
            view.write(f"[yellow]已经在「{name}」里了[/]\n")
            return

        # root 在构造时定死、全程不重绑(session/引擎/控件全挂在它上面),
        # 所以换世界不是改一个字段,而是**换一局**:退出当前 app,由
        # `run_tui` 用新 root 起一个 —— 与 launcher 的交接是同一套路子。
        self.reopen_request = _ReopenRequest(
            root=Path(path),
            continue_session=(kind == "save"),
            mode=mode,
        )
        view.write(f"[green]正在打开「{name}」…[/]\n")
        self.exit()

    def _start_new_run(self, world_id: str) -> Path:
        """一局新的:内置世界从打包模板 scaffold,自己的世界从库里拷一份。
        两条路都落在 PLAYS_HOME,源不动。

        新局用**现在这个世界在用的模型**。之前 scaffold 取 `list_presets()[0]`,
        而那一格在装了 `claude` CLI 的机器上是 Claude Code 虚拟预设 = stub,
        于是 `/open` 开出来的局一开口就是「Stub provider active」。
        """
        from neonrp.worlds import WORLDS, instantiate_run, scaffold_builtin_run

        ref = self._current_model_ref()
        if world_id in WORLDS:
            return scaffold_builtin_run(world_id, model_ref=ref)
        return instantiate_run(world_id, model_ref=ref)

    def _current_model_ref(self) -> str | None:
        """这个世界正在用的模型名;stub 不算(那不是「在用」,是没配)。"""
        try:
            from neonrp.core.config import load_config

            ref = str(load_config(self.root).llm.model_ref or "").strip()
        except Exception:  # noqa: BLE001 — 读不到就交给默认规则
            return None
        return ref if ref and ref != "stub" else None

    def _cmd_vault(self, args: list[str]) -> None:
        """`/vault` —— 一键:投影 → 登记 → 在 Obsidian 里打开(落在画布上)。

        不带参数就是全套;`/vault build` 只投影不开 app(远程终端、或者
        不想被切走窗口时)。Obsidian 在跑而 vault 是新登记的,会替你重启
        它 —— 它只在启动时读 vault 列表,这一步省不掉(core/obsidian.py)。
        """
        view = self.query_one("#conversation-view", ConversationView)
        from neonrp.core.vault import VAULT_DIRNAME, project_vault

        report = project_vault(self.root)
        vault_dir = self.root / VAULT_DIRNAME
        view.write(f"[green]vault {report.headline()}[/]  [dim]{vault_dir}[/]\n")
        if args and args[0].strip().lower() == "build":
            return
        try:
            from neonrp.core.obsidian import open_vault

            for line in open_vault(vault_dir).lines():
                view.write(f"[dim]{line}[/]\n")
        except Exception as exc:  # noqa: BLE001 — 开不开 app 不该炸 TUI
            view.write(f"[red]打不开 Obsidian:{exc}[/]\n")

    def _cmd_init(self, args: list[str]) -> None:
        """`/init [世界]` —— 用一个世界开**新局**(「init 应该
        是读取一个新的世界,load 才是读取存档」)。

        - `/init stone-ford` / `/init 石津镇`:那个世界的一局新的,进 play
          (= `/open <世界> --new`);
        - `/init`:选单 —— 开新局(世界库)/ 从零建一个空白世界;
        - `/init <不是世界的名字> [设定]`:当作从零建空白世界(进它的工坊)。
        读存档是 `/load`(快照)与 `/open <存档>`(接着玩)。
        """
        view = self.query_one("#conversation-view", ConversationView)
        if not args or not args[0].strip():
            self._pick_new_world()
            return
        token = args[0].strip()
        world_id = self._resolve_world_token(token)
        if world_id:
            self._cmd_open([world_id], {"new": "true"})
            return
        view.write(f"[dim]没有叫「{token}」的世界,从零建一个空白世界。[/]\n")
        self._init_blank_world(token, " ".join(args[1:]).strip())

    def _resolve_world_token(self, token: str) -> str | None:
        """A world id or display name from the library → id."""
        try:
            from neonrp.worlds import list_worlds

            worlds = list_worlds(locale=getattr(self, "ui_locale", "en"))
        except Exception:  # noqa: BLE001
            return None
        t = token.strip().lower()
        for w in worlds:
            if str(w.get("id", "")).lower() == t or str(w.get("display_name", "")).strip().lower() == t:
                return str(w["id"])
        return None

    def _pick_new_world(self) -> None:
        """Bare `/init`: which world to start fresh, or build one from scratch."""
        try:
            from neonrp.worlds import list_worlds

            worlds = list_worlds(locale=getattr(self, "ui_locale", "en"))
        except Exception:  # noqa: BLE001
            worlds = []
        options: list[tuple[str, str]] = []
        if worlds:
            options.append(section("── 开新局 ──"))
            for world in worlds:
                options.append((f"{world['display_name']}  ({world['id']})", f"world::{world['id']}"))
            options.append(spacer())
        options.extend(self._template_options())
        options.append(section("── 从零 ──"))
        options.append(("+  建一个空白世界(进工坊)", "blank"))

        def on_selected(value: str | None) -> None:
            if not value:
                return
            if value == "blank":
                self._guide_init()
            elif value.startswith("world::"):
                self._cmd_open([value.split("::", 1)[1]], {"new": "true"})
            elif value.startswith("template::"):
                self._cmd_open(["tpl:" + value.split("::", 1)[1]])

        self.push_screen(
            ChoicePickerScreen("开哪个世界的新局?", options, hint="↑↓ 选 · Enter 开局 · Esc 留在这里"),
            on_selected,
        )

    def _init_blank_world(self, name: str, premise: str = "") -> None:
        """From scratch: a blank world under `~/.worldlines/worlds/<名字>/`,
        then its workshop (build) with the premise as the agent's first words.
        Same principle as `/create`: the command triggers, the agent authors."""
        view = self.query_one("#conversation-view", ConversationView)
        try:
            from neonrp.worlds import create_blank_world

            source = create_blank_world(name, premise=premise, model_ref=self._current_model_ref())
        except Exception as exc:  # noqa: BLE001 — 建不出来要说清楚
            view.write(f"[red]建不出这个世界:{exc}[/]\n")
            return

        brief = f"这是一个刚建好的空白世界,名字叫「{name}」。"
        if premise:
            brief += f"设定:{premise}。"
        brief += (
            "请按 world-game-authoring 的路子,把它从留白写成一个能玩的世界:"
            "先定基调与开局,再补地点、人物与冲突;每一步写进文件。"
        )
        self.reopen_request = _ReopenRequest(
            root=Path(source),
            continue_session=False,
            mode="build",
            startup_commands=[brief],
        )
        view.write(
            f"[green]世界「{name}」已建在 {source}[/]\n"
            "[dim]正在进它的工坊…造好之后 /init 它开新局。[/]\n"
        )

    def _guide_init(self) -> None:
        """裸 `/init`:两问(名字、一句话设定)代替一行用法说明 —— 不带参数
        的命令要**引导**,不是把人打回去背语法。"""
        view = self.query_one("#conversation-view", ConversationView)
        view.write(
            "[dim]/init <名字> [一句话设定] —— 或者直接回答下面两问。[/]\n"
        )

        def got_name(name: str | None) -> None:
            name = (name or "").strip()
            if not name:
                return

            def got_premise(premise: str | None) -> None:
                self._init_blank_world(name, (premise or "").strip())

            self.push_screen(
                TextInputScreen(
                    "一句话设定(可以留空)",
                    hint="例:一座只有猫和一个灯塔守的海岛,雾里有船来。 · Enter 确认 · Esc 跳过",
                ),
                got_premise,
            )

        self.push_screen(
            TextInputScreen("给这个世界起个名字", hint="例:猫岛 · Enter 确认 · Esc 取消"),
            got_name,
        )

    def _pick_openable(self) -> None:
        """裸 `/open` 的选单:存档、世界库、从零建一个。选了就等于敲
        `/open <它>`;Esc 什么都不做(文字清单已经在对话里了)。"""
        from neonrp.worlds import list_saved_games, list_worlds

        try:
            saves = list_saved_games()
        except Exception:  # noqa: BLE001
            saves = []
        try:
            worlds = list_worlds(locale=getattr(self, "ui_locale", "en"))
        except Exception:  # noqa: BLE001
            worlds = []

        options: list[tuple[str, str]] = []
        if saves:
            options.append(section("── 接着玩 ──"))
            for save in saves[:10]:
                name = save.get("display_name") or save.get("dir_name", "?")
                when = save.get("mtime_display", "")
                options.append((f"{name}  {when}  ({save.get('dir_name')})", f"save::{save.get('dir_name')}"))
            options.append(spacer())
        if worlds:
            options.append(section("── 开新局 ──"))
            for world in worlds:
                options.append((f"{world['display_name']}  ({world['id']})", f"world::{world['id']}"))
            options.append(spacer())
        options.extend(self._template_options())
        options.append(section("── 从零 ──"))
        options.append(("+  建一个自己的世界(/init)", "init"))

        def on_selected(value: str | None) -> None:
            if not value:
                return
            if value == "init":
                self._guide_init()
            elif value.startswith("save::"):
                self._cmd_open([value.split("::", 1)[1]])
            elif value.startswith("world::"):
                self._cmd_open([value.split("::", 1)[1]], {"new": "true"})
            elif value.startswith("template::"):
                self._cmd_open(["tpl:" + value.split("::", 1)[1]])

        self.push_screen(
            ChoicePickerScreen("打开哪一个?", options, hint="↑↓ 选 · Enter 打开 · Esc 留在这里"),
            on_selected,
        )

    def _list_openable(self, view: "ConversationView") -> None:
        """存档在前、世界库在后 —— 大多数时候你是要**接着玩**,不是开新的。"""
        from neonrp.worlds import list_saved_games, list_worlds

        try:
            saves = list_saved_games()
        except Exception:  # noqa: BLE001 — 列不出存档不该拦住列世界
            saves = []
        if saves:
            view.write("[bold]存档[/]\n")
            for save in saves[:10]:
                name = save.get("display_name") or save.get("dir_name", "?")
                when = save.get("mtime_display", "")
                mark = "" if save.get("started") else "  [dim](未开始)[/]"
                view.write(f"  [cyan]{save.get('dir_name')}[/]  {name}  [dim]{when}[/]{mark}\n")

        try:
            worlds = list_worlds(locale=getattr(self, "ui_locale", "en"))
        except Exception:  # noqa: BLE001
            worlds = []
        if worlds:
            view.write("\n[bold]世界库[/]\n")
            for world in worlds:
                view.write(
                    f"  [cyan]{world['id']}[/]  {world['display_name']}"
                    f"  [dim]{world.get('desc', '')}[/]\n"
                )

        templates = self._openable_templates()
        if templates:
            view.write("\n[bold]模板[/]\n")
            for tpl in templates:
                tag = f"  [green]{tpl['contract']}[/]" if tpl["contract"] else ""
                view.write(f"  [cyan]tpl:{tpl['id']}[/]  {tpl['title']}{tag}\n")

        if not saves and not worlds and not templates:
            view.write("[yellow]还没有可打开的世界或存档[/]\n")
            return
        view.write(
            "\n[dim]/open <存档>  接着玩 · /open <世界>  开新局 · /open tpl:<模板>  从模板开新局"
            "(--new 强制新局 · --build 进自己世界的工坊)· /init <名字>  从零建一个[/]\n"
        )

    def _resolve_openable(
        self, target: str, *, prefer_world: bool = False
    ) -> tuple[str, str, Path] | None:
        """存档优先于世界库。

        存档目录名是 `<世界id>-<时间戳>`,所以世界 id 是存档名的前缀 ——
        `/open cat-isle` 在两边都有命中时,要的几乎总是**那一局**而不是
        再开一局全新的。`prefer_world` 反过来(`--new` / `--build`)。

        世界命中返回 `("world", 名字, 源目录)`;内置世界没有源,那一格是
        `WORLDS_HOME/<id>`(不存在的路径)—— 调用方开新局时不用它,
        `--build` 时用它的存在与否判断「有没有源可编」。
        """
        from neonrp.worlds import PLAYS_HOME, WORLDS_HOME, list_saved_games, list_worlds

        if target.startswith("tpl:"):  # 模板:世界 × 角色 × 玩法包 × 剧情 × 合约,和内置世界可能同名,所以带前缀
            tid = target[len("tpl:"):]
            hit = next((t for t in self._openable_templates() if t["id"] == tid), None)
            return ("template", hit["title"], Path(hit["dir"])) if hit else None

        try:
            saves = list_saved_games()
        except Exception:  # noqa: BLE001
            saves = []
        try:
            worlds = list_worlds(locale=getattr(self, "ui_locale", "en"))
        except Exception:  # noqa: BLE001
            worlds = []

        world_hit = None
        for world in worlds:
            if world.get("id") == target:
                world_hit = ("world", world.get("display_name", target), WORLDS_HOME / target)
                break
        if prefer_world and world_hit:
            return world_hit

        for save in saves:
            if save.get("dir_name") == target:
                name = save.get("display_name") or target
                return ("save", name, PLAYS_HOME / target)
        # 没有精确命中时,退而求其次:该世界最近的那一局。
        for save in saves:
            dir_name = str(save.get("dir_name", ""))
            if dir_name.startswith(f"{target}-"):
                name = save.get("display_name") or dir_name
                return ("save", name, PLAYS_HOME / dir_name)
        if world_hit is None:  # 不带前缀也认模板 id(没有同名的世界 / 存档时)
            hit = next((t for t in self._openable_templates() if t["id"] == target), None)
            if hit:
                return ("template", hit["title"], Path(hit["dir"]))
        return world_hit

    def _openable_templates(self) -> list[dict[str, str]]:
        """模板库(NEONRP_TEMPLATE_PATH + 仓里的 worldlines/templates):id · 标题 · 合约名(按界面语言)。
        只读 template.json,不跑 lint(lint 要几秒,列表不该等它)。"""
        try:
            from neonrp import template as TP
            from neonrp.template import contract as _contract

            found = TP.discover()
        except Exception:  # noqa: BLE001
            return []
        lang = str(getattr(self, "ui_locale", "zh") or "zh")[:2]

        def pick(v: Any) -> str:
            if isinstance(v, dict):
                return str(v.get(lang) or v.get("zh") or next(iter(v.values()), ""))
            return str(v or "")

        rows: list[dict[str, str]] = []
        for tid, folder in found.items():
            try:
                t = TP.load(folder)
            except Exception:  # noqa: BLE001 — 坏掉的模板不挡别的
                continue
            contract = ""
            if t.play_contract:
                try:
                    contract = pick(_contract.load(t.play_contract).get("title")) or t.play_contract
                except Exception:  # noqa: BLE001
                    contract = t.play_contract
            rows.append({"id": tid, "title": pick((t.card or {}).get("title")) or tid, "contract": contract, "dir": str(folder)})
        return rows

    def _template_options(self) -> list[tuple[str, str]]:
        """选单里的「模板」一节(/open 与 /init 共用)。"""
        templates = self._openable_templates()
        if not templates:
            return []
        out: list[tuple[str, str]] = [section("── 模板 ──")]
        for tpl in templates:
            tag = f"  · {tpl['contract']}" if tpl["contract"] else ""
            out.append((f"{tpl['title']}{tag}  (tpl:{tpl['id']})", f"template::{tpl['id']}"))
        out.append(spacer())
        return out

    def _cmd_import(self, args: list[str]) -> None:
        """`/import <文件>` —— 世界与角色共用一个入口(docs/COMMANDS.md)。

        **按内容分派**:用户手里只有「一个文件」,不该先想清楚它属于哪一类。
        `.zip` 是世界包,酒馆角色卡(PNG/JSON)是角色。分派失败时说清楚我们
        认得哪些,而不是甩一个「未知格式」。

        取代了 `/import sillytavern-card <file>` 与 `/load-world <zip>` 两条。
        """
        view = self.query_one("#conversation-view", ConversationView)
        if not args:
            view.write(
                "[yellow]用法:/import <文件>[/]\n"
                "[dim]世界包(.zip)或酒馆角色卡(.png/.json)都从这里进,"
                "按内容自动分派。[/]\n"
            )
            return

        # `--import-card` 排出来的启动命令仍是 `/import sillytavern-card <文件>`
        # 这个老形状;子命令不再露出,但不能因此打不开(见 test_tui_cli.py)。
        argv = list(args)
        if argv and argv[0] in {"sillytavern-card", "world", "card"}:
            argv = argv[1:]
        if not argv:
            view.write("[red]/import 后面要跟一个文件[/]\n")
            return

        raw = argv[0].strip().strip("'\"")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (self.root / path).resolve()
        if not path.is_file():
            view.write(f"[red]找不到文件:{raw}[/]\n")
            return

        kind = self._classify_import(path)
        if kind == "world":
            self._import_world_zip(path, view)
        elif kind == "card":
            self._import_character_card(path, view)
        else:
            view.write(
                f"[red]认不出这个文件:{path.name}[/]\n"
                "[dim]世界包要是 export 出来的 .zip;角色卡要是酒馆的 "
                "PNG 或 JSON。[/]\n"
            )

    @staticmethod
    def _classify_import(path: Path) -> str:
        """看内容而不是只看后缀 —— 后缀会骗人,而分错类的代价是把一个世界
        当角色导进去。"""
        suffix = path.suffix.lower()
        if suffix == ".zip":
            return "world"
        if suffix == ".png":
            return "card"
        if suffix == ".json":
            # 酒馆卡与世界元数据都可能是 .json,靠字段区分。
            try:
                import json as _json

                data = _json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                return "unknown"
            if isinstance(data, dict) and (
                data.get("name") or data.get("spec") or data.get("data")
            ):
                return "card"
        return "unknown"

    def _import_world_zip(self, path: Path, view: "ConversationView") -> None:
        try:
            from neonrp.core.world_export import load_world_zip

            dest = load_world_zip(path)
        except Exception as exc:  # noqa: BLE001 — 导入失败要说清楚
            view.write(f"[red]世界包导入失败:{exc}[/]\n")
            return
        view.write(
            f"[green]世界已导入:{Path(dest).name}[/]"
            f"[dim]  用 /open 打开它[/]\n"
        )

    def _import_character_card(self, path: Path, view: "ConversationView") -> None:
        """卡 → 完整 soul(而不是扁平实体)。

        走 `card_to_soul`:它跑 `soul-card-authoring` skill 把卡补全成完整的
        soul 包。旧的 `/import sillytavern-card` 产出的是 `game/character/`
        下一个扁平 JSON —— 那不是能独立跑起来的角色。
        """
        view.write(f"[dim]正在把 {path.name} 补全成完整角色…[/]\n")
        try:
            from neonrp.core.config import load_config, resolve_provider
            from neonrp.core.importers.card_to_soul import import_card_to_library
            from neonrp.core.llm import get_adapter_from_config

            llm = get_adapter_from_config(resolve_provider(load_config(self.root)))
            soul_dir = import_card_to_library(path, llm=llm)
        except Exception as exc:  # noqa: BLE001
            view.write(f"[red]角色卡导入失败:{exc}[/]\n")
            return
        sid = Path(soul_dir).name.split("-")[0]
        view.write(
            f"[green]角色已导入:{sid}[/]"
            f"[dim]  用 /cast {sid} 请进这个世界[/]\n"
        )

    def _cmd_create(self, args: list[str]) -> None:
        """`/create [名字]` —— build 侧造一个新角色(薄触发)。

        它**不另起管线**:把意图递给 build agent,与你自己打「新建一个叫 X
        的角色」走同一条路。命令的价值在可发现性——新用户不知道自己可以
        直接说这句话——而不在于提供第二种行为。造东西只有一种行为,
        「命令版和对话版不一样」这种最难查的问题就不会出现。

        在 play 里调用会先切到 build(绿 → 红):这是一次看得见的换挡,
        不是偷偷做一件 build 的事。
        """
        view = self.query_one("#conversation-view", ConversationView)
        name = " ".join(args).strip()

        if self.mode != "build":
            view.write("[dim]造角色属于 build 模式,先切过去。[/]\n")
            self._apply_mode("build")

        if not name:
            view.write(
                "[yellow]用法:/create <名字>[/]\n"
                "[dim]也可以直接说「新建一个叫罗文的铁匠,沉默寡言」"
                "——同一条路,而且能带上更多设定。[/]\n"
            )
            return

        # 递给 agent 的是一句人话,不是一条内部指令:这样它与用户自己打的
        # 那句话在模型眼里没有区别。
        self._submit_user_text(f"新建一个叫{name}的角色,并放进这个世界。")

    def _submit_user_text(self, text: str) -> None:
        """把一句话当作用户输入交给当前会话(薄触发的唯一出口)。"""
        try:
            self._send_message(text)
        except Exception:  # noqa: BLE001 — 触发失败要说出来,不要静默
            view = self.query_one("#conversation-view", ConversationView)
            view.write(f"[red]没能把意图交给 agent,请直接说这句话:{text}[/]\n")

    def _resolve_world_soul(self, token: str):
        """在**这个世界**里找一个角色实例。返回 (soul_dir, SoulRef) 或 None。

        找的是世界里的实例(`souls/<sid>-<iid>/`),不是库里的来源——
        `/remove` 与 `/reset` 动的都是这个世界里的那一份。
        """
        from neonrp.core.playthrough import read_playthrough

        pt = read_playthrough(self.root)
        if pt is None:
            return None
        needle = token.strip().lower()
        for ref in pt.souls:
            if needle in (ref.sid.lower(), ref.instance_id.lower()):
                return self.root / "souls" / f"{ref.sid}-{ref.instance_id}", ref
        return None

    def _cmd_remove_soul(self, args: list[str]) -> None:
        """`/remove <角色>` —— 让角色从这个世界消失。

        `/new` 的逆动作:摘掉花名册条目并移除它在这个世界里的实例。
        **来源不动**(库里或草稿里的那份),所以 `/new` 能把它请回来。
        """
        view = self.query_one("#conversation-view", ConversationView)
        if not args:
            view.write("[yellow]用法:/remove <角色>[/]\n")
            return
        token = args[0]
        found = self._resolve_world_soul(token)
        if found is None:
            view.write(f"[red]这个世界里没有「{token}」。[/]\n")
            return
        soul_dir, ref = found

        try:
            import shutil
            from dataclasses import replace

            from neonrp.core.playthrough import read_playthrough, write_playthrough

            pt = read_playthrough(self.root)
            write_playthrough(
                self.root,
                replace(
                    pt,
                    souls=[s for s in pt.souls if s.instance_id != ref.instance_id],
                    active_souls=tuple(
                        i for i in pt.active_souls if i != ref.instance_id
                    ),
                ),
            )
            if soul_dir.is_dir():
                shutil.rmtree(soul_dir)
        except Exception as exc:  # noqa: BLE001 — surface any failure in-TUI
            view.write(f"[red]移除失败:{exc}[/]\n")
            return
        view.write(
            f"[green]{ref.sid} 已离开这个世界。[/]"
            f"[dim](来源还在,/new {ref.sid} 可以请回来)[/]\n"
        )

    def _cmd_reset_soul(self, args: list[str]) -> None:
        """`/reset <角色>` —— 把角色清回出厂状态。

        抹掉**游玩期长出来的东西**:短期/长期记忆、行动轨迹、运行时状态。
        **著述内容不动**(persona / 背景 / 行为准则)——那是「这个角色是谁」,
        不是「它经历过什么」。
        """
        view = self.query_one("#conversation-view", ConversationView)
        if not args:
            view.write("[yellow]用法:/reset <角色>[/]\n")
            return
        token = args[0]
        found = self._resolve_world_soul(token)
        if found is None:
            view.write(f"[red]这个世界里没有「{token}」。[/]\n")
            return
        soul_dir, ref = found

        # 只清这些:它们都是回合期写出来的。persona/background/rules/agents
        # 是被著述的内容,一个字都不碰。
        volatile = ("short-term-memo", "long-term-memo", "trajectory")
        cleared: list[str] = []
        try:
            for sub in volatile:
                target = soul_dir / sub
                if not target.is_dir():
                    continue
                for path in target.iterdir():
                    if path.is_file():
                        path.unlink()
                        cleared.append(f"{sub}/{path.name}")
            run_state = soul_dir / "run_state.json"
            if run_state.is_file():
                import json as _json

                data = _json.loads(run_state.read_text(encoding="utf-8"))
                for key in ("turn_count", "loop_state"):
                    data.pop(key, None)
                run_state.write_text(
                    _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                cleared.append("run_state.json")
        except Exception as exc:  # noqa: BLE001
            view.write(f"[red]清回出厂失败:{exc}[/]\n")
            return
        view.write(
            f"[green]{ref.sid} 已清回出厂状态({len(cleared)} 项)。[/]"
            f"[dim]它是谁没变,它经历过什么没了。[/]\n"
        )

    def _cmd_clear(self) -> None:
        """Clear conversation history."""
        view = self.query_one("#conversation-view", ConversationView)

        if self.session:
            self.session.clear()

        view.clear()
        view.write("[dim]Conversation history cleared[/]\n")

    def _cmd_mcp(self, args: list[str]) -> None:
        """MCP server management (M11-T6)."""
        view = self.query_one("#conversation-view", ConversationView)
        config = load_config(self.root)

        if not config.mcp_servers:
            view.write("[yellow]No MCP servers configured.[/]\n")
            return

        sub = args[0] if args else "status"

        if sub == "status":
            enabled = {n: c for n, c in config.mcp_servers.items() if c.enabled}
            if not enabled:
                view.write("[yellow]All MCP servers are disabled.[/]\n")
                return

            pool = MCPPool(enabled)
            try:
                results = pool.ensure_started()
                view.write("[bold]MCP Server Status:[/]\n")
                for name, err in results.items():
                    if err:
                        view.write(f"  [red]✖ {name}[/]: {err}\n")
                    else:
                        client = pool.get_started_client(name)
                        tool_count = len(client.list_tools()) if client else 0
                        perm = config.mcp_servers[name].permission
                        view.write(f"  [green]✔ {name}[/]: {tool_count} tools (permission: {perm})\n")
                        if client:
                            for tool in client.list_tools():
                                view.write(f"    [dim]· {tool.name}[/]: {tool.description[:60]}\n")
            finally:
                pool.stop_all()

        elif sub == "restart":
            if len(args) < 2:
                view.write("[yellow]Usage: /mcp restart <server_name>[/]\n")
                return
            server_name = args[1]
            if server_name not in config.mcp_servers:
                view.write(f"[red]Unknown MCP server: {server_name}[/]\n")
                return
            view.write(f"[dim]Restarting MCP server '{server_name}'...[/]\n")
            pool = MCPPool({server_name: config.mcp_servers[server_name]})
            try:
                pool.ensure_started()
                status = pool.get_status(server_name)
                if status and status[0].status == "healthy":
                    view.write(f"[green]✔ Server '{server_name}' restarted successfully.[/]\n")
                else:
                    view.write(f"[red]✖ Server '{server_name}' failed to restart.[/]\n")
            except Exception as exc:
                view.write(f"[red]Error: {exc}[/]\n")
            finally:
                pool.stop_all()

        else:
            view.write(f"[yellow]Unknown subcommand: {sub}. Use status or restart.[/]\n")

    def _cmd_help(self) -> None:
        """Show help."""
        view = self.query_one("#conversation-view", ConversationView)
        from neonrp.tui.commands import format_help

        view.write(format_help(getattr(self, "ui_locale", None)) + "\n")

    def _cmd_stats(self) -> None:
        """Show conversation statistics."""
        view = self.query_one("#conversation-view", ConversationView)
        for line in self._stats_markup().split("\n"):
            view.write(line + "\n")

    def _stats_markup(self) -> str:
        """The conversation's messages and tokens as markup lines — /status usage, in the transcript or its tab."""
        if not self.session:
            return "[yellow]No active session[/]"
        msg_count = len(self.session.messages)
        user_msgs = sum(1 for m in self.session.messages if m.role == "user")
        assistant_msgs = sum(1 for m in self.session.messages if m.role == "assistant")
        tool_msgs = sum(1 for m in self.session.messages if m.role == "tool")
        usage = self.session.total_usage

        lines = [
            "[bold]Conversation Statistics:[/]",
            f"  [cyan]Mode:[/] {self.session.mode}",
            f"  [cyan]Agent:[/] {self.session.agent_id}",
            f"  [cyan]Messages:[/] {msg_count} (user: {user_msgs}, assistant: {assistant_msgs}, tool: {tool_msgs})",
            f"  [cyan]LLM turns:[/] {self.session.total_turns}",
            "  [cyan]Tokens (local est):[/] "
            f"{self._est_prompt_tokens_total + self._est_completion_tokens_total} "
            f"(prompt: {self._est_prompt_tokens_total}, completion: {self._est_completion_tokens_total})",
        ]
        if usage:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            lines.append(f"  [dim]Provider usage:[/] {prompt_tokens + completion_tokens} "
                         f"(prompt: {prompt_tokens}, completion: {completion_tokens})")
        lines.append(f"  [cyan]Files modified:[/] {len(self.session.recent_files)}")
        return "\n".join(lines)

    def _cmd_debug(self, args: list[str]) -> None:
        """Legacy WorldLines debug alias backed by verbose diagnostics."""
        view = self.query_one("#conversation-view", ConversationView)
        if args:
            view.write("[yellow]Usage: /debug[/]\n")
            return
        self._set_verbose_enabled(not self.verbose, announce=True)

    def _cmd_settings(self) -> None:
        """Open the unified settings flow (shared with WorldLines launcher)."""
        from neonrp.tui.settings_flow import SettingsFlow

        flow = SettingsFlow(host=self)
        flow.open_root()

    def _cmd_bridge(self, args: list[str]) -> None:
        """Manage external bridges (Discord, Telegram) at runtime."""
        view = self.query_one("#conversation-view", ConversationView)
        sub = (args[0] if args else "status").lower()

        hub = self._ensure_bridge_hub()
        if hub is None:
            view.write("[red]Bridge subsystem unavailable[/]\n")
            return

        if sub == "status":
            names = hub.list_bridges()
            view.write(f"[bold]Active bridges:[/] {', '.join(names) if names else '(none)'}\n")
            try:
                from neonrp.core.discord_config import get_discord_inline_status, get_discord_settings

                s = get_discord_settings()
                view.write(
                    f"  [cyan]discord[/]: status={get_discord_inline_status()}  "
                    f"autostart={bool(s.get('autostart'))}  "
                    f"channel={s.get('channel_id', '(not set)')}\n"
                )
            except Exception:
                pass
            return

        if sub == "start":
            name = (args[1] if len(args) > 1 else "").strip().lower()
            if name == "discord":
                try:
                    from neonrp.bridges.discord_bridge import build_discord_bridge_from_config

                    bridge = build_discord_bridge_from_config()
                    if bridge is None:
                        view.write("[yellow]Discord config incomplete — run /settings → Discord wizard first.[/]\n")
                        return
                    if "discord" in hub.list_bridges():
                        view.write("[yellow]Discord bridge already running.[/]\n")
                        return
                    hub.register(bridge)
                    err = bridge.last_error()
                    if err:
                        view.write(f"[red]{err}[/]\n")
                    else:
                        view.write("[green]Discord bridge started.[/]\n")
                except Exception as exc:
                    view.write(f"[red]Failed to start discord bridge: {exc}[/]\n")
                return
            view.write(f"[yellow]Unknown bridge: {name}[/]\n")
            return

        if sub == "stop":
            name = (args[1] if len(args) > 1 else "").strip().lower()
            for bridge in list(getattr(hub, "_bridges", [])):
                if getattr(bridge, "name", "") == name:
                    hub.unregister(bridge)
                    view.write(f"[green]Stopped bridge: {name}[/]\n")
                    return
            view.write(f"[yellow]Bridge not running: {name}[/]\n")
            return

        view.write(f"[yellow]Unknown /bridge subcommand: {sub}[/]\n")

    def _step_prompt_text(self, title: str, default: str, on_submit: Callable[[str], None]) -> None:
        """Compatibility shim used by SettingsFlow to pop a TextInputScreen."""
        def handler(value: str | None) -> None:
            on_submit(value or "")

        self.push_screen(TextInputScreen(title, default=default), handler)

    def _cmd_update(self, args: list[str]) -> None:
        """Check / apply product updates (L14 auto-update Phase 1)."""
        view = self.query_one("#conversation-view", ConversationView)
        from neonrp.core import updater

        sub = (args[0] if args else "check").lower()

        if sub == "status":
            mode = updater.detect_install_mode()
            settings = updater.get_update_settings()
            view.write(
                f"  current: {updater.get_current_version()}\n"
                f"  install: {mode.kind} ({mode.detail})\n"
                f"  channel: {settings.get('channel')}\n"
                f"  mode: {updater.launch_mode(settings)} (auto · prompt · notify)\n"
                f"  auto-apply allowed: {mode.allow_auto_apply}\n"
            )
            return

        if sub == "mode":
            if len(args) < 2 or args[1].lower() not in updater.LAUNCH_MODES:
                view.write("[yellow]Usage: /update mode <auto|prompt|notify>[/]\n")
                return
            updater.set_update_settings(mode=args[1].lower())
            view.write(f"[green]update mode set to {args[1].lower()}[/]\n")
            return
        if sub == "channel":
            if len(args) < 2:
                view.write("[yellow]Usage: /update channel <stable|preview|nightly>[/]\n")
                return
            ch = args[1].lower()
            if ch not in ("stable", "preview", "nightly"):
                view.write("[yellow]channel must be one of stable|preview|nightly[/]\n")
                return
            updater.set_update_settings(channel=ch)
            view.write(f"[green]channel set to {ch}[/]\n")
            return

        if sub in ("check", ""):
            result = updater.check_for_update()
            view.write(updater.format_result_for_human(result) + "\n")
            return

        if sub == "apply":
            mode = updater.detect_install_mode()
            target = updater.upgrade_target()
            if not mode.allow_auto_apply:
                view.write(
                    f"[yellow]Auto-apply disabled for this install ({mode.kind}). "
                    f"Please upgrade manually via `uv tool upgrade {target}`.[/]\n"
                )
                return
            # The shim (`worldlines`) pins the engine: upgrading it pulls the
            # matching neonrp. A hardcoded `neonrp` here used to install a
            # second, unpinned engine next to the shim.
            cmd = updater.build_upgrade_command(target)
            if not cmd:
                view.write("[red]No supported package manager on PATH.[/]\n")
                return
            view.write(f"  running: {' '.join(cmd)}\n")
            ok, output = updater.apply_update_in_background(target)
            if output:
                view.write(output + "\n")
            locale = getattr(self, "ui_locale", None) or getattr(self, "locale", "en") or "en"
            if ok:
                view.write(f"[green]{get_message(locale, 'upgrade.success')}[/]\n")
            else:
                view.write(f"[red]{get_message(locale, 'upgrade.failed')}[/]\n")
            return

        view.write(f"[yellow]Unknown /update subcommand: {sub}[/]\n")

    def _cmd_new(self, args: list[str]) -> None:
        """Start a full new session and archive current active session."""
        view = self.query_one("#conversation-view", ConversationView)
        if args:
            view.write("[yellow]Usage: /new[/]\n")
            return
        self._start_new_session(announce=True)

    def _cmd_copy(self) -> None:
        """Copy current conversation to system clipboard."""
        view = self.query_one("#conversation-view", ConversationView)
        transcript = view.get_plain_text()
        if not transcript:
            view.write("[yellow]Nothing to copy yet.[/]\n")
            return
        try:
            self.copy_to_clipboard(transcript)
            view.write("[green]Copied conversation to clipboard.[/]\n")
        except Exception as e:
            view.write(f"[red]Copy failed: {e}[/]\n")

    # ── Worldlines account (10-02) ──────────────────────────────────────────────────────────────────────
    def _t(self, key: str) -> str:
        return get_message(self.ui_locale, key)

    def _account_lang(self) -> str:
        try:
            from neonrp.core.user_config import get_user_locale

            return (get_user_locale() or "zh")[:2]
        except Exception:
            return "zh"

    def _cmd_account(self) -> None:
        from neonrp.core import worldlines_auth as wa

        view = self.query_one("#conversation-view", ConversationView)
        st = wa.status()
        head = self._t("account.signed_in") if st["signed_in"] else self._t("account.signed_out")
        view.write(f"[b]{self._t('account.title')}[/b] · {head}" + (f"  [dim]({st['source']})[/]" if st.get("source") else "") + "\n")
        view.write(f"[dim]{wa.about(self._account_lang())}[/]\n")
        view.write(f"[dim]{self._t('account.hint')}[/]\n")

    def _cmd_login(self, args: list[str]) -> None:
        """Browser sign-in (loopback PKCE), or the short-code device flow with `/login code`. Runs off the UI thread.
        Signed in already: signs in again (another account, or a fresh session) — no /login out first (10-23); the old
        session stays until the new one lands."""
        from neonrp.core import worldlines_auth as wa

        view = self.query_one("#conversation-view", ConversationView)
        device = bool(args) and args[0].lower() in ("code", "device", "短码")
        view.write(f"[b]{self._t('account.title')}[/b]\n[dim]{wa.about(self._account_lang())}[/]\n")
        view.write(self._t("account.relogin" if wa.status()["signed_in"] else "account.logging_in") + "\n")

        def say(msg: str) -> None:
            self.call_from_thread(view.write, msg + "\n")

        def worker() -> None:
            try:
                wa.connect(open_browser=not device, device=True if device else None,
                           on_url=lambda u: say(self._t("account.open_url").format(url=u)),
                           on_code=lambda c: say(self._t("account.enter_code").format(uri=c.get("verification_uri"), code=c.get("user_code"))))
            except Exception as exc:  # noqa: BLE001 — a failed sign-in is a message, never a crash
                say("[red]" + self._t("account.failed").format(err=str(exc)[:200]) + "[/]")
                return
            say("[#18FF82]" + self._t("account.done") + "[/]")
            refresh = getattr(self, "_refresh_status_side", None)  # a stand-in app (tests) has no column
            if refresh is not None:
                self.call_from_thread(refresh)

        self.run_worker(worker, exclusive=True, thread=True, name="worldlines-login")

    def _refresh_status_side(self) -> None:
        """The status column repaints (its account tab follows /login and /login out)."""
        try:
            from neonrp.tui.status_side import StatusSide

            self.query_one("#status-side", StatusSide).refresh_state()
        except Exception:  # noqa: BLE001 — no column (launcher / build)
            pass

    def _cmd_billing(self) -> None:
        """`/login billing`: the billing page of the last refusal (or /manage) in the browser, via open_billing."""
        from neonrp.core import billing_stop

        view = self.query_one("#conversation-view", ConversationView)
        stop = billing_stop.last()
        if stop is not None:
            view.write(f"[dim]{escape(stop.text(self._account_lang()))}[/]\n")
        billing_stop.open_page(stop, on_url=lambda u: view.write(f"{escape(u)}\n"))

    def _cmd_logout(self) -> None:
        from neonrp.core import worldlines_auth as wa

        wa.disconnect()
        self.query_one("#conversation-view", ConversationView).write(self._t("account.logged_out") + "\n")
        self._refresh_status_side()

    def _load_user_config_dict(self) -> dict[str, Any]:
        """Load user config JSON or return default template."""
        user_config_path = get_user_config_path()
        try:
            if user_config_path.exists():
                data = json.loads(user_config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return create_default_config_template()

    def _ensure_models_map(self, data: dict[str, Any]) -> dict[str, Any]:
        """Ensure and return top-level models mapping."""
        models = data.setdefault("models", {})
        if not isinstance(models, dict):
            models = {}
            data["models"] = models
        return models

    def _cmd_auth_set_model(self, args: list[str]) -> None:
        """Set active model_ref: /auth set model <name>.

        load_config() merges user → project with project winning. The
        right write target depends on whether we're inside an
        initialized project:

          * worldlines-launched game / `neonrp init`'d directory →
            <root>/.neonrp/ exists → write to project config so the
            switch overrides the per-game model_ref baked in at launch.
          * neonrp running in an arbitrary directory with no .neonrp/ →
            no project config to override; write to ~/.neonrp/config.json
            so the change still persists and we don't pollute cwd with
            an unwanted .neonrp/ scaffold.

        Named model entries themselves always live in user config (the
        cross-project catalog of providers).
        """
        view = self.query_one("#conversation-view", ConversationView)
        if len(args) < 2 or args[0].lower() != "model":
            view.write("[yellow]Usage: /auth set model <name>[/]\n")
            return
        model_name = args[1].strip()

        # Validate against the user-config catalog (where named model
        # entries live).
        user_data = self._load_user_config_dict()
        user_models = self._ensure_models_map(user_data)
        if model_name not in user_models:
            view.write(f"[red]Model '{model_name}' not found. Use /auth list.[/]\n")
            return

        project_dir = get_neonrp_dir(self.root)
        write_to_project = project_dir.exists()

        if write_to_project:
            target_path = get_config_path(self.root)
            try:
                target_data: dict[str, Any] = (
                    json.loads(target_path.read_text(encoding="utf-8"))
                    if target_path.exists()
                    else {}
                )
            except Exception:
                target_data = {}
        else:
            target_path = get_user_config_path()
            target_data = user_data

        target_llm = target_data.setdefault("llm", {})
        if not isinstance(target_llm, dict):
            target_llm = {}
            target_data["llm"] = target_llm
        target_llm["model_ref"] = model_name

        atomic_write_json(target_path, target_data)
        self._provider_notice_shown = False
        scope_label = "project" if write_to_project else "user"
        view.write(f"[green]Active model set to '{model_name}' ({scope_label} config).[/]\n")
        self._show_provider_setup_notice()
        self._refresh_status(include_event_count=False)

    def _load_agent_llm_config(self, agent_id: str) -> dict[str, Any] | None:
        """Load optional llm config from agent.json."""
        agent_json = self.root / "agents" / agent_id / "agent.json"
        if not agent_json.exists():
            return None
        try:
            data = json.loads(agent_json.read_text(encoding="utf-8"))
            llm_data = data.get("llm")
            return llm_data if isinstance(llm_data, dict) else None
        except Exception:
            return None

    def _get_narrator_agent_id(self) -> str:
        """Resolve configured narrator/router agent id for this project."""
        try:
            narrator_id = str(load_config(self.root).tui.narrator_agent_id or "").strip()
            return narrator_id or "narrator"
        except Exception:
            return "narrator"

    def _get_agent_display_name(self, agent_id: str) -> str:
        """Resolve human-readable speaker name from agents/<id>/agent.json."""
        normalized_id = str(agent_id or "").strip()
        if not normalized_id:
            return "Narrator"
        agent_json = self.root / "agents" / normalized_id / "agent.json"
        if not agent_json.exists():
            return normalized_id
        try:
            payload = json.loads(agent_json.read_text(encoding="utf-8"))
        except Exception:
            return normalized_id
        if not isinstance(payload, dict):
            return normalized_id
        configured_name = str(payload.get("name") or "").strip()
        return configured_name or normalized_id

    def _get_root_speaker_name(self) -> str:
        """Get current top-level speaker display name for untagged model output."""
        agent_id = self.session.agent_id if self.session else self._get_default_agent()
        return self._get_agent_display_name(agent_id)

    def _get_effective_provider_config(self):
        """Resolve effective provider for current app/session."""
        config = load_config(self.root)
        agent_id = self.session.agent_id if self.session else self._get_default_agent()
        agent_llm = self._load_agent_llm_config(agent_id)
        return resolve_provider(config, agent_llm, self.provider)

    def _show_provider_setup_notice(self) -> None:
        """Show one-time provider setup guidance for common misconfiguration cases."""
        if self._provider_notice_shown:
            return

        view = self.query_one("#conversation-view", ConversationView)
        provider_cfg = self._get_effective_provider_config()
        provider_name = provider_cfg.provider

        if provider_name == "stub":
            view.write("[yellow]LLM endpoint is not configured (using stub test provider).[/]\n")
            view.write("[dim]Open /settings to pick a real model endpoint.[/]\n")
            self._provider_notice_shown = True
            return

        if not self._has_api_credential(provider_cfg):
            env_name = self._preferred_env_var_name(provider_name, provider_cfg.api_key_env)
            view.write(f"[yellow]Provider '{provider_name}' is selected but API key is missing.[/]\n")
            view.write(f"[dim]Set {env_name} (or NEONRP_LLM_API_KEY), then run /auth show model.[/]\n")
            self._provider_notice_shown = True

    @staticmethod
    def _is_env_var_name(value: str) -> bool:
        """Heuristic: treat uppercase-with-underscores token as env var name."""
        if not value:
            return False
        if not value.replace("_", "").isalnum():
            return False
        return value.upper() == value and "_" in value

    @staticmethod
    def _preferred_env_var_name(provider: str, api_key_env: str | None) -> str:
        """Return the env var name to show to users."""
        if api_key_env and NeonRPApp._is_env_var_name(api_key_env):
            candidate = api_key_env.upper()
            if candidate.endswith("_API_KEY"):
                return candidate
            return f"{candidate}_API_KEY"
        return f"{provider.upper()}_API_KEY"

    @staticmethod
    def _has_api_credential(provider_cfg: Any) -> bool:
        """Check whether provider has usable API credentials."""
        if getattr(provider_cfg, "api_key", None):
            return True
        key_provider = provider_cfg.api_key_env or provider_cfg.provider
        return bool(get_api_key(key_provider))

    def _cmd_undo(self) -> None:
        """Undo last change — route through the real CLI `undo` (same engine
        as `/redo`). The old path imported neonrp.core.branch.undo_last_event,
        which doesn't exist, so /undo always crashed with
        'No module named neonrp.core.branch'."""
        view = self.query_one("#conversation-view", ConversationView)
        exit_code, output = self._invoke_cli(["undo"])
        if output:
            view.write(f"{output}\n")
        elif exit_code != 0:
            view.write("[red]Undo failed[/]\n")
        self._refresh_status()

    def _cmd_save(self, args: list[str]) -> None:
        """Save checkpoint."""
        view = self.query_one("#conversation-view", ConversationView)

        name = args[0] if args else None
        try:
            from neonrp.commands.save import create_save_snapshot

            result = create_save_snapshot(self.root, name)
            view.write(f"[green]Saved checkpoint: {result['save_id']}[/]\n")
        except Exception as e:
            view.write(f"[red]Save failed: {e}[/]\n")

    def _cmd_load(self, args: list[str]) -> None:
        """`/load [存档|快照]` —— 读存档(「load 才是读取存档」)。

        两层都认:**存档** = `~/.worldlines/plays/` 里的一局(接着玩,等于
        `/open <存档>`);**快照** = 本局里 `/save` 存的点。不带参数 = 选单,
        存档在前、本局快照在后。
        """
        view = self.query_one("#conversation-view", ConversationView)

        if not args:
            from neonrp.commands.save import list_loadable_save_snapshots
            from neonrp.worlds import list_saved_games

            try:
                saves = list_saved_games()
            except Exception:  # noqa: BLE001
                saves = []
            try:
                snapshots = list_loadable_save_snapshots(self.root)
            except Exception:  # noqa: BLE001
                snapshots = []
            if not saves and not snapshots:
                view.write("[yellow]没有存档,也没有本局快照。[/]\n")
                return

            options: list[tuple[str, str]] = []
            here = Path(self.root).resolve()
            if saves:
                options.append(section("── 存档 · 接着玩 ──"))
                for save in saves[:15]:
                    name = save.get("display_name") or save.get("dir_name", "?")
                    when = save.get("mtime_display", "")
                    tag = "  (这局)" if Path(str(save.get("path", ""))).resolve() == here else ""
                    options.append((f"{name}  {when}  ({save.get('dir_name')}){tag}", f"run::{save.get('dir_name')}"))
                options.append(spacer())
            if snapshots:
                options.append(section("── 本局快照 ──"))
                for snapshot in snapshots:
                    created = snapshot.get("created") or "unknown"
                    label = (
                        f"{snapshot['save_id']}  "
                        f"(branch={snapshot['branch']} · head={snapshot['head_event']} · created={created})"
                    )
                    options.append((label, f"snap::{snapshot['save_id']}"))

            def on_selected(value: str | None) -> None:
                if not value:
                    return
                kind, _, ident = value.partition("::")
                if kind == "run":
                    self._cmd_open([ident])
                else:
                    self._cmd_load([ident])

            self.push_screen(
                ChoicePickerScreen("读哪一个?", options, hint="↑↓ 选 · Enter 读 · Esc 留在这里"),
                on_selected,
            )
            return

        snapshot_id = args[0]
        # A run directory name (存档) → continue it, like /open.
        try:
            from neonrp.worlds import list_saved_games

            if any(save.get("dir_name") == snapshot_id for save in list_saved_games()):
                self._cmd_open([snapshot_id])
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            from neonrp.commands.save import load_save_snapshot

            load_save_snapshot(self.root, snapshot_id)
            if self.session:
                self.branch = self.session._current_branch()
                self.session.branch = self.branch
                view.clear()
                self._reset_estimated_tokens()
                if self._restore_session():
                    view.write(f"[green]Loaded snapshot: {snapshot_id} (session restored).[/]\n")
                else:
                    view.write(f"[green]Loaded snapshot: {snapshot_id}.[/]\n")
            else:
                view.write(f"[green]Loaded snapshot: {snapshot_id}.[/]\n")
        except Exception as e:
            view.write(f"[red]Load failed: {e}[/]\n")

    def _cmd_config(self, args: list[str]) -> None:
        """Show or set project-level config values."""
        view = self.query_one("#conversation-view", ConversationView)

        if not args or args[0] == "show":
            try:
                config = load_config(self.root)
                cfg_path = get_config_path(self.root)
                provider_cfg = self._get_effective_provider_config()
                view.write("[bold]Project config:[/]\n")
                view.write(f"  [cyan]llm.model_ref:[/] {config.llm.model_ref}\n")
                view.write(f"  [cyan]resolved provider:[/] {provider_cfg.provider}\n")
                view.write(f"  [cyan]resolved model:[/] {provider_cfg.model or '(default)'}\n")
                view.write(f"  [cyan]llm.max_retries:[/] {config.llm.max_retries}\n")
                view.write(f"  [cyan]llm.max_context_chars:[/] {config.llm.max_context_chars}\n")
                view.write(f"  [cyan]config file:[/] {cfg_path}\n")
                view.write("[dim]Use /config set <model_ref|max_retries|max_context_chars> <value>[/]\n")
            except Exception as e:
                view.write(f"[red]Config error: {e}[/]\n")
            return

        if args[0] != "set":
            view.write("[red]Usage: /config [show|set <key> <value>][/]\n")
            return

        if len(args) < 3:
            view.write("[red]Usage: /config set <key> <value>[/]\n")
            view.write("[dim]Keys: model_ref, max_retries, max_context_chars[/]\n")
            return

        key = args[1]
        value = " ".join(args[2:])
        valid_keys = {"model_ref", "max_retries", "max_context_chars"}
        if key not in valid_keys:
            view.write(f"[red]Unknown key '{key}'. Valid: {', '.join(sorted(valid_keys))}[/]\n")
            return

        if key in {"max_retries", "max_context_chars"}:
            try:
                value = int(value)
            except ValueError:
                view.write(f"[red]{key} must be an integer[/]\n")
                return

        try:
            config_path = get_config_path(self.root)
            data: dict[str, Any]
            if config_path.exists():
                data = json.loads(config_path.read_text(encoding="utf-8"))
            else:
                data = create_default_config_template()
            if "llm" not in data:
                data["llm"] = {}
            data["llm"][key] = value
            atomic_write_json(config_path, data)
            view.write(f"[green]Set {key} = {value}[/]\n")
        except Exception as e:
            view.write(f"[red]Config set failed: {e}[/]\n")

    @staticmethod
    def _parsed_to_argv(command: str, args: list[str], options: dict[str, str]) -> list[str]:
        """Convert parsed slash command into CLI argv."""
        argv = [command, *args]
        for key, value in options.items():
            flag = f"-{key}" if len(key) == 1 else f"--{key}"
            argv.append(flag)
            if value != "true":
                argv.append(value)
        return argv

    def _invoke_cli(self, argv: list[str]) -> tuple[int, str]:
        """Invoke NeonRP CLI command and return (exit_code, output)."""
        from click.testing import CliRunner
        from neonrp.cli import cli

        runner = CliRunner()
        try:
            old_cwd: Path | None = Path.cwd()
        except OSError:
            # Our own cwd may already be gone — e.g. a world import renamed the
            # workspace we launched in out from under us.
            old_cwd = None
        try:
            os.chdir(self.root)
        except OSError as exc:
            return 1, f"Working directory unavailable ({self.root}): {exc}"
        try:
            result = runner.invoke(cli, argv)
        finally:
            # Restore to the first location that still exists. The original cwd
            # can vanish mid-session (a world import renames its workspace), and
            # a bare os.chdir(old_cwd) then raises FileNotFoundError and crashes
            # the whole app. Falling back to self.root / home keeps a valid cwd.
            for target in (old_cwd, self.root, Path.home()):
                if target is None:
                    continue
                try:
                    os.chdir(target)
                    break
                except OSError:
                    continue

        output = (result.output or "").strip()
        if result.exception and isinstance(result.exception, SystemExit):
            return result.exit_code, output
        if result.exception and output:
            output = f"{output}\n{result.exception}"
        elif result.exception:
            output = str(result.exception)
        return result.exit_code, output

    def _forward_cli_command(self, parsed) -> None:
        """Forward a slash command to the corresponding CLI command."""
        view = self.query_one("#conversation-view", ConversationView)
        argv = self._parsed_to_argv(parsed.command, parsed.args, parsed.options)
        exit_code, output = self._invoke_cli(argv)

        if output:
            view.write(f"{output}\n")
        elif exit_code != 0:
            view.write(f"[red]Command failed (exit {exit_code})[/]\n")

        # Commands that mutate project state should refresh status.
        if parsed.command in {"branch", "game", "sandbox", "load", "save", "undo", "redo", "init", "import"}:
            self._refresh_status()

    def _set_live_status(self, text: str) -> None:
        """A status from the stream: only while a turn is being sent. Over the network the host's stream reaches the
        client after the turn's own answer (10-21 TUI --connect: 「Streaming response...」 stayed after the turn ended,
        the input free); a late chunk must not turn the status back on."""
        if self._active_send_thread is not None:
            self._set_run_status(text)

    def _set_run_status(self, text: str) -> None:
        """Show ephemeral run status in input area."""
        try:
            input_area = self.query_one("#input-area", InputArea)
            input_area.set_run_status(text)
        except Exception:
            pass

    def _set_thinking_ticker(self, text: str) -> None:
        """Push the live thinking tail to the input-area ticker."""
        try:
            self.query_one("#input-area", InputArea).set_thinking_ticker(text)
        except Exception:
            pass

    def _clear_thinking_ticker(self) -> None:
        """Hide the live thinking ticker."""
        try:
            self.query_one("#input-area", InputArea).clear_thinking_ticker()
        except Exception:
            pass

    def _clear_run_status(self) -> None:
        """Hide run status in input area."""
        try:
            input_area = self.query_one("#input-area", InputArea)
            input_area.clear_run_status()
        except Exception:
            pass
        # M18 Phase E1: a turn just settled — repaint the character lane
        # from the world-agent's registry. Cheap, idempotent, cosmetic.
        self._refresh_character_lane()

    def _get_ask_user_panel(self) -> AskUserInlinePanel | None:
        """Return inline ask_user panel when mounted."""
        try:
            return self.query_one("#ask-user-inline", AskUserInlinePanel)
        except Exception:
            return None

    @staticmethod
    def _collapse_ws(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _echo_ask_user_to_transcript(self, question: str) -> None:
        """Mirror the ask_user narration into the scrollable transcript.

        In orchestrator / multi-agent mode the sub-agent's scene narration
        is delivered AS the ask_user question, so it only ever lived in the
        (ephemeral) choice dialog — the playthrough log never accumulated
        it. Echo it as a Narrator bubble so the story builds up on screen,
        like a visual-novel log. Local transcript only (``mirror_to_bridge=
        False``): the bridge gets this text via the explicit ask_user event.

        De-duped: in fast mode the same narration may have just been
        streamed into the transcript, so skip if it's already there.
        """
        q = self._collapse_ws(question)
        if not q:
            return
        try:
            view = self.query_one("#conversation-view", ConversationView)
        except Exception:
            return
        # Skip if this narration was already rendered this turn (fast mode
        # streams it before calling ask_user). Compare on collapsed text.
        try:
            recent = self._collapse_ws("".join(view._plain_chunks[-24:]))
        except Exception:
            recent = ""
        probe = q[:60]
        if probe and probe in recent:
            return
        speaker = getattr(view, "_last_header_speaker_in_turn", None) or "Narrator"
        # Belt-and-suspenders: the echo is a nice-to-have; it must NEVER be
        # able to throw and block the ask_user panel from showing (that would
        # hang the turn — "it stopped asking questions"). Swallow everything.
        try:
            view.add_named_assistant_message(speaker, question, mirror_to_bridge=False)
            # add_named_assistant_message (unlike sibling render paths) does
            # not scroll. Without this the echoed bubble mounts BELOW the
            # viewport / behind the inline ask_user panel, so the narration
            # only becomes visible when the sub-agent exits and a later render
            # finally scrolls — i.e. "it all shows at once after town-agent
            # jumps out". Scroll now so each turn's narration appears live,
            # right above the choices.
            view._safe_scroll_end()
        except Exception:
            pass  # echo is best-effort; never let it disturb the turn

    def _show_ask_user_panel(self, question: str, options: list[str], on_submit: Any) -> None:
        """Show inline ask_user panel; fallback to canceled if panel is unavailable.

        Wraps the raw `on_submit` so we can also:
        - clear `_active_ask_user_submit` the moment a result comes in
        - hide the panel if the submit was triggered externally (main
          input / Discord inbound) rather than via the panel's own buttons

        Keeping the main input ENABLED during ask_user means the player
        can answer by typing in the main chat bar too — `_send_message`
        re-routes that text into this callback instead of starting a new
        turn.
        """
        panel = self._get_ask_user_panel()
        if panel is None:
            on_submit(AskUserInlinePanel.CANCEL_RESULT)
            return

        def _wrapped_submit(result: str | None) -> None:
            # Drop the app-level hook first so a late-arriving re-entrant
            # Discord inbound can't double-submit.
            self._active_ask_user_submit = None
            # If the submit came from OUTSIDE the panel (typed in main
            # input, or pushed via bridge), the panel is still visible —
            # dismiss it explicitly.
            try:
                live_panel = self._get_ask_user_panel()
                if live_panel is not None:
                    live_panel.hide_prompt()
            except Exception:
                pass
            on_submit(result)

        self._active_ask_user_submit = _wrapped_submit
        self._set_main_input_enabled(False)
        panel.show_prompt(question, options, _wrapped_submit)
        self._set_run_status("Waiting for your choice...")

    def action_toggle_ask_user_minimize(self) -> None:
        """App-level hook so Ctrl+\\ works when focus is in the main input."""
        panel = self._get_ask_user_panel()
        if panel is None or not panel.is_active:
            return
        panel.toggle_minimize()

    def _cancel_running_turn(self) -> bool:
        """Signal an in-flight conversation turn to cancel.

        Sets ``ConversationSession._cancel_event`` (via its public
        ``cancel()``) which the turn loop checks at every step and
        exits cleanly. Returns ``True`` iff a cancel was signalled
        (so the caller can consume the key event). Idempotent — does
        nothing when no turn is running or one is already cancelling.
        Pure: no thread.join (the worker exits on its own at the next
        cancel check, which keeps ESC instant for the user).
        """
        session = getattr(self, "session", None)
        if session is None:
            return False
        thread = getattr(self, "_active_send_thread", None)
        if thread is None or not thread.is_alive():
            return False
        if getattr(session, "is_cancelled", False):
            return False  # already cancelling — don't spam the user
        try:
            session.cancel()
        except Exception:
            return False
        try:
            view = self.query_one("#conversation-view", ConversationView)
            view.write("[yellow]Cancelling turn… (Esc)[/]\n")
        except Exception:
            pass
        return True

    def _cancel_active_ask_user(self) -> bool:
        """Cancel active inline ask_user prompt, if any."""
        panel = self._get_ask_user_panel()
        if panel is None:
            return False
        cancelled = panel.cancel_current()
        if cancelled:
            # Clear the routing hook too — the panel's own cancel path
            # invokes the wrapped submit with the CANCELLED result, which
            # already clears this, but guard against the panel firing
            # cancel without going through our wrapper.
            self._active_ask_user_submit = None
            self._clear_run_status()
            self._set_main_input_enabled(True)
            try:
                self.query_one("#message-input", Input).focus()
            except Exception:
                pass
        return cancelled

    def _sync_finalize_pending_ask_user(self) -> None:
        """Synchronously close any in-flight ask_user with a cancel result.

        Without this, abrupt exits (close terminal, kill from outside,
        crash) leave an `assistant.tool_calls=[ask_user(...)]` in the
        JSONL with no matching `tool` message. The next session's first
        LLM call then 400s with "An assistant message with 'tool_calls'
        must be followed by tool messages responding to each
        'tool_call_id'." (DeepSeek; strict OpenAI tool spec.)

        This helper writes the cancel `tool` message **directly to disk**
        so the JSONL ends with a complete tool_call → tool_result pair
        even when the conversation worker thread doesn't get a chance
        to run its own cancel path. Idempotent: if a tool message
        already exists for the tool_call_id, skip it.
        """
        if self.session is None:
            return
        # Tests install MagicMock / strict-session stubs that don't expose
        # the same attribute surface as the real ConversationSession. Bail
        # rather than raise from an atexit hook.
        messages = getattr(self.session, "messages", None)
        if not isinstance(messages, list):
            return

        seen_tool_msg_ids: set[str] = set()
        last_ask_call_ids: list[str] = []
        for msg in messages:
            tc_id = getattr(msg, "tool_call_id", None) or ""
            if msg.role == "tool" and tc_id:
                seen_tool_msg_ids.add(tc_id)
            if msg.role == "assistant" and getattr(msg, "tool_calls", None):
                ids = [
                    str(getattr(tc, "id", "") or "")
                    for tc in (msg.tool_calls or [])
                    if (getattr(tc, "name", "") or "") == "ask_user"
                    and getattr(tc, "id", None)
                ]
                if ids:
                    last_ask_call_ids = ids

        pending_ids = [tc_id for tc_id in last_ask_call_ids if tc_id not in seen_tool_msg_ids]
        if not pending_ids:
            return

        from neonrp.core.llm import Message as _LLMMessage
        from neonrp.core.session import append_message as _append_message

        cancel_payload = json.dumps({"status": "cancelled"})
        run_id = getattr(self.session, "_last_run_id", "") or ""
        for tc_id in pending_ids:
            cancel_msg = _LLMMessage(
                role="tool",
                tool_call_id=tc_id,
                name="ask_user",
                content=cancel_payload,
            )
            try:
                messages.append(cancel_msg)
            except Exception:
                pass
            try:
                _append_message(
                    self.session.root,
                    self.session.branch,
                    cancel_msg,
                    run_id=run_id,
                )
            except Exception:
                # Best-effort during shutdown — disk error here can't
                # be surfaced anywhere useful; just don't crash.
                pass

        # Bump the session's "persisted up to" cursor to the new tail so
        # the immediately-following session.flush() in action_safe_quit
        # doesn't re-write the cancel message we just appended (which
        # would land as a duplicate `(已取消)` row when the next
        # `continue` replays the JSONL).
        try:
            self.session._persisted_up_to = len(messages)
        except Exception:
            pass

        self._active_ask_user_submit = None
        try:
            panel = self._get_ask_user_panel()
            if panel is not None:
                panel.hide_prompt()
        except Exception:
            pass

    def _set_main_input_enabled(self, enabled: bool) -> None:
        """Swap placeholder/styling on the main chat input while ask_user is active.

        Historically this actually disabled the input widget — but that
        blocked both keyboard answers and Discord inbound. Now the input
        stays editable; `_send_message` detects the active ask_user hook
        and re-routes the text to it instead of starting a new turn.
        """
        try:
            input_area = self.query_one("#input-area", InputArea)
            if enabled:
                input_area.remove_class("ask-user-active")
            else:
                input_area.add_class("ask-user-active")
        except Exception:
            pass

        try:
            input_widget = self.query_one("#message-input", Input)
            # Always keep the input editable — just change the hint so the
            # user knows typing will answer the pending prompt rather than
            # open a new turn.
            input_widget.disabled = False
            if enabled:
                input_widget.placeholder = get_message(self.ui_locale, "input_hint")
            else:
                input_widget.placeholder = get_message(self.ui_locale, "ask_user.waiting_choice")
        except Exception:
            pass

    @classmethod
    def _estimate_text_tokens(cls, text: str) -> int:
        """Estimate token count from plain text without provider usage metadata."""
        if not text:
            return 0
        try:
            unit_count = len(cls._TOKEN_SPLIT_RE.findall(text))
            byte_count = len(text.encode("utf-8"))
        except Exception:
            unit_count = len(text)
            byte_count = len(text)
        estimate = max(unit_count, byte_count // 4)
        return max(1, estimate)

    def _estimate_prompt_tokens_for_turn(self, user_text: str) -> int:
        """Estimate prompt tokens for the next turn from local conversation context."""
        texts: list[str] = []
        message_count = 1  # current user message
        if self.session:
            raw_messages = getattr(self.session, "messages", [])
            messages = raw_messages if isinstance(raw_messages, list) else []
            for msg in messages:
                content = getattr(msg, "content", "")
                if content:
                    texts.append(str(content))
                message_count += 1
        texts.append(user_text)
        joined = "\n".join(texts)
        # Add small structural overhead per message.
        return self._estimate_text_tokens(joined) + (message_count * 4)

    def _bump_prompt_tokens(self, text: str) -> None:
        increment = self._estimate_prompt_tokens_for_turn(text)
        self._est_prompt_tokens_total += max(0, increment)
        self._refresh_status(include_event_count=False)

    def _bump_completion_tokens(self, text: str) -> None:
        increment = self._estimate_text_tokens(text)
        if increment <= 0:
            return
        self._est_completion_tokens_total += increment
        self._refresh_status(include_event_count=False)

    def _bump_tool_activity_tokens(self, tool_name: str, params: dict[str, Any], raw_result: str = "") -> None:
        """Add a small token estimate for tool-activity events to keep live counters responsive.

        Heuristic direction:
        - tool use announcement (no ``raw_result``): completion-side activity
        - tool result payload (has ``raw_result``): prompt-side activity for next turn
        """
        snippet = raw_result[:320] if raw_result else ""
        payload = f"{tool_name} {json.dumps(params, ensure_ascii=False)} {snippet}"
        increment = max(1, min(64, self._estimate_text_tokens(payload) // 2))
        if raw_result:
            self._est_prompt_tokens_total += increment
        else:
            self._est_completion_tokens_total += increment
        self._refresh_status(include_event_count=False)

    def _reset_estimated_tokens(self) -> None:
        self._est_prompt_tokens_total = 0
        self._est_completion_tokens_total = 0

    @staticmethod
    def _planning_takes(root: Any, parsed: dict[str, Any]) -> bool:
        """With the planning beat on (the run's contract), a line to the room or to someone HERE goes to the planning
        beat, not to the between-beats chat — one record, and the host hands that character the mic. Someone elsewhere
        is still reached by the direct chat (a message from afar)."""
        try:
            from neonrp.core import node_kinds

            if not node_kinds.call("plan", "active", Path(root), "·", default=False):  # a planning node, and it is on
                return False
        except Exception:  # noqa: BLE001
            return False
        if parsed.get("lane") == "room":
            return True
        if parsed.get("lane") == "dialogue":
            try:
                from neonrp.core.light_chat import resolve_room_souls

                return str(parsed.get("target")) in {iid for iid, _d, _n in resolve_room_souls(Path(root))}
            except Exception:  # noqa: BLE001
                return False
        return False

    def _try_interlude_chat(self, text: str) -> bool:
        """M24 对话拍 · TUI 频道语法:@soul 直聊 / # 房间群聊(幕间)。

        时钟不走、不进世界拍;soul 记忆照常 commit(引擎侧 light_chat)。
        返回 True=已按对话拍处理;False=落回世界拍(寻址永不吞输入)。"""
        root = getattr(self.session, "root", None)
        if root is None:
            return False
        try:
            from neonrp.core.address import parse_address

            parsed = parse_address(root, text)
        except Exception:
            return False
        if parsed.get("lane") == "world":
            return False
        if parsed.get("text") and self._planning_takes(root, parsed):
            return False  # 10-08: in a planning run, talking to whoever is here IS the planning beat (the host passes the mic)
        view = self.query_one("#conversation-view", ConversationView)
        view.add_user_message(text)

        def _cm(key: str) -> str:
            return get_message(self.ui_locale, key)

        # 裸 @名字:回看线程尾部(频道基础功能)—— 不发话,只看。
        if parsed.get("lane") == "dialogue" and not parsed.get("text"):
            try:
                from neonrp.core.light_chat import read_thread

                rows = read_thread(root, str(parsed["target"]), limit=8)
                for r in rows:
                    who = _cm("chat.you") if r.get("role") == "player" else _cm("chat.them")
                    view.write(f"[dim]{r.get('ts', '')} {who}:{r.get('text', '')}[/]\n")
                if not rows:
                    view.write(f"[dim]{_cm('chat.never_talked')}[/]\n")
            except Exception:
                pass
            view.write(f"[dim]{_cm('chat.dm_hint')}[/]\n")
            return True
        # 裸 #:看在场 + 房间近况(频道基础功能)。
        if parsed.get("lane") == "room" and not parsed.get("text"):
            try:
                from neonrp.core.light_chat import read_room_thread, resolve_room_souls

                names = [n for _i, _d, n in resolve_room_souls(root)]
                view.write(f"[cyan]{_cm('chat.present')}[/]{_cm('chat.sep').join(names) if names else _cm('chat.nobody_here')}\n")
                for r in read_room_thread(root, limit=6):
                    view.write(f"[dim]{r.get('ts', '')} {r.get('who', '')}:{r.get('text', '')}[/]\n")
            except Exception:
                pass
            view.write(f"[dim]{_cm('chat.room_hint')}[/]\n")
            return True
        self._set_run_status(_cm("chat.running"))

        def worker() -> None:
            lines: list[str] = []
            try:
                if parsed.get("lane") == "dialogue" and parsed.get("target"):
                    from neonrp.core.light_chat import light_chat_reply

                    out = light_chat_reply(root, str(parsed["target"]), str(parsed["text"]))
                    if out.get("ok"):
                        if out.get("remote"):
                            # TODO #6:@ 对不在场的人 = 打电话/发消息,TA 会记得。
                            lines.append(
                                "[dim]"
                                + get_message(self.ui_locale, "chat.call_via").format(medium=out.get("medium") or "")
                                + "[/]"
                            )
                        lines.append(f"[cyan]「{out.get('name')}」[/]{out.get('reply')}")
                        wi = out.get("world_intent")
                        if wi:
                            lines.append(f"[dim]{_cm('chat.act_hint').format(label=wi.get('label') or _cm('chat.act_default'))}[/]")
                    elif out.get("error") == "not-co-located":
                        lines.append("[dim]" + get_message(self.ui_locale, "chat.unreachable") + "[/]")
                    else:
                        lines.append(f"[yellow]{_cm('chat.error').format(err=out.get('error'))}[/]")
                else:
                    from neonrp.core.light_chat import room_chat_reply

                    out = room_chat_reply(root, str(parsed.get("text") or ""))
                    if out.get("ok"):
                        for r in out.get("replies", []):
                            if r.get("reply"):
                                lines.append(f"[cyan]「{r['name']}」[/]{r['reply']}")
                        quiet = [r["name"] for r in out.get("replies", []) if not r.get("reply")]
                        if quiet:
                            lines.append(f"[dim]{_cm('chat.listening').format(names=_cm('chat.sep').join(quiet))}[/]")
                        if not lines:
                            lines.append(f"[dim]{_cm('chat.no_reply')}[/]")
                    elif out.get("error") == "no-souls-here":
                        lines.append(f"[dim]{_cm('chat.nobody_here')}[/]")
                    else:
                        lines.append(f"[yellow]{_cm('chat.error').format(err=out.get('error'))}[/]")
            except Exception as exc:  # noqa: BLE001 — 轻拍失败绝不崩 TUI
                lines.append(f"[yellow]{_cm('chat.failed').format(err=str(exc)[:100])}[/]")

            def apply() -> None:
                try:
                    v = self.query_one("#conversation-view", ConversationView)
                    for ln in lines:
                        v.write(ln + "\n")
                except Exception:
                    pass
                self._clear_run_status()

            self.call_from_thread(apply)

        threading.Thread(
            target=worker, daemon=True, name="neonrp-interlude"
        ).start()
        return True

    def _pick_option(self, text: str) -> None:
        """A pressed option is the player's line for the next turn."""
        self._send_message(text)

    def _send_message(self, text: str, *, silent: bool = False) -> None:
        """Send message to conversation session.

        ``silent`` runs the turn without echoing ``text`` as a "You" bubble
        in the transcript — used for the startup handoff brief, which is a
        system instruction the player never typed and shouldn't see.
        """
        try:  # 10-10: the table is waiting on this player's character — the line answers it, it is not a new turn
            from neonrp.tui import net_room

            if not silent and net_room.take_answer(self, text):
                return
        except Exception:  # noqa: BLE001
            pass
        try:  # whatever the player sends, last turn's options are spent
            from neonrp.tui.options_bar import OptionsBar

            self.query_one("#options-bar", OptionsBar).clear()
        except Exception:  # noqa: BLE001
            pass
        # Ask_user re-routing — must come BEFORE the "request already running"
        # guard, because the worker thread IS alive (blocked on the ask_user
        # response event). Typing in the main input OR a Discord inbound
        # message goes through here; we treat the text as the prompt answer,
        # unblock the worker, and skip starting a new turn.
        if self._active_ask_user_submit is not None:
            cb = self._active_ask_user_submit
            # Render the answer as a user message so the transcript shows
            # what the player said, the same as a normal turn would.
            try:
                view = self.query_one("#conversation-view", ConversationView)
                view.add_user_message(text)
            except Exception:
                pass
            try:
                cb(text)
            except Exception:
                # Never let a broken submit kill the whole event loop —
                # just clear the hook and the worker will time out on its
                # own `response_event.wait()` in the worst case.
                self._active_ask_user_submit = None
            return
        if not self.session:
            view = self.query_one("#conversation-view", ConversationView)
            view.write("[red]Session not initialized[/]\n")
            return
        if self._active_send_thread is not None and self._active_send_thread.is_alive():
            view = self.query_one("#conversation-view", ConversationView)
            view.write("[yellow]A request is already running. Please wait...[/]\n")
            return

        # M24 §0.5 TUI native 寻址:@名字/# 开头 → 对话拍(幕间,时钟不走,
        # 不进世界拍);解析失败自动落回世界拍——寻址永不吞输入。
        if not silent and text.strip()[:1] in ("@", "@", "#", "#") and self._try_interlude_chat(text):
            return

        view = self.query_one("#conversation-view", ConversationView)
        if not silent:
            view.add_user_message(text)
        self._last_user_input = text
        self._stream_started = False
        self._subagent_stream_seen.clear()
        self._set_run_status("Thinking... waiting for model response")
        self._bump_prompt_tokens(text)
        # Immediately tell bridges a turn is starting — Discord etc. show a
        # 💭 placeholder so the remote viewer isn't staring at dead air while
        # the LLM is still streaming locally.
        self._emit_bridge_event("turn_status", data={"state": "thinking"})
        turn_epoch = self._conversation_epoch

        # Use a daemon thread so Ctrl+Q can always return terminal control promptly.
        worker = threading.Thread(
            target=self._send_worker,
            args=(text, turn_epoch),
            name="neonrp-send-worker",
            daemon=True,
        )
        self._active_send_thread = worker
        worker.start()

    # ------------------------------------------------------------------
    # Bridge hub (Phase 1a) — Discord / Telegram / future buddy-bot.
    # Lazy-init: if nobody asks for it, there's zero overhead.
    # ------------------------------------------------------------------

    def _ensure_bridge_hub(self) -> Any:
        """Create the bridge hub on first use and wire up the inbound path.

        Also registers any external bridges (Discord, Telegram) whose
        `autostart` flag is set in user config. If the optional python
        package (discord.py etc) is missing, the bridge silently no-ops.
        """
        if self._bridge_hub is not None:
            return self._bridge_hub
        try:
            from neonrp.bridges import BridgeHub, InboundMessage
            from neonrp.bridges.tui import TUIBridge

            hub = BridgeHub()

            def _on_inbound(msg: InboundMessage) -> None:
                # Bridge-originated player input flows through the same
                # `_send_message` path as local typing. Running on a bridge
                # thread → re-enter via call_from_thread so Textual widgets
                # stay thread-consistent.
                try:
                    self.call_from_thread(self._send_message, msg.text or "")
                except Exception:
                    # call_from_thread requires app.run loop; fall back to
                    # direct call for tests / headless.
                    self._send_message(msg.text or "")

            hub.set_inbound_handler(_on_inbound)
            hub.register(TUIBridge(self))

            # Auto-register external bridges flagged in user config.
            self._register_autostart_bridges(hub)

            hub.start_all()
            self._bridge_hub = hub
        except Exception:
            # Bridge subsystem must never break the TUI — swallow and leave
            # hub as None so emits become no-ops via `emit_if_hub`.
            self._bridge_hub = None
        return self._bridge_hub

    def _register_autostart_bridges(self, hub: Any) -> None:
        """Attach bridges whose `autostart=true` in ~/.neonrp/config.json.

        Hard-skipped under pytest or when `NEONRP_DISABLE_EXTERNAL_BRIDGES=1`
        is set — otherwise the test suite would connect to the developer's
        real Discord channel (because the user config is read globally) and
        blast test fixtures into it. `add_assistant_end` emits to bridges,
        so a single long-stream test fixture posts hundreds of lines.
        """
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("NEONRP_DISABLE_EXTERNAL_BRIDGES"):
            return
        # Discord
        try:
            from neonrp.core.discord_config import get_discord_settings
            from neonrp.bridges.discord_bridge import build_discord_bridge_from_config

            settings = get_discord_settings()
            if settings.get("autostart") and settings.get("bot_token") and settings.get("channel_id"):
                bridge = build_discord_bridge_from_config()
                if bridge is not None:
                    hub.register(bridge)
        except Exception:
            pass  # discord subsystem stays optional

    def _flush_bridge_before_ask_user(self, question: str, options: list[str]) -> None:
        """Drain the per-turn bridge buffer as a narrator_text, then emit ask_user.

        Runs on the UI thread (must touch the view). `on_ask_user` in the
        worker thread hops here via `_safe_call_from_thread` so the ordering
        on bridges is:
          1. any narrative accumulated so far → narrator_text (edits the
             💭 placeholder into the pre-question narration)
          2. ask_user → posts the question as a NEW message below it
        Without step 1, the ask_user prompt would overwrite the 💭 and the
        pre-question story would never reach Discord.
        """
        try:
            view = self.query_one("#conversation-view", ConversationView)
        except Exception:
            view = None
        if view is not None:
            try:
                # Capture whatever's mid-stream into the bridge buffer, then
                # drain — otherwise the post-question `add_assistant_end`
                # would re-emit the same segments we just sent.
                view._flush_assistant_stream_segment()
                segments = list(view._bridge_segment_buffer)
                view._bridge_segment_buffer.clear()
                if segments:
                    view._emit_turn_to_bridges(segments)
            except Exception:
                pass
        self._emit_bridge_event(
            "ask_user",
            data={"question": question, "options": list(options or [])},
        )

    def _emit_bridge_event(
        self,
        kind: str,
        speaker: str = "",
        text: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Publish an event to all registered bridges (no-op if none).

        `data` is an explicit dict kwarg (not **kwargs) — the previous
        signature captured `data={...}` into `**kwargs` as `{"data": {...}}`,
        producing a double-wrapped payload on the OutboundEvent. That broke
        `turn_status`, which packs its state in `data`. Callers now pass a
        plain dict and it's forwarded untouched to the bridge.
        """
        hub = self._bridge_hub
        if hub is None:
            return
        try:
            from neonrp.bridges import OutboundEvent

            hub.emit(
                OutboundEvent(
                    kind=kind,
                    speaker=speaker,
                    text=text,
                    data=dict(data) if data else {},
                )
            )
        except Exception:
            pass

    def _send_worker(
        self,
        text: str,
        turn_epoch: int | None = None,
    ) -> None:
        """Worker for sending message."""
        if turn_epoch is None:
            turn_epoch = self._conversation_epoch

        def _is_stale_turn() -> bool:
            return turn_epoch != self._conversation_epoch

        try:
            worker = get_current_worker()
        except Exception:
            # Not running in a worker thread, run synchronously
            worker = None

        if self.verbose:
            turn_ctx = self._verbose_turn_context(text)
            self._append_verbose_event("turn_start", turn_ctx)
            if worker is None or not worker.is_cancelled:
                self._safe_call_from_thread(
                    self._write_verbose_line,
                    (
                        f"turn start: mode={turn_ctx.get('mode')} agent={turn_ctx.get('agent')} "
                        f"provider={turn_ctx.get('provider', 'unknown')} model={turn_ctx.get('model', '')}"
                    ),
                )

        # Callbacks for streaming and tool use
        def on_chunk(chunk: str) -> None:
            if (worker is None or not worker.is_cancelled) and not _is_stale_turn():
                self._safe_call_from_thread(self._append_chunk, chunk)

        def on_thinking(thinking: str) -> None:
            if (worker is None or not worker.is_cancelled) and not _is_stale_turn():
                self._safe_call_from_thread(self._append_thinking, thinking)

        def on_tool_use(tool_name: str, params: dict[str, Any]) -> None:
            if (worker is None or not worker.is_cancelled) and not _is_stale_turn():
                self._safe_call_from_thread(self._show_tool_use, tool_name, params)

        def on_tool_result(tool_name: str, params: dict[str, Any], raw_result: str) -> None:
            if (worker is None or not worker.is_cancelled) and not _is_stale_turn():
                self._safe_call_from_thread(self._show_tool_result, tool_name, params, raw_result)

        def on_soul_status(snapshot: dict[str, dict[str, str]]) -> None:
            # Persistent multi-agent soul lane: store the latest lifecycle
            # snapshot and repaint on the UI thread. Fires multiple times
            # per turn (queued → running → completed/degraded/offstage).
            if (worker is None or not worker.is_cancelled) and not _is_stale_turn():
                self._safe_call_from_thread(self._apply_soul_status_snapshot, snapshot)

        def on_beat(ev: dict[str, Any]) -> None:
            # engine/beat (10-08): the two beats, dice, state changes, the settlement — structured, not parsed
            if (worker is None or not worker.is_cancelled) and not _is_stale_turn():
                self._safe_call_from_thread(self._apply_beat_event, ev)

        def on_ask_user(question: str, options: list[str]) -> str:
            response_event = threading.Event()
            response_holder: list[str | None] = [None]

            # Mirror the prompt to external bridges (Discord etc) before we
            # block on the TUI modal. Without this the Discord-side viewer
            # would just see "💭 Thinking…" until the turn finally ends,
            # with no idea the game is waiting for an input choice.
            #
            # Flush any accumulated pre-ask-user narrative FIRST so Discord
            # sees the story leading up to the question, not just the
            # question dropped in without context. The normal narrator_text
            # emit only fires at turn end — without this flush, the
            # placeholder would be overwritten by the ask_user prompt and
            # the pre-question narration would be lost on Discord.
            self._safe_call_from_thread(
                self._flush_bridge_before_ask_user, question, list(options or [])
            )

            def _show_inline() -> None:
                def _on_submit(result: str | None) -> None:
                    if result is None or result == AskUserInlinePanel.CANCEL_RESULT:
                        response_holder[0] = ASK_USER_CANCELLED_RESPONSE
                    else:
                        response_holder[0] = result
                    response_event.set()
                    self._set_main_input_enabled(True)
                    try:
                        self.query_one("#message-input", Input).focus()
                    except Exception:
                        pass

                # Accumulate the narration in the scrollable log first, so
                # the playthrough builds up on screen instead of vanishing
                # into the ephemeral choice dialog each turn. NEVER let this
                # block the panel — the panel is the interactive critical
                # path; a thrown echo here would hang the turn.
                try:
                    self._echo_ask_user_to_transcript(question)
                except Exception:
                    pass
                self._show_ask_user_panel(question, options, _on_submit)

            self._safe_call_from_thread(_show_inline)
            response_event.wait()
            return str(response_holder[0] or ASK_USER_CANCELLED_RESPONSE)

        # M18 §6 / Phase 4.3 — the TUI is a PURE SUBSCRIBER: this turn's
        # closures (above — they carry the worker/staleness guards) are
        # installed as the current event sink; the durable session-bus
        # subscriptions (_ensure_bus_bridge) dispatch engine/stream +
        # engine/event into it. send() carries only ask_user, which stays a
        # callback by design (request/response — the turn blocks on the
        # human's answer).
        self._ensure_bus_bridge()
        self._turn_event_sink = {
            "chunk": on_chunk,
            "thinking": on_thinking,
            "tool_use": on_tool_use,
            "tool_result": on_tool_result,
            "soul_status": on_soul_status,
            "beat": on_beat,
        }
        try:
            result = self.session.send(
                text,
                on_ask_user=on_ask_user,
            )
        except Exception as exc:
            if self.verbose:
                self._append_verbose_event(
                    "turn_exception",
                    {
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
            result = ConversationTurnResult(success=False, run_id="", error=f"Conversation failed: {exc}")

        if self.verbose:
            self._append_verbose_event(
                "turn_result",
                {
                    "success": result.success,
                    "run_id": result.run_id,
                    "error": result.error,
                    "turns_used": result.turns_used,
                    "usage": result.usage,
                    "tool_calls_made": result.tool_calls_made,
                    "files_modified": result.files_modified,
                },
            )

        if not _is_stale_turn():
            self._current_run_result = result

        if (worker is None or not worker.is_cancelled) and not _is_stale_turn():
            self._safe_call_from_thread(self._handle_result, result)
        if self._active_send_thread is threading.current_thread():
            self._active_send_thread = None

    def _safe_call_from_thread(self, callback: Any, *args: Any) -> None:
        """Call into UI thread safely; ignore late calls after app shutdown."""
        try:
            self.call_from_thread(callback, *args)
        except Exception:
            pass

    def _append_chunk(self, chunk: str) -> None:
        """Append a chunk to the conversation view (called from thread)."""
        if not chunk:
            return
        speaker, payload = self._extract_sub_agent_tag(chunk)
        payload = self._normalize_assistant_text(payload)
        if not payload:
            return
        # Hidden sub-agents: short-circuit BEFORE touching status bar,
        # tool-prediction cards, or the stream widget. Otherwise the
        # content flashes into the TUI before `add_assistant_chunk` can
        # reject it, giving the "peek-then-hide" UX. Call the class-level
        # staticmethod so tests with MagicMock views don't short-circuit
        # through truthy-Mock returns.
        if speaker and ConversationView._agent_is_hidden_at(self.root, speaker):
            return
        if speaker:
            self._subagent_stream_seen.add(speaker)
        marker = self._CALLING_CHUNK_RE.match(payload.strip())
        if marker:
            raw_names = marker.group(1) if marker.groups() else ""
            func_names = [
                ConversationView._canonical_tool_name(name) for name in self._TOOL_CALL_FUNC_RE.findall(raw_names)
            ]
            if func_names:
                names = list(dict.fromkeys(func_names))
            else:
                names: list[str] = []
                for piece in raw_names.split(","):
                    name = ConversationView._canonical_tool_name(piece.strip())
                    if name and self._TOOL_NAME_TOKEN_RE.fullmatch(name):
                        names.append(name)
            if names:
                view = self.query_one("#conversation-view", ConversationView)
                scoped_names = [self._scope_tool_name(name, speaker) for name in names]
                if len(names) == 1:
                    if speaker:
                        self._set_live_status(f"Sub-agent `{speaker}` preparing tool `{names[0]}`")
                    else:
                        self._set_live_status(f"Thinking... preparing tool `{names[0]}`")
                else:
                    if speaker:
                        self._set_live_status(f"Sub-agent `{speaker}` preparing tools")
                    else:
                        self._set_live_status("Thinking... preparing tools")
                for scoped_name in scoped_names:
                    view.add_tool_indicator(scoped_name, {}, predicted=True)
                    self._bump_tool_activity_tokens(scoped_name, {})
            return
        view = self.query_one("#conversation-view", ConversationView)
        if speaker:
            self._set_live_status(f"Sub-agent `{speaker}` streaming response...")
        else:
            self._stream_started = True
            self._set_live_status("Streaming response...")
            speaker = self._get_root_speaker_name()
        if speaker:
            view.add_assistant_chunk(payload, speaker=speaker)
        else:
            view.add_assistant_chunk(payload)
        self._bump_completion_tokens(payload)

    def _append_thinking(self, thinking: str) -> None:
        """Append model thinking chunk when available (called from thread)."""
        if not thinking:
            return
        speaker, payload = self._extract_sub_agent_tag(thinking)
        if speaker and ConversationView._agent_is_hidden_at(self.root, speaker):
            return
        view = self.query_one("#conversation-view", ConversationView)
        if speaker:
            self._subagent_stream_seen.add(speaker)
        if speaker:
            self._set_run_status(f"Sub-agent `{speaker}` thinking...")
        else:
            self._set_run_status("Thinking...")
            speaker = self._get_root_speaker_name()
        if speaker:
            view.add_thinking_chunk(payload, speaker=speaker)
        else:
            view.add_thinking_chunk(payload)
        self._bump_completion_tokens(payload)

    def _show_tool_use(self, tool_name: str, params: dict[str, Any]) -> None:
        """Show tool use indicator (called from thread)."""
        speaker, raw_tool_name = self._extract_sub_agent_tag(tool_name)
        tool_name = ConversationView._canonical_tool_name(raw_tool_name)
        scoped_tool_name = self._scope_tool_name(tool_name, speaker)
        # Hidden sub-agents' tool cards would leak raw JSON params into
        # the transcript — token accounting still runs, but no UI card.
        if speaker and ConversationView._agent_is_hidden_at(self.root, speaker):
            self._bump_tool_activity_tokens(scoped_tool_name, params)
            return
        view = self.query_one("#conversation-view", ConversationView)
        if speaker:
            self._subagent_stream_seen.add(speaker)
        if speaker:
            self._set_run_status(f"Sub-agent `{speaker}` running tool `{tool_name}`")
        else:
            self._set_run_status(f"Thinking... running tool `{tool_name}`")
        view.add_tool_indicator(scoped_tool_name, params)
        self._bump_tool_activity_tokens(scoped_tool_name, params)

    def _show_tool_result(self, tool_name: str, params: dict[str, Any], raw_result: str) -> None:
        """Update tool indicator with completion detail (called from thread)."""
        speaker, raw_tool_name = self._extract_sub_agent_tag(tool_name)
        tool_name = ConversationView._canonical_tool_name(raw_tool_name)
        scoped_tool_name = self._scope_tool_name(tool_name, speaker)
        if speaker and ConversationView._agent_is_hidden_at(self.root, speaker):
            self._bump_tool_activity_tokens(scoped_tool_name, params, raw_result)
            return
        view = self.query_one("#conversation-view", ConversationView)
        if speaker:
            self._subagent_stream_seen.add(speaker)
        view.complete_tool_indicator(scoped_tool_name, params, raw_result)
        self._bump_tool_activity_tokens(scoped_tool_name, params, raw_result)

        # Show todo list inline immediately when TodoWrite completes
        if tool_name == "TodoWrite":
            try:
                payload = json.loads(raw_result)
                items = payload.get("data", {}).get("items", [])
                if isinstance(items, list) and items:
                    view.add_todo_display(items)
            except Exception:
                pass
        elif tool_name == "ask_user":
            fallback_question, fallback_options = self._extract_ask_user_prompt_from_args(params or {})
            selected = self._extract_ask_user_selection(
                raw_result,
                fallback_question=fallback_question,
                fallback_options=fallback_options,
            )
            if selected:
                question, response, options = selected
                rendered = self._format_ask_user_selection_message(question, response, options)
                if rendered:
                    view.add_user_message(rendered)
            else:
                cancelled = False
                try:
                    payload = json.loads(raw_result)
                    cancelled = str(payload.get("status", "")).strip().lower() == "cancelled"
                except Exception:
                    cancelled = False
                if cancelled:
                    rendered_cancelled = self._format_ask_user_cancelled_message(
                        fallback_question,
                        fallback_options,
                    )
                    if rendered_cancelled:
                        view.add_user_message(rendered_cancelled)
        elif tool_name == "task":
            try:
                payload = json.loads(raw_result)
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                data = payload.get("data", {})
                if isinstance(data, dict):
                    agent_id = str(data.get("agent_id", "") or "").strip()
                    speaker = self._get_agent_display_name(agent_id) if agent_id else "Sub-agent"
                    assistant_text = self._normalize_assistant_text(str(data.get("assistant_text", "") or ""))
                    status = str(payload.get("status", "")).lower()
                    already_streamed = (agent_id in self._subagent_stream_seen) if agent_id else (speaker in self._subagent_stream_seen)
                    if not assistant_text:
                        if status == "success" and already_streamed:
                            return
                        if status == "success":
                            assistant_text = "Sub-task completed."
                        elif status == "cancelled":
                            error_text = str(payload.get("error") or data.get("error") or "").strip()
                            assistant_text = (
                                f"Sub-task canceled: {error_text}" if error_text else "Sub-task canceled by user."
                            )
                        else:
                            error_text = str(payload.get("error") or data.get("error") or "").strip()
                            assistant_text = f"Sub-task failed: {error_text}" if error_text else "Sub-task failed."
                    elif already_streamed:
                        return
                    view.add_named_assistant_message(speaker, assistant_text)
                    # Prevent _handle_result fallback from rendering the same
                    # sub-agent content again as the root narrator speaker.
                    self._stream_started = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle play-stage control buttons + in-transcript buttons."""
        btn_id = event.button.id or ""

        # Play-stage control row.
        if btn_id == "btn-toggle-image":
            event.stop()
            self.action_toggle_portrait()
            self._relabel_play_controls()
            return
        if btn_id == "btn-skip-reveal":
            event.stop()
            self.action_skip_typewriter()
            return
        if btn_id == "btn-gen-scene":
            event.stop()
            self._kick_scene_imagegen(reason="manual")
            return

        # 任务 A1: play tabs + the 文生图 tab's own generate button.
        if btn_id in ("tab-chat", "tab-image", "tab-map"):
            event.stop()
            self._set_play_tab(btn_id.split("-", 1)[1])
            return
        if btn_id == "btn-gen-scene-2":
            event.stop()
            self._kick_scene_imagegen(reason="manual")
            return

        # Right status panel ▲ / ▼ (a page at a time, no animation so the
        # click lands where the eye expects).
        if btn_id in ("btn-state-up", "btn-state-down"):
            event.stop()
            self._scroll_game_state(-1 if btn_id == "btn-state-up" else 1)
            return
        if btn_id == "btn-side-toggle":
            event.stop()
            self._toggle_side_view()
            return

        # Agent-error retry / skip / switch model.
        if btn_id.startswith(("agent-error-retry-", "agent-error-skip-", "agent-error-settings-")):
            event.stop()
            is_retry = btn_id.startswith("agent-error-retry-")
            is_settings = btn_id.startswith("agent-error-settings-")
            seq = btn_id.rsplit("-", 1)[-1]
            # Drop the action row so the callout becomes an inert record.
            try:
                view = self.query_one("#conversation-view", ConversationView)
                row = view.query_one(f"#agent-error-actions-{seq}")
                row.remove()
            except Exception:
                pass
            if is_settings:
                # Open the model/settings GUI; the user retries by hand after
                # switching (the failed input is still in history: ↑).
                self._cmd_settings()
                return
            if is_retry:
                last = str(getattr(self, "_last_user_input", "") or "").strip()
                if last:
                    self._send_message(last)
            return

    def _scroll_game_state(self, direction: int) -> None:
        """Scroll the right status panel by roughly one visible page."""
        try:
            box = self.query_one("#game-state-scroll", VerticalScroll)
        except Exception:
            return
        try:
            step = max(3, int(box.size.height or 0) - 2)
            box.scroll_relative(y=direction * step, animate=False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 任务 A1 — play tabs (对话 / 文生图 / 地图). Visibility flips only; the
    # transcript and input are never re-mounted.
    # ------------------------------------------------------------------
    _PLAY_TABS = ("chat", "image", "map")

    def _set_play_tab(self, tab: str, mode: "AppMode | None" = None) -> None:
        """Show ``tab``. ``mode`` is the mode being switched *to* when called
        from `_apply_mode_chrome` (self.mode may still hold the old one)."""
        tab = tab if tab in self._PLAY_TABS else "chat"
        self._play_tab = tab
        playing = (mode or self.mode) == "play"
        for name in self._PLAY_TABS:
            visible = playing and name == tab
            try:
                self.query_one(f"#play-tab-{name}").display = visible
            except Exception:  # noqa: BLE001 — unmounted / absent
                pass
            try:
                btn = self.query_one(f"#tab-{name}", Button)
                btn.set_class(name == tab, "active")
            except Exception:  # noqa: BLE001
                pass
        # The transcript belongs to the 对话 tab; the input line stays on all.
        # (`#ask-user-inline` is left alone: it shows itself only while a
        # question is pending and hides itself after.)
        chat_visible = (not playing) or tab == "chat"
        try:
            self.query_one("#conversation-view").display = chat_visible
        except Exception:  # noqa: BLE001
            pass
        try:
            _lane = self.query_one("#character-status-lane")
            _lane.display = playing and tab == "chat" and not getattr(_lane, "retired", False)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.query_one("#play-stage").set_class(playing and tab != "chat", "tab-wide")
        except Exception:  # noqa: BLE001
            pass
        # The image band's matrix animation must not tick while it is hidden.
        try:
            band_shown = bool(self.query_one("#stage-top").display)
            self.query_one("#portrait-panel", PortraitPanel).set_hidden(not (playing and tab == "chat" and band_shown))
        except Exception:  # noqa: BLE001
            pass
        try:
            scene = self.query_one("#scene-panel", PortraitPanel)
            if playing and tab == "image":
                scene.set_hidden(False)
                scene.refresh_current(self.root)
            else:
                scene.set_hidden(True)
        except Exception:  # noqa: BLE001
            pass
        if playing and tab == "map":
            try:
                panel = self.query_one("#map-panel", MapPanel)
                if getattr(panel, "_root", None) != self.root:
                    panel.set_root(self.root)
                else:
                    panel.reload()
                panel.focus()
            except Exception:  # noqa: BLE001
                pass

    def _relabel_play_tabs(self) -> None:
        from neonrp.tui.i18n import get_message

        loc = self.ui_locale
        for name in self._PLAY_TABS:
            try:
                self.query_one(f"#tab-{name}", Button).label = get_message(loc, f"play.tab.{name}").strip()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.query_one("#play-tab-map", MapView).relabel(
                get_message(loc, "play.map.up"),
                get_message(loc, "play.map.zoom_in"),
                get_message(loc, "play.map.zoom_out"),
                get_message(loc, "play.map.reset"),
            )
        except Exception:  # noqa: BLE001
            pass

    _side_view: str = "state"

    def _toggle_side_view(self, view: str | None = None) -> None:
        """Right column: status doc ↔ resident map."""
        view = view or ("map" if self._side_view == "state" else "state")
        self._side_view = view
        show_map = view == "map"
        for wid, shown in (("#game-state-scroll", not show_map), ("#btn-state-up", not show_map), ("#btn-state-down", not show_map), ("#side-map", show_map)):
            try:
                self.query_one(wid).display = shown
            except Exception:  # noqa: BLE001
                pass
        if show_map:
            try:
                self.query_one("#side-map", MapPanel).refresh()
            except Exception:  # noqa: BLE001
                pass
        self._relabel_side_toggle()

    def _relabel_side_toggle(self) -> None:
        from neonrp.tui.i18n import get_message

        key = "play.side.state" if self._side_view == "map" else "play.side.map"
        try:
            self.query_one("#btn-side-toggle", Button).label = get_message(self.ui_locale, key)
        except Exception:  # noqa: BLE001
            pass

    def _relabel_play_controls(self) -> None:
        """Set play-control button labels for the current locale + state.

        Labels are bracketed (``［ … ］``) so the thin toolbar row reads
        unmistakably as clickable buttons."""
        if self.mode != "play":
            return
        from neonrp.tui.i18n import get_message

        loc = self.ui_locale

        def _bracket(msg: str) -> str:
            return f"［ {msg.strip()} ］"

        try:
            band = self.query_one("#stage-top")
            toggle = self.query_one("#btn-toggle-image", Button)
            shown = bool(band.display)
            toggle.label = _bracket(get_message(
                loc, "play.btn.hide_image" if shown else "play.btn.show_image"
            ))
        except Exception:
            pass
        try:
            self.query_one("#btn-skip-reveal", Button).label = _bracket(
                get_message(loc, "play.btn.skip")
            )
        except Exception:
            pass
        try:
            self.query_one("#btn-gen-scene", Button).label = _bracket(
                get_message(loc, "play.btn.gen_scene")
            )
        except Exception:
            pass
        try:
            self.query_one("#btn-gen-scene-2", Button).label = _bracket(
                get_message(loc, "play.btn.gen_scene")
            )
        except Exception:
            pass
        self._relabel_play_tabs()
        self._relabel_side_toggle()

    # ------------------------------------------------------------------
    # Scene text-to-image — cover on entry, scene on location change,
    # manual on the 生成场景图 button. All routed through one worker.
    # ------------------------------------------------------------------
    def _on_location_changed(self, node: dict[str, Any]) -> None:
        """LocationHeader hook — player moved to a new location."""
        self._kick_scene_imagegen(reason="scene", node=node)

    def _build_scene_prompt(self, node: dict[str, Any] | None) -> tuple[str, str]:
        """Return (prompt, label) for a scene/cover text-to-image call.

        Pulls the location name + summary + tags from the resolved node;
        falls back to the world directory name for an opening cover when
        no location has been entered yet.
        """
        node = node or {}
        name = str(node.get("name") or "").strip()
        summary = str(node.get("summary") or "").strip()
        tags = node.get("tags")
        tag_str = ", ".join(str(t) for t in tags[:5]) if isinstance(tags, list) else ""
        parts = [p for p in (name, summary, tag_str) if p]
        if parts:
            base = ", ".join(parts)
        else:
            base = str(self.root.name).replace("-", " ")
        prompt = f"{base}, wide cinematic establishing shot, atmospheric, no text, no watermark"
        return prompt, name

    def _kick_scene_imagegen(
        self, *, reason: str, node: dict[str, Any] | None = None
    ) -> None:
        """Start a scene text-to-image job (cover / scene / manual).

        No-op when no backend is configured (manual presses get a one-line
        hint). Only one generation runs at a time.
        """
        if self.mode != "play":
            return
        from neonrp.core.imagegen import load_image_config
        from neonrp.tui.i18n import get_message

        cfg = load_image_config()
        if not cfg.is_configured:
            if reason == "manual":
                self._play_status_line(get_message(self.ui_locale, "play.gen.no_backend"))
            return
        if getattr(self, "_imagegen_running", False):
            return

        if node is None:
            # Resolve the current location for cover / manual triggers.
            try:
                from neonrp.tui.location_header import (
                    _read_run_state,
                    _resolve_location_node,
                )
                state = _read_run_state(self.root) or {}
                node = _resolve_location_node(self.root, state.get("location"))
            except Exception:
                node = None

        prompt, label = self._build_scene_prompt(node)
        self._imagegen_running = True
        if reason == "manual":
            self._play_status_line(get_message(self.ui_locale, "play.gen.busy"))

        worker = threading.Thread(
            target=self._imagegen_worker,
            args=(prompt, label, cfg, reason),
            name="neonrp-imagegen",
            daemon=True,
        )
        worker.start()

    def _imagegen_worker(self, prompt: str, label: str, cfg: Any, reason: str) -> None:
        """Thread body: generate the image, copy to latest.png, notify UI."""
        import shutil

        from neonrp.core.imagegen import generate_image

        out_dir = self.root / ".neonrp" / "imagegen"
        try:
            path = generate_image(prompt, out_dir, cfg=cfg, width=1024, height=640)
            latest = out_dir / "latest.png"
            shutil.copyfile(path, latest)
        except Exception as exc:
            self.call_from_thread(self._on_imagegen_failed, str(exc), reason)
            return
        self.call_from_thread(self._on_imagegen_done, latest, label, reason)

    def _on_imagegen_done(self, latest: Path, label: str, reason: str) -> None:
        self._imagegen_running = False
        try:
            panel = self.query_one("#portrait-panel", PortraitPanel)
            panel.show_image(latest, label)
        except Exception:
            pass
        # 任务 A1: the 文生图 tab shows the same picture, large.
        try:
            self.query_one("#scene-panel", PortraitPanel).show_image(latest, label)
        except Exception:
            pass
        if reason == "manual":
            from neonrp.tui.i18n import get_message
            self._play_status_line(get_message(self.ui_locale, "play.gen.done"))

    def _on_imagegen_failed(self, error: str, reason: str) -> None:
        self._imagegen_running = False
        if reason == "manual":
            from neonrp.tui.i18n import get_message
            self._play_status_line(
                get_message(self.ui_locale, "play.gen.failed").format(error=error[:80])
            )

    def _play_status_line(self, text: str) -> None:
        """Write a dim one-liner to the transcript (image-gen feedback)."""
        try:
            view = self.query_one("#conversation-view", ConversationView)
            view.write(f"[dim]{text}[/]\n")
        except Exception:
            pass

    def _handle_result(self, result: ConversationTurnResult) -> None:
        """Handle conversation result."""
        view = self.query_one("#conversation-view", ConversationView)
        self._set_main_input_enabled(True)

        if not result.success:
            self._stream_started = False
            self._clear_run_status()
            view.fail_open_tool_indicators("interrupted")
            error_speaker = str(getattr(result, "assistant_speaker", "") or "").strip()
            from neonrp.core import billing_stop

            stop = billing_stop.remember(billing_stop.from_text(result.error))
            if stop is not None:  # quota / credits / claim: what to do + where, no Retry button (retrying cannot help)
                lang = self._account_lang()
                view.write(f"\n[b yellow]{escape(stop.text(lang))}[/]\n[dim]{escape(stop.hint(lang))}[/]\n")
            else:
                view.add_agent_error(error_speaker, str(result.error or ""))
            view.flush_pending_execution_details()
            self._refresh_status()
            # Always clear the 💭 placeholder on Discord — even when the
            # turn failed — so the remote viewer sees the turn is done
            # rather than being stuck "Thinking…" forever.
            self._emit_bridge_event("turn_status", data={"state": "complete"})
            if self.verbose:
                self._write_verbose_line(f"turn failed: run_id={result.run_id or '-'} error={result.error}")
            return

        if getattr(result, "cancelled", False) is True:
            self._stream_started = False
            self._clear_run_status()
            view._finalize_predicted_tool_indicators(detail="cancelled")
            view.write("[dim]ask_user canceled. Waiting for your next message.[/]\n")
            view.flush_pending_execution_details()
            self._refresh_status()
            self._emit_bridge_event("turn_status", data={"state": "complete"})
            return

        # Note: todo display is now shown inline via _show_tool_result when
        # the TodoWrite callback fires, so we no longer duplicate it here.

        if not self._stream_started:
            fallback_message = getattr(result, "assistant_message", "")
            if isinstance(fallback_message, str) and fallback_message:
                fallback_message = self._normalize_assistant_text(fallback_message)
            if isinstance(fallback_message, str) and fallback_message:
                speaker_hint = str(getattr(result, "assistant_speaker", "") or "").strip()
                speaker = self._get_agent_display_name(speaker_hint) if speaker_hint else self._get_root_speaker_name()
                view.add_named_assistant_message(speaker, fallback_message)
                self._bump_completion_tokens(fallback_message)
        view._finalize_predicted_tool_indicators(detail="not called")
        self._stream_started = False
        view.add_assistant_end()
        view.flush_pending_execution_details()
        self._clear_run_status()
        try:  # 10-08: the turn's options as buttons above the input (they were only "1. …" text lines)
            from neonrp.tui.options_bar import OptionsBar

            self.query_one("#options-bar", OptionsBar).set_options(list(getattr(result, "options", None) or []))
        except Exception:  # noqa: BLE001
            pass
        # Bridge: mark the turn done. If `add_assistant_end` already
        # replaced the 💭 placeholder with a real narration, this is a
        # no-op on the DiscordBridge side. If the turn was silent
        # (all speakers hidden), the placeholder is finalized here.
        self._emit_bridge_event("turn_status", data={"state": "complete"})
        if self.verbose:
            usage = result.usage or {}
            self._write_verbose_line(
                (
                    f"turn ok: run_id={result.run_id} turns={result.turns_used} "
                    f"prompt={usage.get('prompt_tokens', 0)} completion={usage.get('completion_tokens', 0)} "
                    f"tools={len(result.tool_calls_made)} files={len(result.files_modified)}"
                )
            )

        # M31 B2: the turn's change ledger. Individual write cards scroll
        # past; this is the one line that answers "so what did it change".
        self._write_change_ledger_line(view)

        # Update status
        self._refresh_status()

        # sandbox 的提案流已随 /apply /autoapply 一起退役:sandbox 沉为引擎
        # 内部的子 agent 干跑,不再是人可见的模式(docs/COMMANDS.md)。

    def _write_change_ledger_line(self, view: "ConversationView") -> None:
        """Print this turn's file-change summary (M31 B2), if it moved any.

        Build-side only: in play the world writes itself constantly and a
        file ledger would be noise, not information.
        """
        if self.mode != "build" or not self.session:
            return
        ledger = getattr(self.session, "change_ledger", None)
        if ledger is None or getattr(ledger, "is_empty", True):
            return
        try:
            headline = ledger.headline()
            paths = [entry["path"] for entry in ledger.to_dict().get("files", [])]
        except Exception:  # noqa: BLE001 — a ledger glitch must not eat a turn
            return
        if not headline:
            return
        shown = ", ".join(paths[:4])
        if len(paths) > 4:
            shown = f"{shown} …+{len(paths) - 4}"
        view.write(f"\n[dim]◇ 本回合 {headline}[/]\n")
        if shown:
            view.write(f"[dim]  {shown}[/]\n")

    def _refresh_status(self, include_event_count: bool = True) -> None:
        """Refresh status bar."""
        model_display = self._get_status_model_display()
        world_time, world_location = self._read_world_status_snapshot()
        try:
            input_area = self.query_one("#input-area", InputArea)
        except Exception:
            return
        _ = include_event_count
        input_area.update_status(
            mode=self.session.mode if self.session else self.mode,
            router_mode=self._get_router_mode_status(),
            model_display=model_display,
            world_time=world_time,
            world_location=world_location,
            connection_state=self._get_connection_status_text(),
            prompt_tokens=self._est_prompt_tokens_total,
            completion_tokens=self._est_completion_tokens_total,
        )

    def _read_world_status_snapshot(self) -> tuple[str, str]:
        """Read lightweight world time/location labels for the inline status area."""
        run_state_path = get_game_dir(self.root) / "meta" / "run_state.json"
        if not run_state_path.exists():
            return "-", "-"
        try:
            payload = json.loads(run_state_path.read_text(encoding="utf-8"))
        except Exception:
            return "-", "-"
        if not isinstance(payload, dict):
            return "-", "-"
        return self._format_world_time(payload.get("time")), self._format_world_location(payload.get("location"))

    @staticmethod
    def _format_world_time(raw_time: Any) -> str:
        """Format world time for compact inline display."""
        if not isinstance(raw_time, dict):
            return "-"
        day = raw_time.get("day")
        clock = str(raw_time.get("clock") or "").strip()
        if day in {None, ""} and not clock:
            return "-"
        day_text = f"Day {day}" if day not in {None, ""} else "-"
        if clock:
            return f"{day_text} {clock}".strip()
        return day_text

    def _format_world_location(self, raw_location: Any) -> str:
        """Resolve a compact world location label from run_state location data."""
        if not isinstance(raw_location, dict):
            return "-"

        display = str(raw_location.get("display") or "").strip()
        if display:
            return display.replace("·", "・")

        scope = str(raw_location.get("scope") or "").strip().lower()
        node_id = str(raw_location.get("node_id") or "").strip()
        subnode_id = str(raw_location.get("subnode_id") or raw_location.get("zone") or "").strip()
        if not node_id and not subnode_id:
            return "-"

        if scope == "town" and node_id:
            game_dir = get_game_dir(self.root)
            town_name = node_id
            zone_name = subnode_id
            town_path = game_dir / "towns" / node_id / "town.json"
            try:
                from neonrp.core.place_tree import level_doc

                if town_path.exists():
                    town_payload = json.loads(town_path.read_text(encoding="utf-8"))
                    if isinstance(town_payload, dict):
                        town_name = str(town_payload.get("name") or town_name).strip() or town_name
                if town_name == node_id:  # no town.json: the world map's own name for it
                    for node in (level_doc(self.root, "world") or {}).get("nodes") or []:
                        if isinstance(node, dict) and node.get("id") == node_id and node.get("name"):
                            town_name = str(node["name"])
                if subnode_id:
                    town_map_payload = level_doc(self.root, node_id)  # town_map.json or the town's place folders
                    if isinstance(town_map_payload, dict):
                        for node in town_map_payload.get("nodes", []):
                            if isinstance(node, dict) and str(node.get("id") or "").strip() == subnode_id:
                                zone_name = str(node.get("name") or zone_name).strip() or zone_name
                                break
            except Exception:
                pass
            return "・".join(part for part in [town_name, zone_name] if part) or "-"

        return "・".join(part for part in [node_id, subnode_id] if part) or "-"

    def _get_connection_status_text(self) -> str:
        """Build compact connection-status text for inline metadata."""
        try:
            from neonrp.core.discord_config import get_discord_inline_status

            discord_state = get_discord_inline_status()
        except Exception:
            discord_state = "off"
        return f"discord:{discord_state}"

    def _get_router_mode_status(self) -> str:
        """Return the current router execution mode for compact status display."""
        try:
            return get_router_execution_mode(self.root)
        except Exception:
            return "-"

    def _resolve_ui_locale(self) -> str:
        """Resolve the active TUI locale from config/environment."""
        try:
            configured = load_config(self.root).tui.language
        except Exception:
            configured = "auto"
        return resolve_locale(configured)

    def _get_status_model_display(self) -> str:
        """Build a concise label for the currently effective model."""
        try:
            provider_cfg = self._get_effective_provider_config()
            model_name = (provider_cfg.model or "").strip() or "(default)"
            if len(model_name) > 28:
                model_name = f"{model_name[:25]}..."
            return f"{provider_cfg.provider}:{model_name}"
        except Exception:
            return "unknown"

    @staticmethod
    def _usage_token_pair(usage: dict[str, Any]) -> tuple[int, int]:
        """Extract prompt/completion token counts across provider usage formats."""
        nested = usage.get("usage")
        if isinstance(nested, dict):
            usage = {**nested, **usage}

        prompt_aliases = ("prompt_tokens", "input_tokens", "promptTokenCount")
        completion_aliases = ("completion_tokens", "output_tokens", "completionTokenCount")

        def _to_int(value: Any) -> int:
            try:
                return max(0, int(value or 0))
            except Exception:
                return 0

        prompt = next((_to_int(usage.get(k)) for k in prompt_aliases if usage.get(k) is not None), 0)
        completion = next((_to_int(usage.get(k)) for k in completion_aliases if usage.get(k) is not None), 0)

        # Some providers only return a combined token count.
        if prompt == 0 and completion == 0:
            total = _to_int(usage.get("total_tokens") or usage.get("token_count"))
            if total > 0:
                return total, 0
        return prompt, completion

    def _maybe_add_fallback_token_usage(self, result: ConversationTurnResult) -> None:
        """Estimate token usage when provider doesn't return prompt/completion counts."""
        _ = result
        return

    # === M18 Phase E — TUI surfacing of the multi-agent runtime =========
    #
    # Pure cosmetic: E1 renders the world-agent's CharacterRuntime registry,
    # E2 wires a hotkey to the committed interrupt primitive. None of this
    # mutates turn / commit logic or the registry.

    def _character_runtimes(self) -> dict[str, Any]:
        """Read the world-agent's CharacterRuntime registry (read-only).

        Reaches the world-agent through the *already-constructed* session
        only — it deliberately does NOT call ``_get_world_agent()`` (which
        would lazily construct one) so a legacy single-agent session never
        gets a world-agent it otherwise wouldn't have. Any attribute miss
        (no session, no world-agent yet, future refactor) collapses to an
        empty dict so the lane simply renders nothing.
        """
        session = self.session
        if session is None:
            return {}
        world_agent = getattr(session, "_world_agent", None)
        if world_agent is None:
            return {}
        registry = getattr(world_agent, "_characters", None)
        # Copy so a concurrent registry mutation can't change the dict
        # mid-iteration in the render path. We never write it back.
        return dict(registry) if isinstance(registry, dict) else {}

    def _prime_soul_lane(self) -> None:
        """Seed the lane from playthrough.json at mount so a multi-agent
        play session shows the full soul roster (all 待命) from launch and
        the lane is a PERSISTENT fixture — not something that only
        flickers into existence mid-turn. Non-multi-agent / no-playthrough
        worlds get an empty snapshot ⇒ lane collapses (legacy unchanged).
        """
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.root)
            if pt is None or not pt.souls:
                return
            active = set(getattr(pt, "active_souls", ()) or ())
            snap: dict[str, dict[str, str]] = {}
            for s in pt.souls:
                sd = self.root / "souls" / f"{s.sid}-{s.instance_id}"
                name = s.sid
                try:
                    import json as _json

                    m = _json.loads(
                        (sd / "soul.json").read_text(encoding="utf-8")
                    )
                    name = m.get("name_local") or m.get("name") or s.sid
                except (OSError, ValueError):
                    pass
                snap[s.instance_id] = {
                    "name": name,
                    "role": "active" if s.instance_id in active else "inactive",
                    "state": "queued" if s.instance_id in active else "background",
                }
            self._soul_status_snapshot = snap
            self._refresh_character_lane()
        except Exception:
            # Cosmetic priming only — never block mount.
            return

    def _refresh_character_lane(self) -> None:
        """Repaint the persistent soul lane from the latest unified
        lifecycle snapshot (fed by the engine's on_soul_status callback).

        The old CharacterRuntime registry this read was removed with the
        bespoke layer (#61); the unified soul=agent path emits a
        ``{instance_id: {name, role, state}}`` snapshot instead.
        """
        try:
            lane = self.query_one("#character-status-lane", CharacterStatusLane)
        except Exception:
            # Lane absent (build / sandbox, or not mounted yet) — nothing
            # to surface; this is a cosmetic no-op by design.
            return
        lane.render_soul_status(getattr(self, "_soul_status_snapshot", {}) or {})

    def _settlement_now(self, ev: dict[str, Any] | None = None) -> dict[str, Any]:
        """The run's settlement: game/meta/settlement.json (the whole record), else what the event carried."""
        try:
            from neonrp.core import settlement as _st

            rec = _st.read(self.root) if self.root else None
            if rec:
                return rec
        except Exception:  # noqa: BLE001
            pass
        return {k: v for k, v in (ev or {}).items() if k != "kind"}

    def _item_cards(self, ev: dict[str, Any]) -> list[Any]:
        """The items this beat created, read back from the registry (their props as the narrator wrote them)."""
        from neonrp.tui import beats as _beats

        made = [c for c in ev.get("created") or [] if isinstance(c, dict) and c.get("id")]
        if not made or not self.root:
            return []
        try:
            from neonrp.core.registry import load_registry

            reg = load_registry(self.root)
        except Exception:  # noqa: BLE001
            return []
        out = []
        for c in made:
            cls = str(c.get("class") or "")
            if not _beats.is_item_class(cls, reg.classes.get(cls)):
                continue
            e = reg.entries.get(str(c["id"]))
            props = dict(e.props) if e is not None else {}
            out.append(_beats.item_card(str(c.get("name") or (e.name if e is not None else c["id"])), props))
        return out

    def _beat_decl(self, node: str) -> dict[str, Any]:
        """The engine's declaration of how this beat is shown (orchestration.beat_kinds; cached per session)."""
        cache = getattr(self, "_beat_kinds_cache", None)
        if cache is None:
            try:
                from neonrp.core.orchestration import beat_kinds

                cache = dict(beat_kinds(self.root).get("kinds") or {}) if self.root else {}
            except Exception:  # noqa: BLE001
                cache = {}
            self._beat_kinds_cache = cache
        d = cache.get(str(node))
        return dict(d) if isinstance(d, dict) else {}

    def _is_mode_layer(self, node: str) -> bool:
        try:
            from neonrp.core import modes as _modes

            return bool(_modes.spec_of(self.root, str(node)))
        except Exception:  # noqa: BLE001
            return False

    def _layer_title(self, node: str) -> str:
        """A mode layer's own title from the pack (战斗裁判 / Combat referee …), in the run's language; else its id."""
        try:
            from neonrp.core import modes as _modes
            from neonrp.core.output_lang import pick_lang, prompt_lang

            spec = _modes.spec_of(self.root, str(node)) or {}
            if spec.get("title"):
                return str(pick_lang(spec.get("title"), prompt_lang(self.root)) or node)
        except Exception:  # noqa: BLE001
            pass
        return str(node)

    def _show_mode_tag(self, node: str | None) -> None:
        """The place header's standing tag: the mode layer's own title (pack data, run's language) while the world is in
        a mode layer; cleared on any other beat."""
        label = self._layer_title(node) if node and self._is_mode_layer(node) else ""
        try:
            self.query_one("#location-header", LocationHeader).set_mode(label)
        except Exception:  # noqa: BLE001
            pass

    def _beats_shown_as_text(self) -> bool:
        """turn.display.beats on: the engine already writes the beat skeleton (dice lines included) into the prose."""
        try:
            from neonrp.core import beat_display as _bd

            return bool(self.root and _bd.enabled(self.root))
        except Exception:  # noqa: BLE001
            return False

    def _judge_hint(self) -> None:
        """10-24 niko: with no Jev and no account the talk never settled by itself and the host kept asking. One dim line
        the first time a planning beat lands in this session: who judges now (the run's own model, a few seconds; or
        nobody: the commit word or @dm), and that /login turns Jev on."""
        try:
            from rich.text import Text

            from neonrp.core import system_one as _s1

            if _s1.backend_name() != "off":
                return
            key = "judge.own_hint" if _s1.own_model_judge(getattr(self, "root", None)) else "judge.off_hint"
            view = self.query_one("#conversation-view", ConversationView)
            view.add_beat_row(Text(self._sugg(key), style="dim"), "beat-judge-hint")
        except Exception:  # noqa: BLE001 — a hint, never in the way
            pass

    def _apply_beat_event(self, ev: dict[str, Any]) -> None:
        """One engine/beat event (UI thread): kept in the session's BeatState (read by /plan · /dice · /status);
        entering a beat draws its band in the conversation."""
        from neonrp.tui import beats as _beats

        state = getattr(self, "_beat_state", None)
        if state is None:
            state = self._beat_state = _beats.BeatState()
        node = state.feed(ev)
        kind = str(ev.get("kind") or "")
        if kind == "plan.beat" and not getattr(self, "_judge_hint_shown", False):
            self._judge_hint_shown = True
            self._judge_hint()
        if kind in ("node.enter", "node.leave"):  # a mode layer stands as a tag in the place header
            self._show_mode_tag(state.node)
        try:
            view = self.query_one("#conversation-view", ConversationView)
            if kind == "dice" and not self._beats_shown_as_text():
                from neonrp.core import beat_display as _bd

                from neonrp.core.output_lang import prompt_lang as _pl_d

                line = _bd._dice_line(ev, _pl_d(self.root))
                widget = ConversationView._build_dice_widget(line, level=_bd.outcome_level(ev)) if line else None
                view.add_beat_row(widget if widget is not None else _beats.tool_text(ev), "beat-dice")
                from neonrp.tui.play_hints import dice_detail

                _why = dice_detail(ev, self.ui_locale)  # which skill · why this tier · what for (10-23, the web's dice card)
                if _why is not None:
                    view.add_beat_row(_why, "beat-dice-why")
            elif kind == "tool":
                view.add_beat_row(_beats.tool_text(ev), "beat-tool")
            elif kind.startswith("write_down."):  # the background write-down: under way, then what it did (10-22)
                view.add_beat_row(_beats.write_down_text(ev, self.ui_locale), "beat-tool")
            elif kind == "plan.beat" and not self._beats_shown_as_text():
                view.add_beat_row(_beats.plan_text(ev), "beat-plan")
            elif kind == "state.changed":
                view.add_beat_row(_beats.change_text(ev), "beat-changes")
                for _card in self._item_cards(ev):  # picked-up items as cards, field by field
                    view.add_beat_row(_card, "beat-item")
            elif kind == "resolve.beat":
                for _pv in (ev.get("panels") or {}).values():  # the map / sheet / formation this beat drew
                    if isinstance(_pv, dict) and (_pv.get("text") or _pv.get("data") or _pv.get("fallback")):
                        view.add_beat_row(_beats.panel_renderable(_pv), "beat-panel")
            elif kind == "run.settled":
                view.add_beat_row(_beats.settlement_text(self._settlement_now(ev), self.ui_locale), "beat-settlement")
        except Exception:  # noqa: BLE001 — rows are decoration; never break the turn
            pass
        if kind in ("state.changed", "resolve.beat", "run.settled"):
            self._refresh_play_hints(fresh=True)  # what is here / held / the sheet may have changed (10-23)
            try:
                from neonrp.tui.status_side import StatusSide

                self.query_one("#status-side", StatusSide).refresh_state()
            except Exception:  # noqa: BLE001
                pass
        if not node:
            return
        # 10-10 R1: the TUI knows no beat by itself — a beat's name and colour are what the engine declares (beat-kinds);
        # a mode layer shows its own title; anything else its node id, neutral
        decl = self._beat_decl(node)
        if decl:
            label, color = str(decl.get("label") or node), _beats.tone_color(decl.get("tone"))
        elif self._layer_title(node) != str(node) or self._is_mode_layer(node):
            label, color = f"{self._layer_title(node)} · {get_message(self.ui_locale, 'beat.layer')}", _beats.LAYER_COLOR
        else:
            label, color = str(node), _beats.NEUTRAL_COLOR
        try:
            self.query_one("#conversation-view", ConversationView).add_beat_marker(label, color)
        except Exception:
            pass  # a beat band is decoration; never break the turn

    def _apply_soul_status_snapshot(
        self, snapshot: dict[str, dict[str, str]]
    ) -> None:
        """Apply one exact soul lifecycle snapshot on the UI thread.

        Do not let worker-thread callbacks mutate ``_soul_status_snapshot``
        directly and then enqueue a generic repaint: fast queued→running→done
        transitions can otherwise coalesce into repeated renders of only the
        final state. Passing the snapshot through the UI callback preserves the
        transition order Textual receives.
        """
        self._soul_status_snapshot = {
            str(k): dict(v) for k, v in (snapshot or {}).items()
        }
        self._refresh_character_lane()
        try:  # the same lifecycle beside each name in the right column's Agent view
            from neonrp.tui.status_side import StatusSide

            self.query_one("#status-side", StatusSide).set_lifecycle(self._soul_status_snapshot)
        except Exception:  # noqa: BLE001
            pass

    def _focused_character_sid(self) -> str | None:
        """The sid the cancel hotkey targets.

        Heuristic for v1 (the design only asks for *a* cancel hotkey): the
        first character whose task is still in flight in sorted-sid order —
        that is the one a runaway-cost cancel actually wants. Falls back to
        the first registered sid if none is running, ``None`` if the
        registry is empty (hotkey becomes a no-op).
        """
        runtimes = self._character_runtimes()
        if not runtimes:
            return None
        for sid in sorted(runtimes):
            task = getattr(runtimes[sid], "task", None)
            if task is not None and not task.done():
                return sid
        return sorted(runtimes)[0]

    def action_cancel_character(self) -> None:
        """Phase E2 — interrupt the focused character-agent (Ctrl+X).

        Delegates verbatim to the committed
        ``world_agent.interrupt(sid)`` primitive (§3.2). We do not
        reimplement the soft/hard cancel here — ``interrupt`` is an
        ``async`` coroutine, so we schedule it on the running loop and let
        the world-agent own the ack / hard-cancel escalation exactly as
        Phase C built it. The lane repaints so the state flips visibly.
        """
        sid = self._focused_character_sid()
        if sid is None:
            return
        session = self.session
        world_agent = (
            getattr(session, "_world_agent", None) if session is not None else None
        )
        if world_agent is None:
            return
        try:
            # interrupt() is a coroutine; hand it to the event loop rather
            # than awaiting (this action is sync). We don't track the task
            # — the world-agent owns the cancel lifecycle, we only kicked it.
            self.call_later(self._schedule_interrupt, world_agent, sid)
        except Exception:
            # A cosmetic hotkey must never take the app down.
            return

    def _schedule_interrupt(self, world_agent: Any, sid: str) -> None:
        """Fire ``world_agent.interrupt(sid)`` on the running loop."""
        import asyncio

        try:
            asyncio.ensure_future(world_agent.interrupt(sid))
        except Exception:
            return
        self._refresh_character_lane()

    def action_command_palette(self) -> None:
        """Show command palette."""

        def handle_result(command: str | None) -> None:
            if command:
                self._execute_command(command, [])

        self.push_screen(CommandPalette(), handle_result)

    def action_safe_quit(self) -> None:
        """Quit safely even if an LLM request is in flight.

        Flushes unsaved session messages before exit so that work done
        during a long tool-calling loop is not lost.
        """
        self._sync_finalize_pending_ask_user()
        if self.session:
            try:
                self.session.flush()
            except Exception:
                pass
        self.action_quit()

    def action_quit(self) -> None:
        """Quit TUI and return terminal control immediately."""
        # Synchronous direct-to-disk close of any pending ask_user *before*
        # signalling the worker so the JSONL is guaranteed coherent even
        # if the worker thread doesn't get a chance to write its own
        # cancel result before the process exits.
        self._sync_finalize_pending_ask_user()
        self._cancel_active_ask_user()
        self._clear_run_status()
        self.exit()

    def action_copy_transcript(self) -> None:
        """Copy full conversation transcript to clipboard."""
        self._cmd_copy()

    def action_show_debug(self) -> None:
        """F12 — open the LLM-call debug panel. Active only when the engine
        was started with ``NEONRP_DEBUG=1`` (and not under ``python -O``);
        otherwise the binding is unregistered and this method is unreachable."""
        if not DEBUG_ENABLED:
            return
        from neonrp.tui.debug_panel import DebugScreen
        self.push_screen(DebugScreen())

    def action_toggle_portrait(self) -> None:
        """Show / hide the whole top band (scene image + game-state).

        Collapsing the band hands the freed rows to the transcript; the
        matrix animation is paused while hidden so it costs nothing.
        """
        try:
            band = self.query_one("#stage-top")
        except Exception:
            return
        hide = bool(band.display)
        band.display = not hide
        try:
            panel = self.query_one("#portrait-panel", PortraitPanel)
            panel.set_hidden(hide)
        except Exception:
            pass

    def action_skip_typewriter(self) -> None:
        """Esc — jump the streaming typewriter reveal straight to the end."""
        try:
            view = self.query_one("#conversation-view", ConversationView)
            view.skip_typewriter()
        except Exception:
            return

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        """Gate the Esc binding: it only does anything while a typewriter
        reveal is mid-flight, so Esc stays free for everything else."""
        if action == "skip_typewriter":
            try:
                view = self.query_one("#conversation-view", ConversationView)
                return view.typewriter_active()
            except Exception:
                return False
        return True

    def action_cycle_layer(self) -> None:
        """Cycle transcript visibility between L1 / L2 / L3 (Ctrl+L)."""
        current = getattr(self, "_semantic_layer", 2)
        next_layer = {1: 2, 2: 3, 3: 1}.get(int(current), 2)
        try:
            view = self.query_one("#conversation-view", ConversationView)
            view.set_semantic_layer(next_layer)
        except Exception:
            return
        self._semantic_layer = next_layer
        label = {
            1: "L1 · narrative only",
            2: "L2 · narrative + semantic chips",
            3: "L3 · + raw tool trace",
        }[next_layer]
        try:
            view.write(f"[dim]{label}[/]\n")
        except Exception:
            pass

    def _execute_command(self, command: str, args: list[str]) -> None:
        """Execute a command from palette."""
        command_text = f"/{command}"
        if args:
            command_text = f"{command_text} {' '.join(args)}"
        self._handle_slash_command(command_text)

    def _execute_validate(self, view: ConversationView) -> None:
        """Execute validate command — the world playability health-check."""
        view.write("[dim]Validating...[/]\n")
        try:
            from neonrp.core.validation import check_world

            health = check_world(self.root)
            s = health.stats
            summary = (
                f"{s.get('flavor', '?')} · {s.get('souls', 0)} soul(s) · "
                f"{s.get('locations', 0)} location(s) · {s.get('entities', 0)} entities"
            )
            if health.playable:
                view.write(f"[green]✓ playable — {summary}[/]\n")
            else:
                view.write(f"[red]✗ NOT playable — {len(health.blockers)} blocker(s)[/]\n")
                for issue in health.blockers[:8]:
                    view.write(f"  [red]- {issue.file}: {issue.message}[/]\n")
                if len(health.blockers) > 8:
                    view.write(f"  [red]… and {len(health.blockers) - 8} more[/]\n")
            if health.warnings:
                view.write(f"[yellow]⚠ {len(health.warnings)} warning(s)[/]\n")
                for issue in health.warnings[:5]:
                    view.write(f"  [yellow]- {issue.file}: {issue.message}[/]\n")
                if len(health.warnings) > 5:
                    view.write(f"  [yellow]… and {len(health.warnings) - 5} more[/]\n")
        except Exception as e:
            view.write(f"[red]Validation failed: {e}[/]\n")

    def _execute_index(self, view: ConversationView, args: list[str]) -> None:
        """Execute index command."""
        view.write("[dim]Building index...[/]\n")
        try:
            from neonrp.core.indexing import build_index

            index = build_index(self.root)
            view.write(f"[green]Indexed {len(index.entities)} entities[/]\n")
        except Exception as e:
            view.write(f"[red]Index failed: {e}[/]\n")


def run_tui(
    root: Path | None = None,
    branch: str | None = None,
    provider: str | None = None,
    continue_session: bool = False,
    startup_commands: list[str] | None = None,
    verbose: bool = False,
    mode: AppMode = "build",
) -> None:
    """Run the TUI."""
    while True:
        app = NeonRPApp(
            root=root,
            branch=branch,
            provider=provider,
            continue_session=continue_session,
            startup_commands=startup_commands,
            verbose=verbose,
            mode=mode,
        )
        app.run()

        # `/open` 换世界:退出当前 app,用新 root 再起一局(见 _ReopenRequest)。
        request = getattr(app, "reopen_request", None)
        if request is None:
            return
        root = request.root
        continue_session = request.continue_session
        if request.mode is not None:
            mode = request.mode
        # 分支与启动命令属于**上一局** —— 带过去会在新世界里重放一遍。
        # 交接单自己带的启动输入除外(`/init` 递给 build agent 的设定)。
        branch = None
        startup_commands = list(request.startup_commands or []) or None


def run_worldlines_launcher() -> WorldLinesLaunchSelection | None:
    """Run the public WorldLines launcher flow and return the chosen startup selection."""
    app = WorldLinesLauncherApp()
    app.run()
    return app.launch_selection

