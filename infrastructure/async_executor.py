import asyncio
from typing import Any, Coroutine, TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.scheduler_service import Scheduler


class AsyncExecutor:
    def __init__(self, loop: asyncio.AbstractEventLoop, scheduler: 'Scheduler'):
        self._loop = loop
        self.scheduler = scheduler

    def run(self, coro: Coroutine) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()
