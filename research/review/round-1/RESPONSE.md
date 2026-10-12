# Review round 1: what was done with each finding

An agy session (Gemini 3.8 Flash, effort high) reviewed G1 at commit `fb600c9` with the brief in
`AGY-AUDIT-PROMPT-1.md` and wrote `AGY-AUDIT-1.md` (16 findings, sections A to J). G1 was installed and active during
the review; it refused nothing.

Every finding was then reproduced against that commit in an isolated G1 home before anything was changed, and the
reproduction was run again after the fix. Three further defects turned up while doing so; they are marked "found while
verifying". One more was found after the fixes, in the new `g1 repair` command; it is marked "found after the fixes". Each fix has a regression test in `tests/test_core.py`, class `AuditRound1Tests`, named after the finding.

## Verdicts

| ID | Review severity | Verdict | What was wrong | Fix | Test |
|---|---|---|---|---|---|
| F-01 | critical | confirmed | A `must_flip` check without `targets` skipped the canary, so a check on a file outside the workspace completed a task in which no file changed. | `targets` is required for every `must_flip` check; the completion function requires a sensitive canary for every `must_flip` check. | `test_f01_*` (3) |
| F-01b | found while verifying | confirmed | A target could be the pinned test file itself; corrupting the test makes any check fail, so the canary always looked sensitive. | Targets must lie inside `allowed_paths` and must not be oracle files. | `test_f01_must_flip_needs_targets_inside_scope_and_not_oracles` |
| SYM | found while verifying | confirmed | The canary opened targets by path. A target planted as a symbolic link made G1 write canary bytes to a file outside the workspace for the length of the check. | Canary bytes go only to regular files inside the scratch copy, reached without a link, opened with `O_NOFOLLOW`. | `test_sym_canary_does_not_write_outside_the_scratch_copy` |
| F-02 | critical | confirmed, high | Restoring lost records from the mirror left the head stale, so the ledger no longer verified. A broken repair, not a false completion. | The repair rewrites the ledger and the head from the mirror up to the anchor and verifies the result. | `test_f02_mirror_restores_lost_records_and_the_head` |
| FORGE | found while verifying | confirmed | A record appended to the ledger and the head outside G1 was accepted at the next session start ("mirror extended", "anchor refreshed"), so a forged completion would have stood. | The anchor moves inside every commit, under the lock, with crash recovery. A ledger whose head differs from its anchor locks the workspace down without writing to it; the user decides with `g1 repair`. The check also runs before every verification at Stop. | `test_forge_record_appended_outside_g1_locks_the_workspace_down` |
| F-03 | high | confirmed | A crash inside the append left a partial line; recovery crashed on it. | Recovery completes the line from the journaled record; any other unterminated tail is reported as corruption. Readers read only up to the head. | `test_f03_recovery_completes_an_interrupted_append_and_refuses_garbage` |
| F-04 | high | confirmed, medium | A lone surrogate (`\ud800`) in a proposal crashed proposal processing at every model call. | Canonical decoding rejects strings that are not valid Unicode; the proposal is rejected with a reason. | `test_f04_lone_surrogate_is_rejected_not_crashing` |
| F-05 | high | partly confirmed, low | `[]` was harmless; `[1]` and input that is not UTF-8 crashed the hook process. PreToolUse fails closed on a crash, so nothing was let through. | The payload is read as bytes; anything that is not a JSON object becomes `{}`. | `test_f05_hook_input_not_an_object_or_not_utf8` |
| F-06 | high | confirmed | All check output was buffered before the 1 MiB cap applied: 143 MiB of memory for 64 MiB of output. | Output is read as it arrives; the first byte past the cap stops the check, which then fails as truncated. Measured after: 17 MiB. | `test_f06_output_beyond_the_cap_stops_the_check` |
| F-07 | high | confirmed | A newline in a proposal objective or a blocked item produced lines that looked like G1's status block. | Agent text is printed as a quoted JSON string; notes that may embed agent text are escaped to one line; paths may not contain control characters. | `test_f07_agent_text_cannot_forge_status_lines` |
| F-08 | medium | confirmed in part | Empty directories and directory modes were not in the tree manifest. Changes inside excluded directories are invisible, but those directories are also not copied into the scratch tree, so no check result can depend on them. | Directories are recorded with their mode; the excluded directories and their effect are stated in the design. | `test_f08_an_empty_directory_outside_scope_is_a_scope_violation` |
| F-09 | medium | confirmed | A directory inside G1's own home could be enrolled. | Enrolment refuses any directory inside G1's home. | `test_f09_directories_inside_g1_home_are_never_enrolled` |
| F-10 | medium | confirmed | The binary names the notebook tool `edit_notebook`; G1 listed only `notebook_edit`. Other mutating tools were missing too (`execute_notebook`, `send_command_input`, `write_blob`, `git_commit`, package installs, subagent tools). | Every mutating tool name from the binary and the analysts' list is gated; measured that every tool call fires PreToolUse. | `test_f10_every_known_mutating_tool_is_gated` |
| F-11 | medium | confirmed, worse than reported | The docs claimed foreign hook entries were kept byte for byte; they were reformatted, and a foreign entry with a float (`"timeout": 1.5`) made the install fail. | Host hook files are read as ordinary JSON and written back with every foreign key, value and order kept; an unreadable file is left unchanged and reported. | `test_f11_foreign_hook_entries_survive_and_an_unreadable_file_is_left_alone` |
| F-12 | medium | by design | Strings are hashed as exact code points, without Unicode normalization. Normalizing would give two different file names the same hash. | Stated in `canon.py` and the design. | none |
| F-13 | medium | confirmed, raised to high | Every PreToolUse verified the whole ledger: 124 ms with an empty ledger, 429 ms at 3,000 records. This breaks the rule that G1 must never slow the model. | The per-call hooks read a summary bound to the ledger head by sequence number and hash; completion still verifies the whole chain. Measured after: 122 to 126 ms over the same range. | `test_f13_gate_uses_the_head_bound_summary` |
| CLI | found after the fixes | confirmed | The new `g1 repair --accept-ledger`, and the older `host-verify`, `uninstall` and `turn-end`, could be run by the agent through the shell, so it could lift its own lockdown. | The textual gate refuses G1's decision commands (`repair`, `host-verify`, `install`, `uninstall`, `turn-end`, `init`, `propose`); `status` and `audit` stay open. A tripwire: same-user residual risk, design 7.7. | `test_agent_cannot_run_g1_decision_commands` |
| F-14 | low | confirmed | Test counts in the README and the design were stale. | Updated. | none |
| F-15 | low | confirmed | A test left files open. | Closed; the suite now passes with ResourceWarnings as errors. | the whole suite |
| F-16 | low | confirmed | The package docstring named the host, and two core functions held the host's configuration path. | The host paths moved into the adapter; a test now greps every core module for host names. | `test_f16_core_modules_never_name_the_host` |

