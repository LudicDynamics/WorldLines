"""R4 (the handover 10-06): dry-run one beat — the same input through a throwaway copy of the run, the trace back in the
shape a real beat writes; the run itself, its commits and its clock are untouched.

    POST /api/v1/play/engine/dry-run {"input": "…", "beat": "plan" | "resolve" | "auto", "overrides": {"turn": {…}}}

``beat`` forces which loop answers: ``plan`` (the planning loop on), ``resolve`` (the planning loop off — the line goes
straight to the Resolve), ``auto`` (as the run is configured). ``overrides`` is merged into the copy's engine.json (two
orchestrations / two models side by side). The model is the run's own (a dry run of a real beat costs a real call).
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

_SKIP = shutil.ignore_patterns("assets", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.mp4", "*.mp3", "logs", "node_modules", "__pycache__")


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def run(root: Path, text: str, *, beat: str = "auto", overrides: dict[str, Any] | None = None,
        provider: str | None = None, agent_id: str = "world-agent") -> dict[str, Any]:
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces
    from neonrp.core.paths import get_data_dir_name

    root = Path(root)
    tmp = Path(tempfile.mkdtemp(prefix="neonrp-dry-run-"))
    copy = tmp / root.name
    try:
        shutil.copytree(root, copy, ignore=_SKIP, symlinks=True)
        ej = copy / get_data_dir_name(copy) / "meta" / "engine.json"
        cfg = json.loads(ej.read_text(encoding="utf-8")) if ej.exists() else {}
        cfg = _merge(cfg, overrides or {})
        if beat in ("plan", "resolve"):
            cfg = _merge(cfg, {"turn": {"plan_loop": "on" if beat == "plan" else "off"}})
        ej.parent.mkdir(parents=True, exist_ok=True)
        ej.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            from neonrp.core.llm_openai import usage_snapshot

            u0 = usage_snapshot()
        except Exception:  # noqa: BLE001
            u0 = {}
        sess = ConversationSession(copy, agent_id, mode="play", provider=provider)
        k0 = len(read_turn_traces(copy, sess.branch))
        res = sess.send(str(text or ""))
        trs = read_turn_traces(copy, sess.branch)[k0:]
        try:
            from neonrp.core.llm_openai import usage_snapshot

            u1 = usage_snapshot()
            usage = {k: int(u1.get(k, 0)) - int(u0.get(k, 0)) for k in u1}
        except Exception:  # noqa: BLE001
            usage = {}
        return {"input": text, "beat": beat, "overrides": overrides or {}, "ok": bool(getattr(res, "success", False)),
                "error": getattr(res, "error", None), "reply": getattr(res, "assistant_message", ""), "traces": trs, "usage": usage}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
