# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The records of other kinds in the user properties of a test.

A tool of dokimasia writes a record of its own kind into the item of a test,
beside the call records. The fixture seat attaches the user properties of the
test's item to its collector. append adds each record to them as the
property <kind>.<n>, and numbers the records of each kind of a test from 1.
"""

from __future__ import annotations

import threading
import weakref
from dataclasses import dataclass, field

__all__ = ["CALL_KIND", "append", "attach"]

#: The kind of the call records of this library.
CALL_KIND = "dokimi.assert"


@dataclass(eq=False, slots=True)
class _Test:
    """The user properties of the item of one test.

    Attributes:
        properties: The user properties of the item.
        last: The number of the last record of each kind.
        lock: Guards last and the appends to properties.
    """

    properties: list[tuple[str, object]]
    last: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


#: The test of each collector of the fixture seat.
_TESTS: weakref.WeakKeyDictionary[object, _Test] = weakref.WeakKeyDictionary()


def attach(seat: object, properties: list[tuple[str, object]]) -> None:
    """Make append add the records of seat to properties.

    Args:
        seat: The collector of the fixture seat.
        properties: The user properties of the test's item.
    """
    _TESTS[seat] = _Test(properties)


def append(seat: object, kind: str, record: str) -> None:
    """Add record to the user properties of the test of seat as <kind>.<n>.

    It does not write for a seat without a test, such as a recorder or the
    case of a property. It does not check kind or record.

    Args:
        seat: The seat of the call.
        kind: The kind of the record.
        record: The JSON text of the record.
    """
    try:
        test = _TESTS.get(seat)
    except TypeError:
        return
    if test is None:
        return
    with test.lock:
        number = test.last.get(kind, 0) + 1
        test.last[kind] = number
        test.properties.append((f"{kind}.{number}", record))
