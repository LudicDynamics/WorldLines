"""The localized built-in worlds (10-14/15 「本地化,不只是翻译」): every language's run of each world holds no other
language's proper nouns (the world's i18n/glossary.json) and no borrowed rule words, and the plot's souls resolve by
this run's names. The deep lint (``neonrp template lint <t> --i18n-deep``) is the full check; this keeps the runs honest."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from neonrp import template
from neonrp.template import i18n

TPLS = Path(__file__).resolve().parents[1] / "worldlines" / "templates"
WORLDS = ("wuwu", "spice-witch", "stoneford-town", "kagura-island", "guixiang", "pct-house", "neon-rebirth",
          "stoneford-elena", "stoneford-market", "stoneford-three-towns", "werewolf-night-village")  # 10-16: every world
LANGS = ("zh", "en", "ja", "ko")
BANNED = re.compile(r"cthulhu|克苏鲁|\bCoC\b|\bsanity\b|理智|正気度|SAN値|이성|Moss Tomb", re.I)
ENGINE_FILES = ("game/meta/actions.json", "game/meta/play_contract.json")  # the engine's own op / exit keys, not content


def _texts(root: Path) -> dict[str, str]:
    """The run's text files; a picture spec's ``prompt`` (an English image-generation prompt, the image backend's — the
    model never reads it) is left out of a JSON file."""
    def drop(x):
        if isinstance(x, dict):
            return {k: drop(v) for k, v in x.items() if not (k == "prompt" and isinstance(v, str) and ("image" in x or "video" in x))}
        return [drop(v) for v in x] if isinstance(x, list) else x

    out = {}
    for k, v in i18n.run_texts(root).items():
        if k.startswith(".neonrp/"):
            continue
        if k.endswith(".json"):
            try:
                v = json.dumps(drop(json.loads(v)), ensure_ascii=False)
            except ValueError:
                pass
        out[k] = v
    return out


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("world", WORLDS)
def test_a_localized_world_run_holds_one_language(tmp_path, world, lang):
    tpl = TPLS / f"{world}.template"
    root = tmp_path / "run"
    template.build(template.load(tpl), root, lang=lang)
    here = str(TPLS.parents[1])  # the record names the template's path (a checkout's folder name is not content)
    texts = {k: v.replace(here, "") for k, v in _texts(root).items()}
    hits = i18n.residue(texts, i18n.foreign_terms(template.load(tpl), lang))
    assert not hits, {k: v[:3] for k, v in hits.items()}
    banned = {k: sorted(set(BANNED.findall(v))) for k, v in texts.items() if k not in ENGINE_FILES and BANNED.search(v)}
    assert not banned, banned


def test_the_play_contracts_pitch_in_four_languages():
    """A run in any language shows its contract's pitch in that language (10-15: the ko run fell back to English)."""
    for f in sorted((TPLS.parent / "contracts").glob("*.play-contract.json")):
        pitch = json.loads(f.read_text(encoding="utf-8"))["pitch"]
        assert set(LANGS) <= set(pitch) and all(pitch[lg].strip() for lg in LANGS), f.name


@pytest.mark.parametrize("lang,doc", [("en", "Nerve: 0 = Gone under"), ("ja", "平静: 0 = 崩れ"), ("zh", "心神: 0 = 长久失控")])
def test_the_sanity_variable_doc_uses_the_worlds_words(tmp_path, lang, doc):
    """pct's player.san doc goes to the model each turn (10-15): it names the score and its end as the world calls them
    (灰橡宅's 心神 / Nerve), in the run's language — not a fixed English 「SAN: 0 = permanent insanity」."""
    from neonrp.core.registry import load_registry

    root = tmp_path / "run"
    template.build(template.load(TPLS / "pct-house.template"), root, lang=lang)
    assert load_registry(root).variables["player.san"].doc == doc


_HAN = re.compile(r"[一-鿿]")


@pytest.mark.parametrize("lang", ("en", "ja", "ko"))
def test_the_economy_mixin_speaks_the_runs_language(tmp_path, lang):
    """economy's variable docs, op docs and always-on prompt line reach the model each turn (10-15): in a foreign run they
    are in that language — no fixed Chinese (ja / ko may share kanji, so only Chinese-only wording is checked there)."""
    from neonrp.core.adv import ops_lines
    from neonrp.core.registry import load_registry
    from neonrp.packs.mixins import economy

    root = tmp_path / "run"
    template.build(template.load(TPLS / "stoneford-town.template"), root, lang=lang)
    reg = load_registry(root)
    docs = [v.doc for k, v in reg.variables.items() if k.split(".")[0] in ("stock", "price", "inv", "econ")]
    assert docs
    ops = [ln for ln in ops_lines(reg, lang).splitlines() if ln.split()[0] in ("trade", "new_caravan", "haul", "deliver", "rob")]
    entry = economy.MIXIN["prompt"]["entries"][0]["text"][lang]
    zh_only = ("库存", "单价", "商队", "世界规则", "物价指数", "你带着", "这个世界")
    for text in [*docs, *ops, entry]:
        if lang == "en":
            assert not _HAN.search(text), text
        assert not any(w in text for w in zh_only), text


