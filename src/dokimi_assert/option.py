"""The relaxations that a caller applies to one comparison.

An option applies to the call that it is passed to, and to no other call.
No setting applies to a whole run, because a rule that one place changes
and another place reads makes two tests mean different things by one
assertion.

    check.equal(seat, got, want, "the reply has no items", equate_empty())

Both surfaces take the same options, and every assertion that compares
values accepts them last.
"""

from __future__ import annotations

from dokimi_assert._matcher.option import Option, by_identity, equate_empty, equate_nans

__all__ = ["Option", "by_identity", "equate_empty", "equate_nans"]
