---
rfc: 0002
title: Definition 8.0 in Python
author: Roy Klopper <roy.klopper@stealthscale.io>
status: Accepted
created: 2026-10-11
updated: 2026-10-12
discussion: https://github.com/dokimasia/assert-python/issues/8
supersedes: none
superseded-by: none
produces-adr: none
---

<!--
  ~ Copyright Dokimasia B.V. 2026
  ~ SPDX-License-Identifier: MIT
-->

# RFC-0002: Definition 8.0 in Python

## Summary

The library moves from definition 1.1.0 to 8.0.0 in one step. It gains
the 68 assertions and the 190 Python names that the definition added
since 1.1.0:

- the property engine, with its generators, its property forms and its
  derived inputs
- the 14 relations and `by_identity`
- the history seam and its three checks
- machines and the task scheduler
- trees of files, the file assertions and `golden.match_tree`
- call records, faults, and the accessors of the failure record
- `warmup` on the bench contract

The definition fixes the names, the rules and the vectors. This proposal
decides only what Python must decide:

- **Coroutines.** A body, a callable and an action can be a coroutine
  function. The assertion runs the coroutine on an event loop of its own,
  as the cancellation assertions do.
- **Records.** The `seat` fixture appends each call record to the
  `user_properties` of the test's item, and pytest's JUnit XML report
  writes them.
- **Numbers.** The engine computes the definition's 64-bit arithmetic on
  Python integers that it masks to 64 bits.
- **Tasks.** The task scheduler is an asyncio event loop that releases one
  ready task at a time.
- **Workers.** `prop.workers` and `history.workers` run their work on
  threads.
- **Time.** `prop.duration` generates an `int` of nanoseconds, and a date
  or time at nanoseconds has a Python type only where Python states one
  as an `int`.
- **Files.** The file helpers and assertions call the `os` module. On
  POSIX they create each entry relative to an open directory.
- **The engine.** The engine follows the text of the definition. None of
  its code comes from the definition's executable reference, which
  computes the vectors.
- **Python.** The library still requires Python 3.11 or later. It still
  has no runtime dependency.
- **The definition.** Definition 8.0.0 adds two limits for time zones and
  nanoseconds to the Python overlay and one Python skip to a vector. The
  library vendors 8.0.0.

## Motivation

The library vendors definition 1.1.0. It implements 40 of the
definition's 110 assertions, and its naming table has 81 of the 282 Python
names of 7.2.1. Its completeness gate fails on every row that it neither
implements nor declines, so the library cannot vendor a later version
until it implements the rest.

The shared vectors pin each addition: 430 property vectors, 80 history
vectors, 14 machine vectors and 57 file vectors. The corpus grew from 87
cases at 1.1.0 to 195 at 7.2.1, and none of them skips Python. The library
runs none of the vectors. The Go and TypeScript libraries run them, so
Python disagrees with both wherever it has not caught up:

- `length` counts the code points of a `str` with `len`, so a string with
  a lone surrogate has a length (`src/dokimi_assert/_matcher/value.py`,
  lines 117 to 136).
- `contains` looks a key up with `in`. The key `1` then matches the needle
  `1.0`, and a NaN key matches its own object (lines 186 and 187).
- `matches` searches with `re`, so `$` matches before a final newline and
  `re` accepts a backreference (lines 362 to 369).
- `in_range` passes every number for a range with a NaN bound (lines 449
  to 470).
- `is_empty` states only `length`, and `is_not_empty` states no field
  (lines 139 to 172).
- `completes_within` runs the subject to its end before it fails
  (`_matcher/behaviour.py`, lines 139 to 172).
- `rejects` returns the first message of the check, and the definition
  returns its failure records (`rejects.py`, lines 13 to 52).

## Detailed design

### Components

| Component | Modules | Responsibility |
|---|---|---|
| Typed literals | `_record/literal.py` | Encodes a value as the definition's typed literal |
| Call records | `_record/calls.py`, `_record/switch.py` | Numbers calls, writes each record, and reads `DOKIMI_ASSERT_RECORD` once per process |
| Verdicts | `_matcher/verdict.py` | Reports a pass, a failure and a fault, and writes the call record of each |
| Failure record | `failure.py` | `Failure`, with `want`, `got` and `case_failure` |
| Seats | `seat.py`, `_matcher/seat.py`, `pytest_plugin.py` | `Recorder.records`, and the records of a test in its `user_properties` |
| Coroutines | `_matcher/loop.py` | Runs the coroutine of a body or a callable on the event loop of the assertion |
| Equality and values | `_matcher/compare.py`, `_matcher/value.py`, `_matcher/option.py` | The rules of 2.0.0, 3.0.0, 5.2.0 and 7.1.0, and `by_identity` |
| Portable patterns | `_pattern/` | Parses the portable subset for `matches` and `prop.string_matching` |
| Relations | `_matcher/relation.py`, `check.py`, `expect.py` | The 14 relations on both surfaces |
| Property engine | `prop/`, `_prop/` | The public package `prop`, and the source, the decoder, the shrinker, coverage, tokens, the store, campaigns, shapes and the fuzz bridge |
| Histories | `history/` | The public package `history`: the seam, specs, `concurrently` and the three checks |
| Machines | `stateful/` | The public package `stateful`: machines, their steps and the task scheduler |
| Files | `files/`, `golden.py` | The public package `files`, and `golden.match_tree` |
| Bench | `bench.py` | `warmup` |
| Conformance | `conformance/` | A driver for each vector family, and the corpus driver for the 8.0.0 corpus |

