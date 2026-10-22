# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/history/specs.py tests the named specs of the definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.spec import CallOperation
from dokimi_assert.conformance.history.specs import SPECS
from helpers import refusal

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


def done(name: str, *args: Any, output: Any = None) -> CallOperation:
    """Return the operation of a call that completed as ok with output."""
    return CallOperation(name, args, True, output)


def open_call(name: str, *args: Any) -> CallOperation:
    """Return the operation of a call whose outcome is unknown."""
    return CallOperation(name, args, False)


class TestSpecs:
    """SPECS has the named specs of the definition."""

    def test_contains_the_named_specs(self, seat: Collector) -> None:
        """The names are those of the definition."""
        check.equal(
            seat,
            sorted(SPECS),
            ["cas-register", "key-value", "lossy-register", "queue", "register", "set"],
            "the table has the named specs",
        )

    initial: ClassVar[list[tuple[str, Any]]] = [
        ("register", None),
        ("cas-register", None),
        ("lossy-register", None),
        ("key-value", {}),
        ("queue", ()),
        ("set", ()),
    ]

    @pytest.mark.parametrize(("give", "want"), initial, ids=[t[0] for t in initial])
    def test_starts_each_spec_in_its_empty_state(
        self, seat: Collector, give: str, want: Any
    ) -> None:
        """The register is null, and every collection is empty."""
        check.equal(seat, SPECS[give].initial(), want, "the spec starts empty")

    steps: ClassVar[list[tuple[str, str, Any, CallOperation, list[Any]]]] = [
        ("a write stores its value", "register", None, done("write", 1), [1]),
        ("a read of the state keeps it", "register", 1, done("read", output=1), [1]),
        ("a read of another value fails", "register", 1, done("read", output=2), []),
        ("an unknown read keeps the state", "register", 1, open_call("read"), [1]),
        (
            "a cas of the state stores its value",
            "cas-register",
            1,
            done("cas", 1, 2, output=True),
            [2],
        ),
        (
            "a cas of another value keeps the state",
            "cas-register",
            1,
            done("cas", 3, 2, output=False),
            [1],
        ),
        (
            "a cas that returns a wrong verdict fails",
            "cas-register",
            1,
            done("cas", 1, 2, output=False),
            [],
        ),
        (
            "an unknown cas takes effect when it matches",
            "cas-register",
            1,
            open_call("cas", 1, 2),
            [2],
        ),
        (
            "a write of the cas register stores its value",
            "cas-register",
            1,
            done("write", 5),
            [5],
        ),
        (
            "a read of the cas register returns the state",
            "cas-register",
            1,
            done("read", output=1),
            [1],
        ),
        (
            "a write of the lossy register leaves the new or the old value",
            "lossy-register",
            1,
            done("write", 2),
            [2, 1],
        ),
        (
            "a read of the lossy register returns the state",
            "lossy-register",
            2,
            done("read", output=2),
            [2],
        ),
        (
            "a put stores a value under a key",
            "key-value",
            {},
            done("put", "k", "v"),
            [{"k": "v"}],
        ),
        (
            "a put of the empty value removes the key",
            "key-value",
            {"k": "v", "j": "w"},
            done("put", "k", ""),
            [{"j": "w"}],
        ),
        (
            "a put of an empty value of a new key keeps the state",
            "key-value",
            {},
            done("put", "k", ""),
            [{}],
        ),
        (
            "a put of a stored key keeps its place",
            "key-value",
            {"k": "v", "j": "w"},
            done("put", "k", "x"),
            [{"k": "x", "j": "w"}],
        ),
        (
            "an append extends the value of a key",
            "key-value",
            {"k": "a"},
            done("append", "k", "b"),
            [{"k": "ab"}],
        ),
        (
            "a get of the value keeps the state",
            "key-value",
            {"k": "a"},
            done("get", "k", output="a"),
            [{"k": "a"}],
        ),
        (
            "a get of a missing key returns the empty value",
            "key-value",
            {},
            done("get", "k", output=""),
            [{}],
        ),
        (
            "a get of another value fails",
            "key-value",
            {"k": "a"},
            done("get", "k", output="b"),
            [],
        ),
        (
            "an unknown get keeps the state",
            "key-value",
            {"k": "a"},
            open_call("get", "k"),
            [{"k": "a"}],
        ),
        (
            "an enqueue adds a value at the tail",
            "queue",
            (1,),
            done("enqueue", 2),
            [(1, 2)],
        ),
        (
            "a dequeue returns the head",
            "queue",
            (1, 2),
            done("dequeue", output=1),
            [(2,)],
        ),
        (
            "a dequeue of another value fails",
            "queue",
            (1, 2),
            done("dequeue", output=2),
            [],
        ),
        (
            "a dequeue of an empty queue returns null",
            "queue",
            (),
            done("dequeue", output=None),
            [()],
        ),
        (
            "a dequeue of an empty queue that returns a value fails",
            "queue",
            (),
            done("dequeue", output=1),
            [],
        ),
        (
            "an unknown dequeue of an empty queue keeps it",
            "queue",
            (),
            open_call("dequeue"),
            [()],
        ),
        (
            "an unknown dequeue removes the head",
            "queue",
            (1,),
            open_call("dequeue"),
            [()],
        ),
        ("an add of a new value appends it", "set", (1,), done("add", 2), [(1, 2)]),
        (
            "an add of a present value keeps the set",
            "set",
            (1,),
            done("add", 1),
            [(1,)],
        ),
        (
            "a contains of a present value returns true",
            "set",
            (1,),
            done("contains", 1, output=True),
            [(1,)],
        ),
        (
            "a contains that returns a wrong verdict fails",
            "set",
            (1,),
            done("contains", 1, output=False),
            [],
        ),
        (
            "an unknown contains keeps the set",
            "set",
            (1,),
            open_call("contains", 2),
            [(1,)],
        ),
        (
            "a remove of a present value removes it",
            "set",
            (1, 2),
            done("remove", 1, output=True),
            [(2,)],
        ),
        (
            "a remove that returns a wrong verdict fails",
            "set",
            (1,),
            done("remove", 2, output=True),
            [],
        ),
        (
            "an unknown remove removes a present value",
            "set",
            (1, 2),
            open_call("remove", 2),
            [(1,)],
        ),
    ]

    @pytest.mark.parametrize(
        ("give_spec", "give_state", "give", "want"),
        [t[1:] for t in steps],
        ids=[t[0] for t in steps],
    )
    def test_steps_each_operation_of_a_spec(
        self,
        seat: Collector,
        give_spec: str,
        give_state: Any,
        give: CallOperation,
        want: list[Any],
    ) -> None:
        """Each operation leaves the states of its spec."""
        check.equal(
            seat,
            SPECS[give_spec].next(give_state, give),
            want,
            "the operation leaves the states of its spec",
        )

    undefined: ClassVar[list[tuple[str, Any]]] = [
        ("register", None),
        ("cas-register", None),
        ("lossy-register", None),
        ("key-value", {}),
        ("queue", ()),
        ("set", ()),
    ]

    @pytest.mark.parametrize(
        ("give", "give_state"), undefined, ids=[t[0] for t in undefined]
    )
    def test_raises_for_an_operation_that_a_spec_does_not_define(
        self, seat: Collector, give: str, give_state: Any
    ) -> None:
        """The check reports the error as a fault."""
        check.equal(
            seat,
            refusal(seat, lambda: SPECS[give].next(give_state, done("widget"))),
            f'conformance: the {give} spec does not have the operation "widget"',
            "the spec refuses the operation",
        )

    def test_compares_two_key_value_states_in_any_order(self, seat: Collector) -> None:
        """Two maps of equal entries are one state."""
        spec = SPECS["key-value"]
        check.equal(
            seat,
            (
                spec.equal({"a": "1", "b": "2"}, {"b": "2", "a": "1"}),
                spec.key({"a": "1"}),
            ),
            (True, spec.key({"a": "1"})),
            "the order of the keys does not change a state",
        )

    def test_compares_two_sets_in_any_order(self, seat: Collector) -> None:
        """Two sets of equal values are one state."""
        spec = SPECS["set"]
        check.is_true(
            seat, spec.equal((1, 2), (2, 1)), "the order does not change a set"
        )

    def test_compares_two_queues_in_order(self, seat: Collector) -> None:
        """A queue is a sequence."""
        spec = SPECS["queue"]
        check.is_false(seat, spec.equal((1, 2), (2, 1)), "the order changes a queue")
