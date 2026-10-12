"""The spec of _files/platform.py tests the facts that the file systems record."""

from __future__ import annotations

import pytest

from dokimi_assert import check
from dokimi_assert._files.platform import HOST, POSIX, WINDOWS, target_of, written
from dokimi_assert.seat import Collector
from helpers import WINDOWS as ON_WINDOWS


class TestHost:
    """HOST is the platform of this process."""

    @pytest.mark.skipif(ON_WINDOWS, reason="Windows does not record permission bits")
    def test_records_the_nine_permission_bits_off_windows(
        self, seat: Collector
    ) -> None:
        """A tree reads every bit, and a mode can be read."""
        check.is_true(seat, HOST is POSIX, "the platform is POSIX")
        check.equal(
            seat,
            [HOST.recorded_bits, HOST.mode_fault],
            [0o777, None],
            "the platform records nine bits and does not have a mode fault",
        )

    @pytest.mark.skipif(not ON_WINDOWS, reason="the case runs on Windows only")
    def test_does_not_record_permission_bits_on_windows(self, seat: Collector) -> None:
        """A tree does not read a bit, and a mode cannot be read."""
        check.is_true(seat, HOST is WINDOWS, "the platform is Windows")
        check.equal(
            seat,
            [HOST.recorded_bits, HOST.mode_fault],
            [0, "the file system does not record permission bits"],
            "the platform does not record bits and has a mode fault",
        )


class TestTargetOf:
    """target_of returns the target of a link in the form that a tree uses."""

    def test_returns_a_relative_target_with_slashes_unchanged(
        self, seat: Collector
    ) -> None:
        """Slashes separate the names on every platform."""
        check.equal(
            seat,
            target_of("../shared/a.txt"),
            "../shared/a.txt",
            "target_of returns the target unchanged",
        )

    @pytest.mark.skipif(ON_WINDOWS, reason="a backslash separates names on Windows")
    def test_keeps_a_backslash_in_a_name_off_windows(self, seat: Collector) -> None:
        """A backslash is not a separator off Windows."""
        check.equal(seat, target_of("a\\b"), "a\\b", "target_of keeps the backslash")

    @pytest.mark.skipif(not ON_WINDOWS, reason="the case runs on Windows only")
    def test_returns_the_names_of_a_target_with_slashes_on_windows(
        self, seat: Collector
    ) -> None:
        """A backslash separates names on Windows."""
        check.equal(
            seat,
            target_of("a\\b"),
            "a/b",
            "target_of replaces the backslash with a slash",
        )

    @pytest.mark.skipif(not ON_WINDOWS, reason="the case runs on Windows only")
    def test_drops_the_prefix_of_an_absolute_target_on_windows(
        self, seat: Collector
    ) -> None:
        """Windows returns an absolute target after a prefix."""
        check.equal(
            seat, target_of("\\\\?\\C:\\a"), "C:/a", "target_of drops the prefix"
        )


class TestWritten:
    """written returns the target of a link in the form that the file system stores."""

    @pytest.mark.skipif(ON_WINDOWS, reason="a backslash separates names on Windows")
    def test_returns_the_target_unchanged_off_windows(self, seat: Collector) -> None:
        """A slash is the separator off Windows."""
        check.equal(seat, written("a/b"), "a/b", "written returns the target unchanged")

    @pytest.mark.skipif(not ON_WINDOWS, reason="the case runs on Windows only")
    def test_returns_the_target_with_backslashes_on_windows(
        self, seat: Collector
    ) -> None:
        """Windows resolves a target with backslashes."""
        check.equal(
            seat,
            written("a/b"),
            "a\\b",
            "written replaces the slash with a backslash",
        )