`prop`, `history`, `stateful` and `files` are subpackages of
`dokimi_assert`, beside `check`, `expect`, `golden` and `bench`. A test
imports them as `from dokimi_assert import prop`, so `prop.for_all` and
`files.equal` read as the naming table states them.

### The definition: 8.0.0

The library cannot meet two parts of 7.2.1 as the overlay states it. The
definition requires a limit or a skip for each such part, so the changes
go to assert-spec first. They are part of definition 8.0.0, which also
changes the count of `max-allocs`, an assertion that Python declines:

| Change | Where | Reason |
|---|---|---|
| A limit on `prop.of`: a zone resolves through `zoneinfo`, from the system's time-zone database or from the `tzdata` package. A `datetime` in a zone can then show another wall time than tzdata 2026e states. A zone that neither source has ends the read with a fault, and the text of the fault contains the name of the zone | `overlays/python.json` | CPython reads time zones from the platform, and Windows has no database without the `tzdata` package |
| A limit on `prop.of-shape`, with the zone text of the `prop.of` entry. It also states that the decoder refuses a `time-of-day`, a `local-date-time`, a `zoned-date-time` and a `wall-time` at nanoseconds | `overlays/python.json` | The resolution of `datetime` and `time` is one microsecond. Python states only an instant and a duration in nanoseconds, as an `int` |
| A `python` skip on `zoned-date-time/nanoseconds` | `corpus/prop/shapes.yaml` | No Python type represents a zoned date and time at nanoseconds |

Go's overlay states the same zone difference on `prop.of` and
`prop.of-shape`. The vendored copy then comes from `main` of assert-spec
at 8.0.0.

### Coroutines

A property's body, the function of a form, the callable of a relation, an
action of a machine, the body of `history.concurrently` and the callable
of `files.unchanged` can each be a coroutine function:

- The assertion calls the function. When the result is awaitable, the
  assertion runs it to its end on an event loop that it creates with
  `asyncio.Runner`, and continues with the result.
- One assertion call creates at most one loop, and closes it when the call
  ends. The cases of a property share the loop of their run.
- An assertion that needs its own loop ends with a fault when a loop
  already runs in its thread. The text of the fault contains the name of
  the assertion.

A test can then be a plain `def`, as it is for the cancellation
assertions:

```python
def test_a_second_put_changes_nothing(seat):
    # client.put is an async def. The relation runs it on its own loop.
    check.is_idempotent(
        seat,
        client.put,
        entry,
        client.snapshot,
        "a second put of one entry changes nothing",
    )
```

### Equality, values and the corpus

The rules that definitions 2.0.0 to 7.1.0 added to the assertions that the
library already has:

- `length` counts the Unicode scalar values of text. A `str` with a
  surrogate code point has no length, and fails as a value without a
  length fails. `None` fails with `got` of `None`.
- A key compares as `equal` compares. The library finds a key with its
  own comparison, because a `dict` finds the needle `1.0` under the key
  `1`. Without `equate_nans`, no NaN key matches, and `-0.0` and `0.0` are
  one key. Two maps are equal when a one-to-one matching pairs their
  entries, so a comparison of two maps of n entries takes up to n² key
  comparisons.
- `contains` and `not_contains` compare an element as `equal` compares,
  so an `int` does not match a `float`.
- `matches` parses the pattern with the parser of the portable subset in
  `_pattern/`. It compiles the parsed pattern to an `re` pattern with the
  meaning of the subset: `\Z` for `$`, the flag `re.ASCII` for `\d`, `\w`
  and `\s`, and a class without `\n`, `\r`, U+0085, U+2028 and U+2029 for
  `.`. A pattern outside the subset fails, and the field `reason` states
  the text of the parser.
- `is_empty` states `got` and `length`, and `length` is `None` for a
  value without a length. `is_not_empty` states `got`.
- `close_to` fails for two equal infinities. `in_range` fails for a range
  with a NaN bound.
- `completes_within` calls the subject on a daemon thread. It waits on
  the clock of the seat. When the duration passes before the subject
  returns, it fails at once and does not wait for the subject.
- A detail field without a value states `None`.
- `by_identity()` compares a reference with `is`. Every object is a
  reference except `None`, a `bool`, an `int`, a `float`, a `str`, `bytes`
  and a `tuple`. A tuple compares its items one by one.

