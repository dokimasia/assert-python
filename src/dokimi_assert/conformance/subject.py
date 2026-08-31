"""The behaviours a corpus case can name in place of a callable.

A case states its arguments as typed literals, which cannot describe a
callable. The assertions taking one are handed a named behaviour from a
small fixed set instead, and this builds each one natively.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

__all__ = ["SUBJECTS", "drive"]


class SubjectError(RuntimeError):
    """What a subject raises when it is asked to fail on its own terms."""


def _returns_ok() -> Callable[..., Any]:
    """Do the work and answer success, whatever the handle says."""

    async def body(*_: Any) -> str:
        return "did the work"

    return body


def _reads_handle() -> Callable[..., Any]:
    """Answer the reason the handle gives, or success when it is running."""

    async def body(*_: Any) -> str:
        await asyncio.sleep(0)
        return "did the work"

    return body


def _raises() -> Callable[..., Any]:
    """Raise rather than answering."""

    def body(*_: Any) -> Any:
        raise SubjectError("the subject raised")

    return body


def _fails_otherwise() -> Callable[..., Any]:
    """Answer a failure of its own, unrelated to any handle."""

    async def body(*_: Any) -> Any:
        raise SubjectError("the subject failed for its own reason")

    return body


def _dereferences_handle() -> Callable[..., Any]:
    """Read a handle without checking it is there."""

    def body(handle: Any = None) -> Any:
        return handle.cancelled()

    return body


def _never_settles() -> Callable[..., Any]:
    """Report a failure on every attempt."""
    from dokimi_assert import check

    def body(seat: Any) -> None:
        check.is_true(seat, False, "never settles")

    return body


def _settles_after() -> Callable[..., Any]:
    """Report a failure twice, then succeed.

    The count lives in the closure, so each case gets its own subject and
    two cases cannot see each other's attempts.
    """
    from dokimi_assert import check

    attempts = 0

    def body(seat: Any) -> None:
        nonlocal attempts
        attempts += 1
        check.is_true(seat, attempts >= 3, "not yet")

    return body


class _Observed:
    """A subject with state something outside it can read.

    A callable with an attribute would say the same thing, but a
    function's attributes are not typed, and the projection is half the
    contract here.
    """

    def __init__(self, *, changes: bool) -> None:
        """Hold state, and say whether calling this changes it.

        Args:
            changes: Whether a call appends to the state.
        """
        self._held: list[int] = [1, 2]
        self._changes: bool = changes

    def __call__(self) -> None:
        """Do the work, changing the state or leaving it alone."""
        if self._changes:
            self._held.append(len(self._held))

    def observe(self) -> list[int]:
        """Read the state a caller can see.

        Returns:
            A copy, so the projection does not share memory with the
            subject and read the same value twice.
        """
        return list(self._held)


def _accumulates() -> Callable[..., Any]:
    """Change the observed state once per call."""
    return _Observed(changes=True)


def _leaves_state_alone() -> Callable[..., Any]:
    """Read the observed state and change nothing."""
    return _Observed(changes=False)


#: How each named behaviour is built. A kind absent here is one this
#: language cannot make, and the corpus case declares the skip.
SUBJECTS: dict[str, Callable[[], Callable[..., Any]]] = {
    "returns-ok": _returns_ok,
    "reads-handle": _reads_handle,
    "ignores-handle": _returns_ok,
    "raises": _raises,
    "fails-otherwise": _fails_otherwise,
    "dereferences-handle": _dereferences_handle,
    "never-settles": _never_settles,
    "settles-after": _settles_after,
    "accumulates": _accumulates,
    "leaves-state-alone": _leaves_state_alone,
}


def drive(kind: str) -> Callable[..., Any] | None:
    """Build the named behaviour, or None when this language cannot.

    Args:
        kind: The subject kind the case names.

    Returns:
        A callable of the shape the assertion expects, or None.
    """
    build = SUBJECTS.get(kind)
    return build() if build else None
