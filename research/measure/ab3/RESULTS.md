# A/B run 3: five strict fixtures, G1 on vs off (2026-10-11)

Run 3 uses five strict tasks (a JSON parser, a regex engine, a markdown renderer, a multi-file scheduler, word wrapping) that even our own reference solutions got wrong at first.

How to read the table. Every number comes from the runner, which re-ran the original tests on the final code; G1's
ledger and the agent's words were never used as outcomes. "Paired delta" compares the two arms on the same task and
repeat, and the bracket is a 95% bootstrap interval. If the bracket contains zero, the difference is not established.

agy 1.3.3, gemini-3.8-flash-high. Fixtures: strict JSON parser (29 invalid inputs), mini regex engine (needs an NFA;
naive backtracking loops on `(a*)*b`), markdown renderer (24 exact HTML cases), multi-file job scheduler (3 modules),
word wrap (exact output). 5 x 2 arms x 2 repeats = 20 sessions, same prompt, contract pre-registered in the on arm.

| Metric | G1 on (n=10) | G1 off (n=10) | Paired delta on-off (95% bootstrap, 10 pairs) |
|---|---|---|---|
| Verified pass | 10/10 | 10/10 | +0.00 |
| False DONE | 0/10 | 0/10 | - |
| Tokens (median) | 218,825 | 214,021 | +14,483 [-2,878, 31,482] |
| Wall seconds (median) | 167.9 | 158.9 | +19.3 [-1.5, 37.8] |
| Tool calls (median) | 27 | 20 | - |
| G1 ledger says complete | 10/10 (agrees with the oracle 10/10) | - | - |

## What G1 did in the on arm

One verification attempt per session, no continuations, at most one refused call per session (the agent asking to list `.g1`),
14-46 per-call injections of about 500 bytes, Stop verification 0.6-0.7 s. Direct hook time per session about 3-5 s of 150-220 s.

## Reading

- Correctness still did not separate: Flash (high) passed all 20 sessions, including the regex engine and the multi-file task.
  After three runs (60 sessions) its native failure rate on self-contained Python tasks with visible tests is 0/30. A correctness or
  false-DONE effect of G1 cannot be measured on this class of task; it needs tasks the model fails (larger codebases,
  multi-session work, or tasks without a runnable oracle visible to the agent).
- Cost did not improve here: +14k tokens (+7%) and +19 s, both intervals include zero. On hard tasks the session is dominated by
  the agent's own edit-test loop, which G1 does not shorten; the projection's scope and command hints help less when the agent is
  not exploring. The on arm made more tool calls (27 vs 20 median), consistent with extra self-verification after the injected
  'completion is granted only by G1 receipts' line. Run 4 tests that wording as a variable.
- Across runs 1-3 (30 pairs): easy and medium tasks -24% and -17% tokens with intervals excluding zero; hard tasks +7% with an
  interval including zero. G1's verdict agreed with the independent oracle in 30/30 on-arm sessions.