The corpus driver decodes every literal of the 8.0.0 corpus: `bytes`, a
list of `items`, a map of `entries`, integers written as decimal strings,
absent containers, named floats inside lists, `record`, `variant`,
`reference` and `tree`. It applies the `options` of each case. It requires
that the detail of a failure contain exactly the fields that the assertion
declares. The completeness gate counts the parameters of every function,
which is as much of a signature as Python can read.

### The failure record

```python
@dataclass(frozen=True)
class Failure:
    """The record that a failing assertion reports, as the definition states it."""

    assertion: str
    contract: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    where: Where | None = None

    @property
    def want(self) -> Any:
        """The value of the field want of the detail.

        Raises:
            KeyError: The assertion does not declare the field want.
        """

    @property
    def got(self) -> Any:
        """The value of the field got of the detail.

        Raises:
            KeyError: The assertion does not declare the field got.
        """

    @property
    def case_failure(self) -> Failure:
        """The failure record of a failing case of a property.

        Raises:
            KeyError: The detail does not contain the field failure.
        """
```

A declared field can contain `None`, as `got` of an `equal` failure over
`None` does. `want` and `got` then return `None`. A field that the
assertion does not declare raises `KeyError`, as the definition states for
Python.

`rejects` returns the failure records of its check, in call order, on
both surfaces:

```python
def rejects(seat: Seat, msg: str, body: Callable[[Seat], object]) -> list[Failure]: ...
```

The check runs on a seat of its own and ends at its first aborting
failure, as a test does. When the check passes, `check.rejects` fails the
test and `expect.rejects` records a failure. Both return an empty list
then.

### Faults

An assertion that cannot run reports a fault. A spec function that
raises, a malformed shape, a refused interval and a call from a running
event loop are faults. So is the switch `DOKIMI_ASSERT_RECORD` set to a
value that the definition does not define. A fault ends the call with the
verdict `error`. The seat receives the text of the fault through `fail` on
both surfaces, and the call record states the text in the field `error`.

### Call records

`DOKIMI_ASSERT_RECORD=1` records every assertion call. The library reads
the variable once per process, on the first call that needs it.

A call record is a JSON object with the fields of the definition, in its
order: `definition`, `seq`, `parent`, `run`, `phase`, `assertion`,
`contract`, `verdict`, `aborting`, `where`, `detail` and `error`. An
absent field is left out. `seq` counts from 1 in each test. A call that
runs a body takes its `seq` before the calls of its body.

The encoder maps a Python value to a typed literal:

| Value | Literal |
|---|---|
| `None` | `null` |
| `bool` | `bool` |
| `int` | `int`, as a decimal string beyond ±(2^53 − 1) |
| `float` | `float`, with `NaN`, `Inf` and `-Inf` as strings |
| `str` | `string`, or `opaque` for a string with a surrogate code point |
| `bytes`, `bytearray` | `bytes` |
| `list`, `tuple` | `list` |
| `set`, `frozenset` | `list` |
| `dict` | `map` |
| A dataclass and a `NamedTuple` | `record`, with the fields in declaration order |
| An `Enum` member | `variant`, without a payload |
| A value nested past 61 levels, and any other value | `opaque`, with its `repr` as the text |

The encoder writes the items of a set in the order of the JSON text of
their literals. The iteration order of a set of strings changes with
`PYTHONHASHSEED`. The sorted order keeps the record of a set the same in
every run.

The `seat` fixture writes the records of a test where the overlay states:
one property per record, named `dokimi.assert.<seq>`, with the JSON of
the record as its value. The plugin appends each record to the
`user_properties` of the item when the call reports its verdict. In every
`junit_family`, pytest's JUnit XML report writes each user property of a
test as a `property` element of its `testcase` element. The plugin does
not call the fixture `record_property`, because that fixture warns under
`xunit2`, the default family.

A `Recorder` keeps its records whatever the switch states:

```python
class Recorder:
    @property
    def records(self) -> list[str]:
        """The call records of the calls on this recorder, in the order of their seq, as JSON lines."""
```

A `Standard` seat does not write records. A `Collector` that a test builds
without the fixture does not write them either.

### Relations

The 14 relations are on `check` and `expect`. A callable can be a
coroutine function, as the section on coroutines describes.

```python
def is_idempotent(
    seat: Seat,
    call: Callable[[I], object],
    value: I,
    observe: Callable[[], object],
    msg: str,
    *options: Option,
) -> None: ...


def is_permutation(
    seat: Seat, got: Sequence[T], want: Sequence[T], msg: str, *options: Option
) -> None: ...
```

- A callable that raises fails the relation, unless the relation requires
  a failure, as `fails_after_close` and `is_poisoned` do.
- `observe` returns a copy. A projection that shares state with the
  subject compares one object with itself.
- `accumulates` reads an `int` or a `float`, and `is_monotonic` reads
  numbers.
