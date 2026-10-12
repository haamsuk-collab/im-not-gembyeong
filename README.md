# im-not-gembyeong

제미나이, 더 이상 젬병이 아니(고 싶)다.

*Gembyeong* (젬병) is Korean for "hopeless at it", and it happens to rhyme with Gemini. Gemini, show the receipt.

Korean version: [README.ko.md](README.ko.md)

In the code, the commands and the docs, the program is called G1. That's a pun too: one g, the gravity that
Antigravity does without. G1 is a small program that runs beside the Antigravity CLI (`agy`) while Gemini works on your
code. It does two things. When the agent says it's done, G1 checks whether that's true. And when the session ends, G1
keeps the state of the work so the next session doesn't start from nothing. It's about 4,700 lines of standard-library
Python (`wc -l`), has no dependencies, and never writes into your project folders.

You install it once. From then on it works in every project without you doing anything.

## The problem

"Done. The tests pass."

There are two ways that sentence can be wrong, and we measured both. With tool calls deliberately blocked, Gemini 3.8
Flash still answered "DONE" in 3 of 8 runs, having done nothing at all (`research/agy-hooks/`). And when a session
ends, the agent's memory ends with it. The next session doesn't know what was done, what's left, or what "done" was
even supposed to mean.

An agent declaring itself done is a student grading their own exam. G1 takes the grading away from the student. It
collects the definition of done before the work starts, runs the checks itself, and writes the result into a record
nobody can edit.

## Four terms

| Term | In the code |
|---|---|
| **contract** | The definition of "done", written before the work: objective, criteria, checks, the paths the agent may edit (`allowed_paths`), the files the checks read (`oracle_files`). Stored whole in a `contract_registered` ledger record. |
| **receipt** | A `verification_succeeded` record: the checks G1 ran itself, their exit codes, the tree digest, the environment digest, the list of changed files. Completion binds to this record's sequence number and hash. |
| **ledger** | An append-only JSONL file where every record carries the SHA-256 of the one before it, so a single edited line shows. Lives under `~/.g1/workspaces/<id>/`. |
| **projection** | The short status block G1 injects into the model's context: 1,024 bytes at session start, 512 bytes before each model call, built from the ledger alone. |

Everything else in G1 exists to produce or protect one of these four.

## Where it plugs in

`agy` runs the agent in a loop: call the model, run the tools it asked for, repeat, stop. At fixed points in that loop
it can run an external command, which gets a JSON payload on stdin and answers with JSON on stdout. Those points are
hooks. G1 registers four of them in `~/.gemini/config/hooks.json`, under a group called `g1`:

| Event | When | What G1 does | Time limit |
|---|---|---|---|
| `SessionStart` | once per conversation, subagents included | enrols the project if it's new, checks the ledger against its anchor, checks that the `agy` binary hasn't changed, restores its own rule files if they were tampered with, injects the status block | 30 s |
| `PreInvocation` | right before each model call | validates waiting proposals (at most two red baselines per call), applies blocked and resume reports, injects a 512-byte status block | 900 s |
| `PreToolUse` | right before a mutating tool runs | journals the call; refuses writes to G1's own files, to transcripts, to pinned oracle files and outside the scope; refuses shell commands that touch G1's state or run G1's command line | 20 s |
| `Stop` | when the agent goes idle | runs the contract's checks on a copy of the code, runs the canary, compares the tree, writes the receipt, then decides: complete, one more turn, or pause | 1800 s |

The `PreToolUse` entry has a regex matcher that only selects mutating tools (`write_to_file`, `replace_file_content`,
`run_command`, `invoke_subagent` and so on). Reading a file or searching never starts G1 at all, so reads are free.

Each hook entry is a short inline Python program. It hashes `~/.g1/g1.pyz`, compares the hash with the value pinned at
install time, and exits with code 3 if they differ. So if anyone touches G1's code, G1 simply stops running for the rest
of the session. Since `agy` treats a failing `PreToolUse` as a refusal, that means every mutating tool is blocked until
G1 is reinstalled. We measured this and left it that way on purpose.

## Following one task from start to finish

