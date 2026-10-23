"""10-08: in an installed release the templates, contracts and screen come from the worldlines wheel
(worldlines_shim/{templates,contracts,spa}); the engine finds them itself, whichever package's `worldlines` command won.
The player's own templates live in ~/.worldlines/templates, looked up first."""
from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest
from _paths import PRODUCT, PRODUCT_TEMPLATES

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def fake_shell(tmp_path, monkeypatch):
    pkg = tmp_path / "site" / "worldlines_shim"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    shutil.copytree(PRODUCT_TEMPLATES / "werewolf-night-village.template", pkg / "templates" / "werewolf-night-village.template")
    shutil.copytree(PRODUCT / "contracts", pkg / "contracts")
    (pkg / "spa").mkdir()
    (pkg / "spa" / "index.html").write_text("<title>x</title>", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    sys.modules.pop("worldlines_shim", None)
    importlib.invalidate_caches()
    yield pkg
    sys.modules.pop("worldlines_shim", None)


def test_engine_finds_what_the_shell_ships(fake_shell, monkeypatch):
    from neonrp import template as TP
    from neonrp.commands.web import _spa_root
    from neonrp.core.paths import shell_dir
    from neonrp.template import contract

    monkeypatch.delenv("NEONRP_SPA_DIR", raising=False)
    assert shell_dir("templates") == fake_shell / "templates"
    assert fake_shell / "templates" in TP.search_dirs() and fake_shell / "contracts" in contract.search_dirs()
    assert _spa_root() == fake_shell / "spa"


def test_template_store_goes_first(tmp_path, monkeypatch):
    from neonrp.core.paths import ensure_template_store

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", "/x/other")
    monkeypatch.delenv("NEONRP_TEMPLATE_WRITE_DIR", raising=False)
    store = ensure_template_store()
    import os

    assert store == tmp_path / ".worldlines" / "templates"
    assert os.environ["NEONRP_TEMPLATE_WRITE_DIR"] == str(store)
    assert os.environ["NEONRP_TEMPLATE_PATH"].split(os.pathsep)[:2] == [str(store), "/x/other"]