- `has_stable_order` and `no_duplicates` read an iterable.
- `is_permutation` pairs elements through a maximum bipartite matching. A
  greedy match fails under `equate_empty`, which makes `None` equal to
  both `[]` and `{}` while those two differ.

### The property engine

```python
def for_all(
    seat: Seat, contract: str, body: Callable[[Case], object], *options: Option
) -> None: ...


class Case:
    """The seat of the assertions of a body, and the source of its inputs."""

    def draw(self, generator: Generator[T], label: str) -> T: ...
    def assume(self, condition: bool) -> None: ...
    def classify(self, label: str) -> None: ...
    def note(self, message: str) -> None: ...
    def rand(self) -> random.Random: ...
    def observe(self, fingerprint: int) -> None: ...
    def cleanup(self, fn: Callable[[], object]) -> None: ...
    def history(self) -> History: ...
    def target(self, label: str, score: float) -> None: ...


class Generator(Generic[T]):
    def map(self, f: Callable[[T], U]) -> Generator[U]: ...
    def filter(self, keep: Callable[[T], bool]) -> Generator[T]: ...
    def bind(self, f: Callable[[T], Generator[U]]) -> Generator[U]: ...
```

The generators take the parameters of the table of generators. A size or
a flag is a keyword argument:

```python
def integer(lo: int, hi: int) -> Generator[int]: ...
def float(
    lo: float, hi: float, *, allow_nan: bool = False, width: Literal[32, 64] = 64
) -> Generator[float]: ...
def boolean(p: Fraction = Fraction(1, 2)) -> Generator[bool]: ...
def just(value: T) -> Generator[T]: ...
def sampled_from(*values: T) -> Generator[T]: ...
def one_of(*generators: Generator[T]) -> Generator[T]: ...
def optional(of: Generator[T]) -> Generator[T | None]: ...
def list(
    of: Generator[T],
    *,
    min_size: int = 0,
    max_size: int | None = None,
    unique: bool = False,
) -> Generator[list[T]]: ...
def dict(
    keys: Generator[K],
    values: Generator[V],
    *,
    min_size: int = 0,
    max_size: int | None = None,
) -> Generator[dict[K, V]]: ...
def string(
    *, alphabet: str | None = None, min_size: int = 0, max_size: int | None = None
) -> Generator[str]: ...
def bytes(*, min_size: int = 0, max_size: int | None = None) -> Generator[bytes]: ...
def duration(lo: int, hi: int) -> Generator[int]: ...
def permutation(*values: T) -> Generator[list[T]]: ...
def string_matching(pattern: str) -> Generator[str]: ...
def recursive(
    base: Generator[T],
    extend: Callable[[Generator[T]], Generator[T]],
    *,
    max_leaves: int = 100,
) -> Generator[T]: ...
def composite(f: Callable[[Case], T]) -> Generator[T]: ...
```

`prop.float`, `prop.list`, `prop.dict` and `prop.bytes` shadow builtins
inside the package `prop`, so its own code refers to the builtins through
the module `builtins`. `prop.duration` takes and generates nanoseconds,
because the generator of the definition decodes a duration in
nanoseconds. Python states such a duration as an `int`, as
`time.monotonic_ns` returns one.

A property form takes the arguments of its assertion, with a function of
the input in place of each value. The form reads the type of the input
from the annotation of the first parameter of the function, through
`typing.get_type_hints`. A function of more than one parameter generates
its parameters in order, as the fields of a record:

```python
def equal(
    seat: Seat,
    got: Callable[[T], U],
    want: Callable[[T], U],
    msg: str,
    *options: FormOption,
) -> None: ...


def total(order: Order) -> int:
    return sum(line.price * line.quantity for line in order.lines)


prop.in_range(seat, total, 0, 2**63 - 1, "a total is never negative")
```

A function whose first parameter has no annotation, such as a lambda, ends
the form with a fault. The text of the fault contains the name of the
function. Every other form follows the same pattern. `prop.max_allocs`
and `prop.max_allocs_with_setup` remain declined, as their assertions are.

The derived inputs:

```python
def of(t: type[T]) -> Generator[T]: ...
def shape_of(t: type) -> str: ...
def of_shape(text: str) -> Generator[Any]: ...
def register(t: type[T], generator: Generator[T]) -> None: ...
def register_values(t: type[T], *values: T) -> None: ...
def register_variants(t: type, *variants: type) -> None: ...
def using(t: type[T], generator: Generator[T]) -> FormOption: ...
def example(*values: Any) -> FormOption: ...
def examples(*values: Any) -> FormOption: ...
```

`of` reads a type through `typing.get_type_hints(t, include_extras=True)`,
within the definition's table of type readers for Python. A constraint is
an argument of `typing.Annotated`:

- The reader maps the classes `Gt`, `Ge`, `Lt`, `Le`, `Interval`,
  `MinLen`, `MaxLen`, `Len` and `Timezone` of annotated-types onto the
  constraint table. It recognises each class by its module and its name,
  so the library does not import annotated-types.
