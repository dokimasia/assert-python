"""Reading the corpus and driving it against this library."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from types import ModuleType
from typing import Any

from dokimi_assert import check, expect
from dokimi_assert.conformance.literal import decode
from dokimi_assert.seat import Recorder

#: This language's key in a case's skip table.
LANGUAGE = "python"

PASS = "pass"
FAIL = "fail"


def _invokers(surface: ModuleType) -> dict[str, Callable[..., None]]:
    """Map each assertion to the call that drives it on a surface.

    Both surfaces carry the same names, so one table serves either. A
    table rather than a lookup by name because it says which arguments
    an assertion takes and in what order, which a name alone does not.
    """
    return {
        "equal": surface.equal,
        "not-equal": surface.not_equal,
        "true": surface.is_true,
        "false": surface.is_false,
        "nil": surface.is_none,
        "not-nil": surface.is_not_none,
        "length": surface.length,
        "empty": surface.is_empty,
        "not-empty": surface.is_not_empty,
        "contains": surface.contains,
        "not-contains": surface.not_contains,
        "contains-in-order": surface.contains_in_order,
        "has-prefix": surface.has_prefix,
        "has-suffix": surface.has_suffix,
        "matches": surface.matches,
        "close-to": surface.close_to,
        "in-range": surface.in_range,
    }


#: Every surface the corpus is driven through, by name. Both must
#: produce the same outcome from the same case: that is what the two
#: carrying the same assertions means.
SURFACES: dict[str, dict[str, Callable[..., None]]] = {
    "check": _invokers(check),
    "expect": _invokers(expect),
}

#: The aborting surface's table, for a caller that wants just the one.
INVOKERS: dict[str, Callable[..., None]] = SURFACES["check"]


@dataclass(frozen=True)
class Case:
    """One corpus case: what an assertion is given, and what it must report."""

    id: str
    assertion: str
    args: list[Any]
    expect: str
    message_contains: list[str] = field(default_factory=list)
    skip: dict[str, str] = field(default_factory=dict)

    @property
    def skip_reason(self) -> str | None:
        """Why this case does not apply here, or None if it does."""
        return self.skip.get(LANGUAGE)

    def check(self, recorder: Recorder) -> str | None:
        """Say how the outcome differs from what the case states.

        Returns None when it matches. A value rather than a raised
        failure, so the rule can be driven against cases it must
        reject.
        """
        if self.expect == PASS:
            if recorder.failed:
                return f"{self.id} expects pass, got failure: {recorder.message}"
            return None

        if self.expect == FAIL:
            if not recorder.failed:
                return f"{self.id} expects fail, got pass"
            for wanted in self.message_contains:
                if wanted not in recorder.message:
                    return (
                        f"{self.id} failure {recorder.message!r} "
                        f"does not carry {wanted!r}"
                    )
            return None

        return f"{self.id} states an unknown expectation {self.expect!r}"


def cases() -> Iterator[Case]:
    """Read every case the vendored corpus states."""
    corpus = resources.files("dokimi_assert.conformance") / "spec" / "corpus"
    for entry in sorted(corpus.iterdir(), key=lambda p: p.name):
        if not entry.name.endswith(".json"):
            continue
        document = json.loads(entry.read_text())
        assertion = document["assertion"]
        for raw in document["cases"]:
            yield Case(
                id=raw["id"],
                assertion=assertion,
                args=[decode(a) for a in raw["args"]],
                expect=raw["expect"],
                message_contains=raw.get("message_contains", []),
                skip=raw.get("skip", {}),
            )
