"""The record of the run of a property, and its sentence.

The detail of the record has the ten fields of prop-for-all: outcome,
cases, rejected, seed, counterexample, failure, choices, others, divergence
and coverage. A field that the outcome does not use is None. The call record
of a property contains the same detail as JSON. Each drawn value in it is a
typed literal of the type of its generator.
"""

from __future__ import annotations

import json
import os
import weakref
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from dokimi_assert._prop.case import Failing
from dokimi_assert._prop.engine.case import Drawn as EngineDrawn
from dokimi_assert._prop.engine.case import Failed, Place
from dokimi_assert._prop.engine.case import Step as EngineStep
from dokimi_assert._prop.engine.choice import Bounds, FloatBounds, IntegerBounds
from dokimi_assert._prop.engine.execution import Divergence as EngineDivergence
from dokimi_assert._prop.engine.execution import Execution
from dokimi_assert._prop.engine.literal import plain
from dokimi_assert._prop.engine.runner import Outcome
from dokimi_assert._prop.engine.shrink import Explained
from dokimi_assert._prop.engine.tokens import encode
from dokimi_assert._prop.engine.traces import entries
from dokimi_assert._prop.environment import REPLAY_VARIABLE
from dokimi_assert._prop.identity import from_key, text_of
from dokimi_assert._prop.literal import drawn_literal
from dokimi_assert._record.literal import detail as literal_of
from dokimi_assert._record.literal import opaque
from dokimi_assert.failure import Failure, Where, register_sentence, render

__all__ = [
    "FOR_ALL",
    "Divergence",
    "Drawn",
    "Entry",
    "Other",
    "Shortfall",
    "Step",
    "detail_json",
    "detail_of",
    "record_of",
    "register_sentences",
    "sentence",
]

#: The id of the assertion of the record of for_all.
FOR_ALL = "prop-for-all"


@dataclass(frozen=True, slots=True)
class Drawn:
    """One draw of a counterexample.

    Attributes:
        label: The label of the draw.
        value: The value that the generator decoded.
        any_value_fails: True when every value fails at the draw. It is None
            for a draw that the explain phase did not test.
        nearest_passing: The passing value one step towards the target, or
            the value that a map returns for that step. Only a draw of an
            integer or a duration whose value matters has one. It is None for
            every other draw.
    """

    label: str
    value: Any
    any_value_fails: bool | None
    nearest_passing: Any = None


@dataclass(frozen=True, slots=True)
class Step:
    """One step of a machine in a counterexample.

    Attributes:
        step: The name of the action.
        client: The client of a step of a concurrent section, or None.
        drain: When True, the step is a step of the drain.
    """

    step: str
    client: int | None = None
    drain: bool = False


#: One entry of a counterexample. It is a draw or a step.
Entry = Drawn | Step


@dataclass(frozen=True, slots=True)
class Other:
    """A further failure that a run found. The run shrinks it to its smallest case.

    Attributes:
        counterexample: The draws and the steps of the case.
        failure: The failure record of the case.
        choices: The replay token of the case.
    """

    counterexample: list[Entry]
    failure: Failure
    choices: str


@dataclass(frozen=True, slots=True)
class Divergence:
    """The first difference between a failing case and its replay.

    Attributes:
        what: The kind of the difference. It is request, fingerprint or
            verdict.
        index: The position of the request or the fingerprint. For a
            verdict, it is the number of choices of the case.
        recorded: The recorded side. The side of a request is its bounds in
            the form of the vectors of the definition. The side of a
            fingerprint is its value, and the side of a verdict is the text of
            the identity of its failure. The side is None for an end, for an
            absent fingerprint and for a pass.
        replayed: The replayed side in the same form as recorded.
        label: The label of the draw that was running, or None.
        step: The part and the step of the machine that was running, or None.
    """

    what: Literal["request", "fingerprint", "verdict"]
    index: int
    recorded: Any
    replayed: Any
    label: str | None
    step: Place | None


@dataclass(frozen=True, slots=True)
class Shortfall:
    """A coverage requirement that a run refuted or left unmet.

    Attributes:
        label: The label of the requirement.
        share: The share that the requirement needs.
        counted: The number of valid cases that counted the label.
        valid: The number of valid cases.
        verdict: The verdict. It is refuted or unmet.
    """

    label: str
    share: float
    counted: int
    valid: int
    verdict: str


