"""Tests for the pure turn-commit composition (M17 §2 / M18 §3.4).

Covers: deterministic commit_id, id sensitivity to every content field,
passthrough soul handling, soul-commit schema isolation (no world fields),
soul_scene_index correctness, and cross-process byte-identical ids.
"""

from __future__ import annotations

import dataclasses
import importlib

from neonrp.core.turn_commit import (
    CharacterDelta,
    CommitParents,
    SoulCommit,
    TurnCollection,
    WorldDelta,
    compose_commit,
)


def _world(**over) -> WorldDelta:
    base = dict(
        wid="dark-train",
        instance_id="wi-9f2c",
        version_hash="b54b307b50ef",
        game_folder_hash="sha256:game0",
        session_log_hash="sha256:log0",
    )
    base.update(over)
    return WorldDelta(**base)


def _soul(**over) -> CharacterDelta:
    base = dict(
        sid="elena",
        instance_id="si-a1",
        version_hash="soul-elena-v1",
        state="completed",
        soul_folder_hash="sha256:soulA",
    )
    base.update(over)
    return CharacterDelta(**base)


def _collection(**over) -> TurnCollection:
    base = dict(turn_seq=87, world=_world(), souls=[_soul()])
    base.update(over)
    return TurnCollection(**base)


def test_commit_id_is_deterministic():
    parents = CommitParents(world="w-parent", souls={("elena", "si-a1"): "s-parent"})
    w1, s1 = compose_commit(_collection(), parents)
    w2, s2 = compose_commit(_collection(), parents)

    assert w1.world_commit_id == w2.world_commit_id
    assert [c.soul_commit_id for c in s1] == [c.soul_commit_id for c in s2]
    # 12 hex chars per M17 §2 sha256-prefix.
    assert len(w1.world_commit_id) == 12
    assert len(s1[0].soul_commit_id) == 12


def test_world_id_changes_when_any_content_field_changes():
    parents = CommitParents(world="w-parent", souls={("elena", "si-a1"): "s-parent"})
    base_id = compose_commit(_collection(), parents)[0].world_commit_id

    variants = [
        _collection(turn_seq=88),
        _collection(world=_world(game_folder_hash="sha256:game-CHANGED")),
        _collection(world=_world(session_log_hash="sha256:log-CHANGED")),
        _collection(world=_world(version_hash="other-version")),
        _collection(world=_world(instance_id="wi-other")),
        _collection(world=_world(wid="other-world")),
    ]
    for v in variants:
        assert compose_commit(v, parents)[0].world_commit_id != base_id

    # Parent change must also move the id.
    other_parent = CommitParents(world="w-DIFFERENT", souls=parents.souls)
    assert (
        compose_commit(_collection(), other_parent)[0].world_commit_id != base_id
    )


def test_soul_id_changes_when_any_content_field_changes():
    parents = CommitParents(souls={("elena", "si-a1"): "s-parent"})
    base_id = compose_commit(_collection(), parents)[1][0].soul_commit_id

    variants = [
        _collection(souls=[_soul(soul_folder_hash="sha256:soul-CHANGED")]),
        _collection(souls=[_soul(version_hash="soul-v2")]),
        _collection(souls=[_soul(instance_id="si-other")]),
        _collection(souls=[_soul(sid="conductor")]),
        _collection(turn_seq=99),
    ]
    for v in variants:
        assert compose_commit(v, parents)[1][0].soul_commit_id != base_id

    other_parent = CommitParents(souls={("elena", "si-a1"): "s-DIFFERENT"})
    assert (
        compose_commit(_collection(), other_parent)[1][0].soul_commit_id
        != base_id
    )


def test_passthrough_soul_reuses_prior_id_and_allocates_no_commit():
    # elena mutated; conductor interrupted (passthrough), passenger degraded.
    collection = _collection(
        souls=[
            _soul(sid="elena", instance_id="si-a1", state="completed"),
            _soul(sid="conductor", instance_id="si-b7", state="interrupted"),
            _soul(sid="passenger", instance_id="si-c0", state="degraded"),
        ]
    )
    parents = CommitParents(
        world="w-parent",
        souls={
            ("elena", "si-a1"): "s-elena-prior",
            ("conductor", "si-b7"): "s-cond-prior",
            ("passenger", "si-c0"): "s-pax-prior",
        },
    )
    world, souls = compose_commit(collection, parents)

    # Only the mutated soul allocates a SoulCommit.
    assert len(souls) == 1
    assert souls[0].sid == "elena"

    by_sid = {e.sid: e for e in world.soul_scene_index}
    # Passthrough souls point at their PRIOR commit id, unchanged.
    assert by_sid["conductor"].soul_commit == "s-cond-prior"
    assert by_sid["passenger"].soul_commit == "s-pax-prior"
    # Mutated soul points at the freshly derived id.
    assert by_sid["elena"].soul_commit == souls[0].soul_commit_id
    assert by_sid["elena"].soul_commit != "s-elena-prior"


