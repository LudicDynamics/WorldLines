"""LLM adapter interface and response types for NeonRP.

Provides the abstraction layer for LLM providers, enabling testing with stub
and supporting multiple real providers.

M6 additions:
- Message: Multi-turn chat message with role, content, tool_calls, tool_call_id
- ToolCall: Structured tool call from LLM
- LLMTurnResult: Result from a single chat turn including tool calls
- chat(): Multi-turn method for agentic loop

M6-T7 additions:
- StreamChunk: Incremental chunk from streaming LLM output
- chat_stream(): Generator-based streaming method
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, Literal, Iterator


@dataclass
class ToolCall:
    """A tool/function call requested by the LLM.

    Attributes:
        id: Unique identifier for this tool call (for matching results)
        name: Tool/function name (e.g., 'read_file', 'submit_proposal')
        arguments: Tool arguments as a dictionary
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """A message in a multi-turn conversation.

    Attributes:
        role: Message role - 'system', 'user', 'assistant', or 'tool'
        content: Text content of the message (may be None for tool calls)
        tool_calls: List of tool calls if role='assistant' and requesting tools
        tool_call_id: For role='tool', the ID of the tool call being responded to
        name: For role='tool', the name of the tool that was called
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    # Reasoning / chain-of-thought emitted by the model (DeepSeek's
    # `reasoning_content`, OpenRouter's `reasoning`, etc.). Persisted so
    # we can pass it back on follow-up turns — DeepSeek's thinking-mode
    # API rejects multi-turn requests that don't echo the prior
    # `reasoning_content` (HTTP 400 invalid_request_error).
    reasoning_content: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to API format for OpenAI-compatible providers."""
        msg: dict[str, Any] = {"role": self.role}

        # Always include "content" for assistant messages — Ollama and other
        # OpenAI-compatible providers may require it even when tool_calls are
        # present.  Official OpenAI API tolerates the key being absent, but
        # compatible providers often don't, causing garbled tool-call arguments
        # on subsequent turns.
        if self.role == "assistant":
            msg["content"] = self.content or ""
        elif self.content is not None:
            msg["content"] = self.content

        # Echo reasoning_content for assistant messages that carry it.
        # Providers that don't recognize the field (OpenAI proper, etc.)
        # silently ignore it; DeepSeek thinking mode requires it.
        if self.role == "assistant" and self.reasoning_content:
            msg["reasoning_content"] = self.reasoning_content

        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in self.tool_calls
            ]

        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id

        if self.name and self.role == "tool":
            msg["name"] = self.name

        return msg


@dataclass
class LLMTurnResult:
    """Result from a single chat turn.

    Attributes:
        message: The assistant's response message
        tool_calls: Extracted tool calls (shortcut to message.tool_calls)
        finished: True if conversation is complete (no tool calls pending)
        usage: Token usage info
        error: Error message if the call failed
    """

    message: Message | None = None
    tool_calls: list[ToolCall] | None = None
    finished: bool = False
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retryable: bool = False

    @property
    def success(self) -> bool:
        """Check if the call was successful."""
        return self.error is None and self.message is not None


@dataclass
class StreamChunk:
    """A chunk of streamed LLM output (M6-T7).

    Attributes:
        delta: New text content in this chunk
        thinking: Model reasoning/thinking text if provider exposes it
        tool_call_starts: Tool names detected early in the stream (before args finish).
            Emitted as soon as the LLM reveals which tool it intends to call,
            allowing the UI to show "calling write_file..." immediately.
        tool_calls: Completed tool calls (only on final chunk typically)
        finished: True on final chunk (stream complete)
        usage: Token usage info (set on final chunk)
        error: Error message if streaming failed
        retryable: Whether the stream error is transient and safe to retry
    """

    delta: str = ""
    thinking: str = ""
    tool_call_starts: list[str] | None = None
    tool_calls: list[ToolCall] | None = None
    finished: bool = False
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retryable: bool = False


