# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The inverse of a generator from a value to the choices that decode to it.

invert walks a generator with a value. It emits each choice in the order and
with the bounds of the requests that the decode of the generator makes. It
checks each choice against its bounds as it emits the choice. invert then
replays the choices. It returns them only when they decode to the value and
the case records them unchanged.

A value that the generator cannot produce raises CannotInvertError.

- The value has another type.
- The value is outside the bounds.
- The collection has another size.
- A set or a map repeats an element.

Every generator runs backwards except a map without an inverse, a bind and
a composite. A filter runs backwards through the generator that it filters,
and a deferred generator through the generator that it picks.
A function that the engine cannot run backwards raises NoInverseError. The
caller can tell that error apart from a value outside a domain. A one-of and
a recursive raise NoInverseError when no branch produces the value and one
of the branches does not have an inverse.

When more than one sequence of choices decodes to a value, the inverse takes
the first sequence in a fixed order.

- A one-of takes its first alternative whose inverse succeeds.
- A sampled-from takes the first index of an equal value.
- A permutation takes the smallest index at each swap.
- A string-matching takes the match that a backtracking engine finds first.
  The engine tries the alternatives in order. It repeats each quantifier as
  often as the rest of the pattern allows. The search keeps a stack of its
  own, so the length of a string does not count against the recursion
  limit.
- An optional takes absent before present.
- A recursive takes the base before the extension.
- The elements of a set and the entries of a map come in the shortlex order
  of their own choices.

A zoned-date-time and a wall-time run backwards through the branch that
takes the whole range.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from dokimi_assert._prop.engine import alphabet, pattern
from dokimi_assert._prop.engine.case import Case, Rejected, Replaying
from dokimi_assert._prop.engine.choice import (
    UINT64_MAX,
    Bounds,
    Choice,
    IntegerBounds,
    Value,
    choice_of,
    same_choice,
)
from dokimi_assert._prop.engine.draw import flag_bounds
from dokimi_assert._prop.engine.generator import (
    Bool,
    Bytes,
    Deferred,
    Dict,
    Filter,
    Float,
    Generator,
    Integer,
    Just,
    List,
    Mapped,
    Matching,
    OneOf,
    Optional,
    Permutation,
    Piece,
    Position,
    Recursive,
    SampledFrom,
    Text,
)
from dokimi_assert._prop.engine.order import choice_key, shortlex
from dokimi_assert._prop.engine.shape import (
    EnumShape,
    InstantShape,
    Int128Shape,
    IpShape,
    ListShape,
    LocalDateTimeShape,
    MapShape,
    OptionalShape,
    RecordShape,
    Ref,
    Root,
    WallShape,
    ZonedShape,
    halves,
    second_part,
)
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical
from dokimi_assert._prop.engine.zone import ZONES

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from dokimi_assert._prop.engine.collection import Sizes
    from dokimi_assert._prop.engine.float import Key

__all__ = [
    "CannotInvertError",
    "Emitted",
    "NoInverseError",
    "Step",
    "emit",
    "inverse_of",
    "invert",
]


class CannotInvertError(ValueError):
    """The error of a value that a generator cannot produce from any choices."""


class NoInverseError(CannotInvertError):
    """The error of a value whose choices the engine cannot compute.

    A generator on the way to the value applies a function that the engine
    cannot run backwards.
    """


@dataclass(frozen=True, slots=True)
class Step:
    """One emitted choice with the bounds of its request and its value.

    Attributes:
        bounds: The bounds.
        value: The value.
    """

    bounds: Bounds
    value: Value


#: The steps that a generator emits for a value, and the value that they
#: decode to. That value differs from the given value only in the order of
#: the elements of a set and the entries of a map.
Emitted: TypeAlias = tuple[list[Step], object]

#: The bounds of a choice of 0 or 1, and of the index of a zone of the list.
_BIT = IntegerBounds(0, 1)
_ZONE_INDEX = IntegerBounds(0, len(ZONES) - 1)

