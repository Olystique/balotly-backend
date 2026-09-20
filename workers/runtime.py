"""In-process supervision for Balotly's long-running background services.


The API currently hosts its workers in the same process for simple deployments.
Each runner gets an independent supervisor task so a failed dependency (for
example RabbitMQ) cannot cancel its siblings or the FastAPI application.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from api.utils.logger import logger

WorkerRunnerFactory = Callable[[], Awaitable[None]]
WorkerState = Literal["starting", "running", "backoff", "stopping", "stopped"]
WorkerExit = Literal["exception", "returned"]


@dataclass
class _WorkerStatus:
    state: WorkerState = "stopped"
    restart_count: int = 0
    last_exit: WorkerExit | None = None
    next_retry_seconds: float | None = None


class EmbeddedWorkerRuntime:
    """Run and independently restart a collection of async worker runners."""

    def __init__(
        self,
        runners: Mapping[str, WorkerRunnerFactory],
        *,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        if not runners:
            raise ValueError("At least one embedded worker runner is required")
        if any(not name or not name.strip() for name in runners):
            raise ValueError("Embedded worker names must not be empty")
        if not math.isfinite(base_backoff_seconds) or base_backoff_seconds <= 0:
            raise ValueError("base_backoff_seconds must be finite and positive")
        if not math.isfinite(max_backoff_seconds):
            raise ValueError("max_backoff_seconds must be finite")
        if max_backoff_seconds < base_backoff_seconds:
            raise ValueError(
                "max_backoff_seconds must be greater than or equal to "
                "base_backoff_seconds"
            )

        self._runners = dict(runners)
        self._base_backoff_seconds = float(base_backoff_seconds)
        self._max_backoff_seconds = float(max_backoff_seconds)
        self._max_backoff_exponent = math.ceil(
            math.log2(max_backoff_seconds) - math.log2(base_backoff_seconds)
        )
        self._statuses = {name: _WorkerStatus() for name in self._runners}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False
        self._lifecycle_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start every supervisor once; repeated calls are harmless."""

        async with self._lifecycle_lock:
            if self._started:
                return

            self._started = True
            for name, runner_factory in self._runners.items():
                status = self._statuses[name]
                status.state = "starting"
                status.restart_count = 0
                status.last_exit = None
                status.next_retry_seconds = None
                self._tasks[name] = asyncio.create_task(
                    self._supervise(name, runner_factory),
                    name=f"embedded-worker:{name}",
                )

    async def stop(self) -> None:
        """Cancel all supervisors and wait for every runner to clean up."""

        async with self._lifecycle_lock:
            if not self._started:
                return

            self._started = False
            tasks = tuple(self._tasks.values())
            for name, task in self._tasks.items():
                self._statuses[name].state = "stopping"
                task.cancel()

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            self._tasks.clear()
            for status in self._statuses.values():
                status.state = "stopped"
                status.next_retry_seconds = None

    def status_snapshot(self) -> dict[str, object]:
        """Return health-safe worker state without exception messages."""

        return {
            "running": self._started,
            "workers": {
                name: {
                    "state": status.state,
                    "restart_count": status.restart_count,
                    "last_exit": status.last_exit,
                    "next_retry_seconds": status.next_retry_seconds,
                }
                for name, status in self._statuses.items()
            },
        }

    async def _supervise(
        self,
        name: str,
        runner_factory: WorkerRunnerFactory,
    ) -> None:
        status = self._statuses[name]

        try:
            while True:
                status.state = "running"
                status.next_retry_seconds = None

                try:
                    await runner_factory()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - isolation is the supervisor's job
                    status.last_exit = "exception"
                    logger.exception("Embedded worker %s failed", name)
                else:
                    status.last_exit = "returned"
                    logger.warning("Embedded worker %s returned unexpectedly", name)

                retry_seconds = min(
                    math.ldexp(
                        self._base_backoff_seconds,
                        min(status.restart_count, self._max_backoff_exponent),
                    ),
                    self._max_backoff_seconds,
                )
                status.restart_count += 1
                status.state = "backoff"
                status.next_retry_seconds = retry_seconds
                logger.info(
                    "Restarting embedded worker %s in %.2f second(s)",
                    name,
                    retry_seconds,
                )
                await asyncio.sleep(retry_seconds)
        finally:
            status.state = "stopped"
            status.next_retry_seconds = None


def build_default_worker_runtime() -> EmbeddedWorkerRuntime | None:
    """Build the runtime used by FastAPI's lifespan integration.

    Returns ``None`` while there is nothing to supervise. The webhook consumer
    (BE-10) and the poster/settlement workers register here as they land.
    """

    from api.utils.settings import settings

    runners: dict[str, WorkerRunnerFactory] = {}
    if not runners:
        return None

    return EmbeddedWorkerRuntime(
        runners,
        base_backoff_seconds=settings.EMBEDDED_WORKER_RESTART_BASE_SECONDS,
        max_backoff_seconds=settings.EMBEDDED_WORKER_RESTART_MAX_SECONDS,
    )
