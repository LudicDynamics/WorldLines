"""One-shot layer call (10-18): a node of the orchestration graph with its own prompt
that the Resolve calls like a tool. The layer writes once with its own system prompt (``modes.layer_system``), its
reads and its state block; it stops at its own tool requests (``[dice …]``), the engine answers them, it goes on; then
it hands back what it wrote, the state changes it asked for (verified and applied with the rest of the beat) and its
cards. The world's mode never changes — the Planning and Resolve beats stay the only beats.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def run(root: Path, reg: Any, name: str, ask: str, *, seed: str = "", turn: int | None = None, max_stops: int = 3) -> dict[str, Any]:
    """``{"ok", "text", "ops", "panels", "answers", "ms"}`` — ``text`` is the layer's lines (its requests answered in
    place), ``ops`` the changes it wrote (hp …), ``panels`` its raw blocks (``<formation>``), ``answers`` the engine's
    replies to its requests."""
    from neonrp.core import modes, sdk, tool_watch
    from neonrp.core.handlers import HandlerError
    from neonrp.core.output_lang import pick_lang, prompt_lang
    from neonrp.core.turn_v3 import _adapter, _chat, _user_block, drop_restated

    lang = prompt_lang(root)
    spec = modes.spec_of(root, name) or {}
    system = modes.layer_system(root, reg, name, lang)
    pack_text = sdk.render_pack(sdk.pack(root, registry=reg))
    extra = "\n\n".join(x for x in (modes.reads_block(root, reg, spec), modes.state_block(root, reg, spec)) if x)
    tools = {k for k in (spec.get("ops") or []) if reg.actions.get(k) is not None and reg.actions[k].kind == "tool" and reg.actions[k].waits()}
    need = str(spec.get("require_tool") or "")
    hit_var = str(spec.get("hit_needs") or "")  # a passed check of the layer's tool must be followed by a change to a variable ending so (".hp")
    saved = set(sdk.PANEL_TAGS)
    sdk.PANEL_TAGS = set((spec.get("panels") or {}).keys())
    adapter = _adapter(root, None, "adv")
    prefix, answers, ops, panels, ms_total, asked_again, hit_asked = "", [], [], {}, 0.0, False, False
    nudge = ""
    text = ""
    try:
        stop = 0
        while True:
            user = _user_block(pack_text, ask, [], "", None, None, answers or None, lang=lang, prefix=prefix, extra=extra)
            if nudge:
                user += "\n\n" + nudge
                nudge = ""
            raw, ms, _u = _chat(adapter, system, user)
            ms_total += ms
            out = sdk.parse_solve_output(raw)
            lines = out.narration
            if prefix:
                cont = drop_restated(prefix, lines)
                lines = prefix + ("\n" + cont if cont else "")
            panels.update(out.panels)
            req = [o for o in out.ops if o.get("op") in tools]
            ops += [o for o in out.ops if o.get("op") not in tools and o.get("op") not in ("need", "options")]
            if need and not req and not answers and not asked_again:  # the layer's own rule: no result without its tool (a fight with no die)
                asked_again, ops = True, []
                nudge = str(pick_lang(spec.get("require_why"), lang) or "")
                continue
            hits = [t for t in answers if t.get("passed") and t.get("vs")]
            if hit_var and hits and not req and not hit_asked and not any(str(o.get("var") or "").endswith(hit_var) for o in ops):
                hit_asked = True  # fulllog-1001 (d): a passed hit with no hp change — once more from the same stop
                from neonrp.core.turn_v3 import _T

                nudge = _T(lang)["hit_no_hp"].replace("{n}", str(len(hits)))
                prefix = lines
                continue
            if not req or stop >= max_stops:
                text = lines
                break
            vr = sdk.verify(root, req, reg)  # the same field checks as the narrator's requests ([dice 1d20+2 vs 11] → dice / vs)
            for rf in vr.refused:
                answers.append({"request": str(rf.op.get("op") if isinstance(rf.op, dict) else "?"), "ok": False, "why": rf.why})
            for k, o in enumerate(o for o in vr.accepted if o.get("op") in tools):
                o = {kk: vv for kk, vv in o.items() if not str(kk).startswith("_")}
                a = reg.actions[o["op"]]
                try:
                    r = tool_watch.call(root, reg, o["op"], a.handler, {**o, "source": name}, None, seed=f"{seed}:{name}:{stop}:{k}",
                                        source=name, turn=turn)
                except HandlerError as exc:
                    r = {"ok": False, "why": str(exc)[:200]}
                req_txt = " ".join([o["op"]] + [str(o.get(f)) for f in a.fields if o.get(f) is not None])
                answers.append({"request": str((r or {}).get("request") or req_txt) if isinstance(r, dict) else req_txt,
                                **(r if isinstance(r, dict) else {"text": str(r)})})
            prefix = out.prefix or lines
            stop += 1
    finally:
        sdk.PANEL_TAGS = saved
    return {"ok": True, "text": text, "ops": ops, "panels": panels, "answers": answers, "ms": round(ms_total, 1)}
