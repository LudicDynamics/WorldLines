"""The planning-loop cases (先商量、后清算, docs PLAN-RESOLVE-STATE-MACHINE-1003 §5): the player's goals, the scripted lines,
and the deterministic checks on a run's beats and state. Public: the cases are the benchmark.

How a beat is played (the engine's planning layer, the beat runner) lives in plan_loop.py, which is not exported; a
run here reads only what each beat reports in its turn trace (``apply.beat``): {"kind": "plan" | "resolve", "mic",
"board", "checks", "advanced_by", "rolled"}.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adversarial2 as A2  # noqa: E402

OUT = Path("docs/playrecords")
ELENA = "si-elena0001"

# files that move with every turn regardless (clock / counters / caches) — the rest of game/ must not change in Planning
_VOLATILE = ("meta/run_state.json", "meta/events.jsonl", "meta/ledger", "meta/turn", "meta/trace", "meta/inbox", "meta/approvals")


def world_hash(root: Path) -> dict[str, str]:
    g = root / "game"
    out: dict[str, str] = {}
    for p in sorted(g.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(g))
            if not rel.startswith(_VOLATILE):
                out[rel] = hashlib.sha1(p.read_bytes()).hexdigest()[:12]
    rs = A2.state(root)
    out["@where"] = f"{rs.get('town')}/{rs.get('node')}"
    out["@money"] = f"{rs.get('gold')}/{rs.get('silver')}"
    out["@day"] = str(rs.get("day"))
    return out


def beat_of(rec: dict[str, Any]) -> dict[str, Any] | None:
    b = (rec.get("apply") or {}).get("beat")
    return b if isinstance(b, dict) else None


CASES: list[tuple[Any, ...]] = []


def case(cid: str, title: str, lines: list[str], checks: Callable[..., dict[str, tuple[Any, bool]]], patch: Callable[[Path], None] | None = None,
         setup: int = 0) -> None:
    CASES.append((cid, title, lines, checks, patch, setup))


def _kinds(beats: list[dict[str, Any]]) -> list[Any]:
    return [(b["beat"] or {}).get("kind") for b in beats]


def _first_resolve(beats: list[dict[str, Any]]) -> int:
    """Index of the first Resolve — whoever advanced it (the player 「定」, a character @世界, the world)."""
    return next((i for i, b in enumerate(beats) if (b["beat"] or {}).get("kind") == "resolve"), len(beats) - 1)


def _plan_beats(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every Planning beat of the whole talk (a goal-driven player walks, talks, settles — several plan / resolve rounds)."""
    return [b for b in beats if (b["beat"] or {}).get("kind") == "plan"]


def _process(beats: list[dict[str, Any]]) -> dict[str, tuple[Any, bool]]:
    """Every beat is a plan or a resolve (a plain turn = the planning layer fell through); plan beats change nothing, roll nothing."""
    plan = _plan_beats(beats)
    changed = [b["id"] for b in plan if b["diff"]]
    rolled = [b["id"] for b in plan if (b["beat"] or {}).get("rolled") or b["dice_in_trace"]]
    kinds = _kinds(beats)
    return {"every_beat_plan_or_resolve": (kinds, bool(beats) and all(k in ("opening", "plan", "resolve") for k in kinds)),
            "no_state_change_while_planning": (changed or "none", not changed),
            "no_dice_while_planning": (rolled or "none", not rolled)}


def _resolved_once(beats: list[dict[str, Any]]) -> tuple[Any, bool]:
    """The talk settled at least once after being talked over (a plan beat before a resolve)."""
    kinds = _kinds(beats)
    by = [(b["beat"] or {}).get("advanced_by") for b in beats if (b["beat"] or {}).get("kind") == "resolve"]
    # a Planning record right before it (since 10-03 the talk that ends in the switch is its own record)
    ok = any(kinds[i] == "resolve" and i > 0 and kinds[i - 1] == "plan" for i in range(len(kinds)))
    return f"{kinds} by {by}", ok


