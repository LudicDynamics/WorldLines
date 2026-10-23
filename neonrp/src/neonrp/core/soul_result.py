"""Structured soul turn result contract.

Soul-agent prose is valuable for RP voice, but the control plane needs a stable
shape for deciding whether a soul completed, degraded, or needs world-agent
attention. This module parses the final assistant text into that envelope and
degrades malformed output without crashing the turn.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

# Canonical impl lives in neonrp.core.json_repair (shared with the write
# boundary in skills.py); re-exported here for existing callers.
from neonrp.core.json_repair import _repair_broken_strings

SoulResultState = Literal["completed", "interrupted", "degraded"]
_VALID_STATES = {"completed", "interrupted", "degraded"}
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_VOICE_FIELD_RE = re.compile(
    r'"(?:speech|inner_voice|intended_action)"\s*:\s*"((?:[^"\\]|\\.)*)"'
)


def _salvage_voice(raw: str) -> str:
    """Pull a human line out of soul output WITHOUT ever leaking a JSON blob.

    Models (deepseek especially) sometimes return not-quite-valid JSON that
    fails strict parsing. The old preview fell back to dumping ``raw_text`` —
    so the player saw ``{"state":"completed","speech":"…"}`` in the UI
    (WOR-26). Instead: if it looks like JSON, lift the first voice field out;
    if nothing human is in there, return "" (caller shows a short error, not
    the blob). Plain prose (no JSON shape) is returned as-is — it's legit RP."""
    s = str(raw or "").strip()
    if not s:
        return ""
    looks_json = s[:1] in "{[" or '"speech"' in s or '"inner_voice"' in s
    if not looks_json:
        return s
    m = _VOICE_FIELD_RE.search(s)
    if m and m.group(1).strip():
        return m.group(1).replace('\\"', '"').replace("\\n", " ").strip()
    return ""


@dataclass(frozen=True)
class SoulTurnReport:
    """Parsed result returned by one active soul for a turn."""

    state: SoulResultState
    confidence: float = 0.0
    urgency: float = 0.0
    intended_action: str = ""
    speech: str = ""
    inner_voice: str = ""
    memory_delta: str = ""
    needs_world_decision: bool = False
    # The node id this soul MOVED TO this turn ("" = stayed). The engine
    # applies it to the soul's own run_state.json location after the turn —
    # this is what keeps locality routing (scene-understanding) alive: souls
    # move, the router's input state moves with them.
    moved_to: str = ""
    # The soul's own decision procedure (M22+): each turn it brainstorms ~4
    # candidate actions — one a high-variance wildcard (突发奇想 / leave /
    # break the pattern) — scores each by "how likely the real me does this
    # here" (fit, 0..1), and commits to the highest. `intended_action` IS the
    # chosen candidate; `candidates` carries all of them (with fit) for
    # observability. The wildcard wins only when it genuinely scores highest
    # (e.g. after waiting too long), so a soul breaks a rut in-character — no
    # engine override needed (the soul picked + elaborated coherently).
    candidates: tuple[dict[str, Any], ...] = ()
    raw_text: str = ""
    parse_error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_structured(self) -> bool:
        return not self.parse_error

    def digest_line(self, name: str, *, role: str = "npc") -> str:
        """Compact line for the world-agent's internal team report."""
        normalized_role = str(role or "npc").strip().lower()
        is_player = normalized_role == "player"
        pieces = [
            f"role={normalized_role}",
            f"state={self.state}",
            f"confidence={self.confidence:.2f}",
            f"urgency={self.urgency:.2f}",
        ]
        if is_player:
            pieces.append("human_player_sovereignty=true")
        if self.needs_world_decision:
            pieces.append("needs_world_decision=true")
        if self.intended_action:
            key = "avatar_action_suggestion" if is_player else "action"
            pieces.append(f"{key}={self.intended_action}")
        if self.speech:
            key = "avatar_speech_suggestion" if is_player else "speech"
            pieces.append(f"{key}={self.speech}")
        if self.inner_voice:
            pieces.append(f"inner_voice={self.inner_voice}")
        if self.moved_to:
            pieces.append(f"moved_to={self.moved_to}")
        if self.memory_delta:
            pieces.append(f"memory_delta={self.memory_delta}")
        if self.parse_error:
            pieces.append(f"parse_error={self.parse_error}")
        return f"- {name}: " + " | ".join(pieces)

    def preview(self, *, role: str = "npc") -> str:
        """Short human/TUI preview preserving voice when present.

        Never returns a raw JSON blob: the structured fields come first, then
        a JSON-safe salvage of raw_text (WOR-26), then the short parse error."""
        normalized_role = str(role or "npc").strip().lower()
        if normalized_role == "player":
            values = (self.inner_voice, self.memory_delta, self.speech)
        else:
            values = (self.speech, self.inner_voice, self.intended_action)
        for value in values:
            text = str(value or "").strip().replace("\n", " ")
            if text:
                return text
        salvaged = _salvage_voice(self.raw_text)
        if salvaged:
            return salvaged.replace("\n", " ")
        return self.parse_error


