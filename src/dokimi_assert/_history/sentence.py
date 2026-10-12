"""The sentences of the records of the history assertions.

A seat that does not take records receives the sentence of a record.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from dokimi_assert._history.derivation import Edge, Evidence, Observation
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
    lines = "".join(
        f"\n    {_edge_text(e) if isinstance(e, Edge) else _observation_text(e)}"
        for e in explanation
    )
    return (
        f"{failure.contract}: {d['anomaly']}\n    kinds: {', '.join(d['kinds'])}{lines}"
    )
