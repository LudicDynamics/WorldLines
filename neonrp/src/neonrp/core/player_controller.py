"""Deterministic player-controller preflight for M18 live spine.

The player controller is not an LLM agent. It is the control-plane boundary
between the human player's raw input and the role=player soul. Its job is to
preserve player action sovereignty before soul agents run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from neonrp.core.paths import get_data_dir_name

PlayerInputKind = Literal["empty", "start_or_continue", "declared_action"]

_START_MARKERS = {
    "start",
    "begin",
    "continue",
    "resume",
    "开始",
    "开始游戏",
    "开始冒险",
    "继续",
    "继续游戏",
}


@dataclass(frozen=True)
class PlayerTurnIntent:
    """Control-plane interpretation of the human player's input."""

    raw_input: str
    kind: PlayerInputKind
    declared_action: str = ""
    avatar_action_authorized: bool = False
    language_hint: str = "auto"
    controller_path: str = "game/player/controller.json"
    policy: dict[str, Any] = field(default_factory=dict)

    @property
    def is_start_or_continue(self) -> bool:
        return self.kind == "start_or_continue"

    def to_prompt_block(self) -> str:
        # Machine-readable signals only. The player-sovereignty *doctrine*
        # lives in the world-agent system.md (the authoritative layer);
        # repeating it as injected prose every turn was dead weight.
        action = self.declared_action if self.declared_action else "(none)"
        return "\n".join(
            [
                "【PlayerTurnIntent】",
                f"raw_input: {self.raw_input or '(empty)'}",
                f"kind: {self.kind}",
                f"declared_avatar_action: {action}",
                f"avatar_action_authorized: {str(self.avatar_action_authorized).lower()}",
                f"language_hint: {self.language_hint}",
            ]
        )


@dataclass(frozen=True)
class ScenePacket:
    """World preflight packet broadcast to active souls and world-agent."""

    scene_label: str
    location: dict[str, Any] = field(default_factory=dict)
    time: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    player_summary: str = ""
    startup_opening: str = ""
    startup_choices: list[str] = field(default_factory=list)
    player_state_path: str = "game/player"
    # M18 feedback loop: the world-agent's narration from the PREVIOUS turn,
    # so every soul sees what happened last round (not just cold location+time).
    last_narration: str = ""
    # Surgical nav feed: the soul's current place name + the adjacent nodes it
    # may move to THIS turn (canonical town_map ids). Empty for the player feed
    # and for souls in wilderness (no town_map). See core/place_nav.py.
    place_name: str = ""
    exits: list[dict[str, str]] = field(default_factory=list)
    # P1/P2 — the player's DECLARED action this turn (the parsed action intent,
    # NOT raw_input: no inbox/OOC/meta). Carried ONLY in co-located souls'
    # packets (scene_understanding strips it for away souls) so people in the
    # player's scene perceive what the player just did; empty otherwise.
    player_declared_action: str = ""

    def to_prompt_block(self) -> str:
        choices = ", ".join(self.startup_choices) if self.startup_choices else "(none)"
        opening = self.startup_opening or "(none)"
        parts = [
            "【WorldPreflight / ScenePacket】",
            f"scene: {self.scene_label}",
            f"turn_count: {self.turn_count}",
            f"location: {json.dumps(self.location, ensure_ascii=False, sort_keys=True)}",
            f"time: {json.dumps(self.time, ensure_ascii=False, sort_keys=True)}",
            f"player_state: {self.player_state_path}",
            f"player_summary: {self.player_summary or '(unknown)'}",
            f"startup_opening: {opening}",
            f"startup_choices: {choices}",
        ]
        if self.exits:
            exit_lines = "\n".join(
                f"  - {e.get('id')}（{e.get('name')}）" for e in self.exits
            )
            here = f"{self.place_name}（{(self.location or {}).get('node','')}）" if self.place_name else (self.location or {}).get("node", "")
            parts.append(
                "【你当前所在与可前往的相邻地点】\n"
                f"当前: {here}\n"
                "若你这回合决定移动,`moved_to` 必须填下列某个 node id(去更远处先走到通往那里的相邻节点):\n"
                f"{exit_lines}"
            )
        if self.last_narration:
            parts.append(
                "【上一回合的世界叙事——你身处的这个世界刚刚发生了什么】\n"
                f"{self.last_narration}"
            )
        if self.player_declared_action:
            parts.append(
                "【玩家本轮的行动——与你同场的那个独立的人类玩家,此刻做了/说了】\n"
                f"{self.player_declared_action}\n"
                "(这是发生在你眼前、本回合的事;依你自己的人格去感知与回应。"
                "它不是你的台词,也不要替玩家叙述或替他决定下一步。)"
            )
        return "\n".join(parts)


def build_player_turn_intent(root: Path, user_text: str) -> PlayerTurnIntent:
    """Parse raw human input without delegating player agency to a soul."""

    raw = str(user_text or "").strip()
    controller = _read_json(root / get_data_dir_name(root) / "player" / "controller.json")
    policy = controller.get("policy", {}) if isinstance(controller, dict) else {}
    language_hint = str(
        (controller or {}).get("language_hint")
        or policy.get("language_hint")
        or "auto"
    )

    if not raw:
        return PlayerTurnIntent(
            raw_input=raw,
            kind="empty",
            language_hint=language_hint,
            policy=policy if isinstance(policy, dict) else {},
        )

    if _is_start_or_continue(raw):
        return PlayerTurnIntent(
            raw_input=raw,
            kind="start_or_continue",
            declared_action="",
            avatar_action_authorized=False,
            language_hint=language_hint,
            policy=policy if isinstance(policy, dict) else {},
        )

    return PlayerTurnIntent(
        raw_input=raw,
        kind="declared_action",
        declared_action=raw,
        avatar_action_authorized=True,
        language_hint=language_hint,
        policy=policy if isinstance(policy, dict) else {},
    )


