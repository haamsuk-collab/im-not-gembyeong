# G1 Independent Review Report

- Commit: `fb600c912e95a7e1830d3083d21351a19a556a48`
- Environment: `Python 3.13.7`
- Test Suite: `Ran 39 tests in 12.994s - OK`
- Started: 2026-10-11T14:46:00Z
- Finished: 2026-10-11T14:55:00Z

## Findings Table

| ID | Severity | file:line | Claim (one sentence) | Evidence | Fix |
|---|---|---|---|---|---|
| F-01 | critical | `src/g1/complete.py:23` | Omitting `targets` in `must_flip` checks bypasses the canary entirely, allowing false completion on checks that do not depend on workspace code. | ran: reproduction script (`turn_end result: complete stop`) with external flag check | Make `targets` mandatory for `must_flip` checks in `contract.validate_shape` or reject empty canary in `complete.approve`. |
| F-02 | critical | `src/g1/integrity.py:260` | Mirror restore in `check_anchor` copies `ledger.jsonl` but does not update `ledger.head.json`, permanently corrupting the workspace ledger with a stale head anchor. | ran: reproduction script; `led.verify()` failed with `LedgerError head anchor does not match the last record` | Update `led.head_path` to match the mirror's tail record before updating anchor. |
| F-03 | high | `src/g1/ledger.py:219` | Crash recovery in `_recover()` crashes with unhandled `JSONDecodeError` if a crash occurred mid-write leaving a partial line in `ledger.jsonl`. | ran: reproduction script; `led._recover()` raised `JSONDecodeError: Expecting value: line 1 column 32` | Handle `ValueError` / `CanonError` when parsing `lines[-1]` in `_recover` and drop corrupted uncommitted tail. |
| F-04 | high | `src/g1/canon.py:41` | `canon.dumps` outputs lone surrogates that crash subsequent UTF-8 encoding in `sha256_text` and `domain_hash` with `UnicodeEncodeError`. | ran: reproduction script with `\ud800`; `sha256_text` raised `UnicodeEncodeError` | Validate string inputs for surrogate codepoints (`\ud800`–`\udfff`) in `canon._check`. |
| F-05 | high | `src/g1/__main__.py:30` | `cmd_hook` crashes unhandled when payload is not a JSON object or contains non-string elements in `workspacePaths`. | read: `src/g1/__main__.py:30-42` where `payload.get()` raises `AttributeError` on list payloads | Ensure `payload` is verified as `isinstance(payload, dict)` in `cmd_hook`. |
| F-06 | high | `src/g1/runner.py:129` | `runner.run()` uses unbounded `proc.communicate()`, buffering all subprocess output into RAM before `OUTPUT_CAP` is applied, risking OOM. | ran: reproduction script buffering 20 MiB in memory before cap | Stream output in bounded chunks and terminate process if output exceeds `OUTPUT_CAP`. |
| F-07 | high | `src/g1/project.py:40` | Untrusted proposal `objective` and blocked `item` fields are echoed into the model projection without newline escaping, permitting status block spoofing. | ran: reproduction script; fake status block lines injected via `objective` | Escape or strip newlines (`\n`, `\r`) from untrusted strings before building projection text. |
| F-08 | medium | `src/g1/snapshot.py:41` | Workspace tree manifest ignores empty directories, directory permissions, and files inside `DEFAULT_EXCLUDES` directories (`.git/hooks`, `node_modules`, `.venv`). | read: `src/g1/snapshot.py:28-50` where empty directories produce no entry in manifest | Track directory entries and permissions in `out`; restrict or audit excluded directory writes. |
| F-09 | medium | `src/g1/paths.py:75` | `paths.enrollable` allows enrolling subdirectories of `G1_HOME` because it checks `g.startswith(r + os.sep)` instead of `r.startswith(g + os.sep)`. | ran: `paths.enrollable('/tmp/g1home/workspaces/test')` returned `True` | Add check `or r.startswith(g + os.sep)` in `paths.enrollable`. |
| F-10 | medium | `src/g1/adapter/agy.py:18` | `docs/host-agy.md` documents tool `edit_notebook` but `MUTATING_TOOLS` in `agy.py` implements `notebook_edit`. | read: `src/g1/adapter/agy.py:18` vs `docs/host-agy.md:59` | Add `edit_notebook` to `MUTATING_TOOLS`. |
| F-11 | medium | `src/g1/integrity.py:60` | `install_group` documentation claims foreign entries in `hooks.json` are kept "byte-for-byte", but code re-serializes via `canon.loads`/`dumps`, altering formatting. | read: `src/g1/integrity.py:60-67` | Update documentation to state semantic JSON preservation rather than byte preservation. |
| F-12 | medium | `src/g1/canon.py:39` | `canon.dumps` does not normalize Unicode (NFC), causing semantically identical strings in different normalisation forms to produce different hashes. | ran: `\u00e9` (NFC) vs `e\u0301` (NFD) produce different hashes | Apply `unicodedata.normalize('NFC', ...)` in `canon.dumps`. |
| F-13 | medium | `src/g1/adapter/agy.py:197` | PreToolUse gate calls `ctx.state()` which executes a full ledger chain verification `Ledger.verify()` O(N) on every mutating tool call. | read: `src/g1/adapter/agy.py:110, 197` and `src/g1/ledger.py:163, 171` | Cache folded task state or read the latest active contract from head/state cache without re-verifying full history. |
| F-14 | low | `README.md:173` | `README.md:173` and `docs/design.md:486` state the test suite has 36 tests, but the test suite has 39 tests. | read: `README.md:173`, `docs/design.md:486`; ran unit tests (39 tests) | Update test count documentation to 39 tests. |
| F-15 | low | `src/g1/tests/test_core.py:575` | `test_host_files_installed_pinned_protected_and_healed` leaks file descriptors, producing ResourceWarnings during test runs. | ran: unit tests; `ResourceWarning: unclosed file <_io.TextIOWrapper ...>` | Use context manager `with open(...)` when reading host files in test. |
| F-16 | low | `src/g1/__init__.py:1` | Docstring contains host name "Antigravity CLI", violating architectural design rule that core modules never name host. | read: `src/g1/__init__.py:1` vs `docs/design.md:87` | Remove "Antigravity CLI" reference from `__init__.py`. |