#: The notes of the failing case of a record, by the id of the record. Only a
#: record that record_of returned with notes has an entry. A finalizer removes
#: the entry when the record is collected, so an id refers to one record at a
#: time.
_NOTES: dict[int, tuple[str, ...]] = {}


def _bounds_of(bounds: Bounds) -> dict[str, Any]:
    """Return the bounds of a request in the form of the vectors of the definition."""
    if isinstance(bounds, IntegerBounds):
        return {"kind": "integer", "min": plain(bounds.lo), "max": plain(bounds.hi)}
    if isinstance(bounds, FloatBounds):
        return {
            "kind": "float",
            "min": plain(bounds.lo),
            "max": plain(bounds.hi),
            "allow_nan": bounds.allow_nan,
            "width": bounds.width,
        }
    return {
        "kind": "sequence",
        "k": bounds.k,
        "min_size": bounds.min_size,
        "max_size": bounds.max_size,
    }


def _failing_of(execution: Execution) -> Failing:
    """Return the Failing of a failed execution."""
    return cast("Failing", cast("Failed", execution.failure).record)


def _step_of(step: EngineStep) -> Step:
    """Return the counterexample Step of a step of a machine."""
    return Step(step.action, step.client, step.drain)


def _entries_of(execution: Execution, explanation: Sequence[Explained]) -> list[Entry]:
    """Return the entries of a case.

    Each draw has its explanation when the explain phase tested it.
    """
    listed: list[Entry] = []
    index = 0
    for entry in entries(execution.case):
        if isinstance(entry, EngineStep):
            listed.append(_step_of(entry))
            continue
        explained = explanation[index] if index < len(explanation) else None
        index += 1
        if explained is None:
            listed.append(Drawn(entry.label, entry.value, None))
            continue
        nearest = None if explained.nearest is None else explained.nearest[0]
        listed.append(
            Drawn(entry.label, entry.value, explained.any_value_fails, nearest)
        )
    return listed


def _side_of(side: Bounds | int | str | None) -> Any:
    """Return one side of a divergence in the form of the record."""
    if side is None or isinstance(side, int):
        return side
    if isinstance(side, str):
        return text_of(from_key(side))
    return _bounds_of(side)


def _divergence_of(divergence: EngineDivergence) -> Divergence:
    """Return a divergence in the form of the record."""
    return Divergence(
        divergence.what,
        divergence.index,
        _side_of(divergence.recorded),
        _side_of(divergence.replayed),
        divergence.label,
        divergence.step,
    )


def detail_of(outcome: Outcome) -> dict[str, Any]:
    """Return the detail of the record of a run.

    The detail has each field with its value, and None for a field that the
    outcome does not use.

    Args:
        outcome: The outcome of the run.

    Returns:
        The detail.
    """
    failing = outcome.failing
    counterexample = outcome.kind == "counterexample"
    shortfall = outcome.shortfall
    return {
        "outcome": outcome.kind,
        "cases": outcome.cases,
        "rejected": outcome.rejected,
        "seed": str(outcome.seed),
        "counterexample": None
        if failing is None
        else _entries_of(failing, outcome.explanation),
        "failure": None if failing is None else _failing_of(failing).failure,
        "choices": outcome.token if counterexample else None,
        "others": [
            Other(
                _entries_of(other, ()),
                _failing_of(other).failure,
                encode(other.case.choices),
            )
            for other in outcome.others
        ]
        if counterexample
        else None,
        "divergence": None
        if outcome.divergence is None
        else _divergence_of(outcome.divergence),
        "coverage": None
        if shortfall is None
        else Shortfall(
            shortfall.requirement.label,
            shortfall.requirement.share,
            shortfall.counted,
            shortfall.valid,
            shortfall.verdict,
        ),
    }


def _failure_json(failure: Failure) -> dict[str, Any]:
    """Return the JSON of a failure record. Each value of its detail is a literal."""
    where = failure.where
    return {
        "assertion": failure.assertion or None,
        "contract": failure.contract,
        "detail": {name: literal_of(value) for name, value in failure.detail.items()},
        "where": None
        if where is None
        else {"file": os.path.basename(where.file), "line": where.line},
    }


