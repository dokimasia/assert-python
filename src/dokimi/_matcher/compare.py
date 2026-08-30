"""Structural comparison, and the rules the standard states for it.

Python's own ``==`` does not answer what the standard asks. ``bool``
subclasses ``int``, so ``0 == False`` is true; ``int`` and ``float``
compare across types, so ``1 == 1.0`` is true. The standard says values
of different types never compare, so this enforces it rather than
inheriting it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence, Set
from typing import Any

from dokimi._matcher.option import Option

# Types whose members are compared element by element rather than with
# ``==``, so a nested difference is found rather than delegated.
_SEQUENCE = (list, tuple)


def equal(got: Any, want: Any, relax: Option) -> bool:
    """Report whether got and want are equal under the standard.

    Types must match exactly. ``type(x) is type(y)``, not
    ``isinstance``: a bool is not an int here, and an int is not a
    float, because the standard says values of different types never
    compare and Python's own answer disagrees.
    """
    if _absent_against_empty(got, want, relax):
        return True

    if type(got) is not type(want):
        return False

    if isinstance(got, float):
        return _floats_equal(got, want, relax)

    if isinstance(got, Mapping):
        return _mappings_equal(got, want, relax)

    if isinstance(got, _SEQUENCE):
        return _sequences_equal(got, want, relax)

    if isinstance(got, (Set, frozenset)):
        return bool(got == want)

    # A custom __eq__ may return anything, so its answer is narrowed to
    # a bool rather than passed along as whatever it gave.
    return bool(got == want)


def _absent_against_empty(got: Any, want: Any, relax: Option) -> bool:
    """Report whether one side is absent and the other empty, relaxed.

    Only reached when the caller asked for it. The default keeps None
    apart from an empty collection.
    """
    if not relax.equate_empty:
        return False

    pair = (got, want)
    if None not in pair:
        return False

    other = want if got is None else got
    return isinstance(other, (Mapping, Sequence, Set)) and len(other) == 0


def _floats_equal(got: float, want: float, relax: Option) -> bool:
    """Compare two floats exactly, NaN aside.

    Exactly, because a tolerance belongs to close_to and applying one
    here would hide the differences close_to exists to tolerate.
    """
    if math.isnan(got) and math.isnan(want):
        return relax.equate_nans
    return got == want


def _mappings_equal(
    got: Mapping[Any, Any], want: Mapping[Any, Any], relax: Option
) -> bool:
    """Compare two mappings key by key, under the same rules."""
    if len(got) != len(want):
        return False
    if set(got) != set(want):
        return False
    return all(equal(got[k], want[k], relax) for k in got)


def _sequences_equal(got: Sequence[Any], want: Sequence[Any], relax: Option) -> bool:
    """Compare two sequences element by element, under the same rules."""
    if len(got) != len(want):
        return False
    return all(equal(a, b, relax) for a, b in zip(got, want, strict=True))
