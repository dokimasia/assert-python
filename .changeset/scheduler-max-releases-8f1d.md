---
"dokimi-assert": minor
---

**Breaking:** Fail a case whose `Scheduler.run` or `Scheduler.advance` releases `stateful.max_releases` tasks, 1,000,000 by default, while a task is still ready.