#: The choice of a zoned value that takes the whole range. Only a zone with a
#: change makes the choice.
_WHOLE_RANGE = 0


def invert(generator: Generator[Any], value: object) -> list[Choice]:
    """Return the choices that decode to a value.

    Args:
        generator: The generator.
        value: The value.

    Returns:
        The choices.

    Raises:
        NoInverseError: A generator on the way applies a function that the engine
            cannot run backwards.
        CannotInvertError: The generator cannot produce the value.
    """
    steps, normal = emit(generator, value)
    choices = [choice_of(step.bounds, step.value) for step in steps]
    c = Case(Replaying(choices))
    try:
        decoded = generator.decode(c)
    except Rejected:
        msg = f"prop: the choices of {canonical(value)} do not decode to a value"
        raise CannotInvertError(msg) from None
    unchanged = len(c.choices) == len(choices) and all(
        same_choice(a, b) for a, b in zip(c.choices, choices, strict=True)
    )
    if not unchanged or canonical(decoded) != canonical(normal):
        msg = f"prop: {canonical(value)} is not a value that the generator produces"
        raise CannotInvertError(msg)
    return choices


def inverse_of(generator: Generator[Any], value: object) -> list[Choice] | None:
    """Return the choices that decode to a value, or None when there are none.

    An error that the generator raises while it decodes the choices
    propagates to the caller.

    Args:
        generator: The generator.
        value: The value.

    Returns:
        The choices, or None when invert raises CannotInvertError or NoInverseError.
    """
    try:
        return invert(generator, value)
    except CannotInvertError:
        return None


def _step(bounds: Bounds, value: object) -> Step:
    """Return a step whose value its bounds admit."""
    if not bounds.admits(value):
        msg = f"prop: {canonical(value)} is outside {bounds.id}"
        raise CannotInvertError(msg)
    return Step(bounds, cast("Value", value))


def _index_of(values: Sequence[object], value: object) -> int:
    """Return the first index of a value equal to value."""
    wanted = canonical(value)
    for index, candidate in enumerate(values):
        if canonical(candidate) == wanted:
            return index
    msg = f"prop: {canonical(value)} is not one of the values"
    raise CannotInvertError(msg)


def _first_branch(
    branches: list[tuple[int, Generator[Any]]],
    value: object,
    bounds: IntegerBounds,
    refusal: str,
) -> Emitted:
    """Return the index of the first branch that produces value, then its steps.

    refusal is the reason of the refusal when no branch produces the value.
    """
    unknown = False
    for index, branch in branches:
        try:
            steps, normal = emit(branch, value)
        except NoInverseError:
            unknown = True
            continue
        except CannotInvertError:
            continue
        return [Step(bounds, index), *steps], normal
    if unknown:
        msg = f"prop: {refusal}, and one of them does not have an inverse"
        raise NoInverseError(msg)
    msg = f"prop: {refusal}"
    raise CannotInvertError(msg)


def _shortlex(steps: list[Step]) -> tuple[int, tuple[Key, ...]]:
    """Return the shortlex key of steps. The shrinker orders choices by the same key."""
    return shortlex([choice_key(step.bounds, step.value) for step in steps])


def _collection(sizes: Sizes, items: list[list[Step]]) -> list[Step]:
    """Return the flags, the item steps and the stop of a collection."""
    count = len(items)
    if count < sizes.min_size or (
        sizes.max_size is not None and count > sizes.max_size
    ):
        msg = f"prop: {count} items are outside the sizes of the collection"
        raise CannotInvertError(msg)
    steps: list[Step] = []
    for index, item in enumerate(items):
        steps.append(Step(flag_bounds(index, sizes.min_size, sizes.max_size), 1))
        steps.extend(item)
    steps.append(Step(flag_bounds(count, sizes.min_size, sizes.max_size), 0))
    return steps


