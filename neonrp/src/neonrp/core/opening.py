"""A world's opening (generic — any orchestration): the cue that starts a world nobody has played yet, in the run's
language, how a start cue is recognised (the launcher's kickoff too), and the world's own authored opening scene.
Lifted out of the planning beat's module (10-10 R1): opening a world is not a planning matter."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

START_RE = re.compile(r"开始游戏|开始冒险|start the game|start the adventure|begin|ゲーム(?:を)?開始|ゲームを始め|冒険を始め"
                      r"|게임\s*(?:을\s*)?시작|모험\s*(?:을\s*)?시작|^\s*시작\s*$", re.IGNORECASE)
# The cue sent for a world nobody has played yet, in the run's language (commands/tui.py).
def _by_lang(key: str) -> dict[str, str]:
    from neonrp.prompts import by_lang

    return by_lang("opening", key)


START_CUE = _by_lang("start_cue")  # prompts/opening.<lang>.json (10-15)


def start_cue(root: Path) -> str:
    from neonrp.core.output_lang import prompt_lang

    return START_CUE.get(prompt_lang(root), START_CUE["zh"])


# the web / launcher kickoff (tui/i18n handoff.start_game) is the cue on its own FIRST line, then a language note —
# 「开始游戏。\n\n语言:简体中文……」「Start the game.\n\nLanguage: …」「ゲームを始めてください。…」「게임을 시작합니다.…」
START_LINE_RE = re.compile(r"(开始游戏|开始冒险|start the game|begin|ゲームを始めてください|ゲームを始める|게임을 시작합니다|게임 시작)", re.IGNORECASE)


def is_start_cue(root: Path, text: str) -> bool:
    """「开始游戏」 or the launcher's handoff (the cue ends it, or is its whole first line) — or a tag the world's game-start lists."""
    t = (text or "").strip()
    if START_RE.search(t[-80:]):
        return True
    if START_LINE_RE.fullmatch(t.split("\n", 1)[0].strip().rstrip("。.!！ ")):
        return True
    gs = _game_start(root)
    return any(isinstance(x, str) and len(x) >= 2 and t == x for x in gs.get("tags") or [])


def _game_start(root: Path) -> dict[str, Any]:
    from neonrp.core.paths import get_data_dir_name

    for p in (root / get_data_dir_name(root) / "meta" / "game-start.json", root / "game" / "meta" / "game-start.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            continue
    return {}


def authored_opening(root: Path) -> str:
    """The world's own opening scene and its first choices (game-start.json ``startup.opening_scene`` / ``opening_choices``),
    in the run's language (开场旁白四语). Either may be plain (one language) or ``{zh,en,ja,ko}``; choices may
    also be ``{lang: [...]}`` or a list of ``{lang: text}``. A missing language falls back ko → en → zh."""
    from neonrp.core.output_lang import pick_opening, prompt_lang

    scene, choices = pick_opening(_game_start(root).get("startup"), prompt_lang(root))
    if not scene:
        return ""
    ch = choices[:4]
    return scene + ("\n\n" + " / ".join(f"{'①②③④'[i]} {c}" for i, c in enumerate(ch)) if ch else "")


# ── the opening as a node kind (10-11): the world's own first beat, in any orchestration ──────────────────────────────
class _OpeningNode:
    """A world nobody has played yet, the start cue, an authored opening scene: that scene is the first beat — no model,
    no talk (niko 10-03: 「主持的第一句应该是主持的开场」). It takes that beat before any other node kind, whatever the
    orchestration (10-17: a node kind opening its own way left out the companions' party.join and the mentions)."""

    kind = "opening"

    def active(self, root: Path, user_text: str) -> bool:
        return is_start_cue(root, user_text) and not _played(root) and bool(authored_opening(root))

    def take_turn(self, session: Any, *, user_text: str, trace: Any, run_id: Any, on_chunk: Any) -> Any:
        from neonrp.core.conversation import ConversationTurnResult
        from neonrp.core.llm import Message
        from neonrp.core.orchestration_trace import append_turn_trace
        from neonrp.core.session import append_message


        op = authored_opening(session.root)
        if on_chunk is not None:
            on_chunk(op)
        trace.apply = {"narration_plain": op, "applied": [], "refused": [], "options": [],
                       "beat": {"kind": "opening", "script": [{"who": _by_lang("host").get(_lang(session.root), "Host"), "role": "host", "text": op}], "mic": [], "board": {},
                                "checks": [], "next": "wait", "reads": [], "rolled": [], "calls": []}}
        try:  # the entities the opening names (core/mentions.py, 10-14)
            from neonrp.core import mentions as _mn
            from neonrp.core.registry import load_registry

            reg = load_registry(session.root)
            trace.apply["mentions"] = _mn.find(reg, op)
            from neonrp.core import holdings as _hd

            if _hd.members(session.root) is None:  # the companions standing with the player are with them from the start
                trace.apply["joined"] = _hd.party(session.root, reg, _hd.snapshot(reg))[0]
        except Exception:  # noqa: BLE001
            pass
        msg = Message(role="assistant", content=op)
        session.messages.append(msg)
        append_message(session.root, session.branch, msg, run_id=run_id)
        session._persisted_up_to = len(session.messages)
        append_turn_trace(session.root, session.branch, trace)
        session._emit_beats(trace)
        return ConversationTurnResult(success=True, run_id=run_id, assistant_message=op, route_decision="opening",
                                      active_agent=session.agent_id)


def _played(root: Path) -> bool:
    """Has this run had a beat already (any turn trace)?"""
    try:
        from neonrp.core.orchestration_trace import read_turn_traces

        return bool(read_turn_traces(root, "main", last=1))
    except Exception:  # noqa: BLE001
        return False


def _lang(root: Path) -> str:
    from neonrp.core.output_lang import prompt_lang

    return prompt_lang(root)
