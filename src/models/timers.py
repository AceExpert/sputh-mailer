import asyncio

from typing import Callable, Coroutine

class Interval:
    
    loop: 'asyncio.AbstractEventLoop | None'
    
    def __init__(self, time: float, callback: Callable[[], Coroutine], params: tuple = (), once_only: bool = False, start_now: bool = False):
        self.time = time
        self.callback = callback
        self.task: 'asyncio.Task | None' = None
        self.once_only: bool = once_only
        self.start_now: bool = start_now
        self.params = params
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    def start(self, loop: 'asyncio.AbstractEventLoop | None' = None):
        self.loop = self.loop or loop
        self.task = self.loop.create_task(self._task_fn())

    def stop(self):
        self.task.cancel()

    def restart(self):
        if (self.task and self.task.done()) or not self.task:
            self.task = self.loop.create_task(self._task_fn())
        elif self.task:
            self.task.cancel()
            self.task = self.loop.create_task(self._task_fn())

    def resume(self):
        self.restart()

    def once(self, val: bool = True):
        self.once_only = val

    def start_immediate(self, val: bool = True):
        self.start_now = val

    async def _task_fn(self):
        while True:
            if self.start_now and not self.once_only:
                await self.callback(*self.params)
                await asyncio.sleep(self.time)
            else:
                await asyncio.sleep(self.time)
                await self.callback(*self.params)
                if self.once_only:
                    break