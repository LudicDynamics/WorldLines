"""Tests for the M17 `neonrp commit` CLI (`commands/commit.py`).

Covers: every subcommand exists; commit→log→checkout round-trips on a
tmp fixture game dir; branch creates a divergent ref; gc preserves a
tagged commit; backfill yields a single commit. All seeded on disk —
no network, no $HOME writes (`--commits-root` injected).
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.commands.commit import commit_group
from neonrp.core import commit_store
from neonrp.core.hashing import compute_file_hash


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _seed_game(base: Path, *, with_manifest: bool = True, turn: int = 0) -> Path:
    """Build a minimal game working tree under ``base``."""
    game_root = base / "dark-train-wi-test01"
    g = game_root / "game"
    (g / "meta").mkdir(parents=True)
    (g / "location").mkdir(parents=True)
    (g / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": turn, "world_id": "W001"}), encoding="utf-8"
    )
    (g / "location" / "carriage-1.json").write_text('{"id": "c1"}\n', encoding="utf-8")

    if with_manifest:
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
                    "souls": [],
                    "created_at": "2026-05-16T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
    return game_root


def _run(args: list[str]) -> "object":
    return CliRunner().invoke(commit_group, args, catch_exceptions=False)


# --------------------------------------------------------------------------- #
# Subcommand presence
# --------------------------------------------------------------------------- #

class TestSubcommandsExist:
    def test_help_lists_all(self):
        res = _run(["--help"])
        assert res.exit_code == 0
        for sub in ("log", "checkout", "branch", "gc", "verify", "backfill", "commit"):
            assert sub in res.output

    def test_each_subcommand_has_help(self):
        for sub in ("commit", "log", "checkout", "branch", "gc", "verify", "backfill"):
            res = _run([sub, "--help"])
            assert res.exit_code == 0, f"{sub} --help failed: {res.output}"


# --------------------------------------------------------------------------- #
# commit → log → checkout round-trip
# --------------------------------------------------------------------------- #

class TestRoundTrip:
    def test_commit_log_checkout(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src")
        cr = tmp_path / "commits"

        res = _run(
            ["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "1"]
        )
        assert res.exit_code == 0, res.output
        assert "✓ Committed" in res.output

        # HEAD written into the working tree.
        head = (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()
        assert head

        # log walks the DAG from HEAD.
        res = _run(["log", "--game-root", str(game_root), "--commits-root", str(cr)])
        assert res.exit_code == 0, res.output
        assert head in res.output
        assert "turn 1" in res.output

        # checkout restores the game/ subtree byte-identically elsewhere.
        dest = tmp_path / "restored"
        res = _run(["checkout", head, "--commits-root", str(cr), "--into", str(dest)])
        assert res.exit_code == 0, res.output
        restored = dest / "game" / "location" / "carriage-1.json"
        assert restored.exists()
        assert restored.read_text(encoding="utf-8") == '{"id": "c1"}\n'

    def test_commit_advances_manifest_head(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src")
        cr = tmp_path / "commits"
        _run(["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "1"])
        pt = json.loads((game_root / ".neonrp" / "playthrough.json").read_text(encoding="utf-8"))
        assert pt["world"]["head_commit"]

    def test_world_commit_records_partial_determinism_without_fake_llm_calls(
        self, tmp_path: Path
    ):
        game_root = _seed_game(tmp_path / "src")
        cr = tmp_path / "commits"
        _run(["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "1"])
        head = (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()

        obj = commit_store.read_world_commit(cr, head)

        determinism = obj["determinism"]
        assert determinism["schema_version"] == 1
        assert determinism["status"] == "partial"
        assert determinism["replay_status"] == "not_implemented"
        assert determinism["llm_calls_status"] == "not_recorded"
        assert "llm_calls" not in determinism
        assert "world_agent_snapshot" not in obj

    def test_world_commit_determinism_records_session_log_source(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src")
        session_log = game_root / ".neonrp" / "sessions" / "main.jsonl"
        session_log.parent.mkdir(parents=True)
        session_log.write_text('{"role":"user","content":"look"}\n', encoding="utf-8")
        cr = tmp_path / "commits"

        _run(["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "1"])
        head = (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()
        obj = commit_store.read_world_commit(cr, head)

        source = obj["determinism"]["sources"]["session_log"]
        assert source == {
            "path": ".neonrp/sessions/main.jsonl",
            "hash": "sha256:" + compute_file_hash(session_log),
            "present": True,
        }


# --------------------------------------------------------------------------- #
# branch — divergent ref
# --------------------------------------------------------------------------- #

class TestBranch:
    def test_branch_creates_divergent_ref(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src")
        cr = tmp_path / "commits"
        _run(["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "1"])

        res = _run(
            ["branch", "alt-elena", "--game-root", str(game_root), "--commits-root", str(cr)]
        )
        assert res.exit_code == 0, res.output
        assert "alt-elena" in commit_store.list_branches(cr, "dark-train")

        # Branch ref points at the fork commit (HEAD at branch time).
        head = (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()
        assert commit_store.read_ref(cr, "dark-train", "alt-elena") == head

    def test_branch_without_head_fails_cleanly(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src")
        cr = tmp_path / "commits"
        res = CliRunner().invoke(
            commit_group,
            ["branch", "x", "--game-root", str(game_root), "--commits-root", str(cr)],
        )
        assert res.exit_code != 0
        assert "no HEAD" in res.output


# --------------------------------------------------------------------------- #
# gc — preserves tagged
# --------------------------------------------------------------------------- #

class TestGc:
    def test_gc_preserves_tagged(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src")
        cr = tmp_path / "commits"
        _run(["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "1"])
        head = (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()

        # Tag it, then delete the branch ref so the only thing keeping the
        # commit reachable is the tag.
        tags = cr / "refs" / "tags"
        tags.mkdir(parents=True, exist_ok=True)
        (tags / "checkpoint").write_text(head + "\n", encoding="utf-8")
        # The "main" branch is a named branch ref (commit_store._ref_path
        # only treats the literal name "HEAD" as the bare tip file).
        (cr / "refs" / "dark-train" / "branches" / "main").unlink()

        res = _run(["gc", "--commits-root", str(cr), "--keep-tagged"])
        assert res.exit_code == 0, res.output
        # Commit object survives because the tag pins it.
        assert commit_store.read_world_commit(cr, head)["world_commit_id"] == head

    def test_gc_runs_on_empty_store(self, tmp_path: Path):
        res = _run(["gc", "--commits-root", str(tmp_path / "empty")])
        assert res.exit_code == 0
        assert "GC complete" in res.output


# --------------------------------------------------------------------------- #
# verify — match on a freshly-landed commit
# --------------------------------------------------------------------------- #

class TestVerify:
    def test_verify_matches_fresh_commit(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src")
        cr = tmp_path / "commits"
        _run(["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "1"])
        head = (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()

        res = _run([
            "verify", head, "--commits-root", str(cr), "--scratch", str(tmp_path / "scratch")
        ])
        assert res.exit_code == 0, res.output
        assert "MATCH" in res.output
        assert "determinism: RECORDED_UNVERIFIED" in res.output
        assert "replay check is not implemented yet" in res.output


# --------------------------------------------------------------------------- #
# backfill — single commit for a legacy dir
# --------------------------------------------------------------------------- #

class TestBackfill:
    def test_backfill_yields_single_commit(self, tmp_path: Path):
        # Legacy dir: no manifest, no HEAD, just run_state with turn_count.
        game_root = _seed_game(tmp_path / "src", with_manifest=False, turn=42)
        cr = tmp_path / "commits"

        res = _run(["backfill", "--game-root", str(game_root), "--commits-root", str(cr)])
        assert res.exit_code == 0, res.output
        assert "turn:    42" in res.output

        head = (game_root / ".neonrp" / "HEAD").read_text(encoding="utf-8").strip()
        log_res = _run(["log", "--game-root", str(game_root), "--commits-root", str(cr)])
        assert log_res.output.count("turn ") == 1  # exactly one commit, parent=null
        obj = commit_store.read_world_commit(cr, head)
        assert obj["parent"] is None
        assert obj["turn_seq"] == 42
        assert obj["branch"] == "main"

    def test_backfill_skips_without_run_state(self, tmp_path: Path):
        game_root = tmp_path / "src" / "dark-train-wi-x"
        (game_root / "game" / "meta").mkdir(parents=True)
        cr = tmp_path / "commits"
        res = CliRunner().invoke(
            commit_group,
            ["backfill", "--game-root", str(game_root), "--commits-root", str(cr)],
        )
        assert res.exit_code != 0
        assert "skipping" in res.output or "run_state" in res.output

    def test_backfill_refuses_if_graph_exists(self, tmp_path: Path):
        game_root = _seed_game(tmp_path / "src", turn=5)
        cr = tmp_path / "commits"
        _run(["commit", "--game-root", str(game_root), "--commits-root", str(cr), "--turn", "5"])
        res = CliRunner().invoke(
            commit_group,
            ["backfill", "--game-root", str(game_root), "--commits-root", str(cr)],
        )
        assert res.exit_code != 0
        assert "already has a commit graph" in res.output
