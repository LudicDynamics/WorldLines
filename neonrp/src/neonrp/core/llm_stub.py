"""Deterministic stub LLM adapter for testing.

Provides a fully deterministic adapter for CI and testing without network calls.
"""

import json
import uuid
from pathlib import Path
from typing import Any

from neonrp.core.llm import LLMResponse, LLMTurnResult, Message, ToolCall, StreamChunk


class StubAdapter:
    """Deterministic stub adapter for testing.

    When fixture_path is provided, loads and returns the proposal from that file.
    Otherwise returns a hardcoded minimal valid proposal.

    For chat(), supports multi-turn mode with tool calls and submit_proposal.
    """

    def __init__(self, fixture_path: Path | str | None = None):
        """Initialize stub adapter.

        Args:
            fixture_path: Optional path to a proposal fixture file
        """
        self.fixture_path = Path(fixture_path) if fixture_path else None
        self._call_count = 0
        self._chat_turn = 0

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Generate a deterministic response.

        Args:
            system_prompt: Agent's system.md content (logged but not used)
            user_prompt: Contains run_id, agent_id, branch, base_head_event, query
            tools: Skill tool schemas (not used in stub)

        Returns:
            LLMResponse with deterministic proposal
        """
        self._call_count += 1

        # If fixture path provided, load proposal from file
        if self.fixture_path:
            return self._load_fixture()

        # Generate minimal proposal from user prompt
        return self._generate_minimal_proposal(user_prompt)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> LLMTurnResult:
        """Execute one turn of a multi-turn conversation (M6).

        Stub behavior:
        - Turn 0: Return a submit_proposal tool call with minimal proposal
        - This simulates the agent immediately completing its task

        If fixture_path is provided, loads the proposal from that file
        for the submit_proposal call.
        """
        self._chat_turn += 1

        # Extract context from messages
        context = self._extract_context_from_messages(messages)
        tool_names = {
            tool.get("name")
            for tool in (tools or [])
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }

        # 纯对话(tools=None):ask_soul / 轻心跳 / 直聊的轻调用路径。
        # 返回确定性文本——CI 无真实 key 时这些链路也必须 hermetic 可跑
        # (2026-08-14 CI 红修复:此前落进 submit_proposal 分支 → content
        # 为 None → "empty answer")。
        if tools is None:
            tail = ""
            for m in reversed(messages):
                if getattr(m, "role", "") == "user" and getattr(m, "content", None):
                    tail = str(m.content).strip().splitlines()[-1][:60]
                    break
            return LLMTurnResult(
                message=Message(
                    role="assistant",
                    content=f"(stub)我听见了。{tail}",
                ),
                tool_calls=[],
                finished=True,
                usage={"prompt_tokens": 30, "completion_tokens": 15},
            )

        # In build/play mode, submit_proposal is intentionally absent.
        # Return a plain assistant message and finish immediately.
        if tools is not None and "submit_proposal" not in tool_names:
            assistant_msg = Message(
                role="assistant",
                content="Stub provider active — no real model is selected for this world. Type /settings to add or pick one (or /models to switch).",
            )
            return LLMTurnResult(
                message=assistant_msg,
                tool_calls=[],
                finished=True,
                usage={"prompt_tokens": 50, "completion_tokens": 20},
            )

        # If fixture provided, use it for the proposal
        if self.fixture_path:
            proposal_data = self._load_fixture_data()
            if proposal_data is None:
                return LLMTurnResult(
                    error="Failed to load fixture",
                    finished=True,
                )
        else:
            proposal_data = {
                "proposal_version": "0.1",
                "run_id": context.get("run_id", f"stub_run_{self._chat_turn}"),
                "agent_id": context.get("agent_id", "stub-agent"),
                "branch": context.get("branch", "main"),
                "base_head_event": context.get("base_head_event", 0),
                "query": context.get("query", "stub query"),
                "rationale": "Stub provider generated empty proposal for testing.",
                "ops": [],
            }

        # Create a submit_proposal tool call
        tool_call = ToolCall(
            id=f"call_{uuid.uuid4().hex[:12]}",
            name="submit_proposal",
            arguments=proposal_data,
        )

        # Create response message with tool call
        assistant_msg = Message(
            role="assistant",
            content=None,
            tool_calls=[tool_call],
        )

        return LLMTurnResult(
            message=assistant_msg,
            tool_calls=[tool_call],
            finished=False,  # Tool call needs to be processed
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

    def _load_fixture(self) -> LLMResponse:
        """Load proposal from fixture file."""
        if not self.fixture_path.exists():
            return LLMResponse(raw_output="", error=f"Fixture file not found: {self.fixture_path}")

        try:
            content = self.fixture_path.read_text(encoding="utf-8")
            # Validate it's valid JSON
            json.loads(content)
            return LLMResponse(
                proposal_text=content, raw_output=content, usage={"prompt_tokens": 0, "completion_tokens": 0}
            )
        except json.JSONDecodeError as e:
            return LLMResponse(raw_output=content if "content" in dir() else "", error=f"Invalid JSON in fixture: {e}")
        except IOError as e:
            return LLMResponse(raw_output="", error=f"Failed to read fixture: {e}")

    def _load_fixture_data(self) -> dict | None:
        """Load proposal data from fixture file as dict."""
        if not self.fixture_path or not self.fixture_path.exists():
            return None
        try:
            return json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None

    def _generate_minimal_proposal(self, user_prompt: str) -> LLMResponse:
        """Generate a minimal valid proposal from user prompt context.

        Extracts agent_id, branch, and base_head_event from user prompt and
        creates an empty-ops proposal.
        """
        # Parse context from user prompt
        # User prompt format typically includes JSON with these fields
        context = self._parse_user_prompt_context(user_prompt)

        proposal = {
            "proposal_version": "0.1",
            "run_id": context.get("run_id", f"stub_run_{self._call_count}"),
            "agent_id": context.get("agent_id", "stub-agent"),
            "branch": context.get("branch", "main"),
            "base_head_event": context.get("base_head_event", 0),
            "query": context.get("query", "stub query"),
            "rationale": "Stub provider generated empty proposal for testing.",
            "ops": [],
        }

        proposal_text = json.dumps(proposal, indent=2, ensure_ascii=False)
        return LLMResponse(
            proposal_text=proposal_text,
            raw_output=proposal_text,
            usage={"prompt_tokens": len(user_prompt) // 4, "completion_tokens": len(proposal_text) // 4},
        )

    def _parse_user_prompt_context(self, user_prompt: str) -> dict[str, Any]:
        """Parse context values from user prompt.

        Tries to extract run_id, agent_id, branch, base_head_event, query
        from a JSON-like structure in the prompt.
        """
        context: dict[str, Any] = {}

        # Try to find JSON object in prompt
        try:
            if "{" in user_prompt:
                start = user_prompt.find("{")
                depth = 0
                for i, char in enumerate(user_prompt[start:], start):
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            json_str = user_prompt[start : i + 1]
                            data = json.loads(json_str)
                            # Extract relevant fields
                            for key in ["run_id", "agent_id", "branch", "base_head_event", "query"]:
                                if key in data:
                                    context[key] = data[key]
                            break
        except (json.JSONDecodeError, ValueError):
            pass

        return context

    def _extract_context_from_messages(self, messages: list[Message]) -> dict[str, Any]:
        """Extract context from conversation messages.

        Looks for system/user messages containing JSON context.
        """
        context: dict[str, Any] = {}

        for msg in messages:
            if msg.content and msg.role in ("system", "user"):
                parsed = self._parse_user_prompt_context(msg.content)
                context.update(parsed)

        return context

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ):
        """Stream a chat turn chunk by chunk (M6-T7).

        Stub implementation simulates streaming by:
        1. Yielding rationale text character by character (or in small chunks)
        2. Yielding final chunk with tool call

        For testing, this provides a simple way to verify streaming logic.
        """
        # Get the full chat result first
        result = self.chat(messages, tools)

        if result.error:
            yield StreamChunk(error=result.error, finished=True)
            return

        # Simulate streaming the rationale text if available
        if result.message and result.message.content:
            content = result.message.content
            # Yield in small chunks to simulate streaming
            chunk_size = 10
            for i in range(0, len(content), chunk_size):
                yield StreamChunk(delta=content[i : i + chunk_size])

        # Final chunk with tool calls
        yield StreamChunk(
            tool_calls=result.tool_calls,
            finished=True,
            usage=result.usage,
        )
