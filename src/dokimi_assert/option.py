"""Relaxations a caller applies to one comparison.

An option applies to the call it is passed to and to nothing else.
There is no global setting, because a comparison rule changed in one
place and read in another is how two tests come to mean different
things by the same assertion.

    check.equal(seat, got, want, "the reply carries no items", equate_empty())

Both surfaces take the same options, and every assertion that compares
values accepts them last.
"""

from __future__ import annotations

from dokimi_assert._matcher.option import Option, equate_empty, equate_nans

__all__ = ["Option", "equate_empty", "equate_nans"]
