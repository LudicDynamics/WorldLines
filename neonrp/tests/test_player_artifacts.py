"""V0 player-facing artifacts (DESIGN-VISIONRP §2 file contract)."""

import json
from pathlib import Path

from neonrp.core.player_artifacts import (
    append_turn_artifacts,
    drain_inbox,
    ensure_inbox,
)


def _seed_run(root: Path) -> None:
    meta = root / "game" / "meta"
    meta.mkdir(parents=True)
    (meta / "run_state.json").write_text(
        json.dumps(
            {
                "turn_count": 3,
                "location": {"node": "north-gate", "display": "石津镇·北门"},
                "time": {"day": 1, "clock": "08:35"},
                "party": {
                    "souls": {
                        "elena": {"available_for_interaction": True},
                        "bram": {"available_for_interaction": False},
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    neonrp = root / ".neonrp"
    neonrp.mkdir()
    (neonrp / "manifest.json").write_text(
        json.dumps(
            {
                "version": "0.3",
                "current_branch": "main",
                "branches": {
                    "main": {"head_event": 5, "max_event": 7, "kind": "main"},
                    "what-if": {
                        "head_event": 6,
                        "kind": "sandbox",
                        "parent": "main",
                        "fork_event": 4,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _emit(root: Path, turn_seq: int, narration: str = "她抬头看你。") -> None:
    append_turn_artifacts(
        root,
        "main",
        turn_seq=turn_seq,
        player_input="向守卫打听告示板",
        narration=narration,
        speaker="world-agent",
    )


def test_turn_artifacts_written(tmp_path: Path) -> None:
    _seed_run(tmp_path)
    _emit(tmp_path, 3)

    story = (tmp_path / "story.md").read_text(encoding="utf-8")
    assert "## T3 · 石津镇·北门 · Day1 08:35" in story
    assert "> 向守卫打听告示板" in story
    assert "**world-agent**：她抬头看你。" in story

    feed_lines = (tmp_path / "feed.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(feed_lines[-1])
    assert entry["turn_seq"] == 3
    assert entry["location"] == "石津镇·北门"
    assert entry["waiting"] == ["elena"]

    feed_md = (tmp_path / "feed.md").read_text(encoding="utf-8")
    assert "# 今日动态" in feed_md
    assert "**正在等你回应：** elena" in feed_md

    tree = json.loads((tmp_path / "tree.json").read_text(encoding="utf-8"))
    assert tree["current_branch"] == "main"
    assert tree["head"] == {"branch": "main", "turn_seq": 3}
    names = {b["name"] for b in tree["branches"]}
    assert names == {"main", "what-if"}

    assert (tmp_path / "inbox" / "pending").is_dir()
    assert (tmp_path / "inbox" / "README.md").exists()


def test_story_and_feed_accumulate(tmp_path: Path) -> None:
    _seed_run(tmp_path)
    _emit(tmp_path, 3, narration="第一段。")
    _emit(tmp_path, 4, narration="第二段。")

    story = (tmp_path / "story.md").read_text(encoding="utf-8")
    assert story.index("## T3") < story.index("## T4")
    # story.md header written exactly once
    assert story.count("# 世界线实录") == 1

    feed_md = (tmp_path / "feed.md").read_text(encoding="utf-8")
    # newest first in the digest
    assert feed_md.index("T4") < feed_md.index("T3 ·")


def test_artifacts_survive_missing_state(tmp_path: Path) -> None:
    # No game/, no manifest — must not raise, story still appends.
    append_turn_artifacts(
        tmp_path, "main", turn_seq=1, player_input="hi", narration="ok", speaker="wa"
    )
    assert "## T1" in (tmp_path / "story.md").read_text(encoding="utf-8")
    assert not (tmp_path / "tree.json").exists()


def test_inbox_drain_consumes_pending(tmp_path: Path) -> None:
    ensure_inbox(tmp_path)
    pending = tmp_path / "inbox" / "pending"
    (pending / "01-night.md").write_text("让 elena 今晚来找玩家", encoding="utf-8")
    (pending / "02-rain.txt").write_text("入夜后下雨", encoding="utf-8")
    (pending / "ignore.json").write_text("{}", encoding="utf-8")

    notes = drain_inbox(tmp_path)
    assert notes == ["让 elena 今晚来找玩家", "入夜后下雨"]
    # consumed + pending cleared (non-md/txt left untouched)
    assert sorted(p.name for p in pending.iterdir()) == ["ignore.json"]
    consumed = list((tmp_path / "inbox" / "consumed").iterdir())
    assert len(consumed) == 2

    # second drain is a no-op
    assert drain_inbox(tmp_path) == []


def test_inbox_drain_without_inbox_dir(tmp_path: Path) -> None:
    assert drain_inbox(tmp_path) == []