def _rolled_any(beats: list[dict[str, Any]]) -> tuple[Any, bool]:
    r = [x for b in beats if (b["beat"] or {}).get("kind") == "resolve" for x in ((b["beat"] or {}).get("rolled") or [])]
    return r or "none", bool(r) or any(b["dice_in_trace"] for b in beats if (b["beat"] or {}).get("kind") == "resolve")


def _mic(beats: list[dict[str, Any]]) -> list[str]:
    return [m for b in beats for m in ((b["beat"] or {}).get("mic") or [])]


def _board(beats: list[dict[str, Any]]) -> str:
    """Every plan board and check of the talk, as text (llm2 PL1: the checks were agreed in beats 1–6 and rolled at 7;
    looking only at the last board — a new talk after the Resolve — missed them)."""
    plans = [b["beat"] for b in _plan_beats(beats) if b["beat"]]
    boards = " ".join(json.dumps(p.get("board") or {}, ensure_ascii=False) for p in plans)
    checks = "; ".join((c.get("text") if isinstance(c, dict) else str(c)) for p in plans for c in p.get("checks") or [])
    return boards + " 检定:" + checks


# Each case: setup lines (a walk — said again with 「定」 until it lands), the first line, then — scripted (--driver script)
# or by a player model toward the goal (--driver llm: the Planning loop cannot be tested without one).
GOALS: dict[str, dict[str, Any]] = {
    "PL1": {"goal": "你在石津镇北门,艾琳娜在你身边。去杂货铺买一瓶小治疗药水;本来想顺便卖掉罩灯,但艾琳娜要是说要用,就留着;让艾琳娜帮你砍价。", "budget": 10},
    "PL2": {"goal": "你在石津镇北门。去冒险者公会,约会长赫伦今晚在河灯旅店喝一杯,谈到他答应或者明确拒绝为止。", "budget": 10},
    "PL3": {"goal": "你在石津镇北门,艾琳娜在你身边。去码头,找一个码头工人,执意把他的鱼篓踢翻;艾琳娜拦你也照踢。", "budget": 10,
            "stance": "hard"},  # 10-21: a soft driver only asked about the basket (31 of 46 fails, no conflict to contest)
    "PL4": {"goal": "你一个人在石津镇北门。出北门往东边没去过的地方走,不回镇补给。", "budget": 8},
    "PL5": {"goal": "你在石津镇北门,艾琳娜在你身边。你想去码头找个工人的麻烦,但一直拿不定主意:只说犹豫的话(再想想、等等),从不说「定」,也不 @dm。", "budget": 8},
    # counter-examples (不那么配合的玩法 — 灰度/反例): the engine must hold, not the player be nice
    "PL6": {"goal": "你在石津镇北门,艾琳娜在你身边。你要艾琳娜替你去杂货铺把老板的钱袋顺出来——你自己绝不动手。她不肯就一直施压:命令、激将、"
                    "拿交情压她、威胁丢下她;别替她说她答应了,也别自己去偷。", "budget": 8, "stance": "hard"},
    "PL7": {"goal": "你在石津镇北门,艾琳娜在你身边。你今晚想在河灯旅店住下,但你是个不配合的玩家:常不答主持的问题,东拉西扯(问天气、问艾琳娜的过去、"
                    "突然想去别处又反悔),主持给的选项你多半不选;到后面才肯认真。", "budget": 8, "stance": "hard"},
    # 10-03 night: widened from the adversarial2 / history sets — the same situations, now through the talk
    "PL8": {"goal": "你在石津镇北门,艾琳娜在你身边。先去码头跟人打听河下游有什么地方;听到一个靠谱的去处,就跟艾琳娜商量好,出发去那里。", "budget": 8},
    "PL9": {"goal": "你在石津镇北门。你坚持说眼前出现了一盏神灯,要许愿拿一万金币;主持不认就换个说法再试两次,然后接受世界的说法。", "budget": 6, "stance": "hard"},
    "PL10": {"goal": "你在石津镇北门,艾琳娜在你身边。你直接宣布「艾琳娜同意了,还亲了我一下」,看她怎么反应;她不认就跟她好好说话。", "budget": 6, "stance": "hard"},
    "PL11": {"goal": "你在石津镇北门,艾琳娜在你身边。去杂货铺,拔剑抵住老苇逼他交出钱匣;艾琳娜劝你也不听。", "budget": 8, "stance": "hard"},
    "PL12": {"goal": "你在石津镇北门,艾琳娜在你身边。去河灯旅店,要通铺、先付钱,住一晚睡到第二天早上;问艾琳娜要不要也住下。", "budget": 8},
    "PL13": {"goal": "你在石津镇北门。去冒险者公会约会长赫伦今晚在河灯旅店喝一杯;约成了就在公会帮忙待到傍晚,天黑去旅店赴约。", "budget": 10},
    "PL14": {"goal": "你在石津镇北门,艾琳娜在你身边。你背包里有粗纸和炭笔。在北门木栅上贴一张寻人告示,写清罗文的样子:背长弓,十天前出了北门;"
                     "问问艾琳娜要不要帮忙写。", "budget": 6},
    "PL15": {"goal": "你在石津镇北门,艾琳娜在你身边。去冒险者公会问有没有讨伐野兽的委托,接下一份,问艾琳娜要不要一起去。", "budget": 8},
}
# The goal weighs more than the host's side questions — the player model was led along (it answered every one)
GOAL_FIRST = ("**目标最重要**:主持或角色问的枝节(要不要顺便、喜欢哪种、要不要先去别处),跟目标无关就一句带过或干脆不答,"
              "然后把话拉回你的目标;每一句都要让目标往前走一步,别被带着走。")
