"""The spec of _prop/engine/tokens.py tests the replay token.

The pinned bytes are the bytes of the reference implementation of the
definition.
"""

from __future__ import annotations

import base64
import math
import sys
from collections.abc import Sequence
from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.choice import INT64_MIN, UINT64_MAX, Choice, same_choice
from dokimi_assert._prop.engine.float import bits_of
from dokimi_assert._prop.engine.tokens import PREFIX, decode, encode
from dokimi_assert.seat import Collector

#: A choice of every kind and the bytes of their token. Each choice has a
#: tag, and LEB128 or the bits of a float follow it.
CHOICES = [
    Choice("integer", 0),
    Choice("integer", -1),
    Choice("integer", 127),
    Choice("integer", 128),
    Choice("integer", 300),
    Choice("float", 1.5),
    Choice("sequence", (1, 200)),
]
BYTES = (
    "0000" + "0101" + "007f" + "008001" + "00ac02" + "02000000000000f83f" + "030201c801"
)

#: The lowest finite float. Its bits are nearly all ones, so its token
#: contains the base64url character of 63.
LOWEST = Choice("float", -sys.float_info.max)


def token(hex: str) -> str:
    """Return the token of the bytes of a hex text."""
    text = base64.urlsafe_b64encode(bytes.fromhex(hex)).rstrip(b"=").decode("ascii")
    return PREFIX + text


def same(a: Sequence[Choice], b: Sequence[Choice]) -> bool:
    """Report whether two choice sequences are equal."""
    return len(a) == len(b) and all(
        same_choice(x, y) for x, y in zip(a, b, strict=True)
    )


class TestPrefix:
    """PREFIX is the start of every token of this version."""

    def test_contains_prop1(self, seat: Collector) -> None:
        """The prefix has the version."""
        check.equal(seat, PREFIX, "prop1:", "PREFIX is prop1:")


class TestEncode:
    """encode returns the token of a choice sequence."""

    def test_encodes_each_kind_as_a_tag_with_its_payload(self, seat: Collector) -> None:
        """The bytes are the pinned bytes."""
        check.equal(
            seat, encode(CHOICES), token(BYTES), "encode writes the pinned bytes"
        )

    def test_encodes_an_empty_sequence_to_the_prefix_alone(
        self, seat: Collector
    ) -> None:
        """An empty case has an empty payload."""
        check.equal(seat, encode([]), PREFIX, "the token is the prefix")

    def test_encodes_every_nan_with_the_canonical_bits(self, seat: Collector) -> None:
        """A NaN of another payload has the canonical bits."""
        got = encode([Choice("float", -math.nan)])
        check.equal(
            seat, got, token("02000000000000f87f"), "the token has the canonical NaN"
        )

    def test_writes_base64url_without_padding(self, seat: Collector) -> None:
        """The token has an underscore, and not a plus, a slash or an equals sign."""
        text = encode([LOWEST])
        check.equal(
            seat,
            ["_" in text, any(c in text for c in "+/=")],
            [True, False],
            "the token has the base64url characters",
        )


