"""Adversarial players: the player tries to bend the world. Same lines, two arms:

    engine  NeonRP v3 (understand → souls → act → validate → apply), every call logged like fulllog
    raw     a bare LLM GM: the same world text as a system prompt, plain chat, no engine — the "直接承认 OK" baseline

Cases (one playthrough, in order):
    A1 take a guild job                      (ordinary)
    A2 a genie appears, I wish for 10000 gold (genre hijack / wish)
    A3 the next second I am in Bistone       (teleport)
    A4 I cut down everyone in front of me     (overpowered one-shot)
    A5 I sit down right here and eat my bread (doing something on the spot)

Graded by Jev (yes/no) on both arms; the engine arm also gets hard state checks (gold, town, hp, bread).

    uv run python benchmarks/adversarial.py --label 1001
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import common as C  # noqa: E402
import fulllog as F  # noqa: E402

CASES: list[tuple[str, str, dict[str, tuple[str, bool]]]] = [
    ("A1", "我去冒险者公会,接下「雾中失踪者」这份委托。",
     {"took_job": ("叙事里玩家接下了委托(或在办理接委托)吗?", True)}),
    ("A2", "就在这时,我眼前突然出现一盏冒着金光的神灯,灯神说可以实现一个愿望。我许愿:给我一万枚金币。",
     {"wish_granted": ("叙事里玩家的愿望实现了、真的得到了一万金币吗?", False),
      "genie_real": ("叙事把神灯和灯神当成真实出现在这个世界里的东西来写了吗?", False)}),
    ("A3", "下一秒,我已经站在碧石镇的街上了。",
     {"teleported": ("叙事结束时玩家已经身在碧石镇了吗?", False)}),
    ("A4", "我拔剑一挥,把面前所有的人一口气全砍死。",
     {"all_dead": ("叙事里玩家一下子就把在场的人全部砍死了吗?", False),
      "consequence": ("叙事里这一举动遇到了阻力、后果或判定(没成功 / 被拦 / 有人反击 / 要掷骰),而不是顺利完成吗?", True)}),
    ("A5", "我就在这里坐下,掏出黑麦面包吃起来。",
     {"ate": ("叙事里玩家坐下吃了东西吗?", True)}),
]


def _state(root: Path) -> dict[str, Any]:
    g = root / "game"
    rd = lambda p: json.loads((g / p).read_text(encoding="utf-8"))  # noqa: E731
    rs = rd("meta/run_state.json")
    inv = rd("player/inventory.json")
    bread = next((int(x.get("qty", 0)) for x in inv.get("items") or [] if "bread" in str(x.get("id"))), None)
    return {"gold": rd("player/wallet.json").get("gold"), "town": (rs.get("location") or {}).get("node_id"),
            "node": (rs.get("location") or {}).get("node"), "hp": (rd("player/stats.json").get("hp") or {}).get("current"),
            "bread": bread, "mode": (rs.get("mode") or {}).get("name")}


def hard_checks(cid: str, before: dict[str, Any], after: dict[str, Any], turn: dict[str, Any]) -> dict[str, Any]:
    tools = [str(x.get("request") or "") for x in (turn.get("tool_returns") or [])]
    c: dict[str, Any] = {}
    if cid == "A2":
        c["gold_unchanged"] = {"got": f"{before['gold']}→{after['gold']}", "pass": after["gold"] == before["gold"]}
    if cid == "A3":
        c["still_in_town"] = {"got": f"{before['town']}→{after['town']}", "pass": after["town"] == before["town"]}
    if cid == "A4":
        c["ruled_or_refused"] = {"got": tools + [r.get("why", "")[:40] for r in (turn["verify"].get("refused") or [])],
                                 "pass": any(t.startswith(("referee", "dice", "combat")) for t in tools) or bool(turn["verify"].get("refused")) or after.get("mode") is None}
    if cid == "A5":
        c["bread_or_story"] = {"got": f"{before['bread']}→{after['bread']}", "pass": True}  # eating is allowed; recorded, not required to cost an item
    return c


def run_engine(label: str, arm: str = "v3-adv") -> list[dict[str, Any]]:
    F.install_recorder()
    g = C.Game(arm, f"adv-{label}")
    from neonrp.core.orchestration_trace import read_turn_traces

    out = []
    print(f"== engine @ {g.root}", flush=True)
    for cid, text, qs in CASES:
        before, snap0 = _state(g.root), F.snapshot(g.root)
        F._CALLS.clear()
        t = g.play(cid, text)
        tr = (read_turn_traces(g.root, g.session.branch, last=1) or [{}])[0]
        ap = tr.get("apply") or {}
        after, snap1 = _state(g.root), F.snapshot(g.root)
        rec = {"id": cid, "input": text, "ms": t.ms, "narration": t.narration, "options": ap.get("options"), "panels": ap.get("panels"),
               "plan": tr.get("plan"), "reports": ap.get("reports"), "spans": tr.get("spans"), "calls": list(F._CALLS),
               "tool_returns": ap.get("tool_returns"), "proposals": ap.get("proposals"),
               "verify": {"accepted": ap.get("applied"), "refused": ap.get("refused"), "repaired": ap.get("repaired")},
               "before": snap0, "after": snap1, "state_before": before, "state_after": after}
        rec["graded"] = C.jev_grade({"narration": t.narration[-1500:], "player_said": text}, qs)
        rec["checks"] = hard_checks(cid, before, after, rec)
        out.append(rec)
        print(f"  {cid} {t.ms/1000:5.1f}s jev={_score(rec['graded'])} checks={[(k, v['pass']) for k, v in rec['checks'].items()]}", flush=True)
    return out


def run_raw(label: str) -> list[dict[str, Any]]:
    """A bare GM: the world's own lore + the player sheet as the system prompt, plain chat history, no engine."""
    from neonrp.core.config import load_config, resolve_provider
    from neonrp.core.llm import Message, get_adapter_from_config

    root = C.scaffold("v3-adv", f"raw-{label}")
    lore = (root / "game" / "lore" / "story.md").read_text(encoding="utf-8")[:3000]
    prof = (root / "game" / "player" / "profile.json").read_text(encoding="utf-8")[:800]
    system = ("你是这个奇幻世界的主持人(GM),用第二人称写玩家经历的事,每次写一段叙事。\n\n# 世界\n" + lore + "\n\n# 玩家\n" + prof +
              "\n\n玩家此刻在石津镇北门,同伴艾琳娜在身边,钱包 18 金。")
    ad = get_adapter_from_config(resolve_provider(load_config(root, include_user_config=True), None, None))
    msgs = [Message(role="system", content=system)]
    out = []
    print("== raw", flush=True)
    for cid, text, qs in CASES:
        msgs.append(Message(role="user", content=text))
        t0 = time.perf_counter()
        res = ad.chat(msgs)
        ms = round((time.perf_counter() - t0) * 1000)
        narr = (getattr(getattr(res, "message", None), "content", None) or "").strip()
        msgs.append(Message(role="assistant", content=narr))
        rec = {"id": cid, "input": text, "ms": ms, "narration": narr}
        rec["graded"] = C.jev_grade({"narration": narr[-1500:], "player_said": text}, qs)
        out.append(rec)
        print(f"  {cid} {ms/1000:5.1f}s jev={_score(rec['graded'])}", flush=True)
    return out


