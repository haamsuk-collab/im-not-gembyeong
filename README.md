# im-not-gembyeong

제미나이, 더 이상 젬병이 아니(고 싶)다.

*Gembyeong* (젬병) is Korean for "hopeless at it", and it happens to rhyme with Gemini. Gemini, show the receipt.

Korean version: [README.ko.md](README.ko.md)

In the code, the commands and the documents the program is called G1. That name is a pun as well: one g, the gravity
that Antigravity does without. G1 is a small program that sits beside the Antigravity CLI (`agy`) while Gemini works on
your code. It does two things: it checks whether "done" is true, and it keeps the state of the work when the session
ends. It is about 4,700 lines of standard-library Python (`wc -l`), has no dependencies, and writes nothing into your
projects.

You install it once. After that it works in every project without any action from you.

## The problem it solves

"Done. The tests pass."

Two things can be wrong with that sentence, and we measured both. When a tool call was blocked, Gemini 3.8 Flash still
answered "DONE" in 3 of 8 runs, although nothing had been done (`research/agy-hooks/`). And when the session ends, the
agent's memory ends with it. The next session starts from zero, not knowing what was done, what remains, or what "done"
was supposed to mean.

An agent that grades its own work is not a verifier. G1 takes over the grading. It holds the definition of done, runs
the checks itself, and writes the result in a record that nobody can edit.

## Four terms

| Term | What it is in the code |
|---|---|
| **contract** | The definition of "done", written before the work starts: objective, criteria, checks, the paths the agent may edit (`allowed_paths`), the files the checks read (`oracle_files`). Stored whole inside a `contract_registered` ledger record. |
| **receipt** | A `verification_succeeded` record: the checks G1 ran itself, their exit codes, the tree digest, the environment digest, the changed set. Completion binds to its sequence number and hash. |
| **ledger** | An append-only JSONL file in which every record carries the SHA-256 of the record before it. Lives under `~/.g1/workspaces/<id>/`. |
| **projection** | The status block G1 injects into the model's context: 1,024 bytes at session start, 512 bytes before each model call, built from the ledger and nothing else. |

Everything else in G1 exists to produce or protect one of these four.

## Where it hooks in

`agy` runs the agent in a loop: call the model, run the tools the model asked for, repeat, stop. At fixed points of
that loop it can run an external command, which reads a JSON payload on stdin and answers with JSON on stdout. These
points are called hooks. G1 installs four entries into `~/.gemini/config/hooks.json`, in a group named `g1`:

| Event | When it fires | What G1 does | Time limit |
|---|---|---|---|
| `SessionStart` | once per conversation, subagents included | enrols the workspace if it is new, checks the ledger against its anchor, fingerprints the `agy` binary, restores its own rule files if they changed, injects the projection | 30 s |
| `PreInvocation` | before every model call | validates pending proposals (at most two red baselines per call), applies blocked and resume reports, injects a 512-byte status block | 900 s |
| `PreToolUse` | before a mutating tool runs | journals the call; refuses writes to G1's own files, to transcripts, to pinned oracle files and outside the scope; refuses shell commands that name G1's state or run G1's command line | 20 s |
| `Stop` | when the agent goes idle | runs the contract's checks on a scratch copy, runs the canary, compares the tree, writes the receipt, and decides between complete, one more turn, and pause | 1800 s |

The `PreToolUse` matcher is a regular expression over the mutating tool names only (`write_to_file`,
`replace_file_content`, `run_command`, `invoke_subagent` and the like). Viewing a file or searching never starts a G1
process, so reading costs nothing.

Each hook entry is a short inline Python program. It hashes `~/.g1/g1.pyz`, compares the hash with the value pinned at
install time, and exits with code 3 if they differ. If someone changes G1's code, G1 stops running for the rest of the
session, and because `agy` treats a failing `PreToolUse` as a refusal, every mutating tool is blocked until G1 is
reinstalled. This behaviour was measured and chosen deliberately.

## One task, start to finish

The project has a wrong `median()` and a failing test. The user's whole instruction is "Make `tests/test_stats.py` pass
by fixing `src/stats.py`." Nobody mentions G1.

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

