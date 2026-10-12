# G1 pre-review 5, reviewer `opus`

- Commit: `7a12dc3078c340647f3298cec5e57c43597f9140`
- Python: `Python 3.13.7` (Linux 6.17.0 PRoot-Distro)
- Unit tests (`python3 -W error::ResourceWarning -m unittest tests.test_core -v`): `Ran 114 tests in 45.268s`, `OK`
- Started 2026-10-11T23:54:19Z, finished 2026-10-12T00:21Z.
- Every reproduction is a script under `/tmp/g1-pre5/opus/work/`; each imports `h` first, which sets `G1_HOME` and `HOME` under `/tmp/g1-pre5/opus/home/` and inserts `/tmp/g1-pre5/opus/repo/src` on `sys.path`. CLI is exercised only through `__main__.main([...])` with `agy.process_chain` patched (as `tests/test_core.py` does). Nothing under the owner's real paths was touched.

## Findings

| ID | Severity | file:line | Claim (one sentence) | Evidence | Fix (concrete) |
|---|---|---|---|---|---|
| P5-01 | high | src/g1/adapter/agy.py:301-306, 519 | The PreToolUse textual gate runs `shlex` over the whole command string, which is super-linear, so a long `run_command` makes a per-call hook block more than a second (agent-controlled input). | `ran` P501.py: `PreToolUse on a 400KB run_command: 1694 ms` (200KB 494 ms, 100KB 212 ms); isolating, `_shell_tokens` 435 ms of a 535 ms 200KB call, the `invokes_g1` loop 1 ms. Reproduced twice. | Before tokenizing, bound the input: if `len(text) > ~16 KB` skip `_shell_tokens` and use the cheap `CLI_DECISIONS`/`_PY_G1_RE` fallback already present, or tokenize only the first N KB; the per-call path must be O(len) with a small constant. |
| P5-02 | medium | src/g1/workspace.py:138-141 | `_hold` does a path-based `os.chmod(path, 0o600)` after an `lstat` guard; `chmod` follows symlinks, so a symlink swapped into the path after the `lstat` (a TOCTOU window) has its *target* chmod-ed, re-opening the hole R4-03 set out to close. | `ran` a_r403.py step 5 (deterministic mock swapping the path to a symlink between `lstat` and `chmod`): victim `0o755 -> 0o600`. Read of lines 138-141 confirms the chmod is on the path, not an fd. End-to-end race not won (see L). | `os.chmod(path, 0o600, follow_symlinks=False)` (open already uses `O_NOFOLLOW`); or drop the chmod entirely and answer the entry unread (the agent owns the file, so leaving it unreadable only costs that one proposal). |
| P5-03 | medium | src/g1/integrity.py:344-378 | `restore_ledger` rebuilds from the mirror without checking it against the witness's recorded `(seq,hash)`, so a mirror extended past what G1 witnessed is restored as truth and completes with a clean audit and no divergence signal. | `ran` c_forge_restore.py: forged `verification_succeeded`+`complete` records appended to `mirror/<id>.jsonl`, ledger files deleted; user `g1 repair --restore` -> `status: complete`, `audit ok: True`, `src/stats.py` still the broken `return xs[0]`. No file under `anchors/` was rewritten. (Depends on the documented 7.7 shell residual to write the mirror; see C/L.) | In `restore_ledger`, require the mirror record at `witness["seq"]` to equal `witness["hash"]`, and record/alert when the restored head seq exceeds the witnessed seq; a restore should never silently extend beyond what G1 witnessed. |

No critical findings. P5-04 (a textual-gate tripwire gap on `chrt`) is not in the table: per rule 6 it leads to no listed effect (the ancestry guard still refuses decision commands); it is in section E.

## A. Round-4 fixes

Each row reproduced against the current code with my own script, not the author's test.

