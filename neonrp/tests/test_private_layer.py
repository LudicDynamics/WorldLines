"""10-08 open engine · private orchestration: Ludic Dynamics' own prompts / pack orchestration / contracts / templates
live in a separate private repo (``neonrp_private``) and are laid over the engine's public ones. Without it the engine
is the complete public one. These tests drive each seam with a throwaway private folder."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neonrp import prompts
from neonrp.core import orchestration
from neonrp.core.paths import private_dir


@pytest.fixture
def priv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "neonrp_private"
    d.mkdir()
    monkeypatch.setenv("NEONRP_PRIVATE_DIR", str(d))
    monkeypatch.delenv("NEONRP_PRIVATE", raising=False)
    monkeypatch.delenv("NEONRP_TEMPLATE_PATH", raising=False)  # the player's own store (forks) stays first; not tested here
    return d


def test_no_private_layer_is_the_public_engine(monkeypatch: pytest.MonkeyPatch, priv: Path):
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    assert private_dir() is None and private_dir("prompts") is None


def test_private_prompt_wins_and_tables_merge_key_by_key(priv: Path):
    (priv / "prompts").mkdir()
    (priv / "prompts" / "narrate.zh.md").write_text("我们的叙事提示词\n", encoding="utf-8")
    (priv / "prompts" / "adv.zh.json").write_text(json.dumps({"_LANG_RULE": "私有"}, ensure_ascii=False), encoding="utf-8")
    assert prompts.text("narrate", "zh") == "我们的叙事提示词"
    assert prompts.text("narrate", "en") != "我们的叙事提示词"  # a language the private layer lacks keeps the public one
    t = prompts.strings("adv", "zh")
    assert t["_LANG_RULE"] == "私有" and "_LANG_NAMES" in t  # untouched keys stay public


def test_off_switch_restores_public(monkeypatch: pytest.MonkeyPatch, priv: Path):
    public = prompts.text("narrate", "zh")
    (priv / "prompts").mkdir()
    (priv / "prompts" / "narrate.zh.md").write_text("我们的", encoding="utf-8")
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    assert prompts.text("narrate", "zh") == public


def test_private_pack_orchestration_and_layer_prompts(tmp_path: Path, priv: Path):
    from test_engine_v3 import _install

    from neonrp.core import modes

    root = _install(tmp_path / "run")
    before = {e["id"] for e in orchestration.default_graph(root)["edges"]}
    (priv / "packs" / "rpg" / "prompts").mkdir(parents=True)
    (priv / "packs" / "rpg" / "orchestration.json").write_text(json.dumps({
        "add": [{"id": "resolve>combat:ambush", "from": "resolve", "to": "combat", "on": {"tick": "ambush"}, "return": True}],
        "remove": [sorted(before)[0]]}), encoding="utf-8")
    after = {e["id"] for e in orchestration.default_graph(root)["edges"]}
    assert "resolve>combat:ambush" in after and sorted(before)[0] not in after
    assert modes._pack_prompt_dirs(root)[0] == priv / "packs" / "rpg" / "prompts"


def test_private_templates_come_first_and_contracts_are_not_copied(tmp_path: Path, priv: Path):
    from neonrp import template
    from neonrp.template import contract

    (priv / "contracts").mkdir()
    (priv / "templates").mkdir()
    assert priv / "contracts" not in contract.search_dirs()  # a contract lives once, in public; we only add its engine block
    dirs = template.search_dirs()
    pub = [d for d in dirs if d.name == "templates" and d.parent.name == "worldlines"]  # the shipped public ones
    assert priv / "templates" in dirs and (not pub or dirs.index(priv / "templates") < dirs.index(pub[0]))
    src = next(iter(template.discover().values()))
    shutil.copytree(src, priv / "templates" / src.name)
    assert template.discover()[next(k for k, v in template.discover().items() if v.name == src.name)].parent == priv / "templates"


def test_private_contract_engine_block_at_run_time_only(tmp_path: Path, priv: Path):
    """Our turn settings for a contract = only its engine block, laid over at run time; the save keeps the public one."""
    from test_engine_v3 import _install

    from neonrp.core import engine_config
    from neonrp.core.paths import get_data_dir_name

    root = _install(tmp_path / "run")
    meta = root / get_data_dir_name(root) / "meta" / "play_contract.json"
    meta.write_text(json.dumps({"schema": "worldlines.play-contract/1", "id": "mystery-trpg", "version": 1,
                                "engine": {"turn": {"plan_loop": "on"}}}), encoding="utf-8")
    assert engine_config.get(root, "turn.plan_loop") == "on"
    (priv / "contracts").mkdir()
    (priv / "contracts" / "mystery-trpg.engine.json").write_text(json.dumps({"turn": {"plan_loop": "off"}}), encoding="utf-8")
    assert engine_config.get(root, "turn.plan_loop") == "off"
    assert json.loads(meta.read_text(encoding="utf-8"))["engine"]["turn"]["plan_loop"] == "on"  # the save is untouched


def test_effective_graph_sees_the_private_patch(tmp_path: Path, priv: Path):
    from test_engine_v3 import _install

    root = _install(tmp_path / "run")
    orchestration.graph(root)  # warm the cache first
    (priv / "packs" / "rpg").mkdir(parents=True)
    (priv / "packs" / "rpg" / "orchestration.json").write_text(json.dumps(
        {"add": [{"id": "resolve>combat:ambush", "from": "resolve", "to": "combat", "on": {"tick": "ambush"}}]}), encoding="utf-8")
    assert "resolve>combat:ambush" in {e["id"] for e in orchestration.graph(root)["edges"]}


def test_private_folder_copied_into_the_shell_is_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The whole private folder can be copied into WorldLines; the engine finds it there."""
    import neonrp.core.paths as paths

    monkeypatch.delenv("NEONRP_PRIVATE_DIR", raising=False)
    monkeypatch.delenv("NEONRP_PRIVATE", raising=False)
    shell = tmp_path / "worldlines_shim"
    (shell / "private" / "prompts").mkdir(parents=True)
    monkeypatch.setattr(paths, "shell_dir", lambda sub: shell / sub if (shell / sub).is_dir() else None)
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a, **k: None)
    assert paths.private_dir("prompts") == shell / "private" / "prompts"


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "release" / "export.py").is_file(),
                    reason="the export tool lives in the development repo")