The project has a broken `median()` and a test that fails because of it. The user says "Make `tests/test_stats.py`
pass by fixing `src/stats.py`" and nothing else. Nobody brings up G1.

1. **Session start.** G1 has never seen this project. It creates a ledger with a single genesis record under
   `~/.g1/workspaces/<sha256 of the path>/` and injects: *No active contract. For durable work, write a proposal to
   `.../proposals/<id>.json`.* The format is in `views/PROPOSAL_FORMAT.md` and in the installed skill.

2. **Proposal.** The agent writes one JSON file:

   ```json
   {
     "task": "fix-median",
     "objective": "median() returns the middle value for odd-length lists",
     "criteria": [{"id": "C1", "text": "tests in tests/test_stats.py pass"}],
     "checks": [{"id": "K1", "argv": ["python3", "-m", "pytest", "tests/test_stats.py", "-q"],
                 "kind": "must_flip", "covers": ["C1"], "targets": ["src/stats.py"], "timeout_s": 120}],
     "allowed_paths": ["src/"],
     "oracle_files": ["tests/test_stats.py"]
   }
   ```

3. **Validation, right before the next model call.** G1 renames the file to `fix-median.running.json`, takes a lock on
   it, and from then on reads it only through that descriptor. It never opens it by name again, so the agent can't swap
   the content underneath. Then it checks, in this order:
   - Shape. Strictly. One unknown key rejects the whole proposal. Ids match `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, text is
     at most 600 characters, there are at most 64 checks, and paths are relative, never `.` and never `..`.
   - Coverage. Every criterion needs at least one check, and every check has to cover at least one criterion. A
     criterion only a human could confirm has no check, so it's rejected.
   - Targets. Every `must_flip` check lists the files it depends on. They have to be inside `allowed_paths` and must
     not be oracle files.
   - State. No other contract is active in this project, and every task in `depends_on` already has a completion
     receipt.
   - Pins. The SHA-256 of each oracle file and of each executable the checks call. `python3` is looked up on a
     scrubbed PATH, not the agent's.
   - **Red baseline.** G1 copies the tree to `~/.g1/scratch/baseline-*/tree` and runs every check there. A `must_flip`
     check has to fail at this point. A check that already passes before the work can't prove anything about the work,
     so it's rejected. A `guard` check has to pass now and again when the work is done.
   - Base manifest. A listing of the whole tree with each file's hash, mode and size, saved so G1 can tell later which
     files changed.

   The answer lands next to the proposal as `fix-median.accepted.json` or `fix-median.rejected.json`, with typed
   reasons. On acceptance the ledger gets a `contract_registered` record holding the contract, the baseline results,
   the oracle hashes, the executable hashes and the tree digest.

4. **Work.** The agent edits `src/stats.py` and runs the tests as often as it wants. If it tries to edit
   `tests/test_stats.py` with a file tool, `PreToolUse` refuses with "G1 pinned oracle". If it touches `README.md`, the
   refusal says "G1 scope". If it runs `sed -i` on the test file from the shell, G1 lets that through on purpose,
   because the agent has to be able to run its tests. The edit gets caught later, by hash.

5. **Stop.** `agy` reports `fullyIdle: true`, and G1 goes to work:
   - It checks the ledger's last record (the head) against the anchor. If they disagree, it locks the project down
     and stops here.
   - It compares the oracle file hashes with the pinned values. A difference ends the attempt as `oracle_changed`.
   - It counts the mutating tool calls in the host's transcripts and compares the count with its own journal
     (`observation_gap`).
   - It re-hashes the executables (`executable_changed`).
   - It copies the tree to a scratch folder, leaving out `.git`, `node_modules`, `.venv` and the like, with a private
     HOME and TMPDIR, an allowlisted PATH, `LANG=C.UTF-8` and `PYTHONHASHSEED=0`.
   - It runs every check in that copy, each in its own process group with a deadline and a 1 MiB cap per output
     stream. Exit code 0 with no timeout and no truncated output counts as a pass.
   - It runs the **canary**. For each passing `must_flip` check it makes another copy, overwrites that check's target
     files with unparseable bytes, and runs the check again. This time it has to fail. A check that still passes with
     the code destroyed isn't testing the code.
   - It hashes the tree again. The hash has to match the one from before the checks (`identity_changed`).
   - It compares the tree with the base manifest. Here only `src/stats.py` changed. A changed file outside
     `allowed_paths`, or a new symbolic link pointing out of the project, is a `scope_violation`.
   - It writes the evidence to `evidence/<attempt>/results.json`, scrubbing API keys, PEM blocks, JWTs and bearer
     tokens first.
   - It appends `verification_started` and `verification_succeeded` to the ledger.

6. **Completion, inside one lock.** Holding the ledger lock, G1 checks that nothing was appended after the receipt,
   hashes the tree, calls `complete.approve()`, hashes the tree again, and appends `task_status_changed: complete`
   bound to the receipt with a compare-and-swap on the head. If anything moved in between, the task isn't completed
   this turn and the next turn verifies again. After writing the record it hashes the tree once more. A write in that
   tiny window can't be prevented, but it's recorded as `post_completion_change` and shown in the status block.

7. The agent's final message was "I have updated median". That sentence never went into any of the steps above.

## The completion function

`complete.approve()` is a single function, and it's the only place a "complete" verdict can come from. It approves
only when all of this holds:

- every check actually ran and passed, and every `must_flip` check has a sensitive canary;
- the receipt covers every check in the contract (an empty result set is never "all pass");
- the tree digest right now equals the one in the receipt;
- the receipt's contract hash equals the task's;
- the oracle file hashes equal the pinned values;
- the policy digest (G1's version, code hash and hook group hash) equals the one sealed when the contract was
  registered;
- every changed file is inside the allowed paths;
- the observation gap is zero;
- the task is still active.

Everything else is a veto only. Another input can add a reason to refuse, but nothing can add an approval. One test
runs every combination of veto inputs and confirms that none of them approves without executed evidence. A model's
opinion, including the agent's own summary, isn't an input to this function at all.

## When the checks don't pass

Now G1 has to decide whether to let the agent stop or ask for one more turn. `control.decide()` makes that call, and
it's a pure function of the ledger:

| Situation | Decision |
|---|---|
| the tree hasn't changed since the last failing attempt | pause, `no_change`; no verification runs |
| verification couldn't run at all (an oracle changed, disk full, executable missing, observation gap) | stop, `environment_unknown`; counts as neither progress nor failure |
| something outside the scope was changed | pause, `scope_violation` |
| this tree and result were seen before, or the results keep flipping between two states | pause, `oscillation` |
| three continuations already on this task | pause, `budget_exhausted` |
| the set of failing checks didn't shrink | pause, `no_progress` |
| otherwise | `continue`, with one line: how many checks pass, the next failing check, and its exact command |

The continuation count is written to the ledger before the answer goes out, and it never goes down. The checks' raw
output is never shown to the model. `agy` itself allows ten continues per session; G1 uses at most three per task,
because when we forced ten, the run burned 26 times the tokens of a single answer and produced nothing of substance.

A paused task isn't dead. A new proposal with the same task id takes a fresh red baseline and replaces the old
contract. A task the agent paused itself with `<task>.blocked.json` (one item it couldn't confirm, why, options)
resumes with `<task>.resume.json` under the same contract. The question travels in the next session's status block, so
a fresh agent asks the user instead of guessing.

## Why the record can be trusted

**The chain.** A record looks like `{"schema", "seq", "prev", "ts", "event", "data", "hash"}`. It's serialized
canonically (UTF-8, sorted keys, no floats, no duplicate keys, no trailing data) and hashed with a domain prefix.
Change one byte anywhere and every hash after it stops matching. `g1 audit` walks the whole chain, recomputes each
receipt's verdict from its per-check results, re-runs the completion function on each completion, and flags any stored
verdict that's more generous than its evidence.

**The commit.** Holding a lock (`flock`, 10-second timeout, inode re-check), in this order: write the record to
`ledger.pending.json` first, append it to the ledger, move the head, move the anchor, append it to the mirror, delete
the pending file. If the process dies at any step, the next open finishes or discards the commit from the pending
file. A record cut off mid-line is completed from the pending bytes. Committed bytes are never removed.

**Anchor, mirror, witness.** Outside the project's ledger folder, G1 keeps three more things: the anchor (the last
head it wrote, `~/.g1/anchors/<ledger_id>.head`), the mirror (a copy of every record,
`~/.g1/mirror/<ledger_id>.jsonl`), and the witness (which ledger belongs to this project,
`~/.g1/anchors/ws/<id>.json`). At every session start and before every verification, the head has to match the anchor.
A ledger behind its anchor has lost records; they come back from the mirror, and the repair itself is recorded. A ledger
ahead of its anchor, or different from it, was changed by something other than G1. The project is locked down, every
mutating tool is refused, and G1 waits for the user to pick `g1 repair --accept-ledger`, `--restore` or `--forget`. A
restore only goes as far as the anchor, so records someone sneaked into the mirror never come back as real history.

**Self-protection.** The hooks pin the code hash, as described above. At every session start G1 compares its five rule
files and the skill against its manifest and restores anything that changed. It also fingerprints the `agy` binary
(size plus the first and last MiB). If the binary changed, G1 records `host_contract_observed: unverified` and withholds
completion until the user re-runs the probes and runs `g1 host-verify`. G1's decision commands (`install`,
`uninstall`, `init`, `propose`, `turn-end`, `host-verify`, `repair`, `challenge`, `challenges --run`) read `/proc` and
refuse to run if `agy` is among their ancestor processes. If `/proc` can't be read, they assume the caller is the
agent.

**The agent's words.** G1 reads the host's transcript for exactly one reason: to count the model's mutating tool calls
and compare that with what its own hooks journaled. A mismatch is a gap, and a gap refuses completion. If a transcript
is gone entirely, the receipt and the status block say `liveness_unknown`, but completion isn't refused, because a
deleted session shouldn't stop a fresh agent from carrying on.

## The gates, and the one thing they let through

Every gate is deterministic and has a name. None of them tries to understand what a shell command means.

Refused before the call:

- a file-tool write under `~/.g1`, to the hooks file, to G1's rules or skill, or to the project's
  `.agents/hooks.json`. The project's own `proposals/` and `challenges/` folders are the exception, since that's where
  the agent is supposed to write;
- a file-tool write to `agy`'s conversation store, or to anything under a `.system_generated` folder;
- with a contract active, a file-tool write to an oracle file or outside `allowed_paths`;
- a shell command that mentions any of those paths or runs G1's command line. The gate catches `g1`, `g1.pyz`,
  `python -m g1` and `python -c 'import g1'`, even hidden behind `sudo`, `env`, `exec`, `nice`, `timeout`, `sh -c`,
  `eval` or a here-document, whatever the subcommand. The first 16 KB are tokenized with `shlex`, the rest is scanned
  with linear patterns, and anything over 1 MiB is refused without looking;
- every mutating tool, once an integrity lockdown is in place.

One thing is deliberately not refused: editing an ordinary file, or an oracle file, from the shell. The agent has to be
able to run its tests. The receipt re-measures the whole tree afterwards, oracle hashes included, so the edit is caught
there anyway. The textual gate is closer to an alarm than a wall. The real boundary is the hash check, the anchor
check, and the command line refusing processes the agent started.

## A second model as reviewer

A model's review is still just a claim. So G1 accepts a reviewer's finding in exactly one form: a **challenge**, a
file at `challenges/<id>.json` holding one claim and one contract whose `must_flip` checks fail on the current tree
because of that defect. The reviewer is usually a model from another family, running in its own `agy` session.

A challenge's checks never run inside a hook. The user lists them with `g1 challenges .` (parsed but not executed,
every check's full argv shown), reads the commands, and runs them with their own rights via `g1 challenges . --run`.
Each check gets 60 seconds. The real tree is hashed before and after; a check that touched it makes the challenge
`invalid`. All checks failing means `confirmed`; any check passing means `unproven`. A confirmed challenge then waits
for the user. `g1 challenge . <id> accept` takes a fresh red baseline and registers the contract with the decision in
the same record; `reject` records the reason. The decision belongs to the user because a failing check proves that a
behaviour is missing, not that the reviewer's expectation is right. After acceptance it's an ordinary task: the worker
model fixes, G1 verifies, the receipt completes.

We ran this end to end once. Flash built a SemVer library (43 of 44 hidden checks passing), Claude Opus 5.5 proved the
missing case with a failing check in 73 seconds and reported nothing false, the user accepted, and Flash fixed it under
a receipt (44 of 44).

## Install

```sh
git clone https://github.com/haamsuk-collab/im-not-gembyeong ~/src/g1
~/src/g1/bin/g1 install
```

Type those two lines yourself. The installer is a decision command: it reads `/proc` and exits with code 3 if `agy` is
among its ancestors. An agent told to install G1 gets a one-line refusal and ends up asking you.

What the installer writes, and keeps in place from then on:

| Path | Role |
|---|---|
| `~/.g1/g1.pyz` | G1's code as a bytecode-only zipapp (standard library only, no dependencies). Skipping source compilation saves 15 to 25 ms per hook. |
| `~/.g1/manifest.json` | the code hash, the hook group and its hash, the host fingerprint, the hashes of the installed rule files |
| `~/.gemini/config/hooks.json`, group `g1` | the four hook entries, each with the code hash pinned. Entries other tools added are left byte for byte. |
| `~/.gemini/config/rules/g1.md`, `g1-instinct.md` | two always-on rules: the entry rule (order of authority, five duties, the mechanics) and the instinct rule (confirm or stop, authority by channel, evidence, the honest final reply) |
| `~/.gemini/config/rules/g1-work.md`, `g1-writing.md`, `g1-korean.md` | situational rules the model reads before coding, before writing documents, and before writing in Korean |
| `~/.gemini/config/skills/g1/SKILL.md` | the proposal format field by field, the blocked and resume reports, challenges, what G1 does at Stop |
| `~/.g1/workspaces/<id>/` | one per project, created at its first session: `ledger.jsonl`, `ledger.head.json`, `proposals/`, `challenges/`, `evidence/`, `views/` |
| `~/.g1/anchors/`, `mirror/`, `observe/`, `scratch/` | anchors and witnesses, ledger mirrors, hook journals and lockdown markers, scratch copies for checks |

Nothing goes into your project. If a project's `.agents/hooks.json` already had a G1 group, the installer removes it.
There's one hook layer, the global one. With two, the cost doubled and the layers saw different calls. If anyone
changes the hook entries, a rule or the skill, the next session puts them back. `~/src/g1/bin/g1 uninstall` removes
only G1's entries; add `--purge` to remove `~/.g1` as well.

All of these commands are optional:

```sh
~/src/g1/bin/g1 status .       # what G1 knows about this project: head, active task, alerts, tasks
~/src/g1/bin/g1 audit .        # walk the chain and recompute every receipt and completion
~/src/g1/bin/g1 repair .       # after a lockdown: see what differs, then --accept-ledger, --restore or --forget
~/src/g1/bin/g1 challenges .   # list challenges; add --run [ID ...] to run their checks with your rights
~/src/g1/bin/g1 challenge . ID accept|reject [REASON]
~/src/g1/bin/g1 host-verify    # after re-running the probes on a new agy version
~/src/g1/bin/g1 turn-end .     # do what the Stop hook does, once, by hand
```

The launcher prefers the installed archive and falls back to the source tree. `install` always builds from the source
tree next to it.

## What it costs

We ran 137 real `agy` sessions on gemini-3.8-flash-high, one of them with Claude Opus 5.5 as the reviewer. Every
number below comes from an independent oracle that re-ran the original tests on the final tree or inspected the tree
directly. Neither G1 nor the agent had a say in the outcome.

| Question | Answer |
|---|---|
| Does G1 slow the agent down? | A mutating tool call costs 75 ms (5 ms of it G1's own work), a model call 96 ms, a read-only call 0 ms. Verification runs once per turn, 0.3 to 1.1 s. |
| Is the verdict right? | In 46 of 46 sessions, G1's "complete" matched the oracle. No false completion. |
| Does it save work? | Easy and medium tasks: 17 to 24% fewer tokens, 23 to 32% less time. Hard single-session tasks: no difference. |
| What about a lost session? | After we killed a session and deleted its records, the next one finished with 39% fewer tokens and 14 tool calls instead of 33. It didn't have to rediscover the task. |
| Can a second model find what Flash missed? | Once, end to end, as described above. |
| Does the instinct rule change behaviour? | On six ambiguous or impossible tasks, Flash stopped and asked in 12 of 12 sessions with the rule and 12 of 12 without. Not measurable on that class, and no measurable cost either. |

There's also what we couldn't measure. On small tasks with visible tests, Gemini 3.8 Flash never failed and never lied
across 60 sessions. Large repositories and multi-day work, where a referee matters most, aren't in this data yet.
Details and limits are in `docs/design.md` section 14 and `research/measure/`.

## What people complain about

Rather than guess at what goes wrong, we read 909 posts about Gemini on Threads and X (Korean and English, 187
queries, December 2023 to October 2026). 343 of them were the author's own complaint. Most are about things G1 can't
touch: the model got dumber (99), the product (90), outages (74), other models being better (61), pricing (54). The
four things G1 answers directly, false reports, ignored instructions, lost context and loops, showed up in 57 of the
343, and in 18 of the 86 complaints about agents working on code. Read the numbers as a map, not a rate. The method,
the counts and the links are in `research/complaints/`.

## How the code was reviewed

Five independent reviews, each a Gemini 3.8 Flash session inside `agy` with a written brief. Before the fifth, Claude
Opus 5.5 and Claude Fable 5.1 read the same code outside `agy`. Every finding was reproduced with the reviewer's own
script before it was fixed, and every fix has a test named after the finding. The fifth review found nothing. The
briefs, reports and answers are in `research/review/`. The suite is 126 tests in `tests/test_core.py`.

## What G1 doesn't do

- It doesn't make the model smarter. It touches no prompt, no tool and no loop.
- It doesn't use a second model as a judge. A judge can be persuaded; a test can't.
- It doesn't replace `agy`'s own features. Subagents, goal mode and parallel attempts stay native; G1 only verifies
  the results. A subagent's tool calls go through the same hooks under its own conversation id.
- It can't stop an agent that rewrites every G1 file, anchor, witness, mirror and manifest consistently from the shell
  within one session, because all of G1 runs as your user. It does catch partial tampering and any tampering through
  file tools, and removing G1 never produces a false completion. A full defence needs an OS boundary that this
  environment (Termux under PRoot) doesn't have. The residual risk is written down in `docs/design.md` section 7.7.

## Where to read more

| Document | What's in it |
|---|---|
| `docs/principles.md` | the eight principles G1 is built on, and how each became a rule |
| `docs/design.md` | the full design: every mechanism, the fact it proves, and where it came from |
| `docs/host-agy.md` | what we measured about `agy`'s hooks, including where the documentation was wrong |
| `research/complaints/` | the complaint study: method, counts by platform and language, links to the posts behind each label |
| `research/agy-hooks/` | the probes and raw records behind the hook measurements |
| `research/measure/` | the A/B runners, the results of all six measurement runs, and experiment C1 (challenges) |
| `research/review/` | five independent reviews and a pre-audit by two more reviewers, each finding with its reproduction and fix |
| `research/atoms/` | 696 design "atoms" taken from a predecessor harness, five other projects and one post series, each with a verdict |

## Repository map

```
src/g1/           the core: canon, ledger, snapshot, contract, runner, verify, complete, control, state,
                  project, workspace, integrity, audit, install, paths
src/g1/adapter/   agy.py, the only module that knows the host's name
src/g1/host/      the five rules and the skill G1 installs into ~/.gemini/config
tests/            126 tests: chain breaks, crash recovery, the completion function, gates, canary, anchors,
                  challenges, every reviewer's finding
bin/g1            the command-line launcher
docs/             principles, design, host contract
research/         complaints, hook probes, A/B runs, reviews, design atoms
```

## License

MIT. See `LICENSE`.
