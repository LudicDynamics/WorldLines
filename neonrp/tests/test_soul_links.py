"""角色库独立 · 世界里只放 link:
「角色在世界里面其实就是 link 就好 —— 实体化是要在实际进入游戏 template 的时候才会实体化」。

模板的角色行写 {"lib": "<角色库里的名字>"};作者 op `set_cast` 写这张表;开局 build 时才把角色复制进这一局;
`bindings_of` 从角色反查它在哪些模板里(角色页的「在哪些世界里」)。"""

from __future__ import annotations

import json
import shutil

import pytest

from _paths import PRODUCT_TEMPLATES

SOUL_SRC = PRODUCT_TEMPLATES / "pct-house.template" / "world" / "souls" / "chara-si-chara0001"


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = tmp_path / "mine"
    store.mkdir()
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-mine.template")
    p = store / "pct-mine.template" / "template.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["id"] = "pct-mine"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    lib = tmp_path / "souls"
    shutil.copytree(SOUL_SRC, lib / "mira")
    sj = json.loads((lib / "mira" / "soul.json").read_text(encoding="utf-8"))
    sj["sid"] = "mira"
    (lib / "mira" / "soul.json").write_text(json.dumps(sj, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("neonrp.core.souls.SOUL_HOME", lib)
    return store, lib


def test_set_cast_links_a_library_soul_and_build_materializes_it(env, tmp_path):
    from neonrp import template as TP
    from neonrp.template import author

    store, lib = env
    r = author.apply_ops(store / "pct-mine.template", [{"op": "set_cast", "souls": [{"sid": "chara", "role": "npc"}, {"lib": "mira", "role": "companion"}]}])
    assert r["ok"], r
    t = TP.load(store / "pct-mine.template")
    assert {"lib": "mira", "role": "companion", "sid": "mira"} in t.souls        # 只是 link:sid 从角色库读来
    assert not (store / "pct-mine.template" / "souls").exists()                   # 模板里没有复制
    assert not [p for p in r["lint"].get("problems", []) if p.get("code") == "ref.soul"]

    out = TP.build(t, tmp_path / "run")                                           # 开局才实体化
    assert "mira" in out["souls"]
    pt = json.loads((tmp_path / "run" / "playthrough.json").read_text(encoding="utf-8"))
    row = next(x for x in pt["souls"] if x["sid"] == "mira")
    assert row["role"] == "companion"
    assert (tmp_path / "run" / "souls" / f"mira-{row['instance_id']}" / "soul.json").is_file()

    (lib / "mira" / "soul.md").write_text("改过的本体\n", encoding="utf-8")         # 角色库改了:下一局拿到新的
    TP.build(TP.load(store / "pct-mine.template"), tmp_path / "run2")
    assert (tmp_path / "run2" / "souls" / f"mira-{row['instance_id']}" / "soul.md").read_text(encoding="utf-8") == "改过的本体\n"


def test_bindings_of_finds_every_template_linking_the_soul(env):
    from neonrp import template as TP
    from neonrp.template import author

    store, _ = env
    assert TP.bindings_of("mira") == []
    author.apply_ops(store / "pct-mine.template", [{"op": "set_cast", "souls": [{"sid": "chara"}, {"pool": [{"lib": "mira"}, {"sid": "x"}], "pick": 1}]}])
    b = TP.bindings_of("mira")
    assert [(x["template"], x["sid"], x["pool"]) for x in b] == [("pct-mine", "mira", True)]


@pytest.mark.parametrize("rows,why", [
    ([{"lib": "nobody"}], "no soul 'nobody'"),
    ([{"lib": "../etc"}], "no soul"),
    ([{"sid": "chara"}, {"sid": "chara"}], "cast twice"),
    ([{"sid": "chara", "role": "boss"}], "role is"),
    ([{"lib": "mira", "role": "player"}, {"sid": "chara", "role": "player"}], "only one player"),
])
def test_set_cast_refuses_bad_rows_and_writes_nothing(env, rows, why):
    from neonrp.template import author

    store, _ = env
    before = (store / "pct-mine.template" / "template.json").read_text(encoding="utf-8")
    r = author.apply_ops(store / "pct-mine.template", [{"op": "set_cast", "souls": rows}])
    assert not r["ok"] and why in r["refused"][0]["why"], r
    assert (store / "pct-mine.template" / "template.json").read_text(encoding="utf-8") == before


def test_two_new_runs_in_the_same_second_never_share_a_dir(tmp_path, monkeypatch):
    """10-08:同一秒开两局曾共用一个文件夹 —— 第二局建失败,清理时把第一局(正在玩的)删了。"""
    from neonrp import worlds

    monkeypatch.setattr(worlds, "PLAYS_HOME", tmp_path / "plays")
    a = worlds.create_run_dir("tpl-x")
    (a / "keep.txt").write_text("正在玩", encoding="utf-8")
    b = worlds.create_run_dir("tpl-x")
    assert a != b and b.is_dir() and not any(b.iterdir())
    assert (a / "keep.txt").read_text(encoding="utf-8") == "正在玩"
    import re

    assert re.search(r"-\d{8}-\d{6}$", b.name)                                 # 名字格式不变(别处按它切世界 id)