def test_export_refuses_our_private_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The export's hard guard: a private/ path, or a file with the same bytes as a private one, never goes public."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("export", Path(__file__).resolve().parents[1] / "release" / "export.py")
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)  # type: ignore[union-attr]
    priv = tmp_path / "neonrp_private"
    (priv / "prompts").mkdir(parents=True)
    secret = ("我们调过的叙事提示词 " * 10).encode()
    (priv / "prompts" / "narrate.zh.md").write_bytes(secret)
    staged = {"neonrp/src/neonrp/prompts/narrate.zh.md": secret, "worldlines/private/x.json": b"{}",
              "neonrp/README.md": b"public readme " * 10}
    leaks = {x["path"] for x in ex.private_leaks(staged, [priv])}
    assert leaks == {"neonrp/src/neonrp/prompts/narrate.zh.md", "worldlines/private/x.json"}
    man = ex.tomllib.loads(ex.MANIFEST.read_text(encoding="utf-8"))
    assert "worldlines/private/x.json" not in ex.plan({"worldlines/private/x.json": b"{}", "worldlines/README.md": b""}, man)


def test_private_off_is_an_honest_preview_of_the_open_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """10-10: with the private layer off, the planning beat (ours, still living in core for now) is gone too — no node,
    the graph starts on the plain turn, the screen gets no beat declaration; back on, all of it returns."""
    from test_engine_v3 import _install

    from neonrp.core import node_kinds

    root = _install(tmp_path / "run")
    # 10-19: NEONRP_PRIVATE_DIR stays — in a dev checkout it is how the layer is found (no installed neonrp_private);
    # dropping it left the plan plugin loaded but its strings (plan_loop) unreachable once the layer was back on
    monkeypatch.delenv("NEONRP_PRIVATE", raising=False)
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")   # 10-25: the talk beat's node is in a run that has the beat on
    assert "plan" in orchestration.graph(root)["nodes"]
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    g = orchestration.graph(root)
    assert node_kinds.get("plan") is None and "plan" not in g["nodes"] and g["start"] == "resolve"
    assert orchestration.beat_kinds(root) == {"kinds": {}}
    monkeypatch.delenv("NEONRP_PRIVATE")
    assert "plan" in orchestration.graph(root)["nodes"] and orchestration.beat_kinds(root)["kinds"]


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "release" / "export.py").is_file(),
                    reason="the export tool lives in the development repo")
def test_export_refuses_a_file_that_carries_our_prompt_text(tmp_path: Path):
    """10-10: a prompt snapshot keeps our prompts as escaped strings inside one JSON — not byte-identical to any private
    file, still a leak. A distinctive line of our private prompt text anywhere in a staged file stops the export;
    lines the open engine's own prompts carry too do not count."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("export", Path(__file__).resolve().parents[1] / "release" / "export.py")
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)  # type: ignore[union-attr]
    priv = tmp_path / "neonrp_private"
    (priv / "prompts").mkdir(parents=True)
    ours = "这是我们自己调过的一行主持提示词,写清楚怎么递话筒、怎么收尾、什么时候推进到下一拍。"
    shared = "这一行公开版和我们的版本都有,它不算泄露,因为开源引擎自己的提示词里也写着它。"
    (priv / "prompts" / "plan_sys.zh.md").write_text(ours + "\n" + shared + "\n", encoding="utf-8")
    staged = {"neonrp/tests/data/snapshot.json": json.dumps({"plan.host": "开头\n" + ours}, ensure_ascii=False).encode(),
              "neonrp/src/neonrp/prompts/narrate.zh.md": (shared + "\n").encode(),
              "neonrp/README.md": ("一份普通的说明文字,和私有层没有任何关系,长度也足够长。" * 2).encode()}
    leaks = {x["path"] for x in ex.private_leaks(staged, [priv])}
    assert leaks == {"neonrp/tests/data/snapshot.json"}
