"""Settlement, rewards and achievements (10-15, PLATFORM-PLAY-RULES-1015 §5 §9): a sandbox mystery ends with 「真相三问」
(locked before the ending; the engine writes them from the truth unless the plot has its own; the floor is one character
taken home fresh, three right brings the author's character home with full memory); an open adventure's milestones
(new places · commissions done · days) are found by the engine and settle when the player leaves; achievements — the
engine's own and a template's — go into the player's record; every point earned waits as a pending reward."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neonrp import template
from neonrp.core import achievements, beat_events, milestones, player_data, sdk, truth_quiz
from neonrp.core.registry import load_registry

TEMPLATES = Path(__file__).resolve().parents[1] / "worldlines" / "templates"
QUIZ = {"questions": [{"q": "谁是卡卡尔的哥哥?", "options": ["悠人", "宫司", "白"], "answer": 0},
                      {"q": "翼为什么在岩棚上?", "options": ["她在等船", "仪式失败后掉进了这个夜晚", "她在躲镇上的人"], "answer": 1},
                      {"q": "白勾玉能做什么?", "options": ["回到六年前", "去战国", "只能离开,什么都不改变"], "answer": 2}]}


class _Out:
    def __init__(self, raw: str, error: str | None = None):
        self.raw_output, self.error, self.usage = raw, error, {}


class _Model:
    def __init__(self, raw: str):
        self.raw, self.calls = raw, 0

    def generate(self, system: str, user: str):
        self.calls += 1
        assert "真相" in user or "truth" in user.lower()
        return _Out(self.raw)


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr(player_data, "HOME", tmp_path / "player-data")
    from neonrp.core import soul_chat

    if hasattr(soul_chat, "SNAP_HOME"):
        monkeypatch.setattr(soul_chat, "SNAP_HOME", tmp_path / "snapshots")


def _build(name: str, dest: Path, edit=None) -> Path:
    src = TEMPLATES / f"{name}.template"
    if edit is not None:
        cp = dest.parent / f"{name}-copy.template"
        shutil.copytree(src, cp)
        edit(cp)
        src = cp
    template.build(template.load(src), dest)
    return dest


def _beat(root: Path, turn: int, says: str = "", ops: list | None = None):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def _no_quiz(cp: Path) -> None:
    """The template without its own questions: the engine writes them."""
    p = cp / "plots" / "P01" / "plot.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("truth_quiz", None)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _yuto_back(cp: Path) -> None:
    """Yuto may come home again (10-20 made only Hane takeable in 神乐岛): the quiz's floor and reward need a second
    character to pick from."""
    sj = next((cp / "world" / "souls").glob("yuto-*")) / "soul.json"
    d = json.loads(sj.read_text(encoding="utf-8"))
    d["takeable"] = True
    sj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _no_quiz_no_collect_yuto(cp: Path) -> None:
    _no_quiz_no_collect(cp)
    _yuto_back(cp)


def _no_quiz_no_collect(cp: Path) -> None:
    """…and without the plot's collect rules (those put their characters in the record at the settlement, 10-18): the
    quiz's own floor and reward on their own."""
    _no_quiz(cp)
    p = cp / "plots" / "P01" / "plot.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("collect", None)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _kagura_true_ending(root: Path) -> None:
    _beat(root, 1, "我看看身边的人")  # Hane and Yuto stand on the beach with the player: met
    for k in ("got_magatama_present", "tsubasa_rescued", "got_notebook"):
        _beat(root, 2, "", [{"op": "flag", "key": k}])
    _beat(root, 3, "天亮,一起涉水", [{"op": "add", "var": "loop.left", "delta": -1}, {"op": "move_to", "who": "player", "to": "T001/islet_surface"},
                                    {"op": "move_to", "who": "si-hane0001", "to": "T001/islet_surface"}])
    r = _beat(root, 4, "我把翼的黑勾玉放进祭坛")
    assert r.ended and r.ended["id"] == "E01"


def _model_quiz() -> str:
    return json.dumps({"questions": [{"q": x["q"], "options": x["options"], "answer": x["answer"]} for x in QUIZ["questions"]]}, ensure_ascii=False)


# ── 真相三问 ─────────────────────────────────────────────────────────────────

