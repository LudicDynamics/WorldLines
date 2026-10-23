"""bench — run a suite only when the code it measures has changed, archive every run,
and read results back without touching an LLM.

    uv run python benchmarks/bench.py status                   # what ran on which code, what is stale
    uv run python benchmarks/bench.py run aliveness            # skipped if this code already ran this suite/arm
    uv run python benchmarks/bench.py run consistency --force  # run anyway
    uv run python benchmarks/bench.py all                      # every stale suite, serially
    uv run python benchmarks/bench.py all --failed-only        # only suites whose last run had a failure
    uv run python benchmarks/bench.py compare [--critique]     # page from the archive (offline; critique is incremental)
    uv run python benchmarks/bench.py show aliveness           # last archived run, turn by turn, no LLM

Freshness = a fingerprint over the engine core (src/neonrp/core/*.py), the suite file and
benchmarks/common.py. Same fingerprint + suite + arm → the archived run still answers, so it
is not re-run. Archive: docs/playrecords/bench/<suite>/<date>-<label>-<fp>/ + INDEX.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ARCHIVE = REPO / "docs" / "playrecords" / "bench"
INDEX = ARCHIVE / "INDEX.json"
RUNS = HERE / "runs"

SUITES: dict[str, dict[str, Any]] = {
    "aliveness": {"file": "suites/aliveness.py", "exp": "E7", "args": ["--arm", "{arm}"], "minutes": 3},
    "consistency": {"file": "suites/consistency.py", "exp": "E5", "args": ["--arm", "{arm}", "--label", "{label}"], "minutes": 3},
    "negotiation": {"file": "suites/negotiation.py", "exp": "E6", "args": ["--arm", "{arm}", "--runs", "{runs}"], "minutes": 6},
    "speed": {"file": "suites/speed.py", "exp": "E1", "args": ["--arms", "{arm}"], "minutes": 3},
}
ORDER = ["aliveness", "consistency", "negotiation", "speed"]


# ── fingerprint ──────────────────────────────────────────────────────────────

def fingerprint(suite: str) -> str:
    """Hash of everything whose change could change this suite's numbers."""
    h = hashlib.sha256()
    files = sorted((REPO / "src" / "neonrp" / "core").glob("*.py")) + [HERE / "common.py", HERE / SUITES[suite]["file"]]
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:10]


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


# ── index ────────────────────────────────────────────────────────────────────

def load_index() -> list[dict[str, Any]]:
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding="utf-8"))
    return []


def save_index(rows: list[dict[str, Any]]) -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def latest(rows: list[dict[str, Any]], suite: str, arm: str, preset: str = "deepseek") -> dict[str, Any] | None:
    hits = [r for r in rows if r["suite"] == suite and r["arm"] == arm and r.get("preset", "deepseek") == preset]
    return hits[-1] if hits else None


# ── summary of a run dir (no LLM) ────────────────────────────────────────────

