"""Engine v3 — ③ SOLVE → ④ VERIFY → (≤1 loop) → ⑤ APPLY for one turn.

Spliced into ``ConversationSession._run_multi_agent_turn`` when
``engine_config.v3_enabled(root)`` (``NEONRP_TURN_V3=1`` or
``game/meta/engine.json`` ``turn.mode = "v3"``). ① PLAN and ② PARALLEL are the
existing S1/S2 block (souls already ran); this module replaces the world-agent
tool loop with **one structured LLM call, no read tools**, then verifies the
proposed ops against the registry and applies them through the SDK.

The loop (TURN-V3 §九): refused-but-fixable ops or a ``need <soul>`` request
re-invoke the proposer at most ``turn.verify.gate.max_loops`` times (default
1) with the structured refusal; a second failure is dropped, never looped.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from neonrp.core import beat_budget as _beat
from neonrp.core import engine_config
from neonrp.core import mechanics as _mech
from neonrp.core import orchestration as _orch
from neonrp.core.config import load_config, resolve_provider
from neonrp.core import tool_watch as _tool_watch
from neonrp.core.llm import Message, get_adapter_from_config
from neonrp.core.registry import Registry, load_registry
from neonrp.core.sdk import ApplyResult, Pack, Refusal, SolveOutput, apply, pack, parse_solve_output, render_pack, verify
from neonrp.core.sdk import identity_gate as _identity_gate
from neonrp import prompts as _prompts

logger = logging.getLogger(__name__)

# Test seam: set to a callable(root, provider) -> adapter to bypass config.
ADAPTER_FACTORY: Callable[[Path, str | None], Any] | None = None


def adapter_kwargs(structured: str) -> dict[str, Any]:
    """Provider kwargs for the solve call. ``json_object`` asks OpenAI-family
    providers (deepseek included) for constrained JSON output — the fix for the
    2/8 truncated objects seen in E1; ``json_schema`` additionally pins the
    shape where the provider supports it."""
    if structured == "json_object":
        return {"extra_kwargs": {"response_format": {"type": "json_object"}}}
    if structured == "json_schema":
        return {"extra_kwargs": {"response_format": {"type": "json_schema", "json_schema": {
            "name": "turn", "strict": True, "schema": {
                "type": "object", "additionalProperties": False, "required": ["narration", "ops"],
                "properties": {"narration": {"type": "string"},
                               "ops": {"type": "array", "items": {"type": "object", "required": ["op"],
                                                                  "properties": {"op": {"type": "string"}}, "additionalProperties": True}}}}}}}}
    return {}


def _adapter(root: Path, provider: str | None, structured: str = "together") -> Any:
    if ADAPTER_FACTORY is not None:
        return ADAPTER_FACTORY(root, provider)
    config = load_config(root)  # default policy: user config in play, never under pytest (10-02: stub e2e was calling the real provider)
    pc = resolve_provider(config, None, provider)
    kw = adapter_kwargs(structured)
    try:
        return get_adapter_from_config(pc, **kw)
    except TypeError:  # a provider whose adapter has no extra_kwargs seam
        return get_adapter_from_config(pc)


# ── contract ─────────────────────────────────────────────────────────────────


def _user_block(pack_text: str, user_text: str, soul_reports: list[dict[str, Any]], plan_facts: str,
                refusals: list[dict[str, Any]] | None, prev: SolveOutput | None, tool_returns: list[dict[str, Any]] | None = None,
                lang: str = "zh", keyword_entries: list[str] | None = None, prefix: str = "", mentions: list[str] | None = None,
                extra: str = "") -> str:
    from neonrp.core.adv import HEAD, render_prev

    H = HEAD.get(lang) or HEAD["zh"]
    parts = [pack_text]
    if extra:  # a mode layer's own reads + state block (v2 sub-agent's READ contract, packed by the engine)
        parts.append(extra)
    if prefix:  # a request stopped the stream: what came before is final, the model only appends
        parts.append(H["prefix"] + "\n<lines>\n" + prefix + "\n</lines>")
    if tool_returns:
        parts.append(H["tools"] + "\n" + "\n".join(f"<{t.get('request')}>{t.get('text') or t.get('why') or t}</{str(t.get('request') or '').split(' ')[0]}>" for t in tool_returns))
    if soul_reports:
        lines = []
        for r in soul_reports:
            j = r.get("judgment") or {}
            fol = float(j.get("follow") or 0.0) >= 0.6 and float(j.get("stay") or 0.0) < 0.5  # the companions rule's thresholds
            attrs = " ".join(x for x in (f"attitude={j['attitude']}" if j.get("attitude") else "", f"register={j['register']}" if j.get("register") else "",
                                         f"to={r['proposed_move']}" if r.get("proposed_move") else "", "follow=yes" if fol else "") if x)
            lines.append(f"<say {r.get('name')}{(' ' + attrs) if attrs else ''}>{str(r.get('text') or '')[:600]}</say>")
        parts.append(H["reports"] + "\n" + "\n".join(lines))
    if plan_facts:
        parts.append(plan_facts)
    if mentions:  # E5 C4c: the player named someone who is elsewhere — say where, so the prose can lead there instead of forgetting them
        parts.append(H.get("mentions", "# 被点名的人") + "\n" + "\n".join(mentions))
    if keyword_entries:  # 条目 matched by keyword: injected next to the player's line (Yumina: 注入到相关消息附近)
        parts.append(H.get("entries", "# 相关条目") + "\n" + "\n\n".join(keyword_entries))
    parts.append(f"{H['player']}\n{user_text}")
    if prefix:
        parts.append(H["cont"])
    if prev is not None and refusals:
        ref_lines = []
        for r in refusals:
            o = r.get("op") if isinstance(r.get("op"), dict) else {}
            head = str(o.get("op") or r.get("field") or "op")
            allowed = r.get("allowed") or []
            T = _T(lang)
            ref_lines.append(f"<refused {head} {r.get('field') or ''}>{r.get('why')}" + (T["allowed"].replace("{list}", T["list_sep"].join(str(a) for a in allowed[:8])) if allowed else "") + "</refused>")
        parts.append(H["refused"] + "\n" + "\n".join(ref_lines) + "\n\n" + H["prev"] + "\n" + render_prev(prev, lang))
    return "\n\n".join(parts)


H_GATE = _prompts.by_lang("turn_v3", "H_GATE")
_HISTORY_TURNS: list[Message] = []  # set per solve_turn: the last N (player line, narrator output) pairs as chat turns


# ── annotated output: the prose plus every request, engine answer and state change, in place ──────────
# Model-written parts in square brackets ([referee …] · [~player.gold +18]); the engine's answers in angle brackets
# (<referee>…</referee>) so the model, reading it back as history, never learns to write a ruling itself.
# The player's text is sdk.strip_marks(annotated) == narration; sdk.mark_events(annotated) feeds SDK / Godot.

def _mark_request(o: dict[str, Any], t: dict[str, Any]) -> str:
    req = str(t.get("request") or o.get("op"))
    reason = str(o.get("reason") or "").strip()
    head = req.split(" ")[0]
    return f"[{req}]{reason}[/{head}]" if reason else f"[{req}]"


def _mark_answer(t: dict[str, Any], *, by_engine: bool = False) -> str:
    req = str(t.get("request") or "")
    head = req.split(" ")[0] or "tool"
    body = " ".join(str(t.get("text") or t.get("why") or "").split())
    return (f"[{req}]" if by_engine else "") + f"<{head}>{body}</{head}>"


def _op_mark(o: dict[str, Any]) -> str:
    op = str(o.get("op") or "")
    if op in ("add", "set") and o.get("var"):
        v = o.get("delta") if op == "add" else o.get("value")
        try:
            v = f"{int(v):+d}" if op == "add" else v
        except (TypeError, ValueError):
            pass
        return f"[~{o['var']} {v}]"
    if op == "move_to":
        return f"[~move {o.get('who')} {o.get('to')}]"
    if op == "flag":
        return f"[~flag {o.get('key')}]"
    if op == "define":  # define class <name> <title> prop=type … mutable=… / define var <name> <type> <value>
        if o.get("kind") == "var":
            return f"[~define var {o.get('name')} {o.get('type')} {o.get('initial')}]"
        props = " ".join(f"{k}={(v.get('type') if v.get('type') != 'enum' else '|'.join(map(str, v.get('values') or [])))}" for k, v in dict(o.get("props") or {}).items())
        mut = f" mutable={','.join(o.get('mutable') or [])}" if o.get("mutable") else ""
        return f"[~define class {o.get('name')} {o.get('title') or ''} {props}{mut}]".replace("  ", " ")
    if op in ("write", "edit", "rm", "mkdir", "rmdir"):  # file ops: the path (a file's body is content, not a mark)
        extra = _T()["chars"].replace("{n}", str(len(str(o.get('body') or '')))) if op == "write" else (" " + " ".join(f"{k}={v}" for k, v in dict(o.get("set") or {}).items()) if op == "edit" else "")
        return f"[~{op} {o.get('path')}{extra}]"
    if op in ("new", "patch"):  # the open-schema line grammar back: new <class> <name> k=v … / patch <who> k=v …
        props = {k: v for k, v in dict(o.get("props") or {}).items() if k != "name" and v not in (None, "")}
        kv = " ".join(f"{k}={v}" for k, v in props.items())
        who = str(o.get("who") or "")
        who = who.split(":", 2)[-1] if who.startswith("~pending:") else who  # created earlier this turn: show the name
        head = f"new {o.get('class')} {o.get('name')}" if op == "new" else f"patch {who}"
        return f"[~{head} {kv}]".replace(" ]", "]")
    args = " ".join(str(v) for k, v in o.items() if k != "op" and not str(k).startswith("_") and v not in (None, "", [], {}) and k != "await")
    return f"[~{op} {args}]".replace(" ]", "]")


def annotate(narration: str, marks_at: list[dict[str, Any]], accepted: list[dict[str, Any]]) -> str:
    """Insert each recorded mark after the prose line it followed (gate marks first; unknown anchor → end), then the
    turn's accepted state changes at the end (v1: ops sit in their own block, the model rarely places them inline)."""
    lines = (narration or "").splitlines()
    head: list[str] = []
    after: dict[int, list[str]] = {}
    tail: list[str] = []
    for m in marks_at:
        items = [x for x in m.get("items") or [] if x]
        if not items:
            continue
        if m.get("after") is None:
            head += items
            continue
        idx = max((i for i, ln in enumerate(lines) if ln == m["after"]), default=None)
        if idx is None:
            tail += items
        else:
            after.setdefault(idx, []).extend(items)
    out = list(head)
    for i, ln in enumerate(lines):
        out.append(ln)
        out += after.get(i, [])
    out += tail
    ops = " ".join(_op_mark(o) for o in accepted or [])
    if ops:
        out.append(ops)
    return "\n".join(out)


