# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/case.py tests the values and the record of a case.

The pinned draws are the draws of the reference implementation of the
definition. The signals of a case derive from BaseException. The raises
assertion does not catch them, so the spec catches them with pytest.raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from dokimi_assert import check
from dokimi_assert._override import override
from dokimi_assert._prop.engine import draw
from dokimi_assert._prop.engine.case import (
    MAX_CHOICES,
    Case,
    Decoder,
    Failed,
    Generating,
    Overrun,
    Place,
    Provider,
    Rejected,
    Replaying,
    Request,
    Span,
    Step,
    Trailing,
    Valuing,
    Walked,
    Where,
)
from dokimi_assert._prop.engine.choice import (
    INT64_MAX,
    INT64_MIN,
    UINT64_MAX,
    Choice,
    IntegerBounds,
    SequenceBounds,
    Value,
)
from dokimi_assert._prop.engine.source import Source
from helpers import Decoding, integers, values_of

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The bounds that most cases request.
DIGIT = IntegerBounds(0, 9)

#: The bounds of the reuse cases.
WIDE = IntegerBounds(0, 1_000_000_000)


def digit() -> Request:
    """Return a request for one digit that draw.integer draws."""
    return Request(DIGIT, lambda source: draw.integer(source, DIGIT))


def sequence_of(bounds: SequenceBounds) -> Request:
    """Return a request for one sequence inside bounds."""
    return Request(bounds, lambda source: draw.sequence(source, bounds))


def refuse(c: Case) -> Any:
    """Request a digit, then reject the case."""
    c.choose(digit())
    raise Rejected


#: A generator of one digit that does not open a span.
DIGITS = Decoding(lambda c: c.choose(digit()))

#: A generator that requests a digit, then draws a digit under the label
#: inner.
OUTER = Decoding(lambda c: [c.choose(digit()), c.draw(DIGITS, "inner")])

#: A generator that requests a digit, then rejects the case.
REFUSING = Decoding(refuse)


class TestMaxChoices:
    """MAX_CHOICES is the cap of a case."""

    def test_contains_8192(self, seat: Collector) -> None:
        """A case makes at most 8192 choices."""
        check.equal(seat, MAX_CHOICES, 8192, "the cap is 8192")


class TestDecoder:
    """Decoder is the protocol of the decoder of the values of a domain."""

    def test_describes_a_generator_with_a_decode(self, seat: Collector) -> None:
        """A decode method of a case is enough."""
        decoder: Decoder[Any] = DIGITS
        check.equal(
            seat,
            decoder.decode(Case(Replaying(integers(4)))),
            4,
            "the decoder returns 4",
        )


class TestRejected:
    """Rejected is the signal of a rejected case."""

    def test_returns_the_signal_of_a_rejected_case(self, seat: Collector) -> None:
        """A body that catches Exception does not catch the signal."""
        signal = Rejected()
        check.equal(
            seat, str(signal), "prop: the case is rejected", "the signal has its text"
        )
        check.is_false(
            seat, isinstance(signal, Exception), "the signal is not an Exception"
        )


class TestOverrun:
    """Overrun is the signal of a case past its cap."""

    def test_is_a_rejection(self, seat: Collector) -> None:
        """An overrun is a rejection."""
        check.error_as(seat, Overrun(), Rejected, "the signal is a Rejected")


class TestFailed:
    """Failed is the failure of a body."""

    def test_returns_the_failure_of_an_identity_with_its_record(
        self, seat: Collector
    ) -> None:
        """The failure keeps its identity and its record."""
        failed = Failed("true@a.py:1", {"assertion": "true"})
        check.equal(
            seat,
            [str(failed), failed.identity, failed.record],
            [
                "prop: the case fails as true@a.py:1",
                "true@a.py:1",
                {"assertion": "true"},
            ],
            "the failure has its text, its identity and its record",
        )
        check.is_false(
            seat, isinstance(failed, Exception), "the failure is not an Exception"
        )


class TestRequest:
    """Request is one choice that a generator requests."""

    def test_defaults_the_edge_to_none_and_reuse_to_false(
        self, seat: Collector
    ) -> None:
        """A value choice does not reuse an earlier value by default."""
        request = digit()
        check.equal(
            seat,
            (request.edge, request.reuse),
            (None, False),
            "the edge is None and reuse is False",
        )


