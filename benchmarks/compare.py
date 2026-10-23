"""实验对照台 — every archived run of every suite on one page, side by side per turn,
with an LLM critique of the versions of each turn.

    uv run python benchmarks/compare.py                 # page only (fast, offline)
    uv run python benchmarks/compare.py --critique      # + deepseek critique per turn (≈50 calls)
    uv run python benchmarks/compare.py --critique --suites E7,E5

Records are read from docs/playrecords/ (the archive), never from runs/. Output:
benchmarks/runs/compare-<date>/{data.json, critique.json, index.html}; copy index.html
into docs/playrecords/artifacts/ when it is worth keeping.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

REC = Path(__file__).resolve().parents[1] / "docs" / "playrecords"

SUITES = {
    "E1": {"title": "E1 速度 · 同 8 句输入 × 7 臂", "what": "整回合墙钟;无评分,看叙事与角色回包"},
    "E5": {"title": "E5 一致性 · 异地 / 同行 / 分开重逢 / 跨镇", "what": "确定性位置检查 + Jev 叙事判断题"},
    "E6": {"title": "E6 协商 · 说服裁决(轻自判 / 重掷骰)", "what": "分量判对 · 台词与结局一致 · 骰子改变结局"},
    "E7": {"title": "E7 活人感 · 五条", "what": "不无视需求 / 不执着 / 理解环境 / 绝境决策 / 共情 + 易读 + 像人"},
}


# ── normalise every record shape into one turn dict ─────────────────────────

def _speech(t: dict[str, Any]) -> str:
    for r in t.get("reports") or []:
        if r.get("iid") == C.ELENA and r.get("text"):
            return str(r["text"])
    return str(t.get("speech") or (t.get("extra") or {}).get("speech") or "")


def _scores(g: dict[str, Any] | None) -> dict[str, Any]:
    out = {}
    for k, v in (g or {}).items():
        if isinstance(v, dict) and "p_yes" in v:
            out[k] = {"p": v["p_yes"], "pass": v.get("pass"), "expected": v.get("expected")}
        elif isinstance(v, dict) and "value" in v:
            out[k] = {"v": v["value"]}
    return out


def _turn(tid: str, t: dict[str, Any], *, det: bool | None = None, decision: dict | None = None) -> dict[str, Any]:
    sc = _scores(t.get("graded"))
    passed = sum(1 for v in sc.values() if v.get("pass") is True)
    total = sum(1 for v in sc.values() if v.get("pass") is not None)
    return {"id": tid, "input": t.get("input") or "", "narration": t.get("narration") or "", "speech": _speech(t),
            "ms": t.get("ms") or 0, "scores": sc, "passed": passed, "total": total, "det": det,
            "decision": decision, "player": t.get("player"), "elena": ((t.get("souls") or {}).get(C.ELENA) if isinstance(t.get("souls"), dict) else None) or t.get("elena"),
            "loops": (t.get("apply") or {}).get("loops") if isinstance(t.get("apply"), dict) else None,
            "attempts": len((t.get("apply") or {}).get("proposals") or []) if isinstance(t.get("apply"), dict) else None}


def _det(t: dict[str, Any]) -> bool | None:
    c = t.get("checks")
    if not c:
        return None
    return all(v.get("pass") for v in c.values())


def _decision(t: dict[str, Any]) -> dict | None:
    for r in t.get("reports") or []:
        d = (r.get("judgment") or {}).get("decision")
        if d:
            return d
    d = (t.get("extra") or {}).get("decision") or t.get("decision")
    return d if isinstance(d, dict) else None


def load() -> dict[str, dict[str, list[dict[str, Any]]]]:
    S: dict[str, dict[str, list[dict[str, Any]]]] = {k: {} for k in SUITES}
    # E1: arms
    f = REC / "e1-0925" / "e1.out.json"
    if f.exists():
        for arm, turns in json.loads(f.read_text(encoding="utf-8"))["arms"].items():
            S["E1"][arm] = [_turn(f"T{t.get('turn', i)}", t) for i, t in enumerate(turns)]
    # E5: old combined file (run1 / run2 / speak / v2b) + run3 / run4 folders
    f = REC / "e5-0925" / "e5.out.json"
    if f.exists():
        names = {"v3-sjudge": "v3-sjudge·run1", "v3-sjudge-run2": "v3-sjudge·run2", "v3-speak": "v3-speak", "v2b": "v2b"}
        for arm, blob in json.loads(f.read_text(encoding="utf-8"))["arms"].items():
            S["E5"][names.get(arm, arm)] = [_turn(t["id"], t, det=_det(t)) for t in blob["rows"]]
    for n in (3, 4):
        f = REC / "e5-0925" / f"run{n}" / f"v3-sjudge-run{n}.out.json"
        if f.exists():
            S["E5"][f"v3-sjudge·run{n}"] = [_turn(t["id"], t, det=_det(t)) for t in json.loads(f.read_text(encoding="utf-8"))["turns"]]
    # E6: run1 / run2 flat lists with run index; run3 / run4 nested lists
    for n in (1, 2):
        f = REC / "e6-0925" / f"e6.run{n}.out.json"
        if f.exists():
            rows = json.loads(f.read_text(encoding="utf-8"))["runs"]
            flat = [(t.get("run", gi), t) for gi, g in enumerate(rows) for t in (g if isinstance(g, list) else [g])]
            S["E6"][f"run{n}"] = [_turn(f"{t['id']}·局{gi}", t, det=t.get("stakes_ok"), decision=_decision(t)) for gi, t in flat]
    for n in (3, 4):
        f = REC / "e6-0925" / f"run{n}" / "v3-sjudge.out.json"
        if f.exists():
            games = json.loads(f.read_text(encoding="utf-8"))["runs"]
            S["E6"][f"run{n}"] = [_turn(f"{t['id']}·局{gi}", t, det=_det(t), decision=_decision(t)) for gi, g in enumerate(games) for t in g]
    # E7: run1–4
    for n in (1, 2, 3, 4):
        f = REC / "e7-0925" / f"v3-sjudge.run{n}.out.json"
        if f.exists():
            S["E7"][f"run{n}"] = [_turn(t["id"], t) for t in json.loads(f.read_text(encoding="utf-8"))["turns"]]
    # bench.py archive: docs/playrecords/bench/<suite>/<date>-<label>-<fp>/ (every run from here on)
    exp = {"aliveness": "E7", "consistency": "E5", "negotiation": "E6", "speed": "E1"}
    idx = REC / "bench" / "INDEX.json"
    if idx.exists():
        for r in json.loads(idx.read_text(encoding="utf-8")):
            sk = exp.get(r["suite"])
            d = REC.parent.parent / r["path"]
            if not sk or not d.is_dir() or r.get("imported_from"):  # imported = already loaded from its legacy folder above
                continue
            label = f"{r['date'][5:]}·{r.get('label', r['arm'])}·{r['git']}"
            turns: list[dict[str, Any]] = []
            for f in sorted(d.glob("*.out.json")) + sorted(d.glob("out.json")):
                blob = json.loads(f.read_text(encoding="utf-8"))
                if "turns" in blob:
                    turns += [_turn(t["id"], t, det=_det(t), decision=_decision(t)) for t in blob["turns"]]
                elif "runs" in blob:
                    turns += [_turn(f"{t['id']}·局{gi}", t, det=_det(t), decision=_decision(t)) for gi, g in enumerate(blob["runs"]) for t in (g if isinstance(g, list) else [g])]
                elif "arms" in blob:
                    for arm, ts in blob["arms"].items():
                        S[sk][f"{label}·{arm}"] = [_turn(f"T{t.get('turn', i)}", t) for i, t in enumerate(ts)]
            if turns:
                S[sk][label] = turns
    return S


def summary(turns: list[dict[str, Any]]) -> dict[str, Any]:
    ms = sorted(t["ms"] for t in turns if t["ms"])
    p = sum(t["passed"] for t in turns)
    tot = sum(t["total"] for t in turns)
    dets = [t["det"] for t in turns if t["det"] is not None]
    return {"n": len(turns), "passed": p, "total": tot, "rate": (p / tot if tot else None),
            "det_ok": sum(1 for d in dets if d), "det_n": len(dets),
            "ms_median": (statistics.median(ms) if ms else 0), "ms_p90": (ms[min(len(ms) - 1, int(0.9 * len(ms)))] if ms else 0),
            "loops": sum(1 for t in turns if (t.get("loops") or 0) > 0)}


# ── LLM critique ─────────────────────────────────────────────────────────────

_CRITIC_SYS = (
    "你是一个文字 RPG 引擎的评审。同一句玩家输入在几个引擎版本下各产出一段叙事和(可能有的)同伴角色「艾琳娜」的台词。"
    "只比较文字本身:1) 易读(句子不绕、信息顺序清楚)2) 像人(台词是一个真实的人在说,不是旁白 / 说明书)3) 逻辑(位置 / 在场 / 动作前后一致,没有瞬移或凭空出现的人)"
    "4) 对这句输入的回应是否到位(需求 / 情绪 / 请求有没有被接住)。不要奖励长度;凌乱、堆砌、说教扣分。"
    "只输出一个 JSON 对象:{\"ranking\": [版本名,由好到差], \"notes\": {版本名: \"一句话\"}, \"verdict\": \"两三句总评,点出最关键的差别\"}。"
)


def _critic_adapter() -> Any:
    from neonrp.core import turn_v3

    root = C.scaffold("v3-sjudge", "critic")  # carries the same model config the suites ran with
    return turn_v3._adapter(root, None)


def critique(S: dict[str, dict[str, list[dict[str, Any]]]], suites: list[str], out_dir: Path) -> dict[str, Any]:
    from neonrp.core.turn_v3 import _chat

    adapter = _critic_adapter()
    out: dict[str, Any] = {}
    f = out_dir / "critique.json"
    if f.exists():
        out = json.loads(f.read_text(encoding="utf-8"))
    for sk in suites:
        runs = S.get(sk) or {}
        if not runs:
            continue
        out.setdefault(sk, {"turns": {}, "overall": None})
        ids: list[str] = []
        for turns in runs.values():
            for t in turns:
                if t["id"] not in ids:
                    ids.append(t["id"])
        for tid in ids:
            versions = {label: next((t for t in turns if t["id"] == tid), None) for label, turns in runs.items()}
            versions = {k: v for k, v in versions.items() if v and (v["narration"] or v["speech"])}
            if len(versions) < 2:
                continue
            prev = out[sk]["turns"].get(tid)
            if prev and sorted(prev.get("versions") or []) == sorted(versions):
                continue  # already critiqued with exactly these versions; a new arm re-opens the turn
            parts = [f"玩家输入:{next(iter(versions.values()))['input']}"]
            for label, t in versions.items():
                d = t.get("decision") or {}
                dec = f"\n[裁决]{d.get('stakes')} → {d.get('outcome')};" + " / ".join(d.get("reasons") or []) if d else ""
                parts.append(f"\n\n### 版本「{label}」\n[叙事]{t['narration'][:1400]}\n[艾琳娜台词]{t['speech'][:500] or '(无)'}{dec}")
            t0 = time.perf_counter()
            try:
                text, ms, _u = _chat(adapter, _CRITIC_SYS, "\n".join(parts))
                res = C.parse_json_loose(text) if hasattr(C, "parse_json_loose") else _loose(text)
            except Exception as exc:  # noqa: BLE001
                res = {"error": str(exc)[:200]}
            res["ms"] = round((time.perf_counter() - t0) * 1000)
            res["versions"] = sorted(versions)
            out[sk]["turns"][tid] = res
            out[sk]["overall"] = None  # the suite verdict is rebuilt once its turns change
            print(f"  [{sk}] {tid} {res.get('ms')} ms → {res.get('ranking')}", flush=True)
            f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        # one overall verdict per suite from the per-turn verdicts
        if out[sk]["turns"] and not out[sk].get("overall"):
            lines = [f"{tid}: 排名 {r.get('ranking')};{r.get('verdict')}" for tid, r in out[sk]["turns"].items() if r.get("verdict")]
            q = (f"下面是「{SUITES[sk]['title']}」每一回合的逐回合评审(版本名相同即同一引擎版本)。"
                 "请写 4–6 句总评:哪个版本整体最好、差在哪、最反复出现的问题是什么、给引擎的一条具体建议。只输出纯文本。\n\n" + "\n".join(lines))
            try:
                text, _ms, _u = _chat(adapter, "你是文字 RPG 引擎的评审,只写结论,不客套。", q)
                out[sk]["overall"] = text.strip()
            except Exception as exc:  # noqa: BLE001
                out[sk]["overall"] = f"(总评失败:{str(exc)[:120]})"
            f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _loose(text: str) -> dict[str, Any]:
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    i, j = s.find("{"), s.rfind("}")
    try:
        return json.loads(s[i:j + 1])
    except Exception:  # noqa: BLE001
        return {"verdict": s[:600]}


# ── page ─────────────────────────────────────────────────────────────────────

def page(S: dict[str, Any], crit: dict[str, Any]) -> str:
    data = {"suites": {k: {**SUITES[k], "runs": {label: {"turns": turns, "summary": summary(turns)} for label, turns in runs.items()}} for k, runs in S.items() if runs},
            "critique": crit, "world": C.WORLD, "preset": C.PRESET}
    tpl = (Path(__file__).resolve().parent / "compare_page.html").read_text(encoding="utf-8")
    return tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--critique", action="store_true")
    ap.add_argument("--suites", default="E7,E5,E6,E1")
    args = ap.parse_args()
    S = load()
    d = C.run_dir("compare")
    (d / "data.json").write_text(json.dumps(S, ensure_ascii=False), encoding="utf-8")
    for k, runs in S.items():
        print(f"{k}: " + " · ".join(f"{label} {summary(t)['passed']}/{summary(t)['total']} {summary(t)['ms_median'] / 1000:.1f}s" for label, t in runs.items()), flush=True)
    crit: dict[str, Any] = {}
    if (d / "critique.json").exists():
        crit = json.loads((d / "critique.json").read_text(encoding="utf-8"))
    if args.critique:
        crit = critique(S, [s.strip() for s in args.suites.split(",") if s.strip()], d)
    (d / "index.html").write_text(page(S, crit), encoding="utf-8")
    print(f"→ {d / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
