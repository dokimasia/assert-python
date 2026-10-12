"""The strategies of the task scheduler, which choose the ready task to release."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Strategy", "pct", "uniform"]


@dataclass(frozen=True, slots=True)
class Strategy:
    """The way in which a Scheduler chooses the ready task to release.

    Attributes:
        depth: The depth of PCT, and 0 for the uniform strategy.
    """

    depth: int


def uniform() -> Strategy:
    """Return the strategy that chooses each release uniformly among the ready tasks.

    The ready tasks are in the order in which they became ready. The choice
    has the target 0 and the edge 0. A release with one ready task records a
    choice that does not consume the source. A shrunk schedule releases the
    tasks in the order in which they became ready, wherever the failure
    allows.

    Returns:
        The strategy.
    """
    return Strategy(0)


def pct(depth: int) -> Strategy:
    """Return the strategy of probabilistic concurrency testing of a depth.

    Each task receives a priority when it is spawned. The priority is a
    choice from 0 to 2^64 - 1 with the target 0, and the task keeps it when
    it yields. The ready task with the highest priority runs, the earliest
    ready among equals, and a release does not make a choice. Each run of the
    scheduler starts with depth - 1 change points. A change point is a
    presence choice with the edge 1, and then a count of releases. The task
    of the release at that count gets a lower priority than every other
    task. A later change point gives its task a lower priority still.

    Args:
        depth: The depth. Must be at least 1.

    Returns:
        The strategy.

    Raises:
        ValueError: depth is not an int of 1 or more.
    """
    if type(depth) is not int or depth < 1:
        raise ValueError(f"stateful: pct({depth!r}) needs an int of 1 or more")
    return Strategy(depth)
