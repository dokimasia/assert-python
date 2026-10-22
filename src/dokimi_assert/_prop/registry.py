"""The registrations of a test process, and the generators of types and shape files.

A registration applies to the whole test process. The first run of a
property closes the registry, and a later registration raises RuntimeError.
The generators of a test then do not change while other tests run. A
registration of a type that a read has looked up raises RuntimeError too,
because the generators that the read returned do not include it. A
conftest.py has the registrations of a project.

A run of a property can give types other generators through using. A draw of
of picks the generator of its type in the run where it decodes. The run sets
its generators with scope on each thread that decodes its draws.

The registry is safe for concurrent use. A read of a type locks the registry
until the read ends.
"""

from __future__ import annotations

import collections.abc
import inspect
import json
import threading
from collections.abc import Mapping
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any, TypeVar

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.convert import converter_of
from dokimi_assert._prop.engine import literal, shape, strict_json
from dokimi_assert._prop.engine.generator import Deferred, Generator, Mapped
from dokimi_assert._prop.engine.value import canonical
from dokimi_assert._prop.reader import (
    Derived,
    Literals,
    Registrations,
    derive,
    literal_converter,
    qualified,
)

__all__ = [
    "Generators",
    "Picking",
    "Within",
    "close",
    "derived",
    "of",
    "of_shape",
    "register",
    "register_values",
    "register_variants",
    "scope",
    "shape_of",
]

_T = TypeVar("_T")

#: The registrations of the test process.
_REGISTRY = Registrations()

#: The lock of the registry. A read of a type locks it until the read ends.
_LOCK = threading.RLock()

#: The generators that of returned, by type.
_OF: dict[object, Generator[Any]] = {}

#: The most levels of objects and arrays of a shape file.
_SHAPE_DEPTH = 128

#: The generators of the run whose draws decode in the current context. None
#: stands for the generators of the test process.
_RUN: ContextVar[Generators | None] = ContextVar("dokimi_assert_prop_run", default=None)


@contextmanager
def scope(generators: Generators | None) -> collections.abc.Generator[None, None, None]:
    """Make generators the generators of the draws of of inside a with statement.

    A run enters its generators on each thread that decodes its draws. The
    previous generators apply again when the block ends.

    Args:
        generators: The generators of a run, or None for the generators of
            the test process.

    Yields:
        Nothing.
    """
    token = _RUN.set(generators)
    try:
        yield
    finally:
        _RUN.reset(token)


class Generators:
    """The generators that the using options of one run give types.

    A draw of of(t) picks the generator of t from them. The methods are safe
    for concurrent use.
    """

    def __init__(self, stated: Mapping[object, Generator[Any]] | None = None) -> None:
        """Return the generators of a run.

        Args:
            stated: The generator of each type that the run states, or None
                for a run that states none.
        """
        self._stated: dict[object, Generator[Any]] = dict(stated or {})
        self._lock: threading.Lock = threading.Lock()
        self._picked: dict[object, Generator[Any]] = {}
        self._without: dict[object, Generators] = {}

    def __eq__(self, other: object) -> bool:
        """Report whether other states the same generator of each type.

        Args:
            other: The other value.

        Returns:
            True for generators of the same types with the same generators.
        """
        return isinstance(other, Generators) and other._stated == self._stated

    def read(self, t: object) -> Generator[Any]:
        """Return the generator of t under these generators.

        A type that the run states has its stated generator, which decodes
        under the other generators of the run. Any other type has the
        generator that the reader reads with the stated generators in place
        of their types. A property form reads its input this way.

        Args:
            t: The type.

        Returns:
            The generator.

        Raises:
            FaultError: The reader does not read a part of t, or the
                definition refuses a constraint.
        """
        stated = self._stated.get(t)
        if stated is not None:
            return Within(stated, self, t)
        externals = {s: Within(g, self, s) for s, g in self._stated.items()}
        return derived(t, externals)

    def pick(self, t: object, default: Generator[_T]) -> Generator[_T]:
        """Return the generator of a draw of of(t) under these generators.

        A run that states no generator picks default. Any other run reads
        each type once.

        Args:
            t: The type.
            default: The generator of t in the test process.

        Returns:
            The generator.

        Raises:
            TypeError: The reader does not read t with the stated generators
                in place.
        """
        if not self._stated:
            return default
        with self._lock:
            picked = self._picked.get(t)
            if picked is None:
                try:
                    picked = self.read(t)
                except FaultError as error:
                    raise TypeError(f"prop.of: {error}") from error
                self._picked[t] = picked
        return picked

    def without(self, t: object) -> Generators:
        """Return these generators without the generator of t.

        Args:
            t: The type.

        Returns:
            The generators of every other stated type.
        """
        with self._lock:
            rest = self._without.get(t)
            if rest is None:
                rest = Generators({s: g for s, g in self._stated.items() if s != t})
                self._without[t] = rest
        return rest


