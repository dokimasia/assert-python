# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The call records of one test, one recorder or one run of a body.

Each seat of this library has calls, and calls_of finds them. The calls do
one of three things with a record:

- The calls of a test write each record through the sink of the test while
  the switch is on.
- The calls of a recorder keep each record for any value of the switch.
  lines returns them.
- The calls of one run of a body keep their records without a number until
  the call that ran the body takes them through Slot.take.

A call that runs a body takes its number through Slot.begin before the
calls of its body. It writes its record through Slot.write when it ends.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from dokimi_assert._record.call import Call, Phase, Place, encode_call

__all__ = [
    "Calls",
    "Sink",
    "Slot",
    "add",
    "calls_of",
    "cut",
    "keep",
    "lines",
    "own",
    "run",
    "write",
]

#: What a set of calls does with a record.
_State = Literal["off", "keeping", "writing", "running"]

#: The function through which the calls of a test write a record. It takes
#: the number of the record and its line of JSON.
Sink = Callable[[int, str], None]


@dataclass(eq=False, slots=True)
class _Entry:
    """One call among the calls of its test.

    Attributes:
        call: The record. It is None until the call has ended.
        parent: The entry of the call in whose body this call ran.
        run: The run of the body of the parent in which this call ran.
        phase: The phase of that run. Only a call in the case of a property
            has one.
        steps: The number of steps of the walk of the case of the run at the
            verdict of the call.
        seq: The number of the call. It is 0 until the calls of a test or a
            recorder number it.
        home: The calls that keep the entry now.
    """

    call: Call | None = None
    parent: _Entry | None = None
    run: int = 0
    phase: Phase | None = None
    steps: int = 0
    seq: int = 0
    home: Calls | None = None


@dataclass(eq=False, slots=True)
class Calls:
    """The calls of a seat. A new set of calls does not record anything.

    The methods of Calls are safe for concurrent use.

    Attributes:
        state: What the calls do with a record.
        next: The number of the last record that the calls numbered.
        kept: The encoded records of a recorder. The index of a record is its
            number less one.
        sink: The function through which the calls of a test write.
        entries: The calls of a run in the order of their verdicts.
        position: Returns the number of steps that the walk of the case of
            the run has made. Only a run that a property cuts has it.
    """

    state: _State = "off"
    next: int = 0
    kept: list[str] = field(default_factory=list)
    sink: Sink | None = None
    entries: list[_Entry] = field(default_factory=list)
    position: Callable[[], int] | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

    def add(self, entry: _Entry) -> None:
        """Put entry among the calls.

        The calls of a test and of a recorder number the entry and write its
        record. The calls of a run keep it.

        Args:
            entry: The entry.
        """
        with self.lock:
            entry.home = self
            if self.state == "running":
                entry.steps = self.position() if self.position is not None else 0
                self.entries.append(entry)
                return
            if self.state == "off":
                return
            self.next += 1
            entry.seq = self.next
            if entry.call is not None:
                self.emit(entry)

    def emit(self, entry: _Entry) -> None:
        """Write the record of entry. The entry has a number, and its call has ended.

        Args:
            entry: The entry.
        """
        with self.lock:
            parent = entry.parent
            place = (
                Place(seq=entry.seq)
                if parent is None
                else Place(
                    seq=entry.seq, parent=parent.seq, run=entry.run, phase=entry.phase
                )
            )
            line = encode_call(cast("Call", entry.call), place)
            if self.state == "writing":
                cast("Sink", self.sink)(entry.seq, line)
                return
            while len(self.kept) < entry.seq:
                self.kept.append("")
            self.kept[entry.seq - 1] = line

    def reset(
        self,
        state: _State,
        sink: Sink | None = None,
        position: Callable[[], int] | None = None,
    ) -> None:
        """Make the calls start over in state, and drop what they kept.

        Args:
            state: What the calls do with a record from now on.
            sink: The function through which the calls of a test write.
            position: Returns the number of steps that the walk of the case
                of the run has made.
        """
        with self.lock:
            self.state = state
            self.next = 0
            self.kept = []
            self.sink = sink
            self.entries = []
            self.position = position


#: The calls of each seat of this library.
_SEATS: weakref.WeakKeyDictionary[object, Calls] = weakref.WeakKeyDictionary()

#: Guards the registration of the calls of a seat.
_REGISTRATION = threading.Lock()