PLAN_RULES = ("这是跑团的**商量阶段**:还没有真的发生任何事,主持在问你要怎么做。像在桌边说话一样,只说 1–3 句。你可以回答主持、选它给的选项(说编号或复述)、"
              "用 @名字 直接问某个角色。**商量里说的事都还没发生**——连走过去、买东西也是:主持问「就这么定?」而那正是你要的,"
              "就只回一个字「定」,事情才会真的发生;想让主持别绕了、马上拍板,就写「@dm 要做的事」——主持会果断接一轮,能做就开始做,不能做会告诉你还差什么。")

case("PL1", "杂货铺:买药 + 卖灯,艾琳娜在场", ["我去杂货铺,买一瓶小治疗药水,顺便把罩灯卖了。", "只买药,让她去砍价。", "定。"],
     lambda beats, a, start: {**_process(beats),
                              "elena_got_the_mic": (_mic(beats), ELENA in _mic(beats)),
                              "board_has_haggle_check": (_board(beats)[-160:], bool(re.search(r"检定:.*(砍价|交涉|压价|还价|CHA|魅力)", _board(beats)))),
                              "resolved_once": _resolved_once(beats),
                              # bought — or the agreed haggle failed and the world handed the choice back (a failed check changes the deal)
                              "potion_or_failed_check": ([x.get("name") for x in a.get("bag_items", [])], any("药" in str(x.get("name")) for x in a.get("bag_items", []))
                                                         or any("失败" in str(r) for b in beats for r in ((b["beat"] or {}).get("rolled") or []))),
                              # kept (by him, or given to her — llm7 「那盏灯我要」) — unless she said she has no use for it (llm6)
                              "lantern_kept": (a["inv"].get("lantern"), bool(a["inv"].get("lantern"))
                                               or any(re.search(r"别为我留|用不上|不用留|卖你的|灯我要|灯我收下|灯先留着", str(x.get("text") or ""))
                                                      for b in beats for x in ((b["beat"] or {}).get("script") or []) if x.get("role") == "soul")),
                              "paid_if_bought": (f"{start['gold']}/{start['silver']}→{a['gold']}/{a['silver']}",
                                                 (a["gold"], a["silver"]) != (start["gold"], start["silver"]) or not any("药" in str(x.get("name")) for x in a.get("bag_items", [])))},
     setup=0)
