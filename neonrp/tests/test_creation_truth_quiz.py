"""The 「真相三问」 on the creation desk (PLATFORM-PLAY-RULES-1015 §11, 10-18 「都做」): a creator writes and edits a
plot's ``truth_quiz`` (three questions · options · the right answer · ``reward_soul`` from the world's cast) and can have
the engine draft them from the truth (「点生成」, then edit).

- the form carries a ``truth_quiz`` part when the template opens creation and plays under ``mystery-trpg`` (or lists it in
  ``creation.add``): n · options · the cast to pick the reward from · required only when no plot of its own has them
- check: shape (the run's own validate) · every text written · the reward soul in the cast and allowed to leave
- the draft: the creation provider writes four-language questions from the reveal → parsed + checked; a model that does
  not answer in shape is an error, not a crash
- saved into the creator's work, the run plays the creator's questions when it reaches the creator's ending
- route: POST …/<template>/creation/truth-quiz/generate"""
from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from neonrp import template as TP
from neonrp.core import player_data, sdk, truth_quiz
from neonrp.core.registry import load_registry
from neonrp.template import creation, creation_quiz as CQ

TPLS = Path(__file__).resolve().parents[1] / "worldlines" / "templates"
L4 = lambda zh, en, ja, ko: {"zh": zh, "en": en, "ja": ja, "ko": ko}  # noqa: E731
QS = [{"q": L4("谁把钥匙藏进了井里?", "Who hid the key in the well?", "鍵を井戸に隠したのは誰?", "열쇠를 우물에 숨긴 사람은?"),
       "options": [L4("莲妹", "Lian", "蓮", "연"), L4("族长", "The elder", "族長", "족장"), L4("没人", "No one", "誰も", "아무도")], "answer": 1},
      {"q": L4("钥匙开哪扇门?", "Which door does the key open?", "鍵はどの扉を開ける?", "열쇠는 어느 문을 여나?"),
       "options": [L4("祠堂", "The hall", "祠堂", "사당"), L4("仓房", "The barn", "納屋", "곳간")], "answer": 0},
      {"q": L4("他为什么藏?", "Why did he hide it?", "なぜ隠した?", "왜 숨겼나?"),
       "options": [L4("怕人知道族谱", "To keep the register secret", "族譜を隠すため", "족보를 숨기려고"),
                   L4("忘了", "He forgot", "忘れた", "잊었다"), L4("开玩笑", "A joke", "冗談", "농담")], "answer": 0}]
WORK = {"reveal": "族长把祠堂的钥匙藏进了井里,怕人看见族谱最后一页。",
        "ending": [{"title": "开祠堂", "kind": "true", "text": "门开了。"}],
        "rule": [{"trigger": {"when": {"text": "player"}, "if": [{"text": "打开祠堂"}], "then": [{"to": "end", "ending": "#1"}], "once": True}}],
        "truth_quiz": {"questions": QS, "reward_soul": "xiulian"}}


class _Out:
    def __init__(self, raw: str, error: str | None = None):
        self.raw_output, self.error, self.usage = raw, error, {}


