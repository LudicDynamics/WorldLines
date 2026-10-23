import json
from pathlib import Path

from neonrp.core.event_log import GameEvent, append_event, read_events
from neonrp.core.active_agent import write_active_agent
from neonrp.core.paths import get_data_dir_name, get_game_dir
from neonrp.core.runtime_contract import get_runtime_contract_path, load_runtime_contract, resolve_router_agent_id
from neonrp.core.validation import load_schema, validate_game_data


def test_runtime_contract_infers_domain_map_from_sticky_agents(tmp_path: Path) -> None:
    (tmp_path / ".neonrp").mkdir(parents=True)
    (tmp_path / "agents" / "narrator").mkdir(parents=True)
    (tmp_path / "agents" / "station-agent").mkdir(parents=True)
    (tmp_path / "agents" / "station-agent" / "agent.json").write_text(
        json.dumps(
            {
                "id": "station-agent",
                "sticky_domain_kinds": ["station"],
            }
        ),
        encoding="utf-8",
    )

    contract = load_runtime_contract(tmp_path)

    assert contract.source == "inferred"
    assert contract.routing.domain_agent_map == {"station": "station-agent"}
    assert contract.active_agent_relpath == "game/meta/active-agent.json"
    assert contract.router.execution_mode == "orchestrator"


def test_runtime_contract_overrides_data_dir_and_router_paths(tmp_path: Path) -> None:
    contract_path = get_runtime_contract_path(tmp_path)
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        json.dumps(
            {
                "data_dir": "world",
                "router": {
                    "state_file": "router/active-scene.json",
                    "startup_file": "router/prologue.json",
                    "execution_mode": "orchestrator",
                },
                "routing": {
                    "location_source": {
                        "entity_id": "captain",
                        "field": "dock",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    contract = load_runtime_contract(tmp_path)

    assert get_data_dir_name(tmp_path) == "world"
    assert get_game_dir(tmp_path) == tmp_path / "world"
    assert contract.active_agent_relpath == "world/router/active-scene.json"
    assert contract.startup_relpath == "world/router/prologue.json"
    assert contract.router.execution_mode == "orchestrator"
    assert contract.routing.location_source.entity_id == "captain"
    assert contract.routing.location_source.field == "dock"


def test_default_execution_mode_is_orchestrator_when_contract_absent(tmp_path: Path) -> None:
    """A scaffolded game with no runtime_contract.json defaults to `fast`.

    The engine's architectural contract: execution_mode falls back to
    `fast` whenever the game / template hasn't explicitly declared
    orchestrator. In `fast` mode every agent (root narrator + sticky
    sub-agents like town-agent, character-agent) can call ask_user.
    Orchestrator mode is strictly opt-in via runtime_contract.json.
    """
    (tmp_path / ".neonrp").mkdir(parents=True)
    (tmp_path / "agents" / "narrator").mkdir(parents=True)

    contract = load_runtime_contract(tmp_path)

    assert contract.source == "inferred"
    assert contract.router.execution_mode == "orchestrator"


def test_template_runtime_contract_lives_outside_neonrp_dir() -> None:
    """Template `runtime_contract.json` must live at the template root,
    not inside `.neonrp/`. The `.neonrp/` directory is for per-game runtime
    state (sessions, logs) and should never be shipped as template content
    in the wheel. The scaffolder writes the contract into `<game>/.neonrp/`
    at creation time; shipping it pre-nested would conflate config with
    gameplay state and also gets `.gitignore`-excluded from the build.
    """
    from importlib import resources

    for tpl in ("default", "stoneford-orch"):
        root = resources.files("neonrp.templates").joinpath(tpl)
        # New location: template root.
        assert root.joinpath("runtime_contract.json").is_file(), (
            f"template '{tpl}' is missing runtime_contract.json at its root"
        )
        # Old nested location must NOT exist — would mean we shipped a
        # .neonrp/ subtree inside the wheel.
        legacy = root.joinpath(".neonrp").joinpath("runtime_contract.json")
        # Using is_file not exists to avoid false positives on traversable.
        assert not legacy.is_file(), (
            f"template '{tpl}' still has legacy `.neonrp/runtime_contract.json` — move it to the template root"
        )


def test_resolve_router_agent_id_prefers_narrator_then_orchestrator(tmp_path: Path) -> None:
    orchestrator_dir = tmp_path / "agents" / "orchestrator"
    orchestrator_dir.mkdir(parents=True)
    (orchestrator_dir / "agent.json").write_text(json.dumps({"id": "orchestrator"}), encoding="utf-8")

    assert resolve_router_agent_id(tmp_path) == "orchestrator"

    narrator_dir = tmp_path / "agents" / "narrator"
    narrator_dir.mkdir(parents=True)
    (narrator_dir / "agent.json").write_text(json.dumps({"id": "narrator"}), encoding="utf-8")

    assert resolve_router_agent_id(tmp_path) == "narrator"


def test_active_agent_uses_runtime_contract_path(tmp_path: Path) -> None:
    contract_path = get_runtime_contract_path(tmp_path)
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(
        json.dumps(
            {
                "data_dir": "world",
                "router": {"state_file": "router/active-scene.json"},
            }
        ),
        encoding="utf-8",
    )

    write_active_agent(tmp_path, "station-agent", reason="boarding")

    assert (tmp_path / "world" / "router" / "active-scene.json").exists()


def test_append_event_creates_missing_events_directory(tmp_path: Path) -> None:
    event = GameEvent(id=0, type="play", actor="narrator", payload={"ok": True})

    append_event(tmp_path, "main", event)

    path = tmp_path / ".neonrp" / "events" / "main.jsonl"
    assert path.exists()
    events = read_events(tmp_path, "main")
    assert len(events) == 1


def test_validation_uses_runtime_contract_data_dir(tmp_path: Path) -> None:
    contract_path = get_runtime_contract_path(tmp_path)
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text(json.dumps({"data_dir": "world"}), encoding="utf-8")
    world_dir = tmp_path / "world" / "station"
    world_dir.mkdir(parents=True)
    (world_dir / "alpha.json").write_text(
        json.dumps({"id": "alpha", "kind": "station", "name": "Alpha Station"}),
        encoding="utf-8",
    )

    schema = load_schema(tmp_path)
    issues, entities = validate_game_data(tmp_path, schema)

    assert issues == []
    assert len(entities) == 1


def test_legacy_fast_mode_normalizes_to_orchestrator(tmp_path: Path) -> None:
    """fast 退役:旧档/旧配置写 "fast" 一律 fail-open 迁移到
    orchestrator——set 时立即归一,旧契约文件读出来也归一,不报错不断档。"""
    from neonrp.core.runtime_contract import (
        get_router_execution_mode,
        get_runtime_contract_path,
        set_router_execution_mode,
    )

    # set 面:传入 legacy 值直接归一。
    assert set_router_execution_mode(tmp_path, "fast") == "orchestrator"
    assert get_router_execution_mode(tmp_path) == "orchestrator"

    # read 面:磁盘上残留 "fast" 的旧契约照样归一。
    path = get_runtime_contract_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["router"]["execution_mode"] = "fast"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert get_router_execution_mode(tmp_path) == "orchestrator"