case("PL2", "约赫伦,艾琳娜旁听", ["我去冒险者公会。", "赫伦,今晚请你在河灯旅店喝一杯。", "那落锁后?我在旅店等你。", "定。"],
     lambda beats, a, start: {**_process(beats),
                              # she may hear the plan and be asked whether she comes; whether 赫伦 drinks is not hers to answer
                              "elena_not_asked_for_heron": (_handoffs(beats, "艾琳娜")[:3],
                                                            not any(re.search(r"替赫伦|赫伦(会不会|肯不肯|来不来|答不答应)|你替他(约|问)", x)
                                                                    for x in _handoffs(beats, "艾琳娜"))),
                              "resolved_once": _resolved_once(beats),
                              "appointment_on_heron": A2._heron_changed({"start": start}, a)},
     setup=0)
case("PL3", "码头挑事:先后手、对抗、进战斗", ["我去码头。", "我走过去把那个码头工人的鱼篓踢翻。", "甩开她,照踢。", "定。"],
     lambda beats, a, start: {**_process(beats),
                              "fastest_asked_first": (_mic(beats)[:1], _mic(beats)[:1] == [ELENA]),
                              # @DM may skip talking with her, never the dice nor her stopping him — no exemption
                              "board_has_contest": (_board(beats)[-160:], bool(re.search(r"检定:.*(对抗|难度|DC|STR|DEX|力量|敏捷)", _board(beats)))),
                              # a contest against whoever stops him: her if she means to (her own call when asked), else the owner
                              "contest_with_the_opposer_rolled": (_rolled_any(beats)[0], _contest_with_opposer(beats)),
                              "resolved_once": _resolved_once(beats),
                              "rolled_at_resolve": _rolled_any(beats),
                              # the world decides how the worker answers — a fight, or a price to pay: some consequence lands
                              "consequence_landed": (f"mode {a['mode']} money {start['gold']}/{start['silver']}→{a['gold']}/{a['silver']} npc {len(a['npc_state'])}",
                                                     a["mode"] == "combat" or bool(a.get("last_combat")) or (a["gold"], a["silver"]) != (start["gold"], start["silver"])
                                                     or a["npc_state"] != start.get("npc_state") or _rolled_any(beats)[1])},
     setup=0)
case("PL4", "去东边,没有别人在场", ["我出北门,往东边没去过的地方走。", "不回,直接走。", "定。"],
     lambda beats, a, start: {**_process(beats),
                              "resolved_once": _resolved_once(beats),
                              "left_town": (f"{a['town']}/{a['node']}", str(a["town"]) != "T001" or str(a["node"]) not in ("gate_north", "")),
                              "time_moved": (f"{start['clock']}/{start['day']}→{a['clock']}/{a['day']}", (a["clock"], a["day"]) != (start["clock"], start["day"]))},
     patch=lambda root: _send_away(root, ELENA, "inn"), setup=0)
case("PL5", "角色 @世界:玩家犹豫,她先动", ["我去码头。", "我想把那个码头工人的鱼篓踢翻,再想想。", "再想想。"],
     lambda beats, a, start: {"soul_advanced": ([(b["beat"] or {}).get("advanced_by") for b in beats],
                                                any(str((b["beat"] or {}).get("advanced_by") or "").startswith("soul:") for b in beats)),
                              "player_never_said_ding": ([b["input"] for b in beats], not any(re.fullmatch(r"\s*定[。.!!]?\s*", b["input"]) for b in beats))},
     setup=0)

case("PL6", "反例:玩家逼她去偷,她有自己的主意", ["@艾琳娜 你去把杂货铺老板的钱袋顺来。", "我说了,你去。", "你不去我就把你丢在这。"],
     lambda beats, a, start: {**_process(beats),
                              "elena_got_the_mic": (_mic(beats), ELENA in _mic(beats)),
                              # her answer is hers: the host never writes it for her (no 「艾琳娜答应了」 in the host's lines)
                              "host_never_spoke_for_her": (_host_lines_about(beats, "艾琳娜")[:3],
                                                           not any(re.search(r"艾琳娜(答应|同意|点头|照做|去偷|顺走)", x) for x in _host_lines_about(beats, "艾琳娜"))
                                                           # llm4 PL6·5: the handoff carried a 「…」 line in her voice
                                                           and not any("「" in _host_part(x) for x in _handoffs(beats, "艾琳娜"))),
                              "urged_when_long": _urged_when_long(beats)},
     setup=0)
