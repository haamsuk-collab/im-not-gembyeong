# Response to review round 5

The fifth independent review (`AGY-AUDIT-5.md`, Gemini 3.8 Flash in an agy session, 2026-10-12, 18 minutes) examined
G1 at `63fc78f`: it reproduced every round-4 fix (R4-01 to R4-09) and every pre-audit fix (opus and fable P5-01 to
P5-04, the corrupt-head fix) with its own scripts, attacked the code added since round 4 and the whole again, measured
the hooks, and reported **no finding at any severity**: the findings table is empty. Its ten suggested tests (section
M) are advice, not findings, and are answered below.

This is the first round that ends without a finding, and the owner's condition for publishing. The code it reviewed
is unchanged in this commit: `git diff 63fc78f..HEAD -- src` is empty; what this commit adds is the record of the
round, two tests from its suggestions, and the counts in the documents.

## What the author verified

- The reviewer's scripts (`/tmp/g1-review5/test_section_a.py` to `test_section_k.py`) were rerun unchanged by the
  author on the same code after the review:

| Script | Section | Rerun |
|---|---|---|
| `test_section_a.py` | A, round-4 fixes R4-01 to R4-09 with variations | exit 0, every row `fixed` |
| `test_section_b.py` | B, pre-audit fixes with variations (the 1 MiB boundary, a line straddling the 16 KB cut, FIFO entries, tampered mirror hashes, 4 proposals with 2 deferred) | exit 0, every row `fixed` |
| `test_section_c.py` | C, the new functions on hostile input | exit 0 |
| `test_section_d.py` | D, the witness and restore matrix | exit 0, no false lockdown, no missed forgery, no dead end |
| `test_section_e.py` | E, the decision commands and ancestry | exit 0 |
| `test_section_f.py` | F, the gate: ordinary commands allowed, G1 command lines refused, cost 7.7 ms at 10 KB to 96 ms at 1 MiB | exit 0 |
| `test_section_g.py` | G, the scratch walker | exit 0 |
| `test_section_h.py` | H, claims: two processes, 100 rounds, dead claims | exit 0 |
| `test_section_i.py` | I, challenges: `only` by id, double acceptance refused, 1 MiB file, 500 pending listed in 193 ms | exit 0 |
| `test_section_j.py` | J, the status block in every state at 512 and 1,024 bytes; escaping | exit 0 |
| `test_section_k.py` | K, speed: fresh processes and one long process at 1, 2,000 and 5,000 records; stress inputs; component costs; per-call imports | exit 0: fresh processes 10.6 ms PreToolUse and 13.4 ms PreInvocation; one long process 5.7 to 11.7 ms median at every ledger length, first 100 calls equal to the last 100; 30 pending proposals 189 ms; a 20 MB journal rotated, 7.9 ms; `append` 28 ms; `register` on 2,000 files 4.3 s; `turn_end` on them 7.2 s; idle Stop at 10,000 records 168 ms; no check-running module imported by a per-call hook |

- The unit suite at this commit: 126 tests, `OK` (124 at the reviewed commit, plus the two below).
- Section N: the two refusals the reviewer met are the ones designed for it (`python3 -c "import g1..."` from the
  agent's shell, and a `tail` of the conversation store), and the status block it quotes is the no-contract block.

## The ten suggestions (section M), one by one

| M | Suggestion | Answer |
|---|---|---|
| 1 | A multi-line commit message with a decision keyword on a later line is not refused | Already so: `repair` alone is not a G1 command line (the gate looks for `g1`, `g1.pyz`, `-m g1`, G1 imports); `git commit -m 'g1 repair'` is covered by `test_r3_04`/`test_r3_22`. Not added. |
| 2 | `_read_mirror` stops at the first record whose hash does not verify | Already so: `check_chain_step` is applied to every record and the reader returns the verified prefix with the note; covered by the `_read_mirror` note assertions in `test_r4_01_a` and `test_p5_03`. Not added. |
| 3 | A race between `_unclaim` and another process's `_claim` | The descriptor's lock is held until after the rename back, and a `.running.json` is only taken over when its lock is free and it is older than the grace period; `test_h` of the reviewer (two processes, 100 rounds) and `AgentFileTests` cover the claim protocol. Not added. |
| 4 | A FIFO as a target | Covered since round 3: `test_r3_05_r3_14_fifo_and_unreadable_files_are_skipped_not_fatal` (a FIFO target fails the red baseline as "required path ... not a regular file"). Not added. |
| 5 | Accepting a challenge whose task id exists | Covered: `test_r3_10_a_challenge_cannot_name_an_existing_task` and `_commit_contract`'s re-check. Not added. |
| 6 | The exact 1 MiB boundary | 1 MiB + 1 byte refused is `test_p5_01_b`; the reviewer ran the exact boundary (section B). Not added. |
| 7 | `--restore` on a ledger file emptied to 0 bytes | Verified and added: `test_r5_m7_an_empty_ledger_file_is_restored_from_the_mirror` (the state is `unverifiable`, `--restore` rebuilds the chain, `check_anchor` is `ok`). |
| 8 | `short_ids` with 64 ids of 64 characters stays within its byte cap | Covered by `test_r4_09` (64 checks, lines bounded). Not added. |
| 9 | A process whose parent is init | Verified and added: `test_r5_m9_a_parent_of_init_is_recorded_as_no_parent` (the chain is empty, the decision runs and records `no parent`: the double-fork residual of design 7.7, recorded rather than prevented). |
| 10 | The audit does not demand a contract for an `unproven` or `invalid` challenge | Already so: the check applies only to `decision == "accepted"`; `test_p5_l_audit_flags_an_accepted_challenge_without_a_contract` records a confirmed challenge without a decision and asserts the audit is ok before the acceptance. Not added. |

## Suspicion in section O

A SIGKILL between `_claims.pop()` and the rename in `_unclaim` leaves a `.running.json` whose lock is gone: the next
call treats it as an abandoned claim and answers it unread ("G1 stopped before the validation finished ... write the
proposal again"), as the reviewer says. The window is a few microseconds inside a hook that the host does not kill at
that point (the time limit is 900 s), and the outcome is an honest answer, not a lost record. Not changed.

## Speed, as the reviewer measured it

Per-call hooks 6 to 12 ms median in one long process at 1, 2,000 and 5,000 records with no growth from the first 100
calls to the last 100; fresh processes 11.7 ms PreToolUse and 14.5 ms PreInvocation; 30 pending proposals cost one
PreInvocation 115 ms (two baselines run, 28 deferred); a 20 MB journal is rotated; the per-call hooks import none of
the check-running modules. The once-per-decision and once-per-idle-Stop costs on a 2,000-file tree (4.5 s and 6.8 s
here) are the documented tree copies and hashes (design 6.1, 7.2).
