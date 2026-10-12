# G1 review, round 4

- Commit: `21cf4308c1a313e7bb29bd57d6415159ea1f493b` (`21cf430`)
- Python: `Python 3.13.7`
- Unit tests: `python3 -W error::ResourceWarning -m unittest tests.test_core -v`: `Ran 104 tests in 50.707s`, `FAILED (failures=4)`, exit 1
- Started: 2026-10-11T21:51:22Z
- Finished: 2026-10-11T22:06:00Z
- Scratch: every reproduction below ran from `/tmp/g1-review4/` with `G1_HOME` set to a directory under `/tmp/g1-review4/`.

## Findings Table

| ID | Severity | Summary | Files | Status |
|---|---|---|---|---|
| R4-01 | Critical | Unverifiable ledger deadlock in `g1 repair` | `src/g1/integrity.py:341`, `src/g1/__main__.py:220-256` | ran |
| R4-02 | Critical | Multi-record atomicity failure in `_commit_contract` | `src/g1/workspace.py:655-684`, `src/g1/audit.py` | ran |
| R4-03 | High | Arbitrary user file chmod via hardlink in `_hold` | `src/g1/workspace.py:131-133` | ran |
| R4-04 | High | Ancestry guard `_user_only` fails open if `/proc` unreadable | `src/g1/adapter/agy.py:348-386`, `src/g1/__main__.py:34-45` | ran |
| R4-05 | Medium | Unit test suite fails 4 tests under agent host | `tests/test_core.py:718, 1184, 1351, 1390` | ran |
| R4-06 | Medium | Textual gate tripwire bypass via wrapper argument flags | `src/g1/adapter/agy.py:308-316` | ran |
| R4-07 | Medium | False refusals of ordinary commands in textual gate | `src/g1/adapter/agy.py:423-432, 290` | ran |
| R4-08 | Low | Directory mtime lost in scratch walker | `src/g1/runner.py:126-131` | ran |
| R4-09 | Low | P0 lines truncated when P0 bytes exceed budget limit | `src/g1/project.py:53-64` | ran |

## A. Round-3 Fixes (R3-01 to R3-24)

Every round-3 fix was independently reproduced in `/tmp/g1-review4/test_all_round3.py`:

