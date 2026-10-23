"""判断器套题 — the same situations and questions across judge backends (jev / llm / …):
latency, agreement with Jev, confidence. Situations come from a recorded run (a speed or
consistency out.json), so the judge is tested on what the engine actually produces."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as C  # noqa: E402

GOALS = ["在石津镇拿到第一份真正像样的契约", "靠自己的本事挣出名声", "弄清灰雾北境究竟藏着什么"]


def situations(from_json: Path, n: int) -> list[dict]:
    d = json.loads(from_json.read_text(encoding="utf-8"))
    turns = []
    if "arms" in d:
        for ts in d["arms"].values():
            turns.extend(ts if isinstance(ts, list) else ts.get("turns", []))
    else:
        turns = d.get("turns", [])
    out = []
    for t in turns:
        narr = t.get("narration") or ""
        if narr and not narr.startswith("{"):
            out.append({"id": t.get("id"), "player_says": t.get("input"), "what_happened": narr[-800:], "soul": "艾琳娜", "mood_before": "alert", "goals": GOALS})
    return out[:n]


def main() -> None:
    from neonrp.core import system_one as s1
    from neonrp.packs.rpg.soul_settle import questions_for

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, help="a suite out.json to draw situations from")
    ap.add_argument("--backends", default="jev,llm")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--llm-preset", default=C.PRESET)
    args = ap.parse_args()
    sits = situations(Path(args.src), args.n)
    out = {"suite": "judge", "n": len(sits), "backends": {}}
    for backend in [b for b in args.backends.split(",") if b]:
        os.environ["NEONRP_S1_BACKEND"] = backend
        if backend == "llm":
            os.environ["NEONRP_S1_LLM_PRESET"] = args.llm_preset
        s1._CACHE.clear()
        rows = []
        print(f"== {backend}", flush=True)
        for st in sits:
            qs = {"intent.kind": s1.choice("玩家这句话的意图", {"talk": "说话", "act": "行动", "move": "移动", "observe": "观察"}),
                  "soul.reacts": s1.noul("艾琳娜会对玩家这一回合有反应吗?"),
                  "soul.depth": s1.choice("艾琳娜反应的深度", {"silent": "沉默", "gesture": "神态", "speak": "说话", "act": "行动"}),
                  **questions_for(st["soul"], st["mood_before"], st["goals"])}
            t0 = time.perf_counter()
            ans = s1.ask(st, qs, timeout=20.0)
            ms = round((time.perf_counter() - t0) * 1000)
            rows.append({"id": st["id"], "ms": ms, "ok": bool(ans), "error": s1.last_call().get("error"), "answers": {k: a.to_dict() for k, a in (ans or {}).items()}})
            print(f"  [{backend}] {st['id']} {ms} ms ok={bool(ans)}", flush=True)
        out["backends"][backend] = rows
    ref = {r["id"]: r for r in out["backends"].get("jev", [])}
    lines = ["| backend | ok | ms med | p90 | agree(choice) | agree(noul ±.25) | conf med |", "|---|---|---|---|---|---|---|"]
    for b, rows in out["backends"].items():
        ms = sorted(r["ms"] for r in rows)
        p90 = ms[min(len(ms) - 1, int(0.9 * len(ms)))]
        ok = [r for r in rows if r["ok"]]
        confs = [a["confidence"] for r in ok for a in r["answers"].values()]
        ac = an = tc = tn = 0
        for r in ok:
            j = ref.get(r["id"])
            if not j or not j["ok"]:
                continue
            for k, a in r["answers"].items():
                ja = j["answers"].get(k)
                if not ja:
                    continue
                if a["type"] == "noul":
                    tn += 1
                    an += int(abs(float(a["value"]) - float(ja["value"])) <= 0.25)
                else:
                    tc += 1
                    ac += int(str(a["value"]) == str(ja["value"]))
        lines.append(f"| {b} | {len(ok)}/{len(rows)} | {statistics.median(ms)} | {p90} | {ac}/{tc} | {an}/{tn} | {statistics.median(confs) if confs else 0:.2f} |")
    d = C.run_dir("judge")
    (d / "out.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
