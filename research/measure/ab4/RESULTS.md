# A/B run 4: projection wording, current vs facts-only (2026-10-11)

Run 4 changes only one thing: the wording of the text G1 injects. It tests a hypothesis from run 3, that the wording made the agent do extra work.

How to read the table. Every number comes from the runner, which re-ran the original tests on the final code; G1's
ledger and the agent's words were never used as outcomes. "Paired delta" compares the two arms on the same task and
repeat, and the bracket is a 95% bootstrap interval. If the bracket contains zero, the difference is not established.

Same five strict fixtures as run 3, 2 repeats, G1 on in both arms. Arm `on`: the current projection (facts plus
'G1 verifies at the end of the turn' and 'completion is granted only by G1 receipts; your own summary never completes
a task'). Arm `on_facts`: the same facts with those two directive lines removed. Everything else identical.

| Metric | current wording (n=10) | facts-only (n=10) | Paired delta facts-only minus current (95% bootstrap, 10 pairs) |
|---|---|---|---|
| Verified pass | 10/10 | 10/10 | 0 |
| False DONE | 0/10 | 0/10 | - |
| Tokens (median) | 212,384 | 247,599 | +11,578 [-10,831, 39,127] |
| Wall seconds (median) | 155.1 | 163.0 | -4.4 [-19.9, 10.0] |
| Tool calls (median) | 23 | 25 | +2.4 [-0.9, 5.7] |
| G1 ledger says complete | 10/10 | 10/10 | agrees with the oracle 20/20 |

## Reading

- The hypothesis from run 3 (the completion-directive lines make the agent run more tool calls) is not supported: removing
  them did not reduce tool calls, tokens or time; every interval includes zero, and the point estimates lean the other way.
  The run-3 gap (27 vs 20 tool calls) was within session-to-session noise on these tasks (per-fixture tool calls vary 9-22 for the same task).
- Removing the directive lines did not produce false DONE either (0/10), so honesty on this task class does not depend on the lines.
- Decision: keep the current wording. It costs nothing measurable and states the completion rule explicitly.
- Across runs 1-4 (40 pairs, 80 sessions): G1's verdict agreed with the independent oracle in 40/40 on-arm sessions; Flash high
  failed 0/40 natively on self-contained Python tasks with visible tests.
