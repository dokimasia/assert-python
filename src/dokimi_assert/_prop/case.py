# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""A case is one call of the body of a property and the seat of its assertions.

A case keeps each failure record in call order, and its first record is the
failure of the case. A failure of an aborting assertion ends the case with a
signal of the engine. assume, skip, a draw that repeats a tested case and a
draw past the cap end the case with a signal too. Every later call of the
case raises the signal again, so a body that catches a signal cannot run past
the end of its case.

However the body ends, the case runs its cleanups. The last registered
cleanup runs first. A cleanup is part of the case. A failure in a cleanup
fails the case in the same way as a failure in the body, and the later
cleanups still run. A draw in a cleanup is a draw of the case.
"""

from __future__ import annotations

import asyncio
import inspect
import random
import traceback
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NoReturn, TypeVar, cast

from dokimi_assert._history.history import History
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.seat import Seat, clock_of
from dokimi_assert._matcher.verdict import note_fault
from dokimi_assert._override import override
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import Decoder, Failed, Rejected, Skipped
from dokimi_assert._prop.engine.traces import TraceError
from dokimi_assert._prop.engine.tree import Diverged, Repeated
from dokimi_assert._prop.identity import Identity, key_of, of_error, of_record
from dokimi_assert._record.calls import Slot, own, run
from dokimi_assert.failure import Failure, Where, call_site
from dokimi_assert.seat import Standard

if TYPE_CHECKING:
    from dokimi_assert._matcher.loop import Loop
    from dokimi_assert.clock import Clock

__all__ = [
    "Case",
    "Failing",
    "FaultSignal",
    "Faulted",
    "Location",
    "case_of",
    "execute",
    "on_engine",
]

_T = TypeVar("_T")


class FaultSignal(BaseException):
    """The signal that ends the run of a property with a fault.

    The task scheduler of stateful raises it for a member of the event loop
    that it does not implement. The steps of a machine raise it for a
    coroutine that they cannot run. The case runs its cleanups, and then the
    property ends its call with the fault. The class derives from
    BaseException, so a body that catches Exception lets the signal pass.

    Attributes:
        fault: The fault.
    """

    def __init__(self, fault: FaultError) -> None:
        """Return the signal of a fault.

        Args:
            fault: The fault.
        """
        super().__init__(str(fault))
        self.fault: FaultError = fault


class Faulted(BaseException):
    """The signal of a case that a fault of a call of its body ended.

    The fault ends the run of the property in every phase, and the property
    ends its call with the same fault. The class derives from BaseException,
    so a body that catches Exception lets the signal pass.

    Attributes:
        fault: The fault.
    """

    def __init__(self, fault: BaseException) -> None:
        """Return the signal of a fault of a call of the body.

        Args:
            fault: The fault.
        """
        super().__init__(str(fault))
        self.fault: BaseException = fault


#: The exceptions that end a body or a cleanup as the end of a case.
#: KeyboardInterrupt and SystemExit are not among them, so a run stops at them.
_ENDINGS = (
    Exception,
    Rejected,
    Skipped,
    Failed,
    Repeated,
    Diverged,
    FaultSignal,
    Faulted,
)

#: The signals of the engine. Each of them ends a case.
_SIGNALS = (
    Rejected,
    Skipped,
    Failed,
    Repeated,
    Diverged,
    TraceError,
    FaultSignal,
    Faulted,
)

#: The signals that end a case before every failure, because they end the run.
_FINAL = (Repeated, Diverged, TraceError, FaultSignal, Faulted)

#: The step between two values of random(). It is 2^-53.
_UNIT = 2.0**-53


@dataclass(frozen=True, slots=True)
class Failing:
    """The failure record and the identity of a failed case.

    Attributes:
        failure: The failure record of the case.
        identity: The identity of the failure. The shrinker keeps this
            identity while it shrinks the case.
    """

    failure: Failure
    identity: Identity


@dataclass(frozen=True, slots=True)
class Location:
    """The location of the records of a case.

    Attributes:
        site: The call site of the property. A record whose stack does not
            have a frame of the caller is at this site.
        pinned: When True, every record of the case is at the call site of
            the property. The library calls the assertion of a property form,
            so the records of that assertion are pinned.
    """

    site: Where | None
    pinned: bool = False


@dataclass(eq=False)
class _State:
    """The state of a case. Only the run of the property reads it.

    Attributes:
        engine: The record of the call in the engine.
        seat: The seat of the property.
        location: The location of the records of the case.
        records: The failure records in call order.
        raised: The first exception other than a signal that the body or a
            cleanup raised, or None.
        stopped: The signal that ended the case, or None.
        cleanups: The cleanups that have not run. They are in the order of
            their registration.
        history: The history of the case. The case creates it before the
            body runs, so the clients of a body on threads share it.
    """

    engine: Engine
    seat: Seat
    location: Location
    records: list[Failure] = field(default_factory=list)
    raised: BaseException | None = None
    stopped: BaseException | None = None
    cleanups: list[Callable[[], object]] = field(default_factory=list)
    history: History = field(default_factory=History)


#: The state of each case. The values are weak references, because a state
#: refers to its case through the engine. The case keeps its state alive.
_STATES: weakref.WeakKeyDictionary[Case, weakref.ref[_State]] = (
    weakref.WeakKeyDictionary()
)


def _check(state: _State) -> None:
    """Raise the signal that ended the case again, if a signal ended it."""
    if state.stopped is not None:
        raise state.stopped


def _stop(state: _State, error: BaseException) -> NoReturn:
    """Raise error, and keep it as the signal that ends the case when it is one."""
    if isinstance(error, _SIGNALS) and state.stopped is None:
        state.stopped = error
    raise error


def _on(state: _State, fn: Callable[[Engine], _T]) -> _T:
    """Call fn on the engine with the checks that every member of a case makes.

    The call raises the signal that ended the case. It keeps a signal that fn
    raises as the signal that ends the case. It returns the result of fn.
    """
    _check(state)
    try:
        return fn(state.engine)
    except _ENDINGS as error:
        _stop(state, error)


def _locate(location: Location) -> Where | None:
    """Return the location of a record of the caller.

    The location of a pinned case is the call site of the property. Otherwise
    it is the innermost frame of the caller, or the call site when the stack
    does not have such a frame.
    """
    if location.pinned:
        return location.site
    found = call_site()
    return found if found is not None else location.site


def _failed_with(failure: Failure) -> Failed:
    """Return the failure of a case whose first record is failure."""
    identity = of_record(failure)
    return Failed(key_of(identity), Failing(failure, identity))


class _Random(random.Random):
    """A random.Random that makes every value from integer choices of a case.

    random() takes the high 53 bits of one choice. getrandbits(k) takes the
    high k bits of ceil(k / 64) choices. Every other method of random.Random
    calls one of the two, so every value replays and shrinks with the case.
    """

    def __init__(self, value: Callable[[], int]) -> None:
        """Return a random source that takes its choices from value.

        Args:
            value: The function that returns the next integer choice of the
                case.
        """
        super().__init__()
        self._value: Callable[[], int] = value

    @override
    def seed(self, a: object = None, version: int = 2) -> None:
        """Do nothing, because the choices of the case are the source.

        Args:
            a: The seed. The source ignores it.
            version: The version of the seed algorithm. The source ignores it.
        """
        del a, version

    @override
    def random(self) -> float:
        """Return a float in [0, 1) from the high 53 bits of one choice."""
        return (self._value() >> 11) * _UNIT

    @override
    def getrandbits(self, k: int, /) -> int:
        """Return k random bits from the high bits of ceil(k / 64) choices.

        Args:
            k: The number of bits.

        Returns:
            An int below 2^k.

        Raises:
            ValueError: k is negative.
        """
        if k < 0:
            msg = "number of bits must be non-negative"
            raise ValueError(msg)
        words = -(-k // 64)
        bits = 0
        for _ in range(words):
            bits = (bits << 64) | self._value()
        return bits >> (64 * words - k)

    @override
    def getstate(self) -> NoReturn:
        """Refuse, because the choices of the case are the state of the source.

        Raises:
            NotImplementedError: Always.
        """
        msg = "prop: the random source of a case does not have a state"
        raise NotImplementedError(msg)

    @override
    def setstate(self, state: object) -> NoReturn:
        """Refuse, because the choices of the case are the state of the source.

        Args:
            state: The state that the caller saved. The source ignores it.

        Raises:
            NotImplementedError: Always.
        """
        del state
        msg = "prop: the random source of a case does not have a state"
        raise NotImplementedError(msg)


class Case:
    """One call of the body of a property.

    The assertions of the body report to the case, and its draws decode the
    inputs of the body from the choices of the case. A case is a seat, a
    seat that takes failure records and a seat with cleanups, so every
    assertion of this library works on it.
    """

    def __init__(
        self, engine: Engine, seat: Seat, slot: Slot | None, location: Location
    ) -> None:
        """Return the case of one call of a body.

        The run of the property constructs each case.

        Args:
            engine: The record of the call in the engine.
            seat: The seat of the property.
            slot: The slot of the call of the property, or None when the call
                is not recorded. The slot records the calls of the case.
            location: The location of the records of the case.
        """
        self._state: _State = _State(engine, seat, location)
        _STATES[self] = weakref.ref(self._state)
        engine.owner = self
        walk = engine.walk
        run(own(self), slot, None if walk is None else (lambda: len(walk)))

    def helper(self) -> None:
        """Do nothing, because the records of a case have the frames of their calls."""

    def fail(self, message: str) -> NoReturn:
        """Keep a record of message without an assertion, and end the case.

        The contract of the record is the message, and its location is the
        innermost frame of the caller.

        Args:
            message: The failure message.
        """
        state = self._state
        _check(state)
        state.records.append(Failure("", message, {}, _locate(state.location)))
        _stop(state, _failed_with(state.records[0]))

    def record(self, message: str) -> None:
        """Keep a record of message without an assertion, and let the body run on.

        The contract of the record is the message, and its location is the
        innermost frame of the caller. The case fails when the body ends.

        Args:
            message: The failure message.
        """
        state = self._state
        _check(state)
        state.records.append(Failure("", message, {}, _locate(state.location)))

    def report(self, failure: Failure, aborting: bool) -> None:
        """Keep the failure record of an assertion.

        An aborting record ends the case. After a recording record the body
        runs on, and the case fails when the body ends. A case whose records
        are pinned keeps the record at the call site of the property.

        Args:
            failure: The record.
            aborting: When True, the assertion stops at its failure.
        """
        state = self._state
        _check(state)
        location = state.location
        if location.pinned:
            failure = Failure(
                failure.assertion, failure.contract, failure.detail, location.site
            )
        state.records.append(failure)
        if aborting:
            _stop(state, _failed_with(state.records[0]))

    def report_fault(self, fault: BaseException, ending: bool) -> None:
        """Receive a fault of a call of the body.

        A fault that ends its call ends the case, also after a failure. The
        run of the property then ends in every phase, and the property ends
        its call with the same fault. A noted fault passes to the seat of the
        property, and the body runs on.

        Args:
            fault: The fault.
            ending: When True, the fault ends its call.
        """
        if not ending:
            note_fault(self._state.seat, fault)
            return
        state = self._state
        if isinstance(state.stopped, _FINAL):
            raise state.stopped
        state.stopped = Faulted(fault)
        raise state.stopped

    def clock(self) -> Clock:
        """Return the clock of the seat of the property.

        Every case then runs under the clock of the test.

        Returns:
            The clock.
        """
        return clock_of(self._state.seat)

    def draw(self, generator: Decoder[_T], label: str) -> _T:
        """Return a value of generator, and record it under label.

        The counterexample shows the value under its label. Two draws can
        share a label. A draw ends the case under these conditions.

        - The case repeats a tested case.
        - The body requested other choices after the same values in an
          earlier case.
        - The case passes its cap on choices.

        Args:
            generator: The generator.
            label: The label of the draw.

        Returns:
            The value.
        """
        return _on(self._state, lambda engine: engine.draw(generator, label))

    def assume(self, condition: bool) -> None:
        """Reject the case when condition is false.

        The rejection ends the case. The run does not count, shrink or fail a
        rejected case. A run that rejects more than ten cases for every valid
        one fails as rejected.

        Args:
            condition: The condition.
        """
        state = self._state
        _check(state)
        if not condition:
            _stop(state, Rejected())

    def skip(self, reason: str) -> NoReturn:
        """End the run of the property as skipped, with reason.

        The case ends at the call and runs its cleanups. The run does not
        report a failure record, and it skips the test of the seat of the
        property where that seat skips its test. Once the run has found a
        failing case, a case that skips ends as a case that does not fail,
        and the run goes on.

        A body skips the run where its environment lacks a capability:

            if not direct_io_supported(tmp_path):
                case.skip("the file system refuses direct I/O")

        Args:
            reason: The reason of the skip.
        """
        state = self._state
        _check(state)
        _stop(state, Skipped(reason))

    def classify(self, label: str) -> None:
        """Count the case under label for the coverage requirements of prop.require.

        A label that the case counts twice counts once.

        Args:
            label: The label.
        """
        state = self._state
        _check(state)
        state.engine.classify(label)

    def note(self, message: str) -> None:
        """Attach message to the case.

        Only a failing case reports its notes.

        Args:
            message: The note.
        """
        state = self._state
        _check(state)
        state.engine.note(message)

    def rand(self) -> random.Random:
        """Return a random.Random that makes its values from integer choices.

        Each choice is over the whole unsigned 64-bit range, so randomised
        code under test replays and shrinks without change. Each value of the
        source requests an input in the same way as a draw. getstate and
        setstate raise NotImplementedError.

        Returns:
            The source.
        """
        return _Random(self._random)

    def _random(self) -> int:
        """Return the next integer choice of rand."""
        return _on(self._state, lambda engine: engine.random())

    def observe(self, fingerprint: int) -> None:
        """Record a fingerprint of the state of the subject at this point.

        A replay of the case compares its fingerprints with the recorded
        ones. A run ends as flaky when its replay records another fingerprint
        or another number of fingerprints.

        Args:
            fingerprint: The fingerprint.
        """
        state = self._state
        _check(state)
        state.engine.observe(fingerprint)

    def cleanup(self, fn: Callable[[], object]) -> None:
        """Register fn to run when the case ends.

        The case ends after its body returns, fails, raises, rejects the case,
        skips or stops at a draw. The last registered cleanup runs first. The run
        awaits a cleanup that returns an awaitable. A failure in a cleanup
        fails the case in the same way as a failure in the body, and the
        later cleanups still run. A cleanup that a cleanup registers runs
        before the case ends.

        Args:
            fn: The cleanup.
        """
        self._state.cleanups.append(fn)

    def history(self) -> History:
        """Return the history of the case.

        The history records the calls that the body makes to a subject. A
        check of history and a machine of stateful use it. It is empty when
        the case starts, and every call returns the same history.

        Returns:
            The history.
        """
        state = self._state
        _check(state)
        return state.history

    def target(self, label: str, score: float) -> None:
        """Record score under label.

        When a label has two scores, the case keeps the higher score. A
        campaign explores near the cases with the highest score of each
        label. Every other run records the score, and the score does not
        change what the run generates.

        Args:
            label: The label.
            score: The score.
        """
        state = self._state
        _check(state)
        state.engine.target(label, score)


def _state_of(c: Case) -> _State:
    """Return the state of a case. The case keeps its state alive."""
    return cast("_State", _STATES[c]())


def on_engine(c: Case, fn: Callable[[Engine], _T]) -> _T:
    """Return the result of fn on the record of c in the engine.

    fn runs in the same way as a draw of c. The call raises the signal that
    ended the case. It keeps a signal that fn raises as the signal that ends
    the case. The steps of a machine and the task scheduler make their
    choices this way.

    Args:
        c: The case.
        fn: The function of the record.

    Returns:
        The result of fn.
    """
    return _on(_state_of(c), fn)


def case_of(engine: Engine) -> Case:
    """Return the case that runs a body on an engine case.

    An engine case without a body gets a case of a Standard seat. The explain
    phase decodes a filling on such an engine case.

    Args:
        engine: The engine case.

    Returns:
        The case.
    """
    owner = engine.owner
    if isinstance(owner, Case):
        return owner
    return Case(engine, Standard(), None, Location(None))


def _caught(state: _State, error: BaseException) -> None:
    """Keep the signal or the first exception that a body or a cleanup raised.

    A FaultError of the library ends the case as a reported fault does. A
    fault replaces every earlier signal that does not end the run.
    """
    if isinstance(error, FaultError):
        error = Faulted(error)
    if isinstance(error, Faulted):
        if not isinstance(state.stopped, _FINAL):
            state.stopped = error
        return
    if isinstance(error, _SIGNALS):
        if state.stopped is None:
            state.stopped = error
    elif state.raised is None:
        state.raised = error


def _running() -> bool:
    """Report whether an event loop runs in this thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _settle(state: _State, fn: Callable[[], object], loop: Loop) -> None:
    """Call fn, run an awaitable that it returns on loop, and keep what it raises.

    loop cannot run while another loop runs in this thread. Its fault then
    ends the call of the property and passes to the caller.
    """
    try:
        returned = fn()
    except _ENDINGS as error:
        _caught(state, error)
        return
    if not inspect.isawaitable(returned):
        return
    if not _running():
        try:
            loop.resolve(returned)
        except _ENDINGS as error:
            _caught(state, error)
        return
    loop.resolve(returned)


