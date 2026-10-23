"""引擎里给模型 / 玩家的字搬进四语表(10-15):委托状态词、开场 cue 与主持名、捏人「帮我写」的提示与示例。
代码里只剩认字的正则和内部标点(见 tests/data/prompt_cjk_cap.json 的 _reasons)。"""
from __future__ import annotations

from neonrp import prompts
from neonrp.core import objective, opening
from neonrp.template import builder


def test_job_words_cover_every_state_in_every_language():
    for lg in prompts.LANGS:
        words = prompts.strings("objective", lg)["job_words"]
        assert set(words) == {*objective.JOB_STATES, "hidden"}, lg
    assert objective.job_state("進行中") == "active" and objective.job_state("완료") == "done" and objective.job_state("已放弃") == "abandoned"
    assert objective.job_state("ロック") is None and objective.job_state("Completed") == "done"


def test_opening_cue_and_host_label_are_per_language(tmp_path):
    assert opening.START_CUE["zh"] == "开始游戏" and opening.START_CUE["en"] == "Start the game"
    assert {lg: prompts.strings("opening", lg)["host"] for lg in prompts.LANGS} == {"zh": "主持", "en": "Host", "ja": "進行役", "ko": "진행자"}


def test_builder_texts_come_from_the_tables():
    assert set(builder.GEN_SYSTEM) == set(prompts.LANGS) and builder.GEN_SYSTEM["zh"].startswith("你在帮玩家写")
    assert builder.EXAMPLE["en"].startswith("You grew up in a rainy city")
