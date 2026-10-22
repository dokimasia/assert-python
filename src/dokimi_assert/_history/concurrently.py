# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""A driver that runs the clients of a history at the same time."""

from __future__ import annotations

import contextvars
import math
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.loop import Loop

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Outcome", "concurrently"]

#: The qualified name of the function. The name of each thread starts with it.
_OP = "history.concurrently"


@dataclass(frozen=True, slots=True)
class Outcome:
    """The outcome of one client that concurrently ran.

    Attributes:
        client: The number of the client, from 0.
        finished: True when the body of the client ended before the time of
            concurrently passed.
        output: The value that the body returned, or the result of its
            awaitable. It is None when the body did not finish.
    """

    client: int
    finished: bool = False
    output: Any = None


def concurrently(
    clients: int, within: float, body: Callable[[int], object]
) -> list[Outcome]:
    """Run one copy of body for each client at the same time.

    The clients have the numbers 0 to clients - 1. concurrently starts one
    daemon thread for each client. The thread of client i calls body(i) in a
    copy of the context of the caller, so a draw of of in a body picks the
    generators of the run of the caller. A barrier releases the threads at
    once after concurrently has started every thread. concurrently then
    waits until every body has ended or until within seconds have passed on
    the platform clock. It counts the time from the release. When a body
    returns an awaitable, its thread runs the awaitable to its end on an
    event loop of its own.

    When the time passes before a body ends, the outcome of the body is not
    finished. Its thread runs on, because Python cannot stop a thread from
    outside. A call that the body opened in a history is pending there.

    Args:
        clients: The number of clients. Must be an int of 1 or more.
        within: The seconds to wait. Must be a finite number of 0 or more.
        body: The body of one client. It receives the number of the client.

    Returns:
        The outcomes of the clients in client order.

    Raises:
        ValueError: clients is not an int of 1 or more, or within is not a
            finite number of 0 or more.
        BaseException: The body of a client raised before the time passed.
            concurrently raises the error of the lowest-numbered such client
            once the wait has ended. An error after the wait is lost.

    Example:
        outcomes = history.concurrently(4, 60, client)
    """
    if type(clients) is not int or clients < 1:
        msg = (
            f"history: concurrently({clients!r}, {within!r}): clients is not an int "
            "of 1 or more"
        )
        raise ValueError(msg)
    if type(within) not in (int, float) or not 0 <= within < math.inf:
        msg = (
            f"history: concurrently({clients!r}, {within!r}): within is not a finite "
            "number of 0 or more"
        )
        raise ValueError(msg)
    outcomes = [Outcome(client) for client in range(clients)]
    raised: dict[int, BaseException] = {}
    ended = threading.Condition()
    release = threading.Barrier(clients + 1)
    running = clients
    waiting = True

    def run(client: int) -> None:
        """Run the body of client after the release, and record how it ended."""
        nonlocal running
        release.wait()
        outcome = Outcome(client, True)
        error: BaseException | None = None
        try:
            with Loop(_OP) as loop:
                outcome = Outcome(client, True, loop.resolve(body(client)))
        except BaseException as caught:
            error = caught
        with ended:
            if not waiting:
                return
            outcomes[client] = outcome
            if error is not None:
                raised[client] = error
            running -= 1
            ended.notify()

    for client in range(clients):
        name = f"{_OP} client {client}"
        context = contextvars.copy_context()
        threading.Thread(
            target=context.run, args=(run, client), name=name, daemon=True
        ).start()
    release.wait()
    with ended:
        ended.wait_for(lambda: running == 0, min(within, threading.TIMEOUT_MAX))
        waiting = False
        first = min(raised, default=None)
        stated = list(outcomes)
    if first is not None:
        raise raised[first]
    return stated
