"""A soul whose sprite *is* its portrait (10-24, 香料魔女:作者的 portrait 本来就是全身图,sprite 删掉):
``soul.json`` ``assets: {"sprite": "portrait"}`` — the sprite slot points at the portrait, no copy. The template's slots
(Hub hero · lint) and a built run (stage ``has_sprite`` · ``/api/v1/play/sprite``) both see the portrait as the sprite,
in every language; a pointer can only name the soul's own picture slots; without one a missing sprite stays missing."""
from __future__ import annotations

import json

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import worldmap as W

SPICE = PRODUCT_TEMPLATES / "spice-witch.template"
SOULS = {"maestro": "maestro-si-maestro01", "severin": "severin-si-severin1"}


def test_spice_witch_has_no_sprite_files_only_the_pointer():
    for sid, d in SOULS.items():
        assert not list((SPICE / "world-overlay" / "souls" / d / "assets").glob("sprite.*")), f"{sid}: the sprite file is gone"
        assert json.loads((SPICE / "world" / "souls" / d / "soul.json").read_text(encoding="utf-8"))["assets"] == {"sprite": "portrait"}


def test_the_template_s_sprite_slot_is_the_portrait():
    t = TP.load(SPICE)
    for sid in SOULS:
        assert TP.slot_file(t, f"soul.sprite:{sid}") == TP.slot_file(t, f"soul.portrait:{sid}") is not None


@pytest.mark.parametrize("lang", ("zh", "en", "ja", "ko"))
def test_a_run_shows_the_portrait_as_the_sprite(tmp_path, lang):
    run = tmp_path / "run"
    TP.build(TP.load(SPICE), run, lang=lang)
    for sid in SOULS:
        sprite, portrait = W.soul_asset(run, sid, "sprite"), W.soul_asset(run, sid, "portrait")
        assert sprite is not None and sprite == portrait, f"{lang}/{sid}: the stage stands the portrait up (has_sprite)"


def test_a_pointer_names_only_the_soul_s_own_pictures_and_none_means_none(tmp_path):
    sd = tmp_path / "souls" / "x-si-x01"
    (sd / "assets").mkdir(parents=True)
    (sd / "assets" / "portrait.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (sd / "soul.json").write_text(json.dumps({"sid": "x"}), encoding="utf-8")
    assert W.soul_asset(tmp_path, "x", "sprite") is None, "no pointer: a missing sprite stays missing (the frame / fallback path)"
    for bad in ("../../etc/passwd", "sprite", "cover", ""):
        (sd / "soul.json").write_text(json.dumps({"sid": "x", "assets": {"sprite": bad}}), encoding="utf-8")
        assert W.asset_alias(sd, "sprite") is None and W.soul_asset(tmp_path, "x", "sprite") is None, bad
    (sd / "soul.json").write_text(json.dumps({"sid": "x", "assets": {"sprite": "portrait"}}), encoding="utf-8")
    assert W.soul_asset(tmp_path, "x", "sprite") == sd / "assets" / "portrait.png"
    (sd / "assets" / "sprite.webp").write_bytes(b"RIFF")
    assert W.soul_asset(tmp_path, "x", "sprite") == sd / "assets" / "sprite.webp", "a real sprite still wins over the pointer"
