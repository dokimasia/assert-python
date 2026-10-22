"""The spec of _prop/engine/inverse.py tests generators that run backwards.

The choices of a generated value replay to that value. When more than one
sequence of choices decodes to a value, the inverse takes the first.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import Case, Generating, Rejected, Replaying
from dokimi_assert._prop.engine.choice import (
    Choice,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.generator import (
    Bool,
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
    Recursive,
    SampledFrom,
    Text,
)
from dokimi_assert._prop.engine.inverse import (
    CannotInvertError,
    NoInverseError,
    emit,
    inverse_of,
    invert,
)
from dokimi_assert._prop.engine.pattern import piece
from dokimi_assert._prop.engine.shape import read
from dokimi_assert._prop.engine.source import case_source
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical
from dokimi_assert._prop.engine.zone import ZONES
from dokimi_assert.seat import Collector
from helpers import Picked

#: The number of cases of each generator in the round trip.
CASES = 60

INF = float("inf")

DIGIT = Integer(IntegerBounds(0, 9))
TEEN = Integer(IntegerBounds(10, 20))
DIGITS = List(DIGIT, Sizes(0, 3))
EVEN = Filter(DIGIT, lambda value: value % 2 == 0)
UINT8 = {"shape": "int", "width": 8, "signed": False}

#: A map of a digit without an inverse.
IDENTITY = Mapped(DIGIT, lambda value: value)

#: A tree shape. A tree is a record of a value and a list of child trees.
TREE_SHAPE = {
    "shape": "ref",
    "name": "tree",
    "definitions": {
        "tree": {
            "shape": "record",
            "fields": [
                ["value", UINT8],
                ["children", {"shape": "list", "of": {"shape": "ref", "name": "tree"}}],
            ],
        }
    },
}


def tree(base: Generator[Any] = DIGIT) -> Recursive[Any]:
    """Return a tree of a base. A tree is the base or a list of at most three trees."""
    return Recursive(base, 100, lambda own: List(own, Sizes(0, 3)))


def choice_values(choices: list[Choice]) -> list[object]:
    """Return the values of choices."""
    return [choice.value for choice in choices]


def replayed(generator: Generator[Any], choices: list[Choice]) -> object:
    """Return the value that choices decode to."""
    return generator.decode(Case(Replaying(choices)))


def text_of(value: object, unordered: bool) -> str:
    """Return the canonical text of a value. The elements of a set are sorted."""
    if unordered:
        elements = cast("list[object]", value)
        return ";".join(sorted(canonical(element) for element in elements))
    return canonical(value)


def round_trip(
    generator: Generator[Any], unordered: bool = False
) -> tuple[int, list[int]]:
    """Return the number of values that run backwards and the cases that replay wrong.

    A case replays wrong when its choices decode to another value.
    """
    inverted = 0
    failed: list[int] = []
    for index in range(CASES):
        try:
            value = generator.decode(Case(Generating(case_source(17, index))))
        except Rejected:
            continue
        again = replayed(generator, invert(generator, value))
        if text_of(again, unordered) != text_of(value, unordered):
            failed.append(index)
        inverted += 1
    return inverted, failed


def refused(
    seat: Collector, generator: Generator[Any], value: object
) -> tuple[str, bool]:
    """Return the text of the error of invert, and True when it is a NoInverseError."""
    error = check.raises(seat, lambda: invert(generator, value), "the value is refused")
    check.error_as(seat, error, CannotInvertError, "the error is a CannotInvertError")
    return str(error), isinstance(error, NoInverseError)


class Custom:
    """A piece of a pattern outside the portable subset."""

    def emit(self, c: Case, out: list[str]) -> None:
        """Append an x."""
        del c
        out.append("x")


class TestCannotInvertError:
    """CannotInvertError is the error of a value that a generator cannot produce."""

    def test_is_a_value_error(self, seat: Collector) -> None:
        """A caller that catches ValueError catches the error."""
        error = CannotInvertError("prop: int:10 is outside integer 0 9")
        check.error_as(seat, error, ValueError, "the error is a ValueError")


class TestNoInverseError:
    """NoInverseError is the error of a value that the engine cannot run backwards."""

    def test_is_a_cannot_invert_error(self, seat: Collector) -> None:
        """A NoInverseError is a CannotInvertError."""
        error = NoInverseError("prop: a map does not run backwards")
        check.error_as(
            seat, error, CannotInvertError, "the error is a CannotInvertError"
        )


#: Every kind of generator with an inverse and its name.
GENERATORS: list[tuple[str, Generator[Any]]] = [
    ("integer", DIGIT),
    ("float", Float(FloatBounds(-INF, INF, True))),
    ("boolean", Bool(Fraction(1, 3))),
    ("just", Just(4)),
    ("sampled-from", SampledFrom(["a", "b", "c"])),
    ("one-of", OneOf([DIGIT, TEEN])),
    ("optional", Optional(DIGIT)),
    ("list", DIGITS),
    ("unique list", List(DIGIT, Sizes(), True)),
    ("dict", Dict(DIGIT, Bool(Fraction(1, 2)), Sizes(0, 3))),
    ("string", Text(None, SequenceBounds(0x10F800, 0, 4))),
    ("alphabet", Text(["x", "y", "z"], SequenceBounds(3))),
    ("string-matching", Matching(piece("(a|[0-9]+)\\.?x{2}"))),
    ("bytes", Bytes(SequenceBounds(256))),
    ("duration", Integer(IntegerBounds(-1_000_000_000, 1_000_000_000), "duration")),
    ("permutation", Permutation(["a", "b", "c"])),
    ("recursive", tree()),
    ("filter", EVEN),
    ("map with an inverse", Mapped(DIGIT, str, int)),
]

#: A shape of every kind and its name.
SHAPES: list[tuple[str, dict[str, Any]]] = [
    ("bool", {"shape": "bool"}),
    ("int", {"shape": "int", "width": 16, "signed": True}),
    ("int-128", {"shape": "int", "width": 128, "signed": True}),
    ("float", {"shape": "float", "width": 32, "allow_nan": True}),
    ("char", {"shape": "char"}),
    ("string", {"shape": "string", "max_size": 6}),
    ("pattern", {"shape": "string", "pattern": "[a-c]{2,4}(x|yz)?"}),
    ("bytes", {"shape": "bytes", "max_size": 4}),
    ("list", {"shape": "list", "of": UINT8, "max_size": 4}),
    ("fixed-list", {"shape": "fixed-list", "of": UINT8, "size": 3}),
    ("set", {"shape": "set", "of": {"shape": "int", "width": 8, "signed": True}}),
    ("map", {"shape": "map", "key": UINT8, "of": {"shape": "bool"}}),
    ("optional", {"shape": "optional", "of": UINT8}),
    (
        "record",
        {"shape": "record", "fields": [["id", UINT8], ["ok", {"shape": "bool"}]]},
    ),
    ("enum", {"shape": "enum", "variants": [["none", None], ["some", UINT8]]}),
    (
        "literal",
        {
            "shape": "literal",
            "values": [{"type": "string", "value": v} for v in ("a", "b", "a")],
        },
    ),
    ("ref", TREE_SHAPE),
    ("uuid", {"shape": "uuid"}),
    ("ip-address", {"shape": "ip-address"}),
    ("decimal", {"shape": "decimal", "scale": 2, "min": "-5.00", "max": "5.00"}),
    ("instant", {"shape": "instant", "unit": "ms", "min": "2020-01-01T00:00:00.5Z"}),
    ("instant in seconds", {"shape": "instant", "unit": "s"}),
    ("date", {"shape": "date"}),
    ("time-of-day", {"shape": "time-of-day", "unit": "us"}),
    ("local-date-time", {"shape": "local-date-time", "unit": "s"}),
    ("duration", {"shape": "duration", "unit": "ns"}),
    ("offset", {"shape": "offset"}),
    ("zone", {"shape": "zone"}),
    ("zoned-date-time", {"shape": "zoned-date-time", "unit": "ns"}),
    ("wall-time", {"shape": "wall-time", "unit": "ms"}),
]


class TestInvert:
    """invert returns the choices that decode to a value."""

    @pytest.mark.parametrize(
        "generator",
        [t[1] for t in GENERATORS],
        ids=[
            f"runs a generated {t[0]} backwards to choices that replay to it"
            for t in GENERATORS
        ],
    )
    def test_runs_a_generated_value_backwards_to_choices_that_replay_to_it(
        self, seat: Collector, generator: Generator[Any]
    ) -> None:
        """More than half of the cases run backwards, and each replays to its value."""
        inverted, failed = round_trip(generator)
        check.equal(
            seat,
            [inverted > CASES // 2, failed],
            [True, []],
            "the cases run backwards and replay",
        )

    @pytest.mark.parametrize(
        ("name", "shape"),
        SHAPES,
        ids=[
            f"runs a generated {t[0]} shape backwards to choices that replay to it"
            for t in SHAPES
        ],
    )
    def test_runs_a_generated_shape_backwards_to_choices_that_replay_to_it(
        self, seat: Collector, name: str, shape: dict[str, Any]
    ) -> None:
        """More than half of the cases run backwards, and each replays to its value."""
        inverted, failed = round_trip(read(shape), name == "set")
        check.equal(
            seat,
            [inverted > CASES // 2, failed],
            [True, []],
            "the cases run backwards and replay",
        )

    def test_takes_the_first_alternative_of_a_one_of_that_produces_the_value(
        self, seat: Collector
    ) -> None:
        """7 comes from the first alternative, and 12 from the second."""
        either = OneOf([DIGIT, Integer(IntegerBounds(5, 15))])
        check.equal(
            seat,
            [choice_values(invert(either, 7)), choice_values(invert(either, 12))],
            [[0, 7], [1, 12]],
            "the choices take the first alternative that fits",
        )

    def test_takes_the_first_index_of_an_equal_value_of_a_sampled_from(
        self, seat: Collector
    ) -> None:
        """The index is 0."""
        got = choice_values(invert(SampledFrom(["a", "b", "a"]), "a"))
        check.equal(seat, got, [0], "the index is 0")

    def test_takes_the_smallest_index_at_each_swap_of_a_permutation(
        self, seat: Collector
    ) -> None:
        """The first 1 keeps its position."""
        got = choice_values(invert(Permutation([1, 1, 2]), [1, 2, 1]))
        check.equal(seat, got, [0, 2], "each swap takes the smallest index")

    patterns: ClassVar[list[tuple[str, str, str, list[int]]]] = [
        ("takes the greedy match of a repetition", "a*a*", "aa", [1, 1, 0, 0]),
        ("takes the first alternative that matches", "x|x", "x", [0]),
        (
            "takes a repetition that gives back a character to the rest",
            "a*ab",
            "aab",
            [1, 0],
        ),
        ("takes the next alternative after a short match", "a|ab", "ab", [1]),
        (
            "takes a sequence that resumes its search after a short match",
            "(a|ab)c*",
            "ab",
            [1, 0],
        ),
        (
            "takes a repetition that does not repeat an empty match",
            "(a?)*",
            "a",
            [1, 1, 0, 0],
        ),
        ("takes a class index of each character", "[a-c]x", "cx", [2]),
    ]

    @pytest.mark.parametrize(
        ("text", "value", "want"),
        [t[1:] for t in patterns],
        ids=[t[0] for t in patterns],
    )
    def test_takes_the_first_match_of_a_backtracking_engine(
        self, seat: Collector, text: str, value: str, want: list[int]
    ) -> None:
        """The choices are those of the first match."""
        got = choice_values(invert(Matching(piece(text)), value))
        check.equal(seat, got, want, "the choices are those of the first match")

    def test_matches_a_string_of_5000_characters_within_the_recursion_limit(
        self, seat: Collector
    ) -> None:
        """The choices are 5000 continue flags and a stop."""
        got = invert(Matching(piece("a*")), "a" * 5000)
        check.equal(
            seat,
            choice_values(got),
            [1] * 5000 + [0],
            "the choices are 5000 flags and a stop",
        )

    def test_takes_absent_for_the_absent_value_of_an_optional_of_an_optional(
        self, seat: Collector
    ) -> None:
        """The outer optional is absent."""
        got = choice_values(invert(Optional(Optional(DIGIT)), None))
        check.equal(seat, got, [0], "the outer optional is absent")

    def test_takes_the_elements_of_a_set_in_shortlex_order(
        self, seat: Collector
    ) -> None:
        """2 comes before 5."""
        got = choice_values(invert(read({"shape": "set", "of": UINT8}), [5, 2]))
        check.equal(seat, got, [1, 2, 1, 5, 0], "the elements are in shortlex order")

    def test_takes_the_entries_of_a_map_in_shortlex_order(
        self, seat: Collector
    ) -> None:
        """The entry of key 1 comes first."""
        shape = read({"shape": "map", "key": UINT8, "of": UINT8})
        got = choice_values(invert(shape, Pairs(((4, 0), (1, 9)))))
        check.equal(
            seat, got, [1, 1, 9, 1, 4, 0, 0], "the entries are in shortlex order"
        )

    def test_takes_the_whole_range_for_an_instant_at_a_change_of_its_zone(
        self, seat: Collector
    ) -> None:
        """The choices are the zone, 0 and the instant."""
        change = ZONES[1].changes[0]
        value = Fields(
            (
                ("instant", Fields((("seconds", change.at), ("units", 0)))),
                ("zone", "Europe/Amsterdam"),
            )
        )
        shape = read({"shape": "zoned-date-time", "unit": "s"})
        check.equal(
            seat,
            choice_values(invert(shape, value)),
            [1, 0, change.at],
            "the choices take the whole range",
        )

    def test_takes_the_zone_without_a_whole_range_choice_for_a_zone_without_a_change(
        self, seat: Collector
    ) -> None:
        """The choices are UTC, the date and the time."""
        value = Fields(
            (
                ("local-date-time", Fields((("date", 1), ("time-of-day", 2)))),
                ("zone", "UTC"),
            )
        )
        shape = read({"shape": "wall-time", "unit": "s"})
        check.equal(
            seat,
            choice_values(invert(shape, value)),
            [0, 1, 2],
            "the choices do not have a whole-range choice",
        )

    def test_takes_the_base_before_the_extension_of_a_recursive_value(
        self, seat: Collector
    ) -> None:
        """An empty list is a base."""
        got = choice_values(invert(tree(List(DIGIT, Sizes())), []))
        check.equal(seat, got, [0, 0], "the value takes the base")

    def test_runs_a_nested_recursive_value_back_through_its_positions(
        self, seat: Collector
    ) -> None:
        """The value is a list in a list."""
        got = choice_values(invert(tree(), [[3]]))
        check.equal(
            seat,
            got,
            [1, 1, 1, 1, 0, 3, 0, 0],
            "the choices pass through each position",
        )

    def test_runs_a_one_of_back_through_an_alternative_with_an_inverse(
        self, seat: Collector
    ) -> None:
        """The digit alternative follows the map."""
        got = choice_values(invert(OneOf([IDENTITY, DIGIT]), 3))
        check.equal(seat, got, [1, 3], "the choices take the digit alternative")

    def test_runs_a_filter_back_through_the_generator_that_it_filters(
        self, seat: Collector
    ) -> None:
        """4 is even."""
        check.equal(seat, choice_values(invert(EVEN, 4)), [4], "the choice is 4")

    def test_runs_a_deferred_generator_back_through_the_generator_that_it_picks(
        self, seat: Collector
    ) -> None:
        """The walk picks the digit, and the replay of the choices picks it again."""
        deferred = Picked(DIGIT)
        check.equal(
            seat,
            [choice_values(invert(deferred, 4)), deferred.picks],
            [[4], 2],
            "the choice is 4",
        )

    def test_passes_over_an_alternative_of_a_one_of_that_cannot_produce_the_value(
        self, seat: Collector
    ) -> None:
        """The second alternative fits each time."""
        cases: list[tuple[list[Generator[Any]], object]] = [
            ([List(DIGIT, Sizes(0, 1)), List(DIGIT, Sizes(0, 3))], [1, 2]),
            ([List(DIGIT, Sizes(), True), List(DIGIT, Sizes())], [1, 1]),
            ([EVEN, DIGIT], 3),
        ]
        got = [invert(OneOf(of), value)[0].value for of, value in cases]
        check.equal(seat, got, [1, 1, 1], "each index is the second alternative")

    refusals: ClassVar[list[tuple[str, Generator[Any], object, str]]] = [
        (
            "raises cannot invert error for an integer outside its bounds",
            DIGIT,
            10,
            "prop: int:10 is outside integer 0 9",
        ),
        (
            "raises cannot invert error for a bool for an integer",
            DIGIT,
            True,
            "prop: bool:true is outside integer 0 9",
        ),
        (
            "raises cannot invert error for an integer for a bool",
            Bool(Fraction(1, 2)),
            1,
            "prop: int:1 is not a bool",
        ),
        (
            "raises cannot invert error for another value than a just",
            Just(4),
            5,
            "prop: int:5 is not int:4",
        ),
        (
            "raises cannot invert error for a list longer than its maximum",
            List(DIGIT, Sizes(0, 1)),
            [1, 2],
            "prop: 2 items are outside the sizes of the collection",
        ),
        (
            "raises cannot invert error for a repeat in a unique list",
            List(DIGIT, Sizes(), True),
            [1, 1],
            "prop: list:[int:1,int:1] repeats a value",
        ),
        (
            "raises cannot invert error for a set for a list",
            DIGITS,
            {1},
            "prop: set:{int:1} is not a list",
        ),
        (
            "raises cannot invert error for a python dict for a dict",
            Dict(DIGIT, DIGIT, Sizes()),
            {1: 2},
            "prop: map:{int:1=int:2} is not a map",
        ),
        (
            "raises cannot invert error for a repeated key of a dict",
            Dict(DIGIT, DIGIT, Sizes()),
            Pairs(((1, 2), (1, 3))),
            "prop: list:[int:1,int:1] repeats a value",
        ),
        (
            "raises cannot invert error for a character outside a given alphabet",
            Text(["a", "b"], SequenceBounds(2)),
            "c",
            'prop: string:"c" has a character outside the alphabet',
        ),
        (
            "raises cannot invert error for a lone surrogate for the default alphabet",
            Text(None, SequenceBounds(0x10F800)),
            "\ud800",
            'prop: string:"\\ud800" has a character outside the alphabet',
        ),
        (
            "raises cannot invert error for bytes for a string",
            Text(None, SequenceBounds(0x10F800)),
            b"x",
            "prop: bytes:78 is not a string",
        ),
        (
            "raises cannot invert error for bytes longer than their maximum",
            Bytes(SequenceBounds(256, 0, 1)),
            b"\x01\x02",
            "prop: list:[int:1,int:2] is outside sequence 256 0 1",
        ),
        (
            "raises cannot invert error for a string for bytes",
            Bytes(SequenceBounds(256)),
            "x",
            'prop: string:"x" is not bytes',
        ),
        (
            "raises cannot invert error for a string that the pattern does not match",
            Matching(piece("a+")),
            "b",
            'prop: the pattern does not match string:"b" in full',
        ),
        (
            "raises cannot invert error for an integer for a pattern",
            Matching(piece("a+")),
            1,
            "prop: int:1 is not a string",
        ),
        (
            "raises cannot invert error for a value of no alternative",
            OneOf([DIGIT]),
            11,
            "prop: no alternative produces int:11",
        ),
        (
            "raises cannot invert error for a value that the filter rejects",
            EVEN,
            3,
            "prop: the filter rejects int:3",
        ),
        (
            "raises cannot invert error for a value that a permutation lacks",
            Permutation([1]),
            [2],
            "prop: list:[int:2] is not a permutation of the values",
        ),
        (
            "raises cannot invert error for more values than a permutation has",
            Permutation([1]),
            [1, 1],
            "prop: list:[int:1,int:1] is not a permutation of the values",
        ),
        (
            "raises cannot invert error for an element that a permutation lacks",
            Permutation([1, 2]),
            [3, 1],
            "prop: int:3 is not one of the values",
        ),
        (
            "raises cannot invert error for a value that a sampled-from lacks",
            SampledFrom([1]),
            2,
            "prop: int:2 is not one of the values",
        ),
        (
            "raises cannot invert error for a value of neither branch of a tree",
            tree(),
            "x",
            'prop: neither the base nor the extension produces string:"x"',
        ),
    ]

    @pytest.mark.parametrize(
        ("generator", "value", "want"),
        [t[1:] for t in refusals],
        ids=[t[0] for t in refusals],
    )
    def test_raises_cannot_invert_for_a_value_that_the_generator_cannot_produce(
        self, seat: Collector, generator: Generator[Any], value: object, want: str
    ) -> None:
        """The error is not a NoInverseError."""
        check.equal(
            seat,
            refused(seat, generator, value),
            (want, False),
            "the error has the reason and is not a NoInverseError",
        )

    shape_refusals: ClassVar[list[tuple[str, dict[str, Any], object, str]]] = [
        (
            "raises cannot invert error for a record of other fields",
            {"shape": "record", "fields": [["id", UINT8]]},
            Fields((("x", 1),)),
            'prop: record:["x"=int:1] is not a record of id',
        ),
        (
            "raises cannot invert error for an integer for a record",
            {"shape": "record", "fields": [["id", UINT8]]},
            5,
            "prop: int:5 is not a record of id",
        ),
        (
            "raises cannot invert error for a variant whose name the enum lacks",
            {"shape": "enum", "variants": [["a", None]]},
            Variant("b"),
            'prop: variant:"b" is not a variant of a',
        ),
        (
            "raises cannot invert error for a payload of a variant without one",
            {"shape": "enum", "variants": [["a", None]]},
            Variant("a", 1),
            "prop: the variant a does not have a payload",
        ),
        (
            "raises cannot invert error for a string for an enum",
            {"shape": "enum", "variants": [["a", None]]},
            "a",
            'prop: string:"a" is not a variant of a',
        ),
        (
            "raises cannot invert error for units of an instant at seconds",
            {"shape": "instant", "unit": "s"},
            Fields((("seconds", 0), ("units", 1))),
            "prop: an instant at seconds has 0 units, not int:1",
        ),
        (
            "raises cannot invert error for bool units of an instant at seconds",
            {"shape": "instant", "unit": "s"},
            Fields((("seconds", 0), ("units", False))),
            "prop: an instant at seconds has 0 units, not bool:false",
        ),
        (
            "raises cannot invert error for an integer for an instant",
            {"shape": "instant", "unit": "s"},
            0,
            "prop: int:0 is not a record of seconds and units",
        ),
        (
            "raises cannot invert error for an address of five bytes",
            {"shape": "ip-address"},
            bytes(5),
            "prop: bytes:0000000000 is neither 4 nor 16 bytes",
        ),
        (
            "raises cannot invert error for a string for an address",
            {"shape": "ip-address"},
            "127.0.0.1",
            'prop: string:"127.0.0.1" is not an address',
        ),
        (
            "raises cannot invert error for a zone outside the list",
            {"shape": "zone"},
            "Mars/Olympus",
            'prop: string:"Mars/Olympus" is not one of the values',
        ),
        (
            "raises cannot invert error for a zoned value of a zone outside the list",
            {"shape": "zoned-date-time", "unit": "s"},
            Fields((("instant", 0), ("zone", "Mars/Olympus"))),
            'prop: string:"Mars/Olympus" is not one of the values',
        ),
        (
            "raises cannot invert error for a negative unsigned 128-bit int",
            {"shape": "int", "width": 128, "signed": False},
            -1,
            "prop: int:-1 is outside integer 0 18446744073709551615",
        ),
        (
            "raises cannot invert error for a float for a 128-bit int",
            {"shape": "int", "width": 128, "signed": False},
            1.5,
            "prop: float:4609434218613702656 is not an integer",
        ),
    ]

    @pytest.mark.parametrize(
        ("shape", "value", "want"),
        [t[1:] for t in shape_refusals],
        ids=[t[0] for t in shape_refusals],
    )
    def test_raises_cannot_invert_for_a_value_that_the_shape_cannot_produce(
        self, seat: Collector, shape: dict[str, Any], value: object, want: str
    ) -> None:
        """The error is not a NoInverseError."""
        check.equal(
            seat,
            refused(seat, read(shape), value),
            (want, False),
            "the error has the reason and is not a NoInverseError",
        )

    def test_raises_cannot_invert_for_a_value_of_more_choices_than_a_case_can_make(
        self, seat: Collector
    ) -> None:
        """9,000 digits take more than 8,192 choices."""
        text, none = refused(seat, List(DIGIT, Sizes()), [0] * 9000)
        check.equal(
            seat,
            [text.endswith("do not decode to a value"), none],
            [True, False],
            "the choices do not decode to a value",
        )

    def test_raises_cannot_invert_for_a_tree_past_its_budget(
        self, seat: Collector
    ) -> None:
        """The replay stops at the budget."""
        value: object = Fields((("value", 0), ("children", [])))
        for _ in range(100):
            value = Fields((("value", 0), ("children", [value])))
        text, _ = refused(seat, read(TREE_SHAPE), value)
        check.is_true(
            seat,
            text.endswith("is not a value that the generator produces"),
            "the generator does not produce the tree",
        )

    def test_raises_cannot_invert_for_a_value_that_the_inverse_of_a_map_refuses(
        self, seat: Collector
    ) -> None:
        """The error has the error of the inverse."""

        def parsed(text: str) -> int:
            if not text.isdigit():
                raise ValueError(f"{text} is not a digit")
            return int(text)

        check.equal(
            seat,
            refused(seat, Mapped(DIGIT, str, parsed), "x"),
            ('prop: string:"x" is not a value of the map: x is not a digit', False),
            "the error has the error of the inverse",
        )

    def test_passes_on_a_cannot_invert_of_the_inverse_of_a_map(
        self, seat: Collector
    ) -> None:
        """The error of the inverse propagates."""

        def strict(_: str) -> int:
            raise CannotInvertError("prop: the map refuses it")

        check.equal(
            seat,
            refused(seat, Mapped(DIGIT, str, strict), "1"),
            ("prop: the map refuses it", False),
            "the error is the error of the inverse",
        )

    def test_raises_no_inverse_for_a_map_without_an_inverse(
        self, seat: Collector
    ) -> None:
        """The map does not have an inverse."""
        check.equal(
            seat,
            refused(seat, IDENTITY, 1),
            ("prop: a map does not run backwards", True),
            "the error is a NoInverseError",
        )

    def test_raises_no_inverse_for_a_generator_without_an_emitter(
        self, seat: Collector
    ) -> None:
        """A composite runs only forwards."""
        check.equal(
            seat,
            refused(seat, Composite(lambda _: 1), 1),
            ("prop: a Composite does not run backwards", True),
            "the error is a NoInverseError",
        )

    def test_raises_no_inverse_for_a_pattern_of_a_piece_outside_the_subset(
        self, seat: Collector
    ) -> None:
        """The pattern has a piece of its own."""
        check.equal(
            seat,
            refused(seat, Matching(Custom()), "x"),
            ("prop: a Custom piece does not run backwards", True),
            "the error is a NoInverseError",
        )

    around: ClassVar[list[tuple[str, Generator[Any], object]]] = [
        (
            "raises no inverse error for a list around a map without an inverse",
            List(IDENTITY, Sizes()),
            [1],
        ),
        (
            "raises no inverse error for an optional around a map without an inverse",
            Optional(IDENTITY),
            1,
        ),
        (
            "raises no inverse error for a filter around a map without an inverse",
            Filter(IDENTITY, lambda _: True),
            1,
        ),
    ]

    @pytest.mark.parametrize(
        ("generator", "value"), [t[1:] for t in around], ids=[t[0] for t in around]
    )
    def test_raises_no_inverse_around_a_map_without_an_inverse(
        self, seat: Collector, generator: Generator[Any], value: object
    ) -> None:
        """The error of the inner map propagates."""
        check.is_true(
            seat, refused(seat, generator, value)[1], "the error is a NoInverseError"
        )

    def test_raises_no_inverse_for_a_one_of_whose_branch_without_an_inverse_can_fit(
        self, seat: Collector
    ) -> None:
        """One branch does not have an inverse."""
        check.equal(
            seat,
            refused(seat, OneOf([DIGIT, IDENTITY]), 11),
            (
                "prop: no alternative produces int:11, and one of them does not "
                "have an inverse",
                True,
            ),
            "the error is a NoInverseError",
        )

    def test_raises_no_inverse_for_a_recursive_value_whose_base_lacks_an_inverse(
        self, seat: Collector
    ) -> None:
        """The base does not have an inverse."""
        check.equal(
            seat,
            refused(seat, tree(IDENTITY), "x"),
            (
                'prop: neither the base nor the extension produces string:"x", and '
                "one of them does not have an inverse",
                True,
            ),
            "the error is a NoInverseError",
        )

    def test_does_not_raise_no_inverse_for_a_value_outside_every_branch_with_an_inverse(
        self, seat: Collector
    ) -> None:
        """The value is outside the domain."""
        check.is_false(
            seat,
            refused(seat, OneOf([DIGIT]), 11)[1],
            "the error is not a NoInverseError",
        )

    def test_raises_an_error_of_the_generator_that_is_not_a_refusal(
        self, seat: Collector
    ) -> None:
        """The error of the map propagates."""

        def broke(_: int) -> int:
            raise TypeError("the map broke")

        error = check.raises(
            seat, lambda: invert(Mapped(DIGIT, broke, int), 1), "the map raises"
        )
        check.error_as(seat, error, TypeError, "the error is the TypeError of the map")

    def test_raises_an_error_of_a_branch_that_is_not_a_refusal(
        self, seat: Collector
    ) -> None:
        """The error of the branch propagates."""

        def broke(_: int) -> int:
            raise TypeError("the map broke")

        broken = OneOf([Mapped(DIGIT, broke, int)])
        error = check.raises(seat, lambda: invert(broken, 1), "the branch raises")
        check.error_as(
            seat, error, TypeError, "the error is the TypeError of the branch"
        )

    def test_raises_an_error_of_a_replay_that_is_not_a_rejection(
        self, seat: Collector
    ) -> None:
        """The error of the replay propagates."""
        calls = [0]

        def flaky(value: int) -> int:
            calls[0] += 1
            if calls[0] > 1:
                raise ArithmeticError("the second call broke")
            return value

        error = check.raises(
            seat, lambda: invert(Mapped(DIGIT, flaky, int), 1), "the replay raises"
        )
        check.error_as(
            seat,
            error,
            ArithmeticError,
            "the error is the ArithmeticError of the replay",
        )


class TestInverseOf:
    """inverse_of returns the choices that decode to a value, or None."""

    def test_returns_the_choices_that_decode_to_a_value(self, seat: Collector) -> None:
        """7 has one choice."""
        got = inverse_of(DIGIT, 7)
        check.equal(
            seat,
            None if got is None else [(c.kind, c.value) for c in got],
            [("integer", 7)],
            "the choice is 7",
        )

    def test_returns_none_for_a_value_that_the_generator_cannot_produce(
        self, seat: Collector
    ) -> None:
        """10 is not a digit."""
        check.is_none(seat, inverse_of(DIGIT, 10), "the result is None")

    def test_returns_none_for_a_generator_without_an_inverse(
        self, seat: Collector
    ) -> None:
        """The map does not have an inverse."""
        check.is_none(seat, inverse_of(IDENTITY, 1), "the result is None")

    def test_raises_an_error_of_the_generator_that_is_not_a_refusal(
        self, seat: Collector
    ) -> None:
        """The error of the map propagates."""

        def broke(_: int) -> int:
            raise TypeError("the map broke")

        error = check.raises(
            seat, lambda: inverse_of(Mapped(DIGIT, broke, int), 1), "the map raises"
        )
        check.error_as(seat, error, TypeError, "the error is the TypeError of the map")


class TestEmit:
    """emit returns the steps of one generator for a value."""

    def test_returns_the_steps_of_a_value_with_the_value_that_they_decode_to(
        self, seat: Collector
    ) -> None:
        """The elements come in shortlex order."""
        steps, normal = emit(read({"shape": "set", "of": UINT8}), [5, 2])
        check.equal(
            seat,
            [[step.value for step in steps], normal],
            [[1, 2, 1, 5, 0], [2, 5]],
            "the steps and the value are in shortlex order",
        )
