# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The run of the property forms.

A form runs its assertion on each case of a run in the same way as for_all
runs a body. The arguments of the assertion are the values that the case
generates. The form reads the type of its input from the annotation of the
input parameter of its function, and the generators of the run derive the
generator of that type. For a function of more than one input parameter,
the form generates the parameters in order as the fields of a record. A
form also takes the options of a run, the relaxations of its assertion and
the cases of example and examples. Those cases run before the stored cases.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.option import Option as Relaxation
from dokimi_assert._matcher.verdict import Running
from dokimi_assert._prop.case import Case
from dokimi_assert._prop.engine.inverse import (
    CannotInvertError,
    NoInverseError,
    invert,
)
from dokimi_assert._prop.engine.runner import Values
from dokimi_assert._prop.option import FormOnly, FormOption, Option, configure
from dokimi_assert._prop.property import Call, Property
from dokimi_assert._prop.registry import Generators, scope
from dokimi_assert.failure import call_site

if TYPE_CHECKING:
    from dokimi_assert._matcher.seat import Seat
    from dokimi_assert._prop.engine.choice import Choice
    from dokimi_assert._prop.engine.generator import Generator

__all__ = ["INPUT", "PAIR", "TRIPLE", "Check", "Form", "run_form"]

#: The label of the input of a form of one input.
INPUT = ("input",)

#: The labels of the two inputs of is_commutative.
PAIR = ("a", "b")

#: The labels of the three inputs of is_associative.
TRIPLE = ("a", "b", "c")

#: The kinds of parameter that a form generates.
_POSITIONAL = (
    inspect.Parameter.POSITIONAL_ONLY,
    inspect.Parameter.POSITIONAL_OR_KEYWORD,
)


@dataclass(frozen=True, slots=True)
class Form:
    """A property form.

    Attributes:
        op: The operation. The text of each fault starts with it. An example
            is prop.equal.
        id: The id of the form and the assertion of its record. An example is
            prop-equal.
        relaxed: When True, the assertion of the form takes relaxations.
        labels: The labels of the generated arguments in their order.
        skip: The number of parameters of the function before its input. The
            handle of none_handle_safe is such a parameter.
    """

    op: str
    id: str
    relaxed: bool
    labels: tuple[str, ...] = INPUT
    skip: int = 0


#: The function that runs the assertion of a form on a case. It takes the
#: case, the arguments of the function of the form, and the relaxations.
Check = Callable[[Case, tuple[Any, ...], tuple[Relaxation, ...]], object]


@dataclass(frozen=True, slots=True)
class _Sorted:
    """The options of one call of a form, by kind."""

    run: list[Option]
    relaxations: list[Relaxation]
    examples: list[FormOnly]


def _sorted(options: Sequence[FormOption]) -> _Sorted:
    """Return the options of the call of a form by kind."""
    by_kind = _Sorted([], [], [])
    for option in options:
        if isinstance(option, Relaxation):
            by_kind.relaxations.append(option)
        elif isinstance(option, FormOnly):
            by_kind.examples.append(option)
        else:
            by_kind.run.append(option)
    return by_kind


def _parameters(function: Callable[..., Any], skip: int) -> list[inspect.Parameter]:
    """Return the input parameters of a function.

    They are its positional parameters after the first skip of them.

    Raises:
        FaultError: The signature of the function cannot be read, its
            annotations do not resolve, it does not take an input, or an
            input parameter does not have an annotation.
    """
    name = getattr(function, "__qualname__", repr(function))
    try:
        signature = inspect.signature(function, eval_str=True)
    except NameError as error:
        at = ""
        raise FaultError(
            at, f"the annotations of the function {name} do not resolve", error
        ) from error
    except (TypeError, ValueError) as error:
        at = ""
        raise FaultError(
            at, f"the signature of the function {name} cannot be read", error
        ) from error
    positional = [p for p in signature.parameters.values() if p.kind in _POSITIONAL]
    parameters = positional[skip:]
    if not parameters:
        at = ""
        raise FaultError(at, f"the function {name} does not take an input")
    for parameter in parameters:
        if parameter.annotation is inspect.Parameter.empty:
            at = ""
            raise FaultError(
                at,
                f"the parameter {parameter.name} of the function {name} does not "
                "have an annotation, so the form cannot read the type of its input",
            )
    return parameters


