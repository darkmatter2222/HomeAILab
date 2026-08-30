"""Closed-loop and open-loop load generators (goal.md §16)."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol


class LoadGenerator(Protocol):
    """Drives requests at a target server until a stop signal."""

    async def run(
        self,
        request_fn: Callable[[], Awaitable[None]],
        stop: asyncio.Event,
        budget_deadline: float | None = None,
    ) -> int:
        """Issue requests; return the count issued."""
        ...


@dataclass
class ClosedLoopGenerator:
    """Each of ``concurrency`` workers issues the next request only after
    its previous one completes (goal.md §16)."""

    concurrency: int
    total_requests: int | None = None  # None = run until budget/stop
    _issued: int = 0

    async def run(self, request_fn, stop, budget_deadline=None) -> int:
        issued = 0

        async def worker() -> None:
            nonlocal issued
            while not stop.is_set():
                if budget_deadline is not None and time.time() >= budget_deadline:
                    return
                if self.total_requests is not None and issued >= self.total_requests:
                    return
                # Reserve this request atomically enough for our purposes.
                issued += 1
                try:
                    await request_fn()
                except asyncio.CancelledError:
                    raise
                except Exception:  # request_fn should handle its own errors
                    pass

        workers = [asyncio.create_task(worker())
                   for _ in range(self.concurrency)]
        # Let all workers finish (they exit on stop/budget/completion).
        await asyncio.gather(*workers, return_exceptions=True)
        return issued


@dataclass
class OpenLoopGenerator:
    """Issues requests at a fixed target rate, independent of completions.

    ``pattern`` is "constant" (uniform spacing) or "poisson" (exponential
    inter-arrival times).  A bounded backlog prevents unbounded queueing
    when the server is slower than the arrival rate.
    """

    rate: float  # target requests/second
    pattern: str = "constant"  # "constant" | "poisson"
    total_requests: int | None = None
    max_backlog: int = 256

    async def run(self, request_fn, stop, budget_deadline=None) -> int:
        issued = 0
        pending: set[asyncio.Task] = set()
        rng = random.Random(0xC0FFEE)
        while not stop.is_set():
            if budget_deadline is not None and time.time() >= budget_deadline:
                break
            if self.total_requests is not None and issued >= self.total_requests:
                break
            if len(pending) >= self.max_backlog:
                # Backlog bounded; wait for a completion before issuing more.
                if pending:
                    await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                else:
                    await asyncio.sleep(0.01)
                continue

            if self.pattern == "poisson":
                dt = -rng.expovariate(self.rate) if self.rate > 0 else 0.0
            else:
                dt = 1.0 / self.rate if self.rate > 0 else 0.0

            task = asyncio.create_task(request_fn())
            pending.add(task)

            def _done(t: asyncio.Task) -> None:
                pending.discard(t)

            task.add_done_callback(_done)
            issued += 1
            if dt > 0:
                await asyncio.sleep(dt)

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return issued
