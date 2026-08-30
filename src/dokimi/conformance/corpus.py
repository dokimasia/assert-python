"""Reading the corpus and driving it against this library."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from dokimi import check
from dokimi.conformance.literal import decode
from dokimi.seat import Recorder

#: This language's key in a case's skip table.
LANGUAGE = "python"

PASS = "pass"
FAIL = "fail"

#: The call each assertion is driven through. Python can look a name
#: up at run time, but a table says which arguments an assertion takes
#: and in what order, which a name alone does not.
INVOKERS: dict[str, Callable[..., None]] = {
    "equal": check.equal,
    "not-equal": check.not_equal,
    "true": check.is_true,
    "false": check.is_false,
    "nil": check.is_none,
    "not-nil": check.is_not_none,
    "length": check.length,
    "empty": check.is_empty,
    "not-empty": check.is_not_empty,
    "contains": check.contains,
    "not-contains": check.not_contains,
    "contains-in-order": check.contains_in_order,
    "has-prefix": check.has_prefix,
    "has-suffix": check.has_suffix,
    "matches": check.matches,
    "close-to": check.close_to,
    "in-range": check.in_range,
}


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
    corpus = resources.files("dokimi.conformance") / "spec" / "corpus"
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
