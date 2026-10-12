"""The record of a comparison of trees that fails, and the verdict of a comparison.

A record has three fields:

- want has the wanted entries at the first 64 paths that differ.
- got has the entries read at those paths.
- differences is the number of paths that differ.

A missing entry is only in want, an extra entry is only in got, and a changed
entry is in both. An entry of got has its mode only where the wanted entry at
its path has one. A file of got without a mode has the execute bit of its
owner instead. The call record has each tree as a tree literal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dokimi_assert._files.entry import Entry, unstated
from dokimi_assert._files.literal import CONTENT_LIMIT, encode
from dokimi_assert._files.tree import full, paths_of
from dokimi_assert._matcher.seat import Mode
from dokimi_assert._matcher.verdict import Running
from dokimi_assert._record.literal import detail
from dokimi_assert.failure import Failure, Where

__all__ = ["MAX_PATHS", "Comparison", "comparison", "missing", "report"]

#: The most paths that a record lists.
MAX_PATHS = 64


@dataclass(frozen=True, slots=True)
class Comparison:
    """The detail of a comparison of trees that fails.

    Attributes:
        want: The wanted entries at the paths that differ in path order, or
            None for a missing golden tree.
        got: The entries read at the paths that differ in path order.
        differences: The number of paths that differ.
    """

    want: dict[str, Entry] | None
    got: dict[str, Entry]
    differences: int


def _as_compared(read: Entry, w: Entry | None) -> Entry:
    """Return the entry read in the form that the comparison checked.

    w is the wanted entry at the path of read. The result has its mode when
    both entries have one. Otherwise a file has only the execute bit of its
    owner.
    """
    if read.mode is not None and w is not None and w.mode is not None:
        return read
    return unstated(read)


def comparison(
    want: Mapping[str, Entry], got: Mapping[str, Entry], paths: Sequence[str]
) -> Comparison | None:
    """Return the record of a comparison of got with want.

    Args:
        want: The wanted tree.
        got: The tree read.
        paths: The paths that differ in path order.

    Returns:
        The record, or None when no path differs.
    """
    if not paths:
        return None
    wanted = full(want)
    record_want: dict[str, Entry] = {}
    record_got: dict[str, Entry] = {}
    for path in paths[:MAX_PATHS]:
        w = wanted.get(path)
        g = got.get(path)
        if w is not None:
            record_want[path] = w
        if g is not None:
            record_got[path] = _as_compared(g, w)
    return Comparison(want=record_want, got=record_got, differences=len(paths))


def missing(got: Mapping[str, Entry]) -> Comparison:
    """Return the record of a golden tree that is missing.

    Args:
        got: The tree read.

    Returns:
        The record. want is None, got has the first 64 entries of got in path
        order without their modes, and differences is the number of the
        entries of got.
    """
    paths = paths_of(got)
    listed = {path: unstated(got[path]) for path in paths[:MAX_PATHS]}
    return Comparison(want=None, got=listed, differences=len(paths))


def report(
    running: Running,
    assertion: str,
    contract: str,
    record: Comparison | None,
    where: Where | None,
) -> None:
    """Report the verdict of a call of a comparison of trees.

    The verdict is a pass when record is None, and a failure that stops the
    test otherwise. The detail of the failure has want and got as trees. Its
    call record has them as tree literals.

    Args:
        running: The call.
        assertion: The canonical id.
        contract: The message of the caller.
        record: The record, or None when no path differs.
        where: The call site.
    """
    __tracebackhide__ = True
    if record is None:
        running.passed(Mode.FATAL, assertion, contract)
        return
    want, got = record.want, record.got
    failure = Failure(
        assertion,
        contract,
        {"want": want, "got": got, "differences": record.differences},
        where,
    )
    running.failed_run(
        Mode.FATAL,
        failure,
        {
            "want": detail(None) if want is None else encode(want, CONTENT_LIMIT),
            "got": encode(got, CONTENT_LIMIT),
            "differences": detail(record.differences),
        },
    )
