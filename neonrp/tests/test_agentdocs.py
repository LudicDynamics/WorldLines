"""spec 放进文件夹里(「在里面添加就好,不要在外面读 —— spec 也是要给 Claude 和 Codex 其他 agent 读的」)。
每个模板文件夹、模板库、角色库都带 AGENTS.md / CLAUDE.md / spec/;复制模板、导入包时自动写;仓库里的模板必须是最新的。"""

from __future__ import annotations

import json
import shutil

import pytest

from _paths import PRODUCT_TEMPLATES


def test_repo_templates_carry_current_specs():
    from neonrp import template as TP
    from neonrp.template import agentdocs

    for tdir in sorted(PRODUCT_TEMPLATES.glob("*.template")):
        t = TP.load(tdir)
        for rel, text in agentdocs.files_for_template(t).items():
            p = tdir / rel
            assert p.is_file() and p.read_text(encoding="utf-8") == text, (
                f"{tdir.name}/{rel} is stale — run: neonrp spec sync worldlines/templates/*.template")
        assert "/Users/" not in (tdir / "AGENTS.md").read_text(encoding="utf-8")


def test_specs_do_not_change_lint_or_the_run(tmp_path):
    from neonrp import template as TP

    t = TP.load(PRODUCT_TEMPLATES / "pct-house.template")
    assert not [p for p in TP.lint(t)["problems"] if "spec" in str(p.get("where")) or "AGENTS" in str(p.get("where"))]
    TP.build(t, tmp_path / "run")
    assert not (tmp_path / "run" / "AGENTS.md").exists() and not (tmp_path / "run" / "spec").exists()


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = tmp_path / "store"
    s.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(s))
    monkeypatch.setattr("neonrp.core.souls.SOUL_HOME", tmp_path / "souls")
    return s


def test_fork_and_import_write_the_agent_files(store, tmp_path):
    from neonrp.template import author
    from neonrp.template import package as P

    t = author.fork(PRODUCT_TEMPLATES / "stoneford-elena.template", "elena-x")
    for f in ("AGENTS.md", "CLAUDE.md", "spec/template.md", "spec/ops.md", "spec/contract.md"):
        assert (t.dir / f).is_file(), f
    assert "elena-x.template" in (t.dir / "AGENTS.md").read_text(encoding="utf-8")
    assert (store / "AGENTS.md").is_file() and (store / "spec" / "template.md").is_file()

    (t.dir / "spec" / "template.md").write_text("old engine's spec", encoding="utf-8")
    r = P.import_package(P.export_template("elena-x"), new_id="elena-y")
    got = store / f"{r['id']}.template" / "spec" / "template.md"
    assert got.read_text(encoding="utf-8").startswith("# Template")          # 导入后换成这台引擎的 spec


def test_own_agents_md_is_never_overwritten(store):
    from neonrp.template import agentdocs, author

    t = author.fork(PRODUCT_TEMPLATES / "stoneford-elena.template", "elena-own")
    (t.dir / "AGENTS.md").write_text("# my own notes\n", encoding="utf-8")
    agentdocs.write_template(t)
    assert (t.dir / "AGENTS.md").read_text(encoding="utf-8") == "# my own notes\n"
    assert (t.dir / "CLAUDE.md").read_text(encoding="utf-8").startswith(agentdocs.MARK)


def test_library_gets_its_files_and_still_lists_only_souls(store, tmp_path):
    from neonrp.core import souls
    from neonrp.template import agentdocs

    lib = tmp_path / "souls"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template" / "world" / "souls" / "chara-si-chara0001", lib / "mira")
    agentdocs.write_library(lib)
    assert (lib / "AGENTS.md").is_file() and (lib / "spec" / "soul.md").is_file()
    assert [s["dir_name"] for s in souls.list_souls()] == ["mira"]
    json.loads((lib / "mira" / "soul.json").read_text(encoding="utf-8"))
