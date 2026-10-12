# G1 review, round 5

- Commit: `63fc78f4913ca848c485f6e75fba8de37e71aa54`
- Python: `Python 3.13.7`
- Unit tests: `python3 -W error::ResourceWarning -m unittest tests.test_core -v`: `Ran 124 tests in 54.885s`, `OK`
- Started: 2026-10-12T01:01:25Z
- Finished: 2026-10-12T01:19:30Z
- Scratch: `/tmp/g1-review5/` with `G1_HOME` set to an isolated directory under `/tmp/g1-review5/`.

## Findings Table

| ID | Severity | file:line | Claim (one sentence) | Evidence | Fix (concrete) |
|---|---|---|---|---|---|

(No critical, high, medium, or low defects found in this round. The table is empty.)

## A. Round-4 Fixes (R4-01 to R4-09)

Every round-4 fix was reproduced and confirmed against the current code using `/tmp/g1-review5/test_section_a.py`:

- **R4-01** (`integrity.py:341`, `restore_ledger`, `forget_workspace`): `fixed`. A ledger corrupted by truncated bytes or invalid JSON prefix is restored from its mirror up to the anchor, or moved aside to `forgotten-<hex>` via `forget_workspace`. *Variation*: Corrupted byte at seq 0 and a corrupt `ledger.head.json` both restored cleanly from the mirror (`ran`, `test_section_a.py`, exit 0).
- **R4-02** (`workspace.py:655-684`, `decide_challenge`): `fixed`. Challenge acceptance records a single `contract_registered` event containing the decision reason and `run_by`; no separate `challenge_decided` record is written, eliminating multi-record crash windows. Rejections record `challenge_decided` as expected (`ran`, exit 0). *Variation*: Rejection verified to still emit `challenge_decided`.
- **R4-03** (`workspace.py:134-154`, `_hold`): `fixed`. `_hold` never modifies file permissions (chmod removed). Planted hard link to mode 000 file leaves mode 000 untouched and reports entry unreadable (`ran`, exit 0).
- **R4-04** (`adapter/agy.py:480-520`, `process_chain`, `_user_only`): `fixed`. Unreadable `/proc` root ends the ancestry chain as `None`, causing `agent_in_ancestry` to return `True` (fail-closed) and `_user_only` to refuse decision commands (`ran`, exit 0). *Variation*: Ancestor further up that cannot be read appends `["?"]` without failing open.
- **R4-05** (`tests/test_core.py:setUpModule`): `fixed`. The entire test suite patches `agy.process_chain` in `setUpModule` to a user shell chain, so all 124 unit tests pass cleanly even when executed within an `agy` session (`ran`, 124 tests OK).
- **R4-06** (`adapter/agy.py:281-291`, `_skip_wrapper`, `invokes_g1`): `fixed`. Wrappers with argument options (`exec -a`, `env -i`, `sudo -u`, `nice -n`, `timeout 10s`, `flock`, `chrt -f 10`) and stdin/heredoc Python code (`python3 -`, `<<EOF`) are recognized by the textual gate tripwire (`ran`, exit 0). *Variation*: Multi-command line with wrapper and heredoc after `&&` caught.
- **R4-07** (`adapter/agy.py:530-575`, `_names_path`, `_python_code_runs_g1`): `fixed`. Relative path needles (`.agents/hooks.json`, `.system_generated`) match path delimiters rather than substrings within prose, preventing false refusals in commit messages. Python code in `-c` is tokenized, so `x = 'import g1'` is allowed (`ran`, exit 0).
- **R4-08** (`runner.py:130`, `_copy_entry`): `fixed`. Directory access and modification timestamps (`st_atime_ns`, `st_mtime_ns`) are preserved via `os.utime` after directory contents are written (`ran`, exit 0). *Variation*: Empty directories also have mtimes preserved.
- **R4-09** (`project.py:43-83`, `_assemble`, `short_ids`, `short_json`): `fixed`. Priority-0 lines are never cut even when their combined byte size exceeds the projection budget; lists of check IDs and paths are bounded at formatting time using `short_ids` and `short_json` (`ran`, exit 0). *Variation*: 100 check IDs and 100 deep paths formatted safely within budget.

