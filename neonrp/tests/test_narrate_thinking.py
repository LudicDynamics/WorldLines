"""The world's beat writes without thinking first (10-19 N2: deepseek thought 10–100 s before the first word in a
quarter to a half of the narration calls, and the 30 s turn ran out with nothing on screen)."""
from neonrp.core import beat_budget
from neonrp.core.llm_openai import _think_off, thinking


def test_thinking_off_asks_deepseek_and_siliconflow_to_write_at_once():
    assert _think_off("https://api.deepseek.com/v1") == {}  # outside: the provider's default
    with thinking(False):
        assert _think_off("https://api.deepseek.com/v1") == {"thinking": {"type": "disabled"}}
        assert _think_off("https://api.siliconflow.com/v1") == {"enable_thinking": False}
        assert _think_off("https://api.openai.com/v1") == {}  # a provider with no such field: nothing is sent
        with thinking(True):
            assert _think_off("https://api.deepseek.com/v1") == {}
    assert _think_off("https://api.deepseek.com/v1") == {}


def test_the_world_beat_does_not_think_unless_it_is_turned_on(monkeypatch):
    monkeypatch.delenv("NEONRP_NARRATE_THINKING", raising=False)
    assert beat_budget.narrate_thinking() is False
    monkeypatch.setenv("NEONRP_NARRATE_THINKING", "1")
    assert beat_budget.narrate_thinking() is True


def test_the_world_beat_starts_with_its_share_even_after_a_long_talk():
    """10-19 N2 M5: talk + characters ran into the world's reserve and its prose got 9 ms – 1 s."""
    import time

    with beat_budget.turn(1.0):
        time.sleep(0.2)
        beat_budget.floor(2.0, "world.floor")
        assert beat_budget.turn_remaining() > 1.9
        with beat_budget.beat("world", reserve=0.5):
            assert beat_budget.remaining() > 1.4
        assert not beat_budget.hits(), "an extended turn is not a timeout"
        assert [c for c in beat_budget.calls() if c.get("beat") == "world.floor" and c["extended_ms"] > 900]
    with beat_budget.turn(5.0):
        beat_budget.floor(2.0)
        assert beat_budget.turn_remaining() > 4.5 and not beat_budget.calls(), "enough left: nothing changes"


def test_the_planning_talk_does_not_think_unless_it_is_turned_on(monkeypatch):
    """10-19 N2 M6: the planning host thought 1.4 s (p90 2.1 s) of the time before the narration's first word."""
    monkeypatch.delenv("NEONRP_PLAN_THINKING", raising=False)
    assert beat_budget.plan_thinking() is False
    monkeypatch.setenv("NEONRP_PLAN_THINKING", "1")
    assert beat_budget.plan_thinking() is True


def test_the_write_down_after_the_prose_thinks_unless_turned_off(monkeypatch):
    """10-20 全线: the transition without thinking left eaten bread / a chewed herb in the bag."""
    monkeypatch.delenv("NEONRP_TRANSITION_THINKING", raising=False)
    assert beat_budget.transition_thinking() is True
    monkeypatch.setenv("NEONRP_TRANSITION_THINKING", "0")
    assert beat_budget.transition_thinking() is False
