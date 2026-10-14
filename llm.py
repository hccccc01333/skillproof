"""Provider client shared by induction and execution.

Consolidates two things that were duplicated and, more importantly, missed.

**Retry.** The paper's supplied implementation configures 30 attempts with a
maximum backoff of 30 seconds; this harness had none. The consequence was not a
crash but a silent truncation: a transient connection error ends an episode
mid-task, the agent stops where it stood, and the rubric scores whatever partial
state it left behind. That looks exactly like a weak agent.

It happened four times in this project — an overdrawn account, a transcript
validation error, and twice a dropped connection — and twice it produced a
suspiciously round, identical score that only got checked because it was
suspicious. Two of those were mine to fix, but a dropped connection is not a
result about the method under test and must not be allowed to become one.

**Transient vs permanent.** Retrying a 400 is pointless; the request is wrong
and will stay wrong. Retrying a timeout is not. Only the second kind is retried
here, so a genuine authoring bug still surfaces immediately.
"""

from __future__ import annotations

import json
import os
import time

DEFAULT_ATTEMPTS = 12
DEFAULT_BASE_DELAY = 2.0
DEFAULT_MAX_DELAY = 30.0

# Status codes worth trying again. Everything else is treated as permanent, so
# a malformed request fails fast instead of burning the budget.
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 522, 524}


class EndpointNotConfigured(RuntimeError):
    pass


def extra_headers() -> dict | None:
    raw = os.environ.get("S2S_INDUCT_EXTRA_HEADERS")
    if not raw:
        return None
    try:
        headers = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EndpointNotConfigured(f"S2S_INDUCT_EXTRA_HEADERS is not valid JSON: {exc}") from exc
    return headers if isinstance(headers, dict) else None


def model_name() -> str:
    return os.environ.get("S2S_INDUCT_MODEL", "deepseek-chat")


def make_client():
    """An OpenAI-compatible client configured entirely from the environment."""
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise EndpointNotConfigured("pip install openai to run against a model") from exc

    base_url = os.environ.get("S2S_INDUCT_BASE_URL")
    api_key = os.environ.get("S2S_INDUCT_API_KEY")
    if not base_url or not api_key:
        raise EndpointNotConfigured(
            "set S2S_INDUCT_BASE_URL and S2S_INDUCT_API_KEY (and optionally "
            "S2S_INDUCT_MODEL, S2S_INDUCT_EXTRA_HEADERS)"
        )
    return OpenAI(base_url=base_url, api_key=api_key, default_headers=extra_headers())


def is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if isinstance(status, int):
        return status in RETRYABLE_STATUS
    # No status at all means the request never completed: connection reset,
    # DNS blip, read timeout. Retry those.
    name = type(exc).__name__
    return name in {
        "APIConnectionError", "APITimeoutError", "ConnectError",
        "ReadTimeout", "ConnectTimeout", "RemoteProtocolError",
    }


def chat(client, *, attempts: int = DEFAULT_ATTEMPTS, verbose: bool = False, **kwargs):
    """`client.chat.completions.create(**kwargs)` with backoff on transients.

    Raises on the final attempt, and immediately on anything non-retryable.
    """
    delay = DEFAULT_BASE_DELAY
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if not is_retryable(exc):
                raise
            last = exc
            if attempt == attempts:
                break
            if verbose:
                print(f"    [retry {attempt}/{attempts}] {type(exc).__name__}: "
                      f"{str(exc)[:80]} — waiting {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, DEFAULT_MAX_DELAY)
    raise RuntimeError(
        f"provider request failed after {attempts} attempts: {type(last).__name__}: {last}"
    ) from last
