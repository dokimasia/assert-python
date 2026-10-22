# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The functions of the subject kinds of the definition that take one input.

The map generator of the property vectors and the functions of the forms
vectors take the function of a subject kind. Each function behaves as the
table of subjects of the definition describes its kind. It takes and returns
the values that the engine decodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["FUNCTIONS"]

#: The function of each subject kind of one input, by the kind.
FUNCTIONS: dict[str, Callable[[Any], Any]] = {
    "identity": lambda x: x,
    "is-non-negative": lambda x: x >= 0,
    "returns-null": lambda _: None,
    "drops-the-first": lambda x: x[1:],
    "prepends-zero": lambda x: [0, *x],
    "sorts": sorted,
    "wraps-in-a-and-b": lambda x: f"a{x}b",
}
