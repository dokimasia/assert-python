"""Reading the corpus and driving it against this library."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from types import ModuleType
from typing import Any, cast

from dokimi_assert import check, expect
from dokimi_assert.conformance.literal import decode
from dokimi_assert.failure import Failure
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
        # The assertions a case reaches by naming a behaviour rather
        # than stating a value.
        "throws": surface.raises,
        "not-throws": surface.does_not_raise,
        "honours-cancellation": surface.honours_cancellation,
        "honours-deadline": surface.honours_deadline,
        "nil-context-safe": surface.none_handle_safe,
        "pure": surface.is_pure,
        "eventually": surface.eventually,
        "eventually-true": surface.eventually_true,
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


@dataclass(frozen=True, slots=True)
class Case:
    """One corpus case: what an assertion is given, and what it must report."""

    id: str
    assertion: str
    args: list[Any]
    expect: str
    detail: dict[str, Any] = field(default_factory=dict)
    subject: str | None = None
    skip: dict[str, str] = field(default_factory=dict)

    @property
    def skip_reason(self) -> str | None:
        """Why this case does not apply here, or None if it does.

        Returns:
            Why this language skips the case, or None when it does not.
        """
        return self.skip.get(LANGUAGE)

    def check(self, recorder: Recorder) -> str | None:
        """Say how the outcome differs from what the case states.

        Returns None when it matches. A value rather than a raised
        failure, so the rule can be driven against cases it must
        reject.

        Args:
            recorder: The seat the assertion under test reported to.

        Returns:
            What went wrong, or None when the recorder agrees with the case.
        """
        if self.expect == PASS:
            if recorder.failed:
                return f"{self.id} expects pass, got failure: {recorder.message}"
            return None

        if self.expect == FAIL:
            if not recorder.failed:
                return f"{self.id} expects fail, got pass"
            if not recorder.failures:
                return f"{self.id} reported no record; the assertion did not report one"
            return self._check_detail(recorder.failures[0])

        return f"{self.id} states an unknown expectation {self.expect!r}"

    def _check_detail(self, failure: Failure) -> str | None:
        """Say how a record's detail differs from what the case states.

        Every field the case states must match; a field it leaves out
        is not checked.

        Args:
            failure: The record the assertion reported.

        Returns:
            What went wrong, or None when every stated field matches.
        """
        for name, want in self.detail.items():
            if name not in failure.detail:
                return f"{self.id} record holds no detail {name!r}, want {want!r}"
            held = failure.detail[name]
            if not _same(held, want):
                return f"{self.id} detail {name!r} is {held!r}, want {want!r}"
        return None


def _same(held: Any, want: Any) -> bool:
    """Whether a reported value matches what a case states.

    A NaN is unequal to itself under the standard's own rules, which
    would make a case stating one impossible to satisfy. Here the
    question is whether the assertion reported the value the case
    named, so two NaNs of the same type count as the same value.

    Args:
        held: What the assertion reported.
        want: What the case states.

    Returns:
        True when they are the same value.
    """
    if (
        isinstance(held, float)
        and isinstance(want, float)
        and math.isnan(held)
        and math.isnan(want)
    ):
        return True
    return bool(held == want) and type(held) is type(want)


def _subject_kind(raw: dict[str, Any]) -> str | None:
    """The behaviour a case names, or None when it states values.

    Args:
        raw: The case as the corpus file states it.

    Returns:
        The subject kind, or None.
    """
    stated: object = raw.get("subject")
    if not isinstance(stated, dict):
        return None
    kind: object = cast("dict[str, object]", stated).get("kind")
    return kind if isinstance(kind, str) else None


def cases() -> Iterator[Case]:
    """Read every case the vendored corpus states.

    Returns:
        Every case the vendored corpus states.
    """
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
                args=[decode(a) for a in raw.get("args", [])],
                expect=raw["expect"],
                subject=_subject_kind(raw),
                detail={
                    name: decode(value) for name, value in raw.get("detail", {}).items()
                },
                skip=raw.get("skip", {}),
            )
