"""The spec of _matcher/loop.py tests the event loop of one assertion call."""

from __future__ import annotations

import asyncio
import inspect
import warnings
from collections.abc import Generator

import pytest

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.loop import Loop, close_awaitable


class Ready:
    """An awaitable that is not a coroutine."""

    def __await__(self) -> Generator[None, None, str]:
        """Return "ready" after the task yields once to the loop."""
        yield None
        return "ready"


async def returns_42() -> int:
    """Return 42 after an await."""
    await asyncio.sleep(0)
    return 42


class TestLoop:
    """Loop is the event loop of one assertion call."""

    def test_closes_its_event_loop_when_the_with_statement_ends(self) -> None:
        """The loop that the call created is closed after the block."""

        async def running() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        with Loop("x") as loop:
            ran = loop.resolve(running())
        assert ran.is_closed()


class TestLoopResolve:
    """Loop.resolve returns a value or the result of an awaitable."""

    def test_returns_a_value_that_is_not_awaitable(self) -> None:
        """The call returns a plain value unchanged."""
        with Loop("x") as loop:
            assert loop.resolve(3) == 3

    def test_runs_a_coroutine_to_its_end(self) -> None:
        """A coroutine runs on the loop of the call."""
        with Loop("x") as loop:
            assert loop.resolve(returns_42()) == 42
            assert loop.resolve(returns_42()) == 42

    def test_runs_an_awaitable_that_is_not_a_coroutine(self) -> None:
        """Any awaitable runs."""
        with Loop("x") as loop:
            assert loop.resolve(Ready()) == "ready"

    def test_raises_a_fault_inside_a_running_event_loop(self) -> None:
        """The fault contains the id of the assertion, and the coroutine is closed."""
        loop = Loop("the-assertion")
        raised: list[str] = []

        async def test() -> None:
            coroutine = returns_42()
            with pytest.raises(FaultError) as caught:
                loop.resolve(coroutine)
            raised.append(str(caught.value))
            assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED

        asyncio.run(test())
        assert raised == [
            "the-assertion runs a coroutine on an event loop of its own, "
            "and an event loop already runs in this thread"
        ]


class TestLoopClose:
    """Loop.close closes the event loop of a call."""

    def test_closes_a_loop_twice(self) -> None:
        """A second close does nothing."""
        loop = Loop("x")
        loop.resolve(returns_42())
        loop.close()
        loop.close()


class TestCloseAwaitable:
    """close_awaitable closes a coroutine that nobody awaits."""

    def test_closes_a_coroutine_without_a_warning(self) -> None:
        """A closed coroutine does not raise a warning when it is collected."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            coroutine = returns_42()
            close_awaitable(coroutine)
        assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED

    def test_leaves_an_awaitable_that_is_not_a_coroutine(self) -> None:
        """An awaitable that is not a coroutine can still run afterwards."""
        ready = Ready()
        close_awaitable(ready)
        with Loop("x") as loop:
            assert loop.resolve(ready) == "ready"