- **R4-01 (fixed).** a_r401.py drives every corruption site (genesis line, last line, head, witness, mirror middle, and pairs) through `g1 repair` with each flag, then `audit.run` and a `SessionStart`. Every state has a way out and none is a dead end: a last-byte/genesis/head corruption reads `unverifiable`, `--accept-ledger` refuses (`does not read as a chain`), `--restore` rebuilds from the mirror (`seq 0..4`, audit ok, `restored_by_user` alert), `--forget` moves the files aside (`moved to .../forgotten-…`, never deletes) and the next session enrols fresh. Variations in a_r401b.py: an unreadable witness alone is `diverged` and `--accept`/`--restore` both recover; head+witness both unreadable leaves only `--forget` (restore says `no readable witness and no readable head`), still a way out; a readable prefix longer than the mirror is refused by `--restore` with the exact counts and `--forget` still exits; `ledger genesis + mirror genesis` corrupted leaves only `--forget` (restore: `no usable record`). Confirmed: `--forget` twice is idempotent (second run sees no ledger). 
- **R4-02 (fixed).** a_r402.py SIGKILLs a child at every ledger I/O call (1..11) during `decide_challenge`. At every kill point the post-crash `check_anchor` recovers to `ok`, and the challenge is either still open (`decision=None`, task absent, seq unchanged) or fully accepted (`decision=accepted`, task present) — never accepted-without-contract. `audit_ok=True` at every point. The retry after an open-crash succeeds. a_r402b.py confirms the `state.fold` `contract_registered` branch folds a *mixed* ledger (old `challenge_decided`+`contract_registered`) identically, and that a stuck old-form `accepted`-without-contract is still refused on retry (`already accepted`) — i.e. the old two-record form, if present, is not newly broken (but see L).
- **R4-03 (fixed, with a residual).** a_r403.py: a hard link to a mode-000 file is answered `unreadable…` and the file keeps mode 0 and nlink 1 (not chmod-ed); a hard link to a readable 0600 JSON file of the user is parsed but rejected on *shape* (`unknown keys: access_token, refresh_token`) and the file keeps 0600/nlink1 — its content is not leaked into the answer beyond its key names (see L); a symlink is answered unread, target intact; a hard link in `challenges/` is listed `unreadable` and `--run` answers it `invalid` without chmod. The residual TOCTOU is P5-02.
- **R4-04 (fixed).** a_r404.py with `_proc_names` forced: no `/proc` -> `process_chain()` is `None`, `agent_in_ancestry()` True, `repair --accept-ledger` returns rc 3 (`the process ancestry cannot be read (/proc)`); a readable parent with an unreadable grandparent -> chain `[['bash'],['?']]`, agent False, accept succeeds and records `run_by = "bash < ?"`; a >40-deep chain stops at the limit; a comm containing `)` and spaces plus `agy` is still caught; the real chain for the test process is comm-first (`['timeout','gnutimeout']`). 
- **R4-05 (fixed).** `setUpModule` patches `agy.process_chain` to a user shell; the 114-test suite passes here, and the guard tests (`test_r4_04/05`) patch their own chain. `test_r4_05` runs a decision command with `_proc_names -> (['agy'],0)` and still gets rc 0 because of the module patch.
- **R4-06 (fixed, one residual).** e_gate.py: 37 of 38 wrapper/keyword/stdin spellings are recognised (`exec -a`, `env -i/-S`, `sudo -u/--user`, `nice -n/-10`, `time -p`, `timeout -s/-k`, `nohup`, `script -c`, `flock -c`, `uv run`, here-doc, `python3 -`, `import_module/__import__/run_module('g1')`, `ionice/taskset/stdbuf/doas/setsid/strace`, `python3.11`, `pypy3`, `sudo --`, `env --`), and all 22 ordinary commands are not refused. The one miss is `chrt -f 10 g1 status` (P5-04, section E).
- **R4-07 (fixed).** e_gate2.py: prose (`git commit -m '….agents/hooks.json…'`, `python3 -c "x = 'import g1'"`, `grep`, `git log --grep=`, `echo 'see .system_generated'`) is not refused; path tokens (`cat .agents/hooks.json`, `cat sub/.agents/hooks.json`, `ls .system_generated`, `python3 -c "import g1"`) are refused.
- **R4-08 (fixed).** f_walker.py: a directory with mtime `111111111` copies with the same dir mtime, and the file mtime is preserved too.
- **R4-09 (fixed).** i_status.py worst case (every alert + 64 checks + 256 long paths + 600-char objective): block is 1170 bytes at the 512 budget and 1621 at 1024, every priority-0 line present, exactly one `[G1` line, no `objective:` line (the low priorities are what is dropped), no `truncated` marker.

## B. Code added since round 4

