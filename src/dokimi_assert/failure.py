"""The record a failing assertion reports, and where it came from.

The record is the same shape in every implementation of the standard.
The sentence a person reads is rendered from it and is not
standardised, because each language reads its own conventions.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Failure", "Where", "call_site", "render"]


@dataclass(frozen=True, slots=True)
class Where:
    """The call site a failure came from.

    Attributes:
        file: The path the assertion was called from.
        line: The line within it.
    """

    file: str
    line: int


@dataclass(frozen=True, slots=True)
class Failure:
    """What a failing assertion reports.

    Attributes:
        assertion: The canonical id the definition names.
        contract: The caller's message, unchanged.
        detail: The values named by that assertion's declared fields.
        where: The call site, or None when the frame could not be read.
    """

    assertion: str
    contract: str
    detail: dict[str, Any] = field(default_factory=dict)
    where: Where | None = None


#: The order Python names detail fields in, which is want before got
#: and the rest in a fixed reading order. A field not listed here
#: follows these, alphabetically.
#:
#: The standard fixes the record, not the sentence.
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


def render(failure: Failure) -> str:
    """Turn a record into the sentence a person reads.

    Args:
        failure: The record to phrase.

    Returns:
        The contract, then the detail it carries.
    """
    if not failure.detail:
        return failure.contract

    known = [name for name in _ORDER if name in failure.detail]
    rest = sorted(name for name in failure.detail if name not in _ORDER)
    said = ", ".join(f"{name} {failure.detail[name]!r}" for name in known + rest)
    return f"{failure.contract}: {said}"


#: Frames between a caller's line and the reader: the matcher that
#: reported, the reporting seam, and the assertion the caller wrote.
_CALLER_DEPTH = 3


def call_site(depth: int = _CALLER_DEPTH) -> Where | None:
    """Read the call site depth frames above this call.

    Args:
        depth: How many frames to climb.

    Returns:
        Where the assertion was called, or None when the frame cannot
        be read.
    """
    frame = inspect.currentframe()
    for _ in range(depth + 1):
        if frame is None:
            return None
        frame = frame.f_back
    if frame is None:
        return None
    return Where(file=str(Path(frame.f_code.co_filename)), line=frame.f_lineno)
