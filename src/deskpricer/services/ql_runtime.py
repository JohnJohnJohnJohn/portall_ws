"""QuantLib runtime helpers."""

import asyncio
import logging
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import date
from typing import Any

from deskpricer.errors import PricingTimeoutError
from deskpricer.worker import execute_task

_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()

QUANTLIB_VERSION = getattr(
    __import__("QuantLib", fromlist=["__version__"]), "__version__", "unknown"
)

# Default per-task timeout (seconds).  Configurable via DESKPRICER_TASK_TIMEOUT.
# Generous enough for a 5000-step American IV solve (~30s) but catches true
# hangs (worker wedged, infinite loop).  Note: asyncio.wait_for cancels the
# await but cannot kill the worker process — under sustained timeouts the pool
# can be exhausted.  The leaked worker eventually finishes and returns to pool.
_DEFAULT_TASK_TIMEOUT = 60.0


def _default_workers() -> int:
    cpu = os.cpu_count() or 1
    # 8 workers absorbs the bursty concurrency from Excel WEBSERVICE recalc
    # (typically 4-12 simultaneous cells) without saturating a modern desktop.
    return min(8, cpu)


def _parse_workers() -> int:
    raw = os.environ.get("DESKPRICER_WORKERS")
    if raw is None:
        return _default_workers()
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"DESKPRICER_WORKERS must be a positive integer, got: {raw!r}"
        ) from exc
    if n < 1:
        raise ValueError(
            f"DESKPRICER_WORKERS must be a positive integer, got: {n}"
        )
    return n


def get_pool() -> ProcessPoolExecutor:
    # Double-checked locking: safe under uvicorn's default single-threaded event
    # loop AND under multi-threaded event-loop configs (e.g. uvloop with workers).
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ProcessPoolExecutor(max_workers=_parse_workers())
    return _pool


def shutdown_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=True, cancel_futures=True)
            _pool = None


async def run_pricing_task(task: str, valuation_date: date, payload: dict[str, Any]) -> Any:
    """Execute a pricing task in the process pool (or inline when testing).

    Raises ``PricingTimeoutError`` (HTTP 503) when the task exceeds the
    configured timeout.  On ``BrokenProcessPool`` (worker died), the pool is
    shut down for rebuild; the next request transparently gets a fresh pool.
    """
    if os.environ.get("DESKPRICER_INLINE") == "1":
        # Inline (test) path: no timeout, no pool — fail fast for test clarity.
        return execute_task(task, valuation_date.isoformat(), payload)

    timeout = float(os.environ.get("DESKPRICER_TASK_TIMEOUT", _DEFAULT_TASK_TIMEOUT))
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                get_pool(),
                execute_task,
                task,
                valuation_date.isoformat(),
                payload,
            ),
            timeout=timeout,
        )
    except BrokenProcessPool:
        # A worker died (segfault, OOM).  The pool is now permanently broken;
        # tear it down so the next request builds a fresh one, then re-raise
        # as a generic 500 (the retry happens implicitly on the next request).
        logging.getLogger("deskpricer").warning(
            "Process pool broke (worker died); shutting down for restart"
        )
        shutdown_pool()
        raise
    except TimeoutError as exc:
        raise PricingTimeoutError(
            f"Pricing task '{task}' exceeded timeout of {timeout:g}s",
            field=None,
        ) from exc
