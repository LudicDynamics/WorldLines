"""捏人头像字段的 default(10-15):不捏人直接开局(或草稿没选头像)时,玩家头像用这个选项;世界自己给了玩家头像就不覆盖;
default 必须是选项之一(lint)。七夜的 default = 中性的 reader-n。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import worldmap
from neonrp.template import builder

TPL = PRODUCT_TEMPLATES / "neon-rebirth.template"
DRAFT = {"fields": {"name": "早濑", "look": "黑色雨衣", "origin": "hacker", "past": "旧地铁网", "regret": "那通电话",
                    "attrs": {"体": 4, "技": 5, "识": 4, "魂": 4, "运": 3}}, "companion": "kuon"}


def _portrait(run: Path) -> bytes:
    return next((run / "game" / "player" / "assets").glob("portrait.*")).read_bytes()


def test_a_run_started_without_the_builder_gets_the_default_face(tmp_path, monkeypatch):
    monkeypatch.setattr("neonrp.worlds.PLAYS_HOME", tmp_path / "plays")
    run = TP.new_run(TPL)
    assert _portrait(run) == (TPL / "assets" / "player" / "reader-n.webp").read_bytes()
    assert [e["has_portrait"] for e in worldmap.build_map_tree(run)["entities"] if e["kind"] == "player"] == [True]


def test_a_picked_face_wins_and_a_draft_without_one_gets_the_default(tmp_path, monkeypatch):
    monkeypatch.setattr("neonrp.worlds.PLAYS_HOME", tmp_path / "plays")
    run = TP.new_run(TPL, player={**DRAFT, "fields": {**DRAFT["fields"], "face": "reader-f"}})
    assert _portrait(run) == (TPL / "assets" / "player" / "reader-f.webp").read_bytes()
    run2 = TP.new_run(TPL, player=DRAFT)
    assert _portrait(run2) == (TPL / "assets" / "player" / "reader-n.webp").read_bytes()


def test_the_worlds_own_player_portrait_is_kept(tmp_path):
    t = TP.load(TPL)
    dest = tmp_path / "run"
    TP.build(t, dest)
    adir = dest / "game" / "player" / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "portrait.png").write_bytes(b"\x89PNG\r\n\x1a\nown")
    assert builder.apply_default(t, dest) is False and (adir / "portrait.png").read_bytes().endswith(b"own")


def test_default_must_be_an_option(tmp_path):
    d = tmp_path / "neon-rebirth.template"
    shutil.copytree(TPL, d)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    face = next(f for f in tj["player"]["builder"]["fields"] if f["id"] == "face")
    face["default"] = "nobody"
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    probs = builder.view(TP.load(d))["problems"]
    assert any("default" in str(p) for p in probs), probs
    assert builder.default_portrait(TP.load(TPL)).name == "reader-n.webp"
