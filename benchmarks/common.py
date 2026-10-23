"""Shared harness for the NeonRP / WorldLines engine benchmarks.

Everything a suite needs: arms (engine configurations as env presets), a
scaffolded world, one function that plays a turn and records everything the
engine left behind (narration, ops, soul reports with judgments, spans,
positions), the Jev grader, style metrics, and a page renderer.

Suites are scripts under ``benchmarks/suites/``; results land in
``benchmarks/runs/<suite>-<date>/`` (JSON + trace + HTML) and, when they are
worth keeping, get copied into ``docs/playrecords/``.
"""

from __future__ import annotations

import html
import json
import os
import re
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from neonrp.core import node_kinds as _node_kinds  # noqa: E402 — 10-10 R1: load the private layer (the planning beat) up front

_node_kinds.kinds()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("NEONRP_HEARTBEAT", "0")
os.environ.setdefault("NEONRP_V3_STRICT", "1")  # 10-02: a v3 crash fails the case instead of quietly running the old engine

RUNS = ROOT / "benchmarks" / "runs"
WORLD = os.environ.get("BENCH_WORLD", "stoneford-elena")
PRESET = os.environ.get("BENCH_PRESET", "deepseek")
ELENA, ROWAN = "si-elena0001", "si-rowan0001"

# ── arms: one engine configuration each; a suite runs the same script per arm ──
ARMS: dict[str, dict[str, str]] = {
    "v2b":       {"NEONRP_TURN_V3": "0", "NEONRP_S1_BACKEND": "off"},
    "v3-speak":  {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "off", "NEONRP_V3_SOLVE": "adv", "NEONRP_S1_FALLBACK_DEPTH": "speak"},
    "v3-jev":    {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_S1_FALLBACK_DEPTH": "speak"},
    "v3-sjudge": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "json_object", "NEONRP_SOUL_VARIANT": "S-judge"},
    # ── E2: the other two closed-schema soul variants (blueprint ②) ──
    "v3-sdirect": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-direct"},  # one LLM call: line + closed fields as JSON, no soul-side Jev
    "v3-sfree":   {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-free"},  # free line first, Jev classifies after
    "v3-tags":    {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "tags", "NEONRP_SOUL_VARIANT": "S-judge"},  # prose + [bracket] lines instead of JSON
    "v3-l2":      {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "json_object", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_V3_L2": "jev"},  # + Jev semantic audit (moved / answered / grounded)
    # ── 09-28: the ADV shape (抛弃 JSON) — text + <cot>/<lines>/<ops>/<options> blocks; the new default ──
    "v3-adv":     {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge"},
    "v3-plan":    {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PLAN_LOOP": "1"},  # 10-03 先商量后清算
    "v3-plan-narrate": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "narrate", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PLAN_LOOP": "1"},  # 10-04 清算 = 先叙事(工具)后状态转移
    "v3-open-pseudo": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PRIVATE": "off", "NEONRP_STATE": "pseudo"},  # 10-11 开源编排 · 状态 = 伪代码 → JSON
    "v3-open-jev":    {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PRIVATE": "off", "NEONRP_STATE": "jev"},  # 10-11 开源编排 · 状态 = 文字直出 → Jev
    "v3-plan-jevjson-inline": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PLAN_LOOP": "1", "NEONRP_V3_SOLVE": "jevjson-inline"},  # B:变化说明写在叙事那次调用的正文后面(少一次大模型调用)
    "v3-plan-jevjson-novars": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PLAN_LOOP": "1", "NEONRP_V3_SOLVE": "jevjson", "NEONRP_JEV_PARTS": "lines,fallback"},  # 消融:不要变量表
    "v3-plan-jevjson-nolines": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PLAN_LOOP": "1", "NEONRP_V3_SOLVE": "jevjson", "NEONRP_JEV_PARTS": "vars,fallback"},  # 消融:不要工具标签表
    "v3-plan-jevjson": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "jevjson", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PLAN_LOOP": "1"},  # 10-10 逐句:Jev 按注册的工具填 JSON,没把握的句子伪代码兜底
    "v3-plan-describe": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "describe", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PLAN_LOOP": "1"},  # 10-10 叙事(工具)→ 说明变化 → Jev 出 JSON(无伪代码)
    # 10-01 section markers: same engine, the output sections marked differently
    "v3-adv-div":   {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_V3_SECTIONS": "divider"},
    "v3-adv-fence": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_V3_SECTIONS": "fence"},
    "v3-adv-div-tilde": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_V3_SECTIONS": "divider",
                         "NEONRP_V3_ASYNC_MARK": "tilde"},  # 10-01: async written [~map] instead of <map>
    "v3-llmjudge": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "llm", "NEONRP_S1_LLM_PRESET": "deepseek", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge"},  # 10-01: Jev's questions answered by an LLM judge
    "v3-nojev":    {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "off", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-direct", "NEONRP_S1_FALLBACK_DEPTH": "speak"},  # 10-01: no judge at all; souls write their own fields
    "v3-adv-div-angle": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_V3_SECTIONS": "divider",
                         "NEONRP_V3_ASYNC_MARK": "angle"},  # 10-01: the default became tilde; the angle arm stays for comparison
    "v3-adv-l2":  {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_V3_L2": "jev"},
    "v3-split2":  {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "split2", "NEONRP_SOUL_VARIANT": "S-judge"},  # prose, then ops conditioned on the prose, cache-friendly prefix
    "v3-par":     {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "parallel", "NEONRP_SOUL_VARIANT": "S-judge"},  # prose ∥ ops, two concurrent calls, no reconciliation
    "v3-pj":      {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "prose_json", "NEONRP_SOUL_VARIANT": "S-judge"},  # prose first, fenced JSON ops block at the tail; lean extract if the block is missing
    # ── ablations: the full system (now ADV) minus one component each; v3-sjudge keeps json_object as the JSON reference ──
    "v3-act":    {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_S1_FALLBACK_DEPTH": "act"},  # − S-judge: soul runs the old agent loop at the depth Jev says
    "v3-noloop": {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_V3_MAX_LOOPS": "0"},  # − 环
    "v3-noadj":  {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_SOUL_ADJUDICATE": "0"},  # − 说服裁决
    "v3-lean":   {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "adv", "NEONRP_SOUL_VARIANT": "S-judge", "NEONRP_PACK_BUDGET": "2500"},  # − 词条包预算(7000 → 2500 字)
    "v3-split":  {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "jev", "NEONRP_V3_SOLVE": "split", "NEONRP_SOUL_VARIANT": "S-judge"},  # − 一起出:先叙事再抽取
}
_ARM_KEYS = ("NEONRP_TURN_V3", "NEONRP_S1_BACKEND", "NEONRP_V3_SOLVE", "NEONRP_S1_FALLBACK_DEPTH", "NEONRP_SOUL_VARIANT", "NEONRP_S1_LLM_PRESET",
             "NEONRP_V3_MAX_LOOPS", "NEONRP_SOUL_ADJUDICATE", "NEONRP_PACK_BUDGET", "NEONRP_V3_L2", "NEONRP_V3_SECTIONS", "NEONRP_V3_ASYNC_MARK")


def set_arm(arm: str) -> None:
    for k in _ARM_KEYS:
        os.environ.pop(k, None)
    for k, v in ARMS[arm].items():
        if v:
            os.environ[k] = v


def scaffold(arm: str, label: str = "") -> Path:
    from neonrp.worlds import scaffold_template_into

    root = Path(tempfile.mkdtemp(prefix=f"bench-{label or arm}-")) / arm
    scaffold_template_into(WORLD, root, model_ref=PRESET)
    return root


@dataclass
class Turn:
    id: str
    input: str
    ms: int
    ok: bool
    narration: str
    player: str
    souls: dict[str, str]
    reports: list[dict[str, Any]]
    ops: list[str]
    apply: dict[str, Any] | None
    plan: dict[str, Any] | None
    spans: list[dict[str, Any]]
    style: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, Any] = field(default_factory=dict)
    graded: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


class Game:
    """One scaffolded world + session under one arm."""

    def __init__(self, arm: str, label: str = ""):
        from neonrp.core.conversation import ConversationSession
        from neonrp.core.runtime_contract import get_startup_entry_agent

        set_arm(arm)
        self.arm = arm
        self.root = scaffold(arm, label)
        self.session = ConversationSession(root=self.root, agent_id=get_startup_entry_agent(self.root) or "world-agent", mode="play")

    def locations(self) -> tuple[str, dict[str, str]]:
        from neonrp.core.registry import load_registry

        reg = load_registry(self.root)
        return reg.player_location or "?", {e.id: (e.parent or "?") for e in reg.of_class("soul")}

    def anchor(self, iid: str) -> str | None:
        """Scene setup, not engine: put a soul beside the player before a scene
        that assumes she is there. E7 run3: Elena ran to the dock in A2a (alive!)
        and every later criterion was scored with her absent. Returns where she
        was moved from, or None if she was already here."""
        import json as _json

        from neonrp.core.registry import load_registry

        reg = load_registry(self.root)
        env = reg.entries.get(iid)
        here = reg.player_location
        if env is None or not here or env.parent == here:
            return None
        sdir = next((d for d in (self.root / "souls").iterdir() if d.name.endswith(iid)), None)
        if sdir is None:
            return None
        f = sdir / "run_state.json"
        st = _json.loads(f.read_text(encoding="utf-8"))
        was = st.get("location")
        st["location"] = here
        f.write_text(_json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(was)

    def play(self, tid: str, text: str) -> Turn:
        from neonrp.core.orchestration_trace import read_turn_traces

        set_arm(self.arm)  # graders flip the judge backend; put the arm back before every turn
        t0 = time.perf_counter()
        r = self.session.send(text)
        ms = round((time.perf_counter() - t0) * 1000)
        narr = r.assistant_message or ""
        tr = (read_turn_traces(self.root, self.session.branch, last=1) or [{}])[0]
        player, souls = self.locations()
        ap = tr.get("apply") or {}
        return Turn(id=tid, input=text, ms=ms, ok=bool(r.success), narration=narr, player=player, souls=souls,
                    reports=[{k: v for k, v in x.items() if k in ("iid", "name", "kind", "text", "judgment", "proposed_move")} for x in (ap.get("reports") or [])],
                    ops=[x.get("name") for x in (tr.get("world_agent") or {}).get("tool_calls", [])], apply=ap or None,
                    plan=tr.get("plan"), spans=tr.get("spans") or [], style=style_metrics(narr))

    def archive(self, out_dir: Path, name: str) -> None:
        import shutil
        import subprocess

        out_dir.mkdir(parents=True, exist_ok=True)
        src = self.root / ".neonrp" / "orchestration" / f"{self.session.branch}.jsonl"
        if src.exists():
            shutil.copy(src, out_dir / f"{name}.trace.jsonl")
        subprocess.run([sys.executable, "-m", "neonrp.cli", "trace", "html", str(self.root), "--out", str(out_dir / f"{name}.html"), "--title", name],
                       cwd=str(ROOT), capture_output=True)


# ── grading ──────────────────────────────────────────────────────────────────


def jev_grade(state: dict[str, Any], questions: dict[str, tuple[str, bool | None]], *, extra_choice: dict[str, tuple[str, dict[str, str]]] | None = None) -> dict[str, Any]:
    """Ask Jev yes/no questions about a narration (and optional choice questions).
    ``questions[k] = (question, expected)``; expected None = record only."""
    from neonrp.core import system_one as s1

    os.environ["NEONRP_S1_BACKEND"] = "jev"
    qs = {k: s1.noul(q) for k, (q, _e) in questions.items()}
    for k, (q, opts) in (extra_choice or {}).items():
        qs[k] = s1.choice(q, opts)
    ans = s1.ask(state, qs, timeout=15.0)
    out: dict[str, Any] = {}
    for k, (q, exp) in questions.items():
        a = ans.get(k) if ans else None
        p = round(float(a.value), 2) if a else None
        out[k] = {"q": q, "expected": exp, "p_yes": p, "pass": (None if exp is None or p is None else ((p >= 0.5) == exp))}
    for k in (extra_choice or {}):
        a = ans.get(k) if ans else None
        out[k] = {"value": (str(a.value) if a else None), "conf": (round(float(a.confidence), 2) if a else None)}
    return out


STYLE_CHOICE = ("这段叙事的文字状态", {"cluttered": "过于复杂 / 凌乱", "fine": "恰当", "terse": "过于简洁 / 干瘪"})
VOICE_QUESTIONS = {
    "readable": ("这段文字容易读吗(句子不绕、不堆砌、信息顺序清楚)?", True),
    "human_voice": ("角色说话的方式像一个真实的人,而不是旁白、说明书或客服吗?", True),
}


def style_metrics(narr: str) -> dict[str, Any]:
    sents = [s for s in re.split(r"[。!?！？]\s*", narr) if s.strip()]
    quotes = re.findall(r"[「“][^」”]{1,200}[」”]", narr)
    return {"chars": len(narr), "sentences": len(sents), "avg_sentence": round(len(narr) / max(1, len(sents)), 1),
            "dialogue_ratio": round(sum(len(q) for q in quotes) / max(1, len(narr)), 2), "paragraphs": narr.count("\n\n") + 1}


# ── results ──────────────────────────────────────────────────────────────────


def run_dir(suite: str) -> Path:
    d = RUNS / f"{suite}-{date.today().isoformat()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(suite: str, data: dict[str, Any], name: str = "out.json") -> Path:
    d = run_dir(suite)
    (d / name).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=lambda o: o.to_dict() if hasattr(o, "to_dict") else str(o)), encoding="utf-8")
    return d / name


def pass_rate(turns: list[dict[str, Any]], key: str = "graded") -> tuple[int, int]:
    ok = tot = 0
    for t in turns:
        for k, v in (t.get(key) or {}).items():
            if isinstance(v, dict) and v.get("pass") is not None:
                tot += 1
                ok += int(bool(v["pass"]))
    return ok, tot


def esc(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


CSS = """
:root{--bg:#F4F2EC;--paper:#fff;--ink:#22211E;--ink2:#5B5850;--ink3:#8A867C;--line:#DDD9D0;--eng:#2F6B8F;--jev:#6C3FA6;--ok:#2E7D4F;--bad:#B8383D;--ok-bg:#DDF0E4;--bad-bg:#F7DEDF;--warn:#B7791F;--warn-bg:#FBEFD6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141312;--paper:#1C1B19;--ink:#ECE9E1;--ink2:#B5B0A4;--ink3:#847F73;--line:#2E2C28;--eng:#7FB2D6;--jev:#B590E6;--ok:#5CC68A;--bad:#F07A7E;--ok-bg:#12321F;--bad-bg:#3E1A1C;--warn:#E0A33A;--warn-bg:#3A2A10}}
:root[data-theme=dark]{--bg:#141312;--paper:#1C1B19;--ink:#ECE9E1;--ink2:#B5B0A4;--ink3:#847F73;--line:#2E2C28;--eng:#7FB2D6;--jev:#B590E6;--ok:#5CC68A;--bad:#F07A7E;--ok-bg:#12321F;--bad-bg:#3E1A1C;--warn:#E0A33A;--warn-bg:#3A2A10}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 "Noto Sans SC","PingFang SC",system-ui,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:36px 22px 90px}h1{font-family:"Noto Serif SC","Songti SC",serif;font-size:28px;margin:0 0 6px}h2{font-family:"Noto Serif SC",serif;font-size:20px;margin:44px 0 6px;padding-top:14px;border-top:1px solid var(--line)}h3{font-size:15px;margin:18px 0 4px}
.eyebrow{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink3)}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px}.dim{color:var(--ink3)}
.turn{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:12px 16px;margin:10px 0 14px}
.narr{white-space:pre-wrap;font-size:14px;line-height:1.75;margin:8px 0;padding-left:10px;border-left:3px solid var(--line)}
.row{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--ink2);margin:3px 0}.row b{color:var(--ink)}
.soul{color:var(--jev)}.ops{color:var(--eng)}
.p{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:11px;padding:0 6px;border-radius:3px;margin:0 4px 2px 0}.p.ok{background:var(--ok-bg);color:var(--ok)}.p.bad{background:var(--bad-bg);color:var(--bad)}.p.warn{background:var(--warn-bg);color:var(--warn)}.p.na{border:1px solid var(--line);color:var(--ink3)}
table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--ink3);text-transform:uppercase}td.n{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}
.note{border-left:3px solid var(--eng);background:rgba(47,107,143,.08);padding:10px 14px;margin:14px 0;font-size:14px}
"""


def render_turns(turns: list[dict[str, Any]], *, group_of: Callable[[str], str] | None = None, groups: dict[str, str] | None = None) -> str:
    H: list[str] = []
    last = None
    for x in turns:
        g = group_of(x["id"]) if group_of else None
        if g and g != last:
            H.append(f"<h3>{esc(g)} · {esc((groups or {}).get(g, ''))}</h3>")
            last = g
        H.append(f"<div class='turn'><div class='row'><b>{esc(x['id'])}</b> {x['ms']/1000:.1f}s · 玩家:{esc(x['input'])}</div>")
        pl = x.get("plan") or {}
        if pl:
            el = [(k.split('-')[-1][:8], v.get("depth"), round(v.get("reacts", 0), 2)) for k, v in (pl.get("souls") or {}).items() if v.get("present")]
            H.append(f"<div class='row'><b>① 预判</b> {esc(pl.get('source'))} intent={esc((pl.get('intent') or {}).get('kind'))} {esc(el)}</div>")
        for rp in x.get("reports") or []:
            j = rp.get("judgment") or {}
            tag = (f" 态度={j.get('attitude')} 语气={j.get('register')}" if j.get("attitude") else "") + (f" 拟去 {rp.get('proposed_move')}" if rp.get("proposed_move") else "")
            dd = j.get("decision") or {}
            if dd.get("outcome"):
                tag += f" · 裁决 {dd.get('stakes')} 意愿 {dd.get('willingness')}" + (f" 骰 {dd.get('roll')}/{dd.get('target')} {dd.get('tier')}" if dd.get("roll") is not None else "") + f" → {dd.get('outcome')}"
            H.append(f"<div class='row soul'><b>② {esc(rp.get('name'))}</b> [{esc(rp.get('kind'))}{esc(tag)}] {esc(rp.get('text'))}</div>")
            ans = j.get("answers") or {}
            if ans:
                H.append("<div class='row dim'>　判断链(Jev 原始答案 值/置信):" + esc(" · ".join(f"{k}={v.get('v')}/{v.get('c')}" for k, v in ans.items())) + "</div>")
            for r_ in (dd.get("reasons") or []):
                H.append(f"<div class='row dim'>　为什么:{esc(r_)}</div>")
        # ③→④ intermediate outputs: every solve attempt, what verify refused, what was fed back
        props = (x.get("apply") or {}).get("proposals") or []
        for pr in props:
            fed = pr.get("fed_back") or []
            H.append(f"<div class='row'><b>③ 第 {pr.get('attempt', 0) + 1} 次直出</b> fmt={esc(pr.get('fmt'))} ops={esc([o.get('op') + ' ' + str(o.get('who') or o.get('var') or o.get('name') or o.get('key') or '') + ('→' + str(o.get('to')) if o.get('to') else '') for o in pr.get('ops') or []])}"
                     + (f"<br>　回灌给它的拒绝:{esc([f['field'] + ':' + f['why'][:80] for f in fed])}" if fed else "") + "</div>")
            if len(props) > 1 or pr.get("refused"):
                H.append(f"<div class='narr' style='border-left-color:var(--jev)'>{esc(pr.get('narration'))}</div>")
            if pr.get("refused"):
                H.append("<div class='row'><b>④ 拒绝</b> " + "".join(f"<span class='p bad'>{esc(r_['field'])}: {esc(r_['why'][:90])}</span>" for r_ in pr["refused"]) + "</div>")
        if not (len(props) > 1 or (props and props[0].get("refused"))):
            H.append(f"<div class='narr'>{esc(x['narration'])}</div>")
        else:
            H.append(f"<div class='row'><b>最终叙事</b></div><div class='narr'>{esc(x['narration'])}</div>")
        sl = ", ".join(f"{k.split('-')[-1][:8]}@{v}" for k, v in (x.get("souls") or {}).items())
        checks = "".join(f"<span class='p {'ok' if c.get('pass') else 'bad'}'>{esc(k)}: {esc(c.get('got', ''))}</span>" for k, c in (x.get("checks") or {}).items())
        H.append(f"<div class='row ops'><b>⑤ ops</b> {esc(', '.join(x.get('ops') or [])) or '(无)'} · 玩家@{esc(x.get('player'))} · {esc(sl)}<br>{checks}</div>")
        gr = (x.get("graded") or {})
        gp = "".join(f"<span class='p {('na' if v.get('pass') is None else ('ok' if v.get('pass') else 'bad'))}'>{esc(k)} p={v.get('p_yes')}</span>" if "p_yes" in v else f"<span class='p na'>{esc(k)}={esc(v.get('value'))}</span>" for k, v in gr.items() if isinstance(v, dict))
        st = x.get("style") or {}
        H.append(f"<div class='row soul'><b>Jev 评分</b> {gp} <span class='dim'>{st.get('chars')} 字 · {st.get('sentences')} 句 · 对白 {int((st.get('dialogue_ratio') or 0)*100)}%</span></div></div>")
    return "\n".join(H)


def page(title: str, eyebrow: str, intro_html: str, body_html: str) -> str:
    return f"<title>{esc(title)}</title><style>{CSS}</style><div class='wrap'><div class='eyebrow'>{esc(eyebrow)}</div><h1>{esc(title)}</h1>{intro_html}{body_html}</div>"


def loop_stats(turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Did feeding the failure back fix it? Per turn with ≥2 attempts: whether the last
    attempt has no refusals, and the extra time the loop cost."""
    looped = fixed = 0
    extra_ms: list[float] = []
    for t in turns:
        props = (t.get("apply") or {}).get("proposals") or []
        if len(props) < 2:
            continue
        looped += 1
        if not props[-1].get("refused"):
            fixed += 1
        solves = [s for s in (t.get("spans") or []) if s.get("phase") == "solve" and s.get("loop")]
        extra_ms.extend(float(s["t1"]) - float(s["t0"]) for s in solves)
    return {"turns": len(turns), "looped": looped, "fixed_on_retry": fixed,
            "extra_s_median": (round(statistics.median(extra_ms) / 1000, 1) if extra_ms else 0.0)}


def median_ms(turns: list[dict[str, Any]]) -> float:
    return statistics.median(t["ms"] for t in turns) / 1000 if turns else 0.0
