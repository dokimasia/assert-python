# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/zone.py tests the zones and their offset changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dokimi_assert import check
from dokimi_assert._prop.engine.zone import ZONES, Change

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestZones:
    """ZONES is the zone list in the order of the definition."""

    def test_lists_the_sixteen_zones_of_the_definition_with_utc_first(
        self, seat: Collector
    ) -> None:
        """A zone shrinks to UTC."""
        check.equal(
            seat,
            [zone.name for zone in ZONES],
            [
                "UTC",
                "Europe/Amsterdam",
                "America/New_York",
                "Australia/Sydney",
                "Australia/Lord_Howe",
                "Pacific/Chatham",
                "Asia/Kolkata",
                "Asia/Kathmandu",
                "America/St_Johns",
                "Asia/Tehran",
                "America/Sao_Paulo",
                "Pacific/Kiritimati",
                "Pacific/Apia",
                "Europe/Dublin",
                "Africa/Casablanca",
                "Antarctica/Troll",
            ],
            "ZONES has the sixteen zones with UTC first",
        )

    def test_does_not_list_a_change_of_utc(self, seat: Collector) -> None:
        """UTC has one offset."""
        check.is_empty(seat, ZONES[0].changes, "UTC does not have an offset change")

    def test_reads_each_change_as_int_seconds(self, seat: Collector) -> None:
        """The change is the first change of Europe/Amsterdam."""
        check.equal(
            seat,
            ZONES[1].changes[0],
            Change(-1_740_355_200, 0, 3600),
            "the change has int seconds",
        )

    def test_lists_the_changes_of_each_zone_in_time_order_with_matching_offsets(
        self, seat: Collector
    ) -> None:
        """Each change starts from the offset that the change before it ends at."""
        broken = [
            zone.name
            for zone in ZONES
            for change, after in zip(zone.changes, zone.changes[1:], strict=False)
            if after.at <= change.at or after.before != change.after
        ]
        check.is_empty(seat, broken, "every zone has its changes in order")
