# G1 Design

Version 0.1, 2026-10-11. The public name of the project is im-not-gembyeong (제미나이, 더 이상 젬병이 아니(고 싶)다.);
G1 is the development name and the name of everything in the code, the commands and these documents.

## 0. How to read this document

G1 is small, but every part of it exists for a reason, and this document names the reason each time.
You will see labels like `LED-16` or `OUR-01` after a rule. Each label points to a design atom: one idea taken
from an earlier project, with a verdict. The full list is in `research/atoms/CATALOG.md`. You can ignore the labels
on a first reading. They are there so that no rule in G1 is without a traceable origin.

Some mechanisms are built and some are planned. Built means: in the code, covered by a test, and exercised in
real agy sessions. Planned means: designed, not yet in the code. Every planned item says so.

Sources used throughout:

- `docs/principles.md`: the principles (P1-P8), the philosophy (PH), the two-way test (TW), zero trust (Z1-Z7).
- `docs/host-agy.md`: what we measured about agy's hooks.
- `research/agy-hooks/`: the raw measurements (25 contract probes, 6 coverage runs, 8 honesty runs, 4 capability probes).
- `research/measure/`: six A/B measurement runs and experiment C1, 137 sessions.
- `research/review/`: independent reviews of the code and what was done with each finding.

## 1. Purpose and non-goals

G1's purpose is to keep the work of Gemini 3.8 Flash on the Antigravity CLI from being lost or falsely completed.

- A fresh agent continues durable work from G1's records alone (P1, TW-b).
- A task is complete only when G1 itself verified it and bound the receipt (P4, P5).

What "better performance" means here (PH): G1 adds no intelligence. It removes four losses: work lost between
sessions, false completion, continuation without progress, and verification that proves nothing. The native agy loop,
tools, permissions and orchestration stay native (P2).

Non-goals:

- Prompt tricks without measured effect. The wording G1 injects is a measured variable, never a guarantee (PTH-07).
- Model routing, judge models or ensembles on the authority path (KEV-02 rejected, PTH-34).
- Rebuilding agy's native orchestration. Subagents, goal mode and parallel attempts stay native; G1 verifies results (section 12).
- Full defence against a hostile agent that rewrites every G1 file consistently through the shell in one session.
  Section 7.7 states this residual risk.

## 2. What can go wrong, and what G1 does about it

| ID | Threat | Evidence that it is real | G1's answer |
|---|---|---|---|
| TA | False or premature completion | 3 of 8 blocked runs ended with "DONE" (measured); THR-57 | Only G1 receipts complete a task (section 6). The agent's text is never an input (ASC-37). |
| TB | Weakened or empty checks | THR-29; the predecessor's verifier was agent-controlled; PSN-13 | Red baseline, pinned oracle files, coverage matrix (section 5). |
| TC | Edits outside the scope; shell after a refused write | LIFE-25; 8 of 8 agents tried the shell right after a refused file write (measured) | Scope gate and textual gate before the call; exact changed-set check at completion (PTH-29). |
| TD | State lost between sessions | P1; GOV-01 | The ledger is the only store; the projection is built from it (sections 4, 9). |
| TE | Tampering with G1's state, hooks or code | hooks reload at session start (measured); LED-60; THR-01/07/09 | Path gates, pinned bootstrap, anchors, mirror, self-heal (section 7). |
| TF | Continuation without progress | THR-19/38/39; ten forced continues cost 26 times one answer (measured) | The vector Stop policy with a persisted counter (section 8). |
| TG | Gates so broad they break native work | THR-16 | Gates are narrow, deterministic and named. No shell classifier decides anything (ASC-17). |
| TH | Gates that silently stop running | PSN-08 (hooks that never fired, unnoticed); ASC-15 | Per-session liveness proof and a sticky gap counter (section 7.5). |
| TI | The host changes under G1 | PTH-21 (a stale claim about agy); ASC-44; agy updates itself | Host fingerprint at every session start; completion withheld after a change (section 10). |
| TJ | "Unknown" treated as "pass" | ASC-16; PTH-30 | Every fact is pass, fail or unknown. Unknown never satisfies a gate. |

## 3. Architecture

```text
agy (native loop, tools, permissions, subagents: unchanged)
  └─ ~/.gemini/config/hooks.json, group "g1"   (one layer, the root of trust)
        each entry: python3 -I -S -c '<bootstrap: sha256(~/.g1/g1.pyz) must equal the pinned value, else exit 3>'
        │
        ▼
  G1 core (~/.g1/g1.pyz, Python standard library only, no host names)
     canon · ledger · snapshot · contract · runner · verify · complete · control · project · integrity · audit
        │
  adapter/agy.py  (the only module that knows agy; see docs/host-agy.md)
        │
  state under ~/.g1/
     g1.pyz, manifest.json (code hash, hook entries, host files, host fingerprint)
     workspaces/<id>/   ledger.jsonl, ledger.head.json, ledger.pending.json, ledger.lock,
                        proposals/ (the agent writes here), evidence/<attempt>/, views/ (derived)
                        summary.json (head-bound cache for the per-call hooks)
     anchors/<ledger_id>.head, mirror/<ledger_id>.jsonl, observe/<id>/ (journals, lockdown), scratch/
  host files installed by G1 (section 9.1):
     ~/.gemini/config/rules/g1.md, g1-instinct.md          (always on)
     ~/.gemini/config/rules/g1-work.md, g1-writing.md, g1-korean.md   (read on demand)
     ~/.gemini/config/skills/g1/SKILL.md
```

Structural rules:

- The core returns host-neutral verdicts (`none`, `deny`, `continue`, `inject`). The adapter translates them to agy
  JSON. A test asserts that the PreToolUse output set is exactly `{"", deny}` (ASC-38, PTH-09). Built.
- Nothing is written into projects. Per-workspace state is keyed by the workspace's real path under `~/.g1/workspaces/`.
  The home directory, `/` and G1's own home are never enrolled. Built.
- No host names in the core. A test greps every core module for `agy`, `antigravity`, `gemini` and finds nothing (PTH-44).
  Host knowledge lives in `adapter/agy.py`; `install.py` and `__main__.py` are the composition layer that wires the
  adapter to the core; `g1/host/` holds the files installed into the host. Built.
- One home per fact (KEV-29): only the ledger module appends, only the gate prints PreToolUse decisions, only the
  snapshot module computes tree digests. Planned as a lint.
- Evidence classes (ASC-17): a mechanism is `g1-run-check`, `exact-hash`, `host-payload` or `heuristic`. Only the first
  two may refuse a call or ask for a continuation. Followed in the code; planned as a table test.

## 4. The ledger

### 4.1 Why a chain

A record that can be edited is only a claim. G1's ledger is an append-only file where each record holds the
hash of the one before it. Change any byte of the past and every later hash stops matching. The head (sequence number
and hash of the last record) is kept in a second file. Outside the workspace state, the anchor holds the head G1 last
committed and the mirror holds a copy of every record.

