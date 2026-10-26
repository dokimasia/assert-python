# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The call record of one assertion call.

A record has the number of the call in its test, the assertion, the
contract, the verdict, the surface, the call site and the detail of a
failure. The record of a skip has the reason too. Each record is one JSON
object on one line. Its fields are in the order of the definition.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from dokimi_assert._record.literal import json
from dokimi_assert.conformance.definition import version

__all__ = ["DEFINITION", "Call", "Phase", "Place", "Verdict", "encode_call"]

#: The version of the definition that this library implements: the version of
#: the vendored definition, which its file VERSION contains. Every call record
#: contains it.
DEFINITION = version()

#: How a call ended.
Verdict = Literal["pass", "fail", "error", "skip"]

#: The kind of the case of a property in which a call ran.
Phase = Literal[
    "example",
    "stored",
    "simplest",
    "random",
    "prefix",
    "edge",
    "coverage",
    "replay",
    "shrink",
    "explain",
    "token",
    "fuzz",
]


@dataclass(frozen=True, slots=True)
class Call:
    """The record of one call, before the calls that keep it give it a number.

    Attributes:
        assertion: The canonical id of the assertion.
        contract: The message of the caller as the caller wrote it.
        verdict: How the call ended.
        aborting: When True, the call was made on the aborting surface.
        where: The file and the line of the call site. It is None when the
            call could not read them.
        detail: An object of JSON values. A failure has one, and so does the
            run of a property.
        error: The text of the fault that ended a call of the verdict error.
        reason: The reason of the skip of a call of the verdict skip.
    """

    assertion: str
    contract: str
    verdict: Verdict
    aborting: bool
    where: tuple[str, int] | None = None
    detail: Mapping[str, Any] | None = None
    error: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Place:
    """Where a numbered call is among the calls of its test.

    Attributes:
        seq: The number of the call in its test. The numbers start at 1.
        parent: The number of the call in whose body this call ran.
        run: The number of the run of that body. The numbers start at 1.
        phase: The phase of that run. Only a call in the case of a property
            has one.
    """

    seq: int
    parent: int | None = None
    run: int | None = None
    phase: Phase | None = None


def encode_call(call: Call, place: Place) -> str:
    """Return the call record of call at place as one line of JSON.

    Args:
        call: The call.
        place: The number of the call, and its parent, run and phase in a
            body.

    Returns:
        The text of the record. It leaves out each field that is not present.
    """
    record: dict[str, Any] = {"definition": DEFINITION, "seq": place.seq}
    if place.parent is not None:
        record["parent"] = place.parent
        record["run"] = place.run
        if place.phase is not None:
            record["phase"] = place.phase
    record["assertion"] = call.assertion
    record["contract"] = call.contract
    record["verdict"] = call.verdict
    record["aborting"] = call.aborting
    if call.where is not None:
        file, line = call.where
        record["where"] = {"file": pathlib.Path(file).name, "line": line}
    if call.detail is not None:
        record["detail"] = dict(call.detail)
    if call.error is not None:
        record["error"] = call.error
    if call.reason is not None:
        record["reason"] = call.reason
    return json(record)
