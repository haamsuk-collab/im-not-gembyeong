# Response to the pre-audit before round 5

Two fresh reviewers, Claude Opus 5.5 (`opus/REPORT.md`) and Claude Fable 5.1 (`fable/REPORT.md`), read the
round-4 code (`7a12dc3`) in their own git worktrees with the prompt in `PROMPT.md`, outside any agy session, with the
owner's installation off limits. The regression battery of every earlier reviewer's script ran first
(`BATTERY.md`). Every finding below was reproduced with the reviewer's own script before the fix and rerun after it;
each fix has a test named after the finding (`tests/test_core.py`, class `PreAuditRound5Tests`).

## Reviewer `opus`: 3 findings (high 1, medium 2) and one tripwire gap

| ID | Severity | Verdict | What was wrong | Fix | Test |
|---|---|---|---|---|---|
| P5-01 | high | confirmed, fixed | The textual gate tokenized the whole command line with `shlex`, which costs about a millisecond per KB and grows faster on one long token: a 400 KB `run_command` held PreToolUse for 1.7 to 6.4 s (measured: 100 KB 212 to 475 ms, 200 KB 0.5 to 1.7 s). The hard rule says no hook may slow the model on input the agent writes. | Only the first 16 KB of a command line, cut at whitespace, are tokenized (`GATE_TOKENIZE_BYTES`, `_split_for_gate`); the rest is scanned by the linear patterns (`CLI_DECISIONS`, `_PY_G1_RE`: a `g1` or `-m g1` token anywhere, Python that imports the package) and by whitespace tokens for the relative path names. Coarser past the cap, but bounded: the reviewer's `P501.py` now measures 31 / 50 / 89 ms for 100 / 200 / 400 KB. A `g1 repair` placed after 400 KB of filler is still refused. | `test_p5_01_a_long_command_line_does_not_hold_the_gate` |
| P5-02 | medium | confirmed, fixed | `_hold` still did `os.chmod(path, 0o600)` by path after an `lstat` check; a link swapped in between the two (a TOCTOU window) would have its target's mode changed, the hole R4-03 meant to close. Linux has no `lchmod`. | The chmod is gone. An entry G1 cannot open (a link, a special file, a file left unreadable) is answered unread and removed; a file the agent left unreadable is the agent's own loss. `os.chmod` is never called while agent files are processed (the test patches it to raise). | `test_p5_02_hold_never_changes_a_mode` |
| P5-03 | medium | confirmed, fixed | `restore_ledger` took the mirror as truth: forged records appended to `mirror/<id>.jsonl` (which needs the documented ungated-shell residual) came back through `--restore` as a clean completion with `audit ok`. The witness could not bound it (it names seq 0 and 1 only). | The anchor bounds every restore (`_bound_mirror`): G1 writes the mirror after the anchor in each commit, so a mirror with records beyond the anchor's seq was extended by someone else; those records are not restored, the user is told, and the restore record says so. A mirror whose record at the anchor's seq, or at the witness's seq, is not the one they name is refused as not G1's copy. Without a readable anchor nothing bounds the mirror and the restore says that. The reviewer's `c_forge_restore.py` now ends with `status: active` (the contract at seq 1, the forged completion gone) and "3 mirror record(s) beyond the anchor (seq 1) were not restored". | `test_p5_03_restore_never_extends_beyond_the_anchor` |
| P5-04 | (section E, not in the table) | confirmed, fixed | `chrt -f 10 g1 status` passed the textual gate: `chrt` was a wrapper but its priority operand was taken for the command. | `chrt` has one operand before the command, like `timeout` and `flock`. | `test_p5_04_chrt_operand` |
| section L | suspicion | confirmed, fixed | `g1 audit` did not flag an accepted challenge with no contract registered from it (a state only a ledger written before round 4 can hold). | The audit reports `challenge <id>: accepted without a contract registered from it` as a finding. | `test_p5_l_audit_flags_an_accepted_challenge_without_a_contract` |

Also from the report, acted on or noted:

