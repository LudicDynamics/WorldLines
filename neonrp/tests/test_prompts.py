"""Tests for conversation prompt templates (M9-T4)."""

import pytest

from neonrp.core.prompts import build_system_prompt


class TestBuildSystemPrompt:
    def test_build_mode_includes_direct_tools_without_submit_proposal(self):
        prompt = build_system_prompt(
            agent_name="Narrator",
            project_name="my-rpg",
            branch="main",
            mode="build",
            skill_descriptions=["combat: Combat rules"],
        )

        assert "write_file" in prompt
        assert "edit_file" in prompt
        assert "import_sillytavern_card" in prompt
        assert "ensure_playable_scaffold" in prompt
        assert "submit_proposal" not in prompt
        assert "relative" in prompt.lower()
        assert "combat: Combat rules" in prompt

    def test_sandbox_mode_mentions_submit_proposal(self):
        prompt = build_system_prompt(
            agent_name="Narrator",
            project_name="my-rpg",
            branch="main",
            mode="sandbox",
            skill_descriptions=[],
        )

        assert "submit_proposal" in prompt
        assert "Do not rely on direct game-data writes" in prompt

    def test_play_mode_mentions_game_master_behavior(self):
        prompt = build_system_prompt(
            agent_name="Narrator",
            project_name="my-rpg",
            branch="main",
            mode="play",
            skill_descriptions=[],
        )

        assert "game master" in prompt.lower()
        assert "narrative-first" in prompt

    def test_all_modes_list_task_and_skill_tools(self):
        for mode in ("build", "sandbox", "play"):
            prompt = build_system_prompt(
                agent_name="Narrator",
                project_name="my-rpg",
                branch="main",
                mode=mode,
                skill_descriptions=[],
            )
            assert "task(agent_id, prompt, resume_run_id?)" in prompt
            assert "Skill(skill)" in prompt

    def test_all_modes_include_task_routing_gate(self):
        for mode in ("build", "sandbox", "play"):
            prompt = build_system_prompt(
                agent_name="Narrator",
                project_name="my-rpg",
                branch="main",
                mode=mode,
                skill_descriptions=[],
            )
            assert "Routing gate before task()" in prompt
            assert "game/meta/active-agent.json" in prompt
            assert "find(query='player')" in prompt
            assert "location" in prompt
            assert "ensure_playable_scaffold" in prompt

    def test_all_modes_enforce_output_language(self):
        # 语言隔离:软性"跟随玩家消息语言"→ 权威 output_lang
        # 指令(压过 authored 世界文件语言)。默认 zh;可参数化 en/ja。
        for mode in ("build", "sandbox", "play"):
            prompt = build_system_prompt(
                agent_name="Narrator",
                project_name="my-rpg",
                branch="main",
                mode=mode,
                skill_descriptions=[],
            )
            assert "Output language: 中文 (Chinese)" in prompt
            assert "Language lock" in prompt
            assert "Follow the **Output language** rule" in prompt
            # 参数化到日/英
            ja = build_system_prompt(
                agent_name="Narrator", project_name="my-rpg", branch="main",
                mode=mode, skill_descriptions=[], output_lang="ja",
            )
            assert "Output language: 日本語 (Japanese)" in ja
            assert "do NOT switch languages to match those source" in ja
            en = build_system_prompt(
                agent_name="Narrator", project_name="my-rpg", branch="main",
                mode=mode, skill_descriptions=[], output_lang="en",
            )
            assert "Output language: English" in en

    def test_all_modes_strongly_recommend_ask_user_for_choices(self):
        for mode in ("build", "sandbox", "play"):
            prompt = build_system_prompt(
                agent_name="Narrator",
                project_name="my-rpg",
                branch="main",
                mode=mode,
                skill_descriptions=[],
            )
            assert "MUST call `ask_user(" in prompt
            assert "NEVER assume user choices" in prompt

    def test_all_modes_include_game_start_bootstrap_protocol(self):
        for mode in ("build", "sandbox", "play"):
            prompt = build_system_prompt(
                agent_name="Narrator",
                project_name="my-rpg",
                branch="main",
                mode=mode,
                skill_descriptions=[],
            )
            assert "Game-start protocol" in prompt
            assert "game/meta/game-start.json" in prompt
            assert "find(query='player')" in prompt
            assert "No blind startup search" in prompt
            assert "read_context" in prompt

    def test_prompt_can_render_runtime_contract_specific_paths(self):
        prompt = build_system_prompt(
            agent_name="Narrator",
            project_name="ship-rpg",
            branch="main",
            mode="play",
            skill_descriptions=[],
            data_dir_name="world",
            routing_state_path="world/router/active-scene.json",
            startup_path="world/router/intro-scene.json",
            location_source_entity_id="captain",
            location_source_field="dock",
        )

        assert "world/<kind>/<id>.json" in prompt
        assert "world/router/active-scene.json" in prompt
        assert "world/router/intro-scene.json" in prompt
        assert "find(query='captain')" in prompt
        assert "dock" in prompt

    def test_build_mode_mentions_sub_agent_creation_workflow(self):
        prompt = build_system_prompt(
            agent_name="Narrator",
            project_name="my-rpg",
            branch="main",
            mode="build",
            skill_descriptions=[],
        )
        assert "Build mode can create sub-agents" in prompt
        assert "agents/<agent_id>/agent.json" in prompt
        assert "schema/rules authoring skill if available" in prompt
        assert "sub-agent orchestration skill for detailed workflow" in prompt

    def test_build_mode_mentions_specific_skills_when_available(self):
        prompt = build_system_prompt(
            agent_name="Narrator",
            project_name="my-rpg",
            branch="main",
            mode="build",
            skill_descriptions=[
                "entity-authoring: entity workflow",
                "sub-agent-orchestration: sub-agent workflow",
            ],
        )
        assert 'Skill(skill="entity-authoring")' in prompt
        assert 'Skill(skill="sub-agent-orchestration")' in prompt

    def test_build_mode_mentions_claude_code_style(self):
        prompt = build_system_prompt(
            agent_name="Narrator",
            project_name="my-rpg",
            branch="main",
            mode="build",
            skill_descriptions=[],
        )
        assert "Claude Code" in prompt

    def test_contains_project_and_branch_context(self):
        prompt = build_system_prompt(
            agent_name="Guide",
            project_name="neon",
            branch="feature-x",
            mode="build",
            skill_descriptions=[],
        )

        assert "Project: neon" in prompt
        assert "Branch: feature-x" in prompt
        assert "Agent: Guide" not in prompt  # Keep strict template shape stable.

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Unsupported mode"):
            build_system_prompt("Narrator", "my-rpg", "main", "invalid", [])
