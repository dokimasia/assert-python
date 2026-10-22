# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/source.py tests the random source.

The stream matches the output of the C code that Bob Jenkins published in
every bit. testdata/smallprng.json contains the outputs of that code for
five seeds.
"""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.source import MASK, Source, case_source, mix, utf8
from helpers import refusal

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The outputs of the published C code.
ORACLE: dict[str, Any] = json.loads(
    (pathlib.Path(__file__).parent / "testdata" / "smallprng.json").read_text(
        encoding="utf-8"
    )
)

#: The seed of the contract "decoding undoes encoding". A change of the fold
#: fails here.
CONTRACT_SEED = 14_330_315_428_228_886_101


class TestMask:
    """MASK is the largest unsigned 64-bit integer."""

    def test_contains_2_to_the_64_less_1(self, seat: Collector) -> None:
        """Every value of the stream is at most the mask."""
        check.equal(seat, MASK, 2**64 - 1, "MASK is 2^64 - 1")


class TestSource:
    """Source is the stream of one seed."""

    tests: ClassVar[list[tuple[str, int]]] = [
        ("raises value error for a negative seed", -1),
        ("raises value error for a seed of 2^64", MASK + 1),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_raises_value_error_for_a_seed_outside_64_bits(
        self, seat: Collector, give: int
    ) -> None:
        """A seed is an unsigned 64-bit integer."""
        want = f"prop: seed {give} is not an unsigned 64-bit integer"
        check.equal(
            seat, refusal(seat, lambda: Source(give)), want, "the error has the seed"
        )


class TestSourceNext:
    """Source.next returns the next value of the stream."""

    def test_returns_the_outputs_of_the_published_c_code_for_five_seeds(
        self, seat: Collector
    ) -> None:
        """Each seed gives the 32 outputs of the C code."""
        outputs: dict[str, list[str]] = ORACLE["outputs"]
        got: dict[str, list[str]] = {}
        for seed, expected in outputs.items():
            source = Source(int(seed))
            got[seed] = [str(source.next()) for _ in expected]
        check.equal(seat, got, outputs, "the stream has the 32 outputs of each seed")


class TestSourceBelow:
    """Source.below returns a uniform value below n."""

    def test_returns_0_for_one_value_without_consuming_the_stream(
        self, seat: Collector
    ) -> None:
        """The stream does not change."""
        source, twin = Source(7), Source(7)
        check.equal(
            seat,
            [source.below(1), source.next()],
            [0, twin.next()],
            "below does not consume the stream",
        )

    def test_draws_below_n_from_the_top_bits_of_each_output_by_rejection(
        self, seat: Collector
    ) -> None:
        """Each attempt keeps the top bits, and a value of n or more repeats."""
        ns = [2, 3, 10, 1000, (1 << 63) + 5]
        got: list[list[int]] = []
        want: list[list[int]] = []
        for n in ns:
            source, twin = Source(n), Source(n)
            got.append([source.below(n) for _ in range(200)])
            shift = 64 - (n - 1).bit_length()
            drawn: list[int] = []
            for _ in range(200):
                value = twin.next() >> shift
                while value >= n:
                    value = twin.next() >> shift
                drawn.append(value)
            want.append(drawn)
        check.equal(seat, got, want, "below draws by rejection for each n")

    def test_returns_whole_outputs_for_2_to_the_64_values(
        self, seat: Collector
    ) -> None:
        """The draw keeps every bit."""
        source, twin = Source(3), Source(3)
        check.equal(
            seat,
            [source.below(MASK + 1) for _ in range(10)],
            [twin.next() for _ in range(10)],
            "below returns the outputs themselves",
        )

    tests: ClassVar[list[tuple[str, int]]] = [
        ("raises value error for zero values", 0),
        ("raises value error for more than 2^64 values", MASK + 2),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_raises_value_error_for_a_number_of_values_outside_its_range(
        self, seat: Collector, give: int
    ) -> None:
        """The number of values is from 1 to 2^64."""
        want = f"prop: below({give}) needs 1 <= n <= 2^64"
        check.equal(
            seat,
            refusal(seat, lambda: Source(1).below(give)),
            want,
            "the error has the call",
        )


class TestSourceCoin:
    """Source.coin returns a coin of the probability num/den."""

    def test_compares_one_draw_of_below_den_with_num(self, seat: Collector) -> None:
        """A coin of 3 in 8 is a draw below 8 that is below 3."""
        source, twin = Source(9), Source(9)
        check.equal(
            seat,
            [source.coin(3, 8) for _ in range(100)],
            [twin.below(8) < 3 for _ in range(100)],
            "each coin is a draw below 8 that is below 3",
        )

    tests: ClassVar[list[tuple[str, int, int]]] = [
        ("raises value error for a denominator of 0", 1, 0),
        ("raises value error for a negative numerator", -1, 2),
        ("raises value error for a numerator above the denominator", 3, 2),
    ]

    @pytest.mark.parametrize(
        ("num", "den"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for_a_probability_outside_its_range(
        self, seat: Collector, num: int, den: int
    ) -> None:
        """The probability is from 0 to 1."""
        want = f"prop: coin({num}, {den}) needs 0 <= num <= den"
        check.equal(
            seat,
            refusal(seat, lambda: Source(1).coin(num, den)),
            want,
            "the error has the call",
        )


class TestCaseSource:
    """case_source returns the source of one case of a run."""

    def test_returns_the_stream_of_the_seed_plus_the_index(
        self, seat: Collector
    ) -> None:
        """Case 2 of seed 40 is seed 42."""
        check.equal(
            seat,
            case_source(40, 2).next(),
            Source(42).next(),
            "the case has the stream of seed 42",
        )

    def test_wraps_the_seed_of_a_case_at_2_to_the_64(self, seat: Collector) -> None:
        """Case 1 of the last seed is seed 0."""
        check.equal(
            seat,
            case_source(MASK, 1).next(),
            Source(0).next(),
            "the case has the stream of seed 0",
        )


class TestMix:
    """mix folds bytes into one 64-bit value."""

    def test_returns_0_for_empty_bytes(self, seat: Collector) -> None:
        """The fold starts at 0."""
        check.equal(seat, mix(b""), 0, "the fold of empty bytes is 0")

    def test_folds_each_byte_through_the_first_output_of_a_stream(
        self, seat: Collector
    ) -> None:
        """Two bytes are two folds."""
        first = Source(ord("a")).next()
        check.equal(
            seat,
            mix(b"ab"),
            Source(first ^ ord("b")).next(),
            "the value is two folds",
        )

    def test_returns_the_pinned_seed_of_a_contract(self, seat: Collector) -> None:
        """The seed of a contract is the fold of its text."""
        check.equal(
            seat,
            mix(b"decoding undoes encoding"),
            CONTRACT_SEED,
            "mix returns the pinned seed",
        )


class TestUtf8:
    """utf8 returns the bytes of a text that mix folds."""

    def test_returns_the_utf8_bytes_of_a_text(self, seat: Collector) -> None:
        """A text without a lone surrogate has its UTF-8 bytes."""
        check.equal(
            seat, utf8("a" + chr(0xE9)), b"a\xc3\xa9", "utf8 returns the UTF-8 bytes"
        )

    def test_replaces_a_lone_surrogate_with_the_bytes_of_u_fffd(
        self, seat: Collector
    ) -> None:
        """The replacement character takes the place of the surrogate."""
        check.equal(
            seat,
            utf8("a" + chr(0xD800) + "b"),
            b"a\xef\xbf\xbdb",
            "the bytes of U+FFFD replace the surrogate",
        )
