"""The public benchmark site: the case catalog + every experiment, as static pages (「问题一览我们要写论文的…
作为我们的 benchmark,和每次实验记录都可以有一个 index html 可以展示,这个是开源」).

    benchmarks/catalog.json                 every case: category, the player's goal, the checks, where it came from
    benchmarks/records/<exp>/experiment.json one experiment: the question, the groups compared (engine version / arm), runs
    benchmarks/records/<exp>/runs/<label>.json one run, slimmed (checks + beats: what the player said, the prose, refusals)
    benchmarks/records/<exp>/index.html     the experiment page
    benchmarks/index.html                   catalog + experiments

Raw runs stay in docs/playrecords (never exported); `import` copies the parts that can be public.

    uv run python benchmarks/site.py catalog
    uv run python benchmarks/site.py import <exp> --title … --question … \
        --group "old|fb0ea985|identity-v4-old-r1,identity-v4-old-r2" --group "new|47937154|identity-v4-new-r1,…" [--summary kpi.md]
    uv run python benchmarks/site.py build
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = ROOT / "docs" / "playrecords"
RECORDS = HERE / "records"
_HOME = re.compile(r"/(?:Users|home)/[^/\s\"']+")


def _scrub(x: Any) -> Any:
    """No personal paths in anything published."""
    if isinstance(x, str):
        return _HOME.sub("~", x)
    if isinstance(x, list):
        return [_scrub(v) for v in x]
    if isinstance(x, dict):
        return {k: _scrub(v) for k, v in x.items()}
    return x


def _short(v: Any, n: int = 240) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


# ── catalog ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def _latest_checks() -> dict[str, list[str]]:
    """Each case's check names as its most recent run reported them (checks are code; their names come out when run)."""
    best: dict[str, tuple[float, list[str]]] = {}
    for f in glob.glob(str(RAW / "*" / "result-*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        t = os.path.getmtime(f)
        for c in d.get("cases") or []:
            if isinstance(c, dict) and c.get("id") and c.get("checks") and t >= best.get(c["id"], (0.0, []))[0]:
                best[c["id"]] = (t, list(c["checks"]))
    return {k: v for k, (_t, v) in best.items()}


def build_catalog() -> dict[str, Any]:
    sys.path.insert(0, str(HERE))
    import suite  # noqa: PLC0415 — the suite is the source of truth for the cases

    process = ["every_beat_plan_or_resolve", "no_state_change_while_planning", "no_dice_while_planning"]
    names = _latest_checks()
    cases = []
    for cid, (cat, merged) in suite.CATALOG.items():
        sp = suite.spec(cid)
        title = sp["title"].split("] ", 1)[-1]
        checks = [k for k in names.get(cid, []) if k not in process and k != "prose_in_lang"]
        cases.append({"id": cid, "category": cat, "title": title, "goal": sp["goal"], "budget": sp["budget"],
                      "stance": sp.get("stance") or "", "merged": merged, "checks": checks})
    out = {"name": "WorldLines play suite", "built": date.today().isoformat(), "world": "stoneford-elena",
           "categories": list(suite.CATS), "process_checks": process, "cases": cases}
    (HERE / "catalog.json").write_text(json.dumps(_scrub(out), ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ── import one experiment ───────────────────────────────────────────────────────────────────────────────────────────


def _slim_case(c: dict[str, Any]) -> dict[str, Any]:
    beats = []
    for b in c.get("beats") or []:
        bt = b.get("beat") or {}
        beats.append({"id": b.get("id"), "kind": bt.get("kind") or "", "input": b.get("input") or "", "ms": b.get("ms"),
                      "narration": b.get("narration") or "",
                      "refused": [_short(r.get("why") or "", 200) for r in b.get("refused") or [] if isinstance(r, dict)]})
    return {"id": c.get("id"), "title": c.get("title"), "category": c.get("cat"),
            "checks": {k: {"pass": bool(v.get("pass")), "got": _short(v.get("got"))} for k, v in (c.get("checks") or {}).items()},
            "beats": beats}


def import_experiment(exp: str, title: str, question: str, groups: list[str], summary: str = "", when: str = "", src: list[str] = ()) -> Path:
    d = RECORDS / exp
    (d / "runs").mkdir(parents=True, exist_ok=True)
    dirs = [Path(s) for s in src] + [RAW]
    gs = []
    for g in groups:
        name, commit, labels = (g.split("|") + ["", ""])[:3]
        runs = []
        for i, lb in enumerate([x for x in labels.split(",") if x], 1):
            rd = next((x / f"plan-loop-{lb}" for x in dirs if (x / f"plan-loop-{lb}").is_dir()), None)
            if rd is None:
                raise SystemExit(f"no run folder plan-loop-{lb} under {', '.join(map(str, dirs))}")
            cases, arm = [], ""
            for f in sorted(rd.glob("result-*.json")):
                r = json.loads(f.read_text(encoding="utf-8"))
                arm = r.get("arm") or arm
                cases += [_slim_case(c) for c in r.get("cases") or []]
            (d / "runs" / f"{lb}.json").write_text(json.dumps(_scrub({"label": lb, "arm": arm, "cases": cases}), ensure_ascii=False),
                                                   encoding="utf-8")
            runs.append({"label": lb, "run": i, "arm": arm})
        gs.append({"name": name, "commit": commit, "runs": runs})
    meta = {"id": exp, "title": title, "question": question, "date": when or date.today().isoformat(), "groups": gs,
            "summary_md": Path(summary).read_text(encoding="utf-8") if summary else ""}
    (d / "experiment.json").write_text(json.dumps(_scrub(meta), ensure_ascii=False, indent=1), encoding="utf-8")
    return d


# ── pages ───────────────────────────────────────────────────────────────────────────────────────────────────────────


def _experiments() -> list[dict[str, Any]]:
    out = []
    for f in sorted(RECORDS.glob("*/experiment.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        for g in m["groups"]:
            ok = n = 0
            for r in g["runs"]:
                run = json.loads((f.parent / "runs" / f"{r['label']}.json").read_text(encoding="utf-8"))
                for c in run["cases"]:
                    ok += sum(v["pass"] for v in c["checks"].values())
                    n += len(c["checks"])
            g["passed"], g["checks"] = ok, n
        out.append(m)
    return sorted(out, key=lambda m: m["date"], reverse=True)


def _page(kind: str, data: dict[str, Any], title: str, base: str) -> str:
    tpl = (HERE / "site_page.html").read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("{{TITLE}}", title).replace("{{KIND}}", kind).replace("{{BASE}}", base).replace("{{DATA}}", blob)


def build() -> None:
    cat = json.loads((HERE / "catalog.json").read_text(encoding="utf-8")) if (HERE / "catalog.json").exists() else build_catalog()
    exps = _experiments()
    used: dict[str, list[str]] = {}
    for m in exps:
        d = RECORDS / m["id"]
        runs = {r["label"]: json.loads((d / "runs" / f"{r['label']}.json").read_text(encoding="utf-8")) for g in m["groups"] for r in g["runs"]}
        for run in runs.values():
            for c in run["cases"]:
                used.setdefault(c["id"], [])
                if m["id"] not in used[c["id"]]:
                    used[c["id"]].append(m["id"])
        (d / "index.html").write_text(_page("experiment", {"experiment": m, "runs": runs, "catalog": cat}, m["title"], "../../"),
                                      encoding="utf-8")
    home = {"catalog": cat, "experiments": [{k: v for k, v in m.items() if k != "summary_md"} for m in exps], "used": used}
    (HERE / "index.html").write_text(_page("home", home, "WorldLines Play Suite", ""), encoding="utf-8")
    print(f"catalog {len(cat['cases'])} cases · {len(exps)} experiments → {HERE / 'index.html'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalog")
    sub.add_parser("build")
    im = sub.add_parser("import")
    im.add_argument("exp")
    im.add_argument("--title", required=True)
    im.add_argument("--question", default="")
    im.add_argument("--group", action="append", required=True, help="name|commit|label1,label2,…")
    im.add_argument("--summary", default="", help="a Markdown table (e.g. docs/playrecords/kpi-….md)")
    im.add_argument("--date", default="")
    im.add_argument("--src", action="append", default=[], help="another folder holding plan-loop-<label>/ (e.g. an old worktree)")
    a = ap.parse_args()
    if a.cmd == "catalog":
        c = build_catalog()
        print(f"{len(c['cases'])} cases → {HERE / 'catalog.json'}")
    elif a.cmd == "import":
        print(import_experiment(a.exp, a.title, a.question, a.group, a.summary, a.date, a.src))
        build()
    else:
        build()


if __name__ == "__main__":
    main()
