"""速度套题 — same world, same 8 inputs, one game per arm; wall clock + spans + ops."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as C  # noqa: E402

INPUTS = [
    "我站在北门口张望了一会儿,然后叫住艾琳娜:「你还记得昨晚的事吗?」",
    "我不再追问,拉着她往主街走,想找个地方坐下。",
    "路过杂货铺时我停下来,掏出两枚铜币想买个热饼,顺便打听河灯旅店在哪。",
    "我把饼分给艾琳娜一半,自己咬了一口,继续往旅店方向走。",
    "到了旅店门口,我推门进去,问掌柜要一间房,顺便看看有没有人在找我。",
    "我在旅店大堂里坐下,让艾琳娜先上楼休息,自己等罗文来。",
    "等了很久罗文没来,我决定去公会问问有没有人见过他。",
    "夜深了,我回到旅店房间躺下,打算等到明天早上再说。",
]


def phase_breakdown(turns: list[dict]) -> dict[str, float]:
    acc = defaultdict(list)
    for t in turns:
        by = defaultdict(float)
        par = []
        for s in t.get("spans") or []:
            d = float(s.get("t1", 0)) - float(s.get("t0", 0))
            if s["phase"] == "parallel":
                par.append(d)
            else:
                by[s["phase"]] += d
        if par:
            by["parallel"] = max(par)
        for k, v in by.items():
            acc[k].append(v)
    return {k: round(statistics.median(v) / 1000, 1) for k, v in acc.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="v3-sjudge")
    args = ap.parse_args()
    out = {"suite": "speed", "arms": {}}
    d = C.run_dir("speed")
    lines = ["| arm | n | wall med | p90 | " + " | ".join(("plan", "parallel", "solve", "verify", "apply", "settle", "land")) + " | ops | narr |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm in [a for a in args.arms.split(",") if a]:
        g = C.Game(arm, "speed")
        turns = []
        print(f"== speed · {arm} @ {g.root}", flush=True)
        for i, text in enumerate(INPUTS):
            t = g.play(f"T{i}", text)
            turns.append(t.to_dict())
            print(f"  [{arm}] T{i} {t.ms/1000:5.1f}s ops={t.ops[:5]} player={t.player}", flush=True)
        g.archive(d, arm)
        out["arms"][arm] = turns
        ms = sorted(t["ms"] for t in turns)
        p90 = ms[min(len(ms) - 1, int(0.9 * len(ms)))]
        ph = phase_breakdown(turns)
        lines.append(f"| {arm} | {len(turns)} | {statistics.median(ms)/1000:.1f}s | {p90/1000:.1f}s | " + " | ".join(f"{ph.get(k, 0):.1f}" for k in ("plan", "parallel", "solve", "verify", "apply", "settle", "land")) + f" | {statistics.mean(len(t['ops']) for t in turns):.1f} | {statistics.mean(len(t['narration']) for t in turns):.0f} |")
        (d / "out.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    body = "<pre>" + C.esc("\n".join(lines)) + "</pre>" + "".join(f"<h2>{C.esc(arm)}</h2>" + C.render_turns(ts) for arm, ts in out["arms"].items())
    (d / "page.html").write_text(C.page("速度套题", f"NeonRP benchmark · speed · {C.WORLD} · {C.PRESET}", "", body), encoding="utf-8")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