def _distinct(values: list[object]) -> None:
    """Refuse values of which two are equal."""
    if len({canonical(value) for value in values}) != len(values):
        msg = f"prop: {canonical(values)} repeats a value"
        raise CannotInvertError(msg)


def _elements(of: Generator[Any], value: object, unique: bool) -> list[Emitted]:
    """Return the steps of each element, and the value that they decode to."""
    if not isinstance(value, list):
        msg = f"prop: {canonical(value)} is not a list"
        raise CannotInvertError(msg)
    items: list[object] = value
    if unique:
        _distinct(items)
    # A comprehension adds a frame to each level of a recursive value before
    # Python 3.12, and a value at its budget then runs out of frames.
    emitted: list[Emitted] = []
    for element in items:
        emitted.append(emit(of, element))  # noqa: PERF401
    return emitted


def _entries(
    sizes: Sizes, key: Generator[Any], of: Generator[Any], value: object
) -> Emitted:
    """Return the flags and the entries of a map in shortlex order.

    Each entry has the steps of its key, then the steps of its value.
    """
    if not isinstance(value, Pairs):
        msg = f"prop: {canonical(value)} is not a map"
        raise CannotInvertError(msg)
    _distinct([k for k, _ in value.items])
    emitted: list[tuple[list[Step], tuple[object, object]]] = []
    for k, v in value.items:
        key_steps, key_normal = emit(key, k)
        value_steps, value_normal = emit(of, v)
        emitted.append(([*key_steps, *value_steps], (key_normal, value_normal)))
    emitted.sort(key=lambda entry: _shortlex(entry[0]))
    steps = _collection(sizes, [entry for entry, _ in emitted])
    return steps, Pairs(tuple(normal for _, normal in emitted))


#: The fields of a record of a shape of two choices.
_TWO_FIELDS = 2


def _two_parts(value: object, names: tuple[str, str]) -> tuple[object, object]:
    """Return the two fields of a record of a shape of two choices."""
    fields = value.fields if isinstance(value, Fields) else ()
    if len(fields) != _TWO_FIELDS or (fields[0][0], fields[1][0]) != names:
        msg = f"prop: {canonical(value)} is not a record of {names[0]} and {names[1]}"
        raise CannotInvertError(msg)
    return fields[0][1], fields[1][1]


def _zone_steps(value: object, part: str) -> tuple[list[Step], object]:
    """Return the index of the zone and the whole-range choice, and the other part."""
    inner, name = _two_parts(value, (part, "zone"))
    index = _index_of([zone.name for zone in ZONES], name)
    steps = [Step(_ZONE_INDEX, index)]
    if ZONES[index].changes:
        steps.append(Step(_BIT, _WHOLE_RANGE))
    return steps, inner


@dataclass(frozen=True, slots=True)
class _Count:
    """The work of the repetitions of a quantifier from a count on."""

    piece: pattern.Repeat
    count: int


@dataclass(frozen=True, slots=True)
class _Check:
    """The work at the end of one repetition of a quantifier that started at start."""

    piece: pattern.Repeat
    count: int
    start: int


#: The work that a match has left in order, and the steps that it has
#: emitted in reverse order. Each is a linked list of pairs, so a state of the
#: search shares them with its earlier states.
_Work: TypeAlias = "tuple[Piece | _Count | _Check, _Work] | None"
_Steps: TypeAlias = "tuple[Step, _Steps] | None"

#: A state of the search: the work left, the position in the text and the
#: steps so far.
_State: TypeAlias = "tuple[_Work, int, _Steps]"


def _single(
    piece: pattern.Literal | pattern.Class, chars: list[str], at: int
) -> tuple[int, Step | None] | None:
    """Return where a literal or a class at at ends, and its step, or None."""
    if at >= len(chars):
        return None
    char = chars[at]
    if isinstance(piece, pattern.Literal):
        return (at + 1, None) if char == piece.char else None
    offset = piece.offset_of(char)
    if offset is None:
        return None
    return at + 1, Step(IntegerBounds(0, piece.size - 1), offset)


