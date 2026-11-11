# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/traces.py tests the traces of cases and their provider."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import Case, Replaying, Step
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.generator import Composite, Integer, Mapped, Optional
from dokimi_assert._prop.engine.traces import (
    UNSTATED,
    Draw,
    Entry,
    TraceError,
    Tracing,
    entries,
    is_step,
)
from helpers import integers, values_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert.seat import Collector

#: The generator that most draws use.
DIGIT = Integer(IntegerBounds(0, 9))

#: A composite of two digits drawn under a and b. Its value is their list.
PAIR = Composite(lambda c: [c.draw(DIGIT, "a"), c.draw(DIGIT, "b")])


def refused(seat: Collector, call: Callable[[], object]) -> list[object]:
    """Return the fields of the TraceError that call raises."""
    error = check.raises(seat, call, "the call raises")
    check.error_as(seat, error, TraceError, "the error is a TraceError")
    traced = cast("TraceError", error)
    return [traced.entry, traced.what, traced.reason]


class TestUnstated:
    """UNSTATED is the value of a draw entry that does not record a value."""

    def test_has_the_repr_of_its_name(self, seat: Collector) -> None:
        """A trace shows the value by its name."""
        check.equal(seat, repr(UNSTATED), "UNSTATED", "the repr is the name")


class TestIsStep:
    """is_step reports whether an entry is a step entry."""

    def test_returns_true_only_for_a_step_entry(self, seat: Collector) -> None:
        """The entries are of both kinds."""
        check.equal(
            seat,
            [is_step(Step("put")), is_step(Draw("v", 1))],
            [True, False],
            "is_step is true for the step entry alone",
        )


class TestTraceError:
    """TraceError is the refusal of an entry that the body cannot follow."""

    def test_returns_the_error_of_an_entry_at_its_position(
        self, seat: Collector
    ) -> None:
        """The error has a text and three fields."""
        error = TraceError(1, "get", "step")
        check.equal(
            seat,
            [str(error), error.entry, error.what, error.reason],
            ["prop: trace entry 1 (get): step", 1, "get", "step"],
            "the error has the entry, the label and the reason",
        )
        check.error_as(seat, error, ValueError, "a TraceError is a ValueError")


class TestEntries:
    """entries returns the draws and the steps of a case in request order."""

    def test_lists_each_step_before_the_draws_recorded_after_it(
        self, seat: Collector
    ) -> None:
        """The trace has the steps and the draws in request order."""
        c = Case(Replaying(integers(3, 4)))
        c.step(Step("put"))
        c.draw(DIGIT, "v")
        c.step(Step("get", 1))
        c.step(Step("put", None, True))
        c.draw(DIGIT, "w")
        c.step(Step("get"))
        check.equal(
            seat,
            entries(c),
            [
                Step("put"),
                Draw("v", 3),
                Step("get", 1),
                Step("put", None, True),
                Draw("w", 4),
                Step("get"),
            ],
            "entries returns the trace in request order",
        )


