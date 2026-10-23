"""Tests for `commit_subsystem.rollback_to_commit` (rollback-via-branch).

A rollback forks a PAST turn's commit onto a fresh divergent branch:
- the source branch (ref + session log) is left byte-untouched;
- the working game/ tree is restored to the target turn;
- each soul is re-minted with a fresh instance_id AND a MATERIALISED folder
  (the piece plain branch_from_head omits) carrying the target turn's state;
- playthrough + HEAD point at the fork.

All seeded on disk; `--commits-root` injected, no $HOME writes.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.commands.commit import commit_group
from neonrp.core import commit_store
from neonrp.core.commit_subsystem import rollback_to_commit


def _seed_game_with_soul(base: Path) -> Path:
    game_root = base / "dark-train-wi-test01"
    g = game_root / "game" / "meta"
    g.mkdir(parents=True)
    (g / "run_state.json").write_text(
        json.dumps({"turn_count": 0, "world_id": "W001"}), encoding="utf-8"
    )
    soul = game_root / "souls" / "elena-si-a1"
    soul.mkdir(parents=True)
    (soul / "persona.json").write_text('{"name": "Elena"}\n', encoding="utf-8")

    nd = game_root / ".neonrp"
    nd.mkdir(parents=True, exist_ok=True)
    (nd / "playthrough.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "playthrough_id": "pt-test",
                "world": {
                    "wid": "dark-train",
                    "instance_id": "wi-test01",
                    "version_hash": "v-abc",
                    "head_commit": "",
                },
                "world_agent_team": {
                    "seeded_from": "game/agents/manifest.json@v-abc",
                    "agents": [
                        {"id": "world-agent", "role": "orchestrator", "singleton": True}
                    ],
                },
                "souls": [
                    {
                        "sid": "elena",
                        "instance_id": "si-a1",
                        "version_hash": "soul-elena-v1",
                        "head_commit": "",
                        "role": "npc",
                    }
                ],
                "active_souls": ["si-a1"],
                "created_at": "2026-05-16T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return game_root


def _commit(game_root: Path, cr: Path, turn: int) -> str:
    res = CliRunner().invoke(
        commit_group,
        ["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", str(turn)],
        catch_exceptions=False,
    )
    assert res.exit_code == 0, res.output
    return (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()


def test_rollback_forks_playable_branch_leaving_source_untouched(tmp_path: Path):
    game_root = _seed_game_with_soul(tmp_path / "src")
    cr = tmp_path / "commits"

    # Turn 1 — the state we will roll back TO.
    (game_root / "game" / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": 1, "world_id": "W001"}), encoding="utf-8"
    )
    head1 = _commit(game_root, cr, 1)

    # Turn 2 — advance world + soul state, then commit.
    (game_root / "game" / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": 2, "world_id": "W001"}), encoding="utf-8"
    )
    (game_root / "souls" / "elena-si-a1" / "persona.json").write_text(
        '{"name": "Elena-CHANGED"}\n', encoding="utf-8"
    )
    head2 = _commit(game_root, cr, 2)
    assert head1 != head2

    # Roll back to turn 1 on a fresh branch.
    out = rollback_to_commit(game_root, cr, head1, "rb-t1")
    assert out["branch"] == "rb-t1"
    assert out["commit_id"] == head1

    # New branch ref points at turn 1; the source line is UNTOUCHED.
    assert commit_store.read_ref(cr, "dark-train", "rb-t1") == head1
    assert commit_store.read_ref(cr, "dark-train", "main") == head2

    # Working game/ restored to turn 1.
    rs = json.loads((game_root / "game" / "meta" / "run_state.json").read_text(encoding="utf-8"))
    assert rs["turn_count"] == 1

    # HEAD moved to the fork commit.
    assert (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip() == head1

    # Playthrough forked: new soul instance_id, head_commit at the fork.
    pt = json.loads((game_root / ".neonrp" / "playthrough.json").read_text(encoding="utf-8"))
    assert pt["world"]["head_commit"] == head1
    new_iid = pt["souls"][0]["instance_id"]
    assert new_iid != "si-a1"

    # THE KEY FIX: the new soul folder is MATERIALISED with turn-1 state
    # (branch_from_head alone would leave it missing).
    new_persona = game_root / "souls" / f"elena-{new_iid}" / "persona.json"
    assert new_persona.exists(), "forked soul folder was not materialised"
    assert json.loads(new_persona.read_text(encoding="utf-8"))["name"] == "Elena"

    # The old soul folder still holds the turn-2 (source) state.
    old_persona = json.loads(
        (game_root / "souls" / "elena-si-a1" / "persona.json").read_text(encoding="utf-8")
    )
    assert old_persona["name"] == "Elena-CHANGED"


def test_webruntime_rollback_switches_branch_and_carries_history(tmp_path: Path):
    from neonrp.commands.web import WebRuntime
    from neonrp.core.manifest import Manifest

    game_root = _seed_game_with_soul(tmp_path / "src")
    cr = game_root / ".neonrp" / "commits"  # WebRuntime looks under root/.neonrp/commits

    # Seed a manifest (current_branch=main) — WebRuntime reads/writes it.
    (game_root / ".neonrp" / "manifest.json").write_text(
        Manifest().model_dump_json(), encoding="utf-8"
    )

    head1 = _commit(game_root, cr, 1)
    (game_root / "game" / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": 2, "world_id": "W001"}), encoding="utf-8"
    )
    _commit(game_root, cr, 2)

    # Seed an orchestration log for the source branch: turns 1 and 2.
    orch = game_root / ".neonrp" / "orchestration"
    orch.mkdir(parents=True, exist_ok=True)
    (orch / "main.jsonl").write_text(
        json.dumps({"turn_seq": 1, "land": {"commit_id": head1}}) + "\n"
        + json.dumps({"turn_seq": 2, "land": {"commit_id": "x"}}) + "\n",
        encoding="utf-8",
    )

    rt = WebRuntime(game_root, "world-agent")
    out = rt.rollback(head1)
    assert out["ok"] is True, out
    new_branch = out["branch"]

    # Manifest switched to a sandbox branch parented on main.
    m = Manifest(**json.loads((game_root / ".neonrp" / "manifest.json").read_text(encoding="utf-8")))
    assert m.current_branch == new_branch
    assert m.branches[new_branch].kind == "sandbox"
    assert m.branches[new_branch].parent == "main"

    # The new branch's orchestration history carries turn 1 only (not turn 2).
    new_orch = (orch / f"{new_branch}.jsonl").read_text(encoding="utf-8").splitlines()
    seqs = [json.loads(line)["turn_seq"] for line in new_orch if line.strip()]
    assert seqs == [1]

    # Cached session dropped so the next turn runs on the new branch.
    assert rt._session is None


def test_rollback_rejects_duplicate_branch(tmp_path: Path):
    game_root = _seed_game_with_soul(tmp_path / "src")
    cr = tmp_path / "commits"
    head1 = _commit(game_root, cr, 1)
    rollback_to_commit(game_root, cr, head1, "rb")
    # Second rollback onto the same branch name must not clobber it.
    import pytest

    from neonrp.core.commit_subsystem import CommitSubsystemError

    with pytest.raises(CommitSubsystemError):
        rollback_to_commit(game_root, cr, head1, "rb")
