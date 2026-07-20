"""QuantLib runtime helpers."""

import asyncio
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from typing import Any

from deskpricer.worker import execute_task

_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()

QUANTLIB_VERSION = getattr(
    __import__("QuantLib", fromlist=["__version__"]), "__version__", "unknown"
)


def _default_workers() -> int:
    cpu = os.cpu_count() or 1
    return min(4, cpu)


def get_pool() -> ProcessPoolExecutor:
    # Double-checked locking: safe under uvicorn's default single-threaded event
    # loop AND under multi-threaded event-loop configs (e.g. uvloop with workers).
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                workers = int(os.environ.get("DESKPRICER_WORKERS", _default_workers()))
                _pool = ProcessPoolExecutor(max_workers=max(1, workers))
    return _pool


def shutdown_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=True, cancel_futures=True)
            _pool = None


async def run_pricing_task(task: str, valuation_date: date, payload: dict[str, Any]) -> Any:
    """Execute a pricing task in the process pool (or inline when testing)."""
    if os.environ.get("DESKPRICER_INLINE") == "1":
        return execute_task(task, valuation_date.isoformat(), payload)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        get_pool(),
        execute_task,
        task,
        valuation_date.isoformat(),
        payload,
    )
