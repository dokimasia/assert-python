"""The options that set the limits and the workers of a check of linearizability."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

__all__ = [
    "BUDGET",
    "MEMO_LIMIT",
    "Config",
    "Option",
    "budget",
    "configure",
    "memo_limit",
    "time_limit",
    "workers",
]

#: The default number of steps that the search of one partition can spend.
BUDGET = 10_000_000

#: The default number of bits that the memo of one partition can count. 2^33
#: bits are 1 GiB.
MEMO_LIMIT = 2**33


@dataclass(frozen=True, slots=True)
class Config:
    """The settings of one check with its options applied.

    Attributes:
        budget: The steps that the search of one partition can spend.
        memo_limit: The bits that the memo of one partition can count.
        time_limit: The seconds that the check can take. A value of 0 does
            not set a limit.
        workers: The number of partitions that the check searches at once.
    """

    budget: int = BUDGET
    memo_limit: int = MEMO_LIMIT
    time_limit: float = 0.0
    workers: int = 1


@dataclass(frozen=True, slots=True)
class Option:
    """An option of a check of linearizability.

    A later option of a setting replaces an earlier one.

    Attributes:
        apply: Returns the settings with the setting of the option applied.
    """

    apply: Callable[[Config], Config]


def _counted(call: str, n: int, least: int) -> int:
    """Return n if it is an int of least or more.

    Raises:
        ValueError: n is not an int of least or more.
    """
    if type(n) is not int or n < least:
        raise ValueError(f"history: {call}({n!r}) needs an int of {least} or more")
    return n


def budget(steps: int) -> Option:
    """Set the steps that the search of one partition can spend.

    The default is 10,000,000 steps. A step is one call of the next of the
    spec. A step of a spec that spec_from returns costs one step for each
    call that it applies. The search does not take a step past its budget.
    It ends as undecided at the limit steps.

    Args:
        steps: The number of steps. Must be at least 1.

    Returns:
        The option.

    Raises:
        ValueError: steps is not an int of 1 or more.
    """
    _counted("budget", steps, 1)
    return Option(lambda config: replace(config, budget=steps))


def memo_limit(bits: int) -> Option:
    """Set the bits that the memo of the search of one partition can count.

    The default is 2^33 bits, or 1 GiB. Each configuration in the memo counts
    one bit for each call of the partition. The search does not store a
    configuration past the limit. It ends as undecided at the limit memo.

    Args:
        bits: The number of bits. Must be at least 1.

    Returns:
        The option.

    Raises:
        ValueError: bits is not an int of 1 or more.
    """
    _counted("memo_limit", bits, 1)
    return Option(lambda config: replace(config, memo_limit=bits))


def time_limit(seconds: float) -> Option:
    """Set the seconds that the whole check can take.

    The check measures the time on the platform clock and not on the clock
    of the seat. The default of 0 does not set a limit. The search reads the
    clock before its first step and every 1,024 steps after it. Once the
    time has passed, it ends as undecided at the limit time. A time limit
    makes the outcome depend on the machine.

    Args:
        seconds: The time. Must be a finite number of 0 or more.

    Returns:
        The option.

    Raises:
        ValueError: seconds is not a finite number of 0 or more.
    """
    if type(seconds) not in (int, float) or not 0 <= seconds < math.inf:
        raise ValueError(
            f"history: time_limit({seconds!r}) needs a finite number of 0 or more"
        )
    return Option(lambda config: replace(config, time_limit=float(seconds)))


def workers(n: int) -> Option:
    """Set the number of partitions that the check searches at once.

    The default is 1. Above 1, the check searches the partitions on n
    threads. It reports the same detail as a check on one worker. The check
    then calls the functions of the spec on more than one thread at once, so
    they must be thread-safe.

    Args:
        n: The number of workers. Must be at least 1.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 1 or more.
    """
    _counted("workers", n, 1)
    return Option(lambda config: replace(config, workers=n))


def configure(options: Iterable[Option]) -> Config:
    """Return the defaults with each option applied in order.

    Args:
        options: The options of the check.

    Returns:
        The settings.
    """
    config = Config()
    for option in options:
        config = option.apply(config)
    return config
