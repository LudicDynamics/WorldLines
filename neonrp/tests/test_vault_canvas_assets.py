"""Pictures and hierarchy in the projected vault.

Two asks, two properties:

- "最好能显示图片素材" — portraits and the cover are copied into `素材/`
  and embedded in their notes, so a soul page shows a face.
- "通过层级来显示包容关系,而不是把所有可视化都统一成平级关系" — a
  `世界.canvas` where containment is *geometric*: every soul card lies
  inside its place group, every place group inside the world group. That
  is the only hierarchy Obsidian's canvas knows, so it is what we assert.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core import vault as V
from neonrp.core.vault_canvas import (
    CANVAS_FILENAME,
    UNPLACED_LABEL,
    PlaceBox,
    SoulCard,
    build_canvas,
    contains,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _world(tmp_path: Path, *, cover: bool = True) -> Path:
    root = tmp_path / "w"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text(json.dumps({"turn_count": 3}))
    (root / "game" / "world").mkdir()
    (root / "game" / "world" / "world_map.json").write_text(
        json.dumps({"name": "雾港", "nodes": [{"id": "gate", "name": "北门"}, {"id": "inn", "name": "旅店"}]})
    )
    (root / "game" / "locations").mkdir()
    (root / "game" / "locations" / "gate.json").write_text(
        json.dumps({"id": "gate", "kind": "location", "name": "北门", "connections": ["inn"]})
    )
    (root / "game" / "locations" / "inn.json").write_text(
        json.dumps({"id": "inn", "kind": "location", "name": "旅店", "connections": ["gate"]})
    )
    if cover:
        (root / "assets").mkdir()
        (root / "assets" / "cover.png").write_bytes(PNG)

    def soul(sid: str, name: str, location: str, portrait: bool, rel: dict | None = None) -> None:
        d = root / "souls" / f"{sid}-si-{sid}0001"
        (d / "persona").mkdir(parents=True)
        (d / "soul.json").write_text(json.dumps({"sid": sid, "name": name}))
        (d / "run_state.json").write_text(json.dumps({"sid": sid, "location": location}))
        if portrait:
            (d / "assets").mkdir()
            (d / "assets" / "portrait.png").write_bytes(PNG + sid.encode())
        if rel:
            (d / "persona" / "relationships.json").write_text(json.dumps({"relationships": rel}))

    soul("rowan", "罗文", "gate", True, {"艾琳娜": {"disposition": "守护"}})
    soul("elena", "艾琳娜", "gate", True)
    soul("ghost", "无名", "nowhere-land", False)
    return root


# --- pictures ----------------------------------------------------------------


def test_portraits_and_cover_are_copied_and_embedded(tmp_path):
    root = _world(tmp_path)
    report = V.project_vault(root)
    vault = root / "vault"

    assert (vault / "素材" / "罗文.png").read_bytes() == PNG + b"rowan"
    assert (vault / "素材" / "世界.png").read_bytes() == PNG
    assert "![[素材/罗文.png|240]]" in (vault / "角色" / "罗文.md").read_text(encoding="utf-8")
    assert "![[素材/世界.png|480]]" in (vault / "世界.md").read_text(encoding="utf-8")
    # A soul with no picture gets no broken embed.
    assert "![[" not in (vault / "角色" / "无名.md").read_text(encoding="utf-8")
    assert "素材/罗文.png" in report.written


def test_unchanged_pictures_are_not_rewritten(tmp_path):
    root = _world(tmp_path)
    V.project_vault(root)
    before = (root / "vault" / "素材" / "罗文.png").stat().st_mtime_ns
    report = V.project_vault(root)
    assert not report.changed
    assert (root / "vault" / "素材" / "罗文.png").stat().st_mtime_ns == before


def test_removed_soul_takes_its_picture_with_it(tmp_path):
    root = _world(tmp_path)
    V.project_vault(root)
    import shutil

    shutil.rmtree(root / "souls" / "rowan-si-rowan0001")
    report = V.project_vault(root)
    assert "素材/罗文.png" in report.removed
    assert not (root / "vault" / "素材" / "罗文.png").exists()
    # The user's half is never pruned, whatever the index says.
    assert (root / "vault" / "我的笔记" / "读我.md").exists()


# --- hierarchy ---------------------------------------------------------------


def _load_canvas(root: Path) -> dict:
    return json.loads((root / "vault" / CANVAS_FILENAME).read_text(encoding="utf-8"))


def _by(canvas: dict, **match) -> dict:
    hits = [n for n in canvas["nodes"] if all(n.get(k) == v for k, v in match.items())]
    assert len(hits) == 1, (match, hits)
    return hits[0]


def test_canvas_nests_souls_inside_places_inside_world(tmp_path):
    root = _world(tmp_path)
    V.project_vault(root)
    canvas = _load_canvas(root)

    world = _by(canvas, type="group", label="雾港")
    gate = _by(canvas, type="group", label="北门")
    inn = _by(canvas, type="group", label="旅店")
    rowan = _by(canvas, type="file", file="角色/罗文.md")
    elena = _by(canvas, type="file", file="角色/艾琳娜.md")
    cover = _by(canvas, type="file", file="素材/世界.png")

    for node in canvas["nodes"]:
        if node is not world:
            assert contains(world, node), node
    assert contains(gate, rowan) and contains(gate, elena)
    assert not contains(inn, rowan)
    assert contains(world, cover)
    # A place page sits inside its own group so clicking it opens the note.
    assert contains(gate, _by(canvas, type="file", file="地点/北门.md"))


def test_canvas_groups_never_overlap(tmp_path):
    root = _world(tmp_path)
    V.project_vault(root)
    groups = [n for n in _load_canvas(root)["nodes"] if n["type"] == "group" and n["label"] != "雾港"]
    assert len(groups) >= 3

    def overlap(a, b):
        return not (
            a["x"] + a["width"] <= b["x"]
            or b["x"] + b["width"] <= a["x"]
            or a["y"] + a["height"] <= b["y"]
            or b["y"] + b["height"] <= a["y"]
        )

    for i, a in enumerate(groups):
        for b in groups[i + 1 :]:
            assert not overlap(a, b), (a["label"], b["label"])


def test_soul_at_a_nameless_spot_goes_to_the_road_group(tmp_path):
    root = _world(tmp_path)
    V.project_vault(root)
    canvas = _load_canvas(root)
    ghost = _by(canvas, type="file", file="角色/无名.md")
    # `nowhere-land` names nothing in the world, so the projector labels the
    # spot with its raw id — still a box of its own, not silently dropped.
    box = _by(canvas, type="group", label="nowhere-land")
    assert contains(box, ghost)
    assert not any(n.get("label") == UNPLACED_LABEL for n in canvas["nodes"])


def test_truly_unlocated_soul_goes_to_the_road_group():
    canvas = build_canvas(
        "w", None, [PlaceBox(key="p", label="P", note="地点/P.md")],
        [SoulCard(key="x", note="角色/x.md", name="x")], [],
    )
    road = _by(canvas, type="group", label=UNPLACED_LABEL)
    assert contains(road, _by(canvas, type="file", file="角色/x.md"))


def test_canvas_edges_for_roads_and_relationships(tmp_path):
    root = _world(tmp_path)
    V.project_vault(root)
    canvas = _load_canvas(root)
    labels = sorted(e.get("label", "") for e in canvas["edges"])
    assert labels == ["守护", "通向"]
    road = next(e for e in canvas["edges"] if e["label"] == "通向")
    gate, inn = _by(canvas, label="北门"), _by(canvas, label="旅店")
    assert {road["fromNode"], road["toNode"]} == {gate["id"], inn["id"]}
    rel = next(e for e in canvas["edges"] if e["label"] == "守护")
    assert rel["fromNode"] == _by(canvas, file="角色/罗文.md")["id"]
    assert rel["toNode"] == _by(canvas, file="角色/艾琳娜.md")["id"]


def test_canvas_is_deterministic_and_reprojection_is_a_noop(tmp_path):
    root = _world(tmp_path)
    V.project_vault(root)
    first = (root / "vault" / CANVAS_FILENAME).read_bytes()
    report = V.project_vault(root)
    assert not report.changed
    assert (root / "vault" / CANVAS_FILENAME).read_bytes() == first


def test_canvas_moves_with_the_world(tmp_path):
    """Rowan walks to the inn; the next projection redraws him there."""
    root = _world(tmp_path)
    V.project_vault(root)
    rs = root / "souls" / "rowan-si-rowan0001" / "run_state.json"
    rs.write_text(json.dumps({"sid": "rowan", "location": "inn"}))
    report = V.project_vault(root)
    assert CANVAS_FILENAME in report.written
    canvas = _load_canvas(root)
    assert contains(_by(canvas, label="旅店"), _by(canvas, file="角色/罗文.md"))
    assert not contains(_by(canvas, label="北门"), _by(canvas, file="角色/罗文.md"))


def test_world_without_cover_or_places_still_projects(tmp_path):
    root = _world(tmp_path, cover=False)
    import shutil

    shutil.rmtree(root / "game" / "locations")
    report = V.project_vault(root)
    assert CANVAS_FILENAME in report.written
    canvas = _load_canvas(root)
    assert not any(n.get("file") == "素材/世界.png" for n in canvas["nodes"])
    world = _by(canvas, label="雾港")
    for node in canvas["nodes"]:
        assert contains(world, node)


@pytest.mark.parametrize("bad", ["a/b", "x:y", "q?"])
def test_asset_names_are_filesystem_safe(tmp_path, bad):
    root = _world(tmp_path)
    d = root / "souls" / "odd-si-odd0001"
    (d / "assets").mkdir(parents=True)
    (d / "soul.json").write_text(json.dumps({"sid": "odd", "name": bad}))
    (d / "assets" / "portrait.png").write_bytes(PNG)
    V.project_vault(root)
    names = [p.name for p in (root / "vault" / "素材").iterdir()]
    assert all(all(ch not in n for ch in '/:?') for n in names), names