class TestTracingDrawing:
    """Tracing.drawing prepares the choices of the next entry for a draw."""

    def test_prepares_the_choices_of_the_value_of_the_entry_for_its_draw(
        self, seat: Collector
    ) -> None:
        """The draws decode the values of the entries."""
        c = Case(Tracing([Draw("x", 7), Draw("y", None)]))
        check.equal(
            seat,
            [c.draw(DIGIT, "x"), c.draw(Optional(DIGIT), "y"), values_of(c.choices)],
            [7, None, [("integer", 7), ("integer", 0)]],
            "the draws return the values of the entries",
        )

    def test_does_not_prepare_a_choice_for_a_draw_past_the_last_entry(
        self, seat: Collector
    ) -> None:
        """The draw takes the target."""
        c = Case(Tracing([Draw("x", 7)]))
        c.draw(DIGIT, "x")
        got = c.draw(Integer(IntegerBounds(3, 9)), "y")
        check.equal(seat, got, 3, "the draw returns the target")

    def test_raises_trace_error_for_a_draw_with_another_label_than_its_entry(
        self, seat: Collector
    ) -> None:
        """The error has the entry, the label and the reason."""
        c = Case(Tracing([Draw("y", 7)]))
        got = refused(seat, lambda: c.draw(DIGIT, "x"))
        check.equal(
            seat, got, [0, "x", "label"], "the error is at entry 0 for the label"
        )

    def test_raises_trace_error_for_a_draw_where_a_step_entry_is_next(
        self, seat: Collector
    ) -> None:
        """A step entry does not have a label."""
        c = Case(Tracing([Step("put")]))
        got = refused(seat, lambda: c.draw(DIGIT, "v"))
        check.equal(
            seat, got, [0, "v", "label"], "the error is at entry 0 for the label"
        )

    def test_raises_trace_error_for_a_value_that_the_generator_cannot_produce(
        self, seat: Collector
    ) -> None:
        """12 is not a digit."""
        c = Case(Tracing([Draw("x", 7), Draw("x", 12)]))
        c.draw(DIGIT, "x")
        got = refused(seat, lambda: c.draw(DIGIT, "x"))
        check.equal(
            seat, got, [1, "x", "value"], "the error is at entry 1 for the value"
        )

    def test_raises_trace_error_for_an_entry_that_does_not_record_a_value(
        self, seat: Collector
    ) -> None:
        """The value of the entry is UNSTATED."""
        c = Case(Tracing([Draw("x", UNSTATED)]))
        got = refused(seat, lambda: c.draw(DIGIT, "x"))
        check.equal(
            seat, got, [0, "x", "value"], "the error is at entry 0 for the value"
        )

    def test_raises_an_error_of_the_generator_that_is_not_a_refusal(
        self, seat: Collector
    ) -> None:
        """The map raises TypeError."""

        def broke(_: int) -> int:
            msg = "the map broke"
            raise TypeError(msg)

        c = Case(Tracing([Draw("x", 1)]))
        error = check.raises(
            seat, lambda: c.draw(Mapped(DIGIT, broke, int), "x"), "the draw raises"
        )
        check.error_as(seat, error, TypeError, "the error is the error of the map")


class TestTracingDrawn:
    """Tracing.drawn takes the entry of a composite once its draws have taken theirs."""

    def test_takes_the_entry_of_a_composite_after_the_entries_of_its_draws(
        self, seat: Collector
    ) -> None:
        """The draws decode their values, and the pair takes its entry by its label."""
        trace = Tracing([Draw("a", 7), Draw("b", 3), Draw("pair", UNSTATED)])
        c = Case(trace)
        check.equal(
            seat,
            [c.draw(PAIR, "pair"), trace.taken, values_of(c.choices)],
            [[7, 3], 3, [("integer", 7), ("integer", 3)]],
            "the pair takes the three entries",
        )

    def test_takes_the_entry_of_an_inner_composite_before_the_outer_one(
        self, seat: Collector
    ) -> None:
        """The inner pair takes its entry before the draw of c."""
        outer = Composite(lambda c: [c.draw(PAIR, "pair"), c.draw(DIGIT, "c")])
        trace = Tracing(
            [
                Draw("a", 1),
                Draw("b", 2),
                Draw("pair", [1, 2]),
                Draw("c", 5),
                Draw("outer", UNSTATED),
            ]
        )
        check.equal(
            seat,
            [Case(trace).draw(outer, "outer"), trace.taken],
            [[[1, 2], 5], 5],
            "the composites take every entry",
        )

    def test_takes_no_entry_for_a_composite_past_the_last_entry(
        self, seat: Collector
    ) -> None:
        """The second draw of the pair takes its target."""
        trace = Tracing([Draw("a", 7)])
        check.equal(
            seat,
            [Case(trace).draw(PAIR, "pair"), trace.taken],
            [[7, 0], 1],
            "the pair takes one entry",
        )

    def test_takes_no_entry_after_a_draw_that_is_not_a_composite(
        self, seat: Collector
    ) -> None:
        """The digit takes its entry when its draw starts."""
        trace = Tracing([Draw("x", 7), Draw("y", 1)])
        Case(trace).draw(DIGIT, "x")
        check.equal(seat, trace.taken, 1, "the digit takes one entry")

    ends: ClassVar[list[tuple[str, Entry]]] = [
        (
            "raises trace error for an entry of another label after the draws",
            Draw("other", [7, 3]),
        ),
        ("raises trace error for a step entry after the draws", Step("put")),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in ends], ids=[t[0] for t in ends])
    def test_raises_trace_error_for_another_entry_at_the_end_of_a_composite(
        self, seat: Collector, give: Entry
    ) -> None:
        """The entry follows the draws of the pair."""
        c = Case(Tracing([Draw("a", 7), Draw("b", 3), give]))
        got = refused(seat, lambda: c.draw(PAIR, "pair"))
        check.equal(
            seat, got, [2, "pair", "label"], "the error is at entry 2 for the label"
        )


