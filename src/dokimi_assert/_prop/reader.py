# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The reader of Python types into shapes and the converters of their values.

The reader reads a type through typing.get_type_hints. It follows the table
of type readers of the definition:

=================================  ==========================================
Python type                        Shape
=================================  ==========================================
bool, bytes                        bool, bytes
int                                int, 64 bits and signed unless Width
float                              float, 64 bits unless Width
str                                string, or char with Char
list[T], tuple[T, ...]             list, or fixed-list for a Len of one size
tuple[A, B, ...]                   record of the fields 0, 1 and on
set[T], frozenset[T]               set
dict[K, V]                         map
T | None                           optional
A | B, a registration of variants  enum of the classes by their names
IPv4Address | IPv6Address          ip-address of either version
Literal[...], Enum                 literal of the values, enum of the members
dataclass, NamedTuple, TypedDict   record of the fields in their order
date, time, timedelta, timezone    date, time-of-day, duration, offset
datetime with Timezone(None)       local-date-time
datetime with Timezone(utc)        instant
datetime with Timezone(...)        zoned-date-time
ZoneInfo, UUID                     zone, uuid
IPv4Address, IPv6Address           ip-address of version 4, of version 6
Decimal with Scale                 decimal
complex                            record of the floats real and imag
Fraction                           record of the ints num and den
=================================  ==========================================

The reader reads a subclass of int, float, str or bytes as its base, and a
NewType as its supertype. A constraint is an argument of typing.Annotated.
The reader maps the markers of prop and the constraints Gt, Ge, Lt, Le,
Interval, MinLen, MaxLen, Len and Timezone of annotated-types. It recognises
the constraints of annotated-types by their module and their names. An
exclusive bound becomes the inclusive bound one step inside it. A constraint
of an optional applies to its value. Any other constraint fails the read,
and so does a constraint that the part does not take.

