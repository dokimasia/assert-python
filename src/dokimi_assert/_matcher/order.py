# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertion about the relation of neighbouring items.

One assertion checks sorted, unique and strictly increasing, because each of
them is a relation between every two adjacent items and nothing more.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.verdict import fail, pass_

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from dokimi_assert._matcher.seat import Mode, Seat

__all__ = ["pairwise"]


def pairwise(
    seat: Seat,
    mode: Mode,
    items: Sequence[Any],
    predicate: Callable[[Any, Any], object],
    msg: str,
) -> None:
    """Report when an adjacent pair of items does not satisfy the predicate.

    The detail of the failure has the position of the first item of the
    pair as index, and the two items as first and second. An empty sequence
    and a sequence of one item pass, because neither has a pair.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        items: The sequence.
        predicate: Receives an item and the item after it.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    for index in range(1, len(items)):
        first, second = items[index - 1], items[index]
        if not predicate(first, second):
            detail = {"index": index - 1, "first": first, "second": second}
            fail(seat, mode, "pairwise", msg, detail)
            return
    pass_(seat, mode, "pairwise", msg)
