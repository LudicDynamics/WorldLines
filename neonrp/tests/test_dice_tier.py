"""The prose never claims a tier the dice did not give (10-17: the narration said 「大成功」, the engine rolled a
plain 64).

Three ways it happened: the narrator wrote the outcome in the same line after its own ``[dice]`` (the stop point only
cut the lines after it, and the stream only stopped at a line that starts with ``[``); it wrote the outcome before the
request; or, for a check agreed in the talk, it was told only 「→ 成功」 and dressed it up as 大成功. The stop point is
now the request itself, the agreed checks' lines name the tier, and ``core.dice.tier_guard`` puts back any tier word
the beat's rolls did not reach (the words are the pack's strings, four languages)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from neonrp import prompts, template
from neonrp.core import beat_events, dice, sdk, turn_v3
from neonrp.core.registry import load_registry
from neonrp.core.stream_lines import LinesFilter
from neonrp.packs.pct import rules as R
from neonrp.packs.pct import tools as T
from _paths import PRODUCT

try:  # the planning beat lives in the private layer (10-10 R1)
    from neonrp.core import plan_loop
except ImportError:
    plan_loop = None

TPL = PRODUCT / "templates" / "pct-house.template"


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dest = tmp_path / "run"
    template.build(template.load(TPL), dest)
    return dest


class _Streaming:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)

    def chat(self, messages, tools=None):
        text = self.outputs.pop(0) if self.outputs else ""
        return SimpleNamespace(message=SimpleNamespace(content=text), usage={})

    def chat_stream(self, messages, tools=None):
        text = self.outputs.pop(0) if self.outputs else ""
        for i in range(0, len(text), 3):
            yield SimpleNamespace(delta=text[i:i + 3], thinking=None, tool_call_starts=None, finished=False)


@pytest.fixture
def narrate(monkeypatch):
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    yield
    turn_v3.ADAPTER_FACTORY = None
    turn_v3.STREAM.update(on_text=None, on_event=None, shown=False, skip=None)


def _solve(world, monkeypatch, outputs, roll, **kw):
    monkeypatch.setattr(T, "_d100", lambda seed, key: roll)
    a = _Streaming(outputs)
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: a)
    shown: list[str] = []
    turn_v3.STREAM.update(on_text=shown.append, on_event=None, shown=False)
    out = turn_v3.solve_turn(world, user_text="我找暗门", provider=None, turn=1, soul_reports=[], **kw)
    return out, "".join(shown)


_STATE = "<vars>\n</vars>\n<files>\n</files>"


# ── the guard itself ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lang,crit,word", [("zh", "大成功", "成功"), ("en", "critical success", "success"),
                                            ("ja", "クリティカル", "成功"), ("ko", "대성공", "성공")])
def test_a_tier_the_dice_did_not_give_is_put_back_in_every_language(lang, crit, word):
    S = prompts.strings("pct", lang)
    text, fixed = dice.tier_guard(f"— {crit}! —", ["success"], S["tier_words"], S)
    assert crit not in text and word in text and fixed and fixed[0]["tier"] == "crit"
    kept, none = dice.tier_guard(f"— {crit}! —", ["crit"], S["tier_words"], S)
    assert kept == f"— {crit}! —" and not none, "a real critical keeps its word"
    same, nothing = dice.tier_guard(f"— {crit}! —", [], S["tier_words"], S)
    assert same == f"— {crit}! —" and not nothing, "no roll this beat: nothing to contradict"


def test_the_guard_reads_whole_words_in_latin_scripts():
    S = prompts.strings("pct", "en")
    text, fixed = dice.tier_guard("A critical failure. The critical hour.", ["success"], S["tier_words"], S)
    assert text == "A success. The critical hour." and [f["tier"] for f in fixed] == ["fumble"]


# ── the stop point is the request, not its line ──────────────────────────────────────────────────────────────────


def test_words_after_a_request_in_the_same_line_are_cut_and_never_streamed():
    raw = "<lines>\n你蹲下身。\n你摸着砖缝[dice 侦查]找暗门[/dice]——大成功！你一眼看出那块砖是活的。\n后来都顺了。\n</lines>"
    o = sdk.parse_adv(raw)
    assert o.prefix == "你蹲下身。\n你摸着砖缝" and o.ops[0]["op"] == "dice" and o.ops[0]["reason"] == "找暗门"
    whole = LinesFilter().feed(raw)
    f = LinesFilter()
    pieces = "".join(f.feed(c) for c in raw)
    assert whole == pieces == "你蹲下身。\n你摸着砖缝" and f.cut == "你摸着砖缝", "no newline yet: the continuation may finish that line"
    two = sdk.parse_adv("<lines>\n攻击[dice 1d100 vs 50] [dice 1d100 vs 30]然后打中了\n</lines>")
    assert two.prefix == "攻击" and len(two.ops) == 2, "several requests at one stop point are all asked"
    prose = LinesFilter()
    assert "".join(prose.feed(c) for c in "<lines>\n门上贴着[禁入]两个字。\n[dice 1d100 vs 50]\n后面</lines>") == "门上贴着[禁入]两个字。\n"


# ── skill 50, rolled 64: the narration never says 大成功 ─────────────────────────────────────────────────────────


def test_skill_50_rolled_64_the_narrators_own_dice_never_reads_as_a_critical(world, monkeypatch, narrate):
    out, screen = _solve(world, monkeypatch, [
        "<lines>\n你蹲下身。\n你摸着砖缝[dice 1d100 vs 50]找暗门[/dice]——大成功！你一眼看出那块砖是活的。\n</lines>",
        "<lines>\n大成功——砖松了一点,又卡住。\n[options 再推 | 换个地方]\n</lines>",
        _STATE], roll=64)
    die = next(t for t in out["tool_returns"] if str(t.get("request") or "").startswith("dice"))
    assert die["total"] == 64 and die["level"] == "fail" and not die["passed"]
    assert "大成功" not in out["narration"] and "一眼看出" not in out["narration"]
    assert "大成功" not in screen and "一眼看出" not in screen, "the blind half-line never reached the screen"
    assert any(s.get("actor") == "dice_tier" for s in out["spans"]), "the rewrite is on the record"


@pytest.mark.skipif(plan_loop is None, reason="needs the private layer (the planning beat)")
def test_skill_50_rolled_64_an_agreed_check_is_told_with_its_tier_and_the_prose_follows_it(world, monkeypatch, narrate):
    reg = load_registry(world)
    reg.entries["player"].props.setdefault("skills", {})
    monkeypatch.setattr(T, "_d100", lambda seed, key: 64)
    from neonrp.packs.rpg import panel as _panel

    monkeypatch.setattr(_panel, "skill", lambda *a, **k: {"label": "侦查", "value": 50, "source": "sheet", "key": "search"})  # the rule panel (BRP, 10-14)
    r = R.roll_check(world, reg, {"text": "玩家 侦查 为了找暗门", "who": "player", "why": "找暗门"}, seed="t")
    assert r["a"]["roll"] == 64 and r["a"]["target"] == 50 and r["a"]["level"] == "fail"
    line = plan_loop.check_line(reg, r)
    assert line.endswith("→ 失败(找暗门)") and "大成功" not in line
    out, _ = _solve(world, monkeypatch, ["<lines>\n大成功!你的指尖一下就摸到了那块松动的砖。\n</lines>", _STATE], roll=64, rolled=[r])
    assert "大成功" not in out["narration"] and "失败" in out["narration"]
    ev = plan_loop.dice_events([{**r, "line": line}])
    assert ev == [{"request": "dice 1d100", "who": "player", "label": "侦查", "reason": "找暗门", "total": 64, "vs": 50,
                   "under": True, "passed": False, "text": line, "level": "fail"}]


@pytest.mark.skipif(plan_loop is None, reason="needs the private layer (the planning beat)")
def test_an_ordinary_success_is_named_success_and_a_real_critical_keeps_its_word(world, monkeypatch, narrate):
    reg = load_registry(world)
    from neonrp.packs.rpg import panel as _panel

    monkeypatch.setattr(_panel, "skill", lambda *a, **k: {"label": "侦查", "value": 70, "source": "sheet", "key": "search"})  # the rule panel (BRP, 10-14)
    for roll, word in ((64, "→ 成功("), (3, "→ 大成功(")):
        monkeypatch.setattr(T, "_d100", lambda seed, key, roll=roll: roll)
        r = R.roll_check(world, reg, {"text": "玩家 侦查 为了找暗门", "who": "player", "why": "找暗门"}, seed="t")
        assert word in plan_loop.check_line(reg, r)
    out, _ = _solve(world, monkeypatch, ["<lines>\n大成功!砖后面是空的。\n</lines>", _STATE], roll=3, rolled=[r])
    assert "大成功" in out["narration"]


def test_the_agreed_checks_reach_a_front_end_as_dice_events_with_their_tier():
    tr = {"turn_seq": 3, "apply": {"beat": {"kind": "resolve", "rolled": ["[调查员 侦查(找暗门): 64 > 50] → 失败"],
                                            "dice": [{"request": "dice 1d100", "who": "player", "label": "侦查", "total": 64, "vs": 50,
                                                      "under": True, "passed": False, "level": "fail", "text": "[调查员 侦查(找暗门): 64 > 50] → 失败"}]},
                                   "narration_plain": "砖没动。",
                                   "tool_returns": [{"request": "dice 1d100 vs 40", "text": "3 ≤ 40 —— 大成功", "total": 3, "vs": 40,
                                                     "passed": True, "under": True, "level": "crit", "label": ""}]}}
    evs = [e for k, e in beat_events.from_traces([tr])[0] if k == "dice"]
    assert [(e["total"], e["level"]) for e in evs] == [(64, "fail"), (3, "crit")]
    assert evs[0]["label"] == "侦查" and evs[0]["vs"] == 50 and evs[0]["under"] is True


# ── the die plays the moment its tool returns (10-17: 由这个 tool call 直接触发动画) ──────────────────────────


def test_a_die_goes_out_as_dice_rolled_the_moment_its_tool_returns_and_only_for_its_own_world(world, tmp_path):
    from neonrp.core import tool_watch, topics
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.message_bus import InProcessBus

    class _S:  # the session's two fields the watcher reads
        def __init__(self, root):
            self.root, self._session_bus = root, InProcessBus()

    import gc

    # an earlier test's session may be gone but still on the list (it unwatches itself on the next die): let it go now,
    # so the count below is only this test's
    gc.collect()
    tool_watch.notify(tmp_path / "nowhere", "dice", {}, {"ok": True, "total": 1}, record=False)
    n0 = len(tool_watch._WATCHERS)
    s, other = _S(world), _S(tmp_path / "elsewhere")
    got: list[dict] = []
    s._session_bus.subscribe(topics.ENGINE_BEAT, lambda m: got.append(dict(m.payload)))
    ConversationSession._watch_dice(s)
    ConversationSession._watch_dice(other)
    reg = load_registry(world)
    try:
        r = tool_watch.call(world, reg, "dice", "neonrp.packs.pct.tools:dice", {"dice": "1d100", "vs": 50, "reason": "找暗门", "seed_key": "k"}, seed="x", source="narrator")
        d = next(x for x in got if x.get("kind") == "dice.rolled")
        assert d["live"] and d["total"] == r["total"] and d["vs"] == 50 and d["level"] == r["level"] and d["passed"] == r["passed"]
        assert d["reason"] == "找暗门" and d["crit_max"] == 3 and d["fumble_min"] == 99 and d["source"] == "narrator"
        n = len(got)
        tool_watch.call(world, reg, "map", "neonrp.packs.rpg.atlas.draw:draw_map", {}, seed="x")
        assert len(got) == n, "only dice / san"
        other_root = tmp_path / "elsewhere"
        tool_watch.notify(other_root, "dice", {}, {"ok": True, "total": 7}, record=False)
        assert len(got) == n, "a die of another world is not this session's"
    finally:
        del s, other
        gc.collect()
        tool_watch.notify(world, "dice", {}, {"ok": True, "total": 1}, record=False)  # a gone session unwatches itself
    assert len(tool_watch._WATCHERS) == n0


def test_live_dice_is_none_for_what_is_not_a_roll():
    assert beat_events.live_dice({"tool": "dice", "result": {"ok": False, "why": "bad dice"}}) is None
    assert beat_events.live_dice({"tool": "dice", "result": {"ok": True, "text": "x"}}) is None
    d = beat_events.live_dice({"tool": "dice", "args": {"who": "player", "label": "侦查"}, "result": {"ok": True, "total": 9, "rolls": [4, 5], "dice": "2d6"}, "turn": 2})
    assert d["kind"] == "dice.rolled" and d["total"] == 9 and d["who"] == "player" and d["label"] == "侦查" and "vs" not in d


@pytest.mark.parametrize("lang,fail,crit", [("zh", "失败", "大成功"), ("en", "failure", "critical"), ("ja", "失敗", "クリティカル"), ("ko", "실패", "대성공")])
def test_the_tui_dice_line_speaks_the_runs_language_and_names_the_engines_tier(lang, fail, crit):
    from neonrp.core.beat_display import _dice_line
    from neonrp.tui.app import ConversationView

    t = {"total": 64, "vs": 50, "under": True, "passed": False, "level": "fail", "reason": "找暗门"}
    assert _dice_line(t, lang) == f"[找暗门: 64 > 50] → {fail}"
    c = _dice_line({**t, "total": 3, "passed": True, "level": "crit"}, lang)
    assert c == f"[找暗门: 3 ≤ 50] → {crit}" and ConversationView._DICE_LINE_RE.match(c)
    assert _dice_line({"total": 14, "vs": 12, "rolls": [12], "passed": True, "reason": "撬锁"}, lang).endswith(
        prompts.strings("beat_display", lang)["dice_success"]), "no tier (d20): pass / fail in the run's language"


# ── a line is there once (10-17: under the card the same line showed twice) ──────────────────────────────────────


@pytest.mark.parametrize("cont", ["你摸着砖缝,一块砖松了。\n灰落下来。", "你摸着砖缝\n灰落下来。", "灰落下来。"])
def test_a_continuation_that_restates_the_cut_line_shows_it_once(world, monkeypatch, narrate, cont):
    out, screen = _solve(world, monkeypatch, [
        "<lines>\n你蹲下身。\n你摸着砖缝[dice 1d100 vs 50]找暗门[/dice]——大成功！\n</lines>",
        f"<lines>\n{cont}\n[options 再推 | 换个地方]\n</lines>", _STATE], roll=64)
    for name, text in (("narration", out["narration"]), ("screen", screen)):
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        assert len(set(lines)) == len(lines), (name, lines)
        assert sum(x.startswith("你摸着砖缝") for x in lines) == 1, (name, lines)
        assert lines[-1] == "灰落下来。" and lines[0] == "你蹲下身。", (name, lines)
