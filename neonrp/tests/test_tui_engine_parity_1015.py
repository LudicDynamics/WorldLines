"""10-15: the TUI caught up with the engine's recent changes —
① the right column reads ownership through the registry (``on`` = ``{{user}}`` / a name / ``{{char}}``; a character's
  things are not in the player's bag);
② a dice event carries its tier (``level``: one name, ``critical``; pct's ``crit`` read as it), the dice line speaks the
  UI language, a special success has its own colour;
③ the judge (Jev) hint only shows while a planning node runs — never in the public engine;
④ the between-beats chat and /login help come from the four-language table; the tables have the same keys;
⑤ the host is shown as 主持 / GM, not "Narrator" / "World"."""
from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
from types import SimpleNamespace

import pytest
from test_app import _setup_project
from test_engine_v3 import _install

from neonrp.core import beat_display as BD
from neonrp.core import beat_events, sdk
from neonrp.core.registry import load_registry
from neonrp.tui import status_side as S


# ── ① ownership ─────────────────────────────────────────────────────────────

def test_status_effects_follow_the_registry_owner(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.name == "艾琳娜")
    sdk.apply(root, [
        {"op": "new", "class": "status", "name": "fx-user", "props": {"on": "{{user}}", "turns": 2}},
        {"op": "new", "class": "status", "name": "fx-name", "props": {"on": elena.name, "turns": 1}},
        {"op": "new", "class": "status", "name": "fx-char", "props": {"on": "{{char}}"}},  # the one character here
        {"op": "new", "class": "status", "name": "fx-legacy", "props": {"on": f"player:{elena.id}"}},
    ], load_registry(root), turn=1)
    d = S.collect(root)
    mine = {fx["name"] for fx in d["player"]["effects"]}
    hers = {fx["name"] for fx in next(a for a in d["agents"] if a["id"] == elena.id)["effects"]}
    assert "fx-user" in mine and not ({"fx-name", "fx-char", "fx-legacy"} & mine)
    assert {"fx-name", "fx-char", "fx-legacy"} <= hers and "fx-user" not in hers