def history_messages(history: Any) -> list[Message]:
    """(user, assistant) pairs → alternating chat turns. The narrator's earlier output is shown in its own shape
    (<lines>…</lines>) so the model keeps writing the same way. Plain strings (old callers) become assistant turns."""
    out: list[Message] = []
    for h in history or []:
        if isinstance(h, dict):
            if h.get("user"):
                out.append(Message(role="user", content=str(h["user"])))
            if h.get("assistant"):
                a = str(h["assistant"])
                out.append(Message(role="assistant", content=a if a.lstrip().startswith("<") or a.lstrip().startswith("{") else f"<lines>\n{a}\n</lines>"))
        elif isinstance(h, str) and h:
            out.append(Message(role="assistant", content=f"<lines>\n{h}\n</lines>"))
    return out


def _mentions(reg: Registry, user_text: str) -> list[str]:
    """Souls / NPCs the player named in this line who are NOT where the player is: name + where they are."""
    here = reg.player_location
    out: list[str] = []
    for e in list(reg.of_class("soul")) + list(reg.of_class("npc")):
        names = {e.name, *[a for a in e.aliases if isinstance(a, str) and len(a) >= 2]}
        if not any(n and n in user_text for n in names):
            continue
        if e.parent and here and e.parent == here:
            continue
        where = e.parent or "?"
        w = reg.entries.get(where)
        chain = " · ".join(x.name for x in reversed(reg.chain(where))) if w is not None else where
        T = _T()
        if w is not None and w.cls in ("town", "region"):  # the world only knows the town: finding them is a step, not a given
            out.append(T["mention_town"].replace("{name}", e.name).replace("{where}", where).replace("{chain}", chain))
        else:
            out.append(T["mention_place"].replace("{name}", e.name).replace("{where}", where)
                       .replace("{chain}", T["mention_chain"].replace("{chain}", chain) if w is not None else ""))
    return out


_SECTIONS: dict[str, str] = {"style": "xml", "lang": "zh", "async": "angle"}  # turn.solve.sections / async_mark, set per solve_turn


def _T(lang: str | None = None) -> dict[str, Any]:
    """This module's strings (src/neonrp/prompts/turn_v3.<lang>.json) in the turn's language."""
    return _prompts.strings("turn_v3", lang or _SECTIONS.get("lang") or "zh")


def _set_wait_ops(reg: Any) -> None:
    """The registry's sync / async split, for the parser (引擎决定,符号只当提示)."""
    from neonrp.core import sdk as _sdk

    wait, fire = set(), set()
    for a in reg.actions.values():
        if a.scope != "world" or not a.enabled:
            continue
        (wait if a.waits() else fire).update(x for x in (a.op, a.alias) if x)
    _sdk.WAIT_OPS, _sdk.FIRE_OPS = wait, fire


# The prose reaches the screen as it is written. Set by the session around one solve_turn:
# on_text(piece) for the narration as streamed; on_event(kind, data) for a tool's answer the moment the engine gives it.
STREAM: dict[str, Any] = {"on_text": None, "on_event": None, "shown": False, "tier": None, "tail": ""}


def _stream_event(kind: str, data: dict[str, Any]) -> None:
    fn = STREAM.get("on_event")
    if fn is not None:
        try:
            fn(kind, data)
        except Exception:  # noqa: BLE001 — showing never breaks a turn
            logger.debug("stream event failed", exc_info=True)


def drop_restated(prefix: str, cont: str) -> str:
    """The continuation without the lines it restates from the top: a model told to append sometimes rewrites what it
    already wrote before going on. Only leading lines equal to a line already written are dropped."""
    seen = {ln.strip() for ln in str(prefix or "").splitlines() if ln.strip()}
    lines = str(cont or "").splitlines()
    k = 0
    while k < len(lines) and (not lines[k].strip() or lines[k].strip() in seen):
        k += 1
    return "\n".join(lines[k:]).strip("\n")


def join_continued(prefix: str, cont: str) -> str:
    """prefix + the continuation; a first continued line that restates the prefix's last line and goes on (a stop in
    the middle of 「你摸着砖缝[dice 侦查]」, then 「你摸着砖缝,一块砖松了。」) replaces it — the line is there once (10-17)."""
    if not cont:
        return prefix
    pl = prefix.splitlines()
    last, first = (pl[-1].strip() if pl else ""), cont.split("\n", 1)[0].strip()
    if last and first.startswith(last):
        pl = pl[:-1]
    head = "\n".join(pl)
    return head + ("\n" if head else "") + cont


def _chat(adapter: Any, system: str, user: str, on_text: Any = None, errors: list[str] | None = None) -> tuple[str, float, dict[str, Any]]:
    from neonrp.core import sdk as _sdk
    from neonrp.core.adv import async_restyle, restyle

    st, lg, am = _SECTIONS["style"], _SECTIONS["lang"], _SECTIONS.get("async", "angle")

    def rs(t: str, say: bool = False) -> str:
        t = restyle(t, st, lg)
        return async_restyle(t, am, _sdk.FIRE_OPS, lg) if (am != "angle" or say) else t

    hist = [Message(role=m.role, content=rs(m.content or "")) for m in _HISTORY_TURNS]
    t0 = time.perf_counter()
    msgs = [Message(role="system", content=rs(system, say=True)), *hist, Message(role="user", content=rs(user))]
    if on_text is not None:
        from neonrp.core.stream_lines import stream_chat

        tier = STREAM["tier"]() if callable(STREAM.get("tier")) else None
        out_text = _TierStream(on_text, *tier) if tier else on_text  # the screen too names no tier the dice did not give
        text, shown = stream_chat(adapter, msgs, out_text, skip_lines=STREAM.get("skip"), state=STREAM)
        if tier:
            out_text.flush()
        STREAM["shown"] = STREAM.get("shown") or shown
        return text, round((time.perf_counter() - t0) * 1000, 1), {}
    res = adapter.chat(msgs)
    if errors is not None and getattr(res, "error", None):
        errors.append(str(res.error))
    text = (getattr(getattr(res, "message", None), "content", None) or "").strip()
    usage = getattr(res, "usage", None) or {}
    return text, round((time.perf_counter() - t0) * 1000, 1), (dict(usage) if isinstance(usage, dict) else {})


def slow_extra(root: Path, lang: str) -> str:
    """What the thinking write-down reads on top of the shared transition prompt: the ``transition_slow`` unit (a
    layer may add one — the private layer's thinking budget, 10-23 C; the open engine ships none). The straight call
    never sees it: the two are the same prompt otherwise, so a line meant to shape thinking does not lengthen the
    answer that has no thinking."""
    try:
        t = _prompts.text("transition_slow", lang, root)
    except KeyError:
        return ""
    return t if t.strip() else ""


def _write_down(adapter: Any, system: str, user: str, root: Path, *, background: bool = False, lang: str = "zh") -> tuple[str, float, dict[str, Any], str]:
    """The transition after the prose (on screen already). Thinking writes the state down better (10-20: bread eaten,
    herbs chewed) but on a slow provider it ran 15–30 s (10-21 fixc: p90 16.8 s) and, timed by what the prose left over,
    came back empty — a beat's coins, night and moves were lost. So the thinking and the straight call go out together:
    the thinking answer is taken when it comes within ``transition_think_wait_s`` (40 s), else the straight one."""
    import concurrent.futures as _cf
    import contextvars as _cv

    from neonrp.core import beat_budget as _bb
    from neonrp.core.llm_openai import can_turn_thinking_off, thinking as _think

    on = _bb.transition_thinking(root)
    extra = slow_extra(root, lang)
    user_slow = user + ("\n\n" + extra if extra else "")
    if on and background and _bb.transition_async(root) and can_turn_thinking_off(adapter):
        # 10-22: the straight answer lands now; the thinking one corrects it from the background (core/write_down_async)
        from neonrp.core import write_down_async as _wda

        meta: dict[str, Any] = {}

        def slow() -> tuple[str, float, dict[str, Any]]:
            # the model is chosen here, off the beat (``auto`` asks the platform what this account may use)
            return _wda.run_slow(root, adapter, lambda a, errs: _chat(a, system, user_slow, errors=errs), meta, _think)

        _fut = _wda.launch(slow)
        _fut.meta = meta  # type: ignore[attr-defined]
        _wda.SLOW.set(_fut)
        _bb.ensure(_bb.transition_floor_s(root), "world.transition")
        with _think(False):
            return (*_chat(adapter, system, user), "straight")
    if not on or not can_turn_thinking_off(adapter):  # one call: thinking off, or a provider with no switch (both alike)
        _bb.ensure(_bb.transition_floor_s(root), "world.transition")
        with _think(on):
            return (*_chat(adapter, system, user_slow if on else user), "think" if on else "straight")
    wait = _bb.transition_think_wait_s(root)
    _bb.ensure(wait + 1.0, "world.transition")

    def run(on: bool) -> tuple[str, float, dict[str, Any]]:
        with _think(on), _bb.call_cap(wait):
            return _chat(adapter, system, user_slow if on else user)

    ex = _cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="write-down")
    try:
        f_think = ex.submit(_cv.copy_context().run, run, True)
        f_straight = ex.submit(_cv.copy_context().run, run, False)
        try:
            got = f_think.result(timeout=wait + 1.0)
        except Exception:  # noqa: BLE001 — a thinking call that failed or ran out: the straight one is there
            got = None
        if got and (got[0] or "").strip():
            return (*got, "think")
        _bb.note("world.transition_think")
        try:
            got = f_straight.result(timeout=max(1.0, _bb.remaining() or 1.0))
        except Exception:  # noqa: BLE001
            got = ("", 0.0, {})
        return (*got, "straight")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


