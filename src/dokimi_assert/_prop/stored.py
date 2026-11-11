# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The entries that a property writes to its store and checks on a replay.

A property writes one entry for each failure of a counterexample. The entry
has the identity of the failure, the choices of the minimal case, and the
draws and the steps of the case in request order. A draw has the typed
literal of its value in the type of its generator. A draw whose value does
not have a typed literal has only its label in the entry. A step of a
machine has its action, its client and its drain mark. The entry of a case
with a step is of format 2.

A stored case replays its choices, so after a change of a generator or of
the actions of a machine it can decode to values that differ from its entry.
The run then follows the counterexample of the entry as a trace, and the
property notes the difference.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, cast

from dokimi_assert._prop.engine import literal, store
from dokimi_assert._prop.engine.case import Step
from dokimi_assert._prop.engine.runner import Stored
from dokimi_assert._prop.engine.traces import UNSTATED, Draw, Entry, entries
from dokimi_assert._prop.engine.value import canonical
from dokimi_assert._prop.identity import entry_of as identity_entry
from dokimi_assert._prop.literal import drawn_literal
from dokimi_assert._record.call import DEFINITION

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from dokimi_assert._prop.case import Failing
    from dokimi_assert._prop.engine.case import Case, Drawn, Failed
    from dokimi_assert._prop.engine.choice import Choice
    from dokimi_assert._prop.engine.execution import Execution

__all__ = ["differs", "entry_of", "stored_of", "trace_of"]


def _draws_of(draws: Sequence[Drawn]) -> list[dict[str, Any]]:
    """Return each draw in the form of an entry.

    A draw has its label, and the typed literal of its value when the value
    has one.
    """
    recorded: list[dict[str, Any]] = []
    for drawn in draws:
        value = drawn_literal(drawn.generator, drawn.value)
        recorded.append(
            {"label": drawn.label}
            if value is None
            else {"label": drawn.label, "value": value}
        )
    return recorded


def _step_of(step: Step) -> dict[str, Any]:
    """Return a step of a machine in the form of an entry.

    The step has its action, the client of a concurrent section and the drain
    mark of the drain.
    """
    recorded: dict[str, Any] = {"step": step.action}
    if step.client is not None:
        recorded["client"] = step.client
    if step.drain:
        recorded["drain"] = True
    return recorded


def _recorded_of(c: Case) -> list[dict[str, Any]]:
    """Return the draws and the steps of a case in the form of an entry.

    The entries are in request order.
    """
    draws = iter(_draws_of(c.draws))
    return [
        _step_of(entry) if isinstance(entry, Step) else next(draws)
        for entry in entries(c)
    ]


def entry_of(
    contract: str, execution: Execution, found: str
) -> tuple[str, dict[str, Any]]:
    """Return the file name and the entry of a failing case of a property.

    Args:
        contract: The contract of the property.
        execution: The failing execution of a minimal case.
        found: The UTC date of the failure in the form YYYY-MM-DD.

    Returns:
        The name of the file of the entry, and the entry as a JSON object.
    """
    choices = execution.case.choices
    failing = cast("Failing", cast("Failed", execution.failure).record)
    failure = store.Failure(
        contract,
        choices,
        identity_entry(failing.identity),
        _recorded_of(execution.case),
    )
    return store.name(contract, choices), store.entry(failure, DEFINITION, found)


def _literal_key(written: object) -> str | None:
    """Return the canonical text of a decoded literal, or None when it is invalid."""
    try:
        return canonical(literal.decode(written))
    except literal.LiteralError:
        return None


def _item_differs(entry: Mapping[str, Any], item: Mapping[str, Any]) -> bool:
    """Report whether one entry of a replayed case differs from the entry of a store.

    Two steps differ in their actions, their clients or their drain marks. A
    step differs from every draw.
    """
    if "step" in entry or "step" in item:
        return dict(entry) != dict(item)
    if entry.get("label") != item["label"]:
        return True
    if "value" not in entry:
        return False
    value = _literal_key(entry["value"])
    return value is None or "value" not in item or value != _literal_key(item["value"])


def differs(recorded: Sequence[Mapping[str, Any]], replayed: Execution) -> bool:
    """Report whether the values of a replayed case differ from its entry.

    The replay differs when it has different labels, a different number of
    draws, or a different value of a draw with a value in the entry. An entry
    with a step also differs from a replay with other steps, or with its
    steps at other places among its draws. The steps of the replay do not
    count against an entry without a step. Two values are the same when their
    typed literals decode to one value, so the spelling of a number in a file
    of another implementation does not count. A -0.0 in the entry differs
    from a replayed 0.0. A value of the entry that does not decode differs
    from every value.

    Args:
        recorded: The counterexample of the entry.
        replayed: The run of the stored case.

    Returns:
        True when the two differ.
    """
    replay = _recorded_of(replayed.case)
    if not any("step" in entry for entry in recorded):
        replay = [item for item in replay if "step" not in item]
    if len(recorded) != len(replay):
        return True
    return any(
        _item_differs(entry, item) for entry, item in zip(recorded, replay, strict=True)
    )


def _trace_entry(item: Mapping[str, Any]) -> Entry:
    """Return one entry of the counterexample of an entry as an entry of a trace."""
    if "step" in item:
        return Step(item["step"], item.get("client"), item.get("drain") is True)
    try:
        value = literal.decode(item["value"]) if "value" in item else UNSTATED
    except literal.LiteralError:
        value = UNSTATED
    return Draw(item["label"], value)


def trace_of(recorded: Sequence[Mapping[str, Any]]) -> tuple[Entry, ...]:
    """Return the counterexample of an entry as a trace.

    A draw without a value has the value UNSTATED. A draw whose value does
    not decode has it too. The body refuses such a draw.

    Args:
        recorded: The counterexample of the entry.

    Returns:
        The entries of the trace in request order.
    """
    return tuple(_trace_entry(item) for item in recorded)


def _matches(recorded: Sequence[Mapping[str, Any]], replayed: Execution) -> bool:
    """Report whether a replayed case decodes to the counterexample of its entry."""
    return not differs(recorded, replayed)


def stored_of(
    choices: Sequence[Choice], recorded: Sequence[Mapping[str, Any]]
) -> Stored:
    """Return the stored case of an entry.

    A case of the choices matches the entry when its values do not differ
    from the counterexample. After any other case of the choices, the run
    follows the counterexample as a trace.

    Args:
        choices: The choices of the entry.
        recorded: The counterexample of the entry.

    Returns:
        The stored case.
    """
    return Stored(tuple(choices), trace_of(recorded), partial(_matches, recorded))
