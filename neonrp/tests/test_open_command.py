"""`/open [世界|存档]` —— 一条命令回答「我能玩什么、接着玩哪个」。

取代 `/worlds` `/worldlines` `/continue`。它们各自只答了一半,而且 `/worlds`
其实并不「打开」世界:它把模板 scaffold 进**当前**工作区(破坏性的
`game new`),名字和行为对不上。

两处是真正会出事的地方,测试压在这两处:

1. **解析优先级** —— 存档目录名是 `<世界id>-<时间戳>`,世界 id 天然是存档
   名的前缀。`/open cat-isle` 若解析成「世界库」,玩家等来的是一局全新的,
   而他要的是**昨天那局**。
2. **换局的交接** —— root 全程不重绑,所以换世界是退出后重起。上一局的
   branch 和启动命令必须留在上一局,不然会在新世界里重放一遍。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neonrp.tui.app import NeonRPApp, _ReopenRequest
from neonrp.tui.commands import COMMANDS, parse_command, validate_command


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
    app.reopen_request = None
    app.ui_locale = "en"
    view = _View()
    app.push_screen = MagicMock()  # 裸 /open 会弹选单;这里只看它弹了什么
    monkeypatch.setattr(NeonRPApp, "query_one", lambda self, *a, **k: view)
    monkeypatch.setattr(NeonRPApp, "exit", lambda self, *a, **k: None)
    return app, view


def _saves(*entries):
    return [
        {"dir_name": d, "display_name": n, "mtime_display": "刚刚", "started": True}
        for d, n in entries
    ]


def _worlds(*ids):
    return [{"id": i, "display_name": i.title(), "desc": "…"} for i in ids]


# ── 解析优先级 ────────────────────────────────────────────────────────

def test_exact_save_name_opens_that_save(app_view, tmp_path):
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=_saves(("cat-isle-20260901", "猫岛"))), patch(
        "neonrp.worlds.list_worlds", return_value=[]
    ):
        app._cmd_open(["cat-isle-20260901"])
    assert app.reopen_request is not None
    assert app.reopen_request.root.name == "cat-isle-20260901"


def test_world_id_prefers_the_existing_save_over_a_fresh_world(app_view, tmp_path, monkeypatch):
    """这条是整个命令最容易出事的地方。

    `/open cat-isle` 两边都命中:世界库里有 `cat-isle`,存档里有
    `cat-isle-20260901`。解析成世界库 = 给他一局全新的,而他要的是昨天那局。
    """
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    (tmp_path / "worlds" / "cat-isle").mkdir(parents=True)

    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=_saves(("cat-isle-20260901", "猫岛"))), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("cat-isle")
    ):
        app._cmd_open(["cat-isle"])

    assert app.reopen_request is not None
    assert app.reopen_request.root.name == "cat-isle-20260901", "应该接着昨天那局,而不是开新的"
    assert app.reopen_request.continue_session is True


def test_world_without_a_save_starts_a_new_run_not_the_source(app_view, tmp_path, monkeypatch):
    """世界库里的源永远不被直接玩:打开世界 = 在 plays/ 下开一局新的。

    直接在源上玩会把回合状态写回库(下一局就不是新局了),与 launcher 的
    world/run 分离矛盾。"""
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "plays")
    src = tmp_path / "worlds" / "spice-witch"
    src.mkdir(parents=True)
    (src / "marker.txt").write_text("source")

    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("spice-witch")
    ):
        app._cmd_open(["spice-witch"])

    req = app.reopen_request
    assert req is not None
    assert req.root.parent == tmp_path / "plays", "新局落在 plays/,不是库里的源"
    assert req.root.name.startswith("spice-witch-")
    assert (req.root / "marker.txt").read_text() == "source", "新局是源的一份拷贝"
    assert req.continue_session is False, "全新的一局没有会话可续"
    assert req.mode == "play"
    assert "新一局" in view.text


def test_builtin_world_scaffolds_a_run_from_its_template(app_view, tmp_path, monkeypatch):
    """内置世界没有源目录,开新局走打包模板 —— 之前这条路只有 launcher 会走,
    `/open stone-ford` 在 TUI 里会报「没有这个世界」。"""
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")  # 不存在:内置世界没有源
    run = tmp_path / "plays" / "stone-ford-20260908-000000"
    run.mkdir(parents=True)

    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("stone-ford")
    ), patch("neonrp.worlds.scaffold_builtin_run", return_value=run) as scaffold, patch(
        "neonrp.worlds.instantiate_run", side_effect=AssertionError("built-ins have no source to copy")
    ):
        app._cmd_open(["stone-ford"])

    scaffold.assert_called_once()
    assert scaffold.call_args.args == ("stone-ford",)
    assert app.reopen_request is not None and app.reopen_request.root == run


def test_new_flag_forces_a_fresh_run_even_with_a_save(app_view, tmp_path, monkeypatch):
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "plays")
    (tmp_path / "worlds" / "cat-isle").mkdir(parents=True)

    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=_saves(("cat-isle-20260901", "猫岛"))), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("cat-isle")
    ):
        app._cmd_open(["cat-isle"], {"new": "true"})

    req = app.reopen_request
    assert req is not None
    assert req.root.name != "cat-isle-20260901" and req.root.name.startswith("cat-isle-")
    assert req.continue_session is False


def test_build_flag_opens_the_owned_source_in_the_workshop(app_view, tmp_path, monkeypatch):
    """`--build` 是 `/init` 之后回来接着造的路:打开的是**源**,模式是 build,
    而且不能顺手开一局新的。"""
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "plays")
    src = tmp_path / "worlds" / "cat-isle"
    src.mkdir(parents=True)

    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=_saves(("cat-isle-20260901", "猫岛"))), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("cat-isle")
    ):
        app._cmd_open(["cat-isle"], {"build": "true"})

    req = app.reopen_request
    assert req is not None
    assert req.root == src
    assert req.mode == "build"
    assert req.continue_session is False
    assert not (tmp_path / "plays").exists(), "进工坊不该顺手开新局"


def test_build_flag_refuses_a_builtin_world(app_view, tmp_path, monkeypatch):
    """内置世界没有可编辑的源 —— 说清楚,并指向 /init。"""
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("stone-ford")
    ), patch("neonrp.worlds.scaffold_builtin_run", side_effect=AssertionError("must not scaffold")):
        app._cmd_open(["stone-ford"], {"build": "true"})
    assert app.reopen_request is None
    assert "内置" in view.text and "/init" in view.text


def test_failed_run_start_is_reported_not_raised(app_view, tmp_path, monkeypatch):
    import neonrp.worlds as W

    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("stone-ford")
    ), patch("neonrp.worlds.scaffold_builtin_run", side_effect=RuntimeError("disk full")):
        app._cmd_open(["stone-ford"])
    assert app.reopen_request is None
    assert "disk full" in view.text


def test_unknown_name_does_not_reopen(app_view):
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=[]
    ):
        app._cmd_open(["nope"])
    assert app.reopen_request is None, "认不出就不该换局"
    assert "nope" in view.text


def test_opening_the_current_world_is_a_noop(app_view, tmp_path):
    """已经在里面了就别重启一遍 —— 重启会丢掉当前对话。"""
    app, view = app_view
    app.root = tmp_path / "plays" / "cat-isle-20260901"
    with patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"), patch(
        "neonrp.worlds.list_saved_games", return_value=_saves(("cat-isle-20260901", "猫岛"))
    ), patch("neonrp.worlds.list_worlds", return_value=[]):
        app._cmd_open(["cat-isle-20260901"])
    assert app.reopen_request is None
    assert "已经在" in view.text


# ── 菜单 ──────────────────────────────────────────────────────────────

def test_bare_open_lists_saves_before_worlds(app_view):
    """大多数时候你是要接着玩,不是开新的。"""
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=_saves(("cat-isle-20260901", "猫岛"))), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("spice-witch")
    ):
        app._cmd_open([])
    text = view.text
    assert text.index("存档") < text.index("世界库")
    assert "cat-isle-20260901" in text and "spice-witch" in text


def test_bare_open_also_offers_a_picker(app_view):
    """不带参数要**引导**:文字清单之上弹一个选单,选了就等于敲了 /open <它>
    (「如果没有参数的话能引导打开 list」)。"""
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=_saves(("cat-isle-20260901", "猫岛"))), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("spice-witch")
    ):
        app._cmd_open([])
    app.push_screen.assert_called_once()
    screen, callback = app.push_screen.call_args.args[:2]
    values = [v for _, v in screen._options]
    assert "save::cat-isle-20260901" in values
    assert "world::spice-witch" in values
    assert "init" in values, "从零建一个也在选单里"
    assert values.index("save::cat-isle-20260901") < values.index("world::spice-witch"), "存档在前"

    # 选存档 = /open <存档>;选世界 = 开新局;选 init = /init 引导
    app._cmd_open = MagicMock()
    app._guide_init = MagicMock()
    callback("save::cat-isle-20260901")
    app._cmd_open.assert_called_with(["cat-isle-20260901"])
    callback("world::spice-witch")
    assert app._cmd_open.call_args.args[0] == ["spice-witch"]
    assert app._cmd_open.call_args.args[1] == {"new": "true"}
    callback("init")
    app._guide_init.assert_called_once()
    callback(None)  # Esc:什么都不做


def test_bare_open_never_reopens(app_view):
    """不带参数是**看**,不是选 —— 列个表就把人踢出当前世界是最糟的意外。"""
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=_saves(("a-1", "A"))), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("b")
    ):
        app._cmd_open([])
    assert app.reopen_request is None


def test_empty_library_says_so(app_view):
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=[]
    ), patch.object(NeonRPApp, "_openable_templates", return_value=[]):  # 模板也算可打开的(test_open_templates.py)
        app._cmd_open([])
    assert "还没有" in view.text


def test_broken_save_listing_still_lists_worlds(app_view):
    """存档目录坏掉不该连世界库一起看不见。"""
    app, view = app_view
    with patch("neonrp.worlds.list_saved_games", side_effect=OSError("boom")), patch(
        "neonrp.worlds.list_worlds", return_value=_worlds("spice-witch")
    ):
        app._cmd_open([])
    assert "spice-witch" in view.text


# ── 换局的交接 ────────────────────────────────────────────────────────

def test_run_tui_reopens_on_request(tmp_path):
    """换世界 = 退出后用新 root 再起一局。"""
    from neonrp.tui import app as A

    roots: list[Path] = []
    plan = [_ReopenRequest(root=tmp_path / "second"), None]

    class _FakeApp:
        def __init__(self, root=None, **kw):
            roots.append(root)
            self.kw = kw
            self.reopen_request = plan.pop(0)

        def run(self):
            pass

    with patch.object(A, "NeonRPApp", _FakeApp):
        A.run_tui(root=tmp_path / "first")

    assert roots == [tmp_path / "first", tmp_path / "second"]


def test_reopen_does_not_replay_the_previous_sessions_startup(tmp_path):
    """branch 与启动命令属于**上一局**。带过去会在新世界里重放一遍 ——
    比如 `--import-card` 排的 /import 会把同一张卡再导一次。"""
    from neonrp.tui import app as A

    seen: list[dict] = []
    plan = [_ReopenRequest(root=tmp_path / "second", continue_session=True), None]

    class _FakeApp:
        def __init__(self, root=None, **kw):
            seen.append(kw)
            self.reopen_request = plan.pop(0)

        def run(self):
            pass

    with patch.object(A, "NeonRPApp", _FakeApp):
        A.run_tui(root=tmp_path / "first", branch="wip", startup_commands=["/import a.png"])

    assert seen[0]["startup_commands"] == ["/import a.png"]
    assert seen[1]["startup_commands"] is None, "启动命令不该在新世界重放"
    assert seen[1]["branch"] is None, "分支属于上一局"
    assert seen[1]["continue_session"] is True, "存档要接着上次的会话"


def test_reopen_carries_mode_and_its_own_startup_commands(tmp_path):
    """`/init` 换局进工坊时带两样东西:mode=build,和给 agent 的第一句话。
    它们是**新一局**的,与上一局的启动命令(不该重放)是两回事。"""
    from neonrp.tui import app as A

    seen: list[dict] = []
    plan = [
        _ReopenRequest(root=tmp_path / "second", mode="build", startup_commands=["写出这个世界"]),
        _ReopenRequest(root=tmp_path / "third", mode="play"),
        None,
    ]

    class _FakeApp:
        def __init__(self, root=None, **kw):
            seen.append(kw)
            self.reopen_request = plan.pop(0)

        def run(self):
            pass

    with patch.object(A, "NeonRPApp", _FakeApp):
        A.run_tui(root=tmp_path / "first", mode="play", startup_commands=["/import a.png"])

    assert seen[0]["mode"] == "play" and seen[0]["startup_commands"] == ["/import a.png"]
    assert seen[1]["mode"] == "build" and seen[1]["startup_commands"] == ["写出这个世界"]
    assert seen[2]["mode"] == "play" and seen[2]["startup_commands"] is None


def test_run_tui_returns_when_nothing_to_reopen(tmp_path):
    """守卫:没有交接单就必须退出。写错了就是个不肯关的窗口。"""
    from neonrp.tui import app as A

    runs = {"n": 0}

    class _FakeApp:
        def __init__(self, **kw):
            self.reopen_request = None

        def run(self):
            runs["n"] += 1

    with patch.object(A, "NeonRPApp", _FakeApp):
        A.run_tui(root=tmp_path)
    assert runs["n"] == 1


# ── 命令面 ────────────────────────────────────────────────────────────

def test_open_takes_an_optional_argument():
    """不带参数看菜单,带参数打开 —— 两种都得合法。"""
    assert COMMANDS["open"]["args"] == "?"
    assert validate_command(parse_command("/open")) is None
    assert validate_command(parse_command("/open cat-isle")) is None


def test_open_is_local_not_cli_passthrough():
    from neonrp.tui.app import CLI_FORWARD_COMMANDS, LOCAL_SLASH_COMMANDS

    assert "open" in LOCAL_SLASH_COMMANDS
    assert "open" not in CLI_FORWARD_COMMANDS


def test_replaced_commands_left_the_live_surface():
    """/worlds /worldlines /continue 已被 /open 收编:不在主表、不在裸 / 的
    列表里(敲前缀会灰显出现,那是退役命令的统一规则)。"""
    from neonrp.tui.commands import get_command_suggestions

    bare = get_command_suggestions("")
    for name in ("worlds", "worldlines", "continue"):
        assert name not in COMMANDS, name
        assert name not in bare, name


def test_replaced_commands_still_execute():
    """/worlds /continue 删了 —— 敲出来会指向 /open。"""
    for line in ("/worlds", "/continue"):
        assert "/open" in validate_command(parse_command(line)), line