@dataclass
class LLMResponse:
    """Response from an LLM adapter (legacy single-turn).

    Attributes:
        proposal_text: Raw proposal JSON text (to be parsed). None if parsing failed.
        raw_output: Full raw LLM output (for logging)
        usage: Token usage info (prompt_tokens, completion_tokens, etc.)
        error: Error message if the call failed
    """

    proposal_text: str | None = None
    raw_output: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if the call was successful."""
        return self.error is None and self.proposal_text is not None


class LLMAdapter(Protocol):
    """Protocol for LLM providers.

    All LLM adapters must implement this interface to work with agent run.

    M6 adds the `chat()` method for multi-turn agentic loops with tool calling.
    """

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Generate a response from the LLM (legacy single-turn).

        Args:
            system_prompt: Agent's system.md content
            user_prompt: Constructed from query + context items
            tools: Skill tool schemas (M3 passes but does NOT process tool calls)

        Returns:
            LLMResponse with proposal text and raw output
        """
        ...

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> LLMTurnResult:
        """Execute one turn of a multi-turn conversation (M6).

        This is the preferred method for agentic loops. It supports tool calling
        and maintains conversation history.

        Args:
            messages: Conversation history as list of Message objects
            tools: Tool schemas for function calling

        Returns:
            LLMTurnResult with assistant response and any tool calls
        """
        ...

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Iterator[StreamChunk]:
        """Stream a chat turn chunk by chunk (M6-T7).

        Yields StreamChunk objects with delta text. The final chunk has
        finished=True and may include tool_calls if the LLM requested them.

        Non-streaming adapters should yield a single chunk with the full
        response content.

        Args:
            messages: Conversation history as list of Message objects
            tools: Tool schemas for function calling

        Yields:
            StreamChunk with incremental content
        """
        ...


