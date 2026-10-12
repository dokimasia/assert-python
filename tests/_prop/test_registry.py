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
from dokimi_assert._prop.engine.generator import Integer
from dokimi_assert._prop.engine.shape import ShapeError
from dokimi_assert._prop.reader import qualified
from dokimi_assert._prop.registry import derived, of, of_shape, shape_of
from dokimi_assert.seat import Collector
from helpers import integers, refusal, run_python

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))

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

    def test_makes_of_return_the_generator(self, seat: Collector) -> None:
        """The registry returns the registered generator itself."""
        lines = child(
            seat,
            """
registry.register(Point, DIGITS)
print(registry.of(Point) is DIGITS)
""",
        )
        check.equal(seat, lines, ["True"], "of returns the registered generator")

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