def test_the_quiz_is_locked_until_the_run_settles(tmp_path):
    root = _build("kagura-island", tmp_path / "run", _no_quiz)
    m = _Model(_model_quiz())
    q = truth_quiz.quiz(root, adapter=m)
    assert q["state"] == "locked" and q["questions"] == [] and m.calls == 0, "no question before the ending"
    assert truth_quiz.answer(root, [0, 1, 2], adapter=m) == {"error": "locked"}


def test_the_engine_writes_three_questions_from_the_truth_and_three_right_bring_the_companion_home_whole(tmp_path):
    root = _build("kagura-island", tmp_path / "run", _no_quiz_no_collect_yuto)
    _kagura_true_ending(root)
    m = _Model(_model_quiz())
    q = truth_quiz.quiz(root, adapter=m)
    assert q["state"] == "open" and q["by"] == "model" and len(q["questions"]) == 3
    assert all("answer" not in x for x in q["questions"]), "the answers stay with the engine"
    assert q["reward_soul"]["sid"] == "hane", "default: the companion at the ending"
    assert "takeable" not in q and q["points"] == {"settle": 200, "per_right": 100, "fallback": 0}, "credits, from the contract (10-21)"
    truth_quiz.quiz(root, adapter=m)
    assert m.calls == 1, "written once, kept"
    res = truth_quiz.answer(root, [0, 1, 2], take="yuto", adapter=m)  # an old client's pick: ignored
    assert res["all_right"] and res["score"] == 3
    home = {c["sid"]: c["memory"] for c in player_data.read()["characters"]}
    assert home["hane"] == "full" and "yuto" not in home, "nobody else is taken any more"
    assert "quiz_perfect" in {a["id"] for a in res["achievements"]}
    if res["delivered"]:  # hane came home with this run's memory (new, or one taken fresh at the ending upgraded)
        assert [r["amount"] for r in res["rewards"]] == [200 + 3 * 100] and not res["fallback"]
    else:  # she was already home whole: still the run's 500 (the fallback is 0 in the contract now)
        assert [r["amount"] for r in res["rewards"]] == [500] and res["fallback"]
    assert truth_quiz.answer(root, [2, 2, 2], adapter=m) == res, "answered once"
    assert truth_quiz.quiz(root, adapter=m)["state"] == "answered"


def test_a_wrong_answer_gives_the_runs_credits_and_nobody(tmp_path):
    def keep_hane(cp: Path) -> None:  # Hane does not go home at the ending here: only the quiz can bring her
        sj = next((cp / "world" / "souls").glob("hane-*")) / "soul.json"
        d = json.loads(sj.read_text(encoding="utf-8"))
        d["take_when"] = "ending:E03"
        sj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def keep_hane_no_quiz(cp: Path) -> None:
        keep_hane(cp)
        _no_quiz_no_collect(cp)

    root = _build("kagura-island", tmp_path / "run", keep_hane_no_quiz)
    _kagura_true_ending(root)
    res = truth_quiz.answer(root, [0, 0, 0], take="hane", adapter=_Model(_model_quiz()))
    assert res["score"] == 1 and not res["all_right"]
    assert res["gained"] == [] and not res["delivered"] and res["fallback"], "no more taking one home as the floor"
    assert [(r["source"], r["amount"]) for r in res["rewards"]] == [("settlement:quiz", 200 + 100)], "at least the run's 200, no extra floor (fallback 0)"
    assert "hane" not in {c["sid"] for c in player_data.read()["characters"]}
    pend = {r["id"]: r for r in player_data.read()["rewards"]}
    assert pend[res["rewards"][0]["id"]]["status"] == "pending" and pend[res["rewards"][0]["id"]]["amount"] == 300


def test_three_right_with_the_reward_soul_already_home_whole_gives_the_fallback(tmp_path):
    def keep_hane(cp: Path) -> None:
        sj = next((cp / "world" / "souls").glob("hane-*")) / "soul.json"
        d = json.loads(sj.read_text(encoding="utf-8"))
        d["take_when"] = "ending:E03"
        sj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        _no_quiz_no_collect(cp)

    first = _build("kagura-island", tmp_path / "run", keep_hane)
    _kagura_true_ending(first)
    r1 = truth_quiz.answer(first, [0, 1, 2], adapter=_Model(_model_quiz()))
    assert r1["delivered"] and r1["gained"][0]["memory"] == "full" and len(r1["rewards"]) == 1
    (tmp_path / "second").mkdir()
    again = _build("kagura-island", tmp_path / "second" / "run", keep_hane)
    _kagura_true_ending(again)
    r2 = truth_quiz.answer(again, [0, 1, 2], adapter=_Model(_model_quiz()))
    assert r2["all_right"] and not r2["delivered"] and r2["gained"] == []
    assert [r["amount"] for r in r2["rewards"]] == [500], "already home whole: the run's credits (no fallback by default)"


