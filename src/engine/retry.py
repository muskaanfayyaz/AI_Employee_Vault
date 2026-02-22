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
"""
from __future__ import annotations

import functools
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


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
# Decorator
# ---------------------------------------------------------------------------


def with_retry(
    base_delay: float = 2.0,
    max_retries: int = 3,
    multiplier: float = 2.0,
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
    exceptions:
        Tuple of exception types to catch and retry on.  Defaults to
        ``(Exception,)`` — catches everything.

    Raises
    ------
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

                    if attempt < max_retries:
                        logger.warning(
                            "[Retry %d/%d] %s failed: %s — retrying in %.1fs",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
                        delay *= multiplier
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
