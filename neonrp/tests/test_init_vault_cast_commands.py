"""`/init` `/vault` and the bare `/cast` overview.

"跑到尽头,我发现找不到 cast 一览,以及在 /command 里面可以 init 一个新的
游戏,在 .worldlines 里面就好" — three gaps at the end of the M31 path:

- `/init <名字> [设定]` builds a fresh owned world under `~/.worldlines/worlds/`
  and hands its workshop to the build agent with the premise as first words.
- `/vault` is the one-click into Obsidian (projection → registration → open).
- bare `/cast` first answers *who is already here*, from the world's own
  `souls/`, before listing who could be cast — a freshly `/create`d soul is
  not in the library, and listing only the library made it vanish.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neonrp.tui.app import CLI_FORWARD_COMMANDS, LOCAL_SLASH_COMMANDS, NeonRPApp
from neonrp.tui.commands import COMMANDS, get_command_suggestions, parse_command, validate_command


class _View:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        self.lines.append(text)

    @property
    def text(self) -> str:
        return "".join(self.lines)


@pytest.fixture
def app_view(tmp_path, monkeypatch):
    app = NeonRPApp.__new__(NeonRPApp)
    app.root = tmp_path / "current"
    app.root.mkdir()
    app.reopen_request = None
    app.ui_locale = "zh"
    view = _View()
    app.push_screen = MagicMock()
    monkeypatch.setattr(NeonRPApp, "query_one", lambda self, *a, **k: view)
    monkeypatch.setattr(NeonRPApp, "exit", lambda self, *a, **k: None)
    return app, view


@pytest.fixture
def homes(tmp_path, monkeypatch):
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "home" / "worlds")
    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "home" / "plays")
    return tmp_path / "home"


# ── /init ─────────────────────────────────────────────────────────────


def test_init_creates_an_owned_world_and_enters_its_workshop(app_view, homes):
    app, view = app_view
    app._cmd_init(["猫岛", "一座只有猫和一个灯塔守的海岛,雾里有船来。"])

    src = homes / "worlds" / "猫岛"
    assert src.is_dir(), "世界源落在 ~/.worldlines/worlds/<名字>"
    assert not (homes / "plays").exists(), "建世界不是开新局"

    req = app.reopen_request
    assert req is not None
    assert req.root == src
    assert req.mode == "build"
    assert req.continue_session is False
    assert req.startup_commands and "猫岛" in req.startup_commands[0]
    assert "灯塔" in req.startup_commands[0], "设定要原样递给 build agent"
    assert not req.startup_commands[0].startswith("/"), "第一句话是给 agent 的,不是斜杠命令"
    assert "已建在" in view.text


def test_init_names_the_world_inside_its_files(app_view, homes):
    """名字不只在目录名上:开局与地图都要叫这个名字,不然进去还是「白板」。"""
    from neonrp.core.paths import get_game_dir

    app, view = app_view
    app._cmd_init(["猫岛", "雾里有船来"])
    game = get_game_dir(homes / "worlds" / "猫岛")
    start = json.loads((game / "meta" / "game-start.json").read_text(encoding="utf-8"))
    assert start["name"] == "猫岛"
    assert start["world_info"]["world_name"] == "猫岛"
    assert start["world_info"]["premise"] == "雾里有船来"
    world_map = json.loads((game / "world" / "world_map.json").read_text(encoding="utf-8"))
    assert world_map["name"] == "猫岛"


def test_init_is_playable_from_the_start(app_view, homes):
    """白板不是空目录:结构完整、立刻能开局 —— agent 从一个能跑的世界改起。"""
    app, view = app_view
    app._cmd_init(["猫岛"])
    src = homes / "worlds" / "猫岛"
    assert (src / ".neonrp").is_dir()
    assert (src / "souls").is_dir()
    assert any(src.rglob("game-start.json"))


def test_blank_world_same_name_twice_makes_two_worlds(app_view, homes):
    """从零建两次同名 → 猫岛、猫岛-2。(`/init 猫岛` 第二次会命中已有的猫岛
    → 开它的新局,这是 09-11 定的 init 语义,所以这里直接走从零那条。)"""
    app, view = app_view
    app._init_blank_world("猫岛")
    first = app.reopen_request.root
    app.reopen_request = None
    app._init_blank_world("猫岛")
    second = app.reopen_request.root
    assert first != second
    assert second.name == "猫岛-2"
    assert first.is_dir() and second.is_dir()


def test_init_with_an_existing_own_world_starts_its_new_run(app_view, homes):
    app, view = app_view
    app._init_blank_world("猫岛")
    app.reopen_request = None
    app._cmd_open = MagicMock()
    app._cmd_init(["猫岛"])
    app._cmd_open.assert_called_once_with(["猫岛"], {"new": "true"})


def test_bare_init_offers_worlds_then_from_scratch(app_view, homes):
    """「init 应该是读取一个新的世界,load 才是读取存档」——
    裸 /init 是选单:开新局(世界库)/ 从零。"""
    app, view = app_view
    with patch("neonrp.worlds.list_worlds", return_value=[{"id": "stone-ford", "display_name": "石津镇", "desc": ""}]):
        app._cmd_init([])
    screen, cb = app.push_screen.call_args.args[:2]
    values = [v for _, v in screen._options]
    assert "world::stone-ford" in values and "blank" in values
    app._cmd_open = MagicMock()
    cb("world::stone-ford")
    app._cmd_open.assert_called_once_with(["stone-ford"], {"new": "true"})


def test_init_with_a_world_starts_a_new_run_in_play(app_view, homes):
    app, view = app_view
    app._cmd_open = MagicMock()
    with patch("neonrp.worlds.list_worlds", return_value=[{"id": "stone-ford", "display_name": "石津镇", "desc": ""}]):
        app._cmd_init(["石津镇"])
    app._cmd_open.assert_called_once_with(["stone-ford"], {"new": "true"})
    assert not (homes / "worlds").exists(), "没有建空白世界"


def test_guided_init_asks_two_questions_then_builds_blank(app_view, homes):
    """选单里的「从零」:两问 名字 → 一句话设定。"""
    app, view = app_view
    app._guide_init()
    assert app.reopen_request is None
    assert not (homes / "worlds").exists()

    app.push_screen.assert_called_once()
    name_screen, got_name = app.push_screen.call_args.args[:2]
    assert "名字" in name_screen._title

    got_name("猫岛")
    assert app.push_screen.call_count == 2
    premise_screen, got_premise = app.push_screen.call_args.args[:2]
    assert "设定" in premise_screen._title

    got_premise("雾里有船来")
    req = app.reopen_request
    assert req is not None and req.root == homes / "worlds" / "猫岛"
    assert "雾里有船来" in req.startup_commands[0]


def test_init_guide_can_skip_the_premise(app_view, homes):
    app, view = app_view
    app._guide_init()
    got_name = app.push_screen.call_args.args[1]
    got_name("猫岛")
    got_premise = app.push_screen.call_args.args[1]
    got_premise(None)  # Esc
    assert app.reopen_request is not None and app.reopen_request.root == homes / "worlds" / "猫岛"


def test_init_guide_cancel_on_name_builds_nothing(app_view, homes):
    app, view = app_view
    app._guide_init()
    got_name = app.push_screen.call_args.args[1]
    got_name(None)
    assert app.reopen_request is None
    assert not (homes / "worlds").exists()


def test_init_failure_is_reported_not_raised(app_view, homes):
    app, view = app_view
    with patch("neonrp.worlds.create_blank_world", side_effect=RuntimeError("no template")):
        app._cmd_init(["猫岛"])
    assert app.reopen_request is None
    assert "no template" in view.text


def test_init_world_can_then_be_opened_as_a_new_run(app_view, homes):
    """建完 → /open <名字> 开新局:两条命令要接得上。"""
    app, view = app_view
    app._cmd_init(["猫岛"])  # 不是世界 → 从零建
    app.reopen_request = None
    with patch("neonrp.worlds.list_saved_games", return_value=[]):
        app._cmd_open(["猫岛"])
    req = app.reopen_request
    assert req is not None and req.mode == "play"
    assert req.root.parent == homes / "plays" and req.root.name.startswith("猫岛-")


# ── /vault ────────────────────────────────────────────────────────────


def _minimal_world(root: Path) -> None:
    (root / "game" / "meta").mkdir(parents=True, exist_ok=True)
    (root / "game" / "meta" / "run_state.json").write_text("{}")


def test_vault_projects_then_opens(app_view, monkeypatch):
    app, view = app_view
    _minimal_world(app.root)
    calls: list[Path] = []

    class _Report:
        def lines(self):
            return ["已打开。"]

    monkeypatch.setattr("neonrp.core.obsidian.open_vault", lambda d, **k: calls.append(d) or _Report())
    app._cmd_vault([])
    assert (app.root / "vault" / "世界.md").exists()
    assert calls == [app.root / "vault"]
    assert "已打开" in view.text


def test_vault_build_only_projects(app_view, monkeypatch):
    app, view = app_view
    _minimal_world(app.root)
    monkeypatch.setattr(
        "neonrp.core.obsidian.open_vault", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not open"))
    )
    app._cmd_vault(["build"])
    assert (app.root / "vault" / "世界.md").exists()
    assert "vault" in view.text


def test_vault_open_failure_does_not_crash(app_view, monkeypatch):
    app, view = app_view
    _minimal_world(app.root)
    monkeypatch.setattr("neonrp.core.obsidian.open_vault", lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))
    app._cmd_vault([])
    assert "nope" in view.text


# ── bare /cast ────────────────────────────────────────────────────────


def _soul(root: Path, sid: str, name: str, location: str = "") -> None:
    d = root / "souls" / f"{sid}-si-{sid}0001"
    d.mkdir(parents=True)
    (d / "soul.json").write_text(json.dumps({"sid": sid, "name": name}), encoding="utf-8")
    (d / "run_state.json").write_text(json.dumps({"sid": sid, "location": location}), encoding="utf-8")


def test_bare_cast_lists_who_is_here_first(app_view):
    """`/create` 造出来的角色不在角色库里 —— 只对库列表会让它整个消失。"""
    app, view = app_view
    _soul(app.root, "rowan", "罗文", "碧石镇")
    _soul(app.root, "elena", "艾琳娜", "北门")
    with patch("neonrp.core.souls.list_souls", return_value=[{"sid": "mira", "name_local": "米拉"}]):
        app._cmd_list_souls()
    text = view.text
    assert "此刻在这个世界里" in text
    assert "罗文" in text and "碧石镇" in text and "艾琳娜" in text
    assert text.index("此刻在这个世界里") < text.index("可以请进这个世界的角色")
    assert "米拉" in text
    assert "/cast <名字>" in text and "/new" not in text

    # 选单只列还没在场的;选了就是 /cast <sid>
    app.push_screen.assert_called_once()
    screen, callback = app.push_screen.call_args.args[:2]
    assert [v for _, v in screen._options] == ["mira"]
    app._cmd_cast = MagicMock()
    callback("mira")
    app._cmd_cast.assert_called_once_with(["mira"])


def test_bare_cast_offers_no_picker_when_everyone_is_here(app_view):
    app, view = app_view
    _soul(app.root, "mira", "米拉", "北门")
    with patch("neonrp.core.playthrough.read_playthrough") as rp, patch(
        "neonrp.core.souls.list_souls", return_value=[{"sid": "mira", "name_local": "米拉"}]
    ):
        rp.return_value = MagicMock(souls=[MagicMock(sid="mira", instance_id="si-1")])
        app._cmd_list_souls()
    assert "已在场" in view.text
    app.push_screen.assert_not_called()


def test_bare_cast_falls_back_to_flat_npcs_for_orchestrator_worlds(app_view):
    app, view = app_view
    npc = app.root / "game" / "npc"
    npc.mkdir(parents=True)
    (npc / "smith.json").write_text(json.dumps({"id": "smith", "name": "铁匠", "location": "作坊"}), encoding="utf-8")
    with patch("neonrp.core.souls.list_souls", return_value=[]):
        app._cmd_list_souls()
    assert "铁匠" in view.text and "作坊" in view.text


def test_bare_cast_with_nobody_anywhere_points_at_create(app_view):
    app, view = app_view
    with patch("neonrp.core.souls.list_souls", return_value=[]):
        app._cmd_list_souls()
    assert "此刻在这个世界里" not in view.text
    assert "/create" in view.text


def test_world_cast_tolerates_broken_soul_folders(app_view):
    app, view = app_view
    d = app.root / "souls" / "junk-si-0"
    d.mkdir(parents=True)
    (d / "soul.json").write_text("{not json", encoding="utf-8")
    assert app._world_cast() == [("junk", "junk", "")]


# ── command table ─────────────────────────────────────────────────────


def test_init_and_vault_are_live_local_commands():
    for name in ("init", "vault"):
        assert name in COMMANDS, name
        assert name in LOCAL_SLASH_COMMANDS, name
        assert name not in CLI_FORWARD_COMMANDS, f"/{name} 不再是命令行 `neonrp {name}` 的转发"
        assert name in get_command_suggestions(name[:2]), name


def test_init_left_the_legacy_table():
    from neonrp.tui.legacy_commands import LEGACY_COMMANDS

    assert "init" not in LEGACY_COMMANDS, "改义后的 /init 住主表,不能两头都有"


def test_init_and_vault_arguments_parse():
    assert validate_command(parse_command("/init")) is None
    assert validate_command(parse_command("/init 猫岛 一座海岛,雾里有船来")) is None
    assert parse_command("/init 猫岛 一座 海岛").args == ["猫岛", "一座", "海岛"]
    assert validate_command(parse_command("/vault")) is None
    assert validate_command(parse_command("/vault build")) is None
    assert parse_command("/open cat-isle --build").options == {"build": "true"}


def test_live_command_ceiling_still_holds():
    """M31 的口径:在编命令不超过 22 条。加 /init /vault 不该把它撑爆。"""
    assert len(COMMANDS) <= 25, sorted(COMMANDS)  # + /status /lang /dev


# ── 新局用现在在用的模型 ──────────────────────────────────────────────


def test_new_run_inherits_the_model_this_world_is_on(app_view, homes, monkeypatch):
    """`/open` 开的新局一开口是「Stub provider active」:
    scaffold 取了 `list_presets()[0]`,而装了 `claude` CLI 时那一格是 Claude
    Code 虚拟预设 = stub。新局该用**这个世界正在用的**模型。"""
    app, view = app_view
    (app.root / ".neonrp").mkdir()
    (app.root / ".neonrp" / "config.json").write_text(
        json.dumps({"llm": {"model_ref": "qwen"}, "models": {"qwen": {"provider": "openai", "model": "q"}}}),
        encoding="utf-8",
    )
    src = homes / "worlds" / "cat-isle"
    src.mkdir(parents=True)
    (src / ".neonrp").mkdir()
    (src / ".neonrp" / "config.json").write_text(json.dumps({"llm": {"model_ref": "stub"}}), encoding="utf-8")

    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=[{"id": "cat-isle", "display_name": "猫岛", "desc": ""}]
    ), patch("neonrp.presets.build_config_dict", return_value={"llm": {"model_ref": "qwen"}, "models": {"qwen": {"provider": "openai", "model": "q"}}}):
        app._cmd_open(["cat-isle"])

    run = app.reopen_request.root
    cfg = json.loads((run / ".neonrp" / "config.json").read_text(encoding="utf-8"))
    assert cfg["llm"]["model_ref"] == "qwen"
    assert cfg["models"]["qwen"]["model"] == "q"


def test_current_model_ref_ignores_stub(app_view):
    app, view = app_view
    (app.root / ".neonrp").mkdir()
    (app.root / ".neonrp" / "config.json").write_text(json.dumps({"llm": {"model_ref": "stub"}}), encoding="utf-8")
    with patch("neonrp.core.config._use_user_config_by_default", return_value=False):
        assert app._current_model_ref() is None


def test_init_world_starts_on_the_current_model(app_view, homes, monkeypatch):
    app, view = app_view
    app._current_model_ref = lambda: "qwen"
    with patch(
        "neonrp.presets.build_config_dict",
        return_value={"llm": {"model_ref": "qwen"}, "models": {"qwen": {"provider": "openai", "model": "q"}}},
    ):
        app._cmd_init(["猫岛"])
    cfg = json.loads((homes / "worlds" / "猫岛" / ".neonrp" / "config.json").read_text(encoding="utf-8"))
    assert cfg["llm"]["model_ref"] == "qwen"
