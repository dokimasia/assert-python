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
needs Python 3.11 or later and has no runtime dependencies.

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
  `message`, `messages`, `failures` and `records`.
- The `prop.Case` of a property is a seat too, so every assertion works
  inside a property.

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
`history` and `prop` have their own sections.

<!-- api-reference:start -->

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
```

**Benchmark ceilings.** The ceilings chain onto one contract, and
`check` reports a verdict for each of them.

```python
bench.Contract(seat: Seat)
Contract.warmup(iterations: int) -> Contract
Contract.max_latency(seconds: float) -> Contract
Contract.max_mean(seconds: float) -> Contract
Contract.max_bytes(count: int) -> Contract
Contract.loop(iterations: int) -> Iterator[int]
Contract.excluding(setup: Callable[[], _T]) -> _T
Contract.check()
```

Read the docstring of an assertion for its rules and the
meaning of each argument, with `help(check.close_to)` or in
your editor.

<!-- api-reference:end -->

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
    check.matches(seat, "req_0123456789abcdef", r"^req_[0-9a-f]{16}$", "the id is well formed")


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

    golden.match(seat, "report.txt", report, golden.should_update(), golden.scrub_timestamps())
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

    files.equal(seat, root, {"final.txt": files.text("hello\n")}, "the draft becomes the final file")
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
    check.equal(c, list(reversed(xs))[:1], xs[:1], "the reverse starts with the first element")


def test_reverse(seat):
    prop.for_all(seat, "a reversed list starts with its first element", reverse_starts_with_first)
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

## Machines

```python
from collections import deque
from dataclasses import dataclass, field

from dokimi_assert import history, prop, stateful


class Queue:
    def initial(self) -> tuple[int, ...]:
        return ()

    def next(self, state: tuple[int, ...], op: history.Operation) -> list[tuple[int, ...]]:
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

## Testing your own assertions

```python
from dokimi_assert import check


def test_the_check_refuses_an_empty_name(seat):
    failures = check.rejects(
        seat,
        "an empty name is refused",
        lambda inner: check.is_not_empty(inner, "", "the name is not empty"),
    )
    check.equal(seat, failures[0].assertion, "not-empty", "the check fails on the empty name")
```

`rejects` returns the failure records of the body, so a test confirms that
the check fails for the reason that it was written to catch. Both surfaces
have it. The `recorder` fixture is the lower-level form. Drive an assertion
with it, then read `failed`, `message` and `failures`.

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
- The vectors run too: 57 for files, 80 for histories, 430 for properties
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
  `prop.max_allocs_with_setup` for that reason.
- `Contract.max_bytes` measures with `tracemalloc`, which slows the body. A
  contract that states `max_bytes` also measures its latency on traced
  iterations, so set its ceilings from a traced run.

## Development

```sh
make install    # create the environment
make check      # lint, Markdown, types, and the tests with 100% coverage
make test       # the tests
make fmt        # format and autofix
make api-docs   # regenerate the API reference of this README
make build      # build the sdist and wheel
make spec-sync  # refresh the vendored definition
make help       # list every target
```

`make check` runs ruff, a format check, markdownlint, mypy strict,
basedpyright and the tests with 100% coverage of statements and branches.
CI runs ruff, the format check, mypy and the tests on Python 3.11 through
3.14, and it checks the vendored definition.

A `v*` tag starts the release. The workflow builds the package, runs the
gate again and checks that the tag agrees with `pyproject.toml`. Then it
publishes to PyPI through Trusted Publishing.

The design is in
[RFC-0001](docs/rfc/0001-the-python-implementation.md) and
[RFC-0002](docs/rfc/0002-definition-8-in-python.md).

## Licence

MIT. See [LICENSE](LICENSE).