def parse_soul_turn_report(text: str, *, success: bool = True) -> SoulTurnReport:
    """Parse soul-agent output into :class:`SoulTurnReport`.

    Accepted shape is a JSON object, either raw or fenced. Malformed output is a
    degraded report; the original text is preserved as non-authoritative prose.
    """
    raw_text = str(text or "").strip()
    if not success:
        return SoulTurnReport(
            state="degraded",
            raw_text=raw_text,
            parse_error="soul turn failed",
        )

    obj, error = _parse_json_object(raw_text)
    if obj is None:
        return SoulTurnReport(
            state="degraded",
            raw_text=raw_text,
            parse_error=error or "missing JSON object",
        )

    state = str(obj.get("state") or "completed").strip().lower()
    if state not in _VALID_STATES:
        return SoulTurnReport(
            state="degraded",
            raw_text=raw_text,
            parse_error=f"invalid state: {state or '<empty>'}",
        )

    confidence = _coerce_unit_float(obj.get("confidence"))
    urgency = _coerce_unit_float(obj.get("urgency"))
    if confidence is None:
        return SoulTurnReport(
            state="degraded",
            raw_text=raw_text,
            parse_error="confidence must be a number from 0 to 1",
        )
    if urgency is None:
        return SoulTurnReport(
            state="degraded",
            raw_text=raw_text,
            parse_error="urgency must be a number from 0 to 1",
        )

    known = {
        "state",
        "confidence",
        "urgency",
        "intended_action",
        "speech",
        "inner_voice",
        "memory_delta",
        "needs_world_decision",
        "moved_to",
        "candidates",
    }
    extra = {str(k): v for k, v in obj.items() if k not in known}
    return SoulTurnReport(
        state=state,  # type: ignore[arg-type]
        confidence=confidence,
        urgency=urgency,
        intended_action=_coerce_text(obj.get("intended_action")),
        speech=_coerce_text(obj.get("speech")),
        inner_voice=_coerce_text(obj.get("inner_voice")),
        memory_delta=_coerce_text(obj.get("memory_delta")),
        needs_world_decision=bool(obj.get("needs_world_decision", False)),
        moved_to=_coerce_text(obj.get("moved_to")),
        candidates=_coerce_candidates(obj.get("candidates")),
        raw_text=raw_text,
        extra=extra,
    )


def _coerce_candidates(value: Any) -> tuple[dict[str, Any], ...]:
    """Normalise the soul's candidate list to ({action, fit}, …). Tolerant:
    a malformed entry is dropped, never raises."""
    if not isinstance(value, list):
        return ()
    out: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        action = _coerce_text(entry.get("action"))
        if not action:
            continue
        fit = _coerce_unit_float(entry.get("fit"))
        out.append({"action": action, "fit": fit if fit is not None else 0.0})
    return tuple(out)


def _parse_json_object(text: str) -> tuple[dict[str, Any] | None, str]:
    if not text:
        return None, "empty soul result"
    candidates = [text]
    fenced = _FENCED_JSON_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    sliced = _slice_first_json_object(text)
    if sliced:
        candidates.append(sliced)
    # Repair pass — tried AFTER the raw candidates, so well-formed output parses
    # untouched and the repair only kicks in when standard parsing failed. It
    # fixes the common deepseek malformations seen in chatty souls: a string
    # value broken with JS-style concatenation / bare prose between quoted
    # segments (`"a" + 旁白 + "b"`) and raw control chars inside strings.
    for _base in ([fenced.group(1)] if fenced else []) + (
        [sliced] if sliced else [text]
    ):
        _repaired = _repair_broken_strings(_base)
        if _repaired and _repaired not in candidates:
            candidates.append(_repaired)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value, ""
    return None, "malformed soul result JSON"


def _slice_first_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return ""
    return text[start:end + 1]


def _coerce_unit_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0 or parsed > 1:
        return None
    return parsed


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def clean_line(text: str) -> str:
    """What a character says, without the reply's machine blocks: a ``<lines>`` block's content when there is one, never
    a ``<fields>`` / ``<draft>`` block (10-15: a reply in the S-direct shape on the S-judge / S-free path, and a planning
    beat's line, showed its fields on screen)."""
    t = str(text or "")
    m = re.search(r"<lines\s*>(.*?)(?:</lines\s*>|$)", t, re.DOTALL | re.IGNORECASE)
    if m:
        t = m.group(1)
    t = re.sub(r"<(fields|draft)\s*>.*?(?:</\1\s*>|$)", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"</?(lines|fields|draft)\s*>", "", t, flags=re.IGNORECASE)
    return "\n".join(ln.strip() for ln in t.splitlines() if ln.strip())
