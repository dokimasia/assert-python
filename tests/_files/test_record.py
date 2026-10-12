"""The spec of _files/record.py tests the record of a failed comparison of trees."""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert._files.entry import Entry, directory, executable, text
from dokimi_assert._files.record import (
    MAX_PATHS,
    Comparison,
    comparison,
    missing,
    report,
)
from dokimi_assert._matcher.verdict import Running
from dokimi_assert.failure import Where
from dokimi_assert.seat import Collector, Recorder
from helpers import records


def numbered(n: int, content: str) -> dict[str, Entry]:
    """Return a tree of n files named f00.txt, f01.txt and so on.

    Each file has the text content.
    """
    return {f"f{i:02d}.txt": text(content) for i in range(n)}


class TestMaxPaths:
    """MAX_PATHS is the most paths that a record lists."""

    def test_is_64(self, seat: Collector) -> None:
        """A record lists at most 64 paths."""
        check.equal(seat, MAX_PATHS, 64, "a record lists at most 64 paths")


class TestComparison:
    """comparison returns the record of a comparison."""

    def test_returns_none_when_no_path_differs(self, seat: Collector) -> None:
        """Two equal trees do not have a record."""
        check.is_none(seat, comparison({}, {}, []), "comparison returns None")

    def test_lists_each_entry_that_differs(self, seat: Collector) -> None:
        """Each entry that differs is in the record.

        A missing entry is in want, an extra entry is in got, and a changed
        entry is in both.
        """
        want = {"a.txt": text("a"), "b.txt": text("b")}
        got = {"a.txt": text("x"), "c.txt": text("c")}
        check.equal(
            seat,
            comparison(want, got, ["a.txt", "b.txt", "c.txt"]),
            Comparison(
                want={"a.txt": text("a"), "b.txt": text("b")},
                got={"a.txt": text("x"), "c.txt": text("c")},
                differences=3,
            ),
            "comparison returns the entries that differ",
        )

    def test_lists_at_most_64_paths(self, seat: Collector) -> None:
        """A record of 65 differences lists 64 paths and counts 65."""
        want = numbered(65, "b")
        record = comparison(want, numbered(65, "a"), list(want))
        assert record is not None and record.want is not None
        check.equal(
            seat,
            [len(record.want), len(record.got), record.differences],
            [64, 64, 65],
            "the record lists 64 paths and counts 65",
        )

    def test_has_the_mode_of_an_entry_read_when_the_wanted_entry_has_one(
        self, seat: Collector
    ) -> None:
        """Otherwise a file has only its execute bit."""
        want = {
            "key": text("a").with_mode(0o600),
            "run.sh": text("b"),
            "docs": directory(),
        }
        got = {
            "key": text("x").with_mode(0o644),
            "run.sh": text("y").with_mode(0o755),
            "docs": directory().with_mode(0o700),
        }
        record = comparison(want, got, ["docs", "key", "run.sh"])
        assert record is not None
        check.equal(
            seat,
            record.got,
            {
                "docs": directory(),
                "key": text("x").with_mode(0o644),
                "run.sh": executable("y"),
            },
            "the record has the entries in the form that the comparison checked",
        )


class TestMissing:
    """missing returns the record of a golden tree that is missing."""

    def test_returns_the_entries_read_without_modes(self, seat: Collector) -> None:
        """The record does not have a wanted tree, and it counts the entries read."""
        got = {
            "a.txt": text("a").with_mode(0o600),
            "run.sh": text("r").with_mode(0o755),
        }
        check.equal(
            seat,
            missing(got),
            Comparison(
                want=None,
                got={"a.txt": text("a"), "run.sh": executable("r")},
                differences=2,
            ),
            "missing returns the entries without modes",
        )

    def test_lists_at_most_64_entries(self, seat: Collector) -> None:
        """The record of a tree of 65 entries lists 64 and counts 65."""
        record = missing(numbered(65, "a"))
        check.equal(
            seat,
            [len(record.got), record.differences],
            [64, 65],
            "the record lists 64 entries and counts 65",
        )


class TestReport:
    """report reports the verdict of a comparison of trees."""

    def test_reports_a_pass_without_a_record(self, seat: Collector) -> None:
        """A comparison without a record passes."""
        recorder = Recorder()
        report(Running.of(recorder), "tree-equal", "the trees are equal", None, None)
        check.equal(
            seat,
            [recorder.failures, [r["verdict"] for r in records(recorder)]],
            [[], ["pass"]],
            "the call passes",
        )

    def test_reports_the_trees_of_the_failure_as_tree_literals(
        self, seat: Collector
    ) -> None:
        """The detail of the failure has trees, and the call record has literals."""
        recorder = Recorder()
        where = Where("test.py", 3)
        record = Comparison(want={"a.txt": text("a")}, got={}, differences=1)
        report(Running.of(recorder), "tree-equal", "the trees are equal", record, where)
        [failure] = recorder.failures
        check.equal(
            seat,
            [failure.assertion, dict(failure.detail), failure.where],
            [
                "tree-equal",
                {"want": {"a.txt": text("a")}, "got": {}, "differences": 1},
                where,
            ],
            "the failure has the trees",
        )
        check.equal(
            seat,
            records(recorder)[0]["detail"],
            {
                "want": {"type": "tree", "entries": [{"path": "a.txt", "text": "a"}]},
                "got": {"type": "tree", "entries": []},
                "differences": {"type": "int", "value": 1},
            },
            "the call record has the tree literals",
        )

    def test_reports_want_none_for_a_record_without_a_wanted_tree(
        self, seat: Collector
    ) -> None:
        """A missing golden tree has None as want."""
        recorder = Recorder()
        report(
            Running.of(recorder),
            "golden-match-tree",
            "the tree matches",
            missing({}),
            None,
        )
        check.equal(
            seat,
            [recorder.failures[0].detail["want"], records(recorder)[0]["detail"]],
            [
                None,
                {
                    "want": {"type": "null"},
                    "got": {"type": "tree", "entries": []},
                    "differences": {"type": "int", "value": 0},
                },
            ],
            "want is None in the failure and null in the call record",
        )
