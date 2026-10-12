"""The spec of _pattern/parse.py tests the parser of the portable pattern subset.

Each entry of testdata/verdicts.json is the verdict of the reference parser
of the definition on the pattern of the entry. A refusal has the position at
which the reference refuses the pattern. The parser returns the same verdict
at the same position.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from dokimi_assert import check
from dokimi_assert._pattern.parse import (
    LINE_TERMINATORS,
    SHORTHANDS,
    Alternation,
    Class,
    Concat,
    Literal,
    Pattern,
    PatternError,
    Repeat,
    parse,
)
from dokimi_assert.seat import Collector

VERDICTS: list[dict[str, Any]] = json.loads(
    (pathlib.Path(__file__).parent / "testdata" / "verdicts.json").read_text(
        encoding="utf-8"
    )
)

ACCEPTED = [v["pattern"] for v in VERDICTS if v["accepted"]]

REFUSED = [(v["pattern"], v["at"]) for v in VERDICTS if v.get("at") is not None]

UNPLACED = [v["pattern"] for v in VERDICTS if "at" in v and v["at"] is None]


def case_name(verb: str, pattern: str) -> str:
    """Return the name of the case of a pattern."""
    return f"{verb} {json.dumps(pattern)[:60]}"


class TestLineTerminators:
    """LINE_TERMINATORS contains the characters that the dot leaves out."""

    def test_contains_the_line_terminators_of_every_engine(
        self, seat: Collector
    ) -> None:
        """The dot of some engine does not match them."""
        want = "\n\r\N{NEXT LINE}\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}"
        check.equal(
            seat,
            LINE_TERMINATORS,
            want,
            "LINE_TERMINATORS contains the five line terminators",
        )


class TestShorthands:
    r"""SHORTHANDS contains the members of the classes \d, \w and \s."""

    def test_contains_the_members_that_the_class_of_every_engine_has(
        self, seat: Collector
    ) -> None:
        """Each class has the ASCII members alone."""
        check.equal(
            seat,
            SHORTHANDS,
            {
                "d": "0123456789",
                "w": "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_",
                "s": " \t\n\f\r",
            },
            "each shorthand has the ASCII members alone",
        )


class TestParse:
    """parse returns the tree of a pattern of the portable subset."""

    def test_checks_verdicts_of_acceptance_with_verdicts_of_refusal(
        self, seat: Collector
    ) -> None:
        """The table has both kinds of verdict."""
        check.is_not_empty(seat, ACCEPTED, "the table has a verdict that accepts")
        check.is_not_empty(seat, REFUSED, "the table has a verdict that refuses")
        check.equal(
            seat,
            UNPLACED,
            ["a\ud800"],
            "the verdict of a lone surrogate does not have a position",
        )

    @pytest.mark.parametrize(
        "give", ACCEPTED, ids=[case_name("accepts", p) for p in ACCEPTED]
    )
    def test_accepts_a_pattern_that_the_reference_accepts(
        self, seat: Collector, give: str
    ) -> None:
        """The subset contains the pattern."""
        check.does_not_raise(
            seat, lambda: parse(give), "the subset contains the pattern"
        )

    @pytest.mark.parametrize(
        ("give", "want_at"), REFUSED, ids=[case_name("refuses", p) for p, _ in REFUSED]
    )
    def test_refuses_a_pattern_at_the_position_of_the_reference(
        self, seat: Collector, give: str, want_at: int
    ) -> None:
        """The refusal contains the position at which the reference refuses."""
        error = check.raises(
            seat, lambda: parse(give), "the parser refuses the pattern"
        )
        check.is_true(
            seat, isinstance(error, PatternError), "the error is a PatternError"
        )
        check.contains(
            seat,
            str(error),
            f" at {want_at}: ",
            "the text of the refusal contains the position of the reference",
        )

    def test_quotes_the_pattern_with_the_position_of_the_construct_that_it_refuses(
        self, seat: Collector
    ) -> None:
        """The text of a refusal quotes the pattern as JSON."""
        error = check.raises(seat, lambda: parse("(a)\\1"), "the parser refuses \\1")
        check.equal(
            seat,
            str(error),
            'pattern "(a)\\\\1" at 5: \\1 is not in the portable subset',
            "the text of the refusal quotes the pattern",
        )

    def test_writes_a_lone_surrogate_as_its_escape(self, seat: Collector) -> None:
        """The text of the refusal of a lone surrogate is valid UTF-8."""
        error = check.raises(seat, lambda: parse("a\ud800"), "the parser refuses it")
        check.equal(
            seat,
            str(error),
            'pattern "a\\ud800" at 1: a lone surrogate is not a character',
            "the text of the refusal has the escape of the surrogate",
        )

    def test_quotes_an_unexpected_character_as_json(self, seat: Collector) -> None:
        """A character after the end of the pattern is quoted."""
        error = check.raises(seat, lambda: parse("a)"), "the parser refuses )")
        check.equal(
            seat,
            str(error),
            'pattern "a)" at 1: ")" is not expected',
            "the text of the refusal quotes the character",
        )

    def test_returns_the_tree_of_a_pattern_with_its_anchors(
        self, seat: Collector
    ) -> None:
        """The pattern has a sequence, a repeated alternation and a counted repeat."""
        check.equal(
            seat,
            parse("^a(?:b|c)*d{2,3}$"),
            Pattern(
                Concat(
                    (
                        Literal("a"),
                        Repeat(Alternation((Literal("b"), Literal("c"))), 0, None),
                        Repeat(Literal("d"), 2, 3),
                    )
                ),
                start=True,
                end=True,
            ),
            "parse returns the tree of the pattern",
        )

    def test_returns_a_class_as_the_merged_ranges_of_its_code_points(
        self, seat: Collector
    ) -> None:
        """Overlapping ranges and a shorthand merge."""
        check.equal(
            seat,
            parse("[a-cb-e\\d]").node,
            Class(((0x30, 0x39), (0x61, 0x65))),
            "the class has the merged ranges",
        )

    def test_returns_a_negated_class_as_the_ranges_of_every_other_scalar_value(
        self, seat: Collector
    ) -> None:
        """A negated class leaves out the surrogates."""
        check.equal(
            seat,
            parse("[^b-y]").node,
            Class(((0, 0x61), (0x7A, 0xD7FF), (0xE000, 0x10FFFF))),
            "the class has the ranges outside b to y",
        )

    def test_returns_a_negated_class_of_a_range_that_starts_at_nul(
        self, seat: Collector
    ) -> None:
        """The complement starts after the range."""
        check.equal(
            seat,
            parse("[^\x00-a]").node,
            Class(((0x62, 0xD7FF), (0xE000, 0x10FFFF))),
            "the class has the ranges above a",
        )

    def test_returns_a_negated_class_of_a_member_that_is_the_last_code_point(
        self, seat: Collector
    ) -> None:
        """The complement ends before the last code point."""
        check.equal(
            seat,
            parse("[^a\U0010ffff]").node,
            Class(((0, 0x60), (0x62, 0xD7FF), (0xE000, 0x10FFFE))),
            "the class has the ranges without a and U+10FFFF",
        )


class TestPatternError:
    """PatternError is the refusal of a pattern."""

    def test_is_a_value_error(self, seat: Collector) -> None:
        """A caller that catches ValueError catches a refusal."""
        error = check.raises(seat, lambda: parse(")"), "the parser refuses it")
        check.error_as(seat, error, ValueError, "the refusal is a ValueError")