- Section J: on a 2,000-file tree, `register` took 4.0 s and the idle `Stop` with an active contract 16.4 s (the
  tree copies and digests, not per-call hooks; the per-call hooks measured 11 to 14 ms, flat to 5,000 records, no
  heavy import). These are once-per-proposal and once-per-idle-Stop costs, documented in design 6.1 and 7.2; where
  the 16 s goes was measured after this review (below) and is a separate improvement, not a correctness fix.
- Section D: `cmd_repair` without a flag runs `check_anchor` (idempotent self-heal: a pre-witness witness, a
  differing mirror rewritten, lost records restored, a genesis-only ledger anchored) before the guard. Agreed as not
  a guard bypass: the same writes happen at every SessionStart.
- Section G: the answer files are written with mode 0o644 in the agent's own directory under G1's home (mode 0o700):
  by design.
- Verdict: the reviewer would trust `complete` and the lockdowns for the stated threat model once P5-01 is capped;
  per-call speed holds.

## Reviewer `fable`: 4 findings (high 2, medium 1, low 1)

| ID | Severity | Verdict | What was wrong | Fix | Test |
|---|---|---|---|---|---|
| P5-01 | high | confirmed, fixed (the same defect as opus P5-01, with one more consequence) | The quadratic `shlex` cost, measured to 11.9 s at 800 KB; past agy's 20-second PreToolUse limit the host ends the hook and takes the silence for consent, so a long enough command line would have run ungated. | The 16 KB tokenization cap (above), and a hard cap: a shell command over 1 MiB is refused outright with a reason (`GATE_MAX_BYTES`), so the gate can never approach the host's limit. The reviewer's `sE_confirm.py`: 300 KB now 69 ms (was 1,016 ms). | `test_p5_01_a_long_command_line_does_not_hold_the_gate`, `test_p5_01_b_a_command_line_over_a_mebibyte_is_refused_fast` |
| P5-03 | high | confirmed, fixed | PreInvocation validated every pending proposal in one call, and each proposal that passes the cheap checks costs a tree copy and its checks (the red baseline): 30 proposals on a 500-file tree held one call for 31.5 s. The proposals directory is the agent's own, so the agent could do this to itself. | A model call pays for at most two red baselines (`MAX_BASELINES_PER_CALL`); the other proposals are given back unclaimed, stay pending, and the block's notes say so. Cheap rejections (bad shape, a contract already active) are not counted, so the common case, one proposal that registers and others refused at once, is unchanged. The reviewer's `sJ2.py`: 2.1 s for 10 or 30 proposals on the 500-file tree (was 9.5 and 31.5 s). The rule and the skill say it. | `test_p5_f03_at_most_two_red_baselines_per_call` |
| P5-02 | medium | confirmed, fixed | `python3 app.py - && echo 'reminder import g1 module'` was refused: for `-` and here-documents the Python pattern was searched over the whole command line. | A here-document is searched from its marker on (its body follows the command); `-` is searched only in the pipeline segment that feeds it (`echo 'import g1' \| python3 -`); prose in another command of the line is not code. | `test_p5_f02_prose_near_a_python_stdin_command_is_not_refused` |
| P5-04 | low | confirmed, fixed | The skill said "Editing a pinned oracle file: refused" without the file-tool/shell distinction the next sentence makes. | The sentence now reads: with a file tool refused; with a shell command caught at the receipt (its hash is pinned). | (text) |

Also from the report, acted on or noted:

- Section E, `uv tool run g1` passed the gate: `tool` is skipped like `run` for the runners (`uv`, `poetry`, `pipenv`, `pdm`, `pipx`). `python3 - < file` stays a documented residual (the code is in a file G1 does not read). `command -v g1` refused: harmless.
- Section M, test 6 (a crash inside `Ledger._finish` after the append of the one-record acceptance): added, `test_p5_f_m6_a_crash_after_the_append_recovers_the_acceptance`; recovery finishes the record and the challenge is accepted with its contract.
- Section D: the same note as opus on `cmd_repair`'s self-heal before the guard; same answer.
- Section J: per-call hooks flat in ledger length (17.5 ms PreToolUse, 21 ms PreInvocation in one long process); `turn_end` on a 2,000-file tree 16.8 s: see below.
- Verdict: "complete" and the lockdowns trusted for correctness; the two speed findings had to be bounded before shipping, with timing assertions in the suite. Both are, with the assertions.