def test_passthrough_with_no_prior_commit_is_skipped():
    # Interrupted on its very first turn: nothing to point at.
    collection = _collection(
        souls=[_soul(sid="ghost", instance_id="si-z9", state="interrupted")]
    )
    parents = CommitParents(world=None, souls={})
    world, souls = compose_commit(collection, parents)
    assert souls == []
    assert world.soul_scene_index == []


def test_soul_commit_schema_has_no_world_fields():
    _, souls = compose_commit(
        _collection(), CommitParents(souls={("elena", "si-a1"): None})
    )
    field_names = {f.name for f in dataclasses.fields(SoulCommit)}

    # M17 §2.2: a soul commit carries NO world identity whatsoever.
    forbidden = {
        "wid",
        "world",
        "world_commit_id",
        "world_commit",
        "world_instance_id",
        "game_folder_hash",
        "session_log_hash",
    }
    assert field_names.isdisjoint(forbidden)
    # Sanity: it has its own independent identity fields only.
    assert {"soul_commit_id", "sid", "instance_id", "folder_hash"} <= field_names


def test_soul_scene_index_references_each_souls_identity_and_commit():
    collection = _collection(
        souls=[
            _soul(sid="elena", instance_id="si-a1"),
            _soul(sid="conductor", instance_id="si-b7", soul_folder_hash="sha256:c"),
        ]
    )
    parents = CommitParents(
        souls={("elena", "si-a1"): None, ("conductor", "si-b7"): None}
    )
    world, souls = compose_commit(collection, parents)

    commit_by_fork = {(c.sid, c.instance_id): c.soul_commit_id for c in souls}
    for entry in world.soul_scene_index:
        fork = (entry.sid, entry.instance_id)
        assert entry.soul_commit == commit_by_fork[fork]

    # Stable ordering: sorted by (sid, instance_id).
    forks = [(e.sid, e.instance_id) for e in world.soul_scene_index]
    assert forks == sorted(forks)


def test_two_independent_process_runs_yield_byte_identical_ids():
    """Simulate a second process via a fresh module import."""
    import neonrp.core.turn_commit as tc1

    parents1 = tc1.CommitParents(
        world="w-p", souls={("elena", "si-a1"): "s-p"}
    )
    coll1 = tc1.TurnCollection(
        turn_seq=87,
        world=tc1.WorldDelta(
            wid="dark-train",
            instance_id="wi-9f2c",
            version_hash="b54b307b50ef",
            game_folder_hash="sha256:game0",
            session_log_hash="sha256:log0",
        ),
        souls=[
            tc1.CharacterDelta(
                sid="elena",
                instance_id="si-a1",
                version_hash="soul-elena-v1",
                state="completed",
                soul_folder_hash="sha256:soulA",
            )
        ],
    )
    w_a, s_a = tc1.compose_commit(coll1, parents1)

    # Fresh import == a distinct process's module object.
    tc2 = importlib.reload(importlib.import_module("neonrp.core.turn_commit"))
    parents2 = tc2.CommitParents(
        world="w-p", souls={("elena", "si-a1"): "s-p"}
    )
    coll2 = tc2.TurnCollection(
        turn_seq=87,
        world=tc2.WorldDelta(
            wid="dark-train",
            instance_id="wi-9f2c",
            version_hash="b54b307b50ef",
            game_folder_hash="sha256:game0",
            session_log_hash="sha256:log0",
        ),
        souls=[
            tc2.CharacterDelta(
                sid="elena",
                instance_id="si-a1",
                version_hash="soul-elena-v1",
                state="completed",
                soul_folder_hash="sha256:soulA",
            )
        ],
    )
    w_b, s_b = tc2.compose_commit(coll2, parents2)

    assert w_a.world_commit_id == w_b.world_commit_id
    assert s_a[0].soul_commit_id == s_b[0].soul_commit_id
