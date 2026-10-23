"""计划-分批导入(core/import_plan.py)的确定性半边。

LLM 怎么分批不可单测;这里钉死引擎侧的全部确定性行为:源卡持久化、
体量推荐信号、plan schema 校验、恢复检测、以及 continue 流程的恢复钩
(有 pending 计划 → build 模式 + 续跑开场指令)。
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp.core.import_plan import (
    ImportPlan,
    estimate_source,
    has_pending_plan,
    load_plan,
    persist_source_card,
    plan_path,
    resume_startup_command,
    start_planned_conversion,
    validate_plan,
)


def _plan_dict(statuses: list[str]) -> dict:
    return {
        "version": 1,
        "source": "game/import/source.json",
        "batches": [
            {
                "id": f"b{i + 1}",
                "kind": "locations",
                "title": f"批次{i + 1}",
                "items": ["x"],
                "status": s,
                "files_written": [],
            }
            for i, s in enumerate(statuses)
        ],
    }


def _write_plan(root: Path, data: dict) -> None:
    p = plan_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── 源卡持久化 ─────────────────────────────────────────────


def test_persist_source_card_copies_into_game_import(tmp_path: Path):
    src = tmp_path / "外部卡.PNG"
    src.write_bytes(b"png-bytes")
    root = tmp_path / "world"
    root.mkdir()

    dest = persist_source_card(root, src)

    assert dest == root / "game" / "import" / "source.png"  # 扩展名小写化
    assert dest.read_bytes() == b"png-bytes"


def test_persist_source_card_overwrites_idempotently(tmp_path: Path):
    root = tmp_path / "world"
    root.mkdir()
    a = tmp_path / "a.json"
    a.write_text("{}", encoding="utf-8")
    persist_source_card(root, a)
    a.write_text('{"v":2}', encoding="utf-8")

    dest = persist_source_card(root, a)

    assert dest.read_text(encoding="utf-8") == '{"v":2}'


def test_persist_source_card_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        persist_source_card(tmp_path, tmp_path / "nope.png")


# ── 体量推荐信号(仅推荐,不触发) ─────────────────────────


def test_estimate_small_source_not_recommended(tmp_path: Path):
    f = tmp_path / "small.json"
    f.write_text(json.dumps({"name": "mini"}), encoding="utf-8")
    est = estimate_source(f)
    assert est["recommend_plan"] is False


def test_estimate_recommends_on_bytes(tmp_path: Path):
    f = tmp_path / "big.txt"
    f.write_text("设" * 70_000, encoding="utf-8")
    assert estimate_source(f)["recommend_plan"] is True


def test_estimate_recommends_on_lorebook_entries(tmp_path: Path):
    card = {"data": {"character_book": {"entries": [{"k": i} for i in range(45)]}}}
    f = tmp_path / "card.json"
    f.write_text(json.dumps(card), encoding="utf-8")
    est = estimate_source(f)
    assert est["entries"] == 45
    assert est["recommend_plan"] is True


# ── schema 校验 ────────────────────────────────────────────


def test_validate_plan_accepts_valid():
    assert validate_plan(_plan_dict(["pending", "done"])) == []


def test_validate_plan_catches_errors():
    bad = _plan_dict(["pending", "pending"])
    bad["version"] = 2
    bad["batches"][1]["id"] = "b1"  # 重复 id
    bad["batches"][0]["status"] = "doing"  # 非法状态
    del bad["source"]
    errors = validate_plan(bad)
    assert any("version" in e for e in errors)
    assert any("source" in e for e in errors)
    assert any("重复" in e for e in errors)
    assert any("pending|done" in e for e in errors)


# ── 加载 / 恢复检测 ────────────────────────────────────────


def test_load_plan_absent_and_invalid_are_none(tmp_path: Path):
    assert load_plan(tmp_path) is None  # 不存在
    _write_plan(tmp_path, {"version": 1})  # 无效
    assert load_plan(tmp_path) is None


def test_next_pending_order_and_progress(tmp_path: Path):
    _write_plan(tmp_path, _plan_dict(["done", "pending", "pending"]))
    plan = load_plan(tmp_path)
    assert isinstance(plan, ImportPlan)
    assert plan.done == 1 and plan.total == 3
    assert plan.next_pending()["id"] == "b2"  # 第一个 pending,顺序执行
    assert "1/3" in plan.progress_line()


def test_has_pending_plan_states(tmp_path: Path):
    assert has_pending_plan(tmp_path) is False  # 无计划
    _write_plan(tmp_path, _plan_dict(["done", "done"]))
    assert has_pending_plan(tmp_path) is False  # 全部完成
    _write_plan(tmp_path, _plan_dict(["done", "pending"]))
    assert has_pending_plan(tmp_path) is True  # 进行中


# ── 开场指令(可调用入口面) ───────────────────────────────


def test_resume_startup_command_reports_progress(tmp_path: Path):
    assert resume_startup_command(tmp_path) is None
    _write_plan(tmp_path, _plan_dict(["done", "pending"]))
    cmd = resume_startup_command(tmp_path)
    assert cmd is not None
    assert "1/2" in cmd and "b2" in cmd and "不要重新规划" in cmd


def test_start_planned_conversion_points_at_persisted_source(tmp_path: Path):
    src = tmp_path / "card.json"
    src.write_text("{}", encoding="utf-8")
    root = tmp_path / "world"
    root.mkdir()
    persist_source_card(root, src)

    instruction = start_planned_conversion(root)

    assert "game/import/source.json" in instruction
    assert "计划-分批协议" in instruction
    assert "plan.json" in instruction


# ── continue 流程的恢复钩 ─────────────────────────────────


def _continue(game_path: Path):
    from neonrp.cli import _worldlines_continue_game_with_preset

    cwd = Path.cwd()  # 被测函数会 chdir 进 tmp;不还原会毒化后续测试的相对路径
    try:
        with patch("neonrp.presets.build_config_dict", return_value={}), patch(
            "neonrp.core.storage.atomic_write_json"
        ), patch("neonrp.core.config.load_dotenv"), patch(
            "neonrp.cli._launch_surface"
        ) as launch:
            ok = _worldlines_continue_game_with_preset(game_path, "stub-test")
    finally:
        import os

        os.chdir(cwd)
    return ok, launch


def test_continue_with_pending_plan_switches_to_build_and_injects_resume(tmp_path: Path):
    game = tmp_path / "custom-import-x"
    (game / ".neonrp").mkdir(parents=True)
    _write_plan(game, _plan_dict(["done", "pending"]))

    ok, launch = _continue(game)

    assert ok is True
    kwargs = launch.call_args.kwargs
    assert kwargs["mode"] == "build"  # play 写受限,批次必须在 build 落盘
    cmds = kwargs["startup_commands"]
    assert cmds and "导入计划" in cmds[0] and "1/2" in cmds[0]


# ── 世界卡三形态(PNG 内嵌 / 裸 JSON / ZIP + lore 文本) ─────


def _make_png_card(path: Path, card: dict) -> None:
    """最小合法 PNG + `chara` tEXt 块(base64 JSON),复用现有提取器可读。"""
    import base64
    import struct
    import zlib

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00")
    chara = b"chara\x00" + base64.b64encode(
        json.dumps(card, ensure_ascii=False).encode("utf-8")
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"tEXt", chara)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def test_detect_source_format_three_shapes(tmp_path: Path):
    from neonrp.core.import_plan import detect_source_format

    assert detect_source_format("card.PNG") == "png-card"
    assert detect_source_format("card.json") == "json-card"
    assert detect_source_format("world.zip") == "zip"
    assert detect_source_format("lore.txt") == "lore-text"
    assert detect_source_format("mystery.dat") == "unknown"


def test_persist_source_card_keeps_zip_and_png_as_is(tmp_path: Path):
    root = tmp_path / "world"
    root.mkdir()
    z = tmp_path / "世界包.zip"
    z.write_bytes(b"PK\x03\x04fake")
    dest = persist_source_card(root, z)
    assert dest.name == "source.zip"
    assert dest.read_bytes() == b"PK\x03\x04fake"  # 原样保存,不改格式


def test_estimate_png_card_uses_embedded_json_not_image_bytes(tmp_path: Path):
    png = tmp_path / "card.png"
    _make_png_card(png, {"name": "mini", "description": "小卡"})
    est = estimate_source(png)
    assert est["format"] == "png-card"
    # 体量按内嵌 JSON 文本算(远小于阈值),不推荐分批
    assert est["recommend_plan"] is False

    big = tmp_path / "big.png"
    _make_png_card(
        big,
        {"name": "epic", "data": {"character_book": {"entries": [{"i": i} for i in range(50)]}}},
    )
    est2 = estimate_source(big)
    assert est2["entries"] == 50
    assert est2["recommend_plan"] is True


def test_validate_plan_optional_source_format_enum():
    good = _plan_dict(["pending"])
    good["source_format"] = "png-card"
    assert validate_plan(good) == []
    bad = _plan_dict(["pending"])
    bad["source_format"] = "rar"
    assert any("source_format" in e for e in validate_plan(bad))


def test_continue_without_plan_keeps_play_mode(tmp_path: Path):
    game = tmp_path / "save-1"
    (game / ".neonrp").mkdir(parents=True)

    ok, launch = _continue(game)

    assert ok is True
    kwargs = launch.call_args.kwargs
    assert kwargs["mode"] == "play"
    assert kwargs.get("startup_commands") is None