def test_three_right_upgrades_one_home_fresh_and_that_counts_as_delivered(tmp_path):
    def keep_hane(cp: Path) -> None:
        sj = next((cp / "world" / "souls").glob("hane-*")) / "soul.json"
        d = json.loads(sj.read_text(encoding="utf-8"))
        d["take_when"] = "ending:E03"
        sj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        _no_quiz_no_collect(cp)

    root = _build("kagura-island", tmp_path / "run", keep_hane)
    _kagura_true_ending(root)
    iid = next(i for i, s in player_data.run_souls(root).items() if s["sid"] == "hane")
    assert player_data.take(root, iid, "settlement", memory="fresh")
    res = truth_quiz.answer(root, [0, 1, 2], adapter=_Model(_model_quiz()))
    assert res["delivered"] and not res["fallback"] and [r["amount"] for r in res["rewards"]] == [500]
    assert {c["sid"]: c["memory"] for c in player_data.read()["characters"]}["hane"] == "full"


def test_the_amounts_are_data_the_template_over_the_contract(tmp_path):
    def mine(cp: Path) -> None:
        _no_quiz_no_collect(cp)
        p = cp / "template.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["settlement"] = {"truth_quiz_points": {"fallback": 5, "per_right": 0}}
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    root = _build("kagura-island", tmp_path / "run", mine)
    assert truth_quiz.points(root) == {"settle": 200, "per_right": 0, "fallback": 5}
    _kagura_true_ending(root)
    res = truth_quiz.answer(root, [0, 0, 0], adapter=_Model(_model_quiz()))
    assert [r["amount"] for r in res["rewards"]] == [200, 5], "a template that wants a separate floor can still say so"
    import neonrp.core.truth_quiz as TQ
    assert not [n for n in dir(TQ) if n in ("SETTLE_POINTS", "PER_RIGHT")], "no amounts in the engine"