# ── narrate, then transition ─────────────────────
# ① the narrator writes only the prose; anything whose result decides what comes next is a tool on that line (it stops
# there, the engine answers, it goes on — a world-changing one gets the engine's verdict). ② one clean-context call writes
# the state transition in two parts: <vars> new values of registered variables (closed schema), <files> the file-system
# changes (open schema). ③ reconcile: a tool's result wins over the transition; refusals send back only ②.
NARRATE = _prompts.md_by_lang("narrate")
TRANSITION = _prompts.md_by_lang("transition")


def _scalar(v: str) -> Any:
    v = v.strip().strip(",;")
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'「」":
        return v[1:-1]
    if v.startswith("「") and v.endswith("」"):
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def parse_transition(text: str) -> list[dict[str, Any]]:
    """② → ops: <vars> `name = value` lines become set (the player's location a move_to), a change by an amount
    (`name -6` · `name -= 6` · `name += 2`, as <files> already reads it) an add; <files> lines are ops."""
    from neonrp.core import sdk as _sdk

    ops: list[dict[str, Any]] = []
    for ln in (_sdk._block("vars", text or "") or "").splitlines():
        rel = re.match(r"\s*[-*•]?\s*([A-Za-z_][\w.]*)\s*([+-])=?\s*(\d+(?:\.\d+)?)\s*$", ln)
        if rel:  # 10-23 niko: pseudocode — 09-27 var_op reads a signed amount as an add; this parser (10-04) dropped it
            ops.append(_sdk.var_op(rel.group(1), rel.group(2) + rel.group(3)))
            continue
        m = re.match(r"\s*[-*•]?\s*([A-Za-z_][\w.\-]*)\s*[=:：]\s*(.+?)\s*$", ln)
        if not m:
            continue
        name, val = m.group(1), _scalar(m.group(2))
        if name in ("location", "player.location"):
            ops.append({"op": "move_to", "who": "player", "to": str(val)})
        else:
            ops.append({"op": "set", "var": name, "value": val})
    files, bodies = _sdk._lift_writes(_sdk._block("files", text or "") or "")  # a file's body spans lines (llm 1004 PL14)
    for ln in files.splitlines():
        o = _sdk._adv_line_op(re.sub(r"^\s*[-*•]\s*", "", ln))
        if o is not None and o.get("op") != "noop":
            o.pop("await", None)
            if o.get("op") == "write" and o.get("path") in bodies:
                o["body"] = bodies[o["path"]]
            ops.append(o)
    return ops


def _same_target(a: dict[str, Any], b: dict[str, Any], reg: Any) -> bool:
    """Do two ops change the same thing? The same variable (set / add / flag alike) or the same mover — whatever the op."""
    va, vb = a.get("var") or (a.get("key") if a.get("op") == "flag" else None), b.get("var") or (b.get("key") if b.get("op") == "flag" else None)
    if va or vb:
        return bool(va) and va == vb
    if a.get("op") == "move_to" and b.get("op") == "move_to":
        wa, wb = str(a.get("who") or ""), str(b.get("who") or "")
        return (reg.resolve(wa) or wa) == (reg.resolve(wb) or wb)
    return _same_op(a, b, reg)


def _verdict_text(o: dict[str, Any], vr: Any, reg: Any) -> str:
    """The engine's answer to a world-changing tool in the prose: done as asked, landed elsewhere, or refused (why)."""
    T = _T()
    for r in vr.refused:
        if _same_op(r.op if isinstance(r.op, dict) else {}, o, reg):
            return T["v_no"].replace("{why}", str(r.why))
    for a in vr.accepted:
        if _same_op(a, o, reg):
            if a.get("_clamped"):
                return T["v_clamped"].replace("{to}", str(a.get("to"))).replace("{why}", str(a["_clamped"].get("why")))
            return T["v_ok"]
    return T["v_ok"]


def _capture_solve(root: Path, turn: int, system: str, user: str) -> None:
    """NEONRP_CAPTURE_SOLVE=<file.jsonl>: append this solve's exact input (system, history, user block, section style) —
    so output shapes can be compared on identical inputs (benchmarks/solve_ab.py). Never on in play."""
    import json as _json

    from neonrp.core import sdk as _sdk
    from neonrp.core.adv import async_restyle, restyle

    st, lg, am = _SECTIONS["style"], _SECTIONS["lang"], _SECTIONS.get("async", "angle")

    def rs(t: str, say: bool = False) -> str:  # exactly what _chat sends
        t = restyle(t, st, lg)
        return async_restyle(t, am, _sdk.FIRE_OPS, lg) if (am != "angle" or say) else t

    try:
        rec = {"root": str(root), "turn": turn, "system": rs(system, say=True), "user": rs(user), "sections": dict(_SECTIONS),
               "history": [{"role": m.role, "content": rs(m.content or "")} for m in _HISTORY_TURNS]}
        # one file per process: parallel runs must not interleave long lines in one file
        with open(f"{os.environ['NEONRP_CAPTURE_SOLVE']}.{os.getpid()}", "a", encoding="utf-8") as fh:
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — an experiment hook never breaks a turn
        pass


def solve(adapter: Any, system: str, user: str) -> tuple[SolveOutput, float, dict[str, Any]]:
    """together: one call → {narration, ops}. The prose streams to the screen when a session asked for it (STREAM)."""
    text, ms, usage = _chat(adapter, system, user, on_text=STREAM.get("on_text"))
    return parse_solve_output(text), ms, usage


def _split_texts() -> tuple[str, str, str]:
    T = _T()
    return T["split_narrate"], T["split_extract"], T["par_ops"]


def solve_parallel(adapter: Any, system: str, user: str) -> tuple[SolveOutput, float, dict[str, Any], float]:
    """parallel: prose and ops from two concurrent calls that see the same inputs; nothing
    reconciles them. The prose is unconstrained; the ops are decided, not extracted."""
    from concurrent.futures import ThreadPoolExecutor

    split_narrate, _split_extract, par_ops = _split_texts()
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(_chat, adapter, system + split_narrate, user)
        f2 = ex.submit(_chat, adapter, par_ops + system, user)
        narr, ms1, u1 = f1.result()
        ext, ms2, u2 = f2.result()
    narr = parse_solve_output(narr).narration or narr
    out = parse_solve_output(ext)
    usage = {k: (u1.get(k, 0) or 0) + (u2.get(k, 0) or 0) for k in set(u1) | set(u2)}
    return SolveOutput(narr, out.ops, "parallel", narr + "\n---\n" + ext), ms1, usage, ms2


def solve_split2(adapter: Any, system: str, user: str) -> tuple[SolveOutput, float, dict[str, Any], float]:
    """split2: two batches, prose first, then ops conditioned on the prose. Both calls share
    the identical system + user prefix so the provider's prefix cache serves the second call; only the
    short ops output is paid for. (The old `split` arm prepended the extractor to the system prompt and
    broke the cache — that is why it measured 30 s.)"""
    T = _T()
    narr, ms1, u1 = _chat(adapter, system, user + T["split2_narrate"])
    narr = parse_solve_output(narr).narration or narr
    ext, ms2, u2 = _chat(adapter, system, user + T["split2_extract"].format(narr=narr[:4000]))
    out = parse_solve_output(ext)
    usage = {k: (u1.get(k, 0) or 0) + (u2.get(k, 0) or 0) for k in set(u1) | set(u2)}
    return SolveOutput(narr, out.ops, "split2", narr + "\n---\n" + ext), ms1, usage, ms2


def solve_split(adapter: Any, system: str, user: str) -> tuple[SolveOutput, float, dict[str, Any], float]:
    """split: call 1 narration only, call 2 extract ops from it (the 09-23 'B' arm, kept for E1)."""
    split_narrate, split_extract, _par = _split_texts()
    narr, ms1, u1 = _chat(adapter, system + split_narrate, user)
    narr = parse_solve_output(narr).narration or narr
    ext, ms2, u2 = _chat(adapter, split_extract + system, user + _T()["just_happened"] + narr)
    out = parse_solve_output(ext)
    usage = {k: (u1.get(k, 0) or 0) + (u2.get(k, 0) or 0) for k in set(u1) | set(u2)}
    return SolveOutput(narr, out.ops, "split", ext), ms1, usage, ms2


# ── the turn slice ───────────────────────────────────────────────────────────


def _same_op(a: dict[str, Any], b: dict[str, Any], reg: Registry) -> bool:
    """Two ops target the same thing (so a restated op wins over a carried one)."""
    if a.get("op") != b.get("op"):
        return False
    if a.get("op") in ("move_to", "engage", "need"):
        wa, wb = str(a.get("who") or ""), str(b.get("who") or "")
        return (reg.resolve(wa) or wa) == (reg.resolve(wb) or wb)
    for k in ("var", "key", "name"):
        if k in a or k in b:
            return a.get(k) == b.get(k)
    return a == b


