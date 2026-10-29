# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/cleanup.py tests the list of the cleanups of a seat."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dokimi_assert._matcher.cleanup import Cleanups

if TYPE_CHECKING:
    from collections.abc import Callable


def run_one(fn: Callable[[], object]) -> None:
    """Run one cleanup, as a seat without event loop runs it."""
    fn()


class TestCleanups:
    """Cleanups keeps the functions that a seat runs when its test or body ends."""

    def test_returns_an_empty_list(self) -> None:
        """A new list runs nothing."""
        order: list[str] = []
        Cleanups().run(lambda _: order.append("ran"))
        assert order == []


class TestCleanupsAdd:
    """Cleanups.add keeps a function for the next run."""

    def test_keeps_the_function_until_a_run(self) -> None:
        """The list keeps the function, which waits for the run."""
        order: list[str] = []
        cleanups = Cleanups()
        kept = cleanups.add(lambda: order.append("released"))
        assert (kept, order) == (True, [])

    def test_does_not_keep_a_function_after_close(self) -> None:
        """A closed list does not keep the function, so the seat runs it at once."""
        order: list[str] = []
        cleanups = Cleanups()
        cleanups.add(lambda: order.append("closed"))
        cleanups.close(run_one)
        kept = cleanups.add(lambda: order.append("released"))
        cleanups.run(run_one)
        assert (kept, order) == (False, ["closed"])


class TestCleanupsRun:
    """Cleanups.run runs the functions, the last kept first, and forgets them."""

    def test_runs_the_last_kept_function_first(self) -> None:
        """The functions run in the reverse order of their registration."""
        order: list[int] = []
        cleanups = Cleanups()
        cleanups.add(lambda: order.append(1))
        cleanups.add(lambda: order.append(2))
        cleanups.run(run_one)
        assert order == [2, 1]

    def test_runs_a_function_that_a_function_adds_in_the_same_pass(self) -> None:
        """A function that a function adds runs after the one that added it."""
        order: list[str] = []
        cleanups = Cleanups()

        def adding() -> None:
            order.append("adding")
            cleanups.add(lambda: order.append("added"))

        cleanups.add(adding)
        cleanups.run(run_one)
        assert order == ["adding", "added"]

    def test_leaves_a_function_that_arrives_after_the_run_to_the_next_run(
        self,
    ) -> None:
        """A run forgets what it ran, and a later function waits for the next run."""
        order: list[str] = []
        cleanups = Cleanups()
        cleanups.add(lambda: order.append("first run"))
        cleanups.run(run_one)
        kept = cleanups.add(lambda: order.append("second run"))
        assert (kept, order) == (True, ["first run"])
        cleanups.run(run_one)
        assert order == ["first run", "second run"]

    def test_leaves_a_closed_list_closed(self) -> None:
        """A run after close does not reopen the list."""
        cleanups = Cleanups()
        cleanups.close(run_one)
        cleanups.run(run_one)
        assert cleanups.add(lambda: None) is False


class TestCleanupsClose:
    """Cleanups.close runs the functions as run does, and keeps none after them."""

    def test_runs_a_function_that_a_function_adds_before_it_closes(self) -> None:
        """A function that a function adds runs before the list closes."""
        order: list[str] = []
        cleanups = Cleanups()

        def adding() -> None:
            order.append("adding")
            assert cleanups.add(lambda: order.append("added"))

        cleanups.add(adding)
        cleanups.close(run_one)
        assert order == ["adding", "added"]
