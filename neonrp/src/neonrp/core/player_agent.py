"""M20 player-agent — the per-player wrapper archetype.

A player-agent is the human's representative / view layer. It has **no
persona** (the human is the intelligence) and is **never** a soul. One per
``pid``; it owns that player's private state folder (``game/players/<pid>/``,
or the ``game/player/`` N=1 alias). It is a *distinct turn step even at N=1*,
never inlined into the world-agent.

Two entry points mirror M20 §3 turn protocol steps 1 and 6:

- :meth:`PlayerAgent.intake` — raw human input -> ``PlayerTurnIntent``
  (deterministic; wraps the existing ``player_controller`` preflight). Raw
  input dies here; it never reaches souls.
- :meth:`PlayerAgent.render` — the world-agent's perspective-free world-truth
  output -> *this* player's view, plus that player's private-state writes
  (journal). v1 is a deterministic pass-through with the per-player
  perspective-render seam marked; the world-agent still authors prose for
  now, so N=1 behaviour is byte-identical (no regression). C3's generative
  per-player narration plugs into :meth:`render` later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from neonrp.core.player_controller import PlayerTurnIntent, build_player_turn_intent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayerView:
    """One player's per-turn output (M20 §3 step 6)."""

    pid: str
    narration: str
    # SEAM: when C3 lands, this carries a per-player perspective/redaction of
    # the world-truth delta instead of the verbatim world-agent prose.
    perspective_rendered: bool = False


@dataclass(frozen=True)
class PlayerOutputDirective:
    """M18 §2.2 — one render instruction for a frontend, addressed to a single
    player. A tagged union keyed by ``kind``; a frontend subscribes to
    ``player/<pid>/output`` and renders the stream. v1 emits ``text``
    directives; ``voice`` / ``bgm`` / ``image`` kinds plug in behind the same
    contract. The directive is a transport payload — JSON-only, no objects."""

    kind: str  # "text" | "ask_user" | (roadmap) "voice" | "bgm" | "image"
    text: str = ""
    pace: str = "typewriter"  # for kind="text": "typewriter" | "instant"
    options: tuple[str, ...] = ()  # for kind="ask_user"

    def to_dict(self) -> dict:
        d: dict = {"kind": self.kind, "text": self.text}
        if self.kind == "text":
            d["pace"] = self.pace
        if self.options:
            d["options"] = list(self.options)
        return d


@dataclass(frozen=True)
class PlayerAgent:
    """Per-player wrapper. No persona; owns ``state_path`` only."""

    root: Path
    pid: str
    state_path: str  # "game/player" (N=1 alias) or "game/players/<pid>"

    # ---- step 1: intake -------------------------------------------------
    def intake(self, raw_input: str) -> PlayerTurnIntent:
        """Raw human input -> deterministic ``PlayerTurnIntent``.

        Thin, on purpose: the control-plane classification already lives in
        ``player_controller``. Routing through the player-agent makes the
        archetype explicit and gives one observable owner of the boundary.
        """
        intent = build_player_turn_intent(self.root, raw_input)
        logger.info(
            "player-agent[%s] intake: kind=%s authorized=%s",
            self.pid,
            intent.kind,
            intent.avatar_action_authorized,
        )
        return intent

    # ---- step 6: render -------------------------------------------------
    def render(self, world_output: str) -> PlayerView:
        """World-truth output -> this player's view + private-state write.

        v1: pass-through narration (the world-agent still authors prose, so
        N=1 stays byte-identical) + deterministic private journal append +
        an explicit, logged step so the player-agent is observably distinct
        even at N=1. The per-player perspective LLM render is the documented
        next slice (C3) and plugs in right here.
        """
        self._append_journal(world_output)
        logger.info(
            "player-agent[%s] render: %d chars, perspective=passthrough(v1)",
            self.pid,
            len(world_output or ""),
        )
        return PlayerView(pid=self.pid, narration=world_output, perspective_rendered=False)

    def to_directives(self, world_output: str) -> list[PlayerOutputDirective]:
        """World-truth output -> this player's ``PlayerOutputDirective`` stream
        (M18 §2.2 / M20 4.1). Deterministic perspective assembly:

        - a typewriter-paced text directive (the narration, verbatim);
        - a ``choices`` directive when the narration ends with an option list
          (the 「你可以：…」 block) — frontends render clickable choices
          instead of making the human re-type them.

        The per-player perspective/translation LLM render plugs in here (C3);
        voice/bgm/image directives are added as new kinds."""
        text = (world_output or "").strip()
        if not text:
            return []
        directives = [PlayerOutputDirective(kind="text", text=text, pace="typewriter")]
        options = _extract_choices(text)
        if options:
            directives.append(
                PlayerOutputDirective(kind="choices", options=tuple(options))
            )
        return directives

    # ---- private state ownership ---------------------------------------
    def _journal_path(self) -> Path:
        return self.root / self.state_path / "journal.md"

    def _append_journal(self, world_output: str) -> None:
        """Best-effort terse journal append. Never raises into the turn —
        a private-state write failure must not lose the player's narration.
        """
        text = (world_output or "").strip()
        if not text:
            return
        snippet = text if len(text) <= 280 else text[:277] + "…"
        try:
            jp = self._journal_path()
            jp.parent.mkdir(parents=True, exist_ok=True)
            with jp.open("a", encoding="utf-8") as fh:
                fh.write(f"\n- {snippet}\n")
        except OSError as exc:
            logger.debug("player-agent[%s] journal append skipped: %s", self.pid, exc)


def _extract_choices(text: str) -> list[str]:
    """Pull the trailing option list out of a narration (deterministic).

    Looks for the LAST 「你可以」 marker line, then collects subsequent
    bullet lines (``- …`` / ``→ …``), stripping markdown emphasis. Best
    effort: no marker / no bullets ⇒ []."""
    lines = text.splitlines()
    marker = -1
    for i, line in enumerate(lines):
        if "你可以" in line or "You can:" in line:
            marker = i
    if marker < 0:
        return []
    options: list[str] = []
    for line in lines[marker + 1 :]:
        s = line.strip()
        if not s:
            continue
        if s.startswith(("-", "→", "*")):
            cleaned = s.lstrip("-→* ").replace("**", "").strip()
            # drop a trailing parenthetical explainer (keep the action)
            for open_p, close_p in (("（", "）"), ("(", ")")):
                if open_p in cleaned and cleaned.endswith(close_p):
                    cleaned = cleaned[: cleaned.index(open_p)].strip()
            if cleaned:
                options.append(cleaned[:60])
        elif options:
            break
    return options[:6]


def player_agents_for(root: Path, playthrough: object | None) -> list[PlayerAgent]:
    """Build one :class:`PlayerAgent` per ``playthrough.players`` entry.

    No ``players[]`` (legacy / pre-M20) ⇒ a single N=1 default over the
    ``game/player/`` alias, so single-player still gets a distinct
    player-agent step (M20: never inlined into the world-agent).
    """
    players = list(getattr(playthrough, "players", ()) or ())
    if not players:
        return [PlayerAgent(root=root, pid="player", state_path="game/player")]
    return [
        PlayerAgent(
            root=root,
            pid=str(p.pid),
            state_path=str(getattr(p, "state_path", "") or "game/player"),
        )
        for p in players
    ]