One commit, all under the ledger lock: journal the record, append it, move the head, move the anchor, append the record
to the mirror, clear the journal. Recovery finishes an interrupted commit from the journal: if the crash hit the append
itself, the unterminated line is completed from the journaled record, so no committed byte is ever removed; any other
unterminated or unreadable tail is reported as corruption. Readers read the chain only up to the head, so a commit in
progress is never half seen. Whenever no journal is pending, the head, the anchor and the mirror's last record are the
same record, and because the anchor's hash commits to every earlier record, a ledger whose head differs from its anchor
was changed outside G1 (section 7.6).

### 4.2 Kept from the predecessor (T1)

Exact record envelope (LED-02), domain-separated record hash (LED-10), contiguous chain from genesis (LED-11), ledger
id (LED-12), head anchor (LED-13), write-ahead journal (LED-16), durable commit order (LED-17), exact-match recovery that
never truncates (LED-18/19), atomic replace with inode check (LED-24), no-follow opens (LED-27), zero-write reads
(LED-29), event allowlist (LED-33), reserved-field protection (LED-35), validate before the first write (LED-49), the
writer round-trips through the reader (LED-50), completion binding (LED-45/46), staleness (LED-47), terminal tasks
(LED-48), typed codes (LED-57), linear verify with O(1) append (LED-59). All built.

### 4.3 Changed from the predecessor

1. The ledger is the only canonical store. Contracts live in full inside `contract_registered` records. Views are
   derived and never read back (removes LIFE-17, THR-26, THR-37). Built.
2. The encoding is specified: UTF-8, sorted keys, compact separators, no floats, integers within ±(2^53−1),
   duplicate keys rejected before hashing, no trailing data, no lone surrogates (PTH-12), so one record has exactly one
   meaning. Strings are hashed as the exact code points they hold; there is no Unicode normalization, because two file
   names that differ only in normalization are two different files. Built.
3. Compare-and-swap append (PTH-26): an append may name the head it expects and fails with an error if the head moved.
   The completion record is appended this way, bound to its receipt (section 6.2). Built.
4. Locks have a timeout and an inode re-check after acquisition (THR-13). Built.
5. Genesis is journaled. Built.
6. Descriptor-relative opens with an owner check; depth and file-count limits on tree walks; symbolic links are
   recorded, never followed. Built.
7. Three-state facts (ASC-16, PTH-30): a check result is pass, fail or unknown; a tool call is executed, denied or
   unknown. Unknown never satisfies completion. Built.
8. Schema version in every record; an unknown version fails closed instead of migrating silently (PTH-10). Built.
9. Observations are not in the ledger (THR-17). Hook journals live under `~/.g1/observe/`. Built.
10. Idempotent completion keyed by task and receipt hash (PTH-15). Built.
11. Replay re-derives verdicts (OUR-46): the audit recomputes each stored verdict from the per-check results it
    cites, and a stored verdict more favourable than its results is a finding. Built in `g1 audit`.
12. Content-addressed evidence (OUR-25). Planned.

### 4.4 Events

`contract_registered`, `contract_superseded`, `contract_invalidated`, `verification_started`, `verification_succeeded`,
`verification_failed`, `continuation_issued`, `task_status_changed` (active, paused, complete), `host_contract_observed`,
`integrity_alert`, `checkpoint`, `challenge_recorded`, `challenge_decided`. A `complete` status is allowed only with a receipt binding.

### 4.5 Storage

Measured: the predecessor held 1.6 MB after 39 contracts. agy's own conversation store grows about 200 times faster.
G1 never reads old agy conversations, so a user may delete them freely.

| Tier | Content | Rule | Status |
|---|---|---|---|
| A. Authority | contracts, receipts, status records | never deleted | built |
| B. Evidence bytes | check output per attempt | kept for completion-bound receipts and the last three attempts; the rest is removed, the receipt keeps the digests | built |
| C. Observation | hook journals | rotated once past 8 MiB per layer; the gap check reads both files | built |
| D. Scratch copies | tree copies for verification and canary | created per attempt, deleted after; a free-space check runs first and a shortage makes the check unknown | built |

Checkpoint records that let a session verify only the latest segment (for very long histories) are planned. Ledgers
measured so far are kilobytes per contract.

## 5. Contracts

### 5.1 Why a contract comes first

If the definition of "done" is written after the work, it will describe whatever was done. A contract fixes the
definition before the first edit: the goal, the criteria, the checks that prove each criterion, the files the agent
may change, and the files the checks depend on.

### 5.2 Lifecycle (built)

1. The agent writes a proposal to the workspace's proposals directory. The directory is named in every status
   block G1 injects, and the format is in `views/PROPOSAL_FORMAT.md` and in the installed skill.
2. Before the next model call (and at an idle Stop), G1 validates the proposal with strict decoding (ASC-07): an
   unknown key rejects the whole proposal.
   - Coverage matrix (principles section D, PTH-38, KEV-06): every criterion needs a check and every check must
     cover a criterion. A manual-only criterion counts as uncovered.
   - Scope: allowed paths are relative, do not traverse upward, and are never `.` (THR-32).
   - Plain argv (OUR-07): a check is one command vector. No shell. G1 records the hash of the executable and
     re-hashes it before every run (OUR-22).
   - Targets: every `must_flip` check names the files of the work it depends on. A target lies inside the allowed
     paths and is never an oracle file; otherwise a check could pass for a reason unrelated to the work, such as a
     file outside the workspace, or corrupting the test itself would make any check look sensitive.
   - Size limits: 600 characters of objective and criterion text, 64 checks, 64 argv entries, 300-character paths,
     no control characters in paths.
   - Red baseline (PSN-13, PTH-14, OUR-12): G1 runs every `must_flip` check on a copy of the untouched tree. Each must
     fail. A check that already passes proves nothing about the work. A `guard` check must pass now and at completion.
   - Oracle pinning (PTH-41, ASC-03, ASC-12): G1 hashes every oracle file (tests, fixtures, configs the checks read)
     and stores the hashes in the contract. Writes to them are refused during the task. At completion they must be unchanged.
   - Scope snapshot: G1 stores the whole tree manifest at contract time for the changed-set check (PTH-29).
3. A valid proposal becomes `contract_registered` with the baseline results; the task is active; the result is injected.
   An invalid one gets typed reasons injected.
4. A new proposal with the same task id supersedes a paused task (`contract_superseded`) and runs a new red baseline. A
   superseded contract can never bind a completion (ASC-08).
5. Reports beside the proposals (OMO-42, VSP-04). `<task>.blocked.json` (`task`, `item`, `why`, `options`; strict shape)
   pauses the active task with reason `blocked` and the agent's uncertain item; G1 applies it at the next model call and
   at Stop before any verification. `<task>.resume.json` reactivates a task paused by a blocked report, with the contract
   unchanged; any other pause needs a superseding proposal. The projection carries the item and the resume path, so the
   next session asks the user instead of guessing. Built.

### 5.3 A known limit and its partial cure

