"""The spec of failure.py: the failure record, its sentence and its call site.

The record is the verdict of every other spec, so this spec states its
verdicts with pytest's assert.
"""

from __future__ import annotations

import _thread
import inspect
import os
import threading
import weakref
from typing import Any

import pytest

from dokimi_assert.failure import (
    Failure,
    Where,
    call_site,
    register_sentence,
    render,
    site_in,
)


class TestFailure:
    """Failure, the record that a failing assertion reports."""

    def test_accepts_a_weak_reference(self) -> None:
        """A module can keep data beside a live record."""
        failure = Failure("equal", "c")
        assert weakref.ref(failure)() is failure


class TestFailureWant:
    """Failure.want, the field want of the detail."""

    def test_returns_the_field_want_of_the_detail(self) -> None:
        """The property returns the wanted value."""
        assert Failure("equal", "c", {"want": 2, "got": 1}).want == 2

    def test_returns_none_for_a_declared_want_whose_value_is_none(self) -> None:
        """A declared field can contain None."""
        assert Failure("equal", "c", {"want": None, "got": None}).want is None

    def test_raises_key_error_for_an_undeclared_want(self) -> None:
        """The property raises KeyError when the assertion declares no want."""
        with pytest.raises(KeyError):
            _ = Failure("not-equal", "c", {"got": 1}).want


class TestFailureGot:
    """Failure.got, the field got of the detail."""

    def test_returns_the_field_got_of_the_detail(self) -> None:
        """The property returns the value that the assertion received."""
        assert Failure("equal", "c", {"want": 2, "got": 1}).got == 1

    def test_returns_none_for_a_declared_got_whose_value_is_none(self) -> None:
        """A declared field can contain None."""
        assert Failure("equal", "c", {"want": None, "got": None}).got is None

    def test_raises_key_error_for_an_undeclared_got(self) -> None:
        """The property raises KeyError when the assertion declares no got."""
        with pytest.raises(KeyError):
            _ = Failure("true", "c").got


class TestFailureCaseFailure:
    """Failure.case_failure, the record of the case that failed a property."""

    def test_returns_the_failure_record_of_a_failing_case(self) -> None:
        """case_failure returns the record in the field failure."""
        inner = Failure("equal", "inner", {"want": 1, "got": 2})
        assert Failure("prop-for-all", "c", {"failure": inner}).case_failure is inner

    def test_raises_key_error_for_a_failure_field_without_a_record(self) -> None:
        """case_failure raises KeyError when the field contains no record."""
        with pytest.raises(KeyError):
            _ = Failure("prop-for-all", "c", {"failure": None}).case_failure

    def test_raises_key_error_without_a_failure_field(self) -> None:
        """case_failure raises KeyError when the detail has no field failure."""
        with pytest.raises(KeyError):
            _ = Failure("equal", "c", {"want": 1, "got": 2}).case_failure


class TestRender:
    """render, the sentence of a record."""

    def test_returns_the_contract_alone_without_detail(self) -> None:
        """A record without detail renders as its contract."""
        assert render(Failure("true", "the flag is set")) == "the flag is set"

    def test_states_want_before_got(self) -> None:
        """The sentence states want, then got, each with its repr."""
        failure = Failure("length", "every item comes back", {"got": 2, "want": 3})
        assert render(failure) == "every item comes back: want 3, got 2"

    def test_states_an_unknown_field_after_the_known_ones(self) -> None:
        """A field outside the reading order follows it, alphabetically."""
        detail = {"zebra": 1, "got": "x", "apple": 3}
        assert render(Failure("made-up", "c", detail)) == "c: got 'x', apple 3, zebra 1"

    def test_returns_the_registered_sentence_of_an_assertion(self) -> None:
        """A registered sentence replaces the list of the fields."""
        register_sentence(lambda f: f"{f.contract}!", "made-up-sentence")
        assert render(Failure("made-up-sentence", "said", {"got": 1})) == "said!"


class TestRegisterSentence:
    """register_sentence, the sentence of the records of some assertions."""

    def test_gives_each_assertion_that_it_names_the_sentence(self) -> None:
        """Both assertions render with the one sentence."""
        register_sentence(lambda f: f"{f.contract}?", "made-up-a", "made-up-b")
        assert [
            render(Failure("made-up-a", "a", {"got": 1})),
            render(Failure("made-up-b", "b", {"got": 1})),
        ] == ["a?", "b?"]


class TestCallSite:
    """call_site, the innermost frame outside the library."""

    def test_returns_the_line_of_the_caller(self) -> None:
        """The call site of a call from a test is the test's line."""
        here = call_site()
        frame = inspect.currentframe()
        assert frame is not None
        assert here == Where(__file__, frame.f_lineno - 3)

    def test_returns_none_when_every_frame_is_the_library_s(self) -> None:
        """A stack whose every frame is inside the library has no call site.

        A thread that _thread starts has no frame of its own below its
        target, so a target compiled under a path of the library is the
        whole stack.
        """
        library = os.path.dirname(os.path.abspath(call_site.__code__.co_filename))
        space: dict[str, Any] = {"call_site": call_site}
        source = (
            "def probe(found, done):\n    found.append(call_site())\n    done.set()\n"
        )
        exec(compile(source, os.path.join(library, "probe.py"), "exec"), space)
        found: list[Where | None] = []
        done = threading.Event()
        _thread.start_new_thread(space["probe"], (found, done))
        assert done.wait(5)
        assert found == [None]


def _raises() -> None:
    """Raise ValueError, as the code under test of a body does."""
    raise ValueError("the code broke")


class TestSiteIn:
    """site_in, the innermost frame outside the library in a traceback."""

    def test_returns_the_line_of_the_innermost_frame_of_the_caller(self) -> None:
        """The frame that raised is the innermost frame of this file."""
        with pytest.raises(ValueError) as caught:
            _raises()
        assert site_in(caught.value.__traceback__) == Where(
            __file__, _raises.__code__.co_firstlineno + 2
        )

    def test_returns_the_caller_of_a_library_function_that_raised(self) -> None:
        """The library raises, and the frame of this test called it."""
        frame = inspect.currentframe()
        assert frame is not None
        start = frame.f_lineno
        with pytest.raises(KeyError) as caught:
            _ = Failure("true", "c").got
        assert site_in(caught.value.__traceback__) == Where(__file__, start + 2)

    def test_returns_none_when_every_frame_is_the_library_s(self) -> None:
        """A traceback of library code alone has no frame of the caller."""
        library = os.path.dirname(os.path.abspath(call_site.__code__.co_filename))
        space: dict[str, Any] = {}
        source = (
            "def probe():\n"
            "    try:\n"
            "        raise ValueError('inside')\n"
            "    except ValueError as error:\n"
            "        return error.__traceback__\n"
        )
        exec(compile(source, os.path.join(library, "probe.py"), "exec"), space)
        assert site_in(space["probe"]()) is None

    def test_returns_none_for_no_traceback(self) -> None:
        """An exception that was never raised has no traceback."""
        assert site_in(ValueError("never raised").__traceback__) is None
