"""prompt_lang / pick_lang (提示词四语,玩家选的语言优先;ko 不再被当成英文)."""
import json
from pathlib import Path

from neonrp.core.adv import world_lang, world_lang_raw
from neonrp.core.output_lang import pick_lang, prompt_lang


def _w(tmp_path: Path, name: str, lore: str = "", output_lang: str | None = None) -> Path:
    root = tmp_path / name
    (root / "game" / "lore").mkdir(parents=True)
    (root / "game" / "lore" / "a.md").write_text(lore, encoding="utf-8")
    if output_lang:
        (root / "game" / "meta").mkdir(parents=True)
        (root / "game" / "meta" / "run_state.json").write_text(json.dumps({"output_lang": output_lang}), encoding="utf-8")
    return root


def test_world_lang_knows_korean(tmp_path):
    assert world_lang_raw(_w(tmp_path, "goblin-ambush-ko", "x")) == "ko"
    assert world_lang_raw(_w(tmp_path, "w1", "고블린이 숲에서 매복하고 있다. " * 5)) == "ko"
    assert world_lang(_w(tmp_path, "w2-ko", "x")) == "en", "旧调用方只认三语,ko 仍按 en"
    assert prompt_lang(_w(tmp_path, "w3-ko", "x")) == "ko"


def test_player_choice_wins_over_world(tmp_path):
    assert prompt_lang(_w(tmp_path, "zhworld", "石津镇的清晨,河灯还亮着。" * 5)) == "zh"
    assert prompt_lang(_w(tmp_path, "zh2", "石津镇的清晨,河灯还亮着。" * 5, output_lang="ko")) == "ko"
    assert prompt_lang(_w(tmp_path, "zh3", "石津镇的清晨。" * 5, output_lang="en-US")) == "en"


def test_pick_lang_falls_back_ko_en_zh():
    assert pick_lang({"zh": "中", "en": "E", "ko": "K"}, "ko") == "K"
    assert pick_lang({"zh": "中", "en": "E"}, "ko") == "E"
    assert pick_lang({"zh": "中"}, "ja") == "中"
    assert pick_lang("plain", "ja") == "plain"
    assert pick_lang({}, "ja", "d") == "d"
