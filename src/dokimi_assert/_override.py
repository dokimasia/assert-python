# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The decorator that marks a method that overrides a method of a base class.

typing.override exists from Python 3.12 on, and the library supports Python
3.11 without a dependency. A type checker reads the decorator of
typing_extensions, which its own stubs contain. At run time, the decorator
returns the method unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

__all__ = ["override"]

_F = TypeVar("_F")

if TYPE_CHECKING:
    from typing_extensions import override
else:

    def override(method: _F) -> _F:
        """Return method unchanged.

        Args:
            method: The method that overrides a method of a base class.

        Returns:
            The method.
        """
        return method