## Other points in the report

- B, completion window: `approve` and the completion append were not atomic. The completion is now appended by
  compare-and-swap on the receipt; a record appended in between stops the completion for this turn
  (`test_completion_is_compare_and_swap_on_the_receipt`).
- C, parallel tool calls sharing a step index: not observed. In 1,317 recorded hook calls every tool call was its own
  step, and no transcript on the measuring device holds a planner response with two tool calls. If it ever happens, the
  gap check refuses completion, which is the safe direction. Stated in `docs/host-agy.md`.
- C, `conversations.json` written without a lock: replaced. Every journal line now carries the transcript path, and
  the journal is append-only (`test_gap_conversations_come_from_the_append_only_journal`).
- C, textual gate spellings (`$HOME/.g1`, `../..`): true and by design; the design now calls the textual gate a
  tripwire and names what actually holds.
- D, redaction gaps: AWS, GitHub, GitLab, `sk-` and Hugging Face keys and secret-like assignments in YAML, Python and
  single-quoted dictionaries are now redacted (`test_redaction_covers_common_token_shapes`). A process that leaves its
  group with `setsid` survives the kill; stated as a limit.
- F, bootstrap quoting: a path with a single quote broke the hook command. The command is now built with `shlex.quote`.
- H, duplicated scope helper: merged into `paths.in_scope`.
- J, rules against code: E2.3, E2.4, E2.5 and I6 now name the enforcement the code actually has; E3 no longer claims
  that every shell write after a refusal is refused, and no longer points at a `state.json` path the block does not
  carry; the skill lists every paused reason and the target rules; D3.5 and D3.6 no longer conflict with I7 and K1.3;
  the Korean rule allows list items without a verb, quotes its own example correctly, and scopes the rhythm rule to
  prose. W2.2 was already tagged correctly and is unchanged.
- G, ten proposed tests: nine are in (`test_f01_*`, `test_f02_*`, `test_f03_*`, `test_f04_*`, `test_f05_*`,
  `test_f06_*`, `test_f07_*`, `test_f09_*`, `test_guard_failing_at_baseline_is_rejected`); the NFC test is not, by F-12.
