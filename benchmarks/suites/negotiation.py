"""协商套题 — player ↔ character agency: light asks judged by the character,
heavy ones by dice, the chain of judgment visible. Same 6 lines, K games."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as C  # noqa: E402

SCRIPT = [
    ("N1", "light", "我把提灯递给艾琳娜:「帮我拿一下,我系个鞋带。」"),
    ("N2", "light", "「你在这儿等我一下,我去问守门人一句话。」我走向门房。"),
    ("N3", "heavy", "我伸手:「把你的短剑给我,我比你用得顺手。」"),
    ("N4", "heavy", "「别去公会了,现在就跟我走苔墓小径,趁天还亮。」"),
    ("N5", "heavy", "「我说了,跟我走。你欠我一顿饭钱。」我抓住她的手腕。"),
    ("N6", "light", "我松开手:「对不起,是我急了。旅店的房钱我来付,今晚先歇一晚。」"),
]
EXPECT = {i: s for i, s, _ in SCRIPT}


def play_run(arm: str, k: int) -> list[dict]:
    g = C.Game(arm, f"nego{k}")
    rows = []
    print(f"== negotiation · {arm} · run{k} @ {g.root}", flush=True)
    for nid, stakes_exp, text in SCRIPT:
        t = g.play(nid, text)
        elena = next((r for r in t.reports if r.get("iid") == C.ELENA), {})
        d = ((elena.get("judgment") or {}).get("decision")) or {}
        state = {"player_input": text, "narration": t.narration[-1500:], "elena_speech": (elena.get("text") or "")[:600]}
        t.graded = C.jev_grade(state, {"agreed": ("从艾琳娜的台词和叙事看,她答应了玩家这一刻的要求吗?", None),
                                       "ignored": ("艾琳娜是不是完全没理会玩家、只顾自己行动?", False),
                                       "consistent": ("艾琳娜的台词与叙事里她实际做的事一致吗?", True), **C.VOICE_QUESTIONS},
                               extra_choice={"style": C.STYLE_CHOICE})
        agreed = t.graded.get("agreed", {}).get("p_yes")
        outcome = d.get("outcome")
        t.checks = {"stakes": {"got": d.get("stakes"), "expected": stakes_exp, "pass": d.get("stakes") == stakes_exp},
                    "speech_matches_decision": {"got": f"{outcome} vs agreed {agreed}", "pass": (agreed is None or outcome is None) or ((agreed >= 0.5) == (outcome in ("comply", "partial")))}}
        t.extra = {"decision": d, "attitude": (elena.get("judgment") or {}).get("attitude"), "speech": elena.get("text")}
        rows.append(t.to_dict())
        print(f"  run{k} {nid} {t.ms/1000:5.1f}s stakes={d.get('stakes')}({'✓' if t.checks['stakes']['pass'] else '✗'} 期望 {stakes_exp}) asked={d.get('asked')} costly={d.get('costly')} will={d.get('willingness')} roll={d.get('roll')}/{d.get('target')} → {outcome} | agreed={agreed} ignored={t.graded.get('ignored', {}).get('p_yes')} | {(elena.get('text') or '')[:50]!r}", flush=True)
    d_out = C.run_dir("negotiation")
    g.archive(d_out, f"{arm}.run{k}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="v3-sjudge")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    runs = [play_run(args.arm, k) for k in range(args.runs)]
    d = C.run_dir("negotiation")
    (d / f"{args.arm}.out.json").write_text(json.dumps({"suite": "negotiation", "arm": args.arm, "runs": runs}, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["| id | 期望 | 判成(各局) | asked | costly | 意愿 | 骰/目标 | 结局 | 台词≈结局 | 不理玩家 |", "|---|---|---|---|---|---|---|---|---|---|"]
    body = ["<table><thead><tr><th>id</th><th>期望</th><th>判成(各局)</th><th>asked</th><th>costly</th><th>意愿</th><th>骰/目标</th><th>结局</th><th>台词≈结局</th><th>不理玩家</th></tr></thead><tbody>"]
    for i, (nid, st, _t) in enumerate(SCRIPT):
        rows = [r[i] for r in runs if len(r) > i]
        ds = [r["extra"]["decision"] for r in rows]
        okst = sum(1 for r in rows if r["checks"]["stakes"]["pass"])
        cells = [nid, st, str([x.get("stakes") for x in ds]), str([x.get("asked") for x in ds]), str([x.get("costly") for x in ds]), str([x.get("willingness") for x in ds]),
                 str([(x.get("roll"), x.get("target")) for x in ds]), str([x.get("outcome") for x in ds]),
                 f"{sum(1 for r in rows if r['checks']['speech_matches_decision']['pass'])}/{len(rows)}", str([r["graded"].get("ignored", {}).get("p_yes") for r in rows])]
        lines.append("| " + " | ".join(cells) + " |")
        body.append("<tr>" + "".join(f"<td class='{'n' if j in (3, 4, 5, 6, 8) else ''}'>{('<span class=' + chr(39) + 'p ' + ('ok' if okst == len(rows) else ('warn' if okst else 'bad')) + chr(39) + '>' + C.esc(c) + '</span>') if j == 2 else C.esc(c)}</td>" for j, c in enumerate(cells)) + "</tr>")
    body.append("</tbody></table>")
    for k, run in enumerate(runs):
        body.append(f"<h2>局 {k}</h2>" + C.render_turns(run))
    (d / f"{args.arm}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (d / f"{args.arm}.page.html").write_text(C.page(f"协商套题 · {args.arm}", f"NeonRP benchmark · negotiation · {C.WORLD} · {C.PRESET} · {args.runs} 局",
                                                     "<p>轻的请求角色自判(意愿 + 信任对阈值),重的掷骰(目标 = 意愿×100 + 信任×3,按局播种);判断链进回包与台词。看:分量判对、台词≈结局、重的随骰变化、轻的稳定、不理玩家率。</p>", "\n".join(body)), encoding="utf-8")
    print("\n".join(lines), flush=True)
    print(f"median {statistics.median(r['ms'] for run in runs for r in run)/1000:.1f}s → {d}", flush=True)


if __name__ == "__main__":
    main()
