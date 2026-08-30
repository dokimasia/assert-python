"""The corpus, driven against both surfaces.

This is what checks meaning rather than membership: the same cases run
against every implementation of the standard, so a library that means
something different by the same name fails here.

Every case runs twice, once per surface. The two carrying the same
assertions means they produce the same outcome from the same case, and
running one and trusting the other would leave that untested.

Written with pytest's assert rather than with this library. Everything
here reports through one function, so a verdict written with the
subject goes quiet exactly when the subject does: silencing that
function leaves every case passing, having checked nothing.
"""

from __future__ import annotations

import pytest

from dokimi_assert.conformance.corpus import SURFACES, Case, cases
from dokimi_assert.seat import Recorder

CASES = list(cases())


def test_the_corpus_is_not_empty() -> None:
    """A corpus that read nothing would pass having checked nothing."""
    assert CASES, "the vendored corpus states cases"


def test_both_surfaces_are_driven() -> None:
    """Driving one surface would leave the other's meaning untested."""
    assert sorted(SURFACES) == ["check", "expect"], "both surfaces are driven"


@pytest.mark.parametrize("surface", sorted(SURFACES))
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: Case, surface: str) -> None:
    """Drive one case through one surface and hold it to what it states."""
    reason = case.skip_reason
    if reason is not None:
        pytest.skip(f"declared skip: {reason}")

    invoke = SURFACES[surface].get(case.assertion)
    assert invoke is not None, f"{surface} carries an invoker for {case.assertion}"

    recorder = Recorder()
    invoke(recorder, *case.args, case.id)

    mismatch = case.check(recorder)
    assert mismatch is None, f"{surface} disagrees with the corpus: {mismatch}"