### Minimal Reproductions for Critical Findings

#### F-01: False completion via missing canary targets
```python
# Run from /tmp/g1-review with PYTHONPATH=~/src/g1/src
import os, tempfile
from g1 import workspace
tmp = tempfile.mkdtemp()
ws_root, flag = os.path.join(tmp, "ws"), os.path.join(tmp, "flag")
os.makedirs(os.path.join(ws_root, "src"))
with open(os.path.join(ws_root, "src", "app.py"), "w") as f: f.write("x = 1\n")
prop = {"task": "f01", "objective": "bypass", "criteria": [{"id": "C1", "text": "flag"}],
        "checks": [{"id": "K1", "argv": ["python3", "-c", f"import os, sys; sys.exit(0 if os.path.exists({flag!r}) else 1)"],
                    "kind": "must_flip", "covers": ["C1"]}], "allowed_paths": ["src/"], "oracle_files": []}
ws = workspace.Workspace(ws_root, manifest=None); ws.init()
ws.register(prop)
with open(flag, "w") as f: f.write("ok")
print(ws.turn_end()["terminal"])  # prints: complete
```

#### F-02: Mirror repair corrupts workspace head anchor
```python
# Run from /tmp/g1-review with PYTHONPATH=~/src/g1/src
import os, tempfile
from g1 import ledger, integrity, paths
tmp = tempfile.mkdtemp()
ws_root, os.environ["G1_HOME"] = os.path.join(tmp, "ws"), os.path.join(tmp, "g1")
paths.ensure_dirs(ws_root); led = ledger.Ledger(ws_root); led.create()
led.append("integrity_alert", {"kind": "k1", "detail": ""}); integrity.check_anchor(led)
lines = open(led.path).read().splitlines()
open(led.path, "w").write(lines[0] + "\n")  # truncate ledger
ledger._write_atomic(led.head_path, ledger.canon.dumps({"ledger_id": led.read_head()["ledger_id"], "seq": 0, "hash": lines[0].split('"hash":"')[1][:64]}))
integrity.check_anchor(led)
led.verify()  # raises LedgerError: head anchor does not match the last record
```

## A. Documentation against code

