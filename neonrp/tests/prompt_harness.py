"""Render the prompts of the main play path offline (stub LLM) — the zh snapshot guard and the four-language checks.

``render_all(tmp_path, lang)`` installs stoneford-elena, sets the run's language, drives each prompt builder with a fake
model and returns ``{name: text}`` of everything the model would have been sent.
"""
from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

_TPL = Path(__file__).resolve().parents[1] / "src" / "neonrp" / "templates" / "stoneford-elena"


def install(tmp_path: Path, lang: str | None) -> Path:
    root = tmp_path / f"w-{lang or 'default'}"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    if lang:
        rs = root / "game" / "meta" / "run_state.json"
        d = json.loads(rs.read_text(encoding="utf-8")) if rs.exists() else {}
        d["output_lang"] = lang
        rs.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


@contextmanager
def _env(**kv: str) -> Iterator[None]:
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update(kv)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _Fake:
    def __init__(self, outputs: list[str]):
        self.outputs, self.calls = list(outputs), []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        text = self.outputs.pop(0) if self.outputs else "<lines>\n…\n</lines>"
        return SimpleNamespace(message=SimpleNamespace(content=text), usage={"prompt_tokens": 1, "completion_tokens": 1})


def render_all(tmp_path: Path, lang: str | None) -> dict[str, str]:
    from neonrp.core import light_chat, plan_loop, player_gate, sdk, turn_v3
    from neonrp.core import system_one as s1
    from neonrp.core.registry import load_registry

    out: dict[str, str] = {}
    root = install(tmp_path, lang)
    gate_on = player_gate._enabled
    player_gate._enabled = lambda root_: False  # no real judge model anywhere but the gate section below
    try:
        return _render(root, out, gate_on)
    finally:
        player_gate._enabled = gate_on