def _tier_args(root: Path, lang: str, rolled: list[dict[str, Any]] | None,
               tool_log: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any], dict[str, Any]] | None:
    """(levels, words, names) for core.dice.tier_guard — this beat's rolls: the agreed checks (both sides of a contest),
    then the narrator's own [dice] answers; the words are the pack's (``tier_words`` in its strings). None: nothing to guard."""
    from neonrp import packs, prompts

    levels = [str(s.get("level")) for r in rolled or [] if isinstance(r, dict) for s in (r.get("a"), r.get("b")) if isinstance(s, dict) and s.get("level")]
    levels += [str(t["level"]) for t in tool_log if isinstance(t, dict) and t.get("level")]
    if not levels:
        return None
    try:
        pk = packs.resolve(root)
    except Exception:  # noqa: BLE001 — no pack, no words
        return None
    for name in (pk.name, pk.base):
        try:
            S = prompts.strings(name, lang) if name else {}
        except KeyError:
            continue
        if isinstance(S.get("tier_words"), dict):
            return levels, S["tier_words"], S
    return None


def _tier_check(root: Path, lang: str, text: str, rolled: list[dict[str, Any]] | None,
                tool_log: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    from neonrp.core import dice as _dice

    args = _tier_args(root, lang, rolled, tool_log)
    return _dice.tier_guard(text, *args) if args else (text, [])


class _TierStream:
    """on_text through core.dice.tier_guard: the tail that may still grow into a tier word is held for the next piece."""

    def __init__(self, on_text: Any, levels: list[str], words: dict[str, Any], names: dict[str, Any]):
        self.on_text, self.args, self.buf = on_text, (levels, words, names), ""
        self.words = [str(w) for ws in words.values() if isinstance(ws, list) for w in ws if w]

    def __call__(self, piece: str) -> None:
        from neonrp.core import dice as _dice

        text, _ = _dice.tier_guard(self.buf + piece, *self.args)
        hold = max((k for w in self.words for k in range(1, len(w) + (1 if w.isascii() else 0))
                    if text[-k:].lower() == w[:k].lower()), default=0)
        self.buf = text[len(text) - hold:] if hold else ""
        if text[:len(text) - hold]:
            self.on_text(text[:len(text) - hold])

    def flush(self) -> None:
        from neonrp.core import dice as _dice

        if self.buf:
            text, _ = _dice.tier_guard(self.buf, *self.args)
            self.buf = ""
            self.on_text(text)


def solve_turn(
    root: Path,
    *,
    user_text: str,
    provider: str | None,
    turn: int,
    soul_reports: list[dict[str, Any]],
    plan_facts: str = "",
    history: list[str] | None = None,
    spans: list[dict[str, Any]] | None = None,
    t_base: float | None = None,
    ask_soul: Callable[[str, str], dict[str, Any]] | None = None,
    soul_ops: list[dict[str, Any]] | None = None,
    intent_kind: str = "",
    branch: str = "main",
    gate: dict[str, Any] | None = None,
    rolled: list[dict[str, Any]] | None = None,
    talk: list[str] | None = None,
    player_present: bool = True,
    ruled_ops: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run ③–⑤ once (plus at most ``max_loops`` re-proposals). ``player_present=False`` = a beat off the player's
    screen (a character's own action, 10-21): nothing lands on the player (sdk.PLAYER_AWAY — verify refuses it).
    Returns a dict::

        {"narration", "ops", "verify", "apply": ApplyResult, "loops", "ms", "usage", "spans", "solve": SolveOutput}
    """
    if not player_present:
        from neonrp.core import sdk as _sdk_pa

        _tok = _sdk_pa.PLAYER_AWAY.set(True)
        try:
            return solve_turn(root, user_text=user_text, provider=provider, turn=turn, soul_reports=soul_reports, plan_facts=plan_facts,
                              history=history, spans=spans, t_base=t_base, ask_soul=ask_soul, soul_ops=soul_ops, intent_kind=intent_kind,
                              branch=branch, gate=gate, rolled=rolled, talk=talk, ruled_ops=ruled_ops)
        finally:
            _sdk_pa.PLAYER_AWAY.reset(_tok)
    cfg = engine_config.engine_config(root)
    max_loops = int(engine_config._get_path(cfg, "turn.verify.gate.max_loops", 1))
    structured = _orch.solve_structured(root)  # the Resolve node's state parameter: pseudo | jev (10-11; the graph is the one source)
    if structured in ("jevjson", "jevjson-inline", "describe"):
        from neonrp.core import system_one as _s1x

        structured = structured if _s1x.fast_judge_available() else "narrate"  # Jev's hundreds of questions need a fast Jev
    inline = structured == "jevjson-inline"  # variant B: the description written after </lines> in the same call (one model call fewer)
    if inline:
        structured = "jevjson"
    jevjson = structured == "jevjson"  # 10-10 experiment: plain words, then Jev fills our tools' JSON line by line (fallback: pseudo-code)
    describe = structured in ("describe", "jevjson")  # 10-10 experiment: prose with tools, then plain words → Jev → the JSON changes
    narrate = structured in ("narrate", "describe", "jevjson")  # 10-04: prose with tools, then one state transition (the contract stays ADV)
    if narrate:
        structured = "adv"
    max_ops = int(engine_config._get_path(cfg, "turn.solve.max_ops", 24))
    writers = str(engine_config._get_path(cfg, "turn.apply.writers", "on"))
    spans = spans if spans is not None else []
    base = t_base if t_base is not None else time.monotonic()
    from neonrp.core import write_down_async as _wda0

    _wda0.SLOW.set(None)  # a background write-down left by a beat that failed after launching it is not this beat's

    def span(phase: str, actor: str, backend: str, t0: float, **out: Any) -> None:
        spans.append({"phase": phase, "actor": actor, "backend": backend,
                      "t0": round((t0 - base) * 1000, 1), "t1": round((time.monotonic() - base) * 1000, 1), **out})

    t0 = time.monotonic()
    reg = load_registry(root)
    _budget = int(engine_config.get(root, "turn.plan.pack_budget", 0) or 0) or None
    global _HISTORY_TURNS
    from neonrp.core.adv import prompt_spec as _prompt_spec

    _examples = history_messages((_prompt_spec(root).get("examples") or [])[:3])  # 示例对话 (Yumina's example role): before the real history
    _HISTORY_TURNS = _examples + history_messages(history)[-2 * int(engine_config._get_path(cfg, "turn.solve.history", 4)):]
    p: Pack = pack(root, history=None, registry=reg, budget_chars=_budget)  # history rides as chat turns, not as a pasted digest
    pack_text = render_pack(p)
    hints = _mech.get(root, "pack_hints")(root, reg) or ""
    if hints:
        pack_text = pack_text + "\n\n" + hints
    span("plan", "engine.pack", "python", t0, reads=reg.reads, chars=len(pack_text), entries=len(reg.entries))

    adapter = _adapter(root, provider, structured)
    from neonrp.core.output_lang import pick_lang, prompt_lang

    lang = prompt_lang(root)
    _SECTIONS.update({"style": str(engine_config._get_path(cfg, "turn.solve.sections", "xml") or "xml"), "lang": lang,
                      "async": str(engine_config._get_path(cfg, "turn.solve.async_mark", "tilde") or "tilde")})
    from neonrp.core.adv import entries_for, prompt_spec

    _hist_text = "\n".join((h.get("user", "") + "\n" + h.get("assistant", "")) if isinstance(h, dict) else str(h) for h in (history or []))
    kw_entries = entries_for(prompt_spec(root), lang, texts=user_text + "\n" + _hist_text, reg=reg)["keyword"]
    mentions = _mentions(reg, user_text)
    understood = (_mech.get(root, "understand")(root, reg, user_text) or {}) if user_text else {}  # P0: the player's words as an attempt, checked against the world
    from neonrp.core import player_gate as _pg

    t0 = time.monotonic()
    pg = gate if gate is not None else (_pg.gate(root, reg, user_text, history, branch=branch) if user_text else None)  # intent + what the player cannot know (run before the souls when they act)
    if pg:
        understood = dict(understood or {})
        understood["gate"] = {k: v for k, v in pg.items() if k != "block"}
        understood["block"] = "\n\n".join(x for x in (understood.get("block") or "", pg["block"]) if x)
        span("plan", "player_gate", "llm", t0, named=len(pg["named"]), unseen=sum(1 for x in pg["named"] if not x["source"]))
    if understood.get("block"):
        mentions = []  # the understanding covers the named-but-absent people too
    system = _mech.get(root, "contract")(root, reg, structured)
    tool_log: list[dict[str, Any]] = []
    STREAM["tier"] = lambda: _tier_args(root, lang, rolled, tool_log)
    STREAM["tail"] = ""  # what the streamed prose may claim, as the rolls come in
    owner_checked = False  # the owner rule (core/l2.owner_rule) asks once per turn
    marks_at: list[dict[str, Any]] = []  # where each request / engine answer / fired tool sits in the prose (annotated output)
    from neonrp.core import modes as _modes
    from neonrp.core import sdk as _sdk

    _sdk.SWITCH_TAGS = {x for a in reg.actions.values() if a.enabled and a.scope == "world" and (a.kind == "mode" or (a.kind == "tool" and "note" in a.fields))
                        for x in (a.op, a.alias) if x}  # a switch, or a one-shot layer whose call carries a body ([combat …]what each does[/combat])
    _set_wait_ops(reg)
    layer_extra = ""
    gate_returns: list[dict[str, Any]] = []
    t0 = time.monotonic()
    gate = _mech.get(root, "gate")(root, reg, user_text=user_text, intent_kind=intent_kind, turn=turn) or {}
    if gate.get("mode"):  # the engine forces a layer for this turn (a fight on the road …) — when the graph has that edge
        if _modes.enter(root, reg, str(gate["mode"]), turn=turn, note=str(gate.get("note") or ""), via={"gate": True}) is not None:
            reg = load_registry(root)
    if gate.get("returns"):  # the engine pre-ruled (referee): the narrator writes by it
        gate_returns = list(gate["returns"])
        tool_log += gate_returns
        layer_extra = (H_GATE.get(lang) or H_GATE["zh"]) + "\n" + "\n".join(
            f"<{t.get('request')}>{t.get('text') or t.get('why') or t}</{str(t.get('request') or '').split(' ')[0]}>" for t in gate_returns)
        marks_at.append({"after": None, "items": [_mark_answer(t, by_engine=True) for t in gate_returns]})
    gate_panels: dict[str, Any] = {}
    gate_fire: list[dict[str, Any]] = []
    for fo in gate.get("fire") or []:  # the engine fires an async tool itself (<map> when the player asks the way)
        _fs = reg.actions.get(str(fo.get("op")))
        if _fs is None or _fs.waits():
            continue
        # 10-08: not now — after the write-down, with the narrator's own [~map] (it is never awaited, and drawn now it
        # showed where the player stood BEFORE this beat's move)
        gate_fire.append({**dict(fo), "_by": "gate"})
        marks_at.append({"after": None, "items": [f"[~{_fs.op}]"]})
    if gate:
        span("plan", "gate", "python", t0, mode=gate.get("mode"), ruled=bool(gate.get("returns")), fired=[str(f.get("op")) for f in gate.get("fire") or []])
    mode = _modes.read_mode(root)
    if not mode:  # a place-keyed layer (dungeon room → the dungeon agent's prompt) for this turn only
        _hl = _modes.here_layer(root, reg)
        mode = {"name": _hl} if _hl else None
    _sdk.PANEL_TAGS = set()
    if mode:  # the world is inside a mode layer (combat …): the whole system prompt is the layer's, plus its reads and state
        _spec = _modes.spec_of(root, mode["name"]) or {}
        _sdk.PANEL_TAGS = set((_spec.get("panels") or {}).keys())
        system = _modes.layer_system(root, reg, mode["name"], lang, structured=structured)
        layer_extra = "\n\n".join(x for x in (layer_extra, _modes.reads_block(root, reg, _spec), _modes.state_block(root, reg, _spec)) if x)
    reports = list(soul_reports)
    companions_judged: list[dict[str, Any]] = []  # who was asked whether she walks with the player, and what decided it (the trace)
    conts = 0  # continuations this turn (tool requests / layer switches) — not re-proposals
    refusals: list[dict[str, Any]] | None = None
    prev: SolveOutput | None = None
    usage_total: dict[str, Any] = {}
    proposals: list[dict[str, Any]] = []  # every solve attempt: what the model proposed, what verify said
    verdict_keep: list[dict[str, Any]] = []  # narrate: world-changing tools the engine ruled on mid-prose (they land as ruled)
    deferred_fire: list[dict[str, Any]] = list(gate_fire)  # narrate: [~map] / [~sheet] are drawn after the write-down
    narr_lang = lang if lang in NARRATE else "en"
    loops = 0
    out: SolveOutput = SolveOutput("", [], "none")
    vr = None
    # changes a one-shot layer wrote ([combat] → hp): verified and landed with the beat's own. 10-22: the node before's
    # rulings (the plan's agreed payments) start the list — the prose's and the transition's own copy of the same variable
    # goes (PL12: of 9 runs, 4 missed the payment and 3 charged it twice)
    tool_ruled: list[dict[str, Any]] = [{**dict(x), "_by": "plan"} for x in ruled_ops or [] if isinstance(x, dict)]
    carry: list[dict[str, Any]] = []  # E5 run3 C3c: the continuation after `need` came back with ops=[] and dropped the player's move
    tool_returns: list[dict[str, Any]] = []  # [roll 1d6]-style requests answered by the engine, fed into the continuation
    prefix = ""  # lines written before a request: final; the continuation appends to them
    panels_acc: dict[str, Any] = dict(gate_panels)  # a layer's cards (<formation>) and tool-drawn cards ([map]) across the turn's continuations
    while True:
        t0 = time.monotonic()
        ublock = _user_block(pack_text, user_text, reports, plan_facts, refusals, prev, tool_returns, lang=lang, keyword_entries=kw_entries, prefix=prefix, mentions=mentions,
                             extra="\n\n".join(x for x in (layer_extra, understood.get("block") or "") if x))
        if narrate:
            from neonrp.core.adv import narrate_lang_line

            ublock = ublock + _prompts.text("narrate", narr_lang, root) + "".join("\n\n" + x for x in (narrate_lang_line(root, narr_lang),) if x)  # run → pack → engine (R3); the language last (C3-2)
            if inline:  # B: the changes and possibilities after the prose, same call (the stream shows only <lines>)
                ublock += "\n\n" + _prompts.text("describe_inline", narr_lang, root)
        if loops == 0 and not prefix and os.environ.get("NEONRP_CAPTURE_SOLVE"):  # experiments only: the exact first solve input
            _capture_solve(root, turn, system, ublock)
        if structured == "split":
            out, ms, usage, ms2 = solve_split(adapter, system, ublock)
            span("solve", "world.narrate", "llm", t0, loop=loops, chars=len(out.narration), ms=ms)
            span("solve", "world.extract", "llm", time.monotonic() - ms2 / 1000.0, loop=loops, ops=len(out.ops), ms=ms2)
        elif structured == "split2":
            out, ms, usage, ms2 = solve_split2(adapter, system, ublock)
            span("solve", "world.narrate", "llm", t0, loop=loops, chars=len(out.narration), ms=ms)
            span("solve", "world.extract", "llm", time.monotonic() - ms2 / 1000.0, loop=loops, ops=len(out.ops), ms=ms2)
        elif structured == "parallel":
            out, ms, usage, ms2 = solve_parallel(adapter, system, ublock)
            span("solve", "world.narrate", "llm", t0, loop=loops, chars=len(out.narration), ms=ms)
            span("solve", "world.ops", "llm", t0, loop=loops, ops=len(out.ops), ms=ms2)
        elif structured == "prose_json":
            # prose first (unconstrained), one fenced JSON block at the tail; if the block is missing,
            # ONE lean extraction call recovers the ops (the split arm's second call) instead of guessing "no change"
            out, ms, usage = solve(adapter, system, ublock)
            span("solve", "world", "llm", t0, loop=loops, fmt=out.fmt, ops=len(out.ops), chars=len(out.narration), ms=ms)
            if out.fmt == "none" and out.narration:
                t1 = time.monotonic()
                ext, ms2, u2 = _chat(adapter, _split_texts()[1] + system, ublock + _T()["just_happened"] + out.narration)
                out = SolveOutput(out.narration, parse_solve_output(ext).ops, "extracted", out.raw + "\n---\n" + ext)
                for k, v in u2.items():
                    if isinstance(v, (int, float)):
                        usage[k] = (usage.get(k, 0) or 0) + v
                span("solve", "world.extract", "llm", t1, loop=loops, ops=len(out.ops), ms=ms2)
        else:
            out, ms, usage = solve(adapter, system, ublock)
            extra = {} if out.fmt in ("json", "tags") else {"raw_head": out.raw[:400], "raw_tail": out.raw[-200:]}
            span("solve", "world", "llm", t0, loop=loops, fmt=out.fmt, ops=len(out.ops), chars=len(out.narration), ms=ms, **extra)
            # an empty reply (provider dropped the stream; adv7 C4b lost a whole turn to it): ask once more — if the beat has time
            if not out.raw.strip() and not _beat.expired(_beat.MIN_RETRY_S):
                t1 = time.monotonic()
                out, ms, u2 = solve(adapter, system, ublock)
                for k, v in u2.items():
                    if isinstance(v, (int, float)):
                        usage[k] = (usage.get(k, 0) or 0) + v
                span("solve", "world.retry", "llm", t1, loop=loops, fmt=out.fmt, ops=len(out.ops), chars=len(out.narration), ms=ms, why="empty reply")
        if prefix:  # continuation: prepend the final prefix; the model was told to append only
            cont = drop_restated(prefix, out.narration)  # …but sometimes starts over (10-05 C1: six lines twice after [combat])
            out = SolveOutput(join_continued(prefix, cont), out.ops, out.fmt, out.raw, options=out.options, cot=out.cot,
                              panels={**panels_acc, **out.panels})
            prefix = ""
            STREAM["skip"] = None
        if narrate:  # [options …] is a tool: the last one given is the options; it never stays in the prose
            _opt = re.findall(r"\[options\s+([^\]]+)\]", out.raw or "")
            out.ops = [o for o in out.ops if o.get("op") != "options"]
            out.narration = re.sub(r"\[options[^\]]*\]", "", out.narration).strip()
            if _opt:
                out.options = [x.strip() for x in re.split(r"[|｜]", _opt[-1]) if x.strip()]
        panels_acc.update(out.panels)
        for k, v in usage.items():
            if isinstance(v, (int, float)):
                usage_total[k] = usage_total.get(k, 0) + v
        t0 = time.monotonic()
        # a soul's judged move is a proposal like any world op: same verify, same judge_move
        _all_ops = list(out.ops)
        for so in soul_ops or []:
            if not any(o.get("op") == "move_to" and reg.resolve(str(o.get("who") or "")) == so["who"] for o in out.ops):
                _all_ops.append(dict(so))
        for co in carry:
            if not any(_same_op(o, co, reg) for o in _all_ops):
                _all_ops.append(dict(co))
        if tool_ruled:  # the layer's ruling first and whole (two blows on one foe are two ops); the prose's own copy of it goes
            _all_ops = [dict(x) for x in tool_ruled] + [o for o in _all_ops if not any(_same_op(o, x, reg) for x in tool_ruled)]
        if loops == 0:
            # ops queued by hooks (ledger.enqueue) ride the same verify as the model's — never a side door
            from neonrp.core.ledger import drain as _drain

            for qo in _drain(root):
                _all_ops.append({k: v for k, v in qo.items() if k != "_by"})
        # a layer's validator may judge by what the prose has shown (10-19: a foe the narrator brought in is grounds)
        _all_ops = [{**o, "_seen": out.narration, "_player": user_text}
                    if reg.actions.get(o.get("op")) is not None and reg.actions[o["op"]].kind in ("tool", "mode") and reg.actions[o["op"]].validator
                    else o for o in _all_ops]
        vr = verify(root, _all_ops, reg, max_ops=max_ops)
        for _o in [*vr.accepted, *[_r.op for _r in vr.refused]]:
            if isinstance(_o, dict):
                _o.pop("_seen", None)
                _o.pop("_player", None)
        # companions follow the player's ACTUAL landing (after clamping), unless told to stay
        # (a Resolve after a talk: the people present skipped their turn — the seam reads the whole talk instead)
        judged: list[dict[str, Any]] = []
        fops = _mech.get(root, "companions")(root, reg, vr.accepted, reports, talk=talk, user_text=user_text, judged=judged) or []
        companions_judged.extend(judged)
        if fops:
            fvr = verify(root, fops, reg, max_ops=max_ops)
            vr.accepted.extend(fvr.accepted)
            vr.refused.extend(fvr.refused)
        span("verify", "l1", "python", t0, accepted=len(vr.accepted), refused=[r.to_dict() for r in vr.refused], **({"companions": judged} if judged else {}))
        proposals.append({"attempt": loops, "fmt": out.fmt, "narration": out.narration[:2000], "ops": list(out.ops), "raw": (out.raw or "")[:6000],
                          "options": list(out.options), "marks": list(out.marks),
                          "accepted": [{k: v for k, v in o.items() if not k.startswith("_")} for o in vr.accepted],
                          "refused": [r.to_dict() for r in vr.refused], "fed_back": list(refusals or [])})
        # requests to registered tools ([roll d20]): run now, take them out of the diff, answer in the continuation
        if out.marks:
            span("verify", "marks", "python", time.monotonic(), marks=out.marks, mismatched=[m for m in out.marks if not m.get("ok")])
        all_tools = [o for o in vr.accepted if reg.actions.get(o["op"]) and reg.actions[o["op"]].kind == "tool"]
        # async tools (<map>): run now, shown to the player, never awaited — no continuation, nothing fed back
        fire_ops = [o for o in all_tools if not reg.actions[o["op"]].waits()]
        tool_ops = [o for o in all_tools if reg.actions[o["op"]].waits()]
        if narrate and fire_ops:  # shown to the player only: drawn after the write-down (the map sees this beat's places)
            deferred_fire += [o for o in fire_ops if not any(d["op"] == o["op"] for d in deferred_fire)]
            vr.accepted = [o for o in vr.accepted if o not in fire_ops]
            fire_ops = []
        verdict_ops: list[dict[str, Any]] = []
        if narrate:  # a world-changing tool in the prose ([move player far] · [new_location …] · [player.gold -12]): the engine rules, the prose goes on
            # written in brackets in the prose (the parser drops ``await`` for ops the registry says do not wait — here the
            # bracket is the narrator asking for a ruling, so the raw text decides)
            _asked = [x for x in (_sdk._adv_line_op(m.group(0)) for m in _sdk._REQUEST_RE.finditer(out.raw or "")) if x and x.get("op") != "noop"]
            verdict_ops = [o for o in out.ops if o.get("op") not in ("need", "options")
                           and not (reg.actions.get(o["op"]) and reg.actions[o["op"]].kind in ("tool", "mode", "request"))
                           and any(_same_target(o, q, reg) for q in _asked)]
            if verdict_ops:
                fresh_v = [{"request": " ".join(str(x) for x in [o.get("op")] + [v for k, v in o.items() if k not in ("op", "await") and not str(k).startswith("_")]),
                            "text": _verdict_text(o, vr, reg)} for o in verdict_ops]
                verdict_keep += [a for a in vr.accepted if any(_same_op(a, o, reg) for o in verdict_ops) and not any(_same_op(a, k, reg) for k in verdict_keep)]
                tool_returns = tool_returns + fresh_v
                tool_log += fresh_v
                for _t in fresh_v:
                    _stream_event("verdict", _t)
                prefix = out.prefix or out.narration
                STREAM["skip"] = {x.strip() for x in prefix.splitlines() if x.strip()}  # the continuation's restated lines are not streamed again
                marks_at.append({"after": (prefix.splitlines() or [None])[-1], "items": [f"[{t['request']}]<{t['text']}>" for t in fresh_v]})
                span("verify", "verdicts", "python", time.monotonic(), loop=loops, requests=[t["request"] for t in fresh_v])
        if fire_ops:
            from neonrp.core.handlers import HandlerError

            vr.accepted = [o for o in vr.accepted if o not in fire_ops]
            for k, o in enumerate(fire_ops):
                if any(t.get("async") and t.get("request") == o["op"] for t in tool_log):
                    continue  # one card per tool per turn: a re-proposal re-marking <map> does not draw it twice
                try:
                    r = _tool_watch.call(root, reg, o["op"], reg.actions[o["op"]].handler, o, None, seed=f"{turn}:{loops}:a{k}", turn=turn)  # watched (10-03)
                except HandlerError as exc:
                    r = {"ok": False, "why": str(exc)[:200]}
                rec = {"request": o["op"], "async": True, **(r if isinstance(r, dict) else {"text": str(r)})}
                marks_at.append({"after": (out.narration.splitlines() or [None])[-1], "items": [f"[~{o['op']}]"]})
                tool_log.append(rec)
                if isinstance(r, dict) and r.get("panel"):
                    panels_acc[str(r.get("panel"))] = r.get("panel_value") or {"id": str(r.get("panel")), "format": "text", "source": "tool", "text": str(r.get("text") or "")}
        if tool_ops:
            from neonrp.core.handlers import HandlerError

            t3 = time.monotonic()
            vr.accepted = [o for o in vr.accepted if o not in tool_ops]
            fresh: list[dict[str, Any]] = []
            for k, o in enumerate(tool_ops):
                spec = reg.actions[o["op"]]
                req = " ".join([o["op"]] + [str(o.get(f)) for f in spec.fields if o.get(f) is not None])
                _once = bool((_modes.spec_of(root, o["op"]) or {}).get("one_shot"))
                if _once and any(str(t.get("request") or "").split(" ")[0] == o["op"] and t.get("ok") is not False for t in [*tool_log, *fresh]):
                    # a one-shot layer runs once a beat (10-19): one beat is one round; the next is talked over first
                    r = {"ok": False, "why": _T(lang)["one_round_per_beat"].replace("{op}", o["op"])}
                else:
                    try:
                        r = _tool_watch.call(root, reg, o["op"], spec.handler, o, None, seed=f"{turn}:{loops}:{k}", turn=turn)  # watched (10-03)
                    except HandlerError as exc:
                        r = {"ok": False, "why": str(exc)[:200]}
                if isinstance(r, dict) and r.get("ops"):  # a one-shot layer's changes (hp): they land with the beat, the tool's ruling wins
                    tool_ruled += [{**dict(x), "_by": o["op"]} for x in r["ops"] if isinstance(x, dict)]
                if isinstance(r, dict) and r.get("reload"):  # it put things in the world (foes): the rest of the beat sees them
                    reg = load_registry(root)
                fresh.append({"request": req, **({k: v for k, v in r.items() if k != "ops"} if isinstance(r, dict) else {"text": str(r)})})
                if isinstance(r, dict) and r.get("panel"):  # an engine-drawn card ([map]): shown to the player too
                    panels_acc[str(r.get("panel"))] = r.get("panel_value") or {"id": str(r.get("panel")), "format": "text", "source": "tool", "text": str(r.get("text") or "")}
            tool_returns = tool_returns + fresh
            tool_log += fresh
            for _o, _t in zip(tool_ops, fresh):
                _stream_event("tool", {**_t, "reason": _o.get("reason")})
            prefix = out.prefix or out.narration  # the stream's stop point: what came before stays, the rest is appended
            STREAM["skip"] = {x.strip() for x in prefix.splitlines() if x.strip()}  # the continuation's restated lines are not streamed again
            marks_at.append({"after": (prefix.splitlines() or [None])[-1], "items": [_mark_request(o, t) + _mark_answer(t) for o, t in zip(tool_ops, fresh)]})
            span("verify", "tools", "python", t3, loop=loops, requests=[t["request"] for t in fresh], prefix_lines=len(prefix.splitlines()))
        # a layer switch (<combat>…</combat>): the prefix stays, the whole system prompt becomes the layer's, the layer continues the turn
        switch_ops = [o for o in vr.accepted if reg.actions.get(o["op"]) and reg.actions[o["op"]].kind == "mode"]
        if switch_ops:
            t4 = time.monotonic()
            so = switch_ops[0]
            vr.accepted = [o for o in vr.accepted if o not in switch_ops]
            _roster = " ".join(str(x) for x in (so.get("args") or [])) or str(so.get("roster") or "")
            mode = _modes.enter(root, reg, so["op"], turn=turn, note=str(so.get("note") or ""), via={"op": so["op"]},
                                **({"roster": _roster} if _roster else {})) or _modes.read_mode(root)
            reg = load_registry(root)  # the layer's variables (foe.*) exist now
            _spec = _modes.spec_of(root, so["op"]) or {}
            _sdk.PANEL_TAGS = set((_spec.get("panels") or {}).keys())
            system = _modes.layer_system(root, reg, so["op"], lang, structured=structured)
            layer_extra = "\n\n".join(x for x in (_modes.reads_block(root, reg, _spec), _modes.state_block(root, reg, _spec)) if x)
            prefix = out.prefix or out.narration
            STREAM["skip"] = {x.strip() for x in prefix.splitlines() if x.strip()}  # the continuation's restated lines are not streamed again
            marks_at.append({"after": (prefix.splitlines() or [None])[-1],
                             "items": [f"[{so['op']} {_roster}]".replace(" ]", "]") + (str(so.get("note") or "")) + f"[/{so['op']}]"]})
            _Tt = _T(lang)
            fresh = [{"request": so["op"], "text": _Tt["switched"].replace("{title}", str(pick_lang(_spec.get('title'), lang) or so['op']))
                      + (_Tt["handover"].replace("{note}", str(so.get('note'))) if so.get("note") else ""), "mode": mode}]
            tool_returns = tool_returns + fresh
            tool_log += fresh
            span("verify", "switch", "python", t4, loop=loops, mode=so["op"], note=str(so.get("note") or "")[:80], prefix_lines=len(prefix.splitlines()))
        # a plan line (what she agreed in the talk) is not an answer: the narrator may still call on her to carry it out
        needs = [o["who"] for o in vr.accepted if o["op"] == "need" and o["who"] not in {r.get("iid") for r in reports if r.get("kind") != "plan"}]
        fixable = [r.to_dict() for r in vr.refused if r.fixable]
        # L2: deterministic rules always; the Jev audit when turn.verify.l2 = jev
        from neonrp.core import l2 as _l2

        fixable += _l2.deterministic(out.narration, reports)
        fixable += _l2.intended_move(reg, user_text, out.narration, vr.accepted)
        if not owner_checked and not (tool_ops or switch_ops):  # once per turn, on the first finished output (after any continuation)
            owner_checked = True
            fixable += _l2.owner_rule(reg, out.narration, vr.accepted)
        fixable += _mech.get(root, "post_solve")(root, reg, out.narration, turn) or []  # the template's own rules on the prose (rpg: journey overshoot)
        if str(engine_config._get_path(cfg, "turn.verify.l2", "auto")) == "jev":
            t2 = time.monotonic()
            l2_fix, l2_drop = _l2.jev_audit(root, reg, narration=out.narration, ops=[o for o in vr.accepted], reports=reports, user_text=user_text)
            if l2_drop:
                dropped = [vr.accepted[i] for i in l2_drop if i < len(vr.accepted)]
                vr.accepted = [o for i, o in enumerate(vr.accepted) if i not in set(l2_drop)]
                for o in dropped:
                    vr.refused.append(Refusal(-1, o, "world", "op", _T(lang)["ungrounded"], fixable=False))
            fixable += l2_fix
            span("verify", "l2", "jev", t2, fixed=len(l2_fix), dropped=len(l2_drop))
        # L2 rule 0 (E1 v3-sjudge T2): a present soul's spoken line must appear in the prose —
        # the narrator paraphrased 「饼买两个…」 into 「那半个问题还在原地等着」 and wrote her not taking the bread.
        for miss in _mech.get(root, "speech_rule")(root, reg, out.narration, reports) or []:
            fixable.append({"index": -1, "op": {"op": "speech", "who": miss["iid"]}, "scope": "world", "field": "narration",
                            "why": _T(lang)["missing_line"].replace("{name}", str(miss['name'])).replace("{line}", str(miss['line'])),
                            "allowed": [miss["line"]], "fixable": True})
        # a stateful layer may demand its tool every turn (combat: a round without a single [dice] is prose pretending to fight — 地穴冒烟 10-01)
        _cur_mode = _modes.read_mode(root)
        if _cur_mode:
            _mspec = _modes.spec_of(root, _cur_mode["name"]) or {}
            _need = str(_mspec.get("require_tool") or "")
            _hits = [t for t in tool_returns if str(t.get("request") or "").startswith(_need) and t.get("passed") and t.get("vs")]
            _hp_ops = [o for o in vr.accepted if o.get("op") in ("add", "set") and (str(o.get("var") or "").endswith(".hp"))]
            if _need and _hits and not _hp_ops and not any(o.get("op") == _mspec.get("exit") for o in vr.accepted):
                fixable.append({"index": -1, "op": {"op": _need}, "scope": "world", "field": "ops",
                                "why": _T(lang)["hit_no_hp"].replace("{n}", str(len(_hits))),
                                "allowed": [], "fixable": True})
            elif _need and not any(str(t.get("request") or "").startswith(_need) for t in tool_returns) and not any(o.get("op") == _mspec.get("exit") for o in vr.accepted):
                fixable.append({"index": -1, "op": {"op": _need}, "scope": "world", "field": "lines",
                                "why": str(pick_lang(_mspec.get("require_why"), lang) or _T(lang)["require_tool"].replace("{need}", _need).replace("{exit}", str(_mspec.get('exit')))),
                                "allowed": [], "fixable": True})
        # a clamped PLAYER move (two-beat travel) must show in the prose: re-propose once with the landing spot
        for o in vr.accepted:
            if o.get("op") == "move_to" and o.get("who") == "player" and o.get("_clamped"):
                fixable.append({"index": -1, "op": {"op": "move_to", "who": "player", "to": o["_clamped"]["wanted"]}, "scope": "world", "field": "to",
                                "why": _T(lang)["clamped_move"].replace("{to}", str(o['to'])).replace("{why}", str(o['_clamped']['why'])).replace("{wanted}", str(o['_clamped']['wanted'])),
                                "allowed": [o["to"]], "fixable": True})
        if narrate:  # the prose is final once shown: no prose re-proposals; checks move to the state transition (②)
            fixable = []
        cont = bool(tool_ops or switch_ops or verdict_ops)  # a continuation (request answered / layer switched) is not a re-proposal: max_loops gates re-proposals only
        if cont:
            conts += 1
            if conts > 4:
                break
        elif (loops - conts) >= max_loops + (1 if any(f.get("extra_loop") for f in fixable) else 0) or not (fixable or (needs and ask_soul)):
            break  # a rule may buy one more re-proposal (extra_loop) when it fires after the first fix pass (journey overshoot)
        if _beat.expired():  # the world's beat is over (10-14): the prose written so far is the beat; it settles below
            _beat.note("world.continue", loop=loops)
            break
        loops += 1
        if needs and ask_soul:
            t0 = time.monotonic()
            for who in needs[:2]:
                if _beat.expired():
                    _beat.note("world.need")
                    break
                try:
                    rep = ask_soul(who, out.narration[-600:])
                except Exception as exc:  # noqa: BLE001
                    rep = {"ok": False, "error": str(exc)[:200]}
                reports.append({"iid": who, "name": reg.entries.get(who, None).name if who in reg.entries else who,
                                "kind": "need", "text": rep.get("text") or rep.get("answer") or rep.get("error") or ""})
            span("parallel", "need", "llm", t0, loop=loops, souls=needs[:2])
        refusals = fixable or None
        prev = out
        # a `need` continuation keeps what was already accepted (the prose continues, the diff must too);
        # a fix pass replaces it (the model is re-proposing the offending ops).
        carry = [] if fixable else [{k: v for k, v in o.items() if not k.startswith("_")} for o in vr.accepted if o["op"] != "need"]
    if narrate and out is not None and (out.narration or "").strip():
        _beat.grant(_beat.settle_s(root), "world.settle")  # the prose is the beat; the state transition still gets its call
    if narrate and out is not None:
        # ② one clean context: the whole prose + every tool answer → <vars> / <files>; ③ the tools' rulings win; a refusal
        # sends back only ②, the prose does not change
        _tools_txt = "\n".join([f"- {t.get('request')}: {str(t.get('text') or t.get('why') or '')[:200]}" for t in tool_log if not t.get("async")]
                               + [_T(lang)["ruled_tool"].format(var=x.get("var"), delta=x.get("delta")) for x in ruled_ops or []
                                  if isinstance(x, dict) and x.get("op") == "add"]) or _T(lang)["no_tools"]
        from neonrp.core.adv import pack_ops_lines as _pack_ops_lines

        _pack_ops = _pack_ops_lines(reg, narr_lang) or _T(lang)["no_tools"]  # the rule pack's own ops: written as ops (10-19)
        _base = [o for o in verdict_keep] + [o for o in (vr.accepted if vr else []) if o.get("op") not in ("need", "options")
                                              and not any(_same_op(o, k, reg) for k in verdict_keep)]
        _fb = ""
        if describe:  # 10-10: no pseudo-code — the model says what changed and why, Jev turns it into the JSON changes
            from neonrp.core import describe_jev as _dj

            t2 = time.monotonic()
            raw2 = out.raw if inline and "<changes>" in (out.raw or "") else None
            if raw2 is None:  # A (or B when the model left them out): the description is its own call
                raw2, ms2, u2 = _chat(adapter, system, ublock + _prompts.text("describe", narr_lang, root).format(lines=out.narration[:5000], tools=_tools_txt, pack_ops=_pack_ops)
                                     + "".join("\n\n" + x for x in (narrate_lang_line(root, narr_lang),) if x))
                for k, v in u2.items():
                    if isinstance(v, (int, float)):
                        usage_total[k] = usage_total.get(k, 0) + v
                span("solve", "world.describe", "llm", t2, ms=ms2)
            _ch_text, _possible = _dj.parse(raw2)
            t3 = time.monotonic()
            if jevjson:  # line by line, our tools' JSON; the lines Jev is unsure of → the pseudo-code transition, alone
                from neonrp.core import jev_json as _jj

                j_ops, _fb_lines, j_log = _jj.to_ops(root, reg, _ch_text, out.narration)
                _o, j_opts, _ol = _dj.to_ops(root, reg, "", _possible, out.narration, prose_options=list(out.options))  # options only
                j_log["options"], j_log["option_rounds"] = j_opts, _ol.get("rounds")
                span("solve", "world.jev", "jev", t3, ops=len(j_ops), fallback_lines=len(_fb_lines))
                if _fb_lines:
                    t4 = time.monotonic()
                    raw3, ms3, u3 = _chat(adapter, system, ublock + _prompts.text("transition", narr_lang, root).format(lines="\n".join(_fb_lines), tools=_tools_txt, pack_ops=_pack_ops))
                    for k, v in u3.items():
                        if isinstance(v, (int, float)):
                            usage_total[k] = usage_total.get(k, 0) + v
                    _fb_ops = [{**o, "_from": "fallback"} for o in parse_transition(raw3)]
                    j_log["fallback"] = {"lines": _fb_lines, "raw": (raw3 or "")[:4000], "ops": _fb_ops}
                    span("solve", "world.fallback", "llm", t4, lines=len(_fb_lines), ms=ms3)
                    j_ops = j_ops + [o for o in _fb_ops if not any(_same_target(o, b, reg) for b in j_ops)]  # no doubles
            else:
                j_ops, j_opts, j_log = _dj.to_ops(root, reg, _ch_text, _possible, out.narration, prose_options=list(out.options))
                span("solve", "world.jev", "jev", t3, ops=len(j_ops), options=len(j_opts))
            _dedup: list[dict[str, Any]] = []
            for _o in j_ops:  # two lines naming the same change → one
                if not any(_same_target(_o, d, reg) for d in _dedup):
                    _dedup.append(_o)
            j_ops = _dedup
            merged = list(_base) + [o for o in j_ops if not any(_same_target(o, b, reg) for b in _base)]  # the tool's ruling wins
            vr = verify(root, merged, reg, max_ops=max_ops)
            proposals.append({"attempt": "describe", "fmt": "jevjson" if jevjson else "describe", "narration": "", "ops": j_ops, "raw": (raw2 or "")[:6000], "jev": j_log,
                              "accepted": [{k: v for k, v in o.items() if not k.startswith("_")} for o in vr.accepted],
                              "refused": [r.to_dict() for r in vr.refused], "fed_back": ""})
            out = SolveOutput(out.narration, list(vr.accepted), "describe", out.raw, options=j_opts or out.options, cot=out.cot, panels=out.panels)
        _kept: list[dict[str, Any]] = []  # what earlier attempts already got through: a refit rewrites only what was sent back
        for _attempt in range(0 if describe else 1 + max(1, max_loops)):
            if _attempt and _beat.expired():  # a refit only while the beat has time; the first transition always runs
                _beat.note("world.refit")
                break
            t2 = time.monotonic()

            _t_user = (ublock + _prompts.text("transition", narr_lang, root).format(lines=out.narration[:5000], tools=_tools_txt, pack_ops=_pack_ops) + _fb
                       + "".join("\n\n" + x for x in (narrate_lang_line(root, narr_lang),) if x))
            raw2, ms2, u2, _used = _write_down(adapter, system, _t_user, root, background=_attempt == 0, lang=narr_lang)
            for k, v in u2.items():
                if isinstance(v, (int, float)):
                    usage_total[k] = usage_total.get(k, 0) + v
            t_ops = parse_transition(raw2)
            merged = list(_base) + [o for o in t_ops if not any(_same_target(o, b, reg) for b in _base)]  # the tool's ruling wins
            vr = verify(root, merged, reg, max_ops=max_ops)
            vr, _id_log = _identity_gate(root, reg, vr, out.narration)  # names that did not settle on one entry: Jev picks (ENTITY-IDENTITY-1012)
            if _id_log:
                span("solve", "world.identity", "jev", t2, asked=len(_id_log), landed=sum(1 for x in _id_log if x["landed"]))
            if _kept:  # N2 M12 r3 t11: the refit wrote only the fix, and the first attempt's player.hp = 19 was lost
                vr.accepted = [o for o in _kept if not any(_same_target(o, n, reg) for n in vr.accepted)] + list(vr.accepted)
            fx = [r for r in vr.refused if r.fixable]
            span("solve", "world.transition", "llm", t2, attempt=_attempt, ops=len(t_ops), refused=len(vr.refused), fixable=len(fx), ms=ms2, used=_used)
            proposals.append({"attempt": f"transition{_attempt}", "fmt": "transition", "narration": "", "ops": t_ops, "raw": (raw2 or "")[:6000],
                              "accepted": [{k: v for k, v in o.items() if not k.startswith("_")} for o in vr.accepted],
                              "refused": [r.to_dict() for r in vr.refused], "fed_back": _fb,
                              **({"identity": _id_rows} if (_id_rows := [{"op": o.get("op"), **o["_identity"]} for o in vr.accepted if o.get("_identity")]) else {})})
            if not fx:
                break
            _kept = list(vr.accepted)
            _fb = (_T(lang)["refit"] + "\n".join(f"- {r.to_dict().get('why')}" for r in fx))
        if not describe:
            out = SolveOutput(out.narration, list(vr.accepted), "narrate", out.raw, options=out.options, cot=out.cot, panels=out.panels)
        # the transition wrote the player's move only now — companions follow it here too (follow-1017: the seam after
        # the prose's verify saw no move, so in narrate mode nobody ever came along)
        _judged: list[dict[str, Any]] = []
        _fops = _mech.get(root, "companions")(root, reg, list(vr.accepted), reports, talk=talk, user_text=user_text, judged=_judged) or []
        companions_judged.extend(_judged)
        if _fops:
            _fvr = verify(root, _fops, reg, max_ops=max_ops)
            vr.accepted.extend(_fvr.accepted)
            vr.refused.extend(_fvr.refused)
            out.ops = list(out.ops) + list(_fvr.accepted)
            span("verify", "companions", "python", time.monotonic(), accepted=len(_fvr.accepted), companions=_judged)
    if out is not None and not (out.narration or "").strip() and _beat.timed_out("world"):
        out.narration = str(_T(lang).get("beat_timeout") or "")  # nothing written before the beat ran out: a short line, the turn lands
    if out is not None and out.narration:  # the prose names no tier the dice did not give (``rolled``: the checks agreed in the talk)
        t5 = time.monotonic()
        out.narration, _tier_fixed = _tier_check(root, lang, out.narration, rolled, tool_log)
        if _tier_fixed:
            span("verify", "dice_tier", "python", t5, fixed=_tier_fixed)
    if "{{" in (out.narration or "") or any("{{" in str(x) for x in out.options or []):  # handles back to names (ENTITY-IDENTITY-1012)
        out.narration = reg.render_refs(out.narration)
        out.options = [reg.render_refs(x) if isinstance(x, str) else x for x in out.options]
    t0 = time.monotonic()
    accepted = [o for o in vr.accepted if o["op"] != "need"] if vr else []
    from neonrp.core import write_down_async as _wda

    _slow = _wda.SLOW.get()
    _pre = _wda.snapshot(reg) if _slow is not None else {}
    ar: ApplyResult = apply(root, accepted, reg, turn=turn, refused=vr.refused if vr else [], writers=writers,
                            narration=out.narration, player_says=user_text)
    if _slow is not None:  # the thinking write-down is still out: it corrects this state when it comes
        from neonrp.core import beat_budget as _bb_a

        _wda.SLOW.set(None)
        _wda.register(_wda.Pending(root=root, turn=turn, future=_slow, timeout=_bb_a.transition_slow_timeout_s(root),
                                   base=list(locals().get("_base") or []), fast_ops=list(accepted), pre=_pre,
                                   post=dict(ar.variables), writers=writers, max_ops=max_ops, branch=str(branch or "main"),
                                   meta=getattr(_slow, "meta", None) or {}))
    span("apply", "engine", "python", t0, applied=len(ar.applied), created=len(ar.created), repaired=len(ar.repaired), refused=len(ar.refused))
    from neonrp.core import request_ids as _rids
    from neonrp.core import system_one as _s1

    ar.request_ids = _rids.take()  # everything since the last turn: Jev plan, souls, solve, layers, referee
    if (_s1.last_call() or {}).get("fallback") == "quota" or _s1.quota_blocked():
        ar.s1_fallback = "quota"
        span("plan", "s1_fallback", "python", time.monotonic(), why="systemone quota")
    if deferred_fire:  # 10-08: drawn AFTER the write-down, so on the world as it is now (the map showed the old place)
        from neonrp.core.registry import load_registry as _lr_after

        try:
            reg_after = _lr_after(root)
        except Exception:  # noqa: BLE001
            reg_after = reg
    for k, fo in enumerate(deferred_fire):  # narrate: [~map] / [~sheet] after the write-down (and the gate's own fires)
        from neonrp.core.handlers import HandlerError

        by = fo.get("_by")
        fo = {kk: vv for kk, vv in fo.items() if kk != "_by"}
        try:
            r = _tool_watch.call(root, reg_after, fo["op"], reg_after.actions[fo["op"]].handler, fo, None, seed=f"{turn}:after:{k}", turn=turn,
                                 **({"source": by} if by else {}))
        except HandlerError as exc:
            r = {"ok": False, "why": str(exc)[:200]}
        tool_log.append({"request": fo["op"], "async": True, **({"by": by} if by else {}), **(r if isinstance(r, dict) else {"text": str(r)})})
        if isinstance(r, dict) and r.get("panel"):
            panels_acc[str(r.get("panel"))] = r.get("panel_value") or {"id": str(r.get("panel")), "format": "text", "source": "tool", "text": str(r.get("text") or "")}
    _m = _modes.read_mode(root)
    if _m:  # still inside the layer after this turn: its per-turn tick (combat: next round)
        _tick = (_modes.spec_of(root, _m["name"]) or {}).get("tick")
        if _tick:
            from neonrp.core.handlers import resolve as _resolve_tick

            _resolve_tick(str(_tick))(root)
    from neonrp.core import panels as _panels

    _final_panels = {k: (v if isinstance(v, dict) else _panels.finish(root, k, v)) for k, v in {**panels_acc, **out.panels}.items()}
    annotated = annotate(out.narration, marks_at, accepted)
    return {"understood": {k: v for k, v in understood.items() if k != "block"} if understood else {},
            "narration": out.narration, "annotated": annotated, "ops": out.ops, "options": list(out.options), "cot": out.cot, "tool_returns": tool_log, "panels": _final_panels, "verify": vr.to_dict() if vr else {}, "apply": ar, "loops": loops,
            "usage": usage_total, "spans": spans, "solve": out, "reports": reports,
            "companions": list({j.get("iid"): j for j in companions_judged}.values()), "pack_chars": len(pack_text), "proposals": proposals}