A class that the read visits again becomes a definition. Each place where
the class occurs becomes a ref to the definition. The reader reads a type
that a property form or a registration gives a generator as a ref to the
generator. The generator does not have a shape.
"""

from __future__ import annotations

import dataclasses
import enum
import ipaddress
import math
import types
import typing
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Annotated, Any, Literal, cast
from zoneinfo import ZoneInfo

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop import markers
from dokimi_assert._prop.convert import (
    IDENTITY,
    Converter,
    date_converter,
    decimal_converter,
    deferred_converter,
    duration_converter,
    instant_converter,
    ip_converter,
    local_converter,
    offset_converter,
    time_converter,
    uuid_converter,
    zone_converter,
    zoned_converter,
)
from dokimi_assert._prop.engine import literal
from dokimi_assert._prop.engine.float import Width, next_down, next_up
from dokimi_assert._prop.engine.generator import Generator
from dokimi_assert._prop.engine.value import Fields, Pairs, canonical
from dokimi_assert._prop.engine.value import Variant as Neutral
from dokimi_assert._record.literal import encode

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

__all__ = [
    "Derived",
    "Literals",
    "Node",
    "Registrations",
    "derive",
    "literal_converter",
    "qualified",
]

#: A shape as a JSON object.
Node = dict[str, Any]

#: The value of a constraint that the reader did not find.
_UNSET: Any = object()

#: The units that the reader accepts for a time shape of a Python type.
_UNITS = ("s", "ms", "us")

#: The microseconds of one unit of a time shape.
_STEPS = {"s": 1_000_000, "ms": 1_000, "us": 1}

#: The widths of an int and of a float.
_INT_WIDTHS = frozenset({8, 16, 32, 64, 128})
_FLOAT_WIDTHS = frozenset({32, 64})

#: The bound constraints of annotated-types that the reader maps, by class
#: name. Each entry has the attribute, the bound, and True for an exclusive
#: bound.
_ANNOTATED = {
    "Gt": (("gt", "lo", True),),
    "Ge": (("ge", "lo", False),),
    "Lt": (("lt", "hi", True),),
    "Le": (("le", "hi", False),),
    "Interval": (
        ("gt", "lo", True),
        ("ge", "lo", False),
        ("lt", "hi", True),
        ("le", "hi", False),
    ),
}

#: The step of a bound. It is 1 for one step up, 0 for none, and -1 for one
#: step down.
_Step = int


def qualified(t: object) -> str:
    """Return the name of a type with its module, and the repr of any other annotation.

    Args:
        t: The type.

    Returns:
        The name.
    """
    if isinstance(t, type):
        return f"{t.__module__}.{t.__qualname__}"
    return repr(t)


def _name_of(t: object) -> str:
    """Return the short name of a type. The path of its read starts with it.

    The name of an Annotated type is the name of the type that it annotates.
    """
    if typing.get_origin(t) is Annotated:
        return _name_of(typing.get_args(t)[0])
    return t.__qualname__ if isinstance(t, type) else repr(t)


@dataclass(frozen=True, slots=True)
class Literals:
    """The values that register_values gives a type in their order.

    Attributes:
        literals: The typed literal of each value in the form of a shape file.
        converter: The converter between the decoded literals and the
            values.
    """

    literals: list[dict[str, Any]]
    converter: Converter


@dataclass(slots=True)
class Registrations:
    """The registrations of a test process. A read consults them.

    Attributes:
        generators: The generators that register gives types.
        values: The values that register_values gives types.
        variants: The variant classes that register_variants gives types.
        consulted: The types that a read looked up while the registry was
            open.
        closed: When True, the first run of a property has closed the
            registry.
    """

    generators: dict[object, Generator[Any]] = field(default_factory=dict)
    values: dict[object, Literals] = field(default_factory=dict)
    variants: dict[object, tuple[type, ...]] = field(default_factory=dict)
    consulted: set[object] = field(default_factory=set)
    closed: bool = False


@dataclass(slots=True)
class Derived:
    """A Python type that the reader has read into a shape file.

    Attributes:
        root: The root shape. It has the definitions when the read made any.
        externals: The generators without a shape, by the names of their
            refs.
        external_paths: The paths of the parts that the externals generate
            in the order of the read.
        converter: The converter between the neutral values of the root and
            the values of the type.
    """

    root: Node
    externals: dict[str, Generator[Any]]
    external_paths: list[str]
    converter: Converter


@dataclass(slots=True)
class _Constraint:
    """One constraint of typing.Annotated in the form that the reader takes.

    Attributes:
        value: The value of the constraint.
        text: The repr of the constraint object.
        exclusive: When True, the bound excludes its value.
    """

    value: Any
    text: str
    exclusive: bool = False


class _Constraints:
    """The constraints of one part of a type by key."""

    def __init__(self) -> None:
        """Return the constraints of a part without any."""
        self._by_key: dict[str, _Constraint] = {}

    def add(self, metadata: Sequence[object], at: str) -> None:
        """Add the constraints of the arguments of typing.Annotated.

        Raises:
            FaultError: An argument is not a constraint that the reader maps,
                or two arguments set one constraint.
        """
        for item in metadata:
            for key, found in _constraints_of(item, at):
                earlier = self._by_key.get(key)
                if earlier is not None:
                    raise FaultError(
                        at, f"the constraints {earlier.text} and {found.text} conflict"
                    )
                self._by_key[key] = found

    def take(self, key: str) -> Any:
        """Return the value of a constraint and take it, or _UNSET without one."""
        found = self._by_key.pop(key, None)
        return _UNSET if found is None else found.value

    def bound(self, key: str) -> _Constraint | None:
        """Return a bound and take it, or None without one."""
        return self._by_key.pop(key, None)

    def check_taken(self, what: str, at: str) -> None:
        """Refuse the constraints that the part did not take.

        Raises:
            FaultError: A constraint is left.
        """
        for found in self._by_key.values():
            raise FaultError(
                at, f"the constraint {found.text} does not apply to {what}"
            )


def _constraints_of(item: object, at: str) -> list[tuple[str, _Constraint]]:
    """Return the constraints of an argument of typing.Annotated by key.

    Raises:
        FaultError: The argument is not a constraint that the reader maps.
    """
    text = repr(item)
    kind = type(item)
    if kind.__module__ == "annotated_types":
        annotated: Any = item
        name = kind.__name__
        bounds = _ANNOTATED.get(name)
        if bounds is not None:
            return [
                (key, _Constraint(getattr(annotated, attribute), text, exclusive))
                for attribute, key, exclusive in bounds
                if getattr(annotated, attribute) is not None
            ]
        if name in ("MinLen", "MaxLen", "Len"):
            found: list[tuple[str, _Constraint]] = []
            low = getattr(annotated, "min_length", None)
            high = getattr(annotated, "max_length", None)
            if name != "MaxLen" and low is not None:
                found.append(("min_size", _Constraint(low, text)))
            if name != "MinLen" and high is not None:
                found.append(("max_size", _Constraint(high, text)))
            return found
        if name == "Timezone":
            return [("timezone", _Constraint(annotated.tz, text))]
    marker = _MARKERS.get(kind)
    if marker is None:
        raise FaultError(
            at,
            f"{text} is not a constraint of prop or of annotated-types that the "
            "reader maps",
        )
    return [(key, _Constraint(value, text)) for key, value in marker(item)]


#: The keys and the values of each marker of prop.
_MARKERS: dict[type, Callable[[Any], list[tuple[str, Any]]]] = {
    markers.Width: lambda m: [("width", m)],
    markers.Pattern: lambda m: [("pattern", m.regex)],
    markers.Alphabet: lambda m: [("alphabet", m.characters)],
    markers.AllowNan: lambda _: [("allow_nan", True)],
    markers.AllowInfinity: lambda _: [("allow_infinity", True)],
    markers.Unit: lambda m: [("unit", m.name)],
    markers.Scale: lambda m: [("scale", m.digits)],
    markers.Version: lambda m: [("version", m.number)],
    markers.Char: lambda _: [("char", True)],
}


@dataclass(slots=True)
class _SelfReference:
    """A class that its read can visit again.

    Attributes:
        name: The name of its definition.
        cell: The converter of the class after its read ends.
        recursive: When True, the read of the class visited the class again.
    """

    name: str
    cell: list[Converter] = field(default_factory=list)
    recursive: bool = False


#: The origins of a union. A | B has one origin, and typing gives a union of
#: special forms another origin before Python 3.14.
_UNIONS = (types.UnionType, typing.get_origin(Literal[0] | None))


def _union_members(t: object) -> tuple[object, ...] | None:
    """Return the members of a union type, or None for any other annotation."""
    if typing.get_origin(t) in _UNIONS:
        return typing.get_args(t)
    return None


def _is_named_tuple(t: type) -> bool:
    """Report whether a class is a NamedTuple."""
    return issubclass(t, tuple) and isinstance(getattr(t, "_fields", None), tuple)


def _has_payload(t: type) -> bool:
    """Report whether a variant class has a payload.

    A dataclass without fields does not have one.
    """
    if not dataclasses.is_dataclass(t):
        return True
    return any(f.init for f in dataclasses.fields(t))


def _hints(t: type, at: str) -> dict[str, Any]:
    """Return the resolved annotations of a class and their constraints.

    Raises:
        FaultError: An annotation refers to a type that the module of the
            class does not have.
    """
    try:
        return typing.get_type_hints(t, include_extras=True)
    except NameError as error:
        raise FaultError(
            at, f"the annotations of {t.__qualname__} do not resolve: {error}"
        ) from error


#: The arguments of a tuple of any length: the type of its items and the
#: ellipsis.
_VARIADIC_ARGS = 2


class _Reader:
    """The read of one Python type into one shape file."""

    def __init__(
        self,
        registrations: Registrations,
        using: Mapping[object, Generator[Any]],
        skip: object,
    ) -> None:
        """Return a reader that consults registrations and the generators of using.

        Args:
            registrations: The registrations of the test process.
            using: The generators that a property form gives types.
            skip: The type whose own registration the read ignores, or None.
                register_values reads its type this way.
        """
        self._registrations: Registrations = registrations
        self._using: Mapping[object, Generator[Any]] = using
        self._skip: object = skip
        self.definitions: dict[str, Node] = {}
        self.externals: dict[str, Generator[Any]] = {}
        self.external_paths: list[str] = []
        self._open: dict[object, _SelfReference] = {}
        self._defined: dict[object, _SelfReference] = {}

    def read(
        self, t: object, at: str, given: _Constraints | None = None
    ) -> tuple[Node, Converter]:
        """Return the shape of a type and its converter.

        Args:
            t: The type.
            at: The path of the part of the type.
            given: The constraints of an enclosing Annotated or optional.

        Returns:
            The shape and the converter.

        Raises:
            FaultError: The reader does not read a part of the type, or a
                constraint does not apply.
        """
        constraints = _Constraints() if given is None else given
        if typing.get_origin(t) is Annotated:
            inner, *metadata = typing.get_args(t)
            constraints.add(metadata, at)
            return self.read(inner, at, constraints)
        external = self._using.get(t)
        if external is None and t is not self._skip:
            external = self._lookup(t)
        if external is not None:
            constraints.check_taken("a type that a generator generates", at)
            return self._external(t, external, at), IDENTITY
        values = None if t is self._skip else self._registrations.values.get(t)
        if values is not None:
            constraints.check_taken("a type of registered values", at)
            return {"shape": "literal", "values": values.literals}, values.converter
        reference = self._open.get(t) or self._defined.get(t)
        if reference is not None:
            constraints.check_taken("a type that refers to itself", at)
            reference.recursive = reference.recursive or t in self._open
            node = {"shape": "ref", "name": reference.name}
            return node, deferred_converter(reference.cell)
        if not isinstance(t, type):
            return self._form(t, constraints, at)
        return self._read_class(t, constraints, at)

    def _read_class(
        self, t: type, constraints: _Constraints, at: str
    ) -> tuple[Node, Converter]:
        """Return the shape of a class, or a ref to it when it refers to itself.

        The shape of a class that refers to itself becomes a definition.
        """
        reference = _SelfReference(qualified(t))
        self._open[t] = reference
        try:
            node, converter = self._class(t, constraints, at)
        finally:
            del self._open[t]
        if not reference.recursive:
            return node, converter
        reference.cell.append(converter)
        self.definitions[reference.name] = node
        self._defined[t] = reference
        return {"shape": "ref", "name": reference.name}, deferred_converter(
            reference.cell
        )

    def _lookup(self, t: object) -> Generator[Any] | None:
        """Return the generator that register gives a type, and record the lookup."""
        registrations = self._registrations
        if not registrations.closed:
            registrations.consulted.add(t)
        return registrations.generators.get(t)

    def _external(self, t: object, generator: Generator[Any], at: str) -> Node:
        """Return a ref to a generator of a type that does not have a shape."""
        name = qualified(t)
        self.externals[name] = generator
        self.external_paths.append(at)
        return {"shape": "ref", "name": name}

    def _form(
        self, t: object, constraints: _Constraints, at: str
    ) -> tuple[Node, Converter]:
        """Return the shape of a generic, a union, a Literal or a NewType."""
        if isinstance(t, typing.NewType):
            return self.read(t.__supertype__, at, constraints)
        members = _union_members(t)
        if members is not None:
            return self._union(members, constraints, at)
        return self._generic(t, constraints, at)

    def _generic(
        self, t: object, constraints: _Constraints, at: str
    ) -> tuple[Node, Converter]:
        """Return the shape of a Literal, or of a generic list, tuple, set or dict.

        A set can be a frozenset.

        Raises:
            FaultError: The reader does not read the type, or a constraint
                does not apply.
        """
        origin = typing.get_origin(t)
        args = typing.get_args(t)
        if origin is Literal:
            constraints.check_taken("a Literal", at)
            return _literal_of(list(args), at)
        if origin is list:
            return self._list(args[0], constraints, at, list)
        if origin is tuple and len(args) == _VARIADIC_ARGS and args[1] is ...:
            return self._list(args[0], constraints, at, tuple)
        if origin is tuple:
            constraints.check_taken("a tuple of fields", at)
            fields = [(str(i), arg) for i, arg in enumerate(args)]
            return self._record(fields, at, _tuple_of, _tuple_fields(len(args)))
        if origin is set or origin is frozenset:
            return self._set(args[0], constraints, at, origin)
        if origin is dict:
            return self._map(args[0], args[1], constraints, at)
        raise FaultError(at, f"{t!r} is not a type that the reader reads")

    def _union(
        self, members: tuple[object, ...], constraints: _Constraints, at: str
    ) -> tuple[Node, Converter]:
        """Return the shape of a union. It is an optional, an ip-address or an enum."""
        rest = tuple(member for member in members if member is not type(None))
        if len(rest) < len(members):
            inner: Any = rest[0]
            for member in rest[1:]:
                inner = inner | member
            node, converter = self.read(inner, at, constraints)
            return {"shape": "optional", "of": node}, _optional(converter)
        if set(rest) == {ipaddress.IPv4Address, ipaddress.IPv6Address}:
            address: Node = {"shape": "ip-address"}
            version = constraints.take("version")
            if version is not _UNSET:
                address["version"] = version
            constraints.check_taken("an IP address", at)
            return address, ip_converter()
        constraints.check_taken("a union", at)
        return self._variants(rest, at)

    def _variants(self, members: Sequence[object], at: str) -> tuple[Node, Converter]:
        """Return the enum of variant classes. Each variant has the name of its class.

        Raises:
            FaultError: A variant is not a class, or two variants have one name.
        """
        shapes: list[list[Any]] = []
        cases: list[tuple[str, type, Converter | None]] = []
        for member in members:
            if not isinstance(member, type):
                raise FaultError(
                    at,
                    f"the variant {member!r} is not a class, so it does not have a "
                    "name",
                )
            name = member.__name__
            if any(name == case[0] for case in cases):
                raise FaultError(at, f"two variants are named {name}")
            if not _has_payload(member):
                shapes.append([name, None])
                cases.append((name, member, None))
                continue
            node, converter = self.read(member, f"{at}.({name})")
            shapes.append([name, node])
            cases.append((name, member, converter))
        return {"shape": "enum", "variants": shapes}, _variant_converter(cases)

    def _list(
        self, of: object, constraints: _Constraints, at: str, kind: type
    ) -> tuple[Node, Converter]:
        """Return the shape of a list, or of a tuple of one type.

        A Len of one size makes it a fixed-list.
        """
        low = constraints.take("min_size")
        high = constraints.take("max_size")
        constraints.check_taken("a list", at)
        node_of, converter = self.read(of, f"{at}[]")
        if low is not _UNSET and low == high:
            node: Node = {"shape": "fixed-list", "of": node_of, "size": low}
        else:
            node = {"shape": "list", "of": node_of}
            _sizes(node, low, high)
        return node, _sequence(converter, kind)

    def _set(
        self, of: object, constraints: _Constraints, at: str, kind: type
    ) -> tuple[Node, Converter]:
        """Return the shape of a set or a frozenset."""
        node: Node = {"shape": "set"}
        _sizes(node, constraints.take("min_size"), constraints.take("max_size"))
        constraints.check_taken("a set", at)
        _check_hashable(of, f"{at}[]")
        node["of"], converter = self.read(of, f"{at}[]")
        return node, _set_converter(converter, kind)

    def _map(
        self, key: object, of: object, constraints: _Constraints, at: str
    ) -> tuple[Node, Converter]:
        """Return the shape of a dict."""
        node: Node = {"shape": "map"}
        _sizes(node, constraints.take("min_size"), constraints.take("max_size"))
        constraints.check_taken("a dict", at)
        _check_hashable(key, f"{at}.key")
        node["key"], keys = self.read(key, f"{at}.key")
        node["of"], values = self.read(of, f"{at}[]")
        return node, _map_converter(keys, values)

    def _class(
        self, t: type, constraints: _Constraints, at: str
    ) -> tuple[Node, Converter]:
        """Return the shape of a class from the table of type readers.

        Raises:
            FaultError: The reader does not read the class, or a constraint
                does not apply.
        """
        variants = self._registrations.variants.get(t)
        if variants is not None:
            constraints.check_taken("a type of registered variants", at)
            return self._variants(variants, at)
        if issubclass(t, enum.Enum):
            constraints.check_taken("an Enum", at)
            return _enum_of(t, at)
        if t is bool:
            constraints.check_taken("a bool", at)
            return {"shape": "bool"}, IDENTITY
        scalar = _scalar(t, constraints, at)
        constraints.check_taken(t.__qualname__, at)
        if scalar is not None:
            return scalar
        return self._record_class(t, at)

    def _record_class(self, t: type, at: str) -> tuple[Node, Converter]:
        """Return the shape of a dataclass, a NamedTuple or a TypedDict.

        Raises:
            FaultError: The class is none of them, or the TypedDict has a key
                that is not required.
        """
        named: Any = t
        if dataclasses.is_dataclass(t):
            hints = _hints(t, at)
            fields = [(f.name, hints[f.name]) for f in dataclasses.fields(t) if f.init]
            return self._record(
                fields, at, lambda values: named(**values), _attributes(t, fields)
            )
        if _is_named_tuple(t):
            hints = _hints(t, at)
            fields = [(name, hints[name]) for name in named._fields]
            return self._record(
                fields,
                at,
                lambda values: named(*values.values()),
                _attributes(t, fields),
            )
        if typing.is_typeddict(t):
            optional: frozenset[str] = getattr(t, "__optional_keys__", frozenset())
            if optional:
                keys = ", ".join(sorted(optional))
                raise FaultError(
                    at, f"the keys {keys} of the TypedDict are not required"
                )
            fields = list(_hints(t, at).items())
            return self._record(fields, at, dict, _mapping_fields(fields))
        raise FaultError(at, f"{t.__qualname__} is not a type that the reader reads")

    def _record(
        self,
        fields: list[tuple[str, object]],
        at: str,
        build: Callable[[dict[str, Any]], Any],
        values_of: Callable[[Any], dict[str, Any] | None],
    ) -> tuple[Node, Converter]:
        """Return the shape of a record of fields in their order.

        Raises:
            FaultError: The record does not have a field.
        """
        if not fields:
            raise FaultError(at, "a record without fields does not have a shape")
        shapes: list[list[Any]] = []
        converters: list[tuple[str, Converter]] = []
        for name, hint in fields:
            node, converter = self.read(hint, f"{at}.{name}")
            shapes.append([name, node])
            converters.append((name, converter))
        converter = _record_converter(converters, build, values_of)
        return {"shape": "record", "fields": shapes}, converter


def _scalar(
    t: type, constraints: _Constraints, at: str
) -> tuple[Node, Converter] | None:
    """Return the shape of a scalar or a domain class, or None for any other class.

    Raises:
        FaultError: A constraint does not have a value that the shape takes.
    """
    if issubclass(t, int):
        return _int_shape(t, constraints, at)
    if issubclass(t, float):
        return _float_shape(t, constraints, at)
    if issubclass(t, str):
        return _str_shape(t, constraints)
    if issubclass(t, bytes):
        node: Node = {"shape": "bytes"}
        _sizes(node, constraints.take("min_size"), constraints.take("max_size"))
        return node, _built(t)
    return _time_scalar(t, constraints, at)


def _time_scalar(
    t: type, constraints: _Constraints, at: str
) -> tuple[Node, Converter] | None:
    """Return the shape of a datetime, a date, a time or a timedelta class.

    For any other class, the result is the shape of a domain class, or None.
    """
    if issubclass(t, datetime):
        return _datetime_shape(constraints, at)
    if t is date:
        node: Node = {"shape": "date"}
        _bounds(node, constraints, _date_bound(at))
        return node, date_converter()
    if t is time:
        unit = _unit(constraints, at)
        node = {"shape": "time-of-day", "unit": unit}
        _bounds(node, constraints, _time_bound(unit, at))
        return node, time_converter(unit)
    if t is timedelta:
        unit = _unit(constraints, at)
        node = {"shape": "duration", "unit": unit}
        _bounds(node, constraints, _duration_bound(unit, at))
        return node, duration_converter(unit)
    return _domain_scalar(t, constraints, at)


def _domain_scalar(
    t: type, constraints: _Constraints, at: str
) -> tuple[Node, Converter] | None:
    """Return the shape of a domain class or of a number of two parts.

    The domain classes are timezone, ZoneInfo, UUID, the addresses and
    Decimal. A complex and a Fraction are numbers of two parts.
    """
    if t is timezone:
        node = {"shape": "offset"}
        _bounds(node, constraints, _offset_bound(at))
        return node, offset_converter()
    if t is ZoneInfo:
        return {"shape": "zone"}, zone_converter(at)
    if t is uuid.UUID:
        return {"shape": "uuid"}, uuid_converter()
    if t in (ipaddress.IPv4Address, ipaddress.IPv6Address):
        number = 4 if t is ipaddress.IPv4Address else 6
        version = constraints.take("version")
        if version is not _UNSET and version != number:
            raise FaultError(
                at, f"an {t.__name__} is not an address of version {version}"
            )
        return {"shape": "ip-address", "version": number}, ip_converter()
    if t is Decimal:
        return _decimal_shape(constraints, at)
    two_parts = _TWO_PARTS.get(t)
    return None if two_parts is None else two_parts()


def _built(t: type) -> Converter:
    """Return the converter of a scalar of the class t.

    The class can be a subclass of its base.
    """
    if t in (int, float, str, bytes):
        return IDENTITY
    return Converter(t, lambda value: value)


def _int_shape(t: type, constraints: _Constraints, at: str) -> tuple[Node, Converter]:
    """Return the shape of an int with its width, its sign and its bounds.

    Raises:
        FaultError: The width is not 8, 16, 32, 64 or 128.
    """
    width = constraints.take("width")
    bits, signed = (64, True) if width is _UNSET else (width.bits, width.signed)
    if bits not in _INT_WIDTHS:
        raise FaultError(at, f"an int of {bits} bits does not have a shape")
    node: Node = {"shape": "int", "width": bits, "signed": signed}
    _bounds(node, constraints, _int_bound(at))
    return node, _built(t)


def _float_shape(t: type, constraints: _Constraints, at: str) -> tuple[Node, Converter]:
    """Return the shape of a float with its width and its bounds.

    Raises:
        FaultError: The width is not 32 or 64.
    """
    width = constraints.take("width")
    bits = 64 if width is _UNSET else width.bits
    if bits not in _FLOAT_WIDTHS:
        raise FaultError(at, f"a float of {bits} bits does not have a shape")
    node: Node = {"shape": "float", "width": bits}
    for key in ("allow_nan", "allow_infinity"):
        if constraints.take(key) is True:
            node[key] = True
    _bounds(node, constraints, _float_bound(cast("Width", bits), at))
    return node, _built(t)


def _str_shape(t: type, constraints: _Constraints) -> tuple[Node, Converter]:
    """Return the shape of a str. It is a char with Char, and a string otherwise."""
    alphabet = constraints.take("alphabet")
    if constraints.take("char") is True:
        node: Node = {"shape": "char"}
    else:
        node = {"shape": "string"}
        _sizes(node, constraints.take("min_size"), constraints.take("max_size"))
        pattern = constraints.take("pattern")
        if pattern is not _UNSET:
            node["pattern"] = pattern
    if alphabet is not _UNSET:
        node["alphabet"] = alphabet
    return node, _built(t)


def _decimal_shape(constraints: _Constraints, at: str) -> tuple[Node, Converter]:
    """Return the shape of a Decimal of the scale of its constraint.

    Raises:
        FaultError: The Decimal does not have the constraint Scale.
    """
    digits = constraints.take("scale")
    if digits is _UNSET:
        raise FaultError(
            at,
            "a Decimal needs the constraint Scale, because a default scale does not "
            "suit most domains",
        )
    node: Node = {"shape": "decimal", "scale": digits}
    _bounds(node, constraints, _decimal_bound(digits, at))
    return node, decimal_converter(digits)


def _complex_shape() -> tuple[Node, Converter]:
    """Return the shape of a complex: a record of the 64-bit floats real and imag."""
    node: Node = {
        "shape": "record",
        "fields": [
            ["real", {"shape": "float", "width": 64}],
            ["imag", {"shape": "float", "width": 64}],
        ],
    }

    def to(value: Fields) -> complex:
        (_, real), (_, imag) = value.fields
        return complex(real, imag)

    def back(value: Any) -> Any:
        if not isinstance(value, complex):
            return value
        return Fields((("real", value.real), ("imag", value.imag)))

    return node, Converter(to, back)


def _fraction_shape() -> tuple[Node, Converter]:
    """Return the shape of a Fraction: a record of the ints num and den.

    num is a signed 64-bit int, and den is an unsigned 64-bit int of at least
    1. The Fraction of a record is in lowest terms. A Fraction whose
    numerator or denominator is outside its 64-bit range does not have a
    record, so the shape refuses its inverse.
    """
    node: Node = {
        "shape": "record",
        "fields": [
            ["num", {"shape": "int", "width": 64, "signed": True}],
            ["den", {"shape": "int", "width": 64, "signed": False, "min": 1}],
        ],
    }

    def to(value: Fields) -> Fraction:
        (_, num), (_, den) = value.fields
        return Fraction(num, den)

    def back(value: Any) -> Any:
        if not isinstance(value, Fraction):
            return value
        return Fields((("num", value.numerator), ("den", value.denominator)))

    return node, Converter(to, back)


#: The shape of each class of numbers of two parts. A number of two parts
#: does not take a constraint.
_TWO_PARTS: dict[type, Callable[[], tuple[Node, Converter]]] = {
    complex: _complex_shape,
    Fraction: _fraction_shape,
}


def _datetime_shape(constraints: _Constraints, at: str) -> tuple[Node, Converter]:
    """Return the shape of a datetime from its constraint Timezone.

    Raises:
        FaultError: The datetime does not have the constraint Timezone, or
            its zone is not None, timezone.utc or the ellipsis.
    """
    tz = constraints.take("timezone")
    if tz is _UNSET:
        raise FaultError(
            at,
            "a datetime needs the constraint Timezone, because a value of the type "
            "datetime can have a zone or not",
        )
    unit = _unit(constraints, at)
    if tz is None:
        node: Node = {"shape": "local-date-time", "unit": unit}
        _bounds(node, constraints, _local_bound(unit, at))
        return node, local_converter(unit)
    if tz is UTC:
        node = {"shape": "instant", "unit": unit}
        _bounds(node, constraints, _instant_bound(unit, at))
        return node, instant_converter(unit)
    if tz is ...:
        return {"shape": "zoned-date-time", "unit": unit}, zoned_converter(unit, at)
    raise FaultError(
        at, f"the reader maps Timezone of None, timezone.utc and ..., not {tz!r}"
    )


def _unit(constraints: _Constraints, at: str) -> str:
    """Return the unit of a time shape. The default unit is us.

    Raises:
        FaultError: The unit is ns, or it is not one of s, ms, us and ns.
    """
    unit = constraints.take("unit")
    if unit is _UNSET:
        return "us"
    if unit == "ns":
        raise FaultError(
            at,
            "a datetime, a time and a timedelta do not have values at ns, because "
            "their resolution is one microsecond",
        )
    if unit not in _UNITS:
        raise FaultError(at, f"the unit {unit!r} is not one of s, ms, us and ns")
    return cast("str", unit)


def _sizes(node: Node, low: Any, high: Any) -> None:
    """Set the sizes of a shape from its constraints."""
    if low is not _UNSET:
        node["min_size"] = low
    if high is not _UNSET:
        node["max_size"] = high


def _bounds(
    node: Node, constraints: _Constraints, bound: Callable[[Any, _Step], Any]
) -> None:
    """Set the bounds of a shape. An exclusive bound moves one step inside."""
    for key, name, inward in (("min", "lo", 1), ("max", "hi", -1)):
        found = constraints.bound(name)
        if found is not None:
            node[key] = bound(found.value, inward if found.exclusive else 0)


def _refuse(at: str, value: object, what: str) -> FaultError:
    """Return the fault of a bound that is not a value of a part."""
    return FaultError(at, f"the bound {value!r} is not {what}")


def _lonely(at: str, value: object, where: str) -> FaultError:
    """Return the fault of an exclusive bound without a neighbour inside the range."""
    return FaultError(at, f"the bound {value!r} does not have a neighbour in {where}")


def _int_bound(at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the JSON form of a bound of an int."""

    def bound(value: Any, by: _Step) -> Any:
        if type(value) is not int:
            raise _refuse(at, value, "an int")
        return literal.plain(value + by)

    return bound