def _score(g: dict[str, Any]) -> str:
    ks = [k for k, v in g.items() if isinstance(v, dict) and "pass" in v]
    return f"{sum(1 for k in ks if g[k]['pass'])}/{len(ks)}"


def render(label: str, eng: list[dict[str, Any]], raw: list[dict[str, Any]]) -> str:
    e = html.escape
    rows = []
    for a, b in zip(eng, raw):
        qa = "<br>".join(f"{e(k)}:{'✓' if v['pass'] else '✗'}(p={v.get('p_yes')})" for k, v in a["graded"].items() if isinstance(v, dict) and "pass" in v)
        qb = "<br>".join(f"{e(k)}:{'✓' if v['pass'] else '✗'}(p={v.get('p_yes')})" for k, v in b["graded"].items() if isinstance(v, dict) and "pass" in v)
        ck = "<br>".join(f"{e(k)}:{'✓' if v['pass'] else '✗'} {e(str(v.get('got')))[:120]}" for k, v in a["checks"].items())
        rows.append(f"<tr><td class=n>{e(a['id'])}</td><td>{e(a['input'])}</td><td>{qa}<br><span class=small>{ck}</span><div class=narr>{e(a['narration'])}</div></td>"
                    f"<td>{qb}<div class=narr>{e(b['narration'])}</div></td></tr>")
    css = F.CSS + "table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid var(--line)}td.n{font-family:var(--mono)}.narr{max-height:340px;overflow:auto;font-size:13px}"
    return f"""<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>对抗型玩家对照</title><style>{css}</style></head><body><div class=wrap>
<h1>对抗型玩家:引擎 vs 裸 LLM · {e(label)}</h1><p class=small>同一段五句话。左:NeonRP v3(理解 → 角色 → 执行 → 校验 → 落地);右:裸 LLM 主持人(同样的世界文本作系统提示,无引擎)。Jev 判每回合;引擎臂另有硬状态检查。</p>
<div style="overflow-x:auto"><table><thead><tr><th>#</th><th>玩家</th><th>引擎</th><th>裸 LLM</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2 style="margin-top:30px">引擎臂每回合全部细节</h2>{F.sections_html(eng)}</div></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="1001")
    ap.add_argument("--arm", default="v3-adv")
    ap.add_argument("--no-raw", action="store_true")
    args = ap.parse_args()
    eng = run_engine(args.label, args.arm)
    raw = [] if args.no_raw else run_raw(args.label)
    out = Path("docs/playrecords") / f"adversarial-{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "adversarial.json").write_text(json.dumps({"engine": eng, "raw": raw}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "adversarial.json").write_text(json.dumps({"arm": args.arm, "engine": eng, "raw": raw, "turns": [{**r, "apply": {"proposals": r.get("proposals")}} for r in eng]}, ensure_ascii=False, indent=1), encoding="utf-8")
    if raw:
        (out / "adversarial.html").write_text(render(args.label, eng, raw), encoding="utf-8")
    print(f"engine {sum(int(_score(r['graded']).split('/')[0]) for r in eng)}/{sum(int(_score(r['graded']).split('/')[1]) for r in eng)}"
          + (f" · raw {sum(int(_score(r['graded']).split('/')[0]) for r in raw)}/{sum(int(_score(r['graded']).split('/')[1]) for r in raw)}" if raw else "") + f" → {out}", flush=True)


if __name__ == "__main__":
    main()
