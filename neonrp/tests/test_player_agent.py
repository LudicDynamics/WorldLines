"""M20 Phase C — player-agent wrapper archetype."""

from __future__ import annotations

from pathlib import Path

from neonrp.core.player_agent import (
    PlayerAgent,
    PlayerOutputDirective,
    PlayerView,
    player_agents_for,
)
from neonrp.core.player_controller import PlayerTurnIntent


class _P:
    def __init__(self, pid: str, state_path: str) -> None:
        self.pid = pid
        self.state_path = state_path


class _PT:
    def __init__(self, players: list[_P]) -> None:
        self.players = players


def test_n1_default_player_agent_when_no_players(tmp_path: Path) -> None:
    # M20: single-player still gets a DISTINCT player-agent (never inlined).
    agents = player_agents_for(tmp_path, None)
    assert len(agents) == 1
    assert agents[0].pid == "player"
    assert agents[0].state_path == "game/player"


def test_player_agents_one_per_players_entry(tmp_path: Path) -> None:
    pt = _PT([_P("nick", "game/players/nick"), _P("alice", "game/players/alice")])
    agents = player_agents_for(tmp_path, pt)
    assert [(a.pid, a.state_path) for a in agents] == [
        ("nick", "game/players/nick"),
        ("alice", "game/players/alice"),
    ]


def test_intake_wraps_player_controller(tmp_path: Path) -> None:
    pa = PlayerAgent(root=tmp_path, pid="player", state_path="game/player")
    intent = pa.intake("开始游戏")
    assert isinstance(intent, PlayerTurnIntent)
    # "开始游戏" must NOT authorize an avatar action (control-plane preserved).
    assert intent.kind == "start_or_continue"
    assert intent.avatar_action_authorized is False


def test_render_v1_passthrough_and_owns_private_journal(tmp_path: Path) -> None:
    (tmp_path / "game" / "player").mkdir(parents=True)
    pa = PlayerAgent(root=tmp_path, pid="player", state_path="game/player")

    view = pa.render("雾压在北门上。你站在岗亭旁。")

    # v1 pass-through: narration unchanged (no N=1 regression), not yet
    # perspective-rendered (C3 seam).
    assert isinstance(view, PlayerView)
    assert view.narration == "雾压在北门上。你站在岗亭旁。"
    assert view.perspective_rendered is False
    # player-agent owns its private state (deterministic journal write).
    journal = (tmp_path / "game" / "player" / "journal.md").read_text(encoding="utf-8")
    assert "雾压在北门上" in journal


def test_two_players_render_isolated_private_state(tmp_path: Path) -> None:
    for pid in ("nick", "alice"):
        (tmp_path / "game" / "players" / pid).mkdir(parents=True)
    nick = PlayerAgent(root=tmp_path, pid="nick", state_path="game/players/nick")
    alice = PlayerAgent(root=tmp_path, pid="alice", state_path="game/players/alice")

    nick.render("Nick sees the river.")
    alice.render("Alice sees the gate.")

    nick_j = (tmp_path / "game" / "players" / "nick" / "journal.md").read_text(encoding="utf-8")
    alice_j = (tmp_path / "game" / "players" / "alice" / "journal.md").read_text(encoding="utf-8")
    # Each player-agent wrote ONLY its own journal (fog-of-war / privacy).
    assert "Nick sees the river" in nick_j and "Alice" not in nick_j
    assert "Alice sees the gate" in alice_j and "Nick" not in alice_j


def test_render_journal_failure_never_raises(tmp_path: Path) -> None:
    # state_path points nowhere writable-as-dir-parent collision; render must
    # still return a view (a private-state write must not lose narration).
    bad = tmp_path / "game" / "player"
    bad.parent.mkdir(parents=True)
    bad.write_text("not a dir", encoding="utf-8")  # journal.md parent is a file
    pa = PlayerAgent(root=tmp_path, pid="player", state_path="game/player")
    view = pa.render("still narrates")
    assert view.narration == "still narrates"


# --- M18 §2.2/§6 output directives (player-agent as a bus producer node) ---


def test_to_directives_empty_output_is_no_directives(tmp_path: Path) -> None:
    pa = PlayerAgent(root=tmp_path, pid="player", state_path="game/player")
    assert pa.to_directives("") == []
    assert pa.to_directives("   ") == []


def test_to_directives_text_is_typewriter_paced(tmp_path: Path) -> None:
    pa = PlayerAgent(root=tmp_path, pid="player", state_path="game/player")
    directives = pa.to_directives("雾还没散。")
    assert len(directives) == 1
    d = directives[0]
    assert d.kind == "text"
    assert d.text == "雾还没散。"
    assert d.pace == "typewriter"


def test_directive_to_dict_is_json_shaped() -> None:
    text = PlayerOutputDirective(kind="text", text="hi", pace="instant").to_dict()
    assert text == {"kind": "text", "text": "hi", "pace": "instant"}

    ask = PlayerOutputDirective(
        kind="ask_user", text="去哪?", options=("北门", "公会")
    ).to_dict()
    assert ask == {"kind": "ask_user", "text": "去哪?", "options": ["北门", "公会"]}
    # non-text kinds don't leak the text-only `pace` field
    assert "pace" not in ask


def test_to_directives_extracts_trailing_choices(tmp_path: Path) -> None:
    pa = PlayerAgent(root=tmp_path, pid="player", state_path="game/player")
    narration = (
        "雾散了些。她在等你。\n\n你可以：\n\n"
        "- **自由行动**\n"
        "- 在公会门口等到九点开门\n"
        "- 去旁边的杂货铺看看（飘来烤饼的味道）\n"
    )
    directives = pa.to_directives(narration)
    assert [d.kind for d in directives] == ["text", "choices"]
    assert directives[0].text == narration.strip()  # narration untouched
    assert directives[1].options == (
        "自由行动",
        "在公会门口等到九点开门",
        "去旁边的杂货铺看看",
    )
    assert directives[1].to_dict()["options"][0] == "自由行动"


def test_no_choices_marker_means_text_only(tmp_path: Path) -> None:
    pa = PlayerAgent(root=tmp_path, pid="player", state_path="game/player")
    directives = pa.to_directives("纯叙事，没有选项列表。")
    assert [d.kind for d in directives] == ["text"]
