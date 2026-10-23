"""开场旁白四语:game-start.json 的 opening_scene / opening_choices 可写成 {zh,en,ja,ko},按本局语言取,
缺的语言 ko→en→zh 回退;旧的单语字符串/列表照旧可用;日韩开始口令能被认出;所有内置世界四语齐全。"""
import json
from pathlib import Path

import pytest

from neonrp.core.output_lang import pick_opening
from neonrp.core.opening import START_CUE, authored_opening, is_start_cue, start_cue

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "neonrp" / "templates"


def _world(tmp_path: Path, startup: dict, *, name: str = "w", output_lang: str | None = None) -> Path:
    root = tmp_path / name
    meta = root / "game" / "meta"
    meta.mkdir(parents=True)
    (meta / "game-start.json").write_text(json.dumps({"startup": startup}, ensure_ascii=False), encoding="utf-8")
    if output_lang:
        (meta / "run_state.json").write_text(json.dumps({"output_lang": output_lang}), encoding="utf-8")
    (root / "game" / "lore").mkdir()
    (root / "game" / "lore" / "a.md").write_text("石津镇的清晨,河灯还亮着。" * 5, encoding="utf-8")
    return root


FOUR = {
    "opening_scene": {"zh": "雾里的门。", "en": "A gate in the fog.", "ja": "霧の中の門。", "ko": "안개 속의 문."},
    "opening_choices": {"zh": ["进门", "等一等"], "en": ["Go in", "Wait"], "ja": ["入る", "待つ"], "ko": ["들어간다", "기다린다"]},
}


@pytest.mark.parametrize("lang,scene,first", [("zh", "雾里的门。", "进门"), ("en", "A gate in the fog.", "Go in"),
                                              ("ja", "霧の中の門。", "入る"), ("ko", "안개 속의 문.", "들어간다")])
def test_four_language_dict_follows_the_run_language(tmp_path, lang, scene, first):
    out = authored_opening(_world(tmp_path, FOUR, output_lang=lang))
    assert out.startswith(scene) and f"① {first}" in out


def test_missing_language_falls_back_ko_en_zh(tmp_path):
    st = {"opening_scene": {"zh": "中文开场", "en": "English opening"}, "opening_choices": [{"zh": "甲", "en": "A"}, {"zh": "乙"}]}
    assert pick_opening(st, "ko") == ("English opening", ["A", "乙"])
    assert pick_opening(st, "ja") == ("English opening", ["A", "乙"])
    assert pick_opening({"opening_scene": {"zh": "只有中文"}}, "ko") == ("只有中文", [])


def test_old_plain_format_still_works(tmp_path):
    root = _world(tmp_path, {"opening_scene": "旧格式开场。", "opening_choices": ["一", "二", "三", "四", "五"]}, output_lang="ko")
    out = authored_opening(root)
    assert out.startswith("旧格式开场。") and "④ 四" in out and "五" not in out


def test_start_cue_in_four_languages(tmp_path):
    root = _world(tmp_path, FOUR)
    for t in ("开始游戏", "Start the game", "ゲーム開始", "ゲームを始める", "冒険を始めよう", "게임 시작", "게임을 시작", "모험 시작", "시작"):
        assert is_start_cue(root, t), t
    assert not is_start_cue(root, "시작하기 전에 이 문서 좀 볼게")  # bare 시작 inside a sentence is not a cue
    assert start_cue(root) == START_CUE["zh"]
    assert start_cue(_world(tmp_path, FOUR, name="k", output_lang="ko")) == "게임 시작"
    assert is_start_cue(root, start_cue(_world(tmp_path, FOUR, name="j", output_lang="ja")))


def test_played_copy_of_a_suffixed_world_keeps_its_language(tmp_path):
    """A played copy is named <world>-YYYYMMDD-HHMMSS; sakura-hallway-ko has no lore, so the -ko suffix (or its
    one-language summary) must decide — before this, the copy opened in Chinese."""
    from neonrp.core.output_lang import prompt_lang

    st = {**FOUR, "opening_scene": FOUR["opening_scene"]}
    root = tmp_path / "sakura-hallway-ko-20261005-101500"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "game-start.json").write_text(json.dumps({"startup": st}, ensure_ascii=False), encoding="utf-8")
    assert prompt_lang(root) == "ko" and authored_opening(root).startswith("안개 속의 문.")
    other = tmp_path / "some-world-20261005-101500"
    (other / "game" / "meta").mkdir(parents=True)
    (other / "game" / "meta" / "game-start.json").write_text(json.dumps(
        {"summary": "사월, 벚꽃이 만개한 비탈.", "startup": st}, ensure_ascii=False), encoding="utf-8")
    assert prompt_lang(other) == "ko", "no lore, no suffix: the one-language summary decides"


def _game_starts():
    return sorted(TEMPLATES.glob("*/game/meta/game-start.json"))


@pytest.mark.parametrize("path", _game_starts(), ids=lambda p: p.parts[-4])
def test_every_built_in_world_has_a_four_language_opening(path):
    st = json.loads(path.read_text(encoding="utf-8"))["startup"]
    scene, choices = st["opening_scene"], st["opening_choices"]
    assert isinstance(scene, dict) and set(scene) >= {"zh", "en", "ja", "ko"}
    assert all(isinstance(scene[k], str) and scene[k].strip() for k in ("zh", "en", "ja", "ko"))
    assert isinstance(choices, dict) and set(choices) >= {"zh", "en", "ja", "ko"}
    assert len({len(choices[k]) for k in ("zh", "en", "ja", "ko")}) == 1 and 2 <= len(choices["zh"]) <= 4
