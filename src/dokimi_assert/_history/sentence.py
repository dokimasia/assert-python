# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The sentences of the records of the history assertions.

A seat that does not take records receives the sentence of a record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dokimi_assert._history.derivation import Edge, Evidence, Observation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dokimi_assert._history.partition import Span
    from dokimi_assert.failure import Failure

__all__ = ["isolation_sentence", "sentence"]


def _keys_text(keys: Sequence[Any]) -> str:
    """Return the text of the keys of a partition, or "every key" for an empty one."""
    return "every key" if not keys else ", ".join(repr(key) for key in keys)


def _list_text(values: Sequence[Any]) -> str:
    """Return the text of a list of values."""
    return f"[{', '.join(repr(value) for value in values)}]"


def _spans_text(label: str, spans: Sequence[Span]) -> str:
    """Return a line with a label and the text of each span.

    The text of a span contains the call, the operation, the arguments and
    the output. A span whose outcome is not known has "outcome unknown" in
    place of the output. The line ends with "none" for an empty list of
    spans.
    """
    texts: list[str] = []
    for span in spans:
        op = span.operation
        args = ", ".join(repr(arg) for arg in op.args)
        outcome = f" -> {op.output!r}" if op.known else ", outcome unknown"
        texts.append(f"call {span.call} {op.name}({args}){outcome}")
    return f"\n    {label}: {'; '.join(texts) if texts else 'none'}"


def sentence(failure: Failure) -> str:
    """Return the sentence of the record of a failing check of linearizability.

    The first line has the contract, the outcome, the reported partition and
    the limit. The next lines have the counts, the calls of the frontier in
    order, the states of the frontier, and the calls that the spec rejected
    there.

    Args:
        failure: The record.

    Returns:
        The sentence.
    """
    d = failure.detail
    limit = "" if d["limit"] is None else f", at the {d['limit']} limit"
    states = ", ".join(repr(state) for state in d["states"])
    return (
        f"{failure.contract}: {d['outcome']} in the partition of "
        f"{_keys_text(d['partition'])}{limit}"
        f"\n    steps {d['steps']}, partitions {d['partitions']}, calls "
        f"{d['calls']}, concurrency {d['concurrency']}"
        f"{_spans_text('linearized', d['linearized'])}"
        f"\n    states: {states}"
        f"{_spans_text('rejected', d['candidates'])}"
    )


def _edge_text(e: Edge) -> str:
    """Return the text of an edge of a cycle.

    The text has the two calls, the relation, the key and the values that
    prove the edge.
    """
    head = f"call {e.source} -{e.relation}-> call {e.target}: "
    if e.register:
        return head + _register_edge_text(e)
    if e.relation == "ww":
        return (
            f"{head}call {e.target} appended {e.following!r} to {e.key!r} after "
            f"{e.value!r}"
        )
    if e.relation == "wr":
        return f"{head}call {e.target} read {e.key!r} ending in {e.value!r}"
    if e.empty:
        return (
            f"{head}call {e.source} read [] from {e.key!r}, and call {e.target} "
            f"appended {e.following!r} to it"
        )
    return (
        f"{head}call {e.source} read {e.key!r} ending in {e.value!r}, and call "
        f"{e.target} appended {e.following!r} after it"
    )


def _register_edge_text(e: Edge) -> str:
    """Return the values and the calls that prove an edge of a register history."""
    if e.relation == "ww":
        return f"call {e.target} wrote {e.following!r} to {e.key!r} after {e.value!r}"
    if e.relation == "wr":
        return f"call {e.target} read {e.value!r} from {e.key!r}"
    if e.empty:
        return (
            f"call {e.source} read the initial value of {e.key!r}, and call "
            f"{e.target} wrote {e.following!r} to it"
        )
    return (
        f"call {e.source} read {e.value!r} from {e.key!r}, and call {e.target} "
        f"wrote {e.following!r} after it"
    )


def _register_text(value: object) -> str:
    """Return the text of a register's value, and the initial value for None."""
    return "the initial value" if value is None else repr(value)


def _register_observation_text(o: Observation) -> str:
    """Return the text of the observation of a register history."""
    call = o.calls[0]
    key = repr(o.key)
    if o.anomaly == "garbage-read":
        return f"call {call} read {o.read!r} from {key}, and no transaction wrote it"
    if o.anomaly == "internal-inconsistency":
        text = f"call {call} read {_register_text(o.read)} from {key}"
        if o.whole:
            text += f", and it knew the value was {_register_text(o.known)}"
        if o.has_future:
            text += f", and {o.future!r} is a value that call {call} writes later"
        return text
    if o.anomaly == "aborted-read":
        return (
            f"call {call} read {o.value!r} from {key}, and call {o.appender} wrote "
            f"{o.value!r} and aborted"
        )
    return (
        f"call {call} read {o.value!r} from {key}, and call {o.appender} wrote "
        f"{o.value!r} and then {o.following!r}"
    )


def _observation_text(o: Observation) -> str:
    """Return the text of the observation of an anomaly that is not a cycle."""
    call = o.calls[0]
    key = repr(o.key)
    if o.anomaly == "garbage-read":
        return (
            f"call {call} read {_list_text(o.reads[0])} from {key}, and no "
            f"transaction appended {o.value!r}"
        )
    if o.anomaly == "duplicate-append":
        return (
            f"call {call} read {_list_text(o.reads[0])} from {key}, and the list "
            f"contains {o.value!r} twice"
        )
    if o.anomaly == "internal-inconsistency":
        text = f"call {call} read {_list_text(o.reads[0])} from {key}"
        if o.whole:
            text += (
                ", and its earlier micro-operations require the list "
                f"{_list_text(o.expected)}"
            )
        elif o.expected:
            text += (
                ", and its earlier appends require a list that ends with "
                f"{_list_text(o.expected)}"
            )
        if o.has_future:
            text += f", and {o.future!r} is a value that call {call} appends later"
        return text
    if o.anomaly == "incompatible-order":
        return (
            f"calls {call} and {o.calls[1]} read {_list_text(o.reads[0])} and "
            f"{_list_text(o.reads[1])} from {key}, and neither is a prefix of the "
            "other"
        )
    if o.anomaly == "aborted-read":
        return (
            f"call {call} read {o.value!r} from {key}, and call {o.appender} "
            f"appended {o.value!r} and aborted"
        )
    return (
        f"call {call} read {key} ending in {o.value!r}, and call {o.appender} "
        f"appended {o.value!r} and then {o.following!r}"
    )


def _evidence_text(e: Evidence) -> str:
    """Return the text of one entry of an explanation."""
    if isinstance(e, Edge):
        return _edge_text(e)
    if e.register:
        return _register_observation_text(e)
    return _observation_text(e)


def isolation_sentence(failure: Failure) -> str:
    """Return the sentence of the record of a failing isolation check.

    The first line has the contract and the anomaly. The second line lists
    the kinds. Each entry of the explanation follows on a line of its own.

    Args:
        failure: The record.

    Returns:
        The sentence.
    """
    d = failure.detail
    explanation = cast("Sequence[Evidence]", d["explanation"])
    lines = "".join(f"\n    {_evidence_text(e)}" for e in explanation)
    return (
        f"{failure.contract}: {d['anomaly']}\n    kinds: {', '.join(d['kinds'])}{lines}"
    )