def _match(root: Piece, chars: list[str]) -> list[Step] | None:
    """Return the steps of the first match of root that ends at the end of chars.

    The search is depth first in the order of a backtracking engine. A
    repetition that matches the empty string does not repeat beyond the
    minimum, so the search ends.

    Raises:
        NoInverseError: The pattern has a piece outside the portable subset.
    """
    stack: list[_State] = [((root, None), 0, None)]
    while stack:
        work, at, steps = stack.pop()
        if work is None:
            if at == len(chars):
                return _flattened(steps)
            continue
        item, rest = work
        if isinstance(item, (_Count, _Check)):
            stack.extend(_quantifier_states(item, rest, at, steps))
        else:
            stack.extend(_piece_states(item, rest, at, steps, chars))
    return None


def _piece_states(
    piece: Piece, rest: _Work, at: int, steps: _Steps, chars: list[str]
) -> list[_State]:
    """Return the states of the search after a piece at at, in the order of the stack.

    Raises:
        NoInverseError: The piece is outside the portable subset.
    """
    if isinstance(piece, (pattern.Literal, pattern.Class)):
        matched = _single(piece, chars, at)
        if matched is None:
            return []
        end, step = matched
        return [(rest, end, steps if step is None else (step, steps))]
    if isinstance(piece, pattern.Sequence):
        todo = rest
        for item in reversed(piece.items):
            todo = (item, todo)
        return [(todo, at, steps)]
    if isinstance(piece, pattern.Alternation):
        return [
            ((piece.branches[index], rest), at, (Step(piece.bounds, index), steps))
            for index in reversed(range(len(piece.branches)))
        ]
    if isinstance(piece, pattern.Repeat):
        return [((_Count(piece, 0), rest), at, steps)]
    name = type(piece).__name__
    msg = f"prop: a {name} piece does not run backwards"
    raise NoInverseError(msg)


def _quantifier_states(
    work: _Count | _Check, rest: _Work, at: int, steps: _Steps
) -> list[_State]:
    """Return the states of the search after the work of a quantifier at at.

    The states are in the order of the stack.
    """
    if isinstance(work, _Check):
        if at != work.start or work.count < work.piece.sizes.min_size:
            return [((_Count(work.piece, work.count + 1), rest), at, steps)]
        return []
    sizes = work.piece.sizes
    flag = flag_bounds(work.count, sizes.min_size, sizes.max_size)
    states: list[_State] = []
    if flag.lo == 0:
        states.append((rest, at, (Step(flag, 0), steps)))
    if flag.hi == 1:
        check = _Check(work.piece, work.count, at)
        states.append(((work.piece.item, (check, rest)), at, (Step(flag, 1), steps)))
    return states


def _flattened(steps: _Steps) -> list[Step]:
    """Return the steps of a linked list in order."""
    out: list[Step] = []
    while steps is not None:
        step, steps = steps
        out.append(step)
    out.reverse()
    return out


def _emit_integer(g: Integer, value: object) -> Emitted:
    """Return the one choice of an integer."""
    return [_step(g.bounds, value)], value


def _emit_float(g: Float, value: object) -> Emitted:
    """Return the one choice of a float."""
    return [_step(g.bounds, value)], value


def _emit_bool(g: Bool, value: object) -> Emitted:
    """Return the one choice of a bool."""
    del g
    if not isinstance(value, bool):
        msg = f"prop: {canonical(value)} is not a bool"
        raise CannotInvertError(msg)
    return [Step(_BIT, 1 if value else 0)], value


def _emit_just(g: Just[Any], value: object) -> Emitted:
    """Return an empty list of steps for the given value."""
    if canonical(value) != canonical(g.value):
        msg = f"prop: {canonical(value)} is not {canonical(g.value)}"
        raise CannotInvertError(msg)
    return [], value


