"""The spec of golden.py tests the comparison of output with golden files and trees."""

from __future__ import annotations

import errno
import json
import os
import pathlib
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest

from dokimi_assert import check, files, golden
from dokimi_assert.seat import Collector, Recorder
from helpers import UNENFORCED, WINDOWS, records

#: The argument update of a call that can rewrite its golden file.
UPDATING = True

#: The argument update of a call that only compares.
CHECKING = False

#: The contract of a comparison with the golden tree api.
API_CONTRACT = (
    f"the golden tree {os.path.join('testdata', 'golden', 'api')} matches the "
    f"output, and {golden.UPDATE_ENV}=1 writes it"
)


def written(dir: pathlib.Path, content: str, name: str = "golden.txt") -> str:
    """Write content into the golden file name in dir, and return its path."""
    path = dir / name
    path.write_text(content)
    return str(path)


def reported(recorder: Recorder) -> list[tuple[str, str, dict[str, Any]]]:
    """Return the assertion, the contract and the detail of each failure."""
    return [(f.assertion, f.contract, dict(f.detail)) for f in recorder.failures]


def verdicts(recorder: Recorder) -> list[Any]:
    """Return the verdict of each call record of recorder."""
    return [r["verdict"] for r in records(recorder)]


@pytest.fixture
def locked(tmp_path: pathlib.Path) -> Iterator[pathlib.Path]:
    """Return a directory that its owner cannot write until the test ends."""
    dir = tmp_path / "locked"
    dir.mkdir()
    dir.chmod(0o500)
    yield dir
    dir.chmod(0o755)