- `_python_code_runs_g1` (b_hostile.py): 100 KB code with a real `import g1` -> True in 64 ms; 100 KB without -> False in 39 ms; unterminated string / invalid surrogate / deep nesting / 5000-string list -> handled, no raise, <5 ms; null bytes and form feeds take the regex fallback (True, correct — both are whitespace/garbage to the tokenizer). No input made it raise or loop. It only runs on `python -c` code, not every call.
- `_skip_wrapper` / `invokes_g1`: correct on 37/38 spellings (A, R4-06). The `invokes_g1` loop itself is ~1 ms even on 200 KB once tokenised; the cost is entirely in `_shell_tokens` (P5-01).
- `_names_path` / `_blank_own_dirs`: 1000 repetitions of the proposals dir -> 3.8 ms, correct.
- `restore_ledger` / `forget_workspace` / `_known_ledger_id`: A (R4-01) and C. `forget_workspace` moves files under `forgotten-<hex>/` and returns the dir; `_known_ledger_id` prefers the witness over a foreign head (a_r401b/`test_r4_01_b`). Residual: restore ignores the witness seq (P5-03).
- `_why_abandoned`: tri-state reason verified in a_r403 (an entry that could not be opened -> `unreadable…`; one that could -> the normal `write it again`).
- `short_ids` / `short_json` / `_assemble`: section I; no priority-0 line is cut, over-budget is bounded.
- `state.fold` `contract_registered` branch: a_r402b.py (mixed old/new ledgers fold the same); c_forgery.py (a `contract_registered` naming a never-recorded challenge is caught by `audit` as `registered from challenge …, which was not accepted`).
- `_hold` `PermissionError` branch: fixed for hard links/specials; P5-02 TOCTOU residual.

Calling-hook disposition: a gate function that raised would make `gate()` return the fail-closed `ledger could not be verified` deny (correct for PreToolUse); a projection/`short_*` raise is swallowed by `write_views`/handlers (fail-open, correct for the injection path). None of the new functions was made to raise on agent input.

## C. Witness and restore path

- Full file-state matrix in a_r401.py/a_r401b.py (ledger, head, anchor, witness, mirror, and pairs; present/missing/corrupt/foreign). Results: an `ok`/`diverged` ledger offers `--accept-ledger`/`--restore`; an `unverifiable` one offers `--restore`/`--forget`; a `missing` one offers `--restore`/`--forget`. A foreign ledger copied in (`test_r4_01_b`) is `diverged`, and `--restore` brings back the ledger the **witness** names, not the foreign head. No file-state combination was a dead end, and after every repairing flag `SessionStart` injects a normal block (no stuck lockdown).
- **False lockdown:** none found. The SIGKILL matrix (a_r402.py, 11 I/O points) and the crash recovery never produced a spurious `diverged`/`unverifiable`; recovery is `ok` at every point.
- **Missed forgery (P5-03):** c_forge_restore.py is a forged sequence that ends in `ok`/complete **without rewriting any file under `anchors/`**: forged records appended to `mirror/<id>.jsonl`, ledger deleted, then the user's `g1 repair --restore` adopts them. The witness (under `anchors/ws/`) and anchor are G1's own and untouched; `restore_ledger` never checks the mirror against the witness `(seq,hash)`. This requires writing `~/.g1/mirror/` which the gates refuse (K1/K2), so it rests on the documented 7.7 ungated-shell residual — hence medium, not critical — but the restore path turns that residual into a clean completion with only a generic `restored_by_user` alert.
- **Unintended restore/forget:** `--forget` refuses a readable ledger (`reads as a chain`) so it cannot discard good history by mistake; `--restore` refuses when the current readable prefix is not a prefix of the mirror (`are not a prefix of the mirror; accept the ledger, or forget it`), so it cannot silently rewrite history that diverged by real work.

## D. Decision commands

- d_guards.py/d_guard2.py: guarded (rc 3 with `agy` in the ancestry) = `repair --accept-ledger|--restore|--forget`, `challenges --run`, `challenge`, `host-verify`, `init`, `turn-end`, `propose`, `install`, `uninstall`. Unguarded (rc 0 for agent and user alike) = `status`, `audit`, `challenges` (listing), `repair` (no-flag display), `hook`. The set is right: only the no-flag display and the read-only listings are open, and the textual gate separately keeps the agent off all of them.
- No *guarded* mutation happens before the guard: d_guard2.py shows four refused decision commands leave `seq` and `alerts` unchanged. One nuance: `cmd_repair`'s no-flag display calls `check_anchor` (which self-heals: writes a pre-witness witness, rewrites a differing mirror, restores lost records, anchors a genesis-only ledger) **before** `_user_only`. These are idempotent integrity-maintenance writes, not user decisions, and they also run on the unguarded display and at SessionStart, so this is acceptable, not a guard bypass.
- `run_by` records the comm-first names of the ancestry (`bash < sshd`, `bash < ?`). An agent that reaches a decision command at all (the double-fork residual) can name its processes to make `run_by` read like a user's shell; this is the documented tripwire-with-a-record (7.7), not a new issue.

