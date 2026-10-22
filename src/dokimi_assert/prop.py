"""Assertions that pass for every case that a run generates.

for_all runs a body against generated cases. The body takes its inputs from
its Case with generators such as integer, list and string. It asserts on the
case in the same way as a test asserts on its seat. A failing case shrinks to
the smallest case that fails the same way. The failure record has the values
of the case and a replay token.

    def sorted_is_ordered(c: prop.Case) -> None:
        xs = c.draw(prop.list(prop.integer(-100, 100)), "xs")
        check.pairwise(c, sorted(xs), operator.le, "sorted orders the list")

    def test_sorted(seat):
        prop.for_all(seat, "a sorted list is ordered", sorted_is_ordered)

Each property form runs one assertion on every generated input. equal and
round_trip are property forms. A form reads the type of the input from the
annotation of its function. of derives the generator of the type. fuzz
replays the stored cases of a property and returns the target of a fuzzer.
register, register_values and register_variants declare the generators and
the shapes of types, and of and shape_of read them. of_shape returns the
generator of a shape file.

A failing run writes its minimal case to the store of the test under
testdata/prop. Later runs replay it first. around runs each run of the
body inside a wrapper, such as a frozen clock, so that each run gets an
environment of its own.
"""

from __future__ import annotations

from dokimi_assert._prop.case import Case
from dokimi_assert._prop.convert import Variant, WallTime
from dokimi_assert._prop.detail import FOR_ALL, register_sentences
from dokimi_assert._prop.engine.generator import Generator
from dokimi_assert._prop.forall import for_all
from dokimi_assert._prop.forms import (
    FORM_IDS,
    accumulates,
    close_to,
    contains,
    contains_in_order,
    does_not_raise,
    equal,
    error_as,
    error_is,
    error_is_not,
    has_error,
    has_prefix,
    has_suffix,
    honours_cancellation,
    honours_deadline,
    in_range,
    is_associative,
    is_commutative,
    is_deterministic,
    is_empty,
    is_false,
    is_idempotent,
    is_none,
    is_not_empty,
    is_not_none,
    is_not_pure,
    is_permutation,
    is_pure,
    is_true,
    length,
    matches,
    no_error,
    none_handle_safe,
    not_contains,
    not_equal,
    pairwise,
    raises,
    round_trip,
)
from dokimi_assert._prop.fuzz import fuzz
from dokimi_assert._prop.generators import (
    boolean,
    bytes,
    composite,
    dict,
    duration,
    float,
    integer,
    just,
    list,
    one_of,
    optional,
    permutation,
    recursive,
    sampled_from,
    string,
    string_matching,
)
from dokimi_assert._prop.markers import (
    AllowInfinity,
    AllowNan,
    Alphabet,
    Char,
    Pattern,
    Scale,
    Unit,
    Version,
    Width,
)
from dokimi_assert._prop.option import (
    FormOption,
    Option,
    Wrapper,
    around,
    cases,
    draws,
    example,
    examples,
    explain,
    hermetic,
    max_choices,
    replay,
    require,
    seed,
    shrink,
    shrink_time,
    store,
    using,
    workers,
)
from dokimi_assert._prop.registry import (
    of,
    of_shape,
    register,
    register_values,
    register_variants,
    shape_of,
)

__all__ = [
    "AllowInfinity",
    "AllowNan",
    "Alphabet",
    "Case",
    "Char",
    "FormOption",
    "Generator",
    "Option",
    "Pattern",
    "Scale",
    "Unit",
    "Variant",
    "Version",
    "WallTime",
    "Width",
    "Wrapper",
    "accumulates",
    "around",
    "boolean",
    "bytes",
    "cases",
    "close_to",
    "composite",
    "contains",
    "contains_in_order",
    "dict",
    "does_not_raise",
    "draws",
    "duration",
    "equal",
    "error_as",
    "error_is",
    "error_is_not",
    "example",
    "examples",
    "explain",
    "float",
    "for_all",
    "fuzz",
    "has_error",
    "has_prefix",
    "has_suffix",
    "hermetic",
    "honours_cancellation",
    "honours_deadline",
    "in_range",
    "integer",
    "is_associative",
    "is_commutative",
    "is_deterministic",
    "is_empty",
    "is_false",
    "is_idempotent",
    "is_none",
    "is_not_empty",
    "is_not_none",
    "is_not_pure",
    "is_permutation",
    "is_pure",
    "is_true",
    "just",
    "length",
    "list",
    "matches",
    "max_choices",
    "no_error",
    "none_handle_safe",
    "not_contains",
    "not_equal",
    "of",
    "of_shape",
    "one_of",
    "optional",
    "pairwise",
    "permutation",
    "raises",
    "recursive",
    "register",
    "register_values",
    "register_variants",
    "replay",
    "require",
    "round_trip",
    "sampled_from",
    "seed",
    "shape_of",
    "shrink",
    "shrink_time",
    "store",
    "string",
    "string_matching",
    "using",
    "workers",
]

register_sentences([FOR_ALL, *FORM_IDS])