- The markers of `prop` state the constraints that annotated-types does
  not have: `Width(bits, signed=True)`, `Pattern(regex)`,
  `Alphabet(characters)`, `AllowNan()`, `AllowInfinity()`, `Unit(name)`,
  `Scale(digits)` and `Version(number)`. Each is a frozen dataclass.
- A constraint that the table does not map, such as a `Predicate`, fails
  the read. The text of the failure contains the field and the
  constraint.

```python
@dataclass
class Line:
    sku: Annotated[str, Pattern(r"[A-Z]{3}-[0-9]{4}")]
    quantity: Annotated[int, Width(32), Ge(1), Le(99)]
    price: Annotated[Decimal, Scale(2), Ge(0)]
    placed: Annotated[datetime, Timezone(timezone.utc), Unit("ms")]
```

A registration after the first property of the process has started
raises `RuntimeError`, because the definition applies a registration to
the whole test process. Registrations go in a `conftest.py`. `shape_of`
raises `TypeError` for a type that `register` gave a generator without a
shape.

#### The rules of a run

- **A body.** The engine calls the body, and runs an awaitable that the
  body returns on the loop of the run.
- **Workers.** With `workers(n)` above 1, the engine runs cases on n
  threads of a `ThreadPoolExecutor`. It reports what a run on one worker
  reports, as the definition requires. Under the global interpreter lock
  the threads take turns, and on the free-threaded build they run at once.
- **The end of a case.** `assume`, a repeated label and a fatal failure
  raise an exception of the engine. Its class derives from
  `BaseException`, so an `except Exception` in a body does not catch it.
  Every later call of the case raises it again.
- **Cleanup.** The engine runs the cleanups after any kind of end, the
  last registered first. A failing cleanup does not stop the cleanups
  after it.
- **Numbers.** The source is SFC64 on Python integers, and the engine
  masks each result with `0xFFFF_FFFF_FFFF_FFFF`. Choices, seeds and tokens
  are Python integers. `integer(lo, hi)` refuses two bounds that are not
  both inside the signed or both inside the unsigned 64-bit range.
- **Floats.** Width 32 rounds through the format `f` of `struct`. A NaN
  has the bits `0x7FF8000000000000`.
- **Text.** A string generator iterates by code point and never produces
  a surrogate code point. A token decodes through a strict base64url
  reader, because `base64.urlsafe_b64decode` accepts `+`, `/` and padding.
- **Dates and times.** A date or time shape decodes to `date`, `time`,
  `datetime` or `timedelta`. Each of these types has a resolution of one
  microsecond. An instant and a duration at nanoseconds decode to an `int`
  of nanoseconds. `time.time_ns` and `time.monotonic_ns` state the same
  values as an `int`. The decoder refuses every other date or time shape
  at nanoseconds. Definition 8.0.0 states this limit. The type reader
  never reads a shape at nanoseconds, because no type in its table
  represents one.
- **Zones.** The zoned shapes take their zones and their changes from the
  definition's zone table. A generated value resolves its zone through
  `zoneinfo.ZoneInfo`, as the limit of definition 8.0.0 states.
- **The store.** A run stores its failures under
  `testdata/prop/<path>/<test>/`, relative to the working directory, as
  `golden.match` resolves its files. `<path>` is the path of the test's
  module relative to pytest's root directory, and `<test>` is the name of
  the item with its class and its parameters. The store escapes each
  character that a file name cannot contain. A seat outside a pytest item,
  such as a `Standard` seat or a `Recorder`, does not have a store
  directory unless `prop.store` states one.
- **Variables.** A run that is not hermetic reads
  `DOKIMI_ASSERT_PROP_SEED`, `DOKIMI_ASSERT_PROP_PROFILE`,
  `DOKIMI_ASSERT_PROP_BUDGET` and `DOKIMI_ASSERT_PROP_REPLAY`, as the
  definition states.
- **Its report.** `prop.for_all` aborts only, so it reports through
  `fail`. The text of a counterexample renders each value with `repr`.

`prop.fuzz` replays the stored cases and the seed files on the seat, and
returns a target for Atheris:

```python
def fuzz(
    seat: Seat, contract: str, body: Callable[[Case], object], *options: Option
) -> Callable[[bytes], None]: ...
```

The library does not depend on Atheris. A suite that fuzzes passes the
target to `atheris.Setup` in a script of its own. Atheris 3.1.0 publishes
wheels for Python 3.12 to 3.14, and Atheris 3.0.0 for Python 3.11 to 3.13.

### Histories

