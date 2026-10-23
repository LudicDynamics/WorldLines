"""Secrets overlay (docs/SECRETS-DESIGN.md P1) — the omniscience-leak fix.

Regressions pinned here:
- the indexer used to index game/secrets/** (retrieval could surface secrets),
- non-audience agents used to be able to read any secret file,
- knowledge/discovery fields were pure decoration (nothing ever revealed).

Worlds without game/secrets/ must be byte-for-byte unaffected.
"""

import json
from pathlib import Path

import pytest

from neonrp.core.indexing import scan_entities
from neonrp.core.secrets import (
    check_and_apply_reveals,
    condition_met,
    drain_reveal_notices,
    load_secrets,
    read_ledger,
    secrets_deny_paths,
)
from neonrp.core.skills import SkillRegistry
from neonrp.core.validation import check_world

KAGURA = (
    Path(__file__).resolve().parents[2]
    / "rp-core"
    / "examples"
    / "kagura-island"
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _world(tmp_path: Path) -> Path:
    root = tmp_path / "world"
    _write(root / "game" / "npc" / "kagami.json", {
        "id": "kagami", "kind": "npc", "name": "鏡子",
        "summary": "咖啡馆老板。", "trust": 20,
    })
    _write(root / "game" / "location" / "cellar.json", {
        "id": "cellar", "kind": "location", "name": "地下室",
        "summary": "堆满旧物。", "connections": ["cafe"],
    })
    _write(root / "game" / "meta" / "run_state.json", {"turn_count": 3, "location": "cafe"})
    return root


def _add_secret(root: Path, name: str, data: dict) -> None:
    _write(root / "game" / "secrets" / f"{name}.json", data)


CELLAR_SECRET = {
    "id": "secret-location--cellar",
    "kind": "secret",
    "about": "location/cellar",
    "audience": ["gm"],
    "content": {
        "summary_hidden": "有一条通向海底的隐藏通道。",
        "connections_hidden": ["undersea-tunnel"],
    },
    "revealed_when": [
        {"trust_gte": {"npc": "kagami", "value": 60}},
        {"judgment": "玩家认真侦查"},
    ],
}


# ── 1. loader ────────────────────────────────────────────────────────────


def test_loader_parses_and_reports_issues(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", CELLAR_SECRET)
    _add_secret(root, "broken", {"id": "x", "audience": "gm"})  # no about, bad audience type
    secrets, issues = load_secrets(root)
    assert {s.secret_id for s in secrets} == {"secret-location--cellar", "x"}
    assert any("about" in i for i in issues)
    good = next(s for s in secrets if s.secret_id == "secret-location--cellar")
    assert good.machine_conditions() == [{"trust_gte": {"npc": "kagami", "value": 60}}]


# ── 2. audience deny synthesis ───────────────────────────────────────────


def test_deny_paths_follow_audience(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", CELLAR_SECRET)
    _add_secret(root, "npc--kagami", {
        "id": "s-kagami", "kind": "secret", "about": "npc/kagami",
        "audience": ["gm", "npc:kagami"], "content": {"notes_hidden": "x"},
    })
    # A random npc agent is denied both files.
    assert secrets_deny_paths(root, "npc-yuto") == [
        "game/secrets/location--cellar.json",
        "game/secrets/npc--kagami.json",
    ]
    # kagami (either agent naming convention) may read her own secret only.
    for agent in ("kagami", "npc-kagami"):
        assert secrets_deny_paths(root, agent) == ["game/secrets/location--cellar.json"]
    # GM side sees everything; the router does too.
    assert secrets_deny_paths(root, "world-agent") == []
    assert secrets_deny_paths(root, "game-master") == []
    assert secrets_deny_paths(root, "narrator", router_agent_id="narrator") == []


def test_no_secrets_world_is_untouched(tmp_path):
    root = _world(tmp_path)
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert secrets_deny_paths(root, "npc-yuto") == []
    assert check_and_apply_reveals(root) == []
    assert drain_reveal_notices(root) == []
    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert after == before  # not even a ledger/queue file was created


def test_registry_blocks_non_audience_read(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", CELLAR_SECRET)
    denied = SkillRegistry(
        root=root, run_id="r", agent_id="npc-yuto",
        read_globs=["**"], deny_globs=secrets_deny_paths(root, "npc-yuto"),
        direct_write_globs=[],
    )
    result = denied.invoke("read_file", {"path": "game/secrets/location--cellar.json"})
    assert result.success is False
    gm = SkillRegistry(
        root=root, run_id="r", agent_id="world-agent",
        read_globs=["**"], deny_globs=secrets_deny_paths(root, "world-agent"),
        direct_write_globs=[],
    )
    assert gm.invoke("read_file", {"path": "game/secrets/location--cellar.json"}).success is True


# ── 3. indexer never surfaces secrets ────────────────────────────────────


def test_index_excludes_secrets(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", CELLAR_SECRET)
    records, _issues = scan_entities(root)
    paths = {r.path for r in records}
    assert not any("secrets/" in p for p in paths)
    blob = json.dumps([r.__dict__ for r in records], ensure_ascii=False, default=str)
    assert "隐藏通道" not in blob


# ── 4. deterministic reveal ──────────────────────────────────────────────


def test_reveal_on_trust_merges_ledger_and_notice(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", CELLAR_SECRET)
    # Below threshold: nothing happens.
    assert check_and_apply_reveals(root) == []
    host = json.loads((root / "game/location/cellar.json").read_text(encoding="utf-8"))
    assert "隐藏通道" not in host["summary"]
    # Trust crosses the threshold.
    _write(root / "game" / "npc" / "kagami.json", {
        "id": "kagami", "kind": "npc", "name": "鏡子", "summary": "咖啡馆老板。", "trust": 65,
    })
    assert check_and_apply_reveals(root) == ["secret-location--cellar"]
    host = json.loads((root / "game/location/cellar.json").read_text(encoding="utf-8"))
    assert "隐藏通道" in host["summary"]  # summary_hidden merged
    assert host["connections"] == ["cafe", "undersea-tunnel"]  # connections_hidden merged
    ledger = read_ledger(root)
    assert ledger["secret-location--cellar"]["about"] == "location/cellar"
    assert ledger["secret-location--cellar"]["turn"] == 3
    # Idempotent: a second pass reveals nothing and does not double-merge.
    assert check_and_apply_reveals(root) == []
    host2 = json.loads((root / "game/location/cellar.json").read_text(encoding="utf-8"))
    assert host2["summary"].count("隐藏通道") == 1
    # Notice is delivered exactly once.
    notices = drain_reveal_notices(root)
    assert len(notices) == 1 and "location/cellar" in notices[0]
    assert drain_reveal_notices(root) == []


def test_flag_and_visited_conditions(tmp_path):
    root = _world(tmp_path)
    assert condition_met(root, {"flag": {"key": "loop_broken"}}) is False
    assert condition_met(root, {"visited": {"location": "cellar"}}) is False
    _write(root / "game" / "meta" / "run_state.json", {
        "turn_count": 9, "location": {"node_id": "T001", "subnode_id": "cellar"},
        "loop_broken": True,
    })
    assert condition_met(root, {"flag": {"key": "loop_broken"}}) is True
    assert condition_met(root, {"flag": {"key": "loop_broken", "equals": False}}) is False
    assert condition_met(root, {"visited": {"location": "cellar"}}) is True
    # judgment never fires in P1 (keeper's job).
    assert condition_met(root, {"judgment": "认真侦查"}) is False


# ── 5. validate layer ────────────────────────────────────────────────────


def test_check_world_warns_on_bad_secret(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--ghost", {
        "id": "s-ghost", "kind": "secret", "about": "location/ghost",
        "audience": ["gm"], "content": {"summary_hidden": "x"},
    })
    _add_secret(root, "broken", {"id": "b", "audience": ["gm"]})  # no about/content
    health = check_world(root)
    codes = {w.code for w in health.warnings}
    assert "secret-host-missing" in codes
    assert "secret-schema" in codes
    # Secrets problems are warnings, never blockers.
    assert not any(b.layer == "secrets" for b in health.blockers)


# ── 6. kagura pilot ──────────────────────────────────────────────────────


@pytest.mark.skipif(not KAGURA.exists(), reason="kagura example not checked out")
def test_kagura_hosts_are_scrubbed_and_secrets_hold_the_truth():
    makoto = json.loads((KAGURA / "game/npc/makoto.json").read_text(encoding="utf-8"))
    assert "Yith" not in json.dumps(makoto, ensure_ascii=False)
    cellar = json.loads((KAGURA / "game/location/cafe-basement.json").read_text(encoding="utf-8"))
    assert "隐藏通道" not in cellar["summary"]
    assert "undersea-tunnel" not in cellar.get("connections", [])
    secret = json.loads(
        (KAGURA / "game/secrets/npc--makoto.json").read_text(encoding="utf-8")
    )
    assert "Yith" in secret["content"]["summary_hidden"]
    assert secret["audience"] == ["gm", "npc:makoto"]
    health = check_world(KAGURA)
    assert health.playable