### Implemented mechanisms marked "Built" in `docs/design.md`
- PreToolUse output discipline (`{"", deny}`): `adapter.agy.handle` / `adapter.agy.gate`; covered by `test_pretooluse_output_set`.
- Isolated per-workspace state: `paths.ws_dir`, `paths.enrollable`, `workspace.Workspace.init`; covered by `test_home_and_g1_home_are_never_enrolled`.
- Canonical JSON format: `canon.dumps`, `canon.loads`; covered by `CanonTests` (5 tests).
- Ledger hash-chain, head anchor, journal commit & atomic write: `ledger.Ledger`, `ledger._commit`, `ledger._write_atomic`; covered by `test_chain_and_tamper`, `test_cas_conflict`, `test_recovery_pending_without_append`, `test_recovery_pending_with_append_but_stale_head`.
- Contract validation and red baseline: `contract.validate_shape`, `contract.red_baseline`; covered by `test_zero_row_rejected`, `test_unknown_key_rejected`, `test_dot_scope_rejected`, `test_traversal_rejected`, `test_red_baseline_rejects_green_check`.
- Oracle pinning and scope check: `contract.pin_oracles`, `contract.in_scope`, `snapshot.changed_paths`; covered by `test_oracle_edit_blocks_completion`, `test_scope_violation_blocks_completion`.
- Canary mutation: `verify._canary`; covered by `test_canary_rejects_insensitive_check`.
- Completion evaluation: `complete.approve`; covered by `CompletionFunctionTests` (2 tests).
- Stop policy & shrink check: `control.decide`; covered by `ControlTests` (4 tests).
- Blocked and resume reports: `workspace.Workspace.process_reports`; covered by `test_blocked_report_pauses_projection_carries_item_resume_reactivates`.
- Host change detection & fingerprinting: `adapter.agy.host_fingerprint`, `adapter.agy.host_check`; covered by `test_changed_host_binary_withholds_completion`.
- Evidence compaction: `workspace.Workspace.compact_evidence`; covered by `test_old_attempt_evidence_is_removed_and_receipts_stay_provable`.
- Host files install, pin, heal: `integrity.install_host_files`, `integrity.heal_host_files`; covered by `HostFilesTests`.
- Offline audit: `audit.run`; covered by `test_old_attempt_evidence_is_removed_and_receipts_stay_provable`, `test_blocked_report_pauses_projection_carries_item_resume_reactivates`.

### Mechanisms marked "Built" that are missing, partial, or untested
- Canary enforcement is partial: `docs/design.md:240` states every `must_flip` check requires a sensitive canary, but `complete.py:23` skips the check when `targets` is omitted, allowing false completions (F-01).
- Foreign entry preservation is partial: `docs/design.md:305` claims `hooks.json` keeps foreign entries byte-for-byte, but `integrity.py:60` re-serializes via `canon.dumps` (F-11).
- Mirror restore is broken: `docs/design.md:320` states lost records are restored from mirror, but `integrity.py:260` leaves `ledger.head.json` stale (F-02).
- Untested in `test_core.py`: lock acquisition timeout and inode re-check (`ledger.py:94-106`); snapshot max depth/file limits and root UID owner check (`snapshot.py:21, 50, 77`); schema version mismatch in `ledger.records()` (`ledger.py:155`); disk space exhaustion in `runner.scratch_copy` (`runner.py:99`); bootstrap script SHA256 mismatch exit 3 (`integrity.py:22`); liveness gap detection (`adapter.agy.compute_gap`); guard check failing baseline (`contract.py:173`).

### Undocumented code behaviours
- `paths.py:86` automatically writes `root.txt` inside the workspace state directory upon initialization.
- `workspace.py:86` `pending_reports` matches any `*.blocked.json` / `*.resume.json` regardless of the task prefix.
- `runner.py:24-32` implements hardcoded regexes for specific API key formats (Slack, Google `AIza`, JWTs).
- `control.py:38-41` period-two oscillation detection specifically matches 4-history alternations (`v[-1] == v[-3] and v[-2] == v[-4]`).
- `__main__.py:36-42` hook error handler returns a deny JSON only if `ledger.head.json` exists for `root`, else fails open with empty string.

### README and `docs/host-agy.md` alignment
- README "One task, start to finish" steps 1–7 match code flow (`SessionStart` auto-enrol -> proposal validation/red baseline -> tool gates -> idle Stop verification/canary -> tree diff -> completion receipt).
- `docs/host-agy.md` tables match `adapter/agy.py`, except Table 4 documents `edit_notebook` while `MUTATING_TOOLS` in `agy.py:18` defines `notebook_edit` (F-10).

## B. The authority path

