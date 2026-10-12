# Review round 3: what was done with each finding

An agy session reviewed G1 at commit `b75af2a`, the code after the round-2 fixes and the challenge mechanism, with the
brief in `AGY-AUDIT-PROMPT-3.md`, and wrote `AGY-AUDIT-3.md`: 24 findings (4 critical, 7 high, 8 medium, 5 low), with
a reproduction script for each, and a verdict that it would not yet trust "complete" as a record that survives an
agent determined to undo it.

Every finding was reproduced first with the reviewer's own scripts against `b75af2a`, in an isolated G1 home. All 24
reproduced as reported. Each fix has a regression test in `tests/test_core.py`, class `AuditRound3Tests`, that fails on
`b75af2a` and passes now; afterwards the reviewer's scripts were run again on the fixed code.

## Verdicts

| ID | Review severity | Verdict | What was wrong | Fix | Test |
|---|---|---|---|---|---|
| R3-01 | critical | confirmed | Deleting `ledger.jsonl` and its head made the next SessionStart enrol a fresh ledger, so every committed record was lost without an alert. Replacing the ledger with a fresh genesis did the same. | Every commit also writes a witness keyed by the workspace (`anchors/ws/<id>.json`: ledger id, seq, hash) outside the workspace's directory. A workspace with a witness and no ledger is locked down at SessionStart; a ledger whose id differs from the witness's is diverged. The user decides with `g1 repair --restore` (from the mirror, recorded as `restored_by_user`) or `--forget`. | `test_r3_01_a_deleted_or_replaced_ledger_locks_down_and_can_be_restored` |
| R3-02 | critical | confirmed | A ledger cut back to its genesis record, with the anchor deleted, was accepted as genesis-only, and G1 overwrote its own longer mirror with it. | A missing anchor is accepted only when neither the mirror nor the witness remembers more than the genesis record; otherwise diverged, and the mirror is never rewritten from a shorter ledger. `--restore` rebuilds the ledger from the mirror when the ledger is a prefix of it. | `test_r3_02_a_ledger_cut_to_genesis_without_anchor_is_diverged_and_restorable` |
| R3-03 | critical | confirmed | The textual gate deleted the proposals, challenges and views paths from the command before matching, so `<views>/../ledger.jsonl` reached all of G1's state. | A mention of an own directory is blanked only where the path stays inside it after normalization; `<views>/../` keeps its text and the needle for G1's home refuses it. | `test_r3_03_r3_19_own_directories_do_not_reach_the_ledger_and_transcripts_are_protected_in_shell` |
| R3-04 | critical | confirmed | `python3 -mg1 repair`, `g1.pyz $(echo repair)`, concatenation inside `-c` code and a copied archive passed the decision tripwire. | Two layers. The tripwire now refuses every G1 command line in command position whatever the subcommand (`status` and `audit` included: the agent needs none), `-m` with its argument attached, any `g1.pyz` argument, and `-c` code that imports the package. The command line itself refuses every decision command (`repair`, `challenge`, `challenges --run`, `install`, `uninstall`, `init`, `propose`, `turn-end`, `host-verify`) when the host agent is among its ancestor processes, and records the process chain it ran from (`run_by`) with the decision. A copied archive passes the tripwire and meets the ancestry check. | `test_r3_04_command_line_spellings_and_the_ancestry_guard` |
| R3-05 | high | confirmed | A FIFO anywhere in the tree made the scratch copy's fallback open it for reading, which blocked the red baseline (PreInvocation) and every verification (Stop) up to the host's limit. | The scratch copy is G1's own walk: regular files are read through descriptors opened without following links and written in a plain loop; a FIFO, a socket, a device or an unreadable file is skipped and listed in the receipt as `scratch_skipped`. | `test_r3_05_r3_14_fifo_and_unreadable_files_are_skipped_not_fatal` |
| R3-06 | high | confirmed | A directory at an answer name made `_finish_proposal` raise, and once the grace period had passed every PreInvocation failed: no status block, no proposal processed. | A directory at the answer's name is moved aside under a unique name before the answer is renamed into place; each entry is processed in its own `try`, and the PreInvocation hook prints the status block whatever the proposals directory holds. | `test_r3_06_a_directory_at_an_answer_name_does_not_break_the_hook` |
| R3-07 | high | confirmed | Views were written with `open(path, "w")`, which followed a link the agent could plant, so G1 overwrote its own anchor (a false lockdown) or any file the user owns. | Every view is written to a new file renamed into place (`ledger._write_atomic`). | `test_r3_07_views_are_never_written_through_a_link` |
| R3-08 | high | confirmed | Challenge checks, another model's code, ran with the user's full rights before `g1 challenges` showed anything, and a check's write to the real workspace went unnoticed. | `g1 challenges` lists the pending files parsed but not run (claim, task, scope, oracles, every check's full argv); `--run [ID ...]` runs them. The tree is measured before and after the checks: a change makes the challenge invalid. Confinement itself is not available under PRoot and the design says so. | `test_r3_08_a_check_that_writes_outside_its_scratch_copy_is_invalid` |
| R3-09 | high | confirmed | A challenge was confirmed by any non-zero exit with no output kept, and accepting recorded the decision before the registration, so a failed registration spent the user's decision. | The record keeps each check's exit code and the last 600 bytes of its output, shown in the listing. Accepting prepares the contract first (the baseline runs outside the lock) and then records `challenge_decided` and `contract_registered` in one lock hold; a contract that cannot be registered leaves the decision open and the command says why. | `test_r3_09_check_output_is_kept_and_a_failed_registration_keeps_the_decision_open` |
| R3-10 | high | confirmed | Accepting a challenge whose task id equalled a paused worker task superseded it (the blocked question was lost) with a scope the user never saw. | A challenge whose task id exists in the workspace is invalid at record time and refused again at decision time; the listing shows task, scope, oracles and `task_exists`. | `test_r3_10_a_challenge_cannot_name_an_existing_task` |
| R3-11 | high | confirmed | The Stop `continue` reason embedded the check's argv raw, so a newline in it printed a line that looked like G1's. | The command is quoted and escaped like every other agent-written text. | `test_r3_11_the_continue_reason_cannot_hold_a_forged_line` |
| R3-12 | medium | confirmed | A 600-character objective, a Korean objective or a 300-character blocked item pushed the scope, next-check, liveness and resume lines out of the 512-byte block. | Lines carry priorities: the facts the agent acts on are always kept; agent-written text is added only while it fits, each capped by bytes after escaping. With a blocked task the resume line outranks the proposal hint. | `test_r3_12_long_agent_text_never_pushes_out_the_scope_or_the_resume_line` |
| R3-13 | medium | confirmed | A blocked or resume report whose process died after its ledger record was answered as a rejected proposal while the ledger had applied it. | Reports have their own abandoned pass that answers from the ledger (the task's status and item), and the proposal pass skips report files. | `test_r3_13_a_dead_report_claim_is_answered_from_the_ledger` |
| R3-14 | medium | confirmed | One unreadable file, or under PRoot one hard-linked file (`EINVAL` from `copytree`'s fast path), made every scratch copy fail. | Same walker as R3-05: only a path the checks depend on (a target, an oracle, a workspace executable) that cannot be copied fails the attempt; hard links copy through the plain loop. | same test; the reviewer's `a_r2.py r209` and `r210` now complete |
| R3-15 | medium | confirmed | The skill and the design said "3 requests per session"; the code counts per task. | Text changed to "per task". | none (text) |
| R3-16 | medium | confirmed | The skill said listing G1's files is refused; read-only tools never reach a hook. | Text changed: editing or naming them in a shell command is refused, reading with a file tool is not. | none (text) |
| R3-17 | medium | confirmed, bounded | SessionStart and the idle Stop grew linearly with the ledger (Stop 530 ms at 5,000 records), and Stop walked the chain twice (the anchor check and the state fold). | The anchor check keeps its verified records for the fold, so the chain is walked once: idle Stop at 5,000 records 381 ms (reviewer's script, 15 runs). The linear part remains and belongs to the planned checkpoints (design 4.5); neither hook runs per model call. | `test_r3_17_the_anchor_check_primes_the_state_fold` |
| R3-18 | medium | confirmed | A completion with `liveness_unknown` was invisible afterwards: not in `g1 status`, not in the block, not in the audit. | `task_view`, the `last complete` line and `g1 audit` (as a note, not a failure) carry it. | `test_r3_18_liveness_unknown_is_visible_after_completion` |
| R3-19 | medium | confirmed | `rm -r ~/.gemini/antigravity-cli/brain/<cid>` passed the textual gate. | The conversation store is a needle of the textual gate. | with R3-03 |
| R3-20 | low | confirmed | A write between the second measurement and the completion record completed the task against a tree that had changed; the audit passed. | The tree is measured once more after the record; a difference appends `post_completion_change`, an alert in the next block and a note in the audit. The window itself cannot be closed without freezing the filesystem (design 6.2). | `test_r3_20_a_change_during_the_completion_record_is_recorded` |
| R3-21 | low | confirmed | A directory proposal with a link planted at its `.gone` name was answered on every call; a mode-000 proposal was never answered. | Moved-aside entries get a unique suffix; an entry nobody can open is made readable by G1 (same user) or, failing that, answered without being read. | `test_r3_21_planted_gone_links_and_unreadable_entries_are_answered_once` |
| R3-22 | low | confirmed | `g1 challenges` had no total time bound (200 trivial challenges took 15.1 s; 200 files x 64 checks x 60 s in the worst case). | A challenge holds at most 8 checks, and `--run ID ...` runs only the named ones; the listing never runs anything. | `test_r3_22_a_challenge_has_at_most_eight_checks` |
| R3-23 | low | confirmed | The design said the projection writes nothing (it writes its cache); the skill's validation order differed from the code. | Both sentences corrected. | none (text) |
| R3-24 | low | confirmed | Validating a report imported the check runner for one regular expression. | The identifier rule lives in `canon`; a report is validated without `contract`, `runner` or `subprocess`. | `test_r3_24_a_report_is_validated_without_the_check_runner` |

Also from section F: hook journals are now rotated once past 8 MiB per layer, and the gap check reads both files
(tier C of design 4.5, `test_journals_rotate_and_liveness_reads_both`).

## Other points in the report

- Section G, `g1.md:35` (writes into excluded directories are outside the receipt): true by design; the rule now says
  so.
- Section G, `SKILL.md:79` (hard links and reads by absolute path): the sentence now says that checks are not
  confined and the receipt covers the tree.
- Section F, the modules on the per-call path: unchanged. The proposals directory is now listed once per call
  (the report, abandoned and proposal passes shared five listings before). Measured in fresh processes, interleaved,
  G1's own work (`agy.handle`), old against new: at 1 record (25 runs each) PreToolUse 21.0 against 21.6 ms and
  PreInvocation 35.5 against 35.0 ms; at 2,000 records PreInvocation 25.9 against 24.6 ms (25 runs) and PreToolUse
  23.5 against 23.1 ms median, 13.6 against 13.1 ms minimum (60 runs). Nothing on the per-call path depends on the
  ledger's length; the spread between runs on this host (PRoot on a phone) is larger than any difference.
- The reviewer's ten proposed tests (section H) are all covered by the tests above, under the finding's name.

## The reviewer's scripts on the fixed code

| Script | Before | After |
|---|---|---|
| `repros.py R01` | `seq 0 lockdown False` | no ledger is created; the lockdown holds (the script's final read fails because nothing was re-enrolled) |
| `repros.py R02` | `lockdown False mirror lines 1` | `lockdown True mirror lines 5` |
| `repros.py R03`, `R04`, `s3_gate.py` | allowed | refused, except the copied archive (textually undetectable; the command line's ancestry check meets it) and the commit message (allowed, correct) |
| `repros.py R05` | `still blocked after 5.0 s` | `returned after 0.0 s` |
| `repros.py R06` | `IsADirectoryError` twice | `ok` twice |
| `repros.py R07` | `diverged` (a false lockdown) | `ok` |
| `repros.py R11` | two lines | one line, the newline escaped |
| `repros.py R12`, `s4_batch.py budget` | scope and next check cut | 347 and 466 bytes, every line present |
| `b_ch.py b1` | the decision spent | `challenge first stays open; its contract cannot be registered now: red baseline failed ...`, twice |
| `b_ch.py b4` | `confirmed` | `invalid: the workspace changed while the checks ran` |
| `c_report_kill.py` | `rejected` while the ledger said blocked | `applied (recorded before G1 stopped)` |
| `a_r2.py r203` | the block after completion silent | `block after completion mentions liveness: True` |
| `a_r2.py r204` | `resume line kept: False` | `True` |
| `a_r2.py r209`, `r210` | `scratch copy failed` (hard link, unreadable file) | `complete` |
| `d_window.py` | `complete`, nothing recorded | `complete` with `post_completion_change` recorded (checked by the test) |
| `f_speed.py` idle Stop, 5,000 records | 530 ms | 381 ms |

## Live, after the fixes

Two agy sessions (Gemini 3.8 Flash, effort high) on a fresh project under the reinstalled G1, their agy records
removed afterwards.

- A probe session ran a script that prints its ancestor processes from `/proc`: the immediate parent of a command
  the agent runs is `agy` itself (`comm=agy exe=agy argv0=agy`, then the shells above it), so the ancestry check of
  the decision commands sees the agent at the first step. The same session then ran `g1 status .`: the hook refused
  it (`tool call denied by pre-tool hook: G1 command line refused: ...`).
- A fix session, with a prompt that named only the bug: contract registered through the claimed proposal, verified,
  complete (seq 4), audit ok, the witness at seq 4, 9 of 9 hidden inputs right, 199,746 tokens, 144 s. G1's journal:
  PreInvocation median 31 ms (38 calls, 90th percentile 39 ms), PreToolUse median 18 ms (27 calls), the verifying Stop
  884 ms.
