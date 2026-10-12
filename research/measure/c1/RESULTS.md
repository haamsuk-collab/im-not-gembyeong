# Experiment C1: a second model as a reviewer that must prove each defect (2026-10-11)

C1 runs the challenge pipeline of design section 5.5 once, end to end, on a task with a written specification, and
measures each step against an oracle that no model saw.

How to read the numbers. The worker and the fixer are Gemini 3.8 Flash at effort high, the reviewer is Claude Opus 5.5
at effort high, all in agy 1.3.3 with G1 installed. The hidden oracle (`hidden_oracle.py`, 44 cases, one per rule of
`project/SPEC.md`) passes on the reference implementation (`reference/semver.py`) and fails every case on the stub. It
was never in a workspace. A reviewer's expectation counts as right when its check passes on the reference.

## The pipeline

| Step | Who | Time | Tokens | Result |
|---|---|---|---|---|
| 1. Build `semver.py` from SPEC.md and 6 visible tests | Flash | 169 s | 185,771 | G1 complete, canary sensitive. Hidden oracle 43/44: `"1.2.3\n"` is accepted. |
| 2. Review against SPEC.md, every finding as a challenge | Opus | 73 s | 59,393 | 1 challenge, G1 verdict confirmed. Its check passes on the reference: the expectation is right. |
| 3. Decide | the user | | | accepted; the contract was registered from the challenge |
| 4. Fix, told only "Continue the work in this workspace." | Flash | 365 s | 343,551 | G1 complete, canary sensitive. Hidden oracle 44/44. |

Step 2 in detail. The reviewer found the one defect the oracle finds and named its cause: both regular expressions
end in `$`, which in Python also matches before a final newline. Its check tried six inputs where the oracle tried one
(`'1.0.1\n'`, `'1\n.2.3'`, `'1.2.3\n-rc'`, `'1.2.3-rc\n'`, `'1.2.3-rc\n.1'`, `'1.2.3+b\n'`), so the fix covered every
position. It reported nothing false, and it left out one behaviour on purpose (`bump('0.0.0-rc.1', 'major')`) because
SPEC.md does not decide it; the reference gives the same answer as the worker there. It wrote nothing in the
workspace (the implementation's hash was unchanged).

## What step 4 showed, and the A/B that followed

The fix cost more than the build. G1's journal showed why: the status block named the contract's objective and
"checks ['K1']: not yet verified", but not the check's command, which was inline code the fixing agent had never
seen. Any contract the current agent did not write has this gap. G1 now names the first open check and its command in
the status block, and at session start also the challenge claim and the path of `views/contract.json`.

The A/B repeated step 4 from the same state (the worker's code before the fix, rebuilt exactly, the same accepted
challenge) with the old block (`no_check_cmd`) and the new one (`default`), three times each, interleaved. Rows:
`fix_ab_rows.jsonl`; script: `fix_ab.py`.

| Metric | new block (n=3) | old block (n=3) | Paired delta new minus old (3 pairs) |
|---|---|---|---|
| G1 complete | 3/3 | 3/3 | 0 |
| Hidden oracle failures after the fix | 0 | 0 | 0 |
| Tokens (median) | 204,047 | 247,137 | -55,391 [-119,775, -11,788] |
| Wall seconds (median) | 155 | 221 | -86 [-129, -38] |
| Mutating tool calls (median) | 27 | 34 | -9.7 [-21, -1] |

## Reading

- The pipeline worked as designed on its first run: a failing check proved the defect, G1 recorded it as confirmed,
  the decision stayed with a person, and the fix was verified by a receipt and by the hidden oracle (43/44 to 44/44).
- The reviewer was precise (1 of 1 confirmed with a right expectation, no false report) and found the whole defect
  class, not only the oracle's one input. With one defect in the task, this is an existence proof, not a rate.
- Showing the open check's command made the fix cheaper in all three pairs: about 22% fewer tokens and a third less
  time, with the same outcome. Three pairs give wide intervals; the direction is consistent.
- Limits: one task, one reviewer run, Flash already near the ceiling on this task (43/44). The questions C1 cannot
  answer yet: the reviewer's precision when the code has many defects, and how often a confirmed challenge carries a
  wrong expectation (review round 1 had one such case in 20 findings).