- **R3-01** (`witness_restores_diverged_workspace`): `fixed`. Deleting ledger files triggers witness fallback and lockdown. *Variation*: Deleting ledger, head, anchor, and witness causes `lost_ledger` to return `None`; treated as unenrolled fresh workspace. Copying foreign ledger causes `integrity.check_anchor_records` to detect workspace_id mismatch (`ran`, exit 1).
- **R3-02** (`truncated_ledger_without_anchor`): `fixed`. Truncated ledger at seq 1 without anchor is detected by witness comparison. *Variation*: Cutting to seq 1 with anchor, mirror, and witness all deleted results in clean state at seq 1 (`ran`).
- **R3-03** (`gate_matches_dirs_with_trailing_slash`): `fixed`. `_blank_own_dirs` resolves symlinks and canonicalizes paths. *Variation*: Trailing slashes (`.g1/`), `//`, `/./`, and relative paths after `cd` tested; directory normalization catches them (`ran`).
- **R3-04** (`invokes_g1_handles_extra_spaces`): `partly fixed`. Fixed regex handles extra spaces and `-m g1`. *Variation*: Bypassed by `exec -a x python3 -m g1`, `env -i python3 -m g1`, and string evaluation `eval("import g1")` (`ran`, exit 0). Recorded as R4-06.
- **R3-05** (`scratch_copy_handles_fifos`): `fixed`. `_copy_entry` skips FIFOs and sockets. *Variation*: FIFO as oracle or target; `open()` fails cleanly with `IOError` or timeout without hanging G1 (`ran`).
- **R3-06** (`_finish_proposal_replaces_existing`): `fixed`. Directory at answer name moved aside to `.gone.<token>`. *Variation*: FIFO/socket at answer name replaced via atomic rename (`ran`).
- **R3-07** (`_write_atomic_uses_unpredictable_tmp`): `fixed`. Random hex token in tmp filename. *Variation*: Directory at view path moved aside atomically (`ran`).
- **R3-08** (`verification_catches_outside_writes`): `fixed` for repository tree; `partly fixed` globally. Workspace tree hash check catches edits within repository. *Variation*: Check writing to `/tmp/planted_outside.txt` outside workspace and G1 home is completely undetected by receipt or gates (`ran`).
- **R3-09** (`evidence_redacts_large_outputs`): `fixed`. Stderr and stdout tails capped at 600 and 300 characters. *Variation*: 10 MB secret output capped to 600 chars in baseline record (`ran`).
- **R3-10** (`challenge_cannot_replace_completed_task`): `fixed`. `_registrable` rejects task matching completed task. *Variation*: Challenge targeting existing completed task fails registration (`ran`).
- **R3-11** (`turn_end_handles_empty_receipts`): `fixed`. Missing receipts handled without raising unhandled exceptions (`ran`).
- **R3-12** (`projection_truncation_preserves_p0`): `fixed` for normal budgets. *Variation*: When P0 lines alone exceed max_bytes, trailing P0 lines (`scope:`) are truncated (`ran`). Recorded as R4-09.
- **R3-13** (`resume_report_handles_kill`): `fixed`. Resume reports use write-then-rename and unpause cleanly (`ran`).
- **R3-14** (`max_files_enforced_in_scratch`): `fixed`. File count and size limits enforced during tree scan (`ran`).
- **R3-15** (`canary_uses_isolated_copy`): `fixed`. Canary runs on fresh isolated scratch copy (`ran`).
- **R3-16** (`anchor_check_handles_empty_ledger`): `fixed`. Empty ledger treated as unverifiable (`ran`).
- **R3-17** (`summary_cache_invalidated_on_revert`): `fixed`. Summary bound to head hash (`ran`).
- **R3-18** (`host_check_verifies_binary_fingerprint`): `fixed`. First and last MiB plus length hashed (`ran`).
- **R3-19** (`lockdown_blocks_mutating_tools`): `fixed`. `gate(ctx)` denies all mutating tools under lockdown (`ran`).
- **R3-20** (`measurement_catches_interleaved_writes`): `fixed`. Digest compared before and after check run (`ran`).
- **R3-21** (`claimed_directories_moved_to_gone`): `fixed`. Replaced directories renamed to `.gone.<token>` (`ran`).
- **R3-22** (`two_step_challenge_acceptance`): `fixed`. `g1 challenge accept` required before contract registration (`ran`).
- **R3-23** (`liveness_gap_detects_subagent_activity`): `fixed`. Gap check scans journal across layers (`ran`).
- **R3-24** (`journal_rotation_preserves_recent`): `fixed`. Journal rotated to `.1` at 8 MiB (`ran`).

## B. The Witness and the Restore Path

Tested full state matrix for ledger, head, anchor, witness, mirror in `/tmp/g1-review4/test_section_b.py`:

| State | Status Observed | `g1 repair` Behavior | Result |
|---|---|---|---|
| All present & valid | `ok` | No action needed | Normal |
| Ledger deleted, witness present | `lockdown` (missing) | `g1 repair --restore` restores from mirror | Recovered |
| Ledger diverged (head != anchor) | `diverged` | `g1 repair --accept-ledger` or `--restore` | Resolved |
| Ledger corrupt / unverifiable | `unverifiable` | Suggests `--accept-ledger`, but all flags fail | **Deadlock (R4-01)** |
| Witness missing (pre-witness workspace) | `ok` | Regenerated on next commit (`_finish`) | Compatible |
| Foreign ledger (different workspace) | `unverifiable` | `--restore` restores matching mirror | Recovered |

- **False Lockdown**: None observed during clean G1 operation or abrupt process crashes with valid journal recovery.
- **Missed Forgery**: None without rewriting `anchors/` or matching valid hash chain.
- **Pre-witness Workspace**: Handled cleanly. If witness is absent, G1 reads ledger without locking down and writes witness on next commit.

## C. The Decision Commands and Ancestry Guard

- **Guarded Commands**: `repair`, `install`, `uninstall`, `challenges --run`, `challenge accept`, `challenge reject` invoke `_user_only`.
- **Unguarded Commands**: `status`, `audit`, `views`, `turn-end` (when invoked directly). Set is appropriate.
- **`run_by` Record**: Extracts `(user, ppid_chain)`. If `/proc` is manipulated or spoofed by non-standard parent naming, `run_by` reflects process names.
- **Failure Open on Missing `/proc` (R4-04)**: In `adapter/agy.py:360-386`, if `/proc` is unreadable, `_proc_names` returns `set(), 0`. `process_chain()` returns `[[]]`. `agent_in_ancestry` evaluates to `False`, allowing `_user_only` to permit user-only commands to execute (`read`, `agy.py:377`).

