"""issue #14 落地回归 — 画布边车(A′)+ 自动草拟(B)。

A′:导出把 STUDIO_HOME 画布打进 zip 的 .studio/,导入恢复回 STUDIO_HOME,
    世界目录不留 .studio(世界源保持纯内容,07-13 决定的修正案)。
B :flow.json 缺席时 canvas_get(story) 从 timeline 因果链 + quests 草拟。
"""

import json
import zipfile
from pathlib import Path

from neonrp.core.world_export import export_world, load_world_zip


def _make_world(root: Path, name: str = "w-canvas") -> Path:
    w = root / name
    (w / ".neonrp").mkdir(parents=True)
    (w / ".neonrp" / "manifest.json").write_text("{}", encoding="utf-8")
    (w / "game" / "meta").mkdir(parents=True)
    (w / "game" / "meta" / "timeline.json").write_text(
        json.dumps(
            {
                "events": [
                    {"id": "e1", "time": "D1", "what": "迟到二十分钟", "is_cause_of": ["e2"]},
                    {"id": "e2", "time": "D2", "what": "她没有等你", "depends_on": ["e1"]},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (w / "game" / "towns" / "T001").mkdir(parents=True)
    (w / "game" / "towns" / "T001" / "quests.json").write_text(
        json.dumps({"quests": [{"id": "q1", "name": "找回那句道歉"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return w


def test_canvas_sidecar_roundtrip(tmp_path: Path, monkeypatch) -> None:
    import neonrp.worlds as worlds_mod

    monkeypatch.setattr(worlds_mod, "STUDIO_HOME", tmp_path / "studio")
    w = _make_world(tmp_path)
    sdir = worlds_mod.get_studio_dir(w.name, create=True)
    flow = {"nodes": [{"id": "n1", "pos": [0, 0], "data": {"label": "开场"}}], "edges": []}
    (sdir / "flow.json").write_text(json.dumps(flow, ensure_ascii=False), encoding="utf-8")

    zip_path = export_world(w, tmp_path / "out.zip")
    with zipfile.ZipFile(zip_path) as zf:
        assert f"{w.name}/.studio/flow.json" in zf.namelist()  # 画布随包

    # 换一台"新机器":清空 studio,导入 → 画布恢复;世界目录不留 .studio。
    monkeypatch.setattr(worlds_mod, "STUDIO_HOME", tmp_path / "studio2")
    target = load_world_zip(zip_path, games_dir=tmp_path / "lib")
    restored = json.loads(
        (worlds_mod.get_studio_dir(target.name) / "flow.json").read_text(encoding="utf-8")
    )
    assert restored["nodes"][0]["data"]["label"] == "开场"
    assert not (target / ".studio").exists()  # 源保持纯内容


def test_export_without_canvas_still_clean(tmp_path: Path, monkeypatch) -> None:
    import neonrp.worlds as worlds_mod

    monkeypatch.setattr(worlds_mod, "STUDIO_HOME", tmp_path / "studio-empty")
    w = _make_world(tmp_path, "w-nocanvas")
    zip_path = export_world(w, tmp_path / "o2.zip")
    with zipfile.ZipFile(zip_path) as zf:
        assert not any(".studio/" in m for m in zf.namelist())


def test_draft_story_canvas_from_world_data(tmp_path: Path) -> None:
    from neonrp.commands.web import _clean_flow_canvas, _draft_story_canvas

    w = _make_world(tmp_path, "w-draft")
    draft = _draft_story_canvas(w)
    assert draft is not None and draft["drafted"] is True
    ids = {n["id"] for n in draft["nodes"]}
    assert {"e1", "e2", "q1"} <= ids  # 事件 + 任务都进蓝图
    assert any(
        e["source"] == "e1" and e["target"] == "e2" for e in draft["edges"]
    )  # is_cause_of 因果链成边
    # 草稿必须能过画布校验(作者在其上编辑后 PUT 不被拒)。
    ok, _cleaned = _clean_flow_canvas(draft)
    assert ok is True


def test_draft_none_when_world_has_no_story_data(tmp_path: Path) -> None:
    from neonrp.commands.web import _draft_story_canvas

    w = tmp_path / "w-empty"
    (w / ".neonrp").mkdir(parents=True)
    (w / "game").mkdir()
    assert _draft_story_canvas(w) is None


def test_story_canvas_incremental_merge(tmp_path: Path) -> None:
    # 世界更新后蓝图不动 → 增量合并:新事件补进(drafted 标),
    # 旧节点 pos 不变、用户自建节点不删。
    from neonrp.commands.web import _draft_story_canvas, _merge_story_canvas

    w = _make_world(tmp_path, "w-merge")
    saved = {
        "nodes": [
            {"id": "e1", "pos": [123, 456], "data": {"label": "用户改过的e1"}},
            {"id": "my-note", "pos": [9, 9], "data": {"label": "用户自建,数据里没有"}},
        ],
        "edges": [],
        "viewport": {"zoom": 1},
    }
    draft = _draft_story_canvas(w)  # 含 e1/e2/q1 + e1→e2 边
    merged = _merge_story_canvas(saved, draft)
    ids = {n["id"] for n in merged["nodes"]}
    assert {"e1", "e2", "q1", "my-note"} <= ids  # 新节点补进,自建节点保留
    e1 = next(n for n in merged["nodes"] if n["id"] == "e1")
    assert e1["pos"] == [123, 456] and e1["data"]["label"] == "用户改过的e1"  # 旧的不动
    e2 = next(n for n in merged["nodes"] if n["id"] == "e2")
    assert e2["data"].get("drafted") is True  # 新增带草拟标
    assert any(e["source"] == "e1" and e["target"] == "e2" for e in merged["edges"])
    assert merged["viewport"] == {"zoom": 1}  # 其余字段保留


def test_relation_draft_and_merge(tmp_path: Path) -> None:
    from neonrp.commands.web import (
        _clean_relationships,
        _draft_relationships,
        _merge_relationships,
    )

    w = _make_world(tmp_path, "w-rel")
    souls = w / "souls" / "elena-si-1"
    souls.mkdir(parents=True)
    (souls / "soul.json").write_text(
        json.dumps({"sid": "elena", "name": "Elena", "name_local": "艾琳娜"}),
        encoding="utf-8",
    )
    draft = _draft_relationships(w)
    assert draft is not None
    ok, cleaned = _clean_relationships(draft)
    assert ok and cleaned["relationships"][0]["source"] == "艾琳娜"  # 本地名+过校验
    # 增量:已有画布 + 新角色
    saved = {"relationships": [{"id": "rel-1", "source": "老泰德", "target": "玩家", "relation_type": "病人", "description": "", "direction": "directed", "strength": 4}], "layout": {}}
    merged = _merge_relationships(saved, draft)
    srcs = {r["source"] for r in merged["relationships"]}
    assert {"老泰德", "艾琳娜"} <= srcs  # 旧不删,新补进
