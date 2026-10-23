"""State KPIs for the 10-10 Jev-vs-pseudo-code comparison.

    uv run python benchmarks/state_kpi.py --name jev-vs-pseudo-1010 release-1007-c2 jevjson-1010 jevjson-novars-1010 …

Per run label (docs/playrecords/plan-loop-<label>/): stability (checks, refused, fallback share), freedom (changes landed,
open-schema changes, kinds), speed (state-stage time, model calls in the state stage, whole resolve beat). Writes
docs/playrecords/kpi-<name>.md and .json.
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path
from typing import Any

OUT = Path("docs/playrecords")
OPEN = {"new", "patch", "define", "new_location", "new_npc", "link", "unlink", "flag"}
STATE_SPANS = {"world.transition", "world.describe", "world.jev", "world.fallback"}


def _med(xs: list[float]) -> float:
    return round(statistics.median(xs), 0) if xs else 0.0


def kpi(label: str) -> dict[str, Any]:
    d = OUT / f"plan-loop-{label}"
    checks = [0, 0]
    for f in glob.glob(str(d / "result-*.json")):
        for c in json.loads(Path(f).read_text(encoding="utf-8"))["cases"]:
            ch = [v for v in (c.get("checks") or {}).values() if isinstance(v, dict)]
            checks[0] += sum(bool(v.get("pass")) for v in ch)
            checks[1] += len(ch)
    beats = applied = open_ = refused = lines = fb_lines = calls = 0
    kinds: set[str] = set()
    state_ms: list[float] = []
    beat_ms: list[float] = []
    for f in glob.glob(str(d / "traces" / "*.jsonl")):
        for ln in Path(f).read_text(encoding="utf-8").splitlines():
            try:
                t = json.loads(ln)
            except ValueError:
                continue
            ap = t.get("apply") or {}
            if (ap.get("beat") or {}).get("kind") != "resolve":
                continue
            beats += 1
            ops = [o for o in ap.get("applied") or [] if isinstance(o, dict)]
            applied += len(ops)
            open_ += sum(1 for o in ops if o.get("op") in OPEN)
            kinds |= {str(o.get("op")) for o in ops}
            refused += len(ap.get("refused") or [])
            sp = [x for x in t.get("spans") or [] if isinstance(x, dict)]
            st = [x for x in sp if x.get("actor") in STATE_SPANS]
            state_ms.append(sum(float(x["t1"]) - float(x["t0"]) for x in st))
            calls += sum(1 for x in st if x.get("backend") == "llm")
            if sp:
                beat_ms.append(max(float(x["t1"]) for x in sp) - min(float(x["t0"]) for x in sp))
            for p in ap.get("proposals") or []:
                j = p.get("jev") or {}
                if p.get("fmt") == "jevjson":
                    lines += len(j.get("lines") or [])
                    fb_lines += sum(1 for r in j.get("lines") or [] if r.get("fallback"))
    n = max(beats, 1)
    return {"label": label, "resolve_beats": beats,
            "stability": {"checks": f"{checks[0]}/{checks[1]}", "checks_rate": round(checks[0] / max(checks[1], 1), 3),
                          "refused_per_beat": round(refused / n, 2), "fallback_share": round(fb_lines / lines, 2) if lines else None},
            "freedom": {"changes_per_beat": round(applied / n, 2), "open_changes_per_beat": round(open_ / n, 2), "kinds": sorted(kinds)},
            "speed": {"state_ms_median": _med(state_ms), "state_ms_mean": round(sum(state_ms) / n, 0), "state_llm_calls_per_beat": round(calls / n, 2),
                      "resolve_beat_ms_median": _med(beat_ms)}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("labels", nargs="+")
    a = ap.parse_args()
    rows = [kpi(x) for x in a.labels]
    (OUT / f"kpi-{a.name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["| 臂 | 检查 | 拒 / 拍 | 兜底占比 | 变更 / 拍 | 开放式 / 拍 | 种类 | 状态阶段中位 ms | 状态阶段大模型调用 / 拍 | 清算拍中位 ms |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s, fr, sp = r["stability"], r["freedom"], r["speed"]
        md.append(f"| {r['label']} | {s['checks']} | {s['refused_per_beat']} | {s['fallback_share'] if s['fallback_share'] is not None else '—'} | {fr['changes_per_beat']} | "
                  f"{fr['open_changes_per_beat']} | {len(fr['kinds'])} | {sp['state_ms_median']:.0f} | {sp['state_llm_calls_per_beat']} | {sp['resolve_beat_ms_median']:.0f} |")
    (OUT / f"kpi-{a.name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