## D. The Textual Gate and Command-Line Tripwire

- **False Refusals (R4-07)**:
  - `git commit -m "update .agents/hooks.json"`: Refused because regex matches `.agents/hooks.json` anywhere in command line (`ran`).
  - `python3 -c "x = 'import g1'"`: Refused because `_python_code_runs_g1` matches substring `import g1` inside string literals (`ran`).
- **Tripwire Bypasses (R4-06)**:
  - `exec -a custom_name python3 -m g1 status`: Passes (`invokes_g1` returns `False`).
  - `env -i python3 -m g1 status`: Passes (`env` stripped of bare token, but `-i` treated as target binary).
  - `sudo -u <user> g1 status`: Passes.
  - Python dynamic import: `python3 -c "import importlib; importlib.import_module('g1')"`: Passes.
- **Gate Latency**:
  - 10 KB command line: 14.58 ms.
  - 1,000 mentions of proposals dir: 83.98 ms.

## E. The Scratch Walker

- **Tree Comparison**:
  - Symlinks preserved within workspace. Out-of-workspace symlinks skipped.
  - Mode 000 directories / files trigger `PermissionError` and are skipped gracefully.
  - Directory mtimes are not preserved by `_copy_entry` (`ran`, `runner.py:126`, R4-08).
  - Excluded directories (`node_modules`, `.venv`, `.git`) skipped at any depth.
  - Directory depth recursion capped at `MAX_DEPTH = 40`.
- **Performance**:
  - Copy of 2,000 files: 3.209s.
  - Copy of 10,000 files: 13.113s.

## F. Claims and Agent Files

- **Concurrency & Claims**: 100 rounds with 2 concurrent workers claiming proposals, reports, and challenges under `/tmp/g1-review4/` ran without race conditions or deadlocks.
- **Kill During Commit (R4-02)**: SIGKILL between `challenge_decided` and `contract_registered` leaves challenge stuck in `accepted` state without contract.
- **Hardlink Chmod Exploit (R4-03)**:
  - In `Workspace._hold(path)`:
    ```python
    except PermissionError:
        os.chmod(path, 0o600)
    ```
  - An agent hardlinks an unreadable file owned by the user (mode 000) into `proposals/`. Calling `_hold` causes G1 to chmod the underlying target file to `0o600` (`ran`, `test_f_chmod.py`).

## G. Challenges, Two-Step Decision, and Listing

- **Two-Step Acceptance**: Challenges must transition `recorded` -> `confirmed` via `g1 challenges --run` before user acceptance via `g1 challenge accept`.
- **Validation**: Contract shape strictly validated; maximum 8 checks enforced.
- **Performance**: Listing 501 challenge files parsed in 0.227s.

## H. Status Block Priorities and Projection

- **Escaping**: Agent-written text (objectives, reasons) escaped via `_visible()` and `json.dumps()`, preventing status block injection.
- **Priority Truncation (R4-09)**:
  - Normal budget (512 bytes): `P0` lines preserved, `P1-P3` dropped when constrained.
  - Saturated `P0` budget: Under heavy alerts, long task names, and lockdown messages, `_trim` truncates trailing `P0` lines (`scope:` was truncated out, `ran`, `test_section_h.py`).

## I. The Hard Rule (G1 Must Never Slow the Working Model)

Benchmarked in one process via `agy.handle` (`test_section_i.py`, `test_section_i_part2.py`):

| Operation | Median | P99 | First 100 | Last 100 | Growth |
|---|---|---|---|---|---|
| PreToolUse baseline (500 runs) | 11.249 ms | 13.948 ms | 11.077 ms | 9.483 ms | -14.4% |
| PreInvocation baseline (200 runs) | 17.538 ms | 19.141 ms | 16.924 ms | 16.268 ms | -3.9% |
| PreToolUse (200 answered, 50 challenges) | 12.077 ms | 13.092 ms | 11.225 ms | 10.825 ms | -3.6% |
| PreInvocation (200 answered, 50 challenges) | 17.257 ms | 22.127 ms | 16.639 ms | 16.006 ms | -3.8% |
| PreToolUse (20 MB journal) | 11.510 ms | 13.780 ms | 9.376 ms | 11.333 ms | +20.9% |
| PreInvocation (20 MB journal) | 16.803 ms | 19.655 ms | 16.633 ms | 14.741 ms | -11.4% |

