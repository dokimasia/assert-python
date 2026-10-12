"""The spec of _stateful/strategy.py tests the strategies of the task scheduler."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._stateful.strategy import Strategy, pct, uniform
from dokimi_assert.seat import Collector
from helpers import refusal


class TestUniform:
    """uniform returns the strategy that chooses each release among the ready tasks."""

    def test_returns_the_strategy_of_depth_0(self, seat: Collector) -> None:
        """The uniform strategy has no depth of PCT."""
        check.equal(seat, uniform(), Strategy(0), "the uniform strategy has depth 0")


class TestPct:
    """pct returns the strategy of probabilistic concurrency testing of a depth."""

    def test_returns_the_strategy_of_its_depth(self, seat: Collector) -> None:
        """The strategy of pct(3) has the depth 3."""
        check.equal(seat, pct(3), Strategy(3), "the strategy has the depth 3")

    tests: ClassVar[list[tuple[str, Any, str]]] = [
        ("the depth 0", 0, "stateful: pct(0) needs an int of 1 or more"),
        ("a fraction", 1.5, "stateful: pct(1.5) needs an int of 1 or more"),
        ("a bool", True, "stateful: pct(True) needs an int of 1 or more"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(
            seat,
            refusal(seat, lambda: pct(cast("int", give))),
            want,
            "the text of the refusal contains the call",
        )
