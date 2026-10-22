# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The runners of the history vectors.

A seam vector records a script through a History, or intervals through
from_intervals. The runner compares the events of the history in their
JSON form, or the entry that the seam refuses, with the vector. A
linearizable vector has a script that the runner checks with
is_linearizable against a named spec on a recorder. A serializable vector
and a snapshot-isolation vector have a script that the runner checks with
the check of their level. Each runner of a check compares the verdict and
the detail of the call record with the vector.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal, cast

from dokimi_assert import history
from dokimi_assert._history.event import event_json
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.history.specs import SPECS
from dokimi_assert.conformance.literal import decode, same_json
from dokimi_assert.seat import Recorder

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from dokimi_assert.conformance.files import Runner

__all__ = ["ISOLATION_CONTRACT", "LINEARIZABLE_CONTRACT", "RUNNERS"]

#: The contract of the check of a linearizable vector.
LINEARIZABLE_CONTRACT = "the history of the vector is linearizable"

#: The contract of the check of an isolation vector.
ISOLATION_CONTRACT = "the transactions of the vector are isolated"

#: The kinds that complete the call of an interval.
_COMPLETIONS = frozenset({"ok", "fail", "unknown"})

#: The options of a check that a vector can have, by the member of the vector.
_OPTIONS: dict[str, Callable[[int], history.Option]] = {
    "budget": history.budget,
    "memo-limit": history.memo_limit,
    "workers": history.workers,
}


def _value(raw: object, member: str) -> Any:
    """Return the value of a typed literal.

    Raises:
        FaultError: The literal does not decode. The fault is at member.
    """
    try:
        return decode(cast("Mapping[str, Any]", raw))
    except Exception as error:
        raise FaultError(member, "the value is not a typed literal", error) from error


def _values(raw: object, member: str) -> list[Any]:
    """Return the values of a list of typed literals.

    Raises:
        FaultError: The member is not a list, or a literal does not decode.
    """
    if not isinstance(raw, list):
        raise FaultError(member, "the member is not a list")
    items = cast("list[object]", raw)
    return [_value(item, f"{member}[{i}]") for i, item in enumerate(items)]


def _refuses(apply: Callable[[], None]) -> bool:
    """Report whether a call of the seam raises."""
    try:
        apply()
    except Exception:
        return True
    return False


def _record(script: object, member: str) -> tuple[history.History, int | None]:
    """Record a script through a history.

    The result is the history, and the entry whose call of the seam raises,
    or None when the seam does not refuse an entry. The runner does not
    record an entry after the refused one.

    Raises:
        FaultError: The script is not a list, an entry does not have a call
            of the seam, or an entry completes a call that the script does
            not open.
    """
    if not isinstance(script, list):
        raise FaultError(member, "the script is not a list")
    recorded = history.History()
    calls: dict[object, history.Call] = {}
    for i, entry in enumerate(cast("list[dict[str, Any]]", script)):
        if _refuses(_call_of(entry, f"{member}[{i}]", recorded, calls)):
            return recorded, i
    return recorded, None


def _call_of(
    entry: Mapping[str, Any],
    at: str,
    recorded: history.History,
    calls: dict[object, history.Call],
) -> Callable[[], None]:
    """Return the call of the seam of one entry of a script.

    An invocation keeps its call in calls under the number of the entry. A
    completion completes the call of its number.

    Raises:
        FaultError: The entry does not have a call of the seam, a value is
            not a typed literal, or the entry completes a call that is not
            open. The fault is at the entry.
    """
    if "invoke" in entry:
        args = _values(entry.get("args"), f"{at}.args")
        keys = _values(entry.get("keys"), f"{at}.keys")

        def invoke() -> None:
            calls[entry["invoke"]] = recorded.invoke(
                cast("int", entry.get("client")),
                cast("str", entry.get("operation")),
                args,
                *keys,
            )

        return invoke
    kind = next((k for k in ("ok", "fail", "unknown") if k in entry), None)
    if kind is None:
        raise FaultError(at, "the entry does not have a call of the seam")
    call = calls.get(entry[kind])
    if call is None:
        raise FaultError(
            at, f"the entry completes the call {entry[kind]}, which is not open"
        )
    if kind == "ok":
        output = _value(entry.get("output"), f"{at}.output")
        return lambda: call.ok(output)
    complete = call.fail if kind == "fail" else call.unknown
    error = entry.get("error")
    return lambda: complete(error)