def _render(root: Path, out: dict[str, str], gate_on: Any) -> dict[str, str]:
    from neonrp.core import light_chat, plan_loop, player_gate, sdk, turn_v3
    from neonrp.core import system_one as s1
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.parent == reg.player_location)

    # ── plan loop: two host rounds (one hands her the mic), her question, then the resolve brief's exec question ──
    hosts = iter([f"<lines>\nx\n</lines>\n[read 杂货铺]\n<mic>\n{elena.name}: x?\n</mic>\n<board>\n玩家: x\n</board>\nnext: wait",
                  "<lines>\ny\n</lines>\nnext: wait"])
    seen_host: list[tuple[str, str]] = []
    asked: list[tuple[str, dict]] = []
    orig_host, orig_ask = plan_loop._host, light_chat.ask_soul_deliver
    plan_loop._host = lambda root_, system, user: (seen_host.append((system, user)), next(hosts))[1]
    light_chat.ask_soul_deliver = lambda root_, iid, q, **kw: (asked.append((q, kw.get("beat") or {})),
                                                                {"ok": True, "answer": "<lines>\n「x」\n</lines>\n<draft>x</draft>"})[1]
    try:
        with _env(NEONRP_S1_BACKEND="off"):
            res = plan_loop.step(root, user_text="我去杂货铺买药,顺便把罩灯卖了。", last_narration="")
    finally:
        plan_loop._host, light_chat.ask_soul_deliver = orig_host, orig_ask
    for i, (sysm, user) in enumerate(seen_host):
        out[f"plan.host{i}.system"], out[f"plan.host{i}.user"] = sysm, user
    for i, (q, beat) in enumerate(asked):
        out[f"plan.soul{i}.question"], out[f"plan.soul{i}.beat"] = q, json.dumps(beat, ensure_ascii=False)
    out["plan.reply"] = str(res.get("narration") or "")
    fake_out = {"board": {elena.name: "x", "玩家": "y"}, "rolled": [{"line": f"[{elena.name} CHA: 10+2=12 >= 12] → x", "a": {"who": elena.id}}]}
    q, beat = plan_loop.exec_question(reg, elena.id, fake_out, "scene so far")
    out["plan.exec.question"], out["plan.exec.beat"] = q, json.dumps(beat, ensure_ascii=False)
    out["plan.resolve_facts"] = plan_loop.resolve_facts({"board": {"玩家": "y"}, "checks": [], "rolled": [], "talk": []}, root)

    # ── resolve, narrate mode: the prose call and the transition call ──
    a = _Fake(["<lines>\nx\n</lines>", "<vars>\n</vars>\n<files>\n</files>"])
    turn_v3.ADAPTER_FACTORY = lambda root_, provider: a
    try:
        with _env(NEONRP_V3_SOLVE="narrate", NEONRP_S1_BACKEND="off"):
            turn_v3.solve_turn(root, user_text="买药", provider=None, turn=1,
                               soul_reports=[{"iid": elena.id, "name": elena.name, "kind": "speak", "text": "「x」"}])
        for i, msgs in enumerate(a.calls):
            out[f"narrate.call{i}.system"], out[f"narrate.call{i}.user"] = msgs[0].content, msgs[1].content
        b = _Fake(['<lines>\nx\n</lines>\n<ops>\n</ops>\n<options>\nx\n</options>'])
        turn_v3.ADAPTER_FACTORY = lambda root_, provider: b
        with _env(NEONRP_V3_SOLVE="adv", NEONRP_S1_BACKEND="off"):  # the one-call shape, pinned (the default is the graph's pseudo, 10-11)
            turn_v3.solve_turn(root, user_text="买药", provider=None, turn=2, soul_reports=[])
        out["adv.system"], out["adv.user"] = b.calls[0][0].content, b.calls[0][1].content
    finally:
        turn_v3.ADAPTER_FACTORY = None

    # ── light chat: direct (face to face / remote), room (three stances), a question delivered to her ──
    sd = next((root / "souls").glob(f"*-{elena.id}"))
    for remote in (False, True):
        msgs = light_chat.build_chat_messages(root, elena.id, sd, elena.name, "x", remote=remote)
        out[f"chat.direct{'.remote' if remote else ''}"] = "\n---\n".join(m.content for m in msgs)
    for stance in ("primary", "jumpin", "open"):
        msgs = light_chat._room_messages(root, sd, elena.name, ["A", elena.name], "x", [("A", "y")], stance)
        out[f"chat.room.{stance}"] = "\n---\n".join(m.content for m in msgs)
    seen_sys: dict[str, str] = {}
    orig_ad = light_chat._adapter
    light_chat._adapter = lambda root_: SimpleNamespace(chat=lambda msgs: (seen_sys.setdefault("m", "\n---\n".join(m.content for m in msgs)),
                                                                        SimpleNamespace(message=SimpleNamespace(content="「x」")))[1])
    try:
        light_chat.ask_soul_deliver(root, elena.id, "x?", beat={"event": "x"})
    finally:
        light_chat._adapter = orig_ad
    out["chat.deliver"] = seen_sys.get("m", "")

    # ── the pack's mode layers (whole system prompts) ──
    from neonrp.core import modes
    from neonrp.core.output_lang import prompt_lang

    for name in ("referee", "combat", "dungeon"):
        out[f"layer.{name}"] = modes.layer_system(root, reg, name, prompt_lang(root))
    # the same layers from the engine's own pack prompts (this world ships its own agents/*/system.md, zh only — world data)
    agents = root / "agents"
    if agents.is_dir():
        agents.rename(root / "agents.off")
        try:
            for name in ("referee", "combat", "dungeon"):
                out[f"layer_pack.{name}"] = modes.layer_system(root, reg, name, prompt_lang(root))
        finally:
            (root / "agents.off").rename(agents)

    # ── a character's own step (rpg soul_step): the judge's questions, the baked judgment, the direct / free asks ──
    from neonrp.packs.rpg import soul_step as ss

    exits = {"T001/inn": "inn", "T001/dock": "dock"}
    try:
        qs = ss.questions_for(elena.name, exits, lang=prompt_lang(root))
    except TypeError:  # before the strings left the code
        qs = ss.questions_for(elena.name, exits)
    out["soul.questions"] = json.dumps({k: [q.instructions, q.criteria] for k, q in qs.items()}, ensure_ascii=False)
    j = ss.SoulJudgment(elena.id, elena.name, "refuse", "cold", 2, True, "T001/inn", 0.0, "x", 0.9, 0.0,
                        decision={"stakes": "heavy", "outcome": "partial"}, confides=0.7)
    try:
        out["soul.baked"] = j.baked(prompt_lang(root))
    except TypeError:
        out["soul.baked"] = j.baked()
    from neonrp.core import soul_view as _sv

    situation = "x\n\ny\n\n" + (_sv.own_mark(root) if hasattr(_sv, "own_mark") else _sv.OWN_MARK) + "\nz"
    asked_ss: list[str] = []
    orig_ask2 = light_chat.ask_soul_deliver
    light_chat.ask_soul_deliver = lambda root_, iid, q, **kw: (asked_ss.append(q), {"ok": True, "answer": "「x」"})[1]
    try:
        ss._soul_step_direct(root, elena.id, situation=situation, depth="speak", provider=None, mode="play", registry=reg)
    finally:
        light_chat.ask_soul_deliver = orig_ask2
    out["soul.direct"] = asked_ss[0] if asked_ss else ""
    out["soul.gesture"] = ss._escalate_or_gesture(root, elena.id, j, situation=situation, depth="gesture", provider=None, mode="play")["text"]

    # ── the world pack the narrator reads ──
    out["sdk.pack"] = sdk.render_pack(sdk.pack(root))

    # ── the player gate ──
    g = _Fake(['{"intent": "x", "named": [], "claims": []}'])
    orig_f = s1.LLM_ADAPTER_FACTORY
    s1.LLM_ADAPTER_FACTORY = lambda: g
    orig_llm = s1._llm_adapter
    s1._llm_adapter = lambda: g
    player_gate._enabled = lambda root_: True
    try:
        player_gate.gate(root, reg, "我去杂货铺。")
    finally:
        s1.LLM_ADAPTER_FACTORY, s1._llm_adapter = orig_f, orig_llm
        player_gate._enabled = lambda root_: False
    if g.calls:
        out["gate.system"], out["gate.user"] = g.calls[0][0].content, g.calls[0][1].content
    return out


def cjk_share(text: str) -> float:
    """Share of Han characters among letters — the skeleton's language, roughly (kana / hangul counted apart)."""
    han = sum(1 for c in text if "一" <= c <= "鿿")
    letters = sum(1 for c in text if c.isalpha())
    return han / letters if letters else 0.0


def script_share(text: str, script: str) -> float:
    ranges = {"kana": ("぀", "ヿ"), "hangul": ("가", "힯"), "latin": ("A", "z")}
    lo, hi = ranges[script]
    hit = sum(1 for c in text if lo <= c <= hi)
    letters = sum(1 for c in text if c.isalpha())
    return hit / letters if letters else 0.0


def dump(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
