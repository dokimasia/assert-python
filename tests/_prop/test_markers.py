"""The spec of _prop/markers.py tests the constraints of prop for typing.Annotated."""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert._prop.markers import (
    AllowInfinity,
    AllowNan,
    Alphabet,
    Char,
    Pattern,
    Scale,
    Unit,
    Version,
    Width,
)
from dokimi_assert.seat import Collector


class TestWidth:
    """Width is the width of an int or a float in bits."""

    def test_is_signed_by_default(self, seat: Collector) -> None:
        """A width of 32 bits is signed by default."""
        width = Width(32)
        check.equal(
            seat, [width.bits, width.signed], [32, True], "the width is 32 and signed"
        )

    def test_equals_a_width_of_equal_fields(self, seat: Collector) -> None:
        """A marker is a frozen dataclass."""
        check.equal(
            seat, Width(8, signed=False), Width(8, False), "the two widths are equal"
        )


class TestPattern:
    """Pattern is the pattern that every value of a str matches."""

    def test_keeps_its_pattern(self, seat: Collector) -> None:
        """The marker keeps its regex."""
        check.equal(
            seat, Pattern("[a-z]+").regex, "[a-z]+", "the marker keeps the pattern"
        )


class TestAlphabet:
    """Alphabet has the characters of a str."""

    def test_keeps_its_characters(self, seat: Collector) -> None:
        """The marker keeps its characters."""
        check.equal(
            seat, Alphabet("abc").characters, "abc", "the marker keeps the characters"
        )


class TestAllowNan:
    """AllowNan lets a float be NaN."""

    def test_equals_every_other_allow_nan(self, seat: Collector) -> None:
        """The marker does not have a field."""
        check.equal(seat, AllowNan(), AllowNan(), "the two markers are equal")


class TestAllowInfinity:
    """AllowInfinity lets a float be infinite."""

    def test_equals_every_other_allow_infinity(self, seat: Collector) -> None:
        """The marker does not have a field."""
        check.equal(seat, AllowInfinity(), AllowInfinity(), "the two markers are equal")


class TestUnit:
    """Unit is the resolution of a datetime, a time or a timedelta."""

    def test_keeps_its_name(self, seat: Collector) -> None:
        """The marker keeps the name of the unit."""
        check.equal(seat, Unit("ms").name, "ms", "the marker keeps the name")


class TestScale:
    """Scale is the number of digits after the point of a Decimal."""

    def test_keeps_its_digits(self, seat: Collector) -> None:
        """The marker keeps the number of digits."""
        check.equal(seat, Scale(2).digits, 2, "the marker keeps 2 digits")


class TestVersion:
    """Version is the version of an IP address."""

    def test_keeps_its_number(self, seat: Collector) -> None:
        """The marker keeps the version number."""
        check.equal(seat, Version(4).number, 4, "the marker keeps version 4")


class TestChar:
    """Char limits a str to one code point."""

    def test_equals_every_other_char(self, seat: Collector) -> None:
        """The marker does not have a field."""
        check.equal(seat, Char(), Char(), "the two markers are equal")
