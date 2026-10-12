# im-not-gembyeong

제미나이, 더 이상 젬병이 아니(고 싶)다.

*Gembyeong* (젬병) is Korean for "hopeless at it", and it sounds like Gem-ini. Gemini, show the receipt.

Korean version: [README.ko.md](README.ko.md)

In the code, the commands and the documents the program is called G1. (That name is a pun as well: one g, the
gravity that Antigravity does without.) G1 is a small program that sits beside the Antigravity CLI (`agy`) while
Gemini works on your code. It has one job: to make sure that "done" means done, and that work survives when a
session ends.

You install it once. After that it works in every project without any action from you.

## Start with a picture

You ask an AI coding agent to fix a bug. Two minutes later it says: "Done. The tests pass."

Two things can be wrong with that sentence.

1. It may not be true. We measured this with Gemini 3.8 Flash: when a tool call was blocked, the model still
   answered "DONE" in 3 of 8 runs, although nothing had been done.
2. It may be forgotten. When the session ends, the agent's memory ends with it. The next session starts from zero
   and does not know what was done, what remains, or what "done" was supposed to mean.

An agent that says "done" is like a student who grades their own exam. G1 is the referee: it holds the answer key,
runs the test itself, and writes the result in a book that cannot be erased.

## What people say when Gemini fails

We did not want to guess what goes wrong. So we collected what users say. On 12 October 2026 we searched Threads and
X for posts about Gemini in Korean and in English, with 187 search queries, and read 909 posts
(534 from Threads, 375 from X; 336 in Korean, 573 in English; posted between December 2023 and
October 2026). 343 of them are a user's own complaint. Each complaint got one or more of these labels.

| What the user complains about | Posts | G1's answer |
|---|---|---|
| Got dumber, general disappointment | 99 | none; G1 does not change the model |
| Product, app, forced integration | 90 | none |
| Errors, speed, outages | 74 | none; the host's problem |
| Worse than Claude, GPT, Codex | 61 | none |
| Limits, pricing, plans | 54 | none |
| Hallucinated facts and sources | 39 | none for facts; code claims are tested, not believed |
| Refusals, censorship, lazy answers | 35 | none |
| Code broken or deleted, bad code | 25 | pinned test files; the checks must pass on a copy before "done" |
| Ignores instructions, changes unrelated code | 24 | a contract with a scope; writes outside it are refused or caught at the receipt |
| Forgets context, loses the thread | 19 | the ledger; every session starts from the record, not from memory |
| Loops, repeats, endless thinking | 18 | a continuation budget; a turn that changed nothing ends |
| Sycophancy, apologies, gaslighting | 13 | the agent's words are never evidence |
| Korean or language quality | 6 | none |
| Says it finished or tested when it did not | 1 | the receipt; completion exists only when G1 ran the checks |

