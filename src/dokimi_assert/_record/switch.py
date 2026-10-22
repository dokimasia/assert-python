# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The switch that turns call records on.

DOKIMI_ASSERT_RECORD=1 makes the seat of a test write the call record of
every call that it receives. An unset, empty or 0 variable does not write a
record. Any other value ends every call with a fault, and the text of the
fault contains the name of the variable.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass

__all__ = ["VARIABLE", "Reading", "reading"]

#: The environment variable that switches recording on.
VARIABLE = "DOKIMI_ASSERT_RECORD"


@dataclass(frozen=True, slots=True)
class Reading:
    """The reading of the switch.

    Attributes:
        on: When True, the variable switches recording on.
        fault: The fault of a value that the definition does not define, and
            None for a value that it defines.
    """

    on: bool
    fault: str | None = None


@functools.cache
def reading() -> Reading:
    """Return the reading of the switch. The process reads the variable once.

    A change of the variable during a run does not change the reading.

    Returns:
        On for 1, off for an unset, empty or 0 variable, and the fault of
        any other value.
    """
    value = os.environ.get(VARIABLE)
    if value is None or value in ("", "0"):
        return Reading(on=False)
    if value == "1":
        return Reading(on=True)
    return Reading(on=False, fault=f"{VARIABLE}: {value!r} is neither 0 nor 1")