def test_a_characters_things_are_not_in_the_players_bag(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    elena = next(e for e in reg.of_class("soul") if e.name == "艾琳娜")
    sdk.apply(root, [{"op": "new", "class": "carry", "name": "her-dagger", "props": {"on": elena.id, "qty": 1}}],
              load_registry(root), turn=1)
    reg = load_registry(root)
    assert any(e.name == "her-dagger" and reg.owner_of(e) == elena.id for e in reg.of_class("carry"))
    items = {it["name"] for it in S.collect(root)["player"]["items"]}
    assert "her-dagger" not in items and items  # the player's own bag still shows


# ── ② dice tier ─────────────────────────────────────────────────────────────

def _dice_ev(t):
    evs, _ = beat_events.from_traces([{"turn_seq": 1, "apply": {"beat": {"kind": "resolve"}, "tool_returns": [t]}}])
    return next(d for e, d in evs if e == "dice")


def test_dice_events_carry_one_level_name():
    pct = {"request": "dice 1d100 vs 60", "rolls": [2], "total": 2, "vs": 60, "passed": True, "under": True, "level": "crit"}
    assert _dice_ev(pct)["level"] == "crit"  # the pack's own name stays (triggers key on it); renderers read it with outcome_level
    assert BD.outcome_level(_dice_ev(pct)) == "critical"
    assert _dice_ev({**pct, "rolls": [10], "total": 10, "level": "special"})["level"] == "special"
    srd = {"request": "dice 1d20+2 vs 12", "dice": "1d20+2", "rolls": [20], "total": 22, "vs": 12, "passed": True}
    assert _dice_ev(srd)["level"] == "critical"
    assert _dice_ev({**srd, "rolls": [1], "total": 3, "passed": False})["level"] == "fumble"
    assert _dice_ev({**srd, "rolls": [11], "total": 13})["level"] == "success"
    assert "level" not in _dice_ev({"request": "dice 1d6", "rolls": [4], "total": 4})  # no target, no tier


def test_dice_line_speaks_the_ui_language():
    t = {"request": "dice 1d100 vs 60", "rolls": [2], "total": 2, "vs": 60, "passed": True, "under": True, "level": "crit",
         "reason": "search"}
    from neonrp import prompts as _prompts

    for lg in ("en", "ja", "zh"):  # the beat's own words (prompts/beat_display), in the language asked
        assert BD._dice_line(t, lg).endswith("→ " + _prompts.strings("beat_display", lg)["dice_crit"])
    miss = {"request": "dice 1d20 vs 15", "dice": "1d20", "rolls": [7], "total": 7, "vs": 15, "passed": False}
    assert all(BD._dice_line(miss, lg).endswith("→ " + _prompts.strings("beat_display", lg)["dice_fail"]) for lg in ("en", "ko"))


def _accent(widget) -> str:
    return str(widget.content.spans[0].style)  # the glyph span: the tier's accent


def test_special_success_has_its_own_colour():
    from neonrp.tui.app import ConversationView as CV

    special = CV._build_dice_widget("[search: 10 ≤ 60] → Special Success")
    plain = CV._build_dice_widget("[search: 40 ≤ 60] → Success")
    crit = CV._build_dice_widget("[search: 2 ≤ 60] → Success", level="critical")  # the event's level wins over the word
    assert CV._DICE_TIER_STYLE["special"][0] in _accent(special)
    assert CV._DICE_TIER_STYLE["success"][0] in _accent(plain)
    assert CV._DICE_TIER_STYLE["critical"][0] in _accent(crit)
    # a localized label is read in any language, a raw percentile still upgrades to special
    assert CV._dice_tier(None, "スペシャル成功", "30", "60", False) == "special"
    assert CV._dice_tier(None, "成功", "11", "60", False) == "special"
    assert CV._dice_tier("crit", "x", "50", "60", False) == "critical"


# ── ③ the judge hint ────────────────────────────────────────────────────────

def test_judge_hint_only_while_planning(tmp_path, monkeypatch):
    from neonrp.core import node_kinds

    root = _install(tmp_path)
    monkeypatch.setattr(node_kinds, "call", lambda kind, hook, *a, default=None, **k: False if (kind, hook) == ("plan", "active") else default)
    p = S.collect(root)["player"]
    assert not p.get("judge") and "⚖" not in S.render_player("zh", p).plain
    monkeypatch.setattr(node_kinds, "call", lambda kind, hook, *a, default=None, **k: True if (kind, hook) == ("plan", "active") else default)
    p = S.collect(root)["player"]
    assert p.get("judge") and "⚖" in S.render_player("zh", p).plain


def test_public_engine_never_shows_the_judge(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    root = _install(tmp_path)
    assert S.judge_matters(root) is False
    p = S.collect(root)["player"]
    assert not p.get("judge") and "/login" not in S.render_player("en", p).plain


@pytest.mark.parametrize("active", [False, True])
def test_status_account_and_plan_show_the_judge_only_while_planning(tmp_path, monkeypatch, active):
    from neonrp.tui import play_commands as PC
    from neonrp.tui.app import ConversationView, NeonRPApp

    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setattr(S, "judge_matters", lambda root: active)
    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test() as pilot:
            PC.cmd_account(app, [])
            PC.cmd_plan(app, [])
            await pilot.pause(0.1)
            out = "\n".join(str(w.content) for w in app.query_one("#conversation-view", ConversationView).query(".pc-status"))
            assert ("⚖" in out) is active
            app._handle_slash_command("/status account")  # 10-23: the /status screen's usage tab says the same
            await pilot.pause(0.1)
            assert ("⚖" in str(app.screen.query_one("#status-tab-body").content)) is active

    asyncio.run(scenario())


# ── ④ copy from the four-language table ─────────────────────────────────────

def test_i18n_tables_share_every_key():
    from neonrp.tui.i18n import _MESSAGES as M

    keys = set().union(*(set(v) for v in M.values()))
    assert {loc: sorted(keys - set(v)) for loc, v in M.items()} == {loc: [] for loc in M}


def test_interlude_chat_has_no_hardcoded_cjk():
    import re

    from neonrp.tui.app import NeonRPApp

    tree = ast.parse(textwrap.dedent(inspect.getsource(NeonRPApp._try_interlude_chat)))
    fn = tree.body[0]
    doc = fn.body[0].value if isinstance(fn.body[0], ast.Expr) else None
    cjk = re.compile(r"[぀-ヿ一-鿿가-힯]")
    bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n is not doc and cjk.search(n.value)]
    assert not bad, bad


def test_login_help_is_localized():
    from neonrp.tui.commands import localized_spec

    assert "account" in localized_spec("login", "en")["help"]
    assert "アカウント" in localized_spec("login", "ja")["help"]
    assert "계정" in localized_spec("login", "ko")["help"]
    assert "账号" in localized_spec("login", "zh")["help"]


# ── ⑤ the host label ───────────────────────────────────────────────────────

@pytest.mark.parametrize(("loc", "label"), [("zh", "主持"), ("en", "GM"), ("ja", "GM")])
def test_the_host_is_shown_as_host_not_narrator(loc, label):
    from unittest.mock import MagicMock

    from neonrp.tui.app import ConversationView

    view = ConversationView()
    view._app_context = SimpleNamespace(ui_locale=loc, root=None)
    view.write_markdown = MagicMock()
    view.add_markdown_message("雾从河面升起。")
    assert f"### {label}\n" in view.write_markdown.call_args[0][0]
    view.write_markdown.reset_mock()
    view.add_assistant_chunk("x")  # the default speaker ("Narrator")
    assert view.write_markdown.call_args_list[0][0][0] == f"\n### {label}\n\n"
    assert view._resolve_agent_transcript_meta("World")[0] == label


def test_bridge_gets_the_host_label():
    from neonrp.tui.app import ConversationView

    sent = []
    view = ConversationView()
    view._app_context = SimpleNamespace(ui_locale="zh", root=None, _emit_bridge_event=lambda kind, **kw: sent.append(kw))
    view._emit_turn_to_bridges([("Narrator", "雾。")])
    view._emit_turn_to_bridges([("", "雾。")])
    assert [s["speaker"] for s in sent] == ["主持", "主持"]
