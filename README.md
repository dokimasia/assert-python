<!--
  ~ Copyright Dokimasia B.V. 2026
  ~ SPDX-License-Identifier: MIT
-->

# dokimi-assert

Test assertions for Python. A language-neutral standard defines what each
assertion checks and what its failure reports, and this repository runs the
standard's cases against the library.

[![CI](https://github.com/dokimasia/assert-python/actions/workflows/ci.yml/badge.svg)](https://github.com/dokimasia/assert-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dokimi-assert)](https://pypi.org/project/dokimi-assert/)
[![Python](https://img.shields.io/pypi/pyversions/dokimi-assert)](https://pypi.org/project/dokimi-assert/)
[![Licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)

```sh
pip install dokimi-assert
```

The distribution is `dokimi-assert`, and the package is `dokimi_assert`. It
needs Python 3.11 or later and has no runtime dependencies. A property that
draws a zone needs the package `tzdata` on Windows, because Windows has no
time-zone database.

- [Getting started](#getting-started)
- [Two surfaces](#two-surfaces)
- [The assertions](#the-assertions)
- [Equality](#equality)
- [Golden files](#golden-files)
- [Trees of files](#trees-of-files)
- [Properties](#properties)
- [Histories](#histories)
- [Machines](#machines)
- [Testing your own assertions](#testing-your-own-assertions)
- [Call records](#call-records)
- [The standard](#the-standard)
- [Development](#development)

## Getting started

Installing the package registers a pytest plugin, so every test can take
the `seat` fixture as a parameter.

```python
from dokimi_assert import check


def test_trim_removes_the_padding(seat):
    got = "  widget  ".strip()

    check.is_not_empty(seat, got, "the trimmed name is not empty")
    check.equal(seat, got, "widget", "trim removes the padding")
```

Each assertion takes the seat first and the message last. The message is
the contract under test, and the failure starts with it:

```text
AssertionError: trim removes the padding: want 'widget', got 'gadget'
```

The order differs in three places:

- `rejects` and `prop.for_all` take the message before the body.
- An option, such as `equate_empty()`, comes after the message.
- The golden comparisons and the benchmark ceilings take no message.

### Seats

An assertion reports each failure to the seat that the test passes,
instead of calling pytest or raising. What a failure does depends on the
seat:

| Seat | A failure on `check` | A failure on `expect` |
|---|---|---|
| `Collector`, from the `seat` fixture | Raises `AssertionError` | Is collected, and raised when the test body ends |
| `Standard` | Raises | Raises |
| `Recorder`, from the `recorder` fixture | Is kept | Is kept |

- The plugin hands each test a `Collector`. When the test body ends, the
  plugin runs the functions that the test registered with `seat.cleanup`,
  and raises what the collector kept. The failure then belongs to the test
  and not to its teardown.
- Construct a `Standard` outside pytest, where nothing ends a test.
- Use a `Recorder` to read what an assertion reported, through `failed`,
  `message`, `messages`, `failures`, `faults` and `records`.
- The `prop.Case` of a property is a seat too, so every assertion works
  inside a property.

A fault is an input or an environment that a call refuses, such as a
pattern that does not compile. A seat with the method `report_fault`
receives the fault as the exception it is, and a `Recorder` keeps it. A
`Collector` and a `Standard` raise the exception at the call.
`seat.fault(seat, error)` ends the call of a helper of your own in the same
way:

```python
from dokimi_assert.seat import fault


def restart_of(seat, service):
    if service.restart is None:
        fault(seat, ValueError(f"{service.name} cannot restart"))
        return None
    return service.restart
```

## Two surfaces

Both modules have the same 48 assertions under the same names. `check`
stops the test at the first failure. `expect` records the failure and lets
the test continue, so one run reports every failure.

```python
from dokimi_assert import check, expect


def test_reply(seat):
    status, body, items, headers = 200, "[1,2]", [1, 2], {"date": "Wed, 22 Oct 2026"}

    check.equal(seat, status, 200, "the request succeeds")
    expect.has_prefix(seat, body, "{", "the body is JSON")
    expect.length(seat, items, 3, "every item comes back")
    expect.contains(seat, headers, "etag", "the reply is cacheable")
```

The three `expect` calls fail, and the seat raises them together when the
test body ends:

```text
AssertionError: 3 failures:
  1. the body is JSON: got '[1,2]', prefix '{'
  2. every item comes back: want 3, got 2
  3. the reply is cacheable: haystack {'date': 'Wed, 22 Oct 2026'}, needle 'etag'
```

Use `check` when nothing after it makes sense, and `expect` when each line
states an independent property.

## The assertions

`check` and `expect` each have 48 assertions. The `golden` module has 4
comparisons, and a `bench.Contract` has 3 ceilings. The modules `files`,
`prop`, `history` and `stateful` have their own sections, and each section
ends with the reference of its module.

<!-- api-reference:assertions:start -->

Each assertion takes the seat first and the message last.
`check` and `expect` have the same names and the same
signatures. Only what happens on a failure differs.

**Equality.** The comparison is structural and strict about types.

```python
check.equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option)
check.not_equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option)
```

**Truth and absence.** Python has one null value, None.

```python
check.is_true(seat: Seat, condition: object, msg: str)
check.is_false(seat: Seat, condition: object, msg: str)
check.is_none(seat: Seat, got: Any, msg: str)
check.is_not_none(seat: Seat, got: Any, msg: str)
```

**Size.** Each takes anything with a length. None has no length and fails all three.

```python
check.length(seat: Seat, got: Any, want: int, msg: str)
check.is_empty(seat: Seat, got: Any, msg: str)
check.is_not_empty(seat: Seat, got: Any, msg: str)
```

**Containment.** A str contains a substring, a mapping contains a key, and a sequence or a set contains an element by the rules of equal. is_permutation compares two sequences in any order.

```python
check.contains(seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option)
check.not_contains(seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option)
check.contains_in_order(seat: Seat, got: Any, needles: Sequence[str], msg: str)
check.is_permutation(seat: Seat, got: Any, want: Any, msg: str, *options: Option)
```

**Text.** Each takes a str and fails on any other value.

```python
check.has_prefix(seat: Seat, got: Any, prefix: str, msg: str)
check.has_suffix(seat: Seat, got: Any, suffix: str, msg: str)
check.matches(seat: Seat, got: Any, pattern: str, msg: str)
```

**Numbers.** Exact equality is the wrong check for a float.

```python
check.close_to(seat: Seat, got: Any, want: float, tolerance: float, msg: str)
check.in_range(seat: Seat, got: Any, low: float, high: float, msg: str)
```

**Ordering.** pairwise covers sorted, unique and strictly increasing, because each of those is a relation between neighbours.

```python
check.pairwise(seat: Seat, items: Sequence[Any], predicate: Callable[[Any, Any], object], msg: str)
```

**Errors.** These suit code that returns an error instead of raising it.

```python
check.no_error(seat: Seat, error: BaseException | None, msg: str)
check.has_error(seat: Seat, error: BaseException | None, msg: str)
check.error_is(seat: Seat, error: BaseException | None, target: object, msg: str)
check.error_is_not(seat: Seat, error: BaseException | None, target: object, msg: str)
check.error_as(seat: Seat, error: BaseException | None, want: type[_E], msg: str) -> _E | None
```

**Raising.** raises returns the exception of fn, so a test can assert on its class or its message.

```python
check.raises(seat: Seat, fn: Callable[[], Any], msg: str) -> Exception | None
check.does_not_raise(seat: Seat, fn: Callable[[], Any], msg: str)
```

**Cancellation.** Python cancels work through asyncio. honours_cancellation and honours_deadline take a coroutine function and run the event loop themselves, so the test is a plain def. completes_within calls fn on a daemon thread and fails at the deadline without waiting for it.

```python
check.honours_cancellation(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str)
check.honours_deadline(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str)
check.completes_within(seat: Seat, within: float, fn: Callable[[], Any], msg: str)
check.none_handle_safe(seat: Seat, fn: Callable[[Any], Any], msg: str)
```

**Retrying.** These suit a condition that something outside the test makes true. On the platform clock they spend real time. On a Controlled clock they advance the clock between attempts.

```python
check.eventually(seat: Seat, timeout: float, interval: float, body: Callable[[Any], object], msg: str)
check.eventually_true(seat: Seat, timeout: float, predicate: Callable[[], object], msg: str)
```

**Concurrency.** Call what it returns where the scope ends. A thread or an asyncio task that the scope started and that still runs then is a leak.

```python
check.no_task_leaks(seat: Seat, msg: str) -> Callable[[], None]
```

**Purity.** observe must return a copy, because a reading that shares state with the subject compares one object with itself.

```python
check.is_pure(seat: Seat, observe: Callable[[], Any], fn: Callable[[], Any], msg: str, *options: Option)
check.is_not_pure(seat: Seat, observe: Callable[[], Any], fn: Callable[[], Any], msg: str, *options: Option)
```

**Relations.** Each calls the subject with the values that the test passes. A relation that compares two results compares them by the rules of equal.

```python
check.is_idempotent(seat: Seat, call: Callable[[Any], Any], value: Any, observe: Callable[[], Any], msg: str, *options: Option)
check.accumulates(seat: Seat, call: Callable[[Any], Any], value: Any, observe: Callable[[], Any], msg: str)
check.is_deterministic(seat: Seat, call: Callable[[Any], Any], value: Any, msg: str, *options: Option)
check.is_commutative(seat: Seat, combine: Callable[[Any, Any], Any], a: Any, b: Any, msg: str, *options: Option)
check.is_associative(seat: Seat, combine: Callable[[Any, Any], Any], a: Any, b: Any, c: Any, msg: str, *options: Option)
check.round_trip(seat: Seat, forward: Callable[[Any], Any], inverse: Callable[[Any], Any], value: Any, msg: str, *options: Option)
check.has_stable_order(seat: Seat, iterate: Callable[[], Any], msg: str, *options: Option)
check.no_duplicates(seat: Seat, iterate: Callable[[], Any], msg: str, *options: Option)
check.is_monotonic(seat: Seat, observe: Callable[[], Any], advance: Callable[[], Any], steps: int, msg: str)
check.is_total(seat: Seat, call: Callable[[Any], Any], domain: Iterable[Any], msg: str)
check.fails_after_close(seat: Seat, close: Callable[[], Any], call: Callable[[], Any], sentinel: object, msg: str)
check.is_poisoned(seat: Seat, induce: Callable[[], Any], observe: Callable[[], Any], msg: str)
```

**Testing an assertion.** rejects takes the message before its body. It returns the failure records of the body, and fails when the body passes.

```python
check.rejects(seat: Seat, msg: str, body: Callable[[Any], object]) -> list[Failure]
```

**Golden files.** Each comparison reads recorded output and takes
no message. A failure stops the test.

```python
golden.match(seat: Seat, name: str, got: str, update: bool, *scrubbers: Scrubber)
golden.match_at(seat: Seat, path: str | PathLike[str], got: str, update: bool, *scrubbers: Scrubber)
golden.match_json_field(seat: Seat, path: str | PathLike[str], field: str, got: str, update: bool, *scrubbers: Scrubber)
golden.match_tree(seat: Seat, name: str, dir: str | PathLike[str], update: bool, *scrubbers: Scrubber)
golden.should_update() -> bool
golden.scrub_timestamps() -> Scrubber
golden.scrub_hashes() -> Scrubber
golden.scrub_run_ids() -> Scrubber
golden.scrub_json_fields(*fields: str) -> Scrubber
golden.Scrubber = Callable[[str], str]
golden.GOLDEN_DIR = 'testdata/golden'
golden.UPDATE_ENV = 'DOKIMI_ASSERT_UPDATE_GOLDEN'
```

**Benchmark ceilings.** The ceilings chain onto one contract, and
`check` reports a verdict for each of them. `allocs_checked`
returns whether a run checks allocation ceilings.

```python
bench.Contract(seat: Seat)
Contract.warmup(iterations: int) -> Contract
Contract.max_latency(seconds: float) -> Contract
Contract.max_mean(seconds: float) -> Contract
Contract.max_bytes(count: int) -> Contract
Contract.loop(iterations: int) -> Iterator[int]
Contract.excluding(setup: Callable[[], _T]) -> _T
Contract.check()
bench.allocs_checked() -> tuple[bool, str]
```

**Seats.** An assertion reports each failure to its seat. The seat fixture is a Collector, and the recorder fixture is a Recorder.

```python
Seat.helper()
Seat.fail(message: str)
Seat.record(message: str)
seat.Collector()
Collector.cleanup(fn: Callable[[], object])
Collector.with_clock(clock: Clock) -> Collector
seat.Standard()
seat.Recorder()
Recorder.with_clock(clock: Clock) -> Recorder
Recorder.failed: bool
Recorder.message: str
Recorder.messages: list[str]
Recorder.failures: list[Failure]
Recorder.faults: list[BaseException]
Recorder.records: list[str]
Recorder.helper_calls: int
seat.clean_up(collector: Collector)
seat.fault(seat: Seat, error: BaseException)
```

**Options of a comparison.** An option relaxes or narrows equality for the one call that it is passed to.

```python
option.equate_empty() -> Option
option.equate_nans() -> Option
option.by_identity() -> Option
option.Option
```

**Failure records.** A failure is a record of the assertion, the contract and the detail. render returns the sentence of a record.

```python
failure.Failure(assertion: str, contract: str, detail: Mapping[str, Any], where: Where | None)
Failure.want: Any
Failure.got: Any
Failure.case_failure: Failure
failure.Where(file: str, line: int)
failure.render(failure: Failure) -> str
failure.register_sentence(sentence: Callable[[Failure], str], *assertions: str)
failure.call_site() -> Where | None
failure.site_in(traceback: TracebackType | None) -> Where | None
```

**Clocks.** An assertion that waits, retries or measures reads the clock of its seat. A Controlled clock moves only when a test advances it.

```python
Clock.now() -> float
Clock.sleep(duration: float)
clock.System()
clock.Controlled(start: float)
Controlled.advance(duration: float)
```

Read the docstring of an assertion for its rules and the
meaning of each argument, with `help(check.close_to)` or in
your editor.

<!-- api-reference:assertions:end -->

### A few in use

```python
import asyncio
import json
import operator

from dokimi_assert import check


def test_shapes(seat):
    err = check.raises(seat, lambda: json.loads("{"), "a truncated body is refused")
    check.contains(seat, str(err), "line 1", "the error contains the line")

    check.pairwise(seat, [1, 2, 2, 5], operator.le, "the log is ordered")
    check.close_to(seat, 1.02, 1.0, 0.05, "the retry waited about a second")
    check.matches(
        seat, "req_0123456789abcdef", r"^req_[0-9a-f]{16}$", "the id is well formed"
    )


async def serve() -> None:
    await asyncio.sleep(60)


def test_serve_stops_when_told(seat):
    check.honours_cancellation(seat, serve, "the server stops when told")
```

The subject of `honours_cancellation` is a coroutine function, and the test
is a plain `def`. The assertion runs the event loop itself, so the test
does not need an async plugin.

## Equality

`equal` compares two values only when their types are the same:

| Expression | Python's `==` | `equal` |
|---|---|---|
| `0 == False` | `True` | Not equal |
| `1 == 1.0` | `True` | Not equal |

`bool` subclasses `int`, and the numeric types compare across each other,
so `==` equates both pairs. Under the definition, values of different
types are never equal.

An absent collection does not equal an empty one, and NaN does not equal
itself. Where that difference does not matter, relax the comparison for one
call:

```python
from dokimi_assert import check
from dokimi_assert.option import equate_empty


def test_no_items_came_back(seat):
    items = None
    check.equal(seat, items, [], "no items came back", equate_empty())
```

`equate_empty()` makes an absent collection equal an empty one, and
`equate_nans()` makes a NaN equal another NaN. `by_identity()` compares
references by identity, so two equal lists that are distinct objects
differ. An option applies to the call that it is passed to, and to no other
call.

## Golden files

```python
from dokimi_assert import golden


def test_the_report_is_unchanged(seat):
    report = "generated at 2026-10-22T09:30:00Z\ntotal: 3\n"

    golden.match(
        seat, "report.txt", report, golden.should_update(), golden.scrub_timestamps()
    )
```

The file `testdata/golden/report.txt`, below the directory where pytest
runs, contains the recorded output. `DOKIMI_ASSERT_UPDATE_GOLDEN=1 pytest`
writes it. The scrubbers apply to both sides, so the file contains
`generated at SCRUBBED_TIMESTAMP`. Read the diff before an update, because
an update accepts the current output of the code.

`golden.match_tree` compares a directory with a golden tree under
`testdata/golden`. It compares the owner's execute bit of each file, the
one bit that git records. An update makes the golden tree equal the output,
and it removes each entry that the output lacks.

## Trees of files

```python
import os

from dokimi_assert import files


def test_a_rename_moves_the_draft(seat):
    root = files.workspace(seat, {"draft.txt": files.text("hello\n")})

    os.rename(os.path.join(root, "draft.txt"), os.path.join(root, "final.txt"))

    files.equal(
        seat,
        root,
        {"final.txt": files.text("hello\n")},
        "the draft becomes the final file",
    )
    files.absent(seat, os.path.join(root, "draft.txt"), "no draft is left")
```

- `files.text`, `bytes`, `executable`, `directory` and `link` build the
  entries of a tree, a dict from a path to an entry. `Entry.with_mode` sets
  the permission bits where they are part of the contract.
- `workspace` writes a tree into a new directory and returns its path. The
  test removes the directory when it ends, so the seat needs `cleanup`, as
  the `seat` fixture and a `prop.Case` have it.
- `write` writes a tree over a directory that exists, and `read` returns the
  content of a file.
- `equal`, `contains` and `unchanged` compare a directory with a tree.
  `absent`, `is_file`, `is_dir`, `links_to`, `has_content` and `has_mode`
  check the entry at one path.
- Every assertion of `files` stops the test at a failure.
- On a file system that does not record permission bits, such as a file
  system of Windows, a comparison does not compare modes, and `has_mode`
  ends the call with a fault.

<!-- api-reference:files:start -->

**Trees.** A tree maps each path to an entry. A path is relative to the root of the tree, and slashes separate its names.

```python
files.Tree = Mapping[str, Entry]
files.text(content: str) -> Entry
files.bytes(content: builtins.bytes | bytearray) -> Entry
files.executable(content: str) -> Entry
files.directory() -> Entry
files.link(target: str) -> Entry
Entry.with_mode(mode: int) -> Entry
```

**Writing and reading.** workspace writes a tree into a new directory that the test removes when it ends.

```python
files.workspace(seat: Seat, tree: Tree) -> str
files.write(seat: Seat, dir: str | PathLike[str], tree: Tree)
files.read(seat: Seat, path: str | PathLike[str]) -> str
```

**Comparing a tree.** Each compares the tree in a directory with a wanted tree.

```python
files.equal(seat: Seat, dir: str | PathLike[str], want: Tree, msg: str)
files.contains(seat: Seat, dir: str | PathLike[str], want: Tree, msg: str)
files.unchanged(seat: Seat, dir: str | PathLike[str], fn: Callable[[], object], msg: str)
```

**Checking one path.** Each reads the entry at the path itself and does not follow a link there.

```python
files.absent(seat: Seat, path: str | PathLike[str], msg: str)
files.is_file(seat: Seat, path: str | PathLike[str], msg: str)
files.is_dir(seat: Seat, path: str | PathLike[str], msg: str)
files.links_to(seat: Seat, path: str | PathLike[str], target: str, msg: str)
files.has_content(seat: Seat, path: str | PathLike[str], want: str | builtins.bytes | bytearray, msg: str)
files.has_mode(seat: Seat, path: str | PathLike[str], want: int, msg: str)
```

<!-- api-reference:files:end -->

## Properties

```python
import operator

from dokimi_assert import check, prop


def sorted_is_ordered(c: prop.Case) -> None:
    xs = c.draw(prop.list(prop.integer(-100, 100)), "xs")
    check.pairwise(c, sorted(xs), operator.le, "sorted orders the list")


def test_sorted(seat):
    prop.for_all(seat, "a sorted list is ordered", sorted_is_ordered)
```

`prop.for_all` runs the body against generated cases. The body draws its
inputs from its `prop.Case`, and it asserts on the case in the same way as
a test asserts on its seat. A failing case shrinks to the smallest case
that fails the same way:

```python
from dokimi_assert import check, prop


def reverse_starts_with_first(c: prop.Case) -> None:
    xs = c.draw(prop.list(prop.integer(0, 9)), "xs")
    check.equal(
        c, list(reversed(xs))[:1], xs[:1], "the reverse starts with the first element"
    )


def test_reverse(seat):
    prop.for_all(
        seat, "a reversed list starts with its first element", reverse_starts_with_first
    )
```

```text
AssertionError: a reversed list starts with its first element: counterexample after 2 valid and 0 rejected cases, seed 17964245989312729279
  xs: [0, 1]
failure of equal at test_reverse.py:6: the reverse starts with the first element: want [0], got [1]
replay: prop.replay("prop1:AAEAAAABAAEAAA") or DOKIMI_ASSERT_PROP_REPLAY=prop1:AAEAAAABAAEAAA
```

- A failing run writes its minimal case to the store of the test under
  `testdata/prop`, and later runs replay it first.
- A property form, such as `prop.equal` or `prop.round_trip`, runs one
  assertion on every generated input. A form reads the type of its input
  from the annotation of its function, and `prop.of` derives the generator
  of a type. `prop.of_shape` returns the generator of a shape file.
- `prop.fuzz` replays the stored cases of a property and returns the target
  of a fuzzer.
- `DOKIMI_ASSERT_PROP_SEED`, `DOKIMI_ASSERT_PROP_PROFILE`,
  `DOKIMI_ASSERT_PROP_BUDGET` and `DOKIMI_ASSERT_PROP_REPLAY` set the
  defaults of every property of a run. The profile is `default`, `ci` or
  `campaign`. The option `prop.hermetic()` makes a run ignore the four
  variables.

`prop.around` runs each run of the body inside a wrapper, so that every
case, shrink candidate and replay starts in an environment of its own, such
as a frozen clock:

```python
from collections.abc import Callable

import time_machine

from dokimi_assert import prop


def frozen(run: Callable[[], None]) -> None:
    with time_machine.travel(0, tick=False):
        run()


def test_backoff(seat):
    prop.for_all(
        seat, "a retry waits for its backoff", waits_for_backoff, prop.around(frozen)
    )
```

A wrapper that does not call `run`, calls it a second time or raises ends
the call with a fault.

`prop.using(t, generator)` makes `generator` the generator of `t` in one
run of `for_all`, `fuzz` or a property form. A draw of `prop.of(t)` decodes
with it, and a draw of `prop.of(u)` generates each `t` inside `u` with it.
Inside the generator, `prop.of(t)` is the generator of `t` without the
option. The generator can then narrow the values of its own type:

```python
def test_a_paid_order_ships(seat):
    open_orders = prop.of(Status).filter(lambda s: s is not Status.CANCELLED)
    prop.for_all(
        seat, "a paid order ships", ships_when_paid, prop.using(Status, open_orders)
    )
```

`prop.values(generator, seed, n)` returns the values of the first random
cases of a seed outside a property. A benchmark then measures the same
inputs in every run. `values` also takes the options of `prop.using`, so
the benchmark and a run of the property draw from one domain:

```python
open_orders = prop.of(Status).filter(lambda s: s is not Status.CANCELLED)
orders = prop.values(prop.of(Order), 42, 100, prop.using(Status, open_orders))
```

<!-- api-reference:prop:start -->

**Running a property.** for_all runs the body against generated cases, and the body draws its inputs from its case.

```python
prop.for_all(seat: Seat, contract: str, body: Callable[[Case], object], *options: Option)
prop.fuzz(seat: Seat, contract: str, body: Callable[[Case], object], *options: Option) -> Target
Case.draw(generator: Decoder[_T], label: str) -> _T
Case.assume(condition: bool)
Case.skip(reason: str) -> NoReturn
Case.classify(label: str)
Case.target(label: str, score: float)
Case.note(message: str)
Case.observe(fingerprint: int)
Case.cleanup(fn: Callable[[], object])
Case.rand() -> Random
Case.history() -> History
prop.values(generator: Generator[_T], seed: int, n: int, *options: Option) -> list[_T]
```

**Options of a run.** A later option of one kind replaces an earlier one. Each require and each using adds to the earlier ones.

```python
prop.Option
prop.cases(n: int) -> Option
prop.seed(s: int) -> Option
prop.replay(token: str) -> Option
prop.require(label: str, share: float) -> Option
prop.shrink(runs: int) -> Option
prop.shrink_time(seconds: float) -> Option
prop.max_choices(n: int) -> Option
prop.store(directory: str) -> Option
prop.explain(enabled: bool) -> Option
prop.workers(n: int) -> Option
prop.hermetic() -> Option
prop.draws(entries: str) -> Option
prop.around(wrapper: Wrapper) -> Option
prop.Wrapper = Callable[[Callable[[], None]], object]
prop.using(t: type[Any], generator: Generator[Any]) -> Option
```

**Generators.** Each returns a Generator. map, filter and bind derive a new generator from one.

```python
Generator.map(f: Callable[[_T_co], _U]) -> Generator[_U]
Generator.filter(keep: Callable[[_T_co], bool]) -> Generator[_T_co]
Generator.bind(f: Callable[[_T_co], Generator[_U]]) -> Generator[_U]
prop.boolean(p: Fraction | int) -> Generator[bool]
prop.integer(lo: int, hi: int) -> Generator[int]
prop.float(lo: builtins.float, hi: builtins.float, allow_nan: bool, width: Literal[32, 64]) -> Generator[builtins.float]
prop.duration(lo: int, hi: int) -> Generator[int]
prop.string(alphabet: str | None, min_size: int, max_size: int | None) -> Generator[str]
prop.string_matching(pattern: str) -> Generator[str]
prop.bytes(min_size: int, max_size: int | None) -> Generator[builtins.bytes]
prop.list(of: Generator[_T], min_size: int, max_size: int | None, unique: bool) -> Generator[builtins.list[_T]]
prop.dict(keys: Generator[_K], values: Generator[_V], min_size: int, max_size: int | None) -> Generator[builtins.dict[_K, _V]]
prop.optional(of: Generator[_T]) -> Generator[_T | None]
prop.one_of(*generators: Generator[_T]) -> Generator[_T]
prop.just(value: _T) -> Generator[_T]
prop.sampled_from(*values: _T) -> Generator[_T]
prop.permutation(*values: _T) -> Generator[builtins.list[_T]]
prop.recursive(base: Generator[_T], extend: Callable[[Generator[_T]], Generator[_T]], max_leaves: int) -> Generator[_T]
prop.composite(f: Callable[[Case], _T]) -> Generator[_T]
```

**Types and shapes.** of derives the generator of a type from its shape. A registration replaces the generator or the shape of a type in the test process.

```python
prop.of(t: type[_T]) -> Generator[_T]
prop.of_shape(text: str) -> Generator[Any]
prop.shape_of(t: type) -> str
prop.register(t: type[_T], generator: Generator[_T])
prop.register_values(t: type[_T], *values: _T)
prop.register_variants(t: type, *variants: type)
prop.Variant(name: str, payload: Any)
prop.WallTime(local: datetime, zone: ZoneInfo)
```

**Constraints.** Each is an argument of typing.Annotated, as the constraints of annotated-types are.

```python
prop.AllowInfinity()
prop.AllowNan()
prop.Alphabet(characters: str)
prop.Char()
prop.Pattern(regex: str)
prop.Scale(digits: int)
prop.Unit(name: Literal['s', 'ms', 'us', 'ns'])
prop.Version(number: Literal[4, 6])
prop.Width(bits: int, signed: bool)
```

**Forms.** Each form runs its assertion on every generated input. A form takes the options of a run, the options of a comparison that its assertion takes, and example and examples.

```python
prop.equal(seat: Seat, got: Callable[..., Any], want: Callable[..., Any], msg: str, *options: FormOption)
prop.not_equal(seat: Seat, got: Callable[..., Any], want: Callable[..., Any], msg: str, *options: FormOption)
prop.is_true(seat: Seat, condition: Callable[..., object], msg: str, *options: FormOption)
prop.is_false(seat: Seat, condition: Callable[..., object], msg: str, *options: FormOption)
prop.is_none(seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption)
prop.is_not_none(seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption)
prop.length(seat: Seat, got: Callable[..., Any], want: int, msg: str, *options: FormOption)
prop.is_empty(seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption)
prop.is_not_empty(seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption)
prop.contains(seat: Seat, got: Callable[..., Any], needle: Any, msg: str, *options: FormOption)
prop.not_contains(seat: Seat, got: Callable[..., Any], needle: Any, msg: str, *options: FormOption)
prop.contains_in_order(seat: Seat, got: Callable[..., Any], needles: Sequence[str], msg: str, *options: FormOption)
prop.is_permutation(seat: Seat, got: Callable[..., Any], want: Callable[..., Any], msg: str, *options: FormOption)
prop.has_prefix(seat: Seat, got: Callable[..., Any], prefix: str, msg: str, *options: FormOption)
prop.has_suffix(seat: Seat, got: Callable[..., Any], suffix: str, msg: str, *options: FormOption)
prop.matches(seat: Seat, got: Callable[..., Any], pattern: str, msg: str, *options: FormOption)
prop.close_to(seat: Seat, got: Callable[..., Any], want: float, tolerance: float, msg: str, *options: FormOption)
prop.in_range(seat: Seat, got: Callable[..., Any], low: float, high: float, msg: str, *options: FormOption)
prop.pairwise(seat: Seat, got: Callable[..., Sequence[Any]], predicate: Callable[[Any, Any], object], msg: str, *options: FormOption)
prop.no_error(seat: Seat, fn: Callable[..., BaseException | None], msg: str, *options: FormOption)
prop.has_error(seat: Seat, fn: Callable[..., BaseException | None], msg: str, *options: FormOption)
prop.error_is(seat: Seat, fn: Callable[..., BaseException | None], target: object, msg: str, *options: FormOption)
prop.error_is_not(seat: Seat, fn: Callable[..., BaseException | None], target: object, msg: str, *options: FormOption)
prop.error_as(seat: Seat, fn: Callable[..., BaseException | None], want: type[BaseException], msg: str, *options: FormOption)
prop.raises(seat: Seat, fn: Callable[..., Any], msg: str, *options: FormOption)
prop.does_not_raise(seat: Seat, fn: Callable[..., Any], msg: str, *options: FormOption)
prop.honours_cancellation(seat: Seat, fn: Callable[..., Awaitable[Any]], msg: str, *options: FormOption)
prop.honours_deadline(seat: Seat, fn: Callable[..., Awaitable[Any]], msg: str, *options: FormOption)
prop.none_handle_safe(seat: Seat, fn: Callable[..., Any], msg: str, *options: FormOption)
prop.is_pure(seat: Seat, observe: Callable[[], Any], fn: Callable[..., Any], msg: str, *options: FormOption)
prop.is_not_pure(seat: Seat, observe: Callable[[], Any], fn: Callable[..., Any], msg: str, *options: FormOption)
prop.is_idempotent(seat: Seat, call: Callable[..., Any], observe: Callable[[], Any], msg: str, *options: FormOption)
prop.accumulates(seat: Seat, call: Callable[..., Any], observe: Callable[[], Any], msg: str, *options: FormOption)
prop.is_deterministic(seat: Seat, call: Callable[..., Any], msg: str, *options: FormOption)
prop.is_commutative(seat: Seat, combine: Callable[[Any, Any], Any], msg: str, *options: FormOption)
prop.is_associative(seat: Seat, combine: Callable[[Any, Any], Any], msg: str, *options: FormOption)
prop.round_trip(seat: Seat, forward: Callable[..., Any], inverse: Callable[[Any], Any], msg: str, *options: FormOption)
prop.example(*values: Any) -> FormOnly
prop.examples(*values: Any) -> FormOnly
prop.FormOption = prop.Option | option.Option | FormOnly
```

<!-- api-reference:prop:end -->

## Histories

```python
from dokimi_assert import history


class Register:
    def initial(self) -> int:
        return 0

    def next(self, state: int, op: history.Operation) -> list[int]:
        if op.name == "write":
            return [op.args[0]]
        return [state] if op.returned(state) else []


def test_the_register_is_linearizable(seat):
    calls = history.History()
    calls.invoke(0, "write", [1], "x").ok(None)
    calls.invoke(1, "read", [], "x").ok(0)

    history.is_linearizable(seat, calls, Register(), "the register is linearizable")
```

The read returns 0 after the write of 1 completed, so no order of the two
calls fits the register. The failure contains the longest order of calls
that the specification accepts, and the call that it rejects there:

```text
AssertionError: the register is linearizable: violated in the partition of 'x'
    steps 2, partitions 1, calls 2, concurrency 1
    linearized: call 0 write(1) -> None
    states: 1
    rejected: call 2 read() -> 0
```

- A test records each call with `History.invoke` before the call starts.
  After the call returns, the test completes it with `Call.ok`, `Call.fail`
  or `Call.unknown`.
- `history.concurrently` starts the clients together, and
  `history.from_intervals` builds a history from a log of timed calls.
- Calls that share a key form one partition, and the check searches each
  partition on its own.
- `history.spec_from` builds a specification from a factory of the
  subject.
- `history.is_serializable` and `history.has_snapshot_isolation` check a
  history of list-append transactions.

<!-- api-reference:history:start -->

**Recording.** A test records each call before the call starts, and completes it after the call returns.

```python
history.History()
History.invoke(client: int, operation: str, args: Sequence[Any], *keys: Any) -> Call
History.events() -> list[Event]
Call.ok(output: Any)
Call.fail(error: Any)
Call.unknown(error: Any)
history.concurrently(clients: int, within: float, body: Callable[[int], object]) -> list[Outcome]
history.Outcome(client: int, finished: bool, output: Any)
history.from_intervals(entries: Sequence[Interval]) -> History
history.Interval(client: int, operation: str, args: Sequence[Any], keys: Sequence[Any], start: float, end: float | None, kind: Literal['ok', 'fail', 'unknown'] | None, output: Any, error: Any)
history.IntervalError(entry: int, reason: str)
```

**Events.** History.events returns the events in recording order.

```python
history.Event = history.Invocation | history.Completion
history.Invocation(index: int, call: int, client: int, process: int, operation: str, args: tuple[Any, ...], keys: tuple[Any, ...], kind: Literal['invoke'])
history.Completion(index: int, kind: Literal['ok', 'fail', 'unknown'], call: int, client: int, process: int, output: Any, error: Any)
history.Kind = Literal['invoke', 'ok', 'fail', 'unknown']
```

**Specifications.** A spec returns the states that an operation can lead to from a state, and no state for an operation that it refuses.

```python
Spec.initial() -> _S
Spec.next(state: _S, op: Operation) -> Sequence[_S]
Operation.name: str
Operation.args: tuple[Any, ...]
Operation.known: bool
Operation.output: Any
Operation.returned(value: Any) -> bool
history.spec_from(factory: Callable[[], Subject]) -> SubjectSpec
```

**Checks.** is_linearizable checks a history against a spec. is_serializable and has_snapshot_isolation read a history of list-append transactions.

```python
history.is_linearizable(seat: Seat, history: History, spec: Spec[_S], msg: str, *options: Option)
history.is_serializable(seat: Seat, history: History, msg: str)
history.has_snapshot_isolation(seat: Seat, history: History, msg: str)
```

**Options of a check.** Each bounds the search of is_linearizable.

```python
history.Option
history.budget(steps: int) -> Option
history.memo_limit(bits: int) -> Option
history.time_limit(seconds: float) -> Option
history.workers(n: int) -> Option
```

**Calls and evidence.** These are the types of the calls, the transactions and the evidence that the checks and their records use.

```python
history.Span(call: int, completion: int | None, process: int, operation: CallOperation)
history.Transaction(call: int, completion: int | None, kind: Literal['ok', 'fail', 'unknown'] | None, process: int, args: tuple[Any, ...], output: Any, mops: tuple[Mop, ...])
history.Link(call: int, relations: tuple[Relation, ...])
history.Edge(source: int, target: int, relation: Relation, key: Any, value: Any, empty: bool, following: Any)
history.Observation(anomaly: Anomaly, calls: tuple[int, ...], key: Any, reads: tuple[list[Any], ...], value: Any, appender: int | None, following: Any, expected: tuple[Any, ...], whole: bool, future: Any, has_future: bool)
history.Evidence = history.Edge | history.Observation
```

<!-- api-reference:history:end -->

## Machines

```python
from collections import deque
from dataclasses import dataclass, field

from dokimi_assert import history, prop, stateful


class Queue:
    def initial(self) -> tuple[int, ...]:
        return ()

    def next(
        self, state: tuple[int, ...], op: history.Operation
    ) -> list[tuple[int, ...]]:
        if op.name == "put":
            return [(*state, op.args[0])]
        head = state[0] if state else None
        return [state[1:]] if op.returned(head) else []


@dataclass
class QueueMachine:
    queue: deque[int] = field(default_factory=deque)
    spec: Queue = field(default_factory=Queue)

    @property
    def actions(self) -> list[stateful.Action[tuple[int, ...]]]:
        return [
            stateful.Action("put", self.put, input=self.value),
            stateful.Action("get", self.get),
        ]

    def value(self, c: prop.Case, state: tuple[int, ...]) -> int:
        return c.draw(prop.integer(0, 9), "v")

    def put(self, c: prop.Case, client: int, v: int) -> None:
        call = c.history().invoke(client, "put", [v])
        self.queue.append(v)
        call.ok(None)

    def get(self, c: prop.Case, client: int, _: object) -> None:
        call = c.history().invoke(client, "get", [])
        call.ok(self.queue.popleft() if self.queue else None)


def test_the_queue_keeps_its_values_in_order(seat):
    def body(c: prop.Case) -> None:
        stateful.steps(c, QueueMachine(), stateful.clients(2))

    prop.for_all(seat, "the queue keeps its values in order", body)
```

- A machine has the sequential specification of a subject and its actions,
  with the simpler actions first.
- `stateful.steps` takes the steps of a case and makes each decision a
  choice of the case. A failing case then shrinks to the steps that the
  failure needs, and it replays from its token.
- The clients of a concurrent section run on threads by default. A case
  then runs up to `repeat` times, because threads do not replay.
- With the option `stateful.tasks`, the clients run as tasks of a
  `stateful.Scheduler`. The releases of the scheduler are choices of the
  case, so a race replays and shrinks. A subject that runs as tasks awaits
  a future or `asyncio.sleep(0)` at each point where another task can run.

<!-- api-reference:stateful:start -->

**Machines.** A machine has the spec of a subject and its actions. steps takes the steps of a machine in a case.

```python
Machine.spec: Spec[S] | None
Machine.actions: Sequence[Action[S]]
stateful.Action(name: str, run: Callable[[Case, int, Any], object], weight: int, drain: bool, enabled: Callable[[S], bool] | None, input: Callable[[Case, S], Any] | None)
stateful.steps(case: Case, machine: Machine[_S], *options: Option)
```

**Options of steps.** Each sets one bound of the steps of a case, or the way in which the clients of a concurrent section run.

```python
stateful.Option
stateful.clients(n: int) -> Option
stateful.concurrent(n: int) -> Option
stateful.max_steps(n: int) -> Option
stateful.mean(n: int) -> Option
stateful.repeat(n: int) -> Option
stateful.swarm(on: bool) -> Option
stateful.tasks(scheduler: Scheduler) -> Option
```

**Schedulers.** With tasks, the clients run as tasks of a Scheduler. Its releases are choices of the case.

```python
stateful.Scheduler(case: Case, strategy: Strategy)
Scheduler.spawn(task: Callable[[], Coroutine[Any, Any, object]])
Scheduler.run()
stateful.Strategy
stateful.uniform() -> Strategy
stateful.pct(depth: int) -> Strategy
```

<!-- api-reference:stateful:end -->

## Testing your own assertions

```python
from dokimi_assert import check


def test_the_check_refuses_an_empty_name(seat):
    failures = check.rejects(
        seat,
        "an empty name is refused",
        lambda inner: check.is_not_empty(inner, "", "the name is not empty"),
    )
    check.equal(
        seat, failures[0].assertion, "not-empty", "the check fails on the empty name"
    )
```

`rejects` returns the failure records of the body, so a test confirms that
the check fails for the reason that it was written to catch. Both surfaces
have it. The `recorder` fixture is the lower-level form. Drive an assertion
with it, then read `failed`, `message` and `failures`.

A check whose environment lacks a capability calls `skip` of its seat.
When it skips before it fails, `rejects` skips the test with the reason.
The check cannot run there, so it has no verdict on the subject. On a
`Recorder`, which cannot skip, `rejects` returns an empty list. A
`unittest.SkipTest` that the check raises propagates out of `rejects`
without a verdict.

## Call records

With `DOKIMI_ASSERT_RECORD=1`, the seat of each test appends the call
record of every call to the `user_properties` of the test's item. Each
record is one property, named `dokimi.assert.<seq>`. pytest's JUnit XML
report writes each user property as a `property` element of the test's
`testcase` element.

A `Recorder` keeps the records of its calls as lines of JSON, and
`Recorder.records` returns them.

## The standard

[assert-spec](https://github.com/dokimasia/assert-spec) defines the
assertions. This library vendors the definition, and its tests check the
library against it:

- The 195 cases of the corpus run on `check` and `expect`. Python skips none
  of them.
- The vectors run too: 57 for files, 80 for histories, 432 for properties
  and 14 for machines.
- `tests/test_definition.py` checks each of the definition's 110
  assertions. An assertion is present, or the overlay declines it and it is
  absent.
- The library implements 105 of the 110. `pairwise`, `completes_within`,
  `no_task_leaks`, `rejects` and the five error assertions have no corpus
  case.

### Where Python differs

- Python cancels work through asyncio. `honours_cancellation` and
  `honours_deadline` take a coroutine function, start it, and cancel it at
  its first await.
- An assertion that receives a coroutine function runs it on an event loop
  of its own. Inside a running event loop, such as an `async def` test, the
  call ends with a fault. The message of the fault contains the id of the
  assertion in the definition, such as `nil-context-safe`.
- `no_task_leaks` returns a check that the test calls where the scope ends.
  A thread or an asyncio task that started in the scope and still runs then
  is a leak.
- `completes_within` calls the subject on a daemon thread. A subject that
  has not returned at the deadline fails then, and it keeps running on its
  thread.
- CPython does not keep a running count of allocations. The overlay
  declines `max_allocs`, `max_allocs_with_setup`,
  `bench.Contract.max_allocs`, `prop.max_allocs` and
  `prop.max_allocs_with_setup` for that reason. `bench.allocs_checked()`
  returns False and the reason, so a test can report that its run does not
  check an allocation ceiling.
- `Contract.max_bytes` measures with `tracemalloc`, which slows the body. A
  contract that states `max_bytes` also measures its latency on traced
  iterations, so set its ceilings from a traced run.

## Development

ergon manages the Makefile, the workflows and the configuration of the
tools. `ergon init sync` writes them again from its baseline and from the
files under `.ergon/local`.

```sh
make check      # the gate of the repository
make test       # the tests
make coverage   # the tests under coverage, which fail below 100%
make fmt        # format the sources
make api-docs   # regenerate the API reference of this README
make help       # list every target
```

`make check` lints the Markdown files with rumdl and the workflows with
actionlint, and it checks the vendored definition with spec. For Python, it
runs ruff, a format check, mypy in its strictest mode, the tests, and
pip-audit over `uv.lock`. On Linux, it also runs the tests under coverage,
which fail below 100% of the statements and branches. CI runs the gate of
Python on Linux, macOS and Windows with Python 3.11 to 3.14.

A change to the package comes with a changeset, which `ergon release add`
writes. When CI passes on `main`, the workflow `version.yml` opens the
version pull request. Its merge publishes the package to PyPI through
Trusted Publishing. The nightly workflow proposes each new version of the
definition as a pull request.

The design is in
[RFC-0001](docs/rfc/0001-the-python-implementation.md),
[RFC-0002](docs/rfc/0002-definition-8-in-python.md) and
[RFC-0004](docs/rfc/0004-definition-10-in-python.md).

## Licence

MIT. See [LICENSE](LICENSE).
