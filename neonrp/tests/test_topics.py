"""M18 Phase 2 — topic vocabulary."""

from __future__ import annotations

from neonrp.core import topics
from neonrp.core.message_bus import topic_matches


def test_per_entity_topic_builders() -> None:
    # A soul is addressed by its globally-unique instance_id alone.
    assert topics.soul_request("si-elena0001") == "soul/si-elena0001/request"
    assert topics.soul_response("si-elena0001") == "soul/si-elena0001/response"
    assert topics.player_cmd("nick") == "player/nick/cmd"
    assert topics.player_output("nick") == "player/nick/output"


def test_wildcard_patterns_match_built_topics() -> None:
    # The world-agent subscribes to all soul responses; a built response
    # topic must match the wildcard pattern.
    assert topic_matches(topics.ALL_SOUL_RESPONSES, topics.soul_response("si-e"))
    assert topic_matches(topics.ALL_SOUL_REQUESTS, topics.soul_request("si-r"))
    assert topic_matches(topics.ALL_PLAYER_CMDS, topics.player_cmd("nick"))
    assert topic_matches(topics.ALL_ENGINE, topics.ENGINE_EVENT)
    assert topic_matches(topics.ALL_ENGINE, "engine/turn/started")


def test_static_topics_are_distinct() -> None:
    statics = {topics.WORLD_SCENE, topics.WORLD_NARRATION, topics.WORLD_STATE, topics.ENGINE_EVENT}
    assert len(statics) == 4


def test_response_pattern_does_not_match_request() -> None:
    assert not topic_matches(topics.ALL_SOUL_RESPONSES, topics.soul_request("si-e"))