def _value_json(generator: object, value: Any) -> dict[str, Any]:
    """Return the literal of a drawn value, or the opaque literal of its repr."""
    written = drawn_literal(generator, value)
    return opaque(repr(value)) if written is None else written


def _step_json(step: Step) -> dict[str, Any]:
    """Return the JSON of a step of a machine with its client and its drain mark."""
    written: dict[str, Any] = {"step": step.step}
    if step.client is not None:
        written["client"] = step.client
    if step.drain:
        written["drain"] = True
    return written


def _entries_json(
    drawn: Sequence[EngineDrawn], listed: Iterable[Entry], brief: bool
) -> list[dict[str, Any]]:
    """Return the JSON of the draws and the steps of a case.

    Each value is a literal of the type of its generator. A brief entry has
    the label and the value alone.
    """
    written: list[dict[str, Any]] = []
    index = 0
    for entry in listed:
        if isinstance(entry, Step):
            written.append(_step_json(entry))
            continue
        generator = drawn[index].generator
        index += 1
        value = _value_json(generator, entry.value)
        if brief:
            written.append({"label": entry.label, "value": value})
            continue
        nearest = entry.nearest_passing
        written.append(
            {
                "label": entry.label,
                "value": value,
                "any-value-fails": entry.any_value_fails,
                "nearest-passing": None
                if nearest is None
                else _value_json(generator, nearest),
            }
        )
    return written


def _side_json(side: Any) -> Any:
    """Return the JSON of a side of a divergence. A fingerprint is a number."""
    return plain(side) if isinstance(side, int) else side


def detail_json(outcome: Outcome, detail: Mapping[str, Any]) -> dict[str, Any]:
    """Return the detail of a run in the form of its call record.

    The counts are numbers, and the seed and the token are strings. Each
    drawn value is a typed literal of the type of its generator. A failure is
    the JSON of its record, and the bounds of a request have the form of the
    vectors of the definition. A field that the outcome does not use is None.

    Args:
        outcome: The outcome of the run.
        detail: The detail that detail_of returns for the outcome.

    Returns:
        The JSON object.
    """
    listed = cast("list[Entry] | None", detail["counterexample"])
    failure = cast("Failure | None", detail["failure"])
    others = cast("list[Other] | None", detail["others"])
    divergence = cast("Divergence | None", detail["divergence"])
    coverage = cast("Shortfall | None", detail["coverage"])
    failing = outcome.failing
    return {
        "outcome": detail["outcome"],
        "cases": detail["cases"],
        "rejected": detail["rejected"],
        "seed": detail["seed"],
        "counterexample": None
        if listed is None or failing is None
        else _entries_json(failing.case.draws, listed, False),
        "failure": None if failure is None else _failure_json(failure),
        "choices": detail["choices"],
        "others": None
        if others is None
        else [
            {
                "failure": _failure_json(other.failure),
                "counterexample": _entries_json(
                    execution.case.draws, other.counterexample, True
                ),
                "choices": other.choices,
            }
            for other, execution in zip(others, outcome.others, strict=True)
        ],
        "divergence": None
        if divergence is None
        else {
            "what": divergence.what,
            "index": divergence.index,
            "recorded": _side_json(divergence.recorded),
            "replayed": _side_json(divergence.replayed),
            "label": divergence.label,
            "step": None
            if divergence.step is None
            else {
                "part": divergence.step.part,
                "position": divergence.step.position,
                "action": divergence.step.action,
            },
        },
        "coverage": None
        if coverage is None
        else {
            "label": coverage.label,
            "share": coverage.share,
            "counted": coverage.counted,
            "valid": coverage.valid,
            "verdict": coverage.verdict,
        },
    }


