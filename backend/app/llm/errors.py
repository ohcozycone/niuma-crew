"""Classify provider exceptions without swallowing storage or application errors."""

import httpx
import openai


def classify_error(error: Exception) -> str | None:
    if isinstance(error, openai.AuthenticationError):
        return "upstream_auth_failed"
    if isinstance(error, openai.PermissionDeniedError):
        return "upstream_forbidden"
    if isinstance(error, openai.RateLimitError):
        return "upstream_rate_limited"
    if isinstance(error, openai.BadRequestError):
        return (
            "context_limit_exceeded"
            if error.code in ("context_length_exceeded", "context_window_exceeded")
            else "upstream_stream_error"
        )
    if isinstance(error, (openai.APITimeoutError, httpx.TimeoutException)):
        return "run_timeout"
    if isinstance(error, (openai.APIConnectionError, httpx.HTTPError)):
        return "upstream_unavailable"
    if isinstance(error, openai.APIError):
        return "upstream_stream_error"
    return None
