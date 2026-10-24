"""建议里带「@某人」「/技能」(10-16:玩家从来不知道有这两个玩法)。

- 每个出选项的提示词(叙事的 [options] · describe 的 <possible> · ADV 的 <options> · 「再给几个选项」)四语都说了:
  在场有人 → 一条 @名字 …;技能合用 → 一条 /技能名 …;都不合适不硬塞。私有层的叙事提示词(有的话)也一样。
- 「再给几个选项」的提示词里有这一局的技能清单(引擎认的 / 后面那个名字)。
- Jev 挑选项:自然的 @ / / 候选留一个位置。
stub,不调真模型。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from neonrp import prompts as P
from neonrp.core import describe_jev as DJ
from neonrp.core import more_choices as MC
from neonrp.core import system_one as s1
from neonrp.core.registry import load_registry

LANGS = ("zh", "en", "ja", "ko")
AT = re.compile(r"@\S")
SLASH = re.compile(r"/\S")


NO_BRACKETS = {"zh": "方括号", "en": "no brackets", "ja": "括弧で囲まない", "ko": "괄호로 감싸지 않는다"}


def _says_both(text: str) -> bool:
    return bool(AT.search(text)) and bool(SLASH.search(text))


@pytest.mark.parametrize("lang", LANGS)
def test_every_options_prompt_asks_for_at_and_skill(lang):
    narr = next(ln for ln in P._read_md_at(P._DIR, "narrate", lang).splitlines() if ln.startswith("- [options "))
    assert _says_both(narr), narr
    for unit in ("describe", "describe_inline"):
        body = P._read_md_at(P._DIR, unit, lang)
        poss = body.split("<possible>", 1)[1].split("</possible>", 1)[0]
        assert _says_both(poss), (unit, poss)
    assert _says_both(P._read_json_at(P._DIR, "adv", lang)["SPEC"]["options"])
    ch = P._read_json_at(P._DIR, "choices", lang)
    assert _says_both(ch["system"]) and "{skills}" in ch["user"]
    # 10-16 真机:「[暖炉の灰をかき分ける]」—— 每个出选项的地方都说了不加括号
    for t in (narr, poss, P._read_json_at(P._DIR, "adv", lang)["SPEC"]["options"], ch["system"]):
        assert NO_BRACKETS[lang] in t, t


@pytest.mark.parametrize("lang", LANGS)
def test_private_narrate_asks_for_at_and_skill(lang):
    priv = P._private()
    if priv is None or not (priv / f"narrate.{lang}.md").is_file():
        pytest.skip("no private layer here")
    narr = next(ln for ln in (priv / f"narrate.{lang}.md").read_text(encoding="utf-8").splitlines() if ln.startswith("- [options "))
    assert _says_both(narr) and NO_BRACKETS[lang] in narr, narr
    assert _says_both(next(ln for ln in P.text("narrate", lang).splitlines() if ln.startswith("- [options ")))  # what a run gets


class FakeAdapter:
    def __init__(self, raw: str):
        self.raw, self.calls = raw, []

    def generate(self, system, user, tools=None):
        from neonrp.core.llm import LLMResponse

        self.calls.append((system, user))
        return LLMResponse(proposal_text=self.raw, raw_output=self.raw, usage={}, error=None)


def _run(tmp_path: Path, lang: str) -> Path:
    from _paths import PRODUCT_TEMPLATES

    from neonrp import template as TP
    from neonrp.core.output_lang import write_output_lang

    dest = tmp_path / f"run-{lang}"
    TP.build(TP.load(PRODUCT_TEMPLATES / "pct-house.template"), dest)
    write_output_lang(dest, lang)
    return dest


@pytest.mark.parametrize("lang", LANGS)
def test_more_choices_sees_the_skills(tmp_path, lang):
    from neonrp.core import play_menu

    root = _run(tmp_path, lang)
    cat = play_menu.catalog(root, lang)
    names = [str(s["cmd"])[1:] for s in cat["skills"]]
    assert names, "the template has skills"
    fake = FakeAdapter(f"@someone hi\n/{names[0]} look\nwait")
    out = MC.more_choices(root, n=3, adapter=fake)
    system, user = fake.calls[0]
    assert all(n in user for n in names[:3]), "the skills the engine takes after / are in the prompt"
    assert _says_both(system)
    assert any(o.startswith("@") for o in out["options"]) and any(o.startswith("/") for o in out["options"]), "kept as written"


def _reader(state, questions):
    # plain options read as more natural (4) than the @ / / ones (2.5): without the seat they would all fall off
    out = {}
    for k, q in questions.items():
        if q.type == "score":
            c = re.search(r"「(.+?)」|\"(.+?)\"", q.instructions)
            c = (c.group(1) or c.group(2)) if c else ""
            out[k] = s1.Answer("score", 2.5 if c[:1] in ("@", "/") else 4.0)
        elif q.type == "noul":
            out[k] = s1.Answer("noul", 0.05)
        else:
            out[k] = s1.Answer("choice", "none")
    return out


def test_jev_keeps_a_seat_for_at_and_skill(tmp_path, monkeypatch):
    from test_engine_v3 import _install

    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_reader)
    try:
        root = _install(tmp_path)
        reg = load_registry(root)
        poss = ["回北门", "看看柜台", "数数钱", "@老苇 还卖什么", "/侦查 柜台下面"]
        _ops, options, _log = DJ.to_ops(root, reg, "没有变化", poss, "雾还没散。", n_options=3)
        assert len(options) == 3 and any(o.startswith("@") for o in options) and any(o.startswith("/") for o in options), options
        # a low one (score < 2) does not get the seat
        s1.install_stub(lambda st, qs: {k: s1.Answer("score", 1.0 if "@" in q.instructions or "/" in q.instructions else 4.0) if q.type == "score" else s1.Answer("noul", 0.05) for k, q in qs.items()})
        _ops, options, _log = DJ.to_ops(root, reg, "没有变化", poss, "雾还没散。", n_options=3)
        assert not any(o[:1] in ("@", "/") for o in options), options
    finally:
        s1.install_stub(None)


def test_more_choices_takes_plain_lines_the_adapter_flagged(tmp_path):
    """The openai / anthropic adapters look for a proposal JSON and flag plain text — this call asks for plain lines (10-16:
    「再给几个选项」 always came back empty through them)."""
    from neonrp.core.llm import LLMResponse

    class Flagged:
        def generate(self, system, user, tools=None):
            return LLMResponse(raw_output="@someone hi\nwait", usage={}, error="Failed to extract valid proposal JSON from LLM response")

    out = MC.more_choices(_run(tmp_path, "zh"), n=3, adapter=Flagged())
    assert out["options"] == ["@someone hi", "wait"] and "error" not in out
