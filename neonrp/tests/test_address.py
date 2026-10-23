"""寻址接口(@/#)— M24 §0.5 契约回归:一套语法,永不吞输入。"""

import shutil
from pathlib import Path

from neonrp.core.address import parse_address

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


def test_at_name_local_routes_to_dialogue(tmp_path: Path) -> None:
    root = _install(tmp_path)
    out = parse_address(root, "@艾琳娜 早,昨晚睡得好吗?")
    assert out == {"lane": "dialogue", "target": "si-elena0001", "text": "早,昨晚睡得好吗?"}


def test_at_english_first_name_and_fullwidth(tmp_path: Path) -> None:
    root = _install(tmp_path)
    assert parse_address(root, "@Elena morning")["target"] == "si-elena0001"
    assert parse_address(root, "@艾琳娜:走吗")["text"] == "走吗"  # 全角@ + 冒号剥离


def test_hash_routes_to_room(tmp_path: Path) -> None:
    root = _install(tmp_path)
    out = parse_address(root, "#大家早")
    assert out["lane"] == "room" and out["text"] == "大家早"
    assert parse_address(root, "# 有人吗")["text"] == "有人吗"
    # 裸 #(无正文)→ text 空:调用方视作「打开房间/看在场」,不发 "#" 本身。
    bare = parse_address(root, "#")
    assert bare["lane"] == "room" and bare["text"] == ""


def test_unknown_at_falls_back_to_world(tmp_path: Path) -> None:
    # 寻址永不吞输入:@ 后不是已知名字 → 原文进世界拍。
    root = _install(tmp_path)
    out = parse_address(root, "@神秘人 你是谁")
    assert out["lane"] == "world" and out["text"] == "@神秘人 你是谁"


def test_plain_action_is_world(tmp_path: Path) -> None:
    root = _install(tmp_path)
    out = parse_address(root, "推门走进旅店")
    assert out["lane"] == "world" and out["text"] == "推门走进旅店"


def test_at_name_only_opens_dialogue(tmp_path: Path) -> None:
    root = _install(tmp_path)
    out = parse_address(root, "@艾琳娜")
    assert out["lane"] == "dialogue" and out["target"] == "si-elena0001" and out["text"] == ""
