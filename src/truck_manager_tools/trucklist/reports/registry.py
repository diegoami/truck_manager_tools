"""Registry of report name -> report function.

Each report function takes the trucks list (list[dict]) and returns
aggregate rows (list[dict]).
"""

from collections.abc import Callable

REPORTS: dict[str, Callable[[list[dict]], list[dict]]] = {}


def register(name: str, fn: Callable[[list[dict]], list[dict]]) -> None:
    REPORTS[name] = fn
