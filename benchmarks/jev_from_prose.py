"""Offline check: can Jev read the narration itself and judge the CLOSED changes — no second model call?

    uv run python benchmarks/jev_from_prose.py --labels release-1007-c2 release-1010-c2 --name jev-prose-1010

Per resolve beat of a recorded pseudo-code run: the prose (``apply.narration_plain``), the world before the beat
(the landed variables with the changed ones put back to their ``from``), and the pseudo-code's landed changes as the
reference answer. One Jev request per beat, written questions, candidates from the world:

  player move   — moved? / to which known place
  soul move     — for each character present: moved? / to which known place
  numbers       — for each player / present character number: changed? / to what (numbers in the prose — CJK numerals
                  too — and before ± them)
  clock         — moved on? / to which time (before + 5 … 240 min, and times written in the prose)
  status gained — for each status in the table: did someone get it? / who

Precision and recall per class against the reference, Jev time per beat, and how much of the reference is closed at all.
Writes docs/playrecords/<name>.md / .json.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

OUT = Path("docs/playrecords")
_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "半": 0.5}


def _cn_num(s: str) -> list[float]:
    out: list[float] = [float(x) for x in re.findall(r"(?<![\d.])\d+(?:\.\d+)?", s)]
    for m in re.finditer(r"[一二两三四五六七八九十]{1,3}(?=[枚个金银铜点刻分钟天次瓶])", s):
        t = m.group(0)
        if t == "十":
            out.append(10.0)
        elif t.startswith("十"):
            out.append(10.0 + _CN.get(t[1:], 0))
        elif "十" in t:
            a, _, b = t.partition("十")
            out.append(_CN.get(a, 1) * 10.0 + (_CN.get(b, 0) if b else 0))
        else:
            out.append(float(_CN.get(t, 0)))
    return sorted(set(x for x in out if x > 0))


def _hm(t: str) -> int:
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


def _fmt(m: int) -> str:
    m %= 24 * 60
    return f"{m // 60:02d}:{m % 60:02d}"


def _world():
    from test_engine_v3 import _install

    from neonrp.core import effect_rules
    from neonrp.core.registry import load_registry

    root = _install(Path(tempfile.mkdtemp()))
    reg = load_registry(root)
    places = {}
    for e in list(reg.of_class("place")) + list(reg.of_class("town")):
        if e.name:
            places[f"{e.name} ({e.id})"] = str(e.id)
    souls = {str(e.id): str(e.name) for e in reg.of_class("soul")}
    return root, places, souls, list(effect_rules.table(root))


def _node(x: Any) -> str:
    return str(x or "").split("/")[-1]


_SOULS: dict[str, str] = {}  # iid → name (filled by main from the world)


def beats(label: str) -> list[dict[str, Any]]:
    out = []
    for f in sorted(glob.glob(str(OUT / f"plan-loop-{label}" / "traces" / "*.jsonl"))):
        for ln in Path(f).read_text(encoding="utf-8").splitlines():
            try:
                t = json.loads(ln)
            except ValueError:
                continue
            ap = t.get("apply") or {}
            if (ap.get("beat") or {}).get("kind") != "resolve" or not ap.get("narration_plain"):
                continue
            after = dict(ap.get("variables") or {})
            before = dict(after)
            for o in ap.get("applied") or []:
                if isinstance(o, dict) and o.get("op") in ("set", "add") and "from" in o:
                    before[o["var"]] = o["from"]
            present = [s.get("instance_id") for s in t.get("souls") or [] if s.get("instance_id")]  # every character the beat lists
            named = {iid for iid in present if _SOULS.get(iid) and _SOULS[iid] in ap["narration_plain"]}  # … that this prose names
            out.append({"case": Path(f).stem, "prose": ap["narration_plain"], "before": before, "applied": [o for o in ap.get("applied") or [] if isinstance(o, dict)],
                        "player_at": str(t.get("world_location") or ""), "present": [i for i in present if i in named]})
    return out


def judge(b: dict[str, Any], W: tuple) -> tuple[dict[str, list], float, int]:
    """One Jev request → the closed changes it finds (by class)."""
    from neonrp.core import system_one as s1

    root, places, souls, statuses = W
    none = "都不是"
    before = b["before"]
    nums = _cn_num(b["prose"])
    numeric = {k: v for k, v in before.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
               and (k.startswith("player.") or any(k.startswith(f"char.{iid}.") for iid in b["present"]))}
    clock = before.get("time.clock")
    state = {"story": b["prose"][-3000:], "world": {"player_at_before": b["player_at"], "present": [souls.get(i, i) for i in b["present"]],
                                                  "values_before": numeric, "time_before": clock}}
    Q: dict[str, Any] = {}
    cand: dict[str, dict[str, str]] = {}

    def ch(key: str, instr: str, opts: dict[str, str]) -> None:
        cand[key] = dict(list(opts.items())[:200])
        Q[key] = s1.choice(instr, {**cand[key], "none": none})

    pl = {f"p{i}": k for i, k in enumerate(places)}
    Q["pm"] = s1.noul("`story` 里,玩家这一拍结束时是不是已经身在另一个地方(和 `world.player_at_before` 不同)?")
    ch("pm_to", "`story` 里,玩家这一拍结束时身在哪个地方?", pl)
    for j, iid in enumerate(b["present"]):
        nm = souls.get(iid, iid)
        Q[f"sm{j}"] = s1.noul(f"`story` 里,{nm} 这一拍结束时是不是已经身在另一个地方(和开始时不同)?")
        ch(f"sm{j}_to", f"`story` 里,{nm} 这一拍结束时身在哪个地方?", pl)
    for j, (k, v) in enumerate(numeric.items()):
        Q[f"n{j}"] = s1.noul(f"按 `story`,数值 {k}(这一拍开始时是 {v})这一拍变了吗?")
        opts = {}
        for n in nums:
            for val in (n, v + n, v - n):
                if val >= 0 and val != v:
                    opts.setdefault(f"{val:g}", f"{val:g}")
        if opts:
            ch(f"n{j}_to", f"按 `story`,数值 {k}(这一拍开始时是 {v})现在是多少?", opts)
    if clock:  # how long the beat took — a judgment of elapsed time (the prose rarely states the minute)
        dur = {"d2": "两三分钟", "d5": "约 5 分钟", "d10": "约 10 分钟", "d15": "一刻钟", "d30": "半小时", "d45": "约 45 分钟",
               "d60": "约 1 小时", "d90": "一个半小时", "d120": "约 2 小时", "d180": "约 3 小时", "d240": "4 小时以上"}
        cand["tc_to"] = dur
        Q["tc_to"] = s1.choice(f"按 `story`,这一拍从开始到结束大约过了多久(开始时是 {clock})?", dur)
    people = {"玩家": "player", **{souls.get(i, i): i for i in b["present"]}}
    for j, st in enumerate(statuses):
        Q[f"st{j}"] = s1.noul(f"`story` 里,这一拍有没有人身上出现了「{st}」这种状态?")
        ch(f"st{j}_who", f"`story` 里,是谁出现了「{st}」?", {f"w{i}": n for i, n in enumerate(people)})
    t0 = time.monotonic()
    A = s1.ask(state, Q) or {}
    ms = (time.monotonic() - t0) * 1000

    def yes(k: str) -> bool:
        try:
            return float(getattr(A.get(k), "value", 0) or 0) >= 0.6
        except (TypeError, ValueError):
            return False

    def pick(k: str) -> str | None:
        v = getattr(A.get(k), "value", None)
        return None if v in (None, "none") else cand.get(k, {}).get(v)

    got: dict[str, list] = {"player_move": [], "soul_move": [], "number": [], "clock": [], "status": []}
    if yes("pm") and pick("pm_to"):
        got["player_move"].append(places[pick("pm_to")])
    for j, iid in enumerate(b["present"]):
        if yes(f"sm{j}") and pick(f"sm{j}_to"):
            got["soul_move"].append((iid, places[pick(f"sm{j}_to")]))
    for j, k in enumerate(numeric):
        if yes(f"n{j}") and pick(f"n{j}_to") is not None:
            got["number"].append((k, float(pick(f"n{j}_to"))))
    dv = getattr(A.get("tc_to"), "value", None)
    if clock and isinstance(dv, str) and dv.startswith("d"):
        got["clock"].append(_fmt(_hm(clock) + int(dv[1:])))
    for j, st in enumerate(statuses):
        p_ = float(getattr(A.get(f"st{j}"), "value", 0) or 0)
        if p_ >= 0.6 and pick(f"st{j}_who"):
            got["status"].append((people[pick(f"st{j}_who")], st))
            if p_ >= 0.8:
                got.setdefault("status@0.8", []).append((people[pick(f"st{j}_who")], st))
    return got, ms, len(Q)


def reference(b: dict[str, Any]) -> tuple[dict[str, list], int, int]:
    ref: dict[str, list] = {"player_move": [], "soul_move": [], "number": [], "clock": [], "status": []}
    closed = total = 0
    for o in b["applied"]:
        if str(o.get("source") or o.get("_from") or o.get("by") or "").startswith("tick"):  # the engine's own ticks: not read from the prose
            continue
        total += 1
        op = o.get("op")
        if op == "move_to" and o.get("who") == "player":
            ref["player_move"].append(str(o.get("to")))
        elif op == "move_to":
            if str(o.get("who")) not in b["present"]:  # a character the prose does not name moved on its own turn elsewhere
                continue
            ref["soul_move"].append((str(o.get("who")), str(o.get("to"))))
        elif op in ("set", "add") and o.get("var") == "time.clock":
            ref["clock"].append(str(o.get("to")))
        elif op in ("set", "add") and isinstance(o.get("to"), (int, float)) and str(o.get("var", "")).startswith(("player.", "char.")):
            ref["number"].append((o["var"], float(o["to"])))
        elif op == "new" and o.get("class") == "status":
            ref["status"].append((str((o.get("props") or {}).get("on") or o.get("who") or "player"), str(o.get("name"))))
        else:
            continue
        closed += 1
    return ref, closed, total


def _match(cls: str, a: Any, r: Any) -> bool:
    if cls == "player_move":
        return _node(a) == _node(r)
    if cls == "soul_move":
        return a[0] == r[0] and _node(a[1]) == _node(r[1])
    if cls.startswith("status"):
        return a == r
    if cls == "number":
        return a[0] == r[0] and abs(a[1] - r[1]) < 1e-6
    if cls == "clock":
        return abs(_hm(a) - _hm(r)) <= max(10, 0.3 * abs(_hm(r) - _hm(a)))  # elapsed time: within 10 min or 30 %
    return a == r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    W = _world()
    _SOULS.update(W[2])
    stats = {c: {"tp": 0, "fp": 0, "fn": 0} for c in ("player_move", "soul_move", "number", "clock", "status", "status@0.8")}
    times: list[float] = []
    closed = total = nq = 0
    rows = []
    for lab in a.labels:
        for b in beats(lab):
            got, ms, n = judge(b, W)
            ref, c, t = reference(b)
            closed += c
            total += t
            nq += n
            times.append(ms)
            ref["status@0.8"] = list(ref["status"])
            got.setdefault("status@0.8", [])
            for cls in stats:
                left = list(ref[cls])
                for g in got[cls]:
                    hit = next((r for r in left if _match(cls, g, r)), None)
                    if hit is not None:
                        stats[cls]["tp"] += 1
                        left.remove(hit)
                    else:
                        stats[cls]["fp"] += 1
                stats[cls]["fn"] += len(left)
            rows.append({"run": lab, "case": b["case"], "got": got, "ref": ref, "ms": round(ms)})
    res = {"beats": len(times), "jev_ms_median": round(statistics.median(times)) if times else 0, "questions_mean": round(nq / max(len(times), 1)),
           "closed_share_of_reference": round(closed / max(total, 1), 2), "by_class": {}}
    md = [f"Jev 读叙事正文判封闭类变化 · {len(times)} 个清算拍 · Jev 每拍中位 {res['jev_ms_median']} ms(平均 {res['questions_mean']} 题)",
          f"伪代码落账里封闭类占 {closed}/{total} = {res['closed_share_of_reference']:.0%}", "",
          "| 类 | 准确率 | 召回率 | 对 | 多出 | 漏掉 |", "|---|---|---|---|---|---|"]
    for cls, s in stats.items():
        p = s["tp"] / max(s["tp"] + s["fp"], 1)
        r = s["tp"] / max(s["tp"] + s["fn"], 1)
        res["by_class"][cls] = {**s, "precision": round(p, 2), "recall": round(r, 2)}
        md.append(f"| {cls} | {p:.0%} | {r:.0%} | {s['tp']} | {s['fp']} | {s['fn']} |")
    (OUT / f"{a.name}.json").write_text(json.dumps({"summary": res, "beats": rows}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (OUT / f"{a.name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