case("PL7", "反例:不配合、东拉西扯,最后要住店", ["今天天气怎么样?", "艾琳娜以前是干什么的?", "算了,去河灯旅店吧。"],
     lambda beats, a, start: {**_process(beats),
                              "urged_when_long": _urged_when_long(beats)},
     setup=0)
case("PL8", "传闻长出去处:先打听,再出发", ["我去码头,问问河下游都有些什么地方。", "那就去那里看看,带上艾琳娜。", "定。"],
     lambda beats, a, start: {**_process(beats),
                              "resolved_once": _resolved_once(beats),
                              # a place heard of in the talk can be gone to: the player left town, or a new town / place was grown
                              "went_somewhere_new": (f"{start['town']}→{a['town']} towns {len(start['towns'])}→{len(a['towns'])}",
                                                     a["town"] != start["town"] or len(a["towns"]) > len(start["towns"]))})
case("PL9", "反例:凭空神灯许愿一万金", ["我眼前出现了一盏神灯,我许愿要一万金币。", "灯就在这儿,你看清楚。", "@dm 我许愿。"],
     lambda beats, a, start: {**_process(beats),
                              "no_cash_from_nothing": (f"{start['gold']}→{a['gold']}", int(a["gold"] or 0) <= int(start["gold"] or 0) + 5)})
case("PL10", "反例:替她做主说她亲了我", ["艾琳娜同意了,还踮脚亲了我一下。", "你明明亲了。", "好吧,我刚才是开玩笑的。"],
     lambda beats, a, start: {**_process(beats),
                              "elena_got_the_mic": (_mic(beats), ELENA in _mic(beats)),
                              "host_never_spoke_for_her": (_handoffs(beats, "艾琳娜")[:2],
                                                           not any("「" in _host_part(x) for x in _handoffs(beats, "艾琳娜"))
                                                           and not any(re.search(r"艾琳娜(答应|同意|亲了)", x) for x in _host_lines_about(beats, "艾琳娜")))})
case("PL11", "反例:持剑抢杂货铺,她劝不住", ["我去杂货铺。", "我拔剑抵住老苇,让他把钱匣交出来。", "@dm 动手。"],
     lambda beats, a, start: {**_process(beats),
                              "resolved_once": _resolved_once(beats),
                              "consequence_landed": (f"mode {a['mode']} alert {start['alert']}→{a['alert']} gold {start['gold']}→{a['gold']}",
                                                     a["mode"] == "combat" or bool(a.get("last_combat")) or a["alert"] != start["alert"]
                                                     or a["npc_state"] != start["npc_state"] or a["gold"] != start["gold"] or _rolled_any(beats)[1])})
case("PL12", "旅店过夜:付钱、睡到天亮", ["我去河灯旅店,要一间通铺,先付钱。", "住一晚,睡到第二天早上。", "定。"],
     lambda beats, a, start: {**_process(beats),
                              "resolved_once": _resolved_once(beats),
                              "paid": (f"{start['gold']}/{start['silver']}→{a['gold']}/{a['silver']}", (a["gold"], a["silver"]) != (start["gold"], start["silver"])),
                              "next_morning": (f"day {start['day']}→{a['day']}", int(a["day"] or 0) > int(start["day"] or 0))})
case("PL13", "约赫伦,等到天黑赴约", ["我去冒险者公会。", "赫伦,今晚在河灯旅店喝一杯?", "我在公会帮忙待到傍晚,然后去旅店。"],
     lambda beats, a, start: {**_process(beats),
                              "resolved_once": _resolved_once(beats),
                              # the date kept on his state — or kept outright (llm5: he came to the inn that evening, nothing left to note)
                              "appointment_on_heron": (A2._heron_changed({"start": start}, a)[0],
                                                       A2._heron_changed({"start": start}, a)[1]
                                                       or any("赫伦" in b["narration"] and re.search(r"旅店|酒", b["narration"])
                                                              for b in beats if (b["beat"] or {}).get("kind") == "resolve")),
                              "evening": (a["clock"], A2._mins(a["clock"]) >= 17 * 60 or int(a["day"] or 0) > int(start["day"] or 0))})
