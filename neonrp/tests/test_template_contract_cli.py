"""原生捏模板 ↔ 合约(「默认原生能够捏这个 template 的对应」):
`set_play_contract` 创作 op(网页 / 命令行共用)+ `neonrp template contracts | fork | set-contract`。"""

from __future__ import annotations

import json
import shutil

import pytest
from click.testing import CliRunner

from _paths import PRODUCT_TEMPLATES
from neonrp.commands.template_cmd import template_group


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = tmp_path / "mine"
    s.mkdir()
    shutil.copytree(PRODUCT_TEMPLATES / "stoneford-elena.template", s / "elena-mine.template")
    d = json.loads((s / "elena-mine.template" / "template.json").read_text(encoding="utf-8"))
    d["id"] = "elena-mine"
    (s / "elena-mine.template" / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(s))
    return s


def test_op_sets_verifies_and_clears_the_contract(store):
    from neonrp.template import author, load

    r = author.apply_ops(store / "elena-mine.template", [{"op": "set_play_contract", "contract": "romance-companion"}])
    assert r["ok"] and r["applied"][0]["to"] == "romance-companion@1", "没写版本就补上合约文件里的版本"
    assert load(store / "elena-mine.template").play_contract == "romance-companion@1"
    assert any(p["code"].startswith("contract") for p in r["lint"]["problems"]) or r["lint"]["publishable"]
    bad = author.apply_ops(store / "elena-mine.template", [{"op": "set_play_contract", "contract": "nope"}])
    assert not bad["ok"] and "unknown play contract" in bad["refused"][0]["why"]
    assert load(store / "elena-mine.template").play_contract == "romance-companion@1", "全有或全无:拒了就不写"
    author.apply_ops(store / "elena-mine.template", [{"op": "set_play_contract", "contract": ""}])
    assert load(store / "elena-mine.template").play_contract == ""


def test_cli_contracts_lists_the_four_and_who_uses_them(store):
    r = CliRunner().invoke(template_group, ["contracts"])
    assert r.exit_code == 0, r.output
    for cid in ("mystery-trpg@1", "open-adventure@1", "murder-mystery@1", "romance-companion@1"):
        assert cid in r.output


def test_cli_fork_then_set_contract_and_builtins_stay_read_only(store, tmp_path):
    run = CliRunner()
    r = run.invoke(template_group, ["fork", "elena-mine", "elena-two", "--store", str(store)])
    assert r.exit_code == 0, r.output
    r = run.invoke(template_group, ["set-contract", "elena-two", "mystery-trpg@1", "--store", str(store)])
    assert r.exit_code == 0, r.output
    assert "→ mystery-trpg@1" in r.output and "block" in r.output       # 合约的检查直接变成 lint 结果
    r = run.invoke(template_group, ["set-contract", "stoneford-elena", "mystery-trpg"],
                   env={"NEONRP_TEMPLATE_PATH": str(PRODUCT_TEMPLATES), "NEONRP_TEMPLATE_WRITE_DIR": str(tmp_path / "elsewhere")})
    assert r.exit_code != 0 and "只读" in r.output
    r = run.invoke(template_group, ["list"])
    assert "mystery-trpg@1" in r.output
