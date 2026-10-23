"""The state transition names the rule pack's own ops (10-19, two-beat fixes A): a table phase written as a variable is
refused (engine-owned), seat votes written as variables do not exist — the transition now lists the pack's own moves
(``{pack_ops}``, core/adv.pack_ops_lines) and says they are written as ops, never as variables."""
from __future__ import annotations

import pytest

from neonrp import template as TP
from neonrp.core import adv
from neonrp.core.registry import load_registry
from neonrp.prompts import LANGS
from neonrp import prompts as P


def _reg(tid, tmp_path):
    found = TP.discover()
    if tid not in found:
        pytest.skip(f"{tid}: not in this checkout")
    TP.build(TP.load(found[tid]), tmp_path / "run")
    return load_registry(tmp_path / "run")


def test_a_table_game_lists_its_own_moves(tmp_path):
    names = [ln.split()[0] for ln in adv.pack_ops_lines(_reg("werewolf-night-village", tmp_path), "zh").splitlines()]
    assert names == ["vote", "kill", "phase"], names


def test_the_generic_ops_the_transition_already_teaches_are_left_out(tmp_path):
    names = {ln.split()[0] for ln in adv.pack_ops_lines(_reg("stoneford-town", tmp_path), "zh").splitlines()}
    assert names and not names & adv.GENERIC_STATE_OPS, names & adv.GENERIC_STATE_OPS
    assert "trade" in names


def test_a_pack_with_none_lists_nothing(tmp_path):
    assert adv.pack_ops_lines(_reg("pct-house", tmp_path), "zh") == ""


@pytest.mark.parametrize("lang", LANGS)
def test_every_transition_takes_the_pack_ops_and_keeps_its_shape(lang):
    raw = P.md_by_lang("transition")[lang]
    out = raw.format(lines="L", tools="T", pack_ops="vote <x> <y>")
    assert "vote <x> <y>" in out and out.index("vote <x> <y>") < out.rindex("<vars>"), "the pack's ops come before <vars>"
    assert out.rindex("<vars>") > out.index("vote <x> <y>")
