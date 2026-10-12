"""The spec of _history/concurrently.py tests the driver of the clients of a history."""

from __future__ import annotations

import asyncio
import math
import threading
from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.concurrently import Outcome, concurrently
from dokimi_assert.seat import Collector
from helpers import refusal

#: A wait in seconds that is longer than any body of the spec needs.
PATIENT = 60.0

#: The seconds of a case whose body runs past them. A body that returns at
#: once ends within them on a loaded machine.
BRIEF = 0.25


class Gate:
    """A gate at which a body waits until the test opens it."""

    def __init__(self) -> None:
        """Return a closed gate."""
        self._arrived: threading.Event = threading.Event()
        self._opened: threading.Event = threading.Event()
        self._threads: list[threading.Thread] = []

    def wait(self) -> None:
        """Wait at the gate until the test opens it."""
        self._threads.append(threading.current_thread())
        self._arrived.set()
        self._opened.wait(PATIENT)

    def open(self) -> None:
        """Open the gate for a waiting body and wait for its thread to end."""
        self._arrived.wait(PATIENT)
        self._opened.set()
        for thread in self._threads:
            thread.join(PATIENT)


class TestOutcome:
    """Outcome records how one client of concurrently ended."""

    def test_defaults_to_an_unfinished_outcome_without_an_output(
        self, seat: Collector
    ) -> None:
        """Outcome(3) has finished False and output None."""
        outcome = Outcome(3)
        check.equal(
            seat,
            [outcome.client, outcome.finished, outcome.output],
            [3, False, None],
            "the outcome of client 3 is not finished",
        )


class TestConcurrently:
    """concurrently runs the clients of a history at the same time."""

    def test_returns_the_output_of_each_client_in_client_order(
        self, seat: Collector
    ) -> None:
        """Three bodies return ten times the number of their client."""
        check.equal(
            seat,
            concurrently(3, PATIENT, lambda client: client * 10),
            [Outcome(0, True, 0), Outcome(1, True, 10), Outcome(2, True, 20)],
            "concurrently returns the three outputs in client order",
        )

    def test_runs_the_awaitable_of_a_body_to_its_end(self, seat: Collector) -> None:
        """Each coroutine awaits once and then returns the name of its client."""

        async def body(client: int) -> str:
            await asyncio.sleep(0)
            return f"client {client}"

        check.equal(
            seat,
            [outcome.output for outcome in concurrently(2, PATIENT, body)],
            ["client 0", "client 1"],
            "each output is the result of a coroutine",
        )

    def test_runs_the_bodies_at_the_same_time(self, seat: Collector) -> None:
        """Each body waits at a barrier of four parties for the other three."""
        met = threading.Barrier(4, timeout=PATIENT)
        outcomes = concurrently(4, PATIENT, lambda _: met.wait())
        check.equal(
            seat,
            [outcome.finished for outcome in outcomes],
            [True, True, True, True],
            "every body passed the barrier",
        )

    def test_returns_a_body_that_runs_past_the_time_as_not_finished(
        self, seat: Collector
    ) -> None:
        """Client 0 still waits when the time has passed."""
        gate = Gate()

        def body(client: int) -> int:
            if client == 0:
                gate.wait()
            return client

        outcomes = concurrently(2, BRIEF, body)
        gate.open()
        check.equal(
            seat,
            outcomes,
            [Outcome(0), Outcome(1, True, 1)],
            "client 0 still waits when the time has passed",
        )

    def test_returns_at_once_for_a_time_of_0(self, seat: Collector) -> None:
        """The body waits at a gate that the test opens after the call."""
        gate = Gate()
        outcomes = concurrently(1, 0, lambda _: gate.wait())
        gate.open()
        check.equal(seat, outcomes, [Outcome(0)], "the body has not finished")

    def test_returns_the_outcomes_for_a_time_past_the_longest_wait_of_the_platform(
        self, seat: Collector
    ) -> None:
        """The time 1e300 is finite and above threading.TIMEOUT_MAX."""
        check.equal(
            seat,
            concurrently(1, 1e300, lambda client: client),
            [Outcome(0, True, 0)],
            "the body finished",
        )

    def test_raises_the_error_of_the_lowest_client_that_raised_once_every_body_ended(
        self, seat: Collector
    ) -> None:
        """Clients 2 and 3 raise. Client 0 ends after client 3 has raised."""
        raising = threading.Event()
        waited = threading.Event()

        def body(client: int) -> None:
            if client == 0:
                raising.wait(PATIENT)
                waited.set()
            elif client == 2:
                raise ValueError("client 2")
            elif client == 3:
                raising.set()
                raise ValueError("client 3")

        error = check.raises(
            seat,
            lambda: concurrently(4, PATIENT, body),
            "concurrently raises the error of a client",
        )
        check.equal(
            seat,
            [str(error), waited.is_set()],
            ["client 2", True],
            "concurrently raises the error of client 2 after client 0 has ended",
        )

    def test_drops_the_error_of_a_body_that_raises_after_the_time_passed(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The test opens the gate after the call. The body then raises."""
        hooked: list[threading.ExceptHookArgs] = []
        monkeypatch.setattr(threading, "excepthook", hooked.append)
        gate = Gate()

        def late(_: int) -> None:
            gate.wait()
            raise ValueError("too late")

        outcomes = concurrently(1, 0, late)
        gate.open()
        check.equal(seat, outcomes, [Outcome(0)], "the body has not finished")
        check.equal(seat, hooked, [], "the thread hook does not receive the late error")

    tests: ClassVar[list[tuple[str, Any, Any, str]]] = [
        (
            "zero clients",
            0,
            10,
            "history: concurrently(0, 10): clients is not an int of 1 or more",
        ),
        (
            "a fraction of a client",
            1.5,
            10,
            "history: concurrently(1.5, 10): clients is not an int of 1 or more",
        ),
        (
            "a negative time",
            1,
            -1,
            "history: concurrently(1, -1): within is not a finite number of 0 or more",
        ),
        (
            "an infinite time",
            1,
            math.inf,
            "history: concurrently(1, inf): within is not a finite number of 0 or more",
        ),
        (
            "a time that is not a number",
            1,
            "10",
            "history: concurrently(1, '10'): within is not a finite number of 0 or "
            "more",
        ),
    ]

    @pytest.mark.parametrize(
        ("clients", "within", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_a_value_error_for(
        self, seat: Collector, clients: Any, within: Any, want: str
    ) -> None:
        """The call refuses the arguments before it starts a thread."""
        check.equal(
            seat,
            refusal(seat, lambda: concurrently(clients, within, lambda _: None)),
            want,
            "the text of the refusal",
        )
