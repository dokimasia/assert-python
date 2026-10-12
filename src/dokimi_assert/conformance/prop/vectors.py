"""The runners of the property vectors.

Each kind of property vector has a function that takes the inputs of a
vector and returns the outputs that this library computes for them. A
runner compares each output with the output of the vector as JSON. It
raises a fault at the first output that differs.

The kinds of the engine run on the engine itself: decoding, generation,
shapes, inverse, draws, shrinking, coverage, bridge, token and store. A
behaviour vector and a recording vector run their body with prop.for_all on
a recorder, so they check the record and the call records of this library.
A forms vector runs a property form, and a fixtures vector reads a fixture
type with prop.shape_of.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from typing import Any, cast

from dokimi_assert import check, prop
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.directory import save
from dokimi_assert._prop.engine import coverage, literal, shape, store, tokens
from dokimi_assert._prop.engine.bridge import Bridging
from dokimi_assert._prop.engine.case import Case, Generating, Rejected, Replaying
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.generator import Generator
from dokimi_assert._prop.engine.inverse import inverse_of
from dokimi_assert._prop.engine.runner import Settings, run
from dokimi_assert._prop.engine.shrink import DEFAULT_BUDGET
from dokimi_assert._prop.engine.source import case_source
from dokimi_assert._prop.engine.traces import Draw, TraceError
from dokimi_assert.conformance.definition import version
from dokimi_assert.conformance.literal import same_json
from dokimi_assert.conformance.prop.body import DRAWN, body_of
from dokimi_assert.conformance.prop.choices import (
    choice_literal,
    parse_choices,
    seed_of,
)
from dokimi_assert.conformance.prop.detail import detail_of
from dokimi_assert.conformance.prop.fixture import fixtures_of
from dokimi_assert.conformance.prop.forms import forms_of
from dokimi_assert.conformance.prop.generator import build
from dokimi_assert.conformance.prop.predicate import predicate
from dokimi_assert.failure import Failure
from dokimi_assert.seat import Recorder

__all__ = ["CONTRACT", "KINDS", "check_prop"]

#: The contract of the property of a behaviour vector and of a recording
#: vector. The stored cases of a vector are entries of this property.
CONTRACT = "the property of the vector"

#: The contract of the call of true that ends the body of a recording vector.
_END = "the body of the recording vector passes"

#: The identity of the failure of the body of a shrinking vector.
_FAILS_WHEN = "fails-when"

#: The identity of the entry of each stored case, and the date on which the
#: first stored case was found. Each later case was found a day later, so
#: the run tries the cases in the order of the vector.
_STORED = {"assertion": "stored", "contract": "a stored case of the vector"}
_FIRST_FOUND = date(2026, 1, 1)

#: The settings that a behaviour vector and a recording vector can have.
_SETTINGS = frozenset(
    {
        "seed",
        "cases",
        "max-choices",
        "requirements",
        "examples",
        "stored",
        "shrink",
        "replay",
        "workers",
    }
)

#: A function that returns the outputs that this library computes for the
#: inputs of a vector. It takes the vector and a directory of its own.
Compute = Callable[[Mapping[str, Any], str], dict[str, Any]]


def _recorded(c: Case) -> list[object]:
    """Return the recorded choices of a case in the form of a vector."""
    return [choice_literal(choice) for choice in c.choices]


def _decoded(c: Case, generator: Generator[Any]) -> dict[str, Any]:
    """Return the recorded choices and the value of a decode, or its rejection."""
    try:
        value = generator.decode(c)
    except Rejected:
        return {"recorded": _recorded(c), "value": None, "rejected": True}
    return {"recorded": _recorded(c), "value": literal.encode(value), "rejected": False}


def _generated(generator: Generator[Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return the choices and the value of each of the first cases of a seed."""
    seed = seed_of(raw.get("seed"))
    cases: list[dict[str, Any]] = []
    for index in range(cast("int", raw.get("count"))):
        c = Case(Generating(case_source(seed, index)))
        decoded = _decoded(c, generator)
        cases.append({"choices": decoded.pop("recorded"), **decoded})
    return {"cases": cases}