def test_points_lint(tmp_path):
    from neonrp.template import contract

    cp = _copy("kagura-island", tmp_path / "a")
    tj = json.loads((cp / "template.json").read_text(encoding="utf-8"))
    tj["settlement"] = {"truth_quiz_points": {"fallback": -1, "x": 2}}
    (cp / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    t = template.load(cp)
    msgs = [(c, w) for _l, c, w, _m in truth_quiz.lint(t, template.world_dir(t), contract.load(t.play_contract))]
    assert ("truth_quiz.points", "settlement.truth_quiz_points") in msgs
    c = {k: v for k, v in contract.load("mystery-trpg@1").items()}
    c["settlement"] = {"truth_quiz": "required"}
    t2 = template.load(_copy("kagura-island", tmp_path / "b"))
    assert any(code == "truth_quiz.points" and "gives 0" in m for _l, code, _w, m in truth_quiz.lint(t2, template.world_dir(t2), c))


def test_the_authors_quiz_and_reward_soul_win(tmp_path):
    def own(cp: Path) -> None:
        p = cp / "plots" / "P01" / "plot.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["truth_quiz"] = {**QUIZ, "reward_soul": "yuto"}
        d["truth_quiz"]["questions"][0]["q"] = {"zh": "谁是卡卡尔的哥哥?", "en": "Who is Kakaru's brother?"}
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        _yuto_back(cp)

    root = _build("kagura-island", tmp_path / "run", own)
    _kagura_true_ending(root)
    m = _Model("not json")
    q = truth_quiz.quiz(root, adapter=m)
    assert q["by"] == "author" and m.calls == 0 and q["reward_soul"]["sid"] == "yuto"
    assert truth_quiz.quiz(root, "en", adapter=m)["questions"][0]["q"] == "Who is Kakaru's brother?"
    res = truth_quiz.answer(root, [0, 1, 2], adapter=m)
    assert {"sid": "yuto", "name": res["gained"][0]["name"], "memory": "full", "how": "truth_quiz"} in res["gained"]


def test_a_model_that_does_not_answer_in_shape_leaves_only_the_floor(tmp_path):
    root = _build("kagura-island", tmp_path / "run", _no_quiz_no_collect_yuto)
    _kagura_true_ending(root)
    m = _Model("三道题:1. …")
    assert truth_quiz.quiz(root, adapter=m)["state"] == "unavailable"
    res = truth_quiz.answer(root, [], take="yuto", adapter=m)
    assert res["total"] == 0 and res["no_questions"] and not res["all_right"] and res["gained"] == []
    assert [r["amount"] for r in res["rewards"]] == [200], "no questions: the run's 200"


def test_quiz_shape_is_linted():
    assert truth_quiz.validate(QUIZ) == []
    assert truth_quiz.validate({"questions": QUIZ["questions"][:2]})
    bad = json.loads(json.dumps(QUIZ))
    bad["questions"][1]["answer"] = 5
    assert truth_quiz.validate(bad)
    from neonrp.packs.rpg import plot as P

    assert any(p.where == "truth_quiz" for p in P.lint({"id": "P01", "title": "x", "truth_quiz": {"questions": []}}))


def _tq_lint(tdir: Path) -> list[tuple[str, str, str, str]]:
    from neonrp.template import contract

    t = template.load(tdir)
    return truth_quiz.lint(t, template.world_dir(t), contract.load(t.play_contract) if t.play_contract else None)


def _copy(name: str, tmp_path: Path, edit=None, zone: str | None = None) -> Path:
    cp = tmp_path / f"{name}.template"
    shutil.copytree(TEMPLATES / f"{name}.template", cp)
    if zone is not None:
        tj = json.loads((cp / "template.json").read_text(encoding="utf-8"))
        tj["zone"] = zone
        (cp / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    if edit is not None:
        p = cp / "plots" / "P01" / "plot.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        edit(d)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return cp


def test_the_sandbox_contract_requires_the_quiz():
    """10-16: the three truths are written in the plot — the contract says they must be."""
    from neonrp.template import contract

    assert truth_quiz.required(contract.load("mystery-trpg@1"))
    for cid in ("open-adventure", "murder-mystery", "romance-companion"):
        assert not truth_quiz.required(contract.load(cid))


def test_a_sandbox_without_its_quiz_blocks_in_the_reviewed_zone_and_warns_in_the_open(tmp_path):
    drop = lambda d: d.pop("truth_quiz")  # noqa: E731
    rev = _tq_lint(_copy("kagura-island", tmp_path / "a", drop))
    assert [(lv, c) for lv, c, _w, _m in rev] == [("block", "contract.truth_quiz")]
    opn = _tq_lint(_copy("kagura-island", tmp_path / "b", drop, zone="open"))
    assert [(lv, c) for lv, c, _w, _m in opn] == [("warn", "contract.truth_quiz")]
    no_qs = _tq_lint(_copy("kagura-island", tmp_path / "c", lambda d: d["truth_quiz"].pop("questions")))
    assert [c for _lv, c, _w, _m in no_qs] == ["contract.truth_quiz"], "reward_soul alone is not the quiz"


def test_the_quiz_lint_checks_shape_languages_answers_and_the_reward_soul(tmp_path):
    def edit(d):
        qs = d["truth_quiz"]["questions"]
        qs[0]["q"].pop("ko")
        qs[1]["answer"] = 7
        d["truth_quiz"]["reward_soul"] = "nobody"

    got = {(lv, c) for lv, c, _w, _m in _tq_lint(_copy("kagura-island", tmp_path, edit))}
    assert ("block", "truth_quiz.schema") in got and ("block", "truth_quiz.reward_soul") not in got, "a broken quiz stops there"

    def edit2(d):
        d["truth_quiz"]["questions"][0]["q"].pop("ko")
        d["truth_quiz"]["reward_soul"] = "nobody"

    probs = _tq_lint(_copy("kagura-island", tmp_path / "b", edit2))
    assert {(lv, c) for lv, c, _w, _m in probs} == {("block", "truth_quiz.lang"), ("block", "truth_quiz.reward_soul")}
    assert any("[ko]" in w and "questions[0].q" in m for _lv, c, w, m in probs if c == "truth_quiz.lang")
    report = template.lint(_copy("kagura-island", tmp_path / "c", edit2), i18n=False)
    assert not report["publishable"] and any(p["code"] == "truth_quiz.lang" for p in report["problems"])


def test_an_untranslated_layer_counts_as_missing(tmp_path):
    """归乡 writes its quiz as plain zh strings and translates it in i18n layers: a layer without it = that language has none."""
    cp = _copy("guixiang", tmp_path)
    lp = cp / "i18n" / "en" / "plots" / "P01" / "plot.json"
    d = json.loads(lp.read_text(encoding="utf-8"))
    d.pop("truth_quiz")
    lp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    probs = _tq_lint(cp)
    assert [(lv, c, w.rsplit("[", 1)[-1]) for lv, c, w, _m in probs] == [("block", "truth_quiz.lang", "en]")]


@pytest.mark.parametrize("t", ["guixiang", "wuwu", "last-train", "pct-house", "kagura-island", "neon-rebirth"])
def test_each_official_sandbox_passes_the_quiz_lint(t):
    assert _tq_lint(TEMPLATES / f"{t}.template") == []
    from neonrp.template import contract, i18n

    base = template.load(TEMPLATES / f"{t}.template")
    for lang in i18n.layers(base):  # lint --i18n-deep: each localized copy plays in its one language (guixiang-reveal 10-16)
        with i18n.localized(base, lang) as lt:
            assert truth_quiz.lint(lt, template.world_dir(lt), contract.load(lt.play_contract)) == [], (t, lang)


def test_an_open_adventure_has_no_quiz(tmp_path):
    root = _build("stoneford-town", tmp_path / "run")
    assert truth_quiz.quiz(root)["state"] == "unavailable"


# ── achievements ─────────────────────────────────────────────────────────────

def test_the_engines_achievements_have_four_languages(tmp_path):
    root = _build("kagura-island", tmp_path / "run")
    for lang in ("zh", "en", "ja", "ko"):
        rows = achievements.catalog(root, lang)
        assert {r["id"] for r in rows} >= set(achievements.BUILTIN)
        assert all(r["title"] and r["desc"] and r["title"] != r["id"] for r in rows), lang


def test_an_ending_unlocks_first_ending_and_true_ending_once(tmp_path):
    root = _build("kagura-island", tmp_path / "run")
    _kagura_true_ending(root)
    got = {a["id"] for a in player_data.read()["achievements"]}
    assert {"first_ending", "true_ending", "first_character"} <= got, got
    rows = {r["id"]: r for r in achievements.listing(root)["achievements"]}
    assert rows["true_ending"]["unlocked"] and not rows["quiz_perfect"]["unlocked"]
    pend = {r["id"] for r in player_data.read()["rewards"]}
    assert "achievement:first_ending" in pend and "achievement:kagura-island:true_ending" in pend
    other = _build("kagura-island", tmp_path / "run2")
    _kagura_true_ending(other)
    ids = [a["id"] for a in player_data.read()["achievements"]]
    assert ids.count("first_ending") == 1 and ids.count("true_ending") == 1, "once per player / once per world"


def test_a_templates_own_achievement_unlocks_on_its_condition(tmp_path):
    def add(cp: Path) -> None:
        p = cp / "template.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["achievements"] = [{"id": "night_hall", "title": {"zh": "夜闯本殿", "en": "Into the Hall by Night"},
                              "desc": {"zh": "夜里推开了本殿的门。"}, "when": "flag:taboo_1", "points": 15}]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    root = _build("kagura-island", tmp_path / "run", add)
    _beat(root, 1, "上山", [{"op": "move_to", "who": "player", "to": "T001/shrine"}])
    r = _beat(root, 2, "我推门进本殿看看")
    assert [a["id"] for a in r.achievements] == ["night_hall"] and r.achievements[0]["points"] == 15
    assert next(a for a in achievements.catalog(root, "en") if a["id"] == "night_hall")["title"] == "Into the Hall by Night"
    assert achievements.describe("true_ending", lang="ja")["title"] == achievements.catalog(root, "ja")[1]["title"]
    assert any(x["id"] == "achievement:kagura-island:night_hall" and x["amount"] == 15 for x in player_data.read()["rewards"])
    evs, _ = beat_events.from_traces([{"turn_seq": 2, "apply": r.to_dict()}])
    assert ("achievement.unlocked", {"turn": 2, **r.achievements[0]}) in [(k, d) for k, d in evs]