def _input_of(
    form: Form, function: Callable[..., Any], using: Generators
) -> tuple[Generator[Any], type | None]:
    """Return the generator of the input of a form, and the record of its parameters.

    For a form of one input whose function has more than one input parameter,
    the record is the dataclass of those parameters. It is None for every
    other form.

    Raises:
        FaultError: An input parameter of the function does not have an
            annotation, or the reader does not read its type.
    """
    parameters = _parameters(function, form.skip)
    if len(form.labels) > 1 or len(parameters) == 1:
        return using.read(parameters[0].annotation), None
    name = getattr(function, "__name__", "parameters")
    fields = [(p.name, p.annotation) for p in parameters]
    record = dataclasses.make_dataclass(name, fields, frozen=True)
    return using.read(record), record


def _arguments_of(record: type | None, values: tuple[Any, ...]) -> tuple[Any, ...]:
    """Return the arguments of the function of a form from the values of a case."""
    if record is None:
        return values
    return tuple(getattr(values[0], f.name) for f in dataclasses.fields(record))


def _value_of(record: type | None, value: Any) -> Any:
    """Return a value of an example in the form that the generator produces.

    An example of a function of more than one parameter gives a tuple of
    their values.
    """
    if record is None or not isinstance(value, tuple):
        return value
    parts: tuple[Any, ...] = value
    if len(parts) != len(dataclasses.fields(record)):
        return value
    return record(*parts)


def _case_of(
    generator: Generator[Any], values: Sequence[Any], at: Sequence[str]
) -> tuple[Choice, ...] | Values:
    """Return the case of values. Each value is one generated argument.

    The case is the choices that decode to the values. It is the values
    themselves when the generator does not have an inverse of one of them.

    Raises:
        FaultError: The generator does not produce a value, or raises for
            it. The fault is at the value.
    """
    choices: list[Choice] = []
    for index, value in enumerate(values):
        try:
            choices.extend(invert(generator, value))
        except NoInverseError:
            return Values(tuple(values))
        except CannotInvertError as error:
            raise FaultError(
                at[index],
                "the generator of the input does not produce the value",
                error,
            ) from error
        except Exception as error:
            raise FaultError(
                at[index], "the generator of the input raises for the value", error
            ) from error
    return tuple(choices)


def _examples_of(
    labels: tuple[str, ...],
    generator: Generator[Any],
    record: type | None,
    examples: Sequence[FormOnly],
) -> list[tuple[Choice, ...] | Values]:
    """Return the cases of the example options in their order.

    Each case is its choices, or its values where the generator does not
    have an inverse.

    Raises:
        FaultError: An example has another number of values than the form
            generates, a form of more than one input takes examples, or the
            generator does not produce a value.
    """
    cases: list[tuple[Choice, ...] | Values] = []
    for i, option in enumerate(examples):
        at = f"{option.kind}[{i}]"
        values = [_value_of(record, value) for value in option.value]
        if option.kind == "example":
            if len(values) != len(labels):
                raise FaultError(
                    at,
                    f"the example has {len(values)} values, and the form generates "
                    f"{len(labels)}",
                )
            places = [f"{at}[{j}]" for j in range(len(values))]
            cases.append(_case_of(generator, values, places))
            continue
        if len(labels) != 1:
            raise FaultError(
                at,
                "the examples option needs a form of one input, and the form "
                f"generates {len(labels)}",
            )
        cases.extend(
            _case_of(generator, [value], [f"{at}[{j}]"])
            for j, value in enumerate(values)
        )
    return cases


def run_form(
    seat: Seat,
    form: Form,
    msg: str,
    function: Callable[..., Any],
    options: Sequence[FormOption],
    check: Check,
) -> None:
    """Run a property form on seat.

    The record of the form has the id of the form and the contract msg, and
    its location is the call of the form. check runs the assertion of the
    form on each case, with the case as its seat. The form reads the type of
    its input from function.

    Args:
        seat: The seat that receives the failure.
        form: The form.
        msg: The contract under test.
        function: The function that takes the input.
        options: The options of the call.
        check: The function that runs the assertion on a case.
    """
    __tracebackhide__ = True
    seat.helper()
    where = call_site()
    running = Running.begin(seat, where)
    call = Call(form.op, form.id, msg, where, pinned=True)
    by_kind = _sorted(options)
    if by_kind.relaxations and not form.relaxed:
        refused = FaultError(
            "",
            "the form does not take a relaxation, because its assertion does not "
            "take one",
        )
        Property.fault(running, call, refused)
        return
    try:
        config = configure(by_kind.run)
        with scope(config.using):
            generator, record = _input_of(form, function, config.using)
            cases = _examples_of(form.labels, generator, record, by_kind.examples)
        prop = Property.of(seat, call, config, cases)
    except FaultError as error:
        Property.fault(running, call, error)
        return
    relaxations = tuple(by_kind.relaxations)

    def body(c: Case) -> object:
        values = tuple(c.draw(generator, label) for label in form.labels)
        return check(c, _arguments_of(record, values), relaxations)

    prop.run(seat, running, body)