class TestProvider:
    """Provider provides the values of a case."""

    def test_returns_the_target_and_no_value_of_a_draw(self, seat: Collector) -> None:
        """A plain provider does not give a value."""
        provider = Provider()
        provider.drawing(DIGITS, "a")
        check.equal(
            seat,
            [
                provider.value(Request(IntegerBounds(3, 9), lambda _: 9), 0),
                provider.valued(),
            ],
            [3, None],
            "the provider returns the target and no value",
        )


class TestStep:
    """Step is one step that a machine took."""

    def test_defaults_the_client_to_none_and_drain_to_false(
        self, seat: Collector
    ) -> None:
        """A sequential step does not have a client."""
        check.equal(
            seat,
            Step("put"),
            Step("put", None, False),
            "the client is None and drain is False",
        )


class TestPlace:
    """Place is the part of the steps of a machine and its step."""

    def test_defaults_the_position_and_the_action_to_none(
        self, seat: Collector
    ) -> None:
        """A place can have a part alone."""
        check.equal(
            seat,
            Place("swarm"),
            Place("swarm", None, None),
            "the position and the action are None",
        )


class TestWhere:
    """Where is the place where a case made a request."""

    def test_defaults_the_label_and_the_place_to_none(self, seat: Collector) -> None:
        """A request outside every draw and every machine has neither."""
        check.equal(
            seat, Where(), Where(None, None), "the label and the place are None"
        )


class TestWalked:
    """Walked is one step of the kept walk of a case."""

    def test_keeps_the_index_the_request_the_value_and_the_where(
        self, seat: Collector
    ) -> None:
        """Walked keeps the four fields."""
        request = digit()
        step = Walked(2, request, 7, Where("n"))
        check.equal(
            seat,
            [step.index, step.request is request, step.value, step.where],
            [2, True, 7, Where("n")],
            "the step keeps the four fields",
        )


class TestGeneratingValue:
    """Generating.value draws a value from the random source."""

    def test_returns_the_draw_of_each_request(self, seat: Collector) -> None:
        """The values are the draws of the source."""
        c = Case(Generating(Source(3)))
        twin = Source(3)
        got = [c.choose(digit()) for _ in range(20)]
        check.equal(
            seat,
            got,
            [draw.integer(twin, DIGIT) for _ in got],
            "the values are the draws",
        )

    def test_draws_a_coin_before_it_takes_an_earlier_value_of_a_reuse_request(
        self, seat: Collector
    ) -> None:
        """41 reuse requests follow the rules."""
        c = Case(Generating(Source(5)))
        twin = Source(5)
        earlier = [c.integer(WIDE, None, True)]
        want = [draw.integer(twin, WIDE)]
        for _ in range(40):
            got = c.integer(WIDE, None, True)
            if twin.coin(1, draw.REUSE_ODDS):
                want.append(earlier[twin.below(len(earlier))])
            else:
                want.append(draw.integer(twin, WIDE))
            earlier.append(got)
        check.equal(seat, earlier, want, "41 reuse requests follow the rules")

    def test_returns_the_pinned_reuse_requests_of_seed_42(
        self, seat: Collector
    ) -> None:
        """Seed 42 gives twelve pinned values over the signed range."""
        c = Case(Generating(Source(42)))
        wide = IntegerBounds(INT64_MIN, INT64_MAX)
        check.equal(
            seat,
            [c.integer(wide, None, True) for _ in range(12)],
            [
                11,
                13,
                INT64_MAX,
                INT64_MAX,
                -207,
                -781_715_023_583_996_500,
                INT64_MIN,
                -43,
                -12,
                -2_609_675_888_663_766_267,
                -2_609_675_888_663_766_267,
                229,
            ],
            "the twelve values are the pinned values",
        )

    def test_does_not_toss_a_coin_for_a_reuse_request_with_equal_bounds(
        self, seat: Collector
    ) -> None:
        """The requests do not consume the stream."""
        c = Case(Generating(Source(7)))
        twin = Source(7)
        seven = IntegerBounds(7, 7)
        sevens = [c.integer(seven, None, True) for _ in range(3)]
        after = [c.integer(WIDE) for _ in range(5)]
        check.equal(
            seat,
            [sevens, after],
            [[7, 7, 7], [draw.integer(twin, WIDE) for _ in after]],
            "the stream continues where it was",
        )

    def test_reuses_only_values_of_the_bounds_of_the_request(
        self, seat: Collector
    ) -> None:
        """Every value is a digit."""
        c = Case(Generating(Source(5)))
        for _ in range(30):
            c.integer(IntegerBounds(500, 600), None, True)
        values = [c.integer(DIGIT, None, True) for _ in range(30)]
        check.is_true(
            seat, all(DIGIT.admits(v) for v in values), "every value is a digit"
        )

    def test_does_not_toss_a_coin_for_a_request_without_reuse(
        self, seat: Collector
    ) -> None:
        """The request draws as usual."""
        c = Case(Generating(Source(9)))
        twin = Source(9)
        c.integer(DIGIT, None, True)
        draw.integer(twin, DIGIT)
        check.equal(
            seat,
            c.integer(DIGIT, 0),
            draw.integer(twin, DIGIT),
            "the value is the draw",
        )

    def test_does_not_reuse_the_value_of_a_removed_choice(
        self, seat: Collector
    ) -> None:
        """No coin follows the rewind for 50 seeds."""
        got: list[int] = []
        want: list[int] = []
        for seed in range(50):
            c = Case(Generating(Source(seed)))
            start = c.mark()
            c.integer(WIDE, None, True)
            c.rewind(start)
            got.append(c.integer(WIDE, None, True))
            twin = Source(seed)
            draw.integer(twin, WIDE)
            want.append(draw.integer(twin, WIDE))
        check.equal(seat, got, want, "the draws follow the rules for 50 seeds")

    def test_does_not_reuse_a_removed_value_of_other_bounds(
        self, seat: Collector
    ) -> None:
        """No coin follows the rewind for 50 seeds."""
        narrow = IntegerBounds(0, 999_999_999)
        got: list[int] = []
        want: list[int] = []
        for seed in range(50):
            c = Case(Generating(Source(seed)))
            start = c.mark()
            c.integer(WIDE, None, True)
            c.rewind(start)
            c.integer(narrow, None, True)
            got.append(c.integer(WIDE, None, True))
            twin = Source(seed)
            draw.integer(twin, WIDE)
            draw.integer(twin, narrow)
            want.append(draw.integer(twin, WIDE))
        check.equal(seat, got, want, "the draws follow the rules for 50 seeds")