def own(seat: object) -> Calls:
    """Return the calls of seat, and register new ones for a seat without any.

    Args:
        seat: A seat of this library.

    Returns:
        The calls of the seat.
    """
    with _REGISTRATION:
        calls = _SEATS.get(seat)
        if calls is None:
            calls = Calls()
            _SEATS[seat] = calls
        return calls


def calls_of(seat: object) -> Calls | None:
    """Return the calls that keep the record of a call on seat.

    Args:
        seat: The seat of the call.

    Returns:
        The calls, or None when the call is not recorded. A call is not
        recorded on a seat that is not a seat of this library, and on a seat
        whose calls do not record.
    """
    try:
        calls = _SEATS.get(seat)
    except TypeError:
        return None
    return None if calls is None or calls.state == "off" else calls


def keep(calls: Calls) -> None:
    """Make calls the calls of a recorder. They keep the record of every call.

    The calls number the records from 1, and they drop what they kept before.

    Args:
        calls: The calls of a recorder.
    """
    calls.reset("keeping")


def write(calls: Calls, sink: Sink) -> None:
    """Make calls the calls of a test. They write each record through sink.

    The calls number the records from 1.

    Args:
        calls: The calls of the seat of a test.
        sink: The function that receives each record.
    """
    calls.reset("writing", sink=sink)


def lines(calls: Calls) -> list[str]:
    """Return the records that the calls of a recorder keep.

    A call that still runs a body does not have a line yet.

    Args:
        calls: The calls of a recorder.

    Returns:
        One line of JSON for each record, in the order of the numbers.
    """
    with calls.lock:
        return [line for line in calls.kept if line]


def add(calls: Calls, call: Call) -> None:
    """Add call to calls.

    The calls of a test and of a recorder number the call and write its
    record. The calls of a run keep it until the call that ran the body
    takes it.

    Args:
        calls: The calls of the seat of the call.
        call: The record of the call.
    """
    calls.add(_Entry(call=call))


def run(
    body: Calls, slot: Slot | None, position: Callable[[], int] | None = None
) -> None:
    """Make body the calls of one run of the body of the call that slot started.

    Args:
        body: The calls of the seat of the body.
        slot: The slot of the call that runs the body. A call that is not
            recorded has the slot None, and body then does not record.
        position: Returns the number of steps that the walk of the case of
            the run has made. Only a run whose calls cut can drop has it.
    """
    if slot is None:
        body.reset("off")
        return
    body.reset("running", position=position)


def cut(body: Calls, steps: int) -> None:
    """Drop the records of the calls that the run of body made at steps or after.

    A run on one worker does not make those calls, because the case stops at
    that step there.

    Args:
        body: The calls of a run.
        steps: The step at which the case stops.
    """
    with body.lock:
        body.entries = [entry for entry in body.entries if entry.steps < steps]


class Slot:
    """A call that runs a body.

    The call took its number before the calls of its body. It writes its
    record when it ends.
    """

    def __init__(self, entry: _Entry) -> None:
        """Return the slot of entry. Call Slot.begin instead.

        Args:
            entry: The place of the slot among the calls that keep its
                record.
        """
        self._entry: _Entry = entry
        self._runs: int = 0

    @staticmethod
    def begin(seat: object) -> Slot | None:
        """Start the record of a call on seat that runs a body.

        The call takes its number now, before the calls of its body take
        theirs.

        Args:
            seat: The seat of the call.

        Returns:
            The slot, or None when the call is not recorded.
        """
        calls = calls_of(seat)
        if calls is None:
            return None
        entry = _Entry()
        calls.add(entry)
        return Slot(entry)

    def take(self, body: Calls, phase: Phase | None = None) -> None:
        """Take the next run of the body of the slot. body has the calls of the run.

        The calls move to the calls that keep the slot. Each has the call of
        the slot as its parent, and the number and the phase of the run. A
        call of a body inside the run keeps its own parent. body is empty
        afterwards.

        Args:
            body: The calls of the run.
            phase: The phase of the run. Only the case of a property has one.
        """
        with body.lock:
            entries, body.entries = body.entries, []
        self._runs += 1
        home = cast("Calls", self._entry.home)
        for entry in entries:
            if entry.parent is None:
                entry.parent = self._entry
                entry.run = self._runs
                entry.phase = phase
            home.add(entry)

    def write(self, call: Call) -> None:
        """End the call of the slot with its record.

        The calls that keep the slot write the record under the number that
        the call took when it began.

        Args:
            call: The record of the call.
        """
        self._entry.call = call
        home = cast("Calls", self._entry.home)
        if self._entry.seq != 0:
            home.emit(self._entry)
