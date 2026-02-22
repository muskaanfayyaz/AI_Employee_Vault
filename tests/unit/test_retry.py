"""Unit tests for src/engine/retry.py (T027)."""
import time
from unittest.mock import MagicMock, call, patch

import pytest

from src.engine.retry import RetriesExhaustedError, with_retry


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_success_on_first_try():
    """Function succeeds immediately — no retries."""
    calls = []

    @with_retry(base_delay=0, max_retries=3)
    def always_ok():
        calls.append(1)
        return "ok"

    result = always_ok()
    assert result == "ok"
    assert len(calls) == 1


def test_success_on_second_try():
    """Function fails once then succeeds on retry 1."""
    attempts = []

    @with_retry(base_delay=0, max_retries=3)
    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise ValueError("first fail")
        return "recovered"

    result = flaky()
    assert result == "recovered"
    assert len(attempts) == 2


def test_success_on_third_try():
    """Function fails twice then succeeds on retry 2."""
    attempts = []

    @with_retry(base_delay=0, max_retries=3)
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("still failing")
        return "final ok"

    result = flaky()
    assert result == "final ok"
    assert len(attempts) == 3


# ---------------------------------------------------------------------------
# Exhaustion
# ---------------------------------------------------------------------------


def test_raises_retries_exhausted_after_max():
    """Exhausts all retries and raises RetriesExhaustedError."""

    @with_retry(base_delay=0, max_retries=3)
    def always_fails():
        raise RuntimeError("broken")

    with pytest.raises(RetriesExhaustedError) as exc_info:
        always_fails()

    err = exc_info.value
    assert err.retry_count == 3
    assert isinstance(err.original_error, RuntimeError)
    assert len(err.timestamps) == 4  # initial + 3 retries


def test_exhausted_error_message_includes_function_name():
    @with_retry(base_delay=0, max_retries=2)
    def my_named_function():
        raise ValueError("oops")

    with pytest.raises(RetriesExhaustedError) as exc_info:
        my_named_function()

    assert "my_named_function" in str(exc_info.value)


def test_total_calls_equals_one_plus_max_retries():
    """Total invocations = 1 (initial) + max_retries."""
    calls = []

    @with_retry(base_delay=0, max_retries=3)
    def counter():
        calls.append(1)
        raise RuntimeError("always")

    with pytest.raises(RetriesExhaustedError):
        counter()

    assert len(calls) == 4  # 1 + 3


# ---------------------------------------------------------------------------
# Delay schedule
# ---------------------------------------------------------------------------


def test_delay_sequence():
    """Delays are base_delay * multiplier**n: 2s, 4s, 8s."""
    sleep_calls: list[float] = []

    @with_retry(base_delay=2, max_retries=3, multiplier=2)
    def always_fails():
        raise RuntimeError("x")

    with patch("src.engine.retry.time.sleep", side_effect=lambda d: sleep_calls.append(d)):
        with pytest.raises(RetriesExhaustedError):
            always_fails()

    assert len(sleep_calls) == 3
    assert sleep_calls[0] == pytest.approx(2.0)
    assert sleep_calls[1] == pytest.approx(4.0)
    assert sleep_calls[2] == pytest.approx(8.0)


def test_no_sleep_on_last_attempt():
    """sleep is NOT called after the final failed attempt."""
    sleep_calls: list[float] = []

    @with_retry(base_delay=2, max_retries=2, multiplier=2)
    def always_fails():
        raise RuntimeError("x")

    with patch("src.engine.retry.time.sleep", side_effect=lambda d: sleep_calls.append(d)):
        with pytest.raises(RetriesExhaustedError):
            always_fails()

    # max_retries=2 → 3 total calls → 2 sleeps (not 3)
    assert len(sleep_calls) == 2


# ---------------------------------------------------------------------------
# Exception filtering
# ---------------------------------------------------------------------------


def test_only_retries_specified_exception_type():
    """Only retries on listed exception types; others propagate immediately."""
    attempts = []

    @with_retry(base_delay=0, max_retries=3, exceptions=(ValueError,))
    def raises_type_error():
        attempts.append(1)
        raise TypeError("not retried")

    with pytest.raises(TypeError):
        raises_type_error()

    assert len(attempts) == 1  # no retries


def test_retries_on_matching_exception():
    """Retries when the exception matches the specified type."""
    attempts = []

    @with_retry(base_delay=0, max_retries=3, exceptions=(ValueError,))
    def raises_value_error():
        attempts.append(1)
        raise ValueError("retried")

    with pytest.raises(RetriesExhaustedError):
        raises_value_error()

    assert len(attempts) == 4


# ---------------------------------------------------------------------------
# Decorator preserves metadata
# ---------------------------------------------------------------------------


def test_wraps_preserves_function_name():
    @with_retry(base_delay=0, max_retries=1)
    def my_function():
        """My docstring."""
        return 1

    assert my_function.__name__ == "my_function"
    assert "My docstring" in (my_function.__doc__ or "")


# ---------------------------------------------------------------------------
# RetriesExhaustedError attributes
# ---------------------------------------------------------------------------


def test_retries_exhausted_has_timestamps():
    @with_retry(base_delay=0, max_retries=2)
    def fails():
        raise RuntimeError("err")

    with pytest.raises(RetriesExhaustedError) as exc_info:
        fails()

    err = exc_info.value
    # timestamps is a list of ISO-8601 strings
    assert isinstance(err.timestamps, list)
    for ts in err.timestamps:
        assert "T" in ts  # ISO-8601 contains 'T'


def test_retries_exhausted_original_error():
    expected_msg = "the_original_error"

    @with_retry(base_delay=0, max_retries=1)
    def fails():
        raise ValueError(expected_msg)

    with pytest.raises(RetriesExhaustedError) as exc_info:
        fails()

    assert isinstance(exc_info.value.original_error, ValueError)
    assert expected_msg in str(exc_info.value.original_error)