def _generator_of(raw: Mapping[str, Any]) -> Generator[Any]:
    """Return the generator of a vector of a shape or of a generator.

    Raises:
        FaultError: The vector has both a shape and a generator, or neither.
    """
    if ("shape" in raw) == ("generator" in raw):
        raise FaultError("", "the vector has neither a shape nor a generator, or both")
    if "shape" in raw:
        return shape.read(raw["shape"])
    return build(raw["generator"])


def _decoding(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the outputs of a decoding vector."""
    generator = build(raw.get("generator"))
    return _decoded(Case(Replaying(parse_choices(raw.get("choices")))), generator)


def _inverse(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the outputs of an inverse vector."""
    choices = inverse_of(_generator_of(raw), literal.decode(raw.get("value")))
    if choices is None:
        return {"choices": None, "error": True}
    return {"choices": [choice_literal(c) for c in choices], "error": False}


def _draws(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the outputs of a draws vector.

    A body of the draws of the vector runs under a trace of its entries. The
    choices are the inverse of each entry under the generator of its draw.
    """
    stated = cast("list[dict[str, Any]]", raw.get("draws"))
    draws = [(str(d.get("label")), build(d.get("generator"))) for d in stated]
    entries = tuple(
        Draw(str(e.get("label")), literal.decode(e.get("value")))
        for e in cast("list[dict[str, Any]]", raw.get("entries"))
    )
    drawn: list[list[object]] = []

    def body(c: Case) -> None:
        values = [c.draw(generator, label) for label, generator in draws]
        if not drawn:
            drawn.append(values)

    try:
        run(body, Settings(seed=0, cases=1, traces=(entries,)))
    except TraceError as error:
        refused = {"label": error.what, "reason": error.reason}
        return {"choices": None, "values": None, "error": refused}
    choices = [
        choice
        for (_, generator), entry in zip(draws, entries, strict=False)
        for choice in inverse_of(generator, entry.value) or []
    ]
    values = [
        {"label": label, "value": literal.encode(value)}
        for (label, _), value in zip(draws, drawn[0], strict=True)
    ]
    return {
        "choices": [choice_literal(c) for c in choices],
        "values": values,
        "error": None,
    }


def _shrinking(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the outcome of the run of a shrinking vector.

    The body draws one value and fails when the predicate fails-when is
    true for it.
    """
    generator = build(raw.get("generator"))
    fails = predicate(raw.get("fails-when"))

    def body(c: Case) -> None:
        if fails(c.draw(generator, DRAWN)):
            c.fail(_FAILS_WHEN)

    budget = raw.get("budget", DEFAULT_BUDGET)
    outcome = run(body, Settings(seed=seed_of(raw.get("seed")), shrink=budget))
    failing = outcome.failing
    return {
        "outcome": outcome.kind,
        "cases": outcome.cases,
        "value": None
        if failing is None
        else literal.encode(failing.case.draws[0].value),
        "choices": None if failing is None else _recorded(failing.case),
        "token": outcome.token,
        "runs": outcome.runs,
    }


def _coverage(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the verdict of a coverage vector."""
    verdict = coverage.verdict(
        cast("int", raw.get("counted")),
        cast("int", raw.get("valid")),
        cast("float", raw.get("share")),
        raw.get("last") is True,
        raw.get("exact") is True,
    )
    return {"verdict": verdict}


def _bridge(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the outputs of a bridge vector."""
    generator = build(raw.get("generator"))
    c = Case(Bridging(bytes.fromhex(cast("str", raw.get("bytes")))))
    decoded = _decoded(c, generator)
    return {"choices": decoded.pop("recorded"), **decoded}


def _token(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the token of the choices of a token vector, or the decode of its token."""
    if "choices" in raw:
        return {"token": tokens.encode(parse_choices(raw["choices"]))}
    try:
        decoded = tokens.decode(cast("str", raw.get("token")))
    except ValueError:
        return {"decoded": None, "error": True}
    return {"decoded": [choice_literal(c) for c in decoded], "error": False}


def _store(raw: Mapping[str, Any], _: str) -> dict[str, Any]:
    """Return the verdict on the text of a store vector, or the entry that it writes.

    Raises:
        FaultError: The entry does not read back as a replay of its choices.
    """
    contract = cast("str", raw.get("contract"))
    if "text" in raw:
        read = store.read(cast("str", raw["text"]), contract)
        replay = read.verdict == "replay"
        replayed = [choice_literal(c) for c in read.choices] if replay else None
        return {"verdict": read.verdict, "choices": replayed}
    choices = parse_choices(raw.get("choices"))
    failure = store.Failure(
        contract,
        choices,
        cast("dict[str, Any]", raw.get("identity")),
        cast("list[dict[str, Any]]", raw.get("counterexample")),
    )
    written = store.entry(
        failure, cast("str", raw.get("definition")), cast("str", raw.get("found"))
    )
    back = store.read(json.dumps(written), contract)
    if back.verdict != "replay" or tokens.encode(back.choices) != tokens.encode(
        choices
    ):
        raise FaultError(
            "entry", "the entry does not read back as a replay of its choices"
        )
    return {"name": store.name(contract, choices), "entry": written}


def _drawn(choices: list[Choice], spec: object, at: str) -> dict[str, Any]:
    """Return the draw of a body spec whose value the choices decode to.

    The draw has the label value and the typed literal of the value.

    Raises:
        FaultError: The body does not have a draw, or the choices do not
            decode to a value. The fault is at at.
    """
    draw = cast("dict[str, Any]", spec).get("draw")
    if draw is None:
        raise FaultError(at, "the body does not draw a value")
    decoded = _decoded(Case(Replaying(choices)), build(draw))
    if decoded["rejected"]:
        raise FaultError(at, "the choices do not decode to a value")
    return {"label": DRAWN, "value": decoded["value"]}


def _write_stored(stored: object, dir: str, spec: object) -> None:
    """Write each stored case of the settings of a vector into the store dir.

    The entry of a case is an entry of the property of the vector, with the
    draw that its choices decode to under the body spec.

    Raises:
        FaultError: The body does not have a draw, or the choices of a case
            do not decode to a value.
    """
    for i, written in enumerate(cast("list[object]", stored)):
        choices = parse_choices(written)
        drawn = _drawn(choices, spec, f"settings.stored[{i}]")
        failure = store.Failure(CONTRACT, choices, _STORED, [drawn])
        found = (_FIRST_FOUND + timedelta(days=i)).isoformat()
        save(dir, store.name(CONTRACT, choices), store.entry(failure, version(), found))


def _example_of(examples: object, spec: object) -> prop.Option:
    """Return the option draws of the one example of the settings of a vector.

    The value of its entry is the value that the choices of the example
    decode to under the draw of the body.

    Raises:
        FaultError: The settings have more than one example, the body does
            not have a draw, or the choices do not decode to a value.
    """
    listed = cast("list[object]", examples)
    if len(listed) != 1:
        raise FaultError(
            "settings.examples",
            f"the settings have {len(listed)} examples, and a run follows one trace",
        )
    drawn = _drawn(parse_choices(listed[0]), spec, "settings.examples[0]")
    return prop.draws(json.dumps([drawn]))


def _options_of(settings: object, dir: str, spec: object) -> list[Any]:
    """Return the options of the run of a vector, and write its stored cases into dir.

    The run is hermetic, so the variables of the engine do not change it.
    Shrinking does not have a time limit. The store of the run is dir.

    Raises:
        FaultError: The settings have a setting that the runner does not
            take, or an example that the runner cannot follow.
        ValueError: The settings are not an object, or a setting is not
            valid.
    """
    if not isinstance(settings, dict):
        raise ValueError(f"prop: the settings {json.dumps(settings)} are not an object")
    written = cast("dict[str, Any]", settings)
    for name in sorted(written):
        if name not in _SETTINGS:
            raise FaultError(f"settings.{name}", "the runner does not take the setting")
    options: list[Any] = [
        prop.seed(seed_of(written.get("seed"))),
        prop.hermetic(),
        prop.shrink_time(0),
        prop.store(dir),
    ]
    plain = {
        "cases": prop.cases,
        "max-choices": prop.max_choices,
        "shrink": prop.shrink,
        "workers": prop.workers,
    }
    options.extend(
        option(written[name]) for name, option in plain.items() if name in written
    )
    for requirement in cast("list[dict[str, Any]]", written.get("requirements", [])):
        options.append(prop.require(requirement["label"], requirement["share"]))
    if "replay" in written:
        options.append(prop.replay(written["replay"]))
    if "examples" in written:
        options.append(_example_of(written["examples"], spec))
    _write_stored(written.get("stored", []), dir, spec)
    return options


def _failing(c: prop.Case, failure: str | None) -> None:
    """End the case of a behaviour vector with an aborting record of its failure."""
    if failure is not None:
        c.report(Failure(failure, ""), True)


def _asserting(c: prop.Case, failure: str | None) -> None:
    """End the case of a recording vector with one call of true.

    A failing case first keeps a record of its identity, so the identity of
    the failure of the case is the identity of the vector.
    """
    if failure is not None:
        c.report(Failure(failure, ""), False)
    check.is_true(c, failure is None, _END)


def _records_of(recorder: Recorder) -> list[dict[str, Any]]:
    """Return the call records of a recorder, parsed."""
    return [json.loads(record) for record in recorder.records]


def _behaviour(raw: Mapping[str, Any], dir: str) -> dict[str, Any]:
    """Return the detail of the call record of the run of a behaviour vector."""
    spec = raw.get("body")
    body = body_of(spec, _failing)
    recorder = Recorder()
    prop.for_all(recorder, CONTRACT, body, *_options_of(raw.get("settings"), dir, spec))
    return {"detail": detail_of(_records_of(recorder)[0])}


def _recording(raw: Mapping[str, Any], dir: str) -> dict[str, Any]:
    """Return the verdict of the property of a recording vector.

    The runner compares the calls of true in the body with the calls of the
    vector. A call of true has the run of the body that made it, the phase
    of the run and the verdict of true. The call at position i from 0 has
    the seq i + 2, and its parent is the property, whose seq is 1.

    Raises:
        FaultError: The calls of true differ from the calls of the vector.
    """
    spec = raw.get("body")
    body = body_of(spec, _asserting)
    recorder = Recorder()
    prop.for_all(recorder, CONTRACT, body, *_options_of(raw.get("settings"), dir, spec))
    first, *calls = _records_of(recorder)
    names = ("seq", "parent", "run", "phase", "verdict")
    got = [{name: call.get(name) for name in names} for call in calls]
    want = [
        {"seq": i + 2, "parent": 1, **call}
        for i, call in enumerate(cast("list[dict[str, Any]]", raw.get("calls")))
    ]
    if not same_json(got, want):
        raise FaultError(
            "calls", f"the library records {json.dumps(got)}, want {json.dumps(want)}"
        )
    return {"verdict": first["verdict"]}


#: The function that computes the outputs of each kind, by the kind.
KINDS: dict[str, Compute] = {
    "decoding": _decoding,
    "generation": lambda raw, _: _generated(build(raw.get("generator")), raw),
    "shapes": lambda raw, _: _generated(shape.read(raw.get("shape")), raw),
    "inverse": _inverse,
    "draws": _draws,
    "shrinking": _shrinking,
    "coverage": _coverage,
    "bridge": _bridge,
    "token": _token,
    "behaviour": _behaviour,
    "store": _store,
    "recording": _recording,
    "forms": lambda raw, _: forms_of(raw),
    "fixtures": lambda raw, _: fixtures_of(raw),
}


def check_prop(kind: str, raw: Mapping[str, Any], dir: str) -> None:
    """Run a property vector, and compare each output with the output of the vector.

    Args:
        kind: The kind of the vector. It is a key of KINDS.
        raw: The JSON object of the vector.
        dir: A new empty directory of the vector. A behaviour vector and a
            recording vector write their stored cases there.

    Raises:
        FaultError: An output differs from the output of the vector, or the
            runner cannot take an input of the vector. The fault is at the
            member of the vector.
    """
    try:
        outputs = KINDS[kind](raw, dir)
    except FaultError:
        raise
    except Exception as error:
        raise FaultError("", "the vector does not run", error) from error
    for name, got in outputs.items():
        want = raw.get(name)
        if not same_json(got, want):
            raise FaultError(
                name,
                f"the library computes {json.dumps(got)}, want {json.dumps(want)}",
            )