class _Model:
    def __init__(self, raw: str):
        self.raw, self.calls = raw, []

    def generate(self, system: str, user: str):
        self.calls.append((system, user))
        return _Out(self.raw)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    ro, mine = tmp_path / "official", tmp_path / "mine"
    for n in ("guixiang", "stoneford-town", "last-train"):
        shutil.copytree(TPLS / f"{n}.template", ro / f"{n}.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    monkeypatch.setattr(player_data, "HOME", tmp_path / "player-data")
    return mine


def _t(tid):
    return TP.load(TP.discover()[tid])


def test_the_form_opens_the_quiz_for_mystery_templates(desk):
    gx = creation.form(_t("guixiang"))["truth_quiz"]
    assert gx["n"] == 3 and gx["options"] == 3 and gx["langs"] == ["zh", "en", "ja", "ko"] and gx["lang"] == "zh"
    assert gx["souls"] == [{"sid": "xiulian", "name": gx["souls"][0]["name"], "takeable": True}] and gx["reward_default"] == "xiulian"
    assert gx["points"] == {"settle": 200, "per_right": 100, "fallback": 0}, "the contract's amounts, for the preview"
    assert gx["required"] is False, "归乡's own P01 has its three: the creator's are their plot's, not a must"
    assert {s["sid"] for s in creation.form(_t("last-train"))["truth_quiz"]["souls"]} >= {"xiacheng", "laohe"}
    assert "truth_quiz" not in creation.form(_t("stoneford-town")), "an open adventure has no truth to ask about"


def test_required_when_the_contract_needs_it_and_no_plot_has_it(desk):
    p = desk.parent / "official" / "guixiang.template" / "plots" / "P01" / "plot.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("truth_quiz")
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert creation.form(_t("guixiang"))["truth_quiz"]["required"] is True
    base = {k: v for k, v in WORK.items() if k != "truth_quiz"}
    assert "truth_quiz: required" in creation.check(_t("guixiang"), base)
    assert creation.check(_t("guixiang"), WORK) == []


def test_check_says_what_is_wrong(desk):
    t = _t("guixiang")
    assert creation.check(t, WORK) == []
    two = {**WORK, "truth_quiz": {"questions": QS[:2]}}
    assert any("must be a list of 3" in p for p in creation.check(t, two))
    bad = json.loads(json.dumps(WORK))
    bad["truth_quiz"]["questions"][0]["answer"] = 5
    assert any("questions[0].answer" in p for p in creation.check(t, bad))
    blank = json.loads(json.dumps(WORK))
    blank["truth_quiz"]["questions"][1]["options"][1] = {"zh": "", "en": ""}
    assert "truth_quiz.questions[1].options[1]: required" in creation.check(t, blank)
    who = {**WORK, "truth_quiz": {**WORK["truth_quiz"], "reward_soul": "nobody"}}
    assert any("'nobody' is not in the cast" in p for p in creation.check(t, who))
    assert "the template does not ask for the three truth questions" in creation.check(_t("stoneford-town"), {"truth_quiz": {"questions": QS}})
    assert creation.check(t, {**WORK, "truth_quiz": {"questions": [], "reward_soul": ""}}) == [], "an emptied quiz = none"


def test_a_soul_that_cannot_leave_is_no_reward(desk):
    sj = next((desk.parent / "official" / "guixiang.template").rglob("souls/xiulian*/soul.json"))
    d = json.loads(sj.read_text(encoding="utf-8"))
    d["takeable"] = False
    sj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    part = creation.form(_t("guixiang"))["truth_quiz"]
    assert part["souls"][0]["takeable"] is False and part["reward_default"] is None
    assert any("cannot leave the world" in p for p in creation.check(_t("guixiang"), WORK))


def test_to_plot_drops_empty_languages(desk):
    tq = {"questions": [{**QS[0], "q": {"zh": "只写了中文", "en": " "}}, *QS[1:]], "reward_soul": " xiulian "}
    out = creation.to_plot({"truth_quiz": tq}, "mine")["truth_quiz"]
    assert out["questions"][0]["q"] == "只写了中文" and out["questions"][0]["options"][0] == QS[0]["options"][0]
    assert out["reward_soul"] == "xiulian"
    assert "truth_quiz" not in creation.to_plot({"truth_quiz": {"questions": []}}, "mine")


# ── 点生成 ──────────────────────────────────────────────────────────────────

def test_generate_drafts_four_language_questions_from_the_reveal(desk):
    m = _Model("好的:\n" + json.dumps({"questions": QS}, ensure_ascii=False))
    res = CQ.generate(_t("guixiang"), reveal=WORK["reveal"], story="结局:开祠堂", lang="zh", adapter=m)
    assert res["ok"] and res["questions"] == QS and res["reward_soul"] == "xiulian" and res["problems"] == []
    system, user = m.calls[0]
    assert WORK["reveal"] in user and "开祠堂" in user and "zh, en, ja, ko" in user
    assert creation.check(_t("guixiang"), {**WORK, "truth_quiz": {k: res[k] for k in ("questions", "reward_soul")}}) == []


def test_generate_falls_back_to_the_template_truth_and_tolerates_one_language(desk):
    one = {"questions": [{"q": "a?", "options": ["x", "y", "z"], "answer": 2}] * 3}
    m = _Model(json.dumps(one))
    res = CQ.generate(_t("guixiang"), lang="en", adapter=m)
    assert res["ok"] and res["questions"][0] == {"q": {"en": "a?"}, "options": [{"en": "x"}, {"en": "y"}, {"en": "z"}], "answer": 2}
    assert "Luo clan" in m.calls[0][1], "the template plot's own reveal, in the desk language"


@pytest.mark.parametrize("raw,err", [("不会", None), (json.dumps({"questions": QS[:2]}), None), ("", "boom")])
def test_a_model_out_of_shape_is_an_error(desk, raw, err):
    class M(_Model):
        def generate(self, system, user):
            return _Out(raw, err)

    assert CQ.generate(_t("guixiang"), reveal="x", adapter=M(raw)) == {"ok": False, "error": "model"}


def test_no_truth_no_draft(desk):
    gx = desk.parent / "official" / "guixiang.template"
    p = gx / "plots" / "P01" / "plot.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("reveal")
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (gx / "world" / "game" / "lore" / "gm-truth.md").unlink()
    m = _Model("{}")
    assert CQ.generate(_t("guixiang"), adapter=m) == {"ok": False, "error": "no_truth"} and not m.calls
    assert CQ.generate(_t("stoneford-town"), reveal="x", adapter=m) == {"ok": False, "error": "closed"}


# ── 存 → 游戏里触发 ─────────────────────────────────────────────────────────

def test_the_saved_questions_play_when_the_run_reaches_the_creators_ending(desk, tmp_path):
    w = creation.save(_t("guixiang"), WORK, work_id="guixiang-mine")
    plot = json.loads((w.dir / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))
    assert plot["truth_quiz"] == {"questions": QS, "reward_soul": "xiulian"}
    assert not [p for p in TP.lint(w.dir)["problems"] if p["code"].startswith(("truth_quiz", "contract.truth_quiz"))], "four languages lint clean"
    root = tmp_path / "run"
    TP.build(w, root)
    r = sdk.apply(root, [], load_registry(root), turn=1, player_says="我打开祠堂", narration="")
    assert r.ended and r.ended["id"] == "mine_E1"
    q = truth_quiz.quiz(root, "en", adapter=_Model("{}"))
    assert q["state"] == "open" and q["by"] == "author"
    assert [x["q"] for x in q["questions"]] == [x["q"]["en"] for x in QS], "the creator's, not the template's P01"
    assert q["reward_soul"]["sid"] == "xiulian"
    res = truth_quiz.answer(root, [1, 0, 0], lang="en", adapter=_Model("{}"))
    assert res["all_right"] and res["answer"] == [1, 0, 0]


def test_the_template_quiz_still_plays_on_its_own_ending(desk, tmp_path):
    root = tmp_path / "run"
    TP.build(_t("guixiang"), root)
    own = json.loads((desk.parent / "official" / "guixiang.template" / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    assert truth_quiz.spec(root)["questions"] == own["truth_quiz"]["questions"]


# ── 路由 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def server(desk, tmp_path, monkeypatch):
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        srv = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{srv.server_address[1]}"
        finally:
            srv.shutdown()


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_the_generate_route(server, monkeypatch):
    m = _Model(json.dumps({"questions": QS}, ensure_ascii=False))
    monkeypatch.setattr(CQ, "_adapter", lambda: m)
    base = f"{server}/api/v1/local/templates"
    st, body = _post(f"{base}/guixiang/creation/truth-quiz/generate", {"reveal": WORK["reveal"], "lang": "ja"})
    assert st == 200 and body["ok"] and body["questions"] == QS
    assert _post(f"{base}/stoneford-town/creation/truth-quiz/generate", {})[0] == 400
    monkeypatch.setattr(CQ, "_adapter", lambda: _Model("nope"))
    assert _post(f"{base}/guixiang/creation/truth-quiz/generate", {"reveal": "x"}) == (502, {"ok": False, "error": "model"})
    with urllib.request.urlopen(f"{base}/guixiang/creation", timeout=20) as r:
        assert json.loads(r.read())["truth_quiz"]["reward_default"] == "xiulian"
