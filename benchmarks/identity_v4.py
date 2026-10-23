"""Identity check V4 — the old engine (before the identity work) against the new one, same cases, 3 runs.

Runs are suite.py labels `identity-v4-<old|new>-r<n>` (docs/playrecords/plan-loop-<label>/). Per version, summed over its runs:
checks passed (the identity cases ID1–ID5 and the earlier 14 apart), refusals per resolve beat (all, and those about naming),
`{{` left in the prose, how often the identity gate / owner rules stepped in, and the state-stage / resolve-beat time.

    uv run python benchmarks/identity_v4.py [--runs 3] [--name identity-v4-1013]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_kpi as K  # noqa: E402

OUT = Path("docs/playrecords")
MENU = re.compile(r"[①②③]")
ASKING = re.compile(r"([??]|吗|呢|么)\s*$")
NAMING = re.compile(r"unknown entity|unknown place|could be any of|already exists|is already gone|ambiguous|not found in")


def _cases(label: str) -> list[dict[str, Any]]:
    out = []
    for f in glob.glob(str(OUT / f"plan-loop-{label}" / "result-*.json")):
        out += json.loads(Path(f).read_text(encoding="utf-8"))["cases"]
    return out


def _traces(label: str) -> list[dict[str, Any]]:
    out = []
    for f in glob.glob(str(OUT / f"plan-loop-{label}" / "traces" / "*.jsonl")):
        for ln in Path(f).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    return out


def version(ver: str, runs: int) -> dict[str, Any]:
    # "@<prefix>": another experiment's runs, labelled <prefix>-r<n> (10-14: rules-1014 against V4)
    labels = [f"{ver[1:]}-r{r}" if ver.startswith("@") else f"identity-v4-{ver}-r{r}" for r in range(1, runs + 1)]
    per_check: dict[tuple[str, str], list[bool]] = collections.defaultdict(list)
    leaks = unsettled_fails = stuck = mid_talk = 0
    for lb in labels:
        for c in _cases(lb):
            ended_in_talk = ((c.get("beats") or [{}])[-1].get("beat") or {}).get("kind") == "plan"
            if ended_in_talk:  # 10-15: a loop of hand-backs (the host closes on a menu, the player says what he does) vs a talk cut by the budget
                tail = []
                for b in reversed(c.get("beats") or []):
                    if (b.get("beat") or {}).get("kind") != "plan":
                        break
                    tail.append(b)
                loop = [b for b in tail if MENU.search(str(b.get("narration") or "")) and not ASKING.search(str(b.get("input") or "").strip())]
                if len(loop) >= 2:
                    stuck += 1
                else:
                    mid_talk += 1
            for k, v in (c.get("checks") or {}).items():
                per_check[(c["id"], k)].append(bool(v.get("pass")))
                unsettled_fails += ended_in_talk and not v.get("pass")
            leaks += sum("{{" in str(b.get("narration") or "") for b in c.get("beats") or [])
    beats = refused = naming = gate = owner_rows = plan_beats = 0
    naming_why: collections.Counter[str] = collections.Counter()
    state_ms: list[float] = []
    beat_ms: list[float] = []
    for lb in labels:
        for t in _traces(lb):
            ap = t.get("apply") or {}
            if (ap.get("beat") or {}).get("kind") == "plan":
                plan_beats += 1
            if (ap.get("beat") or {}).get("kind") != "resolve":
                continue
            beats += 1
            rf = ap.get("refused") or []
            refused += len(rf)
            for r in rf:
                why = str(r.get("why") or "")
                if NAMING.search(why):
                    naming += 1
                    naming_why[re.sub(r"'[^']*'|\S*\d{3,}\S*", "X", why)[:60]] += 1
            sp = [x for x in t.get("spans") or [] if isinstance(x, dict)]
            gate += sum(1 for x in sp if x.get("actor") == "world.identity")
            owner_rows += sum(len(p.get("identity") or []) for p in ap.get("proposals") or [])
            st = [x for x in sp if x.get("actor") in K.STATE_SPANS]
            state_ms.append(sum(float(x["t1"]) - float(x["t0"]) for x in st))
            if sp:
                beat_ms.append(max(float(x["t1"]) for x in sp) - min(float(x["t0"]) for x in sp))

    def tally(pred) -> str:
        xs = [p for (cid, _k), ps in per_check.items() if pred(cid) for p in ps]
        return f"{sum(xs)}/{len(xs)}"

    n = max(beats, 1)
    return {"version": ver, "labels": labels, "resolve_beats": beats,
            "checks_all": tally(lambda c: True), "checks_identity": tally(lambda c: c.startswith("ID")),
            "checks_rest": tally(lambda c: not c.startswith("ID")), "unsettled_fails": unsettled_fails,
            "stuck_runs": stuck, "mid_talk_runs": mid_talk, "plan_per_resolve": round(plan_beats / max(beats, 1), 2),
            "refused_per_beat": round(refused / n, 2), "naming_refused_per_beat": round(naming / n, 3), "naming_refused": naming,
            "naming_why": naming_why.most_common(8), "brace_leaks": leaks, "gate_spans": gate, "owner_rows": owner_rows,
            "state_ms_median": round(statistics.median(state_ms)) if state_ms else 0,
            "resolve_beat_ms_median": round(statistics.median(beat_ms)) if beat_ms else 0,
            "per_check": {f"{cid}.{k}": ps for (cid, k), ps in sorted(per_check.items())}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--name", default="identity-v4-1013")
    ap.add_argument("--groups", default="旧=old,新=new,新 · 修复后(只 ID)=newfix", help="title=label part, …")
    a = ap.parse_args()
    groups = [(t, version(v, a.runs)) for t, v in (g.split("=") for g in a.groups.split(","))]
    rows = [("检查 · 全部", "checks_all"), ("检查 · 身份 5 例", "checks_identity"), ("检查 · 原 14 例", "checks_rest"),
            ("其中失败于没落账的局", "unsettled_fails"), ("卡住的局(连着 ≥2 拍菜单交回,玩家都在说行动)", "stuck_runs"),
            ("谈到一半预算用完的局", "mid_talk_runs"), ("平均几拍商量进一次清算", "plan_per_resolve"), ("清算拍数", "resolve_beats"), ("拒 / 拍", "refused_per_beat"), ("认名被拒 / 拍", "naming_refused_per_beat"),
            ("认名被拒(条)", "naming_refused"), ("正文露出 {{", "brace_leaks"), ("认定门调用", "gate_spans"), ("补主人 / 门改写(条)", "owner_rows"),
            ("状态阶段中位 ms", "state_ms_median"), ("清算拍中位 ms", "resolve_beat_ms_median")]
    head = "| | " + " | ".join(t for t, _ in groups) + " |"
    md = [head, "|---" * (len(groups) + 1) + "|"] + [f"| {t} | " + " | ".join(str(g[k]) for _, g in groups) + " |" for t, k in rows]
    md += ["", "| 用例 · 检查 | " + " | ".join(t for t, _ in groups) + " |", "|---" * (len(groups) + 1) + "|"]
    keys = sorted(set().union(*(g["per_check"] for _, g in groups)))
    for key in keys:
        cols = [g["per_check"].get(key, []) for _, g in groups]
        filled = [c for c in cols if c]
        if key.startswith("ID") or len({round(sum(c) / len(c), 2) for c in filled}) > 1:
            md.append(f"| {key} | " + " | ".join(f"{sum(c)}/{len(c)}" if c else "—" for c in cols) + " |")
    md += [""] + [f"认名被拒 · {t}:" + (" · ".join(f"{w} ×{n}" for w, n in g["naming_why"]) or "无") for t, g in groups]
    (OUT / f"kpi-{a.name}.json").write_text(json.dumps({t: g for t, g in groups}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / f"kpi-{a.name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