def _emit_sampled(g: SampledFrom[Any], value: object) -> Emitted:
    """Return the index of the first given value equal to value."""
    index = _index_of(g.values, value)
    return [Step(IntegerBounds(0, len(g.values) - 1), index)], value


def _emit_one_of(g: OneOf[Any], value: object) -> Emitted:
    """Return the index of the first alternative that produces value, then its steps."""
    bounds = IntegerBounds(0, len(g.of) - 1)
    refusal = f"no alternative produces {canonical(value)}"
    return _first_branch(list(enumerate(g.of)), value, bounds, refusal)


def _emit_optional(g: Optional[Any] | OptionalShape, value: object) -> Emitted:
    """Return absent, or present and then the steps of the value."""
    if value is None:
        return [Step(_BIT, 0)], None
    steps, normal = emit(g.of, value)
    return [Step(_BIT, 1), *steps], normal


def _emit_list(g: List[Any], value: object) -> Emitted:
    """Return the flags and the elements of a list."""
    emitted = _elements(g.of, value, g.unique)
    return _collection(g.sizes, [s for s, _ in emitted]), [n for _, n in emitted]


def _emit_list_shape(g: ListShape, value: object) -> Emitted:
    """Return the flags and the elements of a list, a fixed-list or a set.

    The elements of a set come in shortlex order.
    """
    emitted = _elements(g.of, value, g.unique)
    if g.unique:
        emitted.sort(key=lambda element: _shortlex(element[0]))
    return _collection(g.sizes, [s for s, _ in emitted]), [n for _, n in emitted]


def _emit_dict(g: Dict[Any, Any], value: object) -> Emitted:
    """Return the flags and the entries of a dict."""
    return _entries(g.sizes, g.keys, g.values, value)


def _emit_map_shape(g: MapShape, value: object) -> Emitted:
    """Return the flags and the entries of a map."""
    return _entries(g.sizes, g.key, g.of, value)


def _emit_text(g: Text, value: object) -> Emitted:
    """Return the one sequence of the indices of the characters of a string."""
    if not isinstance(value, str):
        msg = f"prop: {canonical(value)} is not a string"
        raise CannotInvertError(msg)
    characters = g.characters
    if characters is None:
        indices = [alphabet.index_of(char) for char in value]
    else:
        indices = [
            characters.index(char) if char in characters else None for char in value
        ]
    if None in indices:
        msg = f"prop: {canonical(value)} has a character outside the alphabet"
        raise CannotInvertError(msg)
    return [_step(g.bounds, tuple(indices))], value


def _emit_bytes(g: Bytes, value: object) -> Emitted:
    """Return the one sequence of the bytes."""
    if not isinstance(value, bytes):
        msg = f"prop: {canonical(value)} is not bytes"
        raise CannotInvertError(msg)
    return [_step(g.bounds, tuple(value))], value


def _emit_matching(g: Matching, value: object) -> Emitted:
    """Return the choices of the first match of the pattern in full."""
    if not isinstance(value, str):
        msg = f"prop: {canonical(value)} is not a string"
        raise CannotInvertError(msg)
    steps = _match(g.piece, list(value))
    if steps is None:
        msg = f"prop: the pattern does not match {canonical(value)} in full"
        raise CannotInvertError(msg)
    return steps, value


def _emit_permutation(g: Permutation[Any], value: object) -> Emitted:
    """Return the smallest index at each swap that orders the values as value."""
    current: list[object] = list(g.values)
    if not isinstance(value, list) or len(value) != len(current):
        msg = f"prop: {canonical(value)} is not a permutation of the values"
        raise CannotInvertError(msg)
    ordered: list[object] = value
    steps: list[Step] = []
    last = len(current) - 1
    for i in range(last):
        j = i + _index_of(current[i:], ordered[i])
        steps.append(Step(IntegerBounds(i, last), j))
        current[i], current[j] = current[j], current[i]
    if canonical(current) != canonical(ordered):
        msg = f"prop: {canonical(value)} is not a permutation of the values"
        raise CannotInvertError(msg)
    return steps, value


