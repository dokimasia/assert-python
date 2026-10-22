"""The spec of _prop/registry.py tests the registrations and the generators of types.

Each case of a registration runs in a child process of its own, because the
registry applies to the whole process and the first property closes it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

import annotated_types as at
import pytest

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.engine.case import Case, Replaying
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.generator import Integer, Just
from dokimi_assert._prop.engine.shape import ShapeError
from dokimi_assert._prop.reader import qualified
from dokimi_assert._prop.registry import (
    Generators,
    Picking,
    Within,
    derived,
    of,
    of_shape,
    scope,
    shape_of,
)
from dokimi_assert.seat import Collector
from helpers import integers, refusal, run_python

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))

#: A generator of the one int 7.
SEVEN = Just(7)


def simplest(generator: Any) -> Any:
    """Return the value that generator decodes from a case without choices."""
    return generator.decode(Case(Replaying([])))


#: The types of the child processes of the registrations.
PRELUDE = """
from dataclasses import dataclass
from dokimi_assert._prop.engine.case import Case, Replaying
from dokimi_assert._prop.engine.choice import Choice, IntegerBounds
from dokimi_assert._prop.engine.generator import Integer
from dokimi_assert._prop import registry

DIGITS = Integer(IntegerBounds(0, 9))

@dataclass(frozen=True)
class Point:
    x: int
    y: int

class Status(str):
    pass

class Shape:
    pass

@dataclass(frozen=True)
class Circle(Shape):
    radius: int

@dataclass(frozen=True)
class Square(Shape):
    side: int

def first(generator):
    return generator.decode(Case(Replaying([])))

def refused(call):
    try:
        call()
    except Exception as error:
        print(type(error).__name__, error)
    else:
        print("passed")
