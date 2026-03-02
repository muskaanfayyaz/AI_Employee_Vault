"""Exponential backoff retry decorator (T029).

Usage::

    from src.engine.retry import with_retry, RetriesExhaustedError

    @with_retry(base_delay=2, max_retries=3, multiplier=2)
    def call_external_api():
        ...

The decorator catches exceptions from *exceptions* (default: all), waits
``base_delay * multiplier**attempt`` seconds between attempts, and raises
:exc:`RetriesExhaustedError` once all retries are consumed.

Delay schedule (defaults)::

    attempt 1 → 2 s
    attempt 2 → 4 s
    attempt 3 → 8 s
    → RetriesExhaustedError

Non-retryable errors (FR-G030):
    Raise :exc:`NonRetryableError` to signal the decorator must not retry.
    HTTP status codes in NON_RETRYABLE_HTTP_CODES are also skipped.

Retry-After support (FR-G032):
    When the server returns an HTTP 429 with a ``Retry-After: N`` header
    value embedded in the exception message, the decorator sleeps for
    exactly N seconds instead of the computed backoff delay.

Max-delay cap (FR-G029):
    The *max_delay* parameter caps the computed backoff so it never
    exceeds that value (default 30 s).
"""
from __future__ import annotations

import functools
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# HTTP status-code sets (FR-G030)
# ---------------------------------------------------------------------------

# HTTP status codes that warrant a retry attempt.
RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
# HTTP status codes that are permanent failures and must NOT be retried.
NON_RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({400, 401, 403, 404, 405, 409, 422})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NonRetryableError(Exception):
    """Raise this to tell the retry handler it must NOT retry.

    Use for permanent failures where retrying would be pointless or
    harmful (e.g. invalid credentials, malformed requests, business-logic
    rejections).
    """


class RetriesExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted.

    Attributes
    ----------
    retry_count:
        Number of retry attempts made.
    original_error:
        The last exception that caused failure.
    timestamps:
        ISO-8601 timestamps of each failed attempt.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_count: int,
        original_error: Exception,
        timestamps: list[str],
    ) -> None:
        super().__init__(message)
        self.retry_count = retry_count
        self.original_error = original_error
        self.timestamps = timestamps


# ---------------------------------------------------------------------------
# Error classification (FR-G030)
# ---------------------------------------------------------------------------

# Patterns used to extract an HTTP status code from an exception message.
_HTTP_STATUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"HTTP\s+(\d{3})", re.IGNORECASE),
    re.compile(r"status[=:\s]+(\d{3})", re.IGNORECASE),
    re.compile(r"(\d{3})\s+\w+"),  # e.g. "404 Not Found"
]

# Pattern to extract a numeric Retry-After value from an exception message.
_RETRY_AFTER_PATTERN: re.Pattern[str] = re.compile(
    r"Retry-After[:\s]+(\d+(?:\.\d+)?)", re.IGNORECASE
)


def classify_error(exc: Exception) -> tuple[bool, float | None]:
    """Classify an exception as retryable and extract Retry-After seconds.

    Returns ``(is_retryable, retry_after_seconds)``.

    ``retry_after_seconds`` is ``None`` when no ``Retry-After`` value is
    present in the exception message.

    Rules (evaluated in order):
    1. :exc:`NonRetryableError` → not retryable.
    2. HTTP status code found in exception message:
       - In NON_RETRYABLE_HTTP_CODES → not retryable.
       - In RETRYABLE_HTTP_CODES (including 429) → retryable; for 429 also
         try to extract a ``Retry-After`` value.
    3. No recognisable HTTP code → default to retryable ``(True, None)``.
    """
    if isinstance(exc, NonRetryableError):
        return (False, None)

    message = str(exc)

    # Attempt to extract an HTTP status code from the message.
    status_code: int | None = None
    for pattern in _HTTP_STATUS_PATTERNS:
        match = pattern.search(message)
        if match:
            candidate = int(match.group(1))
            # Only treat 3-digit codes in the plausible HTTP range.
            if 100 <= candidate <= 599:
                status_code = candidate
                break

    if status_code is not None:
        if status_code in NON_RETRYABLE_HTTP_CODES:
            return (False, None)

        if status_code in RETRYABLE_HTTP_CODES:
            retry_after: float | None = None
            if status_code == 429:
                ra_match = _RETRY_AFTER_PATTERN.search(message)
                if ra_match:
                    retry_after = float(ra_match.group(1))
            return (True, retry_after)

    # Unknown error type — default: retry.
    return (True, None)


# ---------------------------------------------------------------------------
# Convenience helper (FR-G030)
# ---------------------------------------------------------------------------


def is_retryable_http_error(status_code: int) -> bool:
    """True when the HTTP status code warrants a retry attempt."""
    return status_code in RETRYABLE_HTTP_CODES


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def with_retry(
    base_delay: float = 2.0,
    max_retries: int = 3,
    multiplier: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Retry decorator with exponential backoff.

    Parameters
    ----------
    base_delay:
        Initial wait time in seconds before the first retry (default 2).
    max_retries:
        Maximum number of retry attempts after the initial failure
        (default 3).  Total calls = 1 + max_retries.
    multiplier:
        Factor by which *base_delay* is multiplied after each retry
        (default 2 → delays: 2 s, 4 s, 8 s).
    max_delay:
        Upper bound on the computed backoff delay in seconds (FR-G029).
        Default 30 s.
    exceptions:
        Tuple of exception types to catch and retry on.  Defaults to
        ``(Exception,)`` — catches everything.

    Raises
    ------
    NonRetryableError
        Re-raised immediately when the wrapped function raises
        :exc:`NonRetryableError` or when :func:`classify_error` marks
        the error as non-retryable (FR-G030).
    RetriesExhaustedError
        When the function fails on every attempt including all retries.
        Contains the original exception, retry count, and timestamps.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            timestamps: list[str] = []
            last_exc: Exception = RuntimeError("unreachable")

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    timestamps.append(datetime.now(timezone.utc).isoformat())

                    is_retryable, retry_after = classify_error(exc)

                    if not is_retryable:
                        logger.warning(
                            "[Retry] %s raised non-retryable error: %s — aborting retries",
                            func.__name__,
                            exc,
                        )
                        raise

                    if attempt < max_retries:
                        # Cap the computed backoff (FR-G029).
                        sleep_duration = min(delay, max_delay)

                        if retry_after is not None:
                            # Honor Retry-After from server (FR-G032).
                            logger.warning(
                                "[Retry-After] Sleeping %.0fs as requested by server "
                                "(attempt %d/%d, func=%s)",
                                retry_after,
                                attempt + 1,
                                max_retries,
                                func.__name__,
                            )
                            time.sleep(retry_after)
                        else:
                            logger.warning(
                                "[Retry %d/%d] %s failed: %s — retrying in %.1fs",
                                attempt + 1,
                                max_retries,
                                func.__name__,
                                exc,
                                sleep_duration,
                            )
                            time.sleep(sleep_duration)

                        delay = delay * multiplier
                    else:
                        logger.error(
                            "[Retry %d/%d] %s exhausted retries after: %s",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            exc,
                        )

            raise RetriesExhaustedError(
                f"{func.__name__} failed after {max_retries} "
                f"{'retry' if max_retries == 1 else 'retries'}: {last_exc}",
                retry_count=max_retries,
                original_error=last_exc,
                timestamps=timestamps,
            )

        return wrapper  # type: ignore[return-value]

    return decorator