def _failure_of(state: _State) -> Failed | None:
    """Return the failure of a case.

    The failure is the first record of the case, or a record of its
    exception. A record of an exception does not have an assertion. Its
    contract is the str of the exception, and its detail has the class of
    the exception and its traceback.
    """
    if state.records:
        return _failed_with(state.records[0])
    raised = state.raised
    if raised is None:
        return None
    identity = of_error(raised, state.location.site)
    detail = {
        "error": identity.error,
        "stack": "".join(traceback.format_exception(raised)),
    }
    failure = Failure("", str(raised), detail, identity.where)
    return Failed(key_of(identity), Failing(failure, identity))


def execute(c: Case, body: Callable[[Case], object], loop: Loop) -> None:
    """Run body on c as one case of a property, and end the case.

    The case runs its cleanups after the body. Then it raises the signal or
    the failure that ended it.

    - A case that repeats a tested case, diverges, meets an entry of a trace
      that it cannot follow, or ends with a fault raises that signal. A fault
      of a call of the body raises Faulted.
    - A case that failed in the body or in a cleanup raises its failure. It
      raises the failure also when the case was rejected, skipped or passed
      its cap.
    - A rejected case raises its rejection, and a skipped case its skip.
    - A case that passed returns.

    Args:
        c: The case.
        body: The body. It can return an awaitable.
        loop: The event loop of the run. It runs an awaitable of the body or
            of a cleanup.
    """
    state = _state_of(c)
    _settle(state, lambda: body(c), loop)
    while state.cleanups:
        _settle(state, state.cleanups.pop(), loop)
    signal = state.stopped
    if isinstance(signal, _FINAL):
        raise signal
    failed = _failure_of(state)
    if failed is not None:
        raise failed
    if signal is not None:
        raise signal