def _interval_of(raw: Mapping[str, Any], member: str) -> history.Interval:
    """Return the interval of one entry of a seam vector.

    Raises:
        FaultError: The entry has a kind without an end, an end without a
            kind, or a kind that does not complete a call.
    """
    kind = raw.get("kind")
    end = raw.get("end")
    if (end is None) != (kind is None) or (
        kind is not None and kind not in _COMPLETIONS
    ):
        raise FaultError(
            member,
            "the entry has a kind without an end, an end without a kind, or a kind "
            "that does not complete a call",
        )
    ok = kind == "ok"
    return history.Interval(
        client=cast("int", raw.get("client")),
        operation=cast("str", raw.get("operation")),
        args=_values(raw.get("args"), f"{member}.args"),
        keys=_values(raw.get("keys"), f"{member}.keys"),
        start=cast("float", raw.get("start")),
        end=cast("float | None", end),
        kind=cast("Literal['ok', 'fail', 'unknown'] | None", kind),
        output=_value(raw.get("output"), f"{member}.output") if ok else None,
        error=None if ok else raw.get("error"),
    )


def _intervals(raw: object) -> tuple[history.History | None, int | None]:
    """Return the history of the intervals of a vector and its refused entry.

    Raises:
        FaultError: The intervals are not a list, or an entry is not an
            interval.
    """
    if not isinstance(raw, list):
        at = "intervals"
        raise FaultError(at, "the intervals are not a list")
    entries = [
        _interval_of(entry, f"intervals[{i}]")
        for i, entry in enumerate(cast("list[dict[str, Any]]", raw))
    ]
    try:
        return history.from_intervals(entries), None
    except history.IntervalError as error:
        return None, error.entry


def _check_seam(raw: Mapping[str, Any], _: str) -> None:
    """Compare the events or the refusal of the seam with a seam vector.

    Raises:
        FaultError: The vector does not have exactly one of a script and
            intervals, the seam refuses another entry than the vector, or an
            event differs from the event of the vector.
    """
    if ("script" in raw) == ("intervals" in raw):
        at = ""
        raise FaultError(at, "the vector has neither a script nor intervals, or both")
    recorded: history.History | None
    if "script" in raw:
        recorded, refused = _record(raw["script"], "script")
    else:
        recorded, refused = _intervals(raw["intervals"])
    want = raw.get("refused")
    if refused != want:
        got = "no entry" if refused is None else f"entry {refused}"
        at = "refused"
        raise FaultError(at, f"the seam refuses {got}, want {json.dumps(want)}")
    if recorded is None or refused is not None:
        return
    events = [event_json(event) for event in recorded.events()]
    stated = raw.get("events")
    if not isinstance(stated, list):
        at = "events"
        raise FaultError(at, "the events are not a list")
    wanted = cast("list[object]", stated)
    for i, (event, expected) in enumerate(zip(events, wanted, strict=False)):
        if not same_json(event, expected):
            at = f"events[{i}]"
            raise FaultError(
                at,
                f"the event is {json.dumps(event)}, want {json.dumps(expected)}",
            )
    if len(events) != len(wanted):
        at = "events"
        raise FaultError(
            at, f"the number of events is {len(events)}, want {len(wanted)}"
        )


def _history_of(raw: Mapping[str, Any]) -> history.History:
    """Return the history of the script of a check vector.

    Raises:
        FaultError: The seam refuses an entry of the script.
    """
    recorded, refused = _record(raw.get("history"), "history")
    if refused is not None:
        at = f"history[{refused}]"
        raise FaultError(at, "the seam refuses the entry")
    return recorded


def _record_of(check: Callable[[Recorder], None]) -> dict[str, Any]:
    """Return the call record of a check on a recorder, parsed."""
    recorder = Recorder()
    check(recorder)
    record: dict[str, Any] = json.loads(recorder.records[0])
    return record


def _compare_verdict(call: Mapping[str, Any], raw: Mapping[str, Any]) -> None:
    """Compare the verdict and the detail of a call record with a vector.

    Raises:
        FaultError: The vector expects neither a pass nor a failure, the
            verdict differs, or a field of the detail of the vector differs.
    """
    expect = raw.get("expect")
    if expect not in ("pass", "fail"):
        at = "expect"
        raise FaultError(
            at, f"the vector expects {json.dumps(expect)}, neither pass nor fail"
        )
    if call["verdict"] != expect:
        error = f" ({call['error']})" if "error" in call else ""
        at = "expect"
        raise FaultError(
            at, f"the check ends as {call['verdict']}{error}, want {expect}"
        )
    if expect == "pass":
        return
    detail = cast("dict[str, Any]", call.get("detail", {}))
    stated = cast("dict[str, Any]", raw.get("detail", {}))
    for name in sorted(stated):
        if name not in detail:
            at = f"detail.{name}"
            raise FaultError(
                at,
                f"the record does not have the field, want {json.dumps(stated[name])}",
            )
        if not same_json(detail[name], stated[name]):
            at = f"detail.{name}"
            raise FaultError(
                at,
                f"the field is {json.dumps(detail[name])}, "
                f"want {json.dumps(stated[name])}",
            )