class TestTrailingValue:
    """Trailing.value returns the value of Generating and keeps the state."""

    def test_returns_the_values_that_generating_returns(self, seat: Collector) -> None:
        """Ten reuse requests give the same values."""
        c = Case(Trailing(Source(5)))
        twin = Case(Generating(Source(5)))
        check.equal(
            seat,
            [c.integer(WIDE, None, True) for _ in range(10)],
            [twin.integer(WIDE, None, True) for _ in range(10)],
            "the values are those of Generating",
        )

    def test_keeps_the_state_of_the_source_before_and_after_each_value(
        self, seat: Collector
    ) -> None:
        """Three values leave four states."""
        trail = Trailing(Source(5))
        c = Case(trail)
        for _ in range(3):
            c.choose(digit())
        check.length(
            seat,
            trail.states,
            4,
            "the provider keeps the state before and three after",
        )


class TestTrailingAfter:
    """Trailing.after returns the source after a number of values."""

    def test_returns_the_source_after_its_first_values(self, seat: Collector) -> None:
        """The stream resumes after the value."""
        trail = Trailing(Source(5))
        Case(trail).choose(digit())
        twin = Source(5)
        draw.integer(twin, DIGIT)
        check.equal(
            seat,
            [trail.after(0).next(), trail.after(1).next()],
            [Source(5).next(), twin.next()],
            "the stream before and after the value",
        )

    def test_returns_a_copy_that_leaves_the_kept_state_unchanged(
        self, seat: Collector
    ) -> None:
        """Two copies give the same value."""
        trail = Trailing(Source(5))
        check.equal(
            seat,
            trail.after(0).next(),
            trail.after(0).next(),
            "both copies give the same value",
        )


