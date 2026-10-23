"""模板演员表(souls)里没列的世界角色留在磁盘上、不激活 —— 地图 / people / 实体 / 玩家数据都不出现他(10-15,assets-pct 报:
pct-house 只列温妮不列奥斯温,地图上多出奥斯温)。stub,不调模型。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import people, player_data, worldmap
from neonrp.core.registry import load_registry


def _only_chara(tmp_path: Path) -> Path:
    d = tmp_path / "pct-house.template"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", d)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj["souls"] = [{"sid": "chara", "role": "npc"}]
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    dest = tmp_path / "run"
    TP.build(TP.load(d), dest)
    return dest


def test_an_uncast_world_soul_stays_off_every_screen(tmp_path):
    root = _only_chara(tmp_path)
    assert any(p.name.startswith("butler-") for p in (root / "souls").iterdir()), "it stays on disk (spec: not listed → not active)"
    assert worldmap.cast_ids(root) == {"si-chara0001"}
    tree = worldmap.build_map_tree(root)
    assert sorted(e["id"] for e in tree["entities"] if e["kind"] == "soul") == ["chara"]
    assert "butler" not in {e["id"] for e in worldmap.map_view(root, lens="play")["entities"]}
    assert "butler" not in {e.props.get("sid") for e in load_registry(root).of_class("soul")}
    assert "butler" not in {p.get("sid") for p in people.people(root)["people"]}
    bdir = next(p for p in (root / "souls").iterdir() if p.name.startswith("butler-"))
    sj = json.loads((bdir / "soul.json").read_text(encoding="utf-8"))
    (bdir / "soul.json").write_text(json.dumps({**sj, "standalone": True}, ensure_ascii=False), encoding="utf-8")
    assert "butler" not in {s["sid"] for s in player_data.run_souls(root).values()}, "not in this run: cannot be talked to or taken"


def test_without_a_playthrough_every_soul_folder_counts(tmp_path):
    root = _only_chara(tmp_path)
    for p in (root / "playthrough.json", root / ".neonrp" / "playthrough.json"):
        if p.exists():
            p.unlink()
    assert worldmap.cast_ids(root) is None
    assert {"butler", "chara"} <= {e["id"] for e in worldmap.build_map_tree(root)["entities"] if e["kind"] == "soul"}