def _emit_filter(g: Filter[Any], value: object) -> Emitted:
    """Return the steps of the source for a value that the predicate keeps."""
    if not g.keep(value):
        msg = f"prop: the filter rejects {canonical(value)}"
        raise CannotInvertError(msg)
    return emit(g.of, value)


def _emit_mapped(g: Mapped[Any, Any], value: object) -> Emitted:
    """Return the steps of the source value that the inverse of the map returns."""
    if g.back is None:
        msg = "prop: a map does not run backwards"
        raise NoInverseError(msg)
    try:
        inner = g.back(value)
    except CannotInvertError:
        raise
    except Exception as error:
        msg = f"prop: {canonical(value)} is not a value of the map: {error}"
        raise CannotInvertError(msg) from error
    steps, normal = emit(g.of, inner)
    return steps, g.f(normal)


def _emit_recursive(g: Recursive[Any], value: object) -> Emitted:
    """Return one position of a recursive value from the base or else the extension."""
    refusal = f"neither the base nor the extension produces {canonical(value)}"
    return _first_branch([(0, g.base), (1, g.extend)], value, _BIT, refusal)


def _emit_position(g: Position[Any], value: object) -> Emitted:
    """Return one position of the value of the owner."""
    return _emit_recursive(g.owner, value)


def _emit_root(g: Root, value: object) -> Emitted:
    """Return the steps of the root shape."""
    return emit(g.node, value)


def _emit_ref(g: Ref, value: object) -> Emitted:
    """Return the steps of the named definition."""
    return emit(g.definitions[g.name], value)


def _emit_record(g: RecordShape, value: object) -> Emitted:
    """Return the steps of each field in declaration order."""
    names = [name for name, _ in g.fields]
    fields = value.fields if isinstance(value, Fields) else ()
    if [name for name, _ in fields] != names:
        msg = f"prop: {canonical(value)} is not a record of {', '.join(names)}"
        raise CannotInvertError(msg)
    steps: list[Step] = []
    normal: list[tuple[str, object]] = []
    for (name, of), (_, field) in zip(g.fields, fields, strict=True):
        field_steps, field_normal = emit(of, field)
        steps.extend(field_steps)
        normal.append((name, field_normal))
    return steps, Fields(tuple(normal))


def _emit_enum(g: EnumShape, value: object) -> Emitted:
    """Return the index of the variant, then the steps of its payload."""
    names = [name for name, _ in g.variants]
    if not isinstance(value, Variant) or value.name not in names:
        msg = f"prop: {canonical(value)} is not a variant of {', '.join(names)}"
        raise CannotInvertError(msg)
    index = names.index(value.name)
    payload = g.variants[index][1]
    head = Step(IntegerBounds(0, len(names) - 1), index)
    if payload is None:
        if value.has_payload:
            msg = f"prop: the variant {value.name} does not have a payload"
            raise CannotInvertError(msg)
        return [head], value
    steps, normal = emit(payload, value.payload)
    return [head, *steps], Variant(value.name, normal)