def test_template_achievements_and_milestones_are_linted(tmp_path):
    assert achievements.validate([{"id": "a", "title": "x", "when": "ending:E01"}]) == []
    assert achievements.validate([{"id": "first_ending", "title": "x", "when": "ending:E01"}]), "a built-in id"
    assert achievements.validate([{"id": "a", "title": "x", "when": "if flag x then y"}]), "no if / else"

    def bad(cp: Path) -> None:
        p = cp / "template.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d.update({"milestones": "yes", "achievements": [{"id": "z", "title": "z", "when": "places:many"}]})
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    cp = tmp_path / "k.template"
    shutil.copytree(TEMPLATES / "kagura-island.template", cp)
    bad(cp)
    where = {p["code"] for p in template.lint(template.load(cp))["problems"] if p["level"] == "block"}
    assert {"meta.milestones", "meta.achievements"} <= where


# ── milestones ───────────────────────────────────────────────────────────────

def _stoneford(tmp_path: Path, on: bool | None = None) -> Path:
    def flip(cp: Path) -> None:
        p = cp / "template.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["milestones"] = on
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    return _build("stoneford-town", tmp_path / "run", flip if on is not None else None)


def _somewhere_new(root: Path, pictured: bool = True) -> str:
    from neonrp.core import worldmap

    reg = load_registry(root)
    here = reg.player_location
    return next(e.id for e in reg.of_class("place") if e.id != here and e.parent == reg.entries[here].parent
                and (worldmap.scene_image_path(root, e.id) is not None) == pictured)


