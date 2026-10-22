# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/coverage.py tests the coverage test.

Each verdict is the verdict of the reference implementation of the
definition on the same counts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.coverage import CHECKS, Verdict, verdict

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestChecks:
    """CHECKS has the checks of a run as multiples of its cases."""

    def test_contains_each_power_of_two_up_to_8(self, seat: Collector) -> None:
        """The last check is at 8 times the cases."""
        check.equal(seat, CHECKS, (1, 2, 4, 8), "CHECKS has the powers of two up to 8")


class TestVerdict:
    """verdict returns the verdict of one requirement at one check."""

    tests: ClassVar[list[tuple[str, int, int, float, bool, bool, Verdict]]] = [
        ("returns met for 27 of 100 against 10%", 27, 100, 0.1, False, False, "met"),
        (
            "returns undecided for 26 of 100 against 10% before the last check",
            26,
            100,
            0.1,
            False,
            False,
            "undecided",
        ),
        (
            "returns undecided for 10 of 100 against 10% before the last check",
            10,
            100,
            0.1,
            False,
            False,
            "undecided",
        ),
        (
            "returns refuted for none of 100 against 50%",
            0,
            100,
            0.5,
            False,
            False,
            "refuted",
        ),
        (
            "returns met for 75 of 800 against 10% at the last check",
            75,
            800,
            0.1,
            True,
            False,
            "met",
        ),
        (
            "returns unmet for 70 of 800 against 10% at the last check",
            70,
            800,
            0.1,
            True,
            False,
            "unmet",
        ),
        (
            "returns refuted for none of 800 against 50% at the last check",
            0,
            800,
            0.5,
            True,
            False,
            "refuted",
        ),
        (
            "returns undecided for 6 of 6 against 100% from the interval",
            6,
            6,
            1.0,
            False,
            False,
            "undecided",
        ),
        (
            "returns met for 9 of 10 against an exact 100%",
            9,
            10,
            1.0,
            True,
            True,
            "met",
        ),
        (
            "returns met for one of six exact inputs against 10%",
            1,
            6,
            0.1,
            False,
            True,
            "met",
        ),
        (
            "returns unmet for none of six exact inputs against 10%",
            0,
            6,
            0.1,
            False,
            True,
            "unmet",
        ),
        (
            "returns met for six of six exact inputs against 100%",
            6,
            6,
            1.0,
            False,
            True,
            "met",
        ),
    ]

    @pytest.mark.parametrize(
        ("k", "n", "share", "last", "exact", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_verdict_of_the_counts(
        self,
        seat: Collector,
        k: int,
        n: int,
        share: float,
        last: bool,
        exact: bool,
        want: Verdict,
    ) -> None:
        """The Wilson score interval decides an inexact share."""
        check.equal(
            seat,
            verdict(k, n, share, last, exact),
            want,
            "verdict returns the verdict of the reference",
        )

    refusals: ClassVar[list[tuple[str, int, int]]] = [
        ("raises value error without a trial", 0, 0),
        ("raises value error for a negative count", -1, 10),
        ("raises value error for more successes than trials", 11, 10),
    ]

    @pytest.mark.parametrize(
        ("k", "n"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_value_error_for_counts_that_are_not_a_share(
        self, seat: Collector, k: int, n: int
    ) -> None:
        """A share has at least one trial, and its successes do not outnumber them."""
        error = check.raises(
            seat, lambda: verdict(k, n, 0.5, False, False), "verdict raises"
        )
        check.error_as(seat, error, ValueError, "the error is a ValueError")
        check.equal(
            seat,
            str(error),
            f"prop: {k} of {n} is not a share",
            "the error has the counts",
        )
