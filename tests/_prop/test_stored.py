# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/stored.py tests the entries of the store of a property."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.case import Failing
from dokimi_assert._prop.engine.case import Case, Failed, Replaying, Step
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
from dokimi_assert._prop.engine.traces import UNSTATED, Draw
from dokimi_assert._prop.identity import key_of, of_record
from dokimi_assert._prop.stored import differs, entry_of, stored_of, trace_of
from dokimi_assert._record.call import DEFINITION
from dokimi_assert.failure import Failure, Where
from helpers import integers, values_of

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The location of the failure of the executions.
WHERE = Where("/work/tests/test_total.py", 9)

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))

#: A generator of values without a typed literal.
OPAQUE = Mapped(DIGITS, lambda _: object())

#: The literal of the digit 3.
THREE = {"type": "int", "value": 3}


def failing(
    choices: list[Choice], *requests: tuple[str, Generator[Any]] | Step
) -> Execution:
    """Return a failed execution of the steps and the draws of requests.

    The case decodes each generator under its label and takes each step.
    """
    c = Case(Replaying(choices))
    for request in requests:
        if isinstance(request, Step):
            c.step(request)
            continue
        label, generator = request
        c.draw(generator, label)
    failure = Failure("equal", "the total", {}, WHERE)
    identity = of_record(failure)
    return Execution(c, "failed", Failed(key_of(identity), Failing(failure, identity)))


#: The failed execution of a machine with a step of each form.
MACHINE = failing(
    integers(2, 3),
    ("capacity", DIGITS),
    Step("put"),
    ("v", DIGITS),
    Step("get", 1),
    Step("put", None, True),
)


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

    def test_writes_format_2_with_the_steps_of_a_machine_among_the_draws(
        self, seat: Collector
    ) -> None:
        """The steps keep their places in request order."""
        _, entry = entry_of("c", MACHINE, "2026-11-10")
        check.equal(
            seat,
            [entry["store"], entry["counterexample"]],
            [
                2,
                [
                    {"label": "capacity", "value": {"type": "int", "value": 2}},
                    {"step": "put"},
                    {"label": "v", "value": THREE},
                    {"step": "get", "client": 1},
                    {"step": "put", "drain": True},
                ],
            ],
            "the entry has the steps among the draws",
        )


class TestTraceOf:
    """trace_of returns the counterexample of an entry as a trace."""

    tests: ClassVar[list[tuple[str, list[dict[str, Any]], list[object]]]] = [
        (
            "returns the draws and the steps in their order",
            [
                {"label": "x", "value": THREE},
                {"step": "put"},
                {"step": "get", "client": 1},
                {"step": "put", "drain": True},
            ],
            [Draw("x", 3), Step("put"), Step("get", 1), Step("put", None, True)],
        ),
        (
            "returns unstated for a draw without a value",
            [{"label": "x"}],
            [Draw("x", UNSTATED)],
        ),
        (
            "returns unstated for a value that does not decode",
            [{"label": "x", "value": {"type": "bogus"}}],
            [Draw("x", UNSTATED)],
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_entries_of_the_counterexample(
        self, seat: Collector, give: list[dict[str, Any]], want: list[object]
    ) -> None:
        """Each entry of the counterexample is one entry of the trace."""
        check.equal(seat, list(trace_of(give)), want, "the trace has every entry")


class TestStoredOf:
    """stored_of returns the stored case of an entry."""

    def test_follows_the_counterexample_of_the_entry(self, seat: Collector) -> None:
        """The stored case has the choices and the trace of the entry."""
        recorded = [{"label": "x", "value": THREE}]
        stored = stored_of(integers(4), recorded)
        check.equal(
            seat,
            [values_of(list(stored.choices)), list(stored.trace)],
            [values_of(integers(4)), [Draw("x", 3)]],
            "the stored case has the choices and the trace",
        )

    def test_matches_a_case_that_decodes_to_the_counterexample(
        self, seat: Collector
    ) -> None:
        """3 is the value of the entry, and 4 is another value."""
        matches = stored_of(integers(3), [{"label": "x", "value": THREE}]).matches
        same = failing(integers(3), ("x", DIGITS))
        other = failing(integers(4), ("x", DIGITS))
        check.equal(
            seat,
            None if matches is None else [matches(same), matches(other)],
            [True, False],
            "the stored case matches the case of the value of the entry alone",
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

    steps: ClassVar[list[tuple[str, list[dict[str, Any]], bool]]] = [
        (
            "returns false for the steps and the draws of the replay",
            [
                {"label": "capacity"},
                {"step": "put"},
                {"label": "v", "value": THREE},
                {"step": "get", "client": 1},
                {"step": "put", "drain": True},
            ],
            False,
        ),
        (
            "returns false for the draws alone of an entry of format 1",
            [{"label": "capacity"}, {"label": "v", "value": THREE}],
            False,
        ),
        (
            "returns true for another action",
            [
                {"label": "capacity"},
                {"step": "get"},
                {"label": "v", "value": THREE},
                {"step": "get", "client": 1},
                {"step": "put", "drain": True},
            ],
            True,
        ),
        (
            "returns true for another client",
            [
                {"label": "capacity"},
                {"step": "put"},
                {"label": "v", "value": THREE},
                {"step": "get", "client": 2},
                {"step": "put", "drain": True},
            ],
            True,
        ),
        (
            "returns true for a step without the drain mark of the replay",
            [
                {"label": "capacity"},
                {"step": "put"},
                {"label": "v", "value": THREE},
                {"step": "get", "client": 1},
                {"step": "put"},
            ],
            True,
        ),
        (
            "returns true for a step that the replay does not take",
            [
                {"label": "capacity"},
                {"step": "put"},
                {"label": "v", "value": THREE},
                {"step": "get", "client": 1},
            ],
            True,
        ),
        (
            "returns true for a draw in place of a step",
            [
                {"label": "capacity"},
                {"label": "v", "value": THREE},
                {"step": "put"},
                {"step": "get", "client": 1},
                {"step": "put", "drain": True},
            ],
            True,
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in steps], ids=[t[0] for t in steps]
    )
    def test_compares_the_steps_of_an_entry_with_the_replay(
        self, seat: Collector, give: list[dict[str, Any]], want: bool
    ) -> None:
        """The replay takes three steps around the draws."""
        check.equal(seat, differs(give, MACHINE), want, "differs returns the verdict")
