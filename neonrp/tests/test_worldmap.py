"""Layered world map (core/worldmap.py) + its web routes.

Runs on a copy of the real stoneford-elena template, so the four data issues
seen on 09-25 (dungeon discovered/danger conflicts, an unmapped flat
location, Rowan only placed at town level) stay pinned as regressions too.
"""

from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

import neonrp
from neonrp.core import imagegen
from neonrp.core import worldmap as M

TEMPLATE = Path(neonrp.__file__).parent / "templates" / "stoneford-elena"


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dst = tmp_path / "stone"
    shutil.copytree(TEMPLATE, dst)
    return dst


def _png(path: Path, size=(1536, 1024), mode="RGB") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, (90, 80, 70) if mode == "RGB" else (0, 0, 0, 0)).save(path)
    return path


# ── tree ────────────────────────────────────────────────────────────────

def test_tree_levels_addresses_and_characters(world: Path) -> None:
    t = M.build_map_tree(world)
    assert set(M.map_levels(t)) == {"world", "T001", "T004", "D001"}
    assert t["nodes"]["T001/gate_north"]["parent"] == "T001"
    assert t["nodes"]["D001/D001_R004"]["kind"] == "boss"
    where = {e["id"]: e["addr"] for e in t["entities"] if e["kind"] != "npc"}
    # player (run_state T001/gate_north) and Elena (bare "gate_north") share one address
    assert where["player"] == "T001/gate_north"
    assert where["elena"] == "T001/gate_north"
    # Rowan's run_state only says "T004"; npcs.json has the finer spot
    assert where["rowan"] == "T004/tavern"


def test_tree_reports_real_file_inconsistencies(world: Path) -> None:
    t = M.build_map_tree(world)
    msgs = " | ".join(i["msg"] for i in t["issues"])
    kinds = {i["kind"] for i in t["issues"]}
    assert "discovered: world_map=True vs dungeons/D001/dungeon.json=False" in msgs
    assert "danger: world_map=5" in msgs
    # 10-05 map → folder tree: market-square is a spot of T001 now, north-gate / riverlamp-inn are aliases of the town
    # map's own ids — no second, stale map to report
    assert "unresolved" not in kinds and t["flat_locations"] == []
    assert "T001/market-square" in t["nodes"]["T001"]["children"]
    assert "coarse" in kinds
    from neonrp.core.place_nav import qualify_location

    assert qualify_location(world, "north-gate") == "T001/gate_north"   # legacy alias
    assert qualify_location(world, "riverlamp-inn") == "T001/inn"       # the merged record's id


# ── coordinates ─────────────────────────────────────────────────────────

def test_image_level_roundtrip(world: Path) -> None:
    t = M.build_map_tree(world)
    for lv in M.map_levels(t):
        fit = M.layout_fit(t, lv)
        for c in t["nodes"][lv]["children"]:
            p = t["nodes"][c]["pos"]
            x, y = M.to_level(fit, *M.to_image(fit, p["x"], p["y"]))
            assert abs(x - p["x"]) < 1e-6 and abs(y - p["y"]) < 1e-6
            xp, yp = M.to_image(fit, p["x"], p["y"])
            assert 0 <= xp <= 100 and 0 <= yp <= 100


def test_move_keeps_other_pins_on_the_existing_image(world: Path) -> None:
    """Frozen transform: dragging one pin must not shift the others off the picture."""
    t = M.build_map_tree(world)
    before = M.hotspots(world, t, "T001")
    assert M.map_status(world, t)["T001"]["stale"] is False
    # drag the gate (an extreme node that defines the bbox) somewhere central
    res = M.move_node(world, "T001", "T001/gate_north", 30.0, 40.0)
    assert res["file"].endswith("locations/T001/gate_north/location.json")  # the place's own folder
    t2 = M.build_map_tree(world)
    after = M.hotspots(world, t2, "T001")
    assert after["T001/gate_north"] == pytest.approx([30.0, 40.0], abs=0.1)
    for c, xy in before.items():
        if c != "T001/gate_north":
            assert after[c] == pytest.approx(xy, abs=0.01)
    assert M.map_status(world, t2)["T001"]["stale"] is True


