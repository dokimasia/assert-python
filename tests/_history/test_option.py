"""The spec of _history/option.py tests the options of a check of linearizability."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._history.option import (
    BUDGET,
    MEMO_LIMIT,
    Config,
    Option,
    budget,
    configure,
    memo_limit,
    time_limit,
    workers,
)
from dokimi_assert.seat import Collector
from helpers import refusal

#: A case of a refusal. It has a name, the call, and the text of its ValueError.
Refusal = tuple[str, Callable[[], Option], str]


class TestBudget:
    """budget sets the steps of the search of one partition. BUDGET is the default."""

    def test_allows_10_000_000_steps_by_default(self, seat: Collector) -> None:
        """BUDGET is ten million steps."""
        check.equal(seat, BUDGET, 10_000_000, "the default budget is ten million steps")

    def test_returns_an_option_that_sets_the_budget_alone(
        self, seat: Collector
    ) -> None:
        """The option sets a budget of five steps."""
        check.equal(
            seat,
            configure([budget(5)]),
            Config(budget=5),
            "the option changes only the budget",
        )

    tests: ClassVar[list[Refusal]] = [
        ("0 steps", lambda: budget(0), "history: budget(0) needs an int of 1 or more"),
        (
            "a fraction of a step",
            lambda: budget(cast("Any", 1.5)),
            "history: budget(1.5) needs an int of 1 or more",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], Option], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(
            seat, refusal(seat, give), want, "the text of the refusal has the call"
        )


class TestMemoLimit:
    """memo_limit sets the bits that a memo can count. MEMO_LIMIT is the default."""

    def test_allows_2_to_the_33_bits_by_default(self, seat: Collector) -> None:
        """MEMO_LIMIT is 2^33 bits."""
        check.equal(seat, MEMO_LIMIT, 2**33, "the default memo limit is 2^33 bits")

    def test_returns_an_option_that_sets_the_memo_limit_alone(
        self, seat: Collector
    ) -> None:
        """The option sets a memo limit of 64 bits."""
        check.equal(
            seat,
            configure([memo_limit(64)]),
            Config(memo_limit=64),
            "the option changes only the memo limit",
        )

    def test_raises_value_error_for_0_bits(self, seat: Collector) -> None:
        """A memo of 0 bits cannot store a configuration."""
        check.equal(
            seat,
            refusal(seat, lambda: memo_limit(0)),
            "history: memo_limit(0) needs an int of 1 or more",
            "the text of the refusal has the call",
        )


class TestTimeLimit:
    """time_limit sets the seconds that the whole check can take."""

    def test_returns_an_option_that_sets_the_time_limit_alone(
        self, seat: Collector
    ) -> None:
        """The option sets a time limit of a quarter second."""
        check.equal(
            seat,
            configure([time_limit(0.25)]),
            Config(time_limit=0.25),
            "the option changes only the time limit",
        )

    def test_takes_a_time_of_an_int(self, seat: Collector) -> None:
        """The int 2 becomes the float 2.0."""
        check.equal(
            seat,
            configure([time_limit(2)]).time_limit,
            2.0,
            "the time limit is the float 2.0",
        )

    tests: ClassVar[list[Refusal]] = [
        (
            "a negative time",
            lambda: time_limit(-1),
            "history: time_limit(-1) needs a finite number of 0 or more",
        ),
        (
            "NaN",
            lambda: time_limit(math.nan),
            "history: time_limit(nan) needs a finite number of 0 or more",
        ),
        (
            "an infinite time",
            lambda: time_limit(math.inf),
            "history: time_limit(inf) needs a finite number of 0 or more",
        ),
        (
            "a time that is not a number",
            lambda: time_limit(cast("Any", "1")),
            "history: time_limit('1') needs a finite number of 0 or more",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], Option], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(
            seat, refusal(seat, give), want, "the text of the refusal has the call"
        )


class TestWorkers:
    """workers sets the number of partitions that a check searches at once."""

    def test_returns_an_option_that_sets_the_workers_alone(
        self, seat: Collector
    ) -> None:
        """The option sets four workers."""
        check.equal(
            seat,
            configure([workers(4)]),
            Config(workers=4),
            "the option changes only the workers",
        )

    def test_raises_value_error_for_0_workers(self, seat: Collector) -> None:
        """A check needs at least one worker."""
        check.equal(
            seat,
            refusal(seat, lambda: workers(0)),
            "history: workers(0) needs an int of 1 or more",
            "the text of the refusal has the call",
        )


class TestConfigure:
    """configure applies the options of a check to the defaults in order."""

    def test_returns_the_defaults_without_an_option(self, seat: Collector) -> None:
        """The list of options is empty."""
        check.equal(
            seat,
            configure([]),
            Config(10_000_000, 2**33, 0.0, 1),
            "configure returns the defaults",
        )

    def test_lets_a_later_option_replace_an_earlier_one(self, seat: Collector) -> None:
        """A budget of 7 follows a budget of 5."""
        check.equal(
            seat,
            configure([budget(5), budget(7)]).budget,
            7,
            "the later budget replaces the earlier one",
        )