def summarize(run_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(HERE))
    import compare as CMP  # noqa: E402

    turns: list[dict[str, Any]] = []
    for f in sorted(run_dir.glob("*.out.json")) + sorted(run_dir.glob("out.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if "turns" in d:
            turns += [CMP._turn(t["id"], t, det=CMP._det(t), decision=CMP._decision(t)) for t in d["turns"]]
        elif "runs" in d:
            for gi, g in enumerate(d["runs"]):
                turns += [CMP._turn(f"{t['id']}·局{gi}", t, det=CMP._det(t), decision=CMP._decision(t)) for t in (g if isinstance(g, list) else [g])]
        elif "arms" in d:
            for arm, ts in d["arms"].items():
                turns += [CMP._turn(f"{arm}:T{t.get('turn', i)}", t) for i, t in enumerate(ts)]
    s = CMP.summary(turns)
    s["failed_ids"] = [t["id"] for t in turns if (t["total"] and t["passed"] < t["total"]) or t["det"] is False]
    return s


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> None:
    rows = load_index()
    print(f"{'suite':12} {'arm':12} {'last run':22} {'code':7} {'fresh':6} {'pass':9} {'pos':7} {'median':8} path")
    for suite in ORDER:
        fp = fingerprint(suite)
        arms = sorted({r["arm"] for r in rows if r["suite"] == suite}) or [args.arm]
        for arm in arms:
            r = latest(rows, suite, arm)
            if r is None:
                print(f"{suite:12} {arm:12} {'—':22} {'—':7} {'no':6}")
                continue
            fresh = "yes" if r["fingerprint"] == fp else "STALE"
            s = r["summary"]
            passed = f"{s['passed']}/{s['total']}" if s.get("total") else "—"
            det = f"{s['det_ok']}/{s['det_n']}" if s.get("det_n") else "—"
            print(f"{suite:12} {arm:12} {r['date'] + ' ' + r.get('label', ''):22} {r['git']:7} {fresh:6} {passed:9} {det:7} {s['ms_median'] / 1000:6.1f}s {r['path']}")
    print("\nfingerprint = 引擎核心 + common.py + 套题文件的内容哈希;STALE = 代码变了,数字不再代表现在。")


def run_suite(suite: str, arm: str, label: str, runs: int, *, force: bool, dry: bool, preset: str = "deepseek") -> dict[str, Any] | None:
    import os

    rows = load_index()
    fp = fingerprint(suite)
    prev = latest(rows, suite, arm, preset)
    if prev and prev["fingerprint"] == fp and not force:
        print(f"[skip] {suite} · {arm}: 这份代码已经跑过 → {prev['path']}({prev['date']} {prev.get('label', '')},{prev['summary'].get('passed')}/{prev['summary'].get('total')})。--force 重跑。")
        return prev
    spec = SUITES[suite]
    argv = [sys.executable, str(HERE / spec["file"])] + [a.format(arm=arm, label=label, runs=runs) for a in spec["args"]]
    print(f"[run ] {suite} · {arm} · {label} · 模型 {preset} (≈{spec['minutes']} min, 串行)\n       {' '.join(argv)}")
    if dry:
        return None
    before = {p for p in RUNS.glob(f"{suite}-*")}
    t0 = time.time()
    proc = subprocess.run(argv, cwd=str(REPO), env={**os.environ, "BENCH_PRESET": preset})
    if proc.returncode != 0:
        print(f"[fail] {suite} exit {proc.returncode}")
        return None
    run_dir = max(RUNS.glob(f"{suite}-*"), key=lambda p: p.stat().st_mtime, default=None)
    if run_dir is None:
        print("[fail] no run dir produced")
        return None
    dest = ARCHIVE / suite / f"{date.today().isoformat()}-{label}-{fp[:7]}"
    if dest.exists():
        dest = dest.with_name(dest.name + f"-{int(time.time()) % 100000}")
    dest.mkdir(parents=True)
    # runs/<suite>-<date>/ is shared by every arm run that day: copy only what THIS run wrote
    mine = (label, arm, "out.json", "summary.md", "page.html")
    for f in run_dir.iterdir():
        if f.is_file() and f.stat().st_mtime >= t0 and f.name.startswith(mine):
            shutil.copy(f, dest / f.name)
    summary = summarize(dest)
    row = {"suite": suite, "exp": spec["exp"], "arm": arm, "label": label, "preset": preset, "date": date.today().isoformat(), "git": git_head(),
           "fingerprint": fp, "wall_s": round(time.time() - t0, 1), "summary": summary, "path": str(dest.relative_to(REPO)),
           "new_dir": run_dir not in before}
    rows.append(row)
    save_index(rows)
    s = summary
    print(f"[done] {suite} · {arm}: {s.get('passed')}/{s.get('total')} Jev · 位置 {s.get('det_ok')}/{s.get('det_n')} · 中位 {s['ms_median'] / 1000:.1f}s · 失败 {s['failed_ids'] or '无'} → {row['path']}")
    return row


def cmd_run(args: argparse.Namespace) -> None:
    run_suite(args.suite, args.arm, args.label or args.arm, args.runs, force=args.force, dry=args.dry, preset=args.preset)


def cmd_all(args: argparse.Namespace) -> None:
    rows = load_index()
    for suite in ORDER:
        if args.failed_only:
            prev = latest(rows, suite, args.arm)
            if prev and not prev["summary"].get("failed_ids"):
                print(f"[skip] {suite}: 上次全过")
                continue
        run_suite(suite, args.arm, args.label or args.arm, args.runs, force=args.force, dry=args.dry, preset=args.preset)


def cmd_show(args: argparse.Namespace) -> None:
    r = latest(load_index(), args.suite, args.arm)
    if r is None:
        print("没有归档的跑次;先 bench run", args.suite)
        return
    sys.path.insert(0, str(HERE))
    import compare as CMP  # noqa: E402

    print(f"{args.suite} · {r['arm']} · {r['date']} {r.get('label', '')} · code {r['git']} · {r['path']}")
    for f in sorted((REPO / r["path"]).glob("*.out.json")) + sorted((REPO / r["path"]).glob("out.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        turns = d.get("turns") or [t for g in d.get("runs", []) for t in (g if isinstance(g, list) else [g])]
        for t in turns:
            x = CMP._turn(t["id"], t, det=CMP._det(t), decision=CMP._decision(t))
            fails = [k for k, v in x["scores"].items() if v.get("pass") is False]
            mark = "✓" if not fails and x["det"] is not False else "✗"
            print(f"  {mark} {x['id']:6} {x['ms'] / 1000:5.1f}s {x['passed']}/{x['total']} {('位置✗ ' if x['det'] is False else '')}{' '.join(fails)}  | {x['speech'][:60]!r}")


def cmd_import(args: argparse.Namespace) -> None:
    """Register an existing record folder (e.g. docs/playrecords/e7-0925) as a run, without re-running."""
    src = (REPO / args.dir).resolve()
    files = [src / f for f in args.files.split(",")] if args.files else sorted(src.glob("*.out.json"))
    tmp = RUNS / f"import-{args.suite}-{int(time.time())}"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy(f, tmp / f.name)
    rows = load_index()
    fp = fingerprint(args.suite) if args.as_current else "legacy"
    dest = ARCHIVE / args.suite / f"{args.date}-{args.label}-{fp[:7]}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(tmp, dest)
    shutil.rmtree(tmp)
    summary = summarize(dest)
    rows.append({"suite": args.suite, "exp": SUITES[args.suite]["exp"], "arm": args.arm, "label": args.label, "date": args.date, "git": args.git or git_head(),
                 "fingerprint": fp, "wall_s": None, "summary": summary, "path": str(dest.relative_to(REPO)), "imported_from": str(src.relative_to(REPO))})
    save_index(rows)
    print(f"[import] {args.suite} · {args.arm} · {args.label}: {summary.get('passed')}/{summary.get('total')} → {dest.relative_to(REPO)} ({'current code' if args.as_current else 'legacy, shown STALE'})")


def cmd_play(args: argparse.Namespace) -> None:
    """Scaffold a fresh stoneford-elena world under one arm and hand it to the TUI (or the REPL)."""
    import os

    sys.path.insert(0, str(HERE))
    import common as C  # noqa: E402

    if args.arm not in C.ARMS:
        print("未知臂;可选:", ", ".join(C.ARMS))
        return
    base = Path(os.path.expanduser("~/.neonrp-bench"))
    base.mkdir(parents=True, exist_ok=True)
    root = base / f"{args.arm}-{int(time.time()) % 100000}"
    env = {**os.environ}
    for k in C._ARM_KEYS:
        env.pop(k, None)
    env.update({k: v for k, v in C.ARMS[args.arm].items() if v})
    argv = [sys.executable, "-m", "neonrp.cli"] + (["play"] if args.repl else ["tui", "--play"])
    print(f"[play] 臂 {args.arm} · 世界 {root}\n       env: " + " ".join(f"{k}={v}" for k, v in C.ARMS[args.arm].items() if v) + f"\n       {' '.join(argv)}  (cwd = 世界目录)")
    if args.dry:
        return
    from neonrp.worlds import scaffold_template_into

    scaffold_template_into(C.WORLD, root, model_ref=C.PRESET)
    os.chdir(root)
    os.execve(sys.executable, argv, env)


def cmd_compare(args: argparse.Namespace) -> None:
    argv = [sys.executable, str(HERE / "compare.py")] + (["--critique"] if args.critique else []) + (["--suites", args.suites] if args.suites else [])
    subprocess.run(argv, cwd=str(REPO), check=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status")
    p.add_argument("--arm", default="v3-sjudge")
    p.set_defaults(fn=cmd_status)
    for name, fn in (("run", cmd_run), ("all", cmd_all)):
        p = sub.add_parser(name)
        if name == "run":
            p.add_argument("suite", choices=list(SUITES))
        p.add_argument("--arm", default="v3-sjudge")
        p.add_argument("--label", default=None)
        p.add_argument("--runs", type=int, default=3)
        p.add_argument("--force", action="store_true")
        p.add_argument("--dry", action="store_true")
        p.add_argument("--preset", default="deepseek", help="model preset from ~/.neonrp/config.json (deepseek | kimi-k3 | qwen | …)")
        if name == "all":
            p.add_argument("--failed-only", action="store_true")
        p.set_defaults(fn=fn)
    p = sub.add_parser("show")
    p.add_argument("suite", choices=list(SUITES))
    p.add_argument("--arm", default="v3-sjudge")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("import")
    p.add_argument("suite", choices=list(SUITES))
    p.add_argument("dir")
    p.add_argument("--files", default=None, help="comma-separated out.json names inside dir (default: all *.out.json)")
    p.add_argument("--arm", default="v3-sjudge")
    p.add_argument("--label", required=True)
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--git", default=None)
    p.add_argument("--as-current", action="store_true", help="the engine core is unchanged since this ran → counts as fresh")
    p.set_defaults(fn=cmd_import)
    p = sub.add_parser("play", help="scaffold a fresh world under an arm and open the TUI in it")
    p.add_argument("arm")
    p.add_argument("--repl", action="store_true", help="neonrp play REPL instead of the TUI")
    p.add_argument("--dry", action="store_true")
    p.set_defaults(fn=cmd_play)
    p = sub.add_parser("compare")
    p.add_argument("--critique", action="store_true")
    p.add_argument("--suites", default=None)
    p.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