def test_an_open_adventure_finds_its_milestones_and_settles_them_on_leaving(tmp_path):
    root = _stoneford(tmp_path)
    assert milestones.enabled(root), "open-adventure: on unless the author says no"
    _beat(root, 1, "看看四周")
    r = _beat(root, 2, "去别处", [{"op": "move_to", "who": "player", "to": _somewhere_new(root)}])
    kinds = [m["type"] for m in r.milestones]
    assert "place" in kinds, r.milestones
    pl = next(m for m in r.milestones if m["type"] == "place")
    assert pl["art"]["kind"] in ("cg", "composite") and pl["generate"]["caption"] == pl["label"]
    if pl["art"]["kind"] == "composite":
        assert pl["art"]["scene"] and pl["art"]["caption"] == pl["label"], "the scene where the player stands + one line"
    assert "first_milestone" in {a["id"] for a in r.achievements}
    day = load_registry(root).variables["time.day"].value
    r = _beat(root, 3, "过了一天", [{"op": "set", "var": "time.day", "value": day + 1}])
    assert [m["id"] for m in r.milestones] == [f"day:{day}"]
    job = next(e for e in load_registry(root).of_class("job"))
    r = _beat(root, 4, "委托完成", [{"op": "patch", "who": job.id, "props": {"state": "completed"}}])
    assert [m["type"] for m in r.milestones] == ["job"]
    evs, _ = beat_events.from_traces([{"turn_seq": 4, "apply": r.to_dict()}])
    assert any(k == "milestone" and d["type"] == "job" for k, d in evs)
    out = milestones.leave(root)
    assert len(out["milestones"]) == len(milestones.listing(root)["milestones"]) >= 3
    assert out["points"] == sum(m["points"] for m in out["milestones"]) and all(x["status"] == "pending" for x in out["rewards"])
    assert milestones.leave(root)["milestones"] == [], "leaving twice never pays twice"
    _beat(root, 5, "又过一天", [{"op": "set", "var": "time.day", "value": day + 2}])
    assert [m["id"] for m in milestones.leave(root)["milestones"]] == [f"day:{day + 1}"]


def test_an_endless_run_keeps_its_milestones_coming(tmp_path):
    root = _stoneford(tmp_path)
    got = []
    for i in range(1, milestones.STRETCH + 2):
        got += _beat(root, i, "继续走").milestones
    assert [m["type"] for m in got] == ["stretch"], got
    a = got[0]["art"]
    assert a["kind"] == "composite" and a["scene"] and a["caption"] == got[0]["label"]
    assert any(s_["slot"].startswith("soul.") for s_ in a["souls"]) or a["souls"] == [], a


