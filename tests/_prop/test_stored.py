"""The spec of _prop/stored.py tests the entries of the store of a property."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.case import Failing
from dokimi_assert._prop.engine.case import Case, Failed, Replaying
from dokimi_assert._prop.engine.choice import (
    UINT64_MAX,
    Choice,
    FloatBounds,
    IntegerBounds,
)
from dokimi_assert._prop.engine.execution import Execution
from dokimi_assert._prop.engine.generator import Float, Generator, Integer, Mapped
from dokimi_assert._prop.engine.store import name
from dokimi_assert._prop.engine.tokens import encode
from dokimi_assert._prop.identity import key_of, of_record
from dokimi_assert._prop.stored import differs, entry_of
from dokimi_assert._record.call import DEFINITION
from dokimi_assert.failure import Failure, Where
from dokimi_assert.seat import Collector
from helpers import integers

#: The location of the failure of the executions.
WHERE = Where("/work/tests/test_total.py", 9)

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))

#: A generator of values without a typed literal.
OPAQUE = Mapped(DIGITS, lambda _: object())


def failing(choices: list[Choice], *draws: tuple[str, Generator[Any]]) -> Execution:
    """Return a failed execution that decodes each generator under its label."""
    c = Case(Replaying(choices))
    for label, generator in draws:
        c.draw(generator, label)
    failure = Failure("equal", "the total", {}, WHERE)
    identity = of_record(failure)
    return Execution(c, "failed", Failed(key_of(identity), Failing(failure, identity)))


class TestEntryOf:
    """entry_of returns the file name and the entry of a failing case."""

    def test_returns_the_name_and_the_entry_of_a_failing_case(
        self, seat: Collector
    ) -> None:
        """The entry has the case."""
        execution = failing(integers(3), ("x", DIGITS))
        check.equal(
            seat,
            entry_of("the total is positive", execution, "2026-10-08"),
            (
                name("the total is positive", integers(3)),
                {
                    "store": 1,
                    "definition": DEFINITION,
                    "property": "the total is positive",
                    "identity": {
                        "assertion": "equal",
                        "file": "test_total.py",
                        "line": 9,
                    },
                    "choices": encode(integers(3)),
                    "counterexample": [
                        {"label": "x", "value": {"type": "int", "value": 3}}
                    ],
                    "found": "2026-10-08",
                },
            ),
            "the entry has the case",
        )

    def test_writes_only_the_label_of_a_draw_without_a_typed_literal(
        self, seat: Collector
    ) -> None:
        """The entry has only the label of the draw."""
        _, entry = entry_of("c", failing(integers(3), ("f", OPAQUE)), "2026-10-08")
        check.equal(
            seat,
            entry["counterexample"],
            [{"label": "f"}],
            "the entry has only the label",
        )


class TestDiffers:
    """differs reports whether a replayed case has values that differ from its entry."""

    tests: ClassVar[list[tuple[str, list[dict[str, Any]], bool]]] = [
        (
            "returns false for the labels and the values of the replay",
            [{"label": "x", "value": {"type": "int", "value": 3}}],
            False,
        ),
        ("returns false for a draw without a value", [{"label": "x"}], False),
        ("returns true for a different number of draws", [], True),
        (
            "returns true for a different label",
            [{"label": "y", "value": {"type": "int", "value": 3}}],
            True,
        ),
        (
            "returns true for a different value",
            [{"label": "x", "value": {"type": "int", "value": 4}}],
            True,
        ),
        (
            "returns true for a value that does not decode",
            [{"label": "x", "value": {"type": "bogus"}}],
            True,
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_compares_the_entry_with_the_replay(
        self, seat: Collector, give: list[dict[str, Any]], want: bool
    ) -> None:
        """The replay decodes 3 under the label x."""
        replayed = failing(integers(3), ("x", DIGITS))
        check.equal(seat, differs(give, replayed), want, "differs returns the verdict")

    def test_returns_false_for_an_int_that_another_implementation_writes_in_digits(
        self, seat: Collector
    ) -> None:
        """The two spellings have one value."""
        big = failing(
            integers(UINT64_MAX), ("x", Integer(IntegerBounds(0, UINT64_MAX)))
        )
        recorded = [{"label": "x", "value": {"type": "int", "value": str(UINT64_MAX)}}]
        check.is_false(seat, differs(recorded, big), "the two spellings are one value")

    def test_returns_true_for_a_recorded_negative_zero_that_replays_as_zero(
        self, seat: Collector
    ) -> None:
        """Two zeros differ."""
        zero = failing([Choice("float", 0.0)], ("x", Float(FloatBounds(-1.0, 1.0))))
        recorded = [{"label": "x", "value": {"type": "float", "value": -0.0}}]
        check.is_true(seat, differs(recorded, zero), "two zeros differ")

    def test_returns_true_for_a_recorded_value_whose_replay_does_not_have_a_literal(
        self, seat: Collector
    ) -> None:
        """The replay does not have a value."""
        replayed = failing(integers(3), ("x", OPAQUE))
        recorded = [{"label": "x", "value": {"type": "int", "value": 3}}]
        check.is_true(
            seat, differs(recorded, replayed), "the replay does not have a value"
        )
