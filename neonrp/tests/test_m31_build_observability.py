"""M31 B1-B4 · build 模式的可观测面 —— 改了什么、怎么改的。

build 模式没有 review 步骤:agent 一写,文件就在盘上了。所以「改了什么/
怎么改」必须由 agent 面自己交代,而不是让人去 diff 文件系统。四层:

- B1 ``summarize_write``:每次直接写盘产出一条改动记录(工具卡吃它)
- B2 ``TurnChangeLedger``:一回合的总账(回合末一行)
- B3 ``append_build_artifacts``:写进 run 里的 ``build.md``,让 Obsidian
  这类文件客户端也看得见「世界正在被编辑」
- B4 ``open_in_viewer``:可视化是 agent 的一个动作,不是 TUI 的面板
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core.diffing import TurnChangeLedger, summarize_write
from neonrp.core.player_artifacts import append_build_artifacts
from neonrp.core.skills import SkillRegistry


# ── B1 · 单次写盘的改动记录 ──────────────────────────────────


class TestSummarizeWrite:
    def test_new_file_reads_as_created(self) -> None:
        s = summarize_write("a.md", None, "one\ntwo\nthree")
        assert s.kind == "created"
        assert s.added == 3
        assert s.removed == 0
        assert s.headline == "created +3"

    def test_modified_counts_both_directions(self) -> None:
        s = summarize_write("a.md", "one\ntwo\nthree", "one\nTWO\nthree\nfour")
        assert s.kind == "modified"
        assert s.added == 2  # TWO + four
        assert s.removed == 1  # two
        assert "+2" in s.headline and "-1" in s.headline

    def test_delete_counts_what_was_lost(self) -> None:
        s = summarize_write("a.md", "one\ntwo", None)
        assert s.kind == "deleted"
        assert s.removed == 2
        assert s.preview == ""

    def test_identical_write_is_not_a_change(self) -> None:
        """重写同样内容不该在总账里冒出来——否则总账全是噪音。"""
        s = summarize_write("a.md", "same", "same")
        assert s.kind == "unchanged"
        assert s.headline == "unchanged"

    def test_preview_is_clipped_not_dumped(self) -> None:
        """预览是给人扫一眼的,不是把文件读回来。"""
        big = "\n".join(f"line {i}" for i in range(500))
        s = summarize_write("big.md", None, big)
        assert s.truncated
        assert len(s.preview.splitlines()) <= 24
        assert s.added == 500  # 计数仍然是全量

    def test_long_lines_are_clipped_too(self) -> None:
        s = summarize_write("wide.md", None, "x" * 5000)
        line = s.preview.splitlines()[0]
        assert len(line) < 200
        assert line.endswith("…")


# ── B2 · 回合总账 ───────────────────────────────────────────


class TestTurnChangeLedger:
    def test_empty_ledger_has_no_headline(self) -> None:
        assert TurnChangeLedger().is_empty
        assert TurnChangeLedger().headline() == ""

    def test_counts_by_kind(self) -> None:
        led = TurnChangeLedger()
        led.record(summarize_write("souls/luowen/persona/kernel.json", None, "a"))
        led.record(summarize_write("souls/luowen/rules/behaviour.md", None, "b"))
        led.record(summarize_write("souls/luowen/soul.json", "old", "new"))
        counts = led.counts()
        assert counts["created"] == 2
        assert counts["modified"] == 1

    def test_unchanged_writes_stay_out(self) -> None:
        led = TurnChangeLedger()
        led.record(summarize_write("a.md", "same", "same"))
        assert led.is_empty

    def test_headline_names_the_shared_folder(self) -> None:
        """动的都在一个角色下面时,一行就该说清楚在哪。"""
        led = TurnChangeLedger()
        led.record(summarize_write("souls/luowen/persona/kernel.json", None, "a"))
        led.record(summarize_write("souls/luowen/persona/voice.md", None, "b"))
        assert "souls/luowen/persona" in led.headline()

    def test_scattered_changes_drop_the_folder(self) -> None:
        led = TurnChangeLedger()
        led.record(summarize_write("game/npc/a.json", None, "a"))
        led.record(summarize_write("souls/b/soul.json", None, "b"))
        assert led.common_prefix() == ""
        assert "created" in led.headline()


# ── B3 · build.md(vault 里的痕迹)──────────────────────────


class TestBuildArtifacts:
    def test_writes_an_entry_for_a_turn_that_moved_files(self, tmp_path: Path) -> None:
        led = TurnChangeLedger()
        led.record(summarize_write("souls/luowen/soul.json", None, '{"sid":"luowen"}'))

        wrote = append_build_artifacts(
            tmp_path,
            "main",
            author_input="新建一个叫罗文的铁匠",
            narration="罗文建好了。",
            ledger=led,
        )

        assert wrote
        text = (tmp_path / "build.md").read_text(encoding="utf-8")
        assert "新建一个叫罗文的铁匠" in text
        assert "souls/luowen/soul.json" in text
        assert "罗文建好了。" in text

    def test_turn_that_changed_nothing_writes_nothing(self, tmp_path: Path) -> None:
        """纯问答的 build 回合不该在工坊日志里留噪音。"""
        wrote = append_build_artifacts(
            tmp_path,
            "main",
            author_input="这个世界有几个角色?",
            narration="三个。",
            ledger=TurnChangeLedger(),
        )
        assert not wrote
        assert not (tmp_path / "build.md").exists()

    def test_entries_append_not_overwrite(self, tmp_path: Path) -> None:
        led = TurnChangeLedger()
        led.record(summarize_write("a.json", None, "1"))
        append_build_artifacts(tmp_path, "main", author_input="一", narration="", ledger=led)
        led2 = TurnChangeLedger()
        led2.record(summarize_write("b.json", None, "2"))
        append_build_artifacts(tmp_path, "main", author_input="二", narration="", ledger=led2)

        text = (tmp_path / "build.md").read_text(encoding="utf-8")
        assert "一" in text and "二" in text
        assert text.count("## ") == 2

    def test_never_raises_into_a_turn(self, tmp_path: Path) -> None:
        """artifact 写失败绝不能把回合带崩(与 story.md 同一纪律)。"""

        class _Exploding:
            is_empty = False

            def headline(self):
                raise RuntimeError("boom")

        assert append_build_artifacts(
            tmp_path, "main", author_input="x", narration="", ledger=_Exploding()
        ) is False


# ── B1 端到端:写盘工具真的带回改动记录 ─────────────────────


def _registry(root: Path) -> SkillRegistry:
    return SkillRegistry(
        root=root,
        run_id="run-b1",
        agent_id="world-agent",
        read_globs=["**"],
        deny_globs=[],
        direct_write_globs=["**"],
        allow_protected_paths=True,
    )


class TestWriteToolsCarryChange:
    def test_write_file_reports_created(self, tmp_path: Path) -> None:
        reg = _registry(tmp_path)
        res = reg.invoke("write_file", {"path": "notes.md", "content": "a\nb"})
        assert res.success, res.error
        assert res.data["change"]["kind"] == "created"
        assert res.data["change"]["added"] == 2

    def test_second_write_reports_modified_with_diff(self, tmp_path: Path) -> None:
        reg = _registry(tmp_path)
        reg.invoke("write_file", {"path": "notes.md", "content": "a\nb"})
        res = reg.invoke("write_file", {"path": "notes.md", "content": "a\nB\nc"})
        change = res.data["change"]
        assert change["kind"] == "modified"
        assert "+B" in change["preview"]
        assert "-b" in change["preview"]

    def test_edit_file_reports_change(self, tmp_path: Path) -> None:
        reg = _registry(tmp_path)
        reg.invoke("write_file", {"path": "notes.md", "content": "hello world"})
        res = reg.invoke(
            "edit_file",
            {"path": "notes.md", "old_text": "world", "new_text": "there"},
        )
        assert res.success, res.error
        assert res.data["change"]["kind"] == "modified"

    def test_delete_file_reports_deleted(self, tmp_path: Path) -> None:
        reg = _registry(tmp_path)
        reg.invoke("write_file", {"path": "notes.md", "content": "a\nb"})
        res = reg.invoke("delete_file", {"path": "notes.md"})
        assert res.success, res.error
        assert res.data["change"]["kind"] == "deleted"

    def test_registry_accumulates_a_turn_ledger(self, tmp_path: Path) -> None:
        reg = _registry(tmp_path)
        reg.invoke("write_file", {"path": "a.md", "content": "1"})
        reg.invoke("write_file", {"path": "b.md", "content": "2"})
        reg.invoke("write_file", {"path": "a.md", "content": "1"})  # 无改动
        assert reg.change_ledger.counts()["created"] == 2
        assert len(reg.change_ledger.writes) == 2

    def test_binary_file_does_not_break_the_write(self, tmp_path: Path) -> None:
        """无法解码的旧内容不该让写盘失败——它只是没有行级故事可讲。"""
        target = tmp_path / "cover.png"
        target.write_bytes(b"\x89PNG\x00\x01\x02binary")
        reg = _registry(tmp_path)
        res = reg.invoke("write_file", {"path": "cover.png", "content": "now text"})
        assert res.success, res.error
        assert res.data["change"]["kind"] == "created"  # 旧内容读不出 → 视为新建


# ── B4 · open_in_viewer ─────────────────────────────────────


class TestOpenInViewer:
    def test_opens_a_project_file(self, tmp_path: Path) -> None:
        (tmp_path / "world_map.json").write_text("{}", encoding="utf-8")
        reg = _registry(tmp_path)
        opened: list[str] = []
        reg._viewer_opener = opened.append

        res = reg.invoke(
            "open_in_viewer", {"path": "world_map.json", "reason": "看一眼地图"}
        )

        assert res.success, res.error
        assert opened and opened[0].endswith("world_map.json")
        assert res.data["kind"] == "file"
        assert res.data["reason"] == "看一眼地图"

    def test_opens_a_folder_as_a_folder(self, tmp_path: Path) -> None:
        (tmp_path / "souls").mkdir()
        reg = _registry(tmp_path)
        reg._viewer_opener = lambda _p: None
        res = reg.invoke("open_in_viewer", {"path": "souls"})
        assert res.data["kind"] == "directory"

    def test_refuses_to_leave_the_project(self, tmp_path: Path) -> None:
        """路径来自模型,而这个工具会在真实桌面上开东西。"""
        reg = _registry(tmp_path)
        opened: list[str] = []
        reg._viewer_opener = opened.append

        res = reg.invoke("open_in_viewer", {"path": "../../../etc/passwd"})

        assert not res.success
        assert not opened

    def test_refuses_missing_path(self, tmp_path: Path) -> None:
        reg = _registry(tmp_path)
        reg._viewer_opener = lambda _p: None
        res = reg.invoke("open_in_viewer", {"path": "nope.json"})
        assert not res.success
        assert "Nothing to open" in (res.error or "")

    def test_opener_failure_is_reported_not_raised(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("x", encoding="utf-8")
        reg = _registry(tmp_path)

        def _boom(_p: str) -> None:
            raise RuntimeError("no display")

        reg._viewer_opener = _boom
        res = reg.invoke("open_in_viewer", {"path": "a.md"})
        assert not res.success
        assert "no display" in (res.error or "")


class TestOpenInViewerVaultRoute:
    """`vault/` 的观看器是 Obsidian,不是 Finder:agent 开 vault 里的东西时走
    `obsidian.open_vault`,而且**绝不**从工具调用里重启用户的 Obsidian。"""

    @staticmethod
    def _vault(root: Path) -> Path:
        v = root / "vault"
        (v / "角色").mkdir(parents=True)
        (v / "世界.canvas").write_text("{}", encoding="utf-8")
        (v / "角色" / "罗文.md").write_text("# 罗文", encoding="utf-8")
        return v

    @staticmethod
    def _capture(monkeypatch):
        calls: list[tuple] = []

        class _Report:
            def lines(self):
                return ["已打开。"]

        monkeypatch.setattr(
            "neonrp.core.obsidian.open_vault", lambda d, **k: calls.append((d, k)) or _Report()
        )
        return calls

    def test_vault_root_opens_in_obsidian(self, tmp_path: Path, monkeypatch) -> None:
        v = self._vault(tmp_path)
        calls = self._capture(monkeypatch)
        monkeypatch.setattr("webbrowser.open", lambda *_a, **_k: pytest.fail("Finder 不是 vault 的观看器"))
        reg = _registry(tmp_path)
        reg._viewer_opener = None

        res = reg.invoke("open_in_viewer", {"path": "vault"})

        assert res.success, res.error
        assert calls == [(v.resolve(), {"restart": False})]
        assert res.data["note"] == "已打开。"

    def test_file_inside_vault_lands_on_that_note(self, tmp_path: Path, monkeypatch) -> None:
        self._vault(tmp_path)
        calls = self._capture(monkeypatch)
        reg = _registry(tmp_path)
        reg._viewer_opener = None

        res = reg.invoke("open_in_viewer", {"path": "vault/角色/罗文.md"})

        assert res.success, res.error
        assert calls[0][1] == {"restart": False, "land_on": "角色/罗文.md"}

    def test_non_vault_paths_do_not_touch_obsidian(self, tmp_path: Path, monkeypatch) -> None:
        self._vault(tmp_path)
        (tmp_path / "vaulty.md").write_text("x", encoding="utf-8")  # 前缀相同,不是 vault 里的
        calls = self._capture(monkeypatch)
        opened: list[str] = []
        monkeypatch.setattr("webbrowser.open", lambda uri: opened.append(uri))
        reg = _registry(tmp_path)
        reg._viewer_opener = None

        res = reg.invoke("open_in_viewer", {"path": "vaulty.md"})

        assert res.success, res.error
        assert not calls and opened

    def test_obsidian_failure_is_reported_not_raised(self, tmp_path: Path, monkeypatch) -> None:
        self._vault(tmp_path)
        monkeypatch.setattr(
            "neonrp.core.obsidian.open_vault", lambda *a, **k: (_ for _ in ()).throw(OSError("no obsidian"))
        )
        reg = _registry(tmp_path)
        reg._viewer_opener = None
        res = reg.invoke("open_in_viewer", {"path": "vault"})
        assert not res.success
        assert "no obsidian" in (res.error or "")


# ── 工具面暴露 ──────────────────────────────────────────────


class TestObservabilityToolExposure:
    def test_viewer_is_build_only(self, tmp_path: Path) -> None:
        from neonrp.core.conversation import _get_tool_schemas
        from neonrp.core.skill_loader import SkillLoader

        loader = SkillLoader(root=tmp_path)
        build = {s["name"] for s in _get_tool_schemas("build", loader, tmp_path)}
        play = {s["name"] for s in _get_tool_schemas("play", loader, tmp_path)}

        assert "open_in_viewer" in build
        # 游玩中途在玩家桌面上弹窗口不是玩法,是打扰。
        assert "open_in_viewer" not in play


def test_tool_card_renders_a_diff_block() -> None:
    """TUI 展开写盘卡时,看到的应是 diff,而不是转义过的 JSON。"""
    from neonrp.tui.app import ConversationView

    raw = json.dumps(
        {
            "status": "success",
            "data": {
                "change": {
                    "path": "souls/luowen/soul.json",
                    "kind": "modified",
                    "headline": "modified +1 -1",
                    "preview": "-old\n+new",
                    "truncated": False,
                }
            },
        }
    )

    block = ConversationView._change_diff_block(raw)

    assert "```diff" in block
    assert "+new" in block
    assert "souls/luowen/soul.json" in block


def test_tool_card_survives_a_result_without_change() -> None:
    from neonrp.tui.app import ConversationView

    assert ConversationView._change_diff_block(None) == ""
    assert ConversationView._change_diff_block("not json") == ""
    assert ConversationView._change_diff_block('{"status":"success"}') == ""
