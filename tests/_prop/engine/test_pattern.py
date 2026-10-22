# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/pattern.py tests the pieces of a pattern."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._pattern.match import compile_pattern
from dokimi_assert._pattern.parse import PatternError
from dokimi_assert._prop.engine.alphabet import SIZE
from dokimi_assert._prop.engine.case import Case, Generating, Replaying, Span
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.generator import Matching
from dokimi_assert._prop.engine.pattern import (
    Alternation,
    Class,
    Literal,
    Repeat,
    Sequence,
    piece,
)
from dokimi_assert._prop.engine.source import Source
from helpers import integers, refusal

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The number of seeds per pattern of the check that generated strings match.
SEEDS = 200

#: Patterns that cover every construct of the subset.
ACCEPTED = [
    "",
    "abc",
    "^abc$",
    "^$",
    "a|b|c",
    "(foo|bar)baz",
    "(?:ab)+",
    "[a-z]+@[a-z]+\\.com",
    "\\d{3}-\\d{4}",
    "\\w+\\s\\w*",
    ".",
    ".{2,5}",
    "[^a-z]",
    "[-a]",
    "[a-]",
    "[a-z-]",
    "[\\]\\[\\\\\\-]",
    "[\\d_]x?",
    "a{0}",
    "a{2,}",
    "(a|)+",
    "x*y+z?",
    "[\U000000e0-\U000000ff]",
    "[.$^*+?(){}|]",
    "\\.\\*\\+\\?\\(\\)\\[\\]\\{\\}\\|\\^\\$\\\\",
    "a{1000}",
]


def decoded_from(text: str, *values: int) -> tuple[str, Case]:
    """Return the string that a pattern decodes from recorded integers, and the case."""
    c = Case(Replaying(integers(*values)))
    return Matching(piece(text)).decode(c), c


def class_of(text: str) -> Class:
    """Return the class piece of a pattern of one class."""
    return cast("Class", piece(text))


class TestPiece:
    """piece returns the piece of a pattern of the portable subset."""

    targets: ClassVar[list[tuple[str, str, str]]] = [
        (
            "decodes a@a.com from [a-z]+@[a-z]+\\.com",
            "[a-z]+@[a-z]+\\.com",
            "a@a.com",
        ),
        ("decodes foobaz from (foo|bar)baz", "(foo|bar)baz", "foobaz"),
        ("decodes xxx from x{3}", "x{3}", "xxx"),
        ("decodes a digit a digit and a space from \\d\\w\\s", "\\d\\w\\s", "00 "),
        ("decodes the digit 0 from the dot", ".", "0"),
        ("decodes a from [^0-9]", "[^0-9]", "a"),
        ("decodes the empty string from a?", "a?", ""),
        ("decodes abc from ^abc$", "^abc$", "abc"),
        ("decodes the digit 0 from [A0a]", "[A0a]", "0"),
        ("decodes the digit 0 from [\\d_]", "[\\d_]", "0"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in targets], ids=[t[0] for t in targets]
    )
    def test_decodes_the_simplest_match_from_the_targets(
        self, seat: Collector, give: str, want: str
    ) -> None:
        """Every choice takes its target."""
        check.equal(
            seat, decoded_from(give)[0], want, "the piece decodes the simplest match"
        )

    @pytest.mark.parametrize(
        "text",
        ACCEPTED,
        ids=[f"generates strings that {text!r} matches in full" for text in ACCEPTED],
    )
    def test_generates_strings_that_the_pattern_matches_in_full(
        self, seat: Collector, text: str
    ) -> None:
        """Every string of 200 seeds matches."""
        generator = Matching(piece(text))
        expression = compile_pattern(text)
        generated = [
            generator.decode(Case(Generating(Source(seed)))) for seed in range(SEEDS)
        ]
        misses = [value for value in generated if not expression.fullmatch(value)]
        check.is_empty(seat, misses, "every string matches")

    def test_raises_pattern_error_for_a_pattern_outside_the_subset(
        self, seat: Collector
    ) -> None:
        """A quantifier follows a quantifier."""
        refusal(seat, lambda: piece("a**"), PatternError)

    def test_raises_value_error_for_a_class_without_a_member(
        self, seat: Collector
    ) -> None:
        """The class excludes every scalar value."""
        got = refusal(seat, lambda: piece("[^\x00-\U0010ffff]"))
        check.equal(
            seat,
            got,
            "prop: a class in the pattern does not have a member",
            "the error has the reason",
        )


class TestLiteralEmit:
    """Literal.emit appends one character without a choice."""

    def test_appends_its_character_without_a_choice(self, seat: Collector) -> None:
        """The character is x."""
        out: list[str] = []
        c = Case(Replaying([]))
        Literal("x").emit(c, out)
        check.equal(
            seat, [out, c.choices], [["x"], []], "emit appends x without a choice"
        )


