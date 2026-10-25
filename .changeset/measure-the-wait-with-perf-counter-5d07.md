---
"dokimi-assert": patch
---

Fix `completes_within` to measure its wait with `time.perf_counter`, so a failure on Windows before Python 3.13 reports at least the duration.
