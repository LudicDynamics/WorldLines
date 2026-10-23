"""Tests for the `soul-authoring` builtin skill (M16 §5.1).

Two concerns, mirroring how `world-game-authoring` is exercised:

1. The skill is discoverable/loadable by :class:`SkillLoader` exactly the
   same way `world-game-authoring` is (packaged builtin, single SKILL.md).
2. Given a *stubbed* LLM (no network), the scaffolder produces the M16 §2
   soul folder structure plus a valid `agents/manifest.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neonrp.core.skill_loader import SkillLoader
from neonrp.core.soul_authoring import build_manifest, scaffold_soul
from neonrp.core.souls import SOUL_SUBFOLDERS, create_soul_dir


# --- Skill discovery: same mechanism as world-game-authoring -----------


class TestSoulAuthoringSkillDiscovery:
    def test_packaged_builtin_skill_is_listed_like_world_game_authoring(
        self, tmp_path: Path
    ) -> None:
        loader = SkillLoader(tmp_path)
        names = loader.list_skills()

        # Loaded by the exact same default-package path as the world skill.
        assert "world-game-authoring" in names
        assert "soul-authoring" in names

    def test_skill_description_and_body_load(self, tmp_path: Path) -> None:
        loader = SkillLoader(tmp_path)

        description = loader.get_description("soul-authoring")
        assert description is not None
        assert "soul" in description.lower()

        content = loader.get_content("soul-authoring")
        assert content is not None
        assert '<skill-loaded name="soul-authoring">' in content
        # Mirrors world-game-authoring's documented IO contract.
        assert "Invocation / IO Contract" in content
        assert "agents/manifest.json" in content

    def test_project_skill_overrides_builtin_soul_authoring(
        self, tmp_path: Path
    ) -> None:
        # Same override semantics SkillLoader gives every builtin.
        project = tmp_path / "skills" / "soul-authoring"
        project.mkdir(parents=True)
        (project / "SKILL.md").write_text(
            "---\nname: soul-authoring\ndescription: project override\n---\nOverridden.\n",
            encoding="utf-8",
        )
        loader = SkillLoader(tmp_path)
        assert loader.get_description("soul-authoring") == "project override"


# --- Scaffolding under a stubbed LLM -----------------------------------


class _StubLLM:
    """Deterministic LLM that returns a partial file map (no network)."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._payload = payload
        self.calls = 0

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        self.calls += 1

        class _Resp:
            def __init__(self, text: str) -> None:
                self.proposal_text = text
                self.raw_output = text

        if self._payload is None:
            return _Resp("no usable json here")
        return _Resp("Here you go:\n" + json.dumps(self._payload) + "\nDone.")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class TestScaffoldSoul:
    def _make_soul(self, monkeypatch: Any, tmp_path: Path) -> Path:
        # Redirect SOUL_HOME so create_soul_dir does not touch ~/.
        import neonrp.core.souls as souls_mod

        monkeypatch.setattr(souls_mod, "SOUL_HOME", tmp_path / "souls")
        return create_soul_dir("elena", name="Elena Voss", agent_template="heroine-classic")

    def test_produces_full_m16_folder_structure(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        soul_dir = self._make_soul(monkeypatch, tmp_path)
        llm = _StubLLM(
            {
                "soul.md": "# Soul Charter — Elena\n\n## Core Presence\n\nA calm void-mage companion.",
                "persona/core_traits.json": {"calm": True},
                "background/origin.md": "Born in the orbital ring.",
            }
        )

        result = scaffold_soul(
            soul_dir,
            description="a calm void-mage companion",
            sid="elena",
            agent_template="heroine-classic",
            llm=llm,
        )

        assert llm.calls == 1

        # Every minted skeleton subfolder still present.
        for sub in SOUL_SUBFOLDERS:
            assert (soul_dir / sub).is_dir()

        # Each documented content file exists.
        for rel in (
            "soul.md",
            "persona/core_traits.json",
            "persona/motivations.json",
            "persona/values.json",
            "persona/relationships.json",
            "background/origin.md",
            "background/history.md",
            "background/secrets.md",
            "character/stats.json",
            "character/inventory.json",
            "character/equipment.json",
            "character/wallet.json",
            "character/status.json",
            "character/profile.json",
            "rules/decision_rules.md",
            "rules/interaction_rules.md",
            "rules/action_rules.md",
            "short-term-memo/current_context.json",
            "short-term-memo/conversation_cache.json",
            "short-term-memo/recent_events.json",
            "long-term-memo/important_events.md",
            "long-term-memo/learned_facts.json",
            "long-term-memo/emotional_memories.json",
            "trajectory/action_log.md",
            "agents/manifest.json",
            "agents/contracts.md",
        ):
            assert (soul_dir / rel).is_file(), f"missing {rel}"
            assert rel in result["written"]

        # LLM-provided content is honoured...
        assert _read_json(soul_dir / "persona/core_traits.json") == {"calm": True}
        assert "Core Presence" in (soul_dir / "soul.md").read_text(encoding="utf-8")
        assert "orbital ring" in (soul_dir / "background/origin.md").read_text(encoding="utf-8")
        # ...and omitted files are backfilled with a structural seed.
        profile = _read_json(soul_dir / "character/profile.json")
        assert profile["sid"] == "elena"

        # trajectory stays a header-only stub (no fabricated history).
        log = (soul_dir / "trajectory/action_log.md").read_text(encoding="utf-8")
        assert log.startswith("# Trajectory")
        assert "append-only" in log

    def test_does_not_write_soul_json_or_run_state(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        soul_dir = self._make_soul(monkeypatch, tmp_path)
        soul_json_before = (soul_dir / "soul.json").read_text(encoding="utf-8")

        scaffold_soul(
            soul_dir,
            description="x",
            sid="elena",
            agent_template="heroine-classic",
            llm=_StubLLM(None),
        )

        # soul.json is the library's envelope — untouched by the skill.
        assert (soul_dir / "soul.json").read_text(encoding="utf-8") == soul_json_before
        assert not (soul_dir / "run_state.json").exists()
        assert (soul_dir / "soul.md").exists()

    def test_manifest_is_valid_single_soul_agent(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        soul_dir = self._make_soul(monkeypatch, tmp_path)
        scaffold_soul(
            soul_dir,
            description="x",
            sid="elena",
            agent_template="heroine-classic",
            llm=_StubLLM(None),
        )

        manifest = _read_json(soul_dir / "agents/manifest.json")
        assert manifest["schema_version"] == 1
        assert manifest["agent_template"] == "heroine-classic"

        # M30(2026-08-12):1 soul = 1 agent——六路分解与 .claude 路径废除;
        # 写面 = soul 自己的 context 全域(旧六路 write 面的并集)。
        ids = [a["id"] for a in manifest["agents"]]
        assert ids == ["soul-agent"]
        agent = manifest["agents"][0]
        assert {"id", "role", "write_globs"} <= set(agent)
        assert "system_prompt" not in agent  # 路径谎言不再进 manifest
        assert set(agent["write_globs"]) == {
            "run_state.json",
            "trajectory/**",
            "short-term-memo/**",
            "long-term-memo/**",
            "character/**",
        }

    def test_every_template_yields_the_unified_single_agent(self) -> None:
        # M30:模板名只是创作口味标记;roster 一律单 soul-agent,
        # 未知模板同样安全(永不产出坏 soul)。
        for name in ("minimal", "heroine-classic", "totally-unknown"):
            manifest = build_manifest(name)
            assert manifest["agent_template"] == name
            assert [a["id"] for a in manifest["agents"]] == ["soul-agent"]

    def test_scaffold_passes_skill_body_into_system_prompt(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        soul_dir = self._make_soul(monkeypatch, tmp_path)

        captured: dict[str, str] = {}

        class _CapturingLLM:
            def generate(
                self,
                system_prompt: str,
                user_prompt: str,
                tools: list[dict[str, Any]] | None = None,
            ) -> Any:
                captured["system"] = system_prompt
                captured["user"] = user_prompt

                class _R:
                    proposal_text = "{}"
                    raw_output = "{}"

                return _R()

        loader = SkillLoader(tmp_path)
        body = loader.get_content("soul-authoring") or ""

        scaffold_soul(
            soul_dir,
            description="seed desc",
            sid="elena",
            agent_template="minimal",
            llm=_CapturingLLM(),
            skill_body=body,
        )

        assert "soul-authoring skill" in captured["system"]
        assert body[:40] in captured["system"]
        assert "seed desc" in captured["user"]
        assert "soul.md" in captured["user"]


# --- ensure_soul_agent: idempotent runnability backfill ----------------


class TestEnsureSoulAgent:
    def test_writes_manifest_when_absent(self, tmp_path: Path) -> None:
        from neonrp.core.soul_authoring import ensure_soul_agent

        soul_dir = tmp_path / "souls" / "ai-si1"
        (soul_dir / "agents").mkdir(parents=True)  # empty agents/, no manifest
        (soul_dir / "soul.json").write_text(
            json.dumps({"sid": "ai", "name": "Ai"}), encoding="utf-8"
        )

        wrote = ensure_soul_agent(soul_dir)

        assert wrote is True
        manifest = json.loads((soul_dir / "agents" / "manifest.json").read_text("utf-8"))
        assert isinstance(manifest["agents"], list) and manifest["agents"]
        assert (soul_dir / "agents" / "contracts.md").exists()

    def test_idempotent_when_already_valid(self, tmp_path: Path) -> None:
        from neonrp.core.soul_authoring import ensure_soul_agent

        soul_dir = tmp_path / "souls" / "ai-si1"
        (soul_dir / "agents").mkdir(parents=True)
        ensure_soul_agent(soul_dir)
        # second call must be a no-op (returns False, doesn't rewrite)
        assert ensure_soul_agent(soul_dir) is False

    def test_resolve_soul_agent_self_heals_missing_manifest(self, tmp_path: Path) -> None:
        from neonrp.core.soul_agent import resolve_soul_agent_data

        soul_dir = tmp_path / "souls" / "ai-si1"
        (soul_dir / "agents").mkdir(parents=True)  # broken soul: no manifest
        (soul_dir / "soul.json").write_text(
            json.dumps({"sid": "ai", "name": "Ai"}), encoding="utf-8"
        )

        data = resolve_soul_agent_data(tmp_path, "ai", "si1")

        assert isinstance(data, dict)
        assert data["id"] == "soul:ai:si1"
        assert data["permissions"]["write_globs"]  # derived from backfilled roster
        assert (soul_dir / "agents" / "manifest.json").exists()

    def test_resolve_returns_none_when_soul_folder_absent(self, tmp_path: Path) -> None:
        from neonrp.core.soul_agent import resolve_soul_agent_data

        # no souls/<id> dir at all → not a soul, must NOT fabricate one
        assert resolve_soul_agent_data(tmp_path, "ghost", "si9") is None
        assert not (tmp_path / "souls" / "ghost-si9").exists()