A check that only asserts an exit code can be satisfied by a stub (ASC-04). G1 narrows this with the canary (OUR-13):
each `must_flip` check declares the files of the work it depends on. When it passes on the final tree, G1 replaces
those files with unparseable bytes in a scratch copy and runs it again. It must fail. A check that does not react to
its targets, or whose targets do not exist, fails. G1 writes canary bytes only to regular files inside the scratch
copy, reached without a symbolic link, so a link planted in the workspace cannot make G1 overwrite a file elsewhere.
Built.

What this does not prove: that the check captures the user's intent. A check such as "import the new module" is red
before, green after, and canary-sensitive, yet says little, because G1 cannot judge what a test means. Whether a human
should ratify the contract is open decision OD-1 (section 13).

Planned: restoring the pre-task test files from the baseline and running them against the final tree (OUR-14), as a
second veto. With oracle pinning in place, this adds little and is deferred.

### 5.4 Kept rules

Contract hash over immutable fields (LIFE-08), drift refusal (LIFE-10), one active task per workspace (LIFE-13, GOV-29),
terminal completion (LIFE-15/16), permanent invalidation (LIFE-26/27). Dropped: checkbox criteria (LIFE-18); a
checkbox is an agent's claim (Z4).

### 5.5 Challenges: a second model as a reviewer (built)

A model's review is a claim. G1 accepts a reviewer's finding in one form only: a contract whose `must_flip` checks fail
on the current tree because of the defect. The reviewer, typically a model of another family running in its own agy
session (Claude Opus or Sonnet reviewing Gemini's work), writes `<challenges dir>/<id>.json` with the claim and that
contract. `g1 challenges` lists the pending files, parsed but not run: id, claim, task, scope, oracles and every
check's full argv, with a mark when the task id already exists. The checks are code another model wrote and nothing
confines them under PRoot, so the user reads them first and then runs `g1 challenges --run [ID ...]`, with the user's
rights. G1 validates the shape (strict, `must_flip` only, at most 8 checks, a new challenge id, a task id no task in
the workspace has), measures the tree, runs the checks on a scratch copy, measures the tree again, and records
`challenge_recorded` with one verdict: `confirmed` (every check ran and failed), `unproven` (a check passes, or runs
longer than 60 seconds, so the defect is not shown) or `invalid` (malformed, a check that cannot start, or a tree that
changed while the checks ran, which means a check wrote outside its scratch copy). The record keeps each check's exit
code and the last 600 bytes of its output, and the listing shows them, so the user can tell a defect from a check that
fails for another reason (a missing `.git`, a scrubbed variable). Nothing becomes a contract here.

Challenge checks run only in that command, never in a hook. In a hook they ran before the working agent's next model
call: measured while preparing review round 3, three challenges with 2-second checks held a model call for 6.3 s.
Whoever asks for the verdicts waits for them. The command is the user's (section 7.3), because it records verdicts on
the tree as it is at that moment: an agent that could run it could pick a moment when a check passes.

A confirmed challenge waits for the user. The status block says how many wait; `g1 challenge ROOT ID accept` prepares
the contract (the red baseline runs again on the tree as it is then) and records the acceptance inside the
`contract_registered` record itself (`from_challenge`, `decision`): one record, so no crash between two records can
leave a challenge accepted without its contract (round 4, R4-02; round 3 had recorded two records in one lock hold,
which a SIGKILL between them defeated); when the baseline no longer fails, the decision stays open and the command
says why. `reject` records `challenge_decided` with the reason. Both record the process context the command ran from
(`run_by`). The decision is the user's because a failing check proves that a
behaviour is absent, not that the reviewer's expectation is right: in review round 1 one proposed test (Unicode
normalization) would have failed now and demanded a wrong behaviour. The agent can run neither `g1 challenges` nor `g1
challenge` (section 7.3), and the commands refuse a process the agent started (section 7.7). After acceptance the work
is ordinary: the worker model fixes, G1 verifies, the receipt completes.

Why this form: it reuses the authority path unchanged (red baseline, canary, receipt), it keeps every model off it, and
it measured well by hand in two review rounds, where a review that had to attach a reproduction produced few invented
findings (section 11).

Measured once end to end (experiment C1, `research/measure/c1/`): Flash built a SemVer library from a specification
(hidden oracle 43/44); Claude Opus 5.5 reviewed it in 73 s and filed one challenge, confirmed by G1, with a right
expectation, covering the oracle's one defect in six positions and reporting nothing false; the user accepted it; Flash
fixed it under a receipt (oracle 44/44).

## 6. Verification and completion

### 6.1 Verification (built; runs inside the Stop hook, only when the host says the agent is idle)

1. Identity before. G1 computes its own content digest of the tree (EVI-36/37; git is not used, because repository
   git settings can run agent code) and the oracle hashes. A changed oracle ends the attempt: `oracle_changed`.
2. Run every check on a scratch copy (OUR-19, ASC-23): a clean environment with an allowlisted PATH, a private HOME
   and TMPDIR (EVI-09/10/11), the executable re-hashed before it runs, a deadline (EVI-04), an output cap (RUN-21), and
   the check's own process group, which is killed on every exit path (RUN-23, ASC-24). Output is read as it arrives;
   the first byte past the cap (1 MiB per stream) stops the check, so G1's memory stays bounded whatever a check prints.
   Excluded directories (`.git`, `node_modules`, `.venv`, `venv`, caches) are not copied, so no check result can depend
   on them, and changes inside them are outside the scope check. The copy is G1's own walk, not `shutil.copytree`:
   regular files are read through descriptors opened without following links and written in a plain loop (no kernel
   copy fast path; under PRoot one gave `EINVAL` for a hard link), links are copied as links, and a FIFO, a socket, a
   device or an unreadable file is skipped and listed in the receipt as `scratch_skipped` (a FIFO opened for reading
   would hold the hook until the host's limit). Only a path the checks depend on (a target, an oracle, a workspace
   executable) that cannot be copied fails the attempt, recorded as `scratch_copy_failed`, never left as a crash.
   When the check itself exits while a child it started still holds an
   output pipe, reading stops after half a second: the exit status is the check's, and the leftover group is killed.
   A process that leaves its group with `setsid` survives the kill; there is no confinement under PRoot (OUR-49 is planned).
3. A pass needs exit 0, no timeout and untruncated output (ASC-22). G1 counts a timed-out or truncated run as a fail.
4. Canary for every passing `must_flip` check (section 5.3). A target that exists as anything but a regular file
   reached without a link fails the check (`target_not_regular`).
5. Identity after must equal identity before (EVI-42, ASC-02); otherwise `identity_changed`.
6. Changed set. G1 compares the tree with the manifest stored at contract time. A changed path outside the allowed
   set is a `scope_violation`, and so is a new or changed symbolic link whose target leaves the workspace: otherwise
   part of the work could live outside the repository behind a link while the checks pass (`links_out`).
7. Evidence for the attempt is written under `evidence/<attempt>/`, with secrets redacted first (EVI-15: Google, AWS,
   GitHub, GitLab, Slack, Hugging Face and `sk-` API keys, PEM blocks, JWTs, bearer tokens, and secret-like keys in JSON,
   Python dictionaries, YAML and assignments).
