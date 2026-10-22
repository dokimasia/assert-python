# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The corpus, and the verdict of a run of one case.

Every implementation of the definition runs the same cases. A library that
gives a name of the definition a different meaning fails them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dokimi_assert import check, expect, option
from dokimi_assert._record.call import DEFINITION
from dokimi_assert.conformance.definition import (
    LANGUAGE,
    detail_fields,
    names,
    relaxation_names,
    spec_dir,
)
from dokimi_assert.conformance.literal import LiteralError, Objects, canonical, decode

if TYPE_CHECKING:
    from types import ModuleType

    from dokimi_assert._matcher.option import Option
    from dokimi_assert.seat import Recorder

__all__ = [
    "SURFACES",
    "Case",
    "cases",
    "member_for",
    "mismatch",
    "options_of",
    "skip_reason",
]

#: The surfaces check and expect. The runner runs every case on both.
SURFACES: dict[str, ModuleType] = {"check": check, "expect": expect}


@dataclass(frozen=True)
class Case:
    """One case of the corpus with the input of an assertion and its wanted report.

    Attributes:
        id: The id of the case. It starts with the assertion.
        assertion: The canonical id of the assertion under test.
        args: The arguments, decoded.
        options: The ids of the relaxations that the call passes.
        expect: pass when the assertion must pass, and fail when it must
            fail.
        detail: The wanted values of the failure record by field name. The
            run does not check a field that the case does not have.
        fields: The detail fields that the assertion declares. A failure
            record has exactly these fields.
        subject: The kind of the behaviour that the case passes in place of
            arguments, or None for a case of values.
        skip: The reason of each language that skips the case.
    """

    id: str
    assertion: str
    args: tuple[Any, ...] = ()
    options: tuple[str, ...] = ()
    expect: str = "pass"
    detail: Mapping[str, Any] = field(default_factory=dict)
    fields: tuple[str, ...] = ()
    subject: str | None = None
    skip: Mapping[str, str] = field(default_factory=dict)


def cases() -> list[Case]:
    """Return every case of the vendored corpus.

    Returns:
        The cases of each file of the corpus in the order of the file names.
        The references of one case decode to one object per id.
    """
    declared = detail_fields()
    found: list[Case] = []
    corpus = spec_dir() / "corpus"
    for entry in sorted(corpus.iterdir(), key=lambda p: p.name):
        if not entry.name.endswith(".json"):
            continue
        document = json.loads(entry.read_text(encoding="utf-8"))
        assertion = document["assertion"]
        for raw in document["cases"]:
            objects = Objects()
            subject = raw.get("subject")
            found.append(
                Case(
                    id=raw["id"],
                    assertion=assertion,
                    args=tuple(objects.decode(arg) for arg in raw.get("args", [])),
                    options=tuple(raw.get("options", [])),
                    expect=raw["expect"],
                    detail={
                        name: decode(value)
                        for name, value in raw.get("detail", {}).items()
                    },
                    fields=tuple(declared[assertion]),
                    subject=subject["kind"] if subject else None,
                    skip=raw.get("skip", {}),
                )
            )
    return found


def skip_reason(case: Case) -> str | None:
    """Return the reason that this language skips a case.

    Args:
        case: The case.

    Returns:
        The declared reason, or None when this language runs the case.
    """
    return case.skip.get(LANGUAGE)


def member_for(case: Case) -> str | None:
    """Return the Python name of the assertion of a case.

    Args:
        case: The case.

    Returns:
        The name, or None when the naming table does not have one.
    """
    return names().get(case.assertion)


def options_of(case: Case) -> list[Option]:
    """Return the options that the call of a case passes.

    Args:
        case: The case.

    Returns:
        One option per relaxation of the case.

    Raises:
        LookupError: The case has a relaxation without a Python name.
    """
    named = relaxation_names()
    out: list[Option] = []
    for rid in case.options:
        name = named.get(rid, "")
        make = getattr(option, name, None) if name else None
        if make is None:
            msg = f"{case.id}: the relaxation {rid} does not have a Python option"
            raise LookupError(msg)
        out.append(make())
    return out