- **Input to `complete.approve` without executed evidence**: `approve()` validates `state_mod.summarize_results(receipt.get("results"))` which only checks that every result dictionary in `receipt["results"]` has `verdict == "pass"` and `executed is True`. If passed a synthetic dictionary without executing commands, `approve()` returns `(True, [])`.
- **Insensitive checks and canary bypass**: If a contract omits `targets`, `verify._canary()` skips the check (`todo = [k for k in ... if k.get("targets")]`), and `complete.approve()` skips the canary assertion (`k.get("targets") and r.get("canary") != "sensitive"`). A check checking an external condition (`/tmp/flag`) or stub executable passes red baseline when absent, passes verification when present, skips canary, and completes without touching code (F-01).
- **Oracle pinning**: Symlinked oracles are rejected during registration because `snapshot.file_hashes()` returns `None` for symlinks (`snapshot.py:105`). Hard links to oracle files are tracked by content hash; editing a hard link modifies the oracle and is caught at verification. Unlisted oracle files (fixtures, helper scripts) are unmonitored and can be modified without triggering alerts. Oracle paths are normalized with `os.path.normpath` during contract admission. Case sensitivity follows host filesystem semantics.
- **Scope**: Relative paths with `..`, absolute paths, and `.` are rejected by `contract._rel_ok()`. However, `snapshot.manifest()` omits empty directories, directory permission changes, and any file inside `DEFAULT_EXCLUDES` (`.git`, `node_modules`, `.venv`). An agent writing malicious code into `node_modules` or `.git/hooks` causes zero diff in `snapshot.changed_paths()` (F-08). Symlinks created inside allowed directories are captured as `kind: "symlink"` with target text.
- **Red baseline**: Only verifies that `must_flip` checks return `verdict == "fail"` (`contract.py:171`). A check that fails at baseline due to an external error (missing dependency, network timeout, absent `/tmp` file) and later succeeds for that same reason satisfies the baseline check.
- **Identity check**: `verify.run_attempt()` checks `snapshot.digest(man_after) == td`. Any background daemon or concurrent process editing the workspace during check execution triggers `identity_changed`. However, between `complete.approve()` and `Workspace.append("task_status_changed", ...)`, the ledger lock is temporarily released (`workspace.py:254-259`), creating a time-of-check to time-of-use window.
- **Canonical JSON**: `loads()` rejects duplicate keys at root and depth via `object_pairs_hook`, rejects floats, rejects integers $> 2^{53}-1$, and rejects trailing data. However, `canon.dumps()` does not normalize Unicode to NFC (`\u00e9` vs `e\u0301` produce distinct hashes, F-12) and does not reject lone surrogates, which trigger `UnicodeEncodeError` when hashed (F-04).
- **Chain verification and recovery**: Ledger chain detects modified bytes, sequence skips, and hash discrepancies (`test_chain_and_tamper`). CAS correctly raises `ConflictError` when head hash differs (`test_cas_conflict`). But if a crash leaves a partial JSON line at the end of `ledger.jsonl`, `_recover()` crashes with unhandled `JSONDecodeError` (F-03). Mirror restore via `check_anchor()` restores `ledger.jsonl` but fails to update `ledger.head.json`, leaving the ledger broken (F-02).
- **Blocked and resume reports**: `_validate_report()` verifies task matches active contract for `blocked` and paused contract for `resume`. Completed tasks cannot be resumed. However, untrusted text in `item`, `why`, and `options` is reflected into `project.projection` without newline escaping, allowing status block spoofing (F-07).

## C. The gate path

- **PreToolUse output set**: Can print only `""` (allow/no opinion), `{"decision":"deny","reason":"..."}`, or on internal error when `ledger.head.json` exists: `{"decision":"deny","reason":"G1 internal error: ...; mutating tools are refused in this G1 workspace"}`. If `ledger.head.json` is missing or `workspacePaths` is absent in error handler, it prints `""` (fails open).
- **Ways `handle()` can raise before printing**:
  1. Stdin has invalid UTF-8: `sys.stdin.read()` in `__main__.py:28` raises unhandled `UnicodeDecodeError`.
  2. Input JSON is a list (`[]`): `payload.get()` in `Context.__init__` raises `AttributeError`, and the fallback handler in `__main__.py:37` also raises `AttributeError`.
  3. `workspacePaths` contains non-string elements: `os.path.realpath()` raises `TypeError`.
  4. Tool arguments `args` is not a dict: `target_paths` raises `AttributeError`.
  5. Transcript missing or lock timeout: caught gracefully by internal handlers.