"""


@dataclass(frozen=True)
class Point:
    """A record of two ints."""

    x: int
    y: int


def child(seat: Collector, code: str) -> list[str]:
    """Return the lines that a child process prints, and check that it succeeds."""
    done = run_python(PRELUDE + code)
    check.equal(seat, [done.returncode, done.stderr], [0, ""], "the child succeeds")
    return done.stdout.splitlines()


class TestScope:
    """scope sets the generators of the draws of of inside a with statement."""

    def test_makes_a_draw_of_of_pick_the_generator_of_the_run(
        self, seat: Collector
    ) -> None:
        """The run gives int the generator of 7."""
        with scope(Generators({int: SEVEN})):
            value = simplest(of(int))
        check.equal(seat, value, 7, "the draw decodes with the generator of the run")

    def test_restores_the_generators_of_the_enclosing_block(
        self, seat: Collector
    ) -> None:
        """The inner block has the generators of the test process."""
        with scope(Generators({int: SEVEN})):
            with scope(None):
                inner = simplest(of(int))
            outer = simplest(of(int))
        check.equal(
            seat,
            (inner, outer, simplest(of(int))),
            (0, 7, 0),
            "each block decodes with its own generators",
        )


class TestGenerators:
    """Generators are the generators that the using options of one run give types."""

    def test_returns_generators_of_no_type_by_default(self, seat: Collector) -> None:
        """The run states no generator."""
        check.equal(seat, Generators(), Generators({}), "the run states no type")


class TestGeneratorsEq:
    """Generators.__eq__ compares the stated generator of each type."""

    def test_reports_true_for_the_same_generator_of_each_type(
        self, seat: Collector
    ) -> None:
        """Both runs give int the digits."""
        check.is_true(
            seat,
            Generators({int: DIGITS}) == Generators({int: DIGITS}),
            "the generators are equal",
        )

    def test_reports_false_for_another_generator_of_a_type(
        self, seat: Collector
    ) -> None:
        """The second run gives int the generator of 7."""
        check.is_false(
            seat,
            Generators({int: DIGITS}) == Generators({int: SEVEN}),
            "the generators differ",
        )

    def test_reports_false_for_a_value_of_another_class(self, seat: Collector) -> None:
        """A map of the types is not the generators of a run."""
        stated: object = {int: DIGITS}
        check.is_false(
            seat, Generators({int: DIGITS}) == stated, "the generators differ"
        )


class TestGeneratorsRead:
    """Generators.read returns the generator of a type under the generators."""

    def test_returns_the_stated_generator_of_a_stated_type(
        self, seat: Collector
    ) -> None:
        """The generator decodes 7."""
        check.equal(
            seat,
            simplest(Generators({int: SEVEN}).read(int)),
            7,
            "the generator is the stated one",
        )

    def test_reads_a_type_with_the_stated_generators_in_place(
        self, seat: Collector
    ) -> None:
        """Each int of the point is 7."""
        check.equal(
            seat,
            simplest(Generators({int: SEVEN}).read(Point)),
            Point(7, 7),
            "the point has the ints of the stated generator",
        )

    def test_raises_a_fault_for_a_type_that_the_reader_does_not_read(
        self, seat: Collector
    ) -> None:
        """The fault has the part."""
        check.equal(
            seat,
            refusal(seat, lambda: Generators().read(object), FaultError),
            "object: object is not a type that the reader reads",
            "the fault has the part and the reason",
        )


class TestGeneratorsPick:
    """Generators.pick returns the generator of a draw of of under the generators."""

    def test_returns_the_default_of_a_run_that_states_no_generator(
        self, seat: Collector
    ) -> None:
        """The run does not read the type."""
        check.is_true(
            seat, Generators().pick(int, DIGITS) is DIGITS, "the pick is the default"
        )

    def test_reads_each_type_once(self, seat: Collector) -> None:
        """The second pick of the point returns the first read."""
        generators = Generators({int: SEVEN})
        first = generators.pick(Point, DIGITS)
        check.is_true(
            seat,
            generators.pick(Point, DIGITS) is first,
            "the run reads the point once",
        )
        check.equal(seat, simplest(first), Point(7, 7), "the read has the stated ints")

    def test_raises_type_error_for_a_type_that_the_reader_refuses_under_the_run(
        self, seat: Collector
    ) -> None:
        """The bound of the int does not apply to the stated generator of int."""
        text = refusal(
            seat,
            lambda: Generators({int: DIGITS}).pick(Annotated[int, at.Ge(0)], DIGITS),
            TypeError,
        )
        check.has_prefix(seat, text, "prop.of: ", "the error names of")
        check.has_suffix(
            seat,
            text,
            "does not apply to a type that a generator generates",
            "the error has the reason",
        )


class TestGeneratorsWithout:
    """Generators.without returns the generators without the one of a type."""

    def test_returns_the_generators_of_every_other_type(self, seat: Collector) -> None:
        """The run without int keeps the generator of str."""
        letter = Just("a")
        check.equal(
            seat,
            Generators({int: DIGITS, str: letter}).without(int),
            Generators({str: letter}),
            "the generators keep str",
        )

    def test_returns_the_same_generators_for_each_call(self, seat: Collector) -> None:
        """The run makes the generators without a type once."""
        generators = Generators({int: DIGITS})
        check.is_true(
            seat,
            generators.without(int) is generators.without(int),
            "the two calls return one value",
        )


class TestPicking:
    """Picking is the generator that of returns for a type."""

    def test_keeps_its_type_and_its_default(self, seat: Collector) -> None:
        """The generator has int and the digits."""
        picking = Picking(int, DIGITS)
        check.equal(
            seat,
            (picking.t, picking.default is DIGITS),
            (int, True),
            "the generator keeps both",
        )


class TestPickingPicked:
    """Picking.picked returns the generator of the type in the current run."""

    def test_returns_the_default_outside_a_run(self, seat: Collector) -> None:
        """The test process gives int the digits."""
        with Picking(int, DIGITS).picked() as picked:
            check.is_true(seat, picked is DIGITS, "the pick is the default")

    def test_returns_the_generator_that_the_run_picks(self, seat: Collector) -> None:
        """The run gives int the generator of 7."""
        with scope(Generators({int: SEVEN})), Picking(int, DIGITS).picked() as picked:
            value = simplest(picked)
        check.equal(seat, value, 7, "the pick decodes with the generator of the run")


class TestWithin:
    """Within is the generator that a run states for a type."""

    def test_keeps_the_stated_generator(self, seat: Collector) -> None:
        """The generator is the digits."""
        check.is_true(
            seat,
            Within(DIGITS, Generators(), int).generator is DIGITS,
            "the generator keeps the stated one",
        )


class TestWithinPicked:
    """Within.picked enters the other generators of the run."""

    def test_makes_a_draw_of_its_own_type_pick_the_generator_of_the_process(
        self, seat: Collector
    ) -> None:
        """The stated generator of int adds 100 to the simplest int."""
        with scope(Generators({int: of(int).map(lambda x: x + 100)})):
            value = simplest(of(int))
        check.equal(seat, value, 100, "the inner draw of of(int) decodes 0")

    def test_keeps_the_generators_of_the_other_types(self, seat: Collector) -> None:
        """The stated generator of str draws the stated int."""
        with scope(Generators({int: SEVEN, str: of(int).map(str)})):
            value = simplest(of(str))
        check.equal(seat, value, "7", "the inner draw of of(int) decodes 7")


class TestClose:
    """close ends the registrations of the process."""

    def test_makes_a_later_registration_raise_runtime_error(
        self, seat: Collector
    ) -> None:
        """The registry is closed."""
        lines = child(
            seat,
            """
