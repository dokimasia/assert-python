# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The options of the steps of a machine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from dokimi_assert._stateful.scheduler import Scheduler

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "Config",
    "Option",
    "clients",
    "concurrent",
    "configure",
    "max_steps",
    "mean",
    "repeat",
    "swarm",
    "tasks",
]


@dataclass(frozen=True, slots=True)
class Config:
    """The settings of one run of steps with its options applied.

    The defaults are the settings that the definition fixes.

    Attributes:
        mean: The mean number of sequential steps.
        max_steps: The most sequential steps, and the most steps of the drain.
        swarm: When True, a case first chooses the actions that it keeps.
        clients: The clients of the concurrent section besides client 0.
        concurrent: The most steps of a concurrent section.
        scheduler: The scheduler whose tasks run the clients of a concurrent
            section, or None for clients on threads.
        repeat: The runs of a case whose concurrent section runs on threads.
    """

    mean: int = 30
    max_steps: int = 100
    swarm: bool = True
    clients: int = 1
    concurrent: int = 16
    scheduler: Scheduler | None = None
    repeat: int = 4


@dataclass(frozen=True, slots=True)
class Option:
    """An option of steps.

    A later option of a setting replaces an earlier one.

    Attributes:
        apply: Returns the settings with the setting of the option applied.
    """

    apply: Callable[[Config], Config]


def _counted(call: str, n: int, least: int) -> None:
    """Raise ValueError when n is not an int of least or more."""
    if type(n) is not int or n < least:
        msg = f"stateful: {call}({n!r}) needs an int of {least} or more"
        raise ValueError(msg)


def mean(n: int) -> Option:
    """Set the mean number of sequential steps of a case.

    The default is 30.

    Args:
        n: The mean. Must be at least 0.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 0 or more.
    """
    _counted("mean", n, 0)
    return Option(lambda config: replace(config, mean=n))


def max_steps(n: int) -> Option:
    """Set the most sequential steps of a case, and the most steps of its drain.

    The default is 100.

    Args:
        n: The most steps. Must be at least 0.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 0 or more.
    """
    _counted("max_steps", n, 0)
    return Option(lambda config: replace(config, max_steps=n))


def swarm(on: bool) -> Option:
    """Set whether a case first chooses the actions that it keeps.

    The default is True. Under False, a case keeps every action.

    Args:
        on: True to let a case choose its actions.

    Returns:
        The option.
    """
    return Option(lambda config: replace(config, swarm=on))


def clients(n: int) -> Option:
    """Set the clients of the concurrent section besides client 0.

    The default is 1. A case runs a concurrent section for n of 2 or more,
    on the clients 0 to n. The clients 1 to n run on threads, or as tasks of
    the scheduler of tasks.

    Args:
        n: The clients. Must be at least 1.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 1 or more.
    """
    _counted("clients", n, 1)
    return Option(lambda config: replace(config, clients=n))


def concurrent(n: int) -> Option:
    """Set the most steps of a concurrent section.

    The default is 16.

    Args:
        n: The most steps. Must be at least 0.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 0 or more.
    """
    _counted("concurrent", n, 0)
    return Option(lambda config: replace(config, concurrent=n))


def tasks(scheduler: Scheduler) -> Option:
    """Run the clients of a concurrent section as tasks of a scheduler.

    The releases of the scheduler are choices of the case, so a race replays
    and shrinks. Without this option, the clients run on threads.

    Args:
        scheduler: The scheduler.

    Returns:
        The option.
    """
    return Option(lambda config: replace(config, scheduler=scheduler))


def repeat(n: int) -> Option:
    """Set the runs of a case whose concurrent section runs on threads.

    The default is 4. Threads do not replay, so such a case runs up to n
    times on its choices, and it fails at the first run that fails. The
    replay before shrinking and each shrink candidate run the same way.

    Args:
        n: The runs. Must be at least 1.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 1 or more.
    """
    _counted("repeat", n, 1)
    return Option(lambda config: replace(config, repeat=n))


def configure(options: Iterable[Option]) -> Config:
    """Return the defaults with each option applied in order.

    Args:
        options: The options of the run.

    Returns:
        The settings.
    """
    config = Config()
    for option in options:
        config = option.apply(config)
    return config