def extract_proposal_json(raw_output: str) -> str | None:
    """Extract proposal JSON from raw LLM output.

    Handles cases where proposal is wrapped in markdown code blocks or
    contains extra text before/after the JSON.

    Args:
        raw_output: Raw text from LLM

    Returns:
        Extracted JSON string, or None if no valid JSON found
    """
    text = raw_output.strip()

    # Try direct JSON parse first
    if text.startswith("{"):
        try:
            # Validate it's parseable JSON
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

    # Try to extract from markdown code block
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            json_str = text[start:end].strip()
            try:
                json.loads(json_str)
                return json_str
            except json.JSONDecodeError:
                pass

    # Try to find JSON object boundaries
    if "{" in text and "}" in text:
        start = text.find("{")
        # Find matching closing brace
        depth = 0
        for i, char in enumerate(text[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    json_str = text[start : i + 1]
                    try:
                        json.loads(json_str)
                        return json_str
                    except json.JSONDecodeError:
                        break

    return None


def get_adapter(provider: str, **kwargs: Any) -> LLMAdapter:
    """Factory function to get the appropriate LLM adapter.

    Args:
        provider: Provider name (stub, openai, anthropic, glm, gemini)
        **kwargs: Provider-specific arguments

    Returns:
        LLMAdapter instance

    Raises:
        ValueError: If provider is not supported
    """
    if provider == "stub":
        from neonrp.core.llm_stub import StubAdapter

        return StubAdapter(**kwargs)
    if provider == "openai":
        from neonrp.core.llm_openai import OpenAIAdapter

        return OpenAIAdapter(**kwargs)
    if provider == "anthropic":
        return _create_anthropic_adapter(**kwargs)
    if provider == "glm":
        return _create_glm_adapter(**kwargs)
    if provider == "gemini":
        return _create_gemini_adapter(**kwargs)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def get_adapter_from_config(provider_config: Any, **kwargs: Any) -> LLMAdapter:
    """Factory function to get LLM adapter from ProviderConfig (M8-T5).

    Args:
        provider_config: ProviderConfig from resolve_provider()
        **kwargs: Additional provider-specific arguments (e.g., fixture_path for stub)

    Returns:
        LLMAdapter instance

    Raises:
        ValueError: If provider is not supported
    """
    provider = provider_config.provider

    if provider == "stub":
        from neonrp.core.llm_stub import StubAdapter

        return StubAdapter(**kwargs)
    if provider == "anthropic":
        from neonrp.core.llm_anthropic import AnthropicAdapter

        adapter_kwargs = {
            "model": provider_config.model if provider_config.model else None,
            "temperature": provider_config.temperature,
            "max_tokens": provider_config.max_output_tokens,
        }
        if provider_config.base_url:
            adapter_kwargs["base_url"] = provider_config.base_url
        if provider_config.api_key_env:
            adapter_kwargs["api_key_env"] = provider_config.api_key_env
        if getattr(provider_config, "api_key", None):
            adapter_kwargs["api_key"] = provider_config.api_key
        adapter_kwargs = {k: v for k, v in adapter_kwargs.items() if v is not None}
        return AnthropicAdapter(**adapter_kwargs, **kwargs)

    if provider in ("openai", "glm", "gemini"):
        from neonrp.core.llm_openai import OpenAIAdapter

        # Build adapter kwargs from ProviderConfig
        adapter_kwargs = {
            "model": provider_config.model if provider_config.model else None,
            "temperature": provider_config.temperature,
            "max_tokens": provider_config.max_output_tokens,
        }
        if provider_config.seed is not None:
            adapter_kwargs["seed"] = provider_config.seed
        if provider_config.base_url:
            adapter_kwargs["base_url"] = provider_config.base_url
        if provider_config.api_key_env:
            adapter_kwargs["api_key_env"] = provider_config.api_key_env
        if getattr(provider_config, "api_key", None):
            adapter_kwargs["api_key"] = provider_config.api_key
        if getattr(provider_config, "extra", None):
            adapter_kwargs["extra_kwargs"] = provider_config.extra

        # Use GLM defaults if provider is glm
        if provider == "glm":
            import os

            adapter_kwargs.setdefault(
                "base_url", os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
            )
            adapter_kwargs.setdefault("model", os.environ.get("GLM_MODEL", "glm-4-flash"))
            if not adapter_kwargs.get("api_key_env"):
                adapter_kwargs["api_key_env"] = "glm"
        elif provider == "gemini":
            import os

            adapter_kwargs.setdefault(
                "base_url",
                os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            )
            adapter_kwargs.setdefault("model", os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
            if not adapter_kwargs.get("api_key_env"):
                adapter_kwargs["api_key_env"] = "gemini"

        # Remove None values
        adapter_kwargs = {k: v for k, v in adapter_kwargs.items() if v is not None}

        return OpenAIAdapter(**adapter_kwargs, **kwargs)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _create_glm_adapter(**kwargs: Any) -> "LLMAdapter":
    """Create a GLM (Zhipu AI) adapter using OpenAI-compatible interface.

    Reads configuration from GLM_* environment variables:
        GLM_API_KEY, GLM_BASE_URL, GLM_MODEL, GLM_TEMPERATURE,
        GLM_TOP_P, GLM_MAX_TOKENS, GLM_RESPONSE_FORMAT
    """
    import os
    from neonrp.core.llm_openai import OpenAIAdapter

    base_url = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    model = os.environ.get("GLM_MODEL", "glm-4-flash")
    temperature = float(os.environ.get("GLM_TEMPERATURE", "0.7"))
    max_tokens = int(os.environ.get("GLM_MAX_TOKENS", "4096"))

    extra: dict[str, Any] = {}
    top_p = os.environ.get("GLM_TOP_P")
    if top_p is not None:
        extra["top_p"] = float(top_p)
    resp_fmt = os.environ.get("GLM_RESPONSE_FORMAT")
    if resp_fmt:
        extra["response_format"] = {"type": resp_fmt}

    return OpenAIAdapter(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=base_url,
        api_key_env="glm",
        extra_kwargs=extra if extra else None,
        **kwargs,
    )


def _create_gemini_adapter(**kwargs: Any) -> "LLMAdapter":
    """Create a Gemini adapter via Google's OpenAI-compatible endpoint."""
    import os
    from neonrp.core.llm_openai import OpenAIAdapter

    adapter_kwargs: dict[str, Any] = {
        "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "temperature": float(os.environ.get("GEMINI_TEMPERATURE", "0.7")),
        "max_tokens": int(os.environ.get("GEMINI_MAX_TOKENS", "4096")),
        "base_url": os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        "api_key_env": "gemini",
    }
    adapter_kwargs.update(kwargs)
    return OpenAIAdapter(**adapter_kwargs)


def _create_anthropic_adapter(**kwargs: Any) -> "LLMAdapter":
    """Create an Anthropic-compatible adapter."""
    from neonrp.core.llm_anthropic import AnthropicAdapter

    adapter_kwargs: dict[str, Any] = {
        "model": "claude-3-5-sonnet-latest",
        "temperature": 0.7,
        "max_tokens": 4096,
        "api_key_env": "anthropic",
    }
    adapter_kwargs.update(kwargs)
    return AnthropicAdapter(**adapter_kwargs)