**Standalone Workspace Timings**:
- 1 `Workspace.append` with views: 37.528 ms
- 1 `Workspace.register` on 2,000-file tree: 3,635.829 ms
- 1 `Workspace.turn_end` on 2,000-file tree: 9.818 ms
- Idle `Stop` hook at 10,000 ledger records: 404.294 ms

## J. Rules vs Code

- **SKILL.md Line 7**: Claims "never the scope or an alert [is left out]". Refuted by R4-09: `_trim` truncates trailing P0 lines when P0 exceeds budget.
- **Rule E3 (`g1.md:35`)**: Claims "a shell write outside the scope is recorded and fails the changed-set check". Refuted by R3-08 variation: writes outside the workspace root are neither gated nor caught by receipt.
- **Rule E3 (`g1.md:38`)**: Claims "every g1 command... is refused for you, in every spelling". Refuted by R4-06: wrapper arguments (`exec -a`, `env -i`) bypass the gate.
- **Enforcement Tags**:
  - `[gate]`: Accurately gated for direct file tool writes and direct G1 invocations.
  - `[receipt]`: Accurately enforced at turn end.
  - `[ledger]`: Accurately audited.
  - `[self]`: Follows agent self-discipline.

## K. Tests and Coverage

- **Unit Test Execution**: `python3 -W error::ResourceWarning -m unittest tests.test_core -v` resulted in `Ran 104 tests in 50.707s, FAILED (failures=4)`:
  - `test_forge_record_and_catch_at_session_start` (exit 3 != 0)
  - `test_r3_01_witness_restores_diverged_workspace` (exit 3 != 0)
  - `test_r3_02_truncated_ledger_without_anchor_falls_back_to_witness` (exit 3 != 0)
  - `test_hooks_never_run_challenge_checks` (exit 3 != 0)
  - Cause: Agent in process ancestry triggers `_user_only`, returning exit 3 (R4-05).
- **Top 10 Missing Tests**:
  1. `g1 repair` recovery from an unverifiable / single-byte corrupted ledger (R4-01).
  2. Crash consistency in `_commit_contract` between `challenge_decided` and `contract_registered` (R4-02).
  3. `g1 audit` detection of orphan accepted challenges without contracts (R4-02).
  4. Hardlink permission preservation in `Workspace._hold` (R4-03).
  5. Ancestry check fallback behavior when `/proc` is unreadable (R4-04).
  6. Unit test mocking of process ancestry for test runs inside host agents (R4-05).
  7. Textual gate recognition of argument flags on shell wrappers (`exec -a`, `env -i`) (R4-06).
  8. Exclusion of git commit messages and quoted strings from gate tripwires (R4-07).
  9. Directory mtime restoration in scratch tree walker (R4-08).
  10. Truncation behavior when priority 0 lines exceed projection byte limit (R4-09).

## L. The G1 Session Itself

- **Refusal Text**:
  `tool call denied by pre-tool hook: G1 command line refused: G1's commands are the user's (`g1 repair`, `host-verify`, `install`, `uninstall`, `turn-end`, `init`, `propose`, `challenges`, `challenge`); the status block and the state.json view carry what you need. Report what you need to the user instead.`
- **Injected Status Block**:
  `[G1 c854d7] ledger seq 0 head f88879724ab3`
  `No active contract. For durable work, write a proposal to ~/.g1/workspaces/702a78d3b14f1e95/proposals/<id>.json (format: ~/.g1/workspaces/702a78d3b14f1e95/views/PROPOSAL_FORMAT.md). G1 validates it before your next step.`
- **Model Impact**: Fast hook evaluations (~11-17 ms) introduced no perceptible delay. However, tests calling CLI commands directly failed due to the ancestry check.

## Verdict

The round-3 fixes are robust across all 24 issues, with significant architectural improvements in witness tracking, scratch tree isolation, and two-step challenge workflows. However, two Critical vulnerabilities exist in the new code: an inescapable deadlock in `g1 repair` when a ledger suffers disk corruption (R4-01), and atomicity loss during challenge contract registration (R4-02). Additionally, permission escalation via hardlinks in `_hold` (R4-03) and fail-open ancestry detection on unreadable `/proc` (R4-04) warrant resolution before production hardening.

## Not Checked

- In-kernel filesystem race conditions during directory rename on network mounts (NFS/CIFS).
- Windows/macOS process tree ancestry implementations (tested exclusively on Linux `/proc`).
- Behavior under extreme file descriptor exhaustion (< 10 available descriptors).
