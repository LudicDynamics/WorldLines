"""Anthropic-compatible LLM adapter for NeonRP."""

from __future__ import annotations

import json
import logging
from typing import Any

from neonrp.core.config import get_api_key
from neonrp.core.llm import LLMResponse, LLMTurnResult, Message, StreamChunk, ToolCall, extract_proposal_json

logger = logging.getLogger(__name__)


def _normalize_base_url(base_url: str | None) -> str | None:
    """Normalize base URL for Anthropic SDK.

    Some compatible endpoints are provided as /v1/messages. Anthropic SDK appends
    /v1/messages itself, so trim that suffix when present.
    """
    if not base_url:
        return None
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1/messages"):
        return trimmed[: -len("/v1/messages")]
    return trimmed


def _tool_schema_to_anthropic(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert NeonRP/OpenAI-style tool schema into Anthropic tool format."""
    if "function" in tool and isinstance(tool["function"], dict):
        fn = tool["function"]
        return {
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        }

    return {
        "name": tool.get("name", ""),
        "description": tool.get("description", ""),
        "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
    }


def _to_anthropic_messages(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert NeonRP message list to Anthropic messages payload."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == "system":
            if msg.content:
                system_parts.append(msg.content)
            continue

        if msg.role == "tool":
            is_error = False
            content_text = msg.content or ""
            try:
                payload = json.loads(content_text) if content_text else {}
                if isinstance(payload, dict):
                    status = str(payload.get("status", "")).strip().lower()
                    if status in {"error", "failed", "failure"}:
                        is_error = True
                    elif status == "" and payload.get("error"):
                        is_error = True
            except Exception:
                is_error = False
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id or "",
                            "content": content_text,
                            "is_error": is_error,
                        }
                    ],
                }
            )
            continue

        if msg.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if msg.content:
                blocks.append({"type": "text", "text": msg.content})
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
            converted.append({"role": "assistant", "content": blocks if blocks else [{"type": "text", "text": ""}]})
            continue

        # user role
        converted.append({"role": "user", "content": msg.content or ""})

    system_prompt = "\n\n".join([s for s in system_parts if s.strip()]) if system_parts else None
    return system_prompt, converted


def _is_retryable_error(exc: Exception) -> bool:
    """Classify whether an Anthropic API error is retryable.

    The Anthropic SDK already retries transient errors (429, 500, 503) internally
    via max_retries. Errors that reach here have exhausted SDK retries.
    We mark 400 (bad request) and 529 (overloaded) as retryable at the conversation
    loop level — the loop can try to recover by trimming malformed messages.
    """
    try:
        import anthropic
    except ImportError:
        return False

    if isinstance(exc, anthropic.BadRequestError):
        # 400: often caused by malformed message history — loop can trim and retry
        return True
    if isinstance(exc, anthropic.APIStatusError):
        # 529 overloaded, or any 5xx that exhausted SDK retries
        return getattr(exc, "status_code", 0) >= 500
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    return False


class AnthropicAdapter:
    """Anthropic-compatible adapter.

    Works with official Anthropic and Anthropic-compatible endpoints.
    """

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-latest",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str = "anthropic",
        max_retries: int = 3,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = _normalize_base_url(base_url)
        self._api_key = api_key
        self._api_key_env = api_key_env
        self.max_retries = max_retries
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError("anthropic package is required for anthropic adapter. Install with: pip install anthropic") from exc

            api_key = self._api_key or get_api_key(self._api_key_env)
            if not api_key:
                # _api_key_env 可能已是完整变量名(presets 的 api_key_env)——
                # 别再拼一次 _API_KEY 造出不存在的名字。
                env_name = self._api_key_env.upper()
                if not env_name.endswith("_API_KEY"):
                    env_name += "_API_KEY"
                raise ValueError(
                    f"API key not found for '{self._api_key_env}'. "
                    f"Set {env_name} or NEONRP_LLM_API_KEY environment variable."
                )

            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "max_retries": self.max_retries,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def generate(self, system_prompt: str, user_prompt: str, tools: list[dict] | None = None) -> LLMResponse:
        result = self.chat(
            [
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ],
            tools=tools,
        )
        if not result.success or not result.message:
            return LLMResponse(raw_output="", usage=result.usage, error=result.error or "Anthropic API error")
        raw_output = result.message.content or ""
        proposal_text = extract_proposal_json(raw_output)
        if proposal_text is None:
            return LLMResponse(raw_output=raw_output, usage=result.usage, error="Failed to extract valid proposal JSON from LLM response")
        return LLMResponse(proposal_text=proposal_text, raw_output=raw_output, usage=result.usage)

    def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMTurnResult:
        try:
            client = self._get_client()
        except (ImportError, ValueError) as exc:
            return LLMTurnResult(error=str(exc), finished=True)

        system_prompt, anthropic_messages = _to_anthropic_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [_tool_schema_to_anthropic(t) for t in tools]

        from neonrp.core import beat_budget

        if beat_budget.expired():  # the beat is over (core/beat_budget): no call
            beat_budget.note("llm.call")
            return LLMTurnResult(error="beat timeout (llm.call)", finished=True)
        _t = beat_budget.call_timeout()
        if _t is not None and callable(getattr(client, "with_options", None)):
            try:  # inside a beat: this request times out with what is left, and the SDK does not retry on its own
                client = client.with_options(timeout=_t, max_retries=0)
            except Exception:  # noqa: BLE001
                pass
        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:
            retryable = _is_retryable_error(exc)
            logger.warning("Anthropic API error (retryable=%s): %s", retryable, exc)
            return LLMTurnResult(
                error=f"Anthropic API error: {exc}",
                finished=True,
                retryable=retryable,
            )

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "thinking":
                thinking_parts.append(getattr(block, "thinking", "") or "")
            elif block_type == "redacted_thinking":
                # Encrypted thinking — show a marker, not the payload.
                thinking_parts.append("[redacted_thinking]")
            elif block_type == "tool_use":
                arguments = getattr(block, "input", {}) or {}
                if not isinstance(arguments, dict):
                    arguments = {"raw": str(arguments)}
                tool_calls.append(
                    ToolCall(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        arguments=arguments,
                    )
                )

        content = "".join(text_parts).strip() or None
        message = Message(role="assistant", content=content, tool_calls=tool_calls or None)
        usage_obj = getattr(response, "usage", None)
        in_tok = getattr(usage_obj, "input_tokens", 0) if usage_obj else 0
        out_tok = getattr(usage_obj, "output_tokens", 0) if usage_obj else 0
        cache_create = getattr(usage_obj, "cache_creation_input_tokens", 0) if usage_obj else 0
        cache_read = getattr(usage_obj, "cache_read_input_tokens", 0) if usage_obj else 0
        usage = {
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "cache_creation_tokens": cache_create or 0,
            "cache_read_tokens": cache_read or 0,
            "model": getattr(response, "model", "") or self.model,
            "thinking": "\n".join(p for p in thinking_parts if p),
        }

        return LLMTurnResult(
            message=message,
            tool_calls=tool_calls or None,
            finished=not bool(tool_calls),
            usage=usage,
        )

    def chat_stream(self, messages: list[Message], tools: list[dict] | None = None):
        """Best-effort streaming fallback using non-streaming chat()."""
        result = self.chat(messages, tools=tools)
        if not result.success or not result.message:
            yield StreamChunk(error=result.error or "Anthropic API error", finished=True)
            return
        yield StreamChunk(
            delta=result.message.content or "",
            tool_calls=result.tool_calls,
            finished=True,
            usage=result.usage,
        )