## E. Textual gate and tripwire

- Wrongly refused ordinary commands: none found among 22 tested (e_gate.py) and the R4-07 set (e_gate2.py). (`cat ~/.g1/manifest.json` was *not* refused in my sandbox only because the review rules force `G1_HOME` to a sandbox dir, so `paths.home()` is not `~/.g1`; in a real install without `G1_HOME` the needle matches — a sandbox artifact, see L.)
- G1 command lines that pass (bypass): `chrt -f 10 g1 …` (P5-04). `chrt` is in `_WRAPPERS` with option letter `p`, but its real CLI takes a bare priority operand (`-f 10`) before the command, and `chrt` is not in `_WRAPPER_POSITIONALS`, so `_skip_wrapper` treats `10` as the command and never looks past it. Weighed against rule 6: no listed effect follows — `g1 status`/`audit` are not decisions, and `chrt -f 10 g1 repair` is still refused by the ancestry guard (e_gate2.py: rc 3 under an `agy` chain). A tripwire gap, fixable by adding `"chrt": 1` to `_WRAPPER_POSITIONALS` (only in the non-`-p` form). The other documented residuals (copied archive, `$HOME/.g1`, name built from pieces) are accepted (rule 6).
- Gate cost (P5-01): single-token `echo` lines — 100 KB 212 ms, 200 KB 494 ms, 400 KB 1694 ms (end-to-end PreToolUse). 1000 mentions of the proposals dir: 18.9 ms. The growth is super-linear and lives in `shlex`.

## F. Scratch walker

f_walker.py compared the scratch tree with the source: file and **directory** modes and mtimes preserved (R4-08); symlinks copied as links including a self-loop, a link to a directory, and an absolute link (never followed); empty directories and empty files reproduced; a name containing a newline copied; `node_modules` at depth 2 excluded (the walker excludes by name at every level — consistent with `snapshot.manifest` and `contract._rel_ok`, so no scope/scratch mismatch). I found no difference the checks can observe that would flip a `must_flip` with or without the work: the copy is a byte copy with the same hashes, modes and relative layout, and checks run with `cwd` at the copy root using relative paths. Timing: see J (register on a 2000-file tree 4.0 s, turn_end 16.4 s — tree copies, not per-call).

## G. Claims and agent files

- The R4 reviewer's 100-round two-worker run and the suite's `test_a_claimed_file_runs_once…`, `test_a_claim_that_died_after_its_ledger_record…`, `test_r3_21…` cover the concurrency and the SIGKILL-after-record cases; I re-ran the acceptance SIGKILL matrix (a_r402.py, 11 points) and found no double record and no accepted-without-contract.
- `_why_abandoned` tri-state and the hard-link/symlink/FIFO answers verified in a_r403.py. The answer file's mode is `0o644` (a_r403.py step 2) — world-readable, by design (`_finish_proposal` opens the answer with 0o644). That is the agent's own directory; not a finding.

## H. Challenges, decision, listing

gh.py: `process_challenges(only={"realid"})` runs a file named `filename1.json` whose `id` is `realid` (so `only` matches by id, reading the file). A second `accept` on an already-accepted challenge is refused (`was already accepted`); and once accepted the task is active, so a concurrent second acceptance is blocked by the active-task check too. Listing 501 pending files plus one ~1 MiB file: 143 ms; the 1 MiB file is reported `unreadable: larger than 1048576 bytes`, never read into the listing. A `contract_registered` that names a never-recorded challenge is caught by `audit` (c_forgery.py). No way found to accept a challenge twice or to record an acceptance without its contract through any crash (A/R4-02).

## I. Status block

