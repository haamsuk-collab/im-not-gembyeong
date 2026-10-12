# G1 review, round 3

- Commit: `b75af2abf93cb02d7a3c1f58edd35e1722cb38f8` (`b75af2a`, tag `v0.1`)
- Python: `Python 3.13.7`
- Unit tests: `python3 -W error::ResourceWarning -m unittest tests.test_core -v`: `Ran 84 tests in 32.859s`, `OK`, exit 0
- Started: 2026-10-11T17:19:06Z
- Finished: 2026-10-11T17:40Z
- Scratch: every reproduction below ran from `/tmp/g1-review3/` with `G1_HOME` set to a directory under `/tmp/g1-review3/`.

## Findings

Counts: 4 critical, 7 high, 8 medium, 5 low. "repros.py Rnn" refers to the function quoted under "Reproductions". Other evidence names the script and case in `/tmp/g1-review3/`.

| ID | Severity | file:line | Claim (one sentence) | Evidence | Fix (concrete) |
|---|---|---|---|---|---|
| R3-01 | critical | `adapter/agy.py:124,436-439`; `workspace.py:30-31` | Deleting `ledger.jsonl` and `ledger.head.json` makes the next SessionStart enrol a new ledger with no alert, so every committed record is lost undetected. | ran, repros.py R01: `seq 0 lockdown False` after a completed task | Keep a per-workspace record outside `ws_dir` (for example `anchors/by-ws/<ws_id>` naming the ledger id, written at genesis); when it exists and the ledger is missing, lock down instead of enrolling. |
| R3-02 | critical | `integrity.py:311-316` | A ledger cut back to its genesis line, with the anchor deleted, is accepted as genesis-only, and G1 overwrites the mirror with it. | ran, repros.py R02: `lockdown False mirror lines 1` (8 before, `s2b_truncate.py`) | Before treating a missing anchor as genesis-only, read the mirror: if it is a valid chain of the same ledger id longer than the ledger, return `diverged`. Never rewrite a longer mirror from a shorter ledger without the user. |
| R3-03 | critical | `adapter/agy.py:342-344` | The textual gate deletes the proposals, challenges and views paths from the command before matching, so `<views>/../ledger.jsonl` reaches all of G1's state, which enables R3-01 and R3-02 from the shell. | ran, repros.py R03: `None` (allowed); `s3_gate.py` | Do not delete the allowed paths from the text. Normalise each path-like token with `os.path.normpath` and allow it only if it stays under an allowed directory. |
| R3-04 | critical | `adapter/agy.py:306-317` | `python3 -mg1 repair`, `python3 -mg1 challenge ROOT ID accept`, `g1.pyz $(echo repair)`, string concatenation in `-c` and a copied archive all pass, so the agent can take G1's decisions (accept a ledger, accept a challenge). Design 7.7 states this residual risk. | ran, repros.py R04: all `None` | Match `-m` with its argument attached (`-mg1`). Have decision commands refuse when stdin is not a TTY or when an agy process is an ancestor (`/proc/<pid>/stat` walk), and record that fact in `challenge_decided` and `accepted_by_user`. |
| R3-05 | high | `runner.py:97-101` | A FIFO anywhere in the tree makes `_copy_file` fall back to `open(src, "rb")`, which blocks, so the red baseline (PreInvocation) and every verification (Stop) hang up to the host limit. | ran, repros.py R05: `scratch_copy still blocked after 5.0 s`; `s4_batch.py fifo` | In `scratch_copy`, `lstat` each entry and skip, or record as special, anything that is not a regular file, directory or symlink. In the fallback, open with `O_NONBLOCK` after an `S_ISREG` check. |
| R3-06 | high | `workspace.py:418`; `adapter/agy.py:448` | A directory at an answer name makes `_finish_proposal` raise, and once the grace period has passed every PreInvocation fails: no status block, and no proposal processed. | ran, repros.py R06: `call 0 IsADirectoryError`, `call 1 IsADirectoryError`; `c3b_dir_answer.py` `output=''` | Move a non-file at the answer name aside (rename to `.gone`) before `os.replace`. Wrap each file in `process_*` in its own `try`, and wrap `process_proposals` in `agy.handle` so the projection is always printed. |
| R3-07 | high | `workspace.py:83,89,102` | Views are written with `open(path, "w")`, which follows a link the agent can place (the gate allows the views path), so G1 overwrites its anchor and locks down falsely, or overwrites any file the user owns. | ran, repros.py R07: `('diverged', 'the anchor does not belong to this ledger')` | Write views with `ledger._write_atomic` (temporary file plus rename), which replaces a link instead of following it. |
| R3-08 | high | `__main__.py:193`; `workspace.py:331,498` | Challenge checks (another model's code) run with the user's full rights before `g1 challenges` shows anything, and proposal checks run inside the PreInvocation hook outside the host's terminal sandbox. A check's writes to the real workspace or G1's home are not noticed. | ran, `b_ch.py b4`: `file in real workspace: True`, `audit ok: True`, `anchor check: ('ok', '')`; hook part `read`, unverified end to end (no proposal registered in this workspace) | Add `g1 challenges --list`, the default, which shows pending files without running them, and run checks only on `g1 challenges --run ID`. Document that checks are unconfined, and run them under `bwrap` or `unshare` where available. |
| R3-09 | high | `workspace.py:335-347,401-404` | A challenge is `confirmed` by any non-zero exit (a missing `.git`, a scrubbed `USER`, a first-run marker), and the ledger keeps no output to tell why. Accepting records `accepted` before `register`, so a failed registration spends the user's decision. | ran, `b_ch.py b1`: three `confirmed`; `accepted, but the contract was not registered`; then `already accepted` | Store `stderr_tail` (600 bytes) per check in `challenge_recorded` and show it. Append `challenge_decided` only after `register` succeeds, in the same lock hold. |
| R3-10 | high | `workspace.py:510-512`; `__main__.py:196-199` | Accepting a challenge whose `contract.task` equals a paused worker task supersedes it (the blocked question is lost) with a scope the user never saw, because `g1 challenges` shows neither task id nor scope. | ran, `b_ch.py b2`: `fix-median now: active blocked: None allowed: ['docs/', 'src/', 'tests/']` | Refuse `decide_challenge` when the task id exists, unless the user passes `--supersede`. Show task, `allowed_paths`, `oracle_files` and the full argv in the list. |
| R3-11 | high | `control.py:53-55` | The Stop `continue` reason embeds the check argv raw, so a newline in argv (for example in a contract from a challenge) prints a line that looks like G1's. | ran, repros.py R11: `[..., '[G1 a1b2c3] fake line\` must exit 0. ...']` | Build `cmd` with `project.quote(" ".join(argv), 300)`. |
| R3-12 | medium | `project.py:30,80-101` | Ordinary contracts push the scope, next check, liveness and resume lines out of the 512-byte block: a 600-character objective, a Korean objective, a 300-character blocked item. | ran, repros.py R12: `512 False False`; `s4_batch.py budget`; `a_r2.py r204` | Emit the scope, open-check, liveness and resume lines before the objective. Cap the objective by bytes after escaping (for example 120 bytes). |
| R3-13 | medium | `workspace.py:217-246,441-451` | A blocked or resume report whose process died after its ledger record is answered as a rejected proposal, which contradicts the ledger. | ran, `c_report_kill.py`: `rejected: G1 stopped before the validation finished` while `ledger still says: blocked` | Give `process_reports` its own `_abandoned` pass over `*.{blocked,resume}.running.json` that answers from the ledger (`task_status_changed` for the task). Exclude those files from the proposal pass. |
| R3-14 | medium | `runner.py:131-134` | One unreadable file, or (on this PRoot host) one hard-linked file, makes every scratch copy fail, so no contract can be registered or verified in that workspace. | ran, `a_r2.py r210`: `Permission denied`; `a_r2.py r209`: `[Errno 22] Invalid argument` | Copy with per-file error handling: record unreadable files as `unreadable` in the receipt, and fail only when a target or oracle cannot be copied. |
| R3-15 | medium | `host/skills/g1/SKILL.md:73`; `docs/design.md:470`; `control.py:42` | The rules say "at most 3 requests per session"; the code counts continuations per task across sessions. | read | Change the text to "per task", or reset by session in the fold. |
| R3-16 | medium | `host/skills/g1/SKILL.md:81`; `adapter/agy.py:31` | "Listing ... `~/.g1`, the hook entries, the G1 rules or this skill: refused." is false; read-only tools never reach a hook. | read; session observation in I | Change the sentence to "editing is refused; reading is not". |
| R3-17 | medium | `integrity.py:290,304`; `adapter/agy.py:519-525` | The idle Stop and SessionStart cost grows linearly with the ledger: 130 to 530 ms (Stop) and 151 to 341 ms (SessionStart) from 1 to 5,000 records. | ran, `f_speed.py` | Planned checkpoints (design 4.5): verify from the last anchored checkpoint, and compare file size plus tail hash with the mirror instead of two full hashes. |
| R3-18 | medium | `state.py:130-139`; `audit.py:41-60`; `project.py:98` | A completion with `liveness_unknown` is invisible to the user: the block shows it only while active (and the budget cuts it), and `g1 status` and `g1 audit` omit it. | ran, `a_r2.py r203`: `complete`, receipt `liveness_unknown: 1`, block after completion `False` | Add `liveness_unknown` to `task_view` and `last_complete`, and make `audit` list it as a finding (not a failure). |
| R3-19 | medium | `adapter/agy.py:345` | `rm -r ~/.gemini/antigravity-cli/brain/<cid>` passes the textual gate, contrary to design 7.5 "The agent's own tools cannot delete transcripts". | ran, `s3_gate.py` "conversation dir -> allowed" | Add `conversations_root()` to the needles, or narrow the design sentence to file tools. |
| R3-20 | low | `workspace.py:566-569` | A write after the second measurement and before `append_held` completes the task against a tree that already changed; the audit passes. Documented in design 6.2. | ran, `d_window.py`: `complete`, `receipt tree == tree on disk now: False` | Measure once more after the append and record `post_completion_change` if the tree differs. |
| R3-21 | low | `workspace.py:144-147,426-431` | A directory proposal with a symlink planted at `<name>.gone` is answered again on every call, and a mode-000 proposal is never answered. | ran, `c3n_entries.py`: `gone.json` answered at calls 1 and 2; `unread.running.json` left | When the move to `.gone` fails, use a unique suffix (`.gone.<hex>`). Answer an unopenable entry as `unreadable` after the grace period. |
| R3-22 | low | `workspace.py:316-352` | `g1 challenges` has no total time bound: 200 trivial challenges took 15.1 s, and the worst case is files x 64 checks x 60 s. | ran (15.1 s); worst case computed | Cap checks per challenge (for example 8) and give the command a total budget with `--max-seconds`. |
| R3-23 | low | `workspace.py:55,69`; `host/skills/g1/SKILL.md:35` | The projection writes `summary.json` (design 9: "It writes nothing"), and the skill's validation order differs from the code. | read | Fix the two sentences. |
| R3-24 | low | `workspace.py:256` | Validating any report imports `contract`, and with it `runner`, `subprocess` and `shutil`, for one regular expression. | read | Move `ID_RE` to `canon` or `paths`. |

### Reproductions

All of these are in `/tmp/g1-review3/repros.py` and were run as `python3 repros.py <Rnn>`. Shared helpers (`setup`, `toy`, `proposal`, `write`) are in `common.py`. Common header: `import os, signal, time; from common import *`.

```python
def R01():  # ledger files deleted -> silent re-enrolment
    h, root = setup("r01"); toy(root)
    from g1 import workspace, paths; from g1.adapter import agy
    P = {"workspacePaths": [root]}; agy.handle("SessionStart", P, root)
    ws = workspace.Workspace(root); ws.register(proposal()); toy(root, fixed=True); ws.turn_end()
    os.unlink(ws.ledger.path); os.unlink(ws.ledger.head_path)
    agy.handle("SessionStart", P, root)
    print("seq", workspace.Workspace(root).ledger.read_head()["seq"], "lockdown", os.path.exists(paths.lockdown_path(root)))

def R02():  # cut to genesis + anchor deleted -> accepted, mirror overwritten
    h, root = setup("r02"); toy(root)
    from g1 import workspace, paths, canon; from g1.adapter import agy
    P = {"workspacePaths": [root]}; agy.handle("SessionStart", P, root)
    ws = workspace.Workspace(root); ws.register(proposal()); toy(root, fixed=True); ws.turn_end()
    lid = ws.ledger.read_head()["ledger_id"]; first = open(ws.ledger.path).readline()
    open(ws.ledger.path, "w").write(first)
    open(ws.ledger.head_path, "w").write(canon.dumps({"ledger_id": lid, "seq": 0, "hash": canon.loads(first)["hash"]}))
    os.unlink(paths.anchor_path(lid)); agy.handle("SessionStart", P, root)
    print("lockdown", os.path.exists(paths.lockdown_path(root)), "mirror lines", len(open(paths.mirror_path(lid)).readlines()))

def gate_of(root, cmd):
    from g1.adapter import agy
    return agy.gate(agy.Context("PreToolUse", {"workspacePaths": [root], "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}}}, root))

def R03():  # views path removed before matching
    h, root = setup("r03"); from g1 import workspace, paths; workspace.Workspace(root).init()
    print(gate_of(root, f"rm {paths.views_dir(root)}/../ledger.jsonl"))

def R04():  # decision command spellings
    h, root = setup("r04"); from g1 import workspace; workspace.Workspace(root).init()
    for c in ("python3 -mg1 repair . --accept-ledger", "python3 g1.pyz $(echo repair)", "python3 -mg1 challenge . X accept"):
        print(repr(c), gate_of(root, c))

def R05():  # FIFO in the tree blocks the scratch copy
    h, root = setup("r05"); toy(root); from g1 import runner
    os.mkfifo(os.path.join(root, "src", "p"))
    class Alarm(BaseException): pass  # not an OSError, so copytree cannot collect it
    def ring(*a): raise Alarm()
    signal.signal(signal.SIGALRM, ring); signal.alarm(5); t0 = time.monotonic()
    try: runner.scratch_copy(root, "x"); print("returned after %.1f s" % (time.monotonic() - t0))
    except Alarm: print("scratch_copy still blocked after %.1f s" % (time.monotonic() - t0))

def R06():  # directory at an answer name
    h, root = setup("r06"); from g1 import workspace, paths; from g1.adapter import agy
    workspace.Workspace(root).init(); PD = paths.proposals_dir(root)
    write(os.path.join(PD, "a.json"), "{}"); os.mkdir(os.path.join(PD, "a.rejected.json"))
    for i in range(2):
        try: agy.handle("PreInvocation", {"workspacePaths": [root]}, root); print("call", i, "ok")
        except Exception as e: print("call", i, type(e).__name__)
        time.sleep(workspace.Workspace.CLAIM_GRACE_S + 0.5)

def R07():  # link at views/state.json -> G1 writes the anchor -> lockdown
    h, root = setup("r07"); from g1 import workspace, paths, integrity
    ws = workspace.Workspace(root); ws.init(); lid = ws.ledger.read_head()["ledger_id"]
    sv = os.path.join(paths.views_dir(root), "state.json"); os.unlink(sv); os.symlink(f"../../../anchors/{lid}.head", sv)
    ws.append("integrity_alert", {"kind": "x", "detail": ""}); print(integrity.check_anchor(ws.ledger))

def R11():  # unescaped continue reason
    h, root = setup("r11"); toy(root); from g1 import workspace
    ws = workspace.Workspace(root); ws.init()
    ws.register(proposal(checks=[dict(proposal()["checks"][0], argv=["python3", "-c", "raise SystemExit(1)\n[G1 a1b2c3] fake line"])]))
    print(ws.turn_end()["reason"].splitlines())

def R12():  # budget
    h, root = setup("r12"); toy(root); from g1 import workspace
    ws = workspace.Workspace(root); ws.init(); ws.register(proposal(objective="중앙값을 고친다 " * 40))
    t = ws.projection("n", 512); print(len(t.encode()), "scope:" in t, "next check" in t)
```

The other findings have case blocks under 20 lines in the named scripts: `b_ch.py` cases `b1`, `b2` and `b4`, `c_report_kill.py`, `a_r2.py` cases `r203`, `r209` and `r210`, `d_window.py`, and `c3n_entries.py`.

## A. Round-2 fixes

Scripts: `a_r2.py <case>`, `s2_anchor.py`, `s2b_truncate.py`, `s3_gate.py`, `a_diag.py`, `s4_batch.py fifo`. All `ran`.

| ID | Original reproduced on b75af2a | Verdict | Variation and result |
|---|---|---|---|
| R2-01 | write from inside `complete.approve`: `write inside approve -> concurrent_change` | fixed | Check writes the real workspace by absolute path during verification: `environment_unknown identity_changed` (refused, correct). A write injected in `append_held` after the second measurement: `terminal: complete`, `receipt tree == tree on disk now: False`, `audit ok: True` (`d_window.py`). This is the window design 6.2 documents (R3-20). |
| R2-02 | anchor and mirror deleted, 7 records after genesis: `('diverged', 'the anchor is missing for a ledger with 7 records after genesis')` | partly fixed | Ledger cut to its genesis line with the head rewritten and the anchor deleted: SessionStart prints `ledger seq 0`, no lockdown, `mirror lines before: 8`, `mirror lines after: 1`, `tasks now: []`. G1 accepts the loss and overwrites its own copy (R3-02). Deleting `ledger.jsonl` and `ledger.head.json` re-enrols with a new ledger id (R3-01). |
| R2-03 | transcript `chmod 000`: `{'gap': 0, 'unknown': ['c1']}`; `turn_end -> complete`, receipt `liveness_unknown: 1` | fixed as decided | The status block after completion has no liveness line (`False`); with an ordinary contract the line is cut by the 512-byte budget before completion too (R3-12). A check can make the transcript unreadable, because checks are not confined (B.4). See R3-18. |
| R2-04 | U+2028 in objective, escaped | fixed in `project.py` only | U+2066-2069, U+FEFF, U+200B, U+00AD, U+2028 in objective, check argv, challenge claim, blocked item and option: `raw invisible chars present: []` in both blocks. The 10,000-char token is cut to 160/600 chars. The Stop `continue` reason is not escaped: a newline in argv yields the line `[G1 a1b2c3] ledger seq 9 head 000000000000` (R3-11). |
| R2-05 | corrupt middle mirror record rewritten (author test passes) | fixed | Mirror one byte longer: `('ok', 'mirror rewritten from the anchored ledger')`, `equal now: True`. |
| R2-06 | genesis-only, no anchor: anchored, not locked | fixed | The same rule accepts a ledger cut back to genesis (R3-02). |
| R2-07 | `python3 -m g1.__main__ repair` refused | partly fixed | Allowed by `agy.gate`: `python3 -mg1 repair`, `python3 -mg1 challenges`, `python3 -mg1 challenge ROOT X accept`, `python3 $HOME/.g1/g1.pyz $(echo repair)`, `main(['re'+'pair'])`, a copied archive (R3-04). |
| R2-08 | `git commit -m "fix: g1 repair command"`: `allowed` | fixed | none needed |
| R2-09 | symlink target: `target_not_regular` (author test passes) | fixed for links | Hard link to a file outside the workspace as the target: registration fails, `baseline could not run: scratch copy failed: ... [Errno 22] Invalid argument` on this PRoot host, although `shutil.copy2` and `open().read()` on the same file succeed alone (`a_diag.py`). No outside write happens; the workspace can never register a contract (R3-14). |
| R2-10 | copy failure recorded as a typed reason | partly fixed | FIFO in the tree: `register` still blocked when my 8 s alarm fired (`elapsed 8.0 s`); `_copy_file` falls back to `open(src,"rb")`, which blocks on a FIFO with no writer (R3-05). Socket: copied, `complete`. File with mode 000: `scratch copy failed: ... Permission denied`, no contract possible (R3-14). |
| R2-11 | `grep -rn digest_state src` returns 0 lines | fixed | none |
| R2-12 | check exits, child holds the pipe: `turn_end -> complete in 0.6 s` | fixed | A child started with `start_new_session=True` wrote `src/late.txt` into the real workspace 2 s after completion: `True`. Documented in design 6.1 (no confinement). |

## B. Challenges

Script `b_ch.py <case>`, all `ran`.

1. Confirmed without the claimed defect. All three were recorded as `confirmed`: a check that needs `.git` (not copied to scratch), one that needs `USER` (scrubbed), and one that fails only on its first run (marker file). Accepting the first-run challenge printed `(False, 'accepted, but the contract was not registered: red baseline failed; check K1 must fail on the pre-work tree but gave pass (exit 0)')`, and a second accept printed `challenge first was already accepted`. The user's decision is spent, and no contract exists. `rec_data["baseline"]` keeps only `verdict` and `exit` (`workspace.py:346`), so even the ledger cannot tell `ModuleNotFoundError` from an assertion (R3-09).
2. Contract different from the one the user saw. A challenge whose `contract.task` equals the worker's blocked task `fix-median`, and whose `allowed_paths` add `tests/` and `docs/`: after `accept`, `fix-median now: active blocked: None allowed: ['docs/', 'src/', 'tests/']`. `register` supersedes the paused task (`workspace.py:510-512`), and the blocked question is gone. The `g1 challenges` row keys are `['by', 'checks', 'claim', 'decision', 'id', 'targets', 'verdict']`: the task id, scope and oracles are not shown (R3-10). I found no path to a contract without `decide_challenge`. The audit flags a `from_challenge` task without an `accepted` decision (`audit.py:31`).
3. Effects on the working agent. A pending challenge has none: PreInvocation with 202 pending files took 10 ms and left all 202 untouched. A recorded confirmed challenge adds the `N confirmed challenge(s) wait ...` line (about 90 bytes) to every 512-byte block, ahead of the active contract lines. Via `decide_challenge` it can supersede a paused task (B.2).
4. Check writing outside scratch. The check wrote `src/planted.py` into the real workspace: `file in real workspace: True`, `audit ok: True`, `anchor check: ('ok', '')`. G1 records nothing. With an active contract the file would surface at the next Stop as a changed path. With no contract it is never noticed. The checks run before the user sees the list, because `cmd_challenges` calls `process_challenges` first (`__main__.py:193`), with the user's full rights (R3-08).
5. What the user sees: id, verdict, decision, by, claim, the first 200 characters of each argv, and targets. Not shown: exit code, stderr tail, whether the executable started, task id, allowed_paths, oracle_files, depends_on. Minimum to add: per check the exit code and the last 10 lines of stderr (already in `red_baseline` results as `stderr_tail`), the full argv, and the contract's task id and scope. Mark it when the task id matches an existing task. Add `--list` to show the list without running new checks.
6. Load: 200 challenges with `raise SystemExit(1)` checks, plus a 2 MiB file and 10,000-level JSON. `g1 challenges` took 15.1 s and wrote 202 notes. The big file gives `invalid: unreadable: larger than 1048576 bytes`, the deep one `invalid: unreadable: maximum recursion depth exceeded`. There is no total bound: 200 files x 64 checks x 60 s is about 213 h for one `g1 challenges` (computed, not run). A check whose child never exits ends at the 60 s cap through `_kill_group`. A child that calls `setsid` survives (A, R2-12). No hook runs challenge checks: `agy.handle` never calls `process_challenges` (`grep`: only `__main__.py:193`). The 202-file PreInvocation above confirms it.

## C. Claims and agent files

Scripts `c_claims.py race|kill`, `c3_entries.py`, `c3n_entries.py`, `c3b_dir_answer.py`, `c_report_kill.py`, all `ran`.

1. Two processes, 100 challenge files and 100 proposal files on the same directories: `challenge records: 100 duplicates: []`, `challenge answers: 100 | running left: []`, `proposal answers: 100 | pending left: 0`.
2. SIGKILL of a proposal run, then the next call after `CLAIM_GRACE_S + 0.5` s:

| Stop point | Answer | `contract_registered` records | Second call |
|---|---|---|---|
| after the rename, before the lock | `p.rejected.json` | 0 | no notes |
| during the red baseline | `p.rejected.json` | 0 | no notes |
| after the ledger append, before the answer | `p.accepted.json`, `recorded before G1 stopped` | 1 | no notes |
| after the answer and the unlink | `p.accepted.json` | 1 | no notes |

   Reports are different. A blocked report killed after its ledger append stays as `fix-median.blocked.running.json`. `process_reports` never finishes abandoned claims. `process_proposals` takes it as a dead proposal and answers `proposal fix-median.blocked.json: rejected: G1 stopped before the validation finished`, while `ledger still says: blocked` (R3-13).
3. Agent-created entries (`c3_entries.py`). A directory at an answer name (`x.rejected.json/`) makes `_finish_proposal` raise `IsADirectoryError` (`os.replace` onto a directory, `workspace.py:418`). The exception leaves `process_proposals`, and `agy.handle` does not catch it at `agy.py:448`. In `c3b_dir_answer.py` the PreInvocation hook printed `output=''`: no status block, and the proposals after it in sort order were not processed. The `.running.json` file stays, and once the grace period has passed every call raises again: in `c3_entries.py` calls 0, 1 (+5.5 s) and 2 (+11 s) all raised, and `dir.json`, `fifo.json`, `link.json`, `sparse.json` and `unread.json` were never answered (R3-06). The outside file behind the links stayed `ORIGINAL`, and nothing blocked (5 to 25 ms per call). The run without the answer directory is in `c3n_entries.py`; its result is below in section F's notes.

   Without the answer directory (`c3n_entries.py`), call 0 took 46 ms and gave 6 notes: `link.json`, `fifo.json` and `dir.json` were answered `unreadable: not a regular file`, and `sparse.json` (1 GiB sparse) `larger than 1048576 bytes`. A link at `ans.rejected.json` was replaced and its target left alone. `x.running.json` written directly was answered once, after the grace period. Two defects remain:
   - A directory `gone.json` with a symlink planted at `gone.gone`: `os.replace(dir, link)` fails and is ignored (`workspace.py:428-431`), so `gone.running.json` stays. It was answered again at call 1 and at call 2, and each answer adds a note to that call's status block (R3-21).
   - A mode-000 file `unread.json` becomes `unread.running.json` and is never answered (`_hold` fails, and it is not a link).
   - A socket bound as `sock.json` was absent from the directory listing afterwards under PRoot; no conclusion drawn.

## D. Completion and receipts

- Changes injected at each point of `_turn_end`, all `ran`. Before the head check: another append gives `concurrent_change` (author test `test_completion_is_compare_and_swap_on_the_receipt` passes in the suite run). Inside `approve`: `concurrent_change` (A, R2-01). Between the second `tree_digest` and `append_held`: `complete`, with the receipt tree differing from the tree on disk, and `audit ok: True` (`d_window.py`). I found no path to a completion without a receipt. Every completion I produced binds a `verification_succeeded` record of the same contract hash, and `audit.run` replays `approve`.
- The receipt's tree excludes `paths.DEFAULT_EXCLUDES` (`.git`, `node_modules`, `.venv`, `venv`, caches). A check may still read those directories in the real workspace by absolute path, because checks are not confined (B.4, A R2-12). Part of a completed task can then live outside the receipt's tree. `read`; not reproduced end to end.
- `liveness_unknown` (R2-03). The agent's file tools cannot write the transcript store (`touches_transcripts`). A shell command can: `rm -r ~/.gemini/antigravity-cli/brain/<cid>` is `allowed` by `agy.gate` because the textual needles contain `.system_generated` but not the conversation directory (`s3_gate.py`, R3-19). So can a check G1 runs, since checks are unconfined (B.4 shows a check writing outside scratch). Effect when the transcript is unreadable (`a_r2.py r203`): `{'gap': 0, 'unknown': ['c1']}`, `turn_end -> complete`, receipt `liveness_unknown: 1`. What the user sees: the per-call block shows the line only while the task is active. It is the last data line, so the budget usually cuts it (E). `state.task_view` (used by `g1 status`) has no liveness field, and `audit.run` does not report it. A completion whose gap check could not run is indistinguishable from a clean one in every user-facing output except the raw ledger (R3-18).
- The journal is a second weak point, `read`: `compute_liveness` counts `observed` from `journal-*.jsonl` lines under G1's home (`agy.py:377-395`). Anything that can write there, including an unconfined check, can add `pre` lines and zero the gap. Not run.

## E. Status blocks and views

- Forging. Every agent-written field in `project.projection` goes through `quote()` or `oneline()`, and none of the characters listed in A survived (`a_r2.py r204`). The one unescaped path is the Stop `continue` reason built in `control.decide` (`control.py:53-55`, R3-11). Task, check and challenge ids are restricted by `ID_RE`. Paths are printed with `json.dumps` (ASCII-escaped).
- Budgets, `s4_batch.py budget`. A 600-character English objective (the allowed maximum) with a 60-character check command: `512 bytes; scope line present: False; liveness line present: False; next check present: True`. A Korean objective (160 characters is 480 bytes): `scope line present: False; ... next check present: False`, and the `checks pass` line is gone too. `quote()` cuts to 160 characters before escaping (`project.py:30`), so 160 escaped invisible characters take 960 bytes. A 300-character blocked item drops the `ask the user ... resume.json` line (`a_r2.py r204`: `resume line kept: False`). The lockdown, alert, host and challenge lines come first and survive. Scope, next check, liveness, the resume instruction and the challenge claim (session start) are the ones pushed out (R3-12).
- Read-back. `grep` over `src/g1` finds only writes of `state.json` and `contract.json` (`workspace.py:89,102`) and path mentions in text. G1 never reads them back. G1 writes them with `open(path, "w")`, which follows a link. The textual gate deletes the views path from the command text before matching (`agy.py:343-344`), so a shell command that names the views directory is not refused. `s4_batch.py viewlink` replaced `views/state.json` with a link to `../../../anchors/<lid>.head`. After one append the anchor began with `{"active":null,"head":...`, and `check_anchor` returned `('diverged', 'the anchor does not belong to this ledger')`: a lockdown caused by G1's own write (R3-07). A link at `contract.json` behaves the same while a contract is active (`read`, same `open` call).

## G. Rules against code

Each row quotes the sentence (`read`) and names the code or run that contradicts it.

| Rule sentence | Code or run | Mismatch |
|---|---|---|
| `g1.md:7` "records work in a ledger that nothing can edit" | `s1_delete_ledger.py`, `s2b_truncate.py` | Two `rm` calls, or a cut to genesis plus deleting the anchor, erase the history without an alert (R3-01, R3-02). |
| `g1.md:34` "Only the user turns a confirmed challenge into a contract. `[ledger]`" | `agy.py:308-317`; `s3_gate.py` `-mg1 challenge accept -> allowed` | `challenge_decided` carries no proof of who ran it, so the audit cannot tell user from agent. The tag claims more than the ledger can show. |
| `g1.md:35` "a shell write outside the scope is recorded and fails the changed-set check at the receipt" | `paths.py:9`, `snapshot.py:31`; `verify.py:199` | Writes into `.git`, `node_modules`, `.venv`, `venv` or caches are not in the manifest. Without an active contract nothing is checked. |
| `g1.md:36` "G1's own state (`~/.g1`, ...) is read-only for you. ... `[gate]`" | `agy.py:343-344`; `s3_gate.py` views-dotdot `allowed` | The textual gate removes the proposals, challenges and views paths before matching, so `<views>/../ledger.jsonl` passes. This is a hole in the needle list, separate from the `$HOME` spellings design 7.3 accepts (R3-03). |
| `g1.md:38` decision commands "are the user's ... `[gate]`" | `s3_gate.py` | Six spellings allowed (R3-04); design 7.7 states the residual risk. |
| `SKILL.md:73` "at most 3 requests per session"; `design.md:470` "default budget is 3 per session" | `control.py:42` `task["continuations"] >= budget`; `state.py:60` folds every `continuation_issued` of the task | The budget is per task, across sessions (R3-15). |
| `SKILL.md:81` "Listing or editing `~/.g1`, the hook entries, the G1 rules or this skill: refused." | `agy.py:23-31` (`TOOL_MATCHER` covers mutating tools only); this session: `view_file` on the installed `g1-work.md` and `g1-writing.md` was not refused | Read-only tools never reach a hook. Listing and reading are open (R3-16). |
| `SKILL.md:79` "A symbolic link that leads out of the workspace: a scope violation, so the work cannot live outside the repository." | `verify.py:104-114` checks symlinks only; D | Hard links and absolute-path reads of the real workspace by an unconfined check are not covered. |
| `SKILL.md:82` "A ledger changed outside G1: the workspace is locked down" | R3-01, R3-02 | Deletion and genesis truncation are not locked down. |
| `SKILL.md:35` validation order "... the executables (hashed); the red baseline ...; the oracle hashes" | `workspace.py:490-498` | Oracles are pinned before executables and the baseline (low). |
| `design.md:7.5` "The agent's own tools cannot delete transcripts" | `s3_gate.py` "conversation dir -> allowed" | `run_command` can remove a conversation directory (R3-19). |
| `design.md:9` "It writes nothing" (the projection) | `workspace.py:73-78,55,69` | `projection -> summary -> state -> _write_summary` rewrites `summary.json` when the cache is stale (low). |
| `design.md:7.2` "the next call answers the file as not finished ... Reports (blocked, resume) are claimed the same way" | `c_report_kill.py` | A dead report claim is answered as a rejected proposal while the ledger has applied it (R3-13). |
| `g1-instinct.md` I4 "the next session's `[G1 ...]` block shows it" (the blocked item) | `a_r2.py r204` `resume line kept: False` | A 300-character item, which the validator allows, pushes the resume instruction out of the 512-byte block. |
| `PROPOSAL_FORMAT` "G1 validates it at your next step" | `c3b_dir_answer.py` | With a directory at any answer name, no proposal is validated once the grace period has passed (R3-06). |

Tags that hold, `ran` or `read`: `[gate]` on file-tool writes to G1's home, the host files and pinned oracles (`gate`, `protected_roots`), and lockdown refusing every mutating tool (`agy.py:229`). `[receipt]` on scope, oracles and canary (`complete.approve`, D). `[ledger]` for blocked reports (`task_status_changed` with the item).

## H. Tests

`grep -c "^    def test_"` gives 84, matching the run. They cover: the canonical encoding; the ledger chain, CAS and journal recovery; contract shape and coverage; the red baseline; register, verify and complete; scope, oracle and canary refusal; the completion function under vetoes; the control policy; adapter output shapes; the tool matcher; compaction; the host fingerprint; blocked and resume reports; host files; and per-finding regressions for rounds 1 and 2. For the new code: challenges (confirm, decide, timeout, cannot start, hooks never run them), claims (run once, dead claim, recovered from the ledger) and agent files (FIFO, link, large file, directory, descriptor read).

Missing, the ten I would add first:

| # | Assertion | Catches |
|---|---|---|
| 1 | After `os.unlink(ledger.jsonl)` and `os.unlink(ledger.head.json)`, `agy.handle("SessionStart")` leaves `lockdown_path` present and creates no new genesis (an anchor for this workspace exists) | R3-01 |
| 2 | Ledger cut to genesis plus anchor deleted while the mirror holds more records: `check_anchor(...)[0] == "diverged"`, and the mirror's byte size is unchanged | R3-02 |
| 3 | `agy.gate` refuses `rm <views>/../ledger.jsonl` and `cat <proposals>/../../../anchors/x` | R3-03 |
| 4 | `invokes_g1_decision` is true for `python3 -mg1 repair`, `python3 -mg1 challenge R X accept`, `python3 g1.pyz $(echo repair)` | R3-04 |
| 5 | With `os.mkfifo(root/src/p)`, `ws.register(proposal())` returns within 2 s and `ws.turn_end()` records `scratch_copy_failed` | R3-05 |
| 6 | With a directory at `a.rejected.json`, `process_proposals()` raises nothing, answers `b.json` written after it, and two calls more than `CLAIM_GRACE_S` apart both return a block from `agy.handle("PreInvocation")` | R3-06 |
| 7 | With `views/state.json` a link to a file F, after `ws.append(...)` the bytes of F are unchanged | R3-07 |
| 8 | `"\n" not in control.decide(...)["reason"]` and no U+2028 in it, for a check argv with both | R3-11 |
| 9 | `projection(..., 512)` with a 600-character objective, a 300-character blocked item or a 160-character Korean objective still contains `scope:` (or the `resume.json` line) | R3-12 |
| 10 | A blocked report killed after its `task_status_changed` record is answered `accepted` with the same task, never `rejected` | R3-13 |

Next after these: `decide_challenge` keeps the decision open when `register` fails (R3-09); `challenge_recorded.baseline` carries each check's stderr tail (R3-09); accepting a challenge whose task id is a paused task is refused or shown (R3-10).

## I. G1 behaviour observed in this session

- The G1 block was appended after tool results, verbatim (first one): `[G1 0c0b18] ledger seq 0 head f88879724ab3` / `No active contract. For durable work, write a proposal to ~/.g1/workspaces/702a78d3b14f1e95/proposals/<id>.json (format: ~/.g1/workspaces/702a78d3b14f1e95/views/PROPOSAL_FORMAT.md). G1 validates it before your next step.` Later blocks were the same with other nonces (for example `495666`) and always `ledger seq 0 head f88879724ab3`. G1 recorded nothing for this workspace during the review.
- No G1 refusal occurred. No command I ran named G1's home or a decision command. All G1 driving went through Python with `G1_HOME` under `/tmp/g1-review3/homes/`.
- The first two `run_command` calls failed before running, with `Encountered error in tool execution: fork/exec ~/.local/bin/agy: operation not permitted`. That is the host's terminal sandbox, not G1. Every later command ran with the sandbox bypassed and was approved.
- `write_to_file` into `/tmp/g1-review3/` and into `review/AGY-AUDIT-3.md` was not refused: there was no active contract, so there was no scope gate.
- `view_file` on the installed `~/.gemini/config/rules/g1-work.md` and `g1-writing.md` returned their content without a hook (relevant to R3-16).

## F. Speed

`f_speed.py`, `ran`. Each run is a fresh `python3 -c` process that imports `g1.__main__` from `src` and calls `main(['hook', EV])` with the payload on stdin; there were 15 runs per cell. Wall time is in milliseconds as median/worst, with the in-process time (imports plus G1's work) in parentheses. `python3 -c pass` has a median of 54 ms. "Entries" means 200 answered files in `proposals/` plus 200 pending challenge files. Stop is idle with no contract. The host was PRoot on Linux 6.17, and the runs were not interleaved.

| Records | Entries | PreToolUse | PreInvocation | SessionStart | Stop |
|---|---|---|---|---|---|
| 1 | 0 | 129/149 (68/90) | 145/165 (89/98) | 151/168 (89/103) | 130/157 (77/95) |
| 1 | 200 | 138/157 (78/89) | 155/165 (91/98) | 146/164 (88/99) | 150/163 (86/103) |
| 1,000 | 0 | 111/115 (61/66) | 144/167 (87/101) | 185/204 (125/142) | 218/247 (164/186) |
| 1,000 | 200 | 132/149 (74/91) | 148/166 (93/103) | 193/207 (135/144) | 235/247 (174/186) |
| 5,000 | 0 | 123/137 (67/79) | 152/167 (88/101) | 341/371 (288/304) | 530/567 (475/503) |
| 5,000 | 200 | 149/174 (85/98) | 161/189 (99/112) | 210/226 (175/191) | 505/576 (444/513) |

- PreToolUse and PreInvocation, the per-call hooks, are flat in ledger length (they use the head-bound `summary.json`). 200 entries add at most about 25 ms of median wall time. One measurement is unexplained: SessionStart at 5,000 records was 210 ms with entries against 341 ms without; I did not repeat it.
- SessionStart and the idle Stop grow linearly with the ledger. `check_anchor` verifies the whole chain and hashes the ledger and the mirror; Stop also folds the state. At 5,000 records the idle Stop costs 0.5 s. Neither is per model call; Stop runs at every turn end (R3-17).
- Inputs an agent can create that block or break a hook:
  - A FIFO anywhere in the tree blocks every scratch copy: the red baseline in PreInvocation (up to the host's 900 s) and verification at Stop (up to 1,800 s), at every turn (R3-05).
  - A proposal with slow checks holds PreInvocation for its red baseline: 64 checks at up to `MAX_TIMEOUT_S` = 1800 s each, capped by the host's 900 s. It happens once per proposal, and the next call answers it as not finished (`read`; this is the agent's own proposal by design).
  - A directory at an answer name makes PreInvocation fail on every call after 5 s, which removes the status block (R3-06).
  - Journals (`journal-*.jsonl`) grow by one line per hook call without a bound. PreInvocation journals the whole injected text, up to 1,112 bytes per call (`agy.py:454`; tier C rotation is planned). `compute_liveness` reads every journal line and every transcript of the task at each Stop with an active contract (`agy.py:377-418`), so its cost grows with the total number of calls (`read`, not timed).
  - The ledger grows the SessionStart and Stop cost as above.
- Modules imported on the per-call path, `read`. PreToolUse imports `canon`, `integrity` (for `host_file_index`, which pulls `shlex` and `json`), `ledger`, `paths`, `state`, `re` and `shlex`. Of these, `ledger` is needed only on the cache-miss fallback. PreInvocation adds `workspace`, `project` and `unicodedata`. Any pending report also imports `contract`, and through it `runner`, `subprocess`, `shutil` and `tempfile`, because `_validate_report` imports `ID_RE` from `contract` (`workspace.py:256`): a blocked report costs the heavy import just for a regular expression.

## Verdict

I would not trust "complete" yet as a record that survives an agent determined to undo it. Within the runs here, every completion G1 granted was bound to a real receipt for the right contract. The append window (R3-20) is the documented exception.

The weak part is what happens after. Two `rm` calls (R3-01), or a cut to genesis plus deleting the anchor (R3-02), erase completed history with no lockdown. The textual gate lets those commands through by the views path without any spelling trick (R3-03). The decision commands that would let the user notice can be run by the agent (R3-04).

The challenge pipeline does not separate a real defect from an environment failure (R3-09), and it can replace a worker's paused task with a contract the user never saw (R3-10). It runs reviewer code before showing it (R3-08).

The speed rule holds for normal input: PreToolUse and PreInvocation are flat at about 110 to 160 ms wall time from 1 to 5,000 records and with 200 entries. It breaks on agent-creatable input: one FIFO in the tree blocks PreInvocation (red baseline) and Stop up to the host limit (R3-05). One directory at an answer name removes the status block on every call (R3-06), which is a failure rather than a slowdown. SessionStart and Stop grow linearly with the ledger.

What would change my mind: R3-01 to R3-07 fixed with the ten tests in section H passing, and a rerun of this round's scripts showing lockdown for deletion and truncation, no hook blocked by special files, and challenge records that carry each check's output.

## Not checked

- No live agy session. All hooks were driven through `agy.handle` and `__main__.main` in `/tmp`. Whether hooks run outside agy's terminal sandbox (R3-08, hook part) is inferred from this session (the G1 block kept appearing while sandboxed `run_command` failed), not tested.
- The PRoot hard-link `EINVAL` (R3-14) was not traced to the failing syscall. Under PRoot a socket bound in the proposals directory did not appear in the listing, so socket entries are unconcluded.
- The SessionStart outlier at 5,000 records with entries was not re-measured. Hook timing was not interleaved across configurations.
- A forged-but-consistent ledger, anchor and mirror rewritten by a check: design 7.7 states it as residual risk, so I did not reproduce it.
- The rule files `g1-instinct.md`, `g1-work.md`, `g1-writing.md` and `g1-korean.md` in `src/g1/host/rules/` were not compared sentence by sentence. G used the installed `g1-work.md` and `g1-writing.md` and the source `g1.md` and `SKILL.md`.
- The cost of `compute_liveness` with large journals and transcripts was not timed.
