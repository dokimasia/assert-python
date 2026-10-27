# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The values of a generator for a seed, outside a property.

A benchmark takes its inputs from a generator, so every run measures the
same inputs, and the inputs cover more paths than one literal does. The
options of using give types the generators that a run of the property gives
them, so the benchmark and the property draw from one domain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from dokimi_assert._prop.case import Faulted
from dokimi_assert._prop.engine.case import Case, Generating, Rejected, Skipped
from dokimi_assert._prop.engine.source import case_source
from dokimi_assert._prop.option import Option, configure
from dokimi_assert._prop.registry import scope

if TYPE_CHECKING:
    from dokimi_assert._prop.engine.generator import Generator

__all__ = ["values"]

_T = TypeVar("_T")

#: The most cases that values rejects for each value that it returns. A run
#: of a property gives up at the same ratio.
_REJECTIONS_PER_VALUE = 10

#: Every seed is an unsigned 64-bit integer below this limit.
_SEED_LIMIT = 2**64


def values(generator: Generator[_T], seed: int, n: int, *options: Option) -> list[_T]:
    """Return n values of generator for seed.

    The values are those of the random cases of seed, in order, without the
    cases that the generator rejects. Case k decodes from the random source
    of seed + k, as a random case of a run does, so the values are the
    outputs of the generation and shapes vectors of the definition for the
    seed. Two calls with one seed return the same values, and a call with a
    larger n returns the same first values.

    values does not run a property. It does not try the simplest case or a
    boundary case, shrink, record an assertion or write a stored case, and
    it does not read the variables DOKIMI_ASSERT_PROP_*. An exception that
    the generator raises passes through.

    Each option of using makes its generator the generator of its type, as it
    does in a run. A draw of of(t) decodes with the stated generator of t,
    and a draw of of(u) generates each t inside u with it. Inside the stated
    generator of t, a draw of of(t) decodes without it. Without the options,
    a draw of of uses the registration or the shape of its type, also inside
    a run that gives the type a generator through using.

        ids = prop.values(prop.of(str), 42, 100)
        not_cancelled = prop.of(Status).filter(lambda s: s is not Status.CANCELLED)
        orders = prop.values(prop.of(Order), 42, 100, prop.using(Status, not_cancelled))

    Args:
        generator: The generator.
        seed: The seed. It is an int in [0, 2^64).
        n: The number of values. It is an int of 0 or more.
        *options: The options of using. A later option of one type replaces
            an earlier one.

    Returns:
        The values, in order.

    Raises:
        ValueError: n is not an int of 0 or more, seed is not an int in
            [0, 2^64), an option is not an option of using, the generator
            rejects more than ten cases for each of the n values, the
            generator skips a case, or the generator ends a case with a
            fault. values runs no test that a skip could skip or a fault could
            end. The cause of the error of a fault is the fault.
    """
    call = f"values(generator, {seed!r}, {n!r})"
    if type(n) is not int or n < 0:
        msg = f"prop: {call} needs a count that is an int of 0 or more"
        raise ValueError(msg)
    if type(seed) is not int or not 0 <= seed < _SEED_LIMIT:
        msg = f"prop: {call} needs a seed that is an int in [0, 2^64)"
        raise ValueError(msg)
    for option in options:
        if not isinstance(option, Option) or option.kind != "using":  # type: ignore[redundant-expr]  # pyright: ignore[reportUnnecessaryIsInstance]
            kind = getattr(option, "kind", type(option).__name__)
            msg = f"prop: {call} takes the options of using alone, not {kind}"
            raise ValueError(msg)
    out: list[_T] = []
    rejected = 0
    index = 0
    with scope(configure(options).using):
        while len(out) < n:
            case = Case(Generating(case_source(seed, index)))
            index += 1
            try:
                out.append(generator.decode(case))
            except Skipped as skipped:
                msg = (
                    f"prop: {call} stops at a case that the generator skips: "
                    f"{skipped.reason}"
                )
                raise ValueError(msg) from None
            except Faulted as faulted:
                msg = f"prop: {call} stops at a fault of the generator: {faulted}"
                raise ValueError(msg) from faulted.fault
            except Rejected:
                rejected += 1
                if rejected > _REJECTIONS_PER_VALUE * n:
                    msg = (
                        f"prop: {call} stops after the generator rejects {rejected} "
                        f"cases for {n} values"
                    )
                    raise ValueError(msg) from None
    return out