- **The textual gate**: Checks substring presence (`needle in text`) for exact paths. Escapes include: relative traversal paths (`../../.gemini/config/hooks.json`), environment variables (`$HOME/.g1`), extra slashes (`~/.g1//manifest.json`), shell quoting, and subshells. This design is consistent with design doc section 7.3: shell inspection is best-effort; authority rests on structured write gates, Stop verification, and SessionStart self-heal.
- **Protected paths and unmonitored mutating tools**: `target_paths()` resolves symlinks using `os.path.realpath()`. If an agent points a symlink inside `src/` to `~/.gemini/config/hooks.json`, `os.path.realpath()` resolves it and `gate()` denies the call. `PATH_KEYS` covers standard path argument names. However, agy tools such as `define_subagent` (which can create subagents with arbitrary tool permissions) or tools named differently (`edit_notebook` vs `notebook_edit`) are not in `MUTATING_TOOLS` and bypass PreToolUse gating.
- **`compute_gap`**: Reads `stepIdx` from PreToolUse journals and `PLANNER_RESPONSE` from transcripts. Gaps:
  1. If multiple mutating tool calls are issued in a single `PLANNER_RESPONSE` turn sharing one `stepIdx`, `compute_gap` counts multiple expected calls but records only one `stepIdx` in `observed`, generating a false gap.
  2. Denied tool calls are recorded in journals (`kind: "pre"`) and transcripts, correctly matched.
  3. `conversations.json` is read and written without file locking, creating race conditions under concurrent subagent execution.
- **Cost on PreToolUse**: `gate()` calls `ctx.state()`, which calls `Ledger(self.root).verify()`. This reads the entire `ledger.jsonl` from line 0 and computes SHA256 over every record. G1 tool gate overhead scales linearly $O(N)$ with ledger history length, contradicting design atom LED-59 (F-13).

## D. The verification sandbox

