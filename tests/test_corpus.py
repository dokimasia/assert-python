"""The corpus, driven against this library.

This is what checks meaning rather than membership: the same cases run
against every implementation of the standard, so a library that means
something different by the same name fails here.
"""

from __future__ import annotations

import pytest

from dokimi.conformance.corpus import INVOKERS, Case, cases
from dokimi.seat import Recorder

CASES = list(cases())


def test_the_corpus_is_not_empty() -> None:
    """A corpus that read nothing would pass having checked nothing."""
    assert CASES, "the vendored corpus states no cases"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: Case) -> None:
    """Drive one case and hold the outcome to what it states."""
    reason = case.skip_reason
    if reason is not None:
        pytest.skip(f"declared skip: {reason}")

    invoke = INVOKERS.get(case.assertion)
    assert invoke is not None, f"no invoker registered for {case.assertion}"

    recorder = Recorder()
    invoke(recorder, *case.args, case.id)

    mismatch = case.check(recorder)
    assert mismatch is None, mismatch