```python
class History:
    def __init__(self) -> None: ...
    def invoke(
        self, client: int, operation: str, args: Sequence[Any], *keys: Any
    ) -> Call: ...
    def events(self) -> list[Event]: ...


class Call:
    def ok(self, output: Any) -> None: ...
    def fail(self, error: Any) -> None: ...
    def unknown(self, error: Any) -> None: ...


class Operation(Protocol):
    name: str
    args: tuple[Any, ...]
    known: bool
    output: Any

    def returned(self, value: Any) -> bool: ...


class Spec(Protocol[S]):
    def initial(self) -> S: ...
    def next(self, state: S, op: Operation) -> Sequence[S]: ...


def spec_from(
    factory: Callable[[], Callable[[str, Sequence[Any]], Any]],
) -> Spec[Any]: ...
def from_intervals(entries: Sequence[Interval]) -> History: ...
def concurrently(
    clients: int, within: float, body: Callable[[int], object]
) -> list[Outcome]: ...


def is_linearizable(
    seat: Seat, history: History, spec: Spec[S], msg: str, *options: Option
) -> None: ...
def is_serializable(seat: Seat, history: History, msg: str) -> None: ...
def has_snapshot_isolation(seat: Seat, history: History, msg: str) -> None: ...
```

- A spec can define `equal(a, b)`. A spec without it compares two states
  with the library's equality.
- `next` is synchronous. A spec describes a sequential object, and the
  search calls `next` once per state.
- `concurrently` starts one thread per client and releases them at once
  through a `threading.Barrier`. It waits `within` seconds on the
  platform clock and returns the outcome of each client. A client whose
  body raises fails the call after the wait, as a panic does in Go.
- A usage error of the history raises an exception, such as an `invoke`
  for a client whose call is still open.
- A spec function that raises ends the check with a fault.
- `history.workers(n)` checks n partitions at a time on threads.

### Machines and the task scheduler

```python
class Machine(Protocol[S]):
    spec: Spec[S]
    actions: Sequence[Action[S]]


@dataclass(frozen=True)
class Action(Generic[S]):
    name: str
    run: Callable[[Case, int, Any], object]
    weight: int = 1
    drain: bool = False
    enabled: Callable[[S], bool] | None = None
    input: Callable[[Case, S], Any] | None = None


def steps(case: Case, machine: Machine[S], *options: Option) -> None: ...


class Scheduler(asyncio.AbstractEventLoop):
    def __init__(self, case: Case, strategy: Strategy) -> None: ...
    def spawn(self, task: Callable[[], Coroutine[Any, Any, object]]) -> None: ...
    def run(self) -> None: ...


def uniform() -> Strategy: ...
def pct(depth: int) -> Strategy: ...
```

- A machine can define `invariant(case, state)` and `settle(case, state)`.
- The scheduler is the event loop of its tasks. Each task is a coroutine.
  An `await` of a future that the loop has not resolved ends the turn of
  the task, and the strategy chooses the next ready task to release.
- The scheduler calls `send` on the coroutine of each task itself, so it
  can find the task that each ready callback resumes. It implements the members of the
  loop that futures, locks, events, queues and `asyncio.sleep` call.
- `asyncio.sleep` and `call_later` advance a virtual clock of the
  scheduler. A run does not spend real time on them.
- A member for sockets, pipes, subprocesses or signals ends the run with
  a fault. The text of the fault contains the name of the member.
- The overlay declines `scheduler.yield`, because an `await` already
  suspends a task at a point that the loop sees.
- A concurrent section runs as tasks of a scheduler or on threads, as the
  overlay states with the sections `tasks` and `threads`.

### Trees of files and golden trees

```python
Tree = Mapping[str, Entry]


class Entry:
    def with_mode(self, mode: int) -> Entry: ...


def text(content: str) -> Entry: ...
def bytes(content: bytes) -> Entry: ...
def executable(content: str) -> Entry: ...
def directory() -> Entry: ...
def link(target: str) -> Entry: ...


def workspace(seat: Seat, tree: Tree) -> str: ...
def write(seat: Seat, dir: str, tree: Tree) -> None: ...
def read(seat: Seat, path: str) -> str: ...


def equal(seat: Seat, dir: str, want: Tree, msg: str) -> None: ...
def contains(seat: Seat, dir: str, want: Tree, msg: str) -> None: ...
def unchanged(seat: Seat, dir: str, fn: Callable[[], object], msg: str) -> None: ...
def absent(seat: Seat, path: str, msg: str) -> None: ...
def is_file(seat: Seat, path: str, msg: str) -> None: ...
def is_dir(seat: Seat, path: str, msg: str) -> None: ...
def links_to(seat: Seat, path: str, target: str, msg: str) -> None: ...
def has_content(seat: Seat, path: str, want: str | bytes, msg: str) -> None: ...
def has_mode(seat: Seat, path: str, want: int, msg: str) -> None: ...
```

```python
# golden
def match_tree(
    seat: Seat, name: str, dir: str, update: bool, *scrubbers: Scrubber
) -> None: ...
```

- A path is a `str`, as the definition states for Python.
- `workspace` needs a seat with a method `cleanup(fn)`. The `Collector`
  of the fixture and `prop.Case` have one, and the fixture runs the
  cleanups after the test, also after a failed one. A seat without
  `cleanup` ends the call with a fault.