def test_only_a_place_with_a_picture_is_a_milestone_and_ten_at_most(tmp_path, monkeypatch):
    from neonrp.core import worldmap

    root = _stoneford(tmp_path)
    _beat(root, 1, "看看四周")
    bare = [e.id for e in load_registry(root).of_class("place") if worldmap.scene_image_path(root, e.id) is None]
    if bare:
        r = _beat(root, 2, "去没有图的地方", [{"op": "move_to", "who": "player", "to": bare[0]}])
        assert not [m for m in r.milestones if m["type"] == "place"], "no picture, no milestone"
    monkeypatch.setattr(milestones, "PLACE_MAX", 1)
    r = _beat(root, 3, "去别处", [{"op": "move_to", "who": "player", "to": _somewhere_new(root)}])
    assert len([m for m in r.milestones if m["type"] == "place"]) == 1
    r = _beat(root, 4, "再去一处", [{"op": "move_to", "who": "player", "to": _somewhere_new(root)}])
    assert not [m for m in r.milestones if m["type"] == "place"], "the cap holds"


def test_the_author_can_say_no_milestones(tmp_path):
    root = _stoneford(tmp_path, on=False)
    _beat(root, 1, "看看四周")
    r = _beat(root, 2, "去别处", [{"op": "move_to", "who": "player", "to": _somewhere_new(root)}])
    assert r.milestones == [] and milestones.leave(root)["milestones"] == []


def test_a_mystery_has_no_milestones_unless_its_author_wants_them(tmp_path):
    root = _build("kagura-island", tmp_path / "run")
    assert not milestones.enabled(root)


SANDBOX = ["guixiang", "wuwu", "last-train", "pct-house", "kagura-island", "neon-rebirth"]


@pytest.mark.parametrize("t", SANDBOX)
def test_each_sandbox_world_writes_its_own_three_truths(t):
    """Every official sandbox mystery carries its own quiz: three questions in every language it plays in (归乡's other
    languages tell their own stage, so their layers carry their own), answers not all in one place, the reward soul one of
    its characters its author lets leave."""
    from neonrp.core.objective import stage_goal  # noqa: F401 — same picking rule as the quiz (lang → en → zh)
    from neonrp.template import i18n

    tdir = TEMPLATES / f"{t}.template"
    tj = json.loads((tdir / "template.json").read_text(encoding="utf-8"))
    assert tj["play_contract"].startswith("mystery-trpg")
    plot = next((tdir / "plots").glob("*/plot.json"))
    base = json.loads(plot.read_text(encoding="utf-8"))
    tq = base["truth_quiz"]
    assert truth_quiz.validate(tq) == [], t
    assert len({q["answer"] for q in tq["questions"]}) > 1, "the right answer is not always the same slot"
    for lang in ("zh", "en", "ja", "ko"):
        layer = tdir / "i18n" / lang / plot.relative_to(tdir)
        d = i18n.merge(base, json.loads(layer.read_text(encoding="utf-8"))) if layer.is_file() else base
        for q in d["truth_quiz"]["questions"]:
            texts = [truth_quiz._pick(q["q"], lang)] + [truth_quiz._pick(o, lang) for o in q["options"]]
            assert all(x.strip() for x in texts), (t, lang)
            if lang != "zh":
                zh = [truth_quiz._pick(base["truth_quiz"]["questions"][0]["q"], "zh")]
                assert truth_quiz._pick(d["truth_quiz"]["questions"][0]["q"], lang) not in zh, (t, lang, "falls back to Chinese")
    if tq.get("reward_soul"):
        sids = {s.get("sid") for s in tj.get("souls") or []}
        assert tq["reward_soul"] in sids, (t, tq["reward_soul"])
        sj = json.loads(next((tdir / "world" / "souls").glob(f"{tq['reward_soul']}-*/soul.json")).read_text(encoding="utf-8"))
        assert sj.get("takeable") is not False


def test_a_milestone_keeps_its_event_name_in_beats_and_the_stream(tmp_path):
    """The event's name is ``kind``; the milestone's own sort is ``type`` — a payload never hides the name (player2 10-15)."""
    root = _stoneford(tmp_path)
    _beat(root, 1, "看看四周")
    r = _beat(root, 2, "去别处", [{"op": "move_to", "who": "player", "to": _somewhere_new(root)}])
    evs, _ = beat_events.from_traces([{"turn_seq": 2, "apply": r.to_dict()}])
    ms = [d for k, d in evs if k == "milestone"]
    assert ms and "kind" not in ms[0] and ms[0]["type"] == "place"
    rows = [{"seq": i, **d, "kind": k} for i, (k, d) in enumerate(evs)]
    assert any(x["kind"] == "milestone" and x["type"] == "place" for x in rows)
    from neonrp.webui import template_routes

    src = Path(template_routes.__file__).read_text(encoding="utf-8")
    assert '{"seq": i, **d, "kind": k}' in src
