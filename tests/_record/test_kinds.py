# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _record/kinds.py tests the records of other kinds of a test."""

from __future__ import annotations

import types

from dokimi_assert import check
from dokimi_assert._record.kinds import CALL_KIND, append, attach
from dokimi_assert.seat import Collector, Recorder


class TestCallKind:
    """CALL_KIND is the kind of the call records of this library."""

    def test_is_dokimi_assert(self, seat: Collector) -> None:
        """The call records have the kind dokimi.assert."""
        check.equal(seat, CALL_KIND, "dokimi.assert", "the kind of the call records")


class TestAttach:
    """attach makes append add the records of a seat to the properties of a test."""

    def test_makes_append_add_each_record_of_the_seat_to_the_properties(
        self, seat: Collector
    ) -> None:
        """The properties receive the record under its name."""
        tool = Collector()
        properties: list[tuple[str, object]] = []
        attach(tool, properties)
        append(tool, "dokimi.suite", '{"seed": "7"}')
        check.equal(
            seat,
            properties,
            [("dokimi.suite.1", '{"seed": "7"}')],
            "the properties have the record",
        )


class TestAppend:
    """append adds a record to the user properties of the test of a seat."""

    def test_numbers_the_records_of_each_kind_of_a_test_from_1(
        self, seat: Collector
    ) -> None:
        """Each kind counts its own records."""
        tool = Collector()
        properties: list[tuple[str, object]] = []
        attach(tool, properties)
        append(tool, "dokimi.suite", '{"a": 1}')
        append(tool, "dokimi.trace", '{"b": 2}')
        append(tool, "dokimi.suite", '{"c": 3}')
        check.equal(
            seat,
            properties,
            [
                ("dokimi.suite.1", '{"a": 1}'),
                ("dokimi.trace.1", '{"b": 2}'),
                ("dokimi.suite.2", '{"c": 3}'),
            ],
            "each kind counts its records from 1",
        )

    def test_numbers_the_records_of_each_test_on_its_own(self, seat: Collector) -> None:
        """The first record of each test is number 1."""
        first, second = Collector(), Collector()
        first_properties: list[tuple[str, object]] = []
        second_properties: list[tuple[str, object]] = []
        attach(first, first_properties)
        attach(second, second_properties)
        append(first, "dokimi.suite", "{}")
        append(second, "dokimi.suite", "{}")
        check.equal(
            seat,
            [first_properties, second_properties],
            [[("dokimi.suite.1", "{}")], [("dokimi.suite.1", "{}")]],
            "each test numbers its records from 1",
        )

    def test_does_not_write_for_a_seat_without_a_test(self, seat: Collector) -> None:
        """A recorder does not write into the properties of another test."""
        tool = Collector()
        properties: list[tuple[str, object]] = []
        attach(tool, properties)
        append(Recorder(), "dokimi.suite", "{}")
        check.is_empty(seat, properties, "the test has no record of the recorder")

    def test_does_not_raise_for_a_seat_that_is_not_hashable(
        self, seat: Collector
    ) -> None:
        """A seat that cannot be a key does not have a test."""
        check.does_not_raise(
            seat,
            lambda: append(types.SimpleNamespace(), "dokimi.suite", "{}"),
            "append returns for an unhashable seat",
        )
