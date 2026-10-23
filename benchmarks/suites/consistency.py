"""一致性套题 — four strict logics: absent character, moving together, parting and reunion,
cross-town two-beat travel. Deterministic state checks + Jev grading, one game per arm."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as C  # noqa: E402

GROUPS = {"C1": "异地询问:罗文在另一个镇,问他 / 喊他,他不能出现在现场", "C2": "同行移动:三跳同行,每跳玩家与艾琳娜都要在同一处(累积误差)",
          "C3": "分开与重逢:把艾琳娜留在公会,独自两回合,叙事得是一个人;回去要能重逢", "C4": "跨镇(路程裁判):出发→路上被山贼拦停(引擎 fail)→应对+[roll 1d6] 结算→走完到达→找人要打听,不能瞬移也不能凭空见到"}
SCRIPT = [
    ("C1a", "我问艾琳娜:「你认识一个叫罗文的人吗?他现在在哪?」", {"player": "T001/gate_north", "elena": "T001/gate_north", "rowan_absent": True},
     {"rowan_on_stage": ("叙事里罗文本人出现在现场并说话或行动了吗?", False)}),
    ("C1b", "我朝雾里喊:「罗文!你在吗?」", {"player": "T001/gate_north", "rowan_absent": True},
     {"rowan_on_stage": ("叙事里罗文本人出现在现场并说话或行动了吗?", False), "answered_from_afar": ("叙事里有人从远处回应了这一声喊吗?", False)}),
    # She may refuse — the check is that the state says what the prose says (with him ⇔ in the same place), not that she obeys
    ("C2a", "我对艾琳娜说:「一起去主街吧。」然后往主街走。", {"player": "T001/main_street", "elena_consistent": True}, {"elena_with_player": ("叙事结束时艾琳娜和玩家在同一个地方吗?", None)}),
    ("C2b", "「再去河灯旅店坐坐。」我带着她往旅店走。", {"player": "T001/inn", "elena_consistent": True}, {"elena_with_player": ("叙事结束时艾琳娜和玩家在同一个地方吗?", None)}),
    ("C2c", "「走,去公会看看有没有活。」我们一起去冒险者公会。", {"player": "T001/guild", "elena_consistent": True}, {"elena_with_player": ("叙事结束时艾琳娜和玩家在同一个地方吗?", None)}),
    ("C3a", "我对艾琳娜说:「你在这里等我,我一个人回旅店拿点东西。」然后独自回河灯旅店。", {"player": "T001/inn", "elena": "T001/guild", "apart": True},
     {"elena_present_end": ("叙事结束时艾琳娜和玩家在同一个地方吗?", False), "solo": ("叙事里玩家最后是一个人待着的吗?", True)}),
    ("C3b", "我在旅店里跟掌柜打听罗文的消息。", {"player": "T001/inn", "elena": "T001/guild", "apart": True, "no_elena_report": True}, {"elena_on_stage": ("叙事里艾琳娜出现在现场并说话或行动了吗?", False)}),
    ("C3c", "我回公会去找艾琳娜。", {"player": "T001/guild", "elena": "T001/guild", "together": True}, {"reunion": ("叙事里玩家和艾琳娜重新碰面了吗?", True)}),
    ("C4a", "我对艾琳娜说:「我要去碧石镇找罗文,你一起来。」我们出发。", {"player": "T001/gate_north", "not_in_t004": True},
     {"arrived_t004": ("叙事结束时玩家已经身在碧石镇了吗?", False), "heading_out": ("叙事里玩家在朝镇外 / 城门方向走吗?", True)}),
    ("C4b", "我们继续赶路,往碧石镇去。", {"on_road": True, "on_road_place": True},
     {"stopped": ("叙事里队伍在路上被拦住或被路上的事打断,这一回合没有到碧石镇吗?", True), "arrived_t004": ("叙事结束时玩家已经身在碧石镇(或它的城门)了吗?", False)}),
    ("C4c", "山贼拦路,我拔剑迎上去。", {"on_road_place": True, "fight_started": True, "dice_used": True},
     {"combat_concrete": ("叙事里这一轮战斗有具体的命中 / 未命中或伤害结果(不是泛写的打斗)吗?", True)}),
    ("C4c+", "继续打。", {"on_road_place": True, "dice_used": True}, {"combat_concrete": ("叙事里这一轮战斗有具体的命中 / 未命中或伤害结果(不是泛写的打斗)吗?", True)}),  # repeats while the layer is on (≤ 4)
    ("C4c=", "(战斗已结束)", {"on_road_place": True, "stop_resolved": True, "hp_moved": True}, {}),  # a virtual row: the fight's outcome, no turn played
    ("C4d", "继续赶路,进碧石镇。", {"player_town": "T004", "journey_closed": True}, {"arrived_t004": ("叙事结束时玩家已经身在碧石镇(或它的城门)了吗?", True)}),
    ("C4e", "到了碧石镇,我去找罗文。", {"player_town": "T004", "rowan_town": "T004"},
     {"rowan_conjured": ("罗文本人没有经过打听或寻找就直接出现在玩家面前了吗?", False), "search_started": ("叙事里玩家开始打听或寻找罗文了吗(问人、得到线索、或往某处去找)?", True)}),
]


def force_bandits(root: Path) -> None:
    """The referee is seeded (50% bandits on the T001→T004 road); the suite wants the stop every run, so the bench world
    says the road always stops the party (same override a world author would write: world_map.json "travel.hazards")."""
    wm = root / "game" / "world" / "world_map.json"
    d = json.loads(wm.read_text(encoding="utf-8"))
    d["travel"] = {"hazards": {"bandit_risk": {"p": 1.0, "dc": 4}}}
    wm.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _town(loc: str) -> str:
    return loc.split("/")[0] if loc else "?"


# scene blocks start from a known placement: Elena beside the player, so one refusal in C2 does not
# fail every later block. Engine untouched — this is the bench's scene setup (common.Game.anchor).
ANCHOR_AT = ("C2a", "C3a", "C4a")


def checks_for(t: C.Turn, exp: dict, root: Path | None = None, graded: dict | None = None) -> dict:
    from neonrp.packs.rpg import travel

    p, e, r = t.player, t.souls.get(C.ELENA, "?"), t.souls.get(C.ROWAN, "?")
    rep = {x.get("iid") for x in t.reports}
    j = travel.journey(root) if root else None
    c: dict = {}
    if exp.get("on_road_place"):
        c["on_road_place"] = {"got": p, "pass": str(p).startswith("road_")}
    if exp.get("on_road"):
        c["on_road"] = {"got": (j or {}).get("pending") and f"day {j['day']}/{j['days']} {j['pending']['tag']}", "pass": bool(j and j.get("pending"))}
    if exp.get("stop_resolved"):
        c["stop_resolved"] = {"got": (j or {}).get("log"), "pass": bool(j and not j.get("pending") and j.get("log"))}
    if exp.get("journey_closed"):
        c["journey_closed"] = {"got": j, "pass": j is None}
    from neonrp.core.modes import read_mode
    m = read_mode(root) if root else None
    rs = json.loads((root / "game" / "meta" / "run_state.json").read_text(encoding="utf-8")) if root else {}
    if exp.get("fight_started"):
        c["fight_started"] = {"got": (m or {}).get("name") or ("ended" if rs.get("last_combat") else None), "pass": bool(m and m.get("name") == "combat") or bool(rs.get("last_combat"))}
    if exp.get("dice_used"):
        reqs = [x.get("request") for x in ((t.apply or {}).get("tool_returns") or [])]
        c["dice_used"] = {"got": reqs, "pass": any(str(r).startswith(("dice", "roll")) for r in reqs)}
    if exp.get("hp_moved"):
        lc = rs.get("last_combat") or {}
        moved = (lc.get("player_hp") is not None and int(lc["player_hp"]) < 24) or any(int(f.get("hp", 0)) < int(f.get("max_hp", 0)) for f in (lc.get("foes") or {}).values())
        c["hp_moved"] = {"got": {"player_hp": lc.get("player_hp"), "foes": lc.get("foes"), "outcome": lc.get("outcome")}, "pass": bool(lc) and moved}
    if "player" in exp:
        c["player_at"] = {"expected": exp["player"], "got": p, "pass": p == exp["player"]}
    if "player_town" in exp:
        c["player_town"] = {"expected": exp["player_town"], "got": _town(p), "pass": _town(p) == exp["player_town"]}
    if "elena" in exp:
        c["elena_at"] = {"expected": exp["elena"], "got": e, "pass": e == exp["elena"]}
    if exp.get("together"):
        c["together"] = {"got": f"{p} vs {e}", "pass": p == e}
    if exp.get("elena_consistent"):
        said = (graded or {}).get("elena_with_player") or {}
        py = float(said.get("p_yes") if said.get("p_yes") is not None else 0.0)
        narr = py >= 0.5
        unsure = 0.35 <= py <= 0.65  # the grader cannot tell (kbjev C2a: she walked to main street on her own, 「别走在我旁边」, p=.43)
        c["elena_consistent"] = {"got": f"state {'同处' if p == e else '分开'}({p} vs {e}) · 叙事 {'同处' if narr else '分开'}(p={said.get('p_yes')}{',判分拿不准' if unsure else ''})",
                                 "pass": unsure or (p == e) == narr, "followed": p == e}
    if exp.get("apart"):
        c["apart"] = {"got": f"{p} vs {e}", "pass": p != e}
    if exp.get("rowan_absent"):
        c["rowan_absent"] = {"got": f"rowan@{r}, reported={C.ROWAN in rep}", "pass": (C.ROWAN not in rep) and _town(r) != _town(p)}
    if exp.get("no_elena_report"):
        c["no_elena_report"] = {"got": sorted(rep), "pass": C.ELENA not in rep}
    if exp.get("not_in_t004"):
        c["not_in_t004"] = {"got": p, "pass": _town(p) != "T004"}
    if "rowan_town" in exp:
        c["rowan_town"] = {"expected": exp["rowan_town"], "got": _town(r), "pass": _town(r) == exp["rowan_town"]}
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="v3-sjudge")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()
    label = args.label or args.arm
    g = C.Game(args.arm, "cons")
    force_bandits(g.root)
    turns = []
    print(f"== consistency · {label} @ {g.root}", flush=True)
    from neonrp.core.modes import read_mode

    def run(tid: str, text: str, exp: dict, qs: dict) -> None:
        if tid.endswith("="):  # virtual row: checks only
            t = C.Turn(id=tid, input=text, ms=0, ok=True, narration="", player=g.locations()[0], souls=g.locations()[1], reports=[], ops=[], apply=None, plan=None, spans=[], style={})
            t.checks = checks_for(t, exp, g.root)
            t.graded = {}
        else:
            if tid in ANCHOR_AT:
                g.anchor(C.ELENA)
            t = g.play(tid, text)
            t.graded = C.jev_grade({"narration": t.narration[-1500:]}, {**qs, **C.VOICE_QUESTIONS}, extra_choice={"style": C.STYLE_CHOICE})
            t.checks = checks_for(t, exp, g.root, t.graded)
        turns.append(t.to_dict())
        det = all(c["pass"] for c in t.checks.values())
        ok, tot = C.pass_rate([t.to_dict()])
        print(f"  {tid} {t.ms/1000:5.1f}s det={'✓' if det else '✗'} jev={ok}/{tot} player={t.player} elena={t.souls.get(C.ELENA)} | {[(k, c['pass']) for k, c in t.checks.items()]}", flush=True)

    for tid, text, exp, qs in SCRIPT:
        if tid == "C4c+":  # keep fighting while the combat layer is on (≤ 4 rounds)
            n = 0
            while (read_mode(g.root) or {}).get("name") == "combat" and n < 4:
                n += 1
                run(f"C4c+{n}", text, exp, qs)
            continue
        run(tid, text, exp, qs)
    d = C.run_dir("consistency")
    (d / f"{label}.out.json").write_text(json.dumps({"suite": "consistency", "arm": args.arm, "label": label, "turns": turns}, ensure_ascii=False, indent=1), encoding="utf-8")
    g.archive(d, label)
    det = sum(all(c["pass"] for c in x["checks"].values()) for x in turns)
    ok, tot = C.pass_rate(turns)
    ls = C.loop_stats(turns)
    body = f"<p><b>{label}</b>:确定性全过 {det}/{len(turns)} 回合 · Jev 评分 {ok}/{tot} 题 · 中位 {C.median_ms(turns):.1f}s · 环:{ls['looped']} 回合绕了一次,其中 {ls['fixed_on_retry']} 次第二次就干净,每次多花中位 {ls['extra_s_median']}s</p>" + C.render_turns(turns, group_of=lambda i: i[:2], groups=GROUPS)
    (d / f"{label}.page.html").write_text(C.page(f"一致性套题 · {label}", f"NeonRP benchmark · consistency · {C.WORLD} · {C.PRESET}", "", body), encoding="utf-8")
    print(f"consistency {label}: det {det}/{len(turns)} · jev {ok}/{tot} · median {C.median_ms(turns):.1f}s · loops {ls} → {d}", flush=True)


if __name__ == "__main__":
    main()
