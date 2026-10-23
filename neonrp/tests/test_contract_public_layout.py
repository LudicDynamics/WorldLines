"""The open-source repo puts neonrp/ and worldlines/ side by side (neonrp/src/neonrp/...): from a clone, the play
contracts are found in the sibling worldlines/contracts — otherwise lint blocks every shipped template with
contract.unknown (open-source review 10-15)."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

from neonrp.template import contract as dev_contract


def test_contracts_are_found_next_to_the_engine_in_the_public_layout(tmp_path, monkeypatch):
    monkeypatch.delenv("NEONRP_PLAY_CONTRACT_PATH", raising=False)
    mod_dir = tmp_path / "neonrp" / "src" / "neonrp" / "template"
    mod_dir.mkdir(parents=True)
    shutil.copy(dev_contract.__file__, mod_dir / "contract.py")
    (tmp_path / "worldlines" / "contracts").mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("_public_contract", mod_dir / "contract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (tmp_path / "worldlines" / "contracts").resolve() in [Path(d).resolve() for d in mod.search_dirs()]