def _fields_mismatch(whose: str, detail: Mapping[str, Any], case: Case) -> str | None:
    """Return how the names of a detail differ from the fields of the assertion."""
    got = sorted(detail)
    declared = sorted(case.fields)
    if got == declared:
        return None
    return f"{whose} has the fields {json.dumps(got)}, want {json.dumps(declared)}"


def _record_mismatch(case: Case, recorder: Recorder) -> str | None:
    """Compare the first failure record of a failing case with the case."""
    if not recorder.failed:
        return "expected a failure, got a pass"
    failures = recorder.failures
    if not failures:
        return "the assertion did not report a failure record"
    record = failures[0]
    if record.assertion != case.assertion:
        return f"the record is of {record.assertion}, want {case.assertion}"
    if record.contract != case.id:
        return (
            f"the record has the contract {json.dumps(record.contract)}, "
            f"want {json.dumps(case.id)}"
        )
    return _detail_mismatch(record.detail, case)


def _detail_mismatch(detail: Mapping[str, Any], case: Case) -> str | None:
    """Compare the detail of a failure record with the detail of a case."""
    fields = _fields_mismatch("the record", detail, case)
    if fields is not None:
        return fields
    for name, want in case.detail.items():
        got = detail.get(name)
        if canonical(got) != canonical(want):
            return f'detail "{name}" is {canonical(got)}, want {canonical(want)}'
    return None


def _call_mismatch(case: Case, recorder: Recorder, aborting: bool) -> str | None:
    """Compare the one call record of a recorder with a case."""
    lines = recorder.records
    if len(lines) != 1:
        return f"the recorder keeps {len(lines)} call records, want 1"
    call = json.loads(lines[0])
    call.pop("where", None)
    detail = call.pop("detail", None)
    want = {
        "definition": DEFINITION,
        "seq": 1,
        "assertion": case.assertion,
        "contract": case.id,
        "verdict": case.expect,
        "aborting": aborting,
    }
    if call != want:
        return f"the call record is {json.dumps(call)}, want {json.dumps(want)}"
    if case.expect == "pass":
        if detail is None:
            return None
        return f"a passing call record has the detail {json.dumps(detail)}"
    return _literal_mismatch(detail or {}, case)


def _literal_mismatch(detail: Mapping[str, Any], case: Case) -> str | None:
    """Compare the typed literals of the detail of a call record with a case."""
    named = _fields_mismatch("the call record", detail, case)
    if named is not None:
        return named
    for name, want_value in case.detail.items():
        literal = detail[name]
        try:
            decoded = decode(literal)
        except LiteralError as error:
            return (
                f"the field {name} of the call record is not a typed literal: {error}"
            )
        if canonical(decoded) != canonical(want_value):
            return (
                f"the field {name} of the call record is {json.dumps(literal)}, "
                f"want {canonical(want_value)}"
            )
    return None


def mismatch(case: Case, recorder: Recorder, aborting: bool) -> str | None:
    """Return how a run of a case differs from the case.

    The runner passes the id of the case as the contract. The first failure
    record of a failing case must meet these conditions:

    - Its assertion is the assertion of the case.
    - Its contract is the id of the case.
    - It has exactly the fields of the assertion.
    - Each field of the case has the wanted value.

    The recorder must keep one call record. It has the definition of this
    library, the number 1 without a parent, the assertion of the case, the id
    as its contract, the verdict of the case and the surface of the call. A
    failure has its fields as typed literals.

    Args:
        case: The case that the runner drove.
        recorder: The seat that received the report of the assertion.
        aborting: When True, the case ran on the aborting surface.

    Returns:
        The difference, or None when the run agrees with the case.
    """
    if case.expect == "pass" and recorder.failed:
        return f"expected a pass, got: {recorder.message}"
    record = _record_mismatch(case, recorder) if case.expect == "fail" else None
    return record if record is not None else _call_mismatch(case, recorder, aborting)
