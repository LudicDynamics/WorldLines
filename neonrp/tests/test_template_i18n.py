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
WORLDS = ("wuwu", "spice-witch", "stoneford-town", "kagura-island", "guixiang")
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