def build_scene_packet(root: Path, intent: PlayerTurnIntent) -> ScenePacket:
    """Read deterministic world/player context before soul fan-out."""

    data_dir_name = get_data_dir_name(root)
    data_root = root / data_dir_name
    run_state = _read_json(data_root / "meta" / "run_state.json")
    if not isinstance(run_state, dict):
        run_state = {}
    location = run_state.get("location") if isinstance(run_state.get("location"), dict) else {}
    time = run_state.get("time") if isinstance(run_state.get("time"), dict) else {}
    turn_count = _coerce_int(run_state.get("turn_count"), default=0)

    startup = _read_json(data_root / "meta" / "game-start.json")
    startup_block = startup.get("startup") if isinstance(startup, dict) else {}
    if not isinstance(startup_block, dict):
        startup_block = {}
    include_startup = intent.is_start_or_continue and turn_count <= 0

    profile = _read_json(data_root / "player" / "profile.json")
    player_summary = _player_summary(profile if isinstance(profile, dict) else {})
    # The player's state folder. game/player/ today; the M16 disk reorg will
    # move this to players/<pid>/. No projection contract — the player owns
    # this folder outright (player_projection.py retired).
    player_state_path = f"{data_dir_name}/player"

    display = (
        location.get("display")
        or location.get("node")
        or location.get("node_id")
        or "未知地点"
    )
    day = time.get("day") or time.get("cycle_day") or "?"
    clock = time.get("clock") or time.get("period") or "?"
    scene_label = f"{display} · 第{day}日·{clock}"
    opening: tuple[str, list[str]] = ("", [])
    if include_startup:
        from neonrp.core.output_lang import pick_opening, prompt_lang

        opening = pick_opening(startup_block, prompt_lang(root))

    return ScenePacket(
        scene_label=scene_label,
        location=dict(location),
        time=dict(time),
        turn_count=turn_count,
        player_summary=player_summary,
        startup_opening=opening[0] if include_startup else "",
        startup_choices=opening[1] if include_startup else [],
        player_state_path=player_state_path,
        last_narration=_read_last_narration(root),
        # P1: the parsed declared action (empty for start/continue/observe).
        # NOT raw_input — co-located souls perceive the action, not the OOC blob.
        player_declared_action=str(getattr(intent, "declared_action", "") or ""),
    )


def strip_choice_block(text: str) -> str:
    """Remove a trailing player-facing option list (「你可以：…」 + bullets)
    from a narration before a SOUL perceives it.

    The choice menu is game-UI text addressed to the HUMAN; an autonomous
    soul must not have it in its context (it would menu-feed an agent that
    has its own agenda). Only strips when a 你可以 / You can: line is closely
    followed by bullets — ordinary prose mentioning 你可以 is left alone.
    """
    if not text:
        return text
    lines = text.splitlines()
    marker = -1
    for i, line in enumerate(lines):
        if "你可以" in line or "You can:" in line:
            for nxt in lines[i + 1 : i + 4]:
                if nxt.strip().startswith(("-", "→", "*", "•")):
                    marker = i
                    break
    if marker < 0:
        return text
    return "\n".join(lines[:marker]).rstrip()


def read_last_narration(
    root: Path,
    *,
    location_node: str | None = None,
    accept_untagged: bool = True,
) -> str:
    """The most recent ``world/narration`` text for a perspective (M22).

    - ``location_node=None`` — the player feed: the newest narration from a
      non-location world-agent (``loc:*`` narrations never leak to the player).
    - ``location_node="<node>"`` — that location's feed: the newest narration
      tagged with that location. ``accept_untagged`` controls whether legacy
      records with no location field count as a match (True for the player's
      own scene; False for away locations — an away soul must not receive the
      player-scene narration).

    Scans the last few trace lines newest-first (capped at 1200 chars).
    Best-effort: any failure returns ``""`` — a missing trace never breaks a
    turn.
    """
    try:
        from neonrp.core.orchestration_trace import read_turn_traces

        branch = _current_branch(root)
        traces = read_turn_traces(root, branch, last=5)
        for trace in reversed(traces):
            for msg in reversed(trace.get("bus_messages", [])):
                if msg.get("topic") != "world/narration":
                    continue
                payload = msg.get("payload", {})
                text = str(payload.get("text", ""))
                if not text:
                    continue
                tagged = payload.get("location")
                from_loc_agent = str(payload.get("world_agent_id", "")).startswith("loc:")
                if location_node is None:
                    if from_loc_agent:
                        continue  # player feed never carries a loc-agent narration
                    return text[:1200]
                if tagged == location_node:
                    return text[:1200]
                if tagged is None and accept_untagged and not from_loc_agent:
                    return text[:1200]
    except Exception:
        pass
    return ""


def _read_last_narration(root: Path) -> str:
    """Back-compat alias for the player-feed read."""
    return read_last_narration(root)


def _current_branch(root: Path) -> str:
    try:
        m = _read_json(root / ".neonrp" / "manifest.json")
        return str((m or {}).get("current_branch", "main"))
    except Exception:
        return "main"


def _is_start_or_continue(text: str) -> bool:
    normalized = text.strip().lower()
    if normalized in _START_MARKERS:
        return True
    compact = "".join(normalized.split())
    return compact in _START_MARKERS


def _player_summary(profile: dict[str, Any]) -> str:
    name = profile.get("name_local") or profile.get("name") or "player"
    summary = profile.get("summary") or profile.get("background") or ""
    klass = profile.get("class") or profile.get("role") or ""
    bits = [str(name)]
    if klass:
        bits.append(str(klass))
    if summary:
        bits.append(str(summary))
    return " / ".join(bits)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