class TestReplayingValue:
    """Replaying.value reads a recorded value back."""

    def test_returns_the_recorded_values_that_fit(self, seat: Collector) -> None:
        """Two recorded digits come back."""
        c = Case(Replaying(integers(7, 3)))
        check.equal(
            seat,
            [c.choose(digit()), c.choose(digit())],
            [7, 3],
            "the values are the recorded digits",
        )

    def test_returns_the_target_for_a_recorded_value_outside_the_bounds(
        self, seat: Collector
    ) -> None:
        """12 is not a digit."""
        check.equal(
            seat,
            Case(Replaying(integers(12))).choose(digit()),
            0,
            "the value is the target",
        )

    def test_returns_the_target_for_a_recorded_value_of_another_kind(
        self, seat: Collector
    ) -> None:
        """A sequence is not a digit."""
        c = Case(Replaying([Choice("sequence", (5,))]))
        check.equal(seat, c.choose(digit()), 0, "the value is the target")

    def test_returns_the_target_past_the_recorded_choices(
        self, seat: Collector
    ) -> None:
        """The target follows the last choice."""
        bounds = IntegerBounds(3, 9)
        c = Case(Replaying(integers(5)))
        request = Request(bounds, lambda source: draw.integer(source, bounds))
        got = [c.choose(request), c.choose(request), c.choose(request)]
        check.equal(seat, got, [5, 3, 3], "the target follows the last choice")


class TestValuingValued:
    """Valuing.valued returns the next given value of a draw."""

    def test_gives_each_draw_the_next_given_value_without_a_choice(
        self, seat: Collector
    ) -> None:
        """The draws take the values without a choice or a span."""
        c = Case(Valuing([5, "x"]))
        drawn = [c.draw(DIGITS, "a"), c.draw(DIGITS, "b")]
        check.equal(
            seat,
            [drawn, c.choices, c.spans, [(d.label, d.value) for d in c.draws]],
            [[5, "x"], [], [], [("a", 5), ("b", "x")]],
            "the draws take the given values",
        )


class TestValuingValue:
    """Valuing.value returns the value of a request of a draw past the given values."""

    def test_gives_a_request_of_a_draw_past_the_last_value_its_target(
        self, seat: Collector
    ) -> None:
        """The draw decodes the target."""
        c = Case(Valuing([5]))
        c.draw(DIGITS, "a")
        check.equal(
            seat,
            [c.draw(DIGITS, "b"), values_of(c.choices)],
            [0, [("integer", 0)]],
            "the draw decodes the target",
        )


class TestCase:
    """Case is the record of one call of a body."""

    def test_starts_without_an_owner(self, seat: Collector) -> None:
        """No layer above the engine runs a body on it yet."""
        check.is_none(seat, Case(Replaying([])).owner, "the owner is None")


class TestCaseChoose:
    """Case.choose returns the value of a request and records it."""

    def test_records_each_choice_with_its_request(self, seat: Collector) -> None:
        """The case records the choice and the request."""
        c = Case(Generating(Source(3)))
        request = digit()
        value = c.choose(request)
        check.equal(
            seat,
            values_of(c.choices),
            [("integer", value)],
            "the case records the choice",
        )
        check.is_true(seat, c.requests[0] is request, "the case records the request")

    def test_records_the_fitted_value_of_a_replay(self, seat: Collector) -> None:
        """The record has the value that the body received."""
        c = Case(Replaying(integers(12)))
        c.choose(digit())
        check.equal(
            seat,
            values_of(c.choices),
            [("integer", 0)],
            "the case records the fitted value",
        )

    def test_allows_exactly_max_choices_choices(self, seat: Collector) -> None:
        """A cap of 3 allows three choices."""
        c = Case(Replaying([]), 3)
        for _ in range(3):
            c.choose(digit())
        check.length(seat, c.choices, 3, "the case has three choices")

    def test_raises_overrun_for_a_choice_past_the_cap(self, seat: Collector) -> None:
        """The fourth choice raises."""
        c = Case(Replaying([]), 3)
        for _ in range(3):
            c.choose(digit())
        with pytest.raises(Overrun):
            c.choose(digit())
        check.length(seat, c.choices, 3, "the case does not record a fourth choice")

    def test_counts_a_sequence_as_one_choice_plus_one_for_each_element(
        self, seat: Collector
    ) -> None:
        """A cap of 4 takes a sequence of three, and a cap of 3 refuses it."""
        bounds = SequenceBounds(10, 3, 3)
        recorded = [Choice("sequence", (1, 2, 3))]
        got = Case(Replaying(recorded), 4).choose(sequence_of(bounds))
        check.equal(seat, got, (1, 2, 3), "a cap of 4 takes the sequence")
        with pytest.raises(Overrun):
            Case(Replaying(recorded), 3).choose(sequence_of(bounds))

    def test_raises_overrun_before_the_draw_of_a_sequence_whose_minimum_passes_the_cap(
        self, seat: Collector
    ) -> None:
        """The choice does not consume the stream."""
        source, twin = Source(7), Source(7)
        with pytest.raises(Overrun):
            Case(Generating(source), 3).choose(sequence_of(SequenceBounds(10, 3)))
        check.equal(
            seat, source.next(), twin.next(), "the stream continues where it was"
        )

    def test_does_not_keep_a_walk_by_default(self, seat: Collector) -> None:
        """A case does not keep its walk by default."""
        c = Case(Replaying(integers(4)))
        c.choose(digit())
        check.is_none(seat, c.walk, "the walk is None")

    def test_keeps_each_choice_of_its_walk_with_its_where_after_a_rewind(
        self, seat: Collector
    ) -> None:
        """The walk has two steps at index 0."""
        c = Case(Replaying(integers(4)), walk=True)
        start = c.mark()
        c.draw(DIGITS, "a")
        c.rewind(start)
        c.draw(DIGITS, "b")
        walk = c.walk or []
        check.equal(
            seat,
            [(step.index, step.value, step.where) for step in walk],
            [(0, 4, Where("a")), (0, 4, Where("b"))],
            "the walk has two steps at index 0",
        )

    def test_passes_each_choice_to_the_observer(self, seat: Collector) -> None:
        """The observer receives two steps."""
        seen: list[tuple[int, Value]] = []

        class Watching:
            def step(self, index: int, request: Request, value: Value) -> None:
                del request
                seen.append((index, value))

        c = Case(Replaying(integers(1, 2)), MAX_CHOICES, Watching())
        c.choose(digit())
        c.choose(digit())
        check.equal(seat, seen, [(0, 1), (1, 2)], "the observer receives two steps")