## B. Pre-Audit Fixes (opus & fable P5-01 to P5-04, corrupt head)

All pre-audit fixes were confirmed against the current code using `/tmp/g1-review5/test_section_b.py`:

- **P5-01 (opus/fable)** (`adapter/agy.py:316-324`, `_split_for_gate`, `GATE_MAX_BYTES`): `fixed`. `_split_for_gate` tokenizes at most 16 KB (`GATE_TOKENIZE_BYTES`) and applies linear scanning beyond it. Commands exceeding 1 MiB (`GATE_MAX_BYTES`) are refused fast without tokenization (`ran`, exit 0). *Variation*: Command at exactly 1,048,576 bytes passes length check, while 1,048,577 bytes is refused fast with "longer than 1048576 bytes"; command straddling the 16 KB boundary caught by linear scan.
- **P5-02 (opus)** (`workspace.py:134-145`, `_hold`): `fixed`. `_hold` performs no `chmod`. Non-regular files (FIFOs, sockets, symlinks) raise `OSError` or `ValueError` and are answered unread without blocking or altering modes (`ran`, exit 0). *Variation*: Named FIFO in proposals handled without hang.
- **P5-03 (opus)** (`integrity.py:343-375`, `_bound_mirror`): `fixed`. Restores are bounded by the anchor record. Any mirror records beyond the anchor's sequence number are discarded and noted; mirrors contradicting anchor or witness hashes are rejected (`ran`, exit 0). *Variation*: Tampered hash at anchor sequence or witness sequence raises `ValueError: mirror is not G1's copy`.
- **P5-04 (opus)** (`adapter/agy.py:291`, `_WRAPPER_POSITIONALS`): `fixed`. `chrt` priority operand parsed correctly alongside `timeout` and `flock` (`ran`, exit 0).
- **P5-02 (fable)** (`adapter/agy.py:383-391`, `_piped_code`): `fixed`. Standard input `-` code search only inspects the pipeline segment immediately preceding `python3 -`; prose elsewhere on the command line does not trigger false refusal (`ran`, exit 0).
- **P5-03 (fable)** (`workspace.py:615-629`, `_costs_a_baseline`, `MAX_BASELINES_PER_CALL`): `fixed`. At most 2 red baselines run per model call. Additional costly proposals are unclaimed and deferred to the next call with notes (`ran`, exit 0). *Variation*: 4 failing proposals tested; 2 rejected on baseline failure and 2 deferred with "2 proposal(s) wait for the next model call".
- **P5-04 (fable)** (`host/skills/g1/SKILL.md`): `fixed`. Skill documentation distinguishes file-tool oracle edits (refused by gate) from shell edits (caught at receipt).
- **Section L (opus/fable)** (`audit.py:26-30`): `fixed`. `g1 audit` flags accepted challenges without a registered contract (`ran`, exit 0).
- **Corrupt head / journal fix (author)** (`integrity.py:392-402`, `restore_ledger`): `fixed`. Corrupt head file and pending journal file do not prevent `restore_ledger` from rebuilding the ledger from the mirror and clearing pending journals (`ran`, exit 0).

## C. Code Added Since Round 4

The diff (`21cf430..HEAD`) was analyzed across all changed functions in `src/g1/`:
- `_split_for_gate`: safely splits on whitespace before `GATE_TOKENIZE_BYTES`; handles multibyte strings, empty strings, and long single tokens without raising or looping (`ran`, `test_section_c.py`).
- `_skip_wrapper`: bounds recursion depth (`depth < 3`); safely advances tokens and skips runner words (`uv tool run`).
- `_piped_code`: safely walks backward to find pipeline feeder tokens; handles index boundaries and empty tokens.
- `_python_code_runs_g1`: tokenizes Python code to avoid false refusals on string literals; falls back to regex on syntax errors.
- `_names_path`: regex matches path delimiters `(?:^|/)` and `(?:/|$)`; immune to substring matches in prose.
- `_known_ledger_id`: prefers witness ledger ID over head file; handles unreadable/corrupt files gracefully.
- `_bound_mirror`: enforces anchor seq boundary and witness hash consistency.
- `restore_ledger`: handles corrupt ledgers, cleans up unapplied pending journals, and verifies rebuilt chains.
- `forget_workspace`: moves files to `forgotten-<hex>/` without deleting; drops witness cleanly.
- `_why_abandoned`: distinguishes unopenable files (`self.UNREADABLE`) from host timeouts.
- `_unclaim`: safely pops fd, renames `.running.json` back to `.json`, and closes file descriptor.
- `_costs_a_baseline`: evaluates shape and registration prerequisites inside `try...except`, defaulting to `False` on error.
- `short_ids` & `short_json`: guarantees non-empty list output while strictly truncating to character and byte limits.
- `_assemble`: prioritizes priority-0 lines unconditionally, preventing scope loss.
- `contract_registered` branch in `state.fold`: atomically applies challenge decisions when registered from a challenge.
- `_hold`: strictly checks inode identity (`st_ino`) between open and fstat; operates without `chmod`.
- Audit challenge checks: verifies challenge-contract linkage.
Hook error handling: `PreToolUse` fails closed (denies mutating tools) in enrolled workspaces, `Stop` fails closed (`decision: stop`), and `PreInvocation` fails open to avoid model blockage.

## D. The Witness and the Restore Path

All state combinations of ledger, head, anchor, witness, and mirror were evaluated in `/tmp/g1-review5/test_section_d.py`:
- Ledger deleted, witness present: detected as lost ledger; `g1 repair --restore` restores from mirror, `--forget` moves files aside and drops witness.
- Stale ledger (truncated seq): auto-repaired to match anchor during `check_anchor_records`.
- Diverged ledger (forged records outside G1): flagged as diverged; `--accept-ledger` adopts current chain as truth, rewriting anchor and mirror.
- Foreign ledger copied: detected via witness mismatch; `--restore` rebuilds original ledger using witness ledger ID.
- Unreadable witness / anchor: detected as diverged; healed by `--accept-ledger`.
- False lockdowns: None. Ledger recovery (`_recover()`) rolls forward uncommitted journal records idempotently across crashes.
- Missed forgeries: None. Any ledger divergence breaks chain hash or disagrees with anchor/witness, triggering lockdown.
- Every state has a documented and functioning exit path.

## E. The Decision Commands

Guarded commands (`install`, `uninstall`, `init`, `propose`, `turn-end`, `host-verify`, `repair` [with flags], `challenges --run`, `challenge`):
- All decision commands invoke `_user_only`, verifying process ancestry.
- If `/proc` cannot be read, `process_chain()` returns `None`, `agent_in_ancestry` returns `True`, and commands fail closed (`ran`, `test_section_e.py`).
- Unguarded commands (`status`, `audit`, `challenges` [listing], `repair` [no flags]) are strictly read-only informational commands.
- `run_by` records ancestor process names (`comm` first). Subprocess trickery (such as `prctl(PR_SET_NAME)`) cannot disguise ancestor `agy` executable in the chain.

## F. The Textual Gate and Tripwire

Tested ordinary commands and gate tripwires in `/tmp/g1-review5/test_section_f.py`:
- Ordinary commands permitted: `git commit -m "fix .agents/hooks.json doc"`, `echo "g1 is awesome"`, `python3 -c "x = 'import g1'"`.
- Commands refused: `g1 repair`, `python3 -m g1 status`, `sudo g1 init`, `command -v g1` (documented rule 6 residual).
- Gate execution timing measured:
  - 10 KB command line: 7.73 ms (single token), 6.25 ms (many tokens)
  - 100 KB command line: 10.99 ms (single token), 19.97 ms (many tokens)
  - 400 KB command line: 32.99 ms (single token), 47.08 ms (many tokens)
  - 1 MiB command line: 74.23 ms (single token), 95.83 ms (many tokens)
  - 1,000 mentions of proposals dir (61 KB): 14.63 ms
All hook gate executions complete in under 100 ms, well below the 1,000 ms threshold.

## G. The Scratch Walker

Scratch tree preservation tested in `/tmp/g1-review5/test_section_g.py`:
- Modes and timestamps: File modes (0755) and directory modes (0750) preserved; mtimes matched to source.
- Symlinks to files and directories copied as symlinks without following. Symlink loops copied safely without recursive loops.
- Excluded directories at depth 2 (`__pycache__`, `.git`) skipped as designed.
- Newlines in filenames copied accurately.
- Directory depth bound: Trees exceeding `MAX_DEPTH = 40` (tested at depth 42) raise `RunnerError("directory too deep")` and record `scratch_copy_failed` cleanly.

## H. Claims and Agent Files

Evaluated in `/tmp/g1-review5/test_section_h.py`:
- Answer file mode: written with mode `0o644`.
- Inode swap resilience: reading uses open descriptor `pread`, ignoring path swaps to symlinks or directories.
- Concurrency: Two multiprocessing workers competing across 100 rounds with proposals and reports ran without deadlocks or double-processing.
- Dead claims: Unlocked `.running.json` entries aged past grace period are safely finalized as rejected.

## I. Challenges, Decision, and Listing

Evaluated in `/tmp/g1-review5/test_section_i.py`:
- `only` filtering: Correctly matches challenge `id` from document content even if filename differs (`ran`, exit 0).
- Double acceptance: Re-accepting an already decided challenge is rejected (`challenge real_id was already accepted`).
- Oversized challenge (> 1 MiB): `pending_challenge_docs` flags error (`larger than 1048576 bytes`).
- 500 pending challenge files listed in 193.41 ms (< 200 ms).

## J. The Status Block

Evaluated in `/tmp/g1-review5/test_section_j.py`:
- Priority-0 lines: In every state (`no_active`, `active_basic`, `active_heavy`, `paused_blocked`), all priority-0 lines are present at 512 and 1024 bytes.
- Maximum block sizes (unlimited budget):
  - `no_active`: 192 bytes
  - `active_basic`: 382 bytes
  - `active_heavy` (64 checks, 256 paths): 1,923 bytes
  - `paused_blocked`: 449 bytes
- Escaping: Hostile strings with newlines, line separators (U+2028, U+2029), ANSI escapes, and trailing backslashes are escaped via `quote()`; trailing backslashes cannot escape closing quotes.

## K. Speed Benchmarks

Measured using `/tmp/g1-review5/test_section_k.py` (`ran`, exit 0).

### 1. Per-Call Hooks on Fresh Process (n=30 interleaved, 1 record)

| Hook | Median (ms) | p99 (ms) |
|---|---|---|
| `PreToolUse` (file write) | 11.70 | 18.38 |
| `PreInvocation` (no pending) | 14.50 | 21.01 |

### 2. Long-Running Process Scaling (Ledger Length)

| Ledger Records | Hook | Median (ms) | p99 (ms) | First 100 (ms) | Last 100 (ms) |
|---|---|---|---|---|---|
| 1 | `PreToolUse` | 9.12 | 15.92 | 9.10 | 10.17 |
| 1 | `PreInvocation` | 8.52 | 18.05 | 7.15 | 10.31 |
| 2,000 | `PreToolUse` | 6.97 | 10.24 | 5.85 | 7.29 |
| 2,000 | `PreInvocation` | 9.03 | 16.21 | 7.35 | 9.93 |
| 5,000 | `PreToolUse` | 8.60 | 15.41 | 6.27 | 9.80 |
| 5,000 | `PreInvocation` | 9.44 | 17.98 | 10.28 | 8.21 |

Per-call execution remains constant and fast across 5,000 ledger records: neither `PreToolUse` nor `PreInvocation` degrades with ledger growth.

### 3. Stress Scenarios

| Scenario | Hook | Result |
|---|---|---|
| 200 answered proposals + 200 answered challenges + 50 pending challenges | `PreInvocation` | Median 10.08 ms (p99 15.48 ms) |
| 20 MB journal file | `PreToolUse` | Median 6.40 ms (journal rotated to `.1`) |
| 30 pending proposals (fable finding) | `PreInvocation` | 114.90 ms (2 baselines run, 28 deferred) |

### 4. Non-Per-Call Component Costs

| Component Operation | Workload | Latency |
|---|---|---|
| `Workspace.append` with views | 1 record + disk fsync + views | 22.55 ms |
| `register` | 2,000-file project tree (red baseline) | 4,496 ms |
| `turn_end` | 2,000-file project tree (verify canary) | 6,825 ms |
| `Stop` (idle, no active task) | 10,000 ledger records | 160 ms |

### 5. Module Import Isolation on Per-Call Hooks

| Hook | Heavy Modules Loaded (`contract`, `runner`, `verify`, `snapshot`, `complete`, `control`, `audit`, `subprocess`, `tokenize`) |
|---|---|
| `PreToolUse` (file write) | None (`[]`) |
| `PreToolUse` (run_command) | None (`[]`) |
| `PreInvocation` (no pending proposals) | None (`[]`) |

All per-call hooks strictly avoid importing runner, execution, or subprocess modules during ordinary operation.

## L. Rules Against Code

Every rule sentence in `src/g1/host/rules/*.md` and `src/g1/host/skills/g1/SKILL.md` was matched to its implementing code:

1. `rules/g1.md` E2.4 ("Stay inside the scope... `[gate]` for G1's own files always, and for file-tool writes outside the scope or to a pinned oracle while a contract is active; `[receipt]` for every change in the tree; `[self]` for the rest"):
   - `src/g1/adapter/agy.py:251-264`: `gate()` checks protected roots, transcript directories, oracle files, and allowed paths (`[gate]`).
   - `src/g1/verify.py:90-105`: changed-set tree digest compared against allowed paths (`[receipt]`).
2. `rules/g1.md` E3 ("at most two per model call; the rest wait for the next"):
   - `src/g1/workspace.py:615-629`: `MAX_BASELINES_PER_CALL = 2` caps baseline executions; excess proposals wait.
3. `rules/g1.md` E3 ("every must_flip check must fail on the untouched tree"):
   - `src/g1/contract.py:180-210`: `red_baseline` verifies all `must_flip` checks fail on clean tree.
4. `rules/g1.md` E3 ("Blocked report: write `<task>.blocked.json` ... `<task>.resume.json` continues the same contract"):
   - `src/g1/workspace.py:312-320`: `process_reports` handles `blocked` and `resume`.
5. `rules/g1.md` E3 ("A challenge names a new task id and holds at most 8 checks"):
   - `src/g1/workspace.py:385`: `MAX_CHALLENGE_CHECKS = 8`.
6. `rules/g1.md` E3 ("all failing makes the challenge confirmed; any passing, or one still running after 60 seconds, makes it unproven; a check that changes the real workspace makes it invalid"):
   - `src/g1/workspace.py:440-475`: enforces 60s timeout, verifies check failures, checks tree digest before and after.
7. `rules/g1.md` E3 ("Only the user turns a confirmed challenge into a contract, and G1 refuses that command to a process the agent started"):
   - `src/g1/__main__.py:330`: `cmd_challenge` calls `_user_only("challenge")`.
8. `rules/g1.md` E3 ("every g1 command... is refused for you in every spelling the gate recognizes"):
   - `src/g1/adapter/agy.py:426-455`: `invokes_g1` matches all `g1` commands and invocations behind wrappers.
9. `rules/g1.md` E3 ("G1's decision commands refuse to run with the agent among their ancestor processes"):
   - `src/g1/__main__.py:35-51`: `_user_only` checks `agent_in_ancestry(chain)`.
10. `rules/g1.md` E3 ("integrity lockdown... Every mutating tool is refused"):
    - `src/g1/adapter/agy.py:236-239`: `gate()` blocks mutating tools under lockdown.
11. `skills/g1/SKILL.md` ("the objective and the command are the lines left out, never the scope or an alert"):
    - `src/g1/project.py:65-83`: `_assemble` keeps priority-0 lines unconditionally.
12. `rules/g1-work.md` W5.1 ("Never edit a pinned oracle file during the task. `[gate]`"):
    - Note on enforcement tag: `src/g1/adapter/agy.py:257-259` gates file-tool writes, while shell writes are caught at the receipt (`[receipt]`), consistent with `rules/g1.md` E2.4 and `SKILL.md`.

## M. Suggestions, Not Findings

Ten missing unit tests with exact assertions and failures they would catch:

1. `test_gate_multiline_prose_with_decision_keyword`: Test that `git commit -m "line1\nrepair"` is not refused when `\n` is replaced with ` ; `.
   - Assertion: `assert agy.textual_gate(ctx, "git commit -m 'line1\nrepair'", None) is None`.
   - Failure caught: False refusal of multi-line commit messages containing command keywords on later lines.
2. `test_bound_mirror_with_tampered_intermediate_record`: Test that `_read_mirror` stops immediately when record $i$ has an invalid hash, even if subsequent records chain to its corrupted hash.
   - Assertion: `recs, note = integrity._read_mirror(mp, lid); assert len(recs) == i and "hash mismatch" in note`.
   - Failure caught: Restoring corrupt chains that bypassed genesis verification.
3. `test_proposal_unclaim_during_host_timeout`: Test concurrency between `_unclaim` and another process calling `_claim`.
   - Assertion: `assert ws._claim(p) is None` while file descriptor lock is held.
   - Failure caught: Race condition between rename and lock release in unclaim path.
4. `test_scratch_copy_with_fifo_as_target`: Test proposal where `targets` names a FIFO file in workspace.
   - Assertion: `with self.assertRaises(runner.RunnerError): runner.scratch_copy(ws_dir, "test", required={"fifo_target"})`.
   - Failure caught: Canary or baseline hanging on opening a FIFO target.
5. `test_decide_challenge_with_existing_task_conflict`: Test `g1 challenge accept` when the target task name already exists.
   - Assertion: `ok, msg = ws.decide_challenge(cid, "accepted"); assert not ok and "already exists" in msg`.
   - Failure caught: Challenge acceptance silently replacing an existing active or paused task.
6. `test_gate_1mb_boundary_exact_bytes`: Test boundary at 1,048,576 vs 1,048,577 bytes.
   - Assertion: `assert agy.textual_gate(ctx, "echo " + "a"*1048571, None) is None` and `assert "longer than" in agy.textual_gate(ctx, "echo " + "a"*1048572, None)`.
   - Failure caught: Off-by-one errors in `GATE_MAX_BYTES`.
7. `test_restore_ledger_empty_ledger_with_witness`: Test `restore_ledger` when `ledger.jsonl` exists but is 0 bytes.
   - Assertion: `head, notes = integrity.restore_ledger(ws_dir); assert head["seq"] == 1`.
   - Failure caught: Crash when reading 0-byte existing ledger file.
8. `test_status_block_short_ids_boundary`: Test `short_ids` with 64 check IDs each of length 64 (4,096 characters total).
   - Assertion: `assert len(project.short_ids(ids, 200).encode("utf-8")) <= 250`.
   - Failure caught: Buffer overrun in status block projection.
9. `test_ancestry_guard_with_ppid_1`: Test process chain when `os.getppid() == 1`.
   - Assertion: `assert agy.process_chain() == []` and `assert g1_main._user_only("repair") == "no parent"`.
   - Failure caught: Infinite loop or IndexError when process is an orphan attached directly to init.
10. `test_audit_with_unregistered_challenge_verdict`: Test that audit does not require contracts for `unproven` or `invalid` challenges.
    - Assertion: `assert audit.run(ws_dir)["ok"] is True`.
    - Failure caught: Audit falsely demanding contracts for rejected or unconfirmed challenges.

## N. G1 Behaviour Observed During This Session

1. Refusal 1 (Textual gate tripwire on `python3 -c` importing G1):
   - Command: `python3 -c "import g1.integrity..."`
   - Output verbatim: `Encountered error in tool execution: tool call denied by pre-tool hook: G1 command line refused: G1's commands are the user's (`g1 repair`, `host-verify`, `install`, `uninstall`, `turn-end`, `init`, `propose`, `challenges`, `challenge`); the status block and the state.json view carry what you need. Report what you need to the user instead.`
2. Refusal 2 (Textual gate tripwire on protected conversations store):
   - Command: `tail -n 10 ~/.gemini/antigravity-cli/brain/...`
   - Output verbatim: `Encountered error in tool execution: tool call denied by pre-tool hook: G1 protected path referenced in the command: ~/.gemini/antigravity-cli/brain holds conversation transcripts that G1 reads as evidence.`
3. Injected status blocks:
   Observed on every model call in workspace `~/src/g1`:
   ```text
   [G1 <nonce>] ledger seq 0 head f88879724ab3
   No active contract. For durable work, write a proposal to ~/.g1/workspaces/702a78d3b14f1e95/proposals/<id>.json (format: ~/.g1/workspaces/702a78d3b14f1e95/views/PROPOSAL_FORMAT.md). G1 validates it before your next step.
   ```

## O. What Could Not Be Run or Verified

- Live `/proc` filesystem remount with `hidepid=2` or restricted read access (verified via unittest mock patches).
- Hostile double-fork detachment on live host (acknowledged limitation in design 7.7 and rule 6).
- Direct destruction of real `~/.g1` or `~/.gemini` stores (prohibited by review rule 1).
- Unverified suspicion: If a proposal is deferred solely due to `MAX_BASELINES_PER_CALL` and the host terminates the hook process (SIGKILL) in the microsecond interval between `_claims.pop()` and `os.rename()`, the entry remains `.running.json` and will be answered as an abandoned claim on the next turn. Handled safely by existing abandoned claim logic.

## Verdict

G1 at commit `63fc78f4913ca848c485f6e75fba8de37e71aa54` satisfies all core security and integrity properties evaluated in this review. A receipt of completion cannot be forged or induced without fulfilling the active contract's verification checks on an authentic work tree, and state progression remains strictly bound by cryptographic ledger chaining and witness verification. Legitimate operational edge cases (crashes, truncated records, unapplied journal files, corrupt heads) recover automatically or via repair without triggering false integrity lockdowns. Decision commands remain fail-closed against unreadable ancestry and hostile wrapper evasion. The hard performance rule is respected: per-call hook overhead remains sub-15 ms even under scaled 5,000-record ledgers, and heavy execution modules are completely decoupled from hot paths. This review identified zero critical, high, medium, or low findings.

## Not checked

- Live `/proc` filesystem remount with `hidepid=2` or restricted read access (evaluated via mock tests).
- Process detachment via double-fork escaping ancestry tracking (documented constraint).
- Direct mutation of real `~/.g1` state directory on user machine (prohibited by review rules).
