# A/B run 2: six harder fixtures, G1 on vs off (2026-10-11)

Run 2 repeats run 1 with six harder tasks. Each task has edge cases that are easy to miss.

How to read the table. Every number comes from the runner, which re-ran the original tests on the final code; G1's
ledger and the agent's words were never used as outcomes. "Paired delta" compares the two arms on the same task and
repeat, and the bracket is a 95% bootstrap interval. If the bracket contains zero, the difference is not established.

agy 1.3.3, gemini-3.8-flash-high, 6 fixtures (roman numerals, interval merge, LRU cache, mini CSV, topological sort,
time ranges; each with validation and edge cases) x 2 arms x 2 repeats = 24 sessions, same prompt in both arms. Every
fixture was validated beforehand (stub fails, reference solution passes).

| Metric | G1 on (n=12) | G1 off (n=12) | Paired delta on-off (95% bootstrap, 12 pairs) |
|---|---|---|---|
| Verified pass | 12/12 (Wilson 76%-100%) | 12/12 | +0.00 |
| False DONE | 0/12 | 0/12 | - |
| Tokens (median) | 105,530 | 124,698 | -21,566 [-34,933, -8,687] |
| Wall seconds (median) | 53.5 | 79.2 | -19.0 [-33.6, -6.4] |
| Tool calls (median) | 10 | 13 | - |
| G1 ledger says complete | 12/12 (agrees with the oracle 12/12) | - | - |

## Reading

- Correctness still did not separate the arms: Flash (high) passed every fixture in both arms. The fixtures were harder
  (validation, immutability, deterministic ordering, quoting rules) but not hard enough; a correctness effect, if any, needs tasks Flash fails sometimes.
- Cost moved the same way as in run 1 and by a similar amount: fewer tokens (-17% at the median) and less wall time (-32%) with G1 on,
  hook overhead included; both paired intervals exclude zero. Across runs 1 and 2 (20 pairs) the direction is consistent.
- G1's verdict agreed with the independent oracle in all 12 on-arm sessions. Over both runs: 20/20.
- Per-fixture token pairs are noisy: two of twelve pairs favoured the off arm. The effect is an aggregate one.
- Limits unchanged: fixtures by the G1 author, contract pre-registered in the on arm, one device, one day. Next: tasks with a
  measured native failure rate (multi-file changes, ambiguous specs), so that pass rate and false DONE can move.
