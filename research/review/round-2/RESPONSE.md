# Review round 2: what was done with each finding

An agy session (Gemini 3.8 Flash, effort high) reviewed G1 at commit `65f6e76`, the code after the round-1 fixes, with
the brief in `AGY-AUDIT-PROMPT-2.md`, and wrote `AGY-AUDIT-2.md`. It confirmed 16 of the 19 round-1 fixes as complete
and found the other three (F-02, F-07, the CLI tripwire) incomplete; those gaps are R2-05, R2-04 and R2-07 below. It
then attacked the code the fixes had added and reported 12 findings.

Every finding was reproduced against `65f6e76` in an isolated G1 home before anything changed, and the reproduction
was run again after the fix. Each fix has a regression test in `tests/test_core.py`, class `AuditRound2Tests`, or in
`AuditRound1Tests` where it extends a round-1 test.

## Verdicts

| ID | Review severity | Verdict | What was wrong | Fix | Test |
|---|---|---|---|---|---|
| R2-01 | critical | confirmed, high | The tree was measured under the lock, then approved and written after the lock was released; a write in that window (milliseconds, forced in the reproduction from inside `approve`) was completed unseen. | The completion is one lock hold: head check, measure, approve, measure again, append by compare-and-swap. A change in between gives `concurrent_change`. A write after the second measurement is after the completion; no check can freeze a filesystem, and the design says so. | `test_r2_01_tree_change_while_completing_is_not_completed`, `test_completion_is_compare_and_swap_on_the_receipt` |
| R2-02 | critical | confirmed, high | With the anchor deleted, a ledger and mirror forged consistently were accepted as "anchor restored from the mirror". | A missing anchor is accepted only for a genesis-only ledger; otherwise the ledger is diverged. Rewriting the anchor too remains the stated same-user residual risk. | `test_r2_02_deleting_the_anchor_does_not_bless_a_forged_ledger` |
| R2-03 | high | partly accepted, medium | A conversation whose transcript was deleted counted as zero tool calls, silently. | The conversation is now reported as `liveness_unknown` in the receipt and in the status block, and the agent's own tools can no longer delete transcripts. The proposed fix, refusing completion, is not taken: it would make a deleted session block the work, which the two-way test forbids (principles A2) and run 5 measured as working. | `test_r2_03_deleted_transcript_is_unknown_and_transcripts_are_protected` |
| R2-04 | high | confirmed | U+2028 and U+2029 in an objective split the status block into lines that looked like G1's, as did U+0085 and other characters `str.splitlines()` breaks on. | Every control, format, line-separator and paragraph-separator character in agent text is escaped; paths may not contain them. | `test_r2_04_unicode_line_separators_cannot_forge_status_lines` |
| R2-05 | high | confirmed, medium | Only the mirror's last line was compared, so a corrupt middle record went unnoticed until a repair needed it. | In the anchored case the mirror must be byte-identical to the ledger (one file hash each, no parsing); any difference rewrites it from the anchored ledger. | `test_r2_05_a_corrupt_middle_mirror_record_is_rewritten` |
| R2-06 | high | confirmed, low | A missing anchor with an empty mirror on a new ledger locked the workspace down. It needs a manual deletion to happen. | Covered by the R2-02 rule: a genesis-only ledger is anchored, not locked. | `test_r2_06_a_genesis_only_ledger_without_anchor_is_anchored_not_locked` |
| R2-07 | medium | confirmed in part | `python3 -m g1.__main__ repair` and `python3 -c "...main(['repair'])"` passed the tripwire. `g1\ repair` and `G1 repair` also passed, but neither runs G1 (the first names a command "g1 repair" with a space, the second a different file name), so they are not bypasses. | Decision commands are found by shell tokens in command position, including `-m g1.__main__`, `python -c` code, `sh -c`, `$(...)`, backticks and newlines. | `test_r2_07_r2_08_decision_commands_by_shell_tokens` |
| R2-08 | medium | confirmed | `git commit -m "fix: g1 repair command"` and similar commands were refused, which blocks ordinary work in any repository that mentions G1. | Same tokenizer: text inside an argument, such as a commit message or a grep pattern, is not a command. | same test |
| R2-09 | medium | confirmed, raised to high | With two targets, one a symbolic link to a file outside the workspace, the other a real file, the canary reported "sensitive" and the task completed while part of the work lived outside the repository. | A target that is a link or not a regular file fails the canary (`target_not_regular`); a new or changed link whose target leaves the workspace is a scope violation (`links_out`). | `test_r2_09_link_targets_and_links_out_of_the_workspace_fail`, `test_sym_canary_does_not_write_outside_the_scratch_copy` |
| R2-10 | medium | confirmed | A copy error in the scratch tree (`shutil.Error`, seen under PRoot as `EINVAL` from a kernel copy fast path) escaped as an exception, so the Stop hook ended with no record of the attempt. | Copies fall back to a plain read and write; any remaining failure is `scratch_copy_failed`, an `environment_unknown` outcome in the ledger. | `test_r2_10_scratch_copy_failure_is_recorded` |
| R2-11 | low | confirmed | `state.digest_state` had no caller. | Removed. | none |
| R2-12 | low | confirmed | A check that exited while a child it started kept the output pipe open ran into its timeout and failed. A false fail, not a false pass. | When the check has exited, reading stops after half a second, the exit status is the check's, and the leftover group is killed. | `test_r2_12_check_exit_is_not_held_by_a_leftover_child` |

## Other points in the report

- Section B (crash injection at seven points of a commit, a reader during 200 appends, two concurrent writers): the
  reviewer found the commit protocol and its recovery correct in every case it ran. No change.
- Section D (the head-bound summary after a supersede, a blocked report, another process's append, `accept_ledger`,
  and a crash between the head and the summary): correct in every case. PreToolUse measured 8.3 ms, 12.0 ms and
  5.9 ms of G1's own work at 1, 1,000 and 5,000 records. No change.
- Section E.1 (a check that swallows the corrupt target's error): the canary reported it as insensitive; correct.
- Section H, "approve() returns True only from executed evidence" was called misleading because of R2-09; with the
  R2-09 fix the statement holds again.
