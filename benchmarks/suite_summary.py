"""Sum up a suite run (docs/playrecords/plan-loop-<label>/result-*.json): full passes, checks, structural checks, per case.

    uv run python benchmarks/suite_summary.py <run dir> [--md]

Structural = the checks every case carries (beat shape: plan / resolve only, nothing lands while planning, no dice
while planning); the rest are the case's own goals.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STRUCTURAL = ("every_beat_plan_or_resolve", "no_state_change_while_planning", "no_dice_while_planning")


def load(d: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted(d.glob("result-*.json")):
        out += json.loads(f.read_text(encoding="utf-8")).get("cases") or []
    return out


def summary(cases: list[dict]) -> dict:
    full = sum(all(v["pass"] for v in c["checks"].values()) for c in cases)
    allc = [(k, v["pass"]) for c in cases for k, v in c["checks"].items()]
    st = [p for k, p in allc if k in STRUCTURAL]
    cats: dict[str, list[int]] = {}
    for c in cases:
        x = cats.setdefault(c.get("cat") or "?", [0, 0])
        x[0] += all(v["pass"] for v in c["checks"].values())
        x[1] += 1
    return {"cases": len(cases), "full": full, "checks": [sum(p for _, p in allc), len(allc)], "structural": [sum(st), len(st)],
            "cats": cats, "failed": {c["id"]: [k for k, v in c["checks"].items() if not v["pass"]] for c in cases
                                      if not all(v["pass"] for v in c["checks"].values())}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    s = summary(load(Path(a.run)))
    pct = lambda x: f"{x[0]}/{x[1]} ({100 * x[0] / max(1, x[1]):.0f}%)"  # noqa: E731
    if not a.md:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return
    print(f"- 全过 {s['full']}/{s['cases']} · 检查 {pct(s['checks'])} · 结构 {pct(s['structural'])}\n")
    print("| 类 | 全过 |\n|---|---|")
    for k, (f, n) in s["cats"].items():
        print(f"| {k} | {f}/{n} |")
    print("\n| 例 | 没过的检查 |\n|---|---|")
    for k, v in s["failed"].items():
        print(f"| {k} | {' · '.join(v)} |")


if __name__ == "__main__":
    main()
