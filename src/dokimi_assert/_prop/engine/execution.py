"""One call of a body, and how it ended.

The runner, the shrinker and the explain phase each call the body through
execute. A case that walks the case tree can end early as a repeat or a
divergence. A case outside the tree cannot. Stored cases and shrink
candidates are such cases. A run on more than one worker runs its cases
outside the tree and keeps their walks. entered walks each case into the
tree once the case has ended. The walk is the same as the walk of the case
on one worker.

A body can make its case run more than once through Case.repeat. The steps
of a machine call it when the clients of a concurrent section run on
threads, because threads do not replay. Each later run replays the choices
of the case outside the tree. The first run that fails ends the case.

Each call of a body has a phase. The phase is the part of the run that made
the call. An observer of a run receives every call with its phase. The calls
arrive in the order of a run on one worker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, cast

from dokimi_assert._prop.engine.case import (
    Case,
    Failed,
    Overrun,
    Place,
    Provider,
    Rejected,
    Replaying,
    Walked,
    Where,
)
from dokimi_assert._prop.engine.choice import Bounds
from dokimi_assert._prop.engine.tree import Diverged, Ending, Repeated, Tree, Walker

__all__ = [
    "Body",
    "Divergence",
    "Execution",
    "Observer",
    "Phase",
    "Status",
    "entered",
    "execute",
    "finish",
    "identity_of",
    "repeat",
    "unobserved",
]

#: The body of a property. It receives the case and draws values from it. It
#: then fails the case or returns. The engine ignores the return value. The
#: property layer runs the coroutine of an async body to its end before the
#: body returns.
Body = Callable[[Case], object]

#: The part of a run that called the body. It is the kind of the case.
#: example is a case whose values the caller gives. fuzz is the case that the
#: fuzz bridge decodes from the input of a fuzzer.
Phase = Literal[
    "example",
    "stored",
    "simplest",
    "random",
    "prefix",
    "edge",
    "coverage",
    "replay",
    "shrink",
    "explain",
    "token",
    "fuzz",
]

#: How one case ended.
Status = Literal["passed", "failed", "rejected", "repeated", "diverged"]


@dataclass(frozen=True, slots=True)
class Divergence:
    """The first difference between two runs of the same choices.

    The kind of difference is one of these.

    - request means that the bounds of a request differ. None means that the
      case ended before the request.
    - fingerprint means that an observed fingerprint differs. None means
      that the run did not observe a fingerprint there.
    - verdict means that a replay passed or failed in another way. The two
      sides are the identities of the failures. None means a pass.

    Attributes:
        what: The kind of difference.
        index: The position of the request or the fingerprint that differs.
            For a verdict, it is the number of choices of the recorded case.
        recorded: The recorded side.
        replayed: The replayed side.
        label: The label of the draw that was running, or None.
        step: The part and the step of a machine, or None.
    """

    what: Literal["request", "fingerprint", "verdict"]
    index: int
    recorded: Bounds | int | str | None
    replayed: Bounds | int | str | None
    label: str | None = None
    step: Place | None = None


@dataclass(frozen=True, slots=True)
class Execution:
    """The case of one call of the body and how the case ended.

    Attributes:
        case: The case. When a later run of a case failed, it is the case of
            that run.
        status: How the case ended.
        failure: The failure of a failed case, or None.
        divergence: The divergence of a diverged case, or None.
        overran: When True, the case asked for more choices than its cap
            allows. Such a case has the status rejected and no leaf in the
            case tree.
        stopped: The step at which the walk into the case tree stopped a
            case that ran outside the tree. It is None for any other case. A
            run on one worker does not make the calls that the case made
            after that step.
        ran: The cases of the runs of a case that ran more than once. They
            are in the order of the runs. The tuple is empty for a case that
            ran once.
    """

    case: Case
    status: Status
    failure: Failed | None = None
    divergence: Divergence | None = None
    overran: bool = False
    stopped: int | None = None
    ran: tuple[Case, ...] = ()

    @property
    def runs(self) -> int:
        """The number of runs of the body that the execution made."""
        return max(len(self.ran), 1)

    @property
    def cases(self) -> tuple[Case, ...]:
        """The cases of the runs of the body in the order of the runs."""
        return self.ran or (self.case,)


def identity_of(execution: Execution) -> str | None:
    """Return the identity of the failure of an execution.

    Args:
        execution: The execution.

    Returns:
        The identity, or None when the case did not fail.
    """
    return None if execution.failure is None else execution.failure.identity


#: A function that receives each call of the body of a run with its phase.
Observer = Callable[[Phase, Execution], None]


def unobserved(phase: Phase, execution: Execution) -> None:
    """Ignore a call. A run that nobody records uses this observer.

    Args:
        phase: The phase of the call.
        execution: The call.
    """
    del phase, execution


def _divergence_of(diverged: Diverged, where: Where) -> Divergence:
    """Return the divergence of the tree as a request divergence of a case.

    The divergence has the label and the step of the place where the case
    made the request. A case that ended where an earlier case made a request
    did not make a request there. Its where is then empty.
    """
    return Divergence(
        "request",
        diverged.index,
        diverged.recorded,
        diverged.requested,
        where.label,
        where.place,
    )


def execute(
    body: Body,
    provider: Provider,
    max_choices: int,
    tree: Tree | None = None,
    limit: int | None = None,
) -> Execution:
    """Call the body on a case whose values come from a provider.

    With a tree, the case walks the tree. A repeat or a divergence then ends
    the case early. A case that overruns its cap is rejected without a leaf.
    A case with more than one repeat runs again under the rules of repeat.
    An error of the body that is not a signal of the case propagates to the
    caller.

    Args:
        body: The body.
        provider: The provider of the values of the case.
        max_choices: The largest number of choices that the case can make.
        tree: The case tree, or None for a case outside it.
        limit: The largest number of runs of the body, or None to run the
            repeats of the case.

    Returns:
        The execution.
    """
    walker = None if tree is None else tree.walker()
    return finish(body, Case(provider, max_choices, walker), walker, limit)


def finish(
    body: Body, c: Case, walker: Walker | None = None, limit: int | None = None
) -> Execution:
    """Call the body on a case that has not run, and return how it ended.

    A case with a walker walks the case tree in the same way as in execute.
    A case with more than one repeat runs again under the rules of repeat.
    An error of the body that is not a signal of the case propagates to the
    caller.

    Args:
        body: The body.
        c: The case.
        walker: The walker that observes the choices of the case, or None for
            a case outside the case tree.
        limit: The largest number of runs of the body, or None to run the
            repeats of the case.

    Returns:
        The execution.
    """
    return repeat(_once(body, c, walker), body, limit)


def _once(body: Body, c: Case, walker: Walker | None = None) -> Execution:
    """Call the body once on a case that has not run, and return how it ended."""
    ending: Ending = "passed"
    failure: Failed | None = None
    try:
        body(c)
    except Repeated:
        return Execution(c, "repeated")
    except Diverged as diverged:
        divergence = _divergence_of(diverged, c.wheres[diverged.index])
        return Execution(c, "diverged", divergence=divergence)
    except Overrun:
        return Execution(c, "rejected", overran=True)
    except Rejected:
        ending = "rejected"
    except Failed as failed:
        ending = "failed"
        failure = failed
    if walker is not None:
        try:
            walker.end(ending)
        except Diverged as diverged:
            return Execution(
                c, "diverged", divergence=_divergence_of(diverged, Where())
            )
    return Execution(c, ending, failure)


def repeat(execution: Execution, body: Body, limit: int | None = None) -> Execution:
    """Run the body again on the choices of a case that passed.

    Each later run replays the choices of the case outside the case tree.
    The runs stop at the first run that fails, after `repeats` runs, or after
    `limit` runs. The first run that fails ends the case with its record.
    The execution keeps the case of every run.

    Args:
        execution: The first run of the case.
        body: The body.
        limit: The largest number of runs, or None to run the repeats of the
            case.

    Returns:
        The execution of the case. It is the first run with the cases of
        every run when no later run failed.
    """
    c = execution.case
    runs = c.repeats if limit is None else min(c.repeats, limit)
    if execution.status != "passed" or runs == 1:
        return execution
    ran = [c]
    for _ in range(1, runs):
        again = Case(Replaying(c.choices), c.max_choices)
        later = _once(body, again)
        ran.append(again)
        if later.status == "failed":
            return replace(later, ran=tuple(ran))
    return replace(execution, ran=tuple(ran))


def entered(tree: Tree, execution: Execution) -> tuple[Execution, int]:
    """Walk the first run of an execution that ran outside the case tree into the tree.

    The walk takes every choice that the first run made. It includes the
    choices that a rewind removed from the record, because a case that walks
    the tree as it runs steps them too. The walk stops where such a case
    would have stopped.

    - It stops at a choice that repeats a tested case.
    - It stops at a request that differs from the recorded request.

    A stopped case does not keep its later runs, because a run on one worker
    does not make them. A case that the walk does not stop ends in the same
    way as its first run. It has a leaf unless it overran its cap, and it
    keeps its later runs.

    Args:
        tree: The case tree.
        execution: The execution. Its first case kept its walk.

    Returns:
        The execution of the case in the tree and the number of steps of its
        walk.
    """
    first = execution.cases[0]
    steps = cast("list[Walked]", first.walk)
    walker = tree.walker()
    for number, step in enumerate(steps, 1):
        try:
            walker.step(step.index, step.request, step.value)
        except Repeated:
            return Execution(first, "repeated", stopped=number), number
        except Diverged as diverged:
            divergence = _divergence_of(diverged, step.where)
            stopped = Execution(
                first, "diverged", divergence=divergence, stopped=number
            )
            return stopped, number
    if not execution.overran:
        ending = "passed" if execution.ran else execution.status
        try:
            walker.end(cast("Ending", ending))
        except Diverged as diverged:
            divergence = _divergence_of(diverged, Where())
            return Execution(first, "diverged", divergence=divergence), len(steps)
    return execution, len(steps)