def test_add_node_writes_town_map_and_lands_where_clicked(world: Path) -> None:
    res = M.add_node(world, "T001", name="铁匠铺", kind="facility", xp=72.0, yp=30.0,
                     summary="炉火", link_to="T001/main_street")
    from neonrp.core import place_tree

    tm = place_tree.level_doc(world, "T001")  # the town's place folders + town_map.json's own keys (state)
    ids = [n["id"] for n in tm["nodes"]]
    new = res["node"]["id"]
    assert new in ids and new in tm["state"]["discovered_nodes"]
    assert new in next(n for n in tm["nodes"] if n["id"] == "main_street")["links"]
    t = M.build_map_tree(world)
    assert t["nodes"][res["addr"]]["name"] == "铁匠铺"
    assert M.hotspots(world, t, "T001")[res["addr"]] == pytest.approx([72.0, 30.0], abs=0.1)


def test_world_node_ids_never_collide(world: Path) -> None:
    a = M.add_node(world, "world", name="Harbor", kind="town", xp=50, yp=50)
    b = M.add_node(world, "world", name="Harbor", kind="town", xp=60, yp=60)
    assert a["addr"] != b["addr"]


# ── guide + generation ──────────────────────────────────────────────────

@pytest.mark.parametrize("level", ["world", "T001", "D001"])
def test_guide_is_full_size(world: Path, tmp_path: Path, level: str) -> None:
    t = M.build_map_tree(world)
    out = M.draw_guide(t, level, tmp_path / f"{level}.png")
    assert Image.open(out).size == (M.W, M.H)


def test_generate_map_records_frozen_fit_and_hash(world: Path) -> None:
    seen: dict = {}

    def fake_edit(prompt, images, out_path, **kw):
        seen["prompt"], seen["images"] = prompt, images
        return _png(out_path)

    with patch.object(imagegen, "edit_image", fake_edit):
        meta = M.generate_map(world, "T004", cfg=imagegen.ImageConfig(backend="openai"))
    assert M.map_image_path(world, "T004").is_file()
    assert M.map_guide_path(world, "T004") in seen["images"]
    assert "碧石镇" in seen["prompt"] and "no text" in seen["prompt"].lower()
    stored = json.loads(M.map_meta_path(world, "T004").read_text(encoding="utf-8"))
    assert stored["fit"] == meta["fit"] and stored["layout_hash"] == meta["layout_hash"]
    assert M.map_status(world, M.build_map_tree(world))["T004"] == {
        **M.map_status(world, M.build_map_tree(world))["T004"], "has_image": True, "stale": False}


def test_generate_rejects_levels_without_coordinates(world: Path) -> None:
    with pytest.raises(ValueError):
        M.generate_map(world, "T001/inn", cfg=imagegen.ImageConfig(backend="openai"))


def test_shipped_stoneford_maps_are_current() -> None:
    """The template ships generated maps; its coordinates must still match them."""
    t = M.build_map_tree(TEMPLATE)
    st = M.map_status(TEMPLATE, t)
    for lv in ("world", "T001"):
        assert st[lv]["has_image"] and not st[lv]["stale"], lv
    for addr in ("T001/gate_north", "T001/inn", "T001/dock", "T001/guild"):
        assert M.scene_image_path(TEMPLATE, addr) is not None, addr
    assert M.soul_asset(TEMPLATE, "rowan", "sprite") is not None


# ── play lens ───────────────────────────────────────────────────────────

def test_play_lens_hides_what_the_player_has_not_found(world: Path) -> None:
    v = M.map_view(world, lens="play")
    assert v["nodes"]["T002"]["name"] == "" and v["nodes"]["T002"]["kind"] == "unknown"
    assert v["nodes"]["T001"]["name"] == "石津镇"
    assert v["nodes"]["T001/dock"]["name"] == ""          # town_map: not discovered yet
    ids = {e["id"] for e in v["entities"]}
    assert "rowan" not in ids                              # unmet soul, another town
    unmet = [e for e in v["entities"] if e["kind"] == "npc" and not e.get("met")]
    assert unmet and all(e["name"] == "" for e in unmet)
    assert v["issues"] == []
    lore = v["nodes"]["D001"]["extra"].get("lore") or {}
    assert "legends" not in lore                           # GM-only lore stripped


# ── codex backend ───────────────────────────────────────────────────────