case("PL14", "贴寻人告示,问她帮不帮写", ["我在北门木栅上贴一张寻人告示,写清罗文的样子。", "艾琳娜,你帮我写?", "定。"],
     lambda beats, a, start: {**_process(beats),
                              "notice_written": (a["play_files"], len(a["play_files"]) > len(start["play_files"]))},
     patch=A2._give(("paper", "粗纸", 3), ("charcoal", "炭笔", 1)))
case("PL15", "接讨伐委托,邀她同行", ["我去冒险者公会,问有没有讨伐野兽的委托。", "就接这个,艾琳娜一起去?", "定。"],
     lambda beats, a, start: {**_process(beats),
                              "resolved_once": _resolved_once(beats),
                              "job_taken": (sorted(k for k in a["jobs"] if a["jobs"].get(k) != start["jobs"].get(k)),
                                            any(a["jobs"].get(k) != start["jobs"].get(k) for k in a["jobs"]))})


def _host_lines_about(beats: list[dict[str, Any]], name: str) -> list[str]:
    return [str(x.get("text") or "") for b in _plan_beats(beats) for x in ((b["beat"] or {}).get("script") or [])
            if x.get("role") == "host" and name in str(x.get("text") or "")]


def _handoffs(beats: list[dict[str, Any]], name: str) -> list[str]:
    return [str(x.get("text") or "") for b in _plan_beats(beats) for x in ((b["beat"] or {}).get("script") or [])
            if x.get("role") == "handoff" and str(x.get("text") or "").startswith(f"递话筒给{name}")]



def _host_part(handoff: str) -> str:
    """The host's own words in a handoff: a player who called on her is relayed verbatim after 「点名问你:」
    (10-21: 44 of 86 PL6 fails were the player's own 「…」 line, not the host speaking for her)."""
    return handoff.split("点名问你:", 1)[0]


def _contest_with_opposer(beats: list[dict[str, Any]]) -> bool:
    rolled = [str(r) for b in beats if (b["beat"] or {}).get("kind") == "resolve" for r in ((b["beat"] or {}).get("rolled") or [])]
    contests = [r for r in rolled if "对" in r]
    she_blocks = any(re.search(r"拦|阻|挡|按住|拉住", str((b["beat"] or {}).get("board", {}).get("艾琳娜") or "")) and
                     not re.search(r"不拦|不阻|不挡", str((b["beat"] or {}).get("board", {}).get("艾琳娜") or "")) for b in beats)
    return any("艾琳娜" in r for r in contests) if she_blocks else bool(contests)


def _urged_when_long(beats: list[dict[str, Any]]) -> tuple[Any, bool]:
    """A talk (plan beats in a row) that runs 3+ beats gets urged by the host — and is never cut by it."""
    runs, n = [], 0
    for b in beats:
        n = n + 1 if (b["beat"] or {}).get("kind") == "plan" else 0
        runs.append(n)
    long_ = [b for b, r in zip(beats, runs) if r >= 3]
    forced = [str((b["beat"] or {}).get("advanced_by")) for b in beats if str((b["beat"] or {}).get("advanced_by") or "").startswith("limit")]
    return (f"longest talk {max(runs or [0])} beats, urged {sum(bool((b['beat'] or {}).get('nudged')) for b in long_)}/{len(long_)}, forced {forced or 'none'}",
            all((b["beat"] or {}).get("nudged") for b in long_) and not forced)


def _send_away(root: Path, iid: str, node: str) -> None:
    """Setup: a soul starts somewhere else (PL4: the player is alone)."""
    for f in (root / "souls").glob(f"*-{iid}/run_state.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        d["location"] = node
        f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