- **Scrubbed environment**: `runner.scrubbed_env()` creates a clean dictionary from an allowlist (`PATH`, `HOME`, `TMPDIR`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=0`, `NO_COLOR=1`, `TERM=dumb`). All ambient `PYTHON*` (`PYTHONPATH`, `PYTHONSTARTUP`) and `LD_*` (`LD_PRELOAD`, `LD_LIBRARY_PATH`) variables are completely stripped. However, without OS-level namespace/filesystem isolation, subprocesses can read and write to ambient global directories (`/tmp`, `/var/tmp`) and access system services.
- **Process-group termination**: `runner.run()` uses `start_new_session=True` so `proc.pid` is the PGID. In `finally`, `_kill_group()` sends `SIGKILL` to `proc.pid` via `os.killpg()`. Processes that call `setsid()` or create child process groups escape group termination.
- **Output cap and timeout behaviour**: `runner.run()` uses `proc.communicate(timeout=timeout_s)`. This buffers all pipe data into RAM before `OUTPUT_CAP = 1 << 20` is evaluated (F-06). A runaway test outputting gigabytes of text will exhaust memory before truncation occurs. On timeout, `_kill_group()` is invoked, a 5-second drain is attempted, and `timed_out=True` is recorded, which `runner.verdict_of()` maps to `fail`.
- **Scratch copy, excludes, and symbolic links**: `runner.scratch_copy()` copies the workspace to `~/.g1/scratch/<label>-<rand>/tree` using `shutil.copytree(..., symlinks=True)`. Directories in `paths.DEFAULT_EXCLUDES` are skipped. Symlinks pointing to absolute paths outside the workspace remain pointed to those external paths in the scratch copy.
- **Free-space check**: `scratch_copy()` checks `free < total * 2 + MIN_FREE_BYTES` (`MIN_FREE_BYTES = 50 MiB`). If disk space is insufficient, it raises `RunnerError`, which `verify.run_attempt()` catches and returns `insufficient_space`, converted by `control.decide()` to `environment_unknown`.
- **Redaction patterns**: `runner.REDACTIONS` scrubs Slack tokens, Google `AIza` keys, standard PEM blocks, JWTs, bearer tokens, and `"key": "..."` JSON pairs. Secrets that escape redaction include: AWS access/secret keys (`AKIA...`), GitHub PATs (`ghp_...`), OpenAI API keys (`sk-...`), YAML secret assignments (`api_key: secret`), Python variable assignments (`token = "secret"`), and single-quoted dictionaries.
- **Evidence paths and compaction**: Attempt evidence is saved to `~/.g1/workspaces/<id>/evidence/<attempt>/results.json`. `Workspace.compact_evidence()` retains attempt directories matching `receipt_seq` of completed tasks plus the last 3 attempts (`KEEP_ATTEMPTS = 3`). Unbound historical attempts are pruned. The base manifest `base-<task>.json` resides directly in `evidence/` as a file and is preserved.

## E. Control and projection

- **Strict-subset shrink rule**: `control.decide()` checks `failing_now < prev_failing` using Python's set strict-subset operator (`control.py:46`). If the failing check set does not strictly shrink, it terminates continuation with `no_progress`.
- **Budget counter monotonicity**: Continuations are tracked in the ledger and folded via `t["continuations"] = max(t["continuations"], int(d["n"]))` (`state.py:58`), preventing counter decrement. When `t["continuations"] >= budget` (default 3), continuation stops with `budget_exhausted`.
- **Oscillation and revisit detection**: Tracks `(tuple(vector), tree_digest)` in `seen`. Re-visiting an identical state returns `oscillation`. If history has $\ge 3$ past attempts and vectors alternate in a period-2 cycle (`v[-1] == v[-3] and v[-2] == v[-4]`), it halts with `oscillation`.
- **`environment_unknown`**: Triggers on `identity_changed`, `oracle_changed`, `policy_changed`, `observation_gap`, `insufficient_space`, `executable_changed`, `executable_missing`, or `base_manifest_unavailable`. Counts neither as progress nor as a failure turn.
- **Byte caps and truncation**: `project._trim()` enforces `max_bytes` (1024 for SessionStart, 512 for PreInvocation). When truncated, it appends `\n[G1: truncated; full state at <path>]`. UTF-8 byte cutting uses `.decode("utf-8", "ignore")`, cleanly discarding split trailing multi-byte bytes without throwing decode errors.
- **Untrusted text escaping**: Proposal `objective`, `task`, and blocked report `item`, `why`, and `options` are formatted directly into projection strings without newline filtering (`project.py:40-49`). A user or agent can insert arbitrary fake lines into the model's context via newlines in these fields (F-07).

## F. Install and integrity

- **Pinned bootstrap command**: `integrity.bootstrap_command()` generates an inline script executing `python3 -I -S -c '<src>'`. It computes SHA256 of `~/.g1/g1.pyz` and exits with code 3 on mismatch. Shell quoting wraps the Python source in single quotes and replaces internal single quotes with double quotes (`src.replace("'", '"')`). If `pyz_path` contains single quotes, this replacement corrupts the Python string literal syntax.
- **Hooks file merge**: `integrity.install_group()` claims to preserve foreign entries byte-for-byte, but reads via `canon.loads()` and writes via `canon.dumps()`, normalizing whitespace and stripping existing formatting (F-11). If `hooks.json` contains invalid JSON or a list root, `read_json()` or `install_group()` crashes.
- **Uninstall cleanup**: `install.uninstall()` removes only the `"g1"` key from `hooks.json`, deletes the file only if no foreign hooks remain, removes the 6 host files from `~/.gemini/config`, and deletes empty skill directories.
- **Manifest and host fingerprint**: `integrity.make_manifest()` seals `pyz_sha256`, `group_sha256`, and host files into `~/.g1/manifest.json`. `host_fingerprint()` hashes binary size plus the first and last 1 MiB of `agy`.
- **Host files self-heal**: At `SessionStart`, `integrity.heal_host_files()` compares SHA256 of all 6 host files with the manifest and overwrites any altered files. If another tool edits these files, G1 overwrites them on the next session start.
- **`enrollable()` edge cases**: `paths.enrollable()` correctly rejects `/`, `~`, and `~/.g1`. However, because it evaluates `g.startswith(r + os.sep)` instead of `r.startswith(g + os.sep)`, subdirectories inside `~/.g1` (such as `~/.g1/workspaces/x`) evaluate to `enrollable == True` (F-09).
- **Workspace ID collisions**: Keyed by `canon.sha256_text(realpath(root))[:16]`. 64 bits of entropy provide adequate collision resistance for local workspace counts.
- **Launcher execution preference**: `bin/g1` runs `python3 -m g1` from source only for `install` or if `g1.pyz` is missing; all other commands execute `g1.pyz`. Modifications made to repository source code do not affect CLI commands until `bin/g1 install` is re-run.

## G. Tests

The existing 39 unit tests in `tests/test_core.py` provide solid coverage for standard happy paths, CAS conflicts, red baseline rejection of green tests, basic canary insensitivity, compaction, and host file healing. However, they test only conforming inputs and omit adversarial inputs, corrupted ledger state, and edge cases.

### Ten most valuable missing tests

1. **`test_must_flip_without_targets_rejected`**
   - Assertion: `self.assertIn("targets must be provided for must_flip check", ws.register(proposal_no_targets)[1]["reasons"])`
   - Catches: False completions on checks that do not depend on workspace code (F-01).
2. **`test_check_anchor_repair_updates_head`**
   - Assertion: `self.assertEqual(led.read_head()["seq"], len(led.verify()) - 1)` after `integrity.check_anchor(led)` restores lost records from mirror.
   - Catches: Corrupted head anchor that breaks the workspace after mirror repair (F-02).
3. **`test_recover_discards_partial_uncommitted_line`**
   - Assertion: `self.assertEqual(len(led.verify()), 1)` when recovering a ledger that has an incomplete JSON line appended without durable head update.
   - Catches: Unhandled `JSONDecodeError` crashing ledger operations after mid-write crash (F-03).
4. **`test_canon_rejects_lone_surrogates`**
   - Assertion: `with self.assertRaises(canon.CanonError): canon.dumps({"text": "\ud800"})`
   - Catches: `UnicodeEncodeError` crashes during ledger hashing (F-04).
5. **`test_cmd_hook_handles_list_payload`**
   - Assertion: `self.assertEqual(cmd_hook(["PreToolUse"]), 0)` with stdin containing `[]` or non-dict JSON.
   - Catches: Unhandled `AttributeError` crashing the CLI hook handler (F-05).
6. **`test_runner_bounded_output_buffering`**
   - Assertion: `self.assertTrue(r["truncated"])` when executing a command generating 50 MiB of stdout, asserting process memory does not buffer full output.
   - Catches: OOM crash from unbounded pipe buffering in `runner.run` (F-06).
7. **`test_projection_sanitizes_newlines`**
   - Assertion: `self.assertNotIn("\n[G1 fake]", project.projection(s, "n", 512, "/path"))` when objective contains newline characters.
   - Catches: Fake status block injection into model context (F-07).
8. **`test_enrollable_rejects_g1_home_subdirectories`**
   - Assertion: `self.assertFalse(paths.enrollable(os.path.join(paths.home(), "workspaces", "sub")))`
   - Catches: Accidental auto-enrolment of internal G1 state subdirectories (F-09).
9. **`test_canon_dumps_nfc_normalization`**
   - Assertion: `self.assertEqual(canon.sha256_text(canon.dumps({"t": "\u00e9"})), canon.sha256_text(canon.dumps({"t": "e\u0301"})))`
   - Catches: Hash divergence on semantically identical Unicode inputs (F-12).
10. **`test_guard_check_failing_baseline_rejected`**
    - Assertion: `self.assertFalse(ws.register(proposal(checks=[{"id":"G1","argv":["false"],"kind":"guard","covers":["C1"]}]))[0])`
    - Catches: Acceptance of contracts whose guard checks already fail at baseline.

## H. Code quality

- **Dead code and unused functions**: None identified. All modules have concise, focused implementations.
- **Duplicated logic**: `_in_scope` is implemented identically in `contract.py:123` and `adapter/agy.py:77`. `host_file_paths()` and `host_file_texts()` in `integrity.py:152-160` both duplicate path resolution and package index decoding.
- **Misleading names or comments**:
  - `docs/host-agy.md:59` names tool `edit_notebook`, while code names it `notebook_edit` (`adapter/agy.py:18`).
  - `integrity.py:60` docstring claims `hooks.json` foreign entries are kept "byte-for-byte", but `write_json()` completely reformats and sorts keys.
- **Python 3.9 compatibility**: Verified. The codebase avoids `match` statements, union syntax `X | Y`, `zip(strict=)`, and parenthesized context managers. Standard library imports are 3.9-compatible.
- **Platform assumptions**:
  - `fcntl.flock` in `ledger.py:90, 112` is POSIX-specific and fails on Windows.
  - `os.O_NOFOLLOW` in `snapshot.py:41, 56` is POSIX-specific.
  - `os.killpg` in `runner.py:153` is POSIX-specific.
  - `dir_fd` parameter in `os.open` and `os.lstat` in `snapshot.py` is not portable across all non-Unix platforms.
- **Swallowed exceptions**:
  - `workspace.py:37`: `except OSError: pass` around `integrity.update_anchor` and `mirror_append` silently ignores anchor and mirror persistence failures.
  - `workspace.py:56`: `except OSError: pass` silently ignores failures writing `state.json` or `PROPOSAL_FORMAT.md`.
  - `adapter/agy.py:383`: `except Exception:` in `stop()` catches all errors and returns `{"decision": "stop"}`.

## I. Observed G1 behaviour

1. **Status block injection**:
   During initial `run_command` invocations, G1 injected:
   ```text
   [G1 ec6b1a] ledger seq 0 head f88879724ab3
   No active contract. For durable work, write a proposal to ~/.g1/workspaces/702a78d3b14f1e95/proposals/<id>.json (format: ~/.g1/workspaces/702a78d3b14f1e95/views/PROPOSAL_FORMAT.md). G1 validates it before your next step.
   ```
   Observed nonces across turns: `ec6b1a`, `ff2814`, `782526`, `e75072`, `c9e016`, `be16fa`.
2. **Terminal sandbox denial under PRoot**:
   The first unsandboxed command attempt failed natively with:
   `fork/exec ~/.local/bin/agy: operation not permitted`
   This confirmed the documentation in `docs/host-agy.md:79` regarding PRoot environment restrictions requiring `BypassSandbox: true`.
3. **ResourceWarnings in test suite**:
   Running `python3 -m unittest tests.test_core -v` triggered:
   `ResourceWarning: unclosed file <_io.TextIOWrapper name='/tmp/g1test-XXXX/.gemini/config/rules/g1.md' mode='r' encoding='utf-8'>`
   at `tests/test_core.py:575` due to unclosed file handles in `HostFilesTests`.

## J. The installed rules

1. **Rules not enforced by code despite tags**:
   - `g1.md:E2.4` and `g1-instinct.md:I6`: `[gate] for file tools and G1's own files; [receipt] for the changed set`. When no contract is active (`task is None`), `adapter/agy.py:208` does not gate tool writes to stay inside the workspace; file tools can write anywhere outside G1 protected roots.
   - `g1-work.md:W2.2`: `No cd to a parent directory. [gate] for commands that name G1's paths; [self] otherwise`. The textual gate only inspects string substrings against specific needles, ignoring relative cd traversal commands (`cd ../..`).
   - `g1.md:E2.3` / `g1-instinct.md:I4`: `[ledger] through the blocked report`. Violating the rule by guessing instead of writing a blocked report records nothing in the ledger.
   - `g1.md:E3`: "a shell write after a refused file write is refused too, and recorded". `textual_gate` does not inspect or refuse shell edits to project source or test files.
   - `g1.md:E2.5`: `Report facts, not verdicts... [receipt]`. The receipt verifier inspects executed checks and manifests, never evaluating the agent's message prose.
2. **Rule statements contradicting code**:
   - `g1.md:E3` states: "Read the task view at the `state.json` path in the block". The status block injects `PROPOSAL_FORMAT.md` path, not `state.json` (unless truncated).
   - `skills/g1/SKILL.md:50` lists paused reasons as `no_change, no_progress, oscillation, environment_unknown, completion_refused`. The code additionally emits `budget_exhausted` and `scope_violation`.
   - `skills/g1/SKILL.md:30` states `targets` lists files the check depends on for canary testing, but omits that `targets` is optional and omitting it skips canary testing.
3. **Conflicting rule pairs**:
   - `g1-work.md:W2.3` states shell edits of ordinary paths are not refused, but `g1.md:E3` states shell writes after a refused file write are refused.
   - `g1-writing.md:D3.5` forbids absolute `/home/...` paths in documents, while `g1-instinct.md:I7` demands exact quotation of command logs and receipts, which inherently contain absolute paths.
   - `g1-writing.md:D3.6` restricts parentheses to identifiers and short asides, whereas `g1-korean.md:K1.3` mandates parentheses for bilingual technical terms (`receipt(영수증)`).
4. **Korean rule internal self-consistency**:
   - `K1.4` mandates consistent sentence style (해라체 for rules), but sections `K4.1`–`K4.11` use noun fragment headers ending in `금지` or incomplete predicates (`이하`).
   - `K2.2` example `설정 파일을 열어 수정한 뒤 저장한다로 쓴다` violates Korean quotation particle rules (requires `~라고 쓴다` or quotation marks).
   - `K2.4` requires sentence lengths to be mixed between 10–15 characters and 80–100 characters; `g1-korean.md`'s own sentences are uniformly 40–50 characters.

## Verdict

I would not trust this harness's "complete" verdict in its current state. While the hash-chained ledger and deterministic check runner are solidly designed, the completion authority path contains a critical bypass: omitting `targets` in a proposal skips canary verification entirely, allowing checks that assert arbitrary external state (such as `/tmp` markers or stub binaries) to grant false completions on broken code. Furthermore, the integrity path's mirror repair routine restores record history without updating the head anchor file, permanently bricking the workspace ledger upon loss of local records. To earn trust, the harness must: (1) require `targets` for all `must_flip` checks and enforce canary sensitivity unconditionally, (2) fix the mirror repair logic to update `ledger.head.json`, (3) handle partial writes during crash recovery without crashing `JSONDecodeError`, and (4) sanitize untrusted projection strings to prevent model context spoofing.

## Not checked

- Behaviour under concurrent multi-agent tool execution in real-time agy daemon mode (not feasible in single-session batch review).
- Host hook behavior under alternative agy versions or platforms outside PRoot Linux on ARM64.
- Memory consumption profiling of the ledger fold over histories exceeding 10,000 records.
