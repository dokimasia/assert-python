# dokimi-assert

## 0.3.0

### Minor Changes

- 3f88eaa: Await a cleanup of the `seat` fixture that returns an awaitable.
- 3f88eaa: Run the cleanups of the check of `rejects` and of each attempt of `eventually` when the body ends.
- 7f27a74: **Breaking:** End the call of a property with the fault that ends a call in one of its cases.
- 7b16d96: Read a `complex` in `prop.of` and `prop.shape_of` as a record of the floats `real` and `imag`.
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
- 02fff2c: Add `max_live_bytes` to `check` and `expect`, a ceiling on the heap that a call keeps reachable at each call of a probe.
- 3f88eaa: Run a cleanup that a cleanup of the `seat` fixture registers in the same pass.
- 63f81a3: Add `dokimi_assert.call.Call`, and pass every assertion call to the member `observe_call` of a seat that has one.
- ef3e85e: Add `prop.on_result` and `prop.Result` to hand a function the result of each run of a property.
- 516ff81: Add `prop.run_seed` to return the seed that a run takes without `prop.seed`.
- 3f88eaa: Add `Recorder.cleanup` and `Recorder.run_cleanups`.
- 3f88eaa: Run the cleanups of the `recorder` fixture when the test ends.
- d0780e7: **Breaking:** Decode each value of a type with the position generator inside the extension of a stated `prop.recursive` generator of the type.
- c2462e6: Check histories of read-write register transactions with `history.is_serializable` and `history.has_snapshot_isolation`.
- 251c7c2: Add `skip` to the seat of the check of `rejects`, and end the call as skipped when the check skips before it fails.
- 3f88eaa: Add `seat.cleanup` to register a cleanup on any seat.
- 251c7c2: Write the reason of every skip into the field `reason` of its call record.
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
