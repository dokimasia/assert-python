# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/generator.py tests what each generator decodes and draws.

Rejected derives from BaseException. The raises assertion does not catch it,
so the spec catches it with pytest.raises.
"""

from __future__ import annotations

import math
import threading
from fractions import Fraction
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

import pytest

from dokimi_assert import check
from dokimi_assert._override import override
from dokimi_assert._prop.engine import draw
from dokimi_assert._prop.engine.case import (
    Case,
    Generating,
    Provider,
    Rejected,
    Replaying,
    Request,
    Span,
)
from dokimi_assert._prop.engine.choice import (
    Choice,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    Value,
)
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.generator import (
    Bool,
    Bound,
    Bytes,
    Composite,
    Dict,
    Filter,
    Float,
    Generator,
    Integer,
    Just,
    List,
    Mapped,
    Matching,
    OneOf,
    Optional,
    Permutation,
    Position,
    Recursive,
    SampledFrom,
    Text,
)
from dokimi_assert._prop.engine.source import Source
from dokimi_assert._prop.engine.value import Pairs, canonical
from helpers import Picked, values_of

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

T = TypeVar("T")

#: The number of seeds of each check of generation.
SEEDS = 200

#: The seconds that a thread of a case waits on a signal of the other.
WAIT = 10.0

INF = math.inf

DIGIT = Integer(IntegerBounds(0, 9))
TEEN = Integer(IntegerBounds(10, 20))
COIN = Bool(Fraction(1, 2))
LETTERS = SampledFrom(["a", "b", "c"])
DIGITS = List(DIGIT, Sizes(0, 3))
UNIQUE = List(DIGIT, Sizes(), True)
TABLE = Dict(DIGIT, COIN, Sizes(0, 3))
KEEP_EVEN = Filter(DIGIT, lambda value: value % 2 == 0)


def tree(max_leaves: int = 100) -> Recursive[Any]:
    """Return a tree of digits. A tree is a digit or a list of at most three trees."""
    return Recursive(DIGIT, max_leaves, lambda own: List(own, Sizes(0, 3)))


def choice_of(value: Value) -> Choice:
    """Return a recorded choice of the kind of a value."""
    if isinstance(value, tuple):
        return Choice("sequence", value)
    if isinstance(value, float):
        return Choice("float", value)
    return Choice("integer", value)


def replay(*values: Value) -> Case:
    """Return a case that replays values."""
    return Case(Replaying([choice_of(value) for value in values]))


def decoded_from(generator: Generator[T], *values: Value) -> tuple[T, Case]:
    """Return the value that a generator decodes from recorded values, and the case."""
    c = replay(*values)
    return generator.decode(c), c


class Feed(Provider):
    """A provider that returns the given values in order and ignores the index."""

    def __init__(self, *values: Value) -> None:
        """Return the provider of the values."""
        self._values: list[Value] = list(values)

    @override
    def value(self, request: Request, index: int) -> Value:
        """Return the next given value."""
        del request, index
        return self._values.pop(0)


def labels(c: Case) -> list[str]:
    """Return the span labels of a case."""
    return [span.label for span in c.spans]


def outcome(generator: Generator[Any], c: Case) -> str:
    """Return the canonical value that a generator decodes from a case, or rejected."""
    try:
        return canonical(generator.decode(c))
    except Rejected:
        return "rejected"


class TestGeneratorMap:
    """Generator.map returns the generator of a function of each value."""

    def test_returns_a_generator_of_the_function_of_each_value(
        self, seat: Collector
    ) -> None:
        """The map of 4 is 8."""
        doubled = DIGIT.map(lambda value: value * 2)
        check.equal(
            seat,
            [isinstance(doubled, Mapped), decoded_from(doubled, 4)[0]],
            [True, 8],
            "the generator maps 4 to 8",
        )


class TestGeneratorFilter:
    """Generator.filter returns the generator of the values that a predicate keeps."""

    def test_returns_a_generator_of_the_values_that_the_predicate_keeps(
        self, seat: Collector
    ) -> None:
        """The filter keeps 4."""
        even = DIGIT.filter(lambda value: value % 2 == 0)
        check.equal(
            seat,
            [isinstance(even, Filter), decoded_from(even, 4)[0]],
            [True, 4],
            "the filter keeps 4",
        )


class TestGeneratorBind:
    """Generator.bind returns a generator that decodes two values in one span."""

    def test_returns_a_generator_of_the_value_of_the_generator_of_the_function(
        self, seat: Collector
    ) -> None:
        """The bind decodes 5 and then 3."""
        bound = DIGIT.bind(lambda n: Integer(IntegerBounds(0, n)))
        value, c = decoded_from(bound, 5, 3)
        check.equal(
            seat,
            [isinstance(bound, Bound), value, labels(c)],
            [True, 3, ["bind", "integer", "integer"]],
            "the bound generator decodes 3 in one span",
        )


class TestDeferred:
    """Deferred decodes with the generator that it picks."""

    def test_decodes_with_the_picked_generator_without_a_span_of_its_own(
        self, seat: Collector
    ) -> None:
        """The recorded 4 decodes in the span of the integer alone."""
        deferred = Picked(DIGIT)
        value, c = decoded_from(deferred, 4)
        check.equal(
            seat,
            [value, labels(c), deferred.picks],
            [4, ["integer"], 1],
            "the pick decodes 4",
        )


class TestInteger:
    """Integer decodes one integer choice in its bounds."""

    def test_decodes_a_recorded_value_to_itself(self, seat: Collector) -> None:
        """The recorded 7 decodes to 7."""
        check.equal(seat, decoded_from(DIGIT, 7)[0], 7, "the value is 7")

    def test_decodes_the_value_closest_to_zero_without_a_choice(
        self, seat: Collector
    ) -> None:
        """The targets of two ranges without 0."""
        above = Integer(IntegerBounds(3, 9))
        below = Integer(IntegerBounds(-9, -3))
        check.equal(
            seat,
            [decoded_from(above)[0], decoded_from(below)[0]],
            [3, -3],
            "the values are the targets",
        )

    def test_makes_one_reusable_value_choice_in_a_span_of_its_id(
        self, seat: Collector
    ) -> None:
        """The case has one span and one request."""
        c = decoded_from(DIGIT, 7)[1]
        check.equal(
            seat,
            [c.spans, c.requests[0].edge, c.requests[0].reuse],
            [[Span("integer", 0, 1, 0, None)], None, True],
            "the case has the span and the request",
        )

    def test_decodes_a_duration_in_nanoseconds_under_its_own_id(
        self, seat: Collector
    ) -> None:
        """The span has the label duration."""
        duration = Integer(IntegerBounds(0, 1_000_000_000), "duration")
        value, c = decoded_from(duration, 5)
        check.equal(
            seat,
            [value, labels(c)],
            [5, ["duration"]],
            "the duration decodes in its own span",
        )


class TestFloat:
    """Float decodes one float choice in its bounds."""

    def test_decodes_a_recorded_value_to_itself(self, seat: Collector) -> None:
        """The recorded 0.5 decodes to 0.5."""
        got = decoded_from(Float(FloatBounds(-1.0, 1.0)), 0.5)[0]
        check.equal(seat, got, 0.5, "the value is 0.5")

    def test_decodes_the_simplest_float_in_range_without_a_choice(
        self, seat: Collector
    ) -> None:
        """The value has the fewest fractional bits."""
        got = decoded_from(Float(FloatBounds(0.6, 0.7)))[0]
        check.equal(seat, got, 0.625, "the value is 0.625")

    def test_decodes_nan_and_the_infinities_where_the_bounds_allow_them(
        self, seat: Collector
    ) -> None:
        """NaN and negative infinity decode."""
        every = Float(FloatBounds(-INF, INF, True))
        check.is_true(seat, math.isnan(decoded_from(every, math.nan)[0]), "NaN decodes")
        check.equal(seat, decoded_from(every, -INF)[0], -INF, "-inf decodes")

    def test_decodes_the_target_for_nan_where_the_bounds_refuse_it(
        self, seat: Collector
    ) -> None:
        """NaN decodes to the target 1."""
        got = decoded_from(Float(FloatBounds(1.0, 2.0)), math.nan)[0]
        check.equal(seat, got, 1.0, "the value is the target")

    def test_decodes_the_target_for_a_value_of_another_width(
        self, seat: Collector
    ) -> None:
        """0.1 is not a value of width 32."""
        narrow = Float(FloatBounds(0.0, 1.0, False, 32))
        check.equal(
            seat,
            [decoded_from(narrow, 0.1)[0], decoded_from(narrow, 0.5)[0]],
            [0.0, 0.5],
            "0.1 decodes to the target and 0.5 to itself",
        )

    def test_decodes_in_a_span_labelled_float(self, seat: Collector) -> None:
        """The case has one span."""
        c = decoded_from(Float(FloatBounds(0.0, 1.0)), 0.5)[1]
        check.equal(seat, labels(c), ["float"], "the span has the label float")


class TestBool:
    """Bool decodes True with a probability from one integer choice."""

    def test_decodes_true_from_the_choice_1_alone(self, seat: Collector) -> None:
        """The choice 1 decodes to True, and the target to False."""
        check.equal(
            seat,
            [decoded_from(COIN, 1)[0], decoded_from(COIN)[0]],
            [True, False],
            "1 decodes to True and the target to False",
        )

    def test_draws_one_coin_of_its_probability(self, seat: Collector) -> None:
        """Each decode tosses a coin of 1 in 3."""
        third = Bool(Fraction(1, 3))
        got = [third.decode(Case(Generating(Source(seed)))) for seed in range(50)]
        want = [Source(seed).coin(1, 3) for seed in range(50)]
        check.equal(seat, got, want, "each value is the coin")


class TestJust:
    """Just decodes one given value."""

    def test_decodes_its_value_without_a_choice(self, seat: Collector) -> None:
        """The span is empty."""
        value, c = decoded_from(Just("x"))
        check.equal(
            seat,
            [value, c.choices, c.spans],
            ["x", [], [Span("just", 0, 0, 0, None)]],
            "the value has an empty span",
        )


class TestSampledFrom:
    """SampledFrom decodes one of the given values."""

    def test_decodes_the_value_at_the_recorded_index(self, seat: Collector) -> None:
        """Index 2 decodes to the third value."""
        check.equal(seat, decoded_from(LETTERS, 2)[0], "c", "index 2 decodes to c")

    def test_decodes_the_first_value_without_a_choice_or_from_an_index_past_the_end(
        self, seat: Collector
    ) -> None:
        """The target is the first value."""
        check.equal(
            seat,
            [decoded_from(LETTERS)[0], decoded_from(LETTERS, 3)[0]],
            ["a", "a"],
            "both decode to the first value",
        )

    def test_chooses_its_index_as_a_structure_choice_with_the_edge_0(
        self, seat: Collector
    ) -> None:
        """The request of the index has the edge 0."""
        c = decoded_from(LETTERS, 1)[1]
        check.equal(
            seat,
            [c.requests[0].edge, c.requests[0].bounds],
            [0, IntegerBounds(0, 2)],
            "the index has the edge 0 and its bounds",
        )


class TestOneOf:
    """OneOf decodes a value of one of the alternatives."""

    EITHER: ClassVar[OneOf[int]] = OneOf([DIGIT, TEEN])

    def test_decodes_the_value_of_the_alternative_at_the_recorded_index(
        self, seat: Collector
    ) -> None:
        """The second alternative decodes 15."""
        check.equal(seat, decoded_from(self.EITHER, 1, 15)[0], 15, "the value is 15")

    def test_decodes_the_simplest_value_of_the_first_alternative_without_a_choice(
        self, seat: Collector
    ) -> None:
        """The value is the target 0."""
        check.equal(seat, decoded_from(self.EITHER)[0], 0, "the value is 0")

    def test_decodes_the_target_of_the_chosen_alternative_for_a_value_outside_it(
        self, seat: Collector
    ) -> None:
        """5 is outside [10, 20]."""
        check.equal(
            seat, decoded_from(self.EITHER, 1, 5)[0], 10, "the value is the target 10"
        )

    def test_chooses_its_index_as_a_structure_choice_in_its_span(
        self, seat: Collector
    ) -> None:
        """The index has an edge, and the span covers both choices."""
        c = decoded_from(self.EITHER, 1, 15)[1]
        check.equal(
            seat,
            [[request.edge for request in c.requests], c.spans[0]],
            [[0, None], Span("one-of", 0, 2, 0, None)],
            "the index has its edge and the span covers both choices",
        )


class TestOptional:
    """Optional decodes a value or None."""

    MAYBE: ClassVar[Optional[int]] = Optional(DIGIT)

    def test_decodes_none_for_an_absent_value_with_one_choice(
        self, seat: Collector
    ) -> None:
        """The case makes the presence choice alone."""
        value, c = decoded_from(self.MAYBE, 0, 4)
        check.equal(
            seat,
            [value, len(c.choices)],
            [None, 1],
            "the value is absent after one choice",
        )

    def test_decodes_the_value_of_a_present_value(self, seat: Collector) -> None:
        """The present value is 4."""
        check.equal(seat, decoded_from(self.MAYBE, 1, 4)[0], 4, "the value is 4")

    def test_decodes_none_without_a_choice(self, seat: Collector) -> None:
        """The target is absent."""
        check.is_none(seat, decoded_from(self.MAYBE)[0], "the value is absent")

    def test_chooses_its_presence_as_a_structure_choice_with_the_edge_1(
        self, seat: Collector
    ) -> None:
        """The presence choice has the edge 1."""
        c = decoded_from(self.MAYBE, 1, 4)[1]
        edges = [request.edge for request in c.requests]
        check.equal(seat, edges, [1, None], "the presence choice has the edge 1")


class TestList:
    """List decodes the elements of a generator after their flags."""

    def test_decodes_its_flags_and_elements(self, seat: Collector) -> None:
        """The list has two digits."""
        check.equal(
            seat, decoded_from(DIGITS, 1, 7, 1, 3, 0)[0], [7, 3], "the list is [7, 3]"
        )

    def test_decodes_min_size_simplest_elements_without_a_choice(
        self, seat: Collector
    ) -> None:
        """The lists are the targets."""
        pairs = List(DIGIT, Sizes(2, 3))
        check.equal(
            seat,
            [decoded_from(DIGITS)[0], decoded_from(pairs)[0]],
            [[], [0, 0]],
            "the lists are the targets",
        )

    def test_forces_the_flag_at_its_maximum_to_stop(self, seat: Collector) -> None:
        """A recorded 1 replays as the stop."""
        value, c = decoded_from(DIGITS, 1, 1, 1, 2, 1, 3, 1)
        check.equal(
            seat,
            [value, values_of(c.choices)[-1], c.requests[-1].bounds],
            [[1, 2, 3], ("integer", 0), IntegerBounds(0, 0)],
            "the flag at the maximum stops the list",
        )

    def test_gives_an_edge_to_its_flags_alone(self, seat: Collector) -> None:
        """Only the flags have an edge."""
        c = decoded_from(DIGITS, 1, 7, 1, 3, 0)[1]
        edges = [request.edge for request in c.requests]
        check.equal(seat, edges, [1, None, 0, None, 0], "only the flags have an edge")

    def test_opens_the_span_of_each_element_at_its_flag(self, seat: Collector) -> None:
        """The case has five spans."""
        c = decoded_from(DIGITS, 1, 7, 1, 3, 0)[1]
        check.equal(
            seat,
            c.spans,
            [
                Span("list", 0, 5, 0, None),
                Span("element", 0, 2, 1, 0),
                Span("integer", 1, 2, 2, 1),
                Span("element", 2, 4, 1, 0),
                Span("integer", 3, 4, 2, 3),
            ],
            "each element span starts at its flag",
        )

    def test_keeps_duplicates_of_a_list_that_is_not_unique(
        self, seat: Collector
    ) -> None:
        """The list keeps both fours."""
        check.equal(
            seat, decoded_from(DIGITS, 1, 4, 1, 4, 0)[0], [4, 4], "the list is [4, 4]"
        )

    def test_discards_a_duplicate_element_of_a_unique_list(
        self, seat: Collector
    ) -> None:
        """The second four is discarded."""
        got = decoded_from(UNIQUE, 1, 4, 1, 4, 1, 5, 0)[0]
        check.equal(seat, got, [4, 5], "the list is [4, 5]")

    def test_raises_rejected_for_a_unique_list_that_remains_below_its_minimum(
        self, seat: Collector
    ) -> None:
        """The targets repeat."""
        c = replay()
        with pytest.raises(Rejected):
            List(DIGIT, Sizes(2), True).decode(c)
        check.length(seat, c.choices, 22, "the case has 22 choices")

    def test_draws_an_element_after_each_flag_with_the_odds_of_reusing_an_earlier_one(
        self, seat: Collector
    ) -> None:
        """The lists follow the rules for 200 seeds."""
        average = draw.average_length(0, 3)
        element = IntegerBounds(0, 9)
        got = [DIGITS.decode(Case(Generating(Source(seed)))) for seed in range(SEEDS)]
        want: list[list[int]] = []
        for seed in range(SEEDS):
            twin = Source(seed)
            values: list[int] = []
            while draw.flag(twin, len(values), 0, 3, average) == 1:
                if values and twin.coin(1, draw.REUSE_ODDS):
                    values.append(values[twin.below(len(values))])
                else:
                    values.append(draw.integer(twin, element))
            want.append(values)
        check.equal(seat, got, want, "the lists follow the rules for 200 seeds")


class TestDict:
    """Dict decodes entries of a key and a value with distinct keys."""

    def test_discards_an_entry_whose_key_repeats(self, seat: Collector) -> None:
        """The dict keeps the first entry of key 3."""
        got = decoded_from(TABLE, 1, 3, 1, 1, 3, 0, 0)[0]
        check.equal(seat, got, Pairs(((3, True),)), "the dict has one entry")

    def test_opens_the_span_of_each_entry_at_its_flag(self, seat: Collector) -> None:
        """The span of the entry starts at its flag."""
        c = decoded_from(TABLE, 1, 3, 1, 0)[1]
        check.equal(
            seat,
            c.spans[:2],
            [Span("dict", 0, 4, 0, None), Span("entry", 0, 3, 1, 0)],
            "the entry span starts at its flag",
        )

    def test_decodes_an_empty_dict_without_a_choice(self, seat: Collector) -> None:
        """The dict is empty."""
        check.equal(seat, decoded_from(TABLE)[0], Pairs(()), "the dict is empty")

    def test_raises_rejected_for_a_minimum_of_two_that_the_targets_cannot_meet(
        self, seat: Collector
    ) -> None:
        """Both target keys are 0."""
        c = replay()
        with pytest.raises(Rejected):
            Dict(DIGIT, COIN, Sizes(2, 3)).decode(c)
        check.length(seat, c.choices, 33, "the case has 33 choices")


class TestText:
    """Text decodes a string from one sequence of indices into its alphabet."""

    def test_maps_the_indices_into_the_default_alphabet(self, seat: Collector) -> None:
        """Index 10 is a."""
        text = Text(None, SequenceBounds(0x10F800))
        check.equal(seat, decoded_from(text, (10, 0))[0], "a0", "the string is a0")

    def test_maps_the_indices_into_a_given_alphabet_in_its_order(
        self, seat: Collector
    ) -> None:
        """The alphabet keeps its given order."""
        xyz = Text(["x", "y", "z"], SequenceBounds(3))
        check.equal(seat, decoded_from(xyz, (2, 0, 1))[0], "zxy", "the string is zxy")

    def test_repeats_the_first_character_min_size_times_without_a_choice(
        self, seat: Collector
    ) -> None:
        """The strings are the targets."""
        xyz = Text(["x", "y", "z"], SequenceBounds(3, 2))
        digits = Text(None, SequenceBounds(0x10F800, 2))
        check.equal(
            seat,
            [decoded_from(xyz)[0], decoded_from(digits)[0]],
            ["xx", "00"],
            "the strings are the targets",
        )

    def test_maps_an_index_past_the_alphabet_to_its_first_character(
        self, seat: Collector
    ) -> None:
        """5 is outside xyz."""
        xyz = Text(["x", "y", "z"], SequenceBounds(3))
        check.equal(seat, decoded_from(xyz, (5,))[0], "x", "the string is x")

    def test_decodes_in_a_span_labelled_string(self, seat: Collector) -> None:
        """The case has one span."""
        c = decoded_from(Text(None, SequenceBounds(10)))[1]
        check.equal(seat, labels(c), ["string"], "the span has the label string")


class TestBytes:
    """Bytes decodes a byte string from one sequence."""

    def test_decodes_a_sequence_of_256_element_values(self, seat: Collector) -> None:
        """The sequences decode to hi, a zero byte and an empty string."""
        data = Bytes(SequenceBounds(256))
        check.equal(
            seat,
            [
                decoded_from(data, (104, 105))[0],
                decoded_from(data, (256,))[0],
                decoded_from(data)[0],
            ],
            [b"hi", b"\x00", b""],
            "the sequences decode to three byte strings",
        )


class Digit:
    """A piece of a pattern that emits an a and then one digit."""

    def emit(self, c: Case, out: list[str]) -> None:
        """Append an a and a digit."""
        out.extend(["a", str(c.integer(IntegerBounds(0, 9)))])


class TestMatching:
    """Matching decodes a string that a pattern matches in full."""

    def test_joins_the_characters_of_its_piece_in_a_span(self, seat: Collector) -> None:
        """The characters of the piece."""
        value, c = decoded_from(Matching(Digit()), 7)
        check.equal(
            seat,
            [value, labels(c)],
            ["a7", ["string-matching"]],
            "the string is a7 in its span",
        )


class TestPermutation:
    """Permutation decodes an ordering of the given values."""

    ORDERING: ClassVar[Permutation[str]] = Permutation(["a", "b", "c"])

    def test_swaps_each_position_with_the_recorded_index(self, seat: Collector) -> None:
        """Index 2 at both positions."""
        got = decoded_from(self.ORDERING, 2, 2)[0]
        check.equal(seat, got, ["c", "a", "b"], "the ordering is c, a, b")

    def test_keeps_the_given_order_without_a_choice(self, seat: Collector) -> None:
        """Position i targets i."""
        value, c = decoded_from(self.ORDERING)
        check.equal(
            seat,
            [value, [request.bounds for request in c.requests]],
            [["a", "b", "c"], [IntegerBounds(0, 2), IntegerBounds(1, 2)]],
            "the values keep their order",
        )

    def test_decodes_an_empty_ordering_without_a_choice(self, seat: Collector) -> None:
        """The ordering of an empty list is empty."""
        value, c = decoded_from(Permutation[str]([]))
        check.equal(seat, [value, c.choices], [[], []], "the ordering is empty")


class TestFilter:
    """Filter decodes a value of the source that a predicate keeps."""

    def test_decodes_a_kept_first_attempt_in_one_filter_span(
        self, seat: Collector
    ) -> None:
        """4 is even."""
        value, c = decoded_from(KEEP_EVEN, 4)
        check.equal(
            seat,
            [value, c.spans],
            [4, [Span("filter", 0, 1, 0, None), Span("integer", 0, 1, 1, 0)]],
            "the value 4 has its spans",
        )

    def test_removes_a_rejected_attempt_from_the_record(self, seat: Collector) -> None:
        """The record keeps only the kept attempt."""
        c = Case(Feed(3, 4))
        check.equal(
            seat,
            [KEEP_EVEN.decode(c), values_of(c.choices), labels(c)],
            [4, [("integer", 4)], ["filter", "integer"]],
            "the record has the kept attempt alone",
        )

    def test_raises_rejected_after_three_rejected_attempts(
        self, seat: Collector
    ) -> None:
        """1, 3 and 5 are odd."""
        c = Case(Feed(1, 3, 5, 6))
        with pytest.raises(Rejected):
            KEEP_EVEN.decode(c)
        check.equal(
            seat,
            values_of(c.choices),
            [("integer", 5)],
            "the record has the last attempt",
        )

    def test_raises_rejected_for_a_replayed_value_that_the_predicate_rejects(
        self, seat: Collector
    ) -> None:
        """Each attempt replays 3."""
        c = replay(3)
        with pytest.raises(Rejected):
            KEEP_EVEN.decode(c)
        check.equal(
            seat,
            values_of(c.choices),
            [("integer", 3)],
            "the record has the last attempt",
        )


class TestMapped:
    """Mapped decodes the value of a function of the value of the source."""

    def test_decodes_the_function_of_the_value_of_the_source(
        self, seat: Collector
    ) -> None:
        """[3, 1] sorts to [1, 3]."""
        ordered = Mapped(DIGITS, sorted)
        check.equal(
            seat, decoded_from(ordered, 1, 3, 1, 1, 0)[0], [1, 3], "the value is [1, 3]"
        )

    def test_makes_the_choices_of_the_source_without_a_span_of_its_own(
        self, seat: Collector
    ) -> None:
        """The case has the span of the integer alone."""
        value, c = decoded_from(Mapped(DIGIT, lambda n: n >= 0), 4)
        check.equal(
            seat,
            [value, values_of(c.choices), labels(c)],
            [True, [("integer", 4)], ["integer"]],
            "the value and the record are those of the source",
        )

    def test_keeps_the_inverse_of_the_function(self, seat: Collector) -> None:
        """The inverse of str is int."""
        check.is_true(
            seat, Mapped(DIGIT, str, int).back is int, "the generator keeps the inverse"
        )


class TestBound:
    """Bound decodes a value of the generator that a function returns for a value."""

    def test_decodes_the_source_before_the_generator_of_its_value_in_one_span(
        self, seat: Collector
    ) -> None:
        """The second value is 2 of [0, 3]."""
        bound = Bound(DIGIT, lambda n: SampledFrom(list(range(n + 1))))
        value, c = decoded_from(bound, 3, 2)
        check.equal(
            seat,
            [value, c.spans[0]],
            [2, Span("bind", 0, 2, 0, None)],
            "the value 2 has one span",
        )


class TestComposite:
    """Composite decodes the value of a function that draws from other generators."""

    def test_decodes_the_value_of_its_function_in_one_span(
        self, seat: Collector
    ) -> None:
        """The function returns a pair."""
        pair = Composite(lambda c: [c.draw(DIGIT, "a"), c.draw(DIGIT, "b")])
        value, c = decoded_from(pair, 1, 2)
        check.equal(
            seat,
            [value, c.spans[0].label],
            [[1, 2], "composite"],
            "the pair decodes in a composite span",
        )


class TestRecursive:
    """Recursive decodes a base value or an extension of recursive values."""

    def test_decodes_the_simplest_value_of_the_base_without_a_choice(
        self, seat: Collector
    ) -> None:
        """The value is the target of the base."""
        check.equal(seat, decoded_from(tree())[0], 0, "the value is 0")

    def test_decodes_its_positions_recursively(self, seat: Collector) -> None:
        """One tree has two leaves, and the other has one leaf a level deeper."""
        check.equal(
            seat,
            [
                decoded_from(tree(), 1, 1, 0, 5, 1, 0, 7, 0)[0],
                decoded_from(tree(), 1, 1, 1, 1, 0, 3, 0, 0)[0],
            ],
            [[5, 7], [[3]]],
            "the trees decode recursively",
        )

    def test_decodes_each_position_in_a_recursive_span_with_a_structure_choice(
        self, seat: Collector
    ) -> None:
        """The spans have their labels, and the first position has its edge."""
        c = decoded_from(tree(), 1, 1, 0, 5, 0)[1]
        check.equal(
            seat,
            [labels(c), c.requests[0].edge],
            [["recursive", "list", "element", "recursive", "integer"], 0],
            "the spans have their labels and the first position its edge",
        )

    def test_forces_the_base_for_each_position_after_max_leaves(
        self, seat: Collector
    ) -> None:
        """The second position takes the base."""
        value, c = decoded_from(tree(1), 1, 1, 0, 5, 1, 1, 7, 0)
        check.equal(
            seat,
            [value, c.requests[5].bounds],
            [[5, 7], IntegerBounds(0, 0)],
            "the second position takes the base",
        )

    def test_counts_the_leaves_of_each_value_from_zero(self, seat: Collector) -> None:
        """Two values of one generator count their leaves from zero."""
        one = tree(1)
        check.equal(
            seat,
            [
                decoded_from(one, 1, 1, 0, 5, 0)[0],
                decoded_from(one, 1, 1, 0, 5, 0)[0],
            ],
            [[5], [5]],
            "both values are [5]",
        )

    def test_counts_the_leaves_of_the_innermost_recursive_generator(
        self, seat: Collector
    ) -> None:
        """The inner tree has its own limit."""
        outer = Recursive(tree(1), 100, lambda own: List(own, Sizes(0, 3)))
        got = decoded_from(outer, 0, 1, 1, 0, 5, 1, 1, 7, 0)[0]
        check.equal(seat, got, [5, 7], "the inner tree stops at its limit")

    def test_counts_the_leaves_of_each_thread_apart(self, seat: Collector) -> None:
        """A decode in another thread leaves the count of this one alone."""
        in_base = threading.Event()
        other_waits = threading.Event()
        done = threading.Event()

        def base(c: Case) -> int:
            if threading.current_thread().name == "first" and not in_base.is_set():
                in_base.set()
                other_waits.wait(WAIT)
            return c.integer(IntegerBounds(0, 9))

        class Waiting(Provider):
            @override
            def value(self, request: Request, index: int) -> Value:
                del index
                other_waits.set()
                done.wait(WAIT)
                return request.bounds.target

        one: Recursive[Any] = Recursive(
            Composite(base), 1, lambda own: List(own, Sizes(0, 3))
        )
        c = replay(1, 1, 0, 5, 1, 1, 7, 0)
        got: list[object] = []

        def first() -> None:
            try:
                got.append(one.decode(c))
            finally:
                done.set()

        thread = threading.Thread(target=first, name="first")
        thread.start()
        in_base.wait(WAIT)
        other = one.decode(Case(Waiting()))
        thread.join()
        check.equal(
            seat,
            [got, c.requests[5].bounds, other],
            [[[5, 7]], IntegerBounds(0, 0), 0],
            "each thread decodes its own value",
        )


class TestPosition:
    """Position decodes a position of the recursive value that is being decoded."""

    def test_decodes_the_next_position_of_its_owner_inside_the_extension(
        self, seat: Collector
    ) -> None:
        """The value is a list of one base position."""
        owner = tree()
        position = Position(owner)
        check.equal(
            seat,
            [position.owner is owner, decoded_from(owner, 1, 1, 0, 4, 0)[0]],
            [True, [4]],
            "the position has its owner and the value",
        )


#: Every kind of generator with its name for the checks of replay.
EVERY: list[tuple[str, Generator[Any]]] = [
    ("integer", DIGIT),
    ("float", Float(FloatBounds(-INF, INF, True))),
    ("boolean", Bool(Fraction(1, 3))),
    ("just", Just(4)),
    ("sampled-from", LETTERS),
    ("one-of", OneOf([DIGIT, TEEN])),
    ("optional", Optional(DIGIT)),
    ("list", DIGITS),
    ("unique list", UNIQUE),
    ("dict", TABLE),
    ("string", Text(None, SequenceBounds(0x10F800, 0, 4))),
    ("alphabet", Text(["x", "y", "z"], SequenceBounds(3))),
    ("bytes", Bytes(SequenceBounds(256))),
    ("duration", Integer(IntegerBounds(-1_000_000_000, 1_000_000_000), "duration")),
    ("permutation", Permutation(["a", "b", "c"])),
    ("recursive", tree()),
    ("filter", KEEP_EVEN),
    ("map", Mapped(DIGITS, sorted)),
]


@pytest.mark.parametrize(
    "generator",
    [t[1] for t in EVERY],
    ids=[f"replays a generated {t[0]} to the same value and choices" for t in EVERY],
)
def test_replays_a_generated_value_to_the_same_value_and_choices(
    seat: Collector, generator: Generator[Any]
) -> None:
    """No seed replays to another value or other choices."""
    differ: list[int] = []
    for seed in range(SEEDS):
        generated = Case(Generating(Source(seed)))
        value = outcome(generator, generated)
        replayed = Case(Replaying(generated.choices))
        again = outcome(generator, replayed)
        recorded = canonical([choice.value for choice in generated.choices])
        if again != value or canonical([c.value for c in replayed.choices]) != recorded:
            differ.append(seed)
    check.is_empty(seat, differ, "no seed replays to another value")


def test_does_not_draw_a_repeated_element_of_a_unique_collection(
    seat: Collector,
) -> None:
    """No unique list or dict of 200 seeds repeats an element."""
    repeats: list[int] = []
    for seed in range(SEEDS):
        elements = UNIQUE.decode(Case(Generating(Source(seed))))
        entries = TABLE.decode(Case(Generating(Source(seed))))
        keys = [key for key, _ in entries.items]
        if len(set(elements)) != len(elements) or len(set(keys)) != len(keys):
            repeats.append(seed)
    check.is_empty(seat, repeats, "no element or key repeats")


def test_draws_floats_that_the_bounds_of_a_float_admit(seat: Collector) -> None:
    """The floats of 200 seeds are inside [-1, 1]."""
    bounds = FloatBounds(-1.0, 1.0)
    generator = Float(bounds)
    values = [generator.decode(Case(Generating(Source(seed)))) for seed in range(SEEDS)]
    check.is_true(
        seat,
        all(bounds.admits(value) and not math.isnan(value) for value in values),
        "the bounds admit every float",
    )
