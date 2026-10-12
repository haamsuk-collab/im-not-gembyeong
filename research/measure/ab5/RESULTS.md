# A/B run 5: resuming after a lost session (2026-10-11)

Run 5 tests G1's main purpose. A session is killed early, all of its records are deleted, and a new session is told only to continue. Does the work survive, and at what cost?

How to read the table. Every number comes from the runner, which re-ran the original tests on the final code; G1's
ledger and the agent's words were never used as outcomes. "Paired delta" compares the two arms on the same task and
repeat, and the bracket is a 95% bootstrap interval. If the bracket contains zero, the difference is not established.

Six fixtures (roman, intervals, LRU, CSV, topo, time ranges), each in a workspace with two unrelated passing modules.
Session 1 gets the task prompt and is cut after 25 s; every agy record of it is deleted; session 2 gets only
'Continue the work in this workspace.' Outcomes from the final tree: task test passes, the two unrelated tests still
pass, and only the task's source file changed (scope). Session-2 cost from agy's stream-json.

| Metric | G1 on (n=6) | G1 off (n=6) | Paired delta on-off (95% bootstrap, 6 pairs) |
|---|---|---|---|
| Resumed correctly (task + unrelated + scope) | 6/6 | 6/6 | 0 |
| Session 1 already finished within 25 s | 1/6 | 0/6 | - |
| False DONE | 0/6 | 0/6 | - |
| Session-2 tokens (median) | 153,815 | 240,407 | -93,556 [-159,115, -25,378] |
| Session-2 wall seconds (median) | 86.6 | 133.4 | - |
| Session-2 tool calls (median) | 14 | 33 | - |
| G1 ledger says complete | 6/6 (agrees with the oracle) | - | - |

## Reading

- Flash (high) resumed correctly in both arms. In a small repository with a visible test suite the task is rediscoverable:
  the off arm ran the tests, found the failing one and finished. Loss of work was not observed on this task class.
- G1 removes the rediscovery. With the projection (contract, check, scope) injected at session start, session 2 used
  39% fewer tokens (median 154k vs 240k; paired interval excludes zero), 35% less time (87 s vs 133 s) and less than half
  the tool calls (14 vs 33). The off arm spent 32-38 tool calls per session re-establishing what the work was.
- One on-arm session 1 (LRU) finished inside 25 s; its session 2 only confirmed completion from G1 facts. Excluding it, the
  on arm's advantage holds on the other five pairs.
- Scope stayed clean in both arms; no unrelated file was touched. No false DONE.
- Limits: 6 pairs, small repositories where the failing test is easy to find. Rediscovery cost grows with repository size
  and when the task has no visible failing test; that is where loss of work would appear, and it is not measured here.
