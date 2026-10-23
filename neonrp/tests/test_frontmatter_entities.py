"""带 frontmatter 的 Markdown 作为一等实体(见 docs/DATA-FORMAT.md)。

世界的实质是散文加上几个可被查询的事实。frontmatter 放事实、正文放散文,
同一个文件既给人读也给机器索引——不必再维护「给人看的 md」和「给机器读的
json」两份。

这里钉四件:
- **解析器的边界**:覆盖 Obsidian 自己写属性的形态,不引 pyyaml
- **修复/拒绝**:能确定性修的修,修不了的报错要**指出哪一行**,绝不静默吞
- **冲突规则**:同 id 时 md 赢,而且**必须告警**——两份真相是这次迁移最大的隐患
- **安全回归**:`game/secrets/**` 下的 md 同样不进索引,否则换个格式就绕开了保密
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core.frontmatter import FrontmatterError, parse, render
from neonrp.core.indexing import scan_entities


# ── 解析器 ────────────────────────────────────────────────


class TestParsesWhatObsidianWrites:
    def test_scalars_lists_and_types(self) -> None:
        doc = parse(
            "---\n"
            "id: luowen\n"
            "kind: soul\n"
            "aliases: [luowen, 罗文]\n"
            "tags:\n"
            "  - smith\n"
            "  - taciturn\n"
            "turn: 7\n"
            "active: true\n"
            "---\n"
            "\n沉默寡言的铁匠。\n"
        )

        assert doc.fields["id"] == "luowen"
        assert doc.fields["aliases"] == ["luowen", "罗文"]
        assert doc.fields["tags"] == ["smith", "taciturn"]
        assert doc.fields["turn"] == 7
        assert doc.fields["active"] is True
        assert doc.body == "沉默寡言的铁匠。"

    def test_quoted_value_keeps_its_colon(self) -> None:
        """地名里带冒号是常态,引号必须能保住它。"""
        doc = parse('---\n所在: "石津镇:北门"\n---\n')
        assert doc.fields["所在"] == "石津镇:北门"

    def test_a_note_without_frontmatter_is_prose(self) -> None:
        doc = parse("# 只是一段笔记\n\n没有 frontmatter。\n")
        assert doc.fields == {}
        assert not doc.is_entity
        assert "只是一段笔记" in doc.body

    def test_entity_needs_id_and_kind(self) -> None:
        assert parse("---\nid: x\nkind: item\n---\n").is_entity
        assert not parse("---\nname: 无名\n---\n").is_entity

    def test_round_trip(self) -> None:
        fields = {"id": "x", "kind": "item", "tags": ["a", "b"], "n": 3}
        doc = parse(render(fields, "正文"))
        assert doc.fields == fields
        assert doc.body == "正文"


class TestRepairBoundary:
    """模型写坏 frontmatter 和写坏 JSON 是同一类问题,得有同一类边界。"""

    def test_fullwidth_colon_in_a_key_is_healed(self) -> None:
        doc = parse("---\nid：luowen\nkind: soul\n---\n")
        assert doc.fields["id"] == "luowen"
        assert doc.repaired

    def test_missing_closing_fence_is_inferred_when_unambiguous(self) -> None:
        doc = parse("---\nid: x\nkind: item\n\n正文在这里。\n")
        assert doc.fields["id"] == "x"
        assert any("结束" in r for r in doc.repaired)

    def test_unrepairable_input_names_the_line(self) -> None:
        with pytest.raises(FrontmatterError) as ei:
            parse("---\nid: x\n这一行看不懂\nkind: item\n---\n")
        assert "第 3 行" in str(ei.value)

    def test_nested_structure_is_refused_with_a_pointer(self) -> None:
        """纯结构的数据该留在 JSON 里,不该半解析成一个说不清的东西。"""
        with pytest.raises(FrontmatterError) as ei:
            parse("---\nid: x\nstats: {hp: 10}\n---\n")
        assert "DATA-FORMAT" in str(ei.value)

    def test_a_list_item_without_a_key_is_refused(self) -> None:
        with pytest.raises(FrontmatterError):
            parse("---\n  - 孤儿项\n---\n")


# ── 索引 ──────────────────────────────────────────────────


def _world(tmp_path: Path) -> Path:
    # 目录名与 kind 一致(game/<kind>/<id>.<ext>)——既有的布局约定,
    # 这里对齐它,好让用例只在测 md 与 json 的差别。
    (tmp_path / "game" / "location").mkdir(parents=True)
    return tmp_path


def _json_entity(root: Path, rel: str, **fields) -> None:
    path = root / "game" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")


def _md_entity(root: Path, rel: str, body: str = "", **fields) -> None:
    path = root / "game" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(fields, body), encoding="utf-8")


class TestMarkdownEntitiesAreFirstClass:
    def test_a_pure_markdown_world_indexes(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        _md_entity(
            root, "location/north-gate.md", "风从北边灌进来。",
            id="north-gate", kind="location", name="石津镇·北门", tags=["town"],
        )

        records, warnings = scan_entities(root)

        assert [r.id for r in records] == ["north-gate"]
        assert records[0].name == "石津镇·北门"
        assert records[0].tags == ["town"]
        assert not warnings

    def test_body_becomes_the_summary_when_none_given(self, tmp_path: Path) -> None:
        """散文本来就是摘要,不必再让作者写一遍。"""
        root = _world(tmp_path)
        _md_entity(root, "location/a.md", "湿布盖着的摊位。", id="a", kind="location", name="集市")

        records, _ = scan_entities(root)

        assert records[0].summary == "湿布盖着的摊位。"

    def test_json_and_markdown_coexist(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        _json_entity(root, "location/a.json", id="a", kind="location", name="旧格式")
        _md_entity(root, "location/b.md", id="b", kind="location", name="新格式")

        records, warnings = scan_entities(root)

        assert {r.id for r in records} == {"a", "b"}
        assert not warnings

    def test_prose_without_id_is_skipped_quietly(self, tmp_path: Path) -> None:
        """vault 里会有大量人写的笔记,它们不是实体,也不该刷警告。"""
        root = _world(tmp_path)
        (root / "game" / "lore" ).mkdir(parents=True, exist_ok=True)
        (root / "game" / "lore" / "notes.md").write_text("# 随手记\n\n没有属性。\n", encoding="utf-8")

        records, warnings = scan_entities(root)

        assert records == []
        assert not warnings


class TestConflictRule:
    def test_markdown_wins_and_says_so(self, tmp_path: Path) -> None:
        """迁移中同一个 id 会短暂存在于两种格式。规则必须**可见**地解决。"""
        root = _world(tmp_path)
        _json_entity(root, "location/a.json", id="a", kind="location", name="旧的")
        _md_entity(root, "location/a.md", id="a", kind="location", name="新的")

        records, warnings = scan_entities(root)

        assert [r.name for r in records] == ["新的"]
        assert any(w.code == "format-collision" for w in warnings)

    def test_two_json_entities_with_one_id_are_still_a_duplicate(
        self, tmp_path: Path
    ) -> None:
        """冲突规则只为跨格式迁移开口子,不是把重复 id 合法化了。"""
        root = _world(tmp_path)
        _json_entity(root, "location/a.json", id="a", kind="location", name="一")
        _json_entity(root, "location/b.json", id="a", kind="location", name="二")

        _records, warnings = scan_entities(root)

        assert warnings


class TestSecretsStayShut:
    def test_markdown_secrets_never_enter_the_index(self, tmp_path: Path) -> None:
        """换个格式就绕开保密,是这次迁移最容易犯的错。"""
        root = _world(tmp_path)
        _md_entity(
            root, "secrets/twist.md", "她其实记得一切。",
            id="twist", kind="secret", name="真相",
        )

        records, _ = scan_entities(root)

        assert records == []


class TestBrokenFilesAreReported:
    def test_bad_frontmatter_becomes_a_warning_not_a_crash(self, tmp_path: Path) -> None:
        root = _world(tmp_path)
        (root / "game" / "location" / "bad.md").write_text(
            "---\nid: x\n看不懂的一行\n---\n", encoding="utf-8"
        )
        _md_entity(root, "location/ok.md", id="ok", kind="location", name="好的")

        records, warnings = scan_entities(root)

        assert [r.id for r in records] == ["ok"]
        assert any(w.code == "frontmatter" for w in warnings)
        assert any("第 3 行" in w.message for w in warnings)
