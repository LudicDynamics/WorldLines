"""Who can come home from the official templates (niko 10-20): only these characters can be taken at an ending, collected
by a plot's rule, rewarded by the truth quiz or gained as a companion; everyone else stays an in-world character (not
takeable, not chattable on the phone unless the author made them standalone). Template data only: ``takeable: false`` on
the soul (every language layer — a layer over a builtin world replaces the file whole), the plot's ``collect`` rules (and
their language layers) without them, a plot NPC's ``props.takeable: false``. Characters already in a player's library
stay there (nothing is revoked)."""
from __future__ import annotations

from pathlib import Path

import pytest

from neonrp import template
from neonrp.core import player_data, truth_quiz
from neonrp.template import i18n

TEMPLATES = Path(__file__).resolve().parents[1] / "worldlines" / "templates"

KEEP = {
    "stoneford-town": {"elena"}, "stoneford-elena": {"elena"}, "stoneford-market": {"elena"}, "stoneford-three-towns": {"elena"},
    "spice-witch": {"maestro"},
    "wuwu": {"vera", "silverkite"},
    "pct-house": {"chara"},
    "guixiang": {"xiulian"},
    "kagura-island": {"hane"},
    "last-train": {"xiacheng"},
    "neon-rebirth": {"akari", "gu", "hawk", "isse", "kujo", "kuon", "nameless", "rin", "shirase", "yomi"},
}
STANDALONE = {"elena", "maestro", "vera"}
CASES = [(tid, lg) for tid in sorted(KEEP) if (TEMPLATES / f"{tid}.template").is_dir()
         for lg in sorted({"zh", *i18n.layers(template.load(TEMPLATES / f"{tid}.template"))})]


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr(player_data, "HOME", tmp_path / "player-data")


@pytest.mark.parametrize("tid,lang", CASES)
def test_only_the_kept_characters_can_come_home(tmp_path, tid, lang):
    t = template.load(TEMPLATES / f"{tid}.template")
    root = tmp_path / "run"
    template.build(t, root, lang=lang)
    souls = player_data.run_souls(root)
    takeable = {s["sid"] for s in souls.values() if s["takeable"]}
    assert takeable == KEEP[tid] & {s["sid"] for s in souls.values()}, (tid, lang, sorted(takeable))
    assert {s["sid"] for s in souls.values() if s["standalone"]} == STANDALONE & {s["sid"] for s in souls.values()}, "standalone stays"
    # the plots' collect rules (merged with this language's layer) name nobody else
    from neonrp.core import settlement

    for info in (settlement._read(settlement._meta(root) / "plots.json", {}) or {}).values():
        pdef = settlement._read(root / str(info.get("dir") or "") / "plot.json", {}) or {}
        assert set(pdef.get("collect") or {}) <= KEEP[tid], (tid, lang, pdef.get("collect"))
    rs = truth_quiz.reward_soul(root) if truth_quiz.applies(root) else None
    if rs is not None:
        assert rs["sid"] in KEEP[tid]


@pytest.mark.parametrize("tid", sorted(t for t in KEEP if (TEMPLATES / f"{t}.template").is_dir()))
def test_the_hub_sees_who_can_come_home(tid):
    take = template.load(TEMPLATES / f"{tid}.template").take
    assert {s for s, w in take.items() if w is not None} == KEEP[tid] & set(take), take


def test_a_character_already_taken_is_not_revoked(tmp_path):
    root = tmp_path / "run"
    template.build(template.load(TEMPLATES / "kagura-island.template"), root)
    player_data._add("characters", {"sid": "yuto", "name": "悠人", "world": "kagura-island", "how": "collect:ending:E01", "memory": "fresh"}, ("sid", "world"))
    iid = next(i for i, s in player_data.run_souls(root).items() if s["sid"] == "yuto")
    assert not player_data.take(root, iid, "settlement", memory="full"), "no longer takeable"
    assert [c["sid"] for c in player_data.read()["characters"]] == ["yuto"], "still in the library"