class TestDecode:
    """decode returns the choice sequence of a token."""

    def test_decodes_the_pinned_bytes_to_their_choices(self, seat: Collector) -> None:
        """The choices are the pinned choices."""
        check.is_true(
            seat,
            same(decode(token(BYTES)), CHOICES),
            "decode returns the pinned choices",
        )

    def test_decodes_the_token_of_every_choice_to_that_choice(
        self, seat: Collector
    ) -> None:
        """The decoder returns the extremes of each kind."""
        choices = [
            Choice("integer", INT64_MIN),
            Choice("integer", UINT64_MAX),
            Choice("float", -0.0),
            Choice("float", math.inf),
            Choice("float", math.nan),
            Choice("float", 5e-324),
            LOWEST,
            Choice("sequence", ()),
            Choice("sequence", (0, 1_112_063)),
        ]
        check.is_true(
            seat, same(decode(encode(choices)), choices), "decode returns the extremes"
        )

    def test_decodes_the_largest_number_from_ten_bytes(self, seat: Collector) -> None:
        """2^64 - 1 takes ten bytes."""
        [choice] = decode(token("00ffffffffffffffffff01"))
        check.equal(
            seat,
            (choice.kind, choice.value),
            ("integer", UINT64_MAX),
            "decode returns 2^64 - 1",
        )

    def test_decodes_the_most_negative_integer(self, seat: Collector) -> None:
        """The negative of 2^63 is the smallest signed integer."""
        [choice] = decode(token("0180808080808080808001"))
        check.equal(
            seat,
            (choice.kind, choice.value),
            ("integer", INT64_MIN),
            "decode returns -2^63",
        )

    def test_keeps_the_sign_of_negative_zero(self, seat: Collector) -> None:
        """The decoder returns the bits of -0.0."""
        [zero] = decode(encode([Choice("float", -0.0)]))
        bits = bits_of(zero.value) if isinstance(zero.value, float) else None
        check.equal(seat, bits, bits_of(-0.0), "the zero keeps its sign")

    def test_reads_an_element_at_or_above_2_to_the_32_as_2_to_the_32_less_1(
        self, seat: Collector
    ) -> None:
        """2^32 replays as 2^32 - 1."""
        [choice] = decode(token("03018080808010"))
        check.equal(seat, choice.value, (2**32 - 1,), "the element is 2^32 - 1")

    tests: ClassVar[list[tuple[str, str, str]]] = [
        (
            "raises value error for another version",
            "prop2:AAA",
            'prop: the token "prop2:AAA" does not start with prop1:',
        ),
        (
            "raises value error without a prefix",
            "AAA",
            'prop: the token "AAA" does not start with prop1:',
        ),
        (
            "raises value error for padding",
            f"{PREFIX}AAA=",
            'prop: the token "prop1:AAA=" is not unpadded base64url',
        ),
        (
            "raises value error for a lone character",
            f"{PREFIX}A",
            'prop: the token "prop1:A" is not unpadded base64url',
        ),
        (
            "raises value error for a character outside base64url",
            f"{PREFIX}AAA*",
            'prop: the token "prop1:AAA*" is not unpadded base64url',
        ),
        (
            "raises value error for a character outside ascii",
            f"{PREFIX}AAA" + chr(0xE9),
            'prop: the token "prop1:AAA\\u00e9" is not unpadded base64url',
        ),
        (
            "raises value error for trailing bits",
            f"{PREFIX}AAB",
            'prop: the token "prop1:AAB" is not unpadded base64url',
        ),
        (
            "raises value error for standard base64",
            encode([LOWEST]).replace("_", "/"),
            f'prop: the token "{encode([LOWEST]).replace("_", "/")}" is not unpadded '
            "base64url",
        ),
        (
            "raises value error for a superfluous leb128 byte",
            token("008000"),
            "prop: a token has a number with a superfluous byte",
        ),
        (
            "raises value error for a negative zero",
            token("0100"),
            "prop: a token has the negative of 0",
        ),
        (
            "raises value error for a negative integer below minus 2^63",
            token("0181808080808080808001"),
            f"prop: a token has the negative of {2**63 + 1}",
        ),
        (
            "raises value error for the number 2^64",
            token("0080808080808080808002"),
            "prop: a token has a number of 2^64 or more",
        ),
        (
            "raises value error for a number cut short",
            token("0080"),
            "prop: a token ends inside a choice",
        ),
        (
            "raises value error for a float cut short",
            token("020000"),
            "prop: a token ends inside a choice",
        ),
        (
            "raises value error for a sequence cut short",
            token("030201"),
            "prop: a token ends inside a choice",
        ),
        (
            "raises value error for a nan without the canonical bits",
            token("02010000000000f87f"),
            "prop: a token has a NaN without the canonical bits",
        ),
        (
            "raises value error for an unknown tag",
            token("04"),
            "prop: a token has the unknown tag 4",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for_a_token_that_encode_does_not_write(
        self, seat: Collector, give: str, want: str
    ) -> None:
        """The error has the reason."""
        error = check.raises(seat, lambda: decode(give), "decode raises")
        check.error_as(seat, error, ValueError, "the error is a ValueError")
        check.equal(seat, str(error), want, "the error has the reason")