@pytest.mark.parametrize("lang", ("en", "ja", "ko"))
def test_the_rpg_open_schema_ops_have_docs_in_every_language(lang):
    """new_npc / patch / remove are listed to the model every turn (10-15): a foreign run reads them in its language."""
    from neonrp.packs.rpg.pack import ACTIONS

    docs = {a.op: a.doc_for(lang) for a in ACTIONS if a.op in ("new_npc", "patch", "remove")}
    assert set(docs) == {"new_npc", "patch", "remove"}
    assert all(d and "开放" not in d and "新路人" not in d for d in docs.values()), docs


def test_the_image_prompts_the_packs_declare_are_english():
    """rpg's item_icon and economy's caravan_icon go to the image backend (10-15): English reads best there, and the
    record of a foreign run no longer carries Chinese wording."""
    from neonrp.packs.mixins import economy
    from neonrp.packs.rpg.ui import UI

    for p in (UI["prompts"]["item_icon"], economy.MIXIN["ui"]["prompts"]["caravan_icon"]):
        assert p.isascii(), p


def test_the_builtin_dice_skill_has_no_borrowed_rule_words():
    """builtin_skills/dice/SKILL.md is copied into worlds (10-15): neutral words — the ``ruleset="coc"`` value is a code
    identifier of roll_check and stays."""
    text = (Path(__file__).resolve().parents[1] / "src" / "neonrp" / "builtin_skills" / "dice" / "SKILL.md").read_text(encoding="utf-8")
    assert not re.search(r"sanity|CoC 7e|cthulhu", text, re.I)


def test_the_caravan_line_is_in_every_language():
    """economy's caravan class render is listed to the model (10-15): a {lang: text} the engine picks from, not Chinese."""
    from neonrp.packs.mixins import economy

    r = economy.MIXIN["classes"]["caravan"]["render"]
    assert set(r) >= {"zh", "en", "ja", "ko"} and "回合" not in r["en"] and "{left}" in r["en"]


def test_lint_warns_when_a_layer_replaces_a_builtin_worlds_file_and_drops_keys(tmp_path):
    """A layer file over a builtin world's own file replaces it whole (10-15): one with only the display fields would lose
    id / defaults — lint says so; 石津镇's layers (now whole files) do not."""
    t = tmp_path / "x.template"
    (t / "world-overlay").mkdir(parents=True)
    (t / "template.json").write_text(json.dumps({"id": "x", "card": {"title": "标题", "lang": "zh"},
                                                 "world": {"builtin": "stoneford-elena", "overlay": "world-overlay"}}), encoding="utf-8")
    f = t / "i18n" / "en" / "world-overlay" / "agents" / "clock-keeper" / "agent.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"description": "Time-slot narration."}), encoding="utf-8")
    probs, _rep = i18n.lint(template.load(t))
    hit = [p for p in probs if p[1] == "i18n.replaces"]
    assert hit and "agents/clock-keeper/agent.json" in hit[0][3] and "id" in hit[0][3]
    real, _ = i18n.lint(template.load(TPLS / "stoneford-town.template"))
    assert not [p for p in real if p[1] == "i18n.replaces"]


_ORIGINAL_WORK = re.compile(r"\bfate\b|圣杯|聖杯|holy grail|성배|从者|サーヴァント|\bservants?\b|서번트|英灵|英霊|heroic spirit|영령|令咒|令呪|"
                            r"command spell|\bsaber\b|\barcher\b", re.I)


def test_seven_nights_borrows_no_words_from_the_work_it_is_like():
    """七夜 is original (niko 10-14): none of the words of the work it resembles, in any language layer either."""
    tpl = TPLS / "neon-rebirth.template"
    hits = [f"{f.relative_to(tpl)}:{n}" for f in tpl.rglob("*") if f.is_file() and f.suffix in (".json", ".md")
            and "spec" not in f.relative_to(tpl).parts
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if _ORIGINAL_WORK.search(line)]
    assert not hits, hits


def test_a_localized_copy_keeps_its_builder_portraits(tmp_path):
    """The builder's portraits are found in a localized copy too (10-15: the copy links its images to the original, and
    resolving the link put them outside the folder — a false block in every language)."""
    rep = template.lint(template.load(TPLS / "neon-rebirth.template"), i18n_deep=True)
    assert not [p for p in rep["problems"] if p["code"] == "i18n.build" and "player.builder" in p["where"]]


def test_lint_warns_when_a_layers_card_does_not_say_its_language(tmp_path):
    """A layer's card without ``lang`` keeps the main language's (10-15: six ko cards claimed zh)."""
    t = tmp_path / "x.template"
    (t / "i18n" / "ko").mkdir(parents=True)
    (t / "template.json").write_text(json.dumps({"id": "x", "card": {"title": "标题", "lang": "zh"}}), encoding="utf-8")
    (t / "i18n" / "ko" / "template.json").write_text(json.dumps({"card": {"title": "제목"}}), encoding="utf-8")
    probs, _rep = i18n.lint(template.load(t))
    assert [p for p in probs if p[1] == "i18n.card_lang" and "/ko/" in p[2]]


@pytest.mark.parametrize("world", WORLDS)
def test_every_layers_card_says_its_language(world):
    t = template.load(TPLS / f"{world}.template")
    assert not [p for p in i18n.lint(t)[0] if p[1] == "i18n.card_lang"]
    for lg in ("en", "ja", "ko"):
        assert i18n.card(t, lg).get("lang") == lg, (world, lg)
