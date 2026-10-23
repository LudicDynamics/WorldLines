"""C3-2 (10-06): a Chinese world played in ja / en / ko narrated in Chinese — the narrating calls never got the language line."""
from __future__ import annotations

from test_engine_v3 import _install

from neonrp.core.adv import narrate_lang_line
from neonrp.core.output_lang import write_output_lang


def test_same_language_adds_nothing(tmp_path):
    root = _install(tmp_path)
    assert narrate_lang_line(root, "zh") == ""  # the native run's prompts stay byte-for-byte


def test_player_picked_language_says_world_text_is_material(tmp_path):
    root = _install(tmp_path)
    write_output_lang(root, "ja")
    line = narrate_lang_line(root, "ja")
    assert "日本語" in line and "中国語" in line and "素材" in line


def test_plan_sys_and_narrate_carry_it(tmp_path, monkeypatch):
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    write_output_lang(root, "en")
    assert "only source material" in plan_loop.plan_sys(root)
    assert "only source material" not in plan_loop.plan_sys(None)


def test_soul_turn_line_only_across_languages(tmp_path):
    from neonrp.core.adv import soul_lang_line

    root = _install(tmp_path)
    assert soul_lang_line(root) == ""
    write_output_lang(root, "ko")
    line = soul_lang_line(root)
    assert "한국어" in line and "중국어" in line


def test_away_line_label_follows_the_language():
    from neonrp.core.beat_display import away_lines

    t = [{"iid": "x", "name": "Rowan", "text": "길드 문 앞에 선다."}]
    assert away_lines(None, t)[0].startswith("// 异地 · Rowan")
    assert away_lines(None, t, "ko")[0].startswith("// 다른 곳 · Rowan")
    assert away_lines(None, t, "en")[0].startswith("// elsewhere · Rowan")
