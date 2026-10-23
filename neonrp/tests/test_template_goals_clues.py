"""Every story template tells the player what each stage is for and marks its clues (10-15, the standard front end §5.18 /
§5.19): each plot stage is ``{name, goal}`` with a goal in every language the template plays in (the base's four-language
goal, or — where a language moved the story to another stage, 归乡 — the layer's own line), and the plots carry at least
one entry marked ``clue: true``. A built run hands the goal out through the objective endpoint."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp import template
from neonrp.template import i18n

TEMPLATES = Path(__file__).resolve().parents[1] / "worldlines" / "templates"
STORY = ["pct-house", "stoneford-town", "guixiang", "wuwu", "last-train", "spice-witch", "kagura-island", "neon-rebirth"]


def _plots(t: str) -> list[Path]:
    return sorted((TEMPLATES / f"{t}.template" / "plots").glob("*/plot.json"))


def _merged(t: str, plot: Path, lang: str) -> dict:
    base = json.loads(plot.read_text(encoding="utf-8"))
    layer = TEMPLATES / f"{t}.template" / "i18n" / lang / plot.relative_to(TEMPLATES / f"{t}.template")
    return i18n.merge(base, json.loads(layer.read_text(encoding="utf-8"))) if layer.is_file() else base


@pytest.mark.parametrize("t", STORY)
def test_every_stage_has_a_goal_in_every_language(t):
    from neonrp.core.objective import stage_goal, stage_name

    for plot in _plots(t):
        base = json.loads(plot.read_text(encoding="utf-8"))
        names = [stage_name(s) for s in base["stages"]]
        assert all(isinstance(s, dict) and s.get("goal") for s in base["stages"]), (t, plot.parent.name)
        zh = [stage_goal(s, "zh") for s in base["stages"]]
        for lang in ("zh", "en", "ja", "ko"):
            d = _merged(t, plot, lang)
            assert len(d["stages"]) == len(names)
            for i, s in enumerate(d["stages"]):
                g = stage_goal(s, lang)
                assert g and g != stage_name(s), (t, lang, s)
                if lang != "zh":
                    assert g != zh[i], (t, lang, "goal falls back to Chinese (a layer's stage must be {name} or {name, goal})")


@pytest.mark.parametrize("t", STORY)
def test_each_story_marks_its_clues(t):
    clues = []
    for plot in _plots(t):
        d = json.loads(plot.read_text(encoding="utf-8"))
        clues += [eid for eid, e in (d.get("entries") or {}).items() if isinstance(e, dict) and e.get("clue")]
        clues += [cid for cid, c in (d.get("classes") or {}).items() if isinstance(c, dict) and c.get("clue")]
        for eid in [eid for eid, e in (d.get("entries") or {}).items() if isinstance(e, dict) and e.get("clue")]:
            assert d["entries"][eid].get("class") != "place", (t, eid, "a place is not a clue")
    assert clues, t


@pytest.mark.parametrize("t", ["pct-house", "wuwu", "last-train"])
def test_the_run_hands_out_the_first_goal(tmp_path, t):
    from neonrp.core import objective

    dest = tmp_path / "run"
    template.build(template.load(TEMPLATES / f"{t}.template"), dest)
    now = objective.objective(dest, lang="zh")["now"]
    base = json.loads(_plots(t)[0].read_text(encoding="utf-8"))
    assert now and now["goal"] == base["stages"][0]["goal"]["zh"]


@pytest.mark.parametrize("lang", ["zh", "en", "ja", "ko"])
def test_stoneford_town_opens_with_no_commission_in_progress(tmp_path, lang):
    """The built-in board carries Elena's story (the wolves on the Mossbarrow road already taken); in 石津镇 the player
    has taken nothing yet — every commission on the board is an offer, none is active."""
    from neonrp.core import objective
    from neonrp.core.registry import load_registry

    dest = tmp_path / "run"
    template.build(template.load(TEMPLATES / "stoneford-town.template"), dest, lang=lang)
    jobs = {e.id: e.props.get("state") for e in load_registry(dest).of_class("job")}
    assert jobs.get("T001/Q002") == "available", jobs
    assert not [j for j in objective.objective(dest, lang=lang)["jobs"] if j["state"] == "active"]
