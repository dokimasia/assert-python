# dokimi-assert

## 0.3.0

### Minor Changes

- e5be5ab: Add `stateful.Action.keep` to keep an action in every case without a swarm choice.
- 3f88eaa: Await a cleanup of the `seat` fixture that returns an awaitable.
- 3f88eaa: Run the cleanups of the check of `rejects` and of each attempt of `eventually` when the body ends.
- 7f27a74: **Breaking:** End the call of a property with the fault that ends a call in one of its cases.
- 7b16d96: Read a `complex` in `prop.of` and `prop.shape_of` as a record of the floats `real` and `imag`.
- f71960d: Replay a `prop.composite` in a trace after the entries of its draws, so a stored case of a composite replays its counterexample.
- cb9c4f4: Add `stateful.concurrent_mean` to set the mean number of steps of a concurrent section.
- e2bb347: Replay a draw of a `prop.one_of`, `prop.optional`, `prop.list`, `Generator.filter` or `prop.recursive` with a `prop.composite` inside in a trace after the entries of the composite's draws, so its stored case replays its counterexample.
- 76ae6b9: Add `option.equate_by` to compare the values of one type by a function of them.
- 7b16d96: Read a `Fraction` in `prop.of` and `prop.shape_of` as a record of the ints `num` and `den` in lowest terms.
- d0780e7: Implement definition 12.0.0 and write its version into every call record.
- 251c7c2: Implement definition 12.1.0 and write its version into every call record.
- 7b16d96: Implement definition 12.2.0 and write its version into every call record.
- 7f27a74: Implement definition 13.0.0 and write its version into every call record.
- 63f81a3: Implement definition 13.1.0 and write its version into every call record.
- 02fff2c: Implement definition 13.2.0 and write its version into every call record.
- c2462e6: Implement definition 13.3.0 and write its version into every call record.
- 3f88eaa: Implement definition 13.4.0 and write its version into every call record.
- 516ff81: Implement definition 13.5.0 and write its version into every call record.
- ef3e85e: Implement definition 13.6.0 and write its version into every call record.
- eb86802: Implement definition 14.0.0 and write its version into every call record.
- 76ae6b9: Implement definition 14.1.0 and write its version into every call record.
- cb9c4f4: Implement definition 14.2.0 and write its version into every call record.
- de38772: Implement definition 15.0.0 and write its version into every call record.
- 39e4ff6: Implement definition 16.0.0 and write its version into every call record.
- b03bc0c: Implement definition 16.1.0 and write its version into every call record.
- e5be5ab: Implement definition 16.2.0 and write its version into every call record.
- 6a051a1: Implement definition 16.3.0 and write its version into every call record.
- f71960d: Implement definition 16.4.0 and write its version into every call record.
- e2bb347: Implement definition 16.5.0 and write its version into every call record.
- eb86802: **Breaking:** Skip each configuration of the search of `history.is_linearizable` that its memo covers.
- de38772: **Breaking:** Report a lost update in `history.is_serializable` and `history.has_snapshot_isolation`.
- 02fff2c: Add `max_live_bytes` to `check` and `expect`, a ceiling on the heap that a call keeps reachable at each call of a probe.
- 3f88eaa: Run a cleanup that a cleanup of the `seat` fixture registers in the same pass.
- 63f81a3: Add `dokimi_assert.call.Call`, and pass every assertion call to the member `observe_call` of a seat that has one.
- eb86802: Add `prop.confirm` to replay every n-th valid case of a run from its choices.
- ef3e85e: Add `prop.on_result` and `prop.Result` to hand a function the result of each run of a property.
- 39e4ff6: **Breaking:** Add `prop.replays` and the fields `replays` and `reproduced` of the detail of a run, as `Result.replays` and `Result.reproduced`.
- 516ff81: Add `prop.run_seed` to return the seed that a run takes without `prop.seed`.
- 3f88eaa: Add `Recorder.cleanup` and `Recorder.run_cleanups`.
- 3f88eaa: Run the cleanups of the `recorder` fixture when the test ends.
- d0780e7: **Breaking:** Decode each value of a type with the position generator inside the extension of a stated `prop.recursive` generator of the type.
- c2462e6: Check histories of read-write register transactions with `history.is_serializable` and `history.has_snapshot_isolation`.
- 251c7c2: Add `skip` to the seat of the check of `rejects`, and end the call as skipped when the check skips before it fails.
- 39e4ff6: Add `Scheduler.advance` and `Scheduler.clock` to `stateful` to move and read the clock of a scheduler deadline by deadline.
- 39e4ff6: **Breaking:** Start the clock of `stateful.Scheduler` at midnight UTC 2000-01-01.
- 39e4ff6: **Breaking:** Fail a case whose `Scheduler.run` or `Scheduler.advance` releases `stateful.max_releases` tasks, 1,000,000 by default, while a task is still ready.
- 39e4ff6: **Breaking:** Return from `Scheduler.run` while a task is parked, without a move of the clock of the scheduler.
- 3f88eaa: Add `seat.cleanup` to register a cleanup on any seat.
- b03bc0c: Add `seat.skip` to skip the test of a seat from a helper, with a fault on a seat without the member `skip`.
- 251c7c2: Write the reason of every skip into the field `reason` of its call record.
- 6a051a1: Replay the recorded counterexample of a stored case whose choices decode to other values than its entry records.
- 6a051a1: Write the steps of a machine among the draws of a stored case in entries of format 2.
- 516ff81: Add `seat.write_record` to write a record of another kind into the user properties of a test.

### Patch Changes

- d0780e7: Fix `prop.of` to refuse a type at the draw, so `prop.using` can state the generator of a class that the reader does not read.
- 0ffada2: Fix `max_live_bytes` to report the same excess on each call, without the measurer's own objects in its readings.

## 0.2.0

### Minor Changes

- b8296ea: Add `Case.skip` to end the run of a property as skipped and skip its test.
- b8296ea: Implement definition 11.0.0 and write its version into every call record.

### Patch Changes

- 531ce81: Keep the error that ended an operation as the cause of its fault.
- 2a7328d: Fix `completes_within` to measure its wait with `time.perf_counter`, so a failure on Windows before Python 3.13 reports at least the duration.
