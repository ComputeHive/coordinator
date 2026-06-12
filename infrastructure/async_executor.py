import asyncio
from typing import Any, Coroutine


class AsyncExecutor:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def run(self, coro: Coroutine) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()