def test_codex_backend_uses_file_it_was_told_to_write(tmp_path: Path) -> None:
    out = tmp_path / "o" / "map.png"
    calls = {}

    def fake_run(cmd, input, **kw):
        calls["cmd"], calls["input"] = cmd, input
        _png(out)

        class R:
            returncode, stdout, stderr = 0, str(out), ""
        return R()

    with patch("shutil.which", lambda _: "/bin/codex"), patch("subprocess.run", fake_run):
        imagegen.edit_image("draw", [tmp_path / "g.png"], out,
                            cfg=imagegen.ImageConfig(backend="codex"))
    assert out.is_file()
    assert calls["cmd"][:2] == ["/bin/codex", "exec"] and "-i" in calls["cmd"]
    assert str(out) in calls["input"]


def test_codex_backend_falls_back_to_newest_generated_image(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(home))
    out = tmp_path / "map.png"

    def fake_run(cmd, input, **kw):
        _png(home / "generated_images" / "sess" / "exec-1.png")

        class R:
            returncode, stdout, stderr = 0, "done", ""
        return R()

    with patch("shutil.which", lambda _: "/bin/codex"), patch("subprocess.run", fake_run):
        imagegen.edit_image("draw", [], out, cfg=imagegen.ImageConfig(backend="codex"))
    assert out.is_file()


def test_no_backend_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="No image backend"):
        imagegen.edit_image("x", [], tmp_path / "a.png", cfg=imagegen.ImageConfig(backend=""))


# ── routes ──────────────────────────────────────────────────────────────

def _req(base: str, path: str, method="GET", body: dict | bytes | None = None):
    data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{base}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as e:
        return e.code, None


def test_workbench_map_routes(tmp_path: Path) -> None:
    from neonrp.commands.web import make_server
    from neonrp.core.manifest import Manifest

    worlds = tmp_path / "lib" / "worlds"
    shutil.copytree(TEMPLATE, worlds / "stone")
    (worlds / "stone" / ".neonrp").mkdir(exist_ok=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (worlds / "stone" / ".neonrp" / "manifest.json").write_text(json.dumps(m.model_dump(), default=str))
    with (
        patch("neonrp.worlds.WORLDS_HOME", worlds),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            assert _req(base, "/api/v1/create/session", "POST", {"world_id": "stone"})[0] == 200
            P = "/api/v1/create/session/edit-local"
            st, v = _req(base, f"{P}/map")
            assert st == 200 and v["levels"]["T001"]["has_image"] and v["issues"]
            assert v["nodes"]["T001/inn"]["has_scene"] is True
            st, img = _req(base, f"{P}/map/image?level=T001")
            assert st == 200 and img[:4] == b"RIFF"                    # webp
            assert _req(base, f"{P}/map/image?level=T001&guide=1")[0] == 200
            assert _req(base, f"{P}/map/image?level=../../etc")[0] == 404
            assert _req(base, f"{P}/place-image?addr=T001/inn")[0] == 200
            assert _req(base, f"{P}/sprite?id=elena")[0] == 200
            assert _req(base, f"{P}/sprite?id=../x")[0] == 400
            assert _req(base, f"{P}/portrait?id=rowan")[0] == 200
            assert _req(base, f"{P}/portrait?id=player")[0] == 200
            st, r = _req(base, f"{P}/map/node", "PUT", {"level": "T001", "addr": "T001/inn", "x": 70, "y": 50})
            assert st == 200 and r["file"].endswith("T001/inn/location.json")
            st, r = _req(base, f"{P}/map/node", "POST",
                         {"level": "T001", "name": "铁匠铺", "kind": "facility", "x": 72, "y": 30})
            assert st == 200
            addr = r["addr"]
            buf = tmp_path / "s.png"
            _png(buf, (64, 40))
            assert _req(base, f"{P}/place/upload?addr={addr}", "POST", buf.read_bytes())[0] == 200
            assert _req(base, f"{P}/place/upload?addr=nope", "POST", buf.read_bytes())[0] == 400
            assert _req(base, f"{P}/place/upload?addr={addr}", "POST", b"not an image")[0] == 400
            st, v = _req(base, f"{P}/map")
            assert v["nodes"][addr]["has_scene"] and v["levels"]["T001"]["stale"]
            with patch.object(M, "generate_map", lambda root, level: None):
                st, r = _req(base, f"{P}/map/generate", "POST", {"level": "T004"})
                assert st == 202 and r["job"] == "map:T004"
            assert _req(base, f"{P}/map/generate", "POST", {"level": "T001/inn"})[0] == 400
        finally:
            server.shutdown()
