"""The spec of _prop/identity.py tests the identity of the failure of a property."""

from __future__ import annotations

from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.identity import (
    Identity,
    entry_of,
    from_key,
    key_of,
    of_error,
    of_record,
    text_of,
)
from dokimi_assert.failure import Failure, Where
from dokimi_assert.seat import Collector

#: A location of a failure.
WHERE = Where("/work/tests/test_order.py", 12)

#: The location of an exception without a frame of the caller.
FALLBACK = Where("/work/tests/test_call.py", 3)


def broken() -> None:
    """Raise TypeError, as the code under test of a body does."""
    raise TypeError("bad")


class TestOfRecord:
    """of_record returns the identity of a failure record."""

    def test_identifies_the_record_of_an_assertion_without_its_contract(
        self, seat: Collector
    ) -> None:
        """The identity does not have a contract."""
        check.equal(
            seat,
            of_record(Failure("equal", "the total", {}, WHERE)),
            Identity("equal", None, None, WHERE),
            "the identity does not have a contract",
        )

    def test_identifies_a_record_without_a_location_by_its_contract(
        self, seat: Collector
    ) -> None:
        """The identity has the contract."""
        check.equal(
            seat,
            of_record(Failure("equal", "the total", {})),
            Identity("equal", "the total", None, None),
            "the identity has the contract",
        )

    def test_returns_only_the_location_of_a_message(self, seat: Collector) -> None:
        """A message is not part of an identity."""
        check.equal(
            seat,
            of_record(Failure("", "it broke", {}, WHERE)),
            Identity(None, None, None, WHERE),
            "a message is not part of an identity",
        )


class TestOfError:
    """of_error returns the identity of an exception that the body raised."""

    def test_identifies_an_exception_by_its_class_at_the_frame_that_raised_it(
        self, seat: Collector
    ) -> None:
        """The identity has the frame of broken in this file."""
        with pytest.raises(TypeError) as caught:
            broken()
        check.equal(
            seat,
            of_error(caught.value, FALLBACK),
            Identity(
                error="TypeError",
                where=Where(__file__, broken.__code__.co_firstlineno + 2),
            ),
            "the identity has the class and the frame",
        )

    def test_returns_the_fallback_for_an_exception_without_a_frame_of_the_caller(
        self, seat: Collector
    ) -> None:
        """An exception that was never raised does not have a traceback."""
        check.equal(
            seat,
            of_error(ValueError("bad"), FALLBACK),
            Identity(error="ValueError", where=FALLBACK),
            "the identity has the fallback",
        )


class TestKeyOf:
    """key_of returns the text of an identity."""

    def test_returns_one_text_for_two_equal_identities(self, seat: Collector) -> None:
        """Equal identities share a text."""
        a = Identity("equal", where=Where(WHERE.file, WHERE.line))
        b = Identity("equal", where=Where(WHERE.file, WHERE.line))
        check.equal(seat, key_of(a), key_of(b), "equal identities share a text")

    def test_returns_two_texts_for_identities_of_two_lines(
        self, seat: Collector
    ) -> None:
        """The line is part of the identity."""
        a = Identity("equal", where=WHERE)
        b = Identity("equal", where=Where(WHERE.file, 13))
        check.not_equal(seat, key_of(a), key_of(b), "the line is part of the identity")


class TestFromKey:
    """from_key returns the identity of a text of key_of."""

    tests: ClassVar[list[tuple[str, Identity]]] = [
        (
            "returns the identity of an exception",
            Identity(None, None, "TypeError", WHERE),
        ),
        (
            "returns the identity of a record without a location",
            Identity("equal", "c", None, None),
        ),
    ]

    @pytest.mark.parametrize(
        "identity", [t[1] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_identity_of_its_text(
        self, seat: Collector, identity: Identity
    ) -> None:
        """from_key returns the original identity."""
        check.equal(
            seat,
            from_key(key_of(identity)),
            identity,
            "from_key returns the original identity",
        )


class TestTextOf:
    """text_of returns the text of an identity in a sentence."""

    tests: ClassVar[list[tuple[str, Identity, str]]] = [
        (
            "returns the text of a raised exception",
            Identity(error="TypeError", where=WHERE),
            "a TypeError raised at test_order.py:12",
        ),
        (
            "returns the text of a message",
            Identity(where=WHERE),
            "a message at test_order.py:12",
        ),
        (
            "returns the text of the record of an assertion",
            Identity("equal", where=WHERE),
            "equal at test_order.py:12",
        ),
        (
            "returns the text of a record without a location",
            Identity("equal", "c"),
            'equal of "c"',
        ),
        (
            "returns the assertion alone for a record without a location or a contract",
            Identity("equal", ""),
            "equal",
        ),
        ("returns the text of a message without a location", Identity(), "a message"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_text(self, seat: Collector, give: Identity, want: str) -> None:
        """Each identity has its text."""
        check.equal(seat, text_of(give), want, "text_of returns the text")


class TestEntryOf:
    """entry_of returns the identity in the form of a store entry."""

    tests: ClassVar[list[tuple[str, Identity, dict[str, str | int]]]] = [
        (
            "returns the identity of the record of an assertion",
            Identity("equal", where=WHERE),
            {"assertion": "equal", "file": "test_order.py", "line": 12},
        ),
        (
            "returns the identity of a record without a location",
            Identity("equal", "c"),
            {"assertion": "equal", "contract": "c"},
        ),
        (
            "returns the identity of a raised exception",
            Identity(error="TypeError", where=WHERE),
            {"error": "TypeError", "file": "test_order.py", "line": 12},
        ),
        (
            "returns the identity of a message",
            Identity(where=WHERE),
            {"file": "test_order.py", "line": 12},
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_identity_of_the_entry(
        self, seat: Collector, give: Identity, want: dict[str, str | int]
    ) -> None:
        """The entry has the base name of the file and the line."""
        check.equal(
            seat,
            entry_of(give),
            want,
            "the entry has the base name of the file and the line",
        )
