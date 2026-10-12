"""The spec of _prop/form.py tests the run of the property forms."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._matcher import value
from dokimi_assert._matcher.option import Option as Relaxation
from dokimi_assert._matcher.seat import Mode
from dokimi_assert._prop import generators as prop
from dokimi_assert._prop.case import Case
from dokimi_assert._prop.engine.generator import Mapped
from dokimi_assert._prop.form import INPUT, PAIR, TRIPLE, Form, run_form
from dokimi_assert._prop.option import (
    FormOption,
    cases,
    draws,
    example,
    examples,
    hermetic,
    seed,
    store,
    using,
)
from dokimi_assert.option import by_identity, equate_empty, equate_nans
from dokimi_assert.seat import Collector, Recorder
from helpers import records

#: A form of one input whose assertion does not take a relaxation.
BELOW = Form("prop.below", "prop-below", False)

#: A form of two inputs whose assertion takes relaxations.
BOTH = Form("prop.both", "prop-both", True, PAIR)

#: A form whose function takes a handle before its input.
HANDLED = Form("prop.handled", "prop-handled", False, skip=1)

#: The options that make a run of a form reproducible.
STEADY = (hermetic(), seed(1), store(""))

#: The option that generates the digits as the ints of an input.
DIGITS = using(int, prop.integer(0, 9))


def below_five(c: Case, args: tuple[Any, ...], _: tuple[Relaxation, ...]) -> None:
    """Check that each generated argument is below 5."""
    value.is_true(
        c, Mode.FATAL, all(arg < 5 for arg in args), "each argument is below 5"
    )


def digit(x: int) -> int:
    """Return x. Its annotation makes the input of a form an int."""
    return x


def sum_of(a: int, b: int) -> int:
    """Return a plus b. The annotations make both inputs ints."""
    return a + b


def mixed(a: int, b: str) -> str:
    """Return b after a. The annotations make the input a record."""
    return f"{a}{b}"


def handled(handle: object, x: int) -> int:
    """Return x. The form skips the handle before x."""
    del handle
    return x


def opaque(x: object) -> object:
    """Return x. The reader does not read the type of its annotation."""
    return x


def unresolved(x: int) -> int:
    """Return x. The annotation of x refers to a name that does not exist."""
    return x


unresolved.__annotations__["x"] = "Missing"


def unannotated(x: int) -> int:
    """Return x. The parameter x does not have an annotation at run time."""
    return x


del unannotated.__annotations__["x"]


def breaks(_: int) -> int:
    """Raise RuntimeError in the same way as a map that breaks."""
    raise RuntimeError("the map broke")


def seen_by(seen: list[tuple[Any, ...]]) -> Callable[..., None]:
    """Return a check that keeps the arguments of each case in seen."""

    def keep(_: Case, args: tuple[Any, ...], _relaxed: tuple[Relaxation, ...]) -> None:
        seen.append(args)

    return keep


class TestInput:
    """INPUT, PAIR and TRIPLE are the labels of the inputs of the forms."""

    def test_labels_the_inputs_of_the_forms(self, seat: Collector) -> None:
        """The forms have one, two and three inputs."""
        check.equal(
            seat,
            [*INPUT, *PAIR, *TRIPLE],
            ["input", "a", "b", "a", "b", "c"],
            "the constants have the labels of the inputs",
        )


class TestForm:
    """Form is a property form."""

    def test_generates_one_input_without_a_handle_by_default(
        self, seat: Collector
    ) -> None:
        """The form sets only the fields without a default."""
        check.equal(
            seat,
            [BELOW.labels, BELOW.skip],
            [INPUT, 0],
            "a form has one input and does not skip a parameter by default",
        )


class TestRunForm:
    """run_form runs a property form."""

    def test_passes_a_form_whose_assertion_passes_for_every_case(
        self, seat: Collector
    ) -> None:
        """The generator returns the digits below 5."""
        recorder = Recorder()
        below = using(int, prop.integer(0, 4))
        run_form(recorder, BELOW, "below 5", digit, [below, *STEADY], below_five)
        check.equal(
            seat,
            [recorder.failures, records(recorder)[0]["assertion"]],
            [[], "prop-below"],
            "the record of the form passes",
        )

    def test_fails_with_a_record_of_the_id_of_the_form_at_the_call_of_the_form(
        self, seat: Collector
    ) -> None:
        """The failure of the case is at the call of the form."""
        recorder = Recorder()
        run_form(recorder, BELOW, "below 5", digit, [DIGITS, *STEADY], below_five)
        failure = recorder.failures[0]
        case_failure = failure.detail["failure"]
        check.equal(
            seat,
            [failure.assertion, case_failure.assertion, case_failure.where],
            ["prop-below", "true", failure.where],
            "the failure of the case is at the call of the form",
        )
        where = failure.where
        check.has_suffix(
            seat,
            None if where is None else where.file,
            "test_form.py",
            "the record is at the call of the form",
        )

    def test_generates_each_argument_under_its_label(self, seat: Collector) -> None:
        """The form generates the inputs a and b."""
        recorder = Recorder()
        run_form(recorder, BOTH, "both below 5", sum_of, [DIGITS, *STEADY], below_five)
        entries = recorder.failures[0].detail["counterexample"]
        check.equal(
            seat,
            [one.label for one in entries],
            ["a", "b"],
            "the counterexample has the labels a and b",
        )

    def test_passes_the_relaxations_to_a_form_whose_assertion_takes_them(
        self, seat: Collector
    ) -> None:
        """The call has three relaxations."""
        relaxations = (equate_empty(), equate_nans(), by_identity())
        passed: list[tuple[Relaxation, ...]] = []

        def keep(
            _: Case, _args: tuple[Any, ...], relaxed: tuple[Relaxation, ...]
        ) -> None:
            passed.append(relaxed)

        options: list[FormOption] = [DIGITS, *relaxations, *STEADY]
        run_form(Recorder(), BOTH, "c", sum_of, options, keep)
        check.equal(
            seat,
            passed[0],
            relaxations,
            "the check receives the relaxations in order",
        )

    def test_uses_the_later_of_two_generators_of_a_type(self, seat: Collector) -> None:
        """The later generator is below 5."""
        recorder = Recorder()
        options: list[FormOption] = [
            using(int, prop.integer(5, 9)),
            using(int, prop.integer(0, 4)),
            *STEADY,
        ]
        run_form(recorder, BELOW, "below 5", digit, options, below_five)
        check.is_empty(seat, recorder.failures, "the form passes")

    def test_runs_the_cases_of_the_options_of_the_run(self, seat: Collector) -> None:
        """The cases option sets seven cases."""
        recorder = Recorder()
        options: list[FormOption] = [
            using(int, prop.integer(0, 1000)),
            cases(7),
            *STEADY,
        ]
        run_form(recorder, BELOW, "c", digit, options, seen_by([]))
        check.equal(
            seat, records(recorder)[0]["detail"]["cases"], 7, "the run has seven cases"
        )

    def test_shrinks_a_failing_example_that_runs_first(self, seat: Collector) -> None:
        """The example 8 shrinks to 5."""
        recorder = Recorder()
        options: list[FormOption] = [DIGITS, example(8), *STEADY]
        run_form(recorder, BELOW, "below 5", digit, options, below_five)
        entries = recorder.failures[0].detail["counterexample"]
        check.equal(
            seat,
            [records(recorder)[1]["phase"], entries[0].value],
            ["example", 5],
            "the example shrinks to 5",
        )

    def test_runs_one_case_per_value_of_examples_in_order(
        self, seat: Collector
    ) -> None:
        """The values 3 and 4 run first."""
        seen: list[tuple[Any, ...]] = []
        options: list[FormOption] = [DIGITS, examples(3, 4), cases(1), *STEADY]
        run_form(Recorder(), BELOW, "c", digit, options, seen_by(seen))
        check.equal(seat, seen[:2], [(3,), (4,)], "the two examples run first")

    def test_reports_a_failing_example_of_a_generator_without_an_inverse_as_found(
        self, seat: Collector
    ) -> None:
        """The generator of doubled digits does not produce 7."""
        recorder = Recorder()
        doubled = using(int, prop.integer(0, 4).map(lambda x: x * 2))
        options: list[FormOption] = [doubled, example(7), *STEADY]
        run_form(recorder, BELOW, "below 5", digit, options, below_five)
        detail = recorder.failures[0].detail
        check.equal(
            seat,
            [detail["counterexample"][0].value, detail["choices"]],
            [7, None],
            "the counterexample is the value without a token",
        )

    def test_generates_the_parameters_of_a_function_as_the_fields_of_a_record(
        self, seat: Collector
    ) -> None:
        """The parameters are an int and a str under one label."""
        recorder = Recorder()
        seen: list[tuple[Any, ...]] = []
        run_form(recorder, BELOW, "c", mixed, [DIGITS, *STEADY], seen_by(seen))
        check.equal(
            seat,
            [type(arg) for arg in seen[0]],
            [int, str],
            "the arguments are an int and a str",
        )

    def test_names_the_record_of_the_parameters_after_the_function(
        self, seat: Collector
    ) -> None:
        """The counterexample has the record."""
        recorder = Recorder()

        def fails(
            c: Case, _args: tuple[Any, ...], _relaxed: tuple[Relaxation, ...]
        ) -> None:
            c.fail("it broke")

        run_form(recorder, BELOW, "c", mixed, [DIGITS, *STEADY], fails)
        entry = recorder.failures[0].detail["counterexample"][0]
        check.equal(
            seat,
            [entry.label, type(entry.value).__name__],
            ["input", "mixed"],
            "the record has the name of the function",
        )

    def test_takes_a_tuple_as_an_example_of_a_function_of_several_parameters(
        self, seat: Collector
    ) -> None:
        """The example is the tuple of 3 and x."""
        seen: list[tuple[Any, ...]] = []
        options: list[FormOption] = [DIGITS, example((3, "x")), cases(1), *STEADY]
        run_form(Recorder(), BELOW, "c", mixed, options, seen_by(seen))
        check.equal(seat, seen[0], (3, "x"), "the example runs first")

    def test_reads_the_input_after_the_handle_of_a_form_that_skips_one(
        self, seat: Collector
    ) -> None:
        """The handle does not need an annotation."""
        seen: list[tuple[Any, ...]] = []
        run_form(Recorder(), HANDLED, "c", handled, [DIGITS, *STEADY], seen_by(seen))
        check.equal(
            seat, [type(arg) for arg in seen[0]], [int], "the argument is one int"
        )

    tests: ClassVar[
        list[tuple[str, Form, Callable[..., Any], list[FormOption], str]]
    ] = [
        (
            "a relaxation of a form whose assertion does not take one",
            BELOW,
            digit,
            [DIGITS, equate_nans()],
            "prop.below: the form does not take a relaxation, because its "
            "assertion does not take one",
        ),
        (
            "a function without an annotation",
            BELOW,
            unannotated,
            [DIGITS],
            "prop.below: the parameter x of the function unannotated does not have "
            "an annotation, so the form cannot read the type of its input",
        ),
        (
            "a function without an input",
            BELOW,
            lambda: 1,
            [DIGITS],
            "prop.below: the function TestRunForm.<lambda> does not take an input",
        ),
        (
            "a function whose annotations do not resolve",
            BELOW,
            unresolved,
            [DIGITS],
            "prop.below: the annotations of the function unresolved do not "
            "resolve: name 'Missing' is not defined",
        ),
        (
            "a function whose signature cannot be read",
            BELOW,
            type,
            [DIGITS],
            "prop.below: the signature of the function type cannot be read: ",
        ),
        (
            "a type that the reader does not read",
            BELOW,
            opaque,
            [DIGITS],
            "prop.below: object: object is not a type that the reader reads",
        ),
        (
            "an example of another number of values",
            BELOW,
            digit,
            [DIGITS, example(1, 2)],
            "prop.below: example[0]: the example has 2 values, and the form "
            "generates 1",
        ),
        (
            "examples of a form of two inputs",
            BOTH,
            sum_of,
            [DIGITS, examples(1)],
            "prop.both: examples[0]: the examples option needs a form of one "
            "input, and the form generates 2",
        ),
        (
            "an example of a value that the generator does not produce",
            BOTH,
            sum_of,
            [DIGITS, example(1, 99)],
            "prop.both: example[0][1]: the generator of the input does not "
            "produce the value: ",
        ),
        (
            "examples of a value that the generator does not produce",
            BELOW,
            digit,
            [DIGITS, examples(1, 99)],
            "prop.below: examples[0][1]: the generator of the input does not "
            "produce the value: ",
        ),
        (
            "an example of a tuple shorter than the parameters of the function",
            BELOW,
            mixed,
            [DIGITS, example((3,))],
            "prop.below: example[0][0]: the generator of the input does not "
            "produce the value: ",
        ),
        (
            "an example whose generator raises",
            BELOW,
            digit,
            [
                using(int, Mapped(prop.integer(0, 9), breaks, lambda v: v)),
                example(1),
            ],
            "prop.below: example[0][0]: the generator of the input raises for the "
            "value: the map broke",
        ),
        (
            "a fault of the options of the run",
            BELOW,
            digit,
            [DIGITS, draws("[")],
            "prop.below: draws: the entries are not a JSON array of objects: ",
        ),
    ]

    @pytest.mark.parametrize(
        ("form", "function", "options", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_ends_the_call_with_a_fault_for(
        self,
        seat: Collector,
        form: Form,
        function: Callable[..., Any],
        options: list[FormOption],
        want: str,
    ) -> None:
        """The fault ends the call before the first case."""
        recorder = Recorder()
        run_form(recorder, form, "c", function, [*options, *STEADY], below_five)
        check.has_prefix(seat, recorder.message, want, "the fault ends the call")
