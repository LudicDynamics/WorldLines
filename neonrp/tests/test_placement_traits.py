"""10-07: placement read only {"traits": {name: weight}}; souls written since ship {"core_traits": [{trait, intensity}]}."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from neonrp.core.placement import trait_weights

ELENA = Path("src/neonrp/templates/stoneford-elena/souls/elena-si-elena0001")


def test_both_shapes():
    assert trait_weights({"traits": {"drive": 1.0, "loneliness": 0.6}}) == {"drive": 1.0, "loneliness": 0.6}
    got = trait_weights({"core_traits": [{"trait": "Gentle", "intensity": 78}, {"trait": "Wary", "intensity": 0.4}]})
    assert got == {"Gentle": 0.78, "Wary": 0.4}
    assert trait_weights({}) == {} and trait_weights({"core_traits": "x"}) == {}


def test_elena_traits_reach_placement(tmp_path):
    from neonrp.core import placement

    d = tmp_path / ELENA.name
    shutil.copytree(ELENA, d)
    rows = json.loads((d / "persona" / "core_traits.json").read_text(encoding="utf-8")).get("core_traits") or []
    strong = {r["trait"] for r in rows if r.get("intensity", 0) >= 70}
    prof = placement._soul_profile(d)
    assert strong and strong <= set(prof["traits"])
    assert set(placement.load_soul_full(d)["persona"]["core_traits"]) >= strong