registry.close()
refused(lambda: registry.register(Point, DIGITS))
""",
        )
        check.equal(
            seat,
            lines,
            [
                "RuntimeError prop: register(__main__.Point): the first run of a "
                "property closed the registry"
            ],
            "the registration raises RuntimeError",
        )


class TestRegister:
    """register sets the generator of a type in the process."""

    def test_makes_a_draw_of_of_decode_with_the_generator(
        self, seat: Collector
    ) -> None:
        """The draw of the point decodes the digit 7."""
        lines = child(
            seat,
            """
registry.register(Point, DIGITS)
print(registry.of(Point).decode(Case(Replaying([Choice("integer", 7)]))))
""",
        )
        check.equal(seat, lines, ["7"], "of decodes with the registered generator")

    def test_makes_a_type_that_contains_the_type_generate_it_with_the_generator(
        self, seat: Collector
    ) -> None:
        """The list has one point of the digit 7."""
        lines = child(
            seat,
            """
registry.register(Point, DIGITS)
generator = registry.of(list[Point])
print(generator.decode(Case(Replaying([Choice("integer", 1), Choice("integer", 7)]))))
""",
        )
        check.equal(seat, lines, ["[7]"], "the list has the point")

    def test_makes_shape_of_raise_type_error_for_a_type_that_contains_the_type(
        self, seat: Collector
    ) -> None:
        """The error has the part."""
        lines = child(
            seat,
            """
registry.register(Point, DIGITS)
refused(lambda: registry.shape_of(list[Point]))
""",
        )
        check.equal(
            seat,
            lines,
            [
                "TypeError prop.shape_of: list[__main__.Point][]: a registered "
                "generator generates the part, and it does not have a shape"
            ],
            "shape_of raises TypeError",
        )

    def test_raises_runtime_error_for_a_second_registration(
        self, seat: Collector
    ) -> None:
        """A type has one registration."""
        lines = child(
            seat,
            """
registry.register(Point, DIGITS)
refused(lambda: registry.register(Point, DIGITS))
""",
        )
        check.equal(
            seat,
            lines,
            [
                "RuntimeError prop: register(__main__.Point) registers __main__.Point "
                "a second time"
            ],
            "the second registration raises RuntimeError",
        )

    def test_raises_runtime_error_after_a_read_of_the_type(
        self, seat: Collector
    ) -> None:
        """The generators of the read do not include the registration."""
        lines = child(
            seat,
            """
registry.of(Point)
refused(lambda: registry.register(Point, DIGITS))
""",
        )
        check.equal(
            seat,
            lines,
            [
                "RuntimeError prop: register(__main__.Point): the generators of an "
                "earlier read of __main__.Point do not include the registration"
            ],
            "the registration raises RuntimeError",
        )


class TestRegisterValues:
    """register_values makes the values of a type a literal."""

    def test_makes_the_shape_of_the_type_a_literal_of_the_values(
        self, seat: Collector
    ) -> None:
        """The first value is the simplest."""
        lines = child(
            seat,
            """
