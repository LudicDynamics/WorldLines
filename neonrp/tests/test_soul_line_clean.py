"""角色台词不带回包的机器块(10-15,player2:浏览器版 S-judge 下,一个角色把整段 <lines>…</lines><fields>…</fields> 带上了屏幕)。
S-judge / S-free 的台词、商量拍 script 里的角色行都只留说的话。"""
from __future__ import annotations

from unittest.mock import patch

from neonrp.core import beat_events
from neonrp.core.soul_result import clean_line

RAW = "<lines>\n「我跟你去。」\n</lines>\n<fields>\nattitude: comply\nfollow: 1\nstay: 0\n</fields>"


def test_clean_line_keeps_only_what_she_says():
    assert clean_line(RAW) == "「我跟你去。」"
    assert clean_line("「好。」\n<fields>\nfollow: 1") == "「好。」", "an unclosed fields block too"
    assert clean_line("「先这样。」<draft>去码头</draft>") == "「先这样。」"
    assert clean_line("她点点头。") == "她点点头。"


def test_the_planning_script_is_cleaned():
    tr = {"turn_seq": 2, "apply": {"beat": {"kind": "plan", "script": [{"who": "薇拉", "role": "soul", "text": RAW},
                                                                         {"who": "主持", "role": "host", "text": "雾更浓了。"}]}}}
    evs, _ = beat_events.from_traces([tr])
    pb = dict(evs)["plan.beat"]
    assert [x["text"] for x in pb["script"]] == ["「我跟你去。」", "雾更浓了。"]


def test_s_judge_and_s_free_lines_are_cleaned(tmp_path):
    from neonrp import template as TP
    from _paths import PRODUCT_TEMPLATES
    from neonrp.packs.rpg import soul_step

    root = tmp_path / "run"
    TP.build(TP.load(PRODUCT_TEMPLATES / "wuwu.template"), root)
    iid = next(p.name.split("-", 1)[1] for p in (root / "souls").iterdir() if p.name.startswith("vera-"))
    with patch("neonrp.core.light_chat.ask_soul_deliver", lambda *a, **k: {"ok": True, "answer": RAW}):
        r = soul_step._soul_step_free(root, iid, situation="……", depth="speak", provider=None, mode="play", registry=None)
    assert r["text"] == "「我跟你去。」"
