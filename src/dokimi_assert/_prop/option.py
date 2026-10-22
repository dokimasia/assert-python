"""The options of a property, and the options that only a property form takes.

Each option is one setting of a run of for_all, fuzz or a property form.
When a caller passes two options of one kind, the later one applies. Four
kinds add to the earlier options of their kind instead.

- Each require option adds a requirement.
- Each using option adds the generator of its type. A later using of one
  type replaces an earlier one.
- Each example and examples option adds cases.

A property form also takes the relaxations of the comparison. One of them is
equate_nans.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from dokimi_assert._matcher.option import Option as Relaxation
from dokimi_assert._prop.engine.case import MAX_CHOICES
from dokimi_assert._prop.engine.generator import Generator
from dokimi_assert._prop.engine.runner import DEFAULT_CASES, Requirement
from dokimi_assert._prop.engine.shrink import DEFAULT_BUDGET
from dokimi_assert._prop.registry import Generators

__all__ = [
    "DEFAULT_SHRINK_TIME",
    "Config",
    "FormOnly",
    "FormOption",
    "Option",
    "Wrapper",
    "around",
    "cases",
    "configure",
    "draws",
    "example",
    "examples",
    "explain",
    "hermetic",
    "max_choices",
    "replay",
    "require",
    "seed",
    "shrink",
    "shrink_time",
    "store",
    "using",
    "workers",
]

#: Every seed is an unsigned 64-bit integer below this limit.
_SEED_LIMIT = 2**64

#: The seconds that shrinking and explaining can take when no option sets a
#: time.
DEFAULT_SHRINK_TIME = 30.0

#: The wrapper of the runs of a property's body. It calls run once inside an
#: environment that it chooses, and returns after run returns.
Wrapper = Callable[[Callable[[], None]], object]


@dataclass(frozen=True, slots=True)
class Option:
    """One setting of a run of for_all, fuzz or a property form.

    Attributes:
        kind: The canonical id of the setting.
        value: The value of the setting. It is None for hermetic.
    """

    kind: Literal[
        "cases",
        "seed",
        "replay",
        "require",
        "shrink",
        "shrink-time",
        "max-choices",
        "store",
        "explain",
        "workers",
        "hermetic",
        "draws",
        "around",
        "using",
    ]
    value: Any = None


@dataclass(frozen=True, slots=True)
class FormOnly:
    """An option that only a property form takes.

    Attributes:
        kind: The canonical id of the option.
        value: The values of the cases.
    """

    kind: Literal["example", "examples"]
    value: Any


#: An option that a property form takes. It is a setting of the run, a
#: relaxation of the comparison or an option of the form.
FormOption = Option | Relaxation | FormOnly


@dataclass(frozen=True, slots=True)
class Config:
    """The settings of one run after its options.

    Attributes:
        cases: The number of valid cases that the run tries to generate.
        seed: The seed, or None when no option sets one.
        replay: The token of the case to replay, or None.
        requirements: The coverage requirements in the order of their options.
        shrink: The number of calls of the body that shrinking and explaining
            can make.
        shrink_time: The seconds that shrinking and explaining can take.
        max_choices: The largest number of choices that one case can make.
        store: The directory of the store, or None.
        explain: When True, the run explains a counterexample.
        workers: The number of cases that run at once.
        hermetic: When True, the run ignores the variables of the engine.
        draws: The JSON array of entries that the first case follows, or None.
        around: The wrapper of each run of the body, or None.
        using: The generators that the run gives types.
    """

    cases: int = DEFAULT_CASES
    seed: int | None = None
    replay: str | None = None
    requirements: tuple[Requirement, ...] = ()
    shrink: int = DEFAULT_BUDGET
    shrink_time: float = DEFAULT_SHRINK_TIME
    max_choices: int = MAX_CHOICES
    store: str | None = None
    explain: bool = True
    workers: int = 1
    hermetic: bool = False
    draws: str | None = None
    around: Wrapper | None = None
    using: Generators = field(default_factory=Generators)


def configure(options: Iterable[Option]) -> Config:
    """Apply the options to the defaults in their order, and return the settings.

    The defaults are 100 cases, a shrink budget of 2,000 calls and 30
    seconds, a cap of 8,192 choices, an explanation, one worker and no
    generator of a type.

    Args:
        options: The options of the run.

    Returns:
        The settings.
    """
    config = Config()
    stated: dict[object, Generator[Any]] = {}
    for option in options:
        if option.kind == "require":
            config = replace(config, requirements=(*config.requirements, option.value))
        elif option.kind == "hermetic":
            config = replace(config, hermetic=True)
        elif option.kind == "using":
            t, generator = option.value
            stated[t] = generator
        else:
            config = replace(config, **{option.kind.replace("-", "_"): option.value})
    return replace(config, using=Generators(stated))


def _counted(call: str, n: int, minimum: int) -> int:
    """Return n if it is an int of minimum or more.

    Raises:
        ValueError: n is not an int of minimum or more.
    """
    if type(n) is not int or n < minimum:
        raise ValueError(f"prop: {call}({n!r}) needs an int of {minimum} or more")
    return n


def cases(n: int) -> Option:
    """Set the number of valid cases that a run tries to generate.

    The default is 100. A run stops earlier when it has tested every input.
    It also stops after ten times n generated cases.

    Args:
        n: The number of valid cases. It is at least 1.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 1 or more.
    """
    return Option("cases", _counted("cases", n, 1))


def seed(s: int) -> Option:
    """Set the seed of the run.

    Without this option, a run takes its seed from the first of these
    sources.

    - DOKIMI_ASSERT_PROP_SEED in decimal. A hermetic run does not read it.
    - The contract in a process of a mutation run and under the ci profile.
    - A random number.

    A failing run reports its seed.

    Args:
        s: The seed. It is an int in [0, 2^64).

    Returns:
        The option.

    Raises:
        ValueError: s is not an int in [0, 2^64).
    """
    if type(s) is not int or not 0 <= s < _SEED_LIMIT:
        raise ValueError(f"prop: seed({s!r}) needs an int in [0, 2^64)")
    return Option("seed", s)


def replay(token: str) -> Option:
    """Make the run test only the case of a token.

    The run does not shrink the case. A malformed token ends the call with a
    fault. Without this option, a run that is not hermetic replays the token
    of DOKIMI_ASSERT_PROP_REPLAY.

    Args:
        token: The replay token that a failure reports.

    Returns:
        The option.
    """
    return Option("replay", token)


def require(label: str, share: float) -> Option:
    """Require that Case.classify records label in at least share of the valid cases.

    A Wilson score test decides the requirement when the run has the number
    of valid cases that it tries to generate. The test decides again each
    time that number doubles, and it stops at eight times the number. A run
    that refutes the requirement or leaves it unmet fails as coverage-unmet.

    Args:
        label: The label.
        share: The share. It is from 0 to 1.

    Returns:
        The option.

    Raises:
        ValueError: share is not a number from 0 to 1.
    """
    if type(share) not in (int, float) or not 0 <= share <= 1:
        raise ValueError(
            f"prop: require({label!r}, {share!r}) needs a share from 0 to 1"
        )
    return Option("require", Requirement(label, share))


def shrink(runs: int) -> Option:
    """Set the number of calls of the body that shrinking and explaining can make.

    The default is 2,000. A budget of 0 turns off shrinking and explaining.
    The run then reports the failing case as it found the case.

    Args:
        runs: The budget. It is at least 0.

    Returns:
        The option.

    Raises:
        ValueError: runs is not an int of 0 or more.
    """
    return Option("shrink", _counted("shrink", runs, 0))


def shrink_time(seconds: float) -> Option:
    """Set the number of seconds that shrinking and explaining can take.

    The default is 30 seconds, and a time of 0 turns off the limit. The run
    measures the time on the platform clock and not on the clock of the
    seat. A shrink that runs out of time reports the smallest case that it
    has found.

    Args:
        seconds: The time. It is at least 0.

    Returns:
        The option.

    Raises:
        ValueError: seconds is not a finite number of 0 or more.
    """
    if type(seconds) not in (int, float) or not 0 <= seconds < math.inf:
        raise ValueError(
            f"prop: shrink_time({seconds!r}) needs a finite number of 0 or more"
        )
    return Option("shrink-time", seconds)


def max_choices(n: int) -> Option:
    """Set the largest number of choices that one case can make.

    The default is 8,192. A sequence counts as one choice plus one for each
    element. The run rejects a case that requests more choices.

    Args:
        n: The cap. It is at least 1.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 1 or more.
    """
    return Option("max-choices", _counted("max_choices", n, 1))


def store(directory: str) -> Option:
    """Set the directory of the store.

    The run resolves a relative directory against the working directory, and
    the empty string turns off the store. Without this option, the store of
    a test is testdata/prop/<path>/<test>. <path> is the path of the module
    of the test from the root directory of pytest, and <test> is the name of
    the item. A seat outside a pytest item does not have a store.

    Args:
        directory: The directory.

    Returns:
        The option.
    """
    return Option("store", directory)


def explain(enabled: bool) -> Option:
    """Set whether a run explains its counterexample.

    The default is True. For each draw, the run reports whether any value
    fails there. For an integer or a duration whose value matters, the run
    also reports the nearest value that passes.

    Args:
        enabled: When True, the run explains its counterexample.

    Returns:
        The option.
    """
    return Option("explain", enabled)


def workers(n: int) -> Option:
    """Set how many cases, shrink candidates and explain fillings run at once.

    The default is 1. Above 1, the run uses n threads. It reports the same
    outcome as a run on one worker. A body that runs on more than one worker
    must be safe to call from more than one thread at once.

    Args:
        n: The number of workers. It is at least 1.

    Returns:
        The option.

    Raises:
        ValueError: n is not an int of 1 or more.
    """
    return Option("workers", _counted("workers", n, 1))


def hermetic() -> Option:
    """Make the run ignore the four variables of the engine.

    The variables are DOKIMI_ASSERT_PROP_SEED, DOKIMI_ASSERT_PROP_PROFILE,
    DOKIMI_ASSERT_PROP_BUDGET and DOKIMI_ASSERT_PROP_REPLAY. A hermetic run
    follows the default profile, and it replays only the token of the replay
    option. The tests of a property harness use this option, because their
    properties check the harness and not a subject.

    Returns:
        The option.
    """
    return Option("hermetic")


def draws(entries: str) -> Option:
    """Make the first case of the run follow the entries of a counterexample.

    The entries are a JSON array in request order. A draw entry has a label
    and a typed literal in the same form as a draw of a store entry. A step
    entry has the action of a step. It also has the client of the step in a
    concurrent section, and the drain mark in the drain. The call ends with a
    fault before any other case runs in these cases.

    - A draw meets a step entry or an entry of another label.
    - The generator of a draw does not produce the value of its entry.
    - The machine cannot take the step of a step entry.

    Args:
        entries: The JSON text of the entries.

    Returns:
        The option.
    """
    return Option("draws", entries)


def around(wrapper: Wrapper) -> Option:
    """Run each run of the body inside wrapper.

    The run calls wrapper with a function run for each run of the body. That
    includes the case of draws, each stored, generated and replayed case,
    each shrink candidate, each filling that explains a draw, each case of a
    campaign and the case of each fuzz input. wrapper calls run once inside
    an environment that it chooses, and returns after run returns. run takes
    no argument. It returns after the body and its cleanups end, also for a
    failing case, so wrapper does not change the verdict.

    The call ends with a fault when wrapper returns without calling run,
    calls run a second time or raises. Under workers, wrapper runs on more
    than one thread at once.

    Args:
        wrapper: The wrapper. It takes run and calls it once.

    Returns:
        The option.

    Raises:
        ValueError: wrapper is not callable.
    """
    if not callable(wrapper):
        raise ValueError(f"prop: around({wrapper!r}) needs a callable")  # pyright: ignore[reportUnreachable]
    return Option("around", wrapper)


def using(t: type[Any], generator: Generator[Any]) -> Option:
    """Make generator the generator of t in the run that takes the option.

    for_all, fuzz and every property form take the option. In the run, a
    draw of of(t) decodes with generator. A draw of of(u) generates each t
    that u contains with generator. The input of a form is such a draw. The
    generator takes precedence over the generator that register gave t and
    over the shape of t. Every other generator, such as integer(0, 9),
    decodes as it does without the option. A second using of one type
    replaces the first.

    Inside generator, a draw of of(t) decodes with the generator of t
    without the option, so generator can narrow the values of its own type:

        prop.using(Status, prop.of(Status).filter(lambda s: s != Status.CANCELLED))

    Args:
        t: The type.
        generator: The generator of its values.

    Returns:
        The option.
    """
    return Option("using", (t, generator))


def example(*values: Any) -> FormOnly:
    """Make a property form run a case of values before its stored cases.

    The form takes one value for each argument that it generates, in order.
    That is one value for a form over a function, two for is_commutative
    and three for is_associative. A failing example shrinks in the same way
    as any other case. An example of an input whose generator does not have
    an inverse runs on its values, and the run does not shrink it.

    Args:
        *values: The values of the generated arguments.

    Returns:
        The option.
    """
    return FormOnly("example", values)


def examples(*values: Any) -> FormOnly:
    """Make a form over one input run one case per value before its stored cases.

    The cases run in the order of the values. Each case runs in the same way
    as an example of its value.

    Args:
        *values: The values. Each value is one case.

    Returns:
        The option.
    """
    return FormOnly("examples", values)