def record_of(
    outcome: Outcome, assertion: str, contract: str, where: Where | None
) -> tuple[Failure, dict[str, Any]]:
    """Return the record of a run that did not pass.

    A seat that does not take records reads the sentence that this module
    registers. The notes of the failing case follow the detail in the
    sentence.

    Args:
        outcome: The outcome of the run.
        assertion: prop-for-all, or the id of the property form of the run.
        contract: The contract of the property.
        where: The call site of the property.

    Returns:
        The record, and its detail in the form of the call record.
    """
    detail = detail_of(outcome)
    failure = Failure(assertion, contract, detail, where)
    notes = () if outcome.failing is None else tuple(outcome.failing.case.notes)
    if notes:
        key = id(failure)
        _NOTES[key] = notes
        weakref.finalize(failure, _NOTES.pop, key, None)
    return failure, detail_json(outcome, detail)


def _entry_line(entry: Entry) -> str:
    """Return the line of an entry of a counterexample."""
    if isinstance(entry, Step):
        client = "" if entry.client is None else f" on client {entry.client}"
        drain = " in the drain" if entry.drain else ""
        return f"\n  step {entry.step}{client}{drain}"
    fails = ", any value fails" if entry.any_value_fails is True else ""
    nearest = entry.nearest_passing
    passes = "" if nearest is None else f", {nearest!r} passes"
    return f"\n  {entry.label}: {entry.value!r}{fails}{passes}"


def _failure_line(what: str, failure: Failure) -> str:
    """Return the line of the record of a failed case."""
    of = f" of {failure.assertion}" if failure.assertion else ""
    where = failure.where
    at = "" if where is None else f" at {os.path.basename(where.file)}:{where.line}"
    return f"\n{what}{of}{at}: {render(failure)}"


def _replay_line(token: str) -> str:
    """Return the line that shows how to replay the case of a token."""
    return f"\nreplay: prop.replay({json.dumps(token)}) or {REPLAY_VARIABLE}={token}"


#: The text of an absent side of a divergence, by the kind of the difference.
_ABSENT = {
    "request": "no request",
    "fingerprint": "no fingerprint",
    "verdict": "a pass",
}


def _side_text(what: str, side: Any) -> str:
    """Return the text of one side of a divergence, or the words for its absence."""
    if side is None:
        return _ABSENT[what]
    return side if isinstance(side, str) else repr(side)


def sentence(failure: Failure) -> str:
    """Return the sentence of the record of a failed run.

    The sentence has the contract, the outcome with the counts and the seed,
    and a line for each part of the detail that the outcome uses. The notes
    of the failing case follow.

    Args:
        failure: The record.

    Returns:
        The sentence.
    """
    d = failure.detail
    text = (
        f"{failure.contract}: {d['outcome']} after {d['cases']} valid and "
        f"{d['rejected']} rejected cases, seed {d['seed']}"
    )
    for entry in cast("list[Entry] | None", d["counterexample"]) or []:
        text += _entry_line(entry)
    case_failure = d["failure"]
    if isinstance(case_failure, Failure):
        text += _failure_line("failure", case_failure)
    choices = d["choices"]
    if isinstance(choices, str):
        text += _replay_line(choices)
    for other in cast("list[Other] | None", d["others"]) or []:
        text += _failure_line("other failure", other.failure)
        for entry in other.counterexample:
            text += _entry_line(entry)
        text += _replay_line(other.choices)
    divergence = cast("Divergence | None", d["divergence"])
    if divergence is not None:
        label = (
            ""
            if divergence.label is None
            else f" (in the draw {json.dumps(divergence.label)})"
        )
        text += (
            f"\ndivergence: the {divergence.what} at {divergence.index}{label}, "
            f"recorded {_side_text(divergence.what, divergence.recorded)}, "
            f"replayed {_side_text(divergence.what, divergence.replayed)}"
        )
    coverage = cast("Shortfall | None", d["coverage"])
    if coverage is not None:
        text += (
            f"\ncoverage: {coverage.verdict}, {json.dumps(coverage.label)} counted "
            f"{coverage.counted} of {coverage.valid} valid cases against a required "
            f"share of {coverage.share}"
        )
    for note in _NOTES.get(id(failure), ()):
        text += f"\nnote: {note}"
    return text


def register_sentences(assertions: Iterable[str]) -> None:
    """Make sentence the sentence of the records of the assertions.

    Args:
        assertions: The ids of the assertions of the properties.
    """
    register_sentence(sentence, *assertions)
