"""APScheduler must be given a coroutine function, not a Tick instance."""

import asyncio
import inspect

from app.jobs.tick import Tick, schedule_tick
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def test_tick_run_is_a_coroutine_function() -> None:
    tick = Tick(object(), object(), object(), object())  # type: ignore[arg-type]
    assert inspect.iscoroutinefunction(tick.run)
    assert inspect.iscoroutinefunction(Tick.run)
    assert not inspect.iscoroutinefunction(tick)


def test_schedule_tick_registers_the_coroutine_function() -> None:
    tick = Tick(object(), object(), object(), object())  # type: ignore[arg-type]
    scheduler = AsyncIOScheduler()
    schedule_tick(scheduler, tick, 30)
    job = scheduler.get_jobs()[0]
    assert inspect.iscoroutinefunction(job.func)
    assert job.func.__name__ == "run"
    assert getattr(job.func, "__self__", None) is tick


async def test_scheduler_awaits_tick_run() -> None:
    class Probe:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self) -> None:
            self.calls += 1

    probe = Probe()
    scheduler = AsyncIOScheduler()
    try:
        schedule_tick(scheduler, probe, 1)  # type: ignore[arg-type]
        scheduler.start()
        # Trigger immediately: interval jobs wait for the first period unless
        # we also add a date job. Call the registered func the way the executor
        # would after detecting a coroutine function.
        job = scheduler.get_jobs()[0]
        assert inspect.iscoroutinefunction(job.func)
        await job.func()
        assert probe.calls == 1
        # And a live scheduler tick with a short interval.
        started = asyncio.Event()

        async def flag() -> None:
            started.set()

        scheduler.add_job(flag, "interval", seconds=0.05, id="flag", max_instances=1)
        await asyncio.wait_for(started.wait(), timeout=2)
        assert started.is_set()
    finally:
        scheduler.shutdown(wait=False)
