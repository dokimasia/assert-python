# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/bridge.py tests the decoding of fuzzer bytes into a case."""

from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING, cast

from dokimi_assert import check
from dokimi_assert._prop.engine.bridge import Bridging
from dokimi_assert._prop.engine.case import Request
from dokimi_assert._prop.engine.choice import (
    Bounds,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    Value,
)
from helpers import no_draw

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


def values(data: bytes, *bounds: Bounds) -> list[Value]:
    """Return the value of the bytes under each of the bounds in order."""
    bridge = Bridging(data)
    return [
        bridge.value(Request(one, no_draw), index) for index, one in enumerate(bounds)
    ]


class TestBridgingValue:
    """Bridging.value returns the value of the next bytes."""

    def test_reads_an_integer_as_a_little_endian_offset_from_the_lower_bound(
        self, seat: Collector
    ) -> None:
        """0x012c is 300."""
        check.equal(
            seat,
            values(bytes([0x2C, 0x01]), IntegerBounds(0, 1000)),
            [300],
            "0x012c is 300",
        )

    def test_wraps_an_offset_past_the_span_of_the_bounds(self, seat: Collector) -> None:
        """12 mod 11 is 1, so the value is -5 + 1."""
        check.equal(
            seat,
            values(bytes([12]), IntegerBounds(-5, 5)),
            [-4],
            "12 mod 11 is 1, so the value is -5 + 1",
        )

    def test_does_not_read_a_byte_for_integer_bounds_of_one_value(
        self, seat: Collector
    ) -> None:
        """The second integer reads the byte."""
        check.equal(
            seat,
            values(bytes([9]), IntegerBounds(7, 7), IntegerBounds(0, 255)),
            [7, 9],
            "the second integer reads the byte",
        )

    def test_takes_the_target_of_an_integer_whose_bytes_run_out(
        self, seat: Collector
    ) -> None:
        """Three bytes are needed and one remains."""
        check.equal(
            seat,
            values(bytes([1]), IntegerBounds(1, 70_000)),
            [1],
            "three bytes are needed and one remains",
        )

    def test_takes_the_target_of_every_value_after_the_bytes_run_out(
        self, seat: Collector
    ) -> None:
        """The first integer spends the byte that remains."""
        check.equal(
            seat,
            values(bytes([1]), IntegerBounds(1, 70_000), IntegerBounds(0, 255)),
            [1, 0],
            "the first integer spends the byte that remains",
        )

    def test_reads_a_float_of_width_64_from_8_bytes(self, seat: Collector) -> None:
        """The bytes are the float 0.5."""
        check.equal(
            seat,
            values(struct.pack("<d", 0.5), FloatBounds(0.0, 1.0)),
            [0.5],
            "the value is 0.5",
        )

    def test_reads_a_float_of_width_32_from_4_bytes(self, seat: Collector) -> None:
        """The bytes are the float 0.25."""
        check.equal(
            seat,
            values(struct.pack("<f", 0.25), FloatBounds(0.0, 1.0, False, 32)),
            [0.25],
            "the value is 0.25",
        )

    def test_takes_the_target_for_a_float_that_the_bounds_do_not_admit(
        self, seat: Collector
    ) -> None:
        """5 is outside [0, 1]."""
        check.equal(
            seat,
            values(struct.pack("<d", 5.0), FloatBounds(0.0, 1.0)),
            [0.0],
            "5 is outside [0, 1]",
        )

    def test_does_not_read_a_byte_for_float_bounds_of_one_nonzero_value(
        self, seat: Collector
    ) -> None:
        """The integer reads the byte."""
        check.equal(
            seat,
            values(bytes([3]), FloatBounds(2.0, 2.0), IntegerBounds(0, 255)),
            [2.0, 3],
            "the integer reads the byte",
        )

    def test_reads_negative_zero_from_the_bytes_for_float_bounds_of_zero_alone(
        self, seat: Collector
    ) -> None:
        """The float is -0."""
        decoded = values(struct.pack("<d", -0.0), FloatBounds(0.0, 0.0))[0]
        check.equal(
            seat, math.copysign(1.0, cast("float", decoded)), -1.0, "the float is -0"
        )

    def test_takes_the_target_of_a_float_whose_bytes_run_out(
        self, seat: Collector
    ) -> None:
        """8 bytes are needed and 2 remain."""
        check.equal(
            seat,
            values(bytes([1, 2]), FloatBounds(0.0, 1.0)),
            [0.0],
            "8 bytes are needed and 2 remain",
        )

    def test_reads_the_length_of_a_sequence_before_its_elements(
        self, seat: Collector
    ) -> None:
        """The length byte is 2."""
        check.equal(
            seat,
            values(bytes([2, 5, 6, 7]), SequenceBounds(256, 0, 4)),
            [(5, 6)],
            "the sequence has two elements",
        )

    def test_reads_the_length_of_a_sequence_without_a_maximum_from_two_bytes(
        self, seat: Collector
    ) -> None:
        """The two length bytes are 1 and 0."""
        check.equal(
            seat,
            values(bytes([1, 0, 9]), SequenceBounds(256, 0, None)),
            [(9,)],
            "the sequence has one element",
        )

    def test_extends_a_sequence_whose_elements_run_out_with_zeros_to_its_minimum(
        self, seat: Collector
    ) -> None:
        """The bytes have one element."""
        check.equal(
            seat,
            values(bytes([2, 4]), SequenceBounds(256, 3, 6)),
            [(4, 0, 0)],
            "zeros extend the sequence to its minimum",
        )

    def test_takes_the_target_of_a_sequence_without_bytes_for_its_length(
        self, seat: Collector
    ) -> None:
        """The target has two zeros."""
        check.equal(
            seat,
            values(b"", SequenceBounds(256, 2, 4)),
            [(0, 0)],
            "the sequence is the target",
        )