class Picking(Deferred[_T]):
    """The generator that of returns for a type.

    A draw picks the generator of the type in the run where it decodes, and
    the generator of the test process outside a run.

    Attributes:
        t: The type.
        default: The generator of the type in the test process.
    """

    def __init__(self, t: object, default: Generator[_T]) -> None:
        """Return the generator of the draws of a type.

        Args:
            t: The type.
            default: The generator of the type in the test process.
        """
        self.t: object = t
        self.default: Generator[_T] = default

    def picked(self) -> AbstractContextManager[Generator[_T]]:
        """Return the generator of the type in the current run.

        Returns:
            A context manager. Entering it returns the generator.
        """
        run = _RUN.get()
        if run is None:
            return nullcontext(self.default)
        return nullcontext(run.pick(self.t, self.default))


class Within(Deferred[_T]):
    """The generator that a run states for a type.

    It decodes under the other generators of the run. A draw of of(t) inside
    the generator of t then picks the generator of t without it, so the
    generator can narrow the generator of its own type.

    Attributes:
        generator: The stated generator.
    """

    def __init__(self, generator: Generator[_T], run: Generators, t: object) -> None:
        """Return the stated generator of a type in a run.

        Args:
            generator: The stated generator.
            run: The generators of the run.
            t: The type.
        """
        self.generator: Generator[_T] = generator
        self._run: Generators = run
        self._t: object = t

    @contextmanager
    def picked(self) -> collections.abc.Generator[Generator[_T], None, None]:
        """Enter the other generators of the run, and return the stated generator.

        Yields:
            The stated generator.
        """
        with scope(self._run.without(self._t)):
            yield self.generator


def close() -> None:
    """Close the registry.

    A later registration raises RuntimeError. The first run of a property
    calls this function.
    """
    with _LOCK:
        _REGISTRY.closed = True
        _REGISTRY.consulted.clear()


def _admit(call: str, t: object) -> None:
    """Refuse a registration that the registry does not admit.

    Raises:
        RuntimeError: The registry is closed, t has a registration, or a read
            has looked t up.
    """
    if _REGISTRY.closed:
        raise RuntimeError(
            f"prop: {call}: the first run of a property closed the registry"
        )
    registered = (_REGISTRY.generators, _REGISTRY.values, _REGISTRY.variants)
    if any(t in kind for kind in registered):
        raise RuntimeError(f"prop: {call} registers {qualified(t)} a second time")
    if t in _REGISTRY.consulted:
        raise RuntimeError(
            f"prop: {call}: the generators of an earlier read of {qualified(t)} do "
            "not include the registration"
        )


def register(t: type[_T], generator: Generator[_T]) -> None:
    """Make generator the generator of t in the test process.

    A draw of of(t) decodes with the generator, and a type that contains t
    generates t with it. The generator does not need a shape. A generator of
    map, filter or composite does not have one. shape_of raises TypeError
    for t and for a type that contains t, because a registered generator does
    not have a shape.

    Args:
        t: The type.
        generator: The generator of its values.

    Raises:
        RuntimeError: The registry is closed, t has a registration, or a read
            has looked t up.
    """
    with _LOCK:
        _admit(f"register({qualified(t)})", t)
        _REGISTRY.generators[t] = generator


def register_values(t: type[_T], *values: _T) -> None:
    """Make the shape of t a literal of values in their order.

    A generator of t generates one of the values, and the first is the
    simplest. The registry writes each value as a typed literal of the shape
    of t without the registration. The literal is an int for a subclass of
    int, a string for a subclass of str, and a record for a dataclass.
    shape_of writes the literals.

    Args:
        t: The type.
        *values: One value or more.

    Raises:
        RuntimeError: The registry is closed, t has a registration, or a read
            has looked t up.
        ValueError: values is empty, a value does not have a typed literal,
            or two values have one typed literal.
        TypeError: The reader does not read t, or a registered generator
            generates a part of t.
    """
    call = f"register_values({qualified(t)})"
    with _LOCK:
        _admit(call, t)
        if not values:
            raise ValueError(f"prop: {call} needs a value")
        try:
            read = derive(t, _REGISTRY, skip=t)
        except FaultError as error:
            raise TypeError(f"prop: {call}: {error}") from error
        if read.external_paths:
            raise TypeError(
                f"prop: {call}: {read.external_paths[0]}: a registered generator "
                "generates the part, and its values do not have typed literals"
            )
        literals: list[dict[str, Any]] = []
        keys: dict[str, int] = {}
        for i, value in enumerate(values):
            try:
                written = literal.encode(read.converter.back(value))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"prop: {call}: value {i} does not have a typed literal"
                ) from error
            key = canonical(literal.decode(written))
            if key in keys:
                raise ValueError(
                    f"prop: {call}: values {keys[key]} and {i} have one typed literal"
                )
            keys[key] = i
            literals.append(written)
        converter = literal_converter(values, literals)
        _REGISTRY.values[t] = Literals(literals, converter)


