# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The cleanups of a seat.

A seat that has the member cleanup runs the functions that it registers when
its test, its case or its body ends, the last registered first. A function
that a function registers runs in the same pass. The seat decides what an
error of a function does, so the runs here take the function that runs one
cleanup.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Cleanups"]


class Cleanups:
    """The functions that a seat runs when its test or its body ends.

    The methods are safe for concurrent use.
    """

    def __init__(self) -> None:
        """Return an empty list of cleanups."""
        self._fns: list[Callable[[], object]] = []
        self._closed: bool = False
        self._guard: threading.Lock = threading.Lock()

    def add(self, fn: Callable[[], object]) -> bool:
        """Keep fn for the next run.

        Args:
            fn: The function.

        Returns:
            True when the list keeps fn, and False after close, when the
            caller runs fn at once.
        """
        with self._guard:
            if self._closed:
                return False
            self._fns.append(fn)
            return True

    def run(self, run_one: Callable[[Callable[[], object]], None]) -> None:
        """Run the functions that the list keeps, the last kept first, and forget them.

        A function that a function registers runs in the same pass. A
        function that arrives after the run waits for the next run.

        Args:
            run_one: Runs one function, and decides what an error of it does.
        """
        self._drain(run_one, closing=False)

    def close(self, run_one: Callable[[Callable[[], object]], None]) -> None:
        """Run the functions as run does, and then close the list.

        A closed list does not keep a function that arrives later.

        Args:
            run_one: Runs one function, and decides what an error of it does.
        """
        self._drain(run_one, closing=True)

    def _drain(
        self, run_one: Callable[[Callable[[], object]], None], *, closing: bool
    ) -> None:
        """Run the last kept function until none is left, then close when closing."""
        while True:
            with self._guard:
                if not self._fns:
                    self._closed = self._closed or closing
                    return
                fn = self._fns.pop()
            run_one(fn)
