"""The coverage test of a label against a required share of the cases.

The Wilson score interval of the share of the label decides a requirement.
The constants are those of the checkCoverage function of QuickCheck. The
certainty is 10^9, and the tolerance is 0.9. The runner checks every
requirement after cases valid cases. It checks again each time that count
doubles, and it stops at the last check. The test uses arithmetic and a
square root alone. IEEE 754 rounds both exactly, so every language decides
the same way from the same counts when it evaluates the bound in the order
written.
"""

from __future__ import annotations

import math
from typing import Literal

__all__ = ["CHECKS", "Verdict", "verdict"]

#: The standard normal quantile at 1 - 5e-10. It splits a certainty of 10^9
#: between the two tails.
_Z = 6.109410191663286

#: A requirement is met when the lower bound is at least this fraction of
#: the required share.
_TOLERANCE = 0.9

#: The checks as multiples of cases valid cases. The last entry is the last
#: check of the run.
CHECKS = (1, 2, 4, 8)

#: The decision of a check about one requirement.
Verdict = Literal["met", "refuted", "undecided", "unmet"]


def _bound(k: int, n: int, z: float) -> float:
    """Return the Wilson score bound of k successes in n trials at the quantile z.

    The bound is the upper one for a positive z, and the lower one for a
    negative z.
    """
    p = k / n
    a = (z * z) / n
    centre = p + a / 2
    spread = z * math.sqrt((p * (1 - p)) / n + a / (4 * n))
    return (centre + spread) / (1 + a)


def verdict(k: int, n: int, share: float, last: bool, exact: bool) -> Verdict:
    """Return the verdict of one requirement at one check.

    exact marks a run that tested every input of its domain. The shares of
    such a run are exact. An exact share, and an undecided share at the last
    check, are met when k / n is at least 0.9 times the share, and unmet
    otherwise.

    Args:
        k: The number of valid cases that the label counted.
        n: The number of valid cases. It is at least 1.
        share: The required share.
        last: When True, the check is the last of the run.
        exact: When True, the run tested every input of its domain.

    Returns:
        The verdict.

    Raises:
        ValueError: n is below 1, or k is outside [0, n].
    """
    if n < 1 or not 0 <= k <= n:
        raise ValueError(f"prop: {k} of {n} is not a share")
    if not exact:
        if _bound(k, n, -_Z) >= _TOLERANCE * share:
            return "met"
        if _bound(k, n, _Z) < share:
            return "refuted"
        if not last:
            return "undecided"
    return "met" if k / n >= _TOLERANCE * share else "unmet"
