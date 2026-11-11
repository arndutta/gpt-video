"""Cancellation cannot free a resource while its finite blocking worker is still using it."""

import asyncio


async def drain(task: asyncio.Task):
    cancellation = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            cancellation = error
        except Exception:
            break
    if cancellation is not None:
        if not task.cancelled():
            task.exception()
        raise cancellation
    return task.result()


class OwnedWorkers:
    def __init__(self):
        self.tasks: set[asyncio.Task] = set()

    async def run(self, function, *args):
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        self.tasks.add(task)
        try:
            return await drain(task)
        finally:
            if task.done():
                self.tasks.discard(task)