3. **Validation, before the next model call.** G1 renames the file to `fix-median.running.json`, takes a lock on it,
   and from then on reads it only through that descriptor, never by name again, so the agent cannot swap the content
   under it. Then it checks, in this order:
   - Shape. Strict: one unknown key rejects the whole proposal. Ids match `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, text is at
     most 600 characters, there are at most 64 checks, and paths are relative, never `.` and never `..`.
   - Coverage matrix. Every criterion has at least one check and every check covers at least one criterion. A
     criterion that only a human could confirm is a row with no check, and is rejected.
   - Targets. Every `must_flip` check names the files it depends on. They lie inside `allowed_paths` and are never
     oracle files.
   - State. No other contract is active in this workspace, and every task in `depends_on` has a completion receipt.
   - Pins. The SHA-256 of every oracle file, and of every executable the checks name. `python3` is resolved on a
     scrubbed PATH, not the agent's.
   - **Red baseline.** G1 copies the tree to `~/.g1/scratch/baseline-*/tree` and runs every check there. A
     `must_flip` check must fail at this point. A check that already passes proves nothing about the work and is
     rejected. A `guard` check must pass now and again at the end.
   - Base manifest. The whole tree, every file's hash, mode and size, saved for the changed-set check later.

   The answer lands beside the file as `fix-median.accepted.json` or `fix-median.rejected.json`, with typed reasons.
   On acceptance the ledger gets a `contract_registered` record holding the contract, the baseline results, the oracle
   hashes, the executable hashes and the tree digest.

4. **Work.** The agent edits `src/stats.py` and runs the tests as often as it likes. If it tries to edit
   `tests/test_stats.py` with a file tool, `PreToolUse` refuses with the reason "G1 pinned oracle". If it tries
   `README.md`, the reason is "G1 scope". If it runs `sed -i` on the test file through the shell, G1 lets that through
   on purpose, because the agent has to be able to run its tests, and catches the edit later by hash.

5. **Stop.** `agy` reports `fullyIdle: true`. G1 then works through these steps:
   - checks the ledger head against its anchor; a diverged ledger locks the workspace down and nothing runs;
   - compares the oracle hashes with the pins; a difference ends the attempt with `oracle_changed`;
   - counts the mutating tool calls in the host transcripts and compares them with its own journal
     (`observation_gap`);
   - re-hashes the executables (`executable_changed`);
   - copies the tree to a scratch directory, minus `.git`, `node_modules`, `.venv` and the like, with a private HOME
     and TMPDIR, an allowlisted PATH, `LANG=C.UTF-8` and `PYTHONHASHSEED=0`;
   - runs every check there, each in its own process group, with a deadline and a 1 MiB cap per output stream; exit
     code 0 with no timeout and no truncation is a pass;
   - runs the **canary**: for every passing `must_flip` check it makes a second copy, overwrites the check's targets
     with unparseable bytes, and runs the check again. It must fail. A check that passes without the code does not
     test the code;
   - hashes the tree again, which must equal the hash from before the checks ran (`identity_changed`);
   - diffs the tree against the base manifest. Here only `src/stats.py` changed. A changed path outside
     `allowed_paths`, or a new symbolic link that points out of the workspace, is a `scope_violation`;
   - writes the evidence to `evidence/<attempt>/results.json`, after redacting API keys, PEM blocks, JWTs and bearer
     tokens;
   - appends `verification_started` and `verification_succeeded` to the ledger.

6. **Completion, under one lock.** G1 takes the ledger lock, checks that no record landed after the receipt, hashes
   the tree, calls `complete.approve()`, hashes the tree again, and appends `task_status_changed: complete` bound to
   the receipt by compare-and-swap on the head. If anything moved in between, the task is not completed this turn and
   the next turn verifies again. After the record it hashes the tree once more. A write in that small window cannot
   be prevented, but it is recorded as `post_completion_change` and shown in the status block.

7. The agent's final message said "I have updated median". That sentence was not an input to any step above.

## The completion function

`complete.approve()` is one function, and it is the only place a "complete" verdict comes from. It approves only when
all of the following hold:

- every check ran and passed, and every `must_flip` check has a sensitive canary;
- the receipt covers every check of the contract; an empty result set never counts as "all pass";
- the current tree digest equals the receipt's;
- the receipt's contract hash equals the task's;
- the oracle hashes equal the pinned set;
- the policy digest (G1's version, code hash and hook group hash) equals the one sealed at admission;
- the changed set lies inside the allowed paths;
- the observation gap is zero;
- the task is still active.

Every other input is typed as a veto: it can add a reason to refuse, and nothing can add an approval. A test enumerates
every combination of veto inputs and confirms that none of them approves without executed evidence. A model's opinion,
including the agent's own summary, is not among the function's inputs.

## When the checks do not pass

G1 must decide whether to let the agent stop or ask for one more turn. `control.decide()` is a pure function of the
ledger:

| Situation | Decision |
|---|---|
| the tree has not changed since the last failing attempt | pause, `no_change`; no verification runs |
| verification could not run (an oracle changed, no disk space, a missing executable, a gap) | stop, `environment_unknown`; counts as neither progress nor failure |
| changes outside the scope | pause, `scope_violation` |
| this tree-and-vector pair was seen before, or the results alternate between two states | pause, `oscillation` |
| three continuations already issued for this task | pause, `budget_exhausted` |
| the set of failing checks did not strictly shrink | pause, `no_progress` |
| otherwise | `continue`, with one line: how many checks pass, the next failing check and its exact command |

The continuation counter is written to the ledger before the answer is printed and never decreases. Raw check output is
never echoed into the model's context. `agy` itself allows ten continues per session; G1 uses at most three per task,
because ten forced continues cost 26 times one answer in our measurement and produced output with no content.

A paused task is not finished. A new proposal with the same task id supersedes it with a fresh red baseline. A task the
agent paused itself with `<task>.blocked.json` (one uncertain item, why, options) resumes with `<task>.resume.json`
under the same contract. The next session's projection carries the question, so a fresh agent asks the user instead of
guessing.

## Why the record can be trusted

**The chain.** A record is `{"schema", "seq", "prev", "ts", "event", "data", "hash"}`, encoded canonically (UTF-8,
sorted keys, no floats, no duplicate keys, no trailing data) and hashed with a domain prefix. Change one byte anywhere
and every hash after it stops matching. `g1 audit` walks the chain, re-derives every receipt's verdict from its
per-check results, re-runs the completion predicate on every completion, and reports a stored verdict more favourable
than its evidence as a finding.

**The commit.** Under a lock (`flock`, 10-second timeout, inode re-check), in this order: journal the record to
`ledger.pending.json`, append it, move the head, move the anchor, append it to the mirror, clear the journal. If the
process dies at any step, the next open finishes or discards the commit from the journal. An append cut mid-line is
completed from the journaled bytes. No committed byte is ever removed.

**Anchor, mirror, witness.** Outside the workspace's own directory G1 keeps three things: the head it last wrote
(`~/.g1/anchors/<ledger_id>.head`), a copy of every record (`~/.g1/mirror/<ledger_id>.jsonl`) and, per workspace, a
note of which ledger belongs there (`~/.g1/anchors/ws/<id>.json`). At every session start and before every
verification the head must equal the anchor. A ledger behind its anchor has lost records; they are restored from the
mirror and the repair is recorded. A ledger ahead of, or different from, its anchor was changed outside G1; the
workspace is locked down, every mutating tool is refused, and the user decides with `g1 repair --accept-ledger`,
`--restore` or `--forget`. A restore is bounded by the anchor, so records somebody appended to the mirror never come
back as legitimate history.

**Self-protection.** The hook entries pin the code hash. At every session start G1 re-hashes its five rule files and
the skill against its manifest and rewrites any that changed. It fingerprints the `agy` binary (size plus the first and
last MiB); a changed binary records `host_contract_observed: unverified`, and completion is withheld until the user
re-runs the probes and `g1 host-verify`. G1's decision commands (`install`, `uninstall`, `init`, `propose`, `turn-end`,
`host-verify`, `repair`, `challenge`, `challenges --run`) read `/proc` and refuse to run with `agy` among their ancestor
processes. When `/proc` cannot be read, the command treats the caller as the agent.

**The agent's words.** G1 reads the host transcript for one purpose: to count the model's mutating tool calls and
compare the count with what its hooks journaled. A difference is a gap, and a gap refuses completion. A transcript that
is gone is reported as `liveness_unknown` in the receipt and in the status block. It does not refuse completion, because
a deleted session must not stop a fresh agent from continuing.

## The gates, and what they deliberately allow

Every gate is deterministic and named. No gate tries to interpret a shell command.

Refused before the call:

- a file-tool write under `~/.g1`, to the hooks file, to G1's rules or skill, or to the workspace's
  `.agents/hooks.json`; the workspace's own `proposals/` and `challenges/` directories are the exception, since the
  agent writes there;
- a file-tool write to `agy`'s conversation store, or to anything under a `.system_generated` directory;
- with an active contract, a file-tool write to a pinned oracle file or outside `allowed_paths`;
- a shell command whose text names any of the paths above, or runs G1's command line in command position. The gate
  recognises `g1`, `g1.pyz`, `python -m g1` and `python -c 'import g1'`, also behind `sudo`, `env`, `exec`, `nice`,
  `timeout`, `sh -c`, `eval` and here-documents, with any subcommand. The first 16 KB are tokenized with `shlex`, the
  rest is scanned with linear patterns, and a command over 1 MiB is refused outright;
- every mutating tool, after an integrity lockdown.

Deliberately not refused: a shell edit of an ordinary file, or of a pinned oracle file. The agent must be able to run
its tests. The receipt measures the whole tree afterwards, oracle hashes included, so the edit is caught there. The
textual gate is a tripwire; the real boundary is the hash check, the anchor check, and the command line's own refusal
of processes the agent started.

## A second model as reviewer

A model's review is a claim like any other. G1 accepts a reviewer's finding in one form only: a **challenge**, a file
under `challenges/<id>.json` holding one claim and one contract whose `must_flip` checks fail on the current tree
because of the defect. The reviewer is typically a model of another family in its own `agy` session.

Nothing runs in a hook. The user lists the challenges (`g1 challenges .`, parsed but not executed, every check's full
argv shown), reads the commands, and runs them with their own rights (`g1 challenges . --run`). Each check gets 60
seconds. The real tree is hashed before and after, and a check that changed it makes the challenge `invalid`. All
checks failing is `confirmed`; any check passing is `unproven`. A confirmed challenge then waits for the user:
`g1 challenge . <id> accept` runs the red baseline again and registers the contract, with the decision inside the
same record; `reject` records the reason. The decision is the user's because a failing check proves that a behaviour
is absent, not that the reviewer's expectation is right. After acceptance the work is ordinary: the worker model fixes,
G1 verifies, the receipt completes.

Measured once end to end: Flash built a SemVer library (hidden oracle 43 of 44), Claude Opus 5.5 proved the missing
case with a failing check in 73 seconds and no false report, the user accepted, and Flash fixed it under a receipt
(44 of 44).

## Install

```sh
git clone https://github.com/haamsuk-collab/im-not-gembyeong ~/src/g1
~/src/g1/bin/g1 install
```

Run those two lines yourself. The installer is a decision command: it reads `/proc` and exits with code 3 when `agy` is
among its ancestors. An agent told to install G1 gets one line explaining why not, and has to ask you.

What the installer writes, and keeps in place from then on:

| Path | Role |
|---|---|
| `~/.g1/g1.pyz` | G1's code as a bytecode-only zipapp (standard library only, no dependencies); skipping source compilation saves 15 to 25 ms per hook |
| `~/.g1/manifest.json` | the code hash, the hook group and its hash, the host fingerprint, the hashes of the installed rule files |
| `~/.gemini/config/hooks.json`, group `g1` | the four hook entries, each with the code hash pinned; entries of other tools are kept byte for byte |
| `~/.gemini/config/rules/g1.md`, `g1-instinct.md` | two always-on rules: the entry rule (order of authority, five duties, the mechanics) and the instinct rule (confirm or stop, authority by channel, evidence, the honest final reply) |
| `~/.gemini/config/rules/g1-work.md`, `g1-writing.md`, `g1-korean.md` | situational rules the model reads before coding, before writing documents, and before writing Korean |
| `~/.gemini/config/skills/g1/SKILL.md` | the proposal format field by field, the blocked and resume reports, challenges, what G1 does at Stop |
| `~/.g1/workspaces/<id>/` | one per project, created at its first session: `ledger.jsonl`, `ledger.head.json`, `proposals/`, `challenges/`, `evidence/`, `views/` |
| `~/.g1/anchors/`, `mirror/`, `observe/`, `scratch/` | anchors and witnesses, ledger copies, hook journals and lockdown markers, scratch copies for the checks |

Nothing is written into your projects. If a workspace already had a G1 group in its `.agents/hooks.json`, the installer
removes it. There is one hook layer, the global one; with two layers the cost doubled and the layers saw different
calls. If someone changes the hook entries, a rule or the skill, the next session restores them.
`~/src/g1/bin/g1 uninstall` removes only G1's entries; `--purge` also removes `~/.g1`.

Commands, all optional:

```sh
~/src/g1/bin/g1 status .       # what G1 knows about this project: head, active task, alerts, tasks
~/src/g1/bin/g1 audit .        # walk the chain and re-derive every receipt and completion
~/src/g1/bin/g1 repair .       # after a lockdown: see what differs, then --accept-ledger, --restore or --forget
~/src/g1/bin/g1 challenges .   # list challenges; --run [ID ...] runs their checks with your rights
~/src/g1/bin/g1 challenge . ID accept|reject [REASON]
~/src/g1/bin/g1 host-verify    # after re-running the probes on a new agy version
~/src/g1/bin/g1 turn-end .     # run what the Stop hook does, once, by hand
```

The launcher prefers the installed archive and falls back to the source tree. `install` always builds from the source
tree next to it.

## What it costs, measured

137 real `agy` sessions with gemini-3.8-flash-high, one of them with Claude Opus 5.5 as reviewer. Every outcome below
comes from an independent oracle that re-ran the original tests on the final tree or inspected the tree itself.
Neither G1 nor the agent supplied any outcome.

| Question | Answer |
|---|---|
| Does G1 slow the agent? | A mutating tool call costs 75 ms (5 ms of it G1's own work), a model call 96 ms, a read-only call 0 ms. Verification runs once per turn, 0.3 to 1.1 s. |
| Is the verdict right? | In 46 of 46 sessions G1's "complete" agreed with the oracle. No false completion. |
| Does it save work? | Easy and medium tasks: 17 to 24% fewer tokens, 23 to 32% less time. Hard single-session tasks: no difference. |
| What about a lost session? | After we killed a session and deleted its records, the next session finished with 39% fewer tokens and 14 tool calls instead of 33. It did not have to rediscover the task. |
| Can a second model find what Flash missed? | Once, end to end, as described above. |
| Does the instinct rule change behaviour? | On six ambiguous or impossible tasks, Flash stopped and asked in 12 of 12 sessions with the rule and 12 of 12 without it. Not measurable on that class, and no measurable cost either. |

What we could not measure: on self-contained tasks with visible tests, Gemini 3.8 Flash never failed and never lied in
60 sessions. Large repositories and multi-day work, where a referee matters most, are not in this data yet. Details and
limits: `docs/design.md` section 14 and `research/measure/`.

## What people complain about

Rather than guess what goes wrong, we read 909 posts about Gemini on Threads and X (Korean and English, 187 queries,
December 2023 to October 2026). 343 of them are the user's own complaint. Most concern things G1 cannot touch: the
model got dumber (99), the product (90), outages (74), rivals (61), pricing (54). The four labels G1 answers directly,
false reports, ignored instructions, lost context and loops, appear in 57 of the 343 complaints and in 18 of the 86
about agents working on code. The counts are a map of what people complain about, not a rate. The method, the counts
and the links are in `research/complaints/`.

## How the code was reviewed

Five independent reviews, each a Gemini 3.8 Flash session inside `agy` with a written brief. Before the fifth, Claude
Opus 5.5 and Claude Fable 5.1 read the same code outside `agy`. Every finding was reproduced with the reviewer's own
script before it was fixed, and every fix has a test named after the finding. The fifth review found nothing. The
briefs, the reports and the answers are in `research/review/`. The suite is 126 tests in `tests/test_core.py`.

## What G1 does not do

- It does not make the model smarter. It changes no prompt, no tool and no loop.
- It does not use a second model as a judge. A judge can be persuaded; a test cannot.
- It does not replace `agy`'s own features. Subagents, goal mode and parallel attempts stay native; G1 only verifies
  their results. A subagent's tool calls run the same hooks under its own conversation id.
- It cannot stop an agent that rewrites every G1 file, anchor, witness, mirror and manifest consistently through the
  shell in one session, because all of G1 runs as your user. It detects partial tampering and all tampering through
  structured tools, and removing G1 never produces a false completion. A full defence needs an OS boundary that this
  environment (Termux under PRoot) does not provide. `docs/design.md` section 7.7 states the residual risk.

## Where to read more

| Document | What it holds |
|---|---|
| `docs/principles.md` | the eight principles G1 is built from, and how each one became a rule |
| `docs/design.md` | the full design: every mechanism, the fact it proves, and where it came from |
| `docs/host-agy.md` | what we measured about `agy`'s hooks, including where the documentation was wrong |
| `research/complaints/` | the complaint study: method, counts by platform and language, links to the posts behind each label |
| `research/agy-hooks/` | the probes and raw records behind the hook measurements |
| `research/measure/` | the A/B runners, the results of all six measurement runs, and experiment C1 (challenges) |
| `research/review/` | five independent reviews and a pre-audit by two more reviewers, each finding with its reproduction and its fix |
| `research/atoms/` | 696 design "atoms" taken from a predecessor harness, five other projects and one post series, each with a verdict |

## Repository map

```
src/g1/           the core: canon, ledger, snapshot, contract, runner, verify, complete, control, state,
                  project, workspace, integrity, audit, install, paths
src/g1/adapter/   agy.py, the only module that knows the host's name
src/g1/host/      the five rules and the skill that G1 installs into ~/.gemini/config
tests/            126 tests: chain breaks, crash recovery, the completion function, gates, canary, anchors,
                  challenges, every reviewer's finding
bin/g1            the command-line launcher
docs/             principles, design, host contract
research/         complaints, hook probes, A/B runs, reviews, design atoms
```

## License

MIT. See `LICENSE`.
