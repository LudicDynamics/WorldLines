"""M18 §5 — soul-as-external-backend.

A soul-agent is reached *only* through a backend chosen per soul in
``soul.json`` ``backend``. The boundary is a message contract — a perception
goes in, a soul turn result comes out — so the world-agent physically cannot
reach into a soul's reasoning or ghost-write its lines; ventriloquism is
structurally impossible, not merely discouraged by prompt (M18_DESIGN §5).

v1 backends:

- ``internal-llm`` (default): the runtime spawns a soul-agent via
  ``run_conversation_turn`` — **byte-identical** to the pre-Phase-5 path
  (this backend is a pure passthrough; absence of a ``backend`` field selects
  it, so no world content changes).
- ``stub``: a canned response, **no LLM** — for tests and for deterministic
  off-stage / functional souls. This is the OASIS borrow (rule/LLM hybrid):
  run a soul with zero model cost, reserving the LLM for souls that need it.

``sillytavern`` / ``http`` / ``human`` are future backends behind the same
contract; the seam here is where they plug in.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # avoid an import cycle — conversation imports this module
    from neonrp.core.conversation import ConversationTurnResult

logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "internal-llm"


class SoulBackend(Protocol):
    """What sits behind a soul's request topic. Perception (as ``messages``)
    in, a ``ConversationTurnResult`` out — the caller parses the soul's
    ``SoulTurnReport`` from it exactly as before, so swapping the backend never
    changes the turn's downstream handling."""

    name: str

    def respond(
        self,
        *,
        root: Path,
        agent_id: str,
        messages: list[Any],
        mode: str,
        provider: str | None,
        max_turns: int,
        run_id: str,
    ) -> ConversationTurnResult: ...


class InternalLLMBackend:
    """Default backend: spawn the soul-agent. A pure passthrough to
    ``run_conversation_turn`` — behaviour is identical to the pre-Phase-5 call
    site by construction."""

    name = "internal-llm"

    def respond(
        self,
        *,
        root: Path,
        agent_id: str,
        messages: list[Any],
        mode: str,
        provider: str | None,
        max_turns: int,
        run_id: str,
    ) -> ConversationTurnResult:
        # Lazy import: conversation imports this module at top level.
        from neonrp.core.conversation import run_conversation_turn

        return run_conversation_turn(
            root=root,
            agent_id=agent_id,
            messages=messages,
            mode=mode,
            provider=provider,
            max_turns=max_turns,
            run_id=run_id,
        )


class StubBackend:
    """No-LLM backend: returns a canned soul turn report. The report defaults
    to a quiet ``completed`` turn (no speech/action) so an off-stage or test
    soul is a clean passthrough; pass ``report`` (a dict or JSON string) to
    drive a specific response."""

    name = "stub"

    # Includes confidence/urgency because parse_soul_turn_report requires them
    # to be numbers in [0,1] — a report missing them parses as degraded.
    _DEFAULT_REPORT = {
        "state": "completed",
        "confidence": 0.0,
        "urgency": 0.0,
        "speech": "",
        "inner_voice": "",
        "intended_action": "",
    }

    def __init__(self, report: dict[str, Any] | str | None = None) -> None:
        self._report = report

    def respond(
        self,
        *,
        root: Path,
        agent_id: str,
        messages: list[Any],
        mode: str,
        provider: str | None,
        max_turns: int,
        run_id: str,
    ) -> ConversationTurnResult:
        from neonrp.core.conversation import ConversationTurnResult

        if isinstance(self._report, str):
            message = self._report  # caller takes full control of the raw text
        else:
            # Merge over defaults so a partial dict (e.g. just {"speech": ...})
            # still parses as a valid, complete SoulTurnReport.
            payload = {**self._DEFAULT_REPORT, **(self._report or {})}
            message = json.dumps(payload, ensure_ascii=False)
        return ConversationTurnResult(
            success=True, run_id=run_id, assistant_message=message
        )


class HttpBackend:
    """M18 §5 external backend: any REST soul service answers the request.

    ``soul.json``: ``{"backend": "http", "backend_url": "https://…",
    "backend_timeout_s": 60}``. The wire contract mirrors the message
    boundary: POST ``{sid?, agent_id, messages: [{role, content}…]}`` →
    ``{"assistant_message": "<SoulTurnReport JSON>"}``. Failure/timeout
    raises — upstream that is the soul's degraded path, never a hang
    (per-soul timeout still applies on top).
    """

    name = "http"

    def __init__(self, url: str, timeout_s: float = 60.0) -> None:
        self._url = url
        self._timeout_s = timeout_s

    def respond(
        self,
        *,
        root: Path,
        agent_id: str,
        messages: list[Any],
        mode: str,
        provider: str | None,
        max_turns: int,
        run_id: str,
    ) -> ConversationTurnResult:
        import urllib.request

        from neonrp.core.conversation import ConversationTurnResult

        body = json.dumps(
            {
                "agent_id": agent_id,
                "run_id": run_id,
                "messages": [
                    {"role": getattr(m, "role", "user"), "content": getattr(m, "content", "") or ""}
                    for m in (messages or [])
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            self._url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        message = str(data.get("assistant_message") or "")
        if not message:
            raise RuntimeError(f"http soul backend returned no assistant_message: {self._url}")
        return ConversationTurnResult(
            success=True, run_id=run_id, assistant_message=message
        )


_BACKENDS: dict[str, type] = {
    "internal-llm": InternalLLMBackend,
    "stub": StubBackend,
    "http": HttpBackend,
}


def resolve_soul_backend(root: Path, soul: Any) -> SoulBackend:
    """Pick a soul's backend from ``soul.json`` ``backend`` (default
    ``internal-llm``). An unknown backend name — or an http backend with no
    url — falls back to ``internal-llm`` with a warning: a content typo never
    breaks a turn."""
    cfg = _read_soul_config(root, soul)
    name = str(cfg.get("backend") or "").strip() or DEFAULT_BACKEND
    if name == "http":
        url = str(cfg.get("backend_url") or "").strip()
        if not url:
            logger.warning(
                "soul %s: backend=http without backend_url; falling back to %s",
                getattr(soul, "instance_id", "?"),
                DEFAULT_BACKEND,
            )
            return InternalLLMBackend()
        try:
            timeout_s = float(cfg.get("backend_timeout_s") or 60.0)
        except (TypeError, ValueError):
            timeout_s = 60.0
        return HttpBackend(url, timeout_s=timeout_s)
    cls = _BACKENDS.get(name)
    if cls is None:
        logger.warning(
            "soul %s: unknown backend %r; falling back to %s",
            getattr(soul, "instance_id", "?"),
            name,
            DEFAULT_BACKEND,
        )
        cls = InternalLLMBackend
    return cls()


def _read_soul_config(root: Path, soul: Any) -> dict[str, Any]:
    sid = getattr(soul, "sid", "")
    iid = getattr(soul, "instance_id", "")
    path = root / "souls" / f"{sid}-{iid}" / "soul.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
