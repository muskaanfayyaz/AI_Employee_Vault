"""Cron-based orchestrator using the ``schedule`` library (T040).

Wraps ``schedule.Scheduler`` with:

- Graceful shutdown via :meth:`Scheduler.stop`
- Signal handling (SIGINT, SIGTERM) when running in the main thread
- Thread-safe background execution via :meth:`Scheduler.start_in_background`
- Structured logging of lifecycle events
- Convenience :meth:`Scheduler.add_job` for registering interval callbacks

Usage (foreground)::

    from src.engine.scheduler import Scheduler

    sched = Scheduler()
    sched.every(60).seconds.do(my_function)
    sched.start()          # blocks; SIGINT / sched.stop() exits cleanly

Usage (background thread)::

    sched = Scheduler()
    sched.add_job(poll_gmail, interval_seconds=60, tag="gmail")
    sched.add_job(check_approvals, interval_seconds=30, tag="approvals")
    sched.start_in_background()  # non-blocking

    time.sleep(120)
    sched.stop()

Requires Silver tier dependency::

    pip install -e ".[silver]"   # includes 'schedule'
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Scheduler:
    """Configurable interval-based task scheduler.

    Parameters
    ----------
    install_signal_handlers:
        When ``True`` (default), installs SIGINT / SIGTERM handlers that
        call :meth:`stop`.  Set ``False`` in tests or when the scheduler
        runs in a non-main thread (signal handlers must be installed from
        the main thread).
    """

    def __init__(self, *, install_signal_handlers: bool = True) -> None:
        try:
            import schedule as _schedule  # type: ignore[import]

            self._schedule = _schedule
        except ImportError as exc:
            raise ImportError(
                "Scheduler requires Silver tier dependencies: "
                "pip install -e '.[silver]'"
            ) from exc

        # Use a dedicated Scheduler instance so tests don't share global state.
        self._scheduler = self._schedule.Scheduler()
        self._running = False
        self._thread: threading.Thread | None = None
        self._install_signal_handlers = install_signal_handlers

    # ── job registration ──────────────────────────────────────────────────────

    def every(self, interval: int = 1) -> Any:
        """Schedule a job to run every *interval* <unit>.

        Returns the ``schedule.Job`` object; chain ``.seconds``,
        ``.minutes``, ``.hours``, then ``.do(func)`` as usual.

        Example
        -------
        >>> sched.every(30).seconds.do(my_callback)
        """
        return self._scheduler.every(interval)

    def run_pending(self) -> None:
        """Run all jobs whose next run time has passed."""
        self._scheduler.run_pending()

    def clear(self, tag: str | None = None) -> None:
        """Remove all scheduled jobs, optionally filtered by *tag*."""
        if tag:
            self._scheduler.clear(tag)
        else:
            self._scheduler.clear()

    def add_job(
        self,
        callback: Callable[[], Any],
        interval_seconds: int,
        *,
        tag: str | None = None,
    ) -> Any:
        """Convenience method: schedule *callback* every *interval_seconds*.

        Parameters
        ----------
        callback:
            Zero-argument callable to invoke on each tick.
        interval_seconds:
            Run every N seconds.
        tag:
            Optional string tag for grouping and :meth:`clear`.

        Returns
        -------
        schedule.Job
            The created job (can be cancelled via ``sched.clear(tag)``).
        """
        job = self._scheduler.every(interval_seconds).seconds.do(callback)
        if tag:
            job.tag(tag)
        logger.info(
            "Job scheduled: %s every %ds (tag=%r)",
            getattr(callback, "__name__", repr(callback)),
            interval_seconds,
            tag,
        )
        return job

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Run the scheduler loop in the current thread (blocking).

        Polls :meth:`run_pending` every second until :meth:`stop` is
        called (from a signal handler or another thread).
        """
        self._running = True
        if self._install_signal_handlers:
            self._install_signals()

        logger.info("Scheduler started — polling pending jobs every second")
        try:
            while self._running:
                self._scheduler.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Scheduler: KeyboardInterrupt received.")
        finally:
            self._running = False
            logger.info("Scheduler stopped.")

    def start_in_background(self) -> threading.Thread:
        """Start the scheduler loop in a daemon thread (non-blocking).

        Returns
        -------
        threading.Thread
            The daemon thread running the scheduler.
        """
        if self._thread and self._thread.is_alive():
            logger.warning("Scheduler thread is already running.")
            return self._thread

        self._thread = threading.Thread(
            target=self.start,
            name="scheduler-loop",
            daemon=True,
        )
        self._thread.start()
        logger.info("Scheduler started in background thread.")
        return self._thread

    def stop(self) -> None:
        """Signal the scheduler loop to exit on the next tick."""
        self._running = False
        logger.info("Scheduler stop requested.")

    @property
    def is_running(self) -> bool:
        """``True`` while the scheduler loop is active."""
        return self._running

    # ── private helpers ───────────────────────────────────────────────────────

    def _install_signals(self) -> None:
        """Install SIGINT / SIGTERM handlers that call :meth:`stop`."""

        def _handler(sig: int, frame: Any) -> None:
            logger.info("Signal %d received — stopping scheduler.", sig)
            self.stop()

        try:
            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, OSError):
            # Installing signal handlers from a non-main thread raises.
            # This is expected when start_in_background() is used.
            pass
