"""The pytest fixtures, which pytest registers when the package is installed.

The plugin supplies the fixture seat in every test, without a conftest and
without an import. The recording surface needs a place where it reports
its failures at the end of the test, so that a failing assertion does not
stop the assertions after it. The plugin hands each test a Collector. When
the test body ends, it runs the functions that the test registered through
the seat's cleanup, and raises what the collector kept, so the failure
belongs to the test and not to its teardown.

With DOKIMI_ASSERT_RECORD=1, the seat appends the call record of every call
to the user_properties of the test's item, one property per record, named
dokimi.assert.<seq>. pytest's JUnit XML report writes each user property of
a test as a property element of the test's testcase element.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from dokimi_assert._matcher.seat import name_test
from dokimi_assert._record.calls import Sink, own, write
from dokimi_assert._record.switch import reading
from dokimi_assert.seat import Collector, Recorder, clean_up

__all__ = ["RECORDS", "SEATS", "pytest_runtest_call", "recorder", "seat"]

#: The prefix of the name of the user property of a call record.
RECORDS = "dokimi.assert."

#: Every collector that the fixture handed out during one test.
SEATS: pytest.StashKey[list[Collector]] = pytest.StashKey()


def _path_of(item: pytest.Item) -> list[str]:
    """Return the path of a test: its module's path, then its class and its name.

    The module's path is relative to pytest's root directory, one segment
    per directory and one for the file.
    """
    file, *rest = item.nodeid.split("::")
    return [*file.split("/"), *rest]


def _sink(properties: list[tuple[str, object]]) -> Sink:
    """Return the sink that appends each call record to the properties of a test."""

    def sink(seq: int, line: str) -> None:
        properties.append((f"{RECORDS}{seq}", line))

    return sink


@pytest.fixture
def seat(request: pytest.FixtureRequest) -> Collector:
    """Return the seat to pass to an assertion.

    check stops the test at the first failure. expect records the failure
    and continues, and the fixture reports everything that expect recorded
    when the test body ends.

        def test_get(seat):
            item = store.get("widget")

            check.is_not_none(seat, item, "get returns the stored item")
            expect.equal(seat, item.name, "widget", "it is the one stored")

    Args:
        request: The running test.

    Returns:
        A collector, whose recorded failures the fixture raises when the test
        body ends.
    """
    collector = Collector()
    node: pytest.Item = request.node  # pyright: ignore[reportUnknownMemberType]
    name_test(collector, _path_of(node))
    if reading().on:
        # pytest's Item declares user_properties in __init__ without a type
        # that the language server can read.
        write(own(collector), _sink(node.user_properties))  # pyright: ignore[reportUnknownMemberType]

    # pytest ships no complete type for Stash.setdefault, so a checker reads
    # the result as partly unknown.
    stash: pytest.Stash = node.stash  # pyright: ignore[reportUnknownMemberType]
    seats: list[Collector] = stash.setdefault(SEATS, [])  # pyright: ignore[reportUnknownMemberType]
    seats.append(collector)  # pyright: ignore[reportUnknownMemberType]
    return collector


@pytest.fixture
def recorder() -> Recorder:
    """Return a seat that records and fails nothing.

    A test of an assertion drives the assertion with the recorder, then reads
    failed, message and failures. Nothing that a test drives with a recorder
    can fail the test.

    Returns:
        A seat that records every failure and raises none.
    """
    return Recorder()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, Any]:
    """Run the cleanups of the test's seats, and raise what they collected.

    The hook raises in the call phase, so pytest reports a failing test and
    not a passing test with an error in its teardown. A test body that raised
    keeps its own exception, which came first and explains the rest.

    Args:
        item: The running test.

    Yields:
        Nothing. pluggy runs the call phase of the test at the yield and
        sends the result back.

    Returns:
        The result of the wrapped call.
    """
    try:
        result = yield
    finally:
        for collector in item.stash.get(SEATS, []):
            clean_up(collector)
    for collector in item.stash.get(SEATS, []):
        collector.flush()
    return result