class TestCaseInteger:
    """Case.integer makes an integer choice."""

    def test_gives_its_request_the_edge(self, seat: Collector) -> None:
        """The request has the edge, and reuse is False."""
        c = Case(Replaying([]))
        c.integer(DIGIT, 1)
        check.equal(
            seat,
            (c.requests[0].edge, c.requests[0].reuse),
            (1, False),
            "the request has the edge without reuse",
        )


class TestCaseSequence:
    """Case.sequence makes a sequence choice."""

    def test_returns_a_sequence_choice_that_draw_sequence_draws(
        self, seat: Collector
    ) -> None:
        """The value is the draw of the source."""
        bounds = SequenceBounds(256, 0, 8)
        c = Case(Generating(Source(4)))
        check.equal(
            seat,
            c.sequence(bounds),
            draw.sequence(Source(4), bounds),
            "the value is the draw of draw.sequence",
        )


class TestCaseRandom:
    """Case.random returns an integer over the unsigned 64-bit range."""

    def test_returns_an_integer_over_the_whole_unsigned_64_bit_range(
        self, seat: Collector
    ) -> None:
        """The largest value comes back."""
        c = Case(Replaying(integers(UINT64_MAX)))
        check.equal(
            seat,
            [c.random(), c.requests[0].bounds],
            [UINT64_MAX, IntegerBounds(0, UINT64_MAX)],
            "the value and its bounds cover the range",
        )


class TestCaseSpan:
    """Case.span records the choices of a block as one span."""

    def test_covers_the_choices_made_inside_it(self, seat: Collector) -> None:
        """The span covers two choices."""
        c = Case(Replaying([]))
        c.choose(digit())
        with c.span("pair"):
            c.choose(digit())
            c.choose(digit())
        check.equal(
            seat,
            c.spans,
            [Span("pair", 1, 3, 0, None)],
            "the span covers the choices of the block",
        )

    def test_records_the_depth_and_the_parent_of_nested_spans(
        self, seat: Collector
    ) -> None:
        """The case has three spans."""
        c = Case(Replaying([]))
        with c.span("outer"):
            with c.span("first"):
                c.choose(digit())
            with c.span("second"):
                c.choose(digit())
        check.equal(
            seat,
            c.spans,
            [
                Span("outer", 0, 2, 0, None),
                Span("first", 0, 1, 1, 0),
                Span("second", 1, 2, 1, 0),
            ],
            "the spans have their depths and parents",
        )

    def test_starts_at_an_earlier_choice(self, seat: Collector) -> None:
        """The span covers the flag and the element."""
        c = Case(Replaying([]))
        c.choose(digit())
        with c.span("element", 0):
            c.choose(digit())
        check.equal(
            seat,
            c.spans,
            [Span("element", 0, 2, 0, None)],
            "the span starts at the flag",
        )

    def test_closes_where_its_block_raises(self, seat: Collector) -> None:
        """The span closes at the error."""
        c = Case(Replaying([]))
        with pytest.raises(Rejected), c.span("list"):
            refuse(c)
        check.equal(
            seat,
            c.spans,
            [Span("list", 0, 1, 0, None)],
            "the span closes where the block raises",
        )