@pytest.fixture
def project(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Make a new directory the working directory until the test ends."""
    dir = tmp_path / "project"
    dir.mkdir()
    monkeypatch.chdir(dir)
    return dir


def golden_api(seat: Collector, project: pathlib.Path, tree: files.Tree) -> None:
    """Write tree as the golden tree api of project."""
    below = {f"testdata/golden/api/{path}": e for path, e in tree.items()}
    files.write(seat, project, below)


class TestUpdateEnv:
    """UPDATE_ENV is the variable that lets a run rewrite its golden files."""

    def test_is_dokimi_assert_update_golden(self, seat: Collector) -> None:
        """Every implementation uses this name."""
        check.equal(
            seat,
            golden.UPDATE_ENV,
            "DOKIMI_ASSERT_UPDATE_GOLDEN",
            "UPDATE_ENV is DOKIMI_ASSERT_UPDATE_GOLDEN",
        )


class TestGoldenDir:
    """GOLDEN_DIR is the directory in which a name resolves."""

    def test_is_testdata_golden(self, seat: Collector) -> None:
        """The directory is relative to the working directory."""
        want = os.path.join("testdata", "golden")
        check.equal(seat, golden.GOLDEN_DIR, want, "GOLDEN_DIR is testdata/golden")


class TestShouldUpdate:
    """should_update reports whether the run can rewrite its golden files."""

    tests: ClassVar[list[tuple[str, str | None, bool]]] = [
        ("returns false for an unset variable", None, False),
        ("returns false for an empty variable", "", False),
        ("returns false for 0", "0", False),
        ("returns true for 1", "1", True),
        ("returns true for any other value", "yes", True),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict_of_the_variable(
        self,
        seat: Collector,
        monkeypatch: pytest.MonkeyPatch,
        give: str | None,
        want: bool,
    ) -> None:
        """The value of the variable enables an update."""
        if give is None:
            monkeypatch.delenv(golden.UPDATE_ENV, raising=False)
        else:
            monkeypatch.setenv(golden.UPDATE_ENV, give)
        check.equal(
            seat, golden.should_update(), want, "should_update returns the verdict"
        )


class TestScrubTimestamps:
    """scrub_timestamps returns the scrubber of timestamps."""

    def test_replaces_an_iso_8601_timestamp_with_scrubbed_timestamp(
        self, seat: Collector
    ) -> None:
        """The text around the timestamp is kept."""
        got = golden.scrub_timestamps()("started at 2026-08-30T11:22:33Z")
        check.equal(
            seat,
            got,
            "started at SCRUBBED_TIMESTAMP",
            "the scrubber replaces the timestamp",
        )


class TestScrubHashes:
    """scrub_hashes returns the scrubber of hex digests."""

    def test_replaces_a_hex_digest_with_scrubbed_hash(self, seat: Collector) -> None:
        """The text around the digest is kept."""
        got = golden.scrub_hashes()(f"digest {'a1b2c3d4' * 8}")
        check.equal(
            seat, got, "digest SCRUBBED_HASH", "the scrubber replaces the digest"
        )


class TestScrubRunIds:
    """scrub_run_ids returns the scrubber of the identifiers of runs."""

    def test_replaces_an_identifier_of_a_run_with_scrubbed_run_id(
        self, seat: Collector
    ) -> None:
        """The text around the identifier is kept."""
        got = golden.scrub_run_ids()("run run_0123456789abcdef finished")
        check.equal(
            seat,
            got,
            "run SCRUBBED_RUN_ID finished",
            "the scrubber replaces the identifier",
        )


class TestScrubJsonFields:
    """scrub_json_fields returns the scrubber of the values of JSON fields."""

    def test_replaces_the_value_of_each_given_field(self, seat: Collector) -> None:
        """Another field keeps its value."""
        got = golden.scrub_json_fields("id")('{"id": "01J8XY", "name": "kept"}')
        check.equal(
            seat,
            got,
            '{"id": "SCRUBBED", "name": "kept"}',
            "the scrubber replaces the value of id",
        )

    def test_returns_the_text_unchanged_without_a_field(self, seat: Collector) -> None:
        """A scrubber without fields does not change the text."""
        got = golden.scrub_json_fields()('{"id": "01J8XY"}')
        check.equal(
            seat, got, '{"id": "01J8XY"}', "the scrubber returns the text unchanged"
        )


class TestMatchAt:
    """match_at compares the output with the golden file at a path."""

    def test_passes_content_that_matches_the_golden_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The call record has the verdict pass."""
        recorder = Recorder()
        path = written(tmp_path, "recorded output")
        golden.match_at(recorder, path, "recorded output", CHECKING)
        check.equal(seat, verdicts(recorder), ["pass"], "the comparison passes")

    def test_reports_the_content_of_the_file_as_want_with_the_output_as_got(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The failure has both sides."""
        path = written(tmp_path, "recorded output")
        recorder = Recorder()
        golden.match_at(recorder, path, "something else", CHECKING)
        check.equal(
            seat,
            reported(recorder),
            [
                (
                    "golden-match-at",
                    f"the golden file {path} matches the output, and "
                    f"{golden.UPDATE_ENV}=1 writes it",
                    {"want": "recorded output", "got": "something else"},
                )
            ],
            "the failure has the content and the output",
        )

    def test_reports_want_none_for_a_missing_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing file does not have content."""
        recorder = Recorder()
        golden.match_at(recorder, tmp_path / "golden.txt", "content", CHECKING)
        check.equal(
            seat,
            dict(recorder.failures[0].detail),
            {"want": None, "got": "content"},
            "want is None",
        )

    def test_compares_the_two_sides_after_its_scrubbers(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The scrubbed sides match."""
        recorder = Recorder()
        golden.match_at(
            recorder,
            written(tmp_path, "started at SCRUBBED_TIMESTAMP"),
            "started at 2026-08-30T11:22:33Z",
            CHECKING,
            golden.scrub_timestamps(),
        )
        check.is_false(seat, recorder.failed, "the scrubbed sides match")

    def test_reads_the_line_ends_of_the_file_unchanged(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file of CRLF lines differs from output of LF lines."""
        path = tmp_path / "golden.txt"
        path.write_bytes(b"a\r\n")
        recorder = Recorder()
        golden.match_at(recorder, path, "a\n", CHECKING)
        check.equal(
            seat,
            recorder.failures[0].detail["want"],
            "a\r\n",
            "want keeps the CRLF line end",
        )

    def test_writes_the_output_into_a_missing_file_when_updating(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The update creates the directory of the file."""
        path = tmp_path / "new" / "golden.txt"
        golden.match_at(Recorder(), path, "recorded output", UPDATING)
        check.equal(
            seat, path.read_text(), "recorded output", "the update writes the file"
        )

    def test_writes_the_line_ends_of_the_output_unchanged(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The write does not translate a line end of the output on any platform."""
        path = tmp_path / "golden.txt"
        golden.match_at(Recorder(), path, "a\r\nb\n", UPDATING)
        check.equal(
            seat, path.read_bytes(), b"a\r\nb\n", "the file keeps the line ends"
        )

    def test_writes_a_file_of_the_working_directory_when_updating(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """A path without a directory is a file of the working directory."""
        golden.match_at(Recorder(), "golden.txt", "output", UPDATING)
        check.equal(
            seat,
            (project / "golden.txt").read_text(),
            "output",
            "the update writes the file",
        )

    def test_passes_when_it_writes_the_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """An update passes."""
        recorder = Recorder()
        golden.match_at(recorder, tmp_path / "golden.txt", "output", UPDATING)
        check.equal(seat, verdicts(recorder), ["pass"], "an update passes")

    def test_rewrites_content_that_differs_when_updating(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The file has the new output."""
        path = written(tmp_path, "old output")
        golden.match_at(Recorder(), path, "new output", UPDATING)
        check.equal(
            seat,
            pathlib.Path(path).read_text(),
            "new output",
            "the file has the new output",
        )

    def test_ends_the_call_with_a_fault_for_a_file_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A directory is not a golden file."""
        path = tmp_path / "golden.txt"
        path.mkdir()
        recorder = Recorder()
        golden.match_at(recorder, path, "content", CHECKING)
        check.equal(seat, recorder.failures, [], "a fault does not report a failure")
        check.contains(
            seat,
            recorder.message,
            "the golden file cannot be read",
            "the fault has the reason",
        )
        check.equal(
            seat, verdicts(recorder), ["error"], "the call record has the verdict error"
        )

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_ends_the_call_with_a_fault_for_a_file_that_cannot_be_written(
        self, seat: Collector, locked: pathlib.Path
    ) -> None:
        """A directory without the write bit does not take a golden file."""
        recorder = Recorder()
        golden.match_at(recorder, locked / "golden.txt", "content", UPDATING)
        check.contains(
            seat,
            recorder.message,
            "the golden file cannot be written",
            "the fault has the reason",
        )


class TestMatch:
    """match compares the output with the golden file of a name."""

    @pytest.mark.usefixtures("project")
    def test_resolves_the_name_in_testdata_golden(self, seat: Collector) -> None:
        """The contract has the path of the file in testdata/golden."""
        recorder = Recorder()
        golden.match(recorder, "absent-on-purpose.txt", "content", CHECKING)
        path = os.path.join("testdata", "golden", "absent-on-purpose.txt")
        check.equal(
            seat,
            [(assertion, contract) for assertion, contract, _ in reported(recorder)],
            [
                (
                    "golden-match",
                    f"the golden file {path} matches the output, and "
                    f"{golden.UPDATE_ENV}=1 writes it",
                )
            ],
            "the failure has the contract with the path",
        )


class TestMatchJsonField:
    """match_json_field compares a value with one field of a golden JSON object."""

    def test_passes_a_field_whose_value_matches(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """Another field does not count."""
        recorder = Recorder()
        path = written(tmp_path, '{"items": [1, 2], "other": 1}', "g.json")
        golden.match_json_field(recorder, path, "items", "[1, 2]", CHECKING)
        check.is_false(seat, recorder.failed, "the field matches")

    def test_passes_a_value_that_differs_from_the_field_only_in_its_format(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """Both sides are written again with sorted keys first."""
        recorder = Recorder()
        path = written(tmp_path, '{"one":{"b":1,"a":[1,2]}}', "g.json")
        golden.match_json_field(
            recorder, path, "one", '{"a": [ 1,\n  2 ], "b": 1}', CHECKING
        )
        check.is_false(seat, recorder.failed, "the format does not count")

    def test_reports_both_sides_for_a_field_that_differs(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The failure has the field."""
        path = written(tmp_path, '{"items": [1]}', "g.json")
        recorder = Recorder()
        golden.match_json_field(recorder, path, "items", "[1, 2]", CHECKING)
        check.equal(
            seat,
            reported(recorder),
            [
                (
                    "golden-match-json-field",
                    f'the field "items" of the golden file {path} matches the value, '
                    f"and {golden.UPDATE_ENV}=1 writes it",
                    {"want": "[\n  1\n]", "got": "[\n  1,\n  2\n]", "field": "items"},
                )
            ],
            "the failure has both sides and the field",
        )

    def test_reports_want_none_for_a_missing_field(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing field does not have a value."""
        recorder = Recorder()
        path = written(tmp_path, '{"other": 1}', "g.json")
        golden.match_json_field(recorder, path, "absent", "[1]", CHECKING)
        check.equal(
            seat,
            dict(recorder.failures[0].detail),
            {"want": None, "got": "[\n  1\n]", "field": "absent"},
            "want is None",
        )

    def test_reports_want_none_for_a_missing_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing file does not have a field."""
        recorder = Recorder()
        golden.match_json_field(recorder, tmp_path / "g.json", "items", "[1]", CHECKING)
        check.equal(
            seat,
            dict(recorder.failures[0].detail),
            {"want": None, "got": "[\n  1\n]", "field": "items"},
            "want is None",
        )

    def test_writes_a_missing_field_beside_the_other_fields_when_updating(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """Every other field keeps its value."""
        path = written(tmp_path, '{"other": 1}', "g.json")
        golden.match_json_field(Recorder(), path, "added", "[1, 2]", UPDATING)
        document = json.loads(pathlib.Path(path).read_text())
        check.equal(
            seat, document, {"other": 1, "added": [1, 2]}, "the file has both fields"
        )

    def test_rewrites_a_field_that_differs_when_updating(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The field has the new value."""
        path = written(tmp_path, '{"items": [1]}', "g.json")
        golden.match_json_field(Recorder(), path, "items", "[1, 2]", UPDATING)
        document = json.loads(pathlib.Path(path).read_text())
        check.equal(seat, document, {"items": [1, 2]}, "the field has the new value")

    def test_creates_a_missing_file_when_updating(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The file has the one field."""
        path = tmp_path / "g.json"
        golden.match_json_field(Recorder(), path, "items", "[1]", UPDATING)
        check.equal(
            seat, json.loads(path.read_text()), {"items": [1]}, "the file has the field"
        )

    def test_ends_the_call_with_a_fault_for_a_file_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A directory is not a golden file."""
        path = tmp_path / "g.json"
        path.mkdir()
        recorder = Recorder()
        golden.match_json_field(recorder, path, "i", "[1]", CHECKING)
        check.contains(
            seat,
            recorder.message,
            "the golden file cannot be read",
            "the fault has the reason",
        )

    def test_ends_the_call_with_a_fault_for_a_file_that_does_not_parse(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The file is not JSON."""
        recorder = Recorder()
        path = written(tmp_path, "{not json", "g.json")
        golden.match_json_field(recorder, path, "i", "[1]", CHECKING)
        want = "the golden file cannot be read as a JSON object"
        check.contains(seat, recorder.message, want, "the fault has the reason")

    def test_ends_the_call_with_a_fault_for_a_file_that_is_not_an_object(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The file is a JSON array."""
        recorder = Recorder()
        path = written(tmp_path, "[1, 2]", "g.json")
        golden.match_json_field(recorder, path, "i", "[1]", CHECKING)
        want = "the golden file cannot be read as a JSON object"
        check.contains(seat, recorder.message, want, "the fault has the reason")

    def test_ends_the_call_with_a_fault_for_a_value_that_is_not_json(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The value does not parse."""
        recorder = Recorder()
        path = written(tmp_path, "{}", "g.json")
        golden.match_json_field(recorder, path, "i", "not json", CHECKING)
        want = 'the value of the field "i" is not JSON'
        check.contains(seat, recorder.message, want, "the fault has the reason")

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_ends_the_call_with_a_fault_for_a_directory_that_cannot_be_written(
        self, seat: Collector, locked: pathlib.Path
    ) -> None:
        """A directory without the write bit does not take a golden file."""
        recorder = Recorder()
        golden.match_json_field(recorder, locked / "g.json", "i", "[1]", UPDATING)
        check.contains(
            seat,
            recorder.message,
            "the golden file cannot be written",
            "the fault has the reason",
        )


class TestMatchTree:
    """match_tree compares the tree of a directory with the golden tree of a name."""

    LOGO: ClassVar[files.Entry] = files.bytes(b"\x89\x50")

    def test_passes_an_output_equal_to_its_golden_tree(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """The call record has the contract and the verdict pass."""
        tree = {"api.go": files.text("package api\n"), "logo.png": self.LOGO}
        golden_api(seat, project, tree)
        out = files.workspace(seat, tree)
        recorder = Recorder()
        golden.match_tree(recorder, "api", out, CHECKING)
        check.equal(
            seat,
            [(r["assertion"], r["contract"], r["verdict"]) for r in records(recorder)],
            [("golden-match-tree", API_CONTRACT, "pass")],
            "the call record has a pass",
        )

    def test_reports_the_entries_at_the_paths_that_differ(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """The failure has the entries and the call site in this spec."""
        want = {"api.go": files.text("package api\n"), "old.go": files.text("old")}
        golden_api(seat, project, want)
        got = {"api.go": files.text("package api\n\nfunc New() {}\n")}
        out = files.workspace(seat, got)
        recorder = Recorder()
        golden.match_tree(recorder, "api", pathlib.Path(out), CHECKING)
        [failure] = recorder.failures
        check.equal(
            seat,
            dict(failure.detail),
            {"want": want, "got": got, "differences": 2},
            "the failure has the entries that differ",
        )
        where = failure.where
        check.equal(
            seat,
            None if where is None else where.file,
            __file__,
            "the call site is in this spec",
        )

    @pytest.mark.usefixtures("project")
    def test_reports_want_none_for_a_missing_golden_tree(self, seat: Collector) -> None:
        """The record lists the output."""
        out = files.workspace(seat, {"v1/types.go": files.text("package v1\n")})
        recorder = Recorder()
        golden.match_tree(recorder, "api", out, CHECKING)
        check.equal(
            seat,
            dict(recorder.failures[0].detail),
            {
                "want": None,
                "got": {
                    "v1": files.directory(),
                    "v1/types.go": files.text("package v1\n"),
                },
                "differences": 2,
            },
            "the record lists the output",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_compares_only_the_execute_bit_of_a_file(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """The other bits of a mode do not count."""
        golden_api(
            seat,
            project,
            {
                "gen.sh": files.text("#!/bin/sh\n").with_mode(0o700),
                "types.go": files.text("package api\n").with_mode(0o644),
            },
        )
        out = files.workspace(
            seat,
            {
                "gen.sh": files.executable("#!/bin/sh\n"),
                "types.go": files.text("package api\n").with_mode(0o600),
            },
        )
        recorder = Recorder()
        golden.match_tree(recorder, "api", out, CHECKING)
        check.is_false(seat, recorder.failed, "the modes have the same execute bits")

    def test_compares_the_scrubbed_text_of_each_file_on_both_sides(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """A timestamp does not count."""
        golden_api(seat, project, {"log.txt": files.text("at SCRUBBED_TIMESTAMP\n")})
        out = files.workspace(
            seat, {"log.txt": files.text("at 2026-10-08T11:22:33Z\n")}
        )
        recorder = Recorder()
        golden.match_tree(recorder, "api", out, CHECKING, golden.scrub_timestamps())
        check.is_false(seat, recorder.failed, "the scrubbed sides are equal")

    def test_writes_a_missing_golden_tree_under_update(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """The golden tree has the entries of the output."""
        out = files.workspace(seat, {"v1/types.go": files.text("package v1\n")})
        golden.match_tree(Recorder(), "api", out, UPDATING)
        files.equal(
            seat,
            project / "testdata" / "golden" / "api",
            {"v1/types.go": files.text("package v1\n")},
            "the golden tree is written",
        )

    @pytest.mark.usefixtures("project")
    def test_passes_when_it_writes_the_golden_tree(self, seat: Collector) -> None:
        """An update passes."""
        out = files.workspace(seat, {"v1/types.go": files.text("package v1\n")})
        recorder = Recorder()
        golden.match_tree(recorder, "api", out, UPDATING)
        check.equal(seat, verdicts(recorder), ["pass"], "an update passes")

    def test_makes_the_golden_tree_equal_to_the_scrubbed_output_under_update(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """The update removes the entries that the output does not have."""
        golden_api(
            seat, project, {"old.go": files.text("old"), "latest": files.link("old.go")}
        )
        out = files.workspace(
            seat, {"log.txt": files.text("at 2026-10-08T11:22:33Z\n")}
        )
        golden.match_tree(Recorder(), "api", out, UPDATING, golden.scrub_timestamps())
        files.equal(
            seat,
            project / "testdata" / "golden" / "api",
            {"log.txt": files.text("at SCRUBBED_TIMESTAMP\n")},
            "the golden tree equals the scrubbed output",
        )

    @pytest.mark.usefixtures("project")
    def test_ends_the_call_with_a_fault_for_a_name_that_is_not_a_path(
        self, seat: Collector
    ) -> None:
        """A name cannot leave the conventional directory."""
        recorder = Recorder()
        golden.match_tree(recorder, "../api", files.workspace(seat, {}), CHECKING)
        check.equal(
            seat,
            [recorder.message, verdicts(recorder)],
            ['golden.match_tree: the path "../api" has the name ".."', ["error"]],
            "the call ends with a fault",
        )

    def test_ends_the_call_with_a_fault_for_an_output_that_cannot_be_read(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """A missing output does not have a tree."""
        recorder = Recorder()
        golden.match_tree(recorder, "api", project / "missing", CHECKING)
        want = f"golden.match_tree: the tree cannot be read: [Errno {errno.ENOENT}]"
        check.has_prefix(
            seat, recorder.message, want, "the fault has the error of the file system"
        )

    def test_ends_the_call_with_a_fault_for_a_golden_tree_that_is_not_a_directory(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """A file is not a golden tree."""
        files.write(seat, project, {"testdata/golden/api": files.text("a file")})
        recorder = Recorder()
        golden.match_tree(recorder, "api", files.workspace(seat, {}), CHECKING)
        check.equal(
            seat,
            recorder.message,
            "golden.match_tree: the root of the tree is not a directory",
            "the fault has the reason",
        )

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_ends_the_call_with_a_fault_for_a_golden_directory_that_cannot_be_created(
        self, seat: Collector, project: pathlib.Path
    ) -> None:
        """A directory without the write bit does not take a golden tree."""
        files.write(
            seat, project, {"testdata/golden": files.directory().with_mode(0o500)}
        )
        recorder = Recorder()
        try:
            golden.match_tree(recorder, "api", files.workspace(seat, {}), UPDATING)
        finally:
            (project / "testdata" / "golden").chmod(0o755)
        want = (
            "golden.match_tree: the directory cannot be created: "
            f"[Errno {errno.EACCES}]"
        )
        check.has_prefix(
            seat, recorder.message, want, "the fault has the error of the file system"
        )
