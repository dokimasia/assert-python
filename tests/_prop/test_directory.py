# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/directory.py tests the store of a property and its files."""

from __future__ import annotations

import pathlib
from typing import Any

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.seat import name_test
from dokimi_assert._prop.directory import (
    Loaded,
    Stored,
    claim,
    load,
    save,
    seeds,
    seeds_of,
    store_of,
)
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.store import Failure, entry, name
from dokimi_assert.seat import Collector, Recorder, Standard, clean_up
from helpers import refusal

#: A stored entry with its file name and its object.
Entry = tuple[str, dict[str, Any]]


def stored(contract: str, value: int, found: str) -> Entry:
    """Return the entry of a contract with the choice of one integer and a date."""
    choices = (Choice("integer", value),)
    failure = Failure(
        contract,
        choices,
        {"assertion": "equal", "contract": contract},
        [{"label": "x"}],
    )
    return name(contract, choices), entry(failure, "7.2.1", found)


def filled(directory: pathlib.Path, *entries: Entry) -> str:
    """Write each entry into a directory, and return the directory."""
    for file, one in entries:
        save(str(directory), file, one)
    return str(directory)


class TestStored:
    """Stored is an entry that a property replays."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """The entry keeps the name, the choices and the counterexample."""
        one = Stored("e.json", (Choice("integer", 1),), [{"label": "x"}])
        check.equal(
            seat,
            [one.name, one.choices, one.counterexample],
            ["e.json", (Choice("integer", 1),), [{"label": "x"}]],
            "the entry keeps its three fields",
        )


class TestLoaded:
    """Loaded has the entries of a store and the files that a property skips."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """The result keeps the entries and the skipped files."""
        loaded = Loaded([], ["later.json"])
        check.equal(
            seat,
            [loaded.entries, loaded.skipped],
            [[], ["later.json"]],
            "the result keeps its two fields",
        )


class TestStoreOf:
    """store_of returns the directory of the store of a property."""

    def test_returns_the_directory_of_the_option(self, seat: Collector) -> None:
        """The directory of the option comes first."""
        check.equal(
            seat,
            store_of(Recorder(), "kept"),
            "kept",
            "store_of returns the directory of the option",
        )

    def test_returns_the_empty_string_that_turns_the_store_off(
        self, seat: Collector
    ) -> None:
        """The empty string turns the store off."""
        named = Recorder()
        name_test(named, ["test_a.py", "test_t"])
        check.equal(seat, store_of(named, ""), "", "store_of returns the empty string")

    def test_returns_the_empty_string_for_a_seat_that_does_not_run_a_named_test(
        self, seat: Collector
    ) -> None:
        """A seat without a named test does not have a store."""
        check.equal(
            seat, store_of(Recorder(), None), "", "store_of returns the empty string"
        )

    def test_returns_the_store_of_the_test_below_testdata_prop_with_escaped_segments(
        self, seat: Collector
    ) -> None:
        """The segments of the path are escaped."""
        named = Recorder()
        name_test(
            named,
            [
                "tests",
                "test_a.py",
                "TestSuite",
                'c:\\d*"<x>|?',
                "50%",
                "ends.",
                "ends ",
                chr(1),
            ],
        )
        check.equal(
            seat,
            store_of(named, None),
            str(
                pathlib.Path(
                    "testdata",
                    "prop",
                    "tests",
                    "test_a.py",
                    "TestSuite",
                    "c%3A%5Cd%2A%22%3Cx%3E%7C%3F",
                    "50%25",
                    "ends%2E",
                    "ends%20",
                    "%01",
                )
            ),
            "store_of returns the escaped path",
        )


class TestSeedsOf:
    """seeds_of returns the directory of the seed files of a fuzz target."""

    def test_returns_the_seed_files_of_the_test_below_testdata_fuzz(
        self, seat: Collector
    ) -> None:
        """The directory is below testdata/fuzz."""
        named = Recorder()
        name_test(named, ["test_a.py", "test_parses"])
        check.equal(
            seat,
            seeds_of(named),
            str(pathlib.Path("testdata", "fuzz", "test_a.py", "test_parses")),
            "seeds_of returns the directory",
        )

    def test_returns_the_empty_string_for_a_seat_that_does_not_run_a_named_test(
        self, seat: Collector
    ) -> None:
        """A seat without a named test does not have seed files."""
        check.equal(seat, seeds_of(Recorder()), "", "seeds_of returns the empty string")


class TestClaim:
    """claim claims the entries of a contract for a property."""

    def test_succeeds_twice_without_a_store(self, seat: Collector) -> None:
        """Both claims succeed."""
        collector = Collector()
        check.is_true(
            seat,
            claim(collector, "", "c") and claim(collector, "", "c"),
            "both claims succeed",
        )

    def test_succeeds_twice_on_a_seat_without_cleanups(self, seat: Collector) -> None:
        """Both claims succeed."""
        standard = Standard()
        check.is_true(
            seat,
            claim(standard, "dir", "c") and claim(standard, "dir", "c"),
            "both claims succeed",
        )

    def test_refuses_a_second_claim_of_one_contract_in_one_store_until_the_test_ends(
        self, seat: Collector
    ) -> None:
        """The cleanup releases the claim."""
        collector = Collector()
        first = claim(collector, "dir", "c")
        second = claim(collector, "dir", "c")
        clean_up(collector)
        third = claim(collector, "dir", "c")
        clean_up(collector)
        check.equal(
            seat,
            [first, second, third],
            [True, False, True],
            "the cleanup releases the claim",
        )

    def test_grants_the_claims_of_two_contracts_in_one_store(
        self, seat: Collector
    ) -> None:
        """Both claims succeed."""
        collector = Collector()
        claims = [claim(collector, "dir", "a"), claim(collector, "dir", "b")]
        clean_up(collector)
        check.equal(seat, claims, [True, True], "both claims succeed")


class TestLoad:
    """load returns the entries of a contract in a store."""

    def test_returns_an_empty_result_for_a_missing_store(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing store does not have entries."""
        check.equal(
            seat,
            load(str(tmp_path / "absent"), "c"),
            Loaded([], []),
            "load returns an empty result",
        )

    def test_returns_the_entries_of_the_contract_from_the_oldest(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The entries of c are in the order of their dates."""
        later = stored("c", 1, "2026-10-08")
        earlier = stored("c", 2, "2026-01-01")
        between = stored("c", 4, "2026-05-05")
        other = stored("d", 3, "2025-01-01")
        directory = filled(tmp_path, later, earlier, between, other)
        check.equal(
            seat,
            [(one.name, one.choices) for one in load(directory, "c").entries],
            [
                (earlier[0], (Choice("integer", 2),)),
                (between[0], (Choice("integer", 4),)),
                (later[0], (Choice("integer", 1),)),
            ],
            "load returns the entries of c by date",
        )

    def test_orders_the_entries_of_one_date_by_their_names(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The entries of one date are in the order of their names."""
        a = stored("c", 1, "2026-10-08")
        b = stored("c", 2, "2026-10-08")
        directory = filled(tmp_path, a, b)
        check.equal(
            seat,
            [one.name for one in load(directory, "c").entries],
            sorted([a[0], b[0]]),
            "load sorts the entries by name",
        )

    def test_returns_an_entry_of_an_earlier_date_first_whatever_its_name(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The entry of the larger name and the earlier date comes first."""
        one = stored("c", 1, "2026-10-08")
        two = stored("c", 2, "2026-10-08")
        smaller, larger = (one, two) if one[0] < two[0] else (two, one)
        earlier = (larger[0], {**larger[1], "found": "2026-01-01"})
        directory = filled(tmp_path, smaller, earlier)
        check.equal(
            seat,
            [loaded.name for loaded in load(directory, "c").entries],
            [larger[0], smaller[0]],
            "the entry of the larger name and the earlier date comes first",
        )

    def test_returns_the_counterexample_of_each_entry(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The entry has the draws of its counterexample."""
        directory = filled(tmp_path, stored("c", 1, "2026-10-08"))
        check.equal(
            seat,
            load(directory, "c").entries[0].counterexample,
            [{"label": "x"}],
            "the entry has the draws",
        )

    def test_skips_an_entry_of_a_later_format(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The file is skipped."""
        (tmp_path / "later.json").write_text('{"store": 2}', encoding="utf-8")
        check.equal(
            seat,
            load(str(tmp_path), "c"),
            Loaded([], ["later.json"]),
            "the file is skipped",
        )

    def test_reads_only_the_files_whose_names_end_in_json(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The call does not read a directory or a text file."""
        (tmp_path / "nested.json").mkdir()
        (tmp_path / "notes.txt").write_text("free text", encoding="utf-8")
        check.equal(
            seat,
            load(str(tmp_path), "c"),
            Loaded([], []),
            "load does not read the other files",
        )

    def test_raises_a_fault_with_each_damaged_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The fault has the names of the damaged files."""
        (tmp_path / "a.json").write_text("{", encoding="utf-8")
        (tmp_path / "b.json").write_bytes(bytes([0xFF, 0xFE]))
        check.equal(
            seat,
            refusal(seat, lambda: load(str(tmp_path), "c"), FaultError),
            f"{tmp_path}: the store has damaged files: a.json, b.json",
            "the fault has the damaged files",
        )

    def test_raises_a_fault_for_a_store_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The fault has the directory."""
        file = tmp_path / "file"
        file.write_text("", encoding="utf-8")
        check.has_prefix(
            seat,
            refusal(seat, lambda: load(str(file), "c"), FaultError),
            f"{file}: the store cannot be read: ",
            "the fault has the directory and the reason",
        )


class TestSave:
    """save writes an entry into a store."""

    def test_writes_the_entry_as_indented_json_that_ends_in_a_newline(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The file is written."""
        directory = tmp_path / "deep" / "store"
        written = save(str(directory), "e.json", {"store": 1})
        check.equal(
            seat,
            [written, (directory / "e.json").read_text(encoding="utf-8")],
            [True, '{\n  "store": 1\n}\n'],
            "the file is written",
        )

    def test_returns_false_without_replacing_the_file_of_an_existing_name(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The first entry is kept."""
        save(str(tmp_path), "e.json", {"store": 1})
        written = save(str(tmp_path), "e.json", {"store": 2})
        check.equal(
            seat,
            [written, (tmp_path / "e.json").read_text(encoding="utf-8")],
            [False, '{\n  "store": 1\n}\n'],
            "the first entry is kept",
        )

    def test_raises_the_error_of_a_file_system_that_cannot_keep_the_entry(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file is in the place of the directory."""
        file = tmp_path / "file"
        file.write_text("", encoding="utf-8")
        refusal(seat, lambda: save(str(file), "e.json", {}), OSError)

    def test_raises_the_error_of_a_name_that_a_file_cannot_have(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A name with a null character is not a file name."""
        refusal(seat, lambda: save(str(tmp_path), "a\x00.json", {}))


class TestSeeds:
    """seeds returns the seed files of a fuzz target."""

    def test_returns_an_empty_list_for_a_missing_directory(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing directory does not have seed files."""
        check.is_empty(
            seat, seeds(str(tmp_path / "absent")), "seeds returns an empty list"
        )

    def test_returns_the_bytes_of_the_files_in_the_order_of_their_names(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The two files are seeds, and the directory is not."""
        (tmp_path / "b").write_bytes(bytes([2]))
        (tmp_path / "a").write_bytes(bytes([1, 1]))
        (tmp_path / "c").mkdir()
        check.equal(
            seat,
            seeds(str(tmp_path)),
            [("a", bytes([1, 1])), ("b", bytes([2]))],
            "seeds returns the two files in order",
        )

    def test_raises_a_fault_for_a_directory_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The fault has the directory."""
        file = tmp_path / "file"
        file.write_text("", encoding="utf-8")
        check.has_prefix(
            seat,
            refusal(seat, lambda: seeds(str(file)), FaultError),
            f"{file}: the seed files cannot be read: ",
            "the fault has the directory and the reason",
        )