class TestCaseOpen:
    """Case.open opens a span that a function closes."""

    def test_returns_the_function_that_closes_the_span_at_the_current_choice(
        self, seat: Collector
    ) -> None:
        """The span covers the first two choices."""
        c = Case(Replaying([]))
        c.choose(digit())
        close = c.open("step", 0)
        c.choose(digit())
        close()
        c.choose(digit())
        check.equal(
            seat,
            c.spans,
            [Span("step", 0, 2, 0, None)],
            "the span covers the first two choices",
        )

    def test_nests_a_span_that_opens_before_it_closes(self, seat: Collector) -> None:
        """The parent of the inner span is the step."""
        c = Case(Replaying([]))
        close = c.open("step")
        with c.span("inner"):
            c.choose(digit())
        close()
        check.equal(
            seat,
            c.spans,
            [Span("step", 0, 1, 0, None), Span("inner", 0, 1, 1, 0)],
            "the inner span is a child of the step",
        )


class TestCaseProvider:
    """Case.provider returns the provider of the values of the case."""

    def test_returns_the_provider_of_the_case(self, seat: Collector) -> None:
        """The provider is the one that the case received."""
        provider = Replaying([])
        check.is_true(
            seat, Case(provider).provider is provider, "the case returns its provider"
        )


class TestCaseMaxChoices:
    """Case.max_choices returns the largest number of choices that the case can make."""

    def test_returns_the_cap_of_the_case(self, seat: Collector) -> None:
        """A case with a cap of 3 returns 3."""
        check.equal(
            seat, Case(Replaying([]), 3).max_choices, 3, "the cap of the case is 3"
        )


class TestCaseRepeats:
    """Case.repeats returns the number of runs of the body on the case."""

    def test_returns_1_for_a_case_without_a_call_of_repeat(
        self, seat: Collector
    ) -> None:
        """A new case has one run."""
        check.equal(seat, Case(Replaying([])).repeats, 1, "the case has one run")


class TestCaseRepeat:
    """Case.repeat makes the execution run the body again on the choices of the case."""

    def test_keeps_the_larger_of_two_numbers_of_runs(self, seat: Collector) -> None:
        """The body calls repeat with 4, and then with 2."""
        c = Case(Replaying([]))
        c.repeat(4)
        c.repeat(2)
        check.equal(seat, c.repeats, 4, "the case keeps the 4 runs")


class TestCaseRewind:
    """Case.rewind cuts the record back to a mark."""

    def test_removes_everything_that_the_case_recorded_after_the_mark(
        self, seat: Collector
    ) -> None:
        """The record returns to the mark."""
        c = Case(Replaying(integers(1, 2)))
        c.draw(DIGITS, "kept")
        mark = c.mark()
        with c.span("attempt"):
            c.draw(DIGITS, "removed")
        c.rewind(mark)
        check.equal(
            seat,
            [
                values_of(c.choices),
                len(c.requests),
                c.spans,
                [d.label for d in c.draws],
            ],
            [[("integer", 1)], 1, [], ["kept"]],
            "the record is the record at the mark",
        )

    def test_gives_the_next_choice_the_index_of_the_first_removed_choice(
        self, seat: Collector
    ) -> None:
        """The replay reads the choice at the mark again."""
        c = Case(Replaying(integers(1, 2, 3)))
        c.choose(digit())
        mark = c.mark()
        c.choose(digit())
        c.rewind(mark)
        check.equal(
            seat, c.choose(digit()), 2, "the next choice is the choice at the mark"
        )

    def test_counts_the_removed_choices_towards_the_cap(self, seat: Collector) -> None:
        """A third choice passes the cap."""
        c = Case(Replaying([]), 2)
        start = c.mark()
        c.choose(digit())
        c.rewind(start)
        c.choose(digit())
        with pytest.raises(Overrun):
            c.choose(digit())
        check.length(seat, c.choices, 1, "the record has one choice")

    def test_leaves_the_steps_of_the_removed_choices_with_the_observer(
        self, seat: Collector
    ) -> None:
        """The observer has three steps, and the record has two choices."""
        values: list[Value] = []

        class Watching:
            def step(self, index: int, request: Request, value: Value) -> None:
                del index, request
                values.append(value)

        c = Case(Replaying(integers(1, 2, 3)), MAX_CHOICES, Watching())
        c.choose(digit())
        mark = c.mark()
        c.choose(digit())
        c.rewind(mark)
        c.choose(digit())
        check.equal(
            seat,
            [values, len(c.choices)],
            [[1, 2, 2], 2],
            "the observer keeps the removed step",
        )

    def test_removes_the_wheres_of_the_removed_choices(self, seat: Collector) -> None:
        """One where is left."""
        c = Case(Replaying([]))
        c.choose(digit())
        mark = c.mark()
        c.draw(DIGITS, "v")
        c.rewind(mark)
        check.equal(seat, c.wheres, [Where()], "the record has one where")