8. Receipt. `verification_started`, then `verification_succeeded` with the full result tuple, or `verification_failed`
   with a typed reason. The receipt carries the contract hash, the tree digest, the environment digest and the policy
   digest (ASC-21, ASC-05).
9. Gap check. If G1's hooks missed any mutating tool call of the task (section 7.5), the attempt fails with
   `observation_gap`. Conversations whose transcripts are gone are counted in `liveness_unknown` (section 7.5).

Planned: a second, independent enumerator of the changed set (PTH-31); recording `(boot_id, pid, start_ticks)` for
spawned processes (OUR-49); writing the confinement state into the receipt (OUR-21; there is no confinement under PRoot).

### 6.2 Completion (built)

Completion is decided in one function (OUR-01). It returns "complete" only from checks G1 executed. Every other
input, including any model opinion, is typed as a veto and can only say no. A test enumerates every combination of
veto inputs and shows that none produces approval without executed evidence. The function recomputes the summary from
the per-check results; an empty check vector is never "all pass" (OUR-03).

The task is complete when all of the following hold:

- every `must_flip` check passed with an executed flag and a sensitive canary (no `must_flip` check is exempt), and
  every `guard` passed;
- the tree digest, recomputed under the ledger lock, equals the receipt's digest (this closes a time-of-check gap the
  predecessor had);
- the oracle hashes equal the pinned set;
- the changed set is inside the allowed set;
- the gap counter is zero;
- the policy digest equals the one sealed at admission (OUR-51, ASC-05);
- the task is still active.

The completion is decided and written in one hold of the ledger lock: G1 checks that no record was appended after the
receipt, measures the tree, runs the completion function, measures the tree again, and appends the completion bound to
the receipt by compare-and-swap. If a record was appended or the tree changed in between, the task is not completed in
this turn (`concurrent_change`) and the next turn verifies again. A write to the tree after the second measurement
happens after the completion; no check can freeze a filesystem, and the next contract's base manifest includes it.
G1 measures the tree once more after the record and, if it differs, appends `post_completion_change` (an alert in the
next status block and a note in `g1 audit`), so the window is recorded even where it cannot be closed. There is no
time window in the binding itself (LIFE-36); it is by hashes alone.

## 7. Hooks (the agy adapter)

### 7.1 Output discipline (built; every line measured)

| Situation | G1 prints |
|---|---|
| PreToolUse, no opinion | nothing |
| PreToolUse, refusal | `{"decision":"deny","reason":"<one G1 fact>"}` |
| PreToolUse, internal error in a G1 workspace | a refusal naming the error (agy is fail-closed here) |
| SessionStart, PreInvocation | one `ephemeralMessage`, or nothing |
| Stop, agent not idle | `{"decision":"stop"}`; nothing else runs |
| Stop, agent idle | verification, then `stop` or `continue` by section 8 |

Why each line: `{}` counts as a refusal; `allow` can skip a native prompt; `ask` let a write run under the
skip-permissions flag; the documented `toolCall` injection crashed the run; `force_continue` has no limit and spent
180k tokens on filler. All measured; see `docs/host-agy.md`.

### 7.2 Events and their cost

| Event | Work | Measured cost |
|---|---|---|
| SessionStart | enrol the workspace if new (never one whose ledger went missing); check anchors, witness and host files; fingerprint the host; inject the state | 97 ms; 376 ms at 5,000 records |
| PreInvocation | process proposals (at most two red baselines per call, the other proposals wait for the next call: 30 proposals on a 500-file tree once held a call for 31 s, pre-round-5 review); inject a 512-byte status block | 96 ms; the block is printed whatever the proposals directory holds |
| PreToolUse (mutating tools only) | journal the call; gates | 75 ms, of which G1's own work is 5 ms; independent of ledger length |
| Stop (idle) | verification, completion, control | 0.3-1.1 s; idle with no contract 132 ms, 381 ms at 5,000 records (the chain is walked once, for the anchor check and the fold) |

Read-only tools never start a hook process: the matcher is a regular expression over the mutating tool names.

PreInvocation imports the module that runs checks only when a proposal is waiting. Before review round 3 it imported it
on every call (44 to 53 ms under PRoot), for the challenges it no longer processes. Measured in fresh processes, 30
interleaved runs each, imports plus G1's work: 107 ms before, 59 ms after; PreToolUse 46 ms both.

A proposal or challenge file is claimed before it is processed: G1 renames it to `<name>.running.json` and holds a
lock on it until the answer is written. Two hook processes never run the same file. When the host stops a hook at its
time limit (900 s for PreInvocation), the lock goes with the process, and the next call answers the file as not
finished instead of starting it again on every call. If the process stopped after its ledger record and before the
answer, the next call finds the record (same task or id, same contract hash) and answers from the ledger, so nothing
is recorded twice. Reports (blocked, resume) are claimed the same way.

G1 reads a claimed file only through the descriptor it locked, never by its name again, so the agent cannot swap the
content after the claim. It opens without following links and without blocking, and reads only a regular file of at
most 1 MiB: before this, a FIFO named like a proposal held PreInvocation until the host's time limit, on every call. An
answer goes to a new file that is renamed into place, so an entry the agent left at the answer's name is replaced,
never written through.

