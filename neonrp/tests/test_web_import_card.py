"""工坊导入面板的数据源 `_import_status_payload`(web.py)。

新导入 UX:卡片先入工坊,三条转换路径由面板显式选择。该载荷是面板的
唯一数据源 —— 源卡/估计/计划进度/三条开场指令都从这里出。"""

import json
from pathlib import Path

from neonrp.commands.web import _import_status_payload
from neonrp.core.import_plan import persist_source_card


def _world(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    (root / "game").mkdir(parents=True)
    return root


def test_no_source_card(tmp_path: Path):
    assert _import_status_payload(_world(tmp_path)) == {"has_source": False}


def test_world_card_payload_carries_commands(tmp_path: Path):
    root = _world(tmp_path)
    card = tmp_path / "demo.json"
    card.write_text(json.dumps({"name": "雾汐港", "description": "x"}), encoding="utf-8")
    persist_source_card(root, card)

    p = _import_status_payload(root)
    assert p["has_source"] is True
    assert p["kind"] == "world"
    assert p["source_rel"] == "game/import/source.json"
    assert p["format"] == "json-card"
    assert p["plan"] is None
    assert p["resume_command"] is None
    # ①/② 开场指令都指向仓内持久化副本
    assert "game/import/source.json" in p["start_command"]
    assert "计划-分批" in p["start_command"]
    assert "game/import/source.json" in p["oneshot_command"]
    assert "tavern-game-import" in p["oneshot_command"]


def test_soul_card_payload_uses_soul_oneshot(tmp_path: Path):
    root = _world(tmp_path)
    (root / "soul.json").write_text("{}", encoding="utf-8")
    card = tmp_path / "elena.png"
    card.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-real-png")
    persist_source_card(root, card)

    p = _import_status_payload(root)
    assert p["kind"] == "soul"
    assert "soul" in p["oneshot_command"]
    assert "game/import/source.png" in p["oneshot_command"]


def test_pending_plan_surfaces_progress_and_resume(tmp_path: Path):
    root = _world(tmp_path)
    card = tmp_path / "big.json"
    card.write_text("{}", encoding="utf-8")
    persist_source_card(root, card)
    plan = {
        "version": 1,
        "source": "game/import/source.json",
        "source_format": "json-card",
        "batches": [
            {"id": "b1", "title": "骨架", "items": [], "status": "done"},
            {"id": "b2", "title": "地点", "items": [], "status": "pending"},
        ],
    }
    (root / "game" / "import" / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8"
    )

    p = _import_status_payload(root)
    assert p["plan"] == {"done": 1, "total": 2, "next_title": "地点", "complete": False}
    assert p["resume_command"] and "b2" in p["resume_command"]


def test_complete_plan_marks_complete(tmp_path: Path):
    root = _world(tmp_path)
    card = tmp_path / "big.json"
    card.write_text("{}", encoding="utf-8")
    persist_source_card(root, card)
    plan = {
        "version": 1,
        "source": "game/import/source.json",
        "batches": [{"id": "b1", "title": "骨架", "items": [], "status": "done"}],
    }
    (root / "game" / "import" / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8"
    )

    p = _import_status_payload(root)
    assert p["plan"]["complete"] is True
    assert p["resume_command"] is None
