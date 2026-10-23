"""OpenAI-compatible LLM adapter for NeonRP.

Provides integration with OpenAI and OpenAI-compatible APIs (GLM, etc.).
"""

import contextlib
import contextvars
import json
import logging
import os
import random
import sys
import time
import inspect
import uuid
from datetime import datetime, timezone
from typing import Any

from neonrp.core.llm import LLMResponse, LLMTurnResult, Message, ToolCall, extract_proposal_json
from neonrp.core import beat_budget, llm_inflight
from neonrp.core.beat_budget import BeatTimeout
from neonrp.core.llm_errors import AuthError, BillingError, InvalidResponseError, RetryableError
from neonrp.core.config import get_api_key

logger = logging.getLogger(__name__)
raw_logger = logging.getLogger("neonrp.raw_json")
_LOG_STREAM_TOOL_DELTAS = str(os.getenv("NEONRP_LOG_STREAM_TOOL_DELTAS", "0")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _apply_openai_extra_kwargs(client: Any, kwargs: dict[str, Any], extra_kwargs: dict[str, Any]) -> None:
    """Apply custom kwargs safely for OpenAI SDK.

    New/unknown provider fields (e.g. OpenRouter `reasoning`) can raise
    "unexpected keyword argument" on strict SDK signatures. Route unknown keys
    via `extra_body` so they are still sent to compatible endpoints.
    """
    if not extra_kwargs:
        return

    accepted_keys: set[str] = set()
    try:
        sig = inspect.signature(client.chat.completions.create)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
                accepted_keys.add(name)
    except Exception:
        accepted_keys = set()

    extra_body = kwargs.get("extra_body")
    if not isinstance(extra_body, dict):
        extra_body = {}

    for key, value in extra_kwargs.items():
        if key in accepted_keys:
            kwargs[key] = value
        else:
            extra_body[key] = value

    if extra_body:
        kwargs["extra_body"] = extra_body


_THINK: "contextvars.ContextVar[bool]" = contextvars.ContextVar("neonrp_llm_thinking", default=True)


@contextlib.contextmanager
def thinking(on: bool) -> Any:
    """Calls made inside ask the provider to think first (True, its default) or to write at once (False). 10-19 N2:
    deepseek-v4-flash thought 10–100 s before the world's first word in a quarter to a half of the narration calls
    (the 30 s turn ran out with nothing on screen); without thinking the first word comes in about a second."""
    tok = _THINK.set(bool(on))
    try:
        yield
    finally:
        _THINK.reset(tok)


def can_turn_thinking_off(adapter: Any) -> bool:
    """The provider behind ``adapter`` takes a per-request switch for thinking (the ones :func:`_think_off` knows)."""
    with thinking(False):
        return bool(_think_off(getattr(adapter, "base_url", None)))


def _think_off(base_url: str | None) -> dict[str, Any]:
    """The request field that turns thinking off, for the providers known to take one; others: nothing is sent."""
    if _THINK.get():
        return {}
    u = str(base_url or "")
    if "deepseek.com" in u:
        return {"thinking": {"type": "disabled"}}
    if "siliconflow" in u:
        return {"enable_thinking": False}
    return {}


def _merge_streamed_arguments(existing: str, fragment: str) -> str:
    """Merge streamed function arguments from OpenAI-compatible providers.

    Some providers stream argument deltas; others stream cumulative snapshots.
    This helper accepts both styles and avoids duplicated JSON fragments.
    """
    if not fragment:
        return existing
    if not existing:
        return fragment

    # Cumulative style: each fragment contains the full content so far.
    if fragment.startswith(existing):
        return fragment

    # Duplicate retransmission.
    if existing.endswith(fragment):
        return existing

    # Sometimes provider sends a longer full snapshot that includes previous.
    if len(fragment) > len(existing) and existing in fragment:
        return fragment

    # Delta style with overlap: append only non-overlapping tail.
    max_overlap = min(len(existing), len(fragment))
    for overlap in range(max_overlap, 0, -1):
        if existing.endswith(fragment[:overlap]):
            return existing + fragment[overlap:]

    # Fallback: plain append (best effort).
    return existing + fragment


def _finalize_streamed_arguments(fragments: list[str], merged_fallback: str = "") -> str:
    """Reconstruct streamed function arguments from raw fragments.

    OpenAI-compatible providers typically use one of two styles:
    1) Cumulative snapshots: each fragment contains full args-so-far.
    2) Delta chunks: each fragment is the next literal slice.

    We choose style by inspecting fragment progression. For delta mode, we
    preserve repeated adjacent fragments (e.g. '/player' + '/player').
    """
    cleaned = [str(f) for f in fragments if isinstance(f, str) and f]
    if not cleaned:
        return merged_fallback
    if len(cleaned) == 1:
        return cleaned[0]

    cumulative_votes = 0
    for i in range(1, len(cleaned)):
        if cleaned[i].startswith(cleaned[i - 1]):
            cumulative_votes += 1

    # If most fragments look cumulative, pick the longest/fullest snapshot.
    if cumulative_votes >= ((len(cleaned) - 1) * 2) // 3:
        return max(cleaned, key=len)

    # Delta mode: concatenate raw slices directly; do not dedupe suffix repeats.
    return "".join(cleaned)


def _tool_calls_need_recovery(tool_calls: list[ToolCall]) -> bool:
    """Detect likely-incomplete streamed tool calls that need recovery.

    Some compatible providers end with a tool shell (name/id) but missing args,
    or return non-JSON argument fragments that decode as {"raw": ...}.
    """
    if not tool_calls:
        return False

    for tc in tool_calls:
        if not tc.name:
            return True
        if not isinstance(tc.arguments, dict):
            return True
        if "raw" in tc.arguments:
            return True
        if not tc.arguments:
            return True
    return False


def _preview_log_text(value: Any, max_len: int = 220) -> str:
    try:
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
    text = text.replace("\n", "\\n")
    if len(text) > max_len:
        return f"{text[:max_len]}...(+{len(text) - max_len} chars)"
    return text


def _to_jsonable(value: Any) -> Any:
    """Best-effort conversion to JSON-serializable structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]

    for method_name in ("model_dump", "dict", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                dumped = method()
                return _to_jsonable(dumped)
            except Exception:
                pass

    model_dump_json = getattr(value, "model_dump_json", None)
    if callable(model_dump_json):
        try:
            return json.loads(model_dump_json())
        except Exception:
            pass

    return str(value)


# 10-05 C0-11: every response's token usage, summed in-process (the one place every call passes) — the benchmarks and
# the test checklist read it per beat / per run; the raw log keeps the per-call record as before
USAGE: dict[str, int] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cache_hit_tokens": 0}


def usage_snapshot() -> dict[str, int]:
    return dict(USAGE)


def _meter(event: str, payload: dict[str, Any]) -> None:
    if not event.endswith(".response"):
        return
    u = ((payload.get("response_merged") or {}).get("usage") or {}) if isinstance(payload.get("response_merged"), dict) else {}
    if not u:
        return
    USAGE["calls"] += 1
    USAGE["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
    USAGE["completion_tokens"] += int(u.get("completion_tokens") or 0)
    hit = u.get("prompt_cache_hit_tokens")
    if hit is None:
        raw = payload.get("response_raw")
        ru = (getattr(raw, "usage", None) or (raw.get("usage") if isinstance(raw, dict) else None)) if raw is not None else None
        if ru is not None:
            hit = (ru.get("prompt_cache_hit_tokens") if isinstance(ru, dict) else getattr(ru, "prompt_cache_hit_tokens", None)) or 0
    USAGE["cache_hit_tokens"] += int(hit or 0)


def _emit_raw_json(event: str, request_id: str, payload: dict[str, Any]) -> None:
    """Append a structured raw LLM record to neonrp.raw_json logger."""
    try:
        _meter(event, payload)
    except Exception:  # noqa: BLE001 — metering never breaks a call
        pass
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "request_id": request_id,
        **payload,
    }
    try:
        raw_logger.info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:
        logger.debug("Failed to write raw LLM audit log", exc_info=True)


def _classify_openai_error(e: Exception) -> Exception:
    """Map an openai SDK exception to a NeonRP LLMError type."""
    # Check built-in Python connection/OS errors first (before openai-specific)
    # This catches plain ConnectionError, TimeoutError, etc. from network layers
    if isinstance(e, (ConnectionError, TimeoutError, OSError)):
        return RetryableError(str(e))

    # httpx exceptions are common when a provider drops mid-stream
    # (DeepSeek does this frequently). Same prompt usually succeeds on
    # retry, so classify as retryable.
    try:
        import httpx
        if isinstance(e, (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError)):
            return RetryableError(str(e))
    except ImportError:
        pass

    try:
        import openai
    except ImportError:
        return e

    # A money refusal from ai.worldlines.gg (402 / 403 / 429 + billing_url): the player has to act, so never retry it.
    # Duck-typed on status_code + body (an APIStatusError) so a plain rate limit below stays retryable.
    from neonrp.core import billing_stop

    stop = billing_stop.remember(billing_stop.from_exception(e))
    if stop is not None:
        return BillingError(stop, status_code=getattr(e, "status_code", None))
    if isinstance(e, openai.RateLimitError):
        return RetryableError(str(e), status_code=429)
    if isinstance(e, openai.APITimeoutError):
        return RetryableError(str(e))
    if isinstance(e, openai.APIConnectionError):
        return RetryableError(str(e))
    if isinstance(e, openai.InternalServerError):
        return RetryableError(str(e), status_code=getattr(e, "status_code", 500))
    if isinstance(e, openai.AuthenticationError):
        return AuthError(
            f"Authentication failed. Check your API key. Details: {e}",
            status_code=401,
        )
    if isinstance(e, openai.BadRequestError):
        return InvalidResponseError(str(e), status_code=400)
    return e



class StreamStalled(RuntimeError):
    """The provider kept the connection open but stopped producing tokens (10-15)."""


def _stall_limits() -> tuple[float, float, int]:
    """(seconds to the first token, seconds between tokens, extra tries). 「deepseek 理论上 cot 和中断状态我们
    都能检测到,不能干等」 — a healthy deepseek stream starts within ~3 s (reasoning first) and pauses under 1 s; on
    10-13 one call in ten sat 60–75 s (the provider holding the request with keep-alives), so the wait is cut short.
    Mid-stream there is no limit by default (0 = off; a dead stream ends at the client's read timeout): deepseek often
    pauses 5–30 s mid-reasoning and goes on (10-16: ~150 such pauses in one benchmark run), and a cut restarts the whole
    reasoning — 237 cuts at 30 s cost more than they saved. Pauses that recover are logged."""
    def num(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, default))
        except ValueError:
            return default
    return num("NEONRP_LLM_FIRST_TOKEN_S", 20), num("NEONRP_LLM_STALL_GAP_S", 0), int(num("NEONRP_LLM_STALL_RETRIES", 2))


def _wl_signin_message() -> str:
    """What a Worldlines call says when there is no usable session: expired (signed in before) or never signed in. The
    marker words are what the frontends look for (session_expired / session_required → a sign-in prompt, not "no model")."""
    from neonrp.core import worldlines_auth as _wla

    if _wla.session_expired():
        return "session_expired: the Worldlines sign-in has expired — sign in again"
    return "session_required: sign in with a Worldlines account"


def _closing(stream: Any) -> Any:
    """Iterate an SDK stream and close it when the loop ends — normally, by an exception, or when the consumer closes
    us. Left to the garbage collector, an unclosed stream's close() can run *inside* the next request while that request
    holds the shared connection pool's lock (httpcore's Lock is not re-entrant) → the thread waits on itself forever
    (10-11, benchmark hang: GC → openai __stream__ → response.close → ConnectionPool.close, under handle_request).
    While it runs the stream is registered in core/llm_inflight (each chunk marks it): a host can see a stream that
    went quiet across an app suspension and cut it (iOS, 10-18)."""
    tok = llm_inflight.begin("stream")
    llm_inflight.attach(tok, getattr(stream, "response", None))
    try:
        for chunk in stream:
            llm_inflight.touch(tok)
            yield chunk
    finally:
        llm_inflight.end(tok)
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 — closing a broken stream must not raise over the real error
                logger.debug("stream close failed", exc_info=True)

class OpenAIAdapter:
    """OpenAI-compatible API adapter.

    Works with OpenAI, GLM (Zhipu AI), and other OpenAI-compatible endpoints.
    Requires openai package to be installed.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        seed: int | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str = "openai",
        extra_kwargs: dict[str, Any] | None = None,
        max_retries: int = 3,
    ):
        """Initialize OpenAI-compatible adapter.

        Args:
            model: Model name (default: gpt-4o-mini)
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            seed: Optional seed for reproducibility
            base_url: Custom API base URL (for OpenAI-compatible services)
            api_key: Direct API key (overrides env lookup)
            api_key_env: Provider name for env var lookup (default: "openai")
            extra_kwargs: Extra parameters for the API call (e.g. top_p, response_format)
            max_retries: Maximum retry attempts for transient errors (default: 3)
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.seed = seed
        self.base_url = base_url
        self._api_key = api_key
        self._api_key_env = api_key_env
        self.extra_kwargs = extra_kwargs or {}
        self.max_retries = max_retries

        # Lazy import to avoid requiring openai unless used
        self._client = None

    def _create(self, client: Any, kwargs: dict[str, Any]) -> Any:
        """``chat.completions.create`` that also records the upstream ``x-request-id`` (ai.worldlines.gg sends one per
        response — the turn binds local records to api usage). Falls back to the plain call."""
        from neonrp.core import request_ids, worldlines_auth

        if self._client is not None and client is not self._client and getattr(client, "api_key", None) != getattr(self._client, "api_key", None):
            client = self._client  # renewed after a 401 (_renew_after_401): this call was built with the refused token
        client = self._beat_client(client, stream=bool(kwargs.get("stream")))
        if worldlines_auth.is_worldlines(self.base_url) and worldlines_auth.world_header():  # which world (billing: run points)
            kwargs = {**kwargs, "extra_headers": {**(kwargs.get("extra_headers") or {}), **worldlines_auth.world_header()}}
        raw_api = getattr(client.chat.completions, "with_raw_response", None)
        if raw_api is None or kwargs.get("stream") or not worldlines_auth.is_worldlines(self.base_url):
            return client.chat.completions.create(**kwargs)  # only ai.worldlines.gg sends ids worth binding
        raw = raw_api.create(**kwargs)
        try:
            rid = raw.headers.get("x-request-id") or raw.headers.get("X-Request-Id")
        except Exception:  # noqa: BLE001
            rid = None
        request_ids.add(rid, kind="llm", model=self.model)
        return raw.parse()

    @staticmethod
    def _beat_client(client: Any, *, stream: bool) -> Any:
        """Inside a beat (core/beat_budget): this request times out with what is left of the beat (a stream: no chunk for
        ``stall`` seconds = stalled), and the SDK does not retry on its own — our ladder decides whether there is time.
        Outside a beat the client is used as configured."""
        t = beat_budget.call_timeout()
        if t is None:
            return client
        if t <= 0:
            beat_budget.check("llm.call")
        opts = getattr(client, "with_options", None)
        if not callable(opts) or type(client).__module__.startswith("unittest.mock"):  # a test's mock client: as it is
            return client
        try:
            import httpx

            # the browser (Pyodide) has no real stream: its transport is one synchronous XHR whose timeout is `read`, so a
            # stall limit there would cut a whole healthy reply at 15 s (browser-play 10-14: 15 015 ms, then 3.5 s left)
            gap = min(beat_budget.stall_s(), t) if stream and sys.platform != "emscripten" else t
            timeout: Any = httpx.Timeout(t, connect=min(10.0, t), read=gap)
        except Exception:  # noqa: BLE001 — no httpx: a plain number
            timeout = t
        try:
            return opts(timeout=timeout, max_retries=0)
        except Exception:  # noqa: BLE001 — an SDK without per-request options: as configured
            return client

    def _renew_after_401(self) -> bool:
        """The session's access token was refused: renew it (core/worldlines_auth.refresh_now) and rebuild the client."""
        from neonrp.core import worldlines_auth as _wla

        fresh = _wla.refresh_now(getattr(self, "_wl_token", None))
        if not fresh:
            return False
        self._client = None
        self._wl_token = None
        self._get_client()
        return True

    def _get_client(self) -> Any:
        """Get or create OpenAI client."""
        from neonrp.core import worldlines_auth as _wla

        if self._client is not None and getattr(self, "_wl_token", None) and not self._api_key:
            fresh = _wla.access_token()  # the connect session rotates every 15 min: rebuild the client when it does
            if fresh and fresh != self._wl_token:
                self._client = None
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError("openai package is required for OpenAI adapter. Install with: pip install openai")

            api_key = self._api_key or get_api_key(self._api_key_env)
            from neonrp.core import worldlines_auth as _wla

            if not api_key and _wla.is_worldlines(self.base_url):  # ai.worldlines.gg: a PAT or the connect session
                api_key = _wla.access_token()
                self._wl_token = api_key
                if not api_key:  # ValueError like any missing key (callers already turn it into an error answer)
                    raise ValueError(_wl_signin_message())
            if not api_key:
                # _api_key_env 可能已是完整变量名(presets 的 api_key_env,如
                # OPENCODE_ZEN_API_KEY)——别再拼一次 _API_KEY 造出不存在的名字。
                env_name = self._api_key_env.upper()
                if not env_name.endswith("_API_KEY"):
                    env_name += "_API_KEY"
                raise ValueError(
                    f"API key not found for '{self._api_key_env}'. "
                    f"Set {env_name} or NEONRP_LLM_API_KEY environment variable."
                )

            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            # 显式超时(2026-08-11 真机卡死复盘):SDK 缺省 600s/次 +
            # 内部重试,一条挂死的流要干等十分钟以上,TUI 表现为永远
            # "waiting for model response"。read = 流式块间最大间隔——
            # 超过即断开,交给引擎自己的重试梯(API_RETRY_DELAYS_S)。
            try:
                import httpx

                client_kwargs["timeout"] = httpx.Timeout(
                    float(os.environ.get("NEONRP_LLM_TOTAL_TIMEOUT", "600")),
                    connect=float(os.environ.get("NEONRP_LLM_CONNECT_TIMEOUT", "15")),
                    # 回合"没有响应"根因=deepseek 频繁
                    # mid-stream drop(见 _classify_openai_error 注释),原 180s read
                    # timeout 让每次 drop 干等 3 分钟才重试,一回合多次调用 → 拖到
                    # "没有响应"。健康流式块间隔 <1s,60s 必是 drop → 降到 60s 让
                    # 重试快 3 倍。可用 NEONRP_LLM_READ_TIMEOUT 覆盖。
                    read=float(os.environ.get("NEONRP_LLM_READ_TIMEOUT", "60")),
                )
            except Exception:  # noqa: BLE001 — 超时配置失败不挡请求
                pass

            # OpenRouter attributes traffic to apps via `HTTP-Referer`
            # + `X-Title` headers. Without them our calls show up as
            # anonymous on OpenRouter's per-app leaderboard. Inject
            # both when we recognise the base_url. Harmless on any
            # other OpenAI-compatible provider (extra headers are
            # ignored).
            if self.base_url and "openrouter.ai" in self.base_url:
                client_kwargs["default_headers"] = {
                    "HTTP-Referer": "https://worldlines.gg",
                    "X-Title": "WorldLines",
                }
            if _wla.is_worldlines(self.base_url):
                client_kwargs["default_headers"] = {**client_kwargs.get("default_headers", {}), **_wla.headers()}
                # the SDK would retry a 429 quota_exceeded twice on its own; our ladder (_call_with_retry) retries
                # what is really transient and stops on a BillingError
            # one retry ladder, ours (10-14): the SDK's own (2 retries per call) under our 3 made a stalled request wait
            # 3 × 60 s read timeout before our ladder even saw it — the 189 s state transition of the 10-13 benchmark
            client_kwargs["max_retries"] = 0

            self._client = openai.OpenAI(**client_kwargs)

        return self._client

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Generate a response from OpenAI.

        Args:
            system_prompt: Agent's system.md content
            user_prompt: Constructed from query + context items
            tools: Skill tool schemas (passed but not processed in M3)

        Returns:
            LLMResponse with proposal text and raw output
        """
        try:
            client = self._get_client()
        except (ImportError, ValueError) as e:
            return LLMResponse(raw_output="", error=str(e))

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        try:
            # Build API call parameters
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            if self.seed is not None:
                kwargs["seed"] = self.seed

            # Merge extra kwargs (e.g. top_p, response_format, provider-specific custom fields)
            _apply_openai_extra_kwargs(client, kwargs, {**self.extra_kwargs, **_think_off(self.base_url)})

            # M3: tools passed but not processed (for schema exposure to LLM)
            # Tool calling loop deferred to M3.5+
            if tools:
                kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]

            response = self._create(client, kwargs)

            # Extract response content
            raw_output = response.choices[0].message.content or ""

            # Extract proposal JSON from response
            proposal_text = extract_proposal_json(raw_output)

            # Build usage info
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "prompt_cache_hit_tokens": int(getattr(response.usage, "prompt_cache_hit_tokens", 0) or 0),
                }

            if proposal_text is None:
                return LLMResponse(
                    raw_output=raw_output, usage=usage, error="Failed to extract valid proposal JSON from LLM response"
                )

            return LLMResponse(proposal_text=proposal_text, raw_output=raw_output, usage=usage)

        except Exception as e:
            return LLMResponse(raw_output="", error=f"OpenAI API error: {e}")

    def _call_with_retry(self, api_call, error_prefix: str = "OpenAI API error"):
        """Execute an API call with exponential backoff retry for transient errors.

        Args:
            api_call: Callable that makes the API request
            error_prefix: Prefix for error messages

        Returns:
            The API response

        Raises:
            AuthError: On authentication failure (no retry)
            InvalidResponseError: On bad request (no retry)
            RetryableError: After exhausting all retries
            Exception: On unknown errors
        """
        last_error = None
        for attempt in range(self.max_retries + 1):
            beat_budget.check("llm.call" if attempt == 0 else "llm.retry")  # the beat is over: no call (core/beat_budget)
            try:
                return api_call()
            except BeatTimeout:
                raise
            except Exception as e:
                classified = _classify_openai_error(e)
                if isinstance(classified, RetryableError):
                    last_error = classified
                    _left = beat_budget.remaining()
                    if _left is not None and _left < beat_budget.MIN_RETRY_S:  # no time for another try in this beat
                        beat_budget.note("llm.call", error=str(classified)[:120])
                        raise BeatTimeout(f"beat timeout after: {classified}") from e
                    if attempt < self.max_retries:
                        backoff = (2**attempt) + random.uniform(0, 1)
                        if _left is not None:
                            backoff = min(backoff, max(0.0, _left - beat_budget.MIN_RETRY_S) / 2)
                        logger.warning(
                            "Retryable error (attempt %d/%d): %s. Retrying in %.1fs...",
                            attempt + 1,
                            self.max_retries,
                            str(classified)[:200],
                            backoff,
                        )
                        time.sleep(backoff)
                        continue
                    # Exhausted retries
                    raise RetryableError(f"{error_prefix} after {self.max_retries} retries: {classified}") from e
                elif isinstance(classified, AuthError) and getattr(self, "_wl_token", None) and not self._api_key:
                    # ai.worldlines.gg refused the session's token (expired / revoked, niko 10-19 iOS): renew it once and
                    # send the same request again; renewal refused = the player has to sign in again (said so, not "no model")
                    if self._renew_after_401():
                        try:
                            return api_call()  # the same request, once, with the renewed token (_create picks the new client)
                        except Exception as e2:  # noqa: BLE001
                            c2 = _classify_openai_error(e2)
                            if isinstance(c2, AuthError):
                                raise AuthError(_wl_signin_message(), status_code=401) from e2
                            raise c2 if c2 is not e2 else e2
                    raise AuthError(_wl_signin_message(), status_code=401) from e
                elif isinstance(classified, (AuthError, BillingError, InvalidResponseError)):
                    raise classified from e
                else:
                    raise
        # Should not reach here, but just in case
        raise last_error if last_error else RuntimeError("Unexpected retry loop exit")

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> LLMTurnResult:
        """Execute one turn of a multi-turn conversation (M6).

        This method supports the agentic loop with tool calling.
        Includes retry logic for transient API errors.

        Args:
            messages: Conversation history as list of Message objects
            tools: Tool schemas for function calling

        Returns:
            LLMTurnResult with assistant response and any tool calls
        """
        if not tools and self._chat_via_stream():
            got = self._chat_collected(messages)
            if got is not None:
                return got
        try:
            client = self._get_client()
        except (ImportError, ValueError) as e:
            return LLMTurnResult(error=str(e), finished=True)

        # Convert Message objects to API format
        api_messages = [msg.to_api_dict() for msg in messages]

        # Log message summary for diagnosing conversation flow
        if logger.isEnabledFor(logging.DEBUG):
            msg_summary = []
            for i, m in enumerate(api_messages):
                role = m.get("role", "?")
                content_len = len(m.get("content", "") or "")
                has_tc = bool(m.get("tool_calls"))
                tc_id = m.get("tool_call_id", "")
                msg_summary.append(f"[{i}]{role}(c={content_len},tc={has_tc},tcid={tc_id!r})")
            logger.debug("chat() sending %d messages: %s", len(api_messages), " ".join(msg_summary))

        # Build API call parameters
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if self.seed is not None:
            kwargs["seed"] = self.seed

        _apply_openai_extra_kwargs(client, kwargs, {**self.extra_kwargs, **_think_off(self.base_url)})

        # Add tools if provided
        if tools:
            kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]

        request_id = uuid.uuid4().hex
        _emit_raw_json(
            "openai.chat.request",
            request_id,
            {
                "provider": "openai",
                "mode": "chat",
                "model": self.model,
                "base_url": self.base_url,
                "payload": _to_jsonable(kwargs),
            },
        )

        try:
            response = self._call_with_retry(
                lambda: self._create(client, kwargs),
                error_prefix="Chat API error",
            )

            choice = response.choices[0]
            api_message = choice.message

            # Log full response summary for diagnosing non-streaming issues
            logger.debug(
                "chat() response: finish_reason=%s content_len=%d tool_calls=%s",
                choice.finish_reason,
                len(api_message.content or ""),
                len(api_message.tool_calls) if api_message.tool_calls else 0,
            )

            # Build usage info
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "prompt_cache_hit_tokens": int(getattr(response.usage, "prompt_cache_hit_tokens", 0) or 0),
                }

            # 截断自动续写:创作世界/角色的长输出高频撞 max_tokens(DeepSeek
            # 实测)。仅纯文本截断(finish_reason=length 且无 tool_calls)时,
            # 携带已产出部分续请求,最多 2 轮无缝拼接;工具调用截断走下方
            # 既有恢复路径,不在此处理。
            content_text = api_message.content or ""
            _cont_round = 0
            while (
                choice.finish_reason == "length"
                and not api_message.tool_calls
                and _cont_round < 2
                and getattr(self, "continue_on_length", True)  # a caller that asked for a short reply keeps the cut
                and not beat_budget.expired(beat_budget.MIN_RETRY_S)  # in a beat with no time left: keep what came
            ):
                _cont_round += 1
                logger.info(
                    "chat() hit max_tokens; auto-continue round %d (len=%d)",
                    _cont_round,
                    len(content_text),
                )
                cont_kwargs = dict(kwargs)
                cont_kwargs["messages"] = list(kwargs["messages"]) + [
                    {"role": "assistant", "content": content_text},
                    {
                        "role": "user",
                        "content": (
                            "(你的上一条输出因长度限制被截断。从截断处无缝继续,"
                            "不要重复已输出的内容,不要任何解释或开场白。)"
                        ),
                    },
                ]
                response = self._call_with_retry(
                    lambda k=cont_kwargs: self._create(client, k),
                    error_prefix="Chat API error (auto-continue)",
                )
                choice = response.choices[0]
                api_message = choice.message
                content_text += api_message.content or ""
                if response.usage:
                    usage = {
                        "prompt_tokens": usage.get("prompt_tokens", 0)
                        + response.usage.prompt_tokens,
                        "completion_tokens": usage.get("completion_tokens", 0)
                        + response.usage.completion_tokens,
                        "total_tokens": usage.get("total_tokens", 0)
                        + response.usage.total_tokens,
                    }

            # Extract tool calls if any
            tool_calls: list[ToolCall] = []
            if api_message.tool_calls:
                for tc in api_message.tool_calls:
                    logger.debug(
                        "chat() raw tool_call: id=%s name=%s args=%r content=%r",
                        tc.id,
                        tc.function.name,
                        tc.function.arguments,
                        getattr(api_message, "content", None),
                    )
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": tc.function.arguments}

                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=arguments,
                        )
                    )

            # Capture provider-emitted reasoning_content (DeepSeek thinking
            # mode, etc.) so the next turn can echo it back. The OpenAI
            # SDK exposes vendor-extension fields as attributes on the
            # message object when present; absent for vanilla OpenAI.
            reasoning_text = getattr(api_message, "reasoning_content", None)
            if reasoning_text is None:
                reasoning_text = getattr(api_message, "reasoning", None)
            if reasoning_text is not None and not isinstance(reasoning_text, str):
                reasoning_text = str(reasoning_text)

            # Build Message object for response
            assistant_msg = Message(
                role="assistant",
                content=(content_text or None) if _cont_round else api_message.content,
                tool_calls=tool_calls if tool_calls else None,
                reasoning_content=reasoning_text or None,
            )

            _emit_raw_json(
                "openai.chat.response",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat",
                    "model": self.model,
                    "base_url": self.base_url,
                    "response_raw": _to_jsonable(response),
                    "response_merged": {
                        "finish_reason": choice.finish_reason,
                        "message": {
                            "role": "assistant",
                            "content": api_message.content,
                            "tool_calls": [
                                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                                for tc in tool_calls
                            ],
                        },
                        "usage": usage,
                    },
                },
            )

            # Determine if finished (no tool calls = finished)
            finished = len(tool_calls) == 0 and choice.finish_reason == "stop"

            return LLMTurnResult(
                message=assistant_msg,
                tool_calls=tool_calls if tool_calls else None,
                finished=finished,
                usage=usage,
            )

        except BeatTimeout as e:  # the beat ran out (core/beat_budget): a failed call, the caller's fallback runs
            _emit_raw_json("openai.chat.error", request_id, {"provider": "openai", "mode": "chat", "model": self.model,
                                                             "base_url": self.base_url, "error": str(e), "error_type": "BeatTimeout"})
            return LLMTurnResult(error=str(e), finished=True)
        except AuthError as e:
            _emit_raw_json(
                "openai.chat.error",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat",
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": f"Authentication failed: {e}",
                    "error_type": "AuthError",
                },
            )
            return LLMTurnResult(error=f"Authentication failed: {e}", finished=True)
        except BillingError as e:
            _emit_raw_json("openai.chat.error", request_id, {"provider": "openai", "mode": "chat", "model": self.model,
                                                             "base_url": self.base_url, "error": str(e), "error_type": "BillingError"})
            return LLMTurnResult(error=str(e), finished=True)
        except RetryableError as e:
            _emit_raw_json(
                "openai.chat.error",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat",
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": f"API error after retries: {e}",
                    "error_type": "RetryableError",
                },
            )
            return LLMTurnResult(error=f"API error after retries: {e}", finished=True, retryable=True)
        except InvalidResponseError as e:
            _emit_raw_json(
                "openai.chat.error",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat",
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": f"Invalid request: {e}",
                    "error_type": "InvalidResponseError",
                },
            )
            return LLMTurnResult(error=f"Invalid request: {e}", finished=True)
        except Exception as e:
            classified = _classify_openai_error(e)
            if isinstance(classified, RetryableError):
                _emit_raw_json(
                    "openai.chat.error",
                    request_id,
                    {
                        "provider": "openai",
                        "mode": "chat",
                        "model": self.model,
                        "base_url": self.base_url,
                        "error": f"OpenAI API error: {classified}",
                        "error_type": "RetryableError",
                    },
                )
                return LLMTurnResult(error=f"OpenAI API error: {classified}", finished=True, retryable=True)
            if isinstance(classified, BillingError):
                return LLMTurnResult(error=str(classified), finished=True)
            _emit_raw_json(
                "openai.chat.error",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat",
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": f"OpenAI API error: {e}",
                    "error_type": type(e).__name__,
                },
            )
            return LLMTurnResult(error=f"OpenAI API error: {e}", finished=True)

    def _chat_via_stream(self) -> bool:
        """A plain (no-tool) chat is collected from the guarded stream (10-15): a one-shot call shows no progress, so a
        provider holding it (keep-alives, no tokens) can only be waited out. ai.worldlines.gg stays one-shot — its
        response carries the x-request-id the turn binds usage to. NEONRP_LLM_CHAT_VIA_STREAM=0 turns it off."""
        from neonrp.core import worldlines_auth as _wla

        if os.environ.get("NEONRP_LLM_CHAT_VIA_STREAM", "1").strip().lower() in ("0", "off", "false", "no"):
            return False
        if beat_budget.call_timeout() is not None:  # inside a beat its budget times the call (and its stall) on its own
            return False
        if type(getattr(self, "_client", None)).__module__.startswith("unittest.mock"):  # a test's mock client: as it is
            return False
        return not _wla.is_worldlines(self.base_url)

    def _chat_collected(self, messages: list[Message]) -> LLMTurnResult | None:
        """The guarded stream gathered into one result; None (the caller's one-shot path) if it stalled every time."""
        content: list[str] = []
        thinking: list[str] = []
        usage: dict[str, Any] = {}
        error: str | None = None
        retryable = False
        try:
            for ch in self.chat_stream(messages):
                if ch.delta:
                    content.append(ch.delta)
                if ch.thinking:
                    thinking.append(ch.thinking)
                if ch.usage:
                    usage = dict(ch.usage)
                if ch.error:
                    error, retryable = ch.error, bool(ch.retryable)
        except StreamStalled as e:
            logger.warning("collected stream stalled after partial output (%s); one-shot call instead", e)
            return None
        if error and not content:
            return None if "stalled" in error else LLMTurnResult(error=error, finished=True, retryable=retryable)
        msg = Message(role="assistant", content="".join(content) or None, reasoning_content="".join(thinking) or None)
        return LLMTurnResult(message=msg, finished=True, usage=usage)

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ):
        """Stream a chat turn, guarded by a stall watch (10-15): a call that stops producing tokens is closed and sent
        again — at once when nothing was yielded yet; after partial output it raises :class:`StreamStalled` so the
        caller can start over rather than keep half a reply."""
        from neonrp.core.llm import StreamChunk

        import queue
        import threading

        if beat_budget.call_timeout() is not None:  # inside a beat: one call, timed by the beat (core/beat_budget), no resend
            yield from self._chat_stream_once(messages, tools)
            return
        first, gap, retries = _stall_limits()
        why = ""
        for attempt in range(retries + 1):
            # The stream is read on its own thread; here we only wait for its next chunk. A dead connection blocks that
            # read until the client's read timeout, and closing it from outside does not wake a blocked recv — so a
            # stalled read is abandoned (its thread ends at that timeout) and the call goes out again. The wait is the
            # provider's alone: time the caller spends on a chunk is not counted. (10-16: the first version shortened
            # the read timeout to 20 s, which itself cut healthy deepseek streams mid-reasoning — 10 of 12 calls.)
            q: queue.Queue = queue.Queue()
            stop = threading.Event()

            def pump(gen=self._chat_stream_once(messages, tools, on_finish=lambda q=q: q.put(("fin", None))), q=q,
                     stop=stop) -> None:
                last = time.monotonic()
                try:
                    for ch in gen:
                        if stop.is_set():
                            break
                        now = time.monotonic()
                        if now - last > 5 and (ch.delta or ch.thinking or ch.tool_calls):  # a long pause that recovered
                            logger.warning("LLM stream paused %.1fs then resumed, model=%s", now - last, self.model)
                            _emit_raw_json("openai.chat_stream.paused", uuid.uuid4().hex,
                                           {"provider": "openai", "model": self.model, "seconds": round(now - last, 1)})
                        last = now
                        q.put(("chunk", ch))
                except BaseException as e:  # noqa: BLE001 — handed to the caller's thread
                    q.put(("err", e))
                finally:
                    try:
                        gen.close()
                    except Exception:  # noqa: BLE001
                        logger.debug("stream close failed", exc_info=True)
                    q.put(("end", None))

            # the read thread runs in this call's context: a contextvars.ContextVar set by the caller (thinking(False),
            # a beat's budget) is not seen by a plain new thread — 10-22 every streamed call outside a beat asked deepseek
            # to think whatever the caller said, and one in eight sat 60 s before its first token
            ctx = contextvars.copy_context()
            threading.Thread(target=ctx.run, args=(pump,), name="llm-stream", daemon=True).start()
            got = yielded = finished = False
            why = ""
            try:
                while True:
                    limit = None if finished or (got and gap <= 0) else (gap if got else first)
                    try:
                        kind, v = q.get(timeout=limit)
                    except queue.Empty:
                        why = f"no tokens for {limit:g}s ({'mid-stream' if got else 'before the first token'})"
                        break
                    if kind == "end":
                        break
                    if kind == "fin":
                        finished = True
                        continue
                    if kind == "err":
                        raise v
                    if v.delta or v.thinking or v.tool_call_starts or v.tool_calls:
                        got = True
                    if v.delta or v.tool_call_starts or v.tool_calls:
                        yielded = True
                    yield v
            finally:
                stop.set()
            if not why:
                return
            logger.warning("LLM stream stalled (%s), model=%s attempt %d/%d", why, self.model, attempt + 1, retries + 1)
            _emit_raw_json("openai.chat_stream.stalled", uuid.uuid4().hex,
                           {"provider": "openai", "model": self.model, "base_url": self.base_url, "why": why,
                            "attempt": attempt + 1, "partial": yielded})
            if yielded:
                raise StreamStalled(why)
        yield StreamChunk(error=f"stream stalled {retries + 1} times: {why}", finished=True, retryable=True)

    def _chat_stream_once(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        on_finish: Any = None,
    ):
        """Stream a chat turn chunk by chunk (M6-T7).

        Uses OpenAI's stream=True mode to yield chunks as they arrive.
        Accumulates tool calls across chunks since OpenAI sends them incrementally.
        Initial connection uses retry logic for transient errors.

        Args:
            messages: Conversation history as list of Message objects
            tools: Tool schemas for function calling

        Yields:
            StreamChunk with delta text or final tool calls
        """
        from neonrp.core.llm import StreamChunk

        try:
            client = self._get_client()
        except (ImportError, ValueError) as e:
            yield StreamChunk(error=str(e), finished=True)
            return

        # Convert Message objects to API format
        api_messages = [msg.to_api_dict() for msg in messages]

        # Build API call parameters with streaming
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},  # Get usage in final chunk
        }

        if self.seed is not None:
            kwargs["seed"] = self.seed

        _apply_openai_extra_kwargs(client, kwargs, {**self.extra_kwargs, **_think_off(self.base_url)})

        # Add tools if provided
        if tools:
            kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]

        request_id = uuid.uuid4().hex
        _emit_raw_json(
            "openai.chat_stream.request",
            request_id,
            {
                "provider": "openai",
                "mode": "chat_stream",
                "model": self.model,
                "base_url": self.base_url,
                "payload": _to_jsonable(kwargs),
            },
        )

        try:
            # Use retry for the initial connection
            stream = self._call_with_retry(
                lambda: self._create(client, kwargs),
                error_prefix="Stream API error",
            )

            # Accumulate tool calls (OpenAI sends them in parts).
            # Key supports int index and id fallback for compatible APIs that omit index.
            tool_calls_buffer: dict[int | str, dict[str, Any]] = {}
            usage = {}
            chunk_count = 0
            content_parts: list[str] = []
            thinking_parts: list[str] = []
            last_finish_reason: str | None = None

            _chunks = _closing(stream)
            for chunk in _chunks:  # the HTTP stream is closed here, never by the garbage collector (10-11)
                if beat_budget.expired():  # the beat is over: stop reading and close the stream now
                    beat_budget.note("llm.stream")
                    _chunks.close()
                    yield StreamChunk(error="beat timeout (stream)", finished=True)
                    return
                chunk_count += 1
                # Handle usage in final chunk
                if chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                        "prompt_cache_hit_tokens": int(getattr(chunk.usage, "prompt_cache_hit_tokens", 0) or 0),
                    }

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # Yield text content chunks
                if delta.content:
                    content_parts.append(delta.content)
                    yield StreamChunk(delta=delta.content)

                # Yield reasoning/thinking chunks for providers that expose them.
                reasoning_text = ""
                try:
                    rc = getattr(delta, "reasoning_content", None)
                    if isinstance(rc, str):
                        reasoning_text = rc
                    elif rc:
                        reasoning_text = str(rc)
                except Exception:
                    reasoning_text = ""
                if not reasoning_text:
                    try:
                        r = getattr(delta, "reasoning", None)
                        if isinstance(r, str):
                            reasoning_text = r
                        elif r:
                            reasoning_text = str(r)
                    except Exception:
                        reasoning_text = ""
                if reasoning_text:
                    thinking_parts.append(reasoning_text)
                    yield StreamChunk(thinking=reasoning_text)

                # Accumulate tool calls and emit early name notifications
                if delta.tool_calls:
                    newly_named: list[str] = []
                    for pos, tc_delta in enumerate(delta.tool_calls):
                        raw_idx = getattr(tc_delta, "index", None)
                        call_id = getattr(tc_delta, "id", None) or ""
                        if isinstance(raw_idx, int):
                            key: int | str = raw_idx
                        elif call_id:
                            key = call_id
                        else:
                            # Best-effort fallback for non-standard providers that omit both index and id.
                            key = f"pos_{pos}"

                        if key not in tool_calls_buffer:
                            tool_calls_buffer[key] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                                "argument_fragments": [],
                            }
                        if tc_delta.id:
                            tool_calls_buffer[key]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                had_name = bool(tool_calls_buffer[key]["name"])
                                tool_calls_buffer[key]["name"] = tc_delta.function.name
                                if not had_name:
                                    newly_named.append(tc_delta.function.name)
                            if tc_delta.function.arguments:
                                tool_calls_buffer[key]["argument_fragments"].append(tc_delta.function.arguments)
                                tool_calls_buffer[key]["arguments"] = _merge_streamed_arguments(
                                    tool_calls_buffer[key]["arguments"], tc_delta.function.arguments
                                )
                        # Log raw delta for diagnosing Ollama/compatible providers
                        raw_args = getattr(tc_delta.function, "arguments", None) if tc_delta.function else None
                        if _LOG_STREAM_TOOL_DELTAS and logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "stream tc_delta: key=%s id=%s name=%r args=%r (type=%s, bool=%s)",
                                key,
                                getattr(tc_delta, "id", None),
                                getattr(tc_delta.function, "name", None) if tc_delta.function else None,
                                raw_args,
                                type(raw_args).__name__,
                                bool(raw_args),
                            )
                    # Notify UI as soon as tool names are known (before args finish)
                    if newly_named:
                        yield StreamChunk(tool_call_starts=newly_named)

                # Check for finish
                if choice.finish_reason:
                    last_finish_reason = choice.finish_reason
                    if on_finish is not None:
                        on_finish()  # the provider is done; a continuation / recovery call after this is not a stall
                    # Convert accumulated tool calls to ToolCall objects
                    final_tool_calls = []
                    for key, tc_data in tool_calls_buffer.items():
                        finalized_args = _finalize_streamed_arguments(
                            tc_data.get("argument_fragments", []),
                            merged_fallback=tc_data.get("arguments", ""),
                        )
                        parse_ok = True
                        try:
                            arguments = json.loads(finalized_args) if finalized_args else {}
                        except json.JSONDecodeError:
                            parse_ok = False
                            arguments = {"raw": finalized_args}
                        logger.debug(
                            "stream tool_call finalized: key=%s finish_reason=%s id=%s name=%r "
                            "fragment_count=%d merged_len=%d finalized_len=%d parse_ok=%s args=%s",
                            key,
                            choice.finish_reason,
                            tc_data.get("id", ""),
                            tc_data.get("name", ""),
                            len(tc_data.get("argument_fragments", []) or []),
                            len(tc_data.get("arguments", "") or ""),
                            len(finalized_args or ""),
                            parse_ok,
                            _preview_log_text(arguments),
                        )
                        final_tool_calls.append(
                            ToolCall(
                                id=tc_data["id"],
                                name=tc_data["name"],
                                arguments=arguments,
                            )
                        )

                    # Some compatible providers stream incomplete tool calls
                    # (often finish_reason=length). Recover by re-requesting once
                    # with non-stream chat, then prefer recovered calls.
                    recovered_calls = None
                    if final_tool_calls and (
                        choice.finish_reason == "length" or _tool_calls_need_recovery(final_tool_calls)
                    ):
                        logger.warning(
                            "Streamed tool calls need recovery (finish_reason=%s): %s",
                            choice.finish_reason,
                            [(tc.name, tc.arguments) for tc in final_tool_calls],
                        )
                        recovered = self.chat(messages, tools=tools)
                        if recovered.tool_calls and not _tool_calls_need_recovery(recovered.tool_calls):
                            recovered_calls = recovered.tool_calls
                            logger.debug(
                                "stream tool_call recovery succeeded: model=%s recovered=%s",
                                self.model,
                                [(tc.name, _preview_log_text(tc.arguments)) for tc in recovered_calls],
                            )
                        elif recovered.error:
                            logger.warning(
                                "Stream tool-call recovery failed for model=%s: %s",
                                self.model,
                                recovered.error[:300],
                            )
                        else:
                            logger.debug(
                                "stream tool_call recovery not usable: model=%s recovered=%s",
                                self.model,
                                [(tc.name, _preview_log_text(tc.arguments)) for tc in (recovered.tool_calls or [])],
                            )

                    # 纯文本截断续写(与 chat() 同一策略的流式面):无工具调用
                    # 而 finish_reason=length 时,用非流式续请求补齐剩余内容,
                    # 作为一个大 delta 续给 UI —— 创作长输出不再断尾。
                    if not final_tool_calls and choice.finish_reason == "length":
                        try:
                            partial = "".join(content_parts)
                            cont_msgs = list(messages) + [
                                Message(role="assistant", content=partial),
                                Message(
                                    role="user",
                                    content=(
                                        "(你的上一条输出因长度限制被截断。从截断处"
                                        "无缝继续,不要重复已输出的内容,不要任何解释。)"
                                    ),
                                ),
                            ]
                            cont = self.chat(cont_msgs, tools=None)
                            extra = (cont.message.content or "") if cont.message else ""
                            if extra:
                                content_parts.append(extra)
                                yield StreamChunk(delta=extra)
                                if cont.usage and usage:
                                    usage = {
                                        k: usage.get(k, 0) + cont.usage.get(k, 0)
                                        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                                    }
                        except Exception:  # noqa: BLE001 — 续写失败保底返回已有部分
                            logger.warning("stream length auto-continue failed", exc_info=True)

                    yield StreamChunk(
                        tool_calls=recovered_calls or (final_tool_calls if final_tool_calls else None),
                        finished=True,
                        usage=usage,
                    )
                    final_calls = recovered_calls or (final_tool_calls if final_tool_calls else [])
                    _emit_raw_json(
                        "openai.chat_stream.response",
                        request_id,
                        {
                            "provider": "openai",
                            "mode": "chat_stream",
                            "model": self.model,
                            "base_url": self.base_url,
                            "response_merged": {
                                "finish_reason": last_finish_reason,
                                "message": {
                                    "role": "assistant",
                                    "content": "".join(content_parts) if content_parts else "",
                                    "thinking": "".join(thinking_parts) if thinking_parts else "",
                                    "tool_calls": [
                                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                                        for tc in final_calls
                                    ],
                                },
                                "usage": usage,
                                "chunk_count": chunk_count,
                                "recovered_calls": bool(recovered_calls),
                            },
                        },
                    )
                    return

            # If we get here without a finish_reason, yield final chunk with any accumulated tool calls (review fix)
            final_tool_calls = []
            for key, tc_data in tool_calls_buffer.items():
                finalized_args = _finalize_streamed_arguments(
                    tc_data.get("argument_fragments", []),
                    merged_fallback=tc_data.get("arguments", ""),
                )
                parse_ok = True
                try:
                    arguments = json.loads(finalized_args) if finalized_args else {}
                except json.JSONDecodeError:
                    parse_ok = False
                    arguments = {"raw": finalized_args}
                logger.debug(
                    "stream tool_call finalized (no_finish_reason): key=%s id=%s name=%r "
                    "fragment_count=%d merged_len=%d finalized_len=%d parse_ok=%s args=%s",
                    key,
                    tc_data.get("id", ""),
                    tc_data.get("name", ""),
                    len(tc_data.get("argument_fragments", []) or []),
                    len(tc_data.get("arguments", "") or ""),
                    len(finalized_args or ""),
                    parse_ok,
                    _preview_log_text(arguments),
                )
                final_tool_calls.append(
                    ToolCall(
                        id=tc_data["id"],
                        name=tc_data["name"],
                        arguments=arguments,
                    )
                )

            recovered_calls = None
            if final_tool_calls and _tool_calls_need_recovery(final_tool_calls):
                recovered = self.chat(messages, tools=tools)
                if recovered.tool_calls and not _tool_calls_need_recovery(recovered.tool_calls):
                    recovered_calls = recovered.tool_calls
                    logger.debug(
                        "stream tool_call recovery succeeded (no_finish_reason): model=%s recovered=%s",
                        self.model,
                        [(tc.name, _preview_log_text(tc.arguments)) for tc in recovered_calls],
                    )
                elif recovered.error:
                    logger.warning(
                        "Stream tool-call recovery failed for model=%s (no finish_reason): %s",
                        self.model,
                        recovered.error[:300],
                    )
                else:
                    logger.debug(
                        "stream tool_call recovery not usable (no_finish_reason): model=%s recovered=%s",
                        self.model,
                        [(tc.name, _preview_log_text(tc.arguments)) for tc in (recovered.tool_calls or [])],
                    )
            yield StreamChunk(
                tool_calls=recovered_calls or (final_tool_calls if final_tool_calls else None),
                finished=True,
                usage=usage,
            )
            final_calls = recovered_calls or (final_tool_calls if final_tool_calls else [])
            _emit_raw_json(
                "openai.chat_stream.response",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat_stream",
                    "model": self.model,
                    "base_url": self.base_url,
                    "response_merged": {
                        "finish_reason": last_finish_reason,
                        "message": {
                            "role": "assistant",
                            "content": "".join(content_parts) if content_parts else "",
                            "thinking": "".join(thinking_parts) if thinking_parts else "",
                            "tool_calls": [
                                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                                for tc in final_calls
                            ],
                        },
                        "usage": usage,
                        "chunk_count": chunk_count,
                        "recovered_calls": bool(recovered_calls),
                    },
                },
            )

        except AuthError as e:
            _emit_raw_json(
                "openai.chat_stream.error",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat_stream",
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": f"Authentication failed: {e}",
                    "error_type": "AuthError",
                },
            )
            yield StreamChunk(error=f"Authentication failed: {e}", finished=True)
        except BeatTimeout as e:
            yield StreamChunk(error=str(e), finished=True)
        except BillingError as e:
            _emit_raw_json("openai.chat_stream.error", request_id, {"provider": "openai", "mode": "chat_stream", "model": self.model,
                                                                    "base_url": self.base_url, "error": str(e), "error_type": "BillingError"})
            yield StreamChunk(error=str(e), finished=True)
        except RetryableError as e:
            _emit_raw_json(
                "openai.chat_stream.error",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat_stream",
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": f"API error after retries: {e}",
                    "error_type": "RetryableError",
                },
            )
            yield StreamChunk(error=f"API error after retries: {e}", finished=True, retryable=True)
        except InvalidResponseError as e:
            _emit_raw_json(
                "openai.chat_stream.error",
                request_id,
                {
                    "provider": "openai",
                    "mode": "chat_stream",
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": f"Invalid request: {e}",
                    "error_type": "InvalidResponseError",
                },
            )
            yield StreamChunk(error=f"Invalid request: {e}", finished=True)
        except Exception as e:
            classified = _classify_openai_error(e)
            if isinstance(classified, RetryableError):
                _emit_raw_json(
                    "openai.chat_stream.error",
                    request_id,
                    {
                        "provider": "openai",
                        "mode": "chat_stream",
                        "model": self.model,
                        "base_url": self.base_url,
                        "error": f"OpenAI API streaming error: {classified}",
                        "error_type": "RetryableError",
                    },
                )
                yield StreamChunk(error=f"OpenAI API streaming error: {classified}", finished=True, retryable=True)
            elif isinstance(classified, BillingError):
                yield StreamChunk(error=str(classified), finished=True)
            else:
                _emit_raw_json(
                    "openai.chat_stream.error",
                    request_id,
                    {
                        "provider": "openai",
                        "mode": "chat_stream",
                        "model": self.model,
                        "base_url": self.base_url,
                        "error": f"OpenAI API streaming error: {e}",
                        "error_type": type(e).__name__,
                    },
                )
                yield StreamChunk(error=f"OpenAI API streaming error: {e}", finished=True)