import json
registry.register_values(Status, Status("pending"), Status("paid"))
value = first(registry.of(Status))
print(type(value).__name__, value)
print(json.dumps(json.loads(registry.shape_of(Status))["values"]))
""",
        )
        check.equal(
            seat,
            lines,
            [
                "Status pending",
                '[{"type": "string", "value": "pending"}, '
                '{"type": "string", "value": "paid"}]',
            ],
            "the simplest value and the literals",
        )

    refusals: ClassVar[list[tuple[str, str, str]]] = [
        (
            "raises value error without a value",
            "refused(lambda: registry.register_values(Status))",
            "ValueError prop: register_values(__main__.Status) needs a value",
        ),
        (
            "raises value error for a value without a typed literal",
            "refused(lambda: registry.register_values(Status, object()))",
            "ValueError prop: register_values(__main__.Status): value 0 does not have "
            "a typed literal",
        ),
        (
            "raises value error for two values of one typed literal",
            "refused(lambda: registry.register_values("
            "Status, Status('a'), Status('a')))",
            "ValueError prop: register_values(__main__.Status): values 0 and 1 have "
            "one typed literal",
        ),
        (
            "raises type error for a type that the reader does not read",
            "refused(lambda: registry.register_values(object, 1))",
            "TypeError prop: register_values(builtins.object): object: object is not "
            "a type that the reader reads",
        ),
        (
            "raises type error for a part that a registered generator generates",
            "registry.register(Point, DIGITS)\n"
            "refused(lambda: registry.register_values(list[Point], [Point(1, 2)]))",
            "TypeError prop: register_values(list[__main__.Point]): "
            "list[__main__.Point][]: a registered generator generates the part, and "
            "its values do not have typed literals",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_refuses_values_that_it_cannot_register(
        self, seat: Collector, give: str, want: str
    ) -> None:
        """The error has the call."""
        check.equal(
            seat, child(seat, give + "\n"), [want], "register_values raises the error"
        )


class TestRegisterVariants:
    """register_variants makes the variant classes of a type an enum."""

    def test_makes_the_shape_of_the_type_an_enum_of_the_classes(
        self, seat: Collector
    ) -> None:
        """The simplest variant is the first class."""
        lines = child(
            seat,
            """