- On POSIX, a write opens each directory with `O_DIRECTORY` and
  `O_NOFOLLOW`. It creates each entry in it through the argument `dir_fd`
  of `os.open`, `os.mkdir` and `os.symlink`. It then sets the mode of the
  entry with `os.fchmod` on the descriptor of the entry, so the umask does
  not decide a mode. Directories get their modes after their entries.
- On Windows, no function of `os` accepts `dir_fd`, so a write reads every
  parent with `os.lstat` before it creates an entry. A mode is not recorded
  there, so `has_mode` ends with a fault, and the conformance driver skips
  the vectors with a mode, as the definition permits.
- Content compares as bytes. A failure states content as text when the
  content is valid UTF-8, and as bytes otherwise. Paths sort by the bytes
  of their UTF-8.
- `golden.match` and `golden.match_tree` resolve a name against
  `testdata/golden`, relative to the working directory. An update makes
  the golden directory equal to the tree, and deletes every entry that the
  tree lacks.

### Bench

```python
class Contract:
    def warmup(self, iterations: int) -> Contract:
        """State iterations that loop runs before the measured ones, and chain.

        Raises:
            ValueError: iterations is negative, or loop has started.
        """
```

`loop(n)` yields the warm-up iterations, then the n measured ones. No
ceiling covers a warm-up iteration.

### Tests and CI

- **Drivers.** A driver for each vector family runs every vector of 8.0.0
  against both surfaces where an assertion has both. Each driver states
  its verdict with pytest's own `assert`, never with the library.
- **The completeness gate.** The gate expects 110 assertions and reads
  the four new packages. It counts the parameters of every function.
- **Coverage.** The floor rises from 95% to 100% of statements and
  branches.
- **Umask.** The file tests run under the umasks 022, 027 and 077.
- **CI.** CI runs Python 3.11 to 3.14 on Linux, and adds a job each on
  Windows and macOS on Python 3.14.

### What fails, and where

| Event | Effect | Response |
|---|---|---|
| An async test calls an assertion whose callable is a coroutine function | No second loop can run in the thread | The assertion ends with a fault, and its text contains the name of the assertion |
| A body catches the exception that ends a case | The case continues past its end | The class derives from `BaseException`, and every later call of the case raises it again |
| A task of the scheduler opens a socket | The scheduler does not perform I/O | The member ends the run with a fault, and its text contains the name of the member |
| A test on Windows derives a zoned value without the `tzdata` package | `zoneinfo` does not find the zone | The read ends with a fault, and its text contains the name of the zone |
| The function of a form does not have an annotation | The form cannot read the type of its input | The form ends with a fault, and its text contains the name of the function |
| A spec function raises | The search cannot continue | The check ends with a fault |
| A golden directory contains input fixtures | An update deletes them | The docstring of `golden.match_tree` states the rule |
| A test runs on Windows | A mode is not recorded | `has_mode` ends with a fault, and the driver skips the mode vectors |

### Bounds

- The search of `is_linearizable` stops at the budget of 10,000,000
  steps per partition, at its memo limit and at its time limit. The
  definition's Python reference spent 18 to 23 seconds on the full budget,
  at about 2 µs per step.
- A property stops shrinking at 2,000 runs or 30 seconds.
- `workers` runs at most n threads, and the history search checks at most
  n partitions at a time.

## Alternatives considered

### A. One definition version at a time

The library would vendor each version from 1.2.0 to 8.0.0, one after
another, and pass the gate at each.

**Why not:** CI fails a change that vendors a copy other than `main` of
assert-spec. An intermediate version would pass CI only if assert-spec
tagged each version and CI compared the copy with the tag. Each step
would also build code that a later version changes, such as `rejects`.

### B. Hypothesis as the engine

The forms and `for_all` would wrap Hypothesis.

**Why not:** the definition fixes the source, the decoding of each
generator, the shrink passes and the token. Hypothesis has its own, so it
would produce other inputs from the same seed and fail the 430 property
vectors. Hypothesis is also under the Mozilla Public License 2.0, and the
library is under MIT.

### C. The code of the executable reference

The definition's reference of the fixed algorithms is written in Python.
The library would take its code as the engine.

**Why not:** the reference computes the vectors. An engine of the same
code would pass every vector by construction, so the vectors would not
check it. The reference also does not have a seat, options or
assertions, and it does not read or write files.

### D. An async variant of each name

`prop.for_all_async`, `history.concurrently_async` and an async variant of
every relation would serve an async test.

**Why not:** the naming table gives each id one name, so every variant
would be a public name outside the table, about 60 of them. A test that
needs a running loop of its own calls the subject inside a plain `def`
instead.

### E. A coroutine as the result of a call

`prop.for_all` and the relations would return a coroutine when the body
is a coroutine function, and an async test would await it.

