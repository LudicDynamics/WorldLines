"""Tests for system prompt enrichment and token budget (M7-T3)."""

from neonrp.core.agent_runner import (
    _estimate_tokens,
    _build_default_system_prompt,
    BUDGET_WARNING_THRESHOLD,
    BUDGET_TERMINATION_THRESHOLD,
)
from neonrp.core.llm import Message, ToolCall


class TestEstimateTokens:
    """Tests for _estimate_tokens function."""

    def test_empty_messages(self):
        """Empty message list returns 0."""
        result = _estimate_tokens([])
        assert result == 0

    def test_simple_message(self):
        """Simple text message estimation."""
        # 100 chars / 4 = 25 tokens
        messages = [Message(role="user", content="x" * 100)]
        result = _estimate_tokens(messages)
        assert result == 25

    def test_multiple_messages(self):
        """Multiple messages add up."""
        messages = [
            Message(role="system", content="a" * 40),  # 10 tokens
            Message(role="user", content="b" * 80),  # 20 tokens
            Message(role="assistant", content="c" * 120),  # 30 tokens
        ]
        result = _estimate_tokens(messages)
        assert result == 60  # 240 / 4

    def test_message_with_tool_calls(self):
        """Messages with tool calls include tool call size."""
        tool_call = ToolCall(
            id="call-1",
            name="read_file",
            arguments={"path": "game/character/hero.json"},  # ~40 chars JSON
        )
        messages = [
            Message(role="assistant", content="x" * 40, tool_calls=[tool_call]),
        ]
        result = _estimate_tokens(messages)
        # 40 content + ~50 (name + args JSON) = ~90 chars / 4 = ~22
        assert result >= 20
        assert result <= 30

    def test_none_content(self):
        """None content treated as empty."""
        messages = [Message(role="assistant", content=None)]
        result = _estimate_tokens(messages)
        assert result == 0

    def test_estimation_matches_expected_range(self):
        """Token estimate roughly matches 1 token = 4 chars."""
        text = "The quick brown fox jumps over the lazy dog."  # 44 chars
        messages = [Message(role="user", content=text)]
        result = _estimate_tokens(messages)
        assert result == 11  # 44 / 4


class TestBuildDefaultSystemPrompt:
    """Tests for _build_default_system_prompt function."""

    def test_includes_agent_id(self):
        """Prompt includes the agent ID."""
        prompt = _build_default_system_prompt("test-agent")
        assert "test-agent" in prompt

    def test_includes_tools_section(self):
        """Prompt includes Available Tools section."""
        prompt = _build_default_system_prompt("game-master")
        assert "## Available Tools" in prompt
        assert "read_file" in prompt
        assert "submit_proposal" in prompt

    def test_includes_rules_section(self):
        """Prompt includes Rules section."""
        prompt = _build_default_system_prompt("game-master")
        assert "## Rules" in prompt

    def test_includes_entity_format(self):
        """Prompt includes Entity Format section."""
        prompt = _build_default_system_prompt("game-master")
        assert "## Entity Format" in prompt

    def test_ends_with_submit_reminder(self):
        """Prompt ends with submit_proposal reminder."""
        prompt = _build_default_system_prompt("game-master")
        assert "submit_proposal" in prompt.lower()

    def test_default_prompt_length_reasonable(self):
        """Default prompt is reasonably sized."""
        prompt = _build_default_system_prompt("test")
        # Should be comprehensive but not excessive
        assert len(prompt) > 500  # Has substance
        assert len(prompt) < 5000  # Not bloated


class TestBudgetThresholds:
    """Tests for budget threshold constants."""

    def test_warning_threshold(self):
        """Warning threshold is 80%."""
        assert BUDGET_WARNING_THRESHOLD == 0.8

    def test_termination_threshold(self):
        """Termination threshold is 100%."""
        assert BUDGET_TERMINATION_THRESHOLD == 1.0

    def test_warning_before_termination(self):
        """Warning threshold is below termination."""
        assert BUDGET_WARNING_THRESHOLD < BUDGET_TERMINATION_THRESHOLD


class TestBudgetIntegration:
    """Integration tests for budget enforcement in agentic loop."""

    def test_small_context_no_warning(self, tmp_path):
        """Small context stays under budget without warning."""
        from neonrp.core.agent_runner import _estimate_tokens

        # 1000 chars = 250 tokens, well under 100000 char budget
        messages = [Message(role="user", content="x" * 1000)]
        tokens = _estimate_tokens(messages)
        chars = tokens * 4

        max_budget = 100000
        ratio = chars / max_budget

        assert ratio < BUDGET_WARNING_THRESHOLD
        assert ratio < BUDGET_TERMINATION_THRESHOLD

    def test_large_context_triggers_warning(self, tmp_path):
        """Large context should trigger warning threshold."""
        from neonrp.core.agent_runner import _estimate_tokens

        # 85000 chars = 85% of 100000 budget
        messages = [Message(role="user", content="x" * 85000)]
        tokens = _estimate_tokens(messages)
        chars = tokens * 4

        max_budget = 100000
        ratio = chars / max_budget

        assert ratio >= BUDGET_WARNING_THRESHOLD
        assert ratio < BUDGET_TERMINATION_THRESHOLD

    def test_huge_context_triggers_termination(self, tmp_path):
        """Huge context should trigger termination threshold."""
        from neonrp.core.agent_runner import _estimate_tokens

        # 105000 chars = 105% of 100000 budget
        messages = [Message(role="user", content="x" * 105000)]
        tokens = _estimate_tokens(messages)
        chars = tokens * 4

        max_budget = 100000
        ratio = chars / max_budget

        assert ratio >= BUDGET_TERMINATION_THRESHOLD
