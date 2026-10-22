"""The zone list and the offset changes of its zones from the zone table.

The zone shapes sample the list, and the zoned-date-time and wall-time shapes
generate a value near one of the changes of a zone in one case of four. The
list is in the order of the definition. UTC is first, so a zone shrinks to
UTC.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from dokimi_assert.conformance.definition import spec_dir

__all__ = ["ZONES", "Change", "Zone"]


@dataclass(frozen=True, slots=True)
class Change:
    """One offset change and the offsets before and after it.

    Attributes:
        at: The first second of the change in seconds since
            1970-01-01T00:00:00Z.
        before: The offset before the change in seconds east of UTC.
        after: The offset after the change in seconds east of UTC.
    """

    at: int
    before: int
    after: int


@dataclass(frozen=True, slots=True)
class Zone:
    """A zone of the list and its offset changes in time order.

    Attributes:
        name: The name of the zone in the IANA time-zone database.
        changes: The offset changes of the zone in time order.
    """

    name: str
    changes: tuple[Change, ...]


_TABLE = json.loads((spec_dir() / "spec" / "zones.json").read_text(encoding="utf-8"))

#: The zone list in the order of the definition.
ZONES: tuple[Zone, ...] = tuple(
    Zone(zone["name"], tuple(Change(*change) for change in zone["changes"]))
    for zone in _TABLE["zones"]
)