## The idle Stop on a large tree (both reviewers, section J)

Measured by the author after the reviews (`turn_end` with a completing contract on a 2,001-file tree, profiled):
20.8 s under load, of which the tree is hashed six times (`snapshot.manifest`, 9.5 s: the no-change check, the
attempt's identity before and after the checks, and the three measurements around the completion record) and
copied twice (8.1 s: the checks' scratch copy and the canary's), plus 1.5 s of cleanup. Every one of the six hashes
and two copies has a reason in design 6 and 7 (interleaved writes, the canary's fresh tree), and none is on the
per-model-call path; the per-call hooks stayed at 11 to 21 ms in every measurement of this review. This is a cost
per idle Stop with an active contract, proportional to the tree, documented in 7.2, and the candidate for the next
performance change (an in-process cache keyed by inode, size and change time would make five of the six hashes
near free); it was not changed in this round, which fixes what the reviewers found.

## The regression battery

See `BATTERY.md`: every script of reviews 2, 3 and 4 holds on this code, and one defect found by the author while
probing (a corrupt head file or journal crashed `--restore`) is fixed with `test_r4_01_c_restore_survives_a_corrupt_head_file_or_journal`.

## Speed after the fixes

Measured old (`7a12dc3`) against new on the same machine with the same scripts. Nothing on the ordinary per-call
path changed: the tokenization cap only matters past 16 KB, the baseline cap only when more than two proposals
reach a baseline in one call, and the restore bound only runs in `g1 repair`.

| Measurement | Old | New |
|---|---|---|
| Interleaved fresh processes, 2,000-record ledger, n=30 each: PreToolUse, G1's own handle, median (p25-p75) | 23.4 ms (22.7-26.5) | 23.0 ms (22.1-27.6) |
| the same, PreInvocation | 32.9 ms (30.0-36.9) | 30.9 ms (29.6-35.9) |
| One ledger append with views, interleaved, n=8, median | 26.3 ms | 26.4 ms |
| Scratch copy of a 2,001-file tree, interleaved, n=8, median | 3,508 ms | 3,432 ms |
| PreToolUse on a 100 / 200 / 400 KB `run_command` (opus `P501.py`) | 475 / 1,659 / 6,217 ms | 31 / 50 / 89 ms |
| PreToolUse on a 200 / 300 KB one-token line (fable `sE_confirm.py`) | 494 / 1,016 ms | 59 / 69 ms |
| One PreInvocation with 10 / 30 pending proposals on a 500-file tree (fable `sJ2.py`) | 9.5 / 31.5 s | 2.1 / 2.1 s |

The benchmarks ran while nothing else did; the differences between old and new on the ordinary path are inside
the run-to-run noise of this PRoot host.

## Live

After the fixes were installed, two agy sessions (Gemini 3.8 Flash, effort high) ran on a fresh copy of the slug
project with its bug put back; the agy records of both were removed afterwards.

- Probe session (41 s, 35,806 tokens): the ancestry line again shows `agy` as the direct parent of a command the
  agent runs; `g1 status .` and `exec -a x python3 -m g1 status .` were both refused by the hook with the
  "G1 command line refused" text (2 denied calls in the journal, nothing else denied).
- Fix session (162 s, 162,978 tokens): the agent wrote the failing test first, proposed `slug-trim`, fixed, and
  stopped; G1 registered (seq 1), verified (seq 2-3) and completed (seq 4) the contract; `g1 audit` ok with no
  findings and no notes; witness at seq 1; hidden cases 9/9; the agent's last message ends with "G1 end-of-turn
  verification for active contract `slug-trim`" rather than a claim of completion.
- Hook cost from G1's journal: PreInvocation median 27 ms, 90th percentile 34 ms (n=37); PreToolUse median 19 ms,
  worst 20 ms (n=27); the Stop that verified and completed, 774 ms.
