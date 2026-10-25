# dokimi-assert

## 0.2.0

### Minor Changes

- b8296ea: Add `Case.skip` to end the run of a property as skipped and skip its test.
- b8296ea: Implement definition 11.0.0 and write its version into every call record.

### Patch Changes

- 531ce81: Keep the error that ended an operation as the cause of its fault.
- 2a7328d: Fix `completes_within` to measure its wait with `time.perf_counter`, so a failure on Windows before Python 3.13 reports at least the duration.
