"""The pytest fixtures, registered automatically on install.

Installing this package registers the plugin, so ``seat`` is available
in any test without a conftest and without an import.

The recording surface needs someone to report at the end of the test,
because that is what lets a failing assertion be seen without stopping
the ones after it. A seat on its own has no end of test to report at.
This plugin is that someone: it hands out a :class:`Collector` and
raises whatever the collector kept once the test body is done, so the
failure lands on the test rather than on teardown.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from dokimi_assert.seat import Collector, Recorder

#: Every collector handed out during one test. A test may take the
#: fixture once and pass it down, or several fixtures may each want
#: one; all of them are flushed together.
SEATS: pytest.StashKey[list[Collector]] = pytest.StashKey()


@pytest.fixture
def seat(request: pytest.FixtureRequest) -> Collector:
    """Return the seat to pass to an assertion.

    ``check`` stops the test at the first failure. ``expect`` records
    and carries on, and everything it recorded is reported when the
    test body ends.

        def test_get(seat):
            item = store.get("widget")

            check.is_not_none(seat, item, "Get returns the stored item")
            expect.equal(seat, item.name, "widget", "it is the one stored")
    """
    collector = Collector()

    # pytest ships no complete type for Stash.setdefault, so a checker
    # reads the result as partially unknown. The annotation says what
    # it is; the ignores are about pytest's stubs, not this code.
    stash: pytest.Stash = request.node.stash  # pyright: ignore[reportUnknownMemberType]
    seats: list[Collector] = stash.setdefault(SEATS, [])  # pyright: ignore[reportUnknownMemberType]
    seats.append(collector)  # pyright: ignore[reportUnknownMemberType]
    return collector


@pytest.fixture
def recorder() -> Recorder:
    """Return a seat that records instead of failing anything.

    This is for testing an assertion rather than using one: drive the
    assertion with it, then read ``failed`` and ``message`` to say what
    it reported. Nothing driven with a recorder can fail the test.
    """
    return Recorder()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, Any]:
    """Report what the test's seats collected, as the test's failure.

    Raising here rather than in a fixture finalizer puts the failure in
    the call phase, so pytest reports a failing test rather than a
    passing test with an error in teardown.

    A test body that already raised keeps its own exception: that
    failure came first and explains the rest.
    """
    result = yield
    for collector in item.stash.get(SEATS, []):
        collector.flush()
    return result