**Why not:** a plain `def` test that drops the coroutine passes without
running the body. Python only warns about a coroutine that nobody
awaited. The warning does not fail the test.

### F. Workers in processes

`prop.workers` and `history.workers` would run their work in processes.
Processes run at once under the global interpreter lock.

**Why not:** a body, a spec and an action are functions. Many of them are
closures, and `pickle` refuses a closure. The engine therefore cannot send
that work to another process.

### G. A `tzinfo` of the library, built from the zone table

The engine would build a `tzinfo` for each zone from the definition's zone
table. It would not need data from the platform.

**Why not:** a field of type `ZoneInfo` needs a `ZoneInfo`. Code under test
compares zones by their key. It would then receive zones of a kind that
callers do not construct.

## Drawbacks

- **Size.** The TypeScript library implements the same definition in
  33,888 source lines and 42,997 test lines, measured on 2026-10-11. Its
  property engine is 15,238 of those source lines. The Python work is
  likely of the same order.
- **Speed.** The engine and the history search run as pure Python. The
  full budget of the history search costs about 20 seconds per partition.
- **Changes for callers.** `rejects` returns failure records instead of a
  message. `matches` refuses patterns outside the portable subset.
  `length` refuses a string with a surrogate code point, and a `dict`
  finds a key as `equal` compares keys. `completes_within` fails at the
  deadline, and the subject runs on in a daemon thread after the test.
- **Time zones.** A test that derives a zoned value on Windows needs the
  `tzdata` package. A date or time at nanoseconds has no Python value
  except an `int`.
- **The definition.** Definition 8.0.0 contains two Python limits and one
  Python skip.
- **The free-threaded build.** CI runs the default build of CPython. On
  the free-threaded build, the threads of `workers`, of `concurrently` and
  of the section `threads` run at once, and no CI job covers that build.
- **Records.** Only the `seat` fixture writes the records of a test into
  a report.
- **Mutation testing.** dokimasia has no mutation engine for Python, so
  coverage is the only measure of the tests.

## References

| What | Where |
|---|---|
| The definition, its corpus, its vectors and the overlay format | <https://github.com/dokimasia/assert-spec> |
| The table of type readers, the constraint table and the units of the date and time shapes | assert-spec RFC-0011, "Reading a type into a shape" and "Constraints": <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0011-property-forms-and-derived-inputs.md> |
| The generators, the fuzz bridge and the tiers of the engine | assert-spec RFC-0010: <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0010-properties-over-generated-inputs.md> |
| The task scheduler on an event loop for asyncio | assert-spec RFC-0012, lines 575 to 579: <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0012-machines-simulation-and-campaigns.md> |
| The cost of the reference's history search: 18 to 23 seconds for the full budget, about 2 µs per step | assert-spec RFC-0004, lines 360 to 362 and 616 to 620: <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0004-the-history-checker.md> |
| A `dict` finds a NaN needle under the key of its own object | assert-spec RFC-0017, line 37: <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0017-pinning-map-keys.md> |
| `len`, `re.search` and `in` against the results that 2.0.0 pins | assert-spec RFC-0014, lines 34 to 41: <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0014-pinning-the-answers-languages-disagree-on.md> |
| The call record, the typed literals and the references of Python | assert-spec `spec/recording.md` and `spec/encoding.md`: <https://github.com/dokimasia/assert-spec/tree/main/spec> |
| The Python overlay at 7.2.1, and the zone limits of the Go overlay | <https://github.com/dokimasia/assert-spec/blob/main/overlays/python.json>, <https://github.com/dokimasia/assert-spec/blob/main/overlays/go.json> |
| pytest writes each user property of a test into its `testcase` in every family, and `record_property` warns under `xunit2`, the default | pytest 9.1.1: `_pytest/junitxml.py`, lines 490 to 500, 259 to 292 and 415 to 418 |
| `asyncio.Runner`, and the functions that `os.supports_dir_fd` lists on Linux | Python 3.11.15, measured on 2026-10-11 |
| No function accepts `dir_fd` on Windows | <https://docs.python.org/3.11/library/os.html#os.supports_dir_fd>: "Currently dir_fd parameters only work on Unix platforms; none of them work on Windows." |
| `base64.urlsafe_b64decode` accepts `+` and `/` | Python 3.11.15: `urlsafe_b64decode("ab+/")` returns `b'i\xbf\xbf'` |
| Atheris releases | <https://pypi.org/project/atheris/>: 3.1.0 of 2026-06-17 has wheels for CPython 3.12 to 3.14, and 3.0.0 for 3.11 to 3.13 |
| The TypeScript implementation of the same definition, and its size | <https://github.com/dokimasia/assert-typescript/blob/main/docs/rfc/0003-definition-7-2-in-typescript.md>; `src` and `tests` counted with `wc -l` on 2026-10-11 |
| Go's implementation of the same definition | <https://github.com/dokimasia/assert-go> |
