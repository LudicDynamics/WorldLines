"""Testbed 09-27: a few REAL turns on the new engine so a person can read the whole loop and every
intermediate product (plan · soul reports · raw ops · verify · applied · triggers with reason chains
· ledger · ending) and spot differences.

  uv run python benchmarks/testbed.py rpg        # stoneford + a plot pack (关键词 → 阶段 → 地窖 → 结局)
  uv run python benchmarks/testbed.py werewolf   # the werewolf template with a real deepseek judge
  uv run python benchmarks/testbed.py monopoly   # the monopoly template: engine rolls (procedure), deepseek narrates + decides buys
Outputs docs/playrecords/testbed-0927/<name>.json + <name>.md (+ trace html for rpg).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
OUT = REPO / "docs" / "playrecords" / "testbed-0927"

PLOT = {"id": "P01", "title": "雾里的钥匙", "stages": ["起", "承", "合"],
        "entries": {"I900": {"class": "item", "name": "锈钥匙", "parent": "T001/main_street"},
                    "T001/crypt": {"class": "place", "name": "地窖", "parent": "T001", "links": ["T001/main_street"]}},
        "triggers": {"P01.key": {"when": {"text": "both"}, "if": [{"text": ["钥匙", "地窖"]}], "once": True,
                                 "then": [{"to": "var", "var": "P01.stage", "set": 1},
                                          {"to": "narration", "text": "(剧情包 P01)主街石缝里露出一截锈钥匙的柄;有人说镇署后面有个封了的地窖。"},
                                          {"to": "soul", "who": "艾琳娜", "text": "玩家在打听地窖和钥匙的事", "important": True}],
                                 "else": [{"to": "log"}]},
                     "P01.crypt": {"when": {"entry": "T001/crypt", "event": "enter", "who": "player"},
                                   "if": [{"var": "P01.stage", ">=": 1}],
                                   "then": [{"to": "var", "var": "P01.stage", "set": 2}],
                                   "else": [{"to": "narration", "text": "(剧情包 P01)地窖门锁着,没有钥匙进不去。"}]},
                     "P01.done": {"when": {"var": "P01.stage"}, "if": [{"var": "P01.stage", ">=": 2}],
                                  "then": [{"to": "end", "ending": "E01", "title": "雾散", "text": "地窖底下是干的,雾从这里开始退。"}]}},
        "endings": {"E01": {"title": "雾散"}}}


def _w(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _events(root: Path, since: int) -> list[dict]:
    from neonrp.core import ledger

    return [{"seq": e["seq"], "type": e["type"], "payload": e["payload"]} for e in ledger.events(root, since=since)]


def run_rpg() -> None:
    import common as C
    from neonrp.core.registry import load_registry
    from neonrp.packs.rpg import plot as P

    g = C.Game("v3-sjudge", "testbed")
    root = g.root
    pdir = root / "plots" / "P01"
    _w(pdir / "plot.json", PLOT)
    info = P.install(root, pdir)
    rec = {"world": str(root), "arm": "v3-sjudge", "plot_installed": info, "turns": []}
    since = 0
    lines = [
        ("T1", "艾琳娜,我在主街这边转转。你听说过什么锈钥匙吗?这镇上有地窖吗?"),
        ("T2", "我捡起那把钥匙,去镇署后面找那个地窖。"),
        ("T3", "我推开地窖的门走下去。"),
        ("T4", "我在地窖里四处看看。"),
    ]
    for tid, text in lines:
        t = g.play(tid, text)
        reg = load_registry(root)
        ap = t.apply or {}
        rec["turns"].append({
            "id": tid, "input": text, "ms": t.ms, "narration": t.narration,
            "plan": t.plan, "reports": t.reports,
            "proposals": [{"narration": p.get("narration", "")[:200], "ops": p.get("ops"), "refused": p.get("refused")} for p in (ap.get("proposals") or [])],
            "applied": ap.get("applied"), "refused": ap.get("refused"), "repaired": ap.get("repaired"),
            "triggered": ap.get("triggered"), "ended": ap.get("ended"),
            "state": {"player": reg.player_location, "P01.stage": reg.variables.get("P01.stage").value if "P01.stage" in reg.variables else None,
                      "souls": {e.id: e.parent for e in reg.of_class("soul")}, "flag.ended": reg.variables.get("flag.ended").value if "flag.ended" in reg.variables else None},
            "ledger": _events(root, since), "spans": [(s.get("phase"), s.get("actor"), s.get("ms")) for s in t.spans],
        })
        since = max([e["seq"] for e in rec["turns"][-1]["ledger"]] + [since])
        print(f"[{tid}] {t.ms} ms · stage={rec['turns'][-1]['state']['P01.stage']} · triggered={[x.get('trigger') for x in (ap.get('triggered') or [])]} · ended={ap.get('ended')}")
        if ap.get("ended") and tid != "T4":
            pass
    _w(OUT / "rpg-plot.json", rec)
    g.archive(OUT, "rpg-plot")
    _md(OUT / "rpg-plot.md", "stoneford-elena + 剧情包 P01(S-judge · deepseek)", rec)


def run_werewolf() -> None:
    from neonrp.core import turn_v3
    from neonrp.core.registry import load_registry

    root = Path.home() / ".neonrp-bench" / f"werewolf-{int(time.time()) % 100000}"
    _w(root / "manifest.json", {"template": "werewolf", "name": "夜半村"})
    _w(root / "game" / "meta" / "table.json", {"wolves": 2, "villagers": 3, "phase": "day", "round": 1})
    for sid, name, role in (("S01", "阿明", "villager"), ("S02", "小红", "wolf"), ("S03", "老李", "seer"), ("S04", "阿彩", "wolf"), ("S05", "大壮", "villager")):
        _w(root / "game" / "seats" / f"{sid}.json", {"id": sid, "class": "seat", "props": {"name": name, "role": role, "alive": True, "votes": 0}})
    from neonrp.worlds import seed_run_model

    seed_run_model(root, "deepseek")  # same model seeding a scaffolded world gets
    rec = {"world": str(root), "template": "werewolf", "turns": []}
    since = 0
    lines = [
        ("T1", "(我是1号阿明)天亮了。昨晚没人死。我先发言:我觉得小红昨晚发言太急,我怀疑她。大家轮流说一下。"),
        ("T2", "投票阶段。我投小红。请法官统计其他人的票并宣布结果。"),
        ("T3", "天黑了,狼人请行动。然后天亮,法官播报昨晚的情况。"),
        ("T4", "白天讨论。老李(预言家)跳出来报验人结果。然后全员投票,法官计票放逐。"),
    ]
    for tid, text in lines:
        t0 = time.perf_counter()
        turn = len(rec["turns"]) + 1
        out = turn_v3.solve_turn(root, user_text=text, provider=None, turn=turn, soul_reports=[])
        ms = round((time.perf_counter() - t0) * 1000)
        ap = out["apply"]
        reg = load_registry(root)
        rec["turns"].append({
            "id": tid, "input": text, "ms": ms, "narration": out.get("narration"),
            "contract_head": (out.get("contract") or "")[:300] if isinstance(out.get("contract"), str) else None,
            "proposals": [{"narration": p.get("narration", "")[:200], "ops": p.get("ops"), "refused": p.get("refused")} for p in (out.get("proposals") or [])],
            "verify": out.get("verify"), "applied": ap.applied, "refused": ap.refused, "triggered": ap.triggered, "ended": ap.ended,
            "state": {"table": json.loads((root / "game" / "meta" / "table.json").read_text()),
                      "seats": {e.id: {"name": e.props.get("name"), "alive": e.props.get("alive"), "votes": e.props.get("votes")} for e in reg.of_class("seat")}},
            "ledger": _events(root, since), "spans": [(s.get("phase"), s.get("actor"), s.get("ms")) for s in out.get("spans") or []], "loops": out.get("loops"),
        })
        since = max([e["seq"] for e in rec["turns"][-1]["ledger"]] + [since])
        print(f"[{tid}] {ms} ms · ops={[o.get('op') for o in ap.applied]} · refused={len(ap.refused)} · ended={ap.ended}")
        if ap.ended:
            break
    _w(OUT / "werewolf.json", rec)
    _md(OUT / "werewolf.md", "狼人杀模板(法官 = deepseek,无 souls)", rec)


def run_monopoly() -> None:
    """Each turn = (1) engine procedure: roll for whoever's turn it is (P3 in miniature: the dice are
    settled BEFORE the narrator speaks) → (2) solve_turn: the narrator explains the landing and
    proposes buy / endturn. The human is S01; the human's line decides S01's buys."""
    from neonrp.core import sdk, turn_v3
    from neonrp.core.registry import load_registry
    from neonrp.packs.monopoly import pack as M
    from neonrp.worlds import seed_run_model

    root = Path.home() / ".neonrp-bench" / f"monopoly-{int(time.time()) % 100000}"
    M.scaffold(root, seed=11)
    seed_run_model(root, "deepseek")
    rec = {"world": str(root), "template": "monopoly", "turns": []}
    since = 0
    human = {1: "我掷骰子。落到无主的地就买,钱够就买。", 4: "这块要是没主我就买;要是别人的,付了租我认。", 7: "买。我要把这条街占下来。"}
    for turn in range(1, 10):
        t = json.loads((root / "game" / "meta" / "table.json").read_text())
        who = t["turn_of"]
        reg = load_registry(root)
        # (1) procedure
        pr = sdk.apply(root, [{"op": "roll", "who": who}], reg, turn=turn)
        proc = {"roll": pr.applied[0] if pr.applied else None, "triggered": pr.triggered, "ended": pr.ended}
        if pr.ended:
            rec["turns"].append({"id": f"T{turn}", "who": who, "procedure": proc, "ledger": _events(root, since)})
            print(f"[T{turn}] ended by procedure: {pr.ended}")
            break
        # (2) narrator + decision
        text = human.get(turn, "(轮到 AI 座位,你替它决定)") if who == "S01" else f"(轮到 {reg.entries[who].props.get('name')},你替它决定买不买,然后 endturn)"
        t0 = time.perf_counter()
        out = turn_v3.solve_turn(root, user_text=text, provider=None, turn=turn, soul_reports=[])
        ms = round((time.perf_counter() - t0) * 1000)
        ap = out["apply"]
        reg = load_registry(root)
        rec["turns"].append({
            "id": f"T{turn}", "who": who, "input": text, "ms": ms, "narration": out.get("narration"), "procedure": proc,
            "proposals": [{"narration": p.get("narration", "")[:200], "ops": p.get("ops"), "refused": p.get("refused")} for p in (out.get("proposals") or [])],
            "verify": out.get("verify"), "applied": ap.applied, "refused": ap.refused, "triggered": ap.triggered, "ended": ap.ended,
            "state": {"table": json.loads((root / "game" / "meta" / "table.json").read_text()),
                      "seats": {e.id: {"name": e.props.get("name"), "cash": e.props.get("cash"), "pos": e.props.get("pos"), "alive": e.props.get("alive")} for e in reg.of_class("seat")},
                      "owned": {e.id: e.props.get("owner") for e in reg.of_class("tile") if e.props.get("owner")}},
            "ledger": _events(root, since), "spans": [(s.get("phase"), s.get("actor"), s.get("ms")) for s in out.get("spans") or []], "loops": out.get("loops"),
        })
        since = max([e["seq"] for e in rec["turns"][-1]["ledger"]] + [since])
        print(f"[T{turn}] {who} · {ms} ms · roll={proc['roll'] and proc['roll'].get('dice')} {proc['roll'] and proc['roll'].get('event')} · ops={[o.get('op') for o in ap.applied]} · refused={len(ap.refused)} · ended={ap.ended}")
        if ap.ended:
            break
        if not any(o.get("op") == "endturn" for o in ap.applied):  # the narrator forgot to pass the dice: the procedure does it
            sdk.apply(root, [{"op": "endturn"}], load_registry(root), turn=turn)
            rec["turns"][-1]["auto_endturn"] = True
    _w(OUT / "monopoly.json", rec)
    _md(OUT / "monopoly.md", "大富翁模板(引擎掷骰结算 · 庄家 = deepseek)", rec)


def _md(path: Path, title: str, rec: dict) -> None:
    L = [f"# Testbed 09-27 · {title}", "", f"世界:`{rec.get('world')}`", ""]
    for t in rec["turns"]:
        L += [f"## {t['id']} · {t.get('ms', 0)} ms" + (f" · 轮到 {t['who']}" if t.get("who") else ""), ""]
        if t.get("procedure"):
            pr = t["procedure"]
            L += [f"**⓪ 引擎流程(掷骰结算):** `{json.dumps(pr.get('roll'), ensure_ascii=False)}`"] + [f"  触发 `{x.get('trigger')}` → {x.get('branch')}: " + " / ".join(x.get("why") or []) for x in pr.get("triggered") or []] + ([f"  **结局:** `{json.dumps(pr.get('ended'), ensure_ascii=False)}`"] if pr.get("ended") else []) + [""]
        if t.get("input") is None:
            continue
        L += [f"**玩家:** {t['input']}", "", "**叙事:**", "", "> " + (t.get("narration") or "").replace("\n", "\n> "), ""]
        if t.get("plan"):
            L += ["**① plan:** `" + json.dumps(t["plan"], ensure_ascii=False)[:600] + "`", ""]
        if t.get("reports"):
            L += ["**② 角色回包:**"] + [f"- {r.get('name')} [{r.get('kind')}] {r.get('text')}" for r in t["reports"]] + [""]
        for i, p in enumerate(t.get("proposals") or []):
            L += [f"**③ 直出 {i + 1} ops:** `{json.dumps(p.get('ops'), ensure_ascii=False)}`" + (f" · 被拒 `{json.dumps(p.get('refused'), ensure_ascii=False)[:300]}`" if p.get("refused") else "")]
        if t.get("verify"):
            L += [f"**④ verify:** `{json.dumps(t['verify'], ensure_ascii=False)[:500]}`"]
        L += [f"**⑤ applied:** `{json.dumps(t.get('applied'), ensure_ascii=False)[:600]}`"]
        if t.get("refused"):
            L += [f"**⑤ refused:** `{json.dumps(t.get('refused'), ensure_ascii=False)[:400]}`"]
        for x in t.get("triggered") or []:
            L += [f"**⑤ 触发 `{x.get('trigger')}` → {x.get('branch')}:** " + " / ".join(x.get("why") or []) + f" → emitted `{json.dumps(x.get('emitted'), ensure_ascii=False)[:200]}`"]
        if t.get("ended"):
            L += [f"**结局:** `{json.dumps(t['ended'], ensure_ascii=False)}`"]
        L += [f"**状态:** `{json.dumps(t.get('state'), ensure_ascii=False)[:500]}`", "**账本:** " + ", ".join(f"{e['seq']}:{e['type']}" for e in t.get("ledger") or []),
              "**spans:** " + ", ".join(f"{p}/{a} {m}ms" for p, a, m in t.get("spans") or []), ""]
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "rpg"
    OUT.mkdir(parents=True, exist_ok=True)
    {"rpg": run_rpg, "werewolf": run_werewolf, "monopoly": run_monopoly}[which]()
