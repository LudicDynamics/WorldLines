"""M31 · build ↔ play — 模式切换补完 + agent 建角色入世。

两组:
- ``TestApplyMode``:`/mode` 必须把**两半**都搬过去。M31 之前它只搬了
  引擎那半(``session.mode``),``self.mode`` 留在构造值上 —— 于是状态栏
  写着 play、生图闸门还按 build 判、语义层还是 build 的 L3。
- ``TestCastSoulTool``:agent 自己写完 soul 文件夹之后,入世必须走
  ``cast_soul``。playthrough.json 的 soul 引用喂 commit 哈希链
  (见 ``test_hash_first_repro``),手写必炸,所以这条路要能走通、
  结构要保底、越界要挡住。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from neonrp.core.playthrough import (
    Playthrough,
    SoulRef,
    WorldAgentTeam,
    WorldRef,
    read_playthrough,
    write_playthrough,
)
from neonrp.core.skills import SkillRegistry, get_skill_schemas
from neonrp.tui.app import NeonRPApp


# ── /mode 补完 ────────────────────────────────────────────────


class TestApplyMode:
    def test_apply_mode_moves_both_halves(self, tmp_path: Path) -> None:
        """引擎半(session)与 app 半(self.mode)必须一起走。"""
        app = NeonRPApp(root=tmp_path, mode="build")
        session = MagicMock()
        session.mode = "build"
        app.session = session

        app._apply_mode("play")

        assert app.mode == "play"
        session.set_mode.assert_called_once_with("play")

    def test_apply_mode_without_session_still_moves_app_half(
        self, tmp_path: Path
    ) -> None:
        """没有会话时也不能把 self.mode 留在旧值上(切回来才对得上)。"""
        app = NeonRPApp(root=tmp_path, mode="play")
        app.session = None

        app._apply_mode("build")

        assert app.mode == "build"

    def test_apply_mode_seeds_semantic_layer_like_on_mount(
        self, tmp_path: Path
    ) -> None:
        """语义层要与 on_mount 同口径:play=L2(叙事)/ build=L3(工具调用)。"""
        app = NeonRPApp(root=tmp_path, mode="build")
        app.session = None

        app._apply_mode("play")
        assert app._semantic_layer == 2

        app._apply_mode("build")
        assert app._semantic_layer == 3

    def test_cmd_mode_rejects_unknown_mode(self, tmp_path: Path) -> None:
        """未知模式不许改动任何一半。"""
        app = NeonRPApp(root=tmp_path, mode="build")
        session = MagicMock()
        app.session = session
        view = MagicMock()
        app.query_one = MagicMock(return_value=view)

        app._cmd_mode(["nonsense"])

        assert app.mode == "build"
        session.set_mode.assert_not_called()


# ── cast_soul ────────────────────────────────────────────────


_SID = "luowen"
_WORLD_VERSION = "sha256:world-bundle-v1"


def _seed_world(root: Path) -> None:
    """最小 multi-agent 存档:game/ + playthrough(零 soul)。"""
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": 1}, ensure_ascii=False), encoding="utf-8"
    )
    write_playthrough(
        root,
        Playthrough(
            schema_version=2,
            playthrough_id="pt-m31",
            world=WorldRef(
                wid="testworld",
                instance_id="wi-0000000000ff",
                version_hash=_WORLD_VERSION,
                head_commit="",
            ),
            world_agent_team=WorldAgentTeam(seeded_from="m31@test", agents=[]),
            souls=[],
            created_at="2026-08-26T00:00:00Z",
            active_souls=(),
        ),
    )


def _author_draft(root: Path, sid: str = _SID) -> Path:
    """模拟 build agent 用 write_file 写出来的 soul 草稿。

    刻意只写 persona —— agent 写漏 agents/manifest.json 是常态,
    结构保底就是为这种情况存在的。
    """
    draft = root / ".neonrp" / "soul-drafts" / sid
    (draft / "persona").mkdir(parents=True)
    (draft / "soul.json").write_text(
        json.dumps({"sid": sid, "name": "Luowen"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (draft / "persona" / "kernel.md").write_text(
        "沉默寡言的铁匠。", encoding="utf-8"
    )
    return draft


def _registry(root: Path) -> SkillRegistry:
    """Build 模式的权限形状(conversation.py:mode == 'build')。"""
    return SkillRegistry(
        root=root,
        run_id="run-m31",
        agent_id="world-agent",
        read_globs=["**"],
        deny_globs=[],
        direct_write_globs=["**"],
        allow_protected_paths=True,
    )


class TestCastSoulTool:
    def test_cast_soul_registers_draft_into_playthrough(
        self, tmp_path: Path
    ) -> None:
        """草稿 → 入世:soul 落进 souls/ 且 playthrough 认得它。"""
        _seed_world(tmp_path)
        _author_draft(tmp_path)

        result = _registry(tmp_path).invoke("cast_soul", {"sid": _SID})

        assert result.success, result.error
        iid = result.data["instance_id"]
        assert (tmp_path / "souls" / f"{_SID}-{iid}").is_dir()

        pt = read_playthrough(tmp_path)
        assert [s.sid for s in pt.souls] == [_SID]
        assert iid in pt.active_souls

    def test_cast_soul_backfills_agent_manifest(self, tmp_path: Path) -> None:
        """agents/manifest.json 是模板政策,不是 LLM 写的——必须被补上。

        没有它 ``resolve_soul_agent_data`` 返回 None,soul-agent 回合直接报错。
        """
        _seed_world(tmp_path)
        draft = _author_draft(tmp_path)
        assert not (draft / "agents" / "manifest.json").exists()

        result = _registry(tmp_path).invoke("cast_soul", {"sid": _SID})

        assert result.success, result.error
        iid = result.data["instance_id"]
        manifest = tmp_path / "souls" / f"{_SID}-{iid}" / "agents" / "manifest.json"
        assert manifest.is_file()
        assert json.loads(manifest.read_text(encoding="utf-8"))["agents"]

    def test_cast_soul_keeps_playthrough_landable(self, tmp_path: Path) -> None:
        """入世后回合仍要落得了账。

        SoulRef 的 version_hash / head_commit 是 compose 与 land 两侧
        共同的输入(hash-first);由工具确定性写入,才不会重开
        ``test_hash_first_repro`` 那个坑。
        """
        import asyncio

        from neonrp.core.world_agent import WorldAgent

        _seed_world(tmp_path)
        _author_draft(tmp_path)
        assert _registry(tmp_path).invoke("cast_soul", {"sid": _SID}).success

        commit_id = asyncio.run(
            WorldAgent(tmp_path).land_turn([], turn_seq=1, branch="main")
        )
        assert commit_id

    def test_cast_soul_archives_the_character_into_the_library(self, tmp_path: Path) -> None:
        """任务 B1:cast 过的角色也在 ~/.worldlines/souls/<sid>/ 有一份,
        可以被请进别的世界(conftest 已把库指到临时目录)。"""
        import neonrp.core.souls as S

        _seed_world(tmp_path)
        _author_draft(tmp_path)
        res = _registry(tmp_path).invoke("cast_soul", {"sid": _SID})
        assert res.success, res.error
        lib = S.SOUL_HOME / _SID
        assert lib.is_dir() and (lib / "soul.json").is_file()
        assert res.data["library"] == str(lib)
        assert not (lib / "run_state.json").exists()

    def test_cast_soul_reports_missing_draft(self, tmp_path: Path) -> None:
        """没写过文件夹就 cast:报错要指路,而不是静默造一个空角色。"""
        _seed_world(tmp_path)

        result = _registry(tmp_path).invoke("cast_soul", {"sid": "ghost"})

        assert not result.success
        assert "soul-drafts" in (result.error or "")

    def test_cast_soul_refuses_path_escape(self, tmp_path: Path) -> None:
        """sid 来自模型,不许借它走出 project。"""
        _seed_world(tmp_path)

        result = _registry(tmp_path).invoke(
            "cast_soul", {"sid": "../../../etc/passwd"}
        )

        assert not result.success

    def test_cast_soul_rejects_unknown_role(self, tmp_path: Path) -> None:
        _seed_world(tmp_path)
        _author_draft(tmp_path)

        result = _registry(tmp_path).invoke(
            "cast_soul", {"sid": _SID, "role": "villain"}
        )

        assert not result.success
        assert read_playthrough(tmp_path).souls == []

    def test_cast_soul_can_stay_off_stage(self, tmp_path: Path) -> None:
        """activate=False:入册但不上场。"""
        _seed_world(tmp_path)
        _author_draft(tmp_path)

        result = _registry(tmp_path).invoke(
            "cast_soul", {"sid": _SID, "activate": False}
        )

        assert result.success, result.error
        pt = read_playthrough(tmp_path)
        assert [s.sid for s in pt.souls] == [_SID]
        assert pt.active_souls == ()


class TestCastSoulExposure:
    def test_cast_soul_is_a_registered_tool(self) -> None:
        names = {schema["name"] for schema in get_skill_schemas()}
        assert "cast_soul" in names

    def test_cast_is_available_in_both_modes(self, tmp_path: Path) -> None:
        """build 造、play 迎。

        「把已经建好的角色放进世界」是游玩期就该能做的事;真正只属于
        build 的是**写出**一个新角色。所以 cast 两边都在,而写盘工具靠
        权限与提示词留在 build 那侧。
        """
        from neonrp.core.conversation import _get_tool_schemas
        from neonrp.core.skill_loader import SkillLoader

        loader = SkillLoader(root=tmp_path)
        build_names = {s["name"] for s in _get_tool_schemas("build", loader, tmp_path)}
        play_names = {s["name"] for s in _get_tool_schemas("play", loader, tmp_path)}

        assert "cast_soul" in build_names
        assert "cast_soul" in play_names
        # 打开外部查看器仍是著述期的动作:游玩中途在玩家桌面弹窗是打扰。
        assert "open_in_viewer" in build_names
        assert "open_in_viewer" not in play_names

    def test_cast_soul_survives_agent_tool_allowlist(self) -> None:
        """agent.json 的 allowlist(为 play 期路由写的)不该在 build 里
        把著述工具剥掉——与 write_file 同一条豁免。"""
        from neonrp.core.conversation import _filter_tool_schemas_by_agent_config

        schemas = [{"name": "cast_soul"}, {"name": "write_file"}, {"name": "find"}]
        kept = {
            s["name"]
            for s in _filter_tool_schemas_by_agent_config(
                schemas, {"tools": ["find"]}, mode="build"
            )
        }
        assert {"cast_soul", "write_file"} <= kept


def test_new_soul_ref_carries_manifest_version(tmp_path: Path) -> None:
    """SoulRef 的 version_hash 取自 soul 自己的 bundle,不是世界的。

    两者天然不同;compose 侧回落世界版本正是 hash-first 假说③的成因。
    """
    _seed_world(tmp_path)
    _author_draft(tmp_path)

    assert _registry(tmp_path).invoke("cast_soul", {"sid": _SID}).success

    pt = read_playthrough(tmp_path)
    ref: SoulRef = pt.souls[0]
    assert ref.head_commit == ""
    assert ref.instance_id


class TestPlayStatusScrolling:
    """play 面的状态显示必须能滚。

    Textual 只让「有 layout 或有子节点」的 widget 滚动:

        is_scrollable = styles.layout is not None or bool(self._nodes)

    而这两个都是渲染单块内容的叶子 Static,所以 `_refresh_scrollbars`
    在算滚动条之前就 early-return —— CSS 里的 `overflow-y: auto` 是死的。
    内容溢出时只是被裁掉,够不着。
    """

    def test_game_state_panel_scrolls(self) -> None:
        from neonrp.tui.game_state_panel import GameStatePanel

        assert GameStatePanel().is_scrollable

    def test_character_status_lane_scrolls(self) -> None:
        from neonrp.tui.app import CharacterStatusLane

        assert CharacterStatusLane().is_scrollable

    def test_a_plain_static_still_does_not(self) -> None:
        """对照组:证明上面两条是各自 opt-in,不是 Textual 变了。"""
        from textual.widgets import Static

        assert not Static("x").is_scrollable


class TestModeColour:
    """模式要能被余光认出来。

    「从绿色的 play 进入红色的 build」—— 颜色不是装饰,它是这次心智改动的
    载体:红的一侧你改的是世界本身,绿的一侧你只是在里面活动。
    """

    def test_build_is_red_and_play_is_green(self) -> None:
        from neonrp.tui.app import mode_accent

        assert mode_accent("build") == "#ff4757"
        assert mode_accent("play") == "#18FF82"

    def test_the_two_modes_never_share_a_colour(self) -> None:
        from neonrp.tui.app import mode_accent

        assert mode_accent("build") != mode_accent("play")
        assert mode_accent("build", dim=True) != mode_accent("play", dim=True)

    def test_unknown_mode_falls_back_to_build(self) -> None:
        """拿不准时按「可能在改世界」处理,而不是让它看起来像游玩。"""
        from neonrp.tui.app import mode_accent

        assert mode_accent(None) == mode_accent("build")
        assert mode_accent("nonsense") == mode_accent("build")

    def test_accent_does_not_collide_with_the_error_colour(self) -> None:
        from neonrp.tui.app import ConversationView, mode_accent

        assert mode_accent("build") != ConversationView._ERR_COLOR


class TestCharacterVerbs:
    """角色的四个动词(docs/COMMANDS.md)。

        /create 造(build 红) · /new 迎(play 绿)
        /remove 不见了       · /reset 忘了

    动词挂在**角色**上而不是会话上,所以命令名本身就说明你站在哪一侧。
    这里钉两件会动到盘的:remove 只带走这个世界里的那一份,reset 只抹掉
    「经历过什么」而不碰「它是谁」。
    """

    def _world_with_soul(self, tmp_path: Path):
        from neonrp.tui.app import NeonRPApp

        _seed_world(tmp_path)
        _author_draft(tmp_path)
        assert _registry(tmp_path).invoke("cast_soul", {"sid": _SID}).success

        app = NeonRPApp(root=tmp_path, mode="play")
        app.query_one = MagicMock(return_value=MagicMock())
        iid = read_playthrough(tmp_path).souls[0].instance_id
        return app, tmp_path / "souls" / f"{_SID}-{iid}"

    def test_remove_takes_the_character_out_of_the_world(self, tmp_path: Path) -> None:
        app, soul_dir = self._world_with_soul(tmp_path)

        app._cmd_remove_soul([_SID])

        assert read_playthrough(tmp_path).souls == []
        assert not soul_dir.exists()

    def test_remove_leaves_the_source_alone(self, tmp_path: Path) -> None:
        """来源还在,所以 /new 能把它请回来 —— 这是 remove 和「删掉」的区别。"""
        app, _ = self._world_with_soul(tmp_path)

        app._cmd_remove_soul([_SID])

        draft = tmp_path / ".neonrp" / "soul-drafts" / _SID
        assert (draft / "soul.json").is_file()

    def test_remove_reports_an_unknown_name(self, tmp_path: Path) -> None:
        app, _ = self._world_with_soul(tmp_path)
        view = MagicMock()
        app.query_one = MagicMock(return_value=view)

        app._cmd_remove_soul(["查无此人"])

        assert read_playthrough(tmp_path).souls  # 没动
        assert any("查无此人" in str(c) for c in view.write.call_args_list)

    def test_reset_forgets_experience_but_keeps_identity(self, tmp_path: Path) -> None:
        """「它是谁」不动,「它经历过什么」清空 —— 这是 reset 的全部含义。"""
        app, soul_dir = self._world_with_soul(tmp_path)
        (soul_dir / "long-term-memo").mkdir(parents=True, exist_ok=True)
        (soul_dir / "long-term-memo" / "learned.json").write_text("{}", encoding="utf-8")
        (soul_dir / "trajectory").mkdir(parents=True, exist_ok=True)
        (soul_dir / "trajectory" / "action_log.md").write_text("走过很多路", encoding="utf-8")
        persona = soul_dir / "persona" / "kernel.md"

        app._cmd_reset_soul([_SID])

        assert not (soul_dir / "long-term-memo" / "learned.json").exists()
        assert not (soul_dir / "trajectory" / "action_log.md").exists()
        assert persona.is_file()  # 著述内容一个字都不动
        assert read_playthrough(tmp_path).souls  # 仍在世界里

    def test_reset_keeps_the_character_in_the_world(self, tmp_path: Path) -> None:
        """reset 与 remove 的分界:忘了 ≠ 不见了。"""
        app, soul_dir = self._world_with_soul(tmp_path)

        app._cmd_reset_soul([_SID])

        assert soul_dir.is_dir()
        assert [s.sid for s in read_playthrough(tmp_path).souls] == [_SID]


class TestSoulListing:
    """`/new` 不带参数要给出菜单。

    没有这一屏,`/new <角色>` 就要求你先知道名字,而你根本没地方看到它
    (实测时发现)。跟着仓里既有的习惯:`/load` 不带参数
    就列存档,所以「不带参数 = 给我看菜单」。
    """

    def _app(self, tmp_path: Path):
        from neonrp.tui.app import NeonRPApp

        app = NeonRPApp(root=tmp_path, mode="play")
        view = MagicMock()
        app.query_one = MagicMock(return_value=view)
        # 清单之后还会弹一个选单(tests/test_init_vault_cast_commands.py 管它);
        # 没挂载的 app 推屏要事件循环,这里只看文字。
        app.push_screen = MagicMock()
        return app, view

    def _said(self, view) -> str:
        return "".join(str(c.args[0]) for c in view.write.call_args_list)

    def test_drafts_are_listed(self, tmp_path: Path) -> None:
        """build 期刚写出来、还没入世的草稿,是最可能想请进来的。"""
        _seed_world(tmp_path)
        _author_draft(tmp_path)
        app, view = self._app(tmp_path)

        app._cmd_list_souls()

        assert _SID in self._said(view)

    def test_marks_who_is_already_here(self, tmp_path: Path) -> None:
        _seed_world(tmp_path)
        _author_draft(tmp_path)
        assert _registry(tmp_path).invoke("cast_soul", {"sid": _SID}).success
        app, view = self._app(tmp_path)

        app._cmd_list_souls()

        assert "已在场" in self._said(view)

    def test_empty_listing_points_at_create(self, tmp_path: Path) -> None:
        """一个角色都没有时,该告诉人下一步怎么办,而不是给一张空表。"""
        _seed_world(tmp_path)
        app, view = self._app(tmp_path)
        app.ui_locale = "zh"
        import neonrp.core.souls as souls_mod

        original = souls_mod.list_souls
        souls_mod.list_souls = lambda *_a, **_k: []
        try:
            app._cmd_list_souls()
        finally:
            souls_mod.list_souls = original

        assert "/create" in self._said(view)

    def test_listing_survives_a_world_without_playthrough(self, tmp_path: Path) -> None:
        """没绑 playthrough 的世界也要能列(只是没人「已在场」)。"""
        (tmp_path / "game").mkdir(parents=True)
        app, view = self._app(tmp_path)

        app._cmd_list_souls()  # 不抛

        assert view.write.called


