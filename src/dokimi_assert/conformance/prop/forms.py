"""The runner of the forms vectors.

A forms vector has a form, the kinds of the subjects that the assertion of
the form takes, and the values that the assertion takes beside them. It also
has the shape or the generator of the input, the examples, the seed and the
detail of the run. The runner calls the form of this library on a recorder.
The input of each function has the type Input, and prop.using gives Input
the generator of the vector. The runner returns the detail of the call
record of the form.

A run keeps its subjects across its cases, in the same way as a closure of a
caller keeps them. Each subject behaves as the table of subjects of the
definition describes its kind.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from dokimi_assert import prop
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.engine import literal
from dokimi_assert._prop.engine.generator import Generator
from dokimi_assert.conformance.literal import decode
from dokimi_assert.conformance.prop.choices import seed_of
from dokimi_assert.conformance.prop.function import FUNCTIONS
from dokimi_assert.conformance.prop.generator import build
from dokimi_assert.conformance.subject import SUBJECTS, Subject, SubjectError
from dokimi_assert.seat import Recorder

__all__ = ["CONTRACT", "Input", "forms_of"]

_T = TypeVar("_T")

#: The contract of the run of the form of a forms vector.
CONTRACT = "the form of a forms vector"


class Input:
    """The type of the input of the functions of a forms vector.

    prop.using gives it the generator of the vector, so the form reads the
    generator from the annotation of each function.
    """


#: The failure of a subject of the error forms. error_is and error_is_not
#: take it as their target, and error_as takes its class.
_OWN = SubjectError("the subject failed for its own reason")


def _raises(_: Any) -> None:
    """Raise the failure of a subject."""
    raise SubjectError("the subject raised")


def _raises_on_negative(x: Any) -> None:
    """Raise the failure of a subject for a negative input."""
    if x < 0:
        raise SubjectError("the subject raised")


#: The predicate of each subject kind of two items, by the kind.
_PREDICATES: dict[str, Callable[[Any, Any], bool]] = {
    "ascending": lambda earlier, later: earlier <= later,
}

#: The error that each subject kind of the error forms returns for an input,
#: or None for a success, by the kind.
_FAILS: dict[str, Callable[[Any], BaseException | None]] = {
    "returns-ok": lambda _: None,
    "fails-otherwise": lambda _: _OWN,
    "fails-on-negative": lambda x: _OWN if x < 0 else None,
}

#: What each subject kind of raises and does_not_raise does with an input,
#: by the kind. It raises the failure of the subject or returns.
_RAISES: dict[str, Callable[[Any], None]] = {
    "returns-ok": lambda _: None,
    "raises": _raises,
    "raises-on-negative": _raises_on_negative,
}


@dataclass(frozen=True, slots=True)
class _Run:
    """One run of the form of a vector.

    Attributes:
        subjects: The kinds of the subjects in the order of the form.
        args: The values that the assertion takes beside the subjects.
        options: The options of the form.
    """

    subjects: list[object]
    args: list[Any]
    options: list[prop.FormOption]


def _refusal(run: _Run, index: int) -> FaultError:
    """Return the fault of the subject kind at index, which the form does not take."""
    stated = run.subjects[index] if index < len(run.subjects) else None
    return FaultError(
        f"subjects[{index}]",
        f"{json.dumps(stated)} is not a subject that the form takes",
    )


def _kind(table: Mapping[str, _T], run: _Run, index: int) -> _T:
    """Return the entry of a table for the subject kind at index of a run.

    Raises:
        FaultError: The table does not have the kind.
    """
    stated = run.subjects[index] if index < len(run.subjects) else None
    found = table.get(stated) if isinstance(stated, str) else None
    if found is None:
        raise _refusal(run, index)
    return found


def _function(run: _Run, index: int) -> Callable[[Input], Any]:
    """Return the function of the input of the subject kind at index."""
    f = _kind(FUNCTIONS, run, index)

    def function(x: Input) -> Any:
        return f(x)

    return function


def _failing(run: _Run) -> Callable[[Input], BaseException | None]:
    """Return the function of the first subject of an error form."""
    f = _kind(_FAILS, run, 0)

    def function(x: Input) -> BaseException | None:
        return f(x)

    return function


def _raising(run: _Run) -> Callable[[Input], None]:
    """Return the function of the first subject of raises and does_not_raise."""
    f = _kind(_RAISES, run, 0)

    def function(x: Input) -> None:
        f(x)

    return function


def _subject(run: _Run, *members: str) -> Subject:
    """Return the subject of the first subject kind, which has each member of members.

    Raises:
        FaultError: The kind does not exist, or its subject does not have a
            member.
    """
    build_subject = _kind(SUBJECTS, run, 0)
    built = build_subject()
    if any(getattr(built, member) is None for member in members):
        raise _refusal(run, 0)
    return built


def _call(s: Subject) -> Callable[[Input], object]:
    """Return the call of a subject as a function of the input."""
    call = cast("Callable[[Any], object]", s.call)

    def function(x: Input) -> object:
        return call(x)

    return function


def _handled(s: Subject) -> Callable[[object, Input], object]:
    """Return a function of a handle and an input that calls handled of a subject."""
    handled = cast("Callable[..., object]", s.handled)

    def function(handle: object, _input: Input) -> object:
        return handled(handle)

    return function


def _awaited(s: Subject) -> Callable[[Input], Awaitable[Any]]:
    """Return the coroutine function of a subject as a function of the input."""
    handled = cast("Callable[..., Awaitable[Any]]", s.handled)

    def function(x: Input) -> Awaitable[Any]:
        return handled(x)

    return function


def _computed(s: Subject) -> Callable[[Input], object]:
    """Return the computation of a subject as a function of the input."""
    compute = cast("Callable[[Any], object]", s.compute)

    def function(x: Input) -> object:
        return compute(x)

    return function


def _combined(s: Subject) -> Callable[[Input, Input], object]:
    """Return the combination of a subject as a function of two inputs."""
    combine = cast("Callable[[Any, Any], object]", s.combine)

    def function(a: Input, b: Input) -> object:
        return combine(a, b)

    return function


def _rendered(s: Subject) -> Callable[[Input], str]:
    """Return the rendering of a subject as a function of the input."""
    render = cast("Callable[[Any], str]", s.render)

    def function(x: Input) -> str:
        return render(x)

    return function


def _observe(s: Subject) -> Callable[[], Any]:
    """Return the observation of a subject."""
    return cast("Callable[[], Any]", s.observe)


def _pure(seat: Recorder, r: _Run, form: Callable[..., None]) -> None:
    """Run is_pure or is_not_pure on the subject of a run."""
    s = _subject(r, "call", "observe")
    form(seat, _observe(s), _call(s), CONTRACT, *r.options)


def _relation(seat: Recorder, r: _Run, form: Callable[..., None]) -> None:
    """Run is_idempotent or accumulates on the subject of a run."""
    s = _subject(r, "call", "observe")
    form(seat, _call(s), _observe(s), CONTRACT, *r.options)


def _handle(seat: Recorder, r: _Run, form: Callable[..., None]) -> None:
    """Run honours_cancellation or honours_deadline on the subject of a run."""
    form(seat, _awaited(_subject(r, "handled")), CONTRACT, *r.options)


def _combine(seat: Recorder, r: _Run, form: Callable[..., None]) -> None:
    """Run is_commutative or is_associative on the subject of a run."""
    form(seat, _combined(_subject(r, "combine")), CONTRACT, *r.options)


#: A function that calls the form of a vector on a seat.
_Driver = Callable[[Recorder, _Run], None]

#: The driver of each form that a vector runs, by the id of the form.
_DRIVERS: dict[str, _Driver] = {
    "prop-equal": lambda seat, r: prop.equal(
        seat, _function(r, 0), _function(r, 1), CONTRACT, *r.options
    ),
    "prop-not-equal": lambda seat, r: prop.not_equal(
        seat, _function(r, 0), _function(r, 1), CONTRACT, *r.options
    ),
    "prop-true": lambda seat, r: prop.is_true(
        seat, _function(r, 0), CONTRACT, *r.options
    ),
    "prop-false": lambda seat, r: prop.is_false(
        seat, _function(r, 0), CONTRACT, *r.options
    ),
    "prop-nil": lambda seat, r: prop.is_none(
        seat, _function(r, 0), CONTRACT, *r.options
    ),
    "prop-not-nil": lambda seat, r: prop.is_not_none(
        seat, _function(r, 0), CONTRACT, *r.options
    ),
    "prop-length": lambda seat, r: prop.length(
        seat, _function(r, 0), r.args[0], CONTRACT, *r.options
    ),
    "prop-empty": lambda seat, r: prop.is_empty(
        seat, _function(r, 0), CONTRACT, *r.options
    ),
    "prop-not-empty": lambda seat, r: prop.is_not_empty(
        seat, _function(r, 0), CONTRACT, *r.options
    ),
    "prop-contains": lambda seat, r: prop.contains(
        seat, _function(r, 0), r.args[0], CONTRACT, *r.options
    ),
    "prop-not-contains": lambda seat, r: prop.not_contains(
        seat, _function(r, 0), r.args[0], CONTRACT, *r.options
    ),
    "prop-contains-in-order": lambda seat, r: prop.contains_in_order(
        seat, _function(r, 0), r.args[0], CONTRACT, *r.options
    ),
    "prop-permutation": lambda seat, r: prop.is_permutation(
        seat, _function(r, 0), _function(r, 1), CONTRACT, *r.options
    ),
    "prop-has-prefix": lambda seat, r: prop.has_prefix(
        seat, _function(r, 0), r.args[0], CONTRACT, *r.options
    ),
    "prop-has-suffix": lambda seat, r: prop.has_suffix(
        seat, _function(r, 0), r.args[0], CONTRACT, *r.options
    ),
    "prop-matches": lambda seat, r: prop.matches(
        seat, _function(r, 0), r.args[0], CONTRACT, *r.options
    ),
    "prop-close-to": lambda seat, r: prop.close_to(
        seat, _function(r, 0), r.args[0], r.args[1], CONTRACT, *r.options
    ),
    "prop-in-range": lambda seat, r: prop.in_range(
        seat, _function(r, 0), r.args[0], r.args[1], CONTRACT, *r.options
    ),
    "prop-pairwise": lambda seat, r: prop.pairwise(
        seat, _function(r, 0), _kind(_PREDICATES, r, 1), CONTRACT, *r.options
    ),
    "prop-err-absent": lambda seat, r: prop.no_error(
        seat, _failing(r), CONTRACT, *r.options
    ),
    "prop-err-present": lambda seat, r: prop.has_error(
        seat, _failing(r), CONTRACT, *r.options
    ),
    "prop-err-is": lambda seat, r: prop.error_is(
        seat, _failing(r), _OWN, CONTRACT, *r.options
    ),
    "prop-err-is-not": lambda seat, r: prop.error_is_not(
        seat, _failing(r), _OWN, CONTRACT, *r.options
    ),
    "prop-err-as": lambda seat, r: prop.error_as(
        seat, _failing(r), SubjectError, CONTRACT, *r.options
    ),
    "prop-throws": lambda seat, r: prop.raises(seat, _raising(r), CONTRACT, *r.options),
    "prop-not-throws": lambda seat, r: prop.does_not_raise(
        seat, _raising(r), CONTRACT, *r.options
    ),
    "prop-pure": lambda seat, r: _pure(seat, r, prop.is_pure),
    "prop-not-pure": lambda seat, r: _pure(seat, r, prop.is_not_pure),
    "prop-nil-context-safe": lambda seat, r: prop.none_handle_safe(
        seat, _handled(_subject(r, "handled")), CONTRACT, *r.options
    ),
    "prop-honours-cancellation": lambda seat, r: _handle(
        seat, r, prop.honours_cancellation
    ),
    "prop-honours-deadline": lambda seat, r: _handle(seat, r, prop.honours_deadline),
    "prop-idempotent": lambda seat, r: _relation(seat, r, prop.is_idempotent),
    "prop-accumulates": lambda seat, r: _relation(seat, r, prop.accumulates),
    "prop-deterministic": lambda seat, r: prop.is_deterministic(
        seat, _computed(_subject(r, "compute")), CONTRACT, *r.options
    ),
    "prop-commutative": lambda seat, r: _combine(seat, r, prop.is_commutative),
    "prop-associative": lambda seat, r: _combine(seat, r, prop.is_associative),
    "prop-round-trip": lambda seat, r: prop.round_trip(
        seat, _rendered(_subject(r, "render")), int, CONTRACT, *r.options
    ),
}


def _input_of(raw: Mapping[str, Any]) -> Generator[Any]:
    """Return the generator of the input of a vector of a shape or of a generator.

    Raises:
        FaultError: The vector has both a shape and a generator, or neither.
    """
    if ("shape" in raw) == ("generator" in raw):
        raise FaultError("", "the vector has neither a shape nor a generator, or both")
    if "generator" in raw:
        return build(raw["generator"])
    return prop.of_shape(json.dumps(raw["shape"]))


def _failure_of(ours: object, theirs: object) -> object:
    """Return the failure of a record in the form of the failure of a vector.

    The form has the assertion of the record and the fields of its detail
    that the vector has.
    """
    if not isinstance(ours, dict) or not isinstance(theirs, dict):
        return ours
    record = cast("dict[str, Any]", ours)
    stated = cast("dict[str, Any]", theirs).get("detail")
    names = cast("dict[str, Any]", stated) if isinstance(stated, dict) else {}
    detail = cast("dict[str, Any]", record.get("detail", {}))
    return {
        "assertion": record.get("assertion"),
        "detail": {name: detail[name] for name in names if name in detail},
    }


def forms_of(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return the detail of the call record of the form of a vector.

    Args:
        raw: The JSON object of the vector.

    Returns:
        The output detail in the form of the detail of the vector.

    Raises:
        FaultError: The vector has a form that a vector does not run, a
            subject kind that the form does not take, neither a shape nor a
            generator, or the form ends with a fault.
    """
    form = raw.get("form")
    driver = _DRIVERS.get(form) if isinstance(form, str) else None
    if driver is None:
        raise FaultError("form", f"{json.dumps(form)} is not a form that a vector runs")
    options: list[prop.FormOption] = [
        prop.using(Input, _input_of(raw)),
        prop.seed(seed_of(raw.get("seed"))),
        prop.hermetic(),
        prop.shrink_time(0),
        prop.store(""),
    ]
    examples = cast("list[object]", raw.get("examples", []))
    if examples:
        options.append(prop.examples(*(literal.decode(e) for e in examples)))
    args = [decode(arg) for arg in cast("list[dict[str, Any]]", raw.get("args", []))]
    recorder = Recorder()
    driver(
        recorder,
        _Run(list(cast("list[object]", raw.get("subjects", []))), args, options),
    )
    record = json.loads(recorder.records[0])
    ours = record.get("detail")
    if not isinstance(ours, dict):
        error = json.dumps(record.get("error"), ensure_ascii=False)
        raise FaultError("", f"the form ends with the fault {error}")
    detail = cast("dict[str, Any]", ours)
    theirs = cast("dict[str, Any]", raw.get("detail") or {})
    failure = _failure_of(detail.get("failure"), theirs.get("failure"))
    return {"detail": {**detail, "failure": failure}}
