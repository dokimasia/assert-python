# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The entries that a property writes to its store and checks on a replay.

A property writes one entry for each failure of a counterexample. The entry
has the identity of the failure, the choices of the minimal case, and each
draw with the typed literal of its value in the type of its generator. A draw
whose value does not have a typed literal has only its label in the entry.

A stored case replays its choices, so after a change of a generator it can
decode to values that differ from its entry. The run then tested those
values, and the property notes the difference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dokimi_assert._prop.engine import literal, store
from dokimi_assert._prop.engine.value import canonical
from dokimi_assert._prop.identity import entry_of as identity_entry
from dokimi_assert._prop.literal import drawn_literal
from dokimi_assert._record.call import DEFINITION

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from dokimi_assert._prop.case import Failing
    from dokimi_assert._prop.engine.case import Drawn, Failed
    from dokimi_assert._prop.engine.execution import Execution

__all__ = ["differs", "entry_of"]


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
        _draws_of(execution.case.draws),
    )
    return store.name(contract, choices), store.entry(failure, DEFINITION, found)


def _literal_key(written: object) -> str | None:
    """Return the canonical text of a decoded literal, or None when it is invalid."""
    try:
        return canonical(literal.decode(written))
    except literal.LiteralError:
        return None


def differs(recorded: Sequence[Mapping[str, Any]], replayed: Execution) -> bool:
    """Report whether the values of a replayed case differ from its entry.

    The replay differs when it has different labels, a different number of
    draws, or a different value of a draw with a value in the entry. Two
    values are the same when their typed literals decode to one value, so the
    spelling of a number in a file of another implementation does not count.
    A -0.0 in the entry differs from a replayed 0.0. A value of the entry that
    does not decode differs from every value.

    Args:
        recorded: The draws of the entry.
        replayed: The run of the stored case.

    Returns:
        True when the two differ.
    """
    draws = _draws_of(replayed.case.draws)
    if len(recorded) != len(draws):
        return True
    for entry, draw in zip(recorded, draws, strict=True):
        if entry.get("label") != draw["label"]:
            return True
        if "value" not in entry:
            continue
        value = _literal_key(entry["value"])
        if value is None or "value" not in draw or value != _literal_key(draw["value"]):
            return True
    return False
