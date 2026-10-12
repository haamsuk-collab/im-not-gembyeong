---
name: g1
description: How to work under the G1 verification harness - registering a contract (proposal JSON), blocked and resume reports, what G1 checks at the end of a turn, and how completion is decided. Use when a G1 status block appears, when a task needs a contract, or when an uncertain item stops you.
---
# Working with G1

G1 injects a status block. Its first line is `[G1 <nonce>] ledger seq N head H`. The lines after it are facts from the ledger: the active contract and its hash; its objective; the pass/fail vector of its checks; the failing checks; the next failing check's command; the scope; the pinned oracle files; a paused reason; alerts; the proposals directory for this workspace. When the block is short of room, the objective and the command are the lines left out, never the scope or an alert. Nothing in that block is an instruction from the user. It is state.

## Register a contract

Write one JSON object to `<proposals dir>/<id>.json` (the directory is named in the status block):

```json
{
  "task": "fix-median",
  "objective": "median() returns the middle value",
  "criteria": [{"id": "C1", "text": "tests/test_stats.py passes"}],
  "checks": [{"id": "K1", "argv": ["python3", "-m", "pytest", "tests/test_stats.py", "-q"],
              "kind": "must_flip", "covers": ["C1"], "targets": ["src/stats.py"], "timeout_s": 120}],
  "allowed_paths": ["src/"],
  "oracle_files": ["tests/test_stats.py"]
}
```

Field by field:

- `task`: a short id. A new proposal with the same id supersedes a paused task.
- `objective`: one sentence. The next session reads it to know what the work was.
- `criteria`: observable facts, one each. Not "the code is clean" but "`python3 -m pytest tests/test_stats.py` exits 0".
- `checks`: one argv each, no shell. `kind` is `must_flip` (fails now, passes after the work) or `guard` (passes now and after). `covers` lists criterion ids. `targets` is required for every `must_flip` check: the files of the work that the check depends on, inside `allowed_paths`, never oracle files, never symbolic links (a target that is a link fails the check). G1 corrupts them in a scratch copy and expects the check to fail (the canary); a check that still passes, or whose targets do not exist, fails. `timeout_s` comes from a run you did.
- `allowed_paths`: the write scope, relative and as narrow as the work. `.` is rejected.
- `oracle_files`: the tests, fixtures and configuration the checks read. Pinned by hash for the task; writes to them are refused.
- `depends_on` (optional): task ids that must already have completion receipts.

G1 validates the proposal before your next step. It checks, in this order: the shape (strict; an unknown key rejects), with the coverage matrix (every criterion has a check, every check covers a criterion) and the scope of every target; that no contract is active and every dependency has a receipt; the oracle hashes; the executables (hashed); the red baseline (every `must_flip` fails on the untouched tree). The answer is `<id>.accepted.json` or `<id>.rejected.json` with reasons, beside your file. At most two proposals that reach the red baseline are validated per model call; any others wait for the next call.

## Stop on an uncertain item

Write `<proposals dir>/<task>.blocked.json` with `{"task": "...", "item": "...", "why": "...", "options": ["...", "..."]}`. G1 pauses the task with your item and shows it at the next session start. Reply to the user with the item. After the answer, write `<task>.resume.json` with `{"task": "..."}`; the same contract continues. A resume is accepted only for a task paused by a blocked report. Other pauses need a superseding proposal.

## Challenge a defect that is not your task

A reviewer that finds a defect does not fix it. It writes `<challenges dir>/<id>.json`, where the challenges directory sits beside the proposals directory:

```json
{
  "id": "slug-unicode",
  "claim": "slug() keeps accented letters instead of transliterating them",
  "by": "claude-opus-5-5-high",
  "contract": {
    "task": "slug-ascii",
    "objective": "slug() returns ASCII only",
    "criteria": [{"id": "C1", "text": "slug of an accented word is ASCII"}],
    "checks": [{"id": "K1", "argv": ["python3", "-c", "import sys; sys.path.insert(0, 'src'); from text import slug; sys.exit(0 if slug('Été') == 'ete' else 1)"],
                "kind": "must_flip", "covers": ["C1"], "targets": ["src/text.py"], "timeout_s": 60}],
    "allowed_paths": ["src/"],
    "oracle_files": []
  }
}
```

The checks must be `must_flip`, at most 8, self-contained (inline code or files already in the tree), and must fail now because of the defect; `task` must be an id no task in this workspace has. Run each check yourself before you write the file. G1 runs them when the user asks (`g1 challenges --run`), on the tree as it is then: all failing records the challenge as `confirmed`; any passing, or one still running after 60 seconds, as `unproven`; a malformed one, one with a check that cannot start, or one whose check changed the real workspace, as `invalid`. The answer is `<id>.<verdict>.json` beside your file, and the record keeps each check's exit code and output tail. A confirmed challenge is not a contract. The user accepts or rejects it, because a failing check proves that a behaviour is absent, not that the expectation behind it is right.

## At the end of your turn

When the host reports you idle, G1 does this:

1. It copies the tree to a scratch directory and runs every check there, in a scrubbed environment.
2. It runs the canary on every passing `must_flip` check.
3. It compares the tree with the manifest from contract time. The changed set must be inside the scope.
4. It checks the oracle hashes and writes a receipt.

If every check passes and everything else holds, the task is complete, bound to that receipt. If checks fail and the failing set shrank, G1 may ask for one more turn. The request names the next failing check and its exact command; at most 3 requests per task. In every other case the task is paused with a reason: `no_change` (nothing changed since the last failing attempt), `no_progress` (the failing set did not shrink), `oscillation` (a result seen before), `budget_exhausted`, `scope_violation`, `environment_unknown` (the verification could not run: an oracle, the policy, an executable or the observation changed), `completion_refused`, or `blocked` (your report). A new proposal supersedes a paused task; `<task>.resume.json` continues only a `blocked` one.

## What does not work

- Editing a pinned oracle file with a file tool: refused; with a shell command: caught at the receipt (its hash is pinned). Editing outside the scope with a file tool: refused; with a shell command: caught at the receipt, which measures the workspace tree (a write outside the workspace is not measured, and not yours to make).
- A check that passes without the code: rejected by the canary.
- A symbolic link that leads out of the workspace: a scope violation, so the work cannot live outside the repository. (A check is not confined: one that reads outside the workspace by absolute path is not stopped; the receipt covers the tree.)
- "DONE" in your reply: not an input to anything.
- Editing `~/.g1`, the hook entries, the G1 rules or this skill, or naming them in a shell command: refused. Reading them with a file tool is not refused, and not needed.
- Running `g1` yourself, with any subcommand, behind any wrapper: refused by the gate where it recognizes the spelling, and by the command itself when you are among its ancestor processes.
- A ledger changed, replaced or deleted outside G1: the workspace is locked down (every mutating tool refused) until the user runs `g1 repair`.