Measured live after this change (one Flash session, 28 model calls, G1's own journal): PreInvocation median 30.5 ms,
90th percentile 36 ms, against 69 ms and 80 ms over the last 300 calls before it. After review round 3 (one Flash
session, 38 model calls): PreInvocation median 31 ms, 90th percentile 39 ms; PreToolUse median 18 ms. After review
round 4 (two Flash sessions, 29 model calls): PreInvocation median 26 ms, 90th percentile 36 ms; PreToolUse median
11 ms, worst 22 ms; interleaved fresh-process benchmarks against the round-3 code showed no change (round 4 response).

PreToolUse and PreInvocation read `summary.json`, a small cache of the facts they need (the active scope, the projection
lines) that is valid only while its sequence number and hash equal the ledger head; otherwise they fold the ledger and
rewrite it. Completion never reads it: the Stop hook and SessionStart verify the whole chain. Measured before this
cache: a PreToolUse grew from 124 ms with an empty ledger to 429 ms at 3,000 records; with it, 122 to 126 ms over the
same range.

### 7.3 Gates before a tool call (built)

All gates are deterministic. None of them tries to understand a shell command (THR-16).

- Protected paths. A structured write (by its path argument, symbolic links resolved) is refused when the target is
  inside `~/.g1`, the global hooks file, G1's installed rule or skill, or the workspace's `.agents/hooks.json`. The one
  exception is the workspace's own proposals directory.
- Pinned oracles. With an active contract, a write to a pinned oracle file is refused (PTH-41).
- Scope. With an active contract, a structured write outside the allowed paths is refused. Without a contract there is
  no scope gate (P2).
- Textual reference. A shell command (`run_command`, `send_command_input`, `execute_notebook`) whose text names G1's
  state, its installed files or a transcript directory (`.system_generated`) is refused, and so is a command that runs
  G1's command line with any subcommand (`status` and `audit` included: the agent needs none, and refusing every
  subcommand removes the subcommand spellings round 3 found, such as `-mg1` and `$(echo repair)`). The command line
  is found by splitting the command into shell tokens and looking only at commands in command position: after
  separators, shell keywords (`{`, `then`, `do`), assignments, and wrappers (`sudo`, `env`, `exec`, `nice`, `timeout`,
  `nohup`, `uv run` and the like) together with their options and the options' arguments, so `exec -a x python3 -m
  g1` and `sudo -u root g1` are seen (round 4, R4-06); inside `sh -c`, `$(...)`, backticks and the command strings of
  `script -c`, `flock -c` and `env -S`; `python -m g1` in both spellings, a `g1.pyz` argument, `python -c` code that
  imports the package (judged on Python tokens, so a string that merely mentions `import g1` is not refused, R4-07),
  and Python code on standard input or in a here-document. A commit message or a `grep` pattern that mentions them is
  not refused, and the two relative names (`.agents/hooks.json`, `.system_generated`) are matched as path tokens, not
  inside prose. The tokenizer (`shlex`) costs about a millisecond per KB and grows faster on one long token (a 400 KB
  `echo`: 6 s), so only the first 16 KB of a command line, cut at whitespace, are tokenized; the rest is scanned by
  the linear patterns (a `g1` or `-m g1` token anywhere, Python that imports the package) and by whitespace tokens for
  the path names, coarser but bounded, so no command line an agent writes can hold a tool call (pre-round-5 review,
  P5-01: 400 KB took 1.7 to 6 s before, under 100 ms after). A shell command over 1 MiB is refused outright: a file
  written through the shell, and the only way left to approach the host's 20-second limit, after which the host would
  take the silence for consent. The agent may name its proposals, challenges and views directories only where the path stays inside
  them after normalization: `<views>/../ledger.jsonl` is refused. This is a tripwire, not a boundary: a spelling such
  as `$HOME/.g1`, a wrapper script, a module name built from pieces (`__import__('g1.' + '__main__')` is seen, but
  not every construction), or a copied archive passes it; what holds is the path gate on structured writes, the anchor
  check, the receipt, and the command line's own refusal of a process started by the agent (section 7.7).
- Transcripts. A structured write to agy's conversation store, to a conversation directory, or to anything under a
  `.system_generated` directory is refused, and so is a shell command that names the store: G1 reads transcripts as
  evidence. Artifacts the agent writes inside its conversation directory stay writable. Pinned oracle files are not
  refused in shell text: the agent must be able to run its tests, and an edit is caught by the hash check at
  verification. (The first end-to-end run showed the agent blocked from
  running its own tests; this rule was changed for that reason.)
- Lockdown. After an integrity alert, every mutating tool is refused until the user runs `g1 repair`.

The gated tool names come from the binary's step types and the analysts' tool list (an analysis of the agy binary kept outside this repository):
file writes and edits, notebook tools, deletes and moves, `run_command`, `send_command_input`, `git_commit`, package
installs, and the subagent tools. Measured: every tool call fires PreToolUse whatever its name.

Measured need for the textual gate: 8 of 8 agents tried a shell write right after a structured write was refused.

Planned: refusing irreversible publication (`git push`, tag pushes, package publishing) unless the latest receipt passed
on the current tree (PTH-37, ASC-13).

### 7.4 The pinned bootstrap (built)

agy reads the hooks file only at session start. Each G1 hook entry is a small inline Python program that contains the
hash of G1's code and exits with code 3 if the code on disk differs. A changed code file therefore stops every
PreToolUse for the rest of the session. The installer is the only writer of hook entries: it replaces only the `g1`
group, keeps every foreign entry byte for byte, and removes only its own group on uninstall (PTH-19, ASC-41, TW-a).

### 7.5 Liveness and the gap counter (built)

Every PreToolUse appends `(conversationId, transcript path, stepIdx, tool, hash of args)` to a journal (PSN-08).
Journals are append-only lines, so concurrent subagents never rewrite a shared file. At an idle Stop, G1 reads the host
transcript of every conversation in the journal (subagents included), counts the mutating tool calls the model made,
and compares the count with the journal. A difference is a gap (ASC-15). A gap refuses completion. The gates stay
active regardless. A conversation journaled during the task whose transcript is gone cannot be counted: it is
reported in the receipt as `liveness_unknown` and shown in the status block, never counted as zero. It does not refuse
completion, because a deleted session must not stop a fresh agent from continuing (the two-way test, principles A2;
measured in run 5). The agent's own tools cannot delete transcripts, and a shell command that names the store is
refused (section 7.3). The count stays visible after completion: in `g1 status`, in the status block's `last complete`
line and as a note in `g1 audit`. Every tool call observed so far is its own step (1,317 hook calls, no planner response with two
tool calls); if two calls ever shared a step index, the count would show a gap and completion would be refused, which
is the safe direction.

Measured while building: with two hook layers, a call refused by the first layer never reached the second, so the
layers' journals disagreed. G1 now installs one layer. (A payload-shape tripwire, ASC-44, is planned.)

### 7.6 Anchors, mirror, self-heal (built)

- Every commit writes two things outside the workspace's directory: the anchor (keyed by the ledger id, the head G1
  last wrote) and the mirror (a copy of the ledger). The genesis commit and the first record after it also write the
  witness, keyed by the workspace: which ledger lives here and that it had a record after genesis. An ordinary commit
  does not pay for it (measured: a witness written at every commit cost 3.5 ms per append under PRoot).
- At every SessionStart and before every verification at Stop, under the ledger lock, the head must equal the anchor,
  and the ledger id must equal the witness's. The mirror must then be byte-identical to the ledger; any difference, a
  corrupt middle record included, rewrites the mirror from the anchored ledger. A missing anchor is accepted only for
  a ledger that holds nothing but its genesis record while neither the mirror nor the witness remembers more; G1
  writes the anchor in every commit, so a ledger with records and no anchor, a ledger cut back to its genesis record,
  or a ledger replaced by a fresh one is diverged (round 3, R3-01 and R3-02). A ledger behind its anchor lost records:
  they are restored from the mirror, together with the head, and the repair is recorded. A ledger ahead of its anchor,
  or different from it, was changed outside G1: the workspace is locked down without writing to the ledger, so the
  evidence stays as found, and no verification or completion runs (THR-09). A workspace whose ledger files are gone
  while its witness remains is locked down at SessionStart instead of being enrolled again. The user inspects
  (`g1 audit`, `g1 repair`) and decides: `--accept-ledger` (the current ledger is the truth, `accepted_by_user`),
  `--restore` (rebuild it from the mirror, `restored_by_user`) or `--forget` (a lost or unreadable ledger: start
  over). Each is recorded with the process context it ran from. No state is a dead end (round 4, R4-01): a ledger
  that no longer reads as a chain (a corrupt byte) cannot be accepted, but `--restore` rebuilds it from the mirror of
  the ledger the witness names, which must extend the readable prefix of the current file, and `--forget` moves the
  files aside under the workspace's state directory (never deletes them) and drops the witness. The witness, not the
  head file, says which mirror is this workspace's: a ledger copied in from another workspace brings its own head,
  and restoring from that head's mirror would have adopted the foreign ledger. A restore is bounded by the anchor:
  G1 writes the mirror after the anchor in every commit, so a mirror with records beyond the anchor's seq was
  extended by someone else, and those records are not restored (the user is told, and the restore record says so); a
  mirror whose record at the anchor's seq, or at the witness's, is not the one they name is refused as not G1's copy
  (pre-round-5 review, P5-03: before this, forged records appended to the mirror came back through `--restore` as a
  clean completion). Without a readable anchor nothing bounds the mirror, and the restore says that too.
- At every SessionStart G1 re-hashes the hook entries, the rule and the skill against its manifest, and rewrites any
  that changed (KEV-31, PSN-26).
- At every SessionStart G1 fingerprints the agy binary. A change records `host_contract_observed: unverified`, injects
  an alert and withholds completion until `g1 host-verify` records the new binary (PTH-21).

### 7.7 Residual risk

All of G1 runs as the same OS user as the agent. An agent with shell access could, in principle, rewrite every G1
file, anchor, witness, mirror and manifest consistently within one session. G1's decision commands (`repair`,
`challenge`, `challenges --run`, `install`, `uninstall`, `init`, `propose`, `turn-end`, `host-verify`) refuse to run
when the host agent is among the ancestors of their process (measured: a command the agent runs has `agy` itself as
its parent process), and record the process chain they ran from (`run_by`); a process that leaves the tree (a double
fork reparented to init) or a copied archive under another name is not seen by the textual gate, but still meets this
check unless it also leaves the process tree. When the parent process cannot be read at all (no `/proc`), the
ancestry is unknown and the commands refuse: unknown counts as the agent (round 4, R4-04); an ancestor further up that
cannot be read (another user's process under `hidepid`) ends the recorded chain with `?`, and the readable part
decides. Every acceptance is recorded (`accepted_by_user`, `restored_by_user`, a challenge's `decision`) and shown in
the next status block, so it is visible where it is not prevented. G1 detects partial tampering and all tampering through structured tools. Removing
G1 never creates a false completion (Z5). A full defence needs an OS boundary that this environment (Termux with
PRoot) does not provide. Signing would add trust only with a key outside the agent's user (PTH-18; ASC-09 rejected).

## 8. The Stop policy (built)

After verification, G1 must decide: let the agent stop, or ask for one more turn. The decision is a pure function of
the ledger (ASC-26).

- Each attempt gives a pass/fail vector over the contract's checks (unknown counts as fail). All passing means
  completion (section 6.2). An all-pass vector never invents more work (PTH-25).
- Tree unchanged since the last attempt: no new verification; the task is paused with reason `no_change`.
- `continue` only when the set of failing checks is a strict subset of the previous failing set (ASC-27) and the
  continuation counter, written before the answer is printed and never decreased (ASC-31), is below the budget. The
  default budget is 3 per task, well under agy's own limit of 10 per session.
- No shrink, or a revisit of a tree-and-vector pair seen before (RUN-18, ASC-30), or a period-two alternation of vectors
  (OUR-39): paused with `no_progress` or `oscillation`.
- A verification that could not run (oracle changed, identity changed, no space, missing executable, observation gap)
  is `environment_unknown` (ASC-33). It counts neither as progress nor as failure.
- The `continue` reason is one line built only from G1's own fields: the next failing check and its exact command
  (PTH-39, OUR-09). Raw check output is never echoed.
- Model text never selects a control action (OUR-56).
- Never for a paused task, without an active contract, or while the host reports the agent as not idle.
- A blocked report written during the turn (section 5.2, item 5) is applied before verification, so an agent that
  stopped on an uncertain item is never asked to continue.

Planned: the budget sealed into the contract at admission (OUR-40).

Paused reasons, all recorded in the ledger: `no_change`, `no_progress`, `oscillation`, `budget_exhausted`,
`scope_violation`, `environment_unknown`, `completion_refused`, `blocked`.

## 9. The projection (built)

The projection is the status block G1 injects: a budget of 1,024 bytes at session start and 512 bytes before each model
call, within which lines are kept whole or left out by priority, never cut mid-line (KEV-21). It is built from the ledger only: the
active contract and its hash, the pass/fail vector, the failing checks, the scope, the pinned oracles, the paused
reason, any alert or lockdown, and the proposals directory for this workspace. Text that an agent wrote (the objective,
a blocked item) is printed as a quoted JSON string with newlines escaped, so it can never look like a G1 line (KEV-22).
The projection states facts and asks the model for nothing (KEV-39). It writes only G1's own cache (`summary.json`,
section 7.2) and is fail-open by host design; the hard guarantees come from the gates and the receipts. Its lines carry
priorities: the facts the agent must act on (the task, the check state, the scope, the liveness count, the resume
instruction, any alert) are always kept, and agent-written text (the objective, a blocked item, the open check's
command, the options) is added only while it fits, each capped by bytes after escaping, so a 600-character objective,
a 300-character blocked item or a Korean objective never pushes out the scope line (round 3, R3-12). The lines that
are always kept are bounded where they are built: a list of check ids or of paths is cut with a count of the rest
(`['K00', 'K01', +62 more]`), and the lockdown reason, the blocked item and the task id have their own caps. When those
lines alone exceed the budget, the block is them and nothing else, and it runs over the budget rather than lose one
of them (round 4, R4-09): measured worst case, every alert at once (lockdown, a repair alert, an unverified host,
waiting challenges, unknown liveness) with a 64-check contract of 256 long paths, 1,170 bytes per model call and
1,664 at session start; without a contract, 1,145 and 1,287. An ordinary block stays well inside the budget.

The projection also names the first check that does not pass yet and its command (160 characters per model call, 600
at session start), and at session start the challenge claim and the path of `views/contract.json`, the whole active
contract. An agent that did not write the contract (a fresh session, a contract from a challenge or the command line)
otherwise sees only an objective. Measured (C1, 3 pairs): with the command shown, the same fix took 55k fewer tokens
[-120k, -12k] and 86 s less [-129, -38], with the same outcome.

The wording of the projection was A/B tested (run 4): removing the completion lines changed nothing measurable, so the
current wording stays.

### 9.1 Installed rules (built)

G1 installs five rule files and one skill into the host's configuration root, hash-pinned in the manifest, refused to
the agent's file tools, and restored at every SessionStart (section 7.6). They are G1's own text, designed from the
"Gemini taming" post series (atoms VSP-01 to VSP-14, `research/atoms/ext/vesperchant.json`) and from G1's
measurements, and they follow four rules of their own:

1. A rule is a sentence the agent can obey or violate observably, with an id (`E2.3`, `I2`, `W2.1`) for citation.
2. Every rule names its enforcement: `[gate]` (a hook refuses), `[receipt]` (decided at verification), `[ledger]`
   (recorded, found by audit) or `[self]` (the agent's discipline, visible to the user). The series claimed
   "mechanically enforced via 3-tier hooks" without showing the hooks; G1 says exactly which hook does what.
3. Load follows use: `g1` (5.9 KB) and `g1-instinct` (7.3 KB) are `always_on`; `g1-work`, `g1-writing` and
   `g1-korean` are `model_decision` rules whose descriptions say when to read them, and `g1.md` repeats that index.
   No file exceeds 10,000 characters, so each enters the context whole (VSP-03; the host caps a rule at 24,000 bytes).
4. Rules point at mechanics: the proposal, the red baseline, the blocked and resume reports, the refusal, the receipt.

| File | Trigger | Holds |
|---|---|---|
| `rules/g1.md` | always on | what G1 is; order of authority (user, G1 facts, G1 rules, project rules, data); five duties; mechanics; index of the other rules |
| `rules/g1-instinct.md` | always on | terms (primary source, uncertain item); the two paths and the forbidden third; what is not uncertain; the blocked report; authority by channel with examples; workspace; claims and evidence; the final reply |
| `rules/g1-work.md` | on demand | proposal craft; shell discipline (one command per call, file tools for edits); code; dependencies with four confirmations; tests and oracles; commits; the finishing checklist |
| `rules/g1-writing.md` | on demand | lead with the outcome; facts with conditions; formatting; naming; machine prose removed; language |
| `rules/g1-korean.md` | on demand, in Korean | structure, translationese, AI clichés, rhythm, register, the pre-output check |
| `skills/g1/SKILL.md` | skill | the proposal format field by field; blocked and resume reports; what G1 does at Stop; what does not work |

What the series had and G1 left out, with the reason: a judge model at Stop (VSP-07; a model's opinion is not evidence,
KEV-02); an `ask` risk gate (VSP-09; measured no gate under the skip-permissions flag); agent-written records (VSP-10;
an agent's record is a claim, P3; the ledger is the record); bilingual replies (doubles output for no measured gain);
"make at least one mistake" (VSP-11; no evidence; a prompt trick, PH).

Cost: the always-on pair is 13.6 KB, about 3,300 tokens per session, cached by the host; no hook time. Effect: run 6
(`research/measure/ab6/`) put the instinct rule against six ambiguous, contradictory or impossible tasks. Flash at
effort high stopped and asked in 12 of 12 sessions with the rule and 12 of 12 without it, with no guess and no false
DONE, so the rule's behavioural effect is not measurable on that class; the token difference (−21.7k at the paired
mean) has an interval that includes zero. The rule is kept for the cases that run does not reach, and its effect
there remains unmeasured.

## 10. Measurement

Nothing in this section can approve or refuse anything. It exists to answer "did G1 help?" with numbers.

- Host-contract probes (`research/agy-hooks/`): one scripted probe per measured fact (KEV-27). The host fingerprint
  at SessionStart decides when they must be run again. Built.
- A/B runner (`research/measure/ab.py`): fixture repositories with a stub and a failing test; two arms per fixture and
  repeat; the same prompt in both arms; seeded interleaved order. Outcomes are computed by the runner only: pass means
  the fixture's original test bytes exit 0 on the final tree; claim means the final reply starts with DONE; tokens, wall
  seconds and tool calls come from agy's output. Rates carry Wilson 95% intervals; differences use a paired bootstrap
  over fixture-repeat pairs (KEV-04, ASC-51). G1's own verdict is reported beside the oracle, never used as the outcome. Built.
- Resume runner (`research/measure/ab_resume.py`): session 1 is cut early, its agy records are deleted, session 2 is
  told only to continue. Built.
- Results (all on gemini-3.8-flash-high, agy 1.3.3; details in `research/measure/*/RESULTS.md`):

| Run | Question | Result |
|---|---|---|
| 1 | Easy tasks, one session | 8 pairs. Pass 8/8 in both arms. With G1: −31k tokens [−51k, −12k], −10.6 s. |
| 2 | Harder tasks | 12 pairs. Pass 12/12 both. With G1: −21.6k tokens [−34.9k, −8.7k], −19 s. |
| 3 | Strict tasks | 10 pairs. Pass 10/10 both. No cost difference (intervals include zero). |
| 4 | Projection wording | 10 pairs. No measurable difference. Current wording kept. |
| 5 | Resume after a lost session | 6 pairs. Both arms resumed 6/6. With G1: −39% tokens, 14 vs 33 tool calls. |
| 6 | The instinct rule on ambiguous tasks | 12 pairs. Stopped and asked 12/12 in both arms; no guess, no false DONE. Tokens −21.7k [−49.9k, +5.4k]. |
| C1 | Challenges: Flash builds, Opus proves a defect, the user decides, Flash fixes | Oracle 43/44 → 44/44; 1 challenge, confirmed, right expectation, no false report. Showing the open check's command in the fix: −55k tokens [−120k, −12k], −86 s (3 pairs). |

Across all runs: G1's verdict agreed with the independent oracle in 46 of 46 sessions. Gemini 3.8 Flash did not fail
or lie on any of these self-contained tasks, so a correctness effect is not measurable on this task class.

Planned measurement machinery: pre-registered specs with pass/fail/incomplete verdicts (KEV-05), sample-size planning
(KEV-10), withheld-evidence twins (KEV-11), placebo arms (KEV-34), an isolation canary (KEV-36), execution fingerprints
on every measurement receipt (KEV-17).

## 11. Audit and self-tests

Built:

- `g1 audit` (RUN-41): re-derives the chain, every receipt and every completion from the ledger and evidence, and
  reports a compacted attempt as compacted, which is not a finding.
- The approval-authority test (OUR-01): no combination of veto inputs approves without executed evidence.
- Tests for chain breaks, crash recovery at every journal state (including an append cut mid-line), compare-and-swap
  conflicts, the coverage matrix, targets, scope and traversal rejection, the red baseline, the canary (including a
  symbolic-link target), oracle edits, scope violations (including an empty directory), the Stop policy, the PreToolUse
  output set, the matcher and the tool list, auto-enrolment, evidence compaction, host-change detection, the installed
  host files, the blocked and resume reports, anchor repair and lockdown, the head-bound summary, the append-only gap
  journal, quoted agent text, bounded check output, redaction, hook input that is not a JSON object, foreign host hook
  entries, the refusal of G1's decision commands, the absence of host names in the core, every round-2 finding, challenges, the open-check line of the status block, the claims on proposal, report and challenge files, how agent files are read, every round-3 finding, every round-4 finding, every finding of the pre-audit before round 5, and two of the fifth review's suggestions (126 tests). The suite patches the process ancestry G1's decision commands measure, so it passes when a reviewer runs it inside an agy session (round 4, R4-05).
- Two-way tests in practice: uninstall removes only G1's entries (TW-a); a fresh session completed a contract from
  G1's records after the agy records were deleted (TW-b, runs 2b and 5).

- Independent review: an agy session (Gemini 3.8 Flash, effort high) reviewed the code with a written brief and
  reported 16 findings; 15 were confirmed by reproduction and fixed, one (Unicode normalization) was answered as by
  design, and three further defects were found while verifying them. Each finding, its reproduction and its fix are in
  `research/review/round-1/`. A second review of the fixed code reported 12 findings: all reproduced, 11 fixed, one
  (a deleted transcript) answered in part because the fix it proposed would break the two-way test
  (`research/review/round-2/`). A third review reported 24 findings (4 critical: a deleted or truncated ledger
  accepted silently, the agent's own directories opening a path to the ledger, spellings of the decision commands):
  all reproduced, 23 fixed, one (the linear cost of SessionStart and Stop in ledger length) bounded and left to the
  planned checkpoints (`research/review/round-3/`). A fourth review reported 9 findings (2 critical: a corrupt ledger
  that no repair flag accepted, and a challenge acceptance recorded as two records that a crash between them split):
  all reproduced with the reviewer's own scripts and fixed, each with a test named after it; the two spellings it
  listed as remaining bypasses are a copied archive, which the ancestry guard still refuses, and a line that is not
  valid Python (`research/review/round-4/`). Before the fifth review, two fresh reviewers of other families (Claude
  Opus 5.5 and Claude Fable 5.1) read the round-4 code outside any agy session, after every earlier reviewer's script
  had been rerun on it: 7 findings (no critical; 3 high, all the speed rule: the textual gate's tokenizer was
  quadratic in command-line length, and one model call validated every pending proposal; 2 medium: a chmod by path,
  a restore not bounded by the anchor; 2 low), all fixed with tests, plus one defect the author found while probing
  (`research/review/round-5/pre/`). The fifth review (an agy session, Gemini 3.8 Flash, on that code) reproduced
  every round-4 and pre-audit fix with its own scripts, attacked the code added since round 4 and the whole again,
  measured the hooks, and reported no finding at any severity; its ten suggested tests were answered one by one and
  two of them added (`research/review/round-5/`).

Planned: a negative-control fixture per gate (PTH-14), a mutation suite on the authority path (KEV-15, ASC-55),
minimal pairs (KEV-13), differential replay of recorded hook inputs across versions (KEV-30), regression fixtures from
observed failure classes (PTH-35).

## 12. Governing native orchestration (planned)

Measured: subagents run the same hooks under their own conversation id, and the parent's Stop reports "not idle" while
a child runs. A parent that delegated the whole task to a subagent reached completion with no gap (run E2E 3b).

Principle: G1 builds no scheduler and no task graph engine (P2). We examined a graph engine (oh-my-openagent, 60
atoms) and rejected it as an engine, because its node completion equals the child's self-report (OMO-11). G1 governs
native orchestration at the two points it controls: the spawn, and completion.

Planned, at the contract level only: dependencies between contracts with deterministic cycle rejection (OMO-01);
Merkle receipt keys so that a changed upstream invalidates every dependent receipt (OMO-05); derived "blocked by failed
upstream" states (OMO-08/10); one admission gate for every spawn surface (OMO-18); per-lane write scopes (OMO-16);
in-place contract changes only when they strengthen (OMO-35). Today, with one active contract per workspace,
registration already refuses a contract whose declared dependencies lack receipts.

## 13. Open decisions

- OD-1 Contract ratification. A: the user ratifies before activation. B: automatic on machine checks (what runs
  today). C: automatic activation; the user approves only weakening changes and the final "complete" label. D: intent
  coverage: every sentence of the user's request must be quoted by a criterion with a check, or listed as an exemption
  with a reason; a sentence with neither rejects the contract. The mechanism supports all four.
- OD-2 Continuation budget. Default 3 per task.
- OD-3 Terminal sandbox. Under PRoot it fails and doubles every shell call. Disabling it is the user's setting.
- OD-4 Workspace hook layer. Resolved: one layer, the global one.
- OD-5 Contract dependencies. Proposed yes, at contract level only; no scheduler.
- OD-6 Contract-first. Refuse mutating tools while no contract is active (OMO-57). It forces direction first, but
  blocks quick edits. To be decided by measurement.

## 14. Implementation status (v0.1)

Built and installed: everything marked built above, in about 4,600 lines of standard-library Python, 126 tests,
exercised in 128 real agy sessions, five independent reviews (the fifth without a finding) and a pre-audit by two
more reviewers. Decisions taken while building, each from a measurement:

- One hook layer, four events, a matcher over mutating tools only, a bytecode-only archive. Reason: speed. The user's
  rule was that G1 must never slow the model down; a PreToolUse now costs 75 ms, a read-only call nothing.
- Zero-touch install: hooks, rule and skill installed by one command and restored at every session start; workspaces
  enrol themselves; nothing is written into projects. Verified in a never-enrolled project with a prompt that did not
  mention G1: the agent quoted the rule, wrote the proposal to the injected path, and G1 completed the task.
- Pinned oracle files are not refused in shell text, so the agent can run its tests.
- Evidence compaction; host-change detection; `g1 host-verify`.
- Five installed rules and one skill (section 9.1), shipped as package data and self-healed; the blocked and resume
  reports (section 5.2, item 5) that make a stop on an uncertain item survive the session.

Not built: everything marked planned above, in particular contract dependencies and spawn admission (section 12),
the `BLOCKED` declaration, OD-1 modes other than B, OD-6, and harder measurement tasks that Gemini fails.

## Appendix A. Atom traceability

- Predecessor (T1) atoms kept: the LED, LIFE, EVI, RUN and GOV identifiers named in the sections above.
- ouroboros: OUR-01/02/03/07/08/09/12/13/14/19/20/21/22/23/25/38/39/40/45/46/49/51/56/58.
- oh-my-openagent (ideas only; its licence does not allow code reuse): OMO-01/02/03/05/08/09/10/14/16/17/18/19/21/22/26/27/28/33/35/36/37/40/42/49/50/51/55/56/57.
- anti-samcheonpo: ASC-02/03/05/06/07/08/11/12/13/15/16/17/19/21/22/24/26/27/28/30/31/33/34/37/38/41/44/45/50/51/52/53/54/55/57.
- kev: KEV-04/05/06/08/10/11/13/15/16/17/18/20/21/22/23/26/27/29/30/31/32/34/36/39/45.
- paperthin: PTH-09/10/11/12/14/15/16/19/21/25/26/29/30/31/33/35/37/38/39/40/41/43/44.
- polysona: PSN-08/09/13/15/21/26.
- vesperchant (Threads series, ideas only): VSP-03/04/05/06 adopted, VSP-01/02/07/08/10/12 adapted, VSP-09 rejected,
  VSP-11/13/14 research.
- Rejected, with the reason in the catalog: judge models and local classifiers as gates (KEV-02, ASC-61), majority votes
  (PTH-34, OUR-05), model-scored interview gates (OUR-31/33), model-authored certifying checks (OUR-43), generational
  spec rewriting (OUR-36), unverified-success fallbacks (OUR-16), node completion by child self-report (OMO-11),
  agent-asserted evidence records (OMO-31/32/43), keyword anti-weakening regex (OMO-34), time-based evidence pruning
  (OMO-27 part), heuristic shell classification as authority (ASC-62), a same-user HMAC key (ASC-09), a resident daemon
  (ASC-64), persona and prompt-module content (PSN-*, PTH-01/42/45-60), wall-clock throttles (PTH-06).
