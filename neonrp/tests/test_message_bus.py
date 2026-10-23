"""M18 Phase 2 — the in-process message bus."""

from __future__ import annotations

from neonrp.core.message_bus import InProcessBus, topic_matches


# ---- topic matching ------------------------------------------------------
def test_topic_exact_match() -> None:
    assert topic_matches("world/scene", "world/scene")
    assert not topic_matches("world/scene", "world/state")


def test_topic_plus_matches_one_level() -> None:
    assert topic_matches("soul/+/response", "soul/elena/response")
    assert not topic_matches("soul/+/response", "soul/elena/extra/response")
    assert not topic_matches("soul/+/response", "soul/response")


def test_topic_hash_matches_remaining_levels() -> None:
    assert topic_matches("engine/#", "engine/event")
    assert topic_matches("engine/#", "engine/turn/started")
    assert not topic_matches("engine/#", "world/state")


def test_topic_length_must_match_without_hash() -> None:
    assert not topic_matches("a/b", "a/b/c")
    assert not topic_matches("a/b/c", "a/b")


# ---- publish / subscribe -------------------------------------------------
def test_publish_dispatches_to_matching_subscribers() -> None:
    bus = InProcessBus()
    got: list[str] = []
    bus.subscribe("soul/+/response", lambda m: got.append(m.payload["sid"]))
    bus.subscribe("world/scene", lambda m: got.append("scene"))

    bus.publish("soul/elena/response", {"sid": "elena"})
    bus.publish("world/scene", {})
    bus.publish("soul/rowan/response", {"sid": "rowan"})

    assert got == ["elena", "scene", "rowan"]


def test_publish_assigns_monotonic_seq() -> None:
    bus = InProcessBus()
    a = bus.publish("t", {})
    b = bus.publish("t", {})
    c = bus.publish("t", {})
    assert (a.seq, b.seq, c.seq) == (1, 2, 3)
    assert bus.seq == 3


def test_unsubscribe_stops_delivery() -> None:
    bus = InProcessBus()
    hits: list[int] = []
    unsub = bus.subscribe("t", lambda m: hits.append(m.seq))
    bus.publish("t", {})
    unsub()
    bus.publish("t", {})
    assert hits == [1]


def test_faulty_subscriber_is_isolated() -> None:
    bus = InProcessBus()
    delivered: list[str] = []
    bus.subscribe("t", lambda m: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("t", lambda m: delivered.append("ok"))
    bus.publish("t", {})  # must not raise
    assert delivered == ["ok"]  # the good subscriber still got it


def test_recording_captures_publish_order() -> None:
    bus = InProcessBus()
    bus.start_recording()
    bus.publish("a", {"n": 1})
    bus.publish("b", {"n": 2})
    log = bus.drain_log()
    assert [(m.topic, m.payload["n"]) for m in log] == [("a", 1), ("b", 2)]
    assert bus.drain_log() == []  # drain clears


def test_message_to_dict_is_json_shaped() -> None:
    bus = InProcessBus()
    msg = bus.publish("soul/elena/request", {"scene": "north-gate"})
    d = msg.to_dict()
    assert d["topic"] == "soul/elena/request"
    assert d["payload"] == {"scene": "north-gate"}
    assert d["seq"] == 1 and d["protocol_version"] == 1 and "ts" in d
