"""Where an assertion reads time.

An assertion that waits, retries or measures reads a clock the seat
carries rather than calling the platform, so a test can supply time it
controls and a busy machine cannot make the assertion flaky.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol, runtime_checkable

__all__ = ["Clock", "Controlled", "System"]


@runtime_checkable
class Clock(Protocol):
    """The two readings an assertion needs from time."""

    def now(self) -> float:
        """Answer the current instant, in seconds.

        Returns:
            A monotonic reading, comparable against another from the
            same clock.
        """
        ...

    def sleep(self, duration: float) -> None:
        """Block until the duration has passed on this clock.

        Args:
            duration: Seconds to wait.
        """
        ...


class System:
    """Reads the platform clock.

    This is what an assertion gets when the seat carries no other, so
    an assertion that reads time behaves as it did before a clock
    existed.
    """

    def now(self) -> float:
        """Answer the platform's monotonic reading, in seconds.

        Returns:
            Seconds from an arbitrary origin.
        """
        return time.monotonic()

    def sleep(self, duration: float) -> None:
        """Block for duration against the platform clock.

        Args:
            duration: Seconds to wait.
        """
        time.sleep(duration)


class Controlled:
    """A clock that moves only when a test advances it.

    now answers what advance last left it at, and sleep
    blocks until the clock has passed the duration rather than until
    the wall has. An assertion that retries advances this clock between
    attempts rather than sleeping against it, so a body that settles on
    the third attempt costs three attempts and no waiting.

    A controlled clock cannot reach the subject: code under test that
    calls the platform directly reads a different now, and nothing here
    detects that.

    Every method is safe to call from any thread.
    """

    def __init__(self, start: float = 0.0) -> None:
        """Start a clock reading start until it is advanced.

        Args:
            start: The instant it reads before anything advances it.
        """
        self._instant: float = start
        self._woke: threading.Condition = threading.Condition()

    def now(self) -> float:
        """Answer the instant this clock was last advanced to.

        Returns:
            Seconds, as advance has left them.
        """
        with self._woke:
            return self._instant

    def advance(self, duration: float) -> None:
        """Move the clock forward and wake what the new instant passed.

        A duration that is not positive does not move it backwards;
        time on this clock only goes forward.

        Args:
            duration: Seconds to move forward by.
        """
        if duration <= 0:
            return
        with self._woke:
            self._instant += duration
            self._woke.notify_all()

    def sleep(self, duration: float) -> None:
        """Block until the clock has passed duration.

        It returns at once when duration is not positive. Otherwise it
        waits for another thread to advance the clock, so a test that
        sleeps on the only thread it has blocks until something
        advances it.

        The duration is measured from the instant this reads, so a
        caller racing sleep against advance on two threads cannot say
        which instant it slept from. Assertions do not hit this: one
        that retries advances the clock itself, on the thread it is
        already running on.

        Args:
            duration: Seconds to wait.
        """
        if duration <= 0:
            return
        with self._woke:
            until = self._instant + duration
            while self._instant < until:
                self._woke.wait()


def wait(clock: Clock, duration: float) -> None:
    """Move time forward by duration.

    A clock a test controls is advanced, because nothing else will move
    it while this call is running. Any other clock is slept against.

    Args:
        clock: Where time is read.
        duration: Seconds to move forward by.
    """
    advance = getattr(clock, "advance", None)
    if callable(advance):
        advance(duration)
        return
    clock.sleep(duration)
