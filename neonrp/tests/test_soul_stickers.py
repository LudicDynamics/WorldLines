"""角色专属表情包第一批(10-19 出图 · lead 10-20 接线):艾琳娜 · 乐师 · 薇拉各 6 张。小手机从角色的来源文件夹读
(soul_chat.sticker_dir:模板 / 内置世界里它的文件夹 stickers/),不分语言 —— 每个世界 × 四语都一样:「TA 专属」有 6 张,
含义按聊天语言,模型提示词里列出 soul:<id>(含义 · 什么时候发);带走以后照样有。stub 模型。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp.core import player_data, soul_chat
from neonrp.core.llm import LLMTurnResult, Message
from neonrp.core.soul_orchestration import STICKER_MAX

LANGS = ("zh", "en", "ja", "ko")
STONEFORD = ("stoneford-elena", "stoneford-market", "stoneford-three-towns", "stoneford-town")
# world → (sid, the folder the phone reads, relative to the repo)
CAST = {**{t: ("elena", "src/neonrp/templates/stoneford-elena/souls/elena-si-elena0001") for t in STONEFORD},
        "spice-witch": ("maestro", "worldlines/templates/spice-witch.template/world/souls/maestro-si-maestro01"),
        "wuwu": ("vera", "worldlines/templates/wuwu.template/world/souls/vera-si-vera0001")}
REPO = Path(__file__).resolve().parents[1]


class Fake:
    def __init__(self, raw="嗯。"):
        self.raw, self.calls = raw, []

    def chat(self, messages, tools=None):
        self.calls.append((messages[0].content, messages[1].content))
        return LLMTurnResult(message=Message(role="assistant", content=self.raw), finished=True, usage={})


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = tmp_path / "store"
    for t in CAST:
        shutil.copytree(PRODUCT_TEMPLATES / f"{t}.template", s / f"{t}.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    return s


def _meta(rel: str) -> dict:
    return json.loads((REPO / rel / "stickers" / "stickers.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("tpl", list(CAST))
def test_the_pictures_are_niko_s_and_match_the_meanings(tpl):
    _, rel = CAST[tpl]
    d = REPO / rel / "stickers"
    meta = _meta(rel)
    pngs = sorted(p.stem for p in d.glob("*.png"))
    assert pngs == sorted(meta) and len(pngs) == 6, "one picture per meaning, six"
    from PIL import Image

    for p in d.glob("*.png"):
        im = Image.open(p)
        assert im.size == (512, 512) and im.mode == "RGBA" and p.stat().st_size <= STICKER_MAX, p.name
        a = im.getchannel("A")
        assert [a.getpixel(xy) for xy in ((0, 0), (511, 0), (0, 511), (511, 511))] == [0, 0, 0, 0], f"{p.name}: corners transparent"
    for m in meta.values():
        assert set(m["label"]) == set(LANGS) and m["when"]


@pytest.mark.parametrize("tpl", list(CAST))
@pytest.mark.parametrize("lang", LANGS)
def test_every_world_every_language_shows_six_and_tells_the_model(store, tpl, lang):
    sid, rel = CAST[tpl]
    c = soul_chat.resolve(tpl, sid)
    assert c["access"] == "standalone"
    src = store / rel.removeprefix("worldlines/templates/") if rel.startswith("worldlines/") else REPO / rel   # the store's copy · the built-in world
    assert soul_chat.sticker_dir(c).resolve() == (src / "stickers").resolve(), "read from its source folder"
    meta = _meta(rel)
    th = soul_chat.thread(tpl, sid, lang)
    own = th["stickers"]["soul"]
    assert [s["id"] for s in own] == [f"soul:{i}" for i in sorted(meta)], "the 「TA 专属」tab: six"
    assert all(s["label"] == meta[s["id"][5:]]["label"][lang] for s in own), "meanings in the chat's language"
    for s in own:
        f = soul_chat.sticker_file(tpl, sid, s["id"][5:])
        assert f is not None and f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and s["url"].startswith("/api/v1/chat/sticker?")
    fake = Fake("你好。\n[sticker soul:hi]" if "hi" in meta else "你好。")
    out = soul_chat.send(tpl, sid, text="在吗", lang=lang, adapter=fake)
    system = fake.calls[0][0]
    for i, m in meta.items():
        assert f"soul:{i}({m['label'][lang]} · {m['when']})" in system, f"the model is told about soul:{i}"
    if "hi" in meta:
        assert out["messages"][-1] == {**out["messages"][-1], "kind": "sticker", "sticker": "soul:hi"}, "and it can send one"


def test_a_character_taken_home_keeps_them(store, tmp_path):
    """Gained from a run built in another language (the i18n overlay souls): the phone still reads the source's six."""
    from neonrp import template as TP
    from neonrp.core.worldmap import soul_dir_iid

    run = tmp_path / "run"
    TP.build(TP.load(store / "stoneford-town.template"), run, lang="ja")
    sdir = next((run / "souls").glob("elena-*"))
    assert player_data.gain(run, soul_dir_iid(sdir), "companion_at_ending")
    c = soul_chat.resolve("stoneford-town", "elena")
    assert c["access"] == "obtained"
    assert len(soul_chat.thread("stoneford-town", "elena", "ja")["stickers"]["soul"]) == 6