def _emit_int128(g: Int128Shape, value: object) -> Emitted:
    """Return the high half and the low half of a 128-bit integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"prop: {canonical(value)} is not an integer"
        raise CannotInvertError(msg)
    lo, hi = halves(g.lo), halves(g.hi)
    high, low = halves(value)
    first = _step(IntegerBounds(lo[0], hi[0]), high)
    return [first, _step(second_part(high, lo, hi, UINT64_MAX), low)], value


def _emit_instant(g: InstantShape, value: object) -> Emitted:
    """Return the seconds of an instant, then its units within the second."""
    seconds, units = _two_parts(value, ("seconds", "units"))
    first = _step(IntegerBounds(g.lo[0], g.hi[0]), seconds)
    if g.per == 1:
        if not isinstance(units, int) or isinstance(units, bool) or units != 0:
            msg = f"prop: an instant at seconds has 0 units, not {canonical(units)}"
            raise CannotInvertError(msg)
        return [first], value
    bounds = second_part(cast("int", seconds), g.lo, g.hi, g.per - 1)
    return [first, _step(bounds, units)], value


def _emit_local(g: LocalDateTimeShape, value: object) -> Emitted:
    """Return the date of a local date and time, then its time of day."""
    day, time = _two_parts(value, ("date", "time-of-day"))
    first = _step(IntegerBounds(g.lo[0], g.hi[0]), day)
    bounds = second_part(cast("int", day), g.lo, g.hi, 86_400 * g.per - 1)
    return [first, _step(bounds, time)], value


def _emit_zoned(g: ZonedShape, value: object) -> Emitted:
    """Return the zone, the whole-range choice, then the instant."""
    steps, instant = _zone_steps(value, "instant")
    return [*steps, *emit(g.instant, instant)[0]], value


def _emit_wall(g: WallShape, value: object) -> Emitted:
    """Return the zone, the whole-range choice, then the local date and time."""
    steps, local = _zone_steps(value, "local-date-time")
    return [*steps, *emit(g.local, local)[0]], value


def _emit_ip(g: IpShape, value: object) -> Emitted:
    """Return the index of the version of an address, then its bytes."""
    if not isinstance(value, bytes):
        msg = f"prop: {canonical(value)} is not an address"
        raise CannotInvertError(msg)
    for index, version in enumerate(g.versions):
        if version.bounds.min_size == len(value):
            steps, _ = emit(version, value)
            return [Step(_BIT, index), *steps], value
    msg = f"prop: {canonical(value)} is neither 4 nor 16 bytes"
    raise CannotInvertError(msg)


#: The emitter of each class of generator.
_EMITTERS: dict[type[Any], Callable[[Any, object], Emitted]] = {
    Integer: _emit_integer,
    Float: _emit_float,
    Bool: _emit_bool,
    Just: _emit_just,
    SampledFrom: _emit_sampled,
    OneOf: _emit_one_of,
    Optional: _emit_optional,
    OptionalShape: _emit_optional,
    List: _emit_list,
    ListShape: _emit_list_shape,
    Dict: _emit_dict,
    MapShape: _emit_map_shape,
    Text: _emit_text,
    Bytes: _emit_bytes,
    Matching: _emit_matching,
    Permutation: _emit_permutation,
    Filter: _emit_filter,
    Mapped: _emit_mapped,
    Recursive: _emit_recursive,
    Position: _emit_position,
    Root: _emit_root,
    Ref: _emit_ref,
    RecordShape: _emit_record,
    EnumShape: _emit_enum,
    Int128Shape: _emit_int128,
    InstantShape: _emit_instant,
    LocalDateTimeShape: _emit_local,
    ZonedShape: _emit_zoned,
    WallShape: _emit_wall,
    IpShape: _emit_ip,
}


def emit(generator: Generator[Any], value: object) -> Emitted:
    """Return the steps that one generator emits for a value within their bounds.

    Args:
        generator: The generator.
        value: The value.

    Returns:
        The steps, and the value that they decode to.

    Raises:
        CannotInvertError: A step falls outside its bounds, or the value is of a
            type that the generator never decodes.
        NoInverseError: The generator applies a function that the engine
            cannot run backwards.
    """
    if isinstance(generator, Deferred):
        deferred: Deferred[Any] = generator
        with deferred.picked() as picked:
            return emit(picked, value)
    emitter = _EMITTERS.get(type(generator))
    if emitter is None:
        msg = f"prop: a {type(generator).__name__} does not run backwards"
        raise NoInverseError(msg)
    return emitter(generator, value)
