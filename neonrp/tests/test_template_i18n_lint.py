"""i18n lint: what is not localization text (team-lead 10-15).

- an image slot's generation prompt (opening.cg / stage_cg ``prompt``: English for the image model) is not checked for
  residue; a ``prompt`` that is text (not under a slot) still is
- an object whose keys are all language codes (``{"zh": …}``, one language written so far) is a text object: a layer
  adding its own language there is not a new key"""
from __future__ import annotations

import json
from pathlib import Path

from neonrp import template
from neonrp.template import i18n


def _tpl(tmp_path: Path) -> Path:
    t = tmp_path / "x.template"
    (t / "plots" / "P").mkdir(parents=True)
    (t / "i18n" / "ja" / "plots" / "P").mkdir(parents=True)
    (t / "template.json").write_text(json.dumps({
        "id": "x", "card": {"title": "灰宅", "lang": "zh"},
        "opening": {"cg": [{"id": "1", "image": "a.webp", "caption": {"zh": "温妮在台阶上"},
                            "prompt": "Winnie waits on the steps with a lantern"}]},
    }), encoding="utf-8")
    (t / "plots" / "P" / "plot.json").write_text(json.dumps({
        "id": "P", "reveal": {"zh": "温妮知道"},
        "stage_cg": {"1": {"image": "s.webp", "caption": {"zh": "温妮"}, "camera": "近景", "prompt": "Winnie leans in"}},
        "entries": {"N1": {"name": "温妮", "props": {"prompt": "Winnie is here"}}},
    }), encoding="utf-8")
    (t / "i18n" / "glossary.json").write_text(json.dumps({"terms": [
        {"id": "soul:chara", "zh": "温妮", "ja": "ウィニー", "en": "Winnie"}]}), encoding="utf-8")
    (t / "i18n" / "ja" / "template.json").write_text(json.dumps({
        "card": {"title": "灰色の館", "lang": "ja"},
        "opening": {"cg": [{"caption": {"ja": "石段でウィニーが待つ"}}]}}), encoding="utf-8")
    (t / "i18n" / "ja" / "plots" / "P" / "plot.json").write_text(json.dumps({
        "reveal": {"ja": "ウィニーは知っている"},
        "stage_cg": {"1": {"caption": {"ja": "ウィニー"}, "camera": "寄り"}},
        "entries": {"N1": {"name": "ウィニー", "props": {"prompt": "ウィニーがいる"}}}}), encoding="utf-8")
    return t


def test_an_image_prompt_is_not_residue_but_text_named_prompt_is(tmp_path):
    t = _tpl(tmp_path)
    probs, rep = i18n.lint(template.load(t))
    res = [p for p in probs if p[1] == "i18n.residue" and p[2] == "i18n/ja"]
    assert not res, res
    p = t / "i18n" / "ja" / "plots" / "P" / "plot.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["entries"]["N1"]["props"]["prompt"] = "Winnie is here"  # a prompt that is not under an image slot: still text
    p.write_text(json.dumps(d), encoding="utf-8")
    probs, _ = i18n.lint(template.load(t))
    assert any(x[1] == "i18n.residue" and x[2] == "i18n/ja" and "'Winnie'" in x[3] and "plot.json" in x[3] for x in probs), probs


def test_a_language_added_to_a_one_language_text_is_not_a_new_key(tmp_path):
    t = _tpl(tmp_path)
    probs, _ = i18n.lint(template.load(t))
    assert not [p for p in probs if p[1] == "i18n.key"], [p for p in probs if p[1] == "i18n.key"]
    p = t / "i18n" / "ja" / "plots" / "P" / "plot.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["reveal"]["hint"] = "x"  # not a language code: still a key the template does not have
    p.write_text(json.dumps(d), encoding="utf-8")
    probs, _ = i18n.lint(template.load(t))
    assert any(x[1] == "i18n.key" and x[2].endswith("reveal.hint") for x in probs), probs


def test_a_text_with_an_authors_note_takes_a_language_too(tmp_path):
    """七夜 terms.json: ``{"zh": …, "en": …, "doc": …}`` — a layer adding ``ja`` is not a new key; a key outside the
    note list still is."""
    t = _tpl(tmp_path)
    (t / "world" / "game" / "rules").mkdir(parents=True)
    (t / "i18n" / "ja" / "world" / "game" / "rules").mkdir(parents=True)
    (t / "world" / "game" / "rules" / "terms.json").write_text(json.dumps(
        {"machine": {"zh": "终章机", "en": "the Finale Engine", "doc": "裁定规则矛盾的机器"}}), encoding="utf-8")
    over = t / "i18n" / "ja" / "world" / "game" / "rules" / "terms.json"
    over.write_text(json.dumps({"machine": {"ja": "終章機", "doc": "規則の矛盾を裁く機械"}}), encoding="utf-8")
    probs, _ = i18n.lint(template.load(t))
    assert not [p for p in probs if p[1] == "i18n.key"], [p for p in probs if p[1] == "i18n.key"]
    over.write_text(json.dumps({"machine": {"ja": "終章機", "alias": "x"}}), encoding="utf-8")
    probs, _ = i18n.lint(template.load(t))
    assert any(p[1] == "i18n.key" and p[2].endswith("machine.alias") for p in probs), probs
