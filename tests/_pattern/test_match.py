"""The spec of _pattern/match.py tests the match of text against a pattern."""

from __future__ import annotations

import pytest

from dokimi_assert import check
from dokimi_assert._pattern.match import compile_pattern
from dokimi_assert._pattern.parse import PatternError
from dokimi_assert.seat import Collector

tests: list[tuple[str, str, str, bool]] = [
    (
        "returns an expression that finds a match inside the text",
        "[0-9a-f]{8}",
        "id=deadbeef",
        True,
    ),
    (
        "returns an expression that reads ^ at the start of the text",
        "^[0-9a-f]+$",
        "id=deadbeef",
        False,
    ),
    (
        "returns an expression that matches the whole text between the two anchors",
        "^abc$",
        "abc",
        True,
    ),
    (
        "returns an expression that reads $ at the end of the text alone",
        "^abc$",
        "abc\n",
        False,
    ),
    (
        "returns an expression that reads an escaped $ at the end as a dollar",
        "a\\$",
        "a$",
        True,
    ),
    (
        "returns an expression whose \\d leaves out the digits beyond ASCII",
        "\\d",
        "\N{ARABIC-INDIC DIGIT THREE}",
        False,
    ),
    (
        "returns an expression whose \\w leaves out the letters beyond ASCII",
        "\\w",
        "\N{LATIN SMALL LETTER E WITH ACUTE}",
        False,
    ),
    (
        "returns an expression whose \\s leaves out the vertical tab",
        "\\s",
        "\x0b",
        False,
    ),
    (
        "returns an expression whose \\s leaves out U+00A0",
        "\\s",
        "\N{NO-BREAK SPACE}",
        False,
    ),
    ("returns an expression whose \\s contains the form feed", "\\s", "\f", True),
    (
        "returns an expression whose \\s in a class contains the carriage return",
        "[\\s]",
        "\r",
        True,
    ),
    ("returns an expression whose dot leaves out U+0085", "a.b", "a\x85b", False),
    (
        "returns an expression whose dot leaves out U+2028",
        "a.b",
        "a\N{LINE SEPARATOR}b",
        False,
    ),
    (
        "returns an expression whose dot leaves out U+2029",
        "a.b",
        "a\N{PARAGRAPH SEPARATOR}b",
        False,
    ),
    (
        "returns an expression whose dot leaves out the carriage return",
        "a.b",
        "a\rb",
        False,
    ),
    (
        "returns an expression whose dot matches a character beyond the BMP",
        "^.$",
        "\N{GRINNING FACE}",
        True,
    ),
    (
        "returns an expression whose dot in a class is a dot",
        "^[.]$",
        "a",
        False,
    ),
    (
        "returns an expression whose negated class contains the line feed",
        "^[^a]$",
        "\n",
        True,
    ),
    (
        "returns an expression whose escaped dot leaves out other characters",
        "\\.",
        "a",
        False,
    ),
    ("returns an expression whose escaped dot matches a dot", "\\.", ".", True),
    (
        "returns an expression that repeats a group of alternatives",
        "^(?:ab|c)+$",
        "abcab",
        True,
    ),
    ("returns an expression that reads {2} as exactly two", "^x{2}$", "xxx", False),
    (
        "returns an expression of the empty pattern that matches any text",
        "",
        "anything",
        True,
    ),
]


class TestCompilePattern:
    """compile_pattern returns an expression that reads a pattern as the subset does."""

    @pytest.mark.parametrize(
        ("give_pattern", "give_text", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_reads_the_pattern_as_the_subset_reads_it(
        self, seat: Collector, give_pattern: str, give_text: str, want: bool
    ) -> None:
        """The expression finds a match where the subset finds one."""
        found = compile_pattern(give_pattern).search(give_text) is not None
        check.equal(
            seat, found, want, "the expression finds a match where the subset does"
        )

    def test_raises_a_pattern_error_for_a_pattern_outside_the_subset(
        self, seat: Collector
    ) -> None:
        """A lookahead is outside the subset."""
        error = check.raises(
            seat,
            lambda: compile_pattern("a(?=b)"),
            "compile_pattern refuses the pattern",
        )
        check.is_true(
            seat, isinstance(error, PatternError), "the error is a PatternError"
        )
