"""O6 (the neighbour's handover, 10-06): the smallest test of an orchestration graph — a world, a stub model, scripted
input → the state sequence, the tools each node called, and which edges were walked.

    neonrp engine graph-test script.json [--json]

    {"world": "white-blank" | "<path to a world or run folder>",      # default: the engine's blank world
     "template": "<path to a .template> | <template id>",              # instead of world: built into a temp run
     "engine": {"turn": {...}},                                        # merged into the run's engine.json
     "lines": ["我四处看看", "@dm 走吧"],                                # the player's lines, in order
     "replies": ["<lines>\\n…\\n</lines>\\nnext: wait", "…"],          # model replies, in call order (host / narrate / transition)
     "soul": "<lines>\\n\"OK.\"\\n</lines>",                         # every character's answer
     "graph": {...},                                                   # a draft graph laid over the run (the editor's unsaved one)
     "defaults": {"host": "…", "narrate": "…", "transition": "…"},     # the reply for a kind once ``replies`` runs out
     "model": "real", "config": {<a run's .neonrp/config.json>},      # the player's model instead of the stub (the editor's 「真模型」)
     "root": "<a run folder>"}                                         # keep the run there and go on from it on the next call

When ``replies`` runs out each call gets a neutral default for its kind (the host waits, the prose is one line, the
transition changes nothing). The small-model judges (player gate, 「settled」) are off, so a run is deterministic.
Nothing is written outside a temp copy; no network. Inside a running engine use :func:`run_isolated` (a child process):
:func:`run` swaps module-level seams (the stub model, the judges), which a live session's turn would pick up too.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_HOST = "<lines>\n……\n</lines>\nnext: wait"
DEFAULT_PROSE = "<lines>\n(stub)\n</lines>"
DEFAULT_TRANSITION = "<vars>\n</vars>\n<files>\n</files>"
# the editor's chat test (10-17): the host writes the player's intent on the board, so 「定」 settles it like a real talk
EDITOR_HOST = "<lines>\n(stub model) The host is listening.\n</lines>\n<board>\nplayer: as just said\n</board>\nnext: wait"


class _ScriptAdapter:
    def __init__(self, replies: list[str], defaults: dict[str, str] | None = None):
        self.replies = list(replies)
        self.defaults = {"host": DEFAULT_HOST, "transition": DEFAULT_TRANSITION, "narrate": DEFAULT_PROSE, **(defaults or {})}
        self.calls: list[str] = []

    def _kind(self, messages: list[Any]) -> str:
        sys0 = str(getattr(messages[0], "content", "") or "")
        last = str(getattr(messages[-1], "content", "") or "")
        if "<vars>" in last[-1500:]:
            return "transition"
        if "next:" in sys0 and "<mic>" in sys0:
            return "host"
        return "narrate"

    def chat(self, messages: list[Any], *a: Any, **k: Any) -> Any:
        from neonrp.core.llm import LLMTurnResult, Message

        kind = self._kind(messages)
        self.calls.append(kind)
        text = self.replies.pop(0) if self.replies else self.defaults.get(kind, DEFAULT_PROSE)
        return LLMTurnResult(message=Message(role="assistant", content=text), tool_calls=None, finished=True,
                             usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


def _world(script: dict[str, Any], tmp: Path) -> Path:
    root = Path(script["root"]) if script.get("root") else tmp / "run"
    if script.get("root") and get_manifest_path_exists(root):  # a run kept from an earlier call (the editor's real-model chat)
        return root
    if script.get("template"):
        from neonrp import template as TP
        from neonrp.template import build

        tp = Path(str(script["template"])).expanduser()
        if not (tp / "template.json").is_file():  # a template id (the editor sends ids)
            hit = TP.discover().get(str(script["template"]))
            if hit is None:
                raise KeyError(f"no template {script['template']!r}")
            tp = hit
        build(tp, root)
    else:
        w = str(script.get("world") or "white-blank")
        src = Path(w) if Path(w).is_dir() else Path(__file__).resolve().parents[1] / "templates" / w
        shutil.copytree(src, root, ignore=shutil.ignore_patterns(".neonrp", "__pycache__"))
    from neonrp.core.paths import get_data_dir_name, get_manifest_path
    from neonrp.core.storage import atomic_write_json, ensure_dirs

    mp = get_manifest_path(root)
    if not mp.exists():  # a playable project, as `neonrp tui --from` makes one
        from neonrp.core.manifest import Manifest
        from neonrp.core.indexing import refresh_manifest_index

        ensure_dirs(root)
        atomic_write_json(mp, Manifest().model_dump())
        refresh_manifest_index(root, full_rebuild=True)
    if (root / "playthrough.json").exists() and not (root / ".neonrp" / "playthrough.json").exists():
        shutil.copy2(root / "playthrough.json", root / ".neonrp" / "playthrough.json")  # where read_playthrough looks
    cj = root / ".neonrp" / "config.json"
    if _real(script):  # the editor's real-model chat (10-17 ④): the run talks to the player's model, as a play run does
        cj.write_text(json.dumps(script.get("config") or {}, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        # every model call this run makes goes to the stub — a path the script does not cover gets the stub's default,
        # never the network (the provider the user configured is not read)
        conf = json.loads(cj.read_text(encoding="utf-8")) if cj.exists() else {}
        conf["llm"] = {**(conf.get("llm") or {}), "provider": "stub"}
        cj.write_text(json.dumps(conf, ensure_ascii=False, indent=1), encoding="utf-8")
    meta = root / get_data_dir_name(root) / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    ej = meta / "engine.json"
    cfg = json.loads(ej.read_text(encoding="utf-8")) if ej.exists() else {}
    if not _real(script):  # the stub runs pin the beat shape; a real-model run plays the template's own settings
        turn = {**(cfg.get("turn") or {}), "mode": "v3", "plan_loop": "on", "solve": {"structured": "narrate"}}
        turn.update(((script.get("engine") or {}).get("turn")) or {})
        cfg["turn"] = turn
        ej.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    if isinstance(script.get("graph"), dict):  # the editor's draft, as the run's override (a whole graph or a patch)
        from neonrp.core import orchestration

        op = orchestration.override_path(root)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(script["graph"], ensure_ascii=False), encoding="utf-8")
    return root


def _real(script: dict[str, Any]) -> bool:
    return str(script.get("model") or "") == "real"


def get_manifest_path_exists(root: Path) -> bool:
    from neonrp.core.paths import get_manifest_path

    return root.is_dir() and get_manifest_path(root).exists()


def run(script: dict[str, Any]) -> dict[str, Any]:
    from neonrp.core import light_chat, node_kinds, orchestration, player_gate, system_one, turn_v3
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces
    from neonrp.core.registry import load_registry

    tmp = Path(tempfile.mkdtemp(prefix="neonrp-graph-test-"))
    saved = {k: os.environ.get(k) for k in ("NEONRP_TURN_V3", "NEONRP_S1_BACKEND", "NEONRP_PLAN_LOOP", "NEONRP_SYSTEM_ONE")}
    old_factory, old_s1, old_deliver = turn_v3.ADAPTER_FACTORY, system_one.LLM_ADAPTER_FACTORY, light_chat.ask_soul_deliver
    old_lc_adapter = light_chat._adapter
    plan_mod = node_kinds.module_of("plan")  # a node-kind plugin's own small-model judge, stubbed when present
    old_gate, old_settled = player_gate.gate, getattr(plan_mod, "settled", None)
    adapter = _ScriptAdapter(list(script.get("replies") or []), {str(k): str(v) for k, v in (script.get("defaults") or {}).items()})
    soul = str(script.get("soul") or '<lines>\n"OK."\n</lines>')
    real = _real(script)
    try:
        if not real:  # a real-model run (the editor's 「真模型」) keeps every seam: it plays like a run, in a throwaway world
            os.environ.update({"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "off", "NEONRP_PLAN_LOOP": "1"})
            os.environ.pop("NEONRP_SYSTEM_ONE", None)
            turn_v3.ADAPTER_FACTORY = lambda root, provider: adapter
            system_one.LLM_ADAPTER_FACTORY = None
            light_chat.ask_soul_deliver = lambda root, iid, q, **kw: {"ok": True, "answer": soul, "name": iid}
            light_chat._adapter = lambda *a, **k: adapter  # a node plugin's own model call (the interaction scene line) → the script
            player_gate.gate = lambda *a, **k: None  # the small-model judges are off: a run is deterministic, no network
            from neonrp.core import llm_openai as _lo

            old_init = _lo.OpenAIAdapter.__init__

            def _no_network(self, *a: Any, **k: Any) -> None:  # a path the script does not cover must never reach a provider
                raise RuntimeError("graph-test: a real model adapter was requested (this path is not stubbed)")

            _lo.OpenAIAdapter.__init__ = _no_network  # type: ignore[method-assign]
            if plan_mod is not None:
                plan_mod.settled = lambda *a, **k: None
        root = _world(script, tmp)
        g = orchestration.graph(root)
        sess = ConversationSession(root, "world-agent", mode="play")
        steps: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        prev = orchestration.current(root, load_registry(root))
        record = bool(script.get("record"))
        for i, line in enumerate(script.get("lines") or []):
            k0 = len(read_turn_traces(root, sess.branch))
            before = _state(root) if record else None
            said = sess.send(str(line))
            if real and not getattr(said, "success", True):  # the player's model refused / failed: say so, do not count it
                raise RuntimeError(str(getattr(said, "error", "") or getattr(said, "assistant_message", "") or "the model call failed")[:300])
            trs = read_turn_traces(root, sess.branch)[k0:]
            nodes: list[str] = []
            tools: dict[str, list[str]] = {}
            for tr in trs:
                ap = tr.get("apply") or {}
                bt = ap.get("beat") if isinstance(ap.get("beat"), dict) else {}
                node = str(bt.get("kind") or orchestration.current(root, load_registry(root)) or "?")
                node = {"opening": orchestration.PLAN}.get(node, node)
                nodes.append(node)
                tools.setdefault(node, []).extend(str(x.get("request") or "").split(" ")[0] for x in ap.get("tool_returns") or [])
            after = orchestration.current(root, load_registry(root))
            layer = after if after not in (orchestration.PLAN, orchestration.RESOLVE) else None  # a layer the line left running
            if layer and (not nodes or nodes[-1] != layer):
                nodes.append(layer)
            chain = [prev] + nodes
            for a, b in zip(chain, chain[1:]):
                if a and b and a != b:
                    seen_pairs.add((a, b))
            steps.append({"line": line, "nodes": nodes, "reply": str(getattr(said, "assistant_message", "") or "")[:800],
                          **({"usage": dict(getattr(said, "usage", None) or {})} if real else {}), "tools": {k: [x for x in v if x] for k, v in tools.items()},
                          "advanced_by": next((((tr.get("apply") or {}).get("beat") or {}).get("advanced_by")
                                               for tr in trs[::-1] if isinstance((tr.get("apply") or {}).get("beat"), dict)), None),   # no beat record (the plain turn): nobody advanced
                          **({"digest": {"traces": [digest(tr) for tr in trs], "state": _state_delta(before, _state(root))}} if record else {})})
            prev = layer or (nodes[-1] if nodes else prev)
        # Planning → Resolve: the edge is the one its trigger names (advanced_by), not every edge between the two nodes
        fired: set[str] = set()
        for st in steps:
            by = str(st.get("advanced_by") or "")
            kind = ("event" if by.startswith("event:") else "judge" if by.startswith("judge:") else "host" if by.startswith("world:")
                    else ("dm" if "@" in str(st["line"]) else "words") if by in ("player", "soul") or by.startswith("soul:") else "")
            if kind:
                fired.add(kind)

        def _walked(e: dict[str, Any]) -> bool:
            if e.get("from") == orchestration.PLAN and e.get("to") == orchestration.RESOLVE:
                return any(k in fired for k in (e.get("on") or {}))
            return any((e.get("from") in (a, "*")) and (e.get("to") == b or e.get("to") == orchestration.RETURN) for a, b in seen_pairs)

        walked = [e["id"] for e in g.get("edges") or [] if _walked(e)]
        total = [e["id"] for e in g.get("edges") or []]
        return {"world": str(script.get("template") or script.get("world") or "white-blank"), "steps": steps,
                "edges": {"walked": walked, "not_walked": [x for x in total if x not in walked], "coverage": f"{len(walked)}/{len(total)}"},
                "model_calls": adapter.calls, "model": "real" if real else "stub"}
    finally:
        turn_v3.ADAPTER_FACTORY, system_one.LLM_ADAPTER_FACTORY, light_chat.ask_soul_deliver = old_factory, old_s1, old_deliver
        light_chat._adapter = old_lc_adapter
        player_gate.gate = old_gate
        if plan_mod is not None:
            plan_mod.settled = old_settled
        try:
            _lo.OpenAIAdapter.__init__ = old_init  # type: ignore[method-assign]
        except NameError:
            pass
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)


_CHILD = ("import json, sys\nfrom pathlib import Path\nfrom neonrp.core import graph_test as g\n"
          "res = g.run(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))\n"
          "Path(sys.argv[2]).write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')\n")


def run_isolated(script: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
    """:func:`run` in a child process (the orchestration editor's chat test, 10-17): nothing it stubs reaches the engine
    that asked. Raises RuntimeError(the child's last error line) or subprocess.TimeoutExpired."""
    with tempfile.TemporaryDirectory(prefix="neonrp-graph-test-io-") as d:
        sp, out = Path(d) / "script.json", Path(d) / "out.json"
        sp.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        p = subprocess.run([sys.executable, "-c", _CHILD, str(sp), str(out)], capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0 or not out.is_file():
            tail = [ln for ln in (p.stderr or p.stdout or "").strip().splitlines() if ln.strip()]
            raise RuntimeError((tail[-1] if tail else f"graph-test exited {p.returncode}")[:300])
        return json.loads(out.read_text(encoding="utf-8"))


# ── the golden record (10-17 第 4 批 S0): what a turn did, minus times / ids, so a refactor can be held to it ─────────

def _state(root: Path) -> dict[str, Any]:
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    return {"vars": {k: v.value for k, v in reg.variables.items()},
            "at": {e.id: e.parent for e in reg.entries.values() if getattr(e, "parent", None)}}


def _state_delta(a: dict[str, Any] | None, b: dict[str, Any]) -> dict[str, Any]:
    a = a or {"vars": {}, "at": {}}
    vs = {k: [a["vars"].get(k), v] for k, v in b["vars"].items() if a["vars"].get(k) != v and k != "turn"}
    at = {k: [a["at"].get(k), v] for k, v in b["at"].items() if a["at"].get(k) != v}
    return {"vars": dict(sorted(vs.items())), "moved": dict(sorted(at.items()))}


_SPAN_KEEP = ("loop", "fmt", "ops", "accepted", "applied", "created", "refused", "fixable", "n", "kind", "attempt")


def _op(o: Any) -> Any:
    if not isinstance(o, dict):
        return str(o)[:120]
    return {k: o[k] for k in ("op", "var", "value", "to", "who", "target", "id", "cls", "why", "field") if k in o and not isinstance(o[k], (dict, list))}


def digest(tr: dict[str, Any]) -> dict[str, Any]:
    """One turn trace, kept to what the turn did: the spans in order (phase · actor · backend and their counts), the
    beat, the plan, who acted how, the ops applied / refused, the engine's answers and the prose."""
    ap = tr.get("apply") or {}
    bt = ap.get("beat") if isinstance(ap.get("beat"), dict) else {}
    tm = tr.get("timing") or {}
    plan = tr.get("plan") or {}
    spans = []
    for sp in tr.get("spans") or []:
        row = [sp.get("phase"), sp.get("actor"), sp.get("backend")]
        extra = {k: (len(sp[k]) if isinstance(sp[k], list) else sp[k]) for k in _SPAN_KEEP if k in sp}
        spans.append(row + ([extra] if extra else []))
    return {
        "beat": {k: bt.get(k) for k in ("kind", "advanced_by") if bt.get(k) is not None} | ({"board": sorted((bt.get("board") or {}).keys())} if bt.get("board") else {})
                | ({"checks": len(bt.get("checks") or [])} if bt.get("checks") else {}),
        "spans": spans,
        "plan": {"source": plan.get("source"), "intent": (plan.get("intent") or {}).get("kind"),
                 "depth": {k: (v or {}).get("depth") for k, v in sorted((plan.get("souls") or {}).items())}} if plan else None,
        "souls": dict(sorted((tm.get("souls") or {}).items())), "variants": dict(sorted((tm.get("soul_variants") or {}).items())),
        "applied": [_op(o) for o in ap.get("applied") or []], "refused": [_op(o.get("op") if isinstance(o, dict) and isinstance(o.get("op"), dict) else o) for o in ap.get("refused") or []],
        "created": len(ap.get("created") or []),
        "tool_returns": [str(t.get("request") or "") for t in ap.get("tool_returns") or []],
        "narration": str(ap.get("narration_plain") or ""),
    }


def describe(res: dict[str, Any]) -> str:
    out = [f"world {res['world']}"]
    for i, s in enumerate(res["steps"], 1):
        tl = "; ".join(f"{k}: {', '.join(v)}" for k, v in s["tools"].items() if v)
        out.append(f"{i}. 「{s['line']}」 → {' → '.join(s['nodes']) or '—'}" + (f"  (advanced_by {s['advanced_by']})" if s.get("advanced_by") else "")
                   + (f"  tools {tl}" if tl else ""))
    e = res["edges"]
    out.append(f"edges walked {e['coverage']}: {', '.join(e['walked']) or '—'}")
    return "\n".join(out)
