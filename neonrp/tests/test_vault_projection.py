"""M31 · Obsidian vault 投影 —— 把引擎记录变成能看的世界。

我们 file-first,但文件是引擎的账:一个起手世界 82 个 JSON 对 28 个 MD,
Obsidian 打开是一坨死文本。投影器补的就是这一层。

读者是**上帝视角的观察者**:谁在哪、什么关系、世界怎么
演化。所以这里的断言围绕三件事——链接必须活(否则图谱是散点)、位置必须
解析(soul 站的是导航节点,和地点实体不是一套 id)、用户区必须不可侵犯
(否则 Obsidian 唯一不可替代的价值就没了)。
"""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.vault import USER_NOTES_DIRNAME, project_vault


def _world(tmp_path: Path) -> Path:
    """一个有镇、有地点、有两个 soul 的小世界。"""
    root = tmp_path / "w"
    game = root / "game"
    (game / "meta").mkdir(parents=True)
    (game / "meta" / "run_state.json").write_text(
        json.dumps(
            {
                "location": {"scope": "town", "node": "gate_north", "display": "石津镇·北门"},
                "time": {"day": 3, "clock": "18:20"},
                "turn_count": 7,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (game / "world").mkdir(parents=True)
    (game / "world" / "world_map.json").write_text(
        json.dumps(
            {"name": "灰雾北境", "nodes": [{"id": "T004", "name": "碧石镇"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    locs = game / "locations"
    locs.mkdir(parents=True)
    (locs / "north-gate.json").write_text(
        json.dumps(
            {
                "id": "north-gate",
                "kind": "location",
                "name": "石津镇·北门",
                "tags": ["town", "gate"],
                "summary": "风从北边灌进来。",
                "connections": ["market-square"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (locs / "market-square.json").write_text(
        json.dumps(
            {
                "id": "market-square",
                "kind": "location",
                "name": "石津镇·集市广场",
                "summary": "湿布盖着的摊位。",
                "connections": ["north-gate"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _soul(root, "elena", "艾琳娜", location="gate_north", mood="alert")
    _soul(root, "rowan", "罗文", location="T004", mood="restless")
    return root


def _soul(root: Path, sid: str, name: str, *, location: str, mood: str) -> Path:
    d = root / "souls" / f"{sid}-si-{sid}0001"
    (d / "persona").mkdir(parents=True)
    (d / "background").mkdir(parents=True)
    (d / "soul.json").write_text(
        json.dumps({"sid": sid, "name": sid, "name_local": name}, ensure_ascii=False),
        encoding="utf-8",
    )
    (d / "run_state.json").write_text(
        json.dumps(
            {"sid": sid, "location": location, "status": {"mood": mood, "hp": 24, "max_hp": 24}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (d / "soul.md").write_text(f"# {name} 的宪章\n\n她话不多。\n", encoding="utf-8")
    (d / "background" / "origin.md").write_text("# 出身\n\n来自北边。\n", encoding="utf-8")
    return d


class TestProjectionShape:
    def test_projects_the_three_generated_areas(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        report = project_vault(root)

        assert report.changed
        vault = root / "vault"
        assert (vault / "世界.md").is_file()
        assert (vault / "角色" / "艾琳娜.md").is_file()
        assert (vault / "地点" / "石津镇·北门.md").is_file()

    def test_second_run_writes_nothing(self, tmp_path: Path) -> None:
        """幂等:内容没变就别碰文件——否则 Obsidian 每回合闪一次。"""
        root = _world(tmp_path)
        project_vault(root)

        again = project_vault(root)

        assert again.written == []
        assert again.unchanged > 0

    def test_notes_carry_frontmatter_and_a_single_title(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        project_vault(root)
        text = (root / "vault" / "角色" / "艾琳娜.md").read_text(encoding="utf-8")

        assert text.startswith("---\n")
        assert "kind: soul" in text
        # 嵌进来的宪章自带 #,不降级就会出现两个 H1。
        assert len([ln for ln in text.splitlines() if ln.startswith("# ")]) == 1


class TestTheGraphIsAlive:
    def test_location_connections_become_links(self, tmp_path: Path) -> None:
        """`connections` 本来就是图,投影只是把它写成 [[链接]]。"""
        root = _world(tmp_path)
        project_vault(root)
        text = (root / "vault" / "地点" / "石津镇·北门.md").read_text(encoding="utf-8")

        assert "[[石津镇·集市广场]]" in text

    def test_soul_location_resolves_across_id_spaces(self, tmp_path: Path) -> None:
        """soul 站在 `gate_north`,地点实体叫 `north-gate` —— 不归一就是死链。"""
        root = _world(tmp_path)
        project_vault(root)
        text = (root / "vault" / "角色" / "艾琳娜.md").read_text(encoding="utf-8")

        assert "[[石津镇·北门]]" in text
        assert "gate_north" not in text.split("---")[2]  # 正文里不该出现裸节点 id

    def test_town_node_resolves_through_world_map(self, tmp_path: Path) -> None:
        """罗文站在 T004 —— 名字只有 world_map 知道。"""
        root = _world(tmp_path)
        project_vault(root)
        text = (root / "vault" / "角色" / "罗文.md").read_text(encoding="utf-8")

        assert "碧石镇" in text
        assert "T004" not in text.split("---")[2]

    def test_location_page_lists_who_is_there(self, tmp_path: Path) -> None:
        """上帝视角的核心一格:这个地方现在有谁。"""
        root = _world(tmp_path)
        project_vault(root)
        text = (root / "vault" / "地点" / "石津镇·北门.md").read_text(encoding="utf-8")

        assert "[[艾琳娜]]" in text

    def test_index_shows_the_world_moving(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        project_vault(root)
        text = (root / "vault" / "世界.md").read_text(encoding="utf-8")

        assert "灰雾北境" in text
        assert "第 3 天 18:20" in text
        assert "[[艾琳娜]]" in text and "alert" in text


class TestOwnershipBoundary:
    def test_user_notes_are_never_touched(self, tmp_path: Path) -> None:
        """这条守不住,Obsidian 唯一不可替代的价值就没了。"""
        root = _world(tmp_path)
        project_vault(root)
        mine = root / "vault" / USER_NOTES_DIRNAME / "我对艾琳娜的看法.md"
        mine.write_text("她在撒谎。[[艾琳娜]]\n", encoding="utf-8")

        report = project_vault(root)

        assert mine.read_text(encoding="utf-8") == "她在撒谎。[[艾琳娜]]\n"
        assert all(USER_NOTES_DIRNAME not in rel for rel in report.written + report.removed)

    def test_stale_generated_notes_are_pruned(self, tmp_path: Path) -> None:
        """角色改名/地点删除后,旧页不该留在图谱里当孤儿。"""
        root = _world(tmp_path)
        project_vault(root)
        assert (root / "vault" / "地点" / "石津镇·集市广场.md").is_file()

        (root / "game" / "locations" / "market-square.json").unlink()
        report = project_vault(root)

        assert not (root / "vault" / "地点" / "石津镇·集市广场.md").exists()
        assert any("集市广场" in rel for rel in report.removed)

    def test_pruning_never_reaches_outside_generated_dirs(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        project_vault(root)
        stray = root / "vault" / USER_NOTES_DIRNAME / "旧笔记.md"
        stray.write_text("留着", encoding="utf-8")
        # 伪造一条指向用户区的历史记录:投影器也必须拒绝删它。
        idx = root / "vault" / ".projection.json"
        data = json.loads(idx.read_text(encoding="utf-8"))
        data["notes"]["bogus"] = f"{USER_NOTES_DIRNAME}/旧笔记.md"
        idx.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        project_vault(root)

        assert stray.is_file()


class TestRobustness:
    def test_empty_world_does_not_raise(self, tmp_path: Path) -> None:
        """投影绝不能把回合带崩(与 story.md 同一纪律)。"""
        report = project_vault(tmp_path / "nothing-here")
        assert report.written == [] or report.written

    def test_broken_json_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        (root / "game" / "locations" / "broken.json").write_text("{not json", encoding="utf-8")

        report = project_vault(root)

        assert report.changed
        assert (root / "vault" / "角色" / "艾琳娜.md").is_file()

    def test_unsafe_names_do_not_escape_the_vault(self, tmp_path: Path) -> None:
        """名字是作者写的,可能带 / 或 .. —— 不能变成路径。"""
        root = _world(tmp_path)
        (root / "game" / "locations" / "odd.json").write_text(
            json.dumps(
                {"id": "odd", "kind": "location", "name": "../../逃逸/坏名字"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        project_vault(root)

        assert not (tmp_path / "逃逸").exists()
        assert any(p.name.startswith("....") or "逃逸" in p.name
                   for p in (root / "vault" / "地点").iterdir())


class TestFrontmatterRules:
    """世界自己规定 frontmatter 写什么。

    frontmatter 是 Obsidian 唯一能查询/排序/过滤的部分,所以它属于世界的
    本体论——CoC 要理智值,潜入本要警戒度。引擎给默认值然后让开。
    """

    def _rules(self, root: Path, rules: dict) -> None:
        (root / ".neonrp").mkdir(parents=True, exist_ok=True)
        (root / ".neonrp" / "vault.json").write_text(
            json.dumps({"frontmatter": rules}, ensure_ascii=False), encoding="utf-8"
        )

    def test_defaults_apply_with_no_config(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        project_vault(root)
        text = (root / "vault" / "角色" / "艾琳娜.md").read_text(encoding="utf-8")
        assert "所在: 石津镇·北门" in text
        assert "心情: alert" in text

    def test_world_can_rename_and_choose_fields(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        self._rules(root, {"soul": {"现在在": "@location", "本名": "identity.name"}})

        project_vault(root)

        text = (root / "vault" / "角色" / "艾琳娜.md").read_text(encoding="utf-8")
        assert "现在在: 石津镇·北门" in text
        assert "本名: elena" in text
        # 该 kind 的规则是整体替换,不是逐条合并——没写的就不出现。
        assert "心情:" not in text

    def test_dotted_paths_reach_nested_records(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        self._rules(root, {"soul": {"血量": "run_state.status.hp"}})

        project_vault(root)

        assert "血量: 24" in (root / "vault" / "角色" / "艾琳娜.md").read_text(encoding="utf-8")

    def test_missing_field_thins_the_note_instead_of_breaking_it(
        self, tmp_path: Path
    ) -> None:
        """世界写了它没有的属性,应该少一行,而不是坏一页。"""
        root = _world(tmp_path)
        self._rules(root, {"soul": {"理智": "status.sanity", "心情": "@mood"}})

        project_vault(root)

        text = (root / "vault" / "角色" / "艾琳娜.md").read_text(encoding="utf-8")
        assert "理智" not in text
        assert "心情: alert" in text
        assert text.startswith("---\n")

    def test_computed_present_lands_on_location_pages(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        self._rules(root, {"location": {"有谁": "@present"}})

        project_vault(root)

        text = (root / "vault" / "地点" / "石津镇·北门.md").read_text(encoding="utf-8")
        assert "有谁: [艾琳娜]" in text

    def test_bare_list_form_lifts_source_keys(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        self._rules(root, {"location": ["tags", "summary"]})

        project_vault(root)

        text = (root / "vault" / "地点" / "石津镇·北门.md").read_text(encoding="utf-8")
        assert "tags: [town, gate]" in text
        assert "summary: 风从北边灌进来。" in text

    def test_identity_keys_are_engine_owned(self, tmp_path: Path) -> None:
        """id/kind/aliases 是投影器自己用来解析链接的,世界规则不该能删掉。"""
        root = _world(tmp_path)
        self._rules(root, {"soul": {}})

        project_vault(root)

        text = (root / "vault" / "角色" / "艾琳娜.md").read_text(encoding="utf-8")
        assert "id: elena" in text
        assert "kind: soul" in text

    def test_broken_config_falls_back_to_defaults(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        (root / ".neonrp").mkdir(parents=True, exist_ok=True)
        (root / ".neonrp" / "vault.json").write_text("{not json", encoding="utf-8")

        project_vault(root)

        assert "所在: 石津镇·北门" in (
            root / "vault" / "角色" / "艾琳娜.md"
        ).read_text(encoding="utf-8")

    def test_config_template_never_clobbers(self, tmp_path: Path) -> None:
        from neonrp.core.vault import write_config_template

        root = _world(tmp_path)
        self._rules(root, {"soul": {"我的": "@mood"}})

        write_config_template(root)

        data = json.loads((root / ".neonrp" / "vault.json").read_text(encoding="utf-8"))
        assert data["frontmatter"]["soul"] == {"我的": "@mood"}


def test_two_towns_with_the_same_local_place_id_get_two_notes(tmp_path: Path) -> None:
    """10-06 (system test): folder-form ids are local to their town — 石津镇 and 碧石镇 both have `shop_general`.
    Keyed by bare id, both notes landed in one file and every projection rewrote it (never settled). Keyed by address:
    two notes, each linking to its own town's street, and a second projection changes nothing."""
    import shutil
    from collections import Counter

    root = tmp_path / "w"
    shutil.copytree(Path(__file__).resolve().parents[1] / "src" / "neonrp" / "templates" / "stoneford-elena", root)
    first = project_vault(root)
    assert not [k for k, v in Counter(first.written).items() if v > 1]
    names = {p.name for p in (root / "vault" / "地点").glob("*.md")}
    assert {"杂货铺.md", "石锤杂货铺.md"} <= names
    assert "[[主街]]" in (root / "vault" / "地点" / "杂货铺.md").read_text(encoding="utf-8")
    assert "[[矿工大道]]" in (root / "vault" / "地点" / "石锤杂货铺.md").read_text(encoding="utf-8")
    assert not project_vault(root).changed
