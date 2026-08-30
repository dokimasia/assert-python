"""Assertions about the order of a sequence."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from dokimi_assert._matcher.seat import Mode, Seat, report


def pairwise(
    seat: Seat,
    mode: Mode,
    items: Sequence[Any],
    predicate: Callable[[Any, Any], bool],
    msg: str,
) -> None:
    """Report when an adjacent pair fails the predicate.

    The predicate receives them in sequence order as (earlier, later).
    It states an ordering without naming one: pass a less-than for
    ascending, or any relation neighbours must satisfy.

    Nought or one item passes, having no pair to break. The failure
    names the index and both values of the first break.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        items: The sequence to walk.
        predicate: The relation that must hold.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    for index in range(1, len(items)):
        earlier, later = items[index - 1], items[index]
        if not predicate(earlier, later):
            report(
                seat,
                mode,
                f"{msg}: pair {index - 1} and {index} are out of order: "
                f"{earlier!r} then {later!r}",
            )
            return
