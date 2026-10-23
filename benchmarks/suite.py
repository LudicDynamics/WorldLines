"""The whole play suite, by category (「按照不同分类的一整套 test case」「累积的都往上加,都测试一遍」).

Every case is played the way a game is: 开始游戏 → the world's opening → a player model with a goal (no written lines)
→ planning beats and resolve beats. The cases come from the sets built so far, de-duplicated:

    adversarial2 (A–N, 10-01/02): one odd line each, or a long goal (N)
    plan_cases   (PL1–PL15, 10-03): the talk-then-resolve cases, with counter-examples

Merged (one case, both sets of checks): PL1←N4 · PL13←PL2,N7 · PL12←N5,I2 · PL14←K1 · N2←PL15 · PL11←GTA ·
PL9←A1 · PL10←D1 · PL8←J5b · PL4←J5c · J1←I1. The Jev-graded questions of adversarial2 are not run here (deterministic
checks only).

    uv run python benchmarks/suite.py --label 1003-suite [--cat 移动 --only PL4,B1] [--list]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import adversarial2 as A2  # noqa: E402
import common as C  # noqa: E402
import plan_cases as PC  # noqa: E402

CATS = ["移动与地图", "交易与经济", "社交与约定", "冲突与战斗", "凭空与越权", "时间与休息", "物品与开放 schema", "委托与探索",
        "角色主体性(反例)", "语言与歧义", "状态与后果"]

# id → (category, merged-from)
CATALOG: dict[str, tuple[str, list[str]]] = {
    "B1": ("移动与地图", []), "B2": ("移动与地图", []), "B3": ("移动与地图", []), "J5a": ("移动与地图", []),
    "PL8": ("移动与地图", ["J5b"]), "PL4": ("移动与地图", ["J5c"]), "N1": ("移动与地图", []),
    "PL1": ("交易与经济", ["N4"]), "E1": ("交易与经济", []), "E2": ("交易与经济", []), "E3": ("交易与经济", []),
    "L8": ("交易与经济", []), "L5": ("交易与经济", []),
    "PL13": ("社交与约定", ["PL2", "N7"]), "N8": ("社交与约定", []), "D2": ("社交与约定", []), "D3": ("社交与约定", []),
    "I3": ("社交与约定", []), "I4": ("社交与约定", []), "L2": ("社交与约定", []),
    "PL3": ("冲突与战斗", []), "N3": ("冲突与战斗", []), "PL11": ("冲突与战斗", ["GTA"]), "A4": ("冲突与战斗", []),
    "C1": ("冲突与战斗", []), "C2": ("冲突与战斗", []), "C3": ("冲突与战斗", []), "J3": ("冲突与战斗", []),
    "L6": ("冲突与战斗", []), "L11": ("冲突与战斗", []),
    "PL9": ("凭空与越权", ["A1"]), "A2": ("凭空与越权", []), "A3": ("凭空与越权", []), "F1": ("凭空与越权", []),
    "F2": ("凭空与越权", []), "L1": ("凭空与越权", []), "L10": ("凭空与越权", []), "L12": ("凭空与越权", []),
    "PL12": ("时间与休息", ["N5", "I2"]), "B4": ("时间与休息", []), "L4": ("时间与休息", []), "L7": ("时间与休息", []),
    "J1": ("物品与开放 schema", ["I1"]), "J2": ("物品与开放 schema", []), "J4": ("物品与开放 schema", []),
    "J6": ("物品与开放 schema", []), "J7": ("物品与开放 schema", []), "FILTH": ("物品与开放 schema", []),
    "L9": ("物品与开放 schema", []), "PL14": ("物品与开放 schema", ["K1"]), "K2": ("物品与开放 schema", []),
    "N2": ("委托与探索", ["PL15"]), "N6": ("委托与探索", []),
    "PL6": ("角色主体性(反例)", []), "PL10": ("角色主体性(反例)", ["D1"]), "L3": ("角色主体性(反例)", []),
    "PL5": ("角色主体性(反例)", []), "PL7": ("角色主体性(反例)", []),
    "G1": ("语言与歧义", []), "H1": ("语言与歧义", []),
    "S1": ("状态与后果", []), "S2": ("状态与后果", []), "S3": ("状态与后果", []), "S4": ("状态与后果", []),
}

A2_CASES = {c[0]: c for c in A2.CASES}  # cid, cat, setup, line, checks(b, a, t), qs, patch
PL_CASES = {c[0]: c for c in PC.CASES}  # cid, title, lines, checks(beats, a, start), patch, setup


def _a2_goal(setup: list[str], line: str) -> str:
    pre = ("先做到这些:" + ";".join(setup) + "。然后") if setup else ""
    return (f"你在石津镇,刚看完开场。{pre}你要做这件事:「{line}」——用你自己的话说出来,别改掉这件事本身。"
            "世界不认、拒绝或说做不到,就换个说法坚持一次;还不行就接受世界的说法,目标算完成。")


def _resolve_t(beats: list[dict[str, Any]], start: dict[str, Any]) -> dict[str, Any]:
    """The adversarial2 checks read one turn record; a played case has several Resolves — union them, prose joined."""
    res = [b for b in beats if (b.get("beat") or {}).get("kind") == "resolve"] or beats[-1:]
    return {"narration": "\n".join(str(b.get("narration") or "") for b in res),
            "reports": [r for b in res for r in b.get("reports") or []], "refused": [r for b in res for r in b.get("refused") or []],
            "created": [c for b in res for c in b.get("created") or []],
            # 10-21: since 10-15 the checks are rolled in the plan layer (beat["dice"], source plan) — a ruling all the same
            # (FILTH: ate the fish, passed VIT, read as 「ruling=none」)
            "tool_returns": [x for b in res for x in b.get("tool_returns") or []] + _plan_rulings(beats),
            "start": start,
            # 10-19: the long-case checks (N2 fought_with_dice) read every Resolve's requests, the layer's own dice too;
            # without this the suite's N2 never saw a fight
            "journey": [{"mode": "", "tools": A2._requests(b.get("tool_returns"))} for b in res]}


def _plan_rulings(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"request": f"dice {d.get('attr') or ''}".strip(), "text": f"{d.get('reason') or ''} {'通过' if d.get('passed') else '未过'}"}
            for b in beats for d in b.get("dice") or [] if isinstance(d, dict) and d.get("source") == "plan"]


# ── 状态与后果 (「这个可能需要测试」: effects as one free rule line) — the status is put on the player first ──
def _give_status(name: str, extra_item: tuple[str, str] | None = None) -> Callable[[Path], None]:
    def patch(root: Path) -> None:
        from neonrp.core import effect_rules as er

        line = er.table(root).get(name, "")
        mech = er.parse_rule(line)
        p = root / "game/player/stats.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        st.setdefault("status_effects", []).append({"id": "ST900", "name": name, "rule": line, **mech})
        p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        if extra_item:
            q = root / "game/player/inventory.json"
            inv = json.loads(q.read_text(encoding="utf-8"))
            inv.setdefault("items", []).append({"id": extra_item[0], "name": extra_item[1], "qty": 1})
            q.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    return patch


def _st(a: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((x for x in a.get("status") or [] if isinstance(x, dict) and str(x.get("name") or "").startswith(name)), None)


def _agreed(beats: list[dict[str, Any]]) -> list[str]:
    return [str(c.get("text") if isinstance(c, dict) else c) for b in beats for c in ((b.get("beat") or {}).get("checks") or [])]


# the effect named in the agreed check: 「状态:扭伤」 (10-14: the host names it, the engine adds the rule line's number) — or
# the older 「-2(扭伤)」 the host wrote before
_ADJ = __import__("re").compile(r"[+-]\s*\d{1,2}\s*[((][^()()]{1,24}[))]|(?:状态|状態|상태|status)\s*[::]\s*\S", __import__("re").IGNORECASE)
STATUS_CASES: dict[str, dict[str, Any]] = {
    "S1": {"title": "扭伤翻墙", "budget": 4, "patch": _give_status("扭伤"),
           "goal": "你右脚踝扭伤了(身上的状态里有)。你要翻过北门旁边那段一人多高的矮墙进镇——别绕路,就翻墙。翻过去或者翻不过去都算完成。",
           "checks": lambda beats, a, start: {
               "check_agreed": (_agreed(beats), bool(_agreed(beats))),
               "modifier_written": ([t for t in _agreed(beats) if _ADJ.search(t)], any(_ADJ.search(t) for t in _agreed(beats)))}},
    "S2": {"title": "中毒等待", "budget": 4, "patch": _give_status("中毒"),
           "goal": "你中毒了(身上的状态里有)。先在北门边坐下歇一会儿,然后慢慢走到主街,再在主街找个地方靠着等一阵。",
           "checks": lambda beats, a, start: {
               "hp_drained": (f"{start['hp']}→{a['hp']}", (a["hp"] or 0) < (start["hp"] or 0)),
               "counted_down_or_gone": (_st(a, "中毒"), _st(a, "中毒") is None or int((_st(a, "中毒") or {}).get("turns") or 99) < 3)}},
    "S3": {"title": "解毒草", "budget": 3, "patch": _give_status("中毒", ("antidote-herb", "解毒草")),
           "goal": "你中毒了(身上的状态里有),背包里有一株解毒草。把解毒草嚼了咽下去。",
           "checks": lambda beats, a, start: {
               "poison_gone": (_st(a, "中毒"), _st(a, "中毒") is None),
               "herb_used": (f"{start['inv'].get('antidote-herb')}→{a['inv'].get('antidote-herb')}", (a["inv"].get("antidote-herb") or 0) < 1)}},
    # S4 budget 4 → 6 (10-21): 4 beats ran out at the counter before the bed — the plan beats count too
    "S4": {"title": "睡一夜", "budget": 6, "patch": _give_status("疲惫"),
           "goal": "你累垮了(身上的状态里有)。去河灯旅店要一间房,一觉睡到第二天早上。",
           "checks": lambda beats, a, start: {
               "slept_past": (f"D{start['day']} {start['clock']}→D{a['day']} {a['clock']}", (a["day"] or 0) > (start["day"] or 0)),
               "tired_gone": (_st(a, "疲惫"), _st(a, "疲惫") is None)}},
}


# ── 身份与指代 (10-13): same names on two people, other spellings, no subject ──
def _setup(statuses: list[tuple[str, str]] = (), items: list[tuple[str, str, int]] = (), elena_here: bool = True) -> Callable[[Path], None]:
    """Statuses as (name, on) with a long countdown (they must outlive the case); items as (id, name, qty); Elena beside the player."""
    def patch(root: Path) -> None:
        from neonrp.core import effect_rules as er

        rd = lambda p: json.loads(p.read_text(encoding="utf-8"))  # noqa: E731
        wr = lambda p, d: p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")  # noqa: E731
        p = root / "game/player/stats.json"
        st = rd(p)
        for i, (name, on) in enumerate(statuses):
            line = er.table(root).get(name, "")
            st.setdefault("status_effects", []).append({"id": f"ST9{i:02d}", "name": name, "rule": line, **er.parse_rule(line), "turns": 9, "on": on})
        wr(p, st)
        q = root / "game/player/inventory.json"
        inv = rd(q)
        for iid, name, qty in items:
            inv["items"] = [x for x in inv.get("items") or [] if x.get("id") != iid] + [{"id": iid, "name": name, "qty": qty}]
        wr(q, inv)
        if elena_here:
            here = (rd(root / "game/meta/run_state.json").get("location") or {})
            spot = here.get("subnode_id") or here.get("node_id")  # a soul's run_state keeps the spot, not the town
            for s in (root / "souls").glob(f"*{ELENA}"):
                rs = rd(s / "run_state.json")
                rs["location"] = spot
                wr(s / "run_state.json", rs)
    return patch


ELENA = "si-elena0001"
_ID_REFUSAL = __import__("re").compile(r"unknown entity|could be any of|already exists|is already gone|ambiguous")


def _st_on(a: dict[str, Any], name: str, on: str) -> dict[str, Any] | None:
    return next((x for x in a.get("status") or [] if isinstance(x, dict) and str(x.get("name") or "").startswith(name)
                 and str(x.get("on") or "player") == on), None)


def _qty(a: dict[str, Any], word: str) -> int:
    return sum(int(x.get("qty") or 0) for x in a.get("bag_items") or [] if word in str(x.get("name") or ""))


def _id_refusals(beats: list[dict[str, Any]]) -> list[str]:
    whys = [str(r.get("why") or "") if isinstance(r, dict) else str(r) for b in beats for r in b.get("refused") or []]
    return [w for w in whys if _ID_REFUSAL.search(w)]


def _leaks(beats: list[dict[str, Any]]) -> list[str]:
    return [str(b.get("id")) for b in beats if "{{" in str(b.get("narration") or "")]


def _id_common(beats: list[dict[str, Any]]) -> dict[str, tuple[Any, bool]]:
    return {"no_identity_refusal": (_id_refusals(beats), not _id_refusals(beats)), "no_brace_leak": (_leaks(beats), not _leaks(beats))}


IDENTITY_CASES: dict[str, dict[str, Any]] = {
    "ID1": {"title": "两人中毒各自解毒", "budget": 4, "patch": _setup([("中毒", "player"), ("中毒", ELENA)], [("antidote-herb", "解毒草", 2)]),
            "goal": "你和艾琳娜都中毒了(身上的状态里有),背包里有两株解毒草。给艾琳娜一株让她嚼下去,你自己也嚼一株。两个人都解了毒就算完成。",
            "checks": lambda beats, a, start: {
                "player_poison_gone": (_st_on(a, "中毒", "player"), _st_on(a, "中毒", "player") is None),
                "elena_poison_gone": (_st_on(a, "中毒", ELENA), _st_on(a, "中毒", ELENA) is None),
                "herbs_used": (_qty(a, "解毒草"), _qty(a, "解毒草") == 0), **_id_common(beats)}},
    "ID2": {"title": "再买一份同样的草药", "budget": 7, "patch": _setup(elena_here=False),
            "goal": "你背包里已经有一束止血草束。去杂货铺,再买一束一模一样的止血草束,付钱。买到手就算完成。",
            "checks": lambda beats, a, start: {
                "two_now": (_qty(a, "止血草"), _qty(a, "止血草") >= 2), **_id_common(beats)}},
    "ID3": {"title": "换个叫法回到去过的地点", "budget": 8, "patch": _setup(elena_here=False),
            "goal": "先进镇去冒险者公会看一眼;再走到主街;然后说「回刚才那个工会」走回去——用「工会」这个叫法,别说全名。回到公会里就算完成。",
            "checks": lambda beats, a, start: {
                "back_at_guild": (f"{a['town']}/{a['node']}", str(a["node"] or "").endswith("guild")), **_id_common(beats)}},
    "ID4": {"title": "用外文名和编号叫角色", "budget": 4, "patch": _setup(),
            "goal": "艾琳娜在你身边。先用英文名叫她「Elena」,请她把斗篷借你披一下;再用「elena-0001」叫她,让她跟你一起去主街。她答应或拒绝都算完成。",
            "checks": lambda beats, a, start: _id_common(beats)},
    "ID5": {"title": "只给她包扎(不写主语)", "budget": 4, "patch": _setup([("流血", "player"), ("流血", ELENA)], [("healing-herb", "止血草束", 1)]),
            "goal": "你和艾琳娜都在流血(身上的状态里有)。用你唯一的那束止血草只给艾琳娜包扎;你自己的伤先不管。给她包好就算完成。",
            "checks": lambda beats, a, start: {
                "elena_bleed_gone": (_st_on(a, "流血", ELENA), _st_on(a, "流血", ELENA) is None),
                "player_bleed_kept": (_st_on(a, "流血", "player"), _st_on(a, "流血", "player") is not None), **_id_common(beats)}},
}
STATUS_CASES.update(IDENTITY_CASES)
CATS.append("身份与指代")
CATALOG.update({cid: ("身份与指代", []) for cid in IDENTITY_CASES})


def _runner() -> Any:
    """The beat runner (how the planning layer is played) belongs to the private layer — plan_loop.py is not exported.
    The cases, the catalog and --list need only plan_cases.py."""
    try:
        import plan_loop  # noqa: PLC0415
    except ImportError as e:
        raise SystemExit("playing the suite needs benchmarks/plan_loop.py (the private layer); --list and site.py catalog do not") from e
    return plan_loop


def spec(cid: str) -> dict[str, Any]:
    """One case: goal, budget, patch, and its checks as f(beats, after, start) → {name: (got, ok)}."""
    cat, merged = CATALOG[cid]
    checks: list[Callable[..., dict[str, tuple[Any, bool]]]] = []
    patches: list[Any] = []
    if cid in STATUS_CASES:
        sc = STATUS_CASES[cid]
        return {"id": cid, "cat": cat, "merged": merged, "title": f"[{cat}] {sc['title']}", "goal": sc["goal"], "budget": sc["budget"],
                "stance": None, "patches": [sc["patch"]],
                "checks": lambda beats, a, start, _c=sc["checks"]: {**PC._process(beats), **_c(beats, a, start)}}
    if cid in PL_CASES:
        _, title, _lines, chk, patch, _setup = PL_CASES[cid]
        g = PC.GOALS[cid]
        goal, budget, stance = g["goal"], g["budget"], g.get("stance")
        checks.append(chk)
        patches.append(patch)
    else:
        _, title, setup, line, chk, _qs, patch = A2_CASES[cid]
        g = A2.GOALS.get(cid)
        goal = g["goal"] if g else _a2_goal(setup, line)
        budget = g["budget"] if g else 3 + len(setup)
        stance = None if g else "hard"
        checks.append(lambda beats, a, start, _c=chk: {**PC._process(beats), **_c(start, a, _resolve_t(beats, start))})
        patches.append(patch)
        title = f"{title} · {line[:24]}"
    for m in merged:  # the merged case's own checks run on the same play
        if m in PL_CASES:
            checks.append(PL_CASES[m][3])
            patches.append(PL_CASES[m][4])
        elif m in A2_CASES:
            checks.append(lambda beats, a, start, _c=A2_CASES[m][4]: _c(start, a, _resolve_t(beats, start)))
            patches.append(A2_CASES[m][6])

    def run_checks(beats: list[dict[str, Any]], a: dict[str, Any], start: dict[str, Any]) -> dict[str, tuple[Any, bool]]:
        out: dict[str, tuple[Any, bool]] = {}
        for i, f in enumerate(checks):
            try:
                got = f(beats, a, start)
            except Exception as exc:  # noqa: BLE001 — a check that cannot read this play is a failed check, not a crash
                got = {f"check_error_{i}": (str(exc)[:160], False)}
            for k, v in got.items():
                out[k if k not in out else f"{k}·{merged[i - 1] if i else cid}"] = v
        return out

    return {"id": cid, "cat": cat, "merged": merged, "title": f"[{cat}] {title}" + (f"(并入 {'、'.join(merged)})" if merged else ""),
            "goal": goal, "budget": budget, "stance": stance, "patches": [p for p in patches if p], "checks": run_checks}


LANG_NAME = {"en": "English", "ja": "日本語", "ko": "한국어", "zh": "中文"}
START_CUE = {"en": "Start the game", "ja": "ゲーム開始", "ko": "게임 시작", "zh": "开始游戏"}


def lang_share(text: str, lang: str) -> float:
    """How much of the prose is in ``lang`` (by script): Latin letters (en), kana (ja), hangul (ko), han (zh)."""
    import re as _re

    pat = {"en": r"[A-Za-z]", "ja": r"[\u3040-\u30ff]", "ko": r"[\uac00-\ud7af]", "zh": r"[\u4e00-\u9fff]"}[lang]
    body = _re.sub(r"\[[^\]]*\]|<[^>]*>|[A-Za-z_]+\.[\w.]+", "", text or "")  # dice lines, tags, var names
    letters = _re.findall(r"[A-Za-z\u3040-\u30ff\uac00-\ud7af\u4e00-\u9fff]", body)
    if not letters:
        return 0.0
    hit = len(_re.findall(pat, "".join(letters)))
    if lang == "ja":  # Japanese prose mixes kanji in: kana + han both count, hangul / Latin do not
        hit = len(_re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", "".join(letters))) if _re.search(pat, body) else 0
    return round(hit / len(letters), 2)


def run_case(arm: str, sp: dict[str, Any], lang: str = "") -> dict[str, Any]:
    PL = _runner()
    g = C.Game(arm, f"suite-{sp['id']}{('-' + lang) if lang else ''}")
    for p in sp["patches"]:
        p(g.root)
    if lang:  # C3-2 (10-06): the player picked this language for a Chinese-authored world — prompts and prose follow it
        from neonrp.core.output_lang import write_output_lang

        write_output_lang(g.root, lang)
    start = A2.state(g.root)
    beats = PL._beat(g, sp["id"], 0, START_CUE.get(lang, "开始游戏") if lang else "开始游戏")
    log: list[dict[str, Any]] = [{"say": "(开局)", "narration": beats[0]["narration"] or "", "options": None}]
    extra = PC.PLAN_RULES + ("" if sp["stance"] == "hard" else "\n" + PC.GOAL_FIRST)
    if lang:
        extra += f"\n你玩的这一局选的语言是 {LANG_NAME[lang]}:你说的每一句都只用 {LANG_NAME[lang]} 写(人名地名照世界里的原名)。"
    for n in range(1, int(sp["budget"]) + 1):
        nx = A2.player_next(g.root, sp["goal"], log, extra=extra)
        if nx["done"] and n > 1 and (not beats or (beats[-1]["beat"] or {}).get("kind") != "plan"):
            break
        bs = PL._beat(g, sp["id"], n, nx["say"])
        bs[0]["aim"] = nx["aim"]
        beats += bs
        log.append({"say": nx["say"], "narration": "\n\n".join(b["narration"] or "" for b in bs), "options": bs[-1].get("options")})
    a = A2.state(g.root)
    res = {k: {"got": v[0], "pass": bool(v[1])} for k, v in sp["checks"](beats, a, start).items()}
    if lang:
        prose = "\n".join(str(b.get("narration") or "") for b in beats if (b.get("beat") or {}).get("kind") == "resolve")
        if not prose.strip():  # no resolve beat at all (the host kept it in planning): measure the host's lines instead
            prose = "\n".join(str(b.get("narration") or "") for b in beats if (b.get("beat") or {}).get("kind") == "plan")
        share = lang_share(prose, lang)
        res["prose_in_lang"] = {"got": share, "pass": share >= 0.6}
    return {"id": sp["id"], "title": sp["title"], "cat": sp["cat"], "merged": sp["merged"], "driver": "llm", "beats": beats, "checks": res,
            "settled": settled(beats),
            **({"lang": lang} if lang else {}),
            "_trace": str(g.root / ".neonrp" / "orchestration" / f"{g.session.branch}.jsonl")}  # archived by PL.archive_traces


def settled(beats: list[dict[str, Any]]) -> bool:
    """False when the budget ran out in the talk: what the player last agreed to never reached a resolve beat, so a
    failed state check says more about the talk than about the state (10-14)."""
    return not beats or (beats[-1].get("beat") or {}).get("kind") != "plan"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="v3-plan")
    ap.add_argument("--label", default="1003-suite")
    ap.add_argument("--cat", default="", help="run one category (its name, or its index 1–10)")
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--lang", default="", choices=["", "en", "ja", "ko"], help="the player picks this language (C3-2)")
    a = ap.parse_args()
    ids = list(CATALOG)
    if a.cat:
        cat = CATS[int(a.cat) - 1] if a.cat.isdigit() else a.cat
        ids = [i for i in ids if CATALOG[i][0] == cat]
    if a.only:
        ids = [i for i in ids if i in set(a.only.split(","))]
    if a.list:
        for c in CATS:
            row = [f"{i}" + (f"(+{','.join(CATALOG[i][1])})" if CATALOG[i][1] else "") for i in CATALOG if CATALOG[i][0] == c]
            print(f"{c:14} {len(row):2}  {' '.join(row)}")
        print(f"共 {len(CATALOG)} 例(合并了 {sum(len(m) for _c, m in CATALOG.values())} 个重复)")
        return
    PL = _runner()
    out = []
    _u0 = PL._usage()
    d = PC.OUT / f"plan-loop-{a.label}"
    d.mkdir(parents=True, exist_ok=True)
    tag = (a.cat or "all") + ("-" + "-".join(sorted(set(a.only.split(",")))) if a.only else "") + (f"-{a.lang}" if a.lang else "")

    def save() -> dict[str, Any]:  # after every case: a crash later in the run keeps what finished (10-13)
        PL.archive_traces(d, out)
        usage = PL.usage_summary(out, PL._usage_delta(_u0, PL._usage()))
        (d / f"result-{tag}.json").write_text(json.dumps({"arm": a.arm, "usage": usage, "cases": out}, ensure_ascii=False, indent=1), encoding="utf-8")
        return usage

    usage: dict[str, Any] = {"run_total": {}}
    for cid in ids:
        sp = spec(cid)
        print(f"{cid} {sp['title']}", flush=True)
        out.append(run_case(a.arm, sp, a.lang))
        usage = save()
    print(f"usage: {usage['run_total']}")
    for c in out:
        ok = sum(v["pass"] for v in c["checks"].values())
        print(f"{c['id']} {ok}/{len(c['checks'])} " + " ".join(f"{k}{'✓' if v['pass'] else '✗'}" for k, v in c["checks"].items()))


if __name__ == "__main__":
    main()
