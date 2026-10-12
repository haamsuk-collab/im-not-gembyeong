# A/B run 1: G1 on vs off (2026-10-11)

Run 1 asks the simplest question: on easy tasks, does G1 change what Gemini does? Four small tasks, each run twice with G1 on and twice with G1 off.

How to read the table. Every number comes from the runner, which re-ran the original tests on the final code; G1's
ledger and the agent's words were never used as outcomes. "Paired delta" compares the two arms on the same task and
repeat, and the bracket is a 95% bootstrap interval. If the bracket contains zero, the difference is not established.

agy 1.3.3, gemini-3.8-flash-high, 4 fixtures x 2 arms x 2 repeats = 16 sessions, same prompt in both arms,
G1 arm with the contract registered from the CLI before the session. Rows: `rows.jsonl`.

| Metric | G1 on (n=8) | G1 off (n=8) | Paired delta on-off (95% bootstrap) |
|---|---|---|---|
| Verified pass | 8/8 (Wilson 68%-100%) | 8/8 | +0.00 |
| False DONE | 0/8 (Wilson 0-32%) | 0/8 | - |
| Tokens (median) | 109,037 | 130,937 | -31,038 [-50,856, -12,152] |
| Wall seconds (median) | 41.7 | 45.3 | -10.6 [-22.0, -2.2] |
| Tool calls (median) | 9 | 12 | - |
| G1 ledger says complete | 8/8 (agrees with the oracle 8/8) | - | - |

## Reading

- Correctness did not differ: every session in both arms passed. These fixtures are too easy to separate the arms on pass rate, but they do measure cost.
- With G1 on, sessions used fewer tokens and less wall time, hook overhead included, and the paired intervals exclude zero.
  The likely mechanism is the injected projection (exact scope, exact check command): the off arm explored more, up to 22 tool calls on f4-slug against 10-16.
- G1's completion verdict agreed with the independent oracle in all 8 on-arm sessions: no false completion and no refused true completion.
- Limits: 8 pairs; fixtures written by the G1 author; the on arm did not pay for writing the proposal (about one extra turn when the agent authors it, see E2E 1);
  one device, one day. By the runner's withholding rules (design section 10) this shows the direction of the effect; the size is not settled.
