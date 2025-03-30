from typing import Callable, Coroutine, Any

from models import Interval

def interval(timeout: float, start_immediatly: bool = False, once_only: bool = False):

    def wrapper(func: Callable[[Any, Interval], Coroutine]):
        return Interval(timeout, func, once_only = once_only, start_immediatly = start_immediatly)

    return wrapper

def timeout(time: float):
    return interval(time, False, True)