class TestCaseCancel:
    """Case.cancel ends a case at its next choice."""

    def test_raises_overrun_at_the_next_choice_of_a_cancelled_case(
        self, seat: Collector
    ) -> None:
        """The case does not record a choice."""
        c = Case(Replaying(integers(4)))
        c.cancel()
        with pytest.raises(Overrun):
            c.choose(digit())
        check.is_empty(seat, c.choices, "the record is empty")


class TestCaseRecordAt:
    """Case.record_at returns the record after the first steps of the walk."""

    def test_returns_the_record_before_the_rewinds_of_the_later_steps(
        self, seat: Collector
    ) -> None:
        """The second value before the rewind, and the third after it."""
        c = Case(Generating(Source(3)), walk=True)
        twin = Source(3)
        values = [draw.integer(twin, DIGIT) for _ in range(3)]
        c.choose(digit())
        mark = c.mark()
        c.choose(digit())
        c.rewind(mark)
        c.choose(digit())
        check.equal(
            seat,
            [c.record_at(1), c.record_at(2), c.record_at(3)],
            [
                integers(values[0]),
                integers(values[0], values[1]),
                integers(values[0], values[2]),
            ],
            "the record after one, two and three steps",
        )


class TestCaseDraw:
    """Case.draw records a value of a generator under a label."""

    def test_tells_a_provider_that_serves_a_trace_the_label_of_each_draw(
        self, seat: Collector
    ) -> None:
        """The provider hears each label before the values."""
        heard: list[tuple[str, int]] = []
        replay = Replaying(integers(4, 5, 6))

        class Serving(Provider):
            served: int = 0

            @override
            def value(self, request: Request, index: int) -> Value:
                self.served += 1
                return replay.value(request, index)

            @override
            def drawing(self, generator: Decoder[Any], label: str) -> None:
                del generator
                heard.append((label, self.served))

        c = Case(Serving())
        check.equal(
            seat,
            [[c.draw(DIGITS, "a"), c.draw(DIGITS, "b")], heard],
            [[4, 5], [("a", 0), ("b", 1)]],
            "the provider hears each label before the values",
        )

    def test_records_the_label_of_the_draw_with_each_of_its_requests(
        self, seat: Collector
    ) -> None:
        """Only the request inside the draw has the label."""
        c = Case(Replaying([]))
        c.draw(DIGITS, "v")
        c.choose(digit())
        check.equal(
            seat,
            c.wheres,
            [Where("v"), Where()],
            "only the request of the draw has the label",
        )

    def test_records_the_innermost_label_for_the_requests_of_a_nested_draw(
        self, seat: Collector
    ) -> None:
        """Each request has its innermost label."""
        c = Case(Replaying([]))
        c.draw(OUTER, "outer")
        check.equal(
            seat,
            [w.label for w in c.wheres],
            ["outer", "inner"],
            "each request has its innermost label",
        )

    def test_closes_its_label_when_the_generator_raises(self, seat: Collector) -> None:
        """The case is outside every draw after the error."""
        c = Case(Replaying([]))
        with pytest.raises(Rejected):
            c.draw(REFUSING, "v")
        check.equal(
            seat,
            [c.wheres, c.where()],
            [[Where("v")], Where()],
            "the label closes at the error",
        )

    def test_records_the_place_of_the_case_with_each_request(
        self, seat: Collector
    ) -> None:
        """The request has the label and the place."""
        c = Case(Replaying([]))
        c.place = Place("sequential", 2, "put")
        c.draw(DIGITS, "v")
        check.equal(
            seat,
            c.wheres,
            [Where("v", Place("sequential", 2, "put"))],
            "the request has the label and the place",
        )

    def test_records_the_draw_with_the_first_span_of_its_generator(
        self, seat: Collector
    ) -> None:
        """The draw has the span after the earlier span."""
        c = Case(Replaying(integers(3)))

        def spanned(inner: Case) -> Value:
            with inner.span("digit"):
                return inner.choose(digit())

        spanning = Decoding(spanned)
        c.choose(digit())
        with c.span("before"):
            pass
        c.draw(spanning, "v")
        check.equal(
            seat,
            [(d.label, d.value, d.span, d.generator is spanning) for d in c.draws],
            [("v", 0, 1, True)],
            "the draw has the first span of its generator",
        )