class TestTracingValue:
    """Tracing.value returns the next prepared value of a request."""

    def test_returns_the_target_of_a_request_outside_a_draw(
        self, seat: Collector
    ) -> None:
        """The provider does not have a prepared value."""
        c = Case(Tracing([Draw("x", 7)]))
        check.equal(
            seat, c.integer(IntegerBounds(2, 5)), 2, "the request takes its target"
        )


class TestTracingPrepare:
    """Tracing.prepare serves integer values to the next requests."""

    def test_serves_a_prepared_value_fitted_to_its_request(
        self, seat: Collector
    ) -> None:
        """0 is outside [1, 1]."""
        trace = Tracing([])
        c = Case(trace)
        trace.prepare(0)
        check.equal(
            seat,
            c.integer(IntegerBounds(1, 1)),
            1,
            "the request fits the value to its bounds",
        )


class TestTracingNextStep:
    """Tracing.next_step returns the next entry when it is a step entry."""

    def test_returns_the_next_entry_when_it_is_a_step_entry(
        self, seat: Collector
    ) -> None:
        """The next entry is a step entry."""
        check.equal(
            seat,
            Tracing([Step("put")]).next_step(),
            Step("put"),
            "next_step returns the step",
        )

    def test_returns_none_when_the_next_entry_is_a_draw_entry(
        self, seat: Collector
    ) -> None:
        """A draw is next."""
        check.is_none(
            seat, Tracing([Draw("v", 1)]).next_step(), "next_step returns None"
        )

    def test_returns_none_past_the_last_entry(self, seat: Collector) -> None:
        """The trace is empty."""
        check.is_none(seat, Tracing([]).next_step(), "next_step returns None")


class TestTracingTake:
    """Tracing.take takes the next step entry and serves the values of its choices."""

    def test_serves_the_choices_of_a_step_entry_before_the_next_entry(
        self, seat: Collector
    ) -> None:
        """The trace serves the steps, the actions and the values."""
        trace = Tracing([Step("put"), Step("get", 1), Draw("v", 2)])
        c = Case(trace)
        before = [trace.next_step(), trace.actions()]
        trace.take(1, 4)
        after = [trace.next_step(), trace.actions()]
        bounds = IntegerBounds(0, 9)
        values = [c.integer(bounds), c.integer(bounds), c.integer(bounds)]
        trace.take()
        check.equal(
            seat,
            [before, after, values, trace.next_step()],
            [
                [Step("put"), ["put", "get"]],
                [Step("get", 1), ["get"]],
                [1, 4, 0],
                None,
            ],
            "take serves the choices of the step before the next entry",
        )


class TestTracingTaken:
    """Tracing.taken is the number of entries that the draws and the steps took."""

    def test_counts_the_entries_of_the_draws_and_the_steps(
        self, seat: Collector
    ) -> None:
        """A draw and a step take two of the three entries."""
        trace = Tracing([Draw("v", 1), Step("get"), Draw("w", 2)])
        c = Case(trace)
        before = trace.taken
        c.draw(DIGIT, "v")
        drawn = trace.taken
        trace.take()
        check.equal(
            seat,
            [before, drawn, trace.taken],
            [0, 1, 2],
            "the draw and the step each take one entry",
        )


class TestTracingActions:
    """Tracing.actions returns the actions of the step entries from the next one on."""

    def test_returns_each_action_once_in_trace_order(self, seat: Collector) -> None:
        """The trace has two actions."""
        trace = Tracing([Step("put"), Draw("v", 1), Step("get"), Step("put")])
        check.equal(
            seat, trace.actions(), ["put", "get"], "actions returns each action once"
        )


class TestTracingRefuse:
    """Tracing.refuse fails on a step entry that the machine cannot take."""

    def test_raises_trace_error_at_the_next_step_entry(self, seat: Collector) -> None:
        """The second entry is a step entry."""
        trace = Tracing([Draw("v", 1), Step("get")])
        c = Case(trace)
        c.draw(DIGIT, "v")
        check.equal(
            seat,
            refused(seat, trace.refuse),
            [1, "get", "step"],
            "the error is at the step entry",
        )
