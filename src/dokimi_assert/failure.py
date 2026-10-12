"""The record that a failing assertion reports, and the sentence of it.

The record is the same in every implementation of the definition. The
sentence that a person reads is rendered from the record. The definition
does not fix the sentence, because each language has its own conventions.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import CodeType, TracebackType
from typing import Any

__all__ = ["Failure", "Where", "call_site", "register_sentence", "render", "site_in"]

#: The fields of a detail that the accessors of a failure record read.
_WANT = "want"
_GOT = "got"
_CASE_FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class Where:
    """The call site of an assertion.

    Attributes:
        file: The path of the file that called the assertion.
        line: The line of the call, from 1.
    """

    file: str
    line: int


@dataclass(frozen=True, slots=True, weakref_slot=True)
class Failure:
    """The record that a failing assertion reports, as the definition states it.

    A record accepts weak references, so a module can keep data beside a
    record while the record is alive.

    Attributes:
        assertion: The canonical id of the assertion.
        contract: The caller's message, unchanged.
        detail: The fields that the definition declares for the assertion,
            and no others.
        where: The call site, or None when the frame could not be read.
    """

    assertion: str
    contract: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    where: Where | None = None

    @property
    def want(self) -> Any:
        """The value of the field want of the detail.

        A declared field can contain None, as got of an equal failure over
        None does. The accessor then returns None.

        Raises:
            KeyError: The assertion does not declare the field want.
        """
        return self.detail[_WANT]

    @property
    def got(self) -> Any:
        """The value of the field got of the detail.

        Raises:
            KeyError: The assertion does not declare the field got.
        """
        return self.detail[_GOT]

    @property
    def case_failure(self) -> Failure:
        """The failure record of the failing case of a property.

        It is the record of the minimal case of a counterexample, or of the
        case that the replay of a flaky run contradicted.

        Raises:
            KeyError: The detail does not contain a failure record in the
                field failure.
        """
        held = self.detail.get(_CASE_FAILURE)
        if not isinstance(held, Failure):
            raise KeyError(_CASE_FAILURE)
        return held


#: The order in which a sentence states the fields of a detail: want before
#: got, and the rest in a fixed reading order. A field that the order does
#: not list follows them, alphabetically.
_ORDER = (
    "want",
    "got",
    "length",
    "haystack",
    "needle",
    "index",
    "prefix",
    "suffix",
    "pattern",
    "reason",
    "tolerance",
    "low",
    "high",
    "first",
    "second",
    "attempts",
    "last",
    "leaked",
    "field",
)

#: The sentences that a module registered for the records of its assertions,
#: by assertion id.
_SENTENCES: dict[str, Callable[[Failure], str]] = {}


def register_sentence(sentence: Callable[[Failure], str], *assertions: str) -> None:
    """Make sentence the sentence of the records of the assertions.

    The sentence replaces the contract and the list of the fields of the
    detail.

    Args:
        sentence: Returns the sentence of a record.
        *assertions: The canonical ids of the assertions.
    """
    for assertion in assertions:
        _SENTENCES[assertion] = sentence


def render(failure: Failure) -> str:
    """Return the sentence of a failure record.

    Args:
        failure: The record.

    Returns:
        The sentence that the assertion's module registered, or the contract
        followed by each field of the detail with the repr of its value.
    """
    sentence = _SENTENCES.get(failure.assertion)
    if sentence is not None:
        return sentence(failure)
    if not failure.detail:
        return failure.contract

    known = [name for name in _ORDER if name in failure.detail]
    rest = sorted(name for name in failure.detail if name not in _ORDER)
    stated = ", ".join(f"{name} {failure.detail[name]!r}" for name in known + rest)
    return f"{failure.contract}: {stated}"


#: The directory of this library's modules. A frame of a file below it is not
#: the frame of the caller.
_LIBRARY = os.path.dirname(os.path.abspath(__file__)) + os.sep


def _outside(code: CodeType) -> bool:
    """Report whether the file of code is outside the directory of this library."""
    return not os.path.abspath(code.co_filename).startswith(_LIBRARY)


def call_site() -> Where | None:
    """Return the call site of the running assertion.

    The call site is the innermost frame whose file is outside this
    library's directory.

    Returns:
        The file and the line of that frame, or None when every frame of the
        stack is a frame of this library.
    """
    frame = inspect.currentframe()
    while frame is not None and not _outside(frame.f_code):
        frame = frame.f_back
    return None if frame is None else Where(frame.f_code.co_filename, frame.f_lineno)


def site_in(traceback: TracebackType | None) -> Where | None:
    """Return the innermost frame of a traceback whose file is outside this library.

    Args:
        traceback: The traceback of an exception, from the frame that caught
            it to the frame that raised it.

    Returns:
        The file and the line of that frame, or None when every frame of the
        traceback is a frame of this library.
    """
    found: Where | None = None
    while traceback is not None:
        code = traceback.tb_frame.f_code
        if _outside(code):
            found = Where(code.co_filename, traceback.tb_lineno)
        traceback = traceback.tb_next
    return found