class TestCaseStep:
    """Case.step records a step that a machine took."""

    def test_records_a_step_after_the_draws_before_it(self, seat: Collector) -> None:
        """Each step follows its draws."""
        c = Case(Replaying([]))
        c.step(Step("put"))
        c.draw(DIGITS, "v")
        c.step(Step("get", 1))
        check.equal(
            seat,
            c.steps,
            [(0, Step("put")), (1, Step("get", 1))],
            "each step follows the draws before it",
        )


class TestCaseAssume:
    """Case.assume rejects a case whose condition is false."""

    def test_raises_rejected_for_a_false_condition(self, seat: Collector) -> None:
        """The case is rejected."""
        with pytest.raises(Rejected) as caught:
            Case(Replaying([])).assume(False)
        check.error_as(seat, caught.value, Rejected, "the signal is a Rejected")

    def test_returns_for_a_true_condition(self, seat: Collector) -> None:
        """The case continues."""
        check.does_not_raise(
            seat, lambda: Case(Replaying([])).assume(True), "the case continues"
        )


class TestCaseClassify:
    """Case.classify adds a label to the case."""

    def test_counts_a_label_once(self, seat: Collector) -> None:
        """The case has two labels."""
        c = Case(Replaying([]))
        c.classify("even")
        c.classify("even")
        c.classify("small")
        check.equal(seat, c.labels, {"even", "small"}, "the case has two labels")


class TestCaseNote:
    """Case.note adds a message to the case."""

    def test_keeps_the_notes_in_order(self, seat: Collector) -> None:
        """The case keeps two notes in order."""
        c = Case(Replaying([]))
        c.note("first")
        c.note("second")
        check.equal(
            seat, c.notes, ["first", "second"], "the case keeps the notes in order"
        )


class TestCaseObserve:
    """Case.observe records a fingerprint of the subject."""

    def test_records_each_fingerprint_with_where_the_case_observed_it(
        self, seat: Collector
    ) -> None:
        """The case records two fingerprints and their places."""
        c = Case(Replaying([]))
        c.observe(1)
        c.place = Place("drain", 0, "flush")
        c.observe(2)
        check.equal(
            seat,
            [c.fingerprints, c.observed],
            [[1, 2], [Where(), Where(None, Place("drain", 0, "flush"))]],
            "the case records the fingerprints and their places",
        )


class TestCaseTarget:
    """Case.target records a score of the case."""

    def test_keeps_the_higher_of_two_scores_under_one_label(
        self, seat: Collector
    ) -> None:
        """The highest score of each label."""
        c = Case(Replaying([]))
        c.target("depth", 3)
        c.target("depth", 1)
        c.target("depth", 5)
        c.target("width", -2)
        check.equal(
            seat,
            c.targets,
            {"depth": 5, "width": -2},
            "the case keeps the highest scores",
        )


class TestCaseFail:
    """Case.fail fails the case."""

    def test_raises_the_failure_of_an_identity(self, seat: Collector) -> None:
        """The failure keeps its identity and its record."""
        with pytest.raises(Failed) as caught:
            Case(Replaying([])).fail("raises@a.py:3", "the record")
        check.equal(
            seat,
            [caught.value.identity, caught.value.record],
            ["raises@a.py:3", "the record"],
            "the failure keeps its identity and its record",
        )