i_status.py / i_quote.py: across no-contract, active (no vector / with vector), paused-blocked, paused-no_change, lockdown, alert, host-unverified, challenges-waiting, last-complete-with-liveness, active-with-liveness — at both 512 and 1024 — every state has exactly one `[G1` line, the completion directive line is present whenever there is an active task in the `default`/`no_check_cmd` variants and absent in `facts`, and the `scope:` line is always present. Largest block: 1170 bytes (512 budget) and 1621 bytes (1024). `quote` byte-capping was fuzzed (200 backslashes, trailing `\`, ` ` runs, 4-byte emoji, a fake `"]; [G1 …` payload, tabs): always one line, always within the byte cap, never leaks a `Cc/Cf/Zl/Zp` character, never emits `\n[G1 ` — the `rstrip("\\")` before the ellipsis stops a cut landing inside an escape.

## J. Speed

Per-call hooks in one long process (j_time.py, `agy.handle`):

| ledger records | PreToolUse median / p99 | first100 / last100 | PreInvocation median / p99 | first100 / last100 |
|---|---|---|---|---|
| 1 | 14.3 / 19.3 ms | 13.6 / 16.6 | 13.1 / 19.5 ms | 13.1 / 13.2 |
| 2000 | 10.8 / 13.9 ms | 10.9 / 10.8 | 13.2 / 17.1 ms | 13.0 / 14.0 |
| 5000 | 12.3 / 27.5 ms | 12.3 / 12.1 | 14.5 / 21.3 ms | 14.5 / 14.5 |

Flat in ledger length, no first-100→last-100 growth: the summary cache holds. PreToolUse imports **no** heavy module (`g1.runner/contract/verify/snapshot/subprocess/tokenize` all absent after a `write_to_file` and after an `echo` run_command — j_imports.py). Standalone (j_time2.py): idle `Stop` at 10 000 records 171 ms; one `append` with views 36.5 ms; `register` on a 2000-file tree 4007 ms; `turn_end` (Stop verification) on the same tree 16 437 ms.

Agent-creatable inputs that make a hook block or grow:
- **A long `run_command` makes PreToolUse block >1 s (P5-01).** This is the only per-*call* blow-up; it is agent-controlled and not inherent.
- `register`/proposal validation (PreInvocation) and `turn_end` (idle Stop) scale with tree size (4 s / 16 s on 2000 files). These are once-per-proposal and once-per-idle-Stop, documented (design 6.1, 7.2), and off the per-model-call path; a proposal on a very large tree does delay the *next* model call by seconds, which is a real but documented cost (medium, left as the design states). Ledger length, journals (20 MB), answered proposals and pending challenges did not grow the per-call cost here or in the R4 numbers.

## K. Rules vs code

k_rules.py checked each enforcement claim against behaviour: a shell command naming `~/.g1` is refused `[gate]`; a structured write into `~/.g1` is denied `[gate]`; a file-tool write to a pinned oracle is denied `[gate]`; a shell edit of an oracle is **not** gated (caught at the receipt) — matching the corrected skill wording; a shell write to `~/.gemini/config/hooks.json` refused; `g1 status` refused `[gate]`; a shell write inside the workspace but outside scope -> `scope_violation` at `turn_end` `[receipt]`. The corrected `g1.md:35`/`SKILL.md:130` wording ("the receipt measures the workspace tree; a write elsewhere is not measured") now matches the code (a write outside the workspace root is neither gated nor in the manifest). `SKILL.md:135` ("refused by the gate where it recognizes the spelling, and by the command itself when you are among its ancestor processes") already hedges, so the `chrt` gap (P5-04) does not contradict it. `[gate]`/`[receipt]`/`[ledger]`/`[self]` tags all map to real mechanisms. No rule/code mismatch found beyond the gate tripwire's own documented limits.

## L. Not run / unverified / suspicions

- **P5-02 end-to-end race not won.** I proved the code chmods through a symlink injected between `lstat` and `chmod` with a deterministic mock; I did **not** demonstrate an agent winning that microsecond race against a live `_hold`. Real-world exploitability is therefore unverified; the code defect (path-based chmod after lstat) and the trivial fix stand regardless.
- **P5-03 depends on the 7.7 residual.** Writing `~/.g1/mirror/` is refused by every G1 gate; the forgery needs the documented ungated-shell/double-fork escape. I did not attempt that escape (out of scope and pointless — with it an agent can rewrite everything). What I verified is only that `restore_ledger` trusts a tampered mirror once it exists.
- **`cat ~/.g1/…` not refused in-sandbox** is an artifact of the mandatory `G1_HOME`: with it set, `paths.home()` is the sandbox dir, so `~/.g1` is not a needle. I could not exercise the real-install needle (`~/.g1`) because the safety rules forbid an unset `G1_HOME`; by reading `textual_gate` the production needle (`paths.home()` = `~/.g1`) matches, so this is not a production bug.
- **Old two-record challenge acceptances.** a_r402b.py shows a ledger stuck in the pre-R4 `accepted`-without-contract state (a `challenge_decided` with no following `contract_registered`) folds to `decision=accepted` with `task` absent and `audit ok=True` — i.e. `g1 audit` does **not** flag an accepted challenge that has no contract (it only flags a contract whose `from_challenge` was not accepted, the opposite direction). This cannot be newly created at `7a12dc3` (R4-02 fix), so it is only a migration concern for ledgers written by `21cf430`; I note it as a suspicion, not a finding.
- I did not run the full suite under a parent process literally named `agy` (`exec -a agy …`); `setUpModule` plus `test_r4_05` cover the mechanism, and the 114-test run passed.
- Cross-host behaviour, `/proc` on non-Linux, and fd-exhaustion were not tested (no environment).

## M. Ten most valuable missing tests

1. **Gate cost cap.** `assert PreToolUse(run_command of 500 KB) returns in < 200 ms` (or that `textual_gate` refuses/short-circuits over a length cap). Catches P5-01.
2. **`_hold` chmod never follows a link.** Create `x.running.json` as a symlink-after-lstat (monkeypatch `os.lstat` to swap) and `assert victim mode unchanged`. Catches P5-02.
3. **Restore honours the witness seq.** Append an extra forged record to the mirror beyond the witnessed seq, delete the ledger, `--restore`, and `assert` the restore refuses or records an alert that the mirror exceeded the witness. Catches P5-03.
4. **`chrt`/positional-operand wrappers.** `assert invokes_g1("chrt -f 10 g1 status")` (and `taskset`/`nice` numeric forms). Catches P5-04.
5. **`g1 audit` flags an accepted challenge without a contract.** Build the old two-record form, drop the `contract_registered`, `assert not audit.run(root)["ok"]`. Catches the L migration gap.
6. **Restore prefix guard with a readable-prefix-longer-than-mirror.** `assert` `--restore` refuses with the counts message when the current ledger reads further than the mirror (a_r401b case), so a shorter mirror can never truncate good history.
7. **`_python_code_runs_g1` on hostile `-c` code.** 100 KB, null bytes, unterminated string, invalid surrogate: `assert` it returns a bool in < 100 ms and never raises.
8. **PreInvocation with a pending proposal on a large tree is the documented cost, not a per-call one.** Time two consecutive PreInvocations (proposal present, then absent) and `assert` the second is < 50 ms, pinning the "proposal validation is once, not per call" contract.
9. **`forget_workspace` then immediate `SessionStart` enrols a fresh, anchored ledger** and the moved `forgotten-*` dir still holds the old `ledger.jsonl` (durability of the never-delete promise).
10. **Answer-file mode.** `assert` `_finish_proposal` writes `<id>.rejected.json` with a mode that does not widen beyond the proposals dir's intent (documents the 0o644 choice), so a future change can't silently expose answers.

## Verdict

I would trust this harness's `complete` and its lockdowns for the threat model it claims. The completion predicate is evidence-only and veto-hardened; the ledger chain, anchor, mirror and witness recover correctly from every corruption and crash point I could construct, and no state is a dead end (R4-01 holds broadly, not just on the author's one case). R4-02 through R4-09 are genuinely fixed, reproduced against the current code, not merely asserted by the author's tests. The decision-command guards are placed before any guarded mutation and fail closed without `/proc`. The one change that would move the needle is P5-01: a long `run_command` makes the per-call PreToolUse gate block for seconds, which violates the project's own hard rule ("G1 must never slow the working model") on ordinary agent-created input — it is an avoidable `shlex` blow-up, not inherent, and should be capped before this ships. P5-02 (a re-opened chmod TOCTOU on the exact hole R4-03 closed) and P5-03 (restore trusting a mirror past the witness) are both narrow and depend on timing or the documented OS residual, but both are trivially fixable and worth closing. The speed rule otherwise holds: per-call hooks are 11-14 ms and flat to 5000 records, importing no heavy module. What would change my mind on `complete`: a demonstrated win of the P5-02 race, or any path that writes the mirror/anchor through a G1-gated tool (I found none).

## Not checked

- Non-Linux process ancestry, NFS/CIFS rename races, fd exhaustion (no environment; the author also lists these).
- The full suite under a literally-`agy`-named parent process (mechanism covered by `setUpModule` + `test_r4_05`).
- Winning the P5-02 TOCTOU race in real time (deterministic mock only).
- The ungated-shell / double-fork escape that P5-03 presupposes (out of scope; with it all bets are off by design).
- Live agy-session hook costs (no host); relied on the author's live numbers for that one axis.
