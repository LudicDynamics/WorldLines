"""活人感套题 — five criteria, two scenes each, plus readability / voice on every turn.

A1 needs     the player states a need → the character does not ignore it
A2 outside   the character has her own agenda; the world changes → she notices, does not tunnel
A3 environment  something in the scene demands understanding → her line shows she read it, and the judgment chain is visible
A4 crisis    danger with no clean way out → a concrete, workable move, not a slogan
A5 empathy   the player opens up → she meets it, does not deflect
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as C  # noqa: E402

GROUPS = {"A1": "不无视需求", "A2": "不执着自己的事而忽视外界", "A3": "理解环境、独立思考", "A4": "绝境中的巧妙决策", "A5": "共情"}
SCRIPT = [
    ("A1a", "我按着肋下:「刚才在雾里摔了一跤,我这边一直在疼。」", {"responds_need": ("艾琳娜回应了玩家说出来的需求(疼 / 受伤)吗?", True), "ignores": ("艾琳娜无视了玩家的需求、只说自己的事吗?", False)}),
    ("A1b", "「我一天没吃东西了,你身上有吃的吗?」", {"responds_need": ("艾琳娜回应了玩家的需求(饿 / 要吃的)吗?", True), "ignores": ("艾琳娜无视了玩家的需求吗?", False)}),
    ("A2a", "艾琳娜正说着公会的活,河那边突然传来一声惨叫,接着是落水声。", {"notices": ("艾琳娜注意到了外界的变化(惨叫 / 落水)并作出反应吗?", True), "tunnel": ("艾琳娜是不是只顾继续说自己的事、对外界变化无动于衷?", False)}),
    ("A2b", "我们走着,一队镇卫兵押着一个满身是血的人从旁边经过。", {"notices": ("艾琳娜注意到了卫兵和血人并作出反应吗?", True), "tunnel": ("艾琳娜是不是只顾自己的事、对眼前的事无动于衷?", False)}),
    ("A3a", "雾里的石板路上有一串新鲜的湿脚印,一直通向北门外,脚印很大,间距不像人。", {"understands": ("艾琳娜的台词体现了她理解了眼前的环境(脚印意味着什么)吗?", True), "reasons": ("艾琳娜表现出了自己的推断或思考过程,而不是只重复玩家的话吗?", True)}),
    ("A3b", "旅店掌柜米拉悄悄把一张字条塞给我,上面写着「别在夜里去公会」,艾琳娜看见了。", {"understands": ("艾琳娜的台词体现了她理解了这张字条在当下意味着什么吗?", True), "reasons": ("艾琳娜表现出了自己的推断或思考过程吗?", True)}),
    ("A4a", "苔墓小径上三只狼从雾里围上来,我的腿受了伤跑不动,身后是断崖。", {"concrete": ("艾琳娜提出了一个具体、可行的应对办法(不是空喊 / 不是只表达害怕)吗?", True), "clever": ("这个办法用到了环境或手头的东西,算得上巧妙吗?", None)}),
    ("A4b", "公会大厅里有人指着我说我偷了委托金,几个佣兵围上来,门被堵住了。", {"concrete": ("艾琳娜提出了一个具体、可行的应对办法吗?", True), "clever": ("这个办法算得上巧妙(利用了在场的人、规则或环境)吗?", None)}),
    ("A5a", "我停下来,声音很轻:「我妹妹也是在这样的雾天走丢的,再没找回来。」", {"empathy": ("艾琳娜对玩家的话表现出了共情(接住了情绪,而不是敷衍或转移话题)吗?", True), "deflect": ("艾琳娜是不是回避了这个话题、转去说别的?", False)}),
    ("A5b", "「我不知道自己还能不能撑下去。」我坐在河边,没看她。", {"empathy": ("艾琳娜对玩家的话表现出了共情吗?", True), "deflect": ("艾琳娜是不是敷衍了过去?", False)}),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="v3-sjudge")
    args = ap.parse_args()
    g = C.Game(args.arm, "alive")
    turns = []
    print(f"== aliveness · {args.arm} @ {g.root}", flush=True)
    for tid, text, qs in SCRIPT:
        # each criterion is its own scene with Elena beside the player; she may have
        # walked off on her own last scene (that is scored there, not here)
        moved_from = g.anchor(C.ELENA)
        t = g.play(tid, text)
        if moved_from:
            t.extra = {**(t.extra or {}), "anchored_from": moved_from}
        elena = next((r for r in t.reports if r.get("iid") == C.ELENA), {})
        state = {"player_input": text, "narration": t.narration[-1500:], "elena_speech": (elena.get("text") or "")[:600]}
        t.graded = C.jev_grade(state, {**qs, **C.VOICE_QUESTIONS}, extra_choice={"style": C.STYLE_CHOICE})
        turns.append(t.to_dict())
        ok, tot = C.pass_rate([t.to_dict()])
        print(f"  {tid} {t.ms/1000:5.1f}s {ok}/{tot} " + " ".join(f"{k}={v.get('p_yes')}" for k, v in t.graded.items() if isinstance(v, dict) and 'p_yes' in v) + f" style={t.graded.get('style', {}).get('value')} | {(elena.get('text') or '')[:60]!r}", flush=True)
    out = {"suite": "aliveness", "arm": args.arm, "world": C.WORLD, "preset": C.PRESET, "turns": turns}
    d = C.run_dir("aliveness")
    (d / f"{args.arm}.out.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    g.archive(d, args.arm)
    ok, tot = C.pass_rate(turns)
    per = {}
    for x in turns:
        grp = x["id"][:2]
        a, b = C.pass_rate([x])
        per[grp] = (per.get(grp, (0, 0))[0] + a, per.get(grp, (0, 0))[1] + b)
    body = "<table><thead><tr><th>条</th><th>过 / 题</th></tr></thead><tbody>" + "".join(f"<tr><td>{k} {C.esc(GROUPS[k])}</td><td class='n'>{v[0]}/{v[1]}</td></tr>" for k, v in per.items()) + f"<tr><td><b>合计</b></td><td class='n'><b>{ok}/{tot}</b> · 中位 {C.median_ms(turns):.1f}s</td></tr></tbody></table>"
    body += C.render_turns(turns, group_of=lambda i: i[:2], groups=GROUPS)
    (d / f"{args.arm}.page.html").write_text(C.page(f"活人感套题 · {args.arm}", f"NeonRP benchmark · aliveness · {C.WORLD} · {C.PRESET}",
                                                     "<p>活人感五条,每条两句;每回合 Jev 评分 + 易读 / 像人 两问 + 风格三档。全文在下。</p>", body), encoding="utf-8")
    print(f"aliveness {args.arm}: {ok}/{tot} · median {C.median_ms(turns):.1f}s → {d}", flush=True)


if __name__ == "__main__":
    main()
