# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The bodies of the property vectors.

A body draws one value under the label value from the generator draw. It
counts the case under each label of classify whose predicate is true, and
it rejects the case when the predicate rejects-when is true. The identity of
its failure is the identity of the first entry of fails whose predicate is
true. An ending then ends the case with that identity, or with None for a
case that does not fail.

Three named bodies do what a predicate cannot do:

- draws-nothing does not request an input.
- diverges draws an integer from 0 to 9 on its first call and a bool on each
  later call.
- fails-once draws an integer from 0 to 10^9. Its case fails with the
  identity once the first time that it draws a value above 1,000.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, cast

from dokimi_assert import prop
from dokimi_assert.conformance.prop.generator import build
from dokimi_assert.conformance.prop.predicate import predicate

__all__ = ["DRAWN", "Body", "Ending", "body_of"]

#: The label of the draw of a body.
DRAWN = "value"

#: A body of a property.
Body = Callable[[prop.Case], None]

#: A function that ends the case of a body that ran to its end. It takes the
#: identity of the failure of the case, or None.
Ending = Callable[[prop.Case, str | None], None]

#: The identity of the failure of fails-once, and the value above which the
#: body fails.
_ONCE = "once"
_ONCE_ABOVE = 1_000


def _identity_of(value: object) -> str:
    """Return an identity of an entry of fails.

    Raises:
        ValueError: The value is not a string.
    """
    if not isinstance(value, str):
        msg = f"prop: {json.dumps(value)} is not an identity"
        raise ValueError(msg)
    return value


def _drawing(spec: Mapping[str, Any], end: Ending) -> Body:
    """Return the body that draws, classifies, rejects and fails in that order.

    Raises:
        ValueError: classify is not an object, fails is not a list, or a
            generator, a predicate or an identity is not valid.
    """
    generator = build(spec.get("draw"))
    classify = spec.get("classify", {})
    if not isinstance(classify, dict):
        msg = f"prop: classify is {json.dumps(classify)}, not an object"
        raise ValueError(msg)
    labels = [
        (label, predicate(when))
        for label, when in cast("dict[str, object]", classify).items()
    ]
    rejects = predicate(spec["rejects-when"]) if "rejects-when" in spec else None
    entries = spec.get("fails", [])
    if not isinstance(entries, list):
        msg = f"prop: fails is {json.dumps(entries)}, not a list"
        raise ValueError(msg)
    fails = [
        (_identity_of(entry.get("identity")), predicate(entry.get("when")))
        for entry in cast("list[dict[str, object]]", entries)
    ]

    def body(c: prop.Case) -> None:
        value = c.draw(generator, DRAWN)
        for label, test in labels:
            if test(value):
                c.classify(label)
        if rejects is not None:
            c.assume(not rejects(value))
        end(c, next((identity for identity, test in fails if test(value)), None))

    return body


def _diverging(end: Ending) -> Body:
    """Return the body that requests other bounds after its first call."""
    digit = prop.integer(0, 9)
    coin = prop.boolean()
    drawn = [False]

    def body(c: prop.Case) -> None:
        c.draw(coin if drawn[0] else digit, DRAWN)
        drawn[0] = True
        end(c, None)

    return body


def _failing_once(end: Ending) -> Body:
    """Return the body that fails only the first time that it draws above 1,000."""
    wide = prop.integer(0, 1_000_000_000)
    failed = [False]

    def body(c: prop.Case) -> None:
        failure = None
        if c.draw(wide, DRAWN) > _ONCE_ABOVE and not failed[0]:
            failed[0] = True
            failure = _ONCE
        end(c, failure)

    return body


def body_of(spec: object, end: Ending) -> Body:
    """Return a new body of a JSON object.

    A named body has state of its own, so each run takes a new body.

    Args:
        spec: The JSON object of the body.
        end: The ending of each case that runs to its end.

    Returns:
        The body.

    Raises:
        ValueError: The value is not an object, the named body does not
            exist, or a part of the body is not valid.
    """
    if not isinstance(spec, dict):
        msg = f"prop: {json.dumps(spec)} is not a body"
        raise ValueError(msg)
    stated = cast("dict[str, Any]", spec)
    kind = stated.get("kind")
    if kind is None:
        return _drawing(stated, end)
    if kind == "draws-nothing":
        return lambda c: end(c, None)
    if kind == "diverges":
        return _diverging(end)
    if kind == "fails-once":
        return _failing_once(end)
    msg = f"prop: {json.dumps(kind)} is not a named body"
    raise ValueError(msg)