def register_variants(t: type, *variants: type) -> None:
    """Make the shape of t an enum of the variant classes in their order.

    A generator of t generates a value of one of the classes, and the first
    is the simplest. Each variant has the name of its class, and the shape of
    the class is the payload of the variant. The variant of a dataclass
    without fields does not have a payload. Its value is an instance without
    fields.

    Args:
        t: The type. It can be a base class or a Protocol of the variants.
        *variants: One variant class or more.

    Raises:
        RuntimeError: The registry is closed, t has a registration, or a read
            has looked t up.
        ValueError: variants is empty, or two classes have one name.
        TypeError: A variant is not a class.
    """
    call = f"register_variants({qualified(t)})"
    with _LOCK:
        _admit(call, t)
        if not variants:
            raise ValueError(f"prop: {call} needs a variant")
        names: dict[str, int] = {}
        for i, variant in enumerate(variants):
            if not inspect.isclass(variant):
                raise TypeError(
                    f"prop: {call}: variant {i} is {variant!r}, not a class"
                )
            earlier = names.get(variant.__name__)
            if earlier is not None:
                raise ValueError(
                    f"prop: {call}: variants {earlier} and {i} are both named "
                    f"{variant.__name__}"
                )
            names[variant.__name__] = i
        _REGISTRY.variants[t] = tuple(variants)


def _generator_of(read: Derived) -> Generator[Any]:
    """Return the generator of a type that the reader read.

    Raises:
        ShapeError: The definition refuses a constraint of the shape.
    """
    engine = shape.read(read.root, read.externals)
    converter = read.converter
    return Mapped(engine, converter.to, converter.back)


def derived(t: object, using: Mapping[object, Generator[Any]]) -> Generator[Any]:
    """Return the generator of a type with the generators of using for some types.

    of and the generators of a run read a type this way.

    Args:
        t: The type.
        using: The generators of some types.

    Returns:
        The generator.

    Raises:
        FaultError: The reader does not read a part of the type, or the
            definition refuses a constraint.
    """
    with _LOCK:
        generator = using.get(t)
        if generator is None:
            generator = _REGISTRY.generators.get(t)
        if generator is not None:
            return generator
        try:
            return _generator_of(derive(t, _REGISTRY, using))
        except shape.ShapeError as error:
            raise FaultError("", str(error)) from error


def of(t: type[_T]) -> Generator[_T]:
    """Return the generator of t.

    The generator decodes with the generator that register gives t, and
    otherwise with the generator of the shape that the reader reads from t.
    Two types of one shape generate the same values from one seed in every
    language of the definition. A store entry has each value of the
    generator as a typed literal of the shape of t, and the draws option
    accepts that literal. The first call of a type reads the type with the
    registrations of that moment. Every later call returns the same
    generator.

    In a run that gives types generators through using, a draw of the
    generator decodes with the generator that the run gives t. A draw of a
    type that contains such a type reads the type again with the generators
    of the run in place, once per run. A draw whose type the reader then
    refuses raises TypeError inside its case.

    Args:
        t: The type.

    Returns:
        The generator.

    Raises:
        TypeError: The reader does not read a part of t, or a constraint does
            not apply. The text of the error contains the part and the
            constraint.
    """
    with _LOCK:
        cached = _OF.get(t)
        if cached is not None:
            return cached
        try:
            default = derived(t, {})
        except FaultError as error:
            raise TypeError(f"prop.of: {error}") from error
        picking = Picking(t, default)
        _OF[t] = picking
        return picking


def shape_of(t: type) -> str:
    """Return the shape of t as a shape file.

    The file contains the shape that the reader reads from t, with its
    definitions. Its field source contains the language and the name of t
    with its module. The keys are sorted and indented by two spaces, and the
    text ends in a newline. A golden file of the shape then changes only when
    t changes.

    Args:
        t: The type.

    Returns:
        The text of the shape file.

    Raises:
        TypeError: The reader does not read a part of t, a constraint does
            not apply, or a registered generator generates a part of t. The
            text of the error contains the part.
    """
    with _LOCK:
        try:
            read = derive(t, _REGISTRY)
            if read.external_paths:
                raise FaultError(
                    read.external_paths[0],
                    "a registered generator generates the part, and it does not "
                    "have a shape",
                )
            shape.read(read.root)
        except (FaultError, shape.ShapeError) as error:
            raise TypeError(f"prop.shape_of: {error}") from error
    document = {**read.root, "source": {"language": "python", "type": qualified(t)}}
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def of_shape(text: str) -> Generator[Any]:
    """Return the generator of a shape file that shape_of or another language wrote.

    Each value converts to a Python value. A record becomes a dict of its
    fields, an enum becomes a Variant, and a date or a time becomes a value
    of datetime.

    Args:
        text: The shape file.

    Returns:
        The generator.

    Raises:
        ShapeError: The text is not a strict JSON object, the definition refuses
            the shape, or the shape does not have a Python value, such as a
            time-of-day at ns.
    """
    try:
        document = strict_json.parse(text, _SHAPE_DEPTH)
    except strict_json.JsonError as error:
        raise shape.ShapeError(
            f"prop.of_shape: the text is not a shape file: {error}"
        ) from error
    if not isinstance(document, dict):
        raise shape.ShapeError("prop.of_shape: the text is not a JSON object")
    engine = shape.read(document)
    try:
        converter = converter_of(document)
    except FaultError as error:
        raise shape.ShapeError(f"prop.of_shape: {error}") from error
    return Mapped(engine, converter.to, converter.back)
