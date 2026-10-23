"""LLM error types for NeonRP.

Provides typed error hierarchy for distinguishing retryable from fatal LLM errors.
"""


class LLMError(Exception):
    """Base error for LLM operations."""

    retryable: bool = False

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RetryableError(LLMError):
    """Transient error that may succeed on retry.

    Covers: HTTP 429 (rate limit), 500/502/503 (server errors),
    connection errors, and timeouts.
    """

    retryable = True


class AuthError(LLMError):
    """Authentication or authorization failure (401, 403).

    Not retryable — requires user to fix API key configuration.
    """

    retryable = False


class InvalidResponseError(LLMError):
    """LLM returned a malformed or unparseable response.

    Covers: malformed JSON in tool arguments, unexpected response structure.
    """

    retryable = False


class BudgetExhaustedError(LLMError):
    """Token or turn budget exceeded.

    Raised when the agentic loop's context size exceeds the configured limit.
    """

    retryable = False


class BillingError(LLMError):
    """ai.worldlines.gg refused for money: quota used up, not enough credits, today's allowance unclaimed, plan needed
    (402 / 403 / 429 with ``billing_url``; core/billing_stop.py).

    Not retryable — the player has to act; an ordinary 429 rate limit stays a RetryableError.
    """

    retryable = False

    def __init__(self, stop, status_code: int | None = None):
        super().__init__(stop.error_text(), status_code=status_code)
        self.stop = stop
