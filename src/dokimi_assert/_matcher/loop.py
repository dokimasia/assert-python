# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The event loop of one assertion call.

A body, a callable or an action can be a coroutine function. The assertion
calls the function, and runs an awaitable result to its end on an event
loop of its own. It creates the loop with asyncio.Runner at the first
awaitable. One assertion call creates at most one loop, and it closes the
loop when the call ends. A test is then a plain def, in the same way as for
the cancellation assertions.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Self, TypeVar

from dokimi_assert._matcher.fault import FaultError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Coroutine
    from types import TracebackType

__all__ = ["Loop", "close_awaitable"]

_T = TypeVar("_T")


async def _awaited(value: Awaitable[_T]) -> _T:
    """Return the result of value inside a coroutine that a Runner can run."""
    return await value


def close_awaitable(value: object) -> None:
    """Close value when it is a coroutine that nobody awaits.

    Python warns about a coroutine that nobody awaited when the coroutine is
    collected. A closed coroutine does not raise that warning.

    Args:
        value: The value that a callable returned.
    """
    if inspect.iscoroutine(value):
        value.close()


class Loop:
    """The event loop of one assertion call. The call creates it at its first use.

    A call uses it as a context manager, so the loop closes when the call
    ends.
    """

    def __init__(self, assertion: str) -> None:
        """Return the loop of one call of assertion.

        Args:
            assertion: The canonical id of the assertion. The text of a fault
                contains it.
        """
        self._assertion: str = assertion
        self._runner: asyncio.Runner | None = None

    def __enter__(self) -> Self:
        """Return the loop."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """Close the loop."""
        self.close()

    def resolve(self, value: object) -> Any:
        """Return value, or the result of running value when it is awaitable.

        Args:
            value: The result of a call of a body or a callable.

        Returns:
            value itself, or the result of the awaitable.

        Raises:
            FaultError: value is awaitable and an event loop already runs in
                this thread, so the call cannot run a loop of its own.
        """
        if not inspect.isawaitable(value):
            return value
        if self._runner is None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                self._runner = asyncio.Runner()
            else:
                close_awaitable(value)
                at = ""
                raise FaultError(
                    at,
                    f"{self._assertion} runs a coroutine on an event loop of its "
                    "own, and an event loop already runs in this thread",
                ) from None
        awaited: Coroutine[Any, Any, Any] = _awaited(value)
        return self._runner.run(awaited)

    def close(self) -> None:
        """Close the event loop when the call created one."""
        if self._runner is not None:
            self._runner.close()
            self._runner = None