def _float_bound(width: Width, at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the JSON form of a bound of a float of a width."""

    def bound(value: Any, by: _Step) -> Any:
        if type(value) not in (int, float) or math.isnan(value):
            raise _refuse(at, value, "a number")
        x = float(value)
        if by > 0:
            x = next_up(x, width)
        elif by < 0:
            x = next_down(x, width)
        return literal.plain(x)

    return bound


def _decimal_bound(scale: int, at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the text of a bound of a Decimal of a scale."""
    step = Decimal(1).scaleb(-scale)

    def bound(value: Any, by: _Step) -> str:
        if type(value) not in (int, str, Decimal):
            raise _refuse(at, value, "a Decimal")
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise _refuse(at, value, "a Decimal") from None
        if not number.is_finite():
            raise _refuse(at, value, "a finite Decimal")
        return format(number + by * step, "f")

    return bound


def _date_bound(at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the text of a bound of a date."""

    def bound(value: Any, by: _Step) -> str:
        if not isinstance(value, date) or isinstance(value, datetime):
            raise _refuse(at, value, "a date")
        try:
            return (value + timedelta(days=by)).isoformat()
        except OverflowError:
            raise _lonely(at, value, "the years 1 to 9999") from None

    return bound


def _time_bound(unit: str, at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the text of a bound of a time of day at a unit."""
    delta = timedelta(microseconds=_STEPS[unit])

    def bound(value: Any, by: _Step) -> str:
        if not isinstance(value, time) or value.tzinfo is not None:
            raise _refuse(at, value, "a time without a zone")
        day = date(2000, 1, 1)
        moved = datetime.combine(day, value) + by * delta
        if moved.date() != day:
            raise _lonely(at, value, "the same day")
        return moved.time().isoformat(timespec="microseconds")

    return bound


def _local_bound(unit: str, at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the text of a bound of a datetime without a zone."""
    delta = timedelta(microseconds=_STEPS[unit])

    def bound(value: Any, by: _Step) -> str:
        if not isinstance(value, datetime) or value.tzinfo is not None:
            raise _refuse(at, value, "a datetime without a zone")
        try:
            moved = value + by * delta
        except OverflowError:
            raise _lonely(at, value, "the years 1 to 9999") from None
        return moved.isoformat(timespec="microseconds")

    return bound


def _instant_bound(unit: str, at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the text of a bound of an instant in UTC."""
    delta = timedelta(microseconds=_STEPS[unit])

    def bound(value: Any, by: _Step) -> str:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise _refuse(at, value, "a datetime with a zone")
        try:
            utc = (value + by * delta).astimezone(UTC).replace(tzinfo=None)
        except OverflowError:
            raise _lonely(at, value, "the years 1 to 9999") from None
        return utc.isoformat(timespec="microseconds") + "Z"

    return bound


def _duration_bound(unit: str, at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the units of a bound of a timedelta at a unit."""

    def bound(value: Any, by: _Step) -> int:
        if not isinstance(value, timedelta):
            raise _refuse(at, value, "a timedelta")
        units, rest = divmod(value // timedelta(microseconds=1), _STEPS[unit])
        if rest:
            raise _refuse(at, value, f"a whole number of the unit {unit}")
        return units + by

    return bound


def _offset_bound(at: str) -> Callable[[Any, _Step], Any]:
    """Return the function of the seconds east of UTC of a bound of an offset.

    A bound is a timedelta east of UTC, or a timezone.
    """

    def bound(value: Any, by: _Step) -> int:
        if isinstance(value, timezone):
            value = value.utcoffset(None)
        if not isinstance(value, timedelta):
            raise _refuse(at, value, "a timedelta or a timezone")
        seconds, rest = divmod(value, timedelta(seconds=1))
        if rest:
            raise _refuse(at, value, "a whole number of seconds")
        return seconds + by

    return bound


def _hashable(t: object) -> bool:
    """Report whether the values of a type can be the keys of a dict."""
    if typing.get_origin(t) is Annotated:
        return _hashable(typing.get_args(t)[0])
    members = _union_members(t)
    if members is not None:
        return all(_hashable(member) for member in members)
    origin = typing.get_origin(t)
    if origin in (list, dict, set):
        return False
    if origin is tuple:
        return all(_hashable(arg) for arg in typing.get_args(t) if arg is not ...)
    if isinstance(t, type):
        return getattr(t, "__hash__", None) is not None
    return True


def _check_hashable(t: object, at: str) -> None:
    """Refuse a key or element type of a dict or a set whose values are unhashable.

    Raises:
        FaultError: The values of the type are unhashable.
    """
    if not _hashable(t):
        raise FaultError(at, f"the values of {t!r} are not hashable")


def _optional(of: Converter) -> Converter:
    """Return the converter of an optional value."""
    return Converter(
        lambda value: None if value is None else of.to(value),
        lambda value: None if value is None else of.back(value),
    )


def _sequence(of: Converter, kind: type) -> Converter:
    """Return the converter of a list or a tuple of one type."""

    def back(value: Any) -> Any:
        if not isinstance(value, kind):
            return value
        return [of.back(item) for item in cast("Sequence[Any]", value)]

    return Converter(lambda value: kind(of.to(item) for item in value), back)


def _set_converter(of: Converter, kind: type) -> Converter:
    """Return the converter of a set or a frozenset.

    back lists the elements in the order of their canonical texts, so a set
    has one sequence of choices in every process.
    """

    def back(value: Any) -> Any:
        if not isinstance(value, kind):
            return value
        items = [of.back(item) for item in cast("set[Any]", value)]
        return sorted(items, key=canonical)

    return Converter(lambda value: kind(of.to(item) for item in value), back)


def _map_converter(keys: Converter, values: Converter) -> Converter:
    """Return the converter of a dict."""

    def back(value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        entries = value.items()
        return Pairs(tuple((keys.back(k), values.back(v)) for k, v in entries))

    def to(value: Pairs) -> dict[Any, Any]:
        return {keys.to(k): values.to(v) for k, v in value.items}

    return Converter(to, back)


def _tuple_of(values: dict[str, Any]) -> tuple[Any, ...]:
    """Return the tuple of the fields of a record of a tuple type."""
    return tuple(values.values())


def _tuple_fields(count: int) -> Callable[[Any], dict[str, Any] | None]:
    """Return the fields of a tuple of count items, or None for any other value."""

    def values_of(value: Any) -> dict[str, Any] | None:
        if type(value) is not tuple or len(value) != count:
            return None
        return {str(i): item for i, item in enumerate(value)}

    return values_of


def _attributes(
    t: type, fields: list[tuple[str, object]]
) -> Callable[[Any], dict[str, Any] | None]:
    """Return the fields of an instance of a class, or None for any other value."""

    def values_of(value: Any) -> dict[str, Any] | None:
        if type(value) is not t:
            return None
        return {name: getattr(value, name) for name, _ in fields}

    return values_of


def _mapping_fields(
    fields: list[tuple[str, object]],
) -> Callable[[Any], dict[str, Any] | None]:
    """Return the fields of a dict of a TypedDict, or None for any other value."""
    names = [name for name, _ in fields]

    def values_of(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        mapping = cast("dict[str, Any]", value)
        if set(mapping) != set(names):
            return None
        return {name: mapping[name] for name in names}

    return values_of


def _record_converter(
    fields: list[tuple[str, Converter]],
    build: Callable[[dict[str, Any]], Any],
    values_of: Callable[[Any], dict[str, Any] | None],
) -> Converter:
    """Return the converter of a record that build makes from its fields."""

    def to(value: Fields) -> Any:
        items = zip(fields, value.fields, strict=True)
        return build({name: conv.to(item) for (name, conv), (_, item) in items})

    def back(value: Any) -> Any:
        found = values_of(value)
        if found is None:
            return value
        return Fields(tuple((name, conv.back(found[name])) for name, conv in fields))

    return Converter(to, back)


def _variant_converter(cases: list[tuple[str, type, Converter | None]]) -> Converter:
    """Return the converter of an enum of variant classes."""
    by_name = {name: (cls, converter) for name, cls, converter in cases}

    def to(value: Neutral) -> Any:
        cls, converter = by_name[value.name]
        return cls() if converter is None else converter.to(value.payload)

    def back(value: Any) -> Any:
        for name, cls, converter in cases:
            if type(value) is not cls:
                continue
            if converter is None:
                return Neutral(name)
            return Neutral(name, converter.back(value))
        return value

    return Converter(to, back)


def _enum_of(t: type[enum.Enum], at: str) -> tuple[Node, Converter]:
    """Return the shape of an Enum.

    The shape is an enum whose variants have the names of the members.

    Raises:
        FaultError: The Enum does not have a member.
    """
    members = list(t)
    if not members:
        raise FaultError(at, f"{t.__qualname__} does not have a member")
    node: Node = {"shape": "enum", "variants": [[m.name, None] for m in members]}

    def back(value: Any) -> Any:
        return Neutral(value.name) if isinstance(value, t) else value

    return node, Converter(lambda value: t[value.name], back)


def _literal_of(values: list[object], at: str) -> tuple[Node, Converter]:
    """Return the literal shape of the values of a Literal in their order.

    Raises:
        FaultError: A value does not have a typed literal.
    """
    literals: list[dict[str, Any]] = []
    for value in values:
        written = encode(value)
        if written is None:
            raise FaultError(at, f"the value {value!r} does not have a typed literal")
        literals.append(written)
    return {"shape": "literal", "values": literals}, literal_converter(values, literals)


def literal_converter(
    values: Sequence[object], literals: Sequence[object]
) -> Converter:
    """Return the converter between the decoded typed literals of values and the values.

    Args:
        values: The values.
        literals: The typed literal of each value in the order of the values.

    Returns:
        The converter.
    """
    decoded = [literal.decode(written) for written in literals]
    to_value = {canonical(d): v for d, v in zip(decoded, values, strict=True)}
    to_neutral = {canonical(v): d for d, v in zip(decoded, values, strict=True)}

    def back(value: Any) -> Any:
        return to_neutral.get(canonical(value), value)

    return Converter(lambda value: to_value[canonical(value)], back)


def derive(
    t: object,
    registrations: Registrations,
    using: Mapping[object, Generator[Any]] | None = None,
    skip: object = None,
) -> Derived:
    """Read a Python type into a shape file.

    Args:
        t: The type.
        registrations: The registrations of the test process.
        using: The generators that a property form gives types.
        skip: The type whose own registration the read ignores.

    Returns:
        The shape file and its converter.

    Raises:
        FaultError: The reader does not read a part of the type, or a
            constraint does not apply. The fault is at the part.
    """
    reader = _Reader(registrations, {} if using is None else using, skip)
    root, converter = reader.read(t, _name_of(t))
    if reader.definitions:
        root["definitions"] = reader.definitions
    return Derived(root, reader.externals, reader.external_paths, converter)