class TestClassEmit:
    """Class.emit appends one member of a class."""

    def test_appends_the_member_at_the_recorded_index_in_the_order_of_the_alphabet(
        self, seat: Collector
    ) -> None:
        """The digits come first, then the lowercase and the uppercase letters."""
        got = [decoded_from("[A0a]", i)[0] for i in range(3)]
        check.equal(
            seat,
            got,
            ["0", "a", "A"],
            "the members are in the order of the alphabet",
        )

    def test_skips_the_members_of_a_negated_class(self, seat: Collector) -> None:
        """The alphabet has a at index 10."""
        check.equal(
            seat, decoded_from("[^a]", 10)[0], "b", "the member at index 10 is b"
        )

    def test_chooses_an_index_bounded_by_its_size(self, seat: Collector) -> None:
        """The class has three members."""
        value, c = decoded_from("[a-c]", 2)
        check.equal(
            seat,
            [value, c.requests[0].bounds],
            ["c", IntegerBounds(0, 2)],
            "the size of the class bounds the index",
        )

    def test_appends_a_member_of_a_later_interval(self, seat: Collector) -> None:
        """The member x is in the second interval."""
        check.equal(seat, decoded_from("[0x]", 1)[0], "x", "the member is x")


class TestClassOffsetOf:
    """Class.offset_of returns the offset of a character among the members."""

    tests: ClassVar[list[tuple[str, str, int | None]]] = [
        ("returns the offset of a member of the first interval", "3", 3),
        ("returns the offset of a member of a later interval", "x", 10),
        ("returns none for a character that is not a member", "y", None),
        ("returns none for a lone surrogate", "\ud800", None),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_offset_of_a_member(
        self, seat: Collector, give: str, want: int | None
    ) -> None:
        """The class has the digits and x."""
        check.equal(
            seat,
            class_of("[0-9x]").offset_of(give),
            want,
            "offset_of returns the offset",
        )


class TestClass:
    """Class is one character of a set."""

    def test_contains_every_character_of_the_dot_but_the_five_line_terminators(
        self, seat: Collector
    ) -> None:
        """The dot does not match a line terminator."""
        dot = class_of(".")
        terminators = ["\n", "\r", "\x85", "\U00002028", "\U00002029"]
        check.equal(
            seat,
            [dot.size, [dot.offset_of(char) for char in terminators]],
            [SIZE - 5, [None] * 5],
            "the dot has every character but the line terminators",
        )

    def test_contains_the_ascii_members_of_the_digit_and_word_shorthands(
        self, seat: Collector
    ) -> None:
        """The shorthands have ten digits and 63 word characters."""
        check.equal(
            seat,
            [class_of("\\d").size, class_of("\\w").size],
            [10, 63],
            "the shorthands have their ASCII members",
        )

    def test_contains_the_five_members_of_the_space_shorthand_from_space(
        self, seat: Collector
    ) -> None:
        """The members are in the order of the alphabet."""
        got = [decoded_from("\\s", i)[0] for i in range(5)]
        check.equal(
            seat,
            got,
            [" ", "\t", "\n", "\f", "\r"],
            "the space shorthand has five members",
        )


class TestSequenceEmit:
    """Sequence.emit appends its pieces one after another."""

    def test_appends_its_pieces_in_order(self, seat: Collector) -> None:
        """The sequence has two characters."""
        out: list[str] = []
        Sequence([Literal("a"), Literal("b")]).emit(Case(Replaying([])), out)
        check.equal(seat, out, ["a", "b"], "emit appends a and then b")


class TestAlternationEmit:
    """Alternation.emit appends the branch that the case chooses."""

    def test_appends_the_branch_at_the_recorded_index(self, seat: Collector) -> None:
        """The index chooses the second branch."""
        check.equal(seat, decoded_from("(foo|bar)", 1)[0], "bar", "emit appends bar")


class TestAlternation:
    """Alternation is two or more branches."""

    def test_bounds_its_index_by_its_branches(self, seat: Collector) -> None:
        """The alternation has three branches."""
        three = Alternation([Literal("a"), Literal("b"), Literal("c")])
        check.equal(seat, three.bounds, IntegerBounds(0, 2), "the bounds are 0 to 2")


class TestRepeatEmit:
    """Repeat.emit appends the repetitions of a quantified piece."""

    def test_appends_its_repetitions_as_a_collection(self, seat: Collector) -> None:
        """The choices are two continue flags and a stop."""
        check.equal(seat, decoded_from("a*", 1, 1, 0)[0], "aa", "emit appends aa")

    def test_forces_the_flags_of_a_fixed_count(self, seat: Collector) -> None:
        """The quantifier forces two repetitions."""
        check.equal(
            seat,
            decoded_from("(ab|c){2}", 0, 1, 0, 0, 1)[0],
            "cab",
            "emit appends cab",
        )

    def test_decodes_in_spans_with_the_edges_of_its_flags(
        self, seat: Collector
    ) -> None:
        """The case records the spans and the edges."""
        c = decoded_from("(a|b)[cd]*", 1, 1, 1, 0)[1]
        check.equal(
            seat,
            [c.spans, [request.edge for request in c.requests]],
            [
                [
                    Span("string-matching", 0, 4, 0, None),
                    Span("alternation", 0, 1, 1, 0),
                    Span("repeat", 1, 4, 1, 0),
                    Span("element", 1, 3, 2, 2),
                ],
                [0, 1, None, 0],
            ],
            "the case has the spans and the edges",
        )


class TestRepeat:
    """Repeat is a quantified piece."""

    def test_keeps_its_item_and_its_sizes(self, seat: Collector) -> None:
        """Repeat keeps its item and its sizes."""
        item = Literal("a")
        repeat = Repeat(item, Sizes(1, 2))
        check.equal(
            seat,
            [repeat.item is item, repeat.sizes.min_size, repeat.sizes.max_size],
            [True, 1, 2],
            "the repeat keeps its item and its sizes",
        )
