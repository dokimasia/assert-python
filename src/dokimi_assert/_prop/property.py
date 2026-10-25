# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The property run that for_all, fuzz and every property form use.

A property takes its settings from its options and from the environment. It
replays the failures of its store, and it writes each new failure there. It
reports one record of its assertion. The assertion is prop-for-all or the id
of a form. The contract of the record is the contract of the property, and
its location is the call of the property. The record of each call in a case
has the phase of the case. Its parent is the call of the property.

A property notes each fault that does not end its call. A file of its store
that it skips is such a fault. A seat with report_fault receives the fault
with ending False. Any other seat gets a warning, which pytest shows in the
summary of the run.

The generators that the run gives types apply on the thread of the call and
in each run of the body, so every draw of of, its literal, its inverse and
the fillings that explain it pick the same generators.
"""

from __future__ import annotations

import json
import pathlib
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from dokimi_assert._matcher.fault import FaultError, of_operation
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import Running, note_fault
from dokimi_assert._prop.case import Case, FaultSignal, Location, case_of, execute
from dokimi_assert._prop.detail import detail_json, detail_of, record_of
from dokimi_assert._prop.directory import Loaded, claim, load, save, store_of
from dokimi_assert._prop.engine import literal, strict_json, tokens
from dokimi_assert._prop.engine.bridge import Bridging
from dokimi_assert._prop.engine.campaign import campaign
from dokimi_assert._prop.engine.case import Case as EngineCase
from dokimi_assert._prop.engine.case import Step
from dokimi_assert._prop.engine.execution import Body, Execution, Observer, Phase
from dokimi_assert._prop.engine.execution import execute as execute_engine
from dokimi_assert._prop.engine.runner import (
    Outcome,
    Settings,
    Tally,
    Values,
    conclude_case,
    run,
    run_stored,
)
from dokimi_assert._prop.engine.store import MAX_DEPTH
from dokimi_assert._prop.engine.traces import Draw, Entry, TraceError
from dokimi_assert._prop.environment import budget_of, mutated, seed_of, token_of
from dokimi_assert._prop.registry import Generators, close, scope
from dokimi_assert._prop.stored import differs, entry_of
from dokimi_assert._record.calls import Slot, cut, own
from dokimi_assert.failure import Where

if TYPE_CHECKING:
    from dokimi_assert._prop.engine.choice import Choice
    from dokimi_assert._prop.option import Config, Wrapper

__all__ = ["Call", "Property", "PropertyBody"]

#: The name of the draws option. The location of each fault in its entries
#: starts with this name.
_DRAWS = "draws"

#: The name of the around option. The text of each fault of its wrapper
#: starts with this name.
_AROUND = "around"

#: The body of a property. It is a function of a case, and it can return an
#: awaitable.
PropertyBody = Callable[[Case], object]


@dataclass(frozen=True, slots=True)
class Call:
    """The call of a property.

    Attributes:
        op: The operation. The text of each fault starts with it. It is
            prop.for_all, prop.fuzz or the operation of a form.
        assertion: The id of the assertion of the record. It is prop-for-all
            or the id of a form.
        contract: The contract of the property.
        where: The call site of the property.
        pinned: When True, every record of a case has the call site of the
            property as its location. A property form calls its assertion
            from inside the library, so the stack of the call does not
            contain a frame of the caller.
    """

    op: str
    assertion: str
    contract: str
    where: Where | None
    pinned: bool = False


def _step_of(entry: Mapping[str, Any], at: str) -> Step:
    """Return the Step of a step entry of the draws option.

    Raises:
        FaultError: The client is not an int of 0 or more.
    """
    client = entry.get("client")
    if client is not None and not (type(client) is int and client >= 0):
        at = f"{at}.client"
        raise FaultError(
            at,
            f"the client {json.dumps(client)} is not an int of 0 or more",
        )
    return Step(entry["step"], client, entry.get("drain") is True)


def _entries_of(text: str) -> tuple[Entry, ...]:
    """Parse the text of the draws option into its entries.

    The text is a JSON array of objects. A step entry has the action of its
    step under the key step. Its client is under the key client. A step entry
    of the drain also has drain: true. A draw entry has a label and a typed
    literal.

    Raises:
        FaultError: The text is not a JSON array of objects, an entry has
            neither a step nor a label and a value, a client is not an int of
            0 or more, or a value is not a typed literal. The fault is at the
            option or at the entry.
    """
    refused = "the entries are not a JSON array of objects"
    try:
        parsed = strict_json.parse(text, MAX_DEPTH)
    except strict_json.JsonError as error:
        raise FaultError(_DRAWS, refused, error) from error
    if not isinstance(parsed, list) or not all(isinstance(e, dict) for e in parsed):
        raise FaultError(_DRAWS, refused)
    entries: list[Entry] = []
    for i, entry in enumerate(cast("list[dict[str, Any]]", parsed)):
        at = f"{_DRAWS}[{i}]"
        if isinstance(entry.get("step"), str):
            entries.append(_step_of(entry, at))
            continue
        if not isinstance(entry.get("label"), str) or "value" not in entry:
            raise FaultError(at, "the entry has neither a step nor a label and a value")
        try:
            value = literal.decode(entry["value"])
        except literal.LiteralError as error:
            at = f"{at}.value"
            raise FaultError(at, "the value is not a typed literal", error) from error
        entries.append(Draw(entry["label"], value))
    return tuple(entries)


def _replay_of(config: Config) -> tuple[Choice, ...] | None:
    """Return the choices of the token that the run replays.

    The result is None for a run that does not replay a token.

    Raises:
        FaultError: The token is not a replay token. The fault is at the
            option or at the variable that sets the token.
    """
    replayed = token_of(config.replay, config.hermetic)
    if replayed is None:
        return None
    try:
        return tuple(tokens.decode(replayed.token))
    except ValueError as error:
        raise FaultError(
            replayed.source, "the text is not a replay token", error
        ) from error


def _observer_of(slot: Slot | None) -> Observer:
    """Return the observer that passes the calls of each case to the slot.

    The slot takes the calls under the phase of the case. The observer passes
    the calls of each run of a case as a run of its own. The runs keep their
    order. A run on more than one worker can stop a case at a step of its
    walk. The observer then passes only the calls before that step.
    """

    def observe(phase: Phase, execution: Execution) -> None:
        if slot is None:
            return
        for engine in execution.cases:
            calls = own(case_of(engine))
            if execution.stopped is not None:
                cut(calls, execution.stopped)
            slot.take(calls, phase)

    return observe


def _note(seat: Seat, op: str, fault: FaultError) -> None:
    """Note a fault that does not end the call of an operation on seat."""
    note_fault(seat, of_operation(op, fault), stacklevel=4)


class _Run:
    """The function run that a wrapper of the around option receives for one case.

    Its first call runs the case, and it keeps the signal or the failure that
    ended the case. A later call, and a call after the wrapper returned, run
    nothing.
    """

    def __init__(self, case: Callable[[], None]) -> None:
        """Return the run of a case that has not run."""
        self._case: Callable[[], None] = case
        self._lock: threading.Lock = threading.Lock()
        self._done: threading.Event = threading.Event()
        self.calls: int = 0
        self.started: bool = False
        self.closed: bool = False
        self.ending: BaseException | None = None

    def __call__(self) -> None:
        """Run the case at the first call before the wrapper returned."""
        with self._lock:
            self.calls += 1
            if self.calls > 1 or self.closed:
                return
            self.started = True
        try:
            self._case()
        except BaseException as ending:
            self.ending = ending
        finally:
            self._done.set()

    def close(self) -> None:
        """Make each later call run nothing, and wait for a case that started."""
        with self._lock:
            self.closed = True
        if self.started:
            self._done.wait()


def _wrapped(wrapper: Wrapper, case: Callable[[], None]) -> None:
    """Run a case inside wrapper, and end as the case ended.

    Raises:
        FaultSignal: wrapper returned without calling run, called run a second
            time or raised.
        BaseException: the signal or the failure that ended the case.
    """
    run = _Run(case)
    raised: Exception | None = None
    try:
        wrapper(run)
    except Exception as error:
        raised = error
    run.close()
    if raised is not None:
        raise FaultSignal(FaultError(_AROUND, "the wrapper raised", raised)) from raised
    if not run.started:
        raise FaultSignal(
            FaultError(_AROUND, "the wrapper returned without calling run")
        )
    if run.calls > 1:
        raise FaultSignal(FaultError(_AROUND, "the wrapper called run a second time"))
    if run.ending is not None:
        raise run.ending


class Property:
    """A property with its settings and its store.

    Its methods run the property and report each call.
    """

    def __init__(
        self,
        call: Call,
        settings: Settings,
        entries: tuple[Entry, ...],
        budget: int,
        replay: tuple[Choice, ...] | None,
        directory: str,
        around: Wrapper | None,
        using: Generators,
    ) -> None:
        """Return a property. Call Property.of instead.

        Args:
            call: The call of the property.
            settings: The settings of its runs. They do not include stored
                cases.
            entries: The entries of the draws option, or an empty tuple.
            budget: The length of a campaign in seconds. It is 0 for a
                property that does not run a campaign.
            replay: The choices of the token that the property replays, or
                None.
            directory: The directory of the store, or the empty string for a
                property without one.
            around: The wrapper of each run of the body, or None.
            using: The generators that the runs give types.
        """
        self.call: Call = call
        self._settings: Settings = settings
        self._entries: tuple[Entry, ...] = entries
        self._budget: int = budget
        self._replay: tuple[Choice, ...] | None = replay
        self._directory: str = directory
        self._around: Wrapper | None = around
        self._using: Generators = using

    @staticmethod
    def of(
        seat: Seat,
        call: Call,
        config: Config,
        examples: Sequence[tuple[Choice, ...] | Values] = (),
    ) -> Property:
        """Return the property of a call on seat under config, and close the registry.

        A later registration then raises RuntimeError.

        Args:
            seat: The seat of the call.
            call: The call.
            config: The configuration from the options of the call.
            examples: The example cases of a property form. Each case is a
                tuple of choices or a Values.

        Returns:
            The property.

        Raises:
            FaultError: The value of a variable of the engine is not valid,
                the token to replay is not a replay token, or the text of the
                draws option is not a JSON array of entries. A valid profile
                is default, ci or campaign. A valid seed is a decimal number
                below 2^64, and a valid budget is a whole number of seconds
                above 0.
        """
        close()
        seed = seed_of(call.contract, config.seed, config.hermetic)
        budget = budget_of(config.hermetic)
        entries = None if config.draws is None else _entries_of(config.draws)
        settings = Settings(
            seed=seed,
            cases=config.cases,
            max_choices=config.max_choices,
            requirements=config.requirements,
            traces=() if entries is None else (entries,),
            examples=tuple(examples),
            shrink=config.shrink,
            shrink_time=config.shrink_time,
            explain=config.explain,
            workers=config.workers,
        )
        return Property(
            call,
            settings,
            entries or (),
            budget,
            _replay_of(config),
            store_of(seat, config.store),
            config.around,
            config.using,
        )

    def run(self, seat: Seat, running: Running, body: PropertyBody) -> None:
        """Run body as the property on seat, and report the outcome to running.

        A property that replays a token runs only the case of the token. Under
        the campaign profile, the property runs a campaign. Any other property
        runs its cases. The property writes an entry of each failure of a
        counterexample to the store. A campaign writes the entry of a failure
        when it concludes the failure.

        The call ends with a fault in these cases.

        - Another property of the test has the same contract and store.
        - The store cannot be read, or it has a damaged file.
        - The body cannot follow an entry of the draws option.
        - The wrapper of the around option returns without calling run,
          calls run a second time or raises.

        Args:
            seat: The seat of the call.
            running: The call.
            body: The body.
        """
        if not self._claim(seat, running):
            return
        with scope(self._using):
            with Loop(self.call.assertion) as loop:
                cases = self._adapt(seat, running.slot, body, loop)
                observer = _observer_of(running.slot)
                if self._replay is not None:
                    self._run_replay(running, cases, observer)
                    return
                loaded = self._load(running)
                if loaded is None:
                    return
                stored = tuple(entry.choices for entry in loaded.entries)
                settings = replace(self._settings, stored=stored)
                saved: list[FaultError] = []

                def concluded(found: Outcome) -> None:
                    saved.extend(self._save(found))

                def work() -> Outcome:
                    if self._budget > 0:
                        return campaign(
                            cases, settings, self._budget, observer, concluded
                        )
                    return run(cases, settings, observer)

                outcome = self._drive(running, work)
            if outcome is None:
                return
            if outcome.kind == "counterexample" and self._budget == 0:
                concluded(outcome)
            for fault in [*self._store_faults(loaded, outcome), *saved]:
                _note(seat, self.call.op, fault)
            self._report(running, outcome)

    def _run_replay(self, running: Running, cases: Body, observer: Observer) -> None:
        """Run the case of the replay token, and report its outcome to running."""
        settings = replace(self._settings, replay=self._replay)
        outcome = self._drive(running, lambda: run(cases, settings, observer))
        if outcome is not None:
            self._report(running, outcome)

    def replay_stored(self, seat: Seat, running: Running, body: PropertyBody) -> None:
        """Replay the stored cases of the property on seat, and report them.

        The cases run oldest first. When every case passes, the report is a
        pass with the count of the cases. Otherwise the report is the first
        case that does not pass, and the run does not shrink it. A case that
        skips skips the test of the seat. The property notes each stored case
        that decodes to other values than its entry records.

        The call ends with a fault in these cases.

        - Another property of the test has the same contract and store.
        - The store cannot be read, or it has a damaged file.
        - Another fault ends the run.

        Args:
            seat: The seat of the call.
            running: The call.
            body: The body.
        """
        if not self._claim(seat, running):
            return
        loaded = self._load(running)
        if loaded is None:
            return
        stored = tuple(entry.choices for entry in loaded.entries)
        settings = replace(self._settings, stored=stored)
        with scope(self._using):
            with Loop(self.call.assertion) as loop:
                cases = self._adapt(seat, running.slot, body, loop)
                observer = _observer_of(running.slot)
                outcome = self._drive(
                    running, lambda: run_stored(cases, settings, observer)
                )
            if outcome is None:
                return
            for fault in self._store_faults(loaded, outcome):
                _note(seat, self.call.op, fault)
            self._report(running, outcome)

    def input(
        self, seat: Seat, running: Running, body: PropertyBody, data: bytes
    ) -> None:
        """Run the case that the fuzz bridge decodes from data, and report it.

        The report of a case that passes counts one valid case. The report of
        a case that the body rejects counts one rejected case. A case that
        skips skips the input, and its report counts no case. The property
        replays, shrinks and explains a failing case in the same way as a run.
        It writes each failure of the counterexample to the store.

        Args:
            seat: The seat of the call of the input.
            running: The call.
            body: The body.
            data: The bytes from the fuzzer.
        """
        settings = self._settings
        with scope(self._using):
            with Loop(self.call.assertion) as loop:
                cases = self._adapt(seat, running.slot, body, loop)
                observer = _observer_of(running.slot)

                def bridged() -> Outcome:
                    execution = execute_engine(
                        cases, Bridging(data), settings.max_choices
                    )
                    observer("fuzz", execution)
                    tally = Tally(settings.seed)
                    ended = tally.take(execution)
                    if ended is None:
                        return tally.outcome("passed")
                    if ended.kind == "skipped":
                        return ended
                    return conclude_case(cases, settings, execution, observer)

                outcome = self._drive(running, bridged)
            if outcome is None:
                return
            if outcome.kind == "counterexample":
                for fault in self._save(outcome):
                    _note(seat, self.call.op, fault)
            self._report(running, outcome)

    @staticmethod
    def fault(running: Running, call: Call, error: object) -> None:
        """End the call of a property with a fault of its operation.

        Args:
            running: The call.
            call: The call of the property.
            error: The fault.
        """
        running.faulted(
            Mode.FATAL, call.assertion, call.contract, of_operation(call.op, error)
        )

    def _adapt(
        self, seat: Seat, slot: Slot | None, body: PropertyBody, loop: Loop
    ) -> Body:
        """Return the engine body that runs body in a case on seat.

        A case on the thread of the run runs on the loop of the run. A case on
        another thread runs on a loop of its own. Under the around option,
        each case runs inside the wrapper. Each case runs under the
        generators of the run, on any thread.
        """
        location = Location(self.call.where, self.call.pinned)
        thread = threading.get_ident()
        assertion = self.call.assertion
        around = self._around
        using = self._using

        def run_case(c: Case) -> None:
            with scope(using):
                if threading.get_ident() == thread:
                    execute(c, body, loop)
                    return
                with Loop(assertion) as own_loop:
                    execute(c, body, own_loop)

        def adapted(engine: EngineCase) -> None:
            c = Case(engine, seat, slot, location)
            if around is None:
                run_case(c)
                return
            _wrapped(around, lambda: run_case(c))

        return adapted

    def _claim(self, seat: Seat, running: Running) -> bool:
        """Claim the entries of the property in its store.

        The call ends with a fault when another property of the test has
        claimed them.
        """
        if claim(seat, self._directory, self.call.contract):
            return True
        contract = json.dumps(self.call.contract, ensure_ascii=False)
        Property.fault(
            running,
            self.call,
            FaultError(
                self._directory,
                f"two properties of the test have the contract {contract}, and they "
                "would share their stored cases",
            ),
        )
        return False

    def _load(self, running: Running) -> Loaded | None:
        """Return the entries of the store.

        The result is None after the call ended with a fault.
        """
        if self._directory == "":
            return Loaded([], [])
        try:
            return load(self._directory, self.call.contract)
        except FaultError as error:
            Property.fault(running, self.call, error)
            return None

    def _drive(self, running: Running, work: Callable[[], Outcome]) -> Outcome | None:
        """Return the outcome of work, or None after the call ended with a fault.

        These faults end the call.

        - The body cannot follow an entry of the draws option.
        - A case ends with a fault.
        - A fault ends the run. A coroutine body inside a running event loop
          causes such a fault.
        """
        try:
            return work()
        except TraceError as error:
            Property.fault(running, self.call, self._refusal(error))
        except FaultSignal as signal:
            Property.fault(running, self.call, signal.fault)
        except FaultError as error:
            Property.fault(running, self.call, error)
        return None

    def _refusal(self, error: TraceError) -> FaultError:
        """Return the fault at an entry of the draws option.

        The body cannot follow the entry.
        """
        at = f"{_DRAWS}[{error.entry}].{error.reason}"
        entry = self._entries[error.entry]
        label = json.dumps(error.what, ensure_ascii=False)
        if error.reason == "step":
            return FaultError(at, f"the machine cannot take the step {label} there")
        if error.reason == "value":
            return FaultError(
                at,
                f"the generator of the draw labelled {label} does not produce the "
                "value of the entry",
            )
        if isinstance(entry, Step):
            taken = f"the step entry of {json.dumps(entry.action, ensure_ascii=False)}"
        else:
            taken = f"the entry labelled {json.dumps(entry.label, ensure_ascii=False)}"
        return FaultError(at, f"the draw labelled {label} takes {taken}")

    def _save(self, outcome: Outcome) -> list[FaultError]:
        """Write an entry of each failure of a counterexample to the store.

        The result is the fault of each entry that the store does not keep.
        The property does not write an entry in these cases.

        - The property does not have a store.
        - The process is a process of a mutation run.
        - The counterexample is a counterexample of values. The source of the
          test contains those values.
        """
        if self._directory == "" or mutated() or outcome.valued:
            return []
        found = datetime.now(UTC).date().isoformat()
        faults: list[FaultError] = []
        for execution in (cast("Execution", outcome.failing), *outcome.others):
            name, entry = entry_of(self.call.contract, execution, found)
            try:
                save(self._directory, name, entry)
            except (OSError, ValueError) as error:
                contract = json.dumps(self.call.contract, ensure_ascii=False)
                faults.append(
                    FaultError(
                        self._directory,
                        f"the store does not keep a case of {contract}",
                        error,
                    )
                )
        return faults

    def _store_faults(self, loaded: Loaded, outcome: Outcome) -> list[FaultError]:
        """Return the faults of the store that the run notes.

        The run notes each file of the store that it skipped. It also notes
        each stored case that decodes to other values than its entry records.
        """
        faults = [
            FaultError(
                str(pathlib.Path(self._directory, name)),
                "the entry is of a later format, so the run skips it",
            )
            for name in loaded.skipped
        ]
        for execution, entry in zip(outcome.stored, loaded.entries, strict=False):
            if differs(entry.counterexample, execution):
                faults.append(
                    FaultError(
                        str(pathlib.Path(self._directory, entry.name)),
                        "the stored case decodes to other values than it records, "
                        "and the run tested those",
                    )
                )
        return faults

    def _report(self, running: Running, outcome: Outcome) -> None:
        """Report the outcome as the verdict of the call.

        A skipped run skips the test of a seat that skips its test.
        """
        call = self.call
        if outcome.kind == "skipped":
            running.skipped_run(
                Mode.FATAL,
                call.assertion,
                call.contract,
                call.where,
                detail_json(outcome, detail_of(outcome)),
                cast("str", outcome.reason),
            )
            return
        if outcome.kind == "passed":
            running.passed_run(
                Mode.FATAL,
                call.assertion,
                call.contract,
                call.where,
                detail_json(outcome, detail_of(outcome)),
            )
            return
        failure, json_detail = record_of(
            outcome, call.assertion, call.contract, call.where
        )
        running.failed_run(Mode.FATAL, failure, json_detail)