86 of the 343 complaints are about Gemini doing work on code or files (Gemini CLI, Antigravity, Cursor, "it
edited my repo"). In that group the four labels G1 answers, false reports, ignored instructions, lost context and
loops, appear in 18 posts; across all 343 complaints, in 57.

Read the table as a map, not as a score. The posts are what search engines index; neither platform allows search
without an account, so the sample is wide but not complete. The method, the counts by platform and language, and
links to the posts behind each label are in `research/complaints/`. The posts themselves are not in this repository.

## What a referee needs

To referee a task fairly, you need four things.

| You need | Why | What G1 calls it |
|---|---|---|
| A definition of "done", written before the work starts | So the goal cannot move after the fact | a **contract** |
| A way to run the checks yourself | A report is only a claim | **verification** |
| A record that cannot be edited | So history stays true | the **ledger** |
| A way to tell the next person where things stand | So no work is lost | the **projection** |

Everything in G1 is one of these four things.

## The four moments

`agy` lets a program run at certain moments of the agent's work. These moments are called hooks. G1 uses four of them.

```
session starts ──► G1 injects the state: "task X is active, check K2 still fails, scope is src/"
   │
   ├─ before each model call ──► G1 injects a 512-byte status line (so a long session never forgets)
   │
   ├─ before each file write or shell command ──► G1 refuses writes to its own files,
   │                                               to the pinned test files, and outside the scope
   │
   └─ when the agent stops ──► G1 runs the contract's checks ITSELF on a copy of the code,
                               writes a receipt, and decides: complete, or not yet
```

Read-only tools (viewing a file, searching) never start G1, so they cost nothing.

## One task, start to finish

Here is a real run from our tests. The project has a function `median()` that is wrong, and a test that fails.
The user's whole instruction was: *"Make tests/test_stats.py pass by fixing src/stats.py."* The word G1 did not appear.

1. Session start. G1 enrols the project, which it had never seen, and injects: *"No active contract. For durable work,
   write a proposal to `.../proposals/<id>.json`."*
2. The agent writes a proposal. The proposal names the goal and one criterion: "the test passes". It names one
   check, `python3 tests/test_stats.py`, the file the check depends on (`src/stats.py`), the files the agent may
   edit (`src/`), and the test file that must stay fixed (`tests/test_stats.py`).
3. G1 validates the proposal before the next model call. It checks the shape, then runs the check on the untouched
   code. The check must fail now, because a check that already passes proves nothing about the work. This is the
   **red baseline**. G1 also records the hash of the test file. The proposal becomes a contract.
4. The agent edits the code. It runs the test as often as it likes. If it tried to edit the test file, or a file
   outside `src/`, G1 would refuse.
5. The agent stops. G1 copies the code to a scratch directory and runs the check there, in a clean environment.
   The check passes. Then G1 breaks `src/stats.py` in a second copy and runs the check again. This time the check
   must fail; if it did not, it would not depend on the code at all. This is the **canary**.
6. G1 compares the file tree with the tree it recorded at contract time. Only `src/stats.py` changed.
7. G1 writes a receipt into the ledger and marks the task complete. The agent's final message said "I have updated
   median". That message was never an input to this decision.

If step 5 had failed, G1 would have recorded why, and it would ask the agent for one more turn only if fewer checks
failed than last time.

## What makes the record trustworthy

- The ledger is a chain. Every record contains the hash of the record before it, so a change to one byte in the past
  breaks the chain. `g1 audit` recomputes every receipt and every completion from the records alone.
- Completion is one function. It returns "complete" only from checks that G1 ran itself. Any other input, including
  a model's opinion, can only say "no". A test enumerates every combination of inputs and proves that nothing can say
  "yes" without executed evidence.
- G1 protects itself. Every hook entry contains the hash of G1's own code; if the code changes during a session, the
  hooks refuse to run. If the agy binary changes, G1 withholds completion until the binary has been re-measured.
- G1 notices a forged history. Outside the project, G1 keeps an anchor: the last record it wrote. A ledger that ends
  anywhere else was changed by something other than G1, and the project is locked until you decide with `g1 repair`.
- G1 never uses the agent's words as evidence. It reads the agent's transcript for one purpose: to count the tool
  calls, which proves that its own hooks saw every one of them.

## Install

```sh
git clone https://github.com/haamsuk-collab/im-not-gembyeong ~/src/g1
~/src/g1/bin/g1 install
```

You can also tell agy: *"install G1 from https://github.com/haamsuk-collab/im-not-gembyeong"*. The agent runs the
same two lines.

The installer writes these files and keeps them in place from then on:

| File | Role |
|---|---|
| `~/.g1/g1.pyz` | G1's code (Python standard library only, no dependencies) |
| `~/.gemini/config/hooks.json`, group `g1` | the four hook entries, each with the code hash pinned |
| `~/.gemini/config/rules/g1.md`, `g1-instinct.md` | two always-on rules: the entry rule (order of authority, five duties, the mechanics) and the instinct rule (confirm or stop, authority by channel, workspace, evidence, the honest final reply) |
| `~/.gemini/config/rules/g1-work.md`, `g1-writing.md`, `g1-korean.md` | situational rules the agent reads before coding, before writing documents, and before writing Korean |
| `~/.gemini/config/skills/g1/SKILL.md` | the proposal format and the blocked and resume reports, for the agent to read when it needs them |
| `~/.g1/workspaces/<id>/` | one ledger per project, created at the project's first session |

G1 writes nothing into your projects. If someone changes the hook entries, the rule, or the skill, the next session
restores them. To remove G1, run `~/src/g1/bin/g1 uninstall`; it removes only its own entries.

Useful commands, all optional:

```sh
~/src/g1/bin/g1 status .      # what G1 knows about the current project
~/src/g1/bin/g1 audit .       # recompute every receipt and completion from the ledger
~/src/g1/bin/g1 host-verify   # after re-running the probes on a new agy version
~/src/g1/bin/g1 repair .      # after an integrity lockdown: see what changed, then --accept-ledger, --restore or --forget
~/src/g1/bin/g1 challenges .  # list the challenges a reviewing model wrote (nothing runs yet)
~/src/g1/bin/g1 challenges . --run   # run their checks (another model's code, with your rights) and record verdicts
```

## What it costs, measured

We measured G1 on 137 real agy sessions with gemini-3.8-flash-high (and one with Claude Opus 5.5 as a reviewer). The
numbers below come from an independent oracle: the runner re-ran the original tests on the final code, or checked the
file tree itself. Neither G1 nor the agent supplied any outcome.

| Question | Answer |
|---|---|
| Does G1 slow the agent? | No. A mutating tool call costs 75 ms, a model call 96 ms, a read-only call 0 ms. Verification runs once per turn, 0.3-1 s. |
| Is G1's verdict correct? | In 46 of 46 sessions, G1's "complete" agreed with the independent oracle. No false completion. |
| Does it save work? | Easy and medium tasks: 17-24% fewer tokens, 23-32% less time. Hard single-session tasks: no difference. |
| What about a lost session? | After we killed a session and deleted its records, the next session finished with 39% fewer tokens and 14 instead of 33 tool calls. It did not have to rediscover the task. |
| Can a second model find what Flash missed? | Once, end to end: Flash's library passed 43 of 44 hidden checks; Claude Opus 5.5 proved the missing one with a failing check in 73 s, with no false report; after the user accepted it, Flash fixed it under a receipt (44/44). |
| Does the instinct rule change behaviour? | On six ambiguous or impossible tasks, Flash stopped and asked in 12 of 12 sessions with the rule and 12 of 12 without it. Not measurable on that class; no measurable cost either. |

What we could not measure: on self-contained tasks with visible tests, Gemini 3.8 Flash never failed and never lied in
60 sessions. The cases where a referee matters most, large repositories and multi-day work, are not in this data yet.
Details and limits: `docs/design.md` section 14 and `research/measure/`.

## How the code was reviewed

Five independent reviews read the code, each one a Gemini 3.8 Flash session inside agy with a written brief. Before
the fifth, Claude Opus 5.5 and Claude Fable 5.1 reviewed the same code outside agy. Every finding was reproduced with
the reviewer's own script before it was fixed, and every fix has a test named after the finding. The fifth review
found nothing. The briefs, the reports and the answers are in `research/review/`. The suite has 126 tests.

## What G1 does not do

- It does not make the model smarter. It does not change prompts, tools, or the agent's loop.
- It does not use a second model as a judge. A judge can be talked into "yes"; a test cannot.
- It does not replace agy's own features. Subagents, goal mode and parallel attempts stay native; G1 only verifies
  their results.
- It cannot stop an agent that rewrites every G1 file consistently through the shell in one session, because all of
  G1 runs as your user. `docs/design.md` section 7.7 states this residual risk.

## Where to read more

| Document | What it holds |
|---|---|
| `docs/principles.md` | the eight principles G1 is built from, and how each one became a rule |
| `docs/design.md` | the full design: every mechanism, the fact it proves, and where it came from |
| `docs/host-agy.md` | what we measured about agy's hooks, including where the documentation was wrong |
| `research/complaints/` | the complaint study above: method, counts by platform and language, and links to the posts behind each label |
| `research/agy-hooks/` | the probes and raw records behind the hook measurements |
| `research/measure/` | the A/B runners and the results of all six measurement runs, and experiment C1 (challenges) |
| `research/review/` | five independent reviews of the code and a pre-audit by two more reviewers, each finding with its reproduction and its fix; the fifth review found nothing |
| `research/atoms/` | 696 design "atoms" taken from a predecessor harness, five other projects and one post series, each with a verdict |

## Repository map

```
src/g1/           the core: ledger, contract, verify, complete, control, project, integrity, audit, install
src/g1/adapter/   agy.py, the only file that knows anything about agy
tests/            126 tests: chain breaks, crash recovery, the completion function, gates, canary, anchors, auto-enrolment
bin/g1            the command-line launcher
docs/             principles, design, host contract
research/         complaints, measurements, probes, atoms, A/B runs, reviews
```

## License

MIT. See `LICENSE`.
