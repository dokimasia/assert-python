"""Comparison against a recorded file.

Written with the library, as a consumer would. The assertion core
cannot do the same: a package that tests itself with itself lets one
bug hide another.
"""

from __future__ import annotations

import json
from pathlib import Path

from dokimi import check, golden
from dokimi.seat import Recorder, Standard

#: The seat this file's own assertions report through. Standard raises,
#: so a failure here fails the test; the Recorder each case drives the
#: subject with only records, which is what lets a case read what the
#: subject reported without suffering it.
OUTER = Standard()

#: Whether a run may rewrite its golden files. Named rather than
#: repeated, because a case passing the wrong one silently tests the
#: other path.
UPDATING = True
CHECKING = False


def _written(tmp_path: Path, content: str, name: str = "golden.txt") -> Path:
    """Put content in a golden file and answer its path."""
    path = tmp_path / name
    path.write_text(content)
    return path


def test_matching_content_reports_nothing(tmp_path: Path) -> None:
    """Content equal to the golden file passes."""
    path = _written(tmp_path, "recorded output")
    seat = Recorder()

    golden.match_at(seat, path, "recorded output", CHECKING)
    check.is_false(OUTER, seat.failed, "matching content passes")


def test_differing_content_reports_the_file_then_the_diff(tmp_path: Path) -> None:
    """A mismatch names the file, then shows what differed."""
    path = _written(tmp_path, "recorded output")
    seat = Recorder()

    golden.match_at(seat, path, "something else", CHECKING)

    check.is_true(OUTER, seat.failed, "differing content fails")
    check.contains_in_order(
        OUTER, seat.message, [str(path), "want"], "the failure names the file first"
    )


def test_a_missing_file_names_what_would_create_it(tmp_path: Path) -> None:
    """A golden file that does not exist says how to make one."""
    seat = Recorder()
    golden.match_at(seat, tmp_path / "absent.txt", "anything", CHECKING)

    check.is_true(OUTER, seat.failed, "a missing golden file fails")
    check.contains(
        OUTER, seat.message, golden.UPDATE_ENV, "the failure names the variable"
    )


def test_updating_writes_a_missing_file(tmp_path: Path) -> None:
    """Updating creates the file and passes."""
    path = tmp_path / "created.txt"
    seat = Recorder()

    golden.match_at(seat, path, "fresh output", UPDATING)

    check.is_false(OUTER, seat.failed, "updating a missing file passes")
    check.equal(OUTER, path.read_text(), "fresh output", "the file holds the output")


def test_updating_creates_the_directory(tmp_path: Path) -> None:
    """Updating into a directory that is not there creates it."""
    seat = Recorder()
    golden.match_at(seat, tmp_path / "a" / "b" / "c.txt", "fresh", UPDATING)
    check.is_false(OUTER, seat.failed, "the subject reported nothing")


def test_updating_overwrites_stale_content(tmp_path: Path) -> None:
    """Updating replaces content that no longer matches."""
    path = _written(tmp_path, "stale")
    seat = Recorder()

    golden.match_at(seat, path, "current", UPDATING)

    check.is_false(OUTER, seat.failed, "updating over stale content passes")
    check.equal(OUTER, path.read_text(), "current", "the file holds the new output")


def test_a_scrubber_applies_to_both_sides(tmp_path: Path) -> None:
    """Content differing only where scrubbed still matches."""
    path = _written(tmp_path, "at 2026-01-01T00:00:00Z exactly")
    seat = Recorder()

    golden.match_at(
        seat,
        path,
        "at 2026-08-30T12:00:00Z exactly",
        CHECKING,
        golden.scrub_timestamps(),
    )
    check.is_false(OUTER, seat.failed, "the subject reported nothing")


def test_a_scrubber_does_not_hide_a_real_difference(tmp_path: Path) -> None:
    """Content differing outside the scrubbed part still fails."""
    path = _written(tmp_path, "at 2026-01-01T00:00:00Z exactly")
    seat = Recorder()

    golden.match_at(
        seat,
        path,
        "at 2026-08-30T12:00:00Z roughly",
        CHECKING,
        golden.scrub_timestamps(),
    )
    check.is_true(OUTER, seat.failed, "the subject reported")


def test_match_resolves_against_the_conventional_directory() -> None:
    """A bare name resolves under testdata/golden."""
    seat = Recorder()
    golden.match(seat, "resolved.txt", "output", CHECKING)

    check.contains(
        OUTER,
        seat.message,
        str(golden.CONVENTIONAL_DIR),
        "the name resolves under the conventional directory",
    )


def test_a_matching_json_field_reports_nothing(tmp_path: Path) -> None:
    """A field equal to the golden file's passes."""
    path = _written(tmp_path, '{"one": [1, 2], "two": ["a"]}', "g.json")
    seat = Recorder()

    golden.match_json_field(seat, path, "one", "[1, 2]", CHECKING)
    check.is_false(OUTER, seat.failed, "the subject reported nothing")


def test_json_formatting_differences_do_not_fail(tmp_path: Path) -> None:
    """Both sides are re-encoded, so whitespace does not fail."""
    path = _written(tmp_path, '{"one":[1,2]}', "g.json")
    seat = Recorder()

    golden.match_json_field(seat, path, "one", "[ 1,\n  2 ]", CHECKING)
    check.is_false(OUTER, seat.failed, "the subject reported nothing")


def test_a_differing_json_field_names_the_field(tmp_path: Path) -> None:
    """A mismatch says which field it was."""
    path = _written(tmp_path, '{"one":[1,2]}', "g.json")
    seat = Recorder()

    golden.match_json_field(seat, path, "one", "[3]", CHECKING)

    check.is_true(OUTER, seat.failed, "a differing field fails")
    check.contains(OUTER, seat.message, "'one'", "the failure names the field")


def test_updating_a_field_keeps_its_siblings(tmp_path: Path) -> None:
    """Writing one field leaves the others alone."""
    path = _written(tmp_path, '{"kept":[9]}', "g.json")
    seat = Recorder()

    golden.match_json_field(seat, path, "added", "[1]", UPDATING)

    document = json.loads(path.read_text())
    check.is_false(OUTER, seat.failed, "updating a missing field passes")
    check.contains(OUTER, document, "kept", "the sibling survives")
    check.contains(OUTER, document, "added", "the field was added")


def test_a_value_that_is_not_json_reports(tmp_path: Path) -> None:
    """A value the field cannot hold is refused."""
    path = _written(tmp_path, '{"one":[1]}', "g.json")
    seat = Recorder()

    golden.match_json_field(seat, path, "one", "not json", CHECKING)
    check.is_true(OUTER, seat.failed, "the subject reported")


def test_a_golden_file_that_is_not_an_object_reports(tmp_path: Path) -> None:
    """A field cannot be read out of a JSON array."""
    path = _written(tmp_path, "[1,2,3]", "g.json")
    seat = Recorder()

    golden.match_json_field(seat, path, "one", "[1]", CHECKING)
    check.is_true(OUTER, seat.failed, "the subject reported")


def test_should_update_is_false_without_the_variable() -> None:
    """A run that did not ask to update does not update."""
    assert not golden.should_update()