def _options_of(raw: Mapping[str, Any]) -> list[history.Option]:
    """Return the options of a check of a vector.

    Raises:
        FaultError: An option is not an int of 1 or more.
    """
    options: list[history.Option] = []
    for member, option in _OPTIONS.items():
        n = raw.get(member)
        if n is None:
            continue
        if type(n) is not int or n < 1:
            raise FaultError(
                member, f"the {member} is {json.dumps(n)}, not an int of 1 or more"
            )
        options.append(option(n))
    return options


#: The fewest steps of a passing linearizable vector. The runner checks it
#: under a budget of one step less, and a budget has one step at least.
_LEAST_STEPS = 2


def _check_linearizable(raw: Mapping[str, Any], _: str) -> None:
    """Check the history of a linearizable vector against its named spec.

    The runner compares the call record with the vector. A passing check
    does not have a detail, so the runner observes the steps of a passing
    vector through two more checks. The check passes under a budget of
    those steps. Under a budget of one step less, it ends undecided at the
    limit of the steps after that budget.

    Raises:
        FaultError: The named spec does not exist, the call record differs
            from the vector, or a check under a budget does not end as the
            steps of the vector need.
    """
    spec = SPECS.get(cast("str", raw.get("spec")))
    if spec is None:
        at = "spec"
        raise FaultError(at, f"{json.dumps(raw.get('spec'))} is not a named spec")
    recorded = _history_of(raw)
    options = _options_of(raw)

    def checked(*more: history.Option) -> dict[str, Any]:
        return _record_of(
            lambda seat: history.is_linearizable(
                seat, recorded, spec, LINEARIZABLE_CONTRACT, *options, *more
            )
        )

    _compare_verdict(checked(), raw)
    if raw.get("expect") == "fail":
        return
    stated = cast("dict[str, Any]", raw.get("detail", {}))
    steps = stated.get("steps")
    if stated.get("partitions") != 1 or type(steps) is not int or steps < _LEAST_STEPS:
        at = "detail"
        raise FaultError(
            at,
            "the runner observes the steps of a pass over one partition in two steps "
            f"or more, and the vector has the partitions "
            f"{json.dumps(stated.get('partitions'))} and the steps {json.dumps(steps)}",
        )
    exact = checked(history.budget(steps))
    if exact["verdict"] != "pass":
        at = "detail.steps"
        raise FaultError(
            at,
            f"the check ends as {exact['verdict']} within {steps} steps, want pass",
        )
    under = checked(history.budget(steps - 1))
    detail = cast("dict[str, Any]", under.get("detail", {}))
    want = {
        "outcome": "undecided",
        "partitions": 1,
        "steps": steps - 1,
        "limit": "steps",
    }
    got = {name: detail.get(name) for name in want}
    if under["verdict"] != "fail" or not same_json(got, want):
        at = "detail.steps"
        raise FaultError(
            at,
            f"the check within {steps - 1} steps ends as {under['verdict']} with "
            f"{json.dumps(got)}, want {json.dumps(want)}",
        )


def _check_isolation(check: Callable[[Recorder, history.History, str], None]) -> Runner:
    """Return the runner of the isolation vectors of a check."""

    def run(raw: Mapping[str, Any], _: str) -> None:
        recorded = _history_of(raw)
        _compare_verdict(
            _record_of(lambda seat: check(seat, recorded, ISOLATION_CONTRACT)), raw
        )

    return run


#: The runner of each kind of history vector, by the kind. A runner raises a
#: fault at the part of the vector that the run contradicts, and for a vector
#: that it cannot read.
RUNNERS: dict[str, Runner] = {
    "seam": _check_seam,
    "linearizable": _check_linearizable,
    "serializable": _check_isolation(history.is_serializable),
    "snapshot-isolation": _check_isolation(history.has_snapshot_isolation),
}