registry.register_variants(Shape, Circle, Square)
print(first(registry.of(Shape)))
""",
        )
        check.equal(seat, lines, ["Circle(radius=0)"], "the simplest variant")

    refusals: ClassVar[list[tuple[str, str, str]]] = [
        (
            "raises value error without a variant",
            "refused(lambda: registry.register_variants(Shape))",
            "ValueError prop: register_variants(__main__.Shape) needs a variant",
        ),
        (
            "raises type error for a variant that is not a class",
            "refused(lambda: registry.register_variants(Shape, Circle(1)))",
            "TypeError prop: register_variants(__main__.Shape): variant 0 is "
            "Circle(radius=1), not a class",
        ),
        (
            "raises value error for two variants of one name",
            "refused(lambda: registry.register_variants(Shape, Circle, Circle))",
            "ValueError prop: register_variants(__main__.Shape): variants 0 and 1 are "
            "both named Circle",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_refuses_variants_that_it_cannot_register(
        self, seat: Collector, give: str, want: str
    ) -> None:
        """The error has the call."""
        check.equal(
            seat,
            child(seat, give + "\n"),
            [want],
            "register_variants raises the error",
        )


class TestDerived:
    """derived returns the generator of a type with the generators of using."""

    def test_returns_the_generator_of_the_shape_of_a_type(
        self, seat: Collector
    ) -> None:
        """The choices 3 and 4 decode to a point."""
        generator = derived(Point, {})
        check.equal(
            seat,
            generator.decode(Case(Replaying(integers(3, 4)))),
            Point(3, 4),
            "the generator returns the point",
        )

    def test_returns_the_generator_of_using_for_the_type(self, seat: Collector) -> None:
        """The call returns the generator of using itself."""
        check.is_true(
            seat,
            derived(int, {int: DIGITS}) is DIGITS,
            "derived returns the generator of using",
        )

    def test_generates_a_part_with_the_generator_of_using_for_its_type(
        self, seat: Collector
    ) -> None:
        """The point has digits."""
        generator = derived(Point, {int: DIGITS})
        check.equal(
            seat,
            generator.decode(Case(Replaying(integers(12, 5)))),
            Point(0, 5),
            "the generator returns a point of digits",
        )

    def test_raises_a_fault_for_a_type_that_the_reader_does_not_read(
        self, seat: Collector
    ) -> None:
        """The fault has the part."""
        check.equal(
            seat,
            refusal(seat, lambda: derived(object, {}), FaultError),
            "object: object is not a type that the reader reads",
            "the fault has the part and the reason",
        )

    def test_raises_a_fault_for_a_shape_that_the_definition_refuses(
        self, seat: Collector
    ) -> None:
        """The bounds of the int are empty."""
        t = Annotated[int, at.Ge(5), at.Le(1)]
        check.contains(
            seat,
            refusal(seat, lambda: derived(t, {}), FaultError),
            "prop:",
            "the fault comes from the shape",
        )


class TestOf:
    """of returns the generator of a type."""

    def test_returns_the_generator_of_the_shape_of_a_type(
        self, seat: Collector
    ) -> None:
        """The generator returns the simplest point."""
        check.equal(
            seat,
            of(Point).decode(Case(Replaying([]))),
            Point(0, 0),
            "the generator returns the point 0, 0",
        )

    def test_returns_the_same_generator_on_every_call(self, seat: Collector) -> None:
        """The process reads a type once."""
        check.is_true(seat, of(Point) is of(Point), "of returns one generator")

    def test_raises_type_error_for_a_type_that_the_reader_does_not_read(
        self, seat: Collector
    ) -> None:
        """The text has the part."""
        check.equal(
            seat,
            refusal(seat, lambda: of(object), TypeError),
            "prop.of: object: object is not a type that the reader reads",
            "of raises TypeError",
        )


class TestShapeOf:
    """shape_of returns the shape file of a type."""

    def test_returns_the_shape_with_its_source_in_sorted_indented_json(
        self, seat: Collector
    ) -> None:
        """The text ends in a newline."""
        text = shape_of(Point)
        int64 = {"shape": "int", "signed": True, "width": 64}
        want = {
            "fields": [["x", int64], ["y", int64]],
            "shape": "record",
            "source": {"language": "python", "type": qualified(Point)},
        }
        check.equal(
            seat,
            text,
            json.dumps(want, sort_keys=True, indent=2) + "\n",
            "shape_of returns the shape file",
        )

    refusals: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "raises type error for a type that the reader does not read",
            object,
            "prop.shape_of: object: object is not a type that the reader reads",
        ),
        (
            "raises type error for a shape that the definition refuses",
            Annotated[int, at.Ge(5), at.Le(1)],
            "prop.shape_of: prop:",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_refuses_a_type_without_a_shape_file(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The text has the part."""
        check.has_prefix(
            seat,
            refusal(seat, lambda: shape_of(give), TypeError),
            want,
            "shape_of raises TypeError",
        )


class TestOfShape:
    """of_shape returns the generator of a shape file."""

    def test_returns_the_generator_of_the_python_values_of_a_shape_file(
        self, seat: Collector
    ) -> None:
        """A record decodes to a dict."""
        generator = of_shape(shape_of(Point))
        check.equal(
            seat,
            generator.decode(Case(Replaying(integers(3, 4)))),
            {"x": 3, "y": 4},
            "the generator returns the dict of the fields",
        )

    refusals: ClassVar[list[tuple[str, str, str]]] = [
        (
            "raises shape error for text that is not JSON",
            "{",
            "prop.of_shape: the text is not a shape file:",
        ),
        (
            "raises shape error for JSON that is not an object",
            "[]",
            "prop.of_shape: the text is not a JSON object",
        ),
        (
            "raises shape error for a shape that the definition refuses",
            '{"shape": "nothing"}',
            "prop:",
        ),
        (
            "raises shape error for a shape without a Python value",
            '{"shape": "time-of-day", "unit": "ns"}',
            "prop.of_shape: a time-of-day at nanoseconds does not have a Python value",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_refuses_a_text_that_is_not_a_shape_file_of_python_values(
        self, seat: Collector, give: str, want: str
    ) -> None:
        """The error has the reason."""
        check.has_prefix(
            seat,
            refusal(seat, lambda: of_shape(give), ShapeError),
            want,
            "of_shape raises ShapeError",
        )
