# G1 pre-review 5, reviewer `fable`

- Commit: `7a12dc3078c340647f3298cec5e57c43597f9140`
- Python: `Python 3.13.7`
- Unit tests: `Ran 114 tests in 44.547s` / `OK` (`python3 -W error::ResourceWarning -m unittest tests.test_core -v`, run with `G1_HOME`/`HOME` under `/tmp/g1-pre5/fable/home`)
- Start: 2026-10-11T23:54:29Z
- Finish: 2026-10-12T00:35:09Z

All scripts live in `/tmp/g1-pre5/fable/work`; each sets `G1_HOME`/`HOME` to a throwaway dir (`work/h.py`) before importing G1.

## Findings

| ID | Severity | file:line | Claim (one sentence) | Evidence | Fix (concrete) |
|---|---|---|---|---|---|
| P5-01 | high | adapter/agy.py:301 `_shell_tokens`, reached from `textual_gate`:519 | The PreToolUse gate tokenizes the whole `run_command` line with `shlex`, O(n^2) in single-token length, so an agent-chosen line blocks the hook >1 s (and past agy's 20 s PreToolUse timeout the gate is skipped and the command runs ungated). | `ran` `work/sE_scale2.py`: `_shell_tokens` 100 KB->218 ms, 200 KB->816 ms, 400 KB->3.09 s, 800 KB->11.9 s (~4x per doubling); `work/sE_confirm.py`: full PreToolUse handle 300 KB->1016 ms; `integrity.TIMEOUTS["PreToolUse"]==20`, so a ~958 KB single token ~20 s -> host kills the hook -> empty output -> tool allowed. Agent fully controls `toolCall.args.CommandLine` (no length cap in `gate`). | Cap the text the gate parses (refuse/skip tokenizing >64 KB, or deny), and/or replace `shlex` with a bounded tokenizer; never let the gate time out into "allow". |
| P5-03 | high | workspace.py:571 `process_proposals` / :629 `_prepare_contract`, via adapter/agy.py:646 (PreInvocation) | PreInvocation processes every pending proposal in one call and runs a full tree scratch-copy + checks for each proposal whose red baseline fails, so an agent dropping N proposals into its own proposals dir blocks the pre-model-call hook for N tree-copies. | `ran` `work/sJ2.py`: one PreInvocation with failing-baseline proposals - 3-file tree x10 = 1.10 s, x30 = 3.10 s; 500-file tree x10 = 9.50 s, x30 = 31.5 s (`active=None`, all rejected). Proposals dir is agent-writable by design (`agent_writable`); contradicts the round-4 claim that the red baseline is "decision time, not a hook". | Bound per-call proposal work: process at most 1-2 proposals per PreInvocation (defer the rest), or run only the first that passes `_registrable` and reject the remainder without a baseline, or move baseline validation off the pre-invocation path. |
| P5-02 | medium | adapter/agy.py:409 `invokes_g1` (the `a=="-" or a.startswith("<<")` branch) | An ordinary command that passes a bare `-`/heredoc to python and merely mentions `import g1`/`from g1` anywhere in the line is refused, because `_PY_G1_RE` is searched against the whole command text, not the stdin/heredoc body. | `ran` `work/sE_confirm.py`: `python3 report.py - ; echo 'next: from g1 import api'` -> `invokes_g1` True (gate denies); `python3 app.py - && echo 'reminder import g1 module'` -> True; control `cat data.json | python3 - ; echo done` -> False. | Only treat `python -`/heredoc as a G1 invocation when the regex matches within the stdin/heredoc token/body, not the surrounding text; or drop the whole-text fallback for the `-` case. |
| P5-04 | low | host/skills/g1/SKILL.md:77 | "Editing a pinned oracle file: refused" is unqualified, but a shell edit of an oracle is not gated (only caught at the receipt), unlike the adjacent scope bullet which distinguishes file-tool vs shell. | `ran` `work/sK.py`: `sed -i ... tests/test_stats.py` gate -> not denied; file-tool write to the oracle -> denied. | Qualify it like the scope bullet: "with a file tool: refused; with a shell command: caught at the receipt". |

No critical findings. Two high (both speed-rule: a per-call hook an agent can make block > 1 s), one medium, one low.

## A. Round-4 fixes

Every row reproduced against current code with my own scripts. All `ran`.

| ID | Verdict | Evidence (my repro) | Variation |
|---|---|---|---|
| R4-01 | fixed | corrupt last line -> `unverifiable`, `--restore` rc 0 (verify 0..5, anchor ok); corrupt genesis -> restore rc 0; corrupt head file -> "records after head and no commit journaled"; corrupt witness -> `diverged`; mirror-middle corrupt + ledger intact -> `ok` rewritten | both corrupt -> restore rc 1 "no usable record", forget rc 0 (files moved aside); readable prefix(4) > mirror(3) -> restore rc 1 "not a prefix"; forget twice (0 then 1); foreign head -> restore follows witness; SessionStart after restore clean |
| R4-02 | fixed | `append_held` crash -> seq unchanged, decision None, retry ok, audit ok; crash inside `_finish` after the append -> recovery finishes the single `contract_registered` (seq 2) with decision accepted + reason + run_by; task registered; audit ok | old two-record ledger folds to (accepted, old, 2, bash); new one-record folds to (accepted, new, 2, z) |
| R4-03 | fixed | hard link to mode-000 -> mode kept, nlink 1, answered `unreadable`; same in `challenges/`; symlink to 0600 -> never read; TOCTOU (unlink+hardlink-victim between rename and open) -> victim mode 0 kept | hard link to a readable 0600 file -> G1 reads it and registers the task (no chmod); content is the agent's own (it planted the link) -> no escalation (L) |
| R4-04 | fixed | real `process_chain`: parent readable, grandparent not -> `[["bash"],["?"]]`, not agent; fully unreadable -> `None`, agent True; >40 -> truncated at 40; `repair --accept` with no /proc -> rc 3 | `_proc_names(self)` comm-first -> `['python3','python3.13']` |
| R4-05 | fixed | `setUpModule` patches `agy.process_chain`; 114 tests pass here | n/a |
| R4-06 | fixed | `sudo --`, `env --`, `timeout -k 5 10`, `xargs -I{}`, `nice --adjustment=10`, `command -v g1`, `doas`, `setsid`, `strace -f`, `flock -w`, `<<-EOF`, one-line fn, alias+call -> True; `exec -a g1 bash` -> False | `python3 - < myfile.py` -> False (file content unseen; documented residual); `uv tool run g1` -> False (L) |
| R4-07 | fixed | `git commit -m '...agents/hooks.json...'`, `git log --grep=.system_generated`, `grep -rn 'import g1'`, `python3 -c "x='import g1'"` -> gate "" | `.agents/hooks.json` inside a longer name -> not refused; `a/.agents/hooks.json` as a path token -> refused (over-broad, L) |
| R4-08 | fixed | nested dir mtimes preserved (`src/sub`=1e9, `src/sub/deep`=1.1e9) | n/a |
| R4-09 | fixed | worst case (all alerts, 64 checks, 256 long paths): every priority-0 needle present at 512 and 1024, no `truncated`, 1170 B / 1621 B, longest line 582 B; no-contract all-alerts 1104 B / 1246 B | matches author's ~1170/~1664 bound |

No Section A findings. The one-record acceptance is crash-safe through recovery (key R4-02 result).

## B. New code attacked

`work/sB.py`, `work/sE_*.py`. Per function:

- `short_ids`/`short_json`: robust; empty -> `[]`; the first item is kept even if it alone exceeds `max_bytes` (bounded in practice because check ids/paths are length-validated upstream; `short_json` also caps each item to `item_chars`). Non-ASCII in `short_json` is `json.dumps`-escaped to `\uXXXX` (ASCII, so byte==char holds). No raise/loop.
- `_python_code_runs_g1`: hostile inputs handled - null byte/invalid surrogate -> `tokenize` raises `ValueError`, caught, falls back to `_PY_G1_RE` (null-byte -> True; surrogate -> False); unterminated string -> `TokenError` -> regex; deep nesting fine; 100 KB benign 70 ms, "many tokens" 43 ms (bounded, see E). Fail direction on ambiguity is "refuse" (fine for this gate).
- `_skip_wrapper`: `env A=1 B=2 g1`, `sudo -u root -- g1`, `nice -n 10 -- ...` -> True; `timeout g1 repair` -> False (treats `g1` as the duration operand - but a real `timeout` without a duration errors, so not exploitable); `uv tool run g1` -> False (only `uv run` handled; L).
- `invokes_g1` on hostile text does not raise/loop: 100 KB separators 139 ms, deep parens 1.8 ms, unbalanced quote -> regex fallback True, nul -> True.
- `restore_ledger`/`forget_workspace`/`_known_ledger_id`: covered in A and C; follow the witness, move files aside, never delete.
- `_why_abandoned`: returns the `UNREADABLE` string iff `_claims[path] is None` (unopenable) else the default; verified.
- `_names_path`: path-token match works; `HEAD:.agents/hooks.json` not matched (a git-ref read), `.agents/hooks.jsonx` not matched.
- `_assemble`/`contract_registered` fold/`_hold`: covered in A/C/G.

Calling-hook failure mode: an uncaught exception in `gate` is caught by `cmd_hook` and turned into a fail-closed deny for PreToolUse (right direction), but I found no input that makes these raise. The two cost blowups are P5-01/P5-03.

## C. Witness and the restore path

`work/sA_r401.py`, `work/sCD.py`. Status for the four files + mirror:

- Forgery without rewriting `anchors/`: append+head+mirror but stale anchor -> `diverged`; same with anchor deleted -> `diverged`. No missed forgery that ends `ok` without touching `anchors/`.
- False lockdown from crashes: append-landed + pending present + stale head -> `check_anchor` recovers (head->5), `ok`; pending-only (append not landed) -> intent dropped, `ok`. No false lockdown. head-ahead-of-anchor with no pending -> `diverged` (correct: legitimately unreachable without fsync loss; the journal covers the real crash window).
- Witness unreadable / foreign id -> `diverged`; `--accept-ledger` -> `ok` (way out). Every diverged/unverifiable/missing state has a flag that leaves it (A: accept/restore/forget), so no dead end.
- Restore never loses a valid longer ledger: current readable prefix must be a prefix of the mirror, else rc 1 ("accept or forget"); a foreign head is ignored because `_known_ledger_id` follows the witness.

## D. Decision commands

`work/sCD.py`. Guarded (agent chain -> rc 3): `install, uninstall, init, propose, turn-end, host-verify, repair --accept-ledger, challenges --run, challenge`. Open (rc 0): `status, audit, challenges` (listing), `repair` (no flag). The set is right: the open ones are read-only or state-display. `run_by` is built from `names[0]` (the comm, read first in `_proc_names`); the agent cannot rename its ancestors, and the agy process carries `agy`, so `run_by`/`agent_in_ancestry` cannot be made to drop `agy` without leaving the process tree (documented residual). Note: `cmd_repair` with a flag prints the status block (which runs `check_anchor`, a self-heal that may rewrite the mirror / restore records / write the witness) before `_user_only`; I confirmed the mirror is rewritten even when the guard then refuses (rc 3). Benign (idempotent, same as SessionStart) and the decision itself is refused, but a guarded command does perform writes before the guard.

## E. Textual gate and tripwire

`work/sE_*.py`, `work/sA_r404_06_07.py`. Correctly refused: all wrappers/keywords/stdin forms of R4-06. Ordinary commands correctly passed (R4-07). Over-refusals (minor, tripwire): `command -v g1` -> refused (harmless); `a/.agents/hooks.json` as a path token -> refused though it is a nested, not the workspace, hooks file. Bypasses that pass (all within rule 6 / documented tripwire residual, none reaching a listed effect because the ancestry guard and lockdown stand): `uv tool run g1`, `python3 - < file`, `$HOME/.g1/...`. P5-02 (false refusal) and P5-01 (cost) are the findings. Cost: 10 KB line 15 ms; 100 KB 160 ms; 1000x proposals-dir mention 55 ms; 1000x `views/../ledger` 50 ms; the quadratic single-token blowup is P5-01.

## F. The scratch walker

`work/sF.py`. The copy preserves file content, mode and ns-mtime, dir mode and mtime (incl. empty and nested dirs), and copies relative/absolute/dir/loop symlinks as links (never followed); a FIFO is skipped and listed (`[['fifo','special']]`); a nested excluded dir (`src/.git`) is excluded identically in the copy and in `snapshot.manifest`. Differences a check could see: excluded dirs and special files are absent, and hard links become independent files. None can make a `must_flip` pass without the work: every check runs on a copy in baseline, verify and canary alike, the canary forces content-dependence, and completion binds the real tree's digest. A check keyed on hard-link identity registers (baseline fails on the copy) but can never pass on any copy - it fails with the work too (safe direction, never a false completion; a usability limit, L). Copy time is linear: 2000 files 2.8 s, 10000 files 13.7 s (decision/Stop time, not per-call).

## G. Claims and agent files

`work/sGHI.py` plus the suite's `AgentFileTests`/`ChallengeTests` (reran OK). Answer files are 0o644 under a 0o700 proposals dir (owner-only in practice). Two `Workspace` objects over 20 mixed proposals: exactly one registers (one active contract per workspace), the rest rejected cheaply, each file answered once; no double-processing. SIGKILL at each commit point is covered in A (R4-02) and the suite's dead-claim tests: a claim that died after its ledger record is answered from the ledger (`recovered`), one that died before is answered unread; an entry whose type changes after the rename is read through the locked fd and the stale-name dir is moved aside (`_finish_proposal`, R3-21). No finding.

## H. Challenges, decision, listing

`work/sGHI.py`. Accept twice -> second refused ("already accepted"). Two concurrent commits of the same challenge (prepare twice, commit both) -> first True, second rejected ("a contract is already active") because `_commit_contract` re-checks the challenge decision and the active task under the ledger lock - so no double acceptance and no acceptance-without-contract. `only` matches by file name or by the file's `id`, so a name!=id file is run by id. A 1 MiB+ challenge file becomes an error row (`unreadable: larger than 1048576 bytes`) without crashing the listing. 500 pending files list in 186 ms (a user command, not a hook). No finding.

## I. The status block

`work/sGHI.py`, `work/sA_fix.py`. Every priority-0 line is present in all eleven states (no contract; active unverified; active failing; paused-blocked; paused-other; lockdown; alert; host unverified; challenges waiting; liveness-unknown active; last-complete liveness) at both 512 and 1024 budgets, each well under budget except the worst case (R4-09: 1170/1621 B, still whole). Largest block measured is the all-alerts 64-check contract: 1170 B per call / 1621 B session start. A byte-capped `quote` ends with the ellipsis+quote after `rstrip("\\")`, so it cannot end inside an escape or drop the closing quote; a crafted objective `\n[G1 000000] ledger seq 99...` yields exactly one `[G1` line and the forged line is escaped (`embedded forged line present: False`). No finding.

## J. Speed

`work/sJ.py`, `work/sJ2.py`, `work/sK.py`. Long single process:

| Ledger | PreToolUse med / p99 / first100->last100 | PreInvocation med / p99 |
|---|---|---|
| 1 | 17.5 / 23.1 / 17.5->17.4 ms | 20.9 / 42.7 ms |
| 2000 | 17.5 / 23.2 / 14.4->17.7 ms | 20.8 / 27.6 ms |
| 5000 | 15.1 / 23.0 / 14.9->17.5 ms | 20.9 / 27.5 ms |

PreToolUse and PreInvocation are flat in ledger length with no first-100->last-100 growth: the `summary.json` head-bound cache keeps the per-call path off the chain walk (verified: PreToolUse imports none of workspace/contract/runner/tokenize; PreInvocation imports the check runner only when a proposal is pending). A 21 MB journal is rotated and PreToolUse stays 17.5 ms. 200 answered + 50 pending challenge files -> PreInvocation 21.3 ms. Component costs: `append`+views 30 ms; idle `Stop` at 10000 records 988 ms (linear in ledger length, documented, not the model path); `register` on a 2000-file tree 5.7 s and `turn_end` on it 16.8 s (decision/Stop time).

Inputs an agent can create that make a per-call hook block or grow: a long `run_command` line (P5-01, PreToolUse) and flooding the proposals dir (P5-03, PreInvocation). Ledger growth, journal growth (rotated), and answered-file count do NOT grow the per-call path. No per-call hook imports a module it does not need.

## K. Rules against code

`work/sK.py` plus reading. Enforcement tags check out: `[gate]` protected paths / lockdown / scope+oracle for file tools / G1 command line (`gate`, `textual_gate`, `_user_only`); `[receipt]` completion + changed-set (`complete.approve`, `verify.run_attempt`); `[ledger]` challenges/decisions recorded; `[self]` the rest. Verified: file-tool write to a pinned oracle -> denied; file-tool write outside the workspace with an active contract -> denied (scope); shell edit of an oracle -> not gated (caught at the receipt, per design 7.3). The one mismatch is P5-04 (SKILL's unqualified "Editing a pinned oracle file: refused"). The corrected round-4 sentences in `g1.md` ("a shell write inside the workspace but outside the scope fails the changed-set check"; "in every spelling the gate recognizes") now match the code.

## L. Not run / suspected without a reproduction

- Reading a hard-linked readable file (R4-03 variation A): G1 reads a 0600 file the agent hard-linked into the proposals dir and may echo its top-level JSON keys in a rejection reason. The agent planted the link, so it already has read access; I judge this no escalation, not a finding. `ran` but classed here.
- `uv tool run g1` and `python3 - < file` pass the textual gate (`ran`): tripwire residuals under rule 6; the ancestry guard refuses the decision commands regardless. Listed, not findings.
- The P5-01 timeout-skip could let a `run_command` run ungated by the textual tripwire, but lockdown is checked before the gate and the decision commands keep the ancestry guard, so I could not turn it into a false completion, missed forgery, or solo decision. Suspected ceiling: denial-of-model-time only.
- Real multi-process concurrency (true `fork` races, 100 rounds) I exercised only with two in-process `Workspace` objects plus the suite's lock/dead-claim tests; a genuine race window is unproven (the `flock`+inode-recheck design looks sound).
- `cached_summary` miss forces a full chain walk on PreToolUse; I could not make an agent trigger it (summary.json and head are under protected `~/.g1`), so it is not agent-reachable, but if it ever is, the per-call path would regain the ledger-length cost.

## M. Ten most valuable missing tests

1. `assertLess(PreToolUse_handle(run_command, CommandLine="echo "+"a"*300000), 1.0s)` - catches P5-01.
2. Write 20 failing-baseline proposals, assert one PreInvocation stays under a fixed budget (e.g. <=2 baselines) - catches P5-03.
3. `assertFalse(invokes_g1("python3 app.py - ; echo 'from g1 import x'"))` - catches P5-02.
4. `assertIn("deny", gate(sed -i ... oracle))` or fix SKILL - pins the oracle-via-shell semantics (P5-04).
5. `restore` when `len(current_readable) > len(mirror)` -> rc 1 and the ledger is left unchanged (not silently truncated).
6. Crash inside `_finish` of the challenge-acceptance commit, then `check_anchor` recovery, asserting the challenge ends `accepted` with the contract at the next seq (the R4-02 recovery path; only the append-crash path is tested).
7. A `must_flip` check keyed on hard-link inode equality: assert it can never complete (documents the scratch-copy limitation so a future hard-linking "optimization" cannot silently change completion semantics).
8. Two OS-level processes each running `process_proposals`/`decide_challenge` in a loop over shared dirs, asserting each file answered once and each task in the ledger once (real concurrency for G/H).
9. `gate` with a 1,000,000-byte `CommandLine`: assert it denies fast or never yields "allow" by timeout (locks down the P5-01 fail-open).
10. `agent_in_ancestry`/`run_by` with a comm containing `)` and spaces and a `?` tail, asserting the recorded chain and the agent decision are correct (hardens `_proc_names`).

## Verdict

I would trust this harness's "complete" and its lockdowns for correctness. Across A-K I found no false-completion path, no missed forgery that avoids rewriting `anchors/`, no lost committed record, no false lockdown from a crash, no dead-end repair state, and no G1 decision the agent can take alone: the completion predicate (canary, tree-digest CAS under the lock, oracle/policy/scope/gap checks) and the anchor/witness/mirror machinery held against every sequence I threw at them, and the round-4 fixes are all real, including the crash-safe one-record acceptance. Where it fails is the speed rule: the PreToolUse gate is quadratic in command-line length (P5-01) and PreInvocation runs an unbounded number of tree-copies when the proposals dir is flooded (P5-03), so an agent can make a per-model-call hook block for seconds to minutes - and P5-01 can even make the gate time out into "allow". That violates the hard constraint that G1 must never slow the working model, so I would not ship until P5-01 and P5-03 are bounded. What would change my mind: a per-call input-size cap on the gate that never falls open, and a per-call cap on proposal work in PreInvocation, each with a timing assertion in the suite. The medium/low items (P5-02, P5-04) are worth fixing but do not block.

## Not checked

- OS-level concurrency (real forked processes); only in-process `Workspace` races plus the suite's lock/dead-claim tests (L).
- The installer writing real host hooks (`install`/`uninstall` touch `~/.gemini`/`~/.g1`); avoided per the safety rules, code read only.
- `agy`-live behaviour (host binary, fingerprinting, real hook delivery); measured G1 in-process via `agy.handle`, not inside an agy session.
- Full enumeration of every wrapper-option combination in `_WRAPPERS`; sampled representative ones in A/B/E.
- Transcript-size cost of `compute_liveness` at Stop with a very large host transcript (Stop is not the model path; not measured).